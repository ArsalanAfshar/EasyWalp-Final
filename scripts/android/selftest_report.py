#!/usr/bin/env python3
"""Print an on-device self-test report and fail when anything did not work.

`android-selftest` in CI pulls ``selftest/result.json`` from the emulator's copy of
the app's external files dir and feeds it to this script, so the workflow step's
output is the report itself:

    python scripts/android/selftest_report.py selftest-result.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarise an EasyWalp self-test report")
    parser.add_argument("report", type=Path, nargs="?", default=Path("selftest-result.json"))
    args = parser.parse_args(argv)

    if not args.report.is_file():
        print(f"::error::no self-test report at {args.report}")
        return 1
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
    except ValueError as e:
        print(f"::error::unreadable self-test report: {e}")
        return 1

    ok = bool(report.get("ok"))
    print(f"EasyWalp {report.get('app', '?')} on {report.get('platform', {}).get('implementation', '?')}")
    print(f"elapsed {report.get('elapsed')}s, data dir {report.get('platform', {}).get('data_dir')}")
    for step in report.get("steps", []):
        mark = "ok  " if step.get("ok") else "FAIL"
        detail = str(step.get("detail", "")).splitlines()
        print(f"[{mark}] {step.get('name')}: {detail[0] if detail else ''}")
        for line in detail[1:12]:
            print(f"          {line}")
    failed = [s for s in report.get("steps", []) if not s.get("ok")]
    if failed:
        print("::error::self-test failures: " + ", ".join(str(s.get("name")) for s in failed))
    elif not ok:
        print("::error::self-test produced no steps")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
