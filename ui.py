"""File menu and 3D View sidebar for Safe MMD Importer."""

from __future__ import annotations

import bpy

from . import availability, repair


def draw_import_menu(self, context):
    self.layout.operator("import_scene.mmd_safe_model", text="Safe PMX/PMD (.pmx, .pmd)")


class MMD_SAFE_IMPORT_PT_panel(bpy.types.Panel):
    bl_label = "MMD Safe Import"
    bl_idname = "MMD_SAFE_IMPORT_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MMD Safe"

    def draw(self, context):
        layout = self.layout
        layout.label(text=availability.dependency_message())

        import_box = layout.box()
        import_box.enabled = availability.import_operator_available()
        import_box.operator("import_scene.mmd_safe_model", icon="IMPORT")

        node_box = layout.box()
        node_box.label(text="Global node groups")
        for name, status in repair.validate_known_groups().items():
            icon = "CHECKMARK" if status.valid else "ERROR"
            node_box.label(text=name, icon=icon)
            for problem in status.problems:
                row = node_box.row()
                row.scale_x = 0.9
                row.label(text=problem, icon="DOT")
        row = node_box.row(align=True)
        row.operator("mmd_safe_import.diagnose", text="Diagnose")
        row.operator("mmd_safe_import.repair_groups", text="Repair")

        cleanup = layout.box()
        cleanup.label(text="Selected MMD root")
        cleanup.enabled = availability.find_root_object(context.object) is not None
        cleanup.operator("mmd_safe_import.cleanup_root", text="Preview / Clean Hierarchy", icon="TRASH")

        report = getattr(context.scene, "mmd_safe_import_report", "")
        if report:
            report_box = layout.box()
            report_box.label(text="Latest report")
            for line in report.splitlines()[-8:]:
                report_box.label(text=line)


_CLASSES = (MMD_SAFE_IMPORT_PT_panel,)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_import.append(draw_import_menu)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(draw_import_menu)
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
