"""Run MMD Safe Importer regression tests inside Blender.

Usage:
    blender --background --factory-startup --python tests/run_blender_tests.py -- --pmx "D:\\models\\Odette.pmx"

The PMX argument is optional. Without it, only fast in-memory tests run.
"""

from __future__ import annotations

import argparse
import os
import sys
import unittest
from pathlib import Path

import bpy


PACKAGE_DIR = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = str(PACKAGE_DIR.parent)
if PACKAGE_PARENT not in sys.path:
    sys.path.insert(0, PACKAGE_PARENT)

import mmd_safe_importer
from mmd_safe_importer import availability, repair, validation
from mmd_safe_importer.transaction import ImportTransaction


TEST_SCENE_NAME = "__MMD_SAFE_IMPORT_TEST_SCENE__"


def _remove_current(data_collection, datablock) -> None:
    if datablock is not None and data_collection.get(datablock.name) is datablock:
        data_collection.remove(datablock)


def _node_tree_references() -> list[tuple[bpy.types.Node, bpy.types.NodeTree | None]]:
    references = []
    for material in bpy.data.materials:
        if material.node_tree is None:
            continue
        for node in material.node_tree.nodes:
            if node.bl_idname == "ShaderNodeGroup" and node.name in {"mmd_shader", "mmd_tex_uv"}:
                references.append((node, node.node_tree))
    return references


def _restore_node_tree_references(references) -> None:
    for node, node_tree in references:
        try:
            if node.id_data is not None:
                node.node_tree = node_tree
        except ReferenceError:
            pass


class RealPmxRepairRegression(unittest.TestCase):
    pmx_path: Path | None = None

    def setUp(self) -> None:
        if self.pmx_path is None:
            self.skipTest("No PMX path supplied")
        if not self.pmx_path.is_file():
            self.fail(f"PMX file does not exist: {self.pmx_path}")
        if not availability.import_operator_available():
            self.fail("mmd_tools.import_model is not available")

        self.original_scene = bpy.context.window.scene
        self.original_active = bpy.context.view_layer.objects.active
        self.original_selected = list(bpy.context.selected_objects)
        self.node_references = _node_tree_references()
        self.original_groups = {
            name: bpy.data.node_groups.get(name)
            for name in (repair.MMD_TEX_UV, repair.MMD_SHADER_DEV)
        }
        self.original_group_names = {
            name: group.name if group is not None else None
            for name, group in self.original_groups.items()
        }
        self.scene = bpy.data.scenes.new(TEST_SCENE_NAME)
        bpy.context.window.scene = self.scene
        self.import_transaction = None

        for name, group in self.original_groups.items():
            if group is not None:
                group.name = f"__mmd_safe_import_test_original__{name}"
            corrupt = bpy.data.node_groups.new(name, "ShaderNodeTree")
            corrupt.nodes.new("NodeGroupInput")
            corrupt.nodes.new("NodeGroupOutput")

    def tearDown(self) -> None:
        _restore_node_tree_references(self.node_references)
        if self.import_transaction is not None:
            self.import_transaction.rollback()

        for name in (repair.MMD_TEX_UV, repair.MMD_SHADER_DEV):
            group = bpy.data.node_groups.get(name)
            if group is not None and group.users == 0:
                bpy.data.node_groups.remove(group)
        for group in list(bpy.data.node_groups):
            if group.name.startswith("__mmd_safe_import_backup__") and group.users == 0:
                bpy.data.node_groups.remove(group)

        for name, group in self.original_groups.items():
            if group is not None and bpy.data.node_groups.get(group.name) is group:
                group.name = self.original_group_names[name]

        bpy.context.window.scene = self.original_scene
        for obj in bpy.context.selected_objects:
            obj.select_set(False)
        for obj in self.original_selected:
            try:
                obj.select_set(True)
            except ReferenceError:
                pass
        try:
            bpy.context.view_layer.objects.active = self.original_active
        except ReferenceError:
            pass
        if bpy.data.scenes.get(TEST_SCENE_NAME) is self.scene:
            bpy.data.scenes.remove(self.scene)

    def test_corrupt_groups_auto_repair_and_import(self) -> None:
        statuses = repair.validate_known_groups()
        self.assertFalse(statuses[repair.MMD_TEX_UV].valid)
        self.assertFalse(statuses[repair.MMD_SHADER_DEV].valid)

        self.import_transaction = ImportTransaction()
        result = bpy.ops.import_scene.mmd_safe_model(
            "EXEC_DEFAULT",
            filepath=str(self.pmx_path),
            repair_mode="AUTO",
            rollback_on_failure=True,
            preserve_backups=False,
        )

        self.assertIn("FINISHED", result)
        imported = validation.validate_import(
            self.import_transaction.new_objects,
            self.import_transaction.added("images"),
        )
        self.assertTrue(imported.valid, imported.diagnostics.text())
        self.assertEqual(len(imported.roots), 1)
        self.assertTrue(all(status.valid for status in repair.validate_known_groups().values()))

        root = imported.roots[0]
        descendants = [root, *root.children_recursive]
        self.assertTrue(any(obj.type == "ARMATURE" for obj in descendants))
        meshes = [obj for obj in descendants if obj.type == "MESH"]
        self.assertTrue(any(mesh.data.vertices and mesh.data.polygons for mesh in meshes))
        report = self.scene.mmd_safe_import_report
        self.assertIn("Safe MMD import completed successfully.", report)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pmx", type=Path, default=os.environ.get("ODETTE_PMX_PATH"))
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return parser.parse_args(arguments)


def _load_suite(pmx_path: Path | None) -> unittest.TestSuite:
    loader = unittest.defaultTestLoader
    suite = unittest.TestSuite()
    suite.addTests(loader.discover(str(PACKAGE_DIR / "tests"), pattern="test_*.py", top_level_dir=PACKAGE_PARENT))
    RealPmxRepairRegression.pmx_path = pmx_path
    if pmx_path is not None:
        suite.addTests(loader.loadTestsFromTestCase(RealPmxRepairRegression))
    return suite


def main() -> int:
    if bpy.app.version < (4, 2, 0):
        print("FAIL: Blender 4.2 or newer is required")
        return 2
    if not hasattr(bpy.types.Scene, "mmd_safe_import_report"):
        mmd_safe_importer.register()

    arguments = _parse_args()
    result = unittest.TextTestRunner(verbosity=2).run(_load_suite(arguments.pmx))
    print(f"MMD_SAFE_IMPORTER_TESTS: {result.testsRun} run, {len(result.failures)} failures, {len(result.errors)} errors")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    exit_code = main()
    if exit_code:
        raise SystemExit(exit_code)
