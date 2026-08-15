"""Operator-level regressions without requiring a real PMX file."""

from __future__ import annotations

import unittest

import bpy

from mmd_safe_importer import importer_bridge, operators
from mmd_safe_importer.importer_bridge import ImportResult


_PREFIX = "__mmd_safe_importer_test_operator__"


class _OperatorStub:
    repair_mode = "AUTO"
    rollback_on_failure = True
    preserve_backups = False
    confirm = True

    def __init__(self, filepath="") -> None:
        self.filepath = filepath
        self.reports = []

    def report(self, level, message) -> None:
        self.reports.append((set(level), message))


def _ensure_report_property() -> None:
    if not hasattr(bpy.types.Scene, "mmd_safe_import_report"):
        bpy.types.Scene.mmd_safe_import_report = bpy.props.StringProperty(default="")


class OperatorWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        _ensure_report_property()
        self.original_import_model = importer_bridge.import_model
        self.created_objects = []

    def tearDown(self) -> None:
        importer_bridge.import_model = self.original_import_model
        for obj in list(bpy.data.objects):
            if obj.name.startswith(_PREFIX):
                bpy.data.objects.remove(obj, do_unlink=True)
        for mesh in list(bpy.data.meshes):
            if mesh.name.startswith(_PREFIX) and mesh.users == 0:
                bpy.data.meshes.remove(mesh)

    def test_finished_bridge_without_root_is_rolled_back(self) -> None:
        retained_mesh = bpy.data.meshes.new(f"{_PREFIX}preexisting")
        retained_name = retained_mesh.name
        created_name = f"{_PREFIX}probe"

        def simulated_import(_filepath):
            bpy.data.meshes.new(created_name)
            return ImportResult(True, result={"FINISHED"})

        importer_bridge.import_model = simulated_import
        operator = _OperatorStub()
        result = operators.MMD_SAFE_IMPORT_OT_model.execute(operator, bpy.context)

        self.assertEqual(result, {"CANCELLED"})
        self.assertIsNone(bpy.data.meshes.get(created_name))
        self.assertIs(bpy.data.meshes.get(retained_name), retained_mesh)
        report = bpy.context.scene.mmd_safe_import_report
        self.assertIn("The importer did not create an MMD root object.", report)
        self.assertIn("Rolled back", report)

    def test_cleanup_deletes_only_selected_root_hierarchy(self) -> None:
        if not hasattr(bpy.types.Object, "mmd_type"):
            self.skipTest("mmd_tools MMD root property is unavailable")

        root_a = bpy.data.objects.new(f"{_PREFIX}root_a", None)
        child_a = bpy.data.objects.new(f"{_PREFIX}child_a", None)
        root_b = bpy.data.objects.new(f"{_PREFIX}root_b", None)
        child_b = bpy.data.objects.new(f"{_PREFIX}child_b", None)
        bpy.context.scene.collection.objects.link(root_a)
        bpy.context.scene.collection.objects.link(child_a)
        bpy.context.scene.collection.objects.link(root_b)
        bpy.context.scene.collection.objects.link(child_b)
        child_a.parent = root_a
        child_b.parent = root_b
        root_a.mmd_type = "ROOT"
        root_b.mmd_type = "ROOT"

        root_a_name = root_a.name
        child_a_name = child_a.name
        root_b_name = root_b.name
        child_b_name = child_b.name
        bpy.context.view_layer.objects.active = child_a
        child_a.select_set(True)
        operator = _OperatorStub()
        result = operators.MMD_SAFE_IMPORT_OT_cleanup_root.execute(operator, bpy.context)

        self.assertEqual(result, {"FINISHED"})
        self.assertIsNone(bpy.data.objects.get(root_a_name))
        self.assertIsNone(bpy.data.objects.get(child_a_name))
        self.assertIsNotNone(bpy.data.objects.get(root_b_name))
        self.assertIsNotNone(bpy.data.objects.get(child_b_name))


if __name__ == "__main__":
    unittest.main()
