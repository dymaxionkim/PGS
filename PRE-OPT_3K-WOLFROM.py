"""PRE-OPT 3K-Wolfrom gear-combination search GUI.

Tkinter front-end that searches a user-defined parameter space (module,
planet count and ring/sun tooth counts) for Wolfrom (3K) planetary gear
sets satisfying every geometric feasibility check, shows the feasible
combinations in a table and exports them to ``Result.xlsx``.

Run with::

    uv run PRE-OPT_3K-WOLFROM.py
"""

from __future__ import annotations

import math
import os
import queue
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
import tkinter.font as font
from dataclasses import dataclass
from tkinter import filedialog
from tkinter import messagebox
from tkinter import ttk

import pandas as pd

STANDARD_PRESSURE_ANGLE: float = 20.0
MIN_RIM_FOR_TRIMMING: float = 16.0
MIN_EXTERNAL_TEETH: int = 9
MIN_OPERATING_PRESSURE_ANGLE: float = 10.0
MAX_OPERATING_PRESSURE_ANGLE: float = 30.0
MIN_CONTACT_RATIO: float = 1.1
DEFAULT_ADDENDUM_FACTOR: float = 1.0
DEFAULT_DEDENDUM_FACTOR: float = 1.25
DEFAULT_BACKLASH_FACTOR: float = 0.04
DEFAULT_HOB_TIP_RADIUS_FACTOR: float = 0.2
DEFAULT_TOOTH_TIP_RADIUS_FACTOR: float = 0.01
EVAL_SHIFT_CANDIDATES: tuple[float, ...] = (0.0, 0.4)
ROUND_PRECISION: int = 6
EXCEL_MAX_ROWS: int = 1048576

_A0_RAD: float = math.radians(STANDARD_PRESSURE_ANGLE)
_SIN_A0: float = math.sin(_A0_RAD)
_COS_A0: float = math.cos(_A0_RAD)
_TAN_A0: float = math.tan(_A0_RAD)
_INV_A0: float = _TAN_A0 - _A0_RAD
_COS_MIN_AW: float = math.cos(math.radians(MIN_OPERATING_PRESSURE_ANGLE))
_COS_MAX_AW: float = math.cos(math.radians(MAX_OPERATING_PRESSURE_ANGLE))

# --- Modern flat colour palette (identical to design.py) -------------------
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

# --- Search-space definitions --------------------------------------------
# (key, label, has module step?, hint).  The seven input parameters mirror
# the design.py planetary inputs: m1/m2 step through the space while the
# tooth counts and planet number sweep the integers.
PARAM_ROWS = [
    ("Np", "Planet number, Np", False, "[ea] > 2"),
    ("m1", "Module1, m1", True, "[mm] > 0"),
    ("m2", "Module2, m2", True, "[mm] > 0"),
    ("Zs1", "Sun1 Teeth, Zs1", False, "[ea] > 0"),
    ("Zr1", "Ring1 Teeth, Zr1", False, "[ea] > 0"),
    ("Zp2", "Planet2 Teeth, Zp2", False, "[ea] > 0"),
    ("Zr2", "Ring2 Teeth, Zr2", False, "[ea] > 0"),
]

SEARCH_DEFAULTS = {
    "m1_min": 0.8, "m1_max": 0.9, "m1_step": 0.1,
    "m2_min": 1.2, "m2_max": 1.3, "m2_step": 0.1,
    "Np_min": 3, "Np_max": 4,
    "Zr2_min": 50, "Zr2_max": 58,
    "Zp2_min": 18, "Zp2_max": 24,
    "Zr1_min": 85, "Zr1_max": 95,
    "Zs1_min": 12, "Zs1_max": 18,
}

COLUMNS = ["Np", "m1", "m2", "Zs1", "Zp1", "Zr1", "Zp2", "Zr2",
           "Dr1", "Dr2", "Ratio"]

CHECK_NAMES = [
    "Planet Numbers (Equal Distance Condition) 1",
    "Planet Numbers (Equal Distance Condition) 2",
    "Planets Interference (Non-Overlap Condition) 1",
    "Planets Interference (Non-Overlap Condition) 2",
    "Involute Interference Condition 1",
    "Involute Interference Condition 2",
    "Trimming Interference 1",
    "Trimming Interference 2",
    "Teeth Numbers which is Integer 1",
    "Teeth Numbers which is Integer 2",
    "Realizable Tooth Range & Profile/Mesh Geometry 1",
    "Realizable Tooth Range, Pitch-Dia Match & Profile/Mesh Geometry 2",
]


@dataclass
class SearchParams:
    """User-defined min/max/step box for every search parameter."""

    m1_min: float
    m1_max: float
    m1_step: float
    m2_min: float
    m2_max: float
    m2_step: float
    np_min: int
    np_max: int
    zr2_min: int
    zr2_max: int
    zp2_min: int
    zp2_max: int
    zr1_min: int
    zr1_max: int
    zs1_min: int
    zs1_max: int


# Shared mutable GUI state.
app: tk.Tk
entries: dict[str, tk.Entry] = {}
tree: ttk.Treeview
status_var: tk.StringVar
count_var: tk.StringVar
start_button: ttk.Button
pgs_button: ttk.Button
save_button: ttk.Button
last_rows: list[list] | None = None
worker_queue: queue.Queue[tuple] = queue.Queue()
search_thread: threading.Thread | None = None


# -------------------------------------------------------------- feasibility
def _involute_thresh(zp: float) -> float:
    temp = (zp * _SIN_A0) ** 2
    return (temp - 4.0) / (2.0 * temp - 4.0)


def _non_overlap_ok(planets: int, arg: float) -> bool:
    if arg >= 1.0:
        return False
    return planets < math.pi / math.asin(arg)


def _is_int(v: float) -> bool:
    return float(v).is_integer()


def _tooth_profile_ok(z_signed: float, shift: float) -> bool:
    """Return True if GPG produces a non-degenerate, non-twisted tooth.

    Mirrors ``GPG._apply_internal_convention`` and ``GPG._compute_params``
    in module-independent form (module cancels from every tooth angle):
    verifies finite involute bounds, positive involute span
    (``theta_ie > theta_is``), non-pointed / non-self-intersecting outer
    arc (``alpha_e <= alpha_m``) and non-crossing root arc (``alpha_ts >= 0``).
    """
    z = float(z_signed)
    x = float(shift)
    b = DEFAULT_BACKLASH_FACTOR
    a = DEFAULT_ADDENDUM_FACTOR
    d = DEFAULT_DEDENDUM_FACTOR
    c = DEFAULT_HOB_TIP_RADIUS_FACTOR
    e = DEFAULT_TOOTH_TIP_RADIUS_FACTOR
    if z < 0.0:
        z = -z
        x = -x
        b = -b
        a, d = d, a
        c, e = e, c
    if z <= 0.0:
        return False

    alpha_m = math.pi / z
    alpha_is = (
        _A0_RAD + math.pi / (2.0 * z)
        + b / (z * _COS_A0)
        - (1.0 + 2.0 * x / z) * _TAN_A0
    )
    theta_is = (
        _TAN_A0
        + 2.0 * (c * (1.0 - _SIN_A0) + x - d) / (z * _COS_A0 * _SIN_A0)
    )
    u = (z + 2.0 * (x + a - e)) / (z * _COS_A0)
    if u <= 1.0:
        return False
    root_u = math.sqrt(u * u - 1.0)
    theta_ie = 2.0 * e / (z * _COS_A0) + root_u
    alpha_e = alpha_is + theta_ie - math.atan(root_u)
    alpha_ts = (
        (2.0 * (c * (1.0 - _SIN_A0) - d) * _SIN_A0 + b) / (z * _COS_A0)
        - 2.0 * c * _COS_A0 / z
        + math.pi / (2.0 * z)
    )
    if not (math.isfinite(alpha_e) and math.isfinite(alpha_ts)
            and math.isfinite(theta_is) and math.isfinite(theta_ie)):
        return False
    return (
        theta_ie > theta_is
        and alpha_e <= alpha_m
        and alpha_ts >= 0.0
    )


def _ext_mesh_ok(z1: int, x1: float, z2: int, x2: float,
                 dc_norm: float) -> bool:
    """Check stage-1 external mesh (Gs1-Gp1) pitch match, contact & clearance.

    ``dc_norm = dc / module1`` is dimensionless (module cancels).  Mirrors
    ``PGS._calc_mesh_loss_ext`` and checks operating pressure angle,
    tip-to-root clearances and continuous transverse contact ratio.
    """
    if dc_norm <= 0.0 or z1 <= 0 or z2 <= 0:
        return False
    aw_cd = 0.5 * dc_norm
    rb1 = 0.5 * z1 * _COS_A0
    rb2 = 0.5 * z2 * _COS_A0
    cos_aw = (rb1 + rb2) / aw_cd
    if not (_COS_MAX_AW <= cos_aw <= _COS_MIN_AW):
        return False

    a = DEFAULT_ADDENDUM_FACTOR
    d = DEFAULT_DEDENDUM_FACTOR
    ra1 = 0.5 * z1 + x1 + a
    ra2 = 0.5 * z2 + x2 + a
    rf1 = 0.5 * z1 + x1 - d
    rf2 = 0.5 * z2 + x2 - d
    if ra1 <= rb1 or ra2 <= rb2 or rf1 <= 0.0 or rf2 <= 0.0:
        return False
    if ra1 + rf2 >= aw_cd or ra2 + rf1 >= aw_cd:
        return False

    aw = math.acos(cos_aw)
    tan_aw = math.tan(aw)
    pb = math.pi * _COS_A0
    eps1 = (math.sqrt(ra2 * ra2 - rb2 * rb2) - rb2 * tan_aw) / pb
    eps2 = (math.sqrt(ra1 * ra1 - rb1 * rb1) - rb1 * tan_aw) / pb
    return (eps1 + eps2) >= MIN_CONTACT_RATIO


def _int_mesh_ok(zp: int, xp: float, zr: int, dc_norm: float) -> bool:
    """Check an internal mesh (Gp-Gr) pitch-diameter match, contact & profile.

    ``dc_norm = dc / module`` is dimensionless.  The operating pitch
    diameters satisfy ``Dw / (m * Z) = dc_norm / (zr - zp) = cos(a0)/cos(aw)``;
    requiring ``aw in [MIN_OPERATING_PRESSURE_ANGLE, MAX_OPERATING_PRESSURE_ANGLE]``
    directly enforces that the actual tooth count stays consistent with the
    pitch-diameter-derived tooth count ``(dc + m*zp)/m``.  Then computes the
    exact zero-backlash ring shift ``xr`` (mirroring ``PGS.ring_shift_factor``),
    verifies ring inner tip > base circle, radial tip-to-root clearances,
    continuous contact ratio (mirroring ``PGS._calc_mesh_loss_int``) and a
    non-twisted ring tooth profile.
    """
    if dc_norm <= 0.0 or zp <= 0 or zr <= zp:
        return False
    aw_cd = 0.5 * dc_norm
    rbp = 0.5 * zp * _COS_A0
    rbr = 0.5 * zr * _COS_A0
    cos_aw = (rbr - rbp) / aw_cd
    if not (_COS_MAX_AW <= cos_aw <= _COS_MIN_AW):
        return False

    aw = math.acos(cos_aw)
    tan_aw = math.tan(aw)
    inv_aw = tan_aw - aw
    xr = (zr - zp) * (_INV_A0 - inv_aw) / (2.0 * _TAN_A0) - xp

    a = DEFAULT_ADDENDUM_FACTOR
    d = DEFAULT_DEDENDUM_FACTOR
    rap = 0.5 * zp + xp + a
    rfp = 0.5 * zp + xp - d
    rar = 0.5 * zr - xr - a
    rfr = 0.5 * zr - xr + d
    if rap <= rbp or rar <= rbr or rfp <= 0.0:
        return False
    if aw_cd + rap >= rfr or rar <= aw_cd + rfp:
        return False

    pb = math.pi * _COS_A0
    eps_p = (math.sqrt(rap * rap - rbp * rbp) - rbp * tan_aw) / pb
    eps_r = (rbr * tan_aw - math.sqrt(rar * rar - rbr * rbr)) / pb
    if (eps_p + eps_r) < MIN_CONTACT_RATIO:
        return False
    return _tooth_profile_ok(-zr, xr)


def _stage1_feasible_shifts(planets: int, zs1: int, zp1: int,
                            zr1: int) -> tuple[float, ...]:
    """Return baseline shift values at which stage-1 geometry is realizable."""
    if zs1 < MIN_EXTERNAL_TEETH or zp1 < MIN_EXTERNAL_TEETH:
        return ()
    valid: list[float] = []
    for x in EVAL_SHIFT_CANDIDATES:
        dc_norm = zs1 + zp1 + 4.0 * x
        if dc_norm <= 0.0:
            continue
        if not _non_overlap_ok(
                planets, (zp1 + 2.0 * x + 2.0 * DEFAULT_ADDENDUM_FACTOR) / dc_norm):
            continue
        if not (_tooth_profile_ok(zs1, x) and _tooth_profile_ok(zp1, x)):
            continue
        if not _ext_mesh_ok(zs1, x, zp1, x, dc_norm):
            continue
        if not _int_mesh_ok(zp1, x, zr1, dc_norm):
            continue
        valid.append(x)
    return tuple(valid)


def _feasible_matrix(params: SearchParams,
                     report=None) -> list[list]:
    """Return every feasible row of the combination table.

    Columns (``COLUMNS``): the search inputs, the derived Zp1 and the
    stage geometries Dr1 = m1*|Zr1|, Dr2 = m2*|Zr2| and the total Wolfrom
    (3K) ratio g22 = (1 + l1)/(1 - l2) with l1 = |Zr1|/Zs1 and
    l2 = |Zr1|*Zp2/(|Zr2|*Zp1), mirroring PGS._calc_stage2.

    The twelve checks of ``CHECK_NAMES`` combine the ten geometric checks
    mirrored from PGS.py (checks 1–10) with stage-1 and stage-2 realizable
    tooth-range, pitch-diameter match and involute mesh/profile validity
    filters (checks 11–12):

      * stage-1 table: (Np, Zr1, Zs1) combos surviving checks 1, 3, 5, 7, 9
        and 11 with derived Zp1 = (|Zr1| - Zs1)/2, verified for realizable
        tooth counts, Gs1-Gp1 / Gp1-Gr1 contact ratio, clearances and
        non-twisted GPG tooth profiles;
      * stage-2 table: (Np, Zr2, Zp2) combos surviving checks 2, 6, 8, 10
        and minimum realizable planet tooth count / profile validity;
      * module join: evaluates Non-Overlap 2 (check 4), non-singular ratio
        (l2 != 1), and stage-2 pitch-diameter match / operating pressure
        angle / contact ratio / tip-to-root clearance / non-twisted Gr2
        tooth profile (check 12) on the shared carrier diameter.
    """
    m1_values = _step_values(params.m1_min, params.m1_max, params.m1_step)
    m2_values = _step_values(params.m2_min, params.m2_max, params.m2_step)
    if not m1_values or not m2_values:
        return []

    np_range = range(max(2, params.np_min), params.np_max + 1)
    zr1_range = range(params.zr1_min, params.zr1_max + 1)
    zs1_range = range(params.zs1_min, params.zs1_max + 1)

    if report:
        report("Stage 1 filter : scanning (Np, Zr1, Zs1) teeth combos ...")
    stage1_ok: list[tuple[int, int, int, int, tuple[float, ...]]] = []
    stage1_cache: dict[tuple[int, int, int, int], tuple[float, ...]] = {}
    total1 = len(np_range) * len(zr1_range) * len(zs1_range)
    done1 = 0
    for planets in np_range:
        for zr1 in zr1_range:
            for zs1 in zs1_range:
                done1 += 1
                if report and done1 % 2000 == 0:
                    report(f"Stage 1 filter : {done1}/{total1} checked"
                           f" · {len(stage1_ok)} candidates")
                if zs1 < MIN_EXTERNAL_TEETH:
                    continue
                diff = zr1 - zs1
                if diff < 2 * MIN_EXTERNAL_TEETH or diff % 2 != 0:
                    continue
                zp1 = diff // 2
                if not _is_int(zp1):
                    continue
                if (zs1 + zr1) % planets != 0:
                    continue
                if not _non_overlap_ok(planets, (zp1 + 2) / (zp1 + zs1)):
                    continue
                if zr1 < _involute_thresh(zp1):
                    continue
                if zr1 - zp1 < MIN_RIM_FOR_TRIMMING:
                    continue
                s1_key = (planets, zs1, zp1, zr1)
                s1_shifts = stage1_cache.get(s1_key)
                if s1_shifts is None:
                    s1_shifts = _stage1_feasible_shifts(planets, zs1, zp1, zr1)
                    stage1_cache[s1_key] = s1_shifts
                if not s1_shifts:
                    continue
                stage1_ok.append((planets, zr1, zs1, zp1, s1_shifts))
    if report:
        report(f"Stage 1 filter : {len(stage1_ok)} candidate stage-1 sets")

    p2_shift_cache: dict[int, frozenset[float]] = {}
    stage2_by_planets: dict[int, list[tuple[int, int, frozenset[float]]]] = {}
    for planets in np_range:
        combos: list[tuple[int, int, frozenset[float]]] = []
        for zr2 in range(params.zr2_min, params.zr2_max + 1):
            if zr2 % planets != 0:
                continue
            for zp2 in range(params.zp2_min, params.zp2_max + 1):
                if zp2 < MIN_EXTERNAL_TEETH:
                    continue
                if zr2 < _involute_thresh(zp2):
                    continue
                if zr2 - zp2 < MIN_RIM_FOR_TRIMMING:
                    continue
                if not (_is_int(zr2) and _is_int(zp2)):
                    continue
                p2_shifts = p2_shift_cache.get(zp2)
                if p2_shifts is None:
                    p2_shifts = frozenset(
                        x for x in EVAL_SHIFT_CANDIDATES
                        if _tooth_profile_ok(zp2, x))
                    p2_shift_cache[zp2] = p2_shifts
                if not p2_shifts:
                    continue
                combos.append((zr2, zp2, p2_shifts))
        stage2_by_planets[planets] = combos

    # Precompute every (m1, m2, m2/m1) triple once for fast range pruning.
    mod_triples: list[tuple[float, float, float]] = [
        (m1v, m2v, m2v / m1v)
        for m1v in m1_values
        for m2v in m2_values
    ]
    m_ratio_min = min(t[2] for t in mod_triples)
    m_ratio_max = max(t[2] for t in mod_triples)
    sin_half_by_np = {
        planets: math.sin(math.pi / planets) for planets in np_range
    }

    int2_cache: dict[tuple[int, float, int, float], bool] = {}
    results: list[list] = []
    total_join = len(stage1_ok)
    done_join = 0
    for planets, zr1, zs1, zp1, s1_shifts in stage1_ok:
        done_join += 1
        if report and done_join % 10000 == 0:
            report(f"Stage 2 join : {done_join}/{total_join} stage-1 sets"
                   f" · {len(results)} feasible")
        dc_base = zs1 + zp1
        sin_half = sin_half_by_np[planets]
        for zr2, zp2, p2_shifts in stage2_by_planets.get(planets, []):
            if zr1 * zp2 == zr2 * zp1:
                continue
            z_diff2 = zr2 - zp2
            # Compute feasible m2/m1 bands per candidate shift x:
            #   Non-Overlap 2:    m2/m1 < dc_x * sin(pi/Np) / (zp2 + 2*x + 2*A)
            #   Pitch-Dia / aw2:  dc_x * cos(aw_max)/(cos(a0)*z_diff2)
            #                     <= m2/m1 <= dc_x * cos(aw_min)/(cos(a0)*z_diff2)
            bands: list[tuple[float, float, float, float, float]] = []
            for x in s1_shifts:
                if x not in p2_shifts:
                    continue
                dc_x = dc_base + 4.0 * x
                lo = (dc_x * _COS_MAX_AW) / (_COS_A0 * z_diff2)
                hi_aw = (dc_x * _COS_MIN_AW) / (_COS_A0 * z_diff2)
                hi_no = (dc_x * sin_half) / (
                    zp2 + 2.0 * x + 2.0 * DEFAULT_ADDENDUM_FACTOR)
                hi = hi_aw if hi_aw < hi_no else hi_no
                if lo <= hi and hi >= m_ratio_min and lo <= m_ratio_max:
                    bands.append((x, dc_x, lo, hi_aw, hi_no))
            if not bands:
                continue

            ratio = _total_ratio(zr1, zs1, zp1, zr2, zp2)
            for m1v, m2v, m_ratio in mod_triples:
                feasible = False
                for x, dc_x, lo, hi_aw, hi_no in bands:
                    if not (lo <= m_ratio <= hi_aw and m_ratio < hi_no):
                        continue
                    dc_norm2 = dc_x / m_ratio
                    ckey = (zp2, x, zr2, round(dc_norm2, 9))
                    ok = int2_cache.get(ckey)
                    if ok is None:
                        ok = _int_mesh_ok(zp2, x, zr2, dc_norm2)
                        int2_cache[ckey] = ok
                    if ok:
                        feasible = True
                        break
                if feasible:
                    results.append([planets, m1v, m2v, zs1, zp1, zr1, zp2, zr2,
                                    round(m1v * zr1, ROUND_PRECISION),
                                    round(m2v * zr2, ROUND_PRECISION),
                                    ratio])
    if report:
        report(f"Search finished : {len(results)} feasible combinations")
    return results


def _step_values(minv: float, maxv: float, step: float) -> list[float]:
    """Inclusive list of ``minv + k*step`` values not exceeding ``maxv``."""
    values = []
    v = minv
    while v <= maxv + 1e-9:
        values.append(round(v, ROUND_PRECISION))
        v += step
    return values


def _total_ratio(zr1: int, zs1: int, zp1: int, zr2: int, zp2: int) -> float:
    """Total Wolfrom (3K) ratio g22 for a teeth combination.

    Mirrors PGS._calc_stage2: l1 = |Zr1|/Zs1, l2 = |Zr1|*Zp2/(|Zr2|*Zp1),
    g22 = (1 + l1)/(1 - l2), negated when l2 > 1.  The modules cancel so the
    ratio depends only on the tooth counts.
    """
    l1 = zr1 / zs1
    l2 = zr1 * zp2 / (zr2 * zp1)
    if l2 == 1:
        return float("nan")
    g22 = (1 + l1) / (1 - l2)
    if l2 > 1:
        g22 = -g22
    return round(g22, ROUND_PRECISION)


# ----------------------------------------------------------- search worker
def _search_worker(params: SearchParams) -> None:
    try:
        def report(text: str) -> None:
            worker_queue.put(("progress", text))
        rows = _feasible_matrix(params, report)
        worker_queue.put(("done", rows))
    except Exception as exc:
        worker_queue.put(("error", str(exc)))


# ------------------------------------------------------------------ export
def _save_excel(rows: list[list], out_dir: str) -> str:
    df = pd.DataFrame(rows, columns=COLUMNS)
    df = df.sort_values(COLUMNS).reset_index(drop=True)
    path = os.path.join(out_dir, "Result.xlsx")
    df.to_excel(path, index=False)
    return path


# ---------------------------------------------------------------- utilities
def _parse_params() -> SearchParams:
    """Read and validate every min/max/step entry into a ``SearchParams``."""
    def f(key: str) -> float:
        raw = entries[key].get().strip()
        if not raw:
            raise ValueError(key + " is empty")
        return float(raw)

    def i(key: str) -> int:
        raw = entries[key].get().strip()
        if not raw:
            raise ValueError(key + " is empty")
        value = float(raw)
        if not _is_int(value):
            raise ValueError(key + " must be an integer")
        return int(value)

    m1_min = f("m1_min"); m1_max = f("m1_max"); m1_step = f("m1_step")
    m2_min = f("m2_min"); m2_max = f("m2_max"); m2_step = f("m2_step")
    np_min = i("Np_min"); np_max = i("Np_max")
    zr2_min = i("Zr2_min"); zr2_max = i("Zr2_max")
    zp2_min = i("Zp2_min"); zp2_max = i("Zp2_max")
    zr1_min = i("Zr1_min"); zr1_max = i("Zr1_max")
    zs1_min = i("Zs1_min"); zs1_max = i("Zs1_max")

    for lo, hi, name in ((m1_min, m1_max, "m1"), (m2_min, m2_max, "m2"),
                         (np_min, np_max, "Np"), (zr2_min, zr2_max, "Zr2"),
                         (zp2_min, zp2_max, "Zp2"),
                         (zr1_min, zr1_max, "Zr1"),
                         (zs1_min, zs1_max, "Zs1")):
        if lo > hi:
            raise ValueError(name + ": min > max")
    for step, name in ((m1_step, "m1"), (m2_step, "m2")):
        if step <= 0:
            raise ValueError(name + ": step must be > 0")
    if np_min < 2:
        raise ValueError("Np: min must be >= 2")

    return SearchParams(
        m1_min=m1_min, m1_max=m1_max, m1_step=m1_step,
        m2_min=m2_min, m2_max=m2_max, m2_step=m2_step,
        np_min=np_min, np_max=np_max,
        zr2_min=zr2_min, zr2_max=zr2_max,
        zp2_min=zp2_min, zp2_max=zp2_max,
        zr1_min=zr1_min, zr1_max=zr1_max,
        zs1_min=zs1_min, zs1_max=zs1_max)


# ---------------------------------------------------------------- callbacks
def _pump_queue() -> None:
    drained = 0
    while drained < 500:
        try:
            msg = worker_queue.get_nowait()
        except queue.Empty:
            break
        drained += 1
        kind = msg[0]
        if kind == "row":
            tree.insert("", "end", values=msg[1])
        elif kind == "done":
            global last_rows
            rows = msg[1]
            last_rows = rows
            for row in rows:
                tree.insert("", "end", values=row)
            start_button.configure(state="normal")
            count_var.set("Feasible : " + str(len(rows)))
            if rows:
                status_var.set("Done - " + str(len(rows))
                               + " feasible combinations")
                messagebox.showinfo(
                    "Search Complete",
                    "Found " + str(len(rows)) + " feasible combinations.")
            else:
                status_var.set("Done - no feasible combination found")
                messagebox.showinfo("Search Complete",
                                    "No feasible combination was found.")
        elif kind == "error":
            start_button.configure(state="normal")
            status_var.set("Error while searching")
            messagebox.showerror("Search Error", msg[1])
        elif kind == "progress":
            status_var.set(msg[1])
    if start_button.instate(["disabled"]):
        app.after(100, _pump_queue)


def button_start_callback() -> None:
    """Search the parameter space and fill the table with feasible combos."""
    try:
        params = _parse_params()
    except (ValueError, TypeError) as exc:
        messagebox.showerror("Input Error", str(exc))
        return

    for item in tree.get_children():
        tree.delete(item)
    count_var.set("Feasible : 0")
    start_button.configure(state="disabled")
    status_var.set("Searching...")
    app.update_idletasks()

    global search_thread
    search_thread = threading.Thread(
        target=_search_worker, args=(params,), daemon=True)
    search_thread.start()
    app.after(100, _pump_queue)


def button_save_callback() -> None:
    """Ask for a folder and save the current table to ``Result.xlsx``."""
    global last_rows
    if not last_rows:
        messagebox.showwarning("Nothing to Save",
                               "Run a search with the Start button first.")
        return
    if len(last_rows) > EXCEL_MAX_ROWS:
        messagebox.showwarning(
            "Too Many Results",
            "Found " + str(len(last_rows)) + " feasible combinations, more "
            "than the Excel row limit (" + str(EXCEL_MAX_ROWS) + ").\n"
            "Result.xlsx was not saved.  Please narrow the search ranges "
            "and search again.")
        return
    out_dir = filedialog.askdirectory(
        title="Select the folder where Result.xlsx will be saved")
    if not out_dir:
        return
    try:
        path = _save_excel(last_rows, out_dir)
    except Exception as exc:
        status_var.set("Error while saving Result.xlsx")
        messagebox.showerror("Save Error", str(exc))
    else:
        status_var.set("Saved " + str(len(last_rows))
                       + " combinations to " + path)
        messagebox.showinfo("Save Complete",
                            "Saved " + str(len(last_rows))
                            + " combinations to\n" + path)


def button_exit_callback() -> None:
    exit()


def _report_inputs(values: tuple) -> str:
    """Compose a report '## Input Parameters' section for a row.

    Uses the exact keys/layout that design.py parses back, so the loaded
    program reproduces the selected combination.  Ring teeth are stored
    negative in the report while the input widgets expect the positive
    count, mirroring design.py's Saved reports.
    """
    np_, m1, m2, zs1, _zp1, zr1, zp2, zr2 = (str(v) for v in values[:8])
    return ("## Input Parameters\n\n"
            "* Type, TYPE = 1, 3K-Wolfrom\n"
            "* Module1, m1 = " + m1 + "\n"
            "* Module2, m2 = " + m2 + "\n"
            "* Planets Number, Np = " + np_ + "\n"
            "* Ring2 Teeth, Zr2 = -" + zr2 + "\n"
            "* Planet2 Teeth, Zp2 = " + zp2 + "\n"
            "* Ring1 Teeth, Zr1 = -" + zr1 + "\n"
            "* Sun1 Teeth, Zs1 = " + zs1 + "\n")


def _update_pgs_button(_event=None) -> None:
    """Enable the PGS button only when exactly one row is selected."""
    state = "normal" if len(tree.selection()) == 1 else "disabled"
    pgs_button.configure(state=state)


def button_pgs_callback() -> None:
    """Launch design.py with the selected combination's parameters."""
    sel = tree.selection()
    if len(sel) != 1:
        return
    values = tree.item(sel[0], "values")
    tmp = os.path.join(tempfile.gettempdir(), "PGS_preopt_report.md")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(_report_inputs(values))
    except OSError as exc:
        messagebox.showerror("PGS Launch Error", str(exc))
        return
    script_dir = os.path.dirname(os.path.abspath(__file__))
    design_script = os.path.join(script_dir, "design.py")
    try:
        subprocess.Popen([sys.executable, design_script, tmp],
                         cwd=script_dir)
    except OSError as exc:
        messagebox.showerror("PGS Launch Error", str(exc))


# --------------------------------------------------------------------- GUI
def init_parameters() -> None:
    """Populate every input widget with its default value."""
    for key, default in SEARCH_DEFAULTS.items():
        entries[key].insert(0, str(default))


def _configure_style(style: ttk.Style, title_font, section_font) -> None:
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
    style.configure("Treeview", background=CARD, fieldbackground=CARD,
                    foreground=FG, borderwidth=0, rowheight=24)
    style.map("Treeview", background=[("selected", ACCENT)],
              foreground=[("selected", "white")])


def _build_search_space(parent) -> None:
    """Build the min/max/step grid inside the Search Space panel."""
    lf = ttk.LabelFrame(parent, text="Search Space", padding=PAD)
    lf.grid(sticky="ew", pady=(0, PAD))
    lf.columnconfigure(1, weight=1)
    lf.columnconfigure(2, weight=1)
    lf.columnconfigure(3, weight=1)

    columns = [(0, "Parameter", "e"), (1, "Min", "w"),
               (2, "Max", "w"), (3, "Step", "w")]
    for col, text, _anchor in columns:
        ttk.Label(lf, text=text, style="CardMuted.TLabel").grid(
            row=0, column=col, padx=PADX, pady=PADY, sticky="w")

    row = 1
    for key, label_text, has_step, hint in PARAM_ROWS:
        ttk.Label(lf, text=label_text, style="Card.TLabel").grid(
            row=row, column=0, padx=(0, PADX), pady=PADY, sticky="e")
        entries[key + "_min"] = ttk.Entry(lf, width=10)
        entries[key + "_min"].grid(row=row, column=1, padx=PADX, pady=PADY,
                                   sticky="ew")
        entries[key + "_max"] = ttk.Entry(lf, width=10)
        entries[key + "_max"].grid(row=row, column=2, padx=PADX, pady=PADY,
                                   sticky="ew")
        if has_step:
            entries[key + "_step"] = ttk.Entry(lf, width=10)
            entries[key + "_step"].grid(row=row, column=3, padx=PADX,
                                        pady=PADY, sticky="ew")
        else:
            ttk.Label(lf, text="1", style="CardMuted.TLabel").grid(
                row=row, column=3, padx=PADX, pady=PADY, sticky="w")
        ttk.Label(lf, text=hint, style="CardMuted.TLabel").grid(
            row=row, column=4, padx=PADX, pady=PADY, sticky="w")
        row += 1


def _build_result_panel(parent) -> None:
    """Build the feasible-combinations table with its status line."""
    global tree, status_var, count_var
    lf = ttk.LabelFrame(parent, text="Feasible Combinations", padding=PAD)
    lf.grid(sticky="nsew")
    lf.rowconfigure(0, weight=1)
    lf.columnconfigure(0, weight=1)

    tree = ttk.Treeview(lf, columns=COLUMNS, show="headings", height=22)
    for col in COLUMNS:
        tree.heading(col, text=col)
        tree.column(col, anchor="center", width=80)
    tree.grid(row=0, column=0, sticky="nsew")

    vsb = ttk.Scrollbar(lf, orient="vertical", command=tree.yview)
    vsb.grid(row=0, column=1, sticky="ns")
    hsb = ttk.Scrollbar(lf, orient="horizontal", command=tree.xview)
    hsb.grid(row=1, column=0, sticky="ew")
    tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    tree.bind("<<TreeviewSelect>>", _update_pgs_button)

    status_var = tk.StringVar(value="Ready")
    count_var = tk.StringVar(value="Feasible : 0")
    band = ttk.Frame(lf, style="App.TFrame")
    band.grid(row=2, column=0, columnspan=2, sticky="ew")
    ttk.Label(band, textvariable=count_var, style="Card.TLabel").pack(
        side="left", padx=(0, PADX), pady=(PAD, 0))
    ttk.Label(band, textvariable=status_var, style="CardMuted.TLabel").pack(
        side="right", pady=(PAD, 0))


def _build_checks_panel(parent) -> None:
    """List the twelve feasibility conditions that a combo must pass."""
    lf = ttk.LabelFrame(parent, text="Feasibility Conditions", padding=PAD)
    lf.grid(sticky="ew", pady=(0, PAD))
    body = "\n".join(
        "{:>2}.  {}".format(i + 1, name)
        for i, name in enumerate(CHECK_NAMES))
    ttk.Label(lf, text=body, style="CardMuted.TLabel", justify="left",
              wraplength=560).grid(sticky="w")


def build_gui() -> None:
    """Create the themed application window and lay out the widgets."""
    global app, start_button, pgs_button, save_button
    app = tk.Tk()
    app.title("PRE-OPT 3K-WOLFROM — Gear Combination Search")
    app.configure(background=BG)
    app.resizable(True, True)
    app.minsize(980, 560)
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

    left = ttk.Frame(main, style="App.TFrame")
    left.grid(row=0, column=0, sticky="n", padx=(0, PAD))
    _build_search_space(left)
    _build_checks_panel(left)

    right = ttk.Frame(main, style="App.TFrame")
    right.grid(row=0, column=1, sticky="nsew")
    right.rowconfigure(0, weight=1)
    right.columnconfigure(0, weight=1)
    _build_result_panel(right)

    bar = ttk.Frame(main, style="App.TFrame")
    bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(PAD, 0))
    ttk.Button(bar, text="Exit", style="Danger.TButton",
               command=button_exit_callback).pack(side="right", padx=(0, PAD))
    pgs_button = ttk.Button(bar, text="PGS", style="Accent.TButton",
                            command=button_pgs_callback)
    pgs_button.configure(state="disabled")
    pgs_button.pack(side="right", padx=(0, PAD))
    save_button = ttk.Button(bar, text="Save", style="Accent.TButton",
                             command=button_save_callback)
    save_button.pack(side="right", padx=(0, PAD))
    start_button = ttk.Button(bar, text="Start", style="Accent.TButton",
                              command=button_start_callback)
    start_button.pack(side="right", padx=(0, PAD))


def main() -> None:
    build_gui()
    init_parameters()
    app.mainloop()


if __name__ == "__main__":
    main()