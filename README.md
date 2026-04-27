# SEC Browser

Interactive browser and export tools for size exclusion chromatography traces.

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://sec-browser-sxgbgr8md3c4qcdexusdls.streamlit.app/)

Hosted app:

- [SEC Browser on Streamlit Community Cloud](https://sec-browser-sxgbgr8md3c4qcdexusdls.streamlit.app/)

This project includes:

- `sec_browser.py`: a desktop browser for selecting traces, previewing overlays, and exporting SVG, PNG, Plotly HTML, XMGrace, and session JSON files
- `streamlit_app.py`: a shareable browser-based app for uploading SEC files and generating the same exports from a web UI
- `plot_sec_curves.py`: a command-line tool for scripted overlays and exports
- `SEC_Browser_Colab.ipynb`: a Colab workflow for uploading SEC files and generating exports in the cloud: **NOT RECOMMENDED**

## Features

- Browse `.asc` and `.xls` SEC exports
- Filter by search term, file type, and dataset-driven quick filters derived from filenames
- Overlay multiple traces in normalized or actual absorbance mode
- Anchor normalization to `x=0` or the left x-limit
- Export Illustrator-friendly SVG plus high-resolution PNG
- Save and reload `.session.json` figure states
- Export Plotly HTML and XMGrace `.agr`
- Run the workflow as a browser app with Streamlit

## Requirements

- Python 3.11+
- Tkinter available in your Python build for the desktop browser only

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

## Web App Usage

Run the Streamlit app:

```bash
streamlit run streamlit_app.py
```

The web app is designed for GitHub sharing and hosted deployment. It includes:

- SEC file uploads instead of local folder browsing
- search, quick filters, and multi-trace selection
- normalized or actual absorbance mode
- figure size, line width, legend, transparency, and per-trace colors
- per-trace peak annotation controls
- Matplotlib and Plotly preview tabs
- downloadable SVG, PNG, Plotly HTML, XMGrace, and `.session.json`
- a one-click zip bundle containing all export formats

This is the best path if you want a browser-based version instead of the local Tk app.

For Streamlit Community Cloud, point the deployment at:

- app file: `streamlit_app.py`
- dependency file: `requirements.txt`

## Deploy To Streamlit Community Cloud

This repository is already organized for Streamlit Community Cloud deployment.

Use the official Community Cloud flow:

1. Go to [share.streamlit.io](https://share.streamlit.io/).
2. Sign in and connect your GitHub account if needed.
3. Click `Create app`.
4. Choose repository: `elektra773/sec-browser`
5. Choose branch: `main`
6. Choose app file: `streamlit_app.py`
7. Optional: choose a custom subdomain
8. In `Advanced settings`, leave secrets empty unless you add private credentials later
9. Click `Deploy`

The official deployment steps are documented here:

- [Deploy your app on Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)
- [Prep and deploy your app on Community Cloud](https://docs.streamlit.io/streamlit-community-cloud/get-started/deploy-an-app)

After deployment, Streamlit assigns a public `streamlit.app` URL that you can share directly.

Current deployment:

- [https://sec-browser-sxgbgr8md3c4qcdexusdls.streamlit.app/](https://sec-browser-sxgbgr8md3c4qcdexusdls.streamlit.app/)

If anonymous visitors are redirected to sign-in, open your app in Streamlit Community Cloud and set:

- `App settings` → `Sharing`
- `Who can view this app` → `This app is public and searchable`

## Colab Usage

Open the notebook directly in Colab:

- [SEC_Browser_Colab.ipynb](https://colab.research.google.com/github/elektra773/sec-browser/blob/main/SEC_Browser_Colab.ipynb)

The notebook is the recommended path for cloud use and for collaborators who do not want to run the desktop Tk browser locally.
It now mirrors the desktop workflow much more closely, including:

- upload plus session loading
- search, quick filters, and trace multi-select
- tabbed controls for plot settings, appearance, and export
- per-trace color selection
- per-trace peak-label controls
- SVG + PNG export with companion `.session.json`
- Plotly HTML and XMGrace export

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
- For a hosted browser workflow, `streamlit_app.py` is the best fit.
- For Colab, the notebook is useful when collaborators are already working inside Google Drive or Colab.
