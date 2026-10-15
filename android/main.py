"""EasyWalp for Android - python-for-android entry point.

Two modes:

* **normal** - start the Kivy UI (``easywalp_android.ui.app``);
* **self-test** - when ``selftest/request.json`` exists in the app's external files
  dir, run the automated on-device check (engine + full pipeline) and write
  ``selftest/result.json``. CI pushes the request with ``adb push`` and pulls the
  result, so every build is validated on a real Android runtime.
"""
from __future__ import annotations

import json
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def _write_result(result: dict) -> None:
    """Persist the self-test report where CI (or the user) can read it."""
    try:
        from easywalp_android.platform import selftest_dir

        folder = selftest_dir()
        if folder is None:
            return
        (folder / "result.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        # A plain-text copy is handy when reading the report on the device itself.
        lines = [f"ok={result.get('ok')} elapsed={result.get('elapsed')}s"]
        lines += [f"[{'ok' if s['ok'] else 'FAIL'}] {s['name']}: {s['detail']}" for s in result.get("steps", [])]
        (folder / "result.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception:  # noqa: BLE001 - reporting must never raise
        traceback.print_exc()


def main() -> int:
    try:
        from easywalp_android.platform import selftest_request
    except Exception:  # noqa: BLE001 - broken install: still try to start the UI
        traceback.print_exc()
        selftest_request = lambda: None  # noqa: E731

    request = selftest_request()
    if request is not None:
        from easywalp_android.selftest import run

        result = run(request)
        _write_result(result)
        print("EasyWalp self-test:", "OK" if result.get("ok") else "FAILED")
        for step in result.get("steps", []):
            print(f"  [{'ok' if step['ok'] else 'FAIL'}] {step['name']}: {step['detail']}")
        return 0 if result.get("ok") else 1

    from easywalp_android.ui.app import EasyWalpApp

    EasyWalpApp().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
