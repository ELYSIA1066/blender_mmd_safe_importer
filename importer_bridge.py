"""Thin, defensive bridge to the optional mmd_tools import operator."""

from __future__ import annotations

from dataclasses import dataclass

import bpy

from .availability import import_operator_available


@dataclass
class ImportResult:
    finished: bool
    error: str | None = None
    result: set[str] | None = None


def import_model(filepath: str) -> ImportResult:
    """Run mmd_tools import for one file; callers must validate its output."""
    if not import_operator_available():
        return ImportResult(False, "mmd_tools.import_model is not available")
    try:
        result = set(bpy.ops.mmd_tools.import_model("EXEC_DEFAULT", filepath=filepath))
    except Exception as exc:
        return ImportResult(False, f"mmd_tools import raised {type(exc).__name__}: {exc}")
    if "FINISHED" not in result:
        return ImportResult(False, f"mmd_tools import returned {sorted(result)}", result)
    return ImportResult(True, result=result)
