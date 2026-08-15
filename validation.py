"""Post-import structural validation for Safe MMD Importer."""

from __future__ import annotations

from dataclasses import dataclass, field
import os

import bpy

from .availability import find_root_object
from .diagnostics import Diagnostics
from .repair import MMD_SHADER_DEV, MMD_TEX_UV, validate_known_groups


@dataclass
class ValidationResult:
    roots: list[bpy.types.Object] = field(default_factory=list)
    diagnostics: Diagnostics = field(default_factory=Diagnostics)

    @property
    def valid(self) -> bool:
        return bool(self.roots) and not self.diagnostics.has_errors


def _descendants(root: bpy.types.Object) -> list[bpy.types.Object]:
    return [root, *root.children_recursive]


def _validate_material(material: bpy.types.Material, diagnostics: Diagnostics) -> None:
    if not material.use_nodes or material.node_tree is None:
        diagnostics.warning(f"Material '{material.name}' does not use nodes.")
        return
    groups = {
        node.name: node
        for node in material.node_tree.nodes
        if node.bl_idname == "ShaderNodeGroup" and node.name in {"mmd_shader", "mmd_tex_uv"}
    }
    shader = groups.get("mmd_shader")
    if shader is not None and shader.node_tree is not bpy.data.node_groups.get(MMD_SHADER_DEV):
        diagnostics.warning(f"Material '{material.name}' has a non-canonical mmd_shader node group.")
    tex_uv = groups.get("mmd_tex_uv")
    if tex_uv is not None and tex_uv.node_tree is not bpy.data.node_groups.get(MMD_TEX_UV):
        diagnostics.warning(f"Material '{material.name}' has a non-canonical mmd_tex_uv node group.")


def _validate_root(root: bpy.types.Object, diagnostics: Diagnostics) -> None:
    descendants = _descendants(root)
    armatures = [obj for obj in descendants if obj.type == "ARMATURE"]
    meshes = [obj for obj in descendants if obj.type == "MESH"]
    if not armatures:
        diagnostics.error(f"MMD root '{root.name}' has no armature descendant.")
    if not meshes:
        diagnostics.error(f"MMD root '{root.name}' has no mesh descendant.")

    for armature in armatures:
        bones = armature.data.bones
        dummy = sum("_dummy_" in bone.name for bone in bones)
        shadow = sum("_shadow_" in bone.name for bone in bones)
        diagnostics.info(
            f"Armature '{armature.name}': {len(bones)} bones "
            f"({dummy} dummy, {shadow} shadow helper bones)."
        )

    for mesh in meshes:
        if len(mesh.data.vertices) == 0 or len(mesh.data.polygons) == 0:
            diagnostics.error(f"Mesh '{mesh.name}' has no usable geometry.")
        if not mesh.data.uv_layers:
            diagnostics.warning(f"Mesh '{mesh.name}' has no UV layers.")
        if not mesh.material_slots:
            diagnostics.warning(f"Mesh '{mesh.name}' has no material slots.")
        if armatures and not any(mod.type == "ARMATURE" for mod in mesh.modifiers):
            diagnostics.warning(f"Mesh '{mesh.name}' has no armature modifier.")
        for slot in mesh.material_slots:
            if slot.material is not None:
                _validate_material(slot.material, diagnostics)


def _validate_images(images: set[bpy.types.Image], diagnostics: Diagnostics) -> None:
    missing = []
    for image in images:
        if not image.filepath or image.packed_file is not None:
            continue
        path = bpy.path.abspath(image.filepath)
        if not os.path.exists(path):
            missing.append(image.name)
    if missing:
        diagnostics.warning("Missing texture files: " + ", ".join(sorted(missing)))


def validate_import(
    new_objects: set[bpy.types.Object], new_images: set[bpy.types.Image] | None = None
) -> ValidationResult:
    """Validate roots and their imported content without mutating scene data."""
    diagnostics = Diagnostics()
    roots = sorted(
        (obj for obj in new_objects if getattr(obj, "mmd_type", None) == "ROOT"),
        key=lambda obj: obj.name,
    )
    if not roots:
        diagnostics.error("The importer did not create an MMD root object.")
    for root in roots:
        if find_root_object(root) is not root:
            diagnostics.error(f"New root candidate '{root.name}' does not resolve to itself.")
        else:
            _validate_root(root, diagnostics)
    for name, status in validate_known_groups().items():
        if not status.valid:
            diagnostics.error(f"Node group '{name}' is invalid after import: {'; '.join(status.problems)}")
    _validate_images(new_images if new_images is not None else set(), diagnostics)
    diagnostics.info(f"Validated {len(roots)} new MMD root(s).")
    return ValidationResult(roots=roots, diagnostics=diagnostics)
