import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import sys
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser

from matplotlib.figure import Figure

try:
    from plot_sec_curves import (
        DEFAULT_FIGSIZE,
        DEFAULT_LINEWIDTH,
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
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from plot_sec_curves import (
        DEFAULT_FIGSIZE,
        DEFAULT_LINEWIDTH,
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

FILTER_TOKEN_STOPWORDS = {
    "run",
    "rerun",
    "sample",
    "trace",
    "standard",
}

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

@dataclass
class TraceEntry:
    path: Path
    label: str
    suffix: str
    date: str
    column: str


class SecBrowserApp:
    def __init__(self, root: tk.Tk, data_dir: Path) -> None:
        self.root = root
        self.data_dir = data_dir
        self.root.title("SEC Browser")
        self.entries: list[TraceEntry] = []
        self.trace_cache: dict[Path, object] = {}
        self.filtered_entries: list[TraceEntry] = []

        self.search_var = tk.StringVar()
        self.display_mode_var = tk.StringVar(value="normalized")
        self.baseline_var = tk.BooleanVar(value=True)
        self.smooth_var = tk.IntVar(value=5)
        self.style_var = tk.StringVar(value="paper")
        self.format_filter_var = tk.StringVar(value="asc")
        self.normalize_anchor_var = tk.StringVar(value="left-limit")
        self.palette_color_var = tk.StringVar(value="Navy")
        self.linewidth_var = tk.DoubleVar(value=DEFAULT_LINEWIDTH)
        self.figure_width_var = tk.DoubleVar(value=DEFAULT_FIGSIZE[0])
        self.figure_height_var = tk.DoubleVar(value=DEFAULT_FIGSIZE[1])
        self.show_legend_var = tk.BooleanVar(value=True)
        self.title_var = tk.StringVar()
        self.output_var = tk.StringVar(value=str(self.data_dir / "figures" / "selected_overlay"))
        self.xmin_var = tk.StringVar()
        self.xmax_var = tk.StringVar()
        self.ymin_var = tk.StringVar()
        self.ymax_var = tk.StringVar()
        self.transparent_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Scanning files...")
        self.quick_filter_vars: dict[str, tk.BooleanVar] = {}
        self.peak_rank_vars_by_trace: dict[str, dict[int, tk.BooleanVar]] = {}
        self.loaded_peak_visibility: dict[str, set[int]] = {}
        self.trace_colors: dict[Path, str] = {}
        self.trace_target_var = tk.StringVar()
        self.trace_target_lookup: dict[str, Path] = {}
        self.preview_resize_after: str | None = None
        self.preview_image: tk.PhotoImage | None = None
        self.preview_item: int | None = None
        self.preview_cache_path = Path(tempfile.gettempdir()) / "sec_browser_preview.png"

        self._build_ui()
        self.refresh_entries()

    def _build_ui(self) -> None:
        self.root.geometry("1720x1080")
        self.root.minsize(1100, 720)
        self.root.resizable(True, True)

        main = tk.PanedWindow(
            self.root,
            orient=tk.HORIZONTAL,
            sashwidth=12,
            sashrelief=tk.RAISED,
            showhandle=True,
            opaqueresize=True,
            bd=0,
        )
        main.pack(fill=tk.BOTH, expand=True)

        left_pane = tk.PanedWindow(
            main,
            orient=tk.VERTICAL,
            sashwidth=12,
            sashrelief=tk.RAISED,
            showhandle=True,
            opaqueresize=True,
            bd=0,
        )
        right_pane = tk.PanedWindow(
            main,
            orient=tk.VERTICAL,
            sashwidth=12,
            sashrelief=tk.RAISED,
            showhandle=True,
            opaqueresize=True,
            bd=0,
        )
        main.add(left_pane, minsize=280, stretch="always")
        main.add(right_pane, minsize=560, stretch="always")
        self.root.after(50, lambda: main.sashpos(0, 380))

        left_top = ttk.Frame(left_pane, padding=10)
        left_bottom = ttk.Frame(left_pane, padding=(10, 0, 10, 10))
        left_pane.add(left_top, minsize=180)
        left_pane.add(left_bottom, minsize=260, stretch="always")
        self.root.after(50, lambda: left_pane.sashpos(0, 245))

        right_top = ttk.Frame(right_pane, padding=10)
        right_bottom = ttk.Frame(right_pane, padding=(10, 0, 10, 10))
        right_pane.add(right_top, minsize=180)
        right_pane.add(right_bottom, minsize=320, stretch="always")
        self.root.after(50, lambda: right_pane.sashpos(0, 285))

        ttk.Label(left_top, text="Trace Browser").pack(anchor="w")
        ttk.Label(left_top, text="Filter files, then select the traces you want to overlay.").pack(anchor="w", pady=(0, 10))
        ttk.Label(left_top, text="Search").pack(anchor="w")
        search_entry = ttk.Entry(left_top, textvariable=self.search_var)
        search_entry.pack(fill=tk.X, pady=(0, 8))
        search_entry.bind("<KeyRelease>", lambda _event: self.apply_filter())

        button_row = ttk.Frame(left_top)
        button_row.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(button_row, text="Refresh", command=self.refresh_entries).grid(row=0, column=0, sticky="ew")
        ttk.Button(button_row, text="Select Visible", command=self.select_visible).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(button_row, text="Clear", command=self.clear_selection).grid(row=0, column=2, sticky="ew")
        ttk.Button(button_row, text="Load Session", command=self.load_session).grid(row=0, column=3, sticky="ew", padx=(6, 0))
        for idx in range(4):
            button_row.columnconfigure(idx, weight=1)

        filter_row = ttk.Frame(left_top)
        filter_row.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(filter_row, text="Load").pack(side=tk.LEFT)
        format_menu = ttk.Combobox(
            filter_row,
            textvariable=self.format_filter_var,
            values=("asc", "xls", "both"),
            width=8,
            state="readonly",
        )
        format_menu.pack(side=tk.LEFT, padx=(6, 0))
        format_menu.bind("<<ComboboxSelected>>", lambda _event: self.apply_filter())

        self.quick_filter_frame = ttk.LabelFrame(left_top, text="Quick Filters", padding=8)
        self.quick_filter_frame.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(left_bottom, text="Samples").pack(anchor="w", pady=(0, 8))
        tree_holder = ttk.Frame(left_bottom)
        tree_holder.pack(fill=tk.BOTH, expand=True)
        self.tree = ttk.Treeview(
            tree_holder,
            columns=("label", "column", "date", "format"),
            show="headings",
            selectmode="extended",
            height=24,
        )
        self.tree.heading("label", text="Sample")
        self.tree.heading("column", text="Column")
        self.tree.heading("date", text="Date")
        self.tree.heading("format", text="Type")
        self.tree.column("label", width=250, anchor="w")
        self.tree.column("column", width=110, anchor="center")
        self.tree.column("date", width=90, anchor="center")
        self.tree.column("format", width=65, anchor="center")
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self.update_plot())

        scrollbar = ttk.Scrollbar(tree_holder, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        ttk.Label(right_top, text="Figure Controls").pack(anchor="w")
        ttk.Label(right_top, text="Use the tabs to keep setup, styling, and export controls out of the way of the preview.").pack(anchor="w", pady=(0, 10))

        notebook = ttk.Notebook(right_top)
        notebook.pack(fill=tk.BOTH, expand=True)

        plot_tab_shell = ttk.Frame(notebook)
        tab_appearance = ttk.Frame(notebook, padding=12)
        tab_export = ttk.Frame(notebook, padding=12)
        notebook.add(plot_tab_shell, text="Plot")
        notebook.add(tab_appearance, text="Appearance")
        notebook.add(tab_export, text="Export")

        plot_scrollbar = ttk.Scrollbar(plot_tab_shell, orient=tk.VERTICAL)
        plot_canvas = tk.Canvas(
            plot_tab_shell,
            highlightthickness=0,
            yscrollcommand=plot_scrollbar.set,
        )
        plot_scrollbar.configure(command=plot_canvas.yview)
        plot_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        plot_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        tab_plot = ttk.Frame(plot_canvas, padding=8)
        plot_window = plot_canvas.create_window((0, 0), window=tab_plot, anchor="nw")

        def sync_plot_tab_width(_event):
            plot_canvas.itemconfigure(plot_window, width=plot_canvas.winfo_width())

        def sync_plot_scrollregion(_event):
            plot_canvas.configure(scrollregion=plot_canvas.bbox("all"))

        plot_canvas.bind("<Configure>", sync_plot_tab_width)
        tab_plot.bind("<Configure>", sync_plot_scrollregion)

        controls = ttk.LabelFrame(tab_plot, text="Trace Processing", padding=8)
        controls.pack(fill=tk.X)

        ttk.Label(controls, text="Absorbance").grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(
            controls,
            text="Normalized",
            value="normalized",
            variable=self.display_mode_var,
            command=self.update_plot,
        ).grid(row=0, column=1, sticky="w")
        ttk.Radiobutton(
            controls,
            text="Actual",
            value="actual",
            variable=self.display_mode_var,
            command=self.update_plot,
        ).grid(row=0, column=2, sticky="w")
        ttk.Checkbutton(controls, text="Baseline subtract", variable=self.baseline_var, command=self.update_plot).grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Label(controls, text="Smooth").grid(row=1, column=1, sticky="w", pady=(6, 0))
        smooth_spin = ttk.Spinbox(controls, from_=1, to=101, textvariable=self.smooth_var, width=8, command=self.update_plot)
        smooth_spin.grid(row=1, column=2, sticky="w", pady=(6, 0))
        smooth_spin.bind("<KeyRelease>", lambda _event: self.update_plot())

        ttk.Label(controls, text="Anchor").grid(row=1, column=3, sticky="w", pady=(6, 0))
        anchor_menu = ttk.Combobox(
            controls,
            textvariable=self.normalize_anchor_var,
            values=("left-limit", "zero"),
            width=12,
            state="readonly",
        )
        anchor_menu.grid(row=1, column=4, sticky="w", pady=(6, 0))
        anchor_menu.bind("<<ComboboxSelected>>", lambda _event: self.update_plot())

        ttk.Label(controls, text="Title").grid(row=2, column=0, sticky="w", pady=(6, 0))
        title_entry = ttk.Entry(controls, textvariable=self.title_var, width=45)
        title_entry.grid(row=2, column=1, columnspan=4, sticky="ew", pady=(6, 0))
        title_entry.bind("<KeyRelease>", lambda _event: self.update_plot())

        ttk.Label(controls, text="X limits").grid(row=3, column=0, sticky="w", pady=(6, 0))
        xlim_frame = ttk.Frame(controls)
        xlim_frame.grid(row=3, column=1, sticky="w", pady=(6, 0))
        xmin_entry = ttk.Entry(xlim_frame, textvariable=self.xmin_var, width=8)
        xmax_entry = ttk.Entry(xlim_frame, textvariable=self.xmax_var, width=8)
        xmin_entry.pack(side=tk.LEFT)
        ttk.Label(xlim_frame, text="to").pack(side=tk.LEFT, padx=4)
        xmax_entry.pack(side=tk.LEFT)
        xmin_entry.bind("<KeyRelease>", lambda _event: self.update_plot())
        xmax_entry.bind("<KeyRelease>", lambda _event: self.update_plot())

        ttk.Label(controls, text="Y limits").grid(row=3, column=3, sticky="w", pady=(6, 0))
        ylim_frame = ttk.Frame(controls)
        ylim_frame.grid(row=3, column=4, sticky="w", pady=(6, 0))
        ymin_entry = ttk.Entry(ylim_frame, textvariable=self.ymin_var, width=8)
        ymax_entry = ttk.Entry(ylim_frame, textvariable=self.ymax_var, width=8)
        ymin_entry.pack(side=tk.LEFT)
        ttk.Label(ylim_frame, text="to").pack(side=tk.LEFT, padx=4)
        ymax_entry.pack(side=tk.LEFT)
        ymin_entry.bind("<KeyRelease>", lambda _event: self.update_plot())
        ymax_entry.bind("<KeyRelease>", lambda _event: self.update_plot())
        for column in range(5):
            controls.columnconfigure(column, weight=1)

        selection_actions = ttk.LabelFrame(tab_plot, text="Selection Actions", padding=8)
        selection_actions.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(selection_actions, text="Title From Selection", command=self.populate_title_from_selection).grid(row=0, column=0, sticky="ew")
        ttk.Button(selection_actions, text="Copy Labels", command=self.copy_labels).grid(row=0, column=1, sticky="ew", padx=8)
        selection_actions.columnconfigure(0, weight=1)
        selection_actions.columnconfigure(1, weight=1)

        peak_frame = ttk.LabelFrame(tab_plot, text="Peak Annotations", padding=8)
        peak_frame.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(
            peak_frame,
            text="Top peaks are found within the current X limits. If no X limits are set, the full trace is used. Each trace has its own peak toggles.",
            wraplength=620,
            justify="left",
        ).pack(anchor="w")
        self.peak_grid_frame = ttk.Frame(peak_frame)
        self.peak_grid_frame.pack(fill=tk.X, pady=(8, 0))

        appearance = ttk.LabelFrame(tab_appearance, text="Figure Look", padding=10)
        appearance.pack(fill=tk.X)

        ttk.Label(appearance, text="Figure size").grid(row=0, column=0, sticky="w")
        size_frame = ttk.Frame(appearance)
        size_frame.grid(row=0, column=1, sticky="w")
        width_spin = ttk.Spinbox(
            size_frame,
            from_=4.0,
            to=20.0,
            increment=0.1,
            textvariable=self.figure_width_var,
            width=8,
            command=self.update_plot,
        )
        height_spin = ttk.Spinbox(
            size_frame,
            from_=3.0,
            to=20.0,
            increment=0.1,
            textvariable=self.figure_height_var,
            width=8,
            command=self.update_plot,
        )
        width_spin.pack(side=tk.LEFT)
        ttk.Label(size_frame, text="x").pack(side=tk.LEFT, padx=4)
        height_spin.pack(side=tk.LEFT)
        width_spin.bind("<KeyRelease>", lambda _event: self.update_plot())
        height_spin.bind("<KeyRelease>", lambda _event: self.update_plot())

        ttk.Label(appearance, text="Line width").grid(row=0, column=2, sticky="w", padx=(14, 0))
        linewidth_spin = ttk.Spinbox(
            appearance,
            from_=0.4,
            to=4.0,
            increment=0.1,
            textvariable=self.linewidth_var,
            width=8,
            command=self.update_plot,
        )
        linewidth_spin.grid(row=0, column=3, sticky="w")
        linewidth_spin.bind("<KeyRelease>", lambda _event: self.update_plot())

        ttk.Label(appearance, text="Style").grid(row=1, column=0, sticky="w", pady=(10, 0))
        style_menu = ttk.Combobox(appearance, textvariable=self.style_var, values=("paper", "talk"), width=12, state="readonly")
        style_menu.grid(row=1, column=1, sticky="w", pady=(10, 0))
        style_menu.bind("<<ComboboxSelected>>", lambda _event: self.update_plot())

        ttk.Checkbutton(
            appearance,
            text="Show legend",
            variable=self.show_legend_var,
            command=self.update_plot,
        ).grid(row=1, column=2, sticky="w", pady=(10, 0), padx=(14, 0))
        ttk.Checkbutton(appearance, text="Transparent background", variable=self.transparent_var, command=self.update_plot).grid(row=1, column=3, sticky="w", pady=(10, 0))
        for column in range(4):
            appearance.columnconfigure(column, weight=1)

        color_frame = ttk.LabelFrame(tab_appearance, text="Trace Colors", padding=10)
        color_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(color_frame, text="Trace").grid(row=0, column=0, sticky="w")
        self.trace_target_menu = ttk.Combobox(
            color_frame,
            textvariable=self.trace_target_var,
            state="readonly",
        )
        self.trace_target_menu.grid(row=0, column=1, sticky="ew", padx=(6, 10))
        self.trace_target_menu.bind("<<ComboboxSelected>>", lambda _event: self.refresh_color_preview())
        ttk.Label(color_frame, text="Color").grid(row=0, column=2, sticky="w")
        self.palette_menu = ttk.Combobox(
            color_frame,
            textvariable=self.palette_color_var,
            values=tuple(STANDARD_COLORS.keys()),
            width=14,
            state="readonly",
        )
        self.palette_menu.grid(row=0, column=3, sticky="w", padx=(6, 10))
        self.palette_menu.bind("<<ComboboxSelected>>", lambda _event: self.refresh_color_preview())
        self.color_chip = tk.Label(
            color_frame,
            text="      ",
            bg=STANDARD_COLORS[self.palette_color_var.get()],
            relief="solid",
            bd=1,
        )
        self.color_chip.grid(row=0, column=4, sticky="w", padx=(0, 10))
        ttk.Button(color_frame, text="Apply To Trace", command=self.set_trace_color_from_dropdown).grid(
            row=0, column=5, sticky="ew"
        )
        ttk.Button(color_frame, text="Apply To Selected", command=self.set_selected_trace_color).grid(
            row=1, column=3, columnspan=2, sticky="ew", pady=(10, 0)
        )
        ttk.Button(color_frame, text="Reset Colors", command=self.reset_trace_colors).grid(
            row=1, column=5, sticky="ew", pady=(10, 0)
        )
        color_frame.columnconfigure(1, weight=1)

        export_frame = ttk.LabelFrame(tab_export, text="Export", padding=10)
        export_frame.pack(fill=tk.X)
        ttk.Label(export_frame, text="Output base").grid(row=0, column=0, sticky="w")
        output_entry = ttk.Entry(export_frame, textvariable=self.output_var)
        output_entry.grid(row=0, column=1, columnspan=3, sticky="ew")
        ttk.Button(export_frame, text="Browse", command=self.choose_output).grid(row=0, column=4, sticky="ew", padx=(8, 0))

        ttk.Button(export_frame, text="Export SVG + PNG", command=self.save_figure).grid(row=1, column=0, columnspan=2, pady=(12, 0), sticky="ew")
        ttk.Button(export_frame, text="Export XMGrace", command=self.save_xmgrace).grid(row=1, column=2, pady=(12, 0), sticky="ew", padx=8)
        ttk.Button(export_frame, text="Export Plotly HTML", command=self.save_plotly_html).grid(row=1, column=3, columnspan=2, pady=(12, 0), sticky="ew")
        ttk.Button(export_frame, text="Open Plotly Preview", command=self.open_plotly_preview).grid(row=2, column=0, columnspan=5, pady=(10, 0), sticky="ew")
        for column in range(5):
            export_frame.columnconfigure(column, weight=1)

        self.figure_frame = ttk.LabelFrame(right_bottom, text="Overlay Preview", padding=8)
        self.figure_frame.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        self.figure_frame.bind("<Configure>", self.on_preview_resized)
        self.preview_canvas = tk.Canvas(
            self.figure_frame,
            background="#f3f3f3",
            highlightthickness=0,
        )
        self.preview_canvas.pack(fill=tk.BOTH, expand=True)

        status_bar = ttk.Label(self.root, textvariable=self.status_var, anchor="w", padding=(10, 4))
        status_bar.pack(fill=tk.X)

    def scan_entries(self) -> list[TraceEntry]:
        entries = []
        for path in sorted(self.data_dir.iterdir()):
            if path.suffix.lower() not in {".asc", ".xls"}:
                continue
            entries.append(
                TraceEntry(
                    path=path,
                    label=clean_label(path),
                    suffix=path.suffix.lower().lstrip("."),
                    date=extract_run_date(path),
                    column=extract_column_name(path),
                )
            )
        return entries

    def label_tokens(self, entry: TraceEntry) -> set[str]:
        tokens = set()
        for raw_token in entry.label.lower().replace("/", " ").split():
            token = "".join(ch for ch in raw_token if ch.isalnum())
            if len(token) < 2 or token.isdigit() or token in FILTER_TOKEN_STOPWORDS:
                continue
            tokens.add(token)
        return tokens

    def rebuild_quick_filters(self) -> None:
        previous_state = {
            name: var.get() for name, var in self.quick_filter_vars.items()
        }
        self.quick_filter_vars = {}
        for child in self.quick_filter_frame.winfo_children():
            child.destroy()

        token_counts = Counter()
        for entry in self.entries:
            token_counts.update(self.label_tokens(entry))

        visible_tokens = [
            token for token, count in token_counts.most_common(12) if count >= 2
        ]
        if not visible_tokens:
            ttk.Label(
                self.quick_filter_frame,
                text="No shared keywords found in this dataset.",
            ).grid(row=0, column=0, sticky="w")
            return

        for idx, token in enumerate(visible_tokens):
            var = tk.BooleanVar(value=previous_state.get(token, False))
            self.quick_filter_vars[token] = var
            ttk.Checkbutton(
                self.quick_filter_frame,
                text=token,
                variable=var,
                command=self.apply_filter,
            ).grid(row=idx // 3, column=idx % 3, sticky="w", padx=(0, 10), pady=2)
        ttk.Button(
            self.quick_filter_frame,
            text="Clear Filters",
            command=self.clear_quick_filters,
        ).grid(row=(len(visible_tokens) + 2) // 3, column=0, sticky="w", pady=(6, 0))

    def refresh_entries(self) -> None:
        self.entries = self.scan_entries()
        self.rebuild_quick_filters()
        self.apply_filter()
        self.status_var.set(f"Loaded {len(self.entries)} SEC files from {self.data_dir}")

    def apply_filter(self) -> None:
        query = self.search_var.get().strip().lower()
        current_selection = set(self.tree.selection())
        self.tree.delete(*self.tree.get_children())
        if query:
            self.filtered_entries = [
                entry
                for entry in self.entries
                if query in entry.label.lower() or query in entry.path.name.lower()
            ]
        else:
            self.filtered_entries = list(self.entries)

        selected_format = self.format_filter_var.get()
        if selected_format != "both":
            self.filtered_entries = [
                entry for entry in self.filtered_entries if entry.suffix == selected_format
            ]

        active_filters = [
            name for name, var in self.quick_filter_vars.items() if var.get()
        ]
        if active_filters:
            self.filtered_entries = [
                entry for entry in self.filtered_entries if self.entry_matches_filters(entry, active_filters)
            ]

        for entry in self.filtered_entries:
            item_id = str(entry.path)
            self.tree.insert(
                "",
                tk.END,
                iid=item_id,
                values=(entry.label, entry.column, entry.date, entry.suffix),
            )
            if item_id in current_selection:
                self.tree.selection_add(item_id)

        self.update_plot()

    def entry_matches_filters(self, entry: TraceEntry, active_filters: list[str]) -> bool:
        entry_tokens = self.label_tokens(entry)
        return any(filter_name in entry_tokens for filter_name in active_filters)

    def clear_quick_filters(self) -> None:
        for var in self.quick_filter_vars.values():
            var.set(False)
        self.apply_filter()

    def select_visible(self) -> None:
        self.tree.selection_set(self.tree.get_children())
        self.update_plot()

    def clear_selection(self) -> None:
        self.tree.selection_remove(self.tree.selection())
        self.update_plot()

    def get_selected_entries(self) -> list[TraceEntry]:
        return [
            entry
            for entry in self.filtered_entries
            if str(entry.path) in self.tree.selection()
        ]

    def load_trace(self, path: Path):
        if path not in self.trace_cache:
            self.trace_cache[path] = read_sec_file(path)
        return self.trace_cache[path]

    def parse_limits(self, lower_var: tk.StringVar, upper_var: tk.StringVar):
        lower = lower_var.get().strip()
        upper = upper_var.get().strip()
        if not lower and not upper:
            return None
        try:
            return float(lower), float(upper)
        except ValueError:
            return None

    def build_session_state(self) -> dict:
        selected = self.get_selected_entries()
        xlim = self.parse_limits(self.xmin_var, self.xmax_var)
        ylim = self.parse_limits(self.ymin_var, self.ymax_var)
        return {
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "output_base": self.output_var.get(),
            "selected_traces": [str(entry.path) for entry in selected],
            "trace_labels": {str(entry.path): entry.label for entry in selected},
            "trace_colors": {str(path): color for path, color in self.trace_colors.items()},
            "display_mode": self.display_mode_var.get(),
            "normalize_anchor": self.normalize_anchor_var.get(),
            "baseline_subtract": self.baseline_var.get(),
            "smooth_window": int(self.smooth_var.get()),
            "style": self.style_var.get(),
            "palette_color": self.palette_color_var.get(),
            "line_width": float(self.linewidth_var.get()),
            "figure_width": float(self.figure_width_var.get()),
            "figure_height": float(self.figure_height_var.get()),
            "show_legend": self.show_legend_var.get(),
            "title": self.title_var.get(),
            "xlim": list(xlim) if xlim else None,
            "ylim": list(ylim) if ylim else None,
            "transparent_background": self.transparent_var.get(),
            "load_format": self.format_filter_var.get(),
            "active_filters": [
                name for name, var in self.quick_filter_vars.items() if var.get()
            ],
            "peak_visibility": {
                trace_id: sorted(rank for rank, var in rank_vars.items() if var.get())
                for trace_id, rank_vars in self.peak_rank_vars_by_trace.items()
                if any(var.get() for var in rank_vars.values())
            },
        }

    def set_range_vars(
        self,
        lower_var: tk.StringVar,
        upper_var: tk.StringVar,
        values: list[float] | tuple[float, float] | None,
    ) -> None:
        if values is None:
            lower_var.set("")
            upper_var.set("")
            return
        lower_var.set(str(values[0]))
        upper_var.set(str(values[1]))

    def load_session(self) -> None:
        session_path = filedialog.askopenfilename(
            title="Load SEC session",
            initialdir=str(self.data_dir / "figures"),
            filetypes=[
                ("JSON files", "*.json"),
            ],
        )
        if not session_path:
            return

        if not session_path.lower().endswith(".json"):
            messagebox.showerror("Load failed", "Please choose a JSON session file.")
            return

        try:
            state = json.loads(Path(session_path).read_text())
        except (OSError, json.JSONDecodeError) as exc:
            messagebox.showerror("Load failed", f"Could not read session file:\n{exc}")
            return

        try:
            self.output_var.set(state.get("output_base", self.output_var.get()))
            self.display_mode_var.set(state.get("display_mode", self.display_mode_var.get()))
            self.normalize_anchor_var.set(state.get("normalize_anchor", self.normalize_anchor_var.get()))
            self.baseline_var.set(state.get("baseline_subtract", self.baseline_var.get()))
            self.smooth_var.set(int(state.get("smooth_window", self.smooth_var.get())))
            self.style_var.set(state.get("style", self.style_var.get()))
            self.palette_color_var.set(state.get("palette_color", self.palette_color_var.get()))
            self.linewidth_var.set(float(state.get("line_width", self.linewidth_var.get())))
            self.figure_width_var.set(float(state.get("figure_width", self.figure_width_var.get())))
            self.figure_height_var.set(float(state.get("figure_height", self.figure_height_var.get())))
            self.show_legend_var.set(state.get("show_legend", self.show_legend_var.get()))
            self.title_var.set(state.get("title", ""))
            self.transparent_var.set(state.get("transparent_background", self.transparent_var.get()))
            self.format_filter_var.set(state.get("load_format", self.format_filter_var.get()))
            self.set_range_vars(self.xmin_var, self.xmax_var, state.get("xlim"))
            self.set_range_vars(self.ymin_var, self.ymax_var, state.get("ylim"))

            active_filters = state.get("active_filters")
            if active_filters is None:
                active_filters = state.get("active_trace_sets", [])
            active_filters = set(active_filters)
            for name, var in self.quick_filter_vars.items():
                var.set(name in active_filters)

            loaded_peak_visibility = state.get("peak_visibility", {})
            if not loaded_peak_visibility and "visible_peak_ranks" in state:
                global_ranks = set(state.get("visible_peak_ranks", []))
                loaded_peak_visibility = {
                    str(path): sorted(global_ranks)
                    for path in state.get("selected_traces", [])
                }
            self.loaded_peak_visibility = {
                str(path): {int(rank) for rank in ranks}
                for path, ranks in loaded_peak_visibility.items()
            }

            restored_colors = {}
            for path_str, color in state.get("trace_colors", {}).items():
                path = Path(path_str)
                if path.exists():
                    restored_colors[path] = color
            self.trace_colors = restored_colors

            self.apply_filter()

            selected_paths = []
            for path_str in state.get("selected_traces", []):
                path = Path(path_str)
                if path.exists() and self.tree.exists(str(path)):
                    selected_paths.append(str(path))
            if selected_paths:
                self.tree.selection_set(selected_paths)
                if selected_paths:
                    self.tree.see(selected_paths[0])
            else:
                self.tree.selection_remove(self.tree.selection())

            self.update_plot()
            restored_count = len(selected_paths)
            self.status_var.set(
                f"Loaded session {Path(session_path).name}. Restored {restored_count} trace(s)."
            )
        except (tk.TclError, ValueError, TypeError) as exc:
            messagebox.showerror("Load failed", f"Session file is not compatible:\n{exc}")

    def populate_title_from_selection(self) -> None:
        selected = self.get_selected_entries()
        if not selected:
            return
        labels = sorted({entry.label for entry in selected})
        dates = sorted({entry.date for entry in selected if entry.date})
        columns = sorted({entry.column for entry in selected if entry.column})
        title = " vs ".join(labels[:2]) if len(labels) == 2 else ", ".join(labels[:3])
        if len(labels) > 3:
            title = f"{title} +{len(labels) - 3} more"
        if columns:
            title = f"{title} [{', '.join(columns)}]"
        if dates:
            title = f"{title} ({', '.join(dates)})"
        self.title_var.set(title)
        self.update_plot()

    def current_export_size(self) -> tuple[float, float]:
        try:
            export_width = max(4.0, float(self.figure_width_var.get()))
            export_height = max(3.0, float(self.figure_height_var.get()))
        except (tk.TclError, ValueError):
            export_width, export_height = DEFAULT_FIGSIZE
        return export_width, export_height

    def preview_render_dpi(self, export_width: float, export_height: float) -> int:
        self.preview_canvas.update_idletasks()
        canvas_width = max(self.preview_canvas.winfo_width() - 24, 600)
        canvas_height = max(self.preview_canvas.winfo_height() - 24, 380)
        fit_dpi = min(canvas_width / export_width, canvas_height / export_height)
        return max(40, min(PREVIEW_DPI, int(fit_dpi)))

    def on_preview_resized(self, _event) -> None:
        if self.preview_resize_after is not None:
            self.root.after_cancel(self.preview_resize_after)
        self.preview_resize_after = self.root.after(120, self.update_plot)

    def trace_target_options(self, entries: list[TraceEntry]) -> tuple[list[str], dict[str, Path]]:
        counts = Counter(entry.label for entry in entries)
        options = []
        lookup = {}
        for entry in entries:
            option = entry.label
            if counts[entry.label] > 1:
                suffix = entry.date or entry.path.stem
                option = f"{entry.label} ({suffix})"
            options.append(option)
            lookup[option] = entry.path
        return options, lookup

    def refresh_trace_target_menu(self, selected: list[TraceEntry]) -> None:
        options, lookup = self.trace_target_options(selected)
        self.trace_target_lookup = lookup
        self.trace_target_menu.configure(values=options)
        current_value = self.trace_target_var.get()
        if current_value not in lookup:
            self.trace_target_var.set(options[0] if options else "")
        self.refresh_color_preview()

    def rebuild_peak_controls(self, selected: list[TraceEntry]) -> None:
        for child in self.peak_grid_frame.winfo_children():
            child.destroy()

        if not selected:
            ttk.Label(self.peak_grid_frame, text="Select one or more traces to manage peak labels.").grid(
                row=0, column=0, sticky="w"
            )
            return

        ttk.Label(self.peak_grid_frame, text="Trace").grid(row=0, column=0, sticky="w", padx=(0, 10))
        for rank in range(1, 6):
            ttk.Label(self.peak_grid_frame, text=f"Peak {rank}").grid(row=0, column=rank, sticky="w", padx=4)

        active_trace_ids = {str(entry.path) for entry in selected}
        self.peak_rank_vars_by_trace = {
            trace_id: rank_vars
            for trace_id, rank_vars in self.peak_rank_vars_by_trace.items()
            if trace_id in active_trace_ids
        }

        for row_idx, entry in enumerate(selected, start=1):
            trace_id = str(entry.path)
            if trace_id not in self.peak_rank_vars_by_trace:
                saved_ranks = self.loaded_peak_visibility.get(trace_id, set())
                self.peak_rank_vars_by_trace[trace_id] = {
                    rank: tk.BooleanVar(value=rank in saved_ranks)
                    for rank in range(1, 6)
                }
            ttk.Label(self.peak_grid_frame, text=entry.label).grid(row=row_idx, column=0, sticky="w", padx=(0, 10), pady=2)
            for rank in range(1, 6):
                ttk.Checkbutton(
                    self.peak_grid_frame,
                    variable=self.peak_rank_vars_by_trace[trace_id][rank],
                    command=self.update_plot,
                ).grid(row=row_idx, column=rank, sticky="w", padx=8, pady=2)

    def refresh_color_preview(self) -> None:
        target_path = self.trace_target_lookup.get(self.trace_target_var.get())
        color_hex = STANDARD_COLORS.get(self.palette_color_var.get(), STANDARD_COLORS["Navy"])
        if target_path is not None:
            assigned = self.trace_colors.get(target_path)
            if assigned is not None:
                color_hex = assigned
                for name, value in STANDARD_COLORS.items():
                    if value.lower() == assigned.lower():
                        self.palette_color_var.set(name)
                        break
        self.color_chip.configure(bg=color_hex)

    def set_trace_color_from_dropdown(self) -> None:
        target_path = self.trace_target_lookup.get(self.trace_target_var.get())
        if target_path is None:
            return
        self.trace_colors[target_path] = STANDARD_COLORS[self.palette_color_var.get()]
        self.refresh_color_preview()
        self.update_plot()

    def set_selected_trace_color(self) -> None:
        selected = self.get_selected_entries()
        if not selected:
            return
        chosen = STANDARD_COLORS[self.palette_color_var.get()]
        for entry in selected:
            self.trace_colors[entry.path] = chosen
        self.update_plot()

    def reset_trace_colors(self) -> None:
        selected = self.get_selected_entries()
        if selected:
            for entry in selected:
                self.trace_colors.pop(entry.path, None)
        else:
            self.trace_colors.clear()
        self.update_plot()

    def active_peak_ranks(self) -> dict[str, set[int]]:
        return {
            trace_id: {rank for rank, var in rank_vars.items() if var.get()}
            for trace_id, rank_vars in self.peak_rank_vars_by_trace.items()
        }

    def build_processed_traces(self) -> tuple[list[dict], tuple[float, float] | None, tuple[float, float] | None]:
        xlim = self.parse_limits(self.xmin_var, self.xmax_var)
        ylim = self.parse_limits(self.ymin_var, self.ymax_var)
        processed = []
        selected = self.get_selected_entries()
        color_cycle = plt_colors()
        line_width = max(0.4, float(self.linewidth_var.get()))
        for idx, entry in enumerate(selected):
            color = self.trace_colors.get(entry.path, color_cycle[idx % len(color_cycle)])
            raw_trace = self.load_trace(entry.path)
            trace = process_trace(
                raw_trace,
                normalize=self.display_mode_var.get() == "normalized",
                baseline_subtract=self.baseline_var.get(),
                smooth_window=max(1, self.smooth_var.get()),
                normalize_window=xlim if self.display_mode_var.get() == "normalized" else None,
                normalize_anchor=self.normalize_anchor_var.get(),
            )
            processed.append(
                {
                    "entry": entry,
                    "trace_id": str(entry.path),
                    "label": entry.label,
                    "color": color,
                    "line_width": line_width,
                    "data": trace,
                    "peaks": find_top_peaks(trace, peak_window=xlim, top_n=5),
                }
            )
        return processed, xlim, ylim

    def render_preview(self, processed_traces: list[dict], xlim, ylim) -> None:
        export_width, export_height = self.current_export_size()
        preview_dpi = self.preview_render_dpi(export_width, export_height)
        preview_figure = Figure(figsize=(export_width, export_height), dpi=preview_dpi)
        preview_ax = preview_figure.add_subplot(111)
        render_sec_plot(
            fig=preview_figure,
            ax=preview_ax,
            traces=processed_traces,
            title=self.title_var.get().strip(),
            normalized=self.display_mode_var.get() == "normalized",
            xlim=xlim,
            ylim=ylim,
            show_legend=self.show_legend_var.get(),
            style=self.style_var.get(),
            visible_peak_ranks=self.active_peak_ranks(),
        )
        preview_figure.savefig(self.preview_cache_path, dpi=preview_dpi, transparent=False)
        self.preview_image = tk.PhotoImage(file=str(self.preview_cache_path))
        self.preview_canvas.delete("all")
        canvas_width = max(self.preview_canvas.winfo_width(), self.preview_image.width())
        canvas_height = max(self.preview_canvas.winfo_height(), self.preview_image.height())
        x_offset = max((canvas_width - self.preview_image.width()) // 2, 0)
        y_offset = max((canvas_height - self.preview_image.height()) // 2, 0)
        self.preview_item = self.preview_canvas.create_image(
            x_offset,
            y_offset,
            image=self.preview_image,
            anchor="nw",
        )
        self.preview_canvas.configure(scrollregion=(0, 0, canvas_width, canvas_height))

    def update_plot(self) -> None:
        selected = self.get_selected_entries()
        self.refresh_trace_target_menu(selected)
        self.rebuild_peak_controls(selected)
        processed_traces, xlim, ylim = self.build_processed_traces()
        self.render_preview(processed_traces, xlim, ylim)
        self.refresh_color_preview()
        if not selected:
            self.status_var.set(f"{len(self.entries)} files loaded. No traces selected.")
            return
        self.status_var.set(
            f"{len(self.filtered_entries)} visible files. {len(selected)} trace(s) selected."
        )

    def choose_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Choose SEC output base name",
            initialdir=str(self.data_dir / "figures"),
            defaultextension="",
            filetypes=[
                ("All files", "*"),
            ],
        )
        if path:
            output = Path(path)
            if output.suffix.lower() in {".svg", ".png", ".pdf", ".eps"}:
                output = output.with_suffix("")
            self.output_var.set(str(output))

    def save_figure(self) -> None:
        selected = self.get_selected_entries()
        if not selected:
            messagebox.showerror("No selection", "Select at least one trace before saving.")
            return

        output_base = Path(self.output_var.get()).expanduser()
        output_base.parent.mkdir(parents=True, exist_ok=True)
        export_width, export_height = self.current_export_size()
        save_kwargs = {
            "transparent": self.transparent_var.get(),
        }
        svg_output = output_base.with_suffix(".svg")
        png_output = output_base.with_suffix(".png")
        session_output = output_base.with_suffix(".session.json")
        processed_traces, xlim, ylim = self.build_processed_traces()
        export_figure = Figure(figsize=(export_width, export_height), dpi=PREVIEW_DPI)
        export_ax = export_figure.add_subplot(111)
        render_sec_plot(
            fig=export_figure,
            ax=export_ax,
            traces=processed_traces,
            title=self.title_var.get().strip(),
            normalized=self.display_mode_var.get() == "normalized",
            xlim=xlim,
            ylim=ylim,
            show_legend=self.show_legend_var.get(),
            style=self.style_var.get(),
            visible_peak_ranks=self.active_peak_ranks(),
        )
        export_figure.savefig(svg_output, **save_kwargs)
        export_figure.savefig(png_output, dpi=1600, **save_kwargs)
        session_output.write_text(json.dumps(self.build_session_state(), indent=2))
        export_figure.clear()
        self.status_var.set(f"Saved {svg_output.name}, {png_output.name}, and {session_output.name}")
        messagebox.showinfo(
            "Saved",
            f"Saved figure to:\n{svg_output}\n{png_output}\n{session_output}",
        )

    def save_xmgrace(self) -> None:
        selected = self.get_selected_entries()
        if not selected:
            messagebox.showerror("No selection", "Select at least one trace before exporting.")
            return

        output_base = Path(self.output_var.get()).expanduser()
        output_base.parent.mkdir(parents=True, exist_ok=True)
        agr_output = output_base.with_suffix(".agr")
        processed_traces, xlim, ylim = self.build_processed_traces()
        export_xmgrace(
            traces=processed_traces,
            output=agr_output,
            title=self.title_var.get().strip(),
            x_label="Elution Volume (mL)",
            y_label=(
                "Normalized absorbance"
                if self.display_mode_var.get() == "normalized"
                else "Absorbance (mAU)"
            ),
            show_legend=self.show_legend_var.get() and len(processed_traces) > 1,
            xlim=xlim,
            ylim=ylim,
        )
        self.status_var.set(f"Saved {agr_output.name}")
        messagebox.showinfo("Saved", f"Saved XMGrace file to:\n{agr_output}")

    def save_plotly_html(self) -> None:
        selected = self.get_selected_entries()
        if not selected:
            messagebox.showerror("No selection", "Select at least one trace before exporting.")
            return

        output_base = Path(self.output_var.get()).expanduser()
        output_base.parent.mkdir(parents=True, exist_ok=True)
        html_output = output_base.with_suffix(".html")
        processed_traces, xlim, ylim = self.build_processed_traces()
        export_plotly_html(
            traces=processed_traces,
            output=html_output,
            title=self.title_var.get().strip(),
            x_label="Elution Volume (mL)",
            y_label=(
                "Normalized absorbance"
                if self.display_mode_var.get() == "normalized"
                else "Absorbance (mAU)"
            ),
            show_legend=self.show_legend_var.get() and len(processed_traces) > 1,
            xlim=xlim,
            ylim=ylim,
        )
        self.status_var.set(f"Saved {html_output.name}")
        messagebox.showinfo("Saved", f"Saved Plotly HTML to:\n{html_output}")

    def open_plotly_preview(self) -> None:
        selected = self.get_selected_entries()
        if not selected:
            messagebox.showerror("No selection", "Select at least one trace before previewing.")
            return

        preview_dir = self.data_dir / "figures"
        preview_dir.mkdir(parents=True, exist_ok=True)
        preview_output = preview_dir / "_plotly_preview.html"
        processed_traces, xlim, ylim = self.build_processed_traces()
        export_plotly_html(
            traces=processed_traces,
            output=preview_output,
            title=self.title_var.get().strip(),
            x_label="Elution Volume (mL)",
            y_label=(
                "Normalized absorbance"
                if self.display_mode_var.get() == "normalized"
                else "Absorbance (mAU)"
            ),
            show_legend=self.show_legend_var.get() and len(processed_traces) > 1,
            xlim=xlim,
            ylim=ylim,
        )
        webbrowser.open(preview_output.resolve().as_uri())
        self.status_var.set(f"Opened Plotly preview: {preview_output.name}")

    def copy_labels(self) -> None:
        labels = [entry.label for entry in self.get_selected_entries()]
        if not labels:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append("\n".join(labels))
        self.status_var.set("Copied selected labels to clipboard.")


def plt_colors():
    return (
        "#1f77b4",
        "#d62728",
        "#2ca02c",
        "#ff7f0e",
        "#9467bd",
        "#8c564b",
        "#e377c2",
        "#7f7f7f",
        "#bcbd22",
        "#17becf",
        "#003f5c",
        "#7a5195",
        "#ef5675",
        "#ffa600",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Interactive browser for SEC files.")
    parser.add_argument(
        "--root",
        default=".",
        help="Directory containing .asc and .xls SEC files. Default: current directory",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data_dir = Path(args.root).expanduser().resolve()
    root = tk.Tk()
    app = SecBrowserApp(root, data_dir)
    root.mainloop()


if __name__ == "__main__":
    main()
