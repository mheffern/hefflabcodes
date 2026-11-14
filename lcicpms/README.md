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
- `--window START END` – integrate only that retention-time range (seconds); repeatable.
  A straight local baseline between the window edges is also subtracted (`peak_area`),
  which removes leftover drift (e.g. Cu background falling over the day).
- Runs are grouped by method (run length); blanks are only used for runs of the same method.
- `BatchLog.csv` comments are copied into the generated sample sheet; `blanks_*.png` shows drift/carryover.

Outputs go to `csv_folder/results/`: `peak_areas.csv`, `summary_by_type.csv` (mean/SD/CV per type),
`corrected_traces.csv`, and PNG plots.
