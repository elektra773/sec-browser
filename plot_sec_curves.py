import argparse
from datetime import datetime
import re
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import plotly.graph_objects as go

DEFAULT_FIGSIZE = (6.0, 4.0)
DEFAULT_LINEWIDTH = 3.0
PREVIEW_DPI = 220
EXPORT_RASTER_DPI = 1600


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot SEC chromatograms from the thesis archive."
    )
    parser.add_argument("inputs", nargs="+", help="Input .asc or .xls files.")
    parser.add_argument(
        "--output",
        required=True,
        help="Output figure path, e.g. figures/sec_overlay.svg",
    )
    parser.add_argument("--title", default="", help="Optional plot title.")
    parser.add_argument(
        "--labels",
        nargs="*",
        default=None,
        help="Legend labels matching the input order.",
    )
    parser.add_argument(
        "--normalize",
        action="store_true",
        help="Normalize each trace to its own maximum.",
    )
    parser.add_argument(
        "--normalize-anchor",
        choices=("zero", "left-limit"),
        default="left-limit",
        help="Anchor traces to x=0 or the left x-limit before normalization. Default: left-limit",
    )
    parser.add_argument(
        "--baseline-subtract",
        action="store_true",
        help="Subtract the median of the first 30 points from each trace.",
    )
    parser.add_argument(
        "--smooth-window",
        type=int,
        default=1,
        help="Centered rolling-average window. Default: 1 (off).",
    )
    parser.add_argument(
        "--xlim",
        nargs=2,
        type=float,
        metavar=("MIN", "MAX"),
        default=None,
        help="Optional x-axis limits.",
    )
    parser.add_argument(
        "--ylim",
        nargs=2,
        type=float,
        metavar=("MIN", "MAX"),
        default=None,
        help="Optional y-axis limits.",
    )
    parser.add_argument(
        "--figsize",
        nargs=2,
        type=float,
        default=DEFAULT_FIGSIZE,
        metavar=("WIDTH", "HEIGHT"),
        help="Figure size in inches. Default: 6 4",
    )
    parser.add_argument(
        "--format",
        choices=("paper", "talk"),
        default="paper",
        help="Style preset. Default: paper",
    )
    parser.add_argument(
        "--transparent",
        action="store_true",
        help="Save with a transparent background for Illustrator compositing.",
    )
    parser.add_argument(
        "--xmgrace-output",
        default="",
        help="Optional XMGrace .agr output path.",
    )
    parser.add_argument(
        "--plotly-output",
        default="",
        help="Optional Plotly HTML output path.",
    )
    return parser.parse_args()


def apply_style(style: str) -> None:
    params = {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "Liberation Sans", "DejaVu Sans"],
        "font.size": 11 if style == "paper" else 13,
        "axes.linewidth": 1.1 if style == "paper" else 1.4,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "xtick.direction": "in",
        "ytick.direction": "in",
        "legend.frameon": False,
        "figure.dpi": PREVIEW_DPI,
        "savefig.dpi": EXPORT_RASTER_DPI,
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    }
    plt.rcParams.update(params)


def style_sizes(style: str) -> dict[str, int]:
    if style == "talk":
        return {
            "title": 18,
            "axis": 16,
            "tick": 14,
            "legend": 13,
        }
    return {
        "title": 16,
        "axis": 14,
        "tick": 12,
        "legend": 11,
    }


def apply_sec_layout(fig, has_title: bool) -> None:
    fig.subplots_adjust(
        left=0.16,
        right=0.98,
        bottom=0.21,
        top=0.84 if has_title else 0.94,
    )


def read_sec_file(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".asc":
        df = pd.read_csv(path, sep="\t", header=None, skiprows=3, names=["ml", "mAU"])
    elif suffix == ".xls":
        df = pd.read_excel(path, sheet_name=0, header=None, skiprows=3, names=["ml", "mAU"])
    else:
        raise ValueError(f"Unsupported file type: {path.name}")

    df["ml"] = pd.to_numeric(df["ml"], errors="coerce")
    df["mAU"] = pd.to_numeric(df["mAU"], errors="coerce")
    df = df.dropna().sort_values("ml").reset_index(drop=True)
    return df


def clean_label(path: Path) -> str:
    label = path.stem
    label = label.replace("q", " ")
    label = re.sub(r"^S\d+\s+\d{5}\s+", "", label, flags=re.IGNORECASE)
    label = re.sub(r"\bRun\d+\b", "", label, flags=re.IGNORECASE)
    label = re.sub(r"\b\d{6,8}\b", "", label)
    label = re.sub(r"\bmicroplate\d*\b", "", label, flags=re.IGNORECASE)
    label = re.sub(r"\bEM\b", "", label)
    label = re.sub(r"\s+", " ", label).strip()
    return label


def extract_run_date(path: Path) -> str:
    match = re.search(r"(\d{6}|\d{8})(?!.*\d)", path.stem)
    if not match:
        return ""

    token = match.group(1)
    formats = ["%m%d%y"] if len(token) == 6 else ["%m%d%Y", "%m%d%y"]
    for fmt in formats:
        try:
            return datetime.strptime(token, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return token


def extract_column_name(path: Path) -> str:
    match = re.match(r"^(S\d+)q(\d{2})(\d{3})", path.stem, flags=re.IGNORECASE)
    if not match:
        return ""
    resin, diameter, length = match.groups()
    return f"{resin.upper()} {diameter}/{length}"


def extract_run_label(path: Path) -> str:
    match = re.search(r"run(\d+)", path.stem, flags=re.IGNORECASE)
    if match:
        return f"Run{match.group(1)}"
    return "Unspecified"


def process_trace(
    df: pd.DataFrame,
    normalize: bool,
    baseline_subtract: bool,
    smooth_window: int,
    normalize_window: tuple[float, float] | None = None,
    normalize_anchor: str = "left-limit",
) -> pd.DataFrame:
    trace = df.copy()
    if baseline_subtract:
        trace["mAU"] = trace["mAU"] - trace["mAU"].head(30).median()

    if smooth_window > 1:
        trace["mAU"] = (
            trace["mAU"]
            .rolling(window=smooth_window, center=True, min_periods=1)
            .mean()
        )

    if normalize or normalize_window is not None:
        anchor_x = 0.0
        if normalize_anchor == "left-limit" and normalize_window is not None:
            anchor_x = normalize_window[0]
        anchor_idx = (trace["ml"] - anchor_x).abs().idxmin()
        anchor_value = trace.loc[anchor_idx, "mAU"]
        if pd.notna(anchor_value):
            trace["mAU"] = trace["mAU"] - anchor_value

    if normalize:
        window_trace = trace
        if normalize_window is not None:
            x_min, x_max = normalize_window
            window_trace = trace.loc[trace["ml"].between(x_min, x_max)]
            if window_trace.empty:
                window_trace = trace
        peak = window_trace["mAU"].max()
        if pd.notna(peak) and peak != 0:
            trace["mAU"] = trace["mAU"] / peak

    return trace


def hex_to_rgb(color_hex: str) -> tuple[int, int, int]:
    color_hex = color_hex.lstrip("#")
    return tuple(int(color_hex[i : i + 2], 16) for i in (0, 2, 4))


def find_top_peaks(
    trace: pd.DataFrame,
    peak_window: tuple[float, float] | None = None,
    top_n: int = 5,
) -> list[dict]:
    window_trace = trace
    if peak_window is not None:
        x_min, x_max = peak_window
        window_trace = trace.loc[trace["ml"].between(x_min, x_max)].reset_index(drop=True)
        if window_trace.empty:
            window_trace = trace.reset_index(drop=True)
    else:
        window_trace = trace.reset_index(drop=True)

    if len(window_trace) < 3:
        return []

    y_values = window_trace["mAU"]
    local_maxima = window_trace.loc[
        (y_values > y_values.shift(1)) & (y_values >= y_values.shift(-1))
    ].copy()
    if local_maxima.empty:
        local_maxima = window_trace.nlargest(top_n, "mAU").copy()

    positive_peaks = local_maxima.loc[local_maxima["mAU"] > 0].copy()
    if not positive_peaks.empty:
        local_maxima = positive_peaks

    ranked = local_maxima.nlargest(top_n, "mAU").reset_index(drop=True)
    peaks = []
    for rank, row in enumerate(ranked.itertuples(index=False), start=1):
        peaks.append(
            {
                "rank": rank,
                "ml": float(row.ml),
                "mAU": float(row.mAU),
            }
        )
    return peaks


def export_xmgrace(
    traces: list[dict],
    output: Path,
    title: str,
    x_label: str,
    y_label: str,
    show_legend: bool,
    xlim: tuple[float, float] | None = None,
    ylim: tuple[float, float] | None = None,
) -> None:
    lines = [
        "# Grace project file",
        "@version 50123",
        '@page size 792, 612',
        '@with g0',
        f'@    title "{title}"' if title else '@    title ""',
        f'@    xaxis label "{x_label}"',
        f'@    yaxis label "{y_label}"',
        f'@    legend {"on" if show_legend else "off"}',
    ]
    if xlim:
        lines.append(f"@    world xmin {xlim[0]}")
        lines.append(f"@    world xmax {xlim[1]}")
    if ylim:
        lines.append(f"@    world ymin {ylim[0]}")
        lines.append(f"@    world ymax {ylim[1]}")

    for idx, trace in enumerate(traces):
        color_id = 100 + idx
        red, green, blue = hex_to_rgb(trace["color"])
        lines.append(f'@map color {color_id} to ({red}, {green}, {blue}), "{trace["label"]}"')
        lines.extend(
            [
                f"@    s{idx} on",
                f'@    s{idx} legend "{trace["label"]}"',
                f"@    s{idx} line color {color_id}",
                f"@    s{idx} line linewidth {trace['line_width']}",
                f"@    s{idx} symbol 0",
                f"@target G0.S{idx}",
                "@type xy",
            ]
        )
        for x_value, y_value in zip(trace["data"]["ml"], trace["data"]["mAU"]):
            lines.append(f"{x_value} {y_value}")
        lines.append("&")

    output.write_text("\n".join(lines) + "\n")


def export_plotly_html(
    traces: list[dict],
    output: Path,
    title: str,
    x_label: str,
    y_label: str,
    show_legend: bool,
    xlim: tuple[float, float] | None = None,
    ylim: tuple[float, float] | None = None,
) -> None:
    figure = go.Figure()
    for trace in traces:
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
        title=title,
        xaxis_title=x_label,
        yaxis_title=y_label,
        showlegend=show_legend,
        template="simple_white",
        font={"family": "Arial, Helvetica, sans-serif", "size": 14},
    )
    figure.update_xaxes(showline=True, linewidth=1, linecolor="black", ticks="inside")
    figure.update_yaxes(showline=True, linewidth=1, linecolor="black", ticks="inside")
    if xlim:
        figure.update_xaxes(range=list(xlim))
    if ylim:
        figure.update_yaxes(range=list(ylim))
    figure.write_html(output, include_plotlyjs=True, full_html=True)


def render_sec_plot(
    fig,
    ax,
    traces: list[dict],
    title: str,
    normalized: bool,
    xlim: tuple[float, float] | None,
    ylim: tuple[float, float] | None,
    show_legend: bool,
    style: str,
    visible_peak_ranks: set[int] | dict[str, set[int]] | None = None,
) -> None:
    apply_style(style)
    sizes = style_sizes(style)
    ax.clear()

    if not traces:
        ax.text(
            0.5,
            0.5,
            "Select traces to preview",
            ha="center",
            va="center",
            transform=ax.transAxes,
        )
        ax.set_xticks([])
        ax.set_yticks([])
        apply_sec_layout(fig, has_title=False)
        return

    for trace in traces:
        ax.plot(
            trace["data"]["ml"],
            trace["data"]["mAU"],
            linewidth=trace["line_width"],
            color=trace["color"],
            label=trace["label"],
            antialiased=True,
            solid_capstyle="round",
            solid_joinstyle="round",
        )

    ax.set_xlabel("Elution Volume (mL)", fontsize=sizes["axis"], labelpad=8)
    ax.set_ylabel(
        "Normalized absorbance" if normalized else "Absorbance (mAU)",
        fontsize=sizes["axis"],
        labelpad=8,
    )
    ax.tick_params(direction="in", which="both", top=False, right=False, labelsize=sizes["tick"])
    if title:
        ax.set_title(title, pad=8, fontsize=sizes["title"])
    if xlim:
        ax.set_xlim(xlim)
    if ylim:
        ax.set_ylim(ylim)

    if visible_peak_ranks:
        y_min = ax.get_ylim()[0]
        for trace in traces:
            trace_peak_ranks = visible_peak_ranks
            if isinstance(visible_peak_ranks, dict):
                trace_peak_ranks = visible_peak_ranks.get(trace.get("trace_id", ""), set())
            for peak in trace.get("peaks", []):
                if peak["rank"] not in trace_peak_ranks:
                    continue
                ax.vlines(
                    peak["ml"],
                    y_min,
                    peak["mAU"],
                    color=trace["color"],
                    linewidth=max(0.8, trace["line_width"] * 0.45),
                    alpha=0.28,
                    linestyles="--",
                )
                ax.annotate(
                    f"{peak['ml']:.2f}",
                    xy=(peak["ml"], peak["mAU"]),
                    xytext=(0, 8),
                    textcoords="offset points",
                    rotation=0,
                    ha="center",
                    va="bottom",
                    fontsize=max(8, sizes["tick"] - 3),
                    color=trace["color"],
                )

    if show_legend and len(traces) > 1:
        ax.legend(fontsize=sizes["legend"], handlelength=2.2)
    apply_sec_layout(fig, has_title=bool(title))


def main() -> None:
    args = parse_args()
    paths = [Path(item).expanduser().resolve() for item in args.inputs]
    if args.labels and len(args.labels) != len(paths):
        raise ValueError("--labels must match the number of input files")

    apply_style(args.format)
    fig, ax = plt.subplots(figsize=args.figsize, dpi=PREVIEW_DPI)
    colors = plt.get_cmap("tab10").colors
    processed_traces = []

    for idx, path in enumerate(paths):
        trace = read_sec_file(path)
        trace = process_trace(
            trace,
            normalize=args.normalize,
            baseline_subtract=args.baseline_subtract,
            smooth_window=args.smooth_window,
            normalize_window=tuple(args.xlim) if args.xlim else None,
            normalize_anchor=args.normalize_anchor,
        )
        label = args.labels[idx] if args.labels else clean_label(path)
        color = colors[idx % len(colors)]
        processed_traces.append(
            {
                "label": label,
                "color": "#{:02x}{:02x}{:02x}".format(
                    int(color[0] * 255), int(color[1] * 255), int(color[2] * 255)
                ),
                "line_width": DEFAULT_LINEWIDTH,
                "data": trace,
            }
        )

    render_sec_plot(
        fig=fig,
        ax=ax,
        traces=processed_traces,
        title=args.title,
        normalized=args.normalize,
        xlim=tuple(args.xlim) if args.xlim else None,
        ylim=tuple(args.ylim) if args.ylim else None,
        show_legend=len(paths) > 1,
        style=args.format,
    )
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    save_kwargs = {
        "transparent": args.transparent,
    }
    if output.suffix.lower() not in {".svg", ".pdf", ".eps"}:
        save_kwargs["dpi"] = EXPORT_RASTER_DPI
    fig.savefig(output, **save_kwargs)
    if args.xmgrace_output:
        export_xmgrace(
            traces=processed_traces,
            output=Path(args.xmgrace_output).expanduser().resolve(),
            title=args.title,
            x_label="Elution Volume (mL)",
            y_label="Normalized absorbance" if args.normalize else "Absorbance (mAU)",
            show_legend=len(paths) > 1,
            xlim=tuple(args.xlim) if args.xlim else None,
            ylim=tuple(args.ylim) if args.ylim else None,
        )
    if args.plotly_output:
        export_plotly_html(
            traces=processed_traces,
            output=Path(args.plotly_output).expanduser().resolve(),
            title=args.title,
            x_label="Elution Volume (mL)",
            y_label="Normalized absorbance" if args.normalize else "Absorbance (mAU)",
            show_legend=len(paths) > 1,
            xlim=tuple(args.xlim) if args.xlim else None,
            ylim=tuple(args.ylim) if args.ylim else None,
        )
    plt.close(fig)
    print(f"Saved {output}")


if __name__ == "__main__":
    main()
