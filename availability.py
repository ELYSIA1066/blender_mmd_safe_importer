"""Runtime capability checks for the official mmd_tools dependency."""

from __future__ import annotations

import importlib

import bpy


_OFFICIAL_MMD_TOOLS_MODULE = "bl_ext.blender_org.mmd_tools"


def official_mmd_tools_available() -> bool:
    """Return whether Blender's official mmd_tools extension is loaded and owns the importer."""
    try:
        module = importlib.import_module(_OFFICIAL_MMD_TOOLS_MODULE)
        operator_class = getattr(bpy.types, "MMD_TOOLS_OT_import_model", None)
        return (
            operator_class is not None
            and operator_class.__module__.startswith(f"{module.__name__}.")
            and hasattr(bpy.ops, "mmd_tools")
            and hasattr(bpy.ops.mmd_tools, "import_model")
        )
    except (ImportError, ModuleNotFoundError, AttributeError, RuntimeError):
        return False


def import_operator_available() -> bool:
    """Return whether the official mmd_tools PMX/PMD import operator is registered."""
    return official_mmd_tools_available()


def mmd_runtime_available() -> bool:
    """Return whether official mmd_tools object properties have been registered."""
    return import_operator_available() and hasattr(bpy.types.Object, "mmd_type")


def dependency_message() -> str:
    if mmd_runtime_available():
        return "official mmd_tools is ready"
    if official_mmd_tools_available():
        return "official mmd_tools importer is registered; MMD object properties are unavailable"
    return (
        "Enable the official Blender Extensions mmd_tools add-on and disable CATS before using "
        "Safe MMD Importer"
    )


def find_root_object(obj: bpy.types.Object | None) -> bpy.types.Object | None:
    """Find an MMD root without importing mmd_tools internals."""
    while obj is not None:
        if getattr(obj, "mmd_type", None) == "ROOT":
            return obj
        obj = obj.parent
    return None
