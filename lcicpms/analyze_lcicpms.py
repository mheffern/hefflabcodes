"""
LC-ICP-MS chromatogram analysis (Agilent MassHunter "Intensity Vs Time CPS" CSV exports).

What it does
------------
1. Reads every .csv in a folder (one file per injection, e.g. HumanCtrl_1.csv).
2. Uses a sample sheet (sample_sheet.csv) to know each file's sample TYPE and
   whether it is a BLANK. If no sheet exists, it writes a template you can edit.
3. Blank-corrects every sample, metal by metal:
     --blank-mode mean     subtract the average of all blanks (default)
     --blank-mode nearest  subtract the blank run closest in time *before* the
                           sample in the queue (accounts for drift/carryover)
4. Integrates each (corrected) chromatogram -> peak areas, optionally only
   inside retention-time windows you specify.
5. Writes tables (CSV) and plots (PNG) comparing samples by type and by metal.

Usage
-----
    python analyze_lcicpms.py DATA_FOLDER
    python analyze_lcicpms.py DATA_FOLDER --blank-mode nearest
    python analyze_lcicpms.py DATA_FOLDER --window 0 60 --window 60 300
"""

import argparse
import re
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


# --------------------------------------------------------------------------- #
# Reading files
# --------------------------------------------------------------------------- #
def read_icpms_csv(path):
    """Parse one MassHunter export. Returns (sample_name, acquired_datetime, DataFrame)."""
    lines = Path(path).read_text(encoding="utf-8-sig", errors="replace").splitlines()

    sample_name = Path(path).stem
    acquired = None
    header_idx = None
    for i, line in enumerate(lines[:20]):
        first = line.split(",")[0].strip()
        if first.lower().endswith(".d"):  # D:\DATA\...\HumanCtrl_1.d
            sample_name = re.split(r"[\\/]", first)[-1][:-2]
        m = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
        if "acquired" in line.lower() and m:
            acquired = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
        if first.lower().startswith("time"):
            header_idx = i
            break
    if header_idx is None:
        raise ValueError(f"No 'Time [Sec]' header row found in {path}")

    header = [h.strip() for h in lines[header_idx].split(",")]
    rows = []
    for line in lines[header_idx + 1:]:
        parts = [p.strip() for p in line.split(",")]
        try:
            rows.append([float(p) for p in parts[: len(header)] if p != ""])
        except ValueError:
            break  # footer / text reached
    df = pd.DataFrame(rows, columns=header[: len(rows[0])])
    df = df.rename(columns={df.columns[0]: "time_s"})
    df = df.loc[:, [c for c in df.columns if c]]  # drop empty trailing columns
    return sample_name, acquired, df


# --------------------------------------------------------------------------- #
# Sample sheet
# --------------------------------------------------------------------------- #
def guess_type(name):
    """HumanCtrl_1 -> HumanCtrl ; Blank_03 -> Blank"""
    return re.sub(r"[_\-\s]*\d+$", "", name) or name


def load_or_make_sample_sheet(data_dir, runs, sheet_path):
    if sheet_path.exists():
        sheet = pd.read_csv(sheet_path)
        sheet.columns = [c.strip().lower() for c in sheet.columns]
        sheet["blank"] = sheet["blank"].astype(str).str.lower().isin(["yes", "y", "true", "1"])
        if "include" in sheet:
            sheet = sheet[~sheet["include"].astype(str).str.lower().isin(["no", "n", "false", "0"])]
        missing = set(runs) - set(sheet["sample"])
        if missing:
            print(f"WARNING: not in sample sheet (skipped): {sorted(missing)}")
        return sheet.set_index("sample")

    sheet = pd.DataFrame({
        "sample": list(runs),
        "type": [guess_type(n) for n in runs],
        "blank": ["yes" if "blank" in n.lower() else "no" for n in runs],
        "include": "yes",
    })
    sheet.to_csv(sheet_path, index=False)
    print(f"No sample sheet found -> wrote a guessed one to {sheet_path}\n"
          f"   Check/edit the 'type' and 'blank' columns, then re-run.")
    sheet["blank"] = sheet["blank"] == "yes"
    return sheet.set_index("sample")


# --------------------------------------------------------------------------- #
# Main analysis
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("data_dir", type=Path)
    ap.add_argument("--sheet", type=Path, help="sample sheet CSV (default: DATA_DIR/sample_sheet.csv)")
    ap.add_argument("--out", type=Path, help="output folder (default: DATA_DIR/results)")
    ap.add_argument("--blank-mode", choices=["mean", "nearest"], default="mean")
    ap.add_argument("--window", nargs=2, type=float, action="append", metavar=("START", "END"),
                    help="retention-time window (s) to integrate; repeat for several peaks")
    args = ap.parse_args()

    sheet_path = args.sheet or args.data_dir / "sample_sheet.csv"
    out = args.out or args.data_dir / "results"
    out.mkdir(parents=True, exist_ok=True)

    # ---- read all runs
    runs, acquired = {}, {}
    for f in sorted(args.data_dir.glob("*.csv")):
        if f.resolve() == sheet_path.resolve():
            continue
        try:
            name, acq, df = read_icpms_csv(f)
        except Exception as e:
            print(f"skip {f.name}: {e}")
            continue
        runs[name], acquired[name] = df, acq
    if not runs:
        raise SystemExit("No data files found.")
    print(f"Read {len(runs)} runs")

    sheet = load_or_make_sample_sheet(args.data_dir, runs, sheet_path)
    runs = {k: v for k, v in runs.items() if k in sheet.index}

    # ---- common time grid + metals
    ref = next(iter(runs.values()))
    t = ref["time_s"].to_numpy()
    metals = [c for c in ref.columns if c != "time_s"]
    print(f"Metals: {metals}")

    def on_grid(df, metal):
        return np.interp(t, df["time_s"], df[metal])

    blanks = [n for n in runs if sheet.loc[n, "blank"]]
    samples = [n for n in runs if not sheet.loc[n, "blank"]]
    if not blanks:
        print("WARNING: no blanks marked -> no blank subtraction")
    print(f"Blanks: {blanks}")

    # queue order: by acquisition time if available, else file order
    order = sorted(runs, key=lambda n: (acquired[n] or datetime.min, list(runs).index(n)))

    def blank_trace(sample, metal):
        if not blanks:
            return np.zeros_like(t)
        if args.blank_mode == "nearest":
            pos = order.index(sample)
            before = [b for b in order[:pos] if b in blanks]
            chosen = [before[-1]] if before else [b for b in order if b in blanks][:1]
        else:
            chosen = blanks
        return np.mean([on_grid(runs[b], metal) for b in chosen], axis=0)

    # ---- corrected traces (long table)
    long = []
    for n in samples:
        for m in metals:
            raw = on_grid(runs[n], m)
            blk = blank_trace(n, m)
            long.append(pd.DataFrame({"sample": n, "type": sheet.loc[n, "type"], "metal": m,
                                      "time_s": t, "raw_cps": raw, "blank_cps": blk,
                                      "corrected_cps": raw - blk}))
    long = pd.concat(long, ignore_index=True)
    long.to_csv(out / "corrected_traces.csv", index=False)

    # ---- integrate
    windows = args.window or [[t.min(), t.max()]]
    areas = []
    for (n, m), g in long.groupby(["sample", "metal"], sort=False):
        for s, e in windows:
            w = g[(g.time_s >= s) & (g.time_s <= e)]
            areas.append({"sample": n, "type": g["type"].iat[0], "metal": m,
                          "window": f"{s:g}-{e:g} s",
                          "raw_area": np.trapezoid(w.raw_cps, w.time_s),
                          "blank_area": np.trapezoid(w.blank_cps, w.time_s),
                          "corrected_area": np.trapezoid(w.corrected_cps, w.time_s)})
    areas = pd.DataFrame(areas)
    areas.to_csv(out / "peak_areas.csv", index=False)

    summary = (areas.groupby(["metal", "window", "type"])["corrected_area"]
               .agg(n="count", mean="mean", sd="std").reset_index())
    summary["cv_%"] = 100 * summary["sd"] / summary["mean"]
    summary.to_csv(out / "summary_by_type.csv", index=False)

    # ---- plots
    types = sorted(long["type"].unique())
    colors = dict(zip(types, plt.cm.tab10.colors))

    # 1) mean +/- SD corrected chromatogram per type, one panel per metal
    fig, axes = plt.subplots(len(metals), 1, figsize=(9, 3.2 * len(metals)), sharex=True)
    for ax, m in zip(np.atleast_1d(axes), metals):
        for ty in types:
            g = long[(long.metal == m) & (long.type == ty)].pivot(index="time_s", columns="sample",
                                                                   values="corrected_cps")
            mu, sd = g.mean(axis=1), g.std(axis=1).fillna(0)
            ax.plot(g.index, mu, color=colors[ty], label=f"{ty} (n={g.shape[1]})")
            ax.fill_between(g.index, mu - sd, mu + sd, color=colors[ty], alpha=0.2)
        for s, e in (args.window or []):
            ax.axvspan(s, e, color="grey", alpha=0.08)
        ax.set_ylabel(f"{m}\nblank-corr. CPS")
        ax.legend(fontsize=8, frameon=False)
    np.atleast_1d(axes)[-1].set_xlabel("Retention time (s)")
    fig.suptitle(f"Chromatograms by sample type (blank mode: {args.blank_mode})")
    fig.tight_layout()
    fig.savefig(out / "chromatograms_by_type.png", dpi=150)
    plt.close(fig)

    # 2) every individual run, one figure per metal (good for spotting outliers)
    for m in metals:
        fig, ax = plt.subplots(figsize=(9, 4))
        for n in samples:
            g = long[(long.metal == m) & (long["sample"] == n)]
            ax.plot(g.time_s, g.corrected_cps, color=colors[sheet.loc[n, "type"]], lw=0.8, label=n)
        if blanks:
            ax.plot(t, blank_trace(samples[0], m) if args.blank_mode == "mean" else
                    np.mean([on_grid(runs[b], m) for b in blanks], axis=0),
                    "k--", lw=1, label="blank (mean, raw)")
        ax.set(xlabel="Retention time (s)", ylabel="CPS", title=f"{m}: individual runs (blank-corrected)")
        ax.legend(fontsize=7, frameon=False, ncol=2)
        fig.tight_layout()
        fig.savefig(out / f"runs_{m}.png", dpi=150)
        plt.close(fig)

    # 3) bar chart of integrated areas: type x metal, points = replicates
    for win in areas["window"].unique():
        fig, axes = plt.subplots(1, len(metals), figsize=(4 * len(metals), 4))
        for ax, m in zip(np.atleast_1d(axes), metals):
            a = areas[(areas.metal == m) & (areas.window == win)]
            for i, ty in enumerate(types):
                v = a[a.type == ty]["corrected_area"]
                ax.bar(i, v.mean(), yerr=v.std() if len(v) > 1 else 0, color=colors[ty],
                       alpha=0.6, capsize=4)
                ax.scatter(np.full(len(v), i) + np.random.uniform(-0.12, 0.12, len(v)), v,
                           color="k", s=12, zorder=3)
            ax.set_xticks(range(len(types)), types, rotation=30, ha="right")
            ax.set_title(m)
            ax.set_ylabel("Blank-corrected area (counts)")
            ax.axhline(0, color="k", lw=0.5)
        fig.suptitle(f"Integrated area, window {win}")
        fig.tight_layout()
        fig.savefig(out / f"areas_{win.replace(' ', '').replace('-', 'to')}.png", dpi=150)
        plt.close(fig)

    print(f"\nDone. Results in {out}/")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
