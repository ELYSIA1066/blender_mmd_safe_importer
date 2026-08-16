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


def _has_link(group: bpy.types.NodeTree, from_node, from_socket: str, to_node, to_socket: str) -> bool:
    return any(
        link.from_node == from_node
        and link.from_socket.name == from_socket
        and link.to_node == to_node
        and link.to_socket.name == to_socket
        for link in group.links
    )


def _semantic_problems(group: bpy.types.NodeTree, name: str) -> list[str]:
    """Reject interface-complete groups that cannot implement MMD materials."""
    nodes = list(group.nodes)
    if name == MMD_TEX_UV:
        required_types = {"TEX_COORD", "UVMAP", "VECT_TRANSFORM", "MAPPING"}
        missing = required_types - {node.type for node in nodes}
        if missing:
            return ["missing MMD UV nodes: " + ", ".join(sorted(missing))]
        tex_coord = next(node for node in nodes if node.type == "TEX_COORD")
        vector_transform = next(node for node in nodes if node.type == "VECT_TRANSFORM")
        mapping = next(node for node in nodes if node.type == "MAPPING")
        if not _has_link(group, tex_coord, "Normal", vector_transform, "Vector"):
            return ["MMD UV group does not transform camera-space normals"]
        if not _has_link(group, vector_transform, "Vector", mapping, "Vector"):
            return ["MMD UV group does not map transformed normals"]
        return []

    required_types = {"BSDF_DIFFUSE", "BSDF_GLOSSY", "BSDF_TRANSPARENT", "NEW_GEOMETRY"}
    missing = required_types - {node.type for node in nodes}
    if missing:
        return ["missing MMD shader nodes: " + ", ".join(sorted(missing))]
    mix_nodes = [node for node in nodes if node.type == "MIX_RGB"]
    blend_types = {node.blend_type for node in mix_nodes}
    required_blends = {"ADD", "MULTIPLY", "MIX"}
    if required_blends - blend_types:
        return ["missing MMD texture blend stages: " + ", ".join(sorted(required_blends - blend_types))]
    if len([node for node in nodes if node.type == "MIX_SHADER"]) < 2:
        return ["missing MMD alpha and surface shader mixing"]
    return []


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
    if not problems and name in {MMD_TEX_UV, MMD_SHADER_DEV}:
        problems.extend(_semantic_problems(group, name))
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
    """Build the same camera-normal UV projection used by official mmd_tools."""
    group = _new_group(name)
    output = next(node for node in group.nodes if node.type == "GROUP_OUTPUT")
    tex_coord = group.nodes.new("ShaderNodeTexCoord")
    tex_coord1 = group.nodes.new("ShaderNodeUVMap")
    tex_coord1.uv_map = "UV1"
    vector_transform = group.nodes.new("ShaderNodeVectorTransform")
    vector_transform.vector_type = "NORMAL"
    vector_transform.convert_from = "OBJECT"
    vector_transform.convert_to = "CAMERA"
    mapping = group.nodes.new("ShaderNodeMapping")
    mapping.vector_type = "POINT"
    mapping.inputs["Location"].default_value = (0.5, 0.5, 0.0)
    mapping.inputs["Scale"].default_value = (0.5, 0.5, 1.0)
    for socket_name in UV_OUTPUTS:
        _new_socket(group, socket_name, "OUTPUT", "NodeSocketVector")
    group.links.new(tex_coord.outputs["UV"], output.inputs["Base UV"])
    group.links.new(tex_coord.outputs["Normal"], vector_transform.inputs["Vector"])
    group.links.new(vector_transform.outputs["Vector"], mapping.inputs["Vector"])
    group.links.new(mapping.outputs["Vector"], output.inputs["Toon UV"])
    group.links.new(mapping.outputs["Vector"], output.inputs["Sphere UV"])
    group.links.new(tex_coord1.outputs["UV"], output.inputs["SubTex UV"])
    return group


def build_shader(name: str) -> bpy.types.NodeTree:
    """Build the Blender-4-compatible MMDShaderDev graph from official mmd_tools."""
    group = _new_group(name)
    group_input = next(node for node in group.nodes if node.type == "GROUP_INPUT")
    output = next(node for node in group.nodes if node.type == "GROUP_OUTPUT")

    def mix(blend_type: str, fac=None):
        node = group.nodes.new("ShaderNodeMixRGB")
        node.blend_type = blend_type
        if fac is not None:
            node.inputs["Fac"].default_value = fac
        return node

    def math(operation: str, value1=None):
        node = group.nodes.new("ShaderNodeMath")
        node.operation = operation
        if value1 is not None:
            node.inputs[0].default_value = value1
        return node

    diffuse = mix("ADD", 0.6)
    diffuse.use_clamp = True
    base = mix("MULTIPLY")
    toon = mix("MULTIPLY")
    sphere_mul = mix("MULTIPLY")
    sphere_add = mix("ADD")
    sphere = mix("MIX")

    geometry = group.nodes.new("ShaderNodeNewGeometry")
    backface = math("LESS_THAN")
    cull = math("MAXIMUM")
    alpha = math("MINIMUM")
    alpha_base = math("MULTIPLY")
    alpha_toon = math("MULTIPLY")
    alpha_sphere = math("MULTIPLY")
    reflect = math("DIVIDE", 1.0)
    reflect.use_clamp = True

    diffuse_bsdf = group.nodes.new("ShaderNodeBsdfDiffuse")
    glossy_bsdf = group.nodes.new("ShaderNodeBsdfAnisotropic")
    surface_mix = group.nodes.new("ShaderNodeMixShader")
    surface_mix.inputs["Fac"].default_value = 0.02
    transparent = group.nodes.new("ShaderNodeBsdfTransparent")
    alpha_mix = group.nodes.new("ShaderNodeMixShader")

    links = group.links
    links.new(reflect.outputs["Value"], glossy_bsdf.inputs["Roughness"])
    links.new(diffuse_bsdf.outputs["BSDF"], surface_mix.inputs[1])
    links.new(glossy_bsdf.outputs["BSDF"], surface_mix.inputs[2])
    links.new(diffuse.outputs["Color"], base.inputs["Color1"])
    links.new(base.outputs["Color"], toon.inputs["Color1"])
    links.new(toon.outputs["Color"], sphere_mul.inputs["Color1"])
    links.new(toon.outputs["Color"], sphere_add.inputs["Color1"])
    links.new(sphere_mul.outputs["Color"], sphere.inputs["Color1"])
    links.new(sphere_add.outputs["Color"], sphere.inputs["Color2"])
    links.new(sphere.outputs["Color"], diffuse_bsdf.inputs["Color"])
    links.new(geometry.outputs["Backfacing"], backface.inputs[0])
    links.new(backface.outputs["Value"], cull.inputs[0])
    links.new(cull.outputs["Value"], alpha.inputs[0])
    links.new(alpha_base.outputs["Value"], alpha_toon.inputs[0])
    links.new(alpha_toon.outputs["Value"], alpha_sphere.inputs[0])
    links.new(alpha_sphere.outputs["Value"], alpha.inputs[1])
    links.new(alpha.outputs["Value"], alpha_mix.inputs["Fac"])
    links.new(transparent.outputs["BSDF"], alpha_mix.inputs[1])
    links.new(surface_mix.outputs["Shader"], alpha_mix.inputs[2])

    color_defaults = {
        "Ambient Color": (0.4, 0.4, 0.4, 1.0),
        "Diffuse Color": (0.8, 0.8, 0.8, 1.0),
        "Specular Color": (0.0, 0.0, 0.0, 1.0),
        "Base Tex": (1.0, 1.0, 1.0, 1.0),
        "Toon Tex": (1.0, 1.0, 1.0, 1.0),
        "Sphere Tex": (1.0, 1.0, 1.0, 1.0),
    }
    float_defaults = {
        "Reflect": 50.0, "Base Tex Fac": 1.0, "Toon Tex Fac": 1.0,
        "Sphere Tex Fac": 1.0, "Sphere Mul/Add": 0.0, "Double Sided": 0.0,
        "Alpha": 1.0, "Base Alpha": 1.0, "Toon Alpha": 1.0, "Sphere Alpha": 1.0,
    }
    for socket_name in SHADER_INPUTS:
        if socket_name in color_defaults:
            _new_socket(group, socket_name, "INPUT", "NodeSocketColor", color_defaults[socket_name])
        else:
            minimum, maximum = (1.0, 512.0) if socket_name == "Reflect" else (0.0, 1.0)
            _new_socket(group, socket_name, "INPUT", "NodeSocketFloat", float_defaults[socket_name], minimum, maximum)
    _new_socket(group, "Shader", "OUTPUT", "NodeSocketShader")
    _new_socket(group, "Color", "OUTPUT", "NodeSocketColor")
    _new_socket(group, "Alpha", "OUTPUT", "NodeSocketFloat", 1.0, 0.0, 1.0)

    links.new(group_input.outputs["Sphere Tex Fac"], sphere_add.inputs["Fac"])
    links.new(group_input.outputs["Sphere Tex"], sphere_add.inputs["Color2"])
    links.new(group_input.outputs["Ambient Color"], diffuse.inputs["Color1"])
    links.new(group_input.outputs["Diffuse Color"], diffuse.inputs["Color2"])
    links.new(group_input.outputs["Specular Color"], glossy_bsdf.inputs["Color"])
    links.new(group_input.outputs["Reflect"], reflect.inputs[1])
    links.new(group_input.outputs["Base Tex Fac"], base.inputs["Fac"])
    links.new(group_input.outputs["Base Tex"], base.inputs["Color2"])
    links.new(group_input.outputs["Toon Tex Fac"], toon.inputs["Fac"])
    links.new(group_input.outputs["Toon Tex"], toon.inputs["Color2"])
    links.new(group_input.outputs["Sphere Tex Fac"], sphere_mul.inputs["Fac"])
    links.new(group_input.outputs["Sphere Tex"], sphere_mul.inputs["Color2"])
    links.new(group_input.outputs["Sphere Mul/Add"], sphere.inputs["Fac"])
    links.new(group_input.outputs["Double Sided"], cull.inputs[1])
    links.new(group_input.outputs["Alpha"], alpha_base.inputs[0])
    links.new(group_input.outputs["Base Alpha"], alpha_base.inputs[1])
    links.new(group_input.outputs["Toon Alpha"], alpha_toon.inputs[1])
    links.new(group_input.outputs["Sphere Alpha"], alpha_sphere.inputs[1])
    links.new(alpha_mix.outputs["Shader"], output.inputs["Shader"])
    links.new(sphere.outputs["Color"], output.inputs["Color"])
    links.new(alpha.outputs["Value"], output.inputs["Alpha"])
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
