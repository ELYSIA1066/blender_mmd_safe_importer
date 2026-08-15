"""Repair and validate the two global mmd_tools shader node groups."""

from __future__ import annotations

from dataclasses import dataclass, field

import bpy

MMD_TEX_UV = "MMDTexUV"
MMD_SHADER_DEV = "MMDShaderDev"

UV_OUTPUTS = ("Base UV", "Toon UV", "Sphere UV", "SubTex UV")
SHADER_INPUTS = (
    "Ambient Color", "Diffuse Color", "Specular Color", "Reflect",
    "Base Tex Fac", "Base Tex", "Toon Tex Fac", "Toon Tex",
    "Sphere Tex Fac", "Sphere Tex", "Sphere Mul/Add", "Double Sided",
    "Alpha", "Base Alpha", "Toon Alpha", "Sphere Alpha",
)
SHADER_OUTPUTS = ("Shader", "Color", "Alpha")


@dataclass
class GroupStatus:
    name: str
    valid: bool
    problems: list[str] = field(default_factory=list)


@dataclass
class RepairState:
    backups: dict[str, str] = field(default_factory=dict)
    original_node_trees: list[tuple[bpy.types.Node, bpy.types.NodeTree | None]] = field(default_factory=list)
    replacements: list[str] = field(default_factory=list)


def _socket_names(group: bpy.types.NodeTree, in_out: str) -> set[str]:
    names: set[str] = set()
    interface = getattr(group, "interface", None)
    if interface is not None:
        for item in interface.items_tree:
            if getattr(item, "item_type", None) == "SOCKET" and item.in_out == in_out:
                names.add(item.name)
    if not names:
        node_type = "GROUP_INPUT" if in_out == "INPUT" else "GROUP_OUTPUT"
        for node in group.nodes:
            if node.type == node_type:
                sockets = node.outputs if in_out == "INPUT" else node.inputs
                names.update(socket.name for socket in sockets)
    return names


def validate_group(name: str, required_inputs=(), required_outputs=()) -> GroupStatus:
    group = bpy.data.node_groups.get(name)
    if group is None:
        return GroupStatus(name, False, ["node group does not exist"])
    if group.bl_idname != "ShaderNodeTree":
        return GroupStatus(name, False, [f"expected ShaderNodeTree, found {group.bl_idname}"])
    missing_inputs = set(required_inputs) - _socket_names(group, "INPUT")
    missing_outputs = set(required_outputs) - _socket_names(group, "OUTPUT")
    problems = []
    if missing_inputs:
        problems.append("missing inputs: " + ", ".join(sorted(missing_inputs)))
    if missing_outputs:
        problems.append("missing outputs: " + ", ".join(sorted(missing_outputs)))
    return GroupStatus(name, not problems, problems)


def validate_known_groups() -> dict[str, GroupStatus]:
    return {
        MMD_TEX_UV: validate_group(MMD_TEX_UV, required_outputs=UV_OUTPUTS),
        MMD_SHADER_DEV: validate_group(MMD_SHADER_DEV, SHADER_INPUTS, SHADER_OUTPUTS),
    }


def _new_socket(group, name: str, in_out: str, socket_type: str, default=None, min_value=None, max_value=None):
    socket = group.interface.new_socket(name=name, in_out=in_out, socket_type=socket_type)
    if default is not None:
        socket.default_value = default
    if min_value is not None:
        socket.min_value = min_value
    if max_value is not None:
        socket.max_value = max_value
    return socket


def _new_group(name: str) -> bpy.types.NodeTree:
    group = bpy.data.node_groups.new(name=name, type="ShaderNodeTree")
    group.nodes.new("NodeGroupInput")
    group.nodes.new("NodeGroupOutput")
    return group


def build_tex_uv(name: str) -> bpy.types.NodeTree:
    group = _new_group(name)
    output = next(node for node in group.nodes if node.type == "GROUP_OUTPUT")
    tex_coord = group.nodes.new("ShaderNodeTexCoord")
    mapping = group.nodes.new("ShaderNodeMapping")
    mapping.inputs["Location"].default_value = (0.5, 0.5, 0.0)
    mapping.inputs["Scale"].default_value = (0.5, 0.5, 1.0)
    uv1 = group.nodes.new("ShaderNodeUVMap")
    uv1.uv_map = "UV1"
    for socket_name in UV_OUTPUTS:
        _new_socket(group, socket_name, "OUTPUT", "NodeSocketVector")
    group.links.new(tex_coord.outputs["UV"], output.inputs["Base UV"])
    group.links.new(tex_coord.outputs["Generated"], mapping.inputs["Vector"])
    group.links.new(mapping.outputs["Vector"], output.inputs["Toon UV"])
    group.links.new(mapping.outputs["Vector"], output.inputs["Sphere UV"])
    group.links.new(uv1.outputs["UV"], output.inputs["SubTex UV"])
    return group


def build_shader(name: str) -> bpy.types.NodeTree:
    group = _new_group(name)
    group_input = next(node for node in group.nodes if node.type == "GROUP_INPUT")
    output = next(node for node in group.nodes if node.type == "GROUP_OUTPUT")
    color_defaults = {
        "Ambient Color": (0.4, 0.4, 0.4, 1.0), "Diffuse Color": (0.8, 0.8, 0.8, 1.0),
        "Specular Color": (0.0, 0.0, 0.0, 1.0), "Base Tex": (1.0, 1.0, 1.0, 1.0),
        "Toon Tex": (1.0, 1.0, 1.0, 1.0), "Sphere Tex": (1.0, 1.0, 1.0, 1.0),
    }
    float_defaults = {name: 1.0 for name in SHADER_INPUTS if name not in color_defaults}
    float_defaults.update({"Reflect": 50.0, "Sphere Mul/Add": 0.0, "Double Sided": 0.0})
    for socket_name in SHADER_INPUTS:
        if socket_name in color_defaults:
            _new_socket(group, socket_name, "INPUT", "NodeSocketColor", color_defaults[socket_name])
        else:
            _new_socket(group, socket_name, "INPUT", "NodeSocketFloat", float_defaults[socket_name])
    _new_socket(group, "Shader", "OUTPUT", "NodeSocketShader")
    _new_socket(group, "Color", "OUTPUT", "NodeSocketColor")
    _new_socket(group, "Alpha", "OUTPUT", "NodeSocketFloat")

    mix = group.nodes.new("ShaderNodeMixRGB")
    mix.blend_type = "MULTIPLY"
    mix.inputs["Fac"].default_value = 1.0
    principled = group.nodes.new("ShaderNodeBsdfPrincipled")
    group.links.new(group_input.outputs["Diffuse Color"], mix.inputs[1])
    group.links.new(group_input.outputs["Base Tex"], mix.inputs[2])
    group.links.new(mix.outputs["Color"], principled.inputs["Base Color"])
    group.links.new(group_input.outputs["Specular Color"], principled.inputs["Specular IOR Level"])
    group.links.new(group_input.outputs["Alpha"], principled.inputs["Alpha"])
    group.links.new(principled.outputs["BSDF"], output.inputs["Shader"])
    group.links.new(mix.outputs["Color"], output.inputs["Color"])
    group.links.new(group_input.outputs["Alpha"], output.inputs["Alpha"])
    return group


def _unique_name(prefix: str, name: str) -> str:
    index = 1
    candidate = f"{prefix}{name}"
    while bpy.data.node_groups.get(candidate) is not None:
        index += 1
        candidate = f"{prefix}{name}.{index:03d}"
    return candidate


def _relink_material_nodes(state: RepairState, old_groups: dict[str, bpy.types.NodeTree | None]) -> None:
    replacement_by_node = {"mmd_shader": bpy.data.node_groups.get(MMD_SHADER_DEV), "mmd_tex_uv": bpy.data.node_groups.get(MMD_TEX_UV)}
    for material in bpy.data.materials:
        if material.node_tree is None:
            continue
        for node in material.node_tree.nodes:
            replacement = replacement_by_node.get(node.name)
            if replacement is not None and node.bl_idname == "ShaderNodeGroup":
                state.original_node_trees.append((node, node.node_tree))
                node.node_tree = replacement


def repair_known_groups(mode: str = "AUTO") -> tuple[RepairState, dict[str, GroupStatus]]:
    """Build validated replacements and atomically switch known global MMD groups."""
    statuses = validate_known_groups()
    targets = [name for name, status in statuses.items() if mode == "ALWAYS" or not status.valid]
    state = RepairState()
    if not targets:
        return state, statuses

    builders = {MMD_TEX_UV: build_tex_uv, MMD_SHADER_DEV: build_shader}
    replacements: dict[str, bpy.types.NodeTree] = {}
    try:
        for name in targets:
            temporary = _unique_name("__mmd_safe_import_new__", name)
            replacement = builders[name](temporary)
            required_inputs = SHADER_INPUTS if name == MMD_SHADER_DEV else ()
            required_outputs = SHADER_OUTPUTS if name == MMD_SHADER_DEV else UV_OUTPUTS
            candidate = validate_group(temporary, required_inputs, required_outputs)
            if not candidate.valid:
                raise RuntimeError(f"Generated {name} failed validation: {'; '.join(candidate.problems)}")
            replacements[name] = replacement

        old_groups = {name: bpy.data.node_groups.get(name) for name in targets}
        for name, old_group in old_groups.items():
            if old_group is not None:
                backup = _unique_name("__mmd_safe_import_backup__", name)
                old_group.name = backup
                state.backups[name] = backup
        for name, replacement in replacements.items():
            replacement.name = name
            state.replacements.append(name)
        _relink_material_nodes(state, old_groups)
        return state, validate_known_groups()
    except Exception:
        rollback_repair(state)
        for replacement in replacements.values():
            if replacement.name in bpy.data.node_groups and replacement.users == 0:
                bpy.data.node_groups.remove(replacement)
        raise


def rollback_repair(state: RepairState) -> None:
    for node, original_tree in reversed(state.original_node_trees):
        if node.id_data is not None:
            node.node_tree = original_tree
    for name in state.replacements:
        replacement = bpy.data.node_groups.get(name)
        if replacement is not None and replacement.users == 0:
            bpy.data.node_groups.remove(replacement)
    for original_name, backup_name in state.backups.items():
        backup = bpy.data.node_groups.get(backup_name)
        if backup is not None:
            existing = bpy.data.node_groups.get(original_name)
            if existing is not None and existing.users == 0:
                bpy.data.node_groups.remove(existing)
            backup.name = original_name


def commit_repair(state: RepairState, preserve_backups: bool = False) -> list[str]:
    retained = []
    if preserve_backups:
        return list(state.backups.values())
    for backup_name in state.backups.values():
        backup = bpy.data.node_groups.get(backup_name)
        if backup is not None:
            if backup.users == 0:
                bpy.data.node_groups.remove(backup)
            else:
                retained.append(backup.name)
    return retained
