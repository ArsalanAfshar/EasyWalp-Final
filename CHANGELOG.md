# Changelog

All notable changes to EasyWalp are documented here. Format: Keep a Changelog,
Semantic Versioning.

## [0.1.2] - 2026-10-16

### Fixed
- **Desktop: a "Solid Color (Color Fill)" layer the wizard could not see.** Two
  causes, both fixed:
  - a layer inside a group was never offered - PhotoCraft nests layers under
    `children` and the layer walk only looked at top-level `layers`. Nested layers
    are now listed (labelled `Group / Layer`) and, more importantly, *resolved* at
    generate time - a mapped layer inside a folder used to fail with "not found in
    the PSD".
  - the colour layer no longer has to be a fill layer: any layer carrying a
    **Color Overlay** layer style is offered as well, shown as
    `[Color Overlay] Group / Layer`. The preset remembers which flavour it was set
    up with (a fill layer -> `layer.fill.solidColor.set`, a Color Overlay ->
    `layer.layerStyle.colorOverlay`), the wizard explains which one is in use, and
    an old preset without that note keeps meaning the fill behaviour.

## [0.1.1] - 2026-10-15

### Fixed
- **Desktop: the wizard's "Analyze PSD" button did nothing.** Two faults on the
  same page: the button next to *Browse* was created and connected but never added
  to the layout, so it was not on screen at all; and the button in the nav row was
  enabled once, when the dialog opened, so a path typed or pasted into the field
  afterwards left it dead. Both now follow the path field, Enter analyzes, and the
  warning for a wrong path names the file.
- A PSD the engine rejects no longer disables the button for good, and no longer
  leaves an unconfigured preset behind in the preset list.
- **Release pipeline:** the installer is attached to the release (the copy step
  copied the file onto itself and killed the job before it uploaded anything), the
  Windows installer is installed, started and killed again on a clean runner before
  a release goes out, and `--self-check` proves a built app starts (window, assets,
  engine) instead of only printing a version.
- `EasyWalp-Portable-<version>.exe`: the same build as one double-clickable file,
  for machines where nothing should be installed.

## [0.1.0] - 2026-10-15

### Added
- **Android app** (`EasyWalp-0.1.0-arm64-v8a.apk`): the same core and engine behind
  a Kivy UI — system file picker for the wallpapers/PSD, the wizard, presets,
  live code preview, background generation with progress, gallery export through
  MediaStore and the Android share sheet; English/Persian with RTL shaping and
  Persian digits.
- CI builds the APK (python-for-android + buildozer) and validates the installed
  APK on an Android emulator with a self-test that exercises the engine, a
  generated PSD, the wizard analysis, 2K/4K generation, the gallery export and the
  whole Kivy screen tree on the device.
- CI republishes failing job logs as check-run annotations and a commit comment.
- Core pipeline: cover-crop resize to 2K/4K (JPG q95 4:4:4 sRGB), average color,
  PhotoCraft-driven PSD edit (2 smart-object content replacements, solid color
  fill, ranged code text edit) and flat preview JPG export at the PSD's size.
- Presets: cloned PSD + layer mapping (id+name+kind, re-validated every run),
  smart-object contents sizes, code prefix/suffix, filename templates, share as
  `.easywalp` (zip) with optional font bundle.
- Setup wizard: PSD analysis with per-layer thumbnails via `doc.exportLayers`,
  kind-filtered mapping, code auto-detection, smart-object aspect warnings,
  font warnings, dry-run render before saving.
- GUI (PySide6): dark/light themes from the Wallify identity, English/Persian
  with full RTL, drag & drop, live code/naming preview, progress with stages.
- CLI mode (`python -m easywalp ...`).
- GitHub Actions: pinned PhotoCraft build, tests, release with Inno Setup
  installer + SHA256 checksums, and the Android APK.
