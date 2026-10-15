"""Log framing/call helpers for the PhotoCraft headless JSON-lines protocol.

Call framing: one JSON object per line, both directions:
    -> {"id": 7, "method": "doc.inspect", "params": {"index": 0}}
    <- {"id": 7, "ok": true, "result": {...}}          (server.rs wraps results)
    <- {"id": 7, "ok": false, "error": "..."}

The stdio `serve` subcommand logs to stderr; the reply line itself is clean JSON.
"""
from __future__ import annotations

import json
import logging

log = logging.getLogger("easywalp.photocraft")

MAX_LOG_LINE = 2000


def frame(msg_id: int, method: str, params: dict | None = None) -> str:
    msg = {"id": msg_id, "method": method, "params": params or {}}
    return json.dumps(msg, ensure_ascii=False)


def parse_reply(line: str) -> dict:
    """Parse one reply line; raise PhotoCraftError on ok:false."""
    try:
        reply = json.loads(line)
    except json.JSONDecodeError as e:
        raise PhotoCraftError(f"unparseable reply from photocraft-cli: {line[:MAX_LOG_LINE]}") from e
    if not isinstance(reply, dict):
        raise PhotoCraftError(f"unexpected reply shape: {line[:MAX_LOG_LINE]}")
    if reply.get("ok") is False:
        raise PhotoCraftError(str(reply.get("error", "unknown PhotoCraft error")))
    return reply.get("result", reply)


class PhotoCraftError(RuntimeError):
    """A readable error from the PhotoCraft engine or its CLI wrapper."""


def log_lines(label: str, text: str) -> None:
    """Pipe stderr/stdout diagnostics into the rotating EasyWalp log."""
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        if len(line) > MAX_LOG_LINE:
            line = line[:MAX_LOG_LINE] + " …"
        if "warning" in line.lower():
            log.warning("%s: %s", label, line)
        else:
            log.info("%s: %s", label, line)
