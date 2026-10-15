# Release checklist (for non-developers)

How to publish a new EasyWalp version. All commands run in the project folder;
you only need a browser and Git (GitHub Desktop works too).

## One-time: connect this project to your GitHub repo

Done already for `ArsalanAfshar/EasyWalp-Final` (this remote). For a fresh copy:

```bash
git init
git add .
git commit -m "EasyWalp initial import"
git branch -M main
git remote add origin https://github.com/ArsalanAfshar/<repo>.git
git push -u origin main
```

## One-time: enable the binary staging workflow

If the `.github/workflows/photocraft-binaries.yml` file is missing from the repo
(GitHub blocks some app-integrations from creating workflow files), add it by
hand: Actions tab → New workflow, or commit the file from GitHub's web editor
(Add file → Create new file → paste the file → `.github/workflows/photocraft-binaries.yml`).
Then Actions → "PhotoCraft binaries" → Run workflow — it builds the pinned
PhotoCraft and stages ready binaries on the `photocraft-bin` branch.

## Publish a release

1. Make sure the code is on `main` and the **Tests** workflow is green.
2. Bump the version: edit the `version` in `CHANGELOG.md` (add a section) and
   `src/easywalp/__init__.py` (`__version__ = "1.2.3"`), commit.
3. Tag and push the tag:
   ```bash
   git tag v1.2.3
   git push origin v1.2.3
   ```
   (Or: GitHub web → Releases → Draft a new release → type `v1.2.3` → publish.)
4. Watch Actions → **Release**. Three jobs: builds the pinned `photocraft-cli`
   (cached Rust build), packages the app with PyInstaller, builds the Inno Setup
   installer, then publishes to Releases:
   - `EasyWalp-Setup-1.2.3-windows.zip` (installer + portable app)
   - `EasyWalp-Setup-1.2.3.exe`
   - `SHA256SUMS.txt`
5. Post the zip link in the channel's staff chat. Colleagues: unzip → run the
   installer → double-click any `.easywalp` preset file they received.

## Versioning

Semantic versioning `MAJOR.MINOR.PATCH`: breaking preset-format or workflow
changes bump MAJOR, new features MINOR, fixes PATCH. The version shown in
About comes from the release tag (stamped at build time). Preset files record
the `appVersion` that made them, and newer-schema presets are refused by older
apps with a clear message.
