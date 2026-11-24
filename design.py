"""PGS design GUI.

Tkinter front-end that ties the PGS sizing calculator (``PGS``) and the
involute gear profile generator (``GPG``) together, plots the gear set
geometry with matplotlib and exports the results as Markdown and CSV.

Run with::

    uv run design.py
"""

from __future__ import annotations

import math
import os
import re
import sys
import time
import tkinter as tk
import tkinter.font as font
import webbrowser
from dataclasses import replace
from tkinter import filedialog
from tkinter import messagebox
from tkinter import ttk

import matplotlib.pyplot as plt
import numpy as np

try:
    from PIL import Image, ImageTk
except ImportError:  # pragma: no cover - pillow is optional for inline images
    Image = None
    ImageTk = None

import FGPG2_CLI
import animation
import interference
from CPG import CPG
from GPG import GPG
from PGS import PGS, ring_shift_factor

DEFAULT_SCALE = 0.7
DEFAULT_WINDOW_HEIGHT_RATIO = 0.70
PLOT_DPI = 100
PGS_FIGURE = "PGS"
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_RESULT_DIR = os.path.join(PROJECT_DIR, "result")

# Per-gear result generation uses the FGPG2 gear generator that has been
# ported into this project (the ``fgpg2`` package + ``FGPG2_CLI.py``): it
# writes Result.csv, Result.dxf, Result1.png and Result2.png next to the
# gear's Inputs.csv, with no external installation required.

GEAR_ORDER = ["Gs1", "Gp1", "Gr1", "Gs2", "Gp2", "Gr2"]
RING_GEARS = {"Gr1", "Gr2"}

# --- Modern flat colour palette --------------------------------------------
BG = "#f0f2f5"           # window background (cool light gray)
CARD = "#ffffff"         # card / panel background
FG = "#1f2937"           # primary text (slate-800)
MUTED = "#6b7280"        # secondary text (slate-500)
ACCENT = "#2563eb"       # primary accent (blue-600)
ACCENT_DARK = "#1d4ed8"  # accent hover / pressed
DANGER = "#dc2626"       # destructive action (red-600)
DANGER_DARK = "#b91c1c"
NEUTRAL = "#e5e7eb"      # default button face
NEUTRAL_DARK = "#d1d5db"
BORDER = "#d1d5db"       # entry / panel borders

PAD = 6
PADX = 5
PADY = 2

# Default values inserted into the input entries at startup.
DEFAULT_INPUTS = {
    "TYPE": 1,
    "m1": 0.8,
    "m2": 1.2,
    "Np": 3,
    "Zp2": 20.0,
    "Zr1": 90.0,
    "Zs1": 12,
    "Ns1": 1000.0,
    "Gs1X": 0.4,
    "Gp1X": 0.4,
    "Gp2X": 0.4,
    "B": 0.04,
    "A": 1.0,
    "D": 1.25,
    "alpha": 20,
    "C": 0.2,
    "E": 0.01,
    "mu": 0.08,
    "mu_b_in": 0.002,
    "mu_b_p": 0.002,
    "mu_b_c": 0.002,
    "mu_b_out": 0.005,
    "seal": 0.0,
    "churn": 0.005,
    "PlotOption": 3,
    "TeethType": "Involute Teeth",
    "Zr2": 54.0,
}

# (key, label, hint, hint-on-next-row?)
PLANETARY_INPUTS = [
    ("TYPE", "Type", "", False),
    ("Np", "Planet number, Np", "[ea] > 2", False),
    ("m1", "Module1, m1", "[mm] > 0", False),
    ("m2", "Module2, m2", "[mm] > 0", False),
    ("Zs1", "Sun1 Teeth, Zs1", "[ea] > 0", False),
    ("Zr1", "Ring1 Teeth, Zr1", "[ea] > 0", False),
    ("Zp2", "Planet2 Teeth, Zp2", "[ea] > 0", False),
    ("Zr2", "Ring2 Teeth, Zr2", "[ea] > 0", False),
    ("Ns1", "Input speed, ns1", "[rpm]", False),
]

GEAR_INPUTS = [
    ("Gs1X", "Shift factor, Gs1.X", "", False),
    ("Gp1X", "Shift factor, Gp1.X", "", False),
    ("Gp2X", "Shift factor, Gp2.X", "", False),
    ("B", "Backlash factor, B", "", False),
    ("A", "Addendum factor, A", "", False),
    ("D", "Dedendum factor, D", "", False),
    ("alpha", "Pressure angle, α", "[deg]", False),
    ("C", "Hob end radius, C", "[mm]", False),
    ("E", "Tooth end radius, E", "[mm]", False),
]

LOSS_INPUTS = [
    ("mu", "Friction coeff, μ", "or custom", False),
    ("mu_b_in", "Input bearing, μb_in", "or custom", False),
    ("mu_b_p", "Planet bearing, μb_p", "or custom", False),
    ("mu_b_c", "Carrier bearing, μb_c", "or custom", False),
    ("mu_b_out", "Output bearing, μb_out", "or custom", False),
    ("seal", "Seal loss, ζs", "or custom", False),
    ("churn", "Churning coeff, kc", "@1000rpm", False),
]

BEARING_ENTRY_KEYS = ("mu_b_in", "mu_b_p", "mu_b_c", "mu_b_out")

# Editable combobox presets for loss parameters (any custom non-negative
# number may also be typed directly).
LOSS_PRESETS: dict[str, list[tuple[str, float]]] = {
    "mu": [
        ("0.08 (Grease)", 0.08),
        ("0.05 (Oil)", 0.05),
    ],
    "mu_b_in": [
        ("0.002 (Ball)", 0.002),
        ("0.005 (Roller)", 0.005),
        ("0.05 (Bushing)", 0.05),
        ("0.0 (Floating/None)", 0.0),
    ],
    "mu_b_p": [
        ("0.002 (Ball/Needle)", 0.002),
        ("0.005 (Roller)", 0.005),
        ("0.05 (Bushing)", 0.05),
        ("0.0 (None)", 0.0),
    ],
    "mu_b_c": [
        ("0.002 (Ball)", 0.002),
        ("0.005 (Roller)", 0.005),
        ("0.05 (Bushing)", 0.05),
        ("0.0 (Floating/None)", 0.0),
    ],
    "mu_b_out": [
        ("0.005 (Crossed Roller)", 0.005),
        ("0.002 (Ball)", 0.002),
        ("0.01 (Preloaded CRB)", 0.01),
        ("0.05 (Bushing)", 0.05),
        ("0.0 (None)", 0.0),
    ],
    "seal": [
        ("0.0 (None)", 0.0),
        ("0.005 (Low-fric)", 0.005),
        ("0.01 (Lip seal)", 0.01),
        ("0.02 (Double-lip)", 0.02),
    ],
    "churn": [
        ("0.005 (Grease)", 0.005),
        ("0.015 (Oil splash)", 0.015),
        ("0.002 (Oil mist)", 0.002),
        ("0.0 (None)", 0.0),
    ],
}
LOSS_PRESET_OPTIONS: dict[str, list[str]] = {
    key: [label for label, _ in items] for key, items in LOSS_PRESETS.items()
}

PLOT_ITEMS = [
    ("Gs1", 11),
    ("Gp1", 12),
    ("Gr1", 13),
    ("Gp2", 22),
    ("Gr2", 23),
    ("Stage1", 1),
    ("Stage2", 2),
    ("Total", 3),
]
PLOT_OPTIONS = [label for label, _ in PLOT_ITEMS]
PLOT_LABEL_TO_CODE = {label: code for label, code in PLOT_ITEMS}
PLOT_CODE_TO_LABEL = {code: label for label, code in PLOT_ITEMS}

# Stage-1 plot options only (used when TYPE == Simple): the stage-2 and
# combined options do not apply to a simple gear set.
PLOT_ITEMS_SIMPLE = [
    ("Gs1", 11),
    ("Gp1", 12),
    ("Gr1", 13),
    ("Stage1", 1),
]
PLOT_OPTIONS_SIMPLE = [label for label, _ in PLOT_ITEMS_SIMPLE]

# Tooth profile selection: label -> generator class.
TOOTH_ITEMS = [
    ("Involute Teeth", GPG),
    ("Cycloid Teeth", CPG),
]
# "All" overlays both profiles in a single plot.
TOOTH_ALL_LABEL = "All"
TOOTH_OPTIONS = [label for label, _ in TOOTH_ITEMS] + [TOOTH_ALL_LABEL]
TOOTH_LABEL_TO_CLASS = dict(TOOTH_ITEMS)

# Human-readable Type options: the Wolfrom type reads Zr2 (Ring2 Teeth)
# directly instead of a teeth-difference, so only these two choices remain.
TYPE_ITEMS = [
    ("Simple", 0),
    ("3K-Wolfrom", 1),
]
TYPE_LABELS = [label for label, _ in TYPE_ITEMS]
TYPE_LABEL_TO_CODE = {label: code for label, code in TYPE_ITEMS}
TYPE_CODE_TO_LABEL = {code: label for label, code in TYPE_ITEMS}

# Shared mutable state populated by the GUI build below.
app: tk.Tk
entries: dict[str, tk.Widget] = {}
textbox: tk.Text
report_markdown: str = ""
current_markdown: str = ""
P1: PGS
gears: dict[str, GPG | CPG]
gears_second: dict[str, GPG | CPG] | None = None
interference_reports: list[interference.ProfileInterferenceReport] = []
run_button: ttk.Button | None = None
animation_button: ttk.Button | None = None
save_button: ttk.Button | None = None
load_button: ttk.Button | None = None
tip_check_button: ttk.Button | None = None
status_progressbar: ttk.Progressbar | None = None
status_label: ttk.Label | None = None
_is_busy: bool = False
_animation_window: animation.GearboxAnimationWindow | None = None
result_copy_button: ttk.Button | None = None
result_search_var: tk.StringVar | None = None
result_search_entry: ttk.Entry | None = None
result_search_status: ttk.Label | None = None
result_search_matches: list[tuple[str, str]] = []
result_search_index: int = -1


# ---------------------------------------------------------------- parameters
def copy_gear_factors(target_gears, module, b, a, d, angle, c, e):
    """Apply the shared factor inputs to every gear in ``target_gears``."""
    for gear in target_gears:
        gear.module = module
        gear.backlash_factor = b
        gear.addendum_factor = a
        gear.dedendum_factor = d
        gear.pressure_angle = angle
        gear.hob_tip_radius_factor = c
        gear.tooth_tip_radius_factor = e


def _apply_params(g: dict[str, GPG | CPG]) -> None:
    """Apply the current input values (modules, factors, shifts) to ``g``."""
    module1 = float(entries["m1"].get())
    module2 = float(entries["m2"].get())
    b = float(entries["B"].get())
    a = float(entries["A"].get())
    d = float(entries["D"].get())
    angle = float(entries["alpha"].get())
    c = float(entries["C"].get())
    e = float(entries["E"].get())
    copy_gear_factors((g["Gs1"], g["Gp1"], g["Gr1"]),
                      module1, b, a, d, angle, c, e)
    g["Gs1"].shift_factor = float(entries["Gs1X"].get())
    g["Gp1"].shift_factor = float(entries["Gp1X"].get())
    if P1.is_wolfrom:
        copy_gear_factors((g["Gs2"], g["Gp2"], g["Gr2"]),
                          module2, b, a, d, angle, c, e)
        g["Gp2"].shift_factor = float(entries["Gp2X"].get())


def _parse_loss_param(raw: str, name: str = "loss parameter") -> float:
    """Parse a non-negative loss parameter from a preset label or raw number."""
    text = str(raw).strip()
    m = re.match(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", text)
    if not m:
        raise ValueError(f"Invalid {name}: {raw!r}")
    value = float(m.group(0))
    if value < 0.0:
        raise ValueError(f"{name} must be >= 0 (got {value})")
    return value


def _format_loss_option(key: str, value: float) -> str:
    """Format ``value`` as a matching preset label for ``key``, else number."""
    for label, preset in LOSS_PRESETS.get(key, ()):
        if math.isclose(value, preset, rel_tol=0.0, abs_tol=1e-9):
            return label
    return f"{value:g}"


def read_parameters() -> None:
    """Pull values from the input entries into the model objects."""
    global gears, gears_second
    # Rebuild the gear set when the tooth profile selection changes.  "All"
    # builds both profiles (involute primary, cycloid overlay).
    sel = entries["TeethType"].get()
    if sel == TOOTH_ALL_LABEL:
        if not isinstance(gears.get("Gs1"), GPG):
            gears = {name: GPG() for name in GEAR_ORDER}
        if gears_second is None or not isinstance(gears_second.get("Gs1"), CPG):
            gears_second = {name: CPG() for name in GEAR_ORDER}
    else:
        cls = TOOTH_LABEL_TO_CLASS[sel]
        if not isinstance(gears.get("Gs1"), cls):
            gears = {name: cls() for name in GEAR_ORDER}
        gears_second = None

    is_wolfrom = entries["TYPE"].get() != "Simple"
    P1.gear_type = 1 if is_wolfrom else 0
    P1.module1 = float(entries["m1"].get())
    P1.module2 = float(entries["m2"].get())
    P1.num_planets = int(entries["Np"].get())
    if is_wolfrom:
        P1.zp2 = float(entries["Zp2"].get())
        P1.zr2 = -abs(float(entries["Zr2"].get()))
        P1.zr1 = -abs(float(entries["Zr1"].get()))
    else:
        P1.zr1 = -abs(float(entries["Zr1"].get()))
    P1.zs1 = float(entries["Zs1"].get())
    P1.ns1 = float(entries["Ns1"].get())
    P1.shift_s1 = float(entries["Gs1X"].get())
    P1.shift_p1 = float(entries["Gp1X"].get())
    P1.shift_p2 = float(entries["Gp2X"].get()) if is_wolfrom else 0.0
    P1.addendum_factor = float(entries["A"].get())
    P1.friction_coeff = _parse_loss_param(entries["mu"].get(), "friction coeff")
    P1.bearing_coeff_input = _parse_loss_param(
        entries["mu_b_in"].get(), "input bearing coeff"
    )
    P1.bearing_coeff_planet = _parse_loss_param(
        entries["mu_b_p"].get(), "planet bearing coeff"
    )
    P1.bearing_coeff_carrier = (
        _parse_loss_param(entries["mu_b_c"].get(), "carrier bearing coeff")
        if is_wolfrom
        else 0.0
    )
    P1.bearing_coeff_output = _parse_loss_param(
        entries["mu_b_out"].get(), "output bearing coeff"
    )
    P1.seal_loss = _parse_loss_param(entries["seal"].get(), "seal loss")
    P1.churning_coeff = _parse_loss_param(entries["churn"].get(), "churning coeff")
    P1.pressure_angle = float(entries["alpha"].get())

    for g in [gears] + ([gears_second] if gears_second else []):
        _apply_params(g)


def _ring_shift_factor(zp, xp, zr, module, dc, alpha_deg):
    """Ring-gear profile shift for a zero-backlash internal mesh."""
    return ring_shift_factor(zp, xp, zr, module, dc, alpha_deg)


def finalize_parameters(g: dict[str, GPG | CPG]) -> None:
    """Transfer the PGS-derived tooth counts/modules to a gear set ``g``."""
    g["Gs1"].module = P1.module1
    g["Gs1"].teeth = P1.zs1
    g["Gp1"].module = P1.module1
    g["Gp1"].teeth = P1.zp1
    g["Gp1"].y0 = P1.dc / 2.0
    g["Gr1"].module = P1.module1
    g["Gr1"].teeth = P1.zr1

    if P1.is_wolfrom:
        g["Gs2"].module = P1.module2
        g["Gs2"].teeth = P1.zs2
        g["Gp2"].module = P1.module2
        g["Gp2"].teeth = P1.zp2
        g["Gp2"].y0 = P1.dc / 2.0
        g["Gr2"].module = P1.module2
        g["Gr2"].teeth = P1.zr2

    g["Gr1"].shift_factor = _ring_shift_factor(
        P1.zp1, g["Gp1"].shift_factor, -P1.zr1,
        P1.module1, P1.dc, g["Gp1"].pressure_angle)
    if P1.is_wolfrom:
        g["Gs2"].shift_factor = -g["Gp2"].shift_factor
        g["Gr2"].shift_factor = _ring_shift_factor(
            P1.zp2, g["Gp2"].shift_factor, -P1.zr2,
            P1.module2, P1.dc, g["Gp2"].pressure_angle)

    if isinstance(g["Gs1"], CPG):
        # Cycloidal gears must share one circular pitch per meshing stage.
        # Split the carrier centre distance dc/2 in proportion to tooth counts
        # (operating module m_w) so Gs1, Gp1, Gr1 share pi*m_w1 and Gp2, Gr2
        # share pi*m_w2 with tangent pitch circles and zero shift-induced gap.
        if (P1.zs1 + P1.zp1) > 0.0:
            m_w1 = P1.dc / (P1.zs1 + P1.zp1)
            g["Gs1"].pitch_circle_radius = 0.5 * m_w1 * P1.zs1
            g["Gp1"].pitch_circle_radius = 0.5 * m_w1 * P1.zp1
            g["Gr1"].pitch_circle_radius = 0.5 * m_w1 * (-P1.zr1)
        if P1.is_wolfrom and (-P1.zr2 - P1.zp2) > 0.0:
            m_w2 = P1.dc / (-P1.zr2 - P1.zp2)
            g["Gp2"].pitch_circle_radius = 0.5 * m_w2 * P1.zp2
            g["Gr2"].pitch_circle_radius = 0.5 * m_w2 * (-P1.zr2)
    else:
        g["Gs1"].pitch_circle_radius = None
        g["Gp1"].pitch_circle_radius = None
        g["Gr1"].pitch_circle_radius = (
            P1.dc / 2.0
            + P1.module1 * (P1.zp1 / 2.0 + g["Gp1"].shift_factor))
        if P1.is_wolfrom:
            g["Gp2"].pitch_circle_radius = None
            g["Gr2"].pitch_circle_radius = (
                P1.dc / 2.0
                + P1.module2 * (P1.zp2 / 2.0 + g["Gp2"].shift_factor))


def _active_profile_sets() -> list[tuple[str, dict[str, GPG | CPG]]]:
    """Return ``(profile_name, gear_set)`` pairs for the currently selected profile(s)."""
    primary_name = "Cycloid" if isinstance(gears.get("Gs1"), CPG) else "Involute"
    active: list[tuple[str, dict[str, GPG | CPG]]] = [(primary_name, gears)]
    if isinstance(gears_second, dict):
        sec_name = "Cycloid" if isinstance(gears_second.get("Gs1"), CPG) else "Involute"
        active.append((sec_name, gears_second))
    return active


def _calc_gears_only() -> None:
    """Compute PGS ratios and gear tooth profiles without tip-sweep or disk I/O."""
    P1.calc()
    finalize_parameters(gears)
    if gears_second is not None:
        finalize_parameters(gears_second)
    for name in GEAR_ORDER[:3]:
        gears[name].calc()
    if P1.is_wolfrom:
        for name in GEAR_ORDER[3:]:
            gears[name].calc()
    if gears_second is not None:
        for name in GEAR_ORDER[:3]:
            gears_second[name].calc()
        if P1.is_wolfrom:
            for name in GEAR_ORDER[3:]:
                gears_second[name].calc()


def _set_progress(
    percent: float,
    text: str,
    *,
    color: str = MUTED,
    pump_ui: bool = True,
) -> None:
    """Update the bottom-bar progress bar and elapsed-time status label."""
    if status_progressbar is not None:
        try:
            if status_progressbar.winfo_exists():
                status_progressbar["value"] = max(0.0, min(100.0, percent))
        except tk.TclError:
            pass
    if status_label is not None:
        try:
            if status_label.winfo_exists():
                status_label.configure(text=text, foreground=color)
        except tk.TclError:
            pass
    if pump_ui and "app" in globals() and app is not None:
        try:
            if app.winfo_exists():
                app.update()
        except tk.TclError:
            pass


class _ProgressTracker:
    """Tracks step progress and elapsed time for long-running GUI actions."""

    def __init__(self, total_steps: int, *, pump_ui: bool = True) -> None:
        self.total = max(1, int(total_steps))
        self.done = 0
        self.t0 = time.perf_counter()
        self.pump_ui = pump_ui

    @property
    def elapsed(self) -> float:
        return time.perf_counter() - self.t0

    def update(self, message: str, *, advance: int = 0) -> None:
        if advance:
            self.done = min(self.total, self.done + advance)
        pct = min(100.0, (self.done / self.total) * 100.0)
        _set_progress(
            pct,
            f"{message} ({self.done}/{self.total} · {self.elapsed:.1f}s)",
            pump_ui=self.pump_ui,
        )

    def finish(self, message: str = "Done") -> None:
        self.done = self.total
        _set_progress(
            100.0,
            f"{message} ({self.elapsed:.1f}s)",
            color="#15803d",
            pump_ui=self.pump_ui,
        )

    def fail(self, message: str = "Error") -> None:
        _set_progress(
            0.0,
            f"{message} ({self.elapsed:.1f}s)",
            color=DANGER,
            pump_ui=self.pump_ui,
        )


def _estimate_run_steps() -> int:
    """Return total discrete progress steps for lightweight Run."""
    # calc(1) + tip_check(1) + README.md(1) + Involute PNG(1)
    # + Cycloid PNG(1) + render(1) + plot(1)
    return 7


def _estimate_export_steps(*, include_plot: bool = False) -> int:
    """Return total discrete progress steps for Run / Save."""
    n_gears = 5 if P1.is_wolfrom else 3
    n_scopes = 8 if P1.is_wolfrom else 4
    n_all = 1 + n_gears
    # calc(1) + tip_check(1) + report_csv(1) + fgpg2(2*n_gears)
    # + involute_png(n_scopes) + cycloid_png(n_scopes) + all_png(n_all)
    # + tipcheck_png(2) + render(1) [+ plot(1)]
    return 3 + (n_gears * 2) + (n_scopes * 2) + n_all + 2 + 1 + (1 if include_plot else 0)


def _set_action_buttons_state(state: str) -> None:
    """Enable or disable main action buttons during long-running operations."""
    for btn in (
        run_button,
        save_button,
        load_button,
        tip_check_button,
        animation_button,
    ):
        if btn is not None:
            try:
                if btn.winfo_exists():
                    btn.configure(state=state)
            except tk.TclError:
                pass
    if "app" in globals() and app is not None:
        try:
            if app.winfo_exists():
                app.update_idletasks()
        except tk.TclError:
            pass


def run_calc(*, progress: _ProgressTracker | None = None) -> None:
    """Run PGS sizing, every gear's profile generation and kinematic tip checks."""
    global interference_reports
    P1.calc()
    P1.output()
    P1.checks_run()
    finalize_parameters(gears)
    if gears_second is not None:
        finalize_parameters(gears_second)
    for name in GEAR_ORDER[:3]:
        gears[name].calc()
    if P1.is_wolfrom:
        for name in GEAR_ORDER[3:]:
            gears[name].calc()
    if gears_second is not None:
        for name in GEAR_ORDER[:3]:
            gears_second[name].calc()
        if P1.is_wolfrom:
            for name in GEAR_ORDER[3:]:
                gears_second[name].calc()
    if progress is not None:
        progress.update("Checking kinematic tip interference...", advance=1)

    interference_reports = [
        interference.check_profile_interference(P1, g_set, pname)
        for pname, g_set in _active_profile_sets()
    ]
    interference.print_interference_summary(interference_reports)
    if progress is not None:
        progress.update("Writing report & model files...", advance=1)


# --------------------------------------------------------------- helpers
def rotate(x, y, angle):
    """Rotate the point arrays ``(x, y)`` by ``angle`` radians."""
    ca, sa = np.cos(angle), np.sin(angle)
    return ca * x - sa * y, sa * x + ca * y


# --------------------------------------------------------------- plotting
# Plot-option codes: 1/2/3 = whole Stage1 / Stage2 / Total; 11-13 and
# 22-23 = the individual gears Gs1, Gp1, Gr1, Gp2, Gr2.
_PLOT_CODE_KEYS = {
    1:  ["Gs1", "Gp1", "Gr1"],
    2:  ["Gp2", "Gr2"],
    3:  ["Gs1", "Gp1", "Gr1", "Gp2", "Gr2"],
    11: ["Gs1"],
    12: ["Gp1"],
    13: ["Gr1"],
    22: ["Gp2"],
    23: ["Gr2"],
}


def _planet_self_spin(key: str, phi: float) -> float:
    """Self-rotation angle of a planet placed at carrier orbit angle ``phi``.

    Planet 0 (at ``phi = 0``, on the +y axis) is already phased to mesh with
    Gs1, Gr1 and Gr2.  When planet ``i`` is placed at carrier angle ``phi``,
    orbiting it rigidly without spinning around its own axis leaves its teeth
    out of phase whenever ``Zs1`` or ``|Zr|`` is not a multiple of ``Np``
    (non-factorizing designs).

    Spinning planet ``i`` around its own centre before orbiting aligns the
    meshing pitch arcs:
      * Stage-1 planet (Gp1): ``+(Zs1 / Zp1) * phi`` matches Gs1 at every
        planet and simultaneously matches Gr1 whenever the equal-distance
        condition ``(Zs1 + |Zr1|) % Np == 0`` holds (equivalent modulo one
        planet pitch to ``-(|Zr1| / Zp1) * phi``).
      * Stage-2 planet (Gp2): ``-(|Zr2| / Zp2) * phi`` matches Gr2 at every
        planet.
    """
    if key == "Gp1" and P1.zp1 > 0.0:
        return (P1.zs1 / P1.zp1) * phi
    if key == "Gp2" and P1.zp2 > 0.0:
        return -(abs(P1.zr2) / P1.zp2) * phi
    return 0.0


def _plot_gear(key: str, g: dict, *, color, pitch_style, sun_angle: float) -> None:
    """Draw a single gear ``key`` from the gear set ``g``."""
    gear = g[key]
    if key == "Gs1":
        sx, sy = rotate(gear.plot_x, gear.plot_y, sun_angle)
        plt.plot(sx, sy, color)
        plt.plot(gear.pitch_circle_x, gear.pitch_circle_y, pitch_style)
    elif key.startswith("Gp"):
        array_angle = 2 * np.pi / P1.num_planets
        for i in range(P1.num_planets):
            phi = array_angle * i
            spin = _planet_self_spin(key, phi)
            if spin != 0.0:
                lx, ly = rotate(
                    gear.plot_x - gear.x0, gear.plot_y - gear.y0, spin
                )
                px, py = rotate(lx + gear.x0, ly + gear.y0, phi)
            else:
                px, py = rotate(gear.plot_x, gear.plot_y, phi)
            ppx, ppy = rotate(gear.pitch_circle_x, gear.pitch_circle_y, phi)
            plt.plot(px, py, color)
            plt.plot(ppx, ppy, pitch_style)
    else:  # ring
        plt.plot(gear.plot_x, gear.plot_y, color)
        plt.plot(gear.pitch_circle_x, gear.pitch_circle_y, pitch_style)


def _profile_set(cls: type) -> dict[str, GPG | CPG]:
    """Build, finalize and calculate a throwaway gear set of profile ``cls``."""
    s = {name: cls() for name in GEAR_ORDER}
    _apply_params(s)
    finalize_parameters(s)
    for name in GEAR_ORDER[:3]:
        s[name].calc()
    if P1.is_wolfrom:
        for name in GEAR_ORDER[3:]:
            s[name].calc()
    return s


def _show_figures_nonblocking() -> None:
    """Show open matplotlib figures without blocking the Tkinter event loop."""
    plt.show(block=False)
    for num in plt.get_fignums():
        fig = plt.figure(num)
        fig.canvas.draw_idle()
        manager = getattr(fig.canvas, "manager", None)
        win = getattr(manager, "window", None)
        if win is not None and hasattr(win, "lift"):
            try:
                win.lift()
            except tk.TclError:
                pass


def _draw(keys: list[str], sets: list[tuple[dict, bool]],
          out_path: str | None, *, show: bool = True) -> None:
    """Draw ``keys`` from each ``(gear set, is_cycloid)`` pair on one figure.

    Saves the figure to ``out_path``, or shows it interactively when
    ``out_path`` is None (preview).
    """
    plt.figure(PGS_FIGURE, figsize=(6, 6))
    plt.clf()
    # Sun rotation that keeps the sun teeth meshing with the planet array.
    sun_angle = 0.0
    first = sets[0][0]
    if round(first["Gp1"].teeth) % 2 == 0:
        sun_angle = (2 * np.pi / first["Gs1"].teeth) / 2
    for g, is_cyc in sets:
        # Cycloid (CPG) teeth use the brand colours; involute (GPG) keeps
        # the original grey / black scheme.
        color1 = "#95c4ed" if is_cyc else "dimgray"
        color2 = "#19609d" if is_cyc else "black"
        for key in keys:
            color = color1 if key in ("Gs1", "Gp1", "Gr1") else color2
            pitch_style = "r:" if key in ("Gs1", "Gp1", "Gr1") else "r--"
            _plot_gear(key, g, color=color, pitch_style=pitch_style,
                       sun_angle=sun_angle)

    # Carrier circle: the orbit of the planet gear centres.
    theta = np.linspace(0, 2 * np.pi, 361)
    carrier_radius = P1.dc / 2.0
    plt.plot(carrier_radius * np.cos(theta), carrier_radius * np.sin(theta),
             color="lightgray", linestyle="--", linewidth=1)
    plt.axis("equal")
    plt.grid(True)
    if out_path is not None:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        plt.savefig(out_path, dpi=PLOT_DPI)
        plt.close(plt.gcf())
    elif show:
        _show_figures_nonblocking()


def _profile_variant_sets() -> tuple[dict, dict | None]:
    """Return the (involute, cycloid) gear sets for the current design.

    The cycloid set may be None when its profile cannot be generated (e.g.
    a Wolfrom design with a non-integer ``Zs2``).
    """
    if isinstance(gears.get("Gs1"), GPG):
        involute = gears
    else:
        involute = _profile_set(GPG)
    if isinstance(gears.get("Gs1"), CPG):
        cycloid = gears
    elif isinstance(gears_second, dict) and isinstance(gears_second.get("Gs1"), CPG):
        cycloid = gears_second
    else:
        try:
            cycloid = _profile_set(CPG)
        except Exception as e:
            cycloid = None
            print("WARN: cycloid profile generation failed ("
                  + type(e).__name__ + ": " + str(e) + "); cycloid PNGs "
                  "and the combined overlays are skipped.")
    return involute, cycloid


def save_summary_pngs(
    out_dir: str,
    *,
    progress: _ProgressTracker | None = None,
) -> None:
    """Save only the summary PNGs linked from ``README.md`` into ``out_dir``.

    Saves ``Involute_Total.png`` and ``Cycloid_Total.png`` for 3K-Wolfrom
    (or ``Involute_Stage1.png`` and ``Cycloid_Stage1.png`` for Simple).
    """
    os.makedirs(out_dir, exist_ok=True)
    involute, cycloid = _profile_variant_sets()
    scope, code = ("Total", 3) if P1.is_wolfrom else ("Stage1", 1)

    if progress is not None:
        progress.update(f"Saving Involute_{scope}.png...")
    _draw(
        _PLOT_CODE_KEYS[code],
        [(involute, False)],
        os.path.join(out_dir, f"Involute_{scope}.png"),
    )
    if progress is not None:
        progress.update(f"Saved Involute_{scope}.png", advance=1)

    cyc_path = os.path.join(out_dir, f"Cycloid_{scope}.png")
    if cycloid is not None:
        if progress is not None:
            progress.update(f"Saving Cycloid_{scope}.png...")
        _draw(_PLOT_CODE_KEYS[code], [(cycloid, True)], cyc_path)
        if progress is not None:
            progress.update(f"Saved Cycloid_{scope}.png", advance=1)
    else:
        if os.path.isfile(cyc_path):
            try:
                os.remove(cyc_path)
            except OSError:
                pass
        if progress is not None:
            progress.update(f"Skipped Cycloid_{scope}.png", advance=1)


def save_pngs(
    out_dir: str,
    *,
    progress: _ProgressTracker | None = None,
) -> None:
    """Render and save every required PNG into ``out_dir``.

    3K-Wolfrom saves ``Involute_*``/``Cycloid_*``/``All_*`` for the Total,
    Stage1, Stage2 and per-gear scopes; Simple saves the stage-1 set only.
    The ``All_*`` images overlay the involute and cycloid profiles.
    """
    involute, cycloid = _profile_variant_sets()
    if P1.is_wolfrom:
        scopes = [("Total", 3), ("Stage1", 1), ("Stage2", 2),
                  ("Gs1", 11), ("Gp1", 12), ("Gr1", 13),
                  ("Gp2", 22), ("Gr2", 23)]
    else:
        scopes = [("Stage1", 1), ("Gs1", 11), ("Gp1", 12), ("Gr1", 13)]

    for scope, code in scopes:
        if progress is not None:
            progress.update(f"Saving Involute_{scope}.png...")
        _draw(_PLOT_CODE_KEYS[code], [(involute, False)],
              os.path.join(out_dir, f"Involute_{scope}.png"))
        if progress is not None:
            progress.update(f"Saved Involute_{scope}.png", advance=1)
    if cycloid is not None:
        for scope, code in scopes:
            if progress is not None:
                progress.update(f"Saving Cycloid_{scope}.png...")
            _draw(_PLOT_CODE_KEYS[code], [(cycloid, True)],
                  os.path.join(out_dir, f"Cycloid_{scope}.png"))
            if progress is not None:
                progress.update(f"Saved Cycloid_{scope}.png", advance=1)
        # The combined overlay image is produced for the whole set
        # (All_Total for Wolfrom, All_Stage1 for Simple) and for each gear.
        whole = [("Total", 3)] if P1.is_wolfrom else [("Stage1", 1)]
        gear_scopes = [(s, c) for s, c in scopes if c >= 11]
        for scope, code in whole + gear_scopes:
            if progress is not None:
                progress.update(f"Saving All_{scope}.png...")
            _draw(_PLOT_CODE_KEYS[code], [(involute, False), (cycloid, True)],
                  os.path.join(out_dir, f"All_{scope}.png"))
            if progress is not None:
                progress.update(f"Saved All_{scope}.png", advance=1)
    else:
        for stale in (
            "All_Total.png",
            "All_Stage1.png",
            "Cycloid_Total.png",
            "Cycloid_Stage1.png",
            "TipCheck_Cycloid.png",
        ):
            stale_path = os.path.join(out_dir, stale)
            if os.path.isfile(stale_path):
                try:
                    os.remove(stale_path)
                except OSError:
                    pass

    # Always save zoomed worst-phase tip-interference inspection plots for
    # Involute (and Cycloid when available), regardless of pass/fail status.
    if progress is not None:
        progress.update("Saving TipCheck_Involute.png...")
    inv_rep = interference.check_profile_interference(P1, involute, "Involute")
    interference.plot_interference_report(
        P1, involute, inv_rep,
        out_path=os.path.join(out_dir, "TipCheck_Involute.png"),
    )
    if progress is not None:
        progress.update("Saved TipCheck_Involute.png", advance=1)
    if cycloid is not None:
        if progress is not None:
            progress.update("Saving TipCheck_Cycloid.png...")
        cyc_rep = interference.check_profile_interference(P1, cycloid, "Cycloid")
        interference.plot_interference_report(
            P1, cycloid, cyc_rep,
            out_path=os.path.join(out_dir, "TipCheck_Cycloid.png"),
        )
        if progress is not None:
            progress.update("Saved TipCheck_Cycloid.png", advance=1)


def plot_tip_check(*, only_if_fail: bool = False, show: bool = True) -> None:
    """Display zoomed worst-phase tip-interference inspection figure(s)."""
    active = dict(_active_profile_sets())
    opened = False
    for rep in interference_reports:
        if only_if_fail and not rep.has_fail:
            continue
        g_set = active.get(rep.profile_name)
        if g_set is None:
            continue
        interference.plot_interference_report(P1, g_set, rep, show=False)
        opened = True
    if opened and show:
        _show_figures_nonblocking()


def plot_pgs() -> None:
    """Interactive preview of the chosen PlotOption (no file output).

    When any active tooth profile fails the kinematic 1-pitch tip interference
    check, also opens the zoomed worst-phase inspection window alongside the
    main plot with interfering points highlighted in red.
    """
    code = PLOT_LABEL_TO_CODE[entries["PlotOption"].get()]
    keys = _PLOT_CODE_KEYS.get(code, _PLOT_CODE_KEYS[3])
    sets = [(gears, isinstance(gears.get("Gp1"), CPG))]
    if isinstance(gears_second, dict):
        sets.append((gears_second, isinstance(gears_second.get("Gp1"), CPG)))
    _draw(keys, sets, None, show=False)
    plot_tip_check(only_if_fail=True, show=False)
    _show_figures_nonblocking()


# ----------------------------------------------------------- report builder
def _append_checks(lines: list[str]) -> None:
    c = P1.checks
    lines.append("## Check Geometrical Conditions\n")
    lines.append("* Sequential Mesh Condition (Non-Factorizing, Not Required) 1 : " + c.non_factorizing_1 + "\n")
    lines.append("* Planet Numbers (Equal Distance Condition) 1 : " + c.equal_distance_1 + "\n")
    lines.append("* Planets Interference (Non-Overlap Condition) 1 : " + c.planets_interference_1 + "\n")
    lines.append("* Involute Interference Condition 1 : " + c.involute_interference_1 + "\n")
    lines.append("* Trimming Interference 1 : " + c.trimming_interference_1 + "\n")
    lines.append("* Teeth Numbers which is Integer 1 : " + c.teeth_number_integer_1 + "\n")
    lines.extend(interference.format_report_lines(interference_reports))
    lines.append("\n")


def _append_inputs(lines: list[str]) -> None:
    lines.append("## Input Parameters\n")
    type_label = TYPE_CODE_TO_LABEL.get(int(P1.gear_type), "Unknown")
    lines.append("* Type, TYPE = " + str(int(P1.gear_type)) + ", "
                 + type_label + "\n")
    lines.append("* Module1, m1 = " + str(float(P1.module1)) + "\n")
    if P1.is_wolfrom:
        lines.append("* Module2, m2 = " + str(float(P1.module2)) + "\n")
    lines.append("* Planets Number, Np = " + str(int(P1.num_planets)) + "\n")
    if P1.is_wolfrom:
        lines.append("* Ring2 Teeth, Zr2 = " + str(P1.zr2) + "\n")
        lines.append("* Planet2 Teeth, Zp2 = " + str(P1.zp2) + "\n")
    lines.append("* Ring1 Teeth, Zr1 = " + str(P1.zr1) + "\n")
    lines.append("* Sun1 Teeth, Zs1 = " + str(int(P1.zs1)) + "\n")
    lines.append("* Input Speed, ns1 = " + str(float(P1.ns1)) + "\n")
    lines.append("* Shift Factor, Gs1.X = " + str(float(gears["Gs1"].shift_factor)) + "\n")
    lines.append("* Shift Factor, Gp1.X = " + str(float(gears["Gp1"].shift_factor)) + "\n")
    if P1.is_wolfrom:
        lines.append("* Shift Factor, Gp2.X = " + str(float(gears["Gp2"].shift_factor)) + "\n")
    lines.append("* Backlash Factor, B = " + str(float(gears["Gs1"].backlash_factor)) + "\n")
    lines.append("* Addendum Factor, A = " + str(float(gears["Gs1"].addendum_factor)) + "\n")
    lines.append("* Dedendum Factor, D = " + str(float(gears["Gs1"].dedendum_factor)) + "\n")
    lines.append("* Pressure Angle, alpha = " + str(float(gears["Gs1"].pressure_angle)) + "\n")
    lines.append("* Radius of Hib End, C = " + str(float(gears["Gs1"].hob_tip_radius_factor)) + "\n")
    lines.append("* Radius of Tooth End, E = " + str(float(gears["Gs1"].tooth_tip_radius_factor)) + "\n")
    lines.append("* Friction Coeff, mu = " + str(float(P1.friction_coeff)) + "\n")
    lines.append("* Input Bearing Coeff, mu_b_in = " + str(float(P1.bearing_coeff_input)) + "\n")
    lines.append("* Planet Bearing Coeff, mu_b_p = " + str(float(P1.bearing_coeff_planet)) + "\n")
    if P1.is_wolfrom:
        lines.append("* Carrier Bearing Coeff, mu_b_c = " + str(float(P1.bearing_coeff_carrier)) + "\n")
    lines.append("* Output Bearing Coeff, mu_b_out = " + str(float(P1.bearing_coeff_output)) + "\n")
    lines.append("* Seal Loss, zeta_s = " + str(float(P1.seal_loss)) + "\n")
    lines.append("* Churning Coeff, kc = " + str(float(P1.churning_coeff)) + "\n\n")


def _speed_lines(title: str, rows: list[tuple[str, float]]) -> str:
    """Compose one '### Speed (...)' Markdown block for a lockup config."""
    body = [title + "\n"]
    for label, value in rows:
        body.append("* " + label + " = " + PGS._signed(value) + " [rpm]\n")
    body.append("\n")
    return "".join(body)


def _append_wolfrom(lines: list[str]) -> None:
    gr2, gp1, gs1, gr1, gp2 = (gears["Gr2"].teeth, gears["Gp1"].teeth,
                              gears["Gs1"].teeth, gears["Gr1"].teeth,
                              gears["Gp2"].teeth)
    num = int(gr2 * gp1 * gs1 + gr2 * gp1 * gr1)
    den = int(gs1 * gr2 * gp1 - gs1 * gr1 * gp2)
    common = np.gcd(num, den)
    fraction = f"{int(num / common)}/{int(den / common)}"

    lines.append("## Wolfrom Planetary Gear Set\n\n")
    lines.append("### Ratio\n")
    lines.append("* Ratio (Sun-Planet1) = " + str(P1.gp1s) + "\n")
    lines.append("* Ratio (Planet2-Ring2) = " + str(P1.gr2p2) + "\n")
    lines.append("* Ratio Total (Ring2 Fiexed, Carrier Output) = " + str(P1.g1) + "\n")
    lines.append("* Ratio Total (Carrier Fixed, Ring2 Output) = " + str(P1.g2) + "\n")
    lines.append("* Ratio Total (Type-3K : Carrier Free, Ring2 Output) = "
                + str(P1.g22) + " = " + fraction + "\n\n")
    lines.append(_speed_lines(
        "### Speed (Type-3K : Carrier Free, Ring2 Output)",
        [("Input Gear Speed (Gs1)", P1.ns1),
         ("Carrier Speed", P1.n_carrier),
         ("1st Ring Gear Speed (Gr1)", P1.n_ring1),
         ("Planet Gear Speed (Gp1,Gp2)", P1.n_planet),
         ("2nd Ring Gear Speed (Gr2)", P1.n_output)]))
    lines.append(_speed_lines(
        "### Speed (Ring2 Fiexed, Carrier Output)",
        [("Input Gear Speed (Gs1)", P1.ns1),
         ("Carrier Speed", P1.n_g1_carrier),
         ("1st Ring Gear Speed (Gr1)", P1.n_g1_ring1),
         ("Planet Gear Speed (Gp1,Gp2)", P1.n_g1_planet),
         ("2nd Ring Gear Speed (Gr2)", 0.0)]))
    lines.append(_speed_lines(
        "### Speed (Carrier Fixed, Ring2 Output)",
        [("Input Gear Speed (Gs1)", P1.ns1),
         ("Carrier Speed", 0.0),
         ("1st Ring Gear Speed (Gr1)", P1.n_g2_ring1),
         ("Planet Gear Speed (Gp1,Gp2)", P1.n_g2_planet),
         ("2nd Ring Gear Speed (Gr2)", P1.n_g2_ring2)]))
    lines.extend(P1.efficiency_markdown_lines())
    lines.append("### Size\n")
    lines.append("* Sun1 = " + str(P1.ds1) + " [mm],  " + str(P1.zs1) + " [ea]\n")
    lines.append("* Planet1 = " + str(P1.dp1) + " [mm],  " + str(P1.zp1) + " [ea]\n")
    lines.append("* Ring1 = " + str(P1.dr1) + " [mm],  " + str(P1.zr1) + " [ea]\n")
    lines.append("* Sun2 (Not considered) = " + str(P1.ds2) + " [mm],  " + str(P1.zs2) + " [ea]\n")
    lines.append("* Planet2 = " + str(P1.dp2) + " [mm],  " + str(P1.zp2) + " [ea]\n")
    lines.append("* Ring2 = " + str(P1.dr2) + " [mm],  " + str(P1.zr2) + " [ea]\n")
    lines.append("* Radius of Carrier = " + str(P1.dc / 2) + " [mm]\n")
    lines.append("* Number of Planets = " + str(P1.num_planets) + " [ea]\n\n")


def _append_simple(lines: list[str]) -> None:
    lines.append("## Simple Planetary Gear Set\n\n")
    lines.append("### Ratio\n")
    lines.append("* Ratio (Sun-Planet1) = " + str(P1.gp1s) + "\n")
    lines.append("* Ratio (Total, Carrier Output) (1-stage) = " + str(P1.g3) + "\n")
    lines.append("* Ratio (Total, Carrier Output) (2-stages) = " + str(P1.g3 ** 2) + "\n")
    lines.append("* Ratio (Total, Carrier Output) (3-stages) = " + str(P1.g3 ** 3) + "\n")
    lines.append("* Ratio (Total, Ring1 Output) (1-stage) = " + str(P1.g4) + "\n")
    lines.append("* Ratio (Total, Ring1 Output) (2-stages) = " + str(P1.g4 ** 2) + "\n")
    lines.append("* Ratio (Total, Ring1 Output) (3-stages) = " + str(P1.g4 ** 3) + "\n\n")
    lines.append(_speed_lines(
        "### Speed (Carrier Fixed, Ring1 Output)",
        [("Input Gear Speed (Gs1)", P1.n_cf_sun),
         ("Carrier Speed", P1.n_cf_carrier),
         ("Ring Gear Speed (Gr1)", P1.n_cf_ring),
         ("Planet Gear Speed (Gp1)", P1.n_cf_planet)]))
    lines.append(_speed_lines(
        "### Speed (Ring1 Fixed, Carrier Output)",
        [("Input Gear Speed (Gs1)", P1.n_rf_sun),
         ("Carrier Speed", P1.n_rf_carrier),
         ("Ring Gear Speed (Gr1)", P1.n_rf_ring),
         ("Planet Gear Speed (Gp1)", P1.n_rf_planet)]))
    lines.extend(P1.efficiency_markdown_lines())
    lines.append("### Size\n")
    lines.append("* Sun1 = " + str(P1.ds1) + " [mm],  " + str(P1.zs1) + " [ea]\n")
    lines.append("* Planet1 = " + str(P1.dp1) + " [mm],  " + str(P1.zp1) + " [ea]\n")
    lines.append("* Ring1 = " + str(P1.dr1) + " [mm],  " + str(P1.zr1) + " [ea]\n")
    lines.append("* Radius of Carrier = " + str(P1.dc / 2) + " [mm]\n")
    lines.append("* Number of Planets = " + str(P1.num_planets) + " [ea]\n\n")


def _append_gear_specs(lines: list[str]) -> None:
    for name in (GEAR_ORDER[:3] + GEAR_ORDER[4:]
                 if P1.is_wolfrom else GEAR_ORDER[:3]):
        gear = gears[name]
        is_ring = name in RING_GEARS
        teeth_label = f"-{round(gear.teeth, 6)}" if is_ring else f"{round(gear.teeth, 6)}"
        lines.append(f"### {name}\n")
        lines.append(f"* Module = {gear.module} [mm]\n")
        lines.append(f"* Pressure Angle = {gear.pressure_angle} [deg]\n")
        lines.append(f"* Teeth Number = {teeth_label} [ea]\n")
        lines.append(f"* Offset Factor = {gear.shift_factor}\n")
        lines.append(f"* Offset = {gear.shift_factor * gear.module} [mm]\n")
        lines.append(f"* Backlash Factor = {gear.backlash_factor}\n")
        lines.append(f"* Backlash = {gear.backlash_factor * gear.module} [mm]\n")
        lines.append(f"* Addendum Factor = {gear.addendum_factor}\n")
        lines.append(f"* Addendum = {gear.addendum_factor * gear.module} [mm]\n")
        lines.append(f"* Dedendum Factor = {gear.dedendum_factor}\n")
        lines.append(f"* Dedendum = {gear.dedendum_factor * gear.module} [mm]\n")
        lines.append(f"* Total Tooth Height = {(gear.addendum_factor + gear.dedendum_factor) * gear.module} [mm]\n")
        lines.append(f"* Base Circle Dia = {gear.module * gear.teeth * np.cos(np.deg2rad(gear.pressure_angle))} [mm]\n")
        lines.append(f"* Pitch Circle Dia = {gear.module * gear.teeth} [mm]\n")
        lines.append(f"* Offset Circle Dia = {2 * gear.module * (gear.teeth / 2 + gear.shift_factor)} [mm]\n")
        lines.append(f"* Root Circle Dia = {2 * gear.module * (gear.teeth / 2 + gear.shift_factor - gear.dedendum_factor)} [mm]\n")
        lines.append(f"* Outer Circle Dia = {2 * gear.module * (gear.teeth / 2 + gear.shift_factor + gear.addendum_factor)} [mm]\n\n")


def _compose_report_markdown() -> str:
    """Compose the full Markdown report string for the current calculation."""
    lines: list[str] = []
    lines.append("# PGS - Planetary Gear Sizing Program\n\n")
    scope = "Total" if P1.is_wolfrom else "Stage1"
    lines.append(f"![](./Cycloid_{scope}.png)\n")
    lines.append(f"![](./Involute_{scope}.png)\n\n")
    _append_checks(lines)
    _append_inputs(lines)
    if P1.is_wolfrom:
        _append_wolfrom(lines)
    else:
        _append_simple(lines)
    _append_gear_specs(lines)
    return "".join(lines)


def build_report(base_dir: str | None = None) -> None:
    """Compose the Markdown report and render it into the Result textbox."""
    global report_markdown
    report_markdown = _compose_report_markdown()
    if _is_tk_text(textbox):
        _render_markdown(textbox, report_markdown, base_dir=base_dir)
    else:
        textbox.delete("0.0", "end")
        textbox.insert("0.0", report_markdown)
    if result_search_var is not None:
        _update_result_search(jump_first=True)


def _render_saved_readme(out_dir: str) -> None:
    """Read ``out_dir/README.md`` and render it into the Result textbox."""
    global report_markdown
    readme_path = os.path.join(out_dir, "README.md")
    with open(readme_path, encoding="utf-8") as f:
        saved_md = f.read()
    report_markdown = saved_md
    if _is_tk_text(textbox):
        _render_markdown(textbox, saved_md, base_dir=out_dir)
    else:
        textbox.delete("0.0", "end")
        textbox.insert("0.0", saved_md)
    if result_search_var is not None:
        _update_result_search(jump_first=True)


def _save_and_show_run_result(
    out_dir: str,
    *,
    progress: _ProgressTracker | None = None,
) -> None:
    """Save only README.md and its linked summary PNGs into ``out_dir`` and render."""
    global report_markdown
    os.makedirs(out_dir, exist_ok=True)
    report_markdown = _compose_report_markdown()
    with open(os.path.join(out_dir, "README.md"), "w", encoding="utf-8") as f:
        f.write(report_markdown)
    if progress is not None:
        progress.update("Saved README.md", advance=1)
    save_summary_pngs(out_dir, progress=progress)
    if progress is not None:
        progress.update("Rendering report...")
    _render_saved_readme(out_dir)
    if progress is not None:
        progress.update("Report rendered", advance=1)


def _save_and_show_result(
    out_dir: str,
    *,
    progress: _ProgressTracker | None = None,
) -> None:
    """Save all outputs into ``out_dir`` and render its saved README.md."""
    global report_markdown
    report_markdown = _compose_report_markdown()
    save_output(out_dir, progress=progress)
    save_pngs(out_dir, progress=progress)
    if progress is not None:
        progress.update("Rendering report...")
    _render_saved_readme(out_dir)
    if progress is not None:
        progress.update("Report rendered", advance=1)


# --------------------------------------------------------------- file output
def _gear_csv_rows(name: str, gear: GPG) -> list[tuple[str, object]]:
    is_ring = name in RING_GEARS
    return [
        ("parameter", "value"),
        ("m", gear.module),
        ("z", -round(gear.teeth, 6) if is_ring else round(gear.teeth, 6)),
        ("alpha", gear.pressure_angle),
        ("x", -gear.shift_factor if is_ring else gear.shift_factor),
        ("b", -gear.backlash_factor if is_ring else gear.backlash_factor),
        ("a", gear.dedendum_factor if is_ring else gear.addendum_factor),
        ("d", gear.addendum_factor if is_ring else gear.dedendum_factor),
        ("c", gear.hob_tip_radius_factor),
        ("e", gear.tooth_tip_radius_factor),
        ("x_0", gear.x0),
        ("y_0", gear.y0),
        ("seg_circle", gear.seg_circle),
        ("seg_involute", gear.seg_involute),
        ("seg_edge_r", gear.seg_edge_round),
        ("seg_root_r", gear.seg_root_round),
        ("seg_outer", gear.seg_outer),
        ("seg_root", gear.seg_root),
        ("scale", DEFAULT_SCALE),
    ]


def _generate_fgpg2_results(folder: str, profile: str = "involute") -> None:
    """Regenerate Result.csv/.dxf/Result1.png/Result2.png for one gear.

    Runs the ported FGPG2 generator in-process on the gear's ``Inputs.csv``
    (identical to ``python FGPG2_CLI.py <gear>/Inputs.csv <profile>``), so the
    four result files land next to the input CSV.
    """
    csv_path = os.path.abspath(folder + "/Inputs.csv")
    p = FGPG2_CLI.load_params(csv_path)
    p = replace(p, profile=profile)
    FGPG2_CLI.generate(p, folder)


def save_output(
    out_dir: str,
    *,
    progress: _ProgressTracker | None = None,
) -> None:
    """Write the Markdown report, model CSV and per-gear results."""
    os.makedirs(out_dir, exist_ok=True)
    md_content = report_markdown if report_markdown else textbox.get("0.0", "end")
    with open(out_dir + "/README.md", "w", encoding="utf-8") as f:
        f.write(md_content)
    _write_input_model_csv(out_dir + "/model.csv")
    if progress is not None:
        progress.update("Saved README.md & model.csv", advance=1)
    # Gear folders: the Stage-1 gears always, Stage-2 Gp2/Gr2 for the Wolfrom
    # type only.  Gs2 is never exported.
    names = GEAR_ORDER[:3] + GEAR_ORDER[4:] if P1.is_wolfrom else GEAR_ORDER[:3]
    for name in names:
        folder = out_dir + "/" + name
        os.makedirs(folder, exist_ok=True)
        _write_gear_csv(folder + "/Inputs.csv", name)
        # Per-profile result subfolders: Involute/ and Cycloid/ carry FGPG2's
        # Result.csv/.dxf/Result1.png/Result2.png for the matching profile.
        for profile in ("involute", "cycloid"):
            if progress is not None:
                progress.update(f"Generating {name} ({profile.capitalize()})...")
            sub = folder + "/" + profile.capitalize()
            os.makedirs(sub, exist_ok=True)
            _write_gear_csv(sub + "/Inputs.csv", name)
            _generate_fgpg2_results(sub, profile)
            if progress is not None:
                progress.update(
                    f"Generated {name} ({profile.capitalize()})", advance=1
                )


def _write_gear_csv(path: str, name: str) -> None:
    with open(path, "w") as f:
        for key, value in _gear_csv_rows(name, gears[name]):
            f.write(f"{key},{value}\n")


# ----------------------------------------------------- input model CSV (Save)
# The full header of the exported "model.csv".  It mirrors the
# reference "Input_data.csv": six gear rows (Sun/Planet/Annulus per stage)
# followed by a single ETC/Carrier row carrying the carrier, shaft and frame
# dimensions.
INPUT_MODEL_HEADER = (
    "Group,Component,Helix Angle (deg),Normal Module (mm),"
    "Normal Pressure Angle (deg),Center Distance (mm),Number of Planets,"
    "Number of Teeth,Face Width (mm),Normal Profile Shift Coefficient,"
    "Quality Grade (ISO),Material,Gear Tooth Thickness Tolerance,"
    "Basic Rack Addendum Factor,Basic Rack Dedendum Factor,Edge Radius Factor,"
    "Carrier Pin Diameter (mm),Thickness of Carrier Input Side (mm),"
    "Thickness of Carrier Output Side (mm),Diameter of Input Shaft (mm),"
    "Frame Outer Diameter (mm)"
)


def _offset_circle_dia(gear: GPG) -> float:
    """Return the gear's offset-circle diameter in mm."""
    return 2 * gear.module * (gear.teeth / 2 + gear.shift_factor)


def _pitch_circle_dia(gear: GPG) -> float:
    """Return the gear's pitch-circle diameter in mm (always positive)."""
    return abs(gear.teeth) * gear.module


def _input_model_gear_row(group: str, component: str, gear: GPG,
                          center_dist: float, planets: int) -> list[object]:
    """Compose one gear data row for the input-model CSV.

    The gear objects have already run ``calc()``, so ring gears (Annulus)
    carry a negative shift internally; the shift is negated back here to
    match the design value, and the addendum/dedendum factors are swapped
    back to their original magnitudes.
    """
    is_ring = component == "Annulus"
    return [
        group, component,
        0,                              # Helix Angle (deg) — kept as-is
        gear.module,                    # Normal Module (mm)
        gear.pressure_angle,            # Normal Pressure Angle (deg)
        center_dist,                    # Center Distance = Radius of Carrier
        planets,                        # Number of Planets
        gear.teeth,                     # Number of Teeth
        gear.module * 5,                # Face Width (mm) ≈ 5x module
        -gear.shift_factor if is_ring else gear.shift_factor,  # Normal shift
        7 if is_ring else 6,          # Quality Grade (ISO): Sun/Planet=6, Annulus=7
        "Default",                      # Material — kept as-is
        "g26",                          # Tooth Thickness Tolerance — kept as-is
        gear.dedendum_factor if is_ring else gear.addendum_factor,   # Addendum
        gear.addendum_factor if is_ring else gear.dedendum_factor,   # Dedendum
        # Edge Radius Factor = Hob end radius C.  calc() swaps the hob and
        # tooth-tip radius factors on internal (ring) gears, so the original
        # C lives in tooth_tip_radius_factor for a ring.
        gear.tooth_tip_radius_factor if is_ring else gear.hob_tip_radius_factor,
        "", "", "", "", "",             # carrier/shaft/frame only on ETC row
    ]


def _input_model_csv_rows() -> list[list[object]]:
    """Build the rows of the input-model CSV for the current design."""
    center_dist = P1.dc / 2.0
    planets = P1.num_planets

    rows = [
        _input_model_gear_row("Planetary Gear Set 1", "Sun",
                              gears["Gs1"], center_dist, planets),
        _input_model_gear_row("Planetary Gear Set 1", "Planet",
                              gears["Gp1"], center_dist, planets),
        _input_model_gear_row("Planetary Gear Set 1", "Annulus",
                              gears["Gr1"], center_dist, planets),
    ]
    stage2 = P1.is_wolfrom
    if stage2:
        rows.append(_input_model_gear_row("Planetary Gear Set 2", "Planet",
                                          gears["Gp2"], center_dist, planets))
        rows.append(_input_model_gear_row("Planetary Gear Set 2", "Annulus",
                                          gears["Gr2"], center_dist, planets))

    # Carrier pin: the smaller of the planet pitch-circle dia minus ten
    # times the matching planet's module (fractional part truncated).
    planets_gears = [gears["Gp1"]] + ([gears["Gp2"]] if stage2 else [])
    pin_gear = min(planets_gears, key=_pitch_circle_dia)
    carrier_pin = math.floor(
        _pitch_circle_dia(pin_gear) - 10 * pin_gear.module)

    # Carrier thicknesses: same as the planet Face Width of each stage.
    thick_in = gears["Gp1"].module * 5
    thick_out = (gears["Gp2"].module if stage2 else gears["Gp1"].module) * 5

    # Input shaft: Sun pitch-circle dia minus ten times the Sun module
    # (fractional part truncated).
    shaft_dia = math.floor(
        _pitch_circle_dia(gears["Gs1"]) - 10 * gears["Gs1"].module)

    # Frame outer diameter: the larger of the ring pitch-circle dia plus
    # forty times the matching ring's module (fractional part truncated).
    rings_gears = [gears["Gr1"]] + ([gears["Gr2"]] if stage2 else [])
    frame_gear = max(rings_gears, key=_pitch_circle_dia)
    frame_outer = math.floor(
        _pitch_circle_dia(frame_gear) + 40 * frame_gear.module)

    rows.append(["ETC", "Carrier",
                 "", "", "", "", "", "", "", "", "", "", "", "", "", "",
                 carrier_pin, thick_in, thick_out, shaft_dia, frame_outer])
    return rows


def _write_input_model_csv(path: str) -> None:
    """Write the input-model CSV mirroring ``Input_data.csv``."""
    with open(path, "w", newline="") as f:
        f.write(INPUT_MODEL_HEADER + "\n")
        for row in _input_model_csv_rows():
            f.write(",".join("" if v == "" else str(v) for v in row) + "\n")


# ---------------------------------------------------------------- callbacks
def toggle_simple_fields() -> None:
    """Disable Wolfrom-only fields when the Simple Type is selected.

    For the Simple type the stage-2 inputs (m2, Gp2.X, Zr2, Zp2) are
    hidden and only the stage-1 plot options stay usable.  The Ring1
    tooth-count input (Zr1) stays available for both types.
    """
    is_simple = entries["TYPE"].get() == "Simple"
    if is_simple:
        entries["Zp2"].grid_remove()
        entries["Zp2_LABEL"].grid_remove()
        entries["Zr2"].grid_remove()
        entries["Zr2_LABEL"].grid_remove()
        entries["Zr1"].grid()
        entries["Zr1_LABEL"].grid()
    else:
        entries["Zp2"].grid()
        entries["Zp2_LABEL"].grid()
        entries["Zr2"].grid()
        entries["Zr2_LABEL"].grid()
        entries["Zr1"].grid()
        entries["Zr1_LABEL"].grid()
    state = "disabled" if is_simple else "normal"
    entries["m2"].configure(state=state)
    entries["Gp2X"].configure(state=state)
    entries["mu_b_c"].configure(state=state)
    plot_cb = entries["PlotOption"]
    if is_simple:
        plot_cb.configure(values=PLOT_OPTIONS_SIMPLE)
        if plot_cb.get() not in PLOT_OPTIONS_SIMPLE:
            plot_cb.set("Stage1")
    else:
        plot_cb.configure(values=PLOT_OPTIONS)


# Parameter-key mapping used by the Load button: the "## Input Parameters"
# section of a saved Result/README.md is read back to refill the input
# widgets.  The report labels (e.g. "Module1") are ignored; the keys match
# the DEFAULT_INPUTS / PLANETARY_INPUTS keys.
REPORT_KEY_TO_ENTRY = {
    "TYPE": "TYPE",
    "m1": "m1",
    "m2": "m2",
    "Np": "Np",
    "Zr2": "Zr2",
    "Zp2": "Zp2",
    "Zr1": "Zr1",
    "Zs1": "Zs1",
    "ns1": "Ns1",
    "Ns1": "Ns1",
    "Gs1.X": "Gs1X",
    "Gp1.X": "Gp1X",
    "Gp2.X": "Gp2X",
    "B": "B",
    "A": "A",
    "D": "D",
    "alpha": "alpha",
    "C": "C",
    "E": "E",
    "mu": "mu",
    "mu_b_in": "mu_b_in",
    "mu_b_p": "mu_b_p",
    "mu_b_c": "mu_b_c",
    "mu_b_out": "mu_b_out",
    "zeta_s": "seal",
    "kc": "churn",
}


def _parse_input_parameters(md_text: str) -> dict[str, str]:
    """Extract key -> value pairs from the '## Input Parameters' section."""
    values: dict[str, str] = {}
    in_inputs = False
    for line in md_text.splitlines():
        if line.startswith("## "):
            if line.strip() == "## Input Parameters":
                in_inputs = True
            elif in_inputs:
                break
        elif in_inputs and line.startswith("* "):
            m = re.match(r"^\* .*?, ([\w.]+) = (.*)$", line.strip())
            if m:
                values[m.group(1)] = m.group(2).strip()
    return values


def _set_entry_text(key: str, value: str) -> None:
    """Replace the text of an entry widget (clear then insert)."""
    w = entries[key]
    w.delete(0, "end")
    w.insert(0, value)


def _apply_report_values(values: dict[str, str]) -> bool:
    """Refill the input widgets from a report ``## Input Parameters`` map.

    Returns False when the map carries no applicable parameter.  Ring tooth
    counts are stored negative in the report, so they are loaded back as the
    positive numbers expected by the input fields.
    """
    applied = False
    # Backward compatibility: legacy reports carry a single ``mu_b`` key;
    # apply it to any separated bearing field not explicitly present.
    legacy_mu_b = values.get("mu_b")
    if legacy_mu_b is not None:
        try:
            legacy_num = _parse_loss_param(legacy_mu_b, "mu_b")
        except ValueError:
            legacy_num = None
        if legacy_num is not None:
            for bkey in BEARING_ENTRY_KEYS:
                if bkey not in values and bkey in entries:
                    entries[bkey].set(_format_loss_option(bkey, legacy_num))
                    applied = True
    for key, value in values.items():
        entry_key = REPORT_KEY_TO_ENTRY.get(key)
        if entry_key is None or entry_key not in entries:
            continue
        applied = True
        if entry_key == "TYPE":
            try:
                code = int(value.split(",")[0].strip())
            except ValueError:
                continue
            label = TYPE_CODE_TO_LABEL.get(code)
            if label is None:
                continue
            entries["TYPE"].set(label)
        elif entry_key in ("Zr1", "Zr2"):
            try:
                number = abs(float(value))
            except ValueError:
                continue
            _set_entry_text(entry_key, str(number))
        elif entry_key in LOSS_PRESETS:
            try:
                number = _parse_loss_param(value, entry_key)
            except ValueError:
                continue
            entries[entry_key].set(_format_loss_option(entry_key, number))
        else:
            _set_entry_text(entry_key, value)
    return applied


def load_parameters_from_file(path: str) -> bool:
    """Load the inputs from a report file's ``## Input Parameters`` section.

    Reads ``path`` and refills the input widgets; returns False when the
    file cannot be read or carries no applicable parameter.  Used by the
    Load button and by command-line startup (``python design.py <file>``).
    """
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return False
    values = _parse_input_parameters(text)
    return _apply_report_values(values)


def button_load_callback() -> None:
    """Load the inputs back from a saved Result README.md file.

    Opens a file picker for a "README.md" result file, reads the
    "## Input Parameters" section and refills the input widgets, then
    runs the calculation exactly like the Run button.
    """
    if _is_busy:
        return
    path = filedialog.askopenfilename(
        title="Select the README.md result file to load parameters from",
        filetypes=[("README.md", "README.md"),
                   ("Markdown files", "*.md"),
                   ("All files", "*.*")])
    if not path:
        return
    if not load_parameters_from_file(path):
        messagebox.showwarning(
            "Load Warning",
            "The selected file does not contain a '## Input Parameters' "
            "section.")
        return
    toggle_simple_fields()
    button_run_callback()


def button_run_callback() -> None:
    """Compute, save README.md & summary PNGs to ``result/``, render and plot."""
    global _is_busy
    if _is_busy:
        return
    _is_busy = True
    _set_action_buttons_state("disabled")
    progress = _ProgressTracker(1)
    try:
        progress.update("Reading parameters...")
        read_parameters()
        progress.total = _estimate_run_steps()
        progress.update("Calculating gear geometry...")
        run_calc(progress=progress)
        _save_and_show_run_result(DEFAULT_RESULT_DIR, progress=progress)
        print("Result summary saved in " + DEFAULT_RESULT_DIR)
        progress.update("Opening plot window...")
        plot_pgs()
        _set_action_buttons_state("normal")
        progress.finish("Done")
    except Exception as exc:
        _set_action_buttons_state("normal")
        progress.fail("Error")
        messagebox.showerror("Run Error", str(exc))
    finally:
        _is_busy = False
        _set_action_buttons_state("normal")


def button_animation_callback() -> None:
    """Open a popup window animating all gearbox elements at calculated ratios."""
    global _animation_window
    if _is_busy:
        return
    try:
        read_parameters()
        _calc_gears_only()
        plot_opt = entries["PlotOption"].get()
        initial_view = (
            plot_opt if plot_opt in ("Total", "Stage1", "Stage2") else None
        )
        if _animation_window is not None and _animation_window.is_alive():
            _animation_window.close()

        def _clear_ref() -> None:
            global _animation_window
            _animation_window = None

        _animation_window = animation.open_animation_window(
            app,
            P1,
            _active_profile_sets(),
            initial_view=initial_view,
            on_close=_clear_ref,
        )
    except Exception as exc:
        messagebox.showerror(
            "Animation Error",
            f"Could not start animation:\n{exc}",
        )


def button_tip_check_callback() -> None:
    """Run kinematic tip-interference check and open zoomed inspection plots."""
    if _is_busy:
        return
    read_parameters()
    run_calc()
    build_report()
    plot_tip_check(only_if_fail=False, show=True)


def button_save_callback() -> None:
    """Save the result files into a user-selected folder.

    The Save button is disabled for the duration of the operation.  Asks for
    the parent directory first, then creates a ``Result`` folder under it and
    writes the report, per-gear CSV/DXF/PNG files and the plot PNGs.  Also
    (re)runs the calculation so the saved files always match the inputs.
    """
    global _is_busy
    if _is_busy:
        return
    folder = filedialog.askdirectory(
        title="Select the folder where the Result directory will be created")
    if not folder:
        return
    _is_busy = True
    _set_action_buttons_state("disabled")
    progress = _ProgressTracker(1)
    try:
        out_dir = os.path.join(folder, "Result")
        progress.update("Reading parameters...")
        read_parameters()
        progress.total = _estimate_export_steps(include_plot=False)
        progress.update("Calculating gear geometry...")
        run_calc(progress=progress)
        _save_and_show_result(out_dir, progress=progress)
        print("Result files saved in " + out_dir)
        _set_action_buttons_state("normal")
        progress.finish("Saved")
    except Exception as exc:
        _set_action_buttons_state("normal")
        progress.fail("Error")
        messagebox.showerror("Save Error", str(exc))
    finally:
        _is_busy = False
        _set_action_buttons_state("normal")


def button_exit_callback() -> None:
    print("button_exit pressed")
    if _animation_window is not None and _animation_window.is_alive():
        _animation_window.close()
    plt.close("all")
    exit()


# --------------------------------------------------------------------- GUI
def init_parameters() -> None:
    """Populate every input widget with its default value."""
    for key, default in DEFAULT_INPUTS.items():
        w = entries[key]
        if key == "TYPE":
            w.set(TYPE_CODE_TO_LABEL[default])
        elif key == "PlotOption":
            w.set(PLOT_CODE_TO_LABEL[default])
        elif key in LOSS_PRESETS:
            w.set(_format_loss_option(key, default))
        elif hasattr(w, "set"):        # ttk.Combobox
            w.set(str(default))
        else:                          # ttk.Entry
            w.insert(0, str(default))


def _configure_style(style: ttk.Style, title_font, section_font) -> None:
    """Apply a flat, modern colour palette on top of the clam theme."""
    style.configure("App.TFrame", background=BG)
    style.configure("Card.TFrame", background=CARD)

    style.configure("TLabel", background=BG, foreground=FG)
    style.configure("Card.TLabel", background=BG, foreground=FG)
    style.configure("CardMuted.TLabel", background=BG, foreground=MUTED)
    style.configure("Muted.TLabel", background=BG, foreground=MUTED)
    style.configure("Title.TLabel", background=BG, foreground=ACCENT,
                    font=title_font)
    style.configure("Section.TLabel", background=BG, foreground=ACCENT,
                    font=section_font)

    style.configure("TLabelframe", background=BG, bordercolor=BORDER,
                    relief="solid", borderwidth=1)
    style.configure("TLabelframe.Label", background=BG, foreground=ACCENT,
                    font=section_font)

    style.configure("TEntry", fieldbackground="white", foreground=FG,
                    bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                    borderwidth=1, padding=2)
    style.map("TEntry", bordercolor=[("focus", ACCENT)],
              lightcolor=[("focus", ACCENT)], darkcolor=[("focus", ACCENT)])

    style.configure("TCombobox", fieldbackground="white", foreground=FG,
                    bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                    borderwidth=1, padding=2, arrowcolor=ACCENT)
    style.map("TCombobox",
              fieldbackground=[("readonly", "white")],
              foreground=[("readonly", FG)],
              bordercolor=[("focus", ACCENT)],
              lightcolor=[("focus", ACCENT)],
              darkcolor=[("focus", ACCENT)])

    style.configure("TButton", background=NEUTRAL, foreground=FG, borderwidth=0,
                    focusthickness=0, padding=(10, 4))
    style.map("TButton",
              background=[("disabled", "#f3f4f6"), ("active", NEUTRAL_DARK),
                          ("pressed", NEUTRAL_DARK)],
              foreground=[("disabled", "#9ca3af")])

    style.configure("Small.TButton", background=NEUTRAL, foreground=FG,
                    borderwidth=0, focusthickness=0, padding=(5, 2))
    style.map("Small.TButton",
              background=[("disabled", "#f3f4f6"), ("active", NEUTRAL_DARK),
                          ("pressed", NEUTRAL_DARK)],
              foreground=[("disabled", "#9ca3af")])

    style.configure("Accent.TButton", background=ACCENT, foreground="white",
                    borderwidth=0, focusthickness=0, padding=(14, 4))
    style.map("Accent.TButton",
              background=[("disabled", "#93c5fd"), ("active", ACCENT_DARK),
                          ("pressed", ACCENT_DARK)],
              foreground=[("disabled", "#eff6ff")])

    style.configure("Danger.TButton", background=DANGER, foreground="white",
                    borderwidth=0, focusthickness=0, padding=(10, 4))
    style.map("Danger.TButton",
              background=[("active", DANGER_DARK), ("pressed", DANGER_DARK)])

    style.configure("Accent.Horizontal.TProgressbar",
                    background=ACCENT, troughcolor=NEUTRAL,
                    bordercolor=BORDER, lightcolor=ACCENT, darkcolor=ACCENT,
                    thickness=12)

    style.configure("TScrollbar", background=CARD, troughcolor=BG,
                    bordercolor=BG, arrowcolor=MUTED, relief="flat")


def _build_field(parent, row, key, label_text, hint_text, hint_below) -> int:
    """Add one labelled input row inside ``parent``; return next free row."""
    lbl = ttk.Label(parent, text=label_text, style="Card.TLabel")
    lbl.grid(row=row, column=0, padx=(0, PADX), pady=PADY, sticky="e")
    entries[key + "_LABEL"] = lbl
    if key == "TYPE":
        entry = ttk.Combobox(parent, values=TYPE_LABELS,
                             width=20, state="readonly")
    elif key in LOSS_PRESET_OPTIONS:
        entry = ttk.Combobox(parent, values=LOSS_PRESET_OPTIONS[key],
                             width=20, state="normal")
    else:
        entry = ttk.Entry(parent)
    entry.grid(row=row, column=1, padx=PADX, pady=PADY, sticky="ew")
    entries[key] = entry
    if key == "TYPE":
        entry.bind("<<ComboboxSelected>>", lambda _e: toggle_simple_fields())
    if hint_text:
        if hint_below:
            hint = ttk.Label(parent, text=hint_text, style="CardMuted.TLabel")
            hint.grid(row=row + 1, column=0, columnspan=2, padx=PADX,
                      pady=(0, PADY), sticky="w")
            return row + 2
        ttk.Label(parent, text=hint_text, style="CardMuted.TLabel").grid(
            row=row, column=2, padx=PADX, pady=PADY, sticky="w")
    return row + 1


def _build_section(parent, title, fields) -> None:
    """Build a labelled card containing the given input fields."""
    lf = ttk.LabelFrame(parent, text=title, padding=PAD)
    lf.grid(sticky="ew", pady=(0, PAD))
    lf.columnconfigure(1, weight=1)
    row = 0
    for key, label_text, hint_text, hint_below in fields:
        row = _build_field(lf, row, key, label_text, hint_text, hint_below)


def _apply_current_search_highlight() -> None:
    """Highlight the active search match and scroll it into view."""
    if not hasattr(textbox, "tag_remove"):
        return
    textbox.tag_remove("search_current", "1.0", "end")
    if 0 <= result_search_index < len(result_search_matches):
        start, end = result_search_matches[result_search_index]
        textbox.tag_add("search_current", start, end)
        textbox.see(start)
        if result_search_status is not None:
            result_search_status.configure(
                text=f"{result_search_index + 1}/{len(result_search_matches)}",
                foreground=MUTED,
            )


def _update_result_search(*, jump_first: bool = True) -> None:
    """Recompute all keyword matches in the Result textbox and highlight them."""
    global result_search_matches, result_search_index
    if not hasattr(textbox, "tag_remove"):
        return
    textbox.tag_remove("search_match", "1.0", "end")
    textbox.tag_remove("search_current", "1.0", "end")
    result_search_matches = []
    result_search_index = -1

    query = result_search_var.get().strip() if result_search_var is not None else ""
    if not query:
        if result_search_status is not None:
            result_search_status.configure(text="", foreground=MUTED)
        return

    start = "1.0"
    qlen = len(query)
    while True:
        pos = textbox.search(query, start, stopindex="end", nocase=True)
        if not pos:
            break
        end = f"{pos}+{qlen}c"
        textbox.tag_add("search_match", pos, end)
        result_search_matches.append((pos, end))
        start = end

    if result_search_matches:
        result_search_index = 0 if jump_first else min(
            max(0, result_search_index), len(result_search_matches) - 1
        )
        _apply_current_search_highlight()
    elif result_search_status is not None:
        result_search_status.configure(text="0/0", foreground=DANGER)


def _step_result_search(delta: int) -> str:
    """Move to the next (+1) or previous (-1) keyword match in Result."""
    global result_search_index
    if not result_search_matches:
        _update_result_search(jump_first=True)
        return "break"
    result_search_index = (result_search_index + delta) % len(result_search_matches)
    _apply_current_search_highlight()
    return "break"


def _clear_result_search(_event=None) -> str:
    """Clear the Result keyword search box and remove highlights."""
    if result_search_var is not None:
        result_search_var.set("")
    return "break"


def _focus_result_search(_event=None) -> str:
    """Focus the Result keyword search entry and select its text (Ctrl+F)."""
    if result_search_entry is not None:
        result_search_entry.focus_set()
        result_search_entry.selection_range(0, "end")
    return "break"


# -------------------------------------------------------- markdown renderer
WELCOME_MARKDOWN = (
    "# PGS - Planetary Gear Sizing Program\n\n"
    "[https://github.com/dymaxionkim/PGS](https://github.com/dymaxionkim/PGS)\n\n"
    "---\n\n"
    "1. Input Parameters.\n"
    "2. Press **Run** to compute, save to `result/` & plot, or **Save** to export "
    "into a folder you choose.\n"
)

_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)(?:\s+#+\s*)?$")
_MD_HR_RE = re.compile(r"^\s*(?:[-*_]\s*){3,}$")
_MD_UL_RE = re.compile(r"^([ \t]*)[*+-]\s+(.*)$")
_MD_OL_RE = re.compile(r"^([ \t]*)(\d+)\.\s+(.*)$")
_MD_QUOTE_RE = re.compile(r"^\s*>\s?(.*)$")
_MD_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_MD_BLOCK_IMG_RE = re.compile(r"^\s*!\[([^\]]*)\]\(([^)]+)\)\s*$")
_MD_TABLE_SEP_RE = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$")
_MD_INLINE_RE = re.compile(
    r"\\([\\`*_{}\[\]()#+\-.!~|])"                 # 1: escaped char
    r"|`([^`]+)`"                                  # 2: inline code
    r"|!\[([^\]]*)\]\(([^)]+)\)"                   # 3,4: inline image
    r"|\[([^\]]+)\]\(([^)\s]+)\)"                  # 5,6: markdown link
    r"|\*\*\*([^*]+?)\*\*\*"                       # 7: bold + italic
    r"|\*\*([^*]+?)\*\*"                           # 8: bold (**)
    r"|(?<!\w)__([^_]+?)__(?!\w)"                  # 9: bold (__)
    r"|\*([^*\s](?:[^*]*?[^*\s])?)\*"              # 10: italic (*)
    r"|(?<!\w)_([^_\s](?:[^_]*?[^_\s])?)_(?!\w)"   # 11: italic (_)
    r"|~~([^~]+?)~~"                               # 12: strikethrough
    r"|(https?://[^\s<>)\]]+)"                     # 13: bare URL
)
_MD_BULLETS = ("•", "◦", "▪")


def _is_tk_text(widget: object) -> bool:
    """Return True when ``widget`` is a real Tkinter ``Text`` widget."""
    return isinstance(widget, tk.Text)


def _resize_md_rules(event) -> None:
    """Keep embedded horizontal-rule frames matched to the Text widget width."""
    w = event.widget
    rules = getattr(w, "_md_rules", None)
    if not rules:
        return
    target_w = max(40, event.width - 32)
    if getattr(w, "_md_last_rule_width", None) == target_w:
        return
    w._md_last_rule_width = target_w
    for rule in rules:
        if rule.winfo_exists():
            rule.configure(width=target_w)


def _configure_markdown_tags(widget: tk.Text) -> None:
    """Configure Markdown typography, layout, link and search tags on ``widget``."""
    widget._md_rules = []  # type: ignore[attr-defined]
    widget._md_images = []  # type: ignore[attr-defined]
    widget._md_link_tags = []  # type: ignore[attr-defined]
    widget._md_last_rule_width = None  # type: ignore[attr-defined]

    widget.tag_configure("md_h1", font=("Segoe UI", 14, "bold"),
                         foreground="#111827", spacing1=4, spacing3=2)
    widget.tag_configure("md_h2", font=("Segoe UI", 12, "bold"),
                         foreground=ACCENT, spacing1=12, spacing3=2)
    widget.tag_configure("md_h3", font=("Segoe UI", 11, "bold"),
                         foreground="#1e3a8a", spacing1=8, spacing3=2)
    widget.tag_configure("md_h4", font=("Segoe UI", 10, "bold"),
                         foreground="#374151", spacing1=6, spacing3=1)
    widget.tag_configure("md_h5", font=("Segoe UI", 9, "bold"),
                         foreground="#4b5563", spacing1=5, spacing3=1)
    widget.tag_configure("md_h6", font=("Segoe UI", 9, "bold"),
                         foreground=MUTED, spacing1=4, spacing3=1)
    widget.tag_configure("md_hr_line", font=("Segoe UI", 2),
                         spacing1=2, spacing3=6)
    widget.tag_configure("md_p", font=("Segoe UI", 10),
                         foreground=FG, spacing1=1, spacing3=4)

    for level, (m1, m2) in enumerate(((12, 24), (28, 40), (44, 56))):
        widget.tag_configure(f"md_li_{level}", lmargin1=m1, lmargin2=m2,
                             spacing1=1, spacing3=1)
    widget.tag_configure("md_bullet_0", foreground=ACCENT,
                         font=("Segoe UI", 10, "bold"))
    widget.tag_configure("md_bullet_1", foreground=MUTED,
                         font=("Segoe UI", 10))
    widget.tag_configure("md_bullet_2", foreground=MUTED,
                         font=("Segoe UI", 9))

    for level, (m1, m2) in enumerate(((12, 30), (28, 46), (44, 62))):
        widget.tag_configure(f"md_oli_{level}", lmargin1=m1, lmargin2=m2,
                             spacing1=1, spacing3=1)
    widget.tag_configure("md_ol_num", foreground=ACCENT,
                         font=("Segoe UI", 10, "bold"))

    widget.tag_configure("md_bold", font=("Segoe UI", 10, "bold"))
    widget.tag_configure("md_italic", font=("Segoe UI", 10, "italic"))
    widget.tag_configure("md_bold_italic", font=("Segoe UI", 10, "bold italic"))
    widget.tag_configure("md_strike", overstrike=True, foreground=MUTED)
    widget.tag_configure("md_code", font=("Consolas", 9),
                         background="#f1f5f9", foreground="#be123c")
    widget.tag_configure("md_heading_code", background="#f1f5f9",
                         foreground="#be123c")
    widget.tag_configure("md_link", foreground=ACCENT, underline=True)
    widget.tag_configure("md_image_badge", font=("Segoe UI", 9, "italic"),
                         foreground="#475569", background="#f1f5f9")
    widget.tag_configure("md_image_line", spacing1=3, spacing3=5)

    widget.tag_configure("md_quote", lmargin1=14, lmargin2=24,
                         background="#f8fafc", foreground="#475569",
                         spacing1=2, spacing3=2)
    widget.tag_configure("md_quote_bar", foreground=ACCENT,
                         font=("Segoe UI", 10, "bold"))
    widget.tag_configure("md_codeblock", font=("Consolas", 9),
                         background="#f8fafc", foreground="#0f172a",
                         lmargin1=12, lmargin2=12, rmargin=12,
                         spacing1=1, spacing3=1)
    widget.tag_configure("md_table_header", font=("Consolas", 9, "bold"),
                         background="#f1f5f9", foreground="#111827",
                         lmargin1=10, lmargin2=10, spacing1=2, spacing3=2)
    widget.tag_configure("md_table_row", font=("Consolas", 9),
                         background=CARD, foreground=FG,
                         lmargin1=10, lmargin2=10, spacing1=1, spacing3=1)
    widget.tag_configure("md_table_alt", font=("Consolas", 9),
                         background="#f9fafb", foreground=FG,
                         lmargin1=10, lmargin2=10, spacing1=1, spacing3=1)

    widget.tag_bind("md_link", "<Enter>",
                    lambda _e: widget.configure(cursor="hand2"))
    widget.tag_bind("md_link", "<Leave>",
                    lambda _e: widget.configure(cursor=""))

    widget.tag_configure("search_match", background="#fef08a", foreground=FG)
    widget.tag_configure("search_current", background="#f97316", foreground="#ffffff")
    widget.tag_raise("search_match")
    widget.tag_raise("search_current", "search_match")

    widget.bind("<Configure>", _resize_md_rules, add="+")
    widget.bind("<Button-1>", lambda _e: widget.focus_set(), add="+")

    def _select_all(_event=None) -> str:
        widget.tag_add("sel", "1.0", "end-1c")
        return "break"

    widget.bind("<Control-a>", _select_all)
    widget.bind("<Control-A>", _select_all)


def _insert_md_hr(widget: tk.Text, color: str = BORDER, height: int = 1) -> None:
    """Insert a full-width horizontal rule into ``widget``."""
    w = widget.winfo_width()
    width = max(40, w - 32) if w > 1 else 420
    rule = tk.Frame(widget, height=height, width=width,
                    background=color, borderwidth=0, highlightthickness=0)
    widget._md_rules.append(rule)  # type: ignore[attr-defined]
    widget.window_create("end", window=rule, stretch=False)
    widget.insert("end", "\n", ("md_hr_line",))


def _insert_md_link(widget: tk.Text, label: str, url: str,
                    base_tags: tuple[str, ...]) -> None:
    """Insert a styled, clickable hyperlink into ``widget``."""
    link_tags: list[str] = widget._md_link_tags  # type: ignore[attr-defined]
    tag = f"md_link_url_{len(link_tags)}"
    link_tags.append(tag)
    widget.insert("end", label, base_tags + ("md_link", tag))
    widget.tag_bind(tag, "<Button-1>",
                    lambda _e, target=url: webbrowser.open(target))


def _insert_md_inline(
    widget: tk.Text,
    text: str,
    base_tags: tuple[str, ...],
    *,
    is_heading: bool = False,
) -> None:
    """Parse inline Markdown spans in ``text`` and insert them into ``widget``."""
    pos = 0
    for m in _MD_INLINE_RE.finditer(text):
        if m.start() > pos:
            widget.insert("end", text[pos:m.start()], base_tags)
        if m.group(1) is not None:
            widget.insert("end", m.group(1), base_tags)
        elif m.group(2) is not None:
            code_tag = "md_heading_code" if is_heading else "md_code"
            widget.insert("end", m.group(2), base_tags + (code_tag,))
        elif m.group(4) is not None:
            alt, src = m.group(3), m.group(4)
            label = alt.strip() or os.path.basename(src.strip()) or src.strip()
            widget.insert("end", f" [Image: {label}] ",
                          base_tags + ("md_image_badge",))
        elif m.group(5) is not None:
            _insert_md_link(widget, m.group(5), m.group(6), base_tags)
        elif m.group(7) is not None:
            extra = () if is_heading else ("md_bold_italic",)
            widget.insert("end", m.group(7), base_tags + extra)
        elif m.group(8) is not None or m.group(9) is not None:
            content = m.group(8) if m.group(8) is not None else m.group(9)
            extra = () if is_heading else ("md_bold",)
            widget.insert("end", content, base_tags + extra)
        elif m.group(10) is not None or m.group(11) is not None:
            content = m.group(10) if m.group(10) is not None else m.group(11)
            extra = () if is_heading else ("md_italic",)
            widget.insert("end", content, base_tags + extra)
        elif m.group(12) is not None:
            widget.insert("end", m.group(12), base_tags + ("md_strike",))
        elif m.group(13) is not None:
            url = m.group(13)
            _insert_md_link(widget, url, url, base_tags)
        pos = m.end()
    if pos < len(text):
        widget.insert("end", text[pos:], base_tags)


def _insert_md_block_image(
    widget: tk.Text,
    alt: str,
    src: str,
    base_dir: str | None,
) -> None:
    """Render a block-level Markdown image (embedded if local file exists, else badge)."""
    src_clean = src.strip()
    img_path: str | None = None
    if os.path.isabs(src_clean) and os.path.isfile(src_clean):
        img_path = src_clean
    elif base_dir:
        candidate = os.path.normpath(os.path.join(base_dir, src_clean))
        if os.path.isfile(candidate):
            img_path = candidate

    if img_path is not None and Image is not None and ImageTk is not None:
        try:
            resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
            w = widget.winfo_width()
            max_w = min(max(240, w - 40), 420) if w > 1 else 360
            with Image.open(img_path) as im:
                im = im.copy()
                im.thumbnail((max_w, 360), resample)
                photo = ImageTk.PhotoImage(im)
            widget._md_images.append(photo)  # type: ignore[attr-defined]
            widget.image_create("end", image=photo)
            widget.insert("end", "\n", ("md_image_line",))
            return
        except Exception:
            pass

    label = alt.strip() or os.path.basename(src_clean) or src_clean
    widget.insert("end", f"  [Image: {label}]  ", ("md_image_badge", "md_image_line"))
    widget.insert("end", "\n", ("md_image_line",))


def _split_table_cells(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def _insert_md_table(widget: tk.Text, table_lines: list[str]) -> None:
    """Render a GFM pipe table into ``widget`` with aligned monospace columns."""
    header = _split_table_cells(table_lines[0])
    sep_cells = _split_table_cells(table_lines[1])
    rows = [_split_table_cells(r) for r in table_lines[2:]]
    ncols = max(len(header), *(len(r) for r in rows)) if rows else len(header)
    header += [""] * (ncols - len(header))
    aligns: list[str] = []
    for idx in range(ncols):
        cell = sep_cells[idx] if idx < len(sep_cells) else "---"
        left = cell.startswith(":")
        right = cell.endswith(":")
        aligns.append("center" if (left and right) else ("right" if right else "left"))
    widths = [len(h) for h in header]
    for r in rows:
        r += [""] * (ncols - len(r))
        for idx, cell in enumerate(r):
            widths[idx] = max(widths[idx], len(cell))

    def _fmt(cells: list[str]) -> str:
        parts = []
        for idx, cell in enumerate(cells):
            w = widths[idx]
            al = aligns[idx]
            if al == "right":
                parts.append(cell.rjust(w))
            elif al == "center":
                parts.append(cell.center(w))
            else:
                parts.append(cell.ljust(w))
        return " " + " │ ".join(parts) + " \n"

    widget.insert("end", _fmt(header), ("md_table_header",))
    for r_idx, r in enumerate(rows):
        tag = "md_table_row" if r_idx % 2 == 0 else "md_table_alt"
        widget.insert("end", _fmt(r), (tag,))


def _render_markdown(
    widget: tk.Text,
    md_text: str,
    *,
    base_dir: str | None = None,
) -> None:
    """Render Markdown text into a Tkinter ``Text`` widget with styled tags."""
    global current_markdown
    current_markdown = md_text
    if not hasattr(widget, "_md_rules"):
        _configure_markdown_tags(widget)

    widget.configure(state="normal")
    try:
        for rule in widget._md_rules:  # type: ignore[attr-defined]
            if rule.winfo_exists():
                rule.destroy()
        widget._md_rules.clear()  # type: ignore[attr-defined]
        widget._md_images.clear()  # type: ignore[attr-defined]
        for old_tag in widget._md_link_tags:  # type: ignore[attr-defined]
            widget.tag_delete(old_tag)
        widget._md_link_tags.clear()  # type: ignore[attr-defined]
        widget._md_last_rule_width = None  # type: ignore[attr-defined]

        widget.delete("1.0", "end")

        lines = md_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        n = len(lines)
        i = 0
        in_code = False
        code_fence = ""
        last_kind = "start"

        while i < n:
            line = lines[i]

            # Fenced code block (``` or ~~~)
            fence_m = _MD_FENCE_RE.match(line)
            if fence_m:
                marker = fence_m.group(1)
                if not in_code:
                    in_code = True
                    code_fence = marker
                    i += 1
                    continue
                if marker == code_fence:
                    in_code = False
                    code_fence = ""
                    last_kind = "code"
                    i += 1
                    continue
            if in_code:
                widget.insert("end", line + "\n", ("md_codeblock",))
                last_kind = "code"
                i += 1
                continue

            # Blank line: skip immediately after start, heading, HR or blank
            if not line.strip():
                if last_kind not in ("start", "blank", "heading", "hr"):
                    widget.insert("end", "\n")
                    last_kind = "blank"
                i += 1
                continue

            # Horizontal rule
            if _MD_HR_RE.match(line):
                _insert_md_hr(widget, color=BORDER, height=1)
                last_kind = "hr"
                i += 1
                continue

            # ATX heading (# .. ######)
            h_m = _MD_HEADING_RE.match(line)
            if h_m:
                level = len(h_m.group(1))
                htag = f"md_h{level}"
                _insert_md_inline(widget, h_m.group(2).strip(),
                                  (htag,), is_heading=True)
                widget.insert("end", "\n", (htag,))
                if level == 1:
                    _insert_md_hr(widget, color=BORDER, height=2)
                elif level == 2:
                    _insert_md_hr(widget, color="#e5e7eb", height=1)
                last_kind = "heading"
                i += 1
                continue

            # Standalone block image: ![alt](src)
            img_m = _MD_BLOCK_IMG_RE.match(line)
            if img_m:
                _insert_md_block_image(widget, img_m.group(1), img_m.group(2),
                                       base_dir)
                last_kind = "image"
                i += 1
                continue

            # Pipe table
            if ("|" in line and i + 1 < n
                    and _MD_TABLE_SEP_RE.match(lines[i + 1])):
                tbl = [line, lines[i + 1]]
                i += 2
                while i < n and "|" in lines[i] and lines[i].strip():
                    tbl.append(lines[i])
                    i += 1
                _insert_md_table(widget, tbl)
                last_kind = "table"
                continue

            # Blockquote
            q_m = _MD_QUOTE_RE.match(line)
            if q_m:
                widget.insert("end", "▎ ", ("md_quote", "md_quote_bar"))
                _insert_md_inline(widget, q_m.group(1), ("md_quote",))
                widget.insert("end", "\n", ("md_quote",))
                last_kind = "quote"
                i += 1
                continue

            # Unordered list item
            ul_m = _MD_UL_RE.match(line)
            if ul_m:
                indent = len(ul_m.group(1).replace("\t", "  "))
                level = min(indent // 2, 2)
                li_tag = f"md_li_{level}"
                bullet = _MD_BULLETS[level]
                widget.insert("end", f"{bullet} ",
                              (li_tag, f"md_bullet_{level}"))
                _insert_md_inline(widget, ul_m.group(2), (li_tag,))
                widget.insert("end", "\n", (li_tag,))
                last_kind = "list"
                i += 1
                continue

            # Ordered list item
            ol_m = _MD_OL_RE.match(line)
            if ol_m:
                indent = len(ol_m.group(1).replace("\t", "  "))
                level = min(indent // 2, 2)
                oli_tag = f"md_oli_{level}"
                widget.insert("end", f"{ol_m.group(2)}. ",
                              (oli_tag, "md_ol_num"))
                _insert_md_inline(widget, ol_m.group(3), (oli_tag,))
                widget.insert("end", "\n", (oli_tag,))
                last_kind = "list"
                i += 1
                continue

            # Regular paragraph line
            _insert_md_inline(widget, line, ("md_p",))
            widget.insert("end", "\n", ("md_p",))
            last_kind = "paragraph"
            i += 1

        # Remove trailing empty newline(s) if any so bottom padding stays neat
        while widget.compare("end-2c", ">=", "1.0") and widget.get("end-2c", "end-1c") == "\n":
            # Keep at least one character if the document isn't empty
            if widget.get("end-3c", "end-2c") == "\n":
                widget.delete("end-2c", "end-1c")
            else:
                break

        widget.tag_raise("search_match")
        widget.tag_raise("search_current", "search_match")
        widget.yview_moveto(0.0)
    finally:
        widget.configure(state="disabled")


def _copy_result_markdown() -> None:
    """Copy the raw Markdown source currently rendered in Result to clipboard."""
    md = current_markdown if current_markdown else report_markdown
    if not md:
        return
    app.clipboard_clear()
    app.clipboard_append(md)
    app.update_idletasks()
    if result_copy_button is not None:
        result_copy_button.configure(text="Copied!")
        app.after(
            1200,
            lambda: result_copy_button.configure(text="Copy")
            if result_copy_button is not None and result_copy_button.winfo_exists()
            else None,
        )


def _build_result_panel(parent) -> None:
    """Build the Markdown-rendered report panel with Copy, search bar and scrollbar."""
    global textbox, result_copy_button, result_search_var, result_search_entry, result_search_status
    panel = tk.Frame(
        parent,
        background=BG,
        highlightthickness=1,
        highlightbackground=BORDER,
        highlightcolor=BORDER,
        padx=PAD,
        pady=PAD,
    )
    panel.grid(sticky="nsew")
    panel.rowconfigure(1, weight=1)
    panel.columnconfigure(0, weight=1)

    # Header row: "Result" title on the left, Copy button + keyword search bar on the right
    header = ttk.Frame(panel, style="App.TFrame")
    header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, PAD))
    ttk.Label(header, text="Result", style="Section.TLabel").pack(side="left")

    search_bar = ttk.Frame(header, style="App.TFrame")
    search_bar.pack(side="right")
    result_copy_button = ttk.Button(
        search_bar,
        text="Copy",
        style="Small.TButton",
        width=7,
        command=_copy_result_markdown,
    )
    result_copy_button.pack(side="left", padx=(0, 8))
    result_search_status = ttk.Label(
        search_bar, text="", style="CardMuted.TLabel", anchor="e"
    )
    result_search_status.pack(side="left", padx=(0, 6))
    ttk.Label(search_bar, text="Search:", style="CardMuted.TLabel").pack(
        side="left", padx=(0, 4)
    )
    result_search_var = tk.StringVar(value="")
    result_search_entry = ttk.Entry(
        search_bar, textvariable=result_search_var, width=26
    )
    result_search_entry.pack(side="left", padx=(0, 2))
    ttk.Button(
        search_bar,
        text="▲",
        style="Small.TButton",
        width=2,
        command=lambda: _step_result_search(-1),
    ).pack(side="left", padx=(0, 1))
    ttk.Button(
        search_bar,
        text="▼",
        style="Small.TButton",
        width=2,
        command=lambda: _step_result_search(1),
    ).pack(side="left", padx=(0, 1))
    ttk.Button(
        search_bar,
        text="×",
        style="Small.TButton",
        width=2,
        command=_clear_result_search,
    ).pack(side="left")

    result_search_var.trace_add(
        "write", lambda *_args: _update_result_search(jump_first=True)
    )
    result_search_entry.bind("<Return>", lambda _e: _step_result_search(1))
    result_search_entry.bind("<Shift-Return>", lambda _e: _step_result_search(-1))
    result_search_entry.bind("<Escape>", _clear_result_search)

    textbox = tk.Text(panel, width=72, height=18, relief="flat",
                      background=CARD, foreground=FG, insertbackground=ACCENT,
                      borderwidth=0, highlightthickness=1,
                      highlightbackground=BORDER, highlightcolor=ACCENT,
                      padx=12, pady=8, wrap="word",
                      spacing1=1, spacing2=2, spacing3=1,
                      font=("Segoe UI", 10))
    textbox.grid(row=1, column=0, sticky="nsew")
    _configure_markdown_tags(textbox)

    vsb = ttk.Scrollbar(panel, orient="vertical", command=textbox.yview)
    vsb.grid(row=1, column=1, sticky="ns")
    textbox.configure(yscrollcommand=vsb.set)

    _render_markdown(textbox, WELCOME_MARKDOWN)


def build_gui() -> None:
    """Create the themed application window and lay out the widgets."""
    global app, run_button, animation_button, save_button, load_button
    global tip_check_button, status_progressbar, status_label
    app = tk.Tk()
    app.title("PGS — Planetary Gear Sizing")
    app.configure(background=BG)
    app.resizable(True, True)
    app.minsize(880, 420)
    if sys.platform.startswith("win"):
        app.iconbitmap("PGS.ico")

    base = font.nametofont("TkDefaultFont")
    base.configure(family="Segoe UI", size=10)
    title_font = font.Font(family="Segoe UI", size=13, weight="bold")
    section_font = font.Font(family="Segoe UI", size=10, weight="bold")

    style = ttk.Style(app)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    _configure_style(style, title_font, section_font)

    main = ttk.Frame(app, padding=PAD, style="App.TFrame")
    main.grid(row=0, column=0, sticky="nsew")
    app.columnconfigure(0, weight=1)
    app.rowconfigure(0, weight=1)
    main.columnconfigure(1, weight=1)
    main.rowconfigure(0, weight=1)

    # --- left column : scrollable inputs ---------------------------------
    left = ttk.Frame(main, style="App.TFrame")
    left.grid(row=0, column=0, sticky="ns", padx=(0, PAD))
    left.rowconfigure(0, weight=1)
    left.columnconfigure(0, weight=1)

    input_canvas = tk.Canvas(
        left, background=BG, borderwidth=0, highlightthickness=0
    )
    input_canvas.grid(row=0, column=0, sticky="nsew")
    input_vsb = ttk.Scrollbar(
        left, orient="vertical", command=input_canvas.yview
    )
    input_vsb.grid(row=0, column=1, sticky="ns")
    input_canvas.configure(yscrollcommand=input_vsb.set)

    container = ttk.Frame(input_canvas, style="App.TFrame")
    container_win = input_canvas.create_window(
        (0, 0), window=container, anchor="nw"
    )
    _build_section(container, "Planetary System", PLANETARY_INPUTS)
    _build_section(container, "Involute Gear Spec", GEAR_INPUTS)
    _build_section(container, "Loss Parameters", LOSS_INPUTS)
    lf_plot = ttk.LabelFrame(container, text="Plot", padding=PAD)
    lf_plot.grid(sticky="ew")
    lf_plot.columnconfigure(1, weight=1)
    ttk.Label(lf_plot, text="Plot option", style="Card.TLabel").grid(
        row=0, column=0, padx=(0, PADX), pady=PADY, sticky="e")
    cb = ttk.Combobox(lf_plot, values=PLOT_OPTIONS, width=12, state="readonly")
    cb.grid(row=0, column=1, padx=PADX, pady=PADY, sticky="w")
    entries["PlotOption"] = cb
    ttk.Label(lf_plot, text="Teeth profile", style="Card.TLabel").grid(
        row=1, column=0, padx=(0, PADX), pady=PADY, sticky="e")
    cb_teeth = ttk.Combobox(lf_plot, values=TOOTH_OPTIONS, width=12,
                            state="readonly")
    cb_teeth.grid(row=1, column=1, padx=PADX, pady=PADY, sticky="w")
    entries["TeethType"] = cb_teeth

    def _sync_input_scrollregion(_event=None) -> None:
        bbox = input_canvas.bbox("all")
        if bbox is not None:
            input_canvas.configure(scrollregion=bbox)
        req_w = container.winfo_reqwidth()
        if req_w > 1 and input_canvas.winfo_reqwidth() != req_w:
            input_canvas.configure(width=req_w)

    def _sync_container_width(event) -> None:
        if event.width > 1:
            input_canvas.itemconfigure(container_win, width=event.width)

    def _scroll_inputs(event) -> str | None:
        if "popdown" in str(event.widget):
            return None
        if input_canvas.yview() == (0.0, 1.0):
            return "break"
        if getattr(event, "num", None) == 4:
            step = -1
        elif getattr(event, "num", None) == 5:
            step = 1
        elif event.delta:
            step = -1 if event.delta > 0 else 1
        else:
            return None
        input_canvas.yview_scroll(step, "units")
        return "break"

    def _bind_input_wheel(widget) -> None:
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            widget.bind(seq, _scroll_inputs, add="+")
        for child in widget.winfo_children():
            _bind_input_wheel(child)

    container.bind("<Configure>", _sync_input_scrollregion)
    input_canvas.bind("<Configure>", _sync_container_width)
    _bind_input_wheel(input_canvas)
    _bind_input_wheel(container)

    # --- right column : result -------------------------------------------
    right = ttk.Frame(main, style="App.TFrame")
    right.grid(row=0, column=1, sticky="nsew")
    right.rowconfigure(0, weight=1)
    right.columnconfigure(0, weight=1)
    _build_result_panel(right)

    # --- bottom bar : actions & progress status -------------------------
    bar = ttk.Frame(main, style="App.TFrame")
    bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(PAD, 0))
    ttk.Button(bar, text="Exit", style="Danger.TButton",
               command=button_exit_callback).pack(side="right", padx=(0, PAD))
    save_button = ttk.Button(bar, text="Save", style="Accent.TButton",
                             command=button_save_callback)
    save_button.pack(side="right", padx=(0, PAD))
    animation_button = ttk.Button(bar, text="Animation", style="TButton",
                                  command=button_animation_callback)
    animation_button.pack(side="right", padx=(0, PAD))
    run_button = ttk.Button(bar, text="Run", style="Accent.TButton",
                            command=button_run_callback)
    run_button.pack(side="right", padx=(0, PAD))
    tip_check_button = ttk.Button(bar, text="Tip Check", style="TButton",
                                  command=button_tip_check_callback)
    tip_check_button.pack(side="right", padx=(0, PAD))
    load_button = ttk.Button(bar, text="Load", style="Accent.TButton",
                             command=button_load_callback)
    load_button.pack(side="right", padx=(0, PAD))

    status_frame = ttk.Frame(bar, style="App.TFrame")
    status_frame.pack(side="left", fill="x", expand=True, padx=(0, PAD))
    status_progressbar = ttk.Progressbar(
        status_frame,
        orient="horizontal",
        mode="determinate",
        maximum=100,
        value=0,
        length=140,
        style="Accent.Horizontal.TProgressbar",
    )
    status_progressbar.pack(side="left", padx=(0, 8))
    status_label = ttk.Label(
        status_frame,
        text="Ready",
        style="CardMuted.TLabel",
        anchor="w",
    )
    status_label.pack(side="left", fill="x", expand=True)

    # Size the window to ~70% of the full stacked height so it fits comfortably
    # on screen while the left scrollbar keeps every input reachable.
    app.update_idletasks()
    _sync_input_scrollregion()
    app.update_idletasks()
    screen_w = app.winfo_screenwidth()
    screen_h = app.winfo_screenheight()
    init_w = min(max(980, app.winfo_reqwidth() + 16), max(880, screen_w - 40))
    full_h = min(
        container.winfo_reqheight() + bar.winfo_reqheight() + PAD * 4 + 8,
        max(520, screen_h - 100),
    )
    init_h = max(
        420,
        min(
            int(round(full_h * DEFAULT_WINDOW_HEIGHT_RATIO)),
            int(round(screen_h * 0.57)),
        ),
    )
    app.geometry(f"{init_w}x{init_h}")
    app.bind("<Control-f>", _focus_result_search)
    app.bind("<Control-F>", _focus_result_search)


def main(argv: list[str] | None = None) -> None:
    global P1, gears
    P1 = PGS()
    gears = {name: GPG() for name in GEAR_ORDER}
    build_gui()
    init_parameters()
    toggle_simple_fields()
    loaded = bool(argv) and load_parameters_from_file(argv[0])
    if loaded:
        toggle_simple_fields()
    elif argv:
        print("WARN: could not load parameters from " + argv[0]
              + "; using the defaults")
    read_parameters()
    run_calc()
    if loaded:
        _save_and_show_run_result(DEFAULT_RESULT_DIR)
        plot_pgs()
    app.mainloop()


if __name__ == "__main__":
    main(sys.argv[1:] if len(sys.argv) > 1 else None)