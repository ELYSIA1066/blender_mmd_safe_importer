#!/usr/bin/env python3
"""Build the installable MMD Safe Importer Blender extension archive."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = PROJECT_ROOT / "blender_manifest.toml"
DIST_DIR = PROJECT_ROOT / "dist"

ARCHIVE_ROOT = "mmd_safe_importer"
RELEASE_FILES = (
    "__init__.py",
    "availability.py",
    "blender_manifest.toml",
    "diagnostics.py",
    "importer_bridge.py",
    "operators.py",
    "repair.py",
    "transaction.py",
    "ui.py",
    "validation.py",
    "README.md",
    "LICENSE",
)
FORBIDDEN_PARTS = ("tests/", "scripts/", ".git/", ".github/", "dist/")
FORBIDDEN_SUFFIXES = (".pyc", ".pyo", ".zip", ".pmx", ".pmd", ".vmd", ".vpd", ".blend")


def read_version() -> str:
    """Read the extension version from the Blender manifest."""
    if not MANIFEST.is_file():
        raise RuntimeError(f"Missing manifest: {MANIFEST}")

    match = re.search(r'^version\s*=\s*"([^"]+)"\s*$', MANIFEST.read_text(encoding="utf-8"), re.MULTILINE)
    if match is None:
        raise RuntimeError("Could not read version from blender_manifest.toml")
    return match.group(1)


def validate_source_files() -> None:
    """Ensure the release allowlist is complete before packaging."""
    missing = [name for name in RELEASE_FILES if not (PROJECT_ROOT / name).is_file()]
    if missing:
        raise RuntimeError("Missing release file(s): " + ", ".join(missing))


def validate_archive(archive_path: Path) -> None:
    """Confirm the generated archive has only the intended root-level files."""
    with ZipFile(archive_path) as archive:
        names = tuple(archive.namelist())

    expected_names = {f"{ARCHIVE_ROOT}/{name}" for name in RELEASE_FILES}
    if set(names) != expected_names:
        raise RuntimeError("Release archive contents differ from the approved allowlist.")

    for name in names:
        normalized = name.replace("\\", "/")
        if not normalized.startswith(f"{ARCHIVE_ROOT}/") or normalized.count("/") != 1:
            raise RuntimeError(f"Release archive contains unexpected path: {name}")
        relative_name = normalized.removeprefix(f"{ARCHIVE_ROOT}/")
        if relative_name.startswith(FORBIDDEN_PARTS) or relative_name.endswith(FORBIDDEN_SUFFIXES):
            raise RuntimeError(f"Release archive contains forbidden file: {name}")


def main() -> int:
    version = read_version()
    validate_source_files()

    DIST_DIR.mkdir(exist_ok=True)
    archive_path = DIST_DIR / f"mmd_safe_importer-{version}.zip"
    if archive_path.exists():
        raise RuntimeError(f"Refusing to overwrite existing archive: {archive_path}")

    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
        for name in RELEASE_FILES:
            archive.write(PROJECT_ROOT / name, arcname=f"{ARCHIVE_ROOT}/{name}")

    try:
        validate_archive(archive_path)
    except Exception:
        archive_path.unlink(missing_ok=True)
        raise

    print(f"Built and verified: {archive_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"Build failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
