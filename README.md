# MMD Safe Importer

A standalone Blender extension, verified only with Blender 4.2.9 LTS, that wraps Blender's official `mmd_tools` PMX/PMD importer.

> **Compatibility notice:** This release was verified only with Blender 4.2.9 LTS. Other Blender versions, including newer releases, have not been verified and may not install or work correctly.

## Download and install

1. On this repository's **Releases** page, download `mmd_safe_importer-<version>.zip`.
   Do **not** use GitHub's automatically generated **Source code** ZIP as the Blender install package.
2. In **Blender 4.2.9 LTS**, install and enable the official **mmd_tools** extension. Verify that `Object.mmd_type` exists before importing; if it does not, disable/re-enable the official extension or restart Blender. Disable CATS before Safe Import: both projects register `mmd_tools.import_model`, and CATS' embedded legacy importer takes precedence when enabled.
3. Open **Edit > Preferences > Get Extensions**, use the menu in the upper-right corner, then choose **Install from Disk**.
4. Select the downloaded `mmd_safe_importer-<version>.zip`, then enable **MMD Safe Importer**.
5. Import through **File > Import > Safe PMX/PMD (.pmx, .pmd)**.

The recovery tools are also available in the 3D View sidebar: **N-panel > MMD Safe**.

## What it fixes

Some Blender 4.x `mmd_tools` installations retain non-empty but interface-corrupt global node groups named `MMDShaderDev` and `MMDTexUV`. The upstream importer can reuse them, then fail while linking material outputs.

This extension validates those socket contracts, builds replacements when needed, preserves recoverable backups during the import, validates the resulting MMD hierarchy, and rolls back only data created by a failed import.

## What changed in v0.1.5

- Uses only Blender Extensions' official `mmd_tools` importer and refuses to import when CATS owns the shared `mmd_tools.import_model` operator.
- Preflights the official importer and its required MMD object properties before creating any import data, preventing incomplete-registration failures such as a missing `Object.mmd_type`.
- Rebuilds incomplete or interface-corrupt `MMDShaderDev` and `MMDTexUV` groups with Blender-4-compatible node graphs, then verifies the resulting material-node contracts after import.
- Was regression-tested in Blender 4.2.9 LTS with the repository's asset-free suite and a locally licensed PMX model. No third-party model asset is included in this project or release.

## Requirements and limits

- **Verified Blender version:** Blender 4.2.9 LTS only. Other versions, including newer releases, are unverified and may not install or work correctly.
- The official Blender Extensions `mmd_tools` must be enabled and must own `mmd_tools.import_model`; CATS must be disabled while importing. This extension does not bundle or modify either dependency.
- Only the known `MMDShaderDev` and `MMDTexUV` node-group problems are repaired.
- Import validation checks the created hierarchy. It does not guarantee every model's final material appearance, physics, weight deformation, or animation behavior.

## Safety boundaries

- The extension never edits or persists changes to `mmd_tools` or CATS files.
- `material_compat.py` remains in the source tree for regression coverage of the previously supported CATS workaround; the official-backend release does not install or invoke it.
- Safe Import uses only Blender's official `mmd_tools` importer and fails closed if CATS' embedded importer currently owns the shared operator.
- Failed safe imports roll back only datablocks absent from the pre-import snapshot.
- Cleanup of a selected MMD model is explicitly scoped to that root hierarchy.
- It never runs a global orphan-data purge.
- The extension does not send telemetry or model data over the network.

## Build a release ZIP

The repository includes tests and build files, but they are excluded from the installable archive.

```text
python scripts/build_release.py
```

The command creates `dist/mmd_safe_importer-<version>.zip`. Its files are contained in the `mmd_safe_importer/` extension-package directory, including `blender_manifest.toml`, as required by the verified **Install from Disk** workflow.

## Tests

Run the asset-free Blender regression suite from a disposable Blender process:

```text
blender --background --factory-startup --python tests/run_blender_tests.py
```

A separate real-PMX regression is available for locally licensed models only; no PMX/PMD asset is included in this repository or release archive.

## Model assets

Do not bundle or redistribute third-party PMX/PMD/VMD/VPD assets unless their licenses explicitly permit it. This project contains no model asset.

## AI authorship

This project’s source code, documentation, and release materials were generated entirely by AI. This disclosure does not replace or alter the [GPL-3.0-or-later](LICENSE) license.

## License

This project is licensed under [GPL-3.0-or-later](LICENSE).
