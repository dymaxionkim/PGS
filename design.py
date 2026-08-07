"""PGS design GUI.

Tkinter front-end that ties the PGS sizing calculator (``PGS``) and the
involute gear profile generator (``GPG``) together, plots the gear set
geometry with matplotlib and exports the results as Markdown and CSV.

Run with::

    uv run design.py
"""

from __future__ import annotations

import os
import sys
import tkinter as tk
import tkinter.font as font
from tkinter import ttk

import matplotlib.pyplot as plt
import numpy as np

from GPG import GPG
from PGS import PGS

RESULT_DIR = "./Result"
DEFAULT_SCALE = 0.7
PLOT_DPI = 100

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
    "m": 0.5,
    "Np": 3,
    "Zr2overNp": 20,
    "Zs1overNp": 7,
    "Gs1X": 0.2,
    "Gs2X": -0.05,
    "B": 0.04,
    "A": 1.0,
    "D": 1.25,
    "alpha": 20,
    "C": 0.2,
    "E": 0.1,
    "PlotOption": 3,
}

# (key, label, hint, hint-on-next-row?)
PLANETARY_INPUTS = [
    ("TYPE", "Type", "", False),
    ("m", "Module, m", "[mm] > 0", False),
    ("Np", "Planets number, Np", "[ea] > 2", False),
    ("Zr2overNp", "Zr2 / Np", "", False),
    ("Zs1overNp", "Zs1 / Np", "", False),
]

GEAR_INPUTS = [
    ("Gs1X", "Shift factor, Gs1.X", "", False),
    ("Gs2X", "Shift factor, Gs2.X", "", False),
    ("B", "Backlash factor, B", "", False),
    ("A", "Addendum factor, A", "", False),
    ("D", "Dedendum factor, D", "", False),
    ("alpha", "Pressure angle, α", "[deg]", False),
    ("C", "Hob end radius, C", "[mm]", False),
    ("E", "Tooth end radius, E", "[mm]", False),
]

PLOT_ITEMS = [
    ("Stage1", 1),
    ("Stage2", 2),
    ("Total", 3),
]
PLOT_OPTIONS = [label for label, _ in PLOT_ITEMS]
PLOT_LABEL_TO_CODE = {label: code for label, code in PLOT_ITEMS}
PLOT_CODE_TO_LABEL = {code: label for label, code in PLOT_ITEMS}

# Human-readable Type options paired with their integer gear-type codes.
TYPE_ITEMS = [
    ("Simple", 0),
    ("Wolfrom (diff=0.5)", 2),
    ("Wolfrom (diff=1)", 1),
    ("Wolfrom (diff=2)", 3),
    ("Wolfrom (diff=3)", 4),
    ("Wolfrom (diff=4)", 5),
]
TYPE_LABELS = [label for label, _ in TYPE_ITEMS]
TYPE_LABEL_TO_CODE = {label: code for label, code in TYPE_ITEMS}
TYPE_CODE_TO_LABEL = {code: label for label, code in TYPE_ITEMS}

# Shared mutable state populated by the GUI build below.
app: tk.Tk
entries: dict[str, tk.Widget] = {}
textbox: tk.Text
P1: PGS
gears: dict[str, GPG]


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


def read_parameters() -> None:
    """Pull values from the input entries into the model objects."""
    P1.gear_type = TYPE_LABEL_TO_CODE[entries["TYPE"].get()]
    P1.module = float(entries["m"].get())
    P1.num_planets = int(entries["Np"].get())
    P1.zr2_multiple_np = int(entries["Zr2overNp"].get())
    P1.zs1_multiple_np = int(entries["Zs1overNp"].get())
    P1.pressure_angle = float(entries["alpha"].get())

    module = float(entries["m"].get())
    b = float(entries["B"].get())
    a = float(entries["A"].get())
    d = float(entries["D"].get())
    angle = float(entries["alpha"].get())
    c = float(entries["C"].get())
    e = float(entries["E"].get())

    copy_gear_factors((gears["Gs1"], gears["Gp1"], gears["Gr1"]),
                      module, b, a, d, angle, c, e)
    gears["Gs1"].shift_factor = float(entries["Gs1X"].get())

    if P1.is_wolfrom:
        copy_gear_factors((gears["Gs2"], gears["Gp2"], gears["Gr2"]),
                          module, b, a, d, angle, c, e)
        gears["Gs2"].shift_factor = float(entries["Gs2X"].get())


def finalize_parameters() -> None:
    """Transfer the PGS-derived tooth counts/modules to the GPG gears."""
    gears["Gs1"].module = P1.module1
    gears["Gs1"].teeth = P1.zs1
    gears["Gp1"].module = P1.module1
    gears["Gp1"].teeth = P1.zp1
    gears["Gp1"].y0 = P1.dc / 2.0
    gears["Gr1"].module = P1.module1
    gears["Gr1"].teeth = P1.zr1

    if P1.is_wolfrom:
        gears["Gs2"].module = P1.module2
        gears["Gs2"].teeth = P1.zs2
        gears["Gp2"].module = P1.module2
        gears["Gp2"].teeth = P1.zp2
        gears["Gp2"].y0 = P1.dc / 2.0
        gears["Gr2"].module = P1.module2
        gears["Gr2"].teeth = P1.zr2

    gears["Gp1"].shift_factor = -gears["Gs1"].shift_factor
    gears["Gr1"].shift_factor = gears["Gs1"].shift_factor
    if P1.is_wolfrom:
        gears["Gp2"].shift_factor = -gears["Gs2"].shift_factor
        gears["Gr2"].shift_factor = gears["Gs2"].shift_factor


def run_calc() -> None:
    """Run PGS sizing and every gear's profile generation."""
    P1.calc()
    P1.output()
    P1.checks_run()
    finalize_parameters()
    for name in GEAR_ORDER[:3]:
        gears[name].calc()
    if P1.is_wolfrom:
        for name in GEAR_ORDER[3:]:
            gears[name].calc()


# --------------------------------------------------------------- helpers
def rotate(x, y, angle):
    """Rotate the point arrays ``(x, y)`` by ``angle`` radians."""
    ca, sa = np.cos(angle), np.sin(angle)
    return ca * x - sa * y, sa * x + ca * y


# --------------------------------------------------------------- plotting
def _plot_stage(sun, planet, ring, *, color, pitch_style) -> None:
    """Draw the sun, its array of planets and the ring for one stage."""
    sun_angle = 0.0
    if planet.teeth % 2 == 0:
        sun_angle = (2 * np.pi / sun.teeth) / 2
    sx, sy = rotate(sun.plot_x, sun.plot_y, sun_angle)
    plt.plot(sx, sy, color)
    plt.plot(sun.pitch_circle_x, sun.pitch_circle_y, pitch_style)

    array_angle = 2 * np.pi / P1.num_planets
    for i in range(P1.num_planets):
        px, py = rotate(planet.plot_x, planet.plot_y, array_angle * i)
        ppx, ppy = rotate(planet.pitch_circle_x, planet.pitch_circle_y, array_angle * i)
        plt.plot(px, py, color)
        plt.plot(ppx, ppy, pitch_style)

    plt.plot(ring.plot_x, ring.plot_y, color)
    plt.plot(ring.pitch_circle_x, ring.pitch_circle_y, pitch_style)


def plot_pgs() -> None:
    """Render the planetary gear set figure and save the PNG."""
    plt.figure("PGS", figsize=(6, 6))
    plt.clf()
    option = PLOT_LABEL_TO_CODE[entries["PlotOption"].get()]

    if option in (1, 3):
        _plot_stage(gears["Gs1"], gears["Gp1"], gears["Gr1"],
                    color="dimgray", pitch_style="r:")
    if option in (2, 3) and P1.is_wolfrom:
        _plot_stage(gears["Gs2"], gears["Gp2"], gears["Gr2"],
                    color="black", pitch_style="r--")

    plt.axis("equal")
    plt.grid(True)
    out_name = {1: "/PGS1.png", 2: "/PGS2.png", 3: "/PGS.png"}[option]
    plt.savefig(RESULT_DIR + out_name, dpi=PLOT_DPI)
    plt.show()


# ----------------------------------------------------------- report builder
def _append_checks(lines: list[str]) -> None:
    c = P1.checks
    lines.append("## Check Geometrical Conditions\n")
    lines.append("* Sequential Mesh Condition (Non-Factorizing, Not Required) 1 : " + c.non_factorizing_1 + "\n")
    if P1.is_wolfrom:
        lines.append("* Sequential Mesh Condition (Non-Factorizing, Not Required) 2 : " + c.non_factorizing_2 + "\n")
    lines.append("* Planet Numbers (Equal Distance Condition) 1 : " + c.equal_distance_1 + "\n")
    if P1.is_wolfrom:
        lines.append("* Planet Numbers (Equal Distance Condition) 2 : " + c.equal_distance_2 + "\n")
    lines.append("* Planets Interference (Non-Overlap Condition) 1 : " + c.planets_interference_1 + "\n")
    if P1.is_wolfrom:
        lines.append("* Planets Interference (Non-Overlap Condition) 2 : " + c.planets_interference_2 + "\n")
    lines.append("* Involute Interference Condition 1 : " + c.involute_interference_1 + "\n")
    if P1.is_wolfrom:
        lines.append("* Involute Interference Condition 2 : " + c.involute_interference_2 + "\n")
    lines.append("* Trimming Interference 1 : " + c.trimming_interference_1 + "\n")
    if P1.is_wolfrom:
        lines.append("* Trimming Interference 2 : " + c.trimming_interference_2 + "\n")
    lines.append("* Teeth Numbers which is Integer 1 : " + c.teeth_number_integer_1 + "\n")
    if P1.is_wolfrom:
        lines.append("* Teeth Numbers which is Integer 2 : " + c.teeth_number_integer_2 + "\n")
    lines.append("\n")


def _append_inputs(lines: list[str]) -> None:
    lines.append("## Input Parameters\n")
    lines.append("* Type, TYPE = " + str(int(P1.gear_type)) + "\n")
    lines.append("* Module, m = " + str(float(P1.module)) + "\n")
    lines.append("* Planets Number, Np = " + str(int(P1.num_planets)) + "\n")
    lines.append("* Zr2/Np = " + str(int(P1.zr2_multiple_np)) + "\n")
    lines.append("* Zs1/Np = " + str(int(P1.zs1_multiple_np)) + "\n")
    lines.append("* Shift Factor, Gs1.X = " + str(float(gears["Gs1"].shift_factor)) + "\n")
    lines.append("* Shift Factor, Gs2.X = " + str(float(gears["Gs2"].shift_factor)) + "\n")
    lines.append("* Backlash Factor, B = " + str(float(gears["Gs1"].backlash_factor)) + "\n")
    lines.append("* Addendum Factor, A = " + str(float(gears["Gs1"].addendum_factor)) + "\n")
    lines.append("* Dedendum Factor, D = " + str(float(gears["Gs1"].dedendum_factor)) + "\n")
    lines.append("* Pressure Angle, alpha = " + str(float(gears["Gs1"].pressure_angle)) + "\n")
    lines.append("* Radius of Hib End, C = " + str(float(gears["Gs1"].hob_tip_radius_factor)) + "\n")
    lines.append("* Radius of Tooth End, E = " + str(float(gears["Gs1"].tooth_tip_radius_factor)) + "\n\n")


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
    lines.append("### Size\n")
    lines.append("* Sun1 = " + str(P1.ds1) + " [mm],  " + str(P1.zs1) + " [ea]\n")
    lines.append("* Planet1 = " + str(P1.dp1) + " [mm],  " + str(P1.zp1) + " [ea]\n")
    lines.append("* Ring1 = " + str(P1.dr1) + " [mm],  " + str(P1.zr1) + " [ea]\n")
    lines.append("* Sun2 = " + str(P1.ds2) + " [mm],  " + str(P1.zs2) + " [ea]\n")
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
    lines.append("### Size\n")
    lines.append("* Sun1 = " + str(P1.ds1) + " [mm],  " + str(P1.zs1) + " [ea]\n")
    lines.append("* Planet1 = " + str(P1.dp1) + " [mm],  " + str(P1.zp1) + " [ea]\n")
    lines.append("* Ring1 = " + str(P1.dr1) + " [mm],  " + str(P1.zr1) + " [ea]\n")
    lines.append("* Radius of Carrier = " + str(P1.dc / 2) + " [mm]\n")
    lines.append("* Number of Planets = " + str(P1.num_planets) + " [ea]\n\n")


def _append_gear_specs(lines: list[str]) -> None:
    for name in GEAR_ORDER if P1.is_wolfrom else GEAR_ORDER[:3]:
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


def build_report() -> None:
    """Compose the Markdown report and place it into the textbox."""
    lines: list[str] = []
    lines.append("# PGS - Planetary Gear Sizing Program\n\n")
    lines.append("![](./PGS.png)\n\n")
    _append_checks(lines)
    _append_inputs(lines)
    if P1.is_wolfrom:
        _append_wolfrom(lines)
    else:
        _append_simple(lines)
    _append_gear_specs(lines)
    textbox.delete("0.0", "end")
    textbox.insert("0.0", "".join(lines))


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


def save_output() -> None:
    """Write the Markdown report and per-gear CSV inputs to ``RESULT_DIR``."""
    os.makedirs(RESULT_DIR, exist_ok=True)
    with open(RESULT_DIR + "/PGS.md", "w") as f:
        f.write(textbox.get("0.0", "end"))
    for name in GEAR_ORDER if P1.is_wolfrom else GEAR_ORDER[:3]:
        folder = RESULT_DIR + "/" + name
        os.makedirs(folder, exist_ok=True)
        with open(folder + "/Inputs.csv", "w") as f:
            for key, value in _gear_csv_rows(name, gears[name]):
                f.write(f"{key},{value}\n")


# ---------------------------------------------------------------- callbacks
def button_run_callback() -> None:
    read_parameters()
    run_calc()
    build_report()
    save_output()
    plot_pgs()


def button_exit_callback() -> None:
    print("button_exit pressed")
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
              background=[("active", NEUTRAL_DARK), ("pressed", NEUTRAL_DARK)])

    style.configure("Accent.TButton", background=ACCENT, foreground="white",
                    borderwidth=0, focusthickness=0, padding=(14, 4))
    style.map("Accent.TButton",
              background=[("active", ACCENT_DARK), ("pressed", ACCENT_DARK)])

    style.configure("Danger.TButton", background=DANGER, foreground="white",
                    borderwidth=0, focusthickness=0, padding=(10, 4))
    style.map("Danger.TButton",
              background=[("active", DANGER_DARK), ("pressed", DANGER_DARK)])

    style.configure("TScrollbar", background=CARD, troughcolor=BG,
                    bordercolor=BG, arrowcolor=MUTED, relief="flat")


def _build_field(parent, row, key, label_text, hint_text, hint_below) -> int:
    """Add one labelled input row inside ``parent``; return next free row."""
    ttk.Label(parent, text=label_text, style="Card.TLabel").grid(
        row=row, column=0, padx=(0, PADX), pady=PADY, sticky="e")
    if key == "TYPE":
        entry = ttk.Combobox(parent, values=TYPE_LABELS,
                             width=20, state="readonly")
    else:
        entry = ttk.Entry(parent)
    entry.grid(row=row, column=1, padx=PADX, pady=PADY, sticky="ew")
    entries[key] = entry
    if hint_text:
        if hint_below:
            ttk.Label(parent, text=hint_text, style="CardMuted.TLabel").grid(
                row=row + 1, column=0, columnspan=2, padx=PADX,
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


def _build_result_panel(parent) -> None:
    """Build the flat report text widget with a scrollbar."""
    global textbox
    lf = ttk.LabelFrame(parent, text="Result", padding=PAD)
    lf.grid(sticky="nsew")
    lf.rowconfigure(0, weight=1)
    lf.columnconfigure(0, weight=1)

    textbox = tk.Text(lf, width=72, height=26, relief="flat",
                      background=CARD, foreground=FG, insertbackground=ACCENT,
                      borderwidth=0, highlightthickness=1,
                      highlightbackground=BORDER, highlightcolor=ACCENT,
                      padx=6, pady=4, wrap="none",
                      font=("Consolas", 10))
    textbox.grid(row=0, column=0, sticky="nsew")
    sb = ttk.Scrollbar(lf, orient="vertical", command=textbox.yview)
    sb.grid(row=0, column=1, sticky="ns")
    textbox.configure(yscrollcommand=sb.set)

    textbox.delete("0.0", "end")
    textbox.insert("end", "\n ########################################")
    textbox.insert("end", "\n #")
    textbox.insert("end", "\n # PGS - Planetary Gear Sizing Program")
    textbox.insert("end", "\n # https://github.com/dymaxionkim/PGS")
    textbox.insert("end", "\n #")
    textbox.insert("end", "\n ########################################")
    textbox.insert("end", "\n\n 1. Input Parameters.")
    textbox.insert("end", "\n 2. Press Run.")


def build_gui() -> None:
    """Create the themed application window and lay out the widgets."""
    global app
    app = tk.Tk()
    app.title("PGS — Planetary Gear Sizing")
    app.configure(background=BG)
    app.resizable(True, True)
    app.minsize(880, 480)
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

    # --- left column : inputs --------------------------------------------
    left = ttk.Frame(main, style="App.TFrame")
    left.grid(row=0, column=0, sticky="n", padx=(0, PAD))
    container = ttk.Frame(left, style="App.TFrame")
    container.grid(row=0, column=0, sticky="n")
    _build_section(container, "Planetary System", PLANETARY_INPUTS)
    _build_section(container, "Involute Gear Spec", GEAR_INPUTS)
    lf_plot = ttk.LabelFrame(container, text="Plot", padding=PAD)
    lf_plot.grid(sticky="ew")
    lf_plot.columnconfigure(1, weight=1)
    ttk.Label(lf_plot, text="Plot option", style="Card.TLabel").grid(
        row=0, column=0, padx=(0, PADX), pady=PADY, sticky="e")
    cb = ttk.Combobox(lf_plot, values=PLOT_OPTIONS, width=12, state="readonly")
    cb.grid(row=0, column=1, padx=PADX, pady=PADY, sticky="w")
    entries["PlotOption"] = cb

    # --- right column : result -------------------------------------------
    right = ttk.Frame(main, style="App.TFrame")
    right.grid(row=0, column=1, sticky="nsew")
    right.rowconfigure(0, weight=1)
    right.columnconfigure(0, weight=1)
    _build_result_panel(right)

    # --- bottom bar : actions -------------------------------------------
    bar = ttk.Frame(main, style="App.TFrame")
    bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(PAD, 0))
    ttk.Button(bar, text="Exit", style="Danger.TButton",
               command=button_exit_callback).pack(side="right", padx=(0, PAD))
    ttk.Button(bar, text="Run", style="Accent.TButton",
               command=button_run_callback).pack(side="right", padx=(0, PAD))


def main() -> None:
    global P1, gears
    P1 = PGS()
    gears = {name: GPG() for name in GEAR_ORDER}
    build_gui()
    init_parameters()
    read_parameters()
    run_calc()
    app.mainloop()


if __name__ == "__main__":
    main()