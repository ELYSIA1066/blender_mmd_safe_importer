"""Regression tests for conservative import transaction rollback."""

from __future__ import annotations

import unittest

import bpy

from mmd_safe_importer.transaction import ImportTransaction


_PREFIX = "__mmd_safe_importer_test_transaction__"


def _remove_if_current(data_collection, datablock) -> None:
    if datablock is not None and data_collection.get(datablock.name) is datablock:
        data_collection.remove(datablock)


class ImportTransactionTests(unittest.TestCase):
    def tearDown(self) -> None:
        for obj in list(bpy.data.objects):
            if obj.name.startswith(_PREFIX):
                bpy.data.objects.remove(obj, do_unlink=True)
        for collection in list(bpy.data.collections):
            if collection.name.startswith(_PREFIX) and collection.users == 0:
                bpy.data.collections.remove(collection)
        for mesh in list(bpy.data.meshes):
            if mesh.name.startswith(_PREFIX) and mesh.users == 0:
                bpy.data.meshes.remove(mesh)

    def test_rollback_removes_only_post_snapshot_data(self) -> None:
        retained_mesh = bpy.data.meshes.new(f"{_PREFIX}retained")
        retained_name = retained_mesh.name
        transaction = ImportTransaction()

        created_mesh = bpy.data.meshes.new(f"{_PREFIX}created")
        created_name = created_mesh.name
        report = transaction.rollback()

        self.assertIs(bpy.data.meshes.get(retained_name), retained_mesh)
        self.assertIsNone(bpy.data.meshes.get(created_name))
        self.assertIn(f"mesh: {created_name}", report.removed)

    def test_rollback_unlinks_new_scene_collection(self) -> None:
        transaction = ImportTransaction()
        collection = bpy.data.collections.new(f"{_PREFIX}collection")
        bpy.context.scene.collection.children.link(collection)
        collection_name = collection.name

        report = transaction.rollback()

        self.assertIsNone(bpy.data.collections.get(collection_name))
        self.assertIn(f"collection: {collection_name}", report.removed)

    def test_identity_guard_accepts_current_datablock(self) -> None:
        transaction = ImportTransaction()
        mesh = bpy.data.meshes.new(f"{_PREFIX}current")

        self.assertTrue(transaction._is_current(bpy.data.meshes, mesh))


if __name__ == "__main__":
    unittest.main()
