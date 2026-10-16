"""A FAKE PhotoCraft engine used by the test suite (no Rust build needed).

It speaks the real protocols:

* ``serve`` - the stdio JSON-lines session used by ``easywalp.photocraft.Session``
  (``doc.open`` / ``doc.inspect`` / ``doc.exportLayers`` / ``engine.execute`` /
  ``doc.save`` / ``doc.render``);
* ``info <file> --compact`` - the one-shot document tree used by the wizard;
* ``commands --json`` and ``--version``.

``layer.smartObjects.exportContents`` writes a PNG at the size the fake document
declares, so the wizard's "contents size" probing can be tested offline.
Every call is recorded in ``calls.json`` inside the work root, which is how the
tests assert *what* EasyWalp asked the engine to do.
"""
from __future__ import annotations

import sys
from pathlib import Path

FAKE_ENGINE = r'''
import json, os, sys, struct, zlib

work = os.getcwd()

# ---- automation roots ------------------------------------------------------
# `serve` is sandboxed exactly like the real engine: doc.open/doc.place may only
# read inside --automation-read-root, doc.save/doc.exportLayers only write inside
# --automation-write-root (relative request paths resolve beneath the root, an
# absolute path is accepted only when it lies under it). Emulating that here is
# what makes the tests catch "EasyWalp opened the preset's PSD from a session
# rooted in a subfolder of it" - the real engine answered with
# "automation path rejected: absolute paths must be inside the automation root".
_argv = sys.argv[1:]
def _root(name):
    return _argv[_argv.index(name) + 1] if name in _argv else None
READ_ROOT = _root("--automation-read-root")
WRITE_ROOT = _root("--automation-write-root")


def _norm(path):
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def _allowed(root, path):
    """(ok, error) for one request path, mirroring workspace.rs`request_path`."""
    if not root:
        return False, "automation filesystem access is not granted"
    if not os.path.isabs(path):
        return True, ""            # relative: resolved beneath the root
    root_n, path_n = _norm(root), _norm(path)
    if path_n == root_n or path_n.startswith(root_n + os.sep):
        return True, ""
    return False, ("automation path rejected: absolute paths must be inside the "
                   "automation root: `%s`" % path)


def _check(root, path):
    ok, error = _allowed(root, path)
    if not ok:
        return False, {"error": error}
    return True, None
state_path = os.path.join(os.environ.get("FAKE_STATE_DIR", work), "calls.json")
state = {"calls": [], "text": "Code:MD-O-C236", "font": "Vazirmatn"}
if os.path.exists(state_path):
    state = json.load(open(state_path))

DOC = {"width": 2000, "height": 1500, "layers": [
    {"id": 12, "name": "Desktop Screen", "kind": "Smart Object"},
    {"id": 15, "name": "Phone Screen", "kind": "Smart Object"},
    {"id": 3, "name": "BG Color", "kind": "Fill"},
    # A normal layer that means "the background colour" through a Color Overlay
    # layer style, nested in a group: the second flavour of a colour layer, and the
    # one a "Color Fill" template uses when the fill sits inside a folder.
    {"id": 25, "name": "Tint group", "kind": "Group", "children": [
        {"id": 21, "name": "BG Overlay", "kind": "Pixel",
         "effects": {"enabled": True, "items": [{"kind": "colorOverlay", "enabled": True}]}},
    ]},
    {"id": 8, "name": "Code label", "kind": "Type", "font": "Vazirmatn"},
]}
SO_SIZES = {12: (1600, 900), 15: (900, 1600)}


def save_state():
    json.dump(state, open(state_path, "w"))


def png_bytes(size, color=(10, 60, 90)):
    w, h = size
    def chunk(typ, data):
        c = typ + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", 0xFFFFFFFF & zlib.crc32(c))
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + bytes(color) * w for _ in range(h))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def reply(rid, ok, payload):
    msg = {"id": rid, "ok": ok}
    if ok:
        msg["result"] = payload
    else:
        msg["error"] = payload.get("error", "fake failure")
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def handle(rid, method, params):
    """Return (ok, payload) for one serve request."""
    params = params or {}
    if method == "doc.open":
        ok, err = _check(READ_ROOT, params.get("path", ""))
        if not ok:
            return False, err
        return True, {}
    if method == "doc.place":
        ok, err = _check(READ_ROOT, params.get("path", ""))
        if not ok:
            return False, err
        state["calls"].append({"cmd": method, "params": params})
        save_state()
        return True, {}
    if method == "doc.inspect":
        return True, DOC
    if method == "doc.exportLayers":
        out = params.get("dir", ".")
        ok, err = _check(WRITE_ROOT, out if os.path.isabs(out) else os.path.join(WRITE_ROOT or work, out))
        if not ok:
            return False, err
        top = [l for l in DOC["layers"] if l["kind"] != "Adjustment"]
        for index, layer in enumerate(top):
            name = "layer_%04d_%s.png" % (index, layer["name"].replace(" ", "_"))
            open(os.path.join(out, name), "wb").write(png_bytes((60, 40)))
        return True, {"count": 4}
    if method == "doc.render":
        ok, err = _check(WRITE_ROOT, params["path"])
        if not ok:
            return False, err
        open(params["path"], "wb").write(png_bytes((800, 600)))
        return True, {"path": params["path"]}
    if method == "doc.save":
        out = params["path"]
        ok, err = _check(WRITE_ROOT, out if os.path.isabs(out) else os.path.join(WRITE_ROOT or work, out))
        if not ok:
            return False, err
        open(out, "wb").write(png_bytes((2000, 1500)))
        state["calls"].append({"cmd": "doc.save", "params": {"quality": params.get("quality")}})
        save_state()
        return True, {"path": out, "warnings": []}
    if method == "engine.execute":
        cmd = params.get("command")
        p = params.get("params", {})
        if cmd == "type.info":
            result = {"text": state["text"], "font": state.get("font", "Vazirmatn"), "sizePt": 48}
            state["calls"].append({"cmd": cmd, "params": p})
            save_state()
            return True, result
        if cmd == "type.edit":
            rep = p["replace"]
            t = state["text"]
            state["text"] = t[: rep["start"]] + rep["text"] + t[rep["end"]:]
            state["calls"].append({"cmd": cmd, "params": p})
            save_state()
            return True, {}
        if cmd == "layer.smartObjects.replaceContents":
            from PIL import Image
            with Image.open(p["path"]) as im:
                size = [im.width, im.height]
            state["calls"].append({"cmd": cmd, "params": p, "size": size})
            save_state()
            return True, {"replaced": p["layer"], "size": size}
        if cmd == "layer.smartObjects.exportContents":
            layer = int(p.get("layer", 0))
            size = SO_SIZES.get(layer, (1600, 900))
            target = os.path.join(os.getcwd(), p["path"])
            ok, err = _check(WRITE_ROOT, target)
            if not ok:
                return False, err
            os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
            open(target, "wb").write(png_bytes(size))
            state["calls"].append({"cmd": cmd, "params": p, "size": list(size)})
            save_state()
            return True, {"path": p["path"], "size": list(size)}
        if cmd == "layer.fill.solidColor.set":
            state["calls"].append({"cmd": cmd, "params": p})
            save_state()
            return True, {}
        if cmd == "layer.layerStyle.colorOverlay":
            layer = int(p.get("layer", 0))
            doc_layer = None
            for item in DOC["layers"]:
                if int(item["id"]) == layer:
                    doc_layer = item
                for child in item.get("children", []) or []:
                    if int(child["id"]) == layer:
                        doc_layer = child
            if doc_layer is None:
                return False, {"error": "no layer %s" % layer}
            effects = doc_layer.setdefault("effects", {"enabled": True, "items": []})
            for effect in effects["items"]:
                if effect.get("kind") == "colorOverlay":
                    effect["color"] = p.get("color")
                    effect["enabled"] = True
                    break
            else:
                effects["items"].append({"kind": "colorOverlay", "enabled": True, "color": p.get("color")})
            state["calls"].append({"cmd": cmd, "params": p})
            save_state()
            return True, {"layer": layer}
        if cmd == "layer.newFillLayer.solidColor":
            state["calls"].append({"cmd": cmd, "params": p})
            save_state()
            return True, {"layer": 99}
        if cmd == "type.create":
            state["text"] = p.get("text", state["text"])
            state["calls"].append({"cmd": cmd, "params": p})
            save_state()
            return True, {"layer": 100}
        state["calls"].append({"cmd": cmd, "params": p})
        save_state()
        return True, {}
    if method == "doc.new":
        state["calls"].append({"cmd": method, "params": params})
        save_state()
        return True, {}
    return False, {"error": "unknown " + str(method)}


def cli(argv):
    """One-shot subcommands (info / commands / --version)."""
    if "--version" in argv:
        sys.stdout.write("photocraft-cli fake-1.0\n")
        return 0
    if argv and argv[0] == "commands":
        sys.stdout.write(json.dumps([{"id": "layer.smartObjects.replaceContents"},
                                     {"id": "type.edit"}]) + "\n")
        return 0
    if argv and argv[0] == "info":
        sys.stdout.write(json.dumps(DOC) + "\n")
        return 0
    if argv and argv[0] == "run":
        return 0
    return 0


argv = sys.argv[1:]
if argv and argv[0] in ("info", "commands", "run") or "--version" in argv:
    sys.exit(cli(argv))

# serve: JSON lines over stdio
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    req = json.loads(line)
    ok, payload = handle(req["id"], req.get("method"), req.get("params", {}))
    reply(req["id"], ok, payload)
'''


def write_fake_engine(tmp_path: Path, name: str = "photocraft-cli") -> Path:
    """Install the fake engine as an executable shim and return its path."""
    if sys.platform == "win32":  # the shim is a #!/bin/sh script
        raise RuntimeError("the fake engine shim is POSIX-only")
    tmp_path.mkdir(parents=True, exist_ok=True)
    script = tmp_path / "fake_engine.py"
    script.write_text(FAKE_ENGINE, encoding="utf-8")
    shim = tmp_path / name
    shim.write_text(
        f'#!/bin/sh\nexport FAKE_STATE_DIR="${{FAKE_STATE_DIR:-$PWD}}"\n'
        f'exec {sys.executable} {script} "$@"\n',
        encoding="utf-8",
    )
    shim.chmod(0o755)
    return shim


class FakeBinary:
    """The minimum surface of ``easywalp.photocraft.PhotoCraftBinary``."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def version(self) -> str:
        return "fake-1.0"
