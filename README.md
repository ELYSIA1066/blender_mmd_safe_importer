# MMD Safe Importer

A standalone Blender 4.2+ extension that wraps the installed `mmd_tools` PMX/PMD importer.

## Download and install

1. On this repository's **Releases** page, download `mmd_safe_importer-<version>.zip`.
   Do **not** use GitHub's automatically generated **Source code** ZIP as the Blender install package.
2. In Blender 4.2 or newer, install and enable the official **mmd_tools** extension.
3. Open **Edit > Preferences > Get Extensions**, use the menu in the upper-right corner, then choose **Install from Disk**.
4. Select the downloaded `mmd_safe_importer-<version>.zip`, then enable **MMD Safe Importer**.
5. Import through **File > Import > Safe PMX/PMD (.pmx, .pmd)**.

The recovery tools are also available in the 3D View sidebar: **N-panel > MMD Safe**.

## What it fixes

Some Blender 4.x `mmd_tools` installations retain non-empty but interface-corrupt global node groups named `MMDShaderDev` and `MMDTexUV`. The upstream importer can reuse them, then fail while linking material outputs.

This extension validates those socket contracts, builds replacements when needed, preserves recoverable backups during the import, validates the resulting MMD hierarchy, and rolls back only data created by a failed import.

## Requirements and limits

- Blender 4.2 or newer.
- The official `mmd_tools` extension must be installed and enabled. This extension does not bundle or modify it.
- Only the known `MMDShaderDev` and `MMDTexUV` node-group problems are repaired.
- Import validation checks the created hierarchy. It does not guarantee every model's final material appearance, physics, weight deformation, or animation behavior.

## Safety boundaries

- The extension never patches `mmd_tools` files.
- Failed safe imports roll back only datablocks absent from the pre-import snapshot.
- Cleanup of a selected MMD model is explicitly scoped to that root hierarchy.
- It never runs a global orphan-data purge.
- The extension does not send telemetry or model data over the network.

## Build a release ZIP

The repository includes tests and build files, but they are excluded from the installable archive.

```text
python scripts/build_release.py
```

The command creates `dist/mmd_safe_importer-<version>.zip`. Its `blender_manifest.toml` is at the ZIP root, as required for Blender's **Install from Disk** workflow.

## Tests

Run the asset-free Blender regression suite from a disposable Blender process:

```text
blender --background --factory-startup --python tests/run_blender_tests.py
```

A separate real-PMX regression is available for locally licensed models only; no PMX/PMD asset is included in this repository or release archive.

## Model assets

Do not bundle or redistribute third-party PMX/PMD/VMD/VPD assets unless their licenses explicitly permit it. This project contains no model asset.

## License

This project is licensed under [GPL-3.0-or-later](LICENSE).
