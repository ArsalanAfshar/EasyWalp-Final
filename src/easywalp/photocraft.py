"""Thin wrapper around the PhotoCraft headless CLI (photocraft-cli).

EasyWalp renders every preview mockup through PhotoCraft (github.com/storytold/photocraft,
MIT OR Apache-2.0) - never through Photoshop, psd-tools or Pillow compositing.

Two transports:
  * ``run()``   - one-shot `photocraft-cli run <file> --cmd ... --out ...`; simple, stateless.
  * ``Session`` - a long-lived `photocraft-cli serve` process speaking JSON lines over stdio
                  (doc.open / engine.execute / doc.save / doc.render / doc.exportLayers).
                  Used by the pipeline so one PSD open serves all commands of a run.

The binary is discovered from (1) an explicit path, (2) the EasyWalp engines folder,
(3) the bundled app dir (installed layout), (4) PATH.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import paths
from .photocraft_protocol import MAX_LOG_LINE, PhotoCraftError, frame, log_lines, parse_reply

log = logging.getLogger("easywalp.photocraft")


class PhotoCraftBinary:
    """Locates and reports the pinned engine binary."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = self._discover(path)
        if not self.path:
            raise PhotoCraftError(
                "photocraft-cli not found. Install it into the engines folder "
                f"({paths.engines_dir()}) or set engines.photocraftPath in settings.json."
            )

    @staticmethod
    def _discover(explicit: str | Path | None) -> Path | None:
        exe = "photocraft-cli.exe" if os.name == "nt" else "photocraft-cli"
        candidates: list[Path] = []
        if explicit:
            candidates.append(Path(explicit))
        candidates.append(paths.engines_dir() / exe)
        # Versioned folder produced by CI/installer: engines/v0.9.0/photocraft-cli(.exe)
        try:
            for child in sorted(paths.engines_dir().glob("**/" + exe), reverse=True):
                candidates.append(child)
        except OSError:
            pass
        bundled = paths.bundled_dir()
        candidates.append(bundled / "photocraft" / exe)
        candidates.append(bundled / exe)
        path_env = shutil.which("photocraft-cli")
        if path_env:
            candidates.append(Path(path_env))
        for c in candidates:
            if c and c.is_file():
                return c
        return None

    def version(self) -> str:
        try:
            out = subprocess.run(
                [str(self.path), "--version"], capture_output=True, text=True, timeout=30, check=False
            )
            return (out.stdout or out.stderr).strip() or "unknown"
        except (OSError, subprocess.TimeoutExpired):
            return "unknown"


class Session:
    """A long-lived headless PhotoCraft session over stdio JSON lines."""

    def __init__(self, binary: PhotoCraftBinary, work_root: Path) -> None:
        self.binary = binary
        self.work_root = work_root
        self._proc: subprocess.Popen[str] | None = None
        self._next_id = 1
        self._lock = threading.Lock()

    # -- lifecycle ---------------------------------------------------------
    def __enter__(self) -> "Session":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def start(self) -> None:
        if self._proc and self._proc.poll() is None:
            return
        root = str(self.work_root)
        cmd = [
            str(self.binary.path),
            "serve",
            "--automation-read-root", root,
            "--automation-write-root", root,
        ]
        log.info("starting engine: %s", " ".join(cmd))
        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
            cwd=str(self.work_root),
            env=_child_env(),
        )
        self._stderr_reader = threading.Thread(target=_pump_stderr, args=(self._proc,), daemon=True)
        self._stderr_reader.start()

    def close(self) -> None:
        proc, self._proc = self._proc, None
        if not proc:
            return
        try:
            if proc.stdin:
                proc.stdin.close()
        except OSError:
            pass
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

    # -- calls -------------------------------------------------------------
    def call(self, method: str, params: dict | None = None, timeout: float = 600.0) -> dict:
        """Send one JSON-lines request and wait for the matching reply."""
        with self._lock:
            if not self._proc or self._proc.poll() is not None:
                raise PhotoCraftError("the PhotoCraft engine session is not running")
            msg_id = self._next_id
            self._next_id += 1
            assert self._proc.stdin is not None and self._proc.stdout is not None
            line = frame(msg_id, method, params)
            log.debug("-> %s", line[:MAX_LOG_LINE])
            t0 = time.monotonic()
            self._proc.stdin.write(line + "\n")
            self._proc.stdin.flush()
            while True:
                reply_line = self._proc.stdout.readline()
                if not reply_line:
                    raise PhotoCraftError(
                        f"the PhotoCraft engine closed unexpectedly (method {method}; "
                        "see the log for engine diagnostics)"
                    )
                reply_line = reply_line.strip()
                if not reply_line:
                    continue
                try:
                    reply = json.loads(reply_line)
                except json.JSONDecodeError:
                    log_lines("engine-stdout", reply_line)
                    continue
                if reply.get("id") != msg_id:
                    # Diagnostics or a late error frame; log and keep waiting.
                    log_lines("engine", reply_line)
                    continue
                result = parse_reply(reply_line)
                log.debug("<- %s (%.2fs)", method, time.monotonic() - t0)
                return result

    # -- convenience -------------------------------------------------------
    def open(self, path: Path) -> dict:
        return self.call("doc.open", {"path": str(path)})

    def inspect(self) -> dict:
        return self.call("doc.inspect", {})

    def execute(self, command: str, params: dict) -> dict:
        return self.call("engine.execute", {"command": command, "params": params})

    def save(self, path: Path, quality: int | None = None) -> dict:
        params: dict = {"path": str(path)}
        if quality is not None:
            params["quality"] = quality
        return self.call("doc.save", params)

    def render_png(self, out_path: Path, max_side: int) -> dict:
        return self.call("doc.render", {"path": str(out_path), "maxSide": max_side})


def _pump_stderr(proc: subprocess.Popen[str]) -> None:
    """Log the engine's stderr (warnings, font notices) into the rotating log."""
    stream = proc.stderr
    if not stream:
        return
    for raw in iter(stream.readline, ""):
        log_lines("engine", raw)


def _child_env() -> dict:
    env = os.environ.copy()
    # Headless insurance: the CLI is pure CPU; no GPU/window stack is needed.
    env.setdefault("RUST_LOG", "warn,photocraft=info")
    return env


def run_one_shot(
    binary_path: Path,
    psd: Path,
    commands: list[tuple[str, dict]],
    out: Path | None = None,
    quality: int | None = None,
    work_root: Path | None = None,
    timeout: float = 900.0,
) -> subprocess.CompletedProcess[str]:
    """`photocraft-cli run <psd> --cmd <id> --params <json> ... --out <file>`."""
    # `run` uses the trusted-local headless mode: no automation roots needed
    # (only `serve`/`mcp` accept them). One-shot jobs read/write any path.
    cmd = [str(binary_path), "run", str(psd)]
    for command_id, params in commands:
        cmd += ["--cmd", command_id, "--params", json.dumps(params, ensure_ascii=False)]
    if out is not None:
        cmd += ["--out", str(out)]
        if quality is not None:
            cmd += ["--quality", str(quality)]
    log.info("run: %s", " ".join(cmd[:8]) + " …")
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        cwd=str(work_root or psd.parent),
        env=_child_env(),
        check=False,
    )
    if proc.stderr:
        log_lines("cli", proc.stderr)
    if proc.returncode != 0:
        raise PhotoCraftError(
            f"photocraft-cli run failed (exit {proc.returncode}): {proc.stderr.strip()[:MAX_LOG_LINE]}"
        )
    return proc


def command_catalog(binary_path: Path, query: str = "") -> list[dict]:
    """`photocraft-cli commands --json --filter <text>` - used by the wizard and tests."""
    cmd = [str(binary_path), "commands", "--json"]
    if query:
        cmd += ["--filter", query]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, check=False
    )
    if proc.returncode != 0:
        raise PhotoCraftError(proc.stderr.strip()[:MAX_LOG_LINE] or "commands listing failed")
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise PhotoCraftError("could not parse the PhotoCraft command list") from e
    if isinstance(data, dict):  # tolerate {"commands": [...]}
        data = data.get("commands", [])
    return data if isinstance(data, list) else []


def info(binary_path: Path, psd: Path) -> dict:
    """`photocraft-cli info <file> --compact` - document/layer tree with ids."""
    proc = subprocess.run(
        [str(binary_path), "info", str(psd), "--compact"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
        env=_child_env(),
    )
    if proc.stderr:
        log_lines("cli-info", proc.stderr)
    if proc.returncode != 0:
        raise PhotoCraftError(proc.stderr.strip()[:MAX_LOG_LINE] or "info failed")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise PhotoCraftError("could not parse photocraft-cli info output") from e


def main_exit(msg: str) -> int:  # pragma: no cover - tiny CLI helper
    print(msg, file=sys.stderr)
    return 1
