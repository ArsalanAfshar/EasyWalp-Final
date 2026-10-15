#!/usr/bin/env python3
"""EasyWalp feasibility spike (spec section 7) - exercises the REAL PhotoCraft
engine end-to-end on a given PSD (your NM.psd) and writes a report.

What it verifies
  1. Smart objects land in the right place (transform/masks/rounded corners kept)
     by pixel-diffing PhotoCraft's render of the original PSD vs the edited one:
     only the two smart-object regions, the fill color region and the code text
     region may change.
  2. Text keeps font/size/position: the diff outside expected regions must be
     ~zero; missing-font behaviour is reported from engine warnings.
  3. Layer ids stability across open/save/open.
  4. 2K and 4K runs: timings, peak engine memory, and that both preview JPGs are
     visually identical (same PSD-size output).
  5. Startup time and total time per run.

Usage
  python scripts/spike/run_spike.py --cli /path/to/photocraft-cli --psd /path/to/NM.psd \
      --out spike-out [--desktop sample.png --mobile sample2.png]

If --desktop/--mobile are omitted, deterministic gradient samples are generated
at each resolution. The script only READS your PSD; all edits happen on copies.
"""
from __future__ import annotations

import argparse
import json
import os
import resource
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from easywalp import wizard as wiz  # noqa: E402
from easywalp.photocraft import PhotoCraftBinary, Session  # noqa: E402
from easywalp.pipeline import average_color, cover_resize, save_wallpaper_jpg  # noqa: E402
from PIL import Image, ImageChops  # noqa: E402

RESOLUTIONS = {
    "2k": {"desktop": (2560, 1440), "mobile": (1440, 2560)},
    "4k": {"desktop": (4096, 2304), "mobile": (2304, 4096)},
}


class Report:
    def __init__(self, out_dir: Path) -> None:
        self.out_dir = out_dir
        self.lines: list[str] = ["# EasyWalp feasibility spike report", ""]

    def h2(self, text: str) -> None:
        self.lines += [f"## {text}", ""]

    def p(self, text: str) -> None:
        self.lines += [text, ""]

    def kv(self, rows: list[tuple[str, object]]) -> None:
        self.lines += ["| Metric | Value |", "|---|---|"]
        for k, v in rows:
            self.lines.append(f"| {k} | `{v}` |")
        self.lines.append("")

    def save(self, artifact_lines: list[tuple[str, str]] = ()) -> Path:
        for name, content in artifact_lines:
            (self.out_dir / name).write_text(content, encoding="utf-8")
        path = self.out_dir / "spike-report.md"
        path.write_text("\n".join(self.lines), encoding="utf-8")
        print(f"report: {path}")
        return path


def peak_child_rss_mib() -> float:
    """Peak RSS of *finished* child processes so far (Linux/macOS)."""
    try:
        return resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024.0
    except Exception:
        return -1.0


def flatten(doc: dict) -> dict[int, dict]:
    out: dict[int, dict] = {}

    def walk(items):
        for it in items or []:
            if isinstance(it.get("id"), int):
                out[it["id"]] = {"name": it.get("name", ""), "kind": it.get("kind", "")}
            walk(it.get("layers"))

    walk(doc.get("layers", []))
    return out


def find_layers(binary_path: Path, psd: Path):
    """Auto-detect the 4 layers by kind (spike assumption; wizard does it interactively)."""
    info = wiz.inspect_psd(PhotoCraftBinary(binary_path), psd)
    layers = flatten(info)
    smart = [l for l in layers.values() if l["kind"] == "Smart Object"]
    fills = [l for l in layers.values() if l["kind"] == "Fill"]
    texts = [l for l in layers.values() if l["kind"] == "Type"]
    return info, layers, smart, fills, texts


def diff_stats(a_path: Path, b_path: Path) -> tuple[float, tuple[int, int, int, int] | None]:
    a, b = Image.open(a_path).convert("RGB"), Image.open(b_path).convert("RGB")
    if a.size != b.size:
        # Renders may come back at different preview caps; compare at the smaller size.
        target = (min(a.width, b.width), min(a.height, b.height))
        a = a.resize(target, Image.LANCZOS)
        b = b.resize(target, Image.LANCZOS)
    d = ImageChops.difference(a, b).convert("L")
    hist = d.histogram()
    total = a.width * a.height
    changed = sum(hist[8:])  # ignore tiny jpeg/AA noise under 8/255
    bbox = d.point(lambda v: 255 if v >= 8 else 0).getbbox()
    return 100.0 * changed / total, bbox


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cli", default=None, type=Path,
                    help="path to photocraft-cli (default: env EASYWALP_ENGINE, the engines folder, or PATH)")
    ap.add_argument("--psd", required=True, type=Path)
    ap.add_argument("--out", default=Path("spike-out"), type=Path)
    ap.add_argument("--desktop", type=Path, default=None)
    ap.add_argument("--mobile", type=Path, default=None)
    ap.add_argument("--skip-4k", action="store_true")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    rep = Report(args.out)
    try:
        binary = PhotoCraftBinary(args.cli)
    except Exception as e:
        print(f"error: {e}\nRun the 'PhotoCraft binaries' workflow (see docs/RELEASE-CHECKLIST.md), "
              "then: python scripts/fetch_engine.py", file=sys.stderr)
        return 2
    rep.h2("Engine")
    rep.kv([("binary", binary.path), ("version", binary.version()), ("psd", args.psd.name),
            ("psd size (MB)", f"{args.psd.stat().st_size / 1e6:.1f}")])

    work = args.out / "work"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    t0 = time.monotonic()
    info = wiz.inspect_psd(binary, args.psd)
    startup = time.monotonic() - t0
    rep.h2("Document")
    rep.kv([("canvas", f"{info.get('width')}x{info.get('height')}"),
            ("depth", info.get("depth")), ("mode", info.get("mode")),
            ("info time (s)", f"{startup:.2f}"),
            ("font warnings", json.dumps(info.get("warnings", []), ensure_ascii=False))])
    (args.out / "info.json").write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")

    _, layers, smart, fills, texts = find_layers(binary.path, args.psd)
    rep.h2("Detected layers (auto)")
    rep.kv([("Smart Object layers", ", ".join(f"{l['name']}" for l in smart) or "NONE"),
            ("Fill layers", ", ".join(f"{l['name']}" for l in fills) or "NONE"),
            ("Type layers", ", ".join(f"{l['name']}" for l in texts) or "NONE")])
    if len(smart) < 2 or not fills or not texts:
        rep.p("STOP: could not auto-detect the 4 needed layers; inspect info.json and pass them manually.")
        rep.save()
        return 2

    results = {}
    for res_key in (["2k"] + ([] if args.skip_4k else ["4k"])):
        rep.h2(f"Run: {res_key.upper()}")
        r = run_once(binary, args.psd, work, res_key, args.desktop, args.mobile, texts, fills, smart, rep)
        results[res_key] = r

    # pixel diff unmodified vs edited (2K run) ------------------------------
    rep.h2("Pixel diff: unmodified render vs edited render (2K, same 2048px render)")
    base_png = results["2k"]["render_base"]
    edited_png = results["2k"]["render_edited"]
    pct, bbox = diff_stats(base_png, edited_png)
    rep.kv([("changed pixels", f"{pct:.3f}%"), ("changed bbox", bbox),
            ("expectation", "changes only inside the 2 smart-object regions, the fill region and the code text")])
    rep.p("Judge with your eyes too: `render-base.png` vs `render-edited-2k.png` in the output folder.")
    shutil.copyfile(base_png, args.out / "render-base.png")
    shutil.copyfile(edited_png, args.out / "render-edited-2k.png")

    if not args.skip_4k:
        rep.h2("2K vs 4K preview identity")
        pct2, bbox2 = diff_stats(results["2k"]["preview"], results["4k"]["preview"])
        rep.kv([("mean changed pixels (>=8/255)", f"{pct2:.3f}%"),
                ("bbox", bbox2),
                ("expected", "~0% - sampling-level differences only, same PSD-size output")])
        rep.p("Note: automation renders are capped at 2048px per side (engine budget); the saved")
        rep.p("preview JPGs are full PSD size - compare those two JPGs for the 2K/4K identity check.")

    rep.h2("Layer id stability (open -> save -> reopen)")
    rep.p("See `id-stability.json` - ids before save, after save+reopen, and the diff.")

    rep.save()
    return 0


def run_once(binary, psd: Path, work: Path, res_key: str, desktop_src, mobile_src, texts, fills, smart, rep) -> dict:
    sizes = RESOLUTIONS[res_key]
    run_dir = work / res_key
    run_dir.mkdir(parents=True, exist_ok=True)

    # 1. wallpapers
    t0 = time.monotonic()
    d_png = desktop_src
    m_png = mobile_src
    if d_png is None:
        d_png = run_dir / f"sample-desktop-{res_key}.png"
        _gradient(d_png, *sizes["desktop"], (40, 100, 160), (10, 22, 40))
    if m_png is None:
        m_png = run_dir / f"sample-mobile-{res_key}.png"
        _gradient(m_png, *sizes["mobile"], (160, 100, 40), (40, 18, 8))
    d_png, m_png = Path(d_png), Path(m_png)
    d_jpg = run_dir / "desktop.jpg"
    m_jpg = run_dir / "mobile.jpg"
    save_wallpaper_jpg(cover_resize(Image.open(run_dir / d_png), *sizes["desktop"]), d_jpg)
    save_wallpaper_jpg(cover_resize(Image.open(run_dir / m_png), *sizes["mobile"]), m_jpg)
    t_resize = time.monotonic() - t0

    # 2. average color
    color = average_color(d_jpg)

    # 3. engine pass on a clone
    clone = run_dir / "template.psd"
    shutil.copyfile(psd, clone)
    # baseline render of the UNMODIFIED clone (automation renders cap at 2048px)
    t0 = time.monotonic()
    with Session(binary, work_root=run_dir) as s:
        s.start()
        t_start_engine = time.monotonic() - t0
        s.open(clone)
        base_png = run_dir / "render-base.png"
        s.render_png(base_png, max_side=2048)
        doc = s.inspect()
        text_id = texts[0]["id"]
        fill_id = fills[0]["id"]
        so_d_id, so_m_id = smart[0]["id"], smart[1]["id"]
        tinfo = s.execute("type.info", {"layer": text_id})
        before_text = tinfo.get("text", "")

        # smart object contents sizes
        so_sizes = []
        for so_id in (so_d_id, so_m_id):
            out = run_dir / f"so-{so_id}.png"
            s.execute("layer.smartObjects.exportContents", {"layer": so_id, "path": str(out.name)})
            with Image.open(out) as im:
                so_sizes.append(im.size)
        rep.p(f"smart object contents sizes: {so_sizes[0]} (desktop), {so_sizes[1]} (mobile)")

        t0 = time.monotonic()
        for so_id, jpg, (w, h) in ((so_d_id, d_jpg, so_sizes[0]), (so_m_id, m_jpg, so_sizes[1])):
            scaled = run_dir / f"replace-{so_id}.jpg"
            save_wallpaper_jpg(cover_resize(Image.open(jpg), w, h), scaled)
            s.execute("layer.smartObjects.replaceContents", {"layer": so_id, "path": str(scaled.name)})
        t_replace = time.monotonic() - t0

        t0 = time.monotonic()
        s.execute("layer.fill.solidColor.set", {"layer": fill_id, "color": color})
        t_fill = time.monotonic() - t0

        t0 = time.monotonic()
        import re
        code = "MD-O-C236"
        m = re.search(r"MD-[A-Z]-C\\d+", before_text)
        if m:
            start, end = m.span()
        else:
            start = end = len(before_text)
        s.execute("type.edit", {"layer": text_id, "replace": {"start": start, "end": end, "text": code}})
        t_text = time.monotonic() - t0
        after = s.execute("type.info", {"layer": text_id})

        edited_png = run_dir / f"render-edited-{res_key}.png"
        s.render_png(edited_png, max_side=2048)

        t0 = time.monotonic()
        preview = run_dir / f"preview-{res_key}.jpg"
        s.save(preview, quality=95)
        t_save = time.monotonic() - t0

        # id stability: save the psd copy, reopen, compare ids
        saved_psd = run_dir / "resaved.psd"
        s.call("doc.save", {"path": str(saved_psd.name)})

    with Session(binary, work_root=run_dir) as s2:
        s2.start()
        s2.open(saved_psd)
        doc2 = s2.inspect()
    ids1 = {lid: m["name"] for lid, m in flatten(doc).items()}
    ids2 = {lid: m["name"] for lid, m in flatten(doc2).items()}
    (run_dir.parent.parent / "id-stability.json").write_text(
        json.dumps({"before": ids1, "after": ids2, "same_ids": ids1 == ids2}, indent=2), encoding="utf-8")

    rows = [
        ("resize (s)", f"{t_resize:.2f}"),
        ("engine startup (s)", f"{t_start_engine:.2f}"),
        ("open+base render (s)", "-"),
        ("replaceContents 2x (s)", f"{t_replace:.2f}"),
        ("fill set (s)", f"{t_fill:.2f}"),
        ("ranged type.edit (s)", f"{t_text:.3f}"),
        ("save preview jpg (s)", f"{t_save:.2f}"),
        ("peak engine RSS (MiB)", f"{peak_child_rss_mib():.0f}"),
        ("preview size", "x".join(str(v) for v in Image.open(preview).size)),
        ("text before", before_text),
        ("text after", after.get("text", "")),
    ]
    rep.kv(rows)
    return {"preview": preview, "render_base": base_png, "render_edited": edited_png}


def _gradient(path: Path, w: int, h: int, top, bottom) -> None:
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(h):
        t = y / max(1, h - 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        for x in range(w):
            px[x, y] = color
    im.save(path)


if __name__ == "__main__":
    raise SystemExit(main())
