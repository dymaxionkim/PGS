"""PGS design GUI.

Tkinter front-end that ties the PGS sizing calculator (``PGS``) and the
involute gear profile generator (``GPG``) together, plots the gear set
geometry with matplotlib and exports the results as Markdown and CSV.

Run with::

    uv run design.py
"""

from __future__ import annotations

import os
import re
import sys
import tkinter as tk
import tkinter.font as font
from dataclasses import replace
from tkinter import filedialog
from tkinter import messagebox
from tkinter import ttk

import matplotlib.pyplot as plt
import numpy as np

import FGPG2_CLI
from CPG import CPG
from GPG import GPG
from PGS import PGS

DEFAULT_SCALE = 0.7
PLOT_DPI = 100
PGS_FIGURE = "PGS"

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
P1: PGS
gears: dict[str, GPG | CPG]
gears_second: dict[str, GPG | CPG] | None = None
save_button: ttk.Button | None = None


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
    P1.pressure_angle = float(entries["alpha"].get())

    for g in [gears] + ([gears_second] if gears_second else []):
        _apply_params(g)


def _ring_shift_factor(zp, xp, zr, module, dc, alpha_deg):
    """Ring-gear profile shift for a zero-backlash internal mesh.

    The planet (teeth ``zp``, shift ``xp``) meshes with the ring (``zr``
    positive teeth) at the carrier radius ``dc``/2.  The operating
    pressure angle of the mesh follows from the centre distance:

        cos(a') = module * cos(a0) * (zr - zp) / dc

    Matching the tooth thicknesses at the operating pitch point (the
    planet tooth must exactly fill the ring tooth space) gives:

        Xr = (zr - zp) * (inv(a0) - inv(a')) / (2 * tan(a0)) - xp

    The backlash factor is deliberately left uncompensated so that the
    B input keeps creating flank clearance as before.
    """
    a0 = np.deg2rad(alpha_deg)
    cos_aw = np.clip(module * np.cos(a0) * (zr - zp) / dc, -1.0, 1.0)
    aw = np.arccos(cos_aw)
    inv_a0 = np.tan(a0) - a0
    inv_aw = np.tan(aw) - aw
    return (zr - zp) * (inv_a0 - inv_aw) / (2.0 * np.tan(a0)) - xp


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
    g["Gr1"].pitch_circle_radius = (
        P1.dc / 2.0
        + P1.module1 * (P1.zp1 / 2.0 + g["Gp1"].shift_factor))
    if P1.is_wolfrom:
        g["Gs2"].shift_factor = -g["Gp2"].shift_factor
        g["Gr2"].shift_factor = _ring_shift_factor(
            P1.zp2, g["Gp2"].shift_factor, -P1.zr2,
            P1.module2, P1.dc, g["Gp2"].pressure_angle)
        g["Gr2"].pitch_circle_radius = (
            P1.dc / 2.0
            + P1.module2 * (P1.zp2 / 2.0 + g["Gp2"].shift_factor))


def run_calc() -> None:
    """Run PGS sizing and every gear's profile generation."""
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
            px, py = rotate(gear.plot_x, gear.plot_y, array_angle * i)
            ppx, ppy = rotate(gear.pitch_circle_x, gear.pitch_circle_y, array_angle * i)
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


def _draw(keys: list[str], sets: list[tuple[dict, bool]],
          out_path: str | None) -> None:
    """Draw ``keys`` from each ``(gear set, is_cycloid)`` pair on one figure.

    Saves the figure to ``out_path``, or shows it interactively when
    ``out_path`` is None (preview).
    """
    plt.figure(PGS_FIGURE, figsize=(6, 6))
    plt.clf()
    # Sun rotation that keeps the sun teeth meshing with the planet array.
    sun_angle = 0.0
    first = sets[0][0]
    if first["Gp1"].teeth % 2 == 0:
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
    else:
        plt.show()


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


def save_pngs(out_dir: str) -> None:
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
        _draw(_PLOT_CODE_KEYS[code], [(involute, False)],
              os.path.join(out_dir, f"Involute_{scope}.png"))
    if cycloid is not None:
        for scope, code in scopes:
            _draw(_PLOT_CODE_KEYS[code], [(cycloid, True)],
                  os.path.join(out_dir, f"Cycloid_{scope}.png"))
        # The combined overlay image is produced for the whole set
        # (All_Total for Wolfrom, All_Stage1 for Simple) and for each gear.
        whole = [("Total", 3)] if P1.is_wolfrom else [("Stage1", 1)]
        gear_scopes = [(s, c) for s, c in scopes if c >= 11]
        for scope, code in whole + gear_scopes:
            _draw(_PLOT_CODE_KEYS[code], [(involute, False), (cycloid, True)],
                  os.path.join(out_dir, f"All_{scope}.png"))


def plot_pgs() -> None:
    """Interactive preview of the chosen PlotOption (no file output)."""
    code = PLOT_LABEL_TO_CODE[entries["PlotOption"].get()]
    keys = _PLOT_CODE_KEYS.get(code, _PLOT_CODE_KEYS[3])
    sets = [(gears, isinstance(gears.get("Gp1"), CPG))]
    if isinstance(gears_second, dict):
        sets.append((gears_second, isinstance(gears_second.get("Gp1"), CPG)))
    _draw(keys, sets, None)


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
    lines.append("* Radius of Tooth End, E = " + str(float(gears["Gs1"].tooth_tip_radius_factor)) + "\n\n")


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


def build_report() -> None:
    """Compose the Markdown report and place it into the textbox."""
    lines: list[str] = []
    lines.append("# PGS - Planetary Gear Sizing Program\n\n")
    lines.append("![](./" + ("All_Total.png" if P1.is_wolfrom else "All_Stage1.png") + ")\n\n")
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


def save_output(out_dir: str) -> None:
    """Write the Markdown report, input-model CSV and per-gear results."""
    os.makedirs(out_dir, exist_ok=True)
    with open(out_dir + "/README.md", "w") as f:
        f.write(textbox.get("0.0", "end"))
    _write_input_model_csv(out_dir + "/input_model.csv")
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
            sub = folder + "/" + profile.capitalize()
            os.makedirs(sub, exist_ok=True)
            _write_gear_csv(sub + "/Inputs.csv", name)
            _generate_fgpg2_results(sub, profile)


def _write_gear_csv(path: str, name: str) -> None:
    with open(path, "w") as f:
        for key, value in _gear_csv_rows(name, gears[name]):
            f.write(f"{key},{value}\n")


# ----------------------------------------------------- input model CSV (Save)
# The full header of the exported "input_model.csv".  It mirrors the
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
        7,                              # Quality Grade (ISO) — kept as-is
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

    # Carrier pin: the smaller of the two planet offset-circle dia minus twice
    # the matching planet's module.
    planets_gears = [gears["Gp1"]] + ([gears["Gp2"]] if stage2 else [])
    pin_gear = min(planets_gears, key=_offset_circle_dia)
    carrier_pin = _offset_circle_dia(pin_gear) - 2 * pin_gear.module

    # Carrier thicknesses: half the face width of each stage's planet gear.
    thick_in = gears["Gp1"].module * 5 / 2
    thick_out = (gears["Gp2"].module if stage2 else gears["Gp1"].module) * 5 / 2

    shaft_dia = _offset_circle_dia(gears["Gs1"]) - 2 * gears["Gs1"].module

    # Frame outer diameter: the larger of the two ring offset-circle dia plus
    # four times the matching ring's module.
    rings_gears = [gears["Gr1"]] + ([gears["Gr2"]] if stage2 else [])
    frame_gear = max(rings_gears, key=_offset_circle_dia)
    frame_outer = _offset_circle_dia(frame_gear) + 4 * frame_gear.module

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
    read_parameters()
    run_calc()
    build_report()
    plot_pgs()


def button_run_callback() -> None:
    """Compute, show the report text and plot the preview (no file output)."""
    read_parameters()
    run_calc()
    build_report()
    plot_pgs()


def button_save_callback() -> None:
    """Save the result files into a user-selected folder.

    The Save button is disabled for the duration of the operation.  Asks for
    the parent directory first, then creates a ``Result`` folder under it and
    writes the report, per-gear CSV/DXF/PNG files and the plot PNGs.  Also
    (re)runs the calculation so the saved files always match the inputs.
    """
    global save_button
    if save_button is not None:
        save_button.configure(state="disabled")
        app.update_idletasks()
    try:
        folder = filedialog.askdirectory(
            title="Select the folder where the Result directory will be created")
        if not folder:
            return
        out_dir = os.path.join(folder, "Result")
        read_parameters()
        run_calc()
        build_report()
        save_output(out_dir)
        save_pngs(out_dir)
        print("Result files saved in " + out_dir)
    finally:
        if save_button is not None:
            save_button.configure(state="normal")
            app.update_idletasks()


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
    lbl = ttk.Label(parent, text=label_text, style="Card.TLabel")
    lbl.grid(row=row, column=0, padx=(0, PADX), pady=PADY, sticky="e")
    entries[key + "_LABEL"] = lbl
    if key == "TYPE":
        entry = ttk.Combobox(parent, values=TYPE_LABELS,
                             width=20, state="readonly")
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
    textbox.insert("end", "\n 2. Press Run to compute & plot, then Save to write the result files into a folder you choose.")


def build_gui() -> None:
    """Create the themed application window and lay out the widgets."""
    global app, save_button
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
    ttk.Label(lf_plot, text="Teeth profile", style="Card.TLabel").grid(
        row=1, column=0, padx=(0, PADX), pady=PADY, sticky="e")
    cb_teeth = ttk.Combobox(lf_plot, values=TOOTH_OPTIONS, width=12,
                            state="readonly")
    cb_teeth.grid(row=1, column=1, padx=PADX, pady=PADY, sticky="w")
    entries["TeethType"] = cb_teeth

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
    save_button = ttk.Button(bar, text="Save", style="Accent.TButton",
                             command=button_save_callback)
    save_button.pack(side="right", padx=(0, PAD))
    ttk.Button(bar, text="Run", style="Accent.TButton",
               command=button_run_callback).pack(side="right", padx=(0, PAD))
    ttk.Button(bar, text="Load", style="Accent.TButton",
               command=button_load_callback).pack(side="right", padx=(0, PAD))


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
        build_report()
        plot_pgs()
    app.mainloop()


if __name__ == "__main__":
    main(sys.argv[1:] if len(sys.argv) > 1 else None)