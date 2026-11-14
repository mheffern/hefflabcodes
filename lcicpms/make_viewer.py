"""Build a self-contained viewer page with one batch of LC-ICP-MS CSVs embedded.

    python make_viewer.py DATA_FOLDER [OUTPUT.html] [--label "Batch name"]

Embeds every chromatogram export, plus BatchLog.csv and sample_sheet.csv if present,
exactly as they are on disk; the page parses them the same way as files loaded by hand.
viewer_template.html also works on its own: open it in a browser and use
"Files & samples" -> "Add files…".
"""
import argparse
import json
from pathlib import Path

from analyze_lcicpms import read_icpms_csv

ap = argparse.ArgumentParser()
ap.add_argument("data_dir", type=Path)
ap.add_argument("out", type=Path, nargs="?")
ap.add_argument("--label", help="name shown at the top of the page (default: folder name)")
args = ap.parse_args()

out = args.out or args.data_dir / "viewer.html"
files = []
for f in sorted(args.data_dir.glob("*.csv")):
    keep = f.name in ("BatchLog.csv", "sample_sheet.csv")
    if not keep:
        try:
            read_icpms_csv(f)
            keep = True
        except Exception:
            pass
    if keep:
        files.append({"name": f.name, "text": f.read_text(encoding="utf-8-sig", errors="replace")})

payload = {"label": args.label or f"Batch {args.data_dir.name}", "files": files}
html = (Path(__file__).with_name("viewer_template.html").read_text()
        .replace("/*__DATA__*/null", json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")))
out.write_text(html)
print(f"wrote {out} ({len(files)} files, {out.stat().st_size / 1e6:.1f} MB)")
