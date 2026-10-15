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
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.github.com"
MAX_ANNOTATION_CHARS = 55_000
MAX_ANNOTATIONS = 40
MAX_COMMENT_CHARS = 60_000


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


def find_check_run(repo: str, token: str, run_id: str, job_name: str) -> str | None:
    """URL of the check run belonging to the failing job (matched by name)."""
    jobs = call("GET", f"{API}/repos/{repo}/actions/runs/{run_id}/jobs?per_page=100", token)
    candidates = jobs.get("jobs", [])
    exact = [j for j in candidates if j.get("name") == job_name]
    loose = [j for j in candidates if job_name and job_name in (j.get("name") or "")]
    for job in exact + loose + candidates:
        if job.get("check_run_url"):
            return job["check_run_url"]
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

    text = args.file.read_text(encoding="utf-8", errors="replace")
    if len(text) > args.tail:
        text = "... (truncated)\n" + text[-args.tail:]
    title = args.title or args.job_name or "ci"
    head = f"{title}\n{args.repo} run {args.run_id}\n" + "-" * 60 + "\n"
    text = head + text

    if not args.skip_annotations:
        try:
            url = find_check_run(args.repo, token, args.run_id, args.job_name)
            if not url:
                print("publish_log: no check run found for this job")
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
                result = call("POST", f"{url}/annotations", token, {"annotations": annotations})
                print(f"publish_log: posted {len(annotations)} annotation(s) "
                      f"({len(text)} chars) -> {result.get('html_url', url)}")
        except urllib.error.HTTPError as e:
            print(f"publish_log: annotations failed: {e.code} {e.read()[:300]!r}")
        except Exception as e:  # noqa: BLE001
            print(f"publish_log: annotations failed: {type(e).__name__}: {e}")

    if not args.skip_comment and args.sha:
        try:
            body = text[:MAX_COMMENT_CHARS]
            if len(text) > MAX_COMMENT_CHARS:
                body += "\n... (truncated)"
            result = call("POST", f"{API}/repos/{args.repo}/commits/{args.sha}/comments", token,
                          {"body": f"**CI log: {title}**\n\n```\n{body}\n```\n"})
            print(f"publish_log: commit comment -> {result.get('html_url', '?')}")
        except urllib.error.HTTPError as e:
            print(f"publish_log: commit comment failed: {e.code} {e.read()[:300]!r}")
        except Exception as e:  # noqa: BLE001
            print(f"publish_log: commit comment failed: {type(e).__name__}: {e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
