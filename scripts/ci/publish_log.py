#!/usr/bin/env python3
"""Turn a CI log file into something readable from anywhere.

GitHub serves raw job logs from a short-lived signed URL on Azure blob storage, which
some networks cannot reach. This script copies the interesting part of a log into two
places that are always reachable through ``api.github.com``:

* **check-run annotations** - shown right in the Actions UI ("Annotations" panel) and
  readable with ``gh api repos/<repo>/check-runs/<id>/annotations``;
* **a commit comment** on the run's head commit - readable with
  ``gh api repos/<repo>/commits/<sha>/comments``.

It never fails the build: diagnostics that hide the real error are worse than none.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.github.com"
#: ANSI colour codes bloat the text and hide the actual message
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
MAX_ANNOTATION_CHARS = 55_000
MAX_ANNOTATIONS = 40
MAX_COMMENT_CHARS = 60_000


def warn(message: str) -> None:
    """A failure of the diagnostics themselves must be visible in the UI too."""
    print(f"publish_log: {message}", flush=True)
    print(f"::warning title=publish_log::publish_log: {message}", flush=True)


def call(method: str, url: str, token: str, payload: dict | None = None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("X-GitHub-Api-Version", "2022-11-28")
    request.add_header("User-Agent", "easywalp-ci")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=60) as response:
        body = response.read()
    return json.loads(body) if body else {}


def find_check_run_id(repo: str, token: str, sha: str, job_name: str) -> int | None:
    """The check run of the job called *job_name* (Actions names them like the job).

    The jobs API leaves ``check_run_url`` empty, so the check-run list of the head
    commit is the reliable lookup.
    """
    if not sha:
        return None
    runs = call("GET", f"{API}/repos/{repo}/commits/{sha}/check-runs?per_page=100", token)
    candidates = runs.get("check_runs", [])
    for run in candidates:
        if run.get("name") == job_name:
            return int(run["id"])
    for run in candidates:
        if job_name and job_name in (run.get("name") or ""):
            return int(run["id"])
    return None


def chunk(text: str, size: int, limit: int) -> list[str]:
    pieces = [text[i:i + size] for i in range(0, len(text), size)]
    return pieces[:limit]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", required=True, type=Path, help="log file to publish")
    parser.add_argument("--job-name", default=os.environ.get("GITHUB_JOB", ""),
                        help="job name to attach the annotations to")
    parser.add_argument("--title", default="", help="annotation title prefix")
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID", ""))
    parser.add_argument("--sha", default=os.environ.get("GITHUB_SHA", ""))
    parser.add_argument("--tail", type=int, default=400_000,
                        help="publish at most this many trailing characters")
    parser.add_argument("--skip-annotations", action="store_true")
    parser.add_argument("--skip-comment", action="store_true")
    args = parser.parse_args(argv)

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    if not token:
        print("publish_log: no token in GH_TOKEN/GITHUB_TOKEN - nothing published")
        return 0
    if not args.repo or not args.run_id:
        print("publish_log: GITHUB_REPOSITORY/GITHUB_RUN_ID missing - nothing published")
        return 0
    if not args.file.exists():
        print(f"publish_log: {args.file} does not exist - nothing published")
        return 0

    raw = args.file.read_text(encoding="utf-8", errors="replace")
    text = ANSI.sub("", raw)
    total_lines = text.count("\n") + 1
    if len(text) > args.tail:
        text = f"... (trimmed to the last {args.tail} characters)\n" + text[-args.tail:]
    title = args.title or args.job_name or "ci"
    head = (f"{title}\n{args.repo} run {args.run_id} - {total_lines} lines, "
            f"{len(raw)} bytes\n" + "-" * 60 + "\n")
    text = head + text

    if not args.skip_annotations:
        try:
            check_id = find_check_run_id(args.repo, token, args.sha, args.job_name)
            if not check_id:
                warn(f"no check run named {args.job_name!r} on {args.sha[:8]}")
            else:
                pieces = chunk(text, MAX_ANNOTATION_CHARS, MAX_ANNOTATIONS)
                annotations = [
                    {
                        "path": args.file.name,
                        "start_line": 1,
                        "end_line": 1,
                        "annotation_level": "failure",
                        "title": f"{title} (part {i + 1}/{len(pieces)})",
                        "message": piece,
                    }
                    for i, piece in enumerate(pieces)
                ]
                result = call("POST", f"{API}/repos/{args.repo}/check-runs/{check_id}/annotations",
                              token, {"annotations": annotations})
                print(f"publish_log: posted {len(annotations)} annotation(s) "
                      f"({len(text)} chars) to check run {check_id}"
                      f" {result.get('html_url', '')}")
        except urllib.error.HTTPError as e:
            warn(f"annotations failed: {e.code} {e.read()[:200]!r}")
        except Exception as e:  # noqa: BLE001
            warn(f"annotations failed: {type(e).__name__}: {e}")

    if not args.skip_comment and args.sha:
        try:
            # The *end* of a log is where the failure is: keep the tail.
            body = text
            if len(text) > MAX_COMMENT_CHARS:
                body = ("... (earlier output trimmed)\n"
                        + text[-(MAX_COMMENT_CHARS - len("... (earlier output trimmed)\n")):])
            result = call("POST", f"{API}/repos/{args.repo}/commits/{args.sha}/comments", token,
                          {"body": f"**CI log: {title}**\n\n```\n{body}\n```\n"})
            print(f"publish_log: commit comment -> {result.get('html_url', '?')}")
        except urllib.error.HTTPError as e:
            warn(f"commit comment failed: {e.code} {e.read()[:200]!r}")
        except Exception as e:  # noqa: BLE001
            warn(f"commit comment failed: {type(e).__name__}: {e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
