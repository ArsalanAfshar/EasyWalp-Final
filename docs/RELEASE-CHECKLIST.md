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

## One-time: install the CI workflow (one file)

The workflow file ships in `ops/workflows/easywalp-ci.yml` because GitHub
rejects workflow files pushed by some app integrations. Do ONE of these:

**Option A — on your own machine (recommended):**
```bash
python scripts/install_workflows.py
git add .github/workflows && git commit -m "Install EasyWalp CI" && git push
```

**Option B — on github.com (no tools needed):** open the repo → **Add file →
Create new file** → name it `.github/workflows/easywalp-ci.yml` → paste the
content of `ops/workflows/easywalp-ci.yml` → **Commit changes**.
(The raw file is at
`https://github.com/ArsalanAfshar/EasyWalp-Final/blob/main/ops/workflows/easywalp-ci.yml`.)

## Publish a release (Option 1: click "Run workflow" — no tag needed)

1. GitHub → **Actions** tab → **EasyWalp CI** → **Run workflow** →
   type the version, e.g. `0.1.0` → **Run workflow**.
2. The pipeline builds the pinned PhotoCraft engine, the app, the installer,
   creates the `v0.1.0` tag itself and publishes the release when green.

## Publish a release (Option 2: push a v* tag)

## Publish a release

1. Make sure the code is on `main` and the **Tests** workflow is green.
2. Bump the version: edit the `version` in `CHANGELOG.md` (add a section) and
   `src/easywalp/__init__.py` (`__version__ = "1.2.3"`), commit.
3. Tag and push the tag:
   ```bash
   git tag v1.2.3
   git push origin v1.2.3
   ```
4. Watch **Actions → EasyWalp CI**. It builds the pinned `photocraft-cli`
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
