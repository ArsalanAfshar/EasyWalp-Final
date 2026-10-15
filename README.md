# EasyWalp

**Wallpaper release automation for the Wallify channel** (https://t.me/WallifyChannel)

EasyWalp turns two wallpapers (desktop 16:9 + mobile 9:16) into a ready-to-post
package: correctly resized JPGs, a release code like `MD-O-C236`, and the
**preview mockup rendered by the open-source [PhotoCraft](https://github.com/storytold/photocraft)
engine** — your Photoshop template with the wallpapers placed on the iMac/iPhone
and the code text updated. No Photoshop needed at release time.

> The preview render is always done by `photocraft-cli` (MIT OR Apache-2.0).
> Pillow is used **only** for resizing wallpapers, the average color and UI
> thumbnails. *Powered by PhotoCraft engine.*

---

## What a Generate run does

1. **Resize** both wallpapers to the selected resolution with cover-crop
   (scale-to-fill + center crop, never stretched or letterboxed), Lanczos,
   JPG quality 95, 4:4:4, sRGB:
   | Mode | Desktop | Mobile |
   |---|---|---|
   | 2K (default) | 2560×1440 | 1440×2560 |
   | 4K | 4096×2304 | 2304×4096 |
2. **Average color** from the desktop wallpaper (≈256px downscale, mean RGB).
3. **Edit a temp copy of your PSD via PhotoCraft**: replace the desktop and
   mobile Smart Object contents, set the Solid Color fill layer to the average
   color, and replace **only the code substring** inside the text layer
   (`Code:MD-O-C236` → new code; font, size, tracking and position untouched).
   The mockup always uses the Smart Objects' stored contents size, so 2K and 4K
   produce the *identical* preview at the PSD's own size.
4. **Export**: `MD-O-C236\` containing
   `D-O-C236.jpg`, `M-O-C236.jpg`, `MD-O-C236-preview.jpg`.

Optional per-preset **"Add resolution suffix"** produces `MD-O-C236-4K\`,
`D-O-C236-4K.jpg`, … (the code on the mockup never changes). All code and file
name templates are editable in the preset.

## Install (for the channel team)

1. Download `EasyWalp-Setup-x.y.z-windows.zip` from
   [Releases](../../releases), unzip, run `EasyWalp-Setup-x.y.z.exe`.
   Per-user install (no admin needed), Start-Menu + optional desktop shortcut.
2. First start opens the **setup wizard**: pick your PSD, click the suggested
   layers (the wizard shows a thumbnail of every layer), confirm the detected
   code, run the built-in test render, save the preset.
3. Send the created `.easywalp` file (Preset manager → Export) to your
   colleagues — they just double-click it. No re-mapping.

### ⚠️ Windows SmartScreen / antivirus warning (unsigned installer)

The installer is **not code-signed**, so Windows Defender SmartScreen may show
*"Windows protected your PC"* and some antivirus products may heuristically
flag it. This is expected for unsigned open-source apps and does not mean the
file is infected. Options:

- **Verify the download**: check the SHA256 in `SHA256SUMS.txt` against the
  file you downloaded (`certutil -hashfile EasyWalp-Setup-x.y.z.exe SHA256`).
- Click **More info → Run anyway** if you trust the release (built by this
  repo's GitHub Actions from public sources).
- Long-term fixes, in rough order of effort:
  1. **SignPath.io free code signing for open source** (apply with the GitHub
     repo; the certificate removes SmartScreen warnings as reputation builds).
  2. Buy an **OV code-signing certificate** (~$100–300/yr) or an **EV
     certificate** (instant SmartScreen reputation, ~$300–500/yr) and add the
     signing step to `.github/workflows/release.yml`.
  3. Submit a false-positive report to Microsoft/VirusTotal if a scanner
     wrongly flags the file.

## Android app (same pipeline, on a phone)

`EasyWalp-<version>-arm64-v8a.apk` (from [Releases](../../releases)) is the
Android build: the very same engine and core, with a Kivy UI instead of Qt.

1. Copy the APK to the phone and open it (allow *Install unknown apps* for the
   app you open it with — the APK is debug-signed, see below).
2. Pick the desktop + mobile wallpapers (system file picker), choose the preset,
   the category, the resolution and the number, then **Generate**.
3. **Save to gallery** copies the three JPGs into
   `Pictures/EasyWalp/<folder>` (MediaStore, so any gallery app sees them);
   **Share** sends them through the Android share sheet (Telegram, WhatsApp…) or
   copies the code as text.

Everything the desktop version does is done on the device: cover-cropped 2K/4K
JPGs, the PhotoCraft-rendered mockup, the code and folder naming, and the
`.easywalp` preset packages (export/import through the system picker).

Notes:

- The APK ships the PhotoCraft engine as `lib/arm64-v8a/libphotocraft_cli.so`
  (Android only lets an app *execute* files in its native-library directory) and
  copies the bundled Vazirmatn fonts into the app data dir, which is also where
  the engine looks for `$XDG_DATA_HOME/fonts`.
- MinAndroid 7.0 (API 24), portrait, ~xx MB per ABI. The release build is
  `debug`-signed with the standard Android debug key, which is all a sideloaded
  app needs; a Play Store upload would need a real keystore.
- Every release is validated on an emulator: the `android-selftest` job installs
  the APK, pushes a self-test request into the app's own external files dir and
  the app then runs the engine, builds a PSD, analyses it, generates 2K + 4K
  packages and exports to the gallery, writing `selftest/result.json` back.
  `adb logcat -s python.stdout:V` shows the same report live.

## Build from source

Requirements: Windows 10/11, Python 3.11+, and a `photocraft-cli.exe` built
from the commit pinned in `config/photocraft-pin.json`. Easiest: the CI stages
prebuilt binaries on the `photocraft-bin` branch (see *Builds* below), so
`python scripts/fetch_engine.py` downloads the right one into
`%APPDATA%\EasyWalp\engines\`, where both the app and the spike scripts find it.

```bat
py -3.11 -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
set PATH=%CD%\engines;%PATH%      &REM folder containing photocraft-cli.exe
pytest -q                          &REM tests
python -m easywalp gui             &REM the app
python -m easywalp --preset "My PSD" --desktop a.png --mobile b.png --category O --number 236 --res 2k --out D:\Out
```

Everything ships from **one workflow file**
([`.github/workflows/easywalp-ci.yml`](.github/workflows/easywalp-ci.yml)):
every branch push runs the test suite (Linux + Windows, offscreen Qt, the Kivy UI
under xvfb) and cross-compiles the pinned engine; a tag `v1.2.3` (or
**Actions → EasyWalp CI → Run workflow** with the version) builds the pinned
`photocraft-cli`, the PyInstaller app, the Inno Setup installer *and* the Android
APK, then publishes `EasyWalp-Setup-1.2.3-windows.zip`,
`EasyWalp-Setup-1.2.3.exe`, `EasyWalp-1.2.3-arm64-v8a.apk` and
`SHA256SUMS.txt` to Releases. A final job (**Windows installer smoke test**)
installs that very installer on a clean Windows runner, starts the app and checks
that it stays up; ask for the Android emulator validation on a manual run by
ticking *android_emulator* and setting *android_abis* to `x86`.

Downloads land on the [Releases](../../releases) page - direct links:

```
https://github.com/ArsalanAfshar/EasyWalp-Final/releases/latest/download/EasyWalp-Setup-0.1.0-windows.zip
https://github.com/ArsalanAfshar/EasyWalp-Final/releases/latest/download/EasyWalp-Setup-0.1.0.exe
https://github.com/ArsalanAfshar/EasyWalp-Final/releases/latest/download/EasyWalp-0.1.0-arm64-v8a.apk
```
Step-by-step for non-developers: [docs/RELEASE-CHECKLIST.md](docs/RELEASE-CHECKLIST.md).

## Feasibility spike (PhotoCraft proof)

`scripts/spike/run_spike.py` runs the whole pipeline through the real engine on
your PSD (or a synthetic one made by `scripts/spike/make_test_psd.py`) and
writes `spike-report.md`: pixel diffs vs the unmodified render (only the two
screens, the color fill and the code text may change), layer-id stability across
save, 2K vs 4K preview identity, timings and engine memory. See
[docs/SPIKE.md](docs/SPIKE.md).

## Project layout

```
src/easywalp/        core pipeline (GUI-free) + PySide6 app in app/
android/             Kivy app (main.py, easywalp_android/) + buildozer.spec
i18n/                en.json / fa.json  (runtime-switchable, RTL)
assets/              logo, icons, fonts (Vazirmatn, OFL), PhotoCraft licenses
packaging/windows/   PyInstaller spec + Inno Setup script (+ Farsi.isl)
scripts/             icon generation, spike, release helpers, CI log publishing
scripts/android/     prepares the buildozer build folder + reads self-test reports
tests/               pytest suite (core, Qt GUI flows, Android core + Kivy UI)
config/              photocraft-pin.json (exact engine commit, reproducible builds)
```

## Third-party / licensing

- EasyWalp © 2026 Arsalan Afshar (Wallify) — all rights reserved; the attribution
  notice must be kept (see `LICENSE`).
- **Powered by PhotoCraft engine** ([storytold/photocraft](https://github.com/storytold/photocraft)):
  MIT OR Apache-2.0 — licenses and NOTICE ship in `assets/photocraft/` and inside
  the app (About → Licenses). PhotoCraft/ArtCraft names and logos are their
  trademarks; this project uses neither, only the code via its CLI.
- [Vazirmatn font](https://github.com/rastikerdar/vazirmatn): SIL OFL 1.1.

---

# راهنمای فارسی

> **لینک‌های دانلود** (همیشه در صفحهٔ [Releases](../../releases) هم هستند):
>
> ```
> https://github.com/ArsalanAfshar/EasyWalp-Final/releases/latest/download/EasyWalp-Setup-0.1.0-windows.zip
> https://github.com/ArsalanAfshar/EasyWalp-Final/releases/latest/download/EasyWalp-Setup-0.1.0.exe
> https://github.com/ArsalanAfshar/EasyWalp-Final/releases/latest/download/EasyWalp-0.1.0-arm64-v8a.apk
> ```

**EasyWalp** تولید خودکار پکیج والپیپر برای کانال والیفای است: دو والپیپر
(دسکتاپ ۱۶:۹ و موبایل ۹:۱۶) + یک تصویر پیش‌نمایش ماکاپ که با موتور متن‌باز
**PhotoCraft** روی قالب فتوشاپ شما رندر می‌شود — بدون نیاز به فتوشاپ هنگام انتشار.

## کارهایی که Generate انجام می‌دهد

1. تغییر اندازه هر دو تصویر به رزولوشن انتخابی (برش Cover، بدون کشیدگی) با
   کیفیت JPG ۹۵ و بدون کاهش رنگ (4:4:4):
   | حالت | دسکتاپ | موبایل |
   |---|---|---|
   | 2K (پیش‌فرض) | 2560×1440 | 1440×2560 |
   | 4K | 4096×2304 | 2304×4096 |
2. محاسبه **رنگ میانگین** از والپیپر دسکتاپ (قابل تغییر به موبایل یا دستی).
3. ویرایش نسخه موقت PSD با موتور PhotoCraft: جایگزینی محتوای دو اسمارت‌آبجکت،
   تنظیم رنگ لایه Solid Color و تغییر **فقط بخش کدِ متن** (`Code:MD-O-C236`) —
   فونت، اندازه، رنگ و جای متن دست‌نخورده می‌ماند. پیش‌نمایش همیشه در اندازه
   خود PSD و یکسان برای 2K و 4K است.
4. ساخت پوشه خروجی مثل `MD-O-C236\` با فایل‌های `D-O-C236.jpg`،
   `M-O-C236.jpg` و `MD-O-C236-preview.jpg`.

گزینه اختیاری پسوند رزولوشن خروجی را `MD-O-C236-4K` و `D-O-C236-4K.jpg` می‌کند.

## نصب

۱. از بخش [Releases](../../releases) فایل `EasyWalp-Setup-x.y.z-windows.zip`
   را بگیرید، از حالت فشرده خارج کنید و نصاب را اجرا کنید (بدون نیاز به ادمین).
۲. در اولین اجرا، **راه‌انداز** باز می‌شود: فایل PSD را بدهید، لایه‌ها را با
   کمک تصویر کوچک هر لایه انتخاب کنید، کد شناسایی‌شده را تأیید کنید، رندر
   آزمایشی را ببینید و پریست را ذخیره کنید.
۳. پریست را با «Export» به فایل `.easywalp` تبدیل کنید و برای همکاران بفرستید —
   کافی است دابل‌کلیک کنند.

### ⚠️ هشدار SmartScreen ویندوز (نصب بدون امضای دیجیتال)

نصاب امضای دیجیتال ندارد؛ ممکن است ویندوز پیام «Windows protected your PC»
نشان دهد. این برای برنامه‌های متن‌باز بدون امضا طبیعی است. هش فایل را با
`SHA256SUMS.txt` بررسی کنید یا «More info → Run anyway» را بزنید. راه‌حل
بلندمدت: ثبت‌نام رایگان در **SignPath.io** برای پروژه‌های متن‌باز یا خرید
گواهی امضا (توضیح کامل در بخش انگلیسی).

## اپ اندروید (همان موتور، روی گوشی)

فایل `EasyWalp-<version>-arm64-v8a.apk` از بخش [Releases](../../releases) نسخهٔ
اندروید است: همان موتور PhotoCraft و همان منطق تولید، با رابط کاربری Kivy.

۱. فایل APK را روی گوشی باز کنید (اجازهٔ *نصب از منابع ناشناس* را برای برنامهای
   که فایل را باز می‌کند بدهید؛ APK با کلید دیباگ امضا شده است).
۲. والپیپر دسکتاپ و موبایل را انتخاب کنید (از فایل‌منیجر سیستم)، پریست، دسته،
   رزولوشن و شماره را انتخاب کنید و **تولید** را بزنید.
۳. **ذخیره در گالری** سه فایل JPG را در مسیر `Pictures/EasyWalp/<folder>`
   می‌گذارد (با MediaStore، پس همهٔ گالری‌ها آن را می‌بینند)؛ **اشتراک‌گذاری**
   آن‌ها را با تلگرام/واتس‌اپ و… می‌فرستد یا کد تولیدشده را کپی می‌کند.

همه‌چیز روی گوشی انجام می‌شود: والپیپرهای ۲K/۴K با برش و تغییر اندازهٔ دقیق،
رندر ماکاپ با PhotoCraft، نام‌گذاری کد و پوشه‌ها، و پکیج‌های `.easywalp`
(خروجی/ورودی از طریق انتخاب‌گر فایل سیستم).

نکته‌ها:

- موتور به‌صورت `lib/arm64-v8a/libphotocraft_cli.so` داخل APK است (اندروید فقط
  فایل‌های داخل پوشهٔ کتابخانهٔ بومی را قابل‌اجرا می‌کند) و فونت‌های وزیرمتن در
  پوشهٔ دادهٔ برنامه کپی می‌شوند؛ همان جایی که موتور در `$XDG_DATA_HOME/fonts`
  دنبال فونت می‌گردد.
- حداقل اندروید ۷ (API 24). نسخهٔ منتشرشده با کلید دیباگ امضا شده؛ برای انتشار
  در گوگل‌پلی باید کی‌استور واقعی ساخته شود.
- هر نسخه روی امولاتور تست می‌شود: کار `android-selftest` اپ را نصب می‌کند،
  درخواست تست را در پوشهٔ فایل‌های خود اپ می‌گذارد و اپ موتور را اجرا می‌کند،
  یک PSD می‌سازد، تحلیل می‌کند، ۲K و ۴K تولید می‌کند و در گالری ذخیره می‌کند و
  گزارش را در `selftest/result.json` می‌نویسد.

## ساخت از سورس

نیازمندی: ویندوز ۱۰/۱۱، پایتون ۳٫۱۱+ و فایل `photocraft-cli.exe` طبق نسخه
ثبت‌شده در `config/photocraft-pin.json`:

```bat
py -3.11 -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
set PATH=%CD%\engines;%PATH%
pytest -q
python -m easywalp gui
```

**مجوز:** EasyWalp © ۲۰۲۶ ارسلان افشار (والیفای) — تمام حقوق محفوظ است؛ متن
«Powered by PhotoCraft engine» باید حفظ شود. موتور PhotoCraft تحت مجوز
MIT OR Apache-2.0 و فونت وزیرمتن تحت OFL استفاده می‌شود (مجزا از مجوز EasyWalp).

برای انتشار نسخه جدید فقط یک تگ بزنید (مثل `v1.2.3`)؛ GitHub Actions همه‌چیز را
می‌سازد و در Releases می‌گذارد. مراحل دقیق: `docs/RELEASE-CHECKLIST.md`.
