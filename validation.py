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


def _required_socket_names(group: bpy.types.NodeTree, in_out: str) -> set[str]:
    names: set[str] = set()
    interface = getattr(group, "interface", None)
    if interface is not None:
        for item in interface.items_tree:
            if getattr(item, "item_type", None) == "SOCKET" and item.in_out == in_out:
                names.add(item.name)
    return names


def _validate_group_node_contract(
    node,
    group_name: str,
    diagnostics: Diagnostics,
    inputs=(),
    outputs=(),
) -> None:
    if node is None:
        diagnostics.warning(f"Material is missing expected '{group_name}' group node.")
        return
    if node.node_tree is None:
        diagnostics.error(f"Material '{node.id_data.name}' has '{node.name}' without a node tree.")
        return
    missing_inputs = set(inputs) - {socket.name for socket in node.inputs}
    missing_outputs = set(outputs) - {socket.name for socket in node.outputs}
    if missing_inputs:
        diagnostics.error(
            f"Material '{node.id_data.name}' '{node.name}' is missing inputs: "
            + ", ".join(sorted(missing_inputs))
        )
    if missing_outputs:
        diagnostics.error(
            f"Material '{node.id_data.name}' '{node.name}' is missing outputs: "
            + ", ".join(sorted(missing_outputs))
        )


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
    tex_uv = groups.get("mmd_tex_uv")
    if shader is None:
        diagnostics.warning(f"Material '{material.name}' is missing its mmd_shader node.")
    elif shader.node_tree is not bpy.data.node_groups.get(MMD_SHADER_DEV):
        diagnostics.warning(f"Material '{material.name}' has a non-canonical mmd_shader node group.")
    _validate_group_node_contract(
        shader,
        MMD_SHADER_DEV,
        diagnostics=diagnostics,
        inputs=_required_socket_names(bpy.data.node_groups[MMD_SHADER_DEV], "INPUT")
        if bpy.data.node_groups.get(MMD_SHADER_DEV) is not None
        else (),
        outputs=("Shader", "Color", "Alpha"),
    )
    if shader is not None:
        if not any(socket.is_linked for socket in shader.outputs if socket.name in {"Shader", "Color", "Alpha"}):
            diagnostics.warning(f"Material '{material.name}' mmd_shader has no linked Shader, Color, or Alpha output.")

    if tex_uv is None:
        diagnostics.warning(f"Material '{material.name}' is missing its mmd_tex_uv node.")
    elif tex_uv.node_tree is not bpy.data.node_groups.get(MMD_TEX_UV):
        diagnostics.warning(f"Material '{material.name}' has a non-canonical mmd_tex_uv node group.")
    _validate_group_node_contract(
        tex_uv,
        MMD_TEX_UV,
        diagnostics=diagnostics,
        outputs=_required_socket_names(bpy.data.node_groups[MMD_TEX_UV], "OUTPUT")
        if bpy.data.node_groups.get(MMD_TEX_UV) is not None
        else (),
    )
    if tex_uv is not None and any(node.bl_idname == "ShaderNodeTexImage" for node in material.node_tree.nodes):
        if not any(socket.is_linked for socket in tex_uv.outputs):
            diagnostics.warning(f"Material '{material.name}' has textures but no linked mmd_tex_uv output.")


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
