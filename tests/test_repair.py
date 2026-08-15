"""Regression tests for known MMD node-group repair transactions."""

from __future__ import annotations

import unittest

import bpy

from mmd_safe_importer import repair


_PREFIX = "__mmd_safe_importer_test_repair__"


def _remove_group(group) -> None:
    if group is not None and bpy.data.node_groups.get(group.name) is group:
        bpy.data.node_groups.remove(group)


class KnownGroupRepairTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_groups = {
            name: bpy.data.node_groups.get(name)
            for name in (repair.MMD_TEX_UV, repair.MMD_SHADER_DEV)
        }
        self.original_names = {name: group.name if group is not None else None for name, group in self.original_groups.items()}
        self.materials = []
        self.repair_state = None

        for name, group in self.original_groups.items():
            if group is not None:
                group.name = f"{_PREFIX}original__{name}"
            corrupt = bpy.data.node_groups.new(name, "ShaderNodeTree")
            corrupt.nodes.new("NodeGroupInput")
            corrupt.nodes.new("NodeGroupOutput")

    def tearDown(self) -> None:
        if self.repair_state is not None:
            repair.rollback_repair(self.repair_state)

        for material in self.materials:
            if bpy.data.materials.get(material.name) is material:
                bpy.data.materials.remove(material)

        for name in (repair.MMD_TEX_UV, repair.MMD_SHADER_DEV):
            group = bpy.data.node_groups.get(name)
            if group is not None:
                bpy.data.node_groups.remove(group)

        for original_name, group in self.original_groups.items():
            if group is not None and bpy.data.node_groups.get(group.name) is group:
                group.name = original_name

        for group in list(bpy.data.node_groups):
            if group.name.startswith(_PREFIX) and group.users == 0:
                bpy.data.node_groups.remove(group)

    def _make_material_with_known_nodes(self):
        material = bpy.data.materials.new(f"{_PREFIX}material")
        material.use_nodes = True
        shader = material.node_tree.nodes.new("ShaderNodeGroup")
        shader.name = "mmd_shader"
        shader.node_tree = bpy.data.node_groups[repair.MMD_SHADER_DEV]
        tex_uv = material.node_tree.nodes.new("ShaderNodeGroup")
        tex_uv.name = "mmd_tex_uv"
        tex_uv.node_tree = bpy.data.node_groups[repair.MMD_TEX_UV]
        self.materials.append(material)
        return shader, tex_uv

    def test_auto_repair_replaces_invalid_contracts_and_relinks_materials(self) -> None:
        statuses = repair.validate_known_groups()
        self.assertFalse(statuses[repair.MMD_TEX_UV].valid)
        self.assertFalse(statuses[repair.MMD_SHADER_DEV].valid)

        shader, tex_uv = self._make_material_with_known_nodes()
        old_shader = shader.node_tree
        old_tex_uv = tex_uv.node_tree
        self.repair_state, statuses = repair.repair_known_groups("AUTO")

        self.assertTrue(all(status.valid for status in statuses.values()))
        self.assertEqual(set(self.repair_state.replacements), {repair.MMD_TEX_UV, repair.MMD_SHADER_DEV})
        self.assertIs(shader.node_tree, bpy.data.node_groups[repair.MMD_SHADER_DEV])
        self.assertIs(tex_uv.node_tree, bpy.data.node_groups[repair.MMD_TEX_UV])
        self.assertIsNot(shader.node_tree, old_shader)
        self.assertIsNot(tex_uv.node_tree, old_tex_uv)

    def test_rollback_restores_original_group_nodes_and_names(self) -> None:
        shader, tex_uv = self._make_material_with_known_nodes()
        original_shader = shader.node_tree
        original_tex_uv = tex_uv.node_tree
        self.repair_state, _ = repair.repair_known_groups("AUTO")

        repair.rollback_repair(self.repair_state)
        self.repair_state = None

        self.assertIs(shader.node_tree, original_shader)
        self.assertIs(tex_uv.node_tree, original_tex_uv)
        self.assertIs(bpy.data.node_groups[repair.MMD_SHADER_DEV], original_shader)
        self.assertIs(bpy.data.node_groups[repair.MMD_TEX_UV], original_tex_uv)

    def test_commit_removes_unused_backups(self) -> None:
        self.repair_state, _ = repair.repair_known_groups("AUTO")
        backup_names = list(self.repair_state.backups.values())

        retained = repair.commit_repair(self.repair_state, preserve_backups=False)
        self.repair_state = None

        self.assertEqual(retained, [])
        self.assertTrue(all(bpy.data.node_groups.get(name) is None for name in backup_names))


if __name__ == "__main__":
    unittest.main()
