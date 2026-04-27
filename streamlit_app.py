from __future__ import annotations

from collections import Counter
from datetime import datetime
from io import BytesIO
import json
from pathlib import Path
import tempfile
import zipfile

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from plot_sec_curves import (
    DEFAULT_FIGSIZE,
    DEFAULT_LINEWIDTH,
    EXPORT_RASTER_DPI,
    PREVIEW_DPI,
    clean_label,
    export_plotly_html,
    export_xmgrace,
    extract_column_name,
    extract_run_date,
    find_top_peaks,
    process_trace,
    read_sec_file,
    render_sec_plot,
)

STANDARD_COLORS = {
    "Navy": "#16324f",
    "Blue": "#1f77b4",
    "Sky": "#4ea5d9",
    "Teal": "#1b998b",
    "Cyan": "#17becf",
    "Turquoise": "#2ec4b6",
    "Mint": "#52b788",
    "Seafoam": "#74c69d",
    "Green": "#2ca02c",
    "Forest": "#1b5e20",
    "Pine": "#2d6a4f",
    "Olive": "#7a8b24",
    "Lime": "#8ac926",
    "Chartreuse": "#a7c957",
    "Gold": "#d4a017",
    "Mustard": "#e09f3e",
    "Sand": "#e9c46a",
    "Orange": "#ff7f0e",
    "Peach": "#f7b267",
    "Rust": "#c7511f",
    "Red": "#d62728",
    "Crimson": "#b22222",
    "Coral": "#e76f51",
    "Salmon": "#f28482",
    "Berry": "#b23a48",
    "Magenta": "#e83f6f",
    "Rose": "#ff5d8f",
    "Fuchsia": "#d81b60",
    "Hot Pink": "#d94f98",
    "Cerise": "#d65db1",
    "Mulberry": "#b565c2",
    "Orchid": "#c77dff",
    "Purple": "#7a5195",
    "Violet": "#9d4edd",
    "Lavender": "#b8a1ff",
    "Plum": "#8e5ea2",
    "Brown": "#8c564b",
    "Tan": "#b08968",
    "Mocha": "#6f4e37",
    "Black": "#222222",
}

FILTER_TOKEN_STOPWORDS = {
    "run",
    "rerun",
    "sample",
    "trace",
    "standard",
}


def ensure_state() -> None:
    defaults = {
        "working_dir": tempfile.mkdtemp(prefix="sec_browser_streamlit_"),
        "search_term": "",
        "format_filter": "asc",
        "quick_filters": [],
        "selected_trace_names": [],
        "display_mode": "normalized",
        "baseline_subtract": True,
        "smooth_window": 5,
        "normalize_anchor": "left-limit",
        "plot_title": "",
        "x_min": "",
        "x_max": "",
        "y_min": "",
        "y_max": "",
        "figure_width": DEFAULT_FIGSIZE[0],
        "figure_height": DEFAULT_FIGSIZE[1],
        "line_width": DEFAULT_LINEWIDTH,
        "plot_style": "paper",
        "show_legend": True,
        "transparent_background": False,
        "output_stem": "sec_overlay",
        "trace_colors": {},
        "peak_visibility": {},
        "status_message": "Upload SEC files to begin.",
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def upload_dir() -> Path:
    directory = Path(st.session_state["working_dir"]) / "uploads"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def output_dir() -> Path:
    directory = Path(st.session_state["working_dir"]) / "outputs"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def normalize_output_stem(value: str) -> str:
    cleaned = value.strip() or "sec_overlay"
    path = Path(cleaned)
    if path.suffix.lower() in {".svg", ".png", ".html", ".agr", ".json", ".zip"}:
        path = path.with_suffix("")
    return str(path)


def label_tokens(label: str) -> set[str]:
    tokens = set()
    for raw_token in label.lower().replace("/", " ").split():
        token = "".join(ch for ch in raw_token if ch.isalnum())
        if len(token) < 2 or token.isdigit() or token in FILTER_TOKEN_STOPWORDS:
            continue
        tokens.add(token)
    return tokens


def parse_limits(lower: str, upper: str) -> tuple[float, float] | None:
    lower = lower.strip()
    upper = upper.strip()
    if not lower and not upper:
        return None
    return float(lower), float(upper)


def build_inventory(paths: list[Path]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "filename": path.name,
                "sample": clean_label(path),
                "column": extract_column_name(path),
                "date": extract_run_date(path),
                "type": path.suffix.lower().lstrip("."),
            }
            for path in paths
        ]
    )


def title_from_selection(paths: list[Path]) -> str:
    if not paths:
        return ""
    labels = sorted({clean_label(path) for path in paths})
    columns = sorted({extract_column_name(path) for path in paths if extract_column_name(path)})
    dates = sorted({extract_run_date(path) for path in paths if extract_run_date(path)})

    title = " vs ".join(labels[:2]) if len(labels) == 2 else ", ".join(labels[:3])
    if len(labels) > 3:
        title = f"{title} +{len(labels) - 3} more"
    if columns:
        title = f"{title} [{', '.join(columns)}]"
    if dates:
        title = f"{title} ({', '.join(dates)})"
    return title


def sync_uploaded_files(uploaded_files) -> None:
    if not uploaded_files:
        return
    saved = 0
    for uploaded_file in uploaded_files:
        destination = upload_dir() / uploaded_file.name
        destination.write_bytes(uploaded_file.getbuffer())
        saved += 1
    if saved:
        st.session_state["status_message"] = f"Saved {saved} SEC file(s) locally for this session."


def list_sec_files() -> list[Path]:
    return sorted(
        [path for path in upload_dir().iterdir() if path.suffix.lower() in {".asc", ".xls"}],
        key=lambda path: path.name.lower(),
    )


def compute_quick_filters(paths: list[Path]) -> list[str]:
    token_counts = Counter()
    for path in paths:
        token_counts.update(label_tokens(clean_label(path)))
    return [token for token, count in token_counts.most_common(12) if count >= 2]


def filter_paths(paths: list[Path]) -> list[Path]:
    query = st.session_state["search_term"].strip().lower()
    load_format = st.session_state["format_filter"]
    selected_filters = set(st.session_state["quick_filters"])

    filtered = []
    for path in paths:
        label = clean_label(path)
        if query and query not in label.lower() and query not in path.name.lower():
            continue
        if load_format != "both" and path.suffix.lower().lstrip(".") != load_format:
            continue
        if selected_filters and not (label_tokens(label) & selected_filters):
            continue
        filtered.append(path)
    return filtered


def trace_option_label(path: Path) -> str:
    column = extract_column_name(path) or "No column"
    date = extract_run_date(path) or "No date"
    file_type = path.suffix.lower().lstrip(".")
    return f"{clean_label(path)} [{column} | {date} | {file_type}]"


def trace_detail_label(path: Path) -> str:
    column = extract_column_name(path) or "No column"
    date = extract_run_date(path) or "No date"
    file_type = path.suffix.lower().lstrip(".")
    return f"{clean_label(path)} | {column} | {date} | {file_type}"


def get_selected_paths(all_paths: list[Path]) -> list[Path]:
    selected_names = set(st.session_state["selected_trace_names"])
    return [path for path in all_paths if path.name in selected_names]


def color_name_for_trace(path: Path, index: int) -> str:
    saved = st.session_state["trace_colors"].get(path.name)
    if saved in STANDARD_COLORS:
        return saved
    palette = list(STANDARD_COLORS.keys())
    return palette[index % len(palette)]


def peak_ranks_for_trace(path: Path) -> list[int]:
    ranks = st.session_state["peak_visibility"].get(path.name, [])
    return [rank for rank in ranks if rank in {1, 2, 3, 4, 5}]


def build_processed_traces(selected_paths: list[Path]) -> tuple[list[dict], tuple[float, float] | None, tuple[float, float] | None, dict[str, set[int]]]:
    if not selected_paths:
        raise ValueError("Select at least one trace.")

    xlim = parse_limits(st.session_state["x_min"], st.session_state["x_max"])
    ylim = parse_limits(st.session_state["y_min"], st.session_state["y_max"])
    processed = []
    peak_visibility: dict[str, set[int]] = {}

    for index, path in enumerate(selected_paths):
        raw_trace = read_sec_file(path)
        trace = process_trace(
            raw_trace,
            normalize=st.session_state["display_mode"] == "normalized",
            baseline_subtract=st.session_state["baseline_subtract"],
            smooth_window=max(1, int(st.session_state["smooth_window"])),
            normalize_window=xlim if st.session_state["display_mode"] == "normalized" else None,
            normalize_anchor=st.session_state["normalize_anchor"],
        )
        color_name = color_name_for_trace(path, index)
        peak_visibility[str(path)] = set(peak_ranks_for_trace(path))
        processed.append(
            {
                "trace_id": str(path),
                "label": clean_label(path),
                "color": STANDARD_COLORS[color_name],
                "line_width": max(0.4, float(st.session_state["line_width"])),
                "data": trace,
                "peaks": find_top_peaks(trace, peak_window=xlim, top_n=5),
            }
        )

    return processed, xlim, ylim, peak_visibility


def render_current_figure(selected_paths: list[Path]):
    import matplotlib.pyplot as plt

    processed, xlim, ylim, peak_visibility = build_processed_traces(selected_paths)
    fig, ax = plt.subplots(
        figsize=(float(st.session_state["figure_width"]), float(st.session_state["figure_height"])),
        dpi=PREVIEW_DPI,
    )
    render_sec_plot(
        fig=fig,
        ax=ax,
        traces=processed,
        title=st.session_state["plot_title"].strip(),
        normalized=st.session_state["display_mode"] == "normalized",
        xlim=xlim,
        ylim=ylim,
        show_legend=st.session_state["show_legend"],
        style=st.session_state["plot_style"],
        visible_peak_ranks=peak_visibility,
    )
    return fig, processed, xlim, ylim


def make_svg_png_session_bundle(selected_paths: list[Path]) -> dict[str, bytes]:
    fig, processed, xlim, ylim = render_current_figure(selected_paths)
    svg_bytes = BytesIO()
    png_bytes = BytesIO()
    fig.savefig(svg_bytes, format="svg", transparent=st.session_state["transparent_background"])
    fig.savefig(
        png_bytes,
        format="png",
        dpi=EXPORT_RASTER_DPI,
        transparent=st.session_state["transparent_background"],
    )
    session_bytes = json.dumps(build_session_state(selected_paths), indent=2).encode("utf-8")
    import matplotlib.pyplot as plt
    plt.close(fig)
    return {
        ".svg": svg_bytes.getvalue(),
        ".png": png_bytes.getvalue(),
        ".session.json": session_bytes,
    }


def make_plotly_html(selected_paths: list[Path]) -> bytes:
    processed, xlim, ylim, _peak_visibility = build_processed_traces(selected_paths)
    output = output_dir() / "preview.html"
    export_plotly_html(
        traces=processed,
        output=output,
        title=st.session_state["plot_title"].strip(),
        x_label="Elution Volume (mL)",
        y_label="Normalized absorbance" if st.session_state["display_mode"] == "normalized" else "Absorbance (mAU)",
        show_legend=st.session_state["show_legend"] and len(processed) > 1,
        xlim=xlim,
        ylim=ylim,
    )
    return output.read_bytes()


def make_xmgrace(selected_paths: list[Path]) -> bytes:
    processed, xlim, ylim, _peak_visibility = build_processed_traces(selected_paths)
    output = output_dir() / "preview.agr"
    export_xmgrace(
        traces=processed,
        output=output,
        title=st.session_state["plot_title"].strip(),
        x_label="Elution Volume (mL)",
        y_label="Normalized absorbance" if st.session_state["display_mode"] == "normalized" else "Absorbance (mAU)",
        show_legend=st.session_state["show_legend"] and len(processed) > 1,
        xlim=xlim,
        ylim=ylim,
    )
    return output.read_bytes()


def build_session_state(selected_paths: list[Path]) -> dict:
    xlim = parse_limits(st.session_state["x_min"], st.session_state["x_max"])
    ylim = parse_limits(st.session_state["y_min"], st.session_state["y_max"])
    return {
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "output_base": str(output_dir() / normalize_output_stem(st.session_state["output_stem"])),
        "selected_traces": [str(path) for path in selected_paths],
        "trace_labels": {str(path): clean_label(path) for path in selected_paths},
        "trace_colors": {
            str(path): STANDARD_COLORS[color_name_for_trace(path, idx)]
            for idx, path in enumerate(selected_paths)
        },
        "display_mode": st.session_state["display_mode"],
        "normalize_anchor": st.session_state["normalize_anchor"],
        "baseline_subtract": st.session_state["baseline_subtract"],
        "smooth_window": int(st.session_state["smooth_window"]),
        "style": st.session_state["plot_style"],
        "line_width": float(st.session_state["line_width"]),
        "figure_width": float(st.session_state["figure_width"]),
        "figure_height": float(st.session_state["figure_height"]),
        "show_legend": st.session_state["show_legend"],
        "title": st.session_state["plot_title"],
        "xlim": list(xlim) if xlim else None,
        "ylim": list(ylim) if ylim else None,
        "transparent_background": st.session_state["transparent_background"],
        "load_format": st.session_state["format_filter"],
        "active_filters": list(st.session_state["quick_filters"]),
        "peak_visibility": {
            str(path): peak_ranks_for_trace(path)
            for path in selected_paths
            if peak_ranks_for_trace(path)
        },
    }


def apply_session_state(session_state: dict, available_paths: list[Path]) -> None:
    st.session_state["display_mode"] = session_state.get("display_mode", st.session_state["display_mode"])
    st.session_state["normalize_anchor"] = session_state.get("normalize_anchor", st.session_state["normalize_anchor"])
    st.session_state["baseline_subtract"] = session_state.get("baseline_subtract", st.session_state["baseline_subtract"])
    st.session_state["smooth_window"] = int(session_state.get("smooth_window", st.session_state["smooth_window"]))
    st.session_state["plot_style"] = session_state.get("style", st.session_state["plot_style"])
    st.session_state["line_width"] = float(session_state.get("line_width", st.session_state["line_width"]))
    st.session_state["figure_width"] = float(session_state.get("figure_width", st.session_state["figure_width"]))
    st.session_state["figure_height"] = float(session_state.get("figure_height", st.session_state["figure_height"]))
    st.session_state["show_legend"] = bool(session_state.get("show_legend", st.session_state["show_legend"]))
    st.session_state["plot_title"] = session_state.get("title", st.session_state["plot_title"])
    st.session_state["transparent_background"] = bool(session_state.get("transparent_background", st.session_state["transparent_background"]))
    st.session_state["format_filter"] = session_state.get("load_format", st.session_state["format_filter"])
    st.session_state["quick_filters"] = list(session_state.get("active_filters", st.session_state["quick_filters"]))
    st.session_state["output_stem"] = normalize_output_stem(Path(session_state.get("output_base", st.session_state["output_stem"])).name)

    xlim = session_state.get("xlim") or ["", ""]
    ylim = session_state.get("ylim") or ["", ""]
    st.session_state["x_min"] = "" if xlim[0] in ("", None) else str(xlim[0])
    st.session_state["x_max"] = "" if xlim[1] in ("", None) else str(xlim[1])
    st.session_state["y_min"] = "" if ylim[0] in ("", None) else str(ylim[0])
    st.session_state["y_max"] = "" if ylim[1] in ("", None) else str(ylim[1])

    trace_colors = {}
    for path_text, color_hex in session_state.get("trace_colors", {}).items():
        name = Path(path_text).name
        for color_name, known_hex in STANDARD_COLORS.items():
            if known_hex.lower() == str(color_hex).lower():
                trace_colors[name] = color_name
                break
    st.session_state["trace_colors"] = trace_colors

    peak_visibility = {}
    for path_text, ranks in session_state.get("peak_visibility", {}).items():
        peak_visibility[Path(path_text).name] = [int(rank) for rank in ranks if int(rank) in {1, 2, 3, 4, 5}]
    st.session_state["peak_visibility"] = peak_visibility

    available_names = {path.name for path in available_paths}
    st.session_state["selected_trace_names"] = [
        Path(path_text).name
        for path_text in session_state.get("selected_traces", [])
        if Path(path_text).name in available_names
    ]
    st.session_state["status_message"] = f"Loaded session with {len(st.session_state['selected_trace_names'])} restored trace(s)."


def render_plotly_preview(selected_paths: list[Path]) -> go.Figure:
    processed, xlim, ylim, _peak_visibility = build_processed_traces(selected_paths)
    figure = go.Figure()
    for trace in processed:
        figure.add_trace(
            go.Scatter(
                x=trace["data"]["ml"],
                y=trace["data"]["mAU"],
                mode="lines",
                name=trace["label"],
                line={"color": trace["color"], "width": trace["line_width"]},
            )
        )
    figure.update_layout(
        title=st.session_state["plot_title"].strip(),
        xaxis_title="Elution Volume (mL)",
        yaxis_title="Normalized absorbance" if st.session_state["display_mode"] == "normalized" else "Absorbance (mAU)",
        showlegend=st.session_state["show_legend"],
        template="simple_white",
        font={"family": "Arial, Helvetica, sans-serif", "size": 14},
        margin={"l": 40, "r": 20, "t": 60, "b": 40},
    )
    figure.update_xaxes(showline=True, linewidth=1, linecolor="black", ticks="inside")
    figure.update_yaxes(showline=True, linewidth=1, linecolor="black", ticks="inside")
    if xlim:
        figure.update_xaxes(range=list(xlim))
    if ylim:
        figure.update_yaxes(range=list(ylim))
    return figure


st.set_page_config(page_title="SEC Browser", page_icon="📈", layout="wide")
ensure_state()

st.title("SEC Browser Web App")
st.caption("Upload SEC files, select traces, preview the exact figure styling, and export the same formats as the desktop browser.")

uploaded_files = st.file_uploader(
    "Upload `.asc` or `.xls` SEC files",
    type=["asc", "xls"],
    accept_multiple_files=True,
)
sync_uploaded_files(uploaded_files)
all_paths = list_sec_files()
quick_filter_options = compute_quick_filters(all_paths)
st.session_state["quick_filters"] = [token for token in st.session_state["quick_filters"] if token in quick_filter_options]
filtered_paths = filter_paths(all_paths)
filtered_names = [path.name for path in filtered_paths]
st.session_state["selected_trace_names"] = [name for name in st.session_state["selected_trace_names"] if name in filtered_names]

tab_browser, tab_plot, tab_appearance, tab_export = st.tabs(["Browser", "Plot", "Appearance", "Export"])

with tab_browser:
    left_col, right_col = st.columns([0.95, 1.8], gap="large")

    with left_col:
        session_file = st.file_uploader("Optional session JSON", type=["json"], accept_multiple_files=False)
        action_col1, action_col2 = st.columns(2)
        with action_col1:
            if st.button("Refresh", use_container_width=True):
                st.session_state["status_message"] = "Refreshed uploaded files."
                st.rerun()
            if st.button("Select Visible", use_container_width=True):
                st.session_state["selected_trace_names"] = filtered_names
                st.rerun()
        with action_col2:
            if st.button("Clear", use_container_width=True):
                st.session_state["selected_trace_names"] = []
                st.rerun()
            if st.button("Load Session", use_container_width=True) and session_file is not None:
                apply_session_state(json.loads(session_file.getvalue().decode("utf-8")), all_paths)
                st.rerun()

        st.text_input("Search", key="search_term", placeholder="WT, blocker, EC1, salsa, S75...")
        st.selectbox("Load", options=["asc", "xls", "both"], key="format_filter")
        st.multiselect("Quick Filters", options=quick_filter_options, key="quick_filters")

        if st.button("Title From Selection", use_container_width=True):
            st.session_state["plot_title"] = title_from_selection(get_selected_paths(all_paths))
            st.rerun()

        st.caption(f"{len(filtered_paths)} visible trace(s), {len(st.session_state['selected_trace_names'])} selected.")

    with right_col:
        inventory = build_inventory(all_paths)
        if inventory.empty:
            st.info("No SEC files uploaded yet.")
        else:
            previously_selected = list(st.session_state["selected_trace_names"])
            filtered_inventory = inventory[inventory["filename"].isin({path.name for path in filtered_paths})].copy()
            filtered_inventory.insert(
                0,
                "plot",
                filtered_inventory["filename"].isin(st.session_state["selected_trace_names"]),
            )
            filtered_inventory = filtered_inventory.rename(
                columns={
                    "plot": "Plot",
                    "sample": "Sample",
                    "column": "Column",
                    "date": "Date",
                    "type": "Type",
                }
            )
            selector_view = filtered_inventory[["Plot", "Sample", "Column", "Date", "Type"]]
            edited_selector = st.data_editor(
                selector_view,
                use_container_width=True,
                hide_index=True,
                height=460,
                disabled=["Sample", "Column", "Date", "Type"],
                column_config={
                    "Plot": st.column_config.CheckboxColumn(
                        "Plot",
                        help="Check traces to include in the overlay.",
                        width="small",
                    ),
                    "Sample": st.column_config.TextColumn("Sample", width="large"),
                    "Column": st.column_config.TextColumn("Column", width="medium"),
                    "Date": st.column_config.TextColumn("Date", width="medium"),
                    "Type": st.column_config.TextColumn("Type", width="small"),
                },
                key="trace_selector_editor",
            )
            visible_selected = filtered_inventory.loc[edited_selector["Plot"], "filename"].tolist()
            hidden_selected = [
                name for name in previously_selected if name not in set(filtered_inventory["filename"])
            ]
            st.session_state["selected_trace_names"] = hidden_selected + visible_selected

with tab_plot:
    st.radio(
        "Absorbance",
        options=["normalized", "actual"],
        key="display_mode",
        format_func=lambda value: "Normalized" if value == "normalized" else "Actual",
        horizontal=True,
    )
    row1_col1, row1_col2, row1_col3 = st.columns(3)
    with row1_col1:
        st.checkbox("Baseline subtract", key="baseline_subtract")
    with row1_col2:
        st.number_input("Smooth", min_value=1, max_value=101, step=1, key="smooth_window")
    with row1_col3:
        st.selectbox("Anchor", options=["left-limit", "zero"], key="normalize_anchor")

    st.text_input("Title", key="plot_title")
    xcol1, xcol2 = st.columns(2)
    with xcol1:
        st.text_input("X min", key="x_min")
    with xcol2:
        st.text_input("X max", key="x_max")
    ycol1, ycol2 = st.columns(2)
    with ycol1:
        st.text_input("Y min", key="y_min")
    with ycol2:
        st.text_input("Y max", key="y_max")

    st.markdown("**Peak Annotations**")
    st.caption("Top 5 peaks are found inside the current X limits when limits are set. Each trace keeps its own peak toggles.")
    selected_paths = get_selected_paths(all_paths)
    if not selected_paths:
        st.info("Select one or more traces in the Browser tab to manage peak labels.")
    else:
        for path in selected_paths:
            key = f"peaks_{path.name}"
            st.session_state.setdefault(key, peak_ranks_for_trace(path))
            chosen = st.multiselect(
                clean_label(path),
                options=[1, 2, 3, 4, 5],
                default=st.session_state[key],
                key=key,
                format_func=lambda rank: f"Peak {rank}",
            )
            st.session_state["peak_visibility"][path.name] = chosen

with tab_appearance:
    size_col1, size_col2, size_col3 = st.columns(3)
    with size_col1:
        st.number_input("Figure width", min_value=2.0, max_value=20.0, step=0.5, key="figure_width")
    with size_col2:
        st.number_input("Figure height", min_value=2.0, max_value=20.0, step=0.5, key="figure_height")
    with size_col3:
        st.number_input("Line width", min_value=0.4, max_value=10.0, step=0.2, key="line_width")

    style_col1, style_col2, style_col3 = st.columns(3)
    with style_col1:
        st.selectbox("Style", options=["paper", "talk"], key="plot_style")
    with style_col2:
        st.checkbox("Show legend", key="show_legend")
    with style_col3:
        st.checkbox("Transparent background", key="transparent_background")

    st.markdown("**Trace Colors**")
    selected_paths = get_selected_paths(all_paths)
    if not selected_paths:
        st.info("Select one or more traces in the Browser tab to customize colors.")
    else:
        for index, path in enumerate(selected_paths):
            key = f"color_{path.name}"
            st.session_state.setdefault(key, color_name_for_trace(path, index))
            palette_col, swatch_col = st.columns([1.9, 0.7], gap="small")
            with palette_col:
                selected_color = st.selectbox(
                    trace_detail_label(path),
                    options=list(STANDARD_COLORS.keys()),
                    index=list(STANDARD_COLORS.keys()).index(st.session_state[key]),
                    key=key,
                    format_func=lambda name: f"{name}  {STANDARD_COLORS[name]}",
                )
            with swatch_col:
                swatch_hex = STANDARD_COLORS[selected_color]
                st.markdown(
                    (
                        "<div style='padding-top:2rem'>"
                        f"<div style='height:2.6rem;border-radius:0.6rem;border:1px solid #d0d7de;background:{swatch_hex};'></div>"
                        f"<div style='font-size:0.8rem;color:#666;padding-top:0.35rem'>{swatch_hex}</div>"
                        "</div>"
                    ),
                    unsafe_allow_html=True,
                )
            st.session_state["trace_colors"][path.name] = selected_color

selected_paths = get_selected_paths(all_paths)

preview_tab_matplotlib, preview_tab_plotly = st.tabs(["Matplotlib Preview", "Plotly Preview"])
with preview_tab_matplotlib:
    if not selected_paths:
        st.info("Select traces to preview.")
    else:
        try:
            figure, _processed, _xlim, _ylim = render_current_figure(selected_paths)
            st.pyplot(figure, clear_figure=True, use_container_width=False)
        except Exception as exc:
            st.error(f"Could not render preview: {exc}")

with preview_tab_plotly:
    if not selected_paths:
        st.info("Select traces to preview.")
    else:
        try:
            st.plotly_chart(render_plotly_preview(selected_paths), use_container_width=True)
        except Exception as exc:
            st.error(f"Could not render Plotly preview: {exc}")

with tab_export:
    st.text_input("Output stem", key="output_stem", help="Base name for downloaded exports.")
    if not selected_paths:
        st.info("Select traces before exporting.")
    else:
        try:
            svg_png_session = make_svg_png_session_bundle(selected_paths)
            plotly_html = make_plotly_html(selected_paths)
            xmgrace_bytes = make_xmgrace(selected_paths)

            stem = normalize_output_stem(st.session_state["output_stem"])
            st.download_button(
                "Download SVG",
                data=svg_png_session[".svg"],
                file_name=f"{stem}.svg",
                mime="image/svg+xml",
            )
            st.download_button(
                "Download PNG",
                data=svg_png_session[".png"],
                file_name=f"{stem}.png",
                mime="image/png",
            )
            st.download_button(
                "Download Session JSON",
                data=svg_png_session[".session.json"],
                file_name=f"{stem}.session.json",
                mime="application/json",
            )
            st.download_button(
                "Download Plotly HTML",
                data=plotly_html,
                file_name=f"{stem}.html",
                mime="text/html",
            )
            st.download_button(
                "Download XMGrace AGR",
                data=xmgrace_bytes,
                file_name=f"{stem}.agr",
                mime="text/plain",
            )

            bundle_bytes = BytesIO()
            with zipfile.ZipFile(bundle_bytes, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
                bundle.writestr(f"{stem}.svg", svg_png_session[".svg"])
                bundle.writestr(f"{stem}.png", svg_png_session[".png"])
                bundle.writestr(f"{stem}.session.json", svg_png_session[".session.json"])
                bundle.writestr(f"{stem}.html", plotly_html)
                bundle.writestr(f"{stem}.agr", xmgrace_bytes)
            st.download_button(
                "Download Export Bundle",
                data=bundle_bytes.getvalue(),
                file_name=f"{stem}_exports.zip",
                mime="application/zip",
            )
            st.success("Exports are ready.")
        except Exception as exc:
            st.error(f"Could not prepare exports: {exc}")

st.caption(st.session_state["status_message"])
