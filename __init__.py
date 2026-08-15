"""Standalone transactional MMD import repair extension."""

bl_info = {
    "name": "MMD Safe Importer",
    "author": "Local",
    "version": (0, 1, 1),
    "blender": (4, 2, 9),
    "location": "File > Import > Safe PMX/PMD",
    "description": "Repairs known mmd_tools node-group failures and validates PMX imports",
    "category": "Import-Export",
}

import bpy

from . import diagnostics, operators, ui


def register():
    bpy.types.Scene.mmd_safe_import_report = bpy.props.StringProperty(
        name="Safe MMD Import Report", default=""
    )
    operators.register()
    ui.register()


def unregister():
    ui.unregister()
    operators.unregister()
    if hasattr(bpy.types.Scene, "mmd_safe_import_report"):
        del bpy.types.Scene.mmd_safe_import_report
