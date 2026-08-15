"""Blender operators for transactional MMD import and recovery."""

from __future__ import annotations

import bpy
from bpy_extras.io_utils import ImportHelper
from bpy.props import BoolProperty, EnumProperty, StringProperty

from . import availability, importer_bridge, repair, validation
from .diagnostics import Diagnostics, publish
from .transaction import ImportTransaction


def _publish(context, diagnostics: Diagnostics) -> None:
    publish(context.scene, diagnostics)


def _add_group_statuses(diagnostics: Diagnostics, statuses) -> None:
    for name, status in statuses.items():
        if status.valid:
            diagnostics.info(f"Node group '{name}' is valid.")
        else:
            diagnostics.error(f"Node group '{name}': {'; '.join(status.problems)}")


class MMD_SAFE_IMPORT_OT_model(bpy.types.Operator, ImportHelper):
    """Repair known MMD shader groups, then validate a native mmd_tools import."""

    bl_idname = "import_scene.mmd_safe_model"
    bl_label = "Safe PMX/PMD Import"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ".pmx"
    filter_glob: StringProperty(default="*.pmx;*.pmd", options={"HIDDEN"})
    repair_mode: EnumProperty(
        name="Node Group Repair",
        items=(
            ("AUTO", "Automatic", "Repair only missing or invalid groups"),
            ("ALWAYS", "Always replace", "Build fresh known MMD node groups"),
            ("NEVER", "Do not repair", "Validate existing groups without replacement"),
        ),
        default="AUTO",
    )
    rollback_on_failure: BoolProperty(name="Rollback failed import", default=True)
    preserve_backups: BoolProperty(name="Keep node group backups", default=False)

    @classmethod
    def poll(cls, context):
        return availability.import_operator_available()

    def execute(self, context):
        diagnostics = Diagnostics()
        if not availability.import_operator_available():
            diagnostics.error(availability.dependency_message())
            _publish(context, diagnostics)
            self.report({"ERROR"}, availability.dependency_message())
            return {"CANCELLED"}

        transaction = ImportTransaction()
        repair_state = None
        try:
            diagnostics.info("Captured pre-import datablock snapshot.")
            if self.repair_mode == "NEVER":
                statuses = repair.validate_known_groups()
                _add_group_statuses(diagnostics, statuses)
                if any(not status.valid for status in statuses.values()):
                    raise RuntimeError("Known MMD node groups are invalid and repair is disabled.")
            else:
                repair_state, statuses = repair.repair_known_groups(self.repair_mode)
                _add_group_statuses(diagnostics, statuses)
                if any(not status.valid for status in statuses.values()):
                    raise RuntimeError("Known MMD node groups failed post-repair validation.")
                if repair_state.replacements:
                    diagnostics.info("Repaired node groups: " + ", ".join(repair_state.replacements))

            bridge_result = importer_bridge.import_model(self.filepath)
            if not bridge_result.finished:
                raise RuntimeError(bridge_result.error or "mmd_tools import did not finish")

            result = validation.validate_import(transaction.new_objects, transaction.added("images"))
            diagnostics.extend(result.diagnostics.events)
            if not result.valid:
                raise RuntimeError("Post-import validation failed.")

            if repair_state is not None:
                retained = repair.commit_repair(repair_state, self.preserve_backups)
                if retained:
                    diagnostics.warning("Retained in-use node group backups: " + ", ".join(retained))
            diagnostics.info("Safe MMD import completed successfully.")
            _publish(context, diagnostics)
            self.report({"INFO"}, f"Safe import completed: {len(result.roots)} MMD root(s)")
            return {"FINISHED"}
        except Exception as exc:
            diagnostics.error(str(exc))
            if repair_state is not None:
                repair.rollback_repair(repair_state)
                diagnostics.info("Restored node-group state from repair transaction.")
            if self.rollback_on_failure:
                report = transaction.rollback()
                diagnostics.info(f"Rolled back {len(report.removed)} newly created datablock(s).")
                for message in report.retained:
                    diagnostics.warning(message)
            _publish(context, diagnostics)
            self.report({"ERROR"}, "Safe MMD import failed; see MMD Safe Import report")
            return {"CANCELLED"}


class MMD_SAFE_IMPORT_OT_diagnose(bpy.types.Operator):
    bl_idname = "mmd_safe_import.diagnose"
    bl_label = "Diagnose MMD Node Groups"
    bl_options = {"REGISTER"}

    def execute(self, context):
        diagnostics = Diagnostics()
        diagnostics.info(availability.dependency_message())
        _add_group_statuses(diagnostics, repair.validate_known_groups())
        _publish(context, diagnostics)
        self.report({"INFO"}, "MMD node group diagnostics recorded")
        return {"FINISHED"}


class MMD_SAFE_IMPORT_OT_repair_groups(bpy.types.Operator):
    bl_idname = "mmd_safe_import.repair_groups"
    bl_label = "Repair MMD Node Groups"
    bl_options = {"REGISTER", "UNDO"}

    preserve_backups: BoolProperty(name="Keep node group backups", default=True)

    def execute(self, context):
        diagnostics = Diagnostics()
        try:
            state, statuses = repair.repair_known_groups("AUTO")
            _add_group_statuses(diagnostics, statuses)
            retained = repair.commit_repair(state, self.preserve_backups)
            if state.replacements:
                diagnostics.info("Repaired node groups: " + ", ".join(state.replacements))
            else:
                diagnostics.info("Known MMD node groups already satisfy the required interface.")
            if retained:
                diagnostics.warning("Kept backups: " + ", ".join(retained))
            _publish(context, diagnostics)
            self.report({"INFO"}, "MMD node group repair completed")
            return {"FINISHED"}
        except Exception as exc:
            diagnostics.error(str(exc))
            _publish(context, diagnostics)
            self.report({"ERROR"}, "MMD node group repair failed")
            return {"CANCELLED"}


class MMD_SAFE_IMPORT_OT_cleanup_root(bpy.types.Operator):
    bl_idname = "mmd_safe_import.cleanup_root"
    bl_label = "Clean Selected MMD Model"
    bl_options = {"REGISTER", "UNDO"}

    confirm: BoolProperty(
        name="Confirm root hierarchy deletion",
        description="Delete only the selected MMD root and its descendants",
        default=False,
    )

    @classmethod
    def poll(cls, context):
        return availability.find_root_object(context.object) is not None

    def execute(self, context):
        root = availability.find_root_object(context.object)
        diagnostics = Diagnostics()
        if root is None:
            self.report({"ERROR"}, "Select an MMD root or an object below one")
            return {"CANCELLED"}
        objects = [root, *root.children_recursive]
        root_name = root.name
        object_count = len(objects)
        if not self.confirm:
            diagnostics.warning(
                f"Cleanup preview for '{root_name}': {object_count} object(s). Confirm to delete this hierarchy."
            )
            _publish(context, diagnostics)
            self.report({"WARNING"}, "Confirm cleanup in the operator panel")
            return {"CANCELLED"}
        for obj in reversed(objects):
            if obj.name in bpy.data.objects:
                bpy.data.objects.remove(obj, do_unlink=True)
        diagnostics.info(f"Deleted scoped MMD hierarchy '{root_name}' ({object_count} object(s)).")
        _publish(context, diagnostics)
        self.report({"INFO"}, "Selected MMD hierarchy deleted")
        return {"FINISHED"}


_CLASSES = (
    MMD_SAFE_IMPORT_OT_model,
    MMD_SAFE_IMPORT_OT_diagnose,
    MMD_SAFE_IMPORT_OT_repair_groups,
    MMD_SAFE_IMPORT_OT_cleanup_root,
)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
