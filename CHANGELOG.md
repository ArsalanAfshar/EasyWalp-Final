# Changelog

All notable changes to EasyWalp are documented here. Format: Keep a Changelog,
Semantic Versioning.

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
