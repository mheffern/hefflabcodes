# LC-ICP-MS analysis

Compares Fe/Cu/Zn (or any metals) chromatograms from MassHunter "Intensity Vs Time CPS" CSV exports
by sample type and by metal, with blank subtraction.

```bash
pip install pandas numpy matplotlib
python lcicpms/analyze_lcicpms.py path/to/csv_folder                     # 1st run writes sample_sheet.csv
# edit sample_sheet.csv (type / blank / include columns), then:
python lcicpms/analyze_lcicpms.py path/to/csv_folder --blank-mode nearest --window 150 280 --window 280 400
```

- `--blank-mode mean` – subtract the average of all blanks (default)
- `--blank-mode nearest` – subtract the blank run just before each sample in the queue (drift/carryover)
- `--window START END` – integrate only that retention-time range (seconds); repeatable

Outputs go to `csv_folder/results/`: `peak_areas.csv`, `summary_by_type.csv` (mean/SD/CV per type),
`corrected_traces.csv`, and PNG plots.
