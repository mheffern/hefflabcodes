"""
LC-ICP-MS chromatogram analysis (Agilent MassHunter "Intensity Vs Time CPS" CSV exports).

What it does
------------
1. Reads every chromatogram .csv in a folder (one file per injection). Non-chromatogram
   files (BatchLog.csv, Meter.csv) are skipped; BatchLog comments are copied into the
   sample sheet if present.
2. Groups runs by METHOD (run length), so e.g. a 700 s standards method and a 1065 s
   serum method are blank-corrected, compared and plotted separately.
3. Uses a sample sheet (sample_sheet.csv) for each run's TYPE, whether it is a BLANK,
   and whether to INCLUDE it. If none exists, a guessed one is written for you to edit.
4. Blank-corrects every run, metal by metal, using only blanks from the same method:
     --blank-mode mean     average of all same-method blanks (default)
     --blank-mode nearest  the same-method blank run closest before it in the queue
                           (falls back to the first one after it)
5. Integrates each corrected chromatogram (whole run, or --window START END), also
   subtracting a straight local baseline between the window edges (peak_area), which
   removes leftover drift between the sample and its blank.
6. Writes tables (CSV) and plots (PNG), including a blank overlay to check drift/carryover.

Usage
-----
    python analyze_lcicpms.py DATA_FOLDER
    python analyze_lcicpms.py DATA_FOLDER --blank-mode nearest --window 300 500
"""

import argparse
import csv
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

    sample_name, acquired, header_idx = Path(path).stem, None, None
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
        raise ValueError("not a chromatogram export (no 'Time [Sec]' header)")

    header = [h.strip() for h in lines[header_idx].split(",")]
    header = header[: max(i for i, h in enumerate(header) if h) + 1]
    rows = []
    for line in lines[header_idx + 1:]:
        parts = [p.strip() for p in line.split(",")][: len(header)]
        try:
            rows.append([float(p) for p in parts])
        except ValueError:
            break  # blank line / "Printed:" footer reached
    df = pd.DataFrame(rows, columns=header)
    return sample_name, acquired, df.rename(columns={header[0]: "time_s"})


def read_batch_comments(data_dir):
    """Map file name (without .d) -> Comment from MassHunter BatchLog.csv, if present."""
    log = data_dir / "BatchLog.csv"
    if not log.exists():
        return {}
    out = {}
    with open(log, encoding="utf-8-sig", errors="replace") as f:
        rows = list(csv.reader(f))
    hdr = rows[0]
    try:
        fi, ci, ri = hdr.index("File Name"), hdr.index("Comment"), hdr.index("Acquisition Result")
    except ValueError:
        return {}
    for r in rows[1:]:
        if len(r) > max(fi, ci, ri) and r[ri] == "Pass":
            name = re.split(r"[\\/]", r[fi])[-1]
            out[name[:-2] if name.lower().endswith(".d") else name] = r[ci]
    return out


# --------------------------------------------------------------------------- #
# Sample sheet
# --------------------------------------------------------------------------- #
def guess_type(name):
    """HumanCtrl_1 -> HumanCtrl ; NASH-01_1 -> NASH ; K9_1 -> K9"""
    t = re.sub(r"_\d+$", "", name)
    t = re.sub(r"-\d+$", "", t)
    return t or name


def load_or_make_sample_sheet(data_dir, runs, method, sheet_path):
    if not sheet_path.exists():
        comments = read_batch_comments(data_dir)
        sheet = pd.DataFrame({
            "sample": list(runs),
            "type": ["Blank" if "blank" in n.lower() else guess_type(n) for n in runs],
            "blank": ["yes" if "blank" in n.lower() else "no" for n in runs],
            "include": "yes",
            "method": [method[n] for n in runs],
            "comment": [comments.get(n, "") for n in runs],
        })
        sheet.to_csv(sheet_path, index=False)
        print(f"No sample sheet found -> wrote a guessed one to {sheet_path}\n"
              f"   Check/edit 'type', 'blank' and 'include', then re-run.")

    sheet = pd.read_csv(sheet_path, dtype=str).fillna("")
    sheet.columns = [c.strip().lower() for c in sheet.columns]
    yes = lambda s: s.str.strip().str.lower().isin(["yes", "y", "true", "1"])
    sheet["blank"] = yes(sheet["blank"])
    if "include" in sheet:
        sheet = sheet[yes(sheet["include"]) | (sheet["include"].str.strip() == "")]
    missing = set(runs) - set(sheet["sample"])
    if missing:
        print(f"Not in sample sheet / excluded (skipped): {sorted(missing)}")
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
        raise SystemExit("No chromatogram files found.")

    # method = run length rounded to 10 s
    method = {n: f"{round(df.time_s.max(), -1):.0f}s run" for n, df in runs.items()}
    sheet = load_or_make_sample_sheet(args.data_dir, runs, method, sheet_path)
    runs = {k: v for k, v in runs.items() if k in sheet.index}
    metals = [c for c in next(iter(runs.values())).columns if c != "time_s"]
    order = sorted(runs, key=lambda n: acquired[n] or datetime.min)  # queue order
    print(f"Using {len(runs)} runs; metals {metals}")

    all_long, blank_info = [], []
    for meth in sorted(set(method[n] for n in runs)):
        members = [n for n in order if method[n] == meth]
        t = runs[max(members, key=lambda n: len(runs[n]))]["time_s"].to_numpy()  # common grid
        grid = {n: {m: np.interp(t, runs[n].time_s, runs[n][m]) for m in metals} for n in members}
        blanks = [n for n in members if sheet.loc[n, "blank"]]
        print(f"\n[{meth}] {len(members)} runs, blanks: {blanks or 'NONE -> no subtraction'}")

        def chosen_blanks(n):
            if not blanks:
                return []
            if args.blank_mode == "mean":
                return blanks
            pos = order.index(n)
            before = [b for b in blanks if order.index(b) < pos]
            after = [b for b in blanks if order.index(b) > pos]
            return [before[-1]] if before else [after[0]]

        for n in members:
            if sheet.loc[n, "blank"]:
                continue
            cb = chosen_blanks(n)
            blank_info.append({"sample": n, "method": meth, "blanks_used": "; ".join(cb) or "none"})
            for m in metals:
                blk = np.mean([grid[b][m] for b in cb], axis=0) if cb else np.zeros_like(t)
                all_long.append(pd.DataFrame({
                    "sample": n, "type": sheet.loc[n, "type"], "method": meth, "metal": m,
                    "acquired": acquired[n], "time_s": t, "raw_cps": grid[n][m],
                    "blank_cps": blk, "corrected_cps": grid[n][m] - blk}))

        # blank overlay plot: check drift / carryover
        if blanks:
            fig, axes = plt.subplots(len(metals), 1, figsize=(9, 2.8 * len(metals)), sharex=True)
            for ax, m in zip(np.atleast_1d(axes), metals):
                for b in blanks:
                    ax.plot(t, grid[b][m], lw=0.9,
                            label=f"{b} ({acquired[b]:%H:%M})" if acquired[b] else b)
                ax.set_ylabel(f"{m} CPS")
                ax.legend(fontsize=7, frameon=False)
            np.atleast_1d(axes)[-1].set_xlabel("Retention time (s)")
            fig.suptitle(f"Blank runs, {meth} (raw)")
            fig.tight_layout()
            fig.savefig(out / f"blanks_{meth.replace(' ', '_')}.png", dpi=150)
            plt.close(fig)

    long = pd.concat(all_long, ignore_index=True)
    long.to_csv(out / "corrected_traces.csv", index=False)
    pd.DataFrame(blank_info).to_csv(out / "blank_assignment.csv", index=False)

    # ---- integrate
    areas = []
    for (n, m), g in long.groupby(["sample", "metal"], sort=False):
        for s, e in (args.window or [[g.time_s.min(), g.time_s.max()]]):
            w = g[(g.time_s >= s) & (g.time_s <= e)]
            # local baseline: straight line between the median of the first and last
            # 5 points of the window -> removes leftover drift the blank didn't capture
            y, x = w.corrected_cps.to_numpy(), w.time_s.to_numpy()
            k = min(5, len(y) // 4) or 1
            x0, x1 = x[:k].mean(), x[-k:].mean()
            y0, y1 = np.median(y[:k]), np.median(y[-k:])
            base = y0 + (y1 - y0) * (x - x0) / (x1 - x0)
            areas.append({"sample": n, "type": g["type"].iat[0], "method": g["method"].iat[0],
                          "metal": m, "window": f"{s:.0f}-{e:.0f} s",
                          "raw_area": np.trapezoid(w.raw_cps, x),
                          "blank_area": np.trapezoid(w.blank_cps, x),
                          "blank_corrected_area": np.trapezoid(y, x),
                          "peak_area": np.trapezoid(y - base, x)})
    areas = pd.DataFrame(areas)
    areas["blank_%_of_raw"] = 100 * areas["blank_area"] / areas["raw_area"]
    if not args.window:
        print("\nNOTE: no --window given -> peak_area uses the whole run. For drifting baselines\n"
              "      (e.g. Cu), pass --window START END around your peaks.")
    areas.to_csv(out / "peak_areas.csv", index=False)

    summary = (areas.groupby(["method", "metal", "window", "type"])["peak_area"]
               .agg(n="count", mean="mean", sd="std").reset_index())
    summary["cv_%"] = 100 * summary["sd"] / summary["mean"]
    summary.to_csv(out / "summary_by_type.csv", index=False)

    # ---- plots, one set per method
    for meth, L in long.groupby("method"):
        tag = meth.replace(" ", "_")
        types = list(dict.fromkeys(L.sort_values("acquired")["type"]))
        colors = dict(zip(types, plt.cm.tab10.colors * 3))

        # mean +/- SD corrected chromatogram per type
        fig, axes = plt.subplots(len(metals), 1, figsize=(10, 3.2 * len(metals)), sharex=True)
        for ax, m in zip(np.atleast_1d(axes), metals):
            for ty in types:
                g = L[(L.metal == m) & (L.type == ty)].pivot(index="time_s", columns="sample",
                                                               values="corrected_cps")
                mu, sd = g.mean(axis=1), g.std(axis=1).fillna(0)
                ax.plot(g.index, mu, color=colors[ty], lw=1, label=f"{ty} (n={g.shape[1]})")
                ax.fill_between(g.index, mu - sd, mu + sd, color=colors[ty], alpha=0.2)
            for s, e in (args.window or []):
                ax.axvspan(s, e, color="grey", alpha=0.08)
            ax.axhline(0, color="k", lw=0.4)
            ax.set_ylabel(f"{m}\nblank-corr. CPS")
            ax.legend(fontsize=7, frameon=False)
        np.atleast_1d(axes)[-1].set_xlabel("Retention time (s)")
        fig.suptitle(f"{meth}: mean ± SD by type (blank mode: {args.blank_mode})")
        fig.tight_layout()
        fig.savefig(out / f"by_type_{tag}.png", dpi=150)
        plt.close(fig)

        # every individual run, stacked panels per metal
        fig, axes = plt.subplots(len(metals), 1, figsize=(10, 3.2 * len(metals)), sharex=True)
        for ax, m in zip(np.atleast_1d(axes), metals):
            for n, g in L[L.metal == m].groupby("sample", sort=False):
                ax.plot(g.time_s, g.corrected_cps, lw=0.8, label=n)
            ax.axhline(0, color="k", lw=0.4)
            ax.set_ylabel(f"{m}\nblank-corr. CPS")
            ax.legend(fontsize=6, frameon=False, ncol=2)
        np.atleast_1d(axes)[-1].set_xlabel("Retention time (s)")
        fig.suptitle(f"{meth}: individual runs")
        fig.tight_layout()
        fig.savefig(out / f"runs_{tag}.png", dpi=150)
        plt.close(fig)

        # integrated areas by type
        A = areas[areas.method == meth]
        for win in A["window"].unique():
            fig, axes = plt.subplots(1, len(metals), figsize=(4.2 * len(metals), 4.5))
            for ax, m in zip(np.atleast_1d(axes), metals):
                a = A[(A.metal == m) & (A.window == win)]
                for i, ty in enumerate(types):
                    v = a[a.type == ty]["peak_area"]
                    ax.bar(i, v.mean(), yerr=v.std() if len(v) > 1 else 0, color=colors[ty],
                           alpha=0.6, capsize=4)
                    ax.scatter(np.full(len(v), i), v, color="k", s=12, zorder=3)
                ax.set_xticks(range(len(types)), types, rotation=45, ha="right", fontsize=7)
                ax.set_title(m)
                ax.axhline(0, color="k", lw=0.5)
            np.atleast_1d(axes)[0].set_ylabel("Peak area, blank + baseline corr. (CPS·s)")
            fig.suptitle(f"{meth}: integrated area, {win}")
            fig.tight_layout()
            fig.savefig(out / f"areas_{tag}_{win.replace(' ', '').replace('-', 'to')}.png", dpi=150)
            plt.close(fig)

    print(f"\nDone. Results in {out}/")
    with pd.option_context("display.width", 200, "display.float_format", "{:.3g}".format):
        print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
