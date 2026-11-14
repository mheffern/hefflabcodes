"""Build a self-contained viewer page with one batch of LC-ICP-MS CSVs embedded.

    python make_viewer.py DATA_FOLDER [OUTPUT.html]

viewer_template.html also works on its own: open it in a browser and use
"Load CSV files…" to pick the exports from any batch.
"""
import json
import sys
from pathlib import Path

from analyze_lcicpms import read_icpms_csv

data_dir = Path(sys.argv[1])
out = Path(sys.argv[2]) if len(sys.argv) > 2 else data_dir / "viewer.html"
runs = []
for f in sorted(data_dir.glob("*.csv")):
    try:
        name, acq, df = read_icpms_csv(f)
    except Exception:
        continue
    runs.append({"name": name, "acquired": acq.strftime("%Y-%m-%d %H:%M:%S") if acq else None,
                 "t": [round(v, 3) for v in df.time_s],
                 "metals": {m: [round(v, 1) for v in df[m]] for m in df.columns if m != "time_s"}})
label = f"Batch {data_dir.name}"
html = (Path(__file__).with_name("viewer_template.html").read_text()
        .replace("/*__DATA__*/null", json.dumps({"label": label, "runs": runs}, separators=(",", ":"))))
out.write_text(html)
print(f"wrote {out} ({len(runs)} runs, {out.stat().st_size/1e6:.1f} MB)")
