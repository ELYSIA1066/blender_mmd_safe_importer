"""Runtime capability checks for the optional mmd_tools dependency."""

from __future__ import annotations

import bpy


def import_operator_available() -> bool:
    """Return whether the mmd_tools PMX/PMD import operator is registered."""
    try:
        return hasattr(bpy.ops, "mmd_tools") and hasattr(bpy.ops.mmd_tools, "import_model")
    except (AttributeError, RuntimeError):
        return False


def mmd_runtime_available() -> bool:
    """Return whether mmd_tools object properties have been registered."""
    return import_operator_available() and hasattr(bpy.types.Object, "mmd_type")


def dependency_message() -> str:
    if import_operator_available() and hasattr(bpy.types.Object, "mmd_type"):
        return "mmd_tools is ready"
    if import_operator_available():
        return "mmd_tools importer is registered; MMD object properties are unavailable"
    return "Enable the official mmd_tools extension before using Safe MMD Importer"


def find_root_object(obj: bpy.types.Object | None) -> bpy.types.Object | None:
    """Find an MMD root without importing mmd_tools internals."""
    while obj is not None:
        if getattr(obj, "mmd_type", None) == "ROOT":
            return obj
        obj = obj.parent
    return None
