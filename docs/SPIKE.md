# Feasibility spike — how to run it

The spike proves the PhotoCraft engine can do the whole mockup edit on **your
real PSD** before any UI work is trusted. It is a script, not an app.

## What it checks (spec §7)

1. Smart objects land correctly (position/size/masks/rounded corners kept) —
   verified by pixel-diffing PhotoCraft's render of the unmodified PSD against
   the edited preview: only the two screen regions, the fill-color region and
   the code text may differ.
2. Text keeps font/size/color/position — everything outside the expected
   regions must be pixel-identical; missing-font behaviour is printed from the
   engine's own warnings.
3. Layer-id stability across open → save → reopen (`id-stability.json`).
4. 2K and 4K runs: timings per stage, peak engine memory, and that both
   previews are visually identical (same PSD-size output).
5. Engine startup time and total run time.
6. Windows build of `photocraft-cli.exe` — proven by the "Release" workflow
   (`build-engine` job) or locally with `cargo build --release -p photocraft-cli`.

## Run it

You need a `photocraft-cli` binary (see "Getting the engine" below).

```bash
# with your real PSD (nothing in it is modified; edits happen on copies):
python scripts/spike/run_spike.py --cli /path/to/photocraft-cli --psd /path/to/NM.psd --out spike-out

# without any private PSD (synthetic mockup built BY PhotoCraft itself):
python scripts/spike/make_test_psd.py --cli /path/to/photocraft-cli --out spike-work
python scripts/spike/run_spike.py --cli /path/to/photocraft-cli --psd spike-work/template.psd --out spike-out
```

Open `spike-out/spike-report.md` and eyeball `spike-out/render-base.png` vs
`spike-out/work/2k/preview-2k.jpg`.

## Getting the engine

1. **Preferred**: run the repo's GitHub Actions workflow **"PhotoCraft binaries"**
   once (Actions tab → choose it → Run workflow). It builds the pinned commit on
   Windows x64 and Linux x86_64 and stages the binaries on the `photocraft-bin`
   branch + workflow artefacts.
2. Or build locally: install Rust + MSVC Build Tools, then
   `cargo build --release -p photocraft-cli` in a checkout of the pinned commit.
3. Or grab the official `photocraft-cli-0.9.0-macos-universal.zip` /
   `windows-x64` portable from PhotoCraft's releases page.

Put `photocraft-cli.exe` into `%APPDATA%\EasyWalp\engines\` (or point
Settings → Engine at it) — the app and the spike both find it there.
