# Changelog

All notable changes to EasyWalp are documented here. Format: Keep a Changelog,
Semantic Versioning.

## [0.1.0] - 2026-10-15

### Added
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
  installer + SHA256 checksums.
