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

## The CI workflow (already installed)

The workflow lives at `.github/workflows/easywalp-ci.yml` and is part of the
repository - there is nothing to install. It runs

- on **every push** to any branch: the test suite (Linux + Windows, offscreen Qt
  and the Android screens through the app's own self-test) and the pinned engine
  cross-builds;
- on a **manual run** (**Actions** → **EasyWalp CI** → **Run workflow**) or a
  `v*` **tag**: the pinned engine, the Windows app + installer, the Android APK
  and the release.

Keep that file as the single source of truth: when you change the workflow, push
it like any other file.

## Publish a release (Option 1: click "Run workflow" — no tag needed)

1. GitHub → **Actions** tab → **EasyWalp CI** → **Run workflow** →
   type the version, e.g. `0.1.1` → **Run workflow**.
   Optional: set *android_abis* to `arm64-v8a,x86` (or `x86`) and tick
   *android_emulator* to also install the APK on an emulator and run the
   on-device self-test (engine, PSD analysis, 2K/4K generation, gallery export).
   The self-test needs the x86 ABI: an arm64-only APK cannot run on the emulator.
2. The pipeline builds the pinned PhotoCraft engine, the app, the installer,
   creates the `v0.1.1` tag itself and publishes the release when green.

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
   - `EasyWalp-1.2.3-arm64-v8a.apk` (the Android app, engine included)
   - `SHA256SUMS.txt`
   A job called **Windows installer smoke test** then installs that very installer
   on a clean Windows runner, starts the app and checks that it stays up - if it
   is red, do not post the download.
5. Post the links in the channel's staff chat. Colleagues: unzip → run the
   installer → double-click any `.easywalp` preset file they received; for phones,
   send the `.apk` (sideload, see the README).

## Versioning

Semantic versioning `MAJOR.MINOR.PATCH`: breaking preset-format or workflow
changes bump MAJOR, new features MINOR, fixes PATCH. The version shown in
About comes from the release tag (stamped at build time). Preset files record
the `appVersion` that made them, and newer-schema presets are refused by older
apps with a clear message.
