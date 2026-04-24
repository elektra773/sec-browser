# SEC Browser

Interactive browser and export tools for size exclusion chromatography traces.

This project includes:

- `sec_browser.py`: a desktop browser for selecting traces, previewing overlays, and exporting SVG, PNG, Plotly HTML, XMGrace, and session JSON files
- `plot_sec_curves.py`: a command-line tool for scripted overlays and exports

## Features

- Browse `.asc` and `.xls` SEC exports
- Filter by search term, file type, and dataset-driven quick filters derived from filenames
- Overlay multiple traces in normalized or actual absorbance mode
- Anchor normalization to `x=0` or the left x-limit
- Export Illustrator-friendly SVG plus high-resolution PNG
- Save and reload `.session.json` figure states
- Export Plotly HTML and XMGrace `.agr`

## Requirements

- Python 3.11+
- Tkinter available in your Python build

Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Browser Usage

Run the browser and point it at a directory containing `.asc` and/or `.xls` SEC files:

```bash
python sec_browser.py --root /path/to/sec/data
```

Typical workflow:

1. Filter or search the file list.
2. Select the traces you want to overlay.
3. Adjust normalization, limits, title, legend, figure size, and line width.
4. Choose a trace from the color dropdown and assign a palette color if needed.
5. Export SVG + PNG.

Each SVG/PNG export also writes a companion session file:

- `figure_name.svg`
- `figure_name.png`
- `figure_name.session.json`

You can reload that state later from `Load Session`.

## CLI Usage

Example overlay:

```bash
python plot_sec_curves.py \
  sample1.asc sample2.asc \
  --labels "Sample 1" "Sample 2" \
  --normalize \
  --normalize-anchor left-limit \
  --xlim 5 20 \
  --title "SEC Overlay" \
  --output figures/sec_overlay.svg
```

Optional exports:

```bash
python plot_sec_curves.py \
  sample1.asc sample2.asc \
  --normalize \
  --output figures/sec_overlay.svg \
  --plotly-output figures/sec_overlay.html \
  --xmgrace-output figures/sec_overlay.agr
```

## Notes For Sharing

- The code is no longer tied to thesis-specific labels like `WT`, `Probe`, or `Blocker`.
- The browser now builds `Quick Filters` automatically from repeated words in whatever SEC labels are present in the folder.
- The code works on generic `.asc` and `.xls` SEC exports with two numeric columns after the standard header rows.
- For GitHub, keep the code and docs in the repo and usually leave raw data files out unless you intend to share them.
- For Colab, the command-line workflow in `plot_sec_curves.py` is the better fit, since the Tk browser is a desktop GUI.
