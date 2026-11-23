"""Build a self-contained viewer page with one batch of chromatogram exports embedded.

    python make_viewer.py DATA_FOLDER [OUTPUT.html] [--label "Batch name"] [--extra FILE ...]
    python make_viewer.py --project saved.lcproj.json [OUTPUT.html]

Embeds every ICP-MS "Intensity Vs Time" export and every Agilent DAD signal export in the
folder (plus BatchLog.csv and sample_sheet.csv if present), as text, so the page parses them
exactly like files loaded by hand. DAD exports (often 40 Hz) are bin-averaged to at most
~8000 points per signal to keep the page small; the viewer would do the same on load.
--extra adds files from elsewhere (e.g. a DAD export kept in another folder).
--project embeds a project saved from the viewer ("Save project file"), so the page opens
exactly as it was saved (panels, offsets, replicates, zoom...).
viewer_template.html also works on its own: open it in a browser and use
"Files & samples" -> "Add files…".
"""
import argparse
import json
import math
import re
from pathlib import Path

from analyze_lcicpms import read_icpms_csv

MAXPTS = 8000


def is_dad(text):
    head = text.lstrip("﻿").splitlines()[:3]
    return any(l.startswith("#") and "Sig=" in l for l in head)


def thin_dad(text):
    """Bin-average each signal block of an Agilent DAD export to <= MAXPTS rows, same layout."""
    out, block = [], []

    def flush():
        if not block:
            return
        k = max(1, math.ceil(len(block) / MAXPTS))
        for i in range(0, len(block), k):
            chunk = block[i:i + k]
            x = sum(c[1] for c in chunk) / len(chunk)
            y = sum(c[2] for c in chunk) / len(chunk)
            out.append(f"{int(chunk[0][0])},{x:.5f},{y:.6g}")
        block.clear()

    for line in text.lstrip("﻿").splitlines():
        parts = line.strip().split(",")
        if len(parts) >= 3 and re.fullmatch(r"-?\d+", parts[0].strip()):
            try:
                block.append((float(parts[0]), float(parts[1]), float(parts[2])))
                continue
            except ValueError:
                pass
        flush()
        out.append(line.rstrip("\r"))
    flush()
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir", type=Path, nargs="?")
    ap.add_argument("out", type=Path, nargs="?")
    ap.add_argument("--project", type=Path, help="embed a .lcproj.json saved from the viewer instead of a data folder")
    ap.add_argument("--label", help="name shown at the top of the page (default: folder name)")
    ap.add_argument("--extra", type=Path, nargs="*", default=[], help="additional export files to embed")
    args = ap.parse_args()
    template = Path(__file__).with_name("viewer_template.html").read_text()

    if args.project:
        proj = json.loads(args.project.read_text(encoding="utf-8"))
        if proj.get("app") != "lc-trace-viewer":
            raise SystemExit(f"{args.project} is not a project saved from the viewer")
        # with --project the first positional argument (if any) is the output file
        out = args.out or args.data_dir or args.project.with_suffix("").with_suffix(".html")
        out.write_text(template.replace("/*__DATA__*/null", json.dumps(proj, separators=(",", ":")).replace("</", "<\\/")))
        print(f"wrote {out} (project “{proj.get('name')}”, {len(proj['files'])} files, {out.stat().st_size / 1e6:.1f} MB)")
        return
    if not args.data_dir:
        raise SystemExit("give a data folder, or --project FILE")

    out = args.out or args.data_dir / "viewer.html"
    files = []
    for f in sorted(args.data_dir.glob("*.csv")) + sorted(args.data_dir.glob("*.CSV")) + list(args.extra):
        if any(x["name"] == f.name for x in files):
            continue
        text = f.read_text(encoding="utf-8-sig", errors="replace")
        if is_dad(text):
            files.append({"name": f.name, "text": thin_dad(text)})
            continue
        keep = f.name in ("BatchLog.csv", "sample_sheet.csv")
        if not keep:
            try:
                read_icpms_csv(f)
                keep = True
            except Exception:
                pass
        if keep:
            files.append({"name": f.name, "text": text})

    payload = {"label": args.label or f"Batch {args.data_dir.name}", "files": files}
    html = (template
            .replace("/*__DATA__*/null", json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")))
    out.write_text(html)
    print(f"wrote {out} ({len(files)} files, {out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
