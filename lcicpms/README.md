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

## Interactive viewer (ICP-MS, DAD and other detectors)

`viewer_template.html` is a standalone page: open it in a browser, tap **Files & samples → Add files…**
and select the exports from one batch.

- **Recognised automatically:** Agilent ICP-MS "Intensity Vs Time" CSVs, Agilent DAD signal exports
  (one `#"DAD1 - …Sig=280.0,4.0 …"` block per wavelength, time in minutes; 40 Hz data is bin-averaged to
  ≤ 8000 points), `BatchLog.csv`, `sample_sheet.csv`.
- **Import editor:** any other text table opens an editor showing the raw lines; pick separator, header and
  data rows, time column and unit, signal columns, detector label, unit and where the run name comes from.
  **Save format** makes later files that start the same way load automatically (stored in that browser).
- **Runs:** files with the same run name merge, so an ICP-MS and a DAD export of one injection become one run.
  Rename a file's run under Files & samples to pair them.
- **Panels & offsets:** build your own stacked panels (any mix of isotopes/wavelengths), each trace raw,
  % of its own max, or × factor, plus a vertical shift. Per-detector time offsets (s) line up detectors in series.
- **Method:** pick a run length or **All** to overlay runs of different lengths (blanks still matched per method).
- Blank subtraction (off / mean / nearest prior / per-run choice), technical vs biological replicates,
  mean by type, run-order carryover check, multi-peak table (CSV), independent X/Y zoom, Save picture (PNG/SVG).

To make a copy with a batch preloaded:
`python lcicpms/make_viewer.py path/to/csv_folder --label "Batch name" [--extra other_export.CSV ...]`
