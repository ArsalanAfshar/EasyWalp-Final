# Buildozer spec for EasyWalp (Android).
#
# This file is the *human-readable* source of truth. The CI (and you, locally)
# render it into a build folder with `python scripts/android/prepare_apk.py`,
# which fills in the SDK/NDK paths, the version and the engine libraries:
#
#   python scripts/android/prepare_apk.py --version 1.0.0 \
#       --engine-dir engines-android --sdk "$ANDROID_HOME" --ndk "$ANDROID_NDK_LATEST_HOME" \
#       --build-dir android/build/app
#   cd android/build/app && buildozer android debug
#
# The resulting APK lands in android/build/app/bin/.
# APK properties (written by the prepare script, listed here for reference):
#   version = 1.0.0                     <- release version
#   android.sdk_path = <Android SDK>    <- ANDROID_HOME / ANDROID_SDK_ROOT
#   android.ndk_path = <Android NDK>    <- ANDROID_NDK_LATEST_HOME / ANDROID_NDK_HOME

[app]

title = EasyWalp
package.name = easywalp
package.domain = org.wallify

source.dir = .
source.include_exts = py,png,jpg,jpeg,webp,ttf,otf,json,txt,md,so
# The app code, the shared core, and the bundled resources (fonts, icons, i18n).
source.include_patterns = main.py,easywalp/**,easywalp_android/**,assets/**,i18n/**
source.exclude_patterns = .buildozer/**,bin/**,libs/**/.*,tests/**,__pycache__/**

version = 1.0.0

# Core runtime. `androidstorage4kivy` handles the system file picker, the gallery
# export (MediaStore) and the share sheet; the two text packages let Kivy display
# Persian (Kivy has no Arabic shaping of its own).
requirements = python3,kivy==2.3.1,pillow,pyjnius,android,arabic-reshaper,python-bidi,androidstorage4kivy

orientation = portrait
fullscreen = 0
# No window title bar: the app draws its own header.
# No quotes around the value - buildozer passes it to p4a verbatim and p4a renders
# it into android:theme="...", so quotes here break the manifest XML.
android.apptheme = @android:style/Theme.NoTitleBar

# The Wallify identity.
icon.filename = %(source.dir)s/assets/icons/easywalp-512.png
android.presplash_color = #0b1524

# Export goes through MediaStore (no permission needed on Android 10+); these are
# only for older devices, where the app writes into the shared Pictures folder.
android.permissions = android.permission.READ_EXTERNAL_STORAGE, (name=android.permission.WRITE_EXTERNAL_STORAGE;maxSdkVersion=28)

android.api = 35
android.minapi = 24
android.ndk_api = 24
# arm64-v8a: every current phone. x86: the emulator CI runs the on-device self-test with.
# Overridden by scripts/android/prepare_apk.py --abis (the engine libs must match).
android.archs = arm64-v8a
android.accept_sdk_license = True
android.private_storage = True
android.allow_backup = True

# The PhotoCraft engine ships as a *native library*: Android extracts native
# libraries with the executable bit set, while files in the app's data directory
# cannot be executed at all (Android 10+). `easywalp.photocraft` looks for
# `libphotocraft_cli.so` inside ApplicationInfo.nativeLibraryDir.
#
# `android.add_libs_<abi>` lines are written by scripts/android/prepare_apk.py, one
# per ABI in --abis, so the APK only contains engine binaries that exist.

[buildozer]
# 1: no DEBUG. Level 2 drowns the CI log in Cython "performance hint" lines and
# pushes the real error out of the published tail.
log_level = 1
warn_on_root = 0
