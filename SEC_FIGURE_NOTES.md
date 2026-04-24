# SEC Figure Notes

Use `plot_sec_curves.py` for thesis figures from the AKTA exports in this folder.
Use `sec_browser.py` when you want to browse the full archive, interactively choose traces, and save selected overlays.

The script is set up for Adobe Illustrator workflows:

- Save as `.svg`, `.pdf`, or `.eps` for vector curves.
- Text is exported as editable text, not converted to outlines.
- Use `--transparent` if you want to place curves over custom Illustrator layouts.

## Examples

Interactive browser:

```bash
python sec_browser.py --root /Users/elektramakris/Desktop/SOTOMAYOR/Thesis/Archive
```

Browser controls:

- `Load`: choose `asc`, `xls`, or `both`
- `Absorbance`: switch between `Normalized` and `Actual`
- `Title From Selection`: auto-build a title from the selected samples and dates
- Select traces directly in the main table; there is no separate second sample list
- `Apply Palette Color` applies one of 15 standardized colors to the selected trace rows
- `Reset Colors` clears custom colors for the selected rows, or all rows if none are selected
- `Line width` controls how thick the plotted traces are
- `Column`: parsed from the filename, such as `S75 10/300` or `S200 16/600`
- `Trace Sets`: checkbox filters for groups like `WT`, `Probe`, `Blocker`, `Salsa`, `EC1/2`, `EC7/8`, and `S1-S4`
- file list includes parsed run dates from filename tokens like `05112025` or `120325`

Single chromatogram:

```bash
python plot_sec_curves.py \
  S75q10300qmicroplateqEMqCDH23EC1q2qProbe1qRun1q05112025.asc \
  --output figures/cdh23_probe1.svg
```

Normalized overlay:

```bash
python plot_sec_curves.py \
  S200q16600qmicroplateqEMqCDH23qEC7q8qsalsaqRun1q09232025.asc \
  S200q16600qmicroplateqEMqCDH23EC7q8qsalsaqRun1q09252025.asc \
  --labels "Salsa run 1" "Salsa run 2" \
  --normalize \
  --baseline-subtract \
  --smooth-window 5 \
  --output figures/salsa_overlay.svg
```

WT versus sample comparison:

```bash
python plot_sec_curves.py \
  S200q16600qmicroplate004qEMqCDH23qEC7q8qWTqRun1q120325.asc \
  S200q16600qmicroplateqEMqCDH23EC7q8qsalsaqRun1q10152025.asc \
  --labels WT Salsa \
  --normalize \
  --baseline-subtract \
  --xlim 5 16 \
  --output figures/wt_vs_salsa.svg
```

## Practical defaults

- `--baseline-subtract` is usually worth using for cleaner overlays.
- `--normalize` is useful when comparing oligomeric state patterns rather than total signal.
- The browser exports both `.svg` and `.png` together from the same base filename.
- Save the `.svg` in Illustrator for editing; use the `.png` for slides or quick sharing.
- Axis ticks are drawn inward.
- Axis labels and tick labels are intentionally smaller.
- PNG export now saves at high resolution.
- In `sec_browser.py`, use the search bar to narrow by sample names like `WT`, `Probe`, `Blocker`, `EC1`, or `EC7`.
