"""Regression coverage for the temporary Blender 4.x mmd_tools compatibility patch."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
import unittest
from unittest import mock

import bpy

from mmd_safe_importer import material_compat


_PREFIX = "__mmd_safe_importer_test_material_compat__"
_TARGET_NAME = "_FnMaterialCycles__update_shader_input"


class _FakeUpdaterTarget:
    def __init__(self, material) -> None:
        self.material = material
        self.updated = False

    def _FnMaterialCycles__update_shader_nodes(self) -> None:
        self.updated = True

    def _FnMaterialCycles__update_shader_input(self, name, val) -> None:
        raise AssertionError("The original updater must be replaced during this test")


class MaterialCompatibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_descriptor = _FakeUpdaterTarget.__dict__[_TARGET_NAME]
        self.group = bpy.data.node_groups.new(f"{_PREFIX}group", "ShaderNodeTree")
        self.group.interface.new_socket(name="Scalar", in_out="INPUT", socket_type="NodeSocketFloat")
        self.group.interface.items_tree["Scalar"].min_value = 0.0
        self.group.interface.items_tree["Scalar"].max_value = 1.0
        self.group.interface.new_socket(name="Color", in_out="INPUT", socket_type="NodeSocketColor")
        self.group.nodes.new("NodeGroupInput")
        self.group.nodes.new("NodeGroupOutput")
        self.material = bpy.data.materials.new(f"{_PREFIX}material")
        self.material.use_nodes = True
        self.shader = self.material.node_tree.nodes.new("ShaderNodeGroup")
        self.shader.name = "mmd_shader"
        self.shader.node_tree = self.group

    def tearDown(self) -> None:
        while material_compat.compatibility_patch_active():
            for target_class in tuple(material_compat._PATCH_STATES):
                material_compat._restore_for_class(target_class)
        if _FakeUpdaterTarget.__dict__.get(_TARGET_NAME) is not self.original_descriptor:
            setattr(_FakeUpdaterTarget, _TARGET_NAME, self.original_descriptor)
        if bpy.data.materials.get(self.material.name) is self.material:
            bpy.data.materials.remove(self.material)
        if bpy.data.node_groups.get(self.group.name) is self.group:
            bpy.data.node_groups.remove(self.group)

    def _target(self):
        return _FakeUpdaterTarget(self.material)

    def _resolved_target(self):
        return _FakeUpdaterTarget, "test target"

    def test_scalar_clamps_and_color_is_not_scalar_clamped(self) -> None:
        target = self._target()
        with mock.patch.object(material_compat, "_resolve_target_class", self._resolved_target):
            with material_compat.patched_shader_input_update() as status:
                self.assertTrue(status.active, status.message)
                target._FnMaterialCycles__update_shader_input("Scalar", 4.0)
                target._FnMaterialCycles__update_shader_input("Color", (0.25, 0.75, 0.5, 1.0))

        self.assertTrue(target.updated)
        self.assertEqual(self.shader.inputs["Scalar"].default_value, 1.0)
        self.assertEqual(tuple(self.shader.inputs["Color"].default_value), (0.25, 0.75, 0.5, 1.0))

    def test_missing_interface_socket_still_updates_instance_socket(self) -> None:
        target = self._target()
        self.group.interface.remove(self.group.interface.items_tree["Scalar"])
        with mock.patch.object(material_compat, "_resolve_target_class", self._resolved_target):
            with material_compat.patched_shader_input_update() as status:
                self.assertTrue(status.active, status.message)
                target._FnMaterialCycles__update_shader_input("Scalar", 4.0)

        self.assertIsNone(self.shader.inputs.get("Scalar"))

    def test_mmd_material_is_a_safe_no_op(self) -> None:
        self.material.name = "mmd_edge.test"
        target = self._target()
        with mock.patch.object(material_compat, "_resolve_target_class", self._resolved_target):
            with material_compat.patched_shader_input_update():
                target._FnMaterialCycles__update_shader_input("Scalar", 0.5)

        self.assertFalse(target.updated)
        self.assertEqual(self.shader.inputs["Scalar"].default_value, 0.0)

    def test_normal_exceptional_and_nested_contexts_restore_exact_descriptor(self) -> None:
        with mock.patch.object(material_compat, "_resolve_target_class", self._resolved_target):
            with material_compat.patched_shader_input_update() as outer:
                self.assertTrue(outer.active)
                wrapper = _FakeUpdaterTarget.__dict__[_TARGET_NAME]
                self.assertIsNot(wrapper, self.original_descriptor)
                with material_compat.patched_shader_input_update() as inner:
                    self.assertTrue(inner.active)
                    self.assertIs(_FakeUpdaterTarget.__dict__[_TARGET_NAME], wrapper)
                self.assertIs(_FakeUpdaterTarget.__dict__[_TARGET_NAME], wrapper)
            self.assertIs(_FakeUpdaterTarget.__dict__[_TARGET_NAME], self.original_descriptor)

            with self.assertRaisesRegex(RuntimeError, "probe"):
                with material_compat.patched_shader_input_update():
                    raise RuntimeError("probe")
            self.assertIs(_FakeUpdaterTarget.__dict__[_TARGET_NAME], self.original_descriptor)

    def test_unknown_signature_fails_closed_without_mutation(self) -> None:
        class _UnexpectedTarget:
            def _FnMaterialCycles__update_shader_input(self, only_one_argument):
                return only_one_argument

        original = _UnexpectedTarget.__dict__[_TARGET_NAME]
        with mock.patch.object(
            material_compat,
            "_resolve_target_class",
            return_value=(_UnexpectedTarget, "unexpected test target"),
        ):
            with material_compat.patched_shader_input_update() as status:
                self.assertFalse(status.active)
                self.assertIn("not recognized", status.message)
        self.assertIs(_UnexpectedTarget.__dict__[_TARGET_NAME], original)

    def test_missing_target_module_fails_closed(self) -> None:
        with mock.patch.object(
            material_compat,
            "_resolve_target_class",
            return_value=(None, "CATS/mmd_tools material module is unavailable"),
        ):
            with material_compat.patched_shader_input_update() as status:
                self.assertFalse(status.active)
                self.assertIn("unavailable", status.message)


if __name__ == "__main__":
    unittest.main()
