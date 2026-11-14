# LC-ICP-MS analysis

Compares Fe/Cu/Zn (or any metals) chromatograms from MassHunter "Intensity Vs Time CPS" CSV exports
by sample type and by metal, with blank subtraction.

```bash
pip install pandas numpy matplotlib
python lcicpms/analyze_lcicpms.py path/to/csv_folder                     # 1st run writes sample_sheet.csv
# edit sample_sheet.csv (type / blank / include columns), then:
python lcicpms/analyze_lcicpms.py path/to/csv_folder --blank-mode nearest --window 300 550
```

- `--blank-mode mean` – subtract the average of all blanks (default)
- `--blank-mode nearest` – subtract the blank run just before each sample in the queue (drift/carryover)
- Sample sheet columns: `sample, type, blank, include, bio_sample, blank_used`. Runs sharing a
  `bio_sample` are technical replicates and are averaged before the mean/SD across biological samples
  (`summary_by_type.csv`, `peak_areas_by_bio_sample.csv`). `blank_used`: auto, none, or blank name(s) joined by `;`.
  The viewer's **Copy sample sheet** button produces this file.
- `--window START END` – integrate only that retention-time range (seconds); repeatable.
  A straight local baseline between the window edges is also subtracted (`peak_area`),
  which removes leftover drift (e.g. Cu background falling over the day).
- Runs are grouped by method (run length); blanks are only used for runs of the same method.
- `BatchLog.csv` comments are copied into the generated sample sheet; `blanks_*.png` shows drift/carryover.

Outputs go to `csv_folder/results/`: `peak_areas.csv`, `summary_by_type.csv` (mean/SD/CV per type),
`corrected_traces.csv`, and PNG plots.

## Interactive viewer

`viewer_template.html` is a standalone page: open it in a browser, tap **Files & samples → Add files…**
and select the exports from one batch (add BatchLog.csv too for queue comments).
**Files & samples** lets you add/remove files, exclude runs, and set each run's role (sample/blank),
type, biological sample (same value = technical replicate) and which blank to subtract.
Tap a sample name to see its CSV header, batch-log entry and raw signal summary. Toggles: method, metals, blank subtraction
(off / mean / nearest prior), seconds vs minutes, linear/log, each run vs mean by type, raw blanks.
**Run order** shows every run in acquisition order (blanks shaded) with a carryover table
(blank peak-window area as % of the run before it) and a background-through-the-queue chart.
Hover for exact time + CPS, drag to zoom onto a peak and read apex times from the table,
click to pin points; both tables copy as tab-separated text for Excel.

To make a copy with a batch preloaded: `python lcicpms/make_viewer.py path/to/csv_folder`.
