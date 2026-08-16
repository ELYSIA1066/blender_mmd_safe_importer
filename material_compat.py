"""Temporary Blender 4.x compatibility bridge for legacy mmd_tools material updates."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import importlib
import inspect
import numbers
from typing import Iterator

import bpy


_TARGET_CLASS_NAME = "_FnMaterialCycles"
_TARGET_METHOD_NAME = "_FnMaterialCycles__update_shader_input"
_MODULE_NAMES = ("mmd_tools_local.core.material", "mmd_tools.core.material")


@dataclass(frozen=True)
class PatchStatus:
    active: bool
    message: str


@dataclass
class _PatchState:
    original: object
    wrapper: object
    depth: int = 1


_PATCH_STATES: dict[type, _PatchState] = {}


def _find_input_interface_socket(node_tree, name: str):
    interface = getattr(node_tree, "interface", None)
    items = getattr(interface, "items_tree", ()) if interface is not None else ()
    for item in items:
        if (
            getattr(item, "item_type", None) == "SOCKET"
            and getattr(item, "in_out", None) == "INPUT"
            and getattr(item, "name", None) == name
        ):
            return item
    return None


def _clamp_scalar(value, interface_socket):
    if not isinstance(value, numbers.Real):
        return value
    if interface_socket is None:
        return value
    minimum = getattr(interface_socket, "min_value", None)
    maximum = getattr(interface_socket, "max_value", None)
    if not isinstance(minimum, numbers.Real) or not isinstance(maximum, numbers.Real):
        return value
    return min(max(value, minimum), maximum)


def _compatible_updater(self, name, value) -> None:
    material = self.material
    if material.name.startswith("mmd_"):
        return

    update_nodes = getattr(self, "_FnMaterialCycles__update_shader_nodes")
    update_nodes()
    shader = material.node_tree.nodes.get("mmd_shader", None)
    if shader is None:
        return

    input_socket = shader.inputs.get(name)
    if input_socket is None:
        return

    interface_socket = _find_input_interface_socket(getattr(shader, "node_tree", None), name)
    input_socket.default_value = _clamp_scalar(value, interface_socket)


def _expected_original(raw_descriptor) -> bool:
    if not inspect.isfunction(raw_descriptor):
        return False
    try:
        parameters = tuple(inspect.signature(raw_descriptor).parameters)
    except (TypeError, ValueError):
        return False
    return parameters == ("self", "name", "val")


def _resolve_target_class() -> tuple[type | None, str]:
    for module_name in _MODULE_NAMES:
        try:
            module = importlib.import_module(module_name)
        except (ImportError, ModuleNotFoundError):
            continue
        target_class = getattr(module, _TARGET_CLASS_NAME, None)
        if target_class is None:
            return None, f"'{module_name}' has no {_TARGET_CLASS_NAME}"
        return target_class, f"resolved '{module_name}'"
    return None, "CATS/mmd_tools material module is unavailable"


def _install_for_class(target_class: type) -> PatchStatus:
    existing = _PATCH_STATES.get(target_class)
    if existing is not None:
        if target_class.__dict__.get(_TARGET_METHOD_NAME) is existing.wrapper:
            existing.depth += 1
            return PatchStatus(True, "reused temporary Blender 4.x mmd_tools compatibility patch")
        _PATCH_STATES.pop(target_class, None)
        return PatchStatus(False, "compatibility patch target changed while already active")

    raw_descriptor = target_class.__dict__.get(_TARGET_METHOD_NAME)
    if not _expected_original(raw_descriptor):
        return PatchStatus(False, "expected legacy mmd_tools shader-input updater was not recognized")

    try:
        setattr(target_class, _TARGET_METHOD_NAME, _compatible_updater)
    except (AttributeError, TypeError) as exc:
        return PatchStatus(False, f"could not install mmd_tools compatibility patch: {exc}")

    if target_class.__dict__.get(_TARGET_METHOD_NAME) is not _compatible_updater:
        try:
            setattr(target_class, _TARGET_METHOD_NAME, raw_descriptor)
        except (AttributeError, TypeError):
            pass
        return PatchStatus(False, "mmd_tools compatibility patch installation could not be verified")

    _PATCH_STATES[target_class] = _PatchState(raw_descriptor, _compatible_updater)
    return PatchStatus(True, "applied temporary Blender 4.x mmd_tools shader-input compatibility patch")


def _restore_for_class(target_class: type) -> None:
    state = _PATCH_STATES.get(target_class)
    if state is None:
        return
    state.depth -= 1
    if state.depth > 0:
        return
    try:
        if target_class.__dict__.get(_TARGET_METHOD_NAME) is state.wrapper:
            setattr(target_class, _TARGET_METHOD_NAME, state.original)
    finally:
        _PATCH_STATES.pop(target_class, None)


@contextmanager
def patched_shader_input_update() -> Iterator[PatchStatus]:
    """Temporarily replace CATS' Blender-3.x node-tree input lookup during import."""
    if bpy.app.version < (4, 0, 0):
        yield PatchStatus(True, "using native pre-Blender-4 mmd_tools shader-input updater")
        return

    target_class, resolution = _resolve_target_class()
    if target_class is None:
        yield PatchStatus(False, resolution)
        return

    status = _install_for_class(target_class)
    if not status.active:
        yield PatchStatus(False, status.message)
        return

    try:
        yield status
    finally:
        _restore_for_class(target_class)


def compatibility_patch_active() -> bool:
    """Return whether this extension currently owns an installed compatibility patch."""
    return bool(_PATCH_STATES)
