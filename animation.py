"""Interactive 2D animation popup for Planetary Gear Sets (Simple & 3K-Wolfrom).

Animates every gearbox element (Sun1 ``Gs1``, Planet1 ``Gp1``, Ring1 ``Gr1``,
Carrier, and for 3K-Wolfrom Planet2 ``Gp2`` and Ring2 ``Gr2``) simultaneously
at their exact calculated kinematic speed ratios in a dedicated Tkinter popup
window with embedded Matplotlib rendering, blitting, zoom/pan navigation,
lockup-mode switching, stage filtering, and live speed/angle readouts.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import sys
import time
import tkinter as tk
from tkinter import ttk
from typing import Callable

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

# --- Visual palette (matches design.py) ------------------------------------
BG = "#f0f2f5"
CARD = "#ffffff"
FG = "#1f2937"
MUTED = "#6b7280"
ACCENT = "#2563eb"
BORDER = "#d1d5db"

ELEMENT_COLORS: dict[str, str] = {
    "Gs1": "#2563eb",      # Royal blue (Input Sun1)
    "Gp1": "#16a34a",      # Emerald green (Stage-1 Planet)
    "Gr1": "#475569",      # Dark slate (Stage-1 Ring)
    "Gp2": "#d97706",      # Amber/orange (Stage-2 Planet)
    "Gr2": "#dc2626",      # Crimson red (Stage-2 Ring)
    "Carrier": "#7c3aed",  # Violet (Carrier arms & orbit)
}

VIEW_OPTIONS_WOLFROM = ("Total", "Stage1", "Stage2")
VIEW_OPTIONS_SIMPLE = ("Stage1",)
VIEW_TO_KEYS: dict[str, tuple[str, ...]] = {
    "Total": ("Gs1", "Gp1", "Gr1", "Gp2", "Gr2"),
    "Stage1": ("Gs1", "Gp1", "Gr1"),
    "Stage2": ("Gp2", "Gr2"),
}

FRAME_INTERVAL_MS = 20        # ~50 FPS animation tick
HUD_UPDATE_INTERVAL_S = 0.08  # ~12.5 Hz Tkinter label refresh
DEFAULT_SUN_SPEED_DEG_S = 60.0
MIN_SUN_SPEED_DEG_S = 5.0
MAX_SUN_SPEED_DEG_S = 720.0
STEP_ANGLE_DEG = 5.0


# --------------------------------------------------------------- kinematics
@dataclass(frozen=True)
class AnimationMode:
    """Exact kinematic angular-velocity ratios for one lockup configuration."""

    key: str
    label: str
    total_ratio: float | None
    ratio_display: str
    omega_s1: float
    omega_c: float
    omega_p: float
    omega_r1: float
    omega_r2: float | None
    fixed_elements: tuple[str, ...]
    output_element: str


@dataclass(frozen=True)
class GearGeometry:
    """Centered, closed 2D outline and reference radii of one gear."""

    name: str
    teeth: float
    module: float
    x0: np.ndarray
    y0: np.ndarray
    pc_x0: np.ndarray
    pc_y0: np.ndarray
    r_pitch: float
    r_outer: float
    r_inner: float


@dataclass(frozen=True)
class ProfileSnapshot:
    """One tooth profile variant (e.g. Involute or Cycloid)."""

    name: str
    gears: dict[str, GearGeometry]


@dataclass(frozen=True)
class GearboxSnapshot:
    """Self-contained immutable snapshot of a calculated PGS design."""

    is_wolfrom: bool
    num_planets: int
    dc: float
    ns1: float
    zs1: float
    zp1: float
    zr1: float
    zp2: float
    zr2: float
    sun_phase0: float
    planet_phi0: tuple[float, ...]
    planet_spin0_p1: tuple[float, ...]
    planet_spin0_p2: tuple[float, ...]
    profiles: tuple[ProfileSnapshot, ...]
    modes: tuple[AnimationMode, ...]
    bounding_radius: float


def _close_xy(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return copies of ``(x, y)`` closed into a loop."""
    xc = np.asarray(x, dtype=float).copy()
    yc = np.asarray(y, dtype=float).copy()
    if len(xc) > 0 and (xc[0] != xc[-1] or yc[0] != yc[-1]):
        xc = np.append(xc, xc[0])
        yc = np.append(yc, yc[0])
    return xc, yc


def rotate_translate(
    x: np.ndarray,
    y: np.ndarray,
    angle: float,
    cx: float = 0.0,
    cy: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Rotate ``(x, y)`` by ``angle`` [rad] CCW about origin, then shift by ``(cx, cy)``."""
    ca = math.cos(angle)
    sa = math.sin(angle)
    return ca * x - sa * y + cx, sa * x + ca * y + cy


def _format_signed(value: float, digits: int = 3) -> str:
    if abs(value) < 1e-12:
        return "0"
    return f"{value:+.{digits}f}"


def build_animation_modes(pgs) -> list[AnimationMode]:
    """Build exact kinematic speed-ratio modes matching ``PGS.calc()``."""
    zs1 = float(pgs.zs1)
    zp1 = float(pgs.zp1)
    zr1 = abs(float(pgs.zr1))
    if zs1 <= 0.0 or zp1 <= 0.0 or zr1 <= 0.0:
        raise ValueError(
            "Invalid stage-1 tooth counts for animation "
            f"(Zs1={zs1:g}, Zp1={zp1:g}, |Zr1|={zr1:g})."
        )
    if float(pgs.dc) <= 0.0 or int(pgs.num_planets) < 1:
        raise ValueError(
            f"Invalid carrier geometry (dc={pgs.dc:g}, Np={pgs.num_planets})."
        )

    gp1s = zp1 / zs1

    if not pgs.is_wolfrom:
        # Mode 1: Ring1 Fixed, Carrier Output (classic planetary reduction, ratio g3)
        g3 = 1.0 + zr1 / zs1
        wc_rf = 1.0 / g3
        wp_rf = wc_rf * (1.0 - zr1 / zp1)
        m_rf = AnimationMode(
            key="simple_rf",
            label="Ring1 Fixed, Carrier Output",
            total_ratio=g3,
            ratio_display=f"{g3:+.4f}",
            omega_s1=1.0,
            omega_c=wc_rf,
            omega_p=wp_rf,
            omega_r1=0.0,
            omega_r2=None,
            fixed_elements=("Gr1",),
            output_element="Carrier",
        )
        # Mode 2: Carrier Fixed, Ring1 Output (star train, ratio g4)
        g4 = -(zr1 / zs1)
        wp_cf = -1.0 / gp1s
        wr1_cf = (zp1 / zr1) * wp_cf
        m_cf = AnimationMode(
            key="simple_cf",
            label="Carrier Fixed, Ring1 Output",
            total_ratio=g4,
            ratio_display=f"{g4:+.4f}",
            omega_s1=1.0,
            omega_c=0.0,
            omega_p=wp_cf,
            omega_r1=wr1_cf,
            omega_r2=None,
            fixed_elements=("Carrier",),
            output_element="Gr1",
        )
        return [m_rf, m_cf]

    # 3K-Wolfrom
    zp2 = float(pgs.zp2)
    zr2 = abs(float(pgs.zr2))
    if zp2 <= 0.0 or zr2 <= 0.0:
        raise ValueError(
            "Invalid stage-2 tooth counts for animation "
            f"(Zp2={zp2:g}, |Zr2|={zr2:g})."
        )
    gr2p2 = zr2 / zp2
    l1 = zr1 / zs1
    l2 = (zr1 * zp2) / (zr2 * zp1)

    # Mode 1: Type-3K (Ring1 Fixed, Carrier Free, Ring2 Output)
    wc_3k = 1.0 / (1.0 + l1)
    wp_3k = wc_3k * (1.0 - zr1 / zp1)
    wr2_3k = wc_3k * (1.0 - l2)
    if abs(1.0 - l2) < 1e-12:
        ratio_3k = None
        ratio_3k_str = "∞ (Singular, l2 = 1)"
    else:
        ratio_3k = (1.0 + l1) / (1.0 - l2)
        ratio_3k_str = f"{ratio_3k:+.4f}"
    m_3k = AnimationMode(
        key="wolfrom_3k",
        label="Type-3K (Ring1 Fixed, Ring2 Output)",
        total_ratio=ratio_3k,
        ratio_display=ratio_3k_str,
        omega_s1=1.0,
        omega_c=wc_3k,
        omega_p=wp_3k,
        omega_r1=0.0,
        omega_r2=wr2_3k,
        fixed_elements=("Gr1",),
        output_element="Gr2",
    )

    # Mode 2: Ring2 Fixed, Carrier Output (ratio g1)
    g1 = 1.0 + gr2p2 * gp1s
    wc_g1 = 1.0 / g1
    wp_g1 = wc_g1 * (1.0 - gr2p2)
    wr1_g1 = wc_g1 + (zp1 / zr1) * (wp_g1 - wc_g1)
    m_g1 = AnimationMode(
        key="wolfrom_g1",
        label="Ring2 Fixed, Carrier Output",
        total_ratio=g1,
        ratio_display=f"{g1:+.4f}",
        omega_s1=1.0,
        omega_c=wc_g1,
        omega_p=wp_g1,
        omega_r1=wr1_g1,
        omega_r2=0.0,
        fixed_elements=("Gr2",),
        output_element="Carrier",
    )

    # Mode 3: Carrier Fixed, Ring2 Output (ratio g2)
    g2 = -(gr2p2 * gp1s)
    wp_g2 = -1.0 / gp1s
    wr1_g2 = (zp1 / zr1) * wp_g2
    wr2_g2 = wp_g2 / gr2p2
    m_g2 = AnimationMode(
        key="wolfrom_g2",
        label="Carrier Fixed, Ring2 Output",
        total_ratio=g2,
        ratio_display=f"{g2:+.4f}",
        omega_s1=1.0,
        omega_c=0.0,
        omega_p=wp_g2,
        omega_r1=wr1_g2,
        omega_r2=wr2_g2,
        fixed_elements=("Carrier",),
        output_element="Gr2",
    )

    return [m_3k, m_g1, m_g2]


def build_snapshot(
    pgs,
    profile_sets: list[tuple[str, dict]],
) -> GearboxSnapshot:
    """Capture an immutable geometry & kinematics snapshot from ``pgs`` and ``profile_sets``."""
    modes = tuple(build_animation_modes(pgs))
    gear_keys = ("Gs1", "Gp1", "Gr1", "Gp2", "Gr2") if pgs.is_wolfrom else ("Gs1", "Gp1", "Gr1")

    profiles: list[ProfileSnapshot] = []
    max_r = float(pgs.dc) / 2.0

    for prof_name, gset in profile_sets:
        geom_map: dict[str, GearGeometry] = {}
        for key in gear_keys:
            g = gset[key]
            if len(g.all_teeth_x) < 3:
                raise ValueError(f"Gear '{key}' ({prof_name}) has no valid tooth profile.")
            x0, y0 = _close_xy(g.all_teeth_x, g.all_teeth_y)
            pc_x0 = np.asarray(g.pitch_circle_x, dtype=float) - float(g.x0)
            pc_y0 = np.asarray(g.pitch_circle_y, dtype=float) - float(g.y0)
            radii = np.hypot(x0, y0)
            r_outer = float(radii.max())
            r_inner = float(radii.min())
            r_pitch = float(np.hypot(pc_x0, pc_y0).mean()) if len(pc_x0) else 0.5 * (r_outer + r_inner)
            signed_teeth = -abs(float(g.teeth)) if key in ("Gr1", "Gr2") else abs(float(g.teeth))
            geom_map[key] = GearGeometry(
                name=key,
                teeth=signed_teeth,
                module=float(g.module),
                x0=x0,
                y0=y0,
                pc_x0=pc_x0,
                pc_y0=pc_y0,
                r_pitch=r_pitch,
                r_outer=r_outer,
                r_inner=r_inner,
            )
            if key in ("Gr1", "Gr2"):
                max_r = max(max_r, r_outer + 2.2 * float(g.module))
            elif key in ("Gp1", "Gp2"):
                max_r = max(max_r, float(pgs.dc) / 2.0 + r_outer)
            else:
                max_r = max(max_r, r_outer)
        profiles.append(ProfileSnapshot(name=prof_name, gears=geom_map))

    if not profiles:
        raise ValueError("No gear profiles available for animation.")

    first_gp1 = profiles[0].gears["Gp1"]
    first_gs1 = profiles[0].gears["Gs1"]
    sun_phase0 = (math.pi / first_gs1.teeth) if round(first_gp1.teeth) % 2 == 0 else 0.0

    np_count = int(pgs.num_planets)
    phi0 = tuple((2.0 * math.pi * i) / np_count for i in range(np_count))
    spin0_p1 = tuple((float(pgs.zs1) / float(pgs.zp1)) * p for p in phi0)
    spin0_p2 = (
        tuple(-(abs(float(pgs.zr2)) / float(pgs.zp2)) * p for p in phi0)
        if pgs.is_wolfrom
        else tuple(0.0 for _ in phi0)
    )

    return GearboxSnapshot(
        is_wolfrom=bool(pgs.is_wolfrom),
        num_planets=np_count,
        dc=float(pgs.dc),
        ns1=float(pgs.ns1),
        zs1=float(pgs.zs1),
        zp1=float(pgs.zp1),
        zr1=float(pgs.zr1),
        zp2=float(pgs.zp2) if pgs.is_wolfrom else 0.0,
        zr2=float(pgs.zr2) if pgs.is_wolfrom else 0.0,
        sun_phase0=sun_phase0,
        planet_phi0=phi0,
        planet_spin0_p1=spin0_p1,
        planet_spin0_p2=spin0_p2,
        profiles=tuple(profiles),
        modes=modes,
        bounding_radius=max_r,
    )


def compute_element_angles(mode: AnimationMode, theta_s1: float) -> dict[str, float]:
    """Return angular displacements [rad] of every gearbox element for ``theta_s1``."""
    angles: dict[str, float] = {
        "Gs1": mode.omega_s1 * theta_s1,
        "Gp1": mode.omega_p * theta_s1,
        "Gr1": mode.omega_r1 * theta_s1,
        "Carrier": mode.omega_c * theta_s1,
    }
    if mode.omega_r2 is not None:
        angles["Gp2"] = mode.omega_p * theta_s1
        angles["Gr2"] = mode.omega_r2 * theta_s1
    return angles


def compute_planet_poses(
    snap: GearboxSnapshot,
    theta_c: float,
    theta_p: float,
) -> list[tuple[float, float, float, float]]:
    """Return ``(cx, cy, abs_angle_p1, abs_angle_p2)`` for each planet ``i``."""
    r_c = snap.dc / 2.0
    poses: list[tuple[float, float, float, float]] = []
    for i in range(snap.num_planets):
        arm = snap.planet_phi0[i] + theta_c
        # Planet 0 starts at (0, +dc/2); rotating (0, r_c) CCW by arm gives (-r_c sin, r_c cos).
        cx = -r_c * math.sin(arm)
        cy = r_c * math.cos(arm)
        ang_p1 = snap.planet_phi0[i] + snap.planet_spin0_p1[i] + theta_p
        ang_p2 = snap.planet_phi0[i] + snap.planet_spin0_p2[i] + theta_p
        poses.append((cx, cy, ang_p1, ang_p2))
    return poses


# --------------------------------------------------------------- popup GUI
class GearboxAnimationWindow:
    """Interactive popup window animating all planetary gearbox elements."""

    def __init__(
        self,
        master: tk.Misc,
        snap: GearboxSnapshot,
        *,
        initial_view: str | None = None,
        on_close: Callable[[], None] | None = None,
    ) -> None:
        self.master = master
        self.snap = snap
        self._on_close = on_close

        self.mode_index: int = 0
        self.mode: AnimationMode = snap.modes[0]
        self.theta_s1: float = 0.0  # accumulated Sun1 angle [rad]
        self.playing: bool = True
        self.direction: int = -1 if snap.ns1 < 0.0 else 1
        self.speed_deg_s: float = DEFAULT_SUN_SPEED_DEG_S
        self._last_time: float = time.perf_counter()
        self._last_hud_time: float = 0.0
        self._after_id: str | None = None
        self._bg = None
        self._closed: bool = False
        self._mpl_cids: list[int] = []

        valid_views = VIEW_OPTIONS_WOLFROM if snap.is_wolfrom else VIEW_OPTIONS_SIMPLE
        if initial_view in valid_views:
            self.current_view = initial_view
        else:
            self.current_view = "Total" if snap.is_wolfrom else "Stage1"

        self.win = tk.Toplevel(master)
        kind_str = "3K-Wolfrom" if snap.is_wolfrom else "Simple"
        self.win.title(f"PGS — Planetary Gearbox Animation ({kind_str})")
        self.win.configure(background=BG)
        self.win.minsize(860, 560)
        if sys.platform.startswith("win"):
            try:
                self.win.iconbitmap("PGS.ico")
            except tk.TclError:
                pass

        self._build_ui(valid_views)
        self._build_plot_artists()
        self._apply_visibility()
        self._refresh_mode_table()
        self._update_artists_geometry()
        self._update_hud(force=True)

        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.win.bind("<space>", self._on_space)
        self.win.bind("<r>", self._on_reset_key)
        self.win.bind("<R>", self._on_reset_key)
        self.win.bind("<Left>", lambda _e: self._step_by(-STEP_ANGLE_DEG))
        self.win.bind("<Right>", lambda _e: self._step_by(+STEP_ANGLE_DEG))
        self.win.bind("<Escape>", lambda _e: self.close())

        # Trigger initial full draw and start loop
        self.canvas.draw()
        self._last_time = time.perf_counter()
        self._schedule_next_tick()

    # ------------------------------------------------------------ UI layout
    def _build_ui(self, valid_views: tuple[str, ...]) -> None:
        root = ttk.Frame(self.win, padding=8, style="App.TFrame")
        root.grid(row=0, column=0, sticky="nsew")
        self.win.columnconfigure(0, weight=1)
        self.win.rowconfigure(0, weight=1)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        # --- Left pane: matplotlib figure + toolbar -----------------------
        plot_frame = tk.Frame(
            root,
            background=CARD,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=BORDER,
        )
        plot_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        plot_frame.columnconfigure(0, weight=1)
        plot_frame.rowconfigure(1, weight=1)

        self.fig = Figure(figsize=(6.4, 6.4), dpi=100, facecolor=CARD)
        self.ax = self.fig.add_subplot(111)
        self.fig.subplots_adjust(left=0.10, right=0.97, top=0.92, bottom=0.09)

        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        toolbar_holder = ttk.Frame(plot_frame, style="Card.TFrame")
        toolbar_holder.grid(row=0, column=0, sticky="ew")
        self.toolbar = NavigationToolbar2Tk(self.canvas, toolbar_holder)
        self.toolbar.update()

        canvas_widget = self.canvas.get_tk_widget()
        canvas_widget.grid(row=1, column=0, sticky="nsew")

        self._mpl_cids.append(self.canvas.mpl_connect("draw_event", self._on_draw))

        # --- Right pane: controls & live kinematics -----------------------
        side = ttk.Frame(root, style="App.TFrame")
        side.grid(row=0, column=1, sticky="ns")
        side.columnconfigure(0, weight=1)

        # 1. Configuration card
        cfg = ttk.LabelFrame(side, text="Configuration", padding=8)
        cfg.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        cfg.columnconfigure(1, weight=1)

        ttk.Label(cfg, text="Mode", style="Card.TLabel").grid(
            row=0, column=0, sticky="e", padx=(0, 6), pady=3
        )
        self.mode_var = tk.StringVar(value=self.mode.label)
        self.mode_cb = ttk.Combobox(
            cfg,
            textvariable=self.mode_var,
            values=[m.label for m in self.snap.modes],
            state="readonly",
            width=30,
        )
        self.mode_cb.grid(row=0, column=1, sticky="ew", pady=3)
        self.mode_cb.bind("<<ComboboxSelected>>", self._on_mode_changed)

        ttk.Label(cfg, text="View", style="Card.TLabel").grid(
            row=1, column=0, sticky="e", padx=(0, 6), pady=3
        )
        self.view_var = tk.StringVar(value=self.current_view)
        self.view_cb = ttk.Combobox(
            cfg,
            textvariable=self.view_var,
            values=list(valid_views),
            state="readonly",
            width=16,
        )
        self.view_cb.grid(row=1, column=1, sticky="w", pady=3)
        self.view_cb.bind("<<ComboboxSelected>>", self._on_view_changed)

        prof_names = " + ".join(p.name for p in self.snap.profiles)
        info_text = (
            f"Profile: {prof_names}   |   Np = {self.snap.num_planets}"
            f"   |   Rc = {self.snap.dc / 2.0:.2f} mm"
        )
        ttk.Label(cfg, text=info_text, style="CardMuted.TLabel").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(4, 0)
        )

        # 2. Playback controls card
        ctrl = ttk.LabelFrame(side, text="Playback Controls", padding=8)
        ctrl.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        ctrl.columnconfigure(0, weight=1)

        btn_row = ttk.Frame(ctrl, style="App.TFrame")
        btn_row.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self.play_btn = ttk.Button(
            btn_row,
            text="Pause",
            style="Accent.TButton",
            width=8,
            command=self.toggle_play,
        )
        self.play_btn.pack(side="left", padx=(0, 4))
        ttk.Button(
            btn_row,
            text="Reset",
            style="TButton",
            width=6,
            command=self.reset_angles,
        ).pack(side="left", padx=(0, 4))
        ttk.Button(
            btn_row,
            text="◀ -5°",
            style="Small.TButton",
            command=lambda: self._step_by(-STEP_ANGLE_DEG),
        ).pack(side="left", padx=(0, 2))
        ttk.Button(
            btn_row,
            text="+5° ▶",
            style="Small.TButton",
            command=lambda: self._step_by(+STEP_ANGLE_DEG),
        ).pack(side="left", padx=(0, 4))

        dir_row = ttk.Frame(ctrl, style="App.TFrame")
        dir_row.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(dir_row, text="Direction:", style="Card.TLabel").pack(
            side="left", padx=(0, 6)
        )
        self.dir_btn = ttk.Button(
            dir_row,
            text=self._dir_label(),
            style="Small.TButton",
            width=11,
            command=self.toggle_direction,
        )
        self.dir_btn.pack(side="left")

        speed_hdr = ttk.Frame(ctrl, style="App.TFrame")
        speed_hdr.grid(row=2, column=0, sticky="ew")
        ttk.Label(speed_hdr, text="Visual Input Speed:", style="Card.TLabel").pack(
            side="left"
        )
        self.speed_label = ttk.Label(
            speed_hdr,
            text=self._speed_text(),
            style="CardMuted.TLabel",
        )
        self.speed_label.pack(side="right")

        self.speed_var = tk.DoubleVar(value=self.speed_deg_s)
        speed_scale = ttk.Scale(
            ctrl,
            from_=MIN_SUN_SPEED_DEG_S,
            to=MAX_SUN_SPEED_DEG_S,
            variable=self.speed_var,
            orient="horizontal",
            command=self._on_speed_changed,
        )
        speed_scale.grid(row=3, column=0, sticky="ew", pady=(2, 6))

        chk_row = ttk.Frame(ctrl, style="App.TFrame")
        chk_row.grid(row=4, column=0, sticky="ew")
        self.show_pitch_var = tk.BooleanVar(value=True)
        self.show_markers_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            chk_row,
            text="Pitch circles",
            variable=self.show_pitch_var,
            command=self._on_overlay_toggled,
        ).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(
            chk_row,
            text="Carrier & markers",
            variable=self.show_markers_var,
            command=self._on_overlay_toggled,
        ).pack(side="left")

        # 3. Calculated ratios & live speeds card
        kin = ttk.LabelFrame(side, text="Calculated Ratios & Live Kinematics", padding=8)
        kin.grid(row=2, column=0, sticky="nsew")
        side.rowconfigure(2, weight=1)
        kin.columnconfigure(0, weight=1)

        self.summary_label = ttk.Label(
            kin,
            text="",
            style="Section.TLabel",
            justify="left",
        )
        self.summary_label.grid(row=0, column=0, sticky="w", pady=(0, 2))
        self.input_rpm_label = ttk.Label(
            kin,
            text=f"Input Speed ns1 = {_format_signed(self.snap.ns1, 2)} [rpm]",
            style="CardMuted.TLabel",
        )
        self.input_rpm_label.grid(row=1, column=0, sticky="w", pady=(0, 6))

        tbl = ttk.Frame(kin, style="App.TFrame")
        tbl.grid(row=2, column=0, sticky="ew")
        for col, (text, anchor, pad) in enumerate(
            (
                ("Element", "w", (0, 6)),
                ("ω / ωs1", "e", (4, 6)),
                ("Speed [rpm]", "e", (4, 6)),
                ("Angle [deg]", "e", (4, 0)),
            )
        ):
            ttk.Label(tbl, text=text, style="CardMuted.TLabel", anchor=anchor).grid(
                row=0, column=col, sticky="ew", padx=pad, pady=(0, 3)
            )
        tbl.columnconfigure(0, weight=1)

        self._row_widgets: dict[str, dict[str, ttk.Label]] = {}
        elem_order = (
            ("Gs1", "Gp1", "Gr1", "Carrier", "Gp2", "Gr2")
            if self.snap.is_wolfrom
            else ("Gs1", "Gp1", "Gr1", "Carrier")
        )
        for row_idx, key in enumerate(elem_order, start=1):
            name_frame = ttk.Frame(tbl, style="App.TFrame")
            name_frame.grid(row=row_idx, column=0, sticky="w", padx=(0, 6), pady=2)
            swatch = tk.Label(
                name_frame,
                text="■",
                fg=ELEMENT_COLORS[key],
                bg=BG,
                font=("Segoe UI", 10, "bold"),
            )
            swatch.pack(side="left", padx=(0, 4))
            elem_txt = self._element_label(key)
            name_lbl = ttk.Label(name_frame, text=elem_txt, style="Card.TLabel")
            name_lbl.pack(side="left")

            ratio_lbl = ttk.Label(tbl, text="", style="Card.TLabel", anchor="e", width=9)
            ratio_lbl.grid(row=row_idx, column=1, sticky="e", padx=(4, 6), pady=2)
            rpm_lbl = ttk.Label(tbl, text="", style="Card.TLabel", anchor="e", width=11)
            rpm_lbl.grid(row=row_idx, column=2, sticky="e", padx=(4, 6), pady=2)
            ang_lbl = ttk.Label(tbl, text="", style="Card.TLabel", anchor="e", width=10)
            ang_lbl.grid(row=row_idx, column=3, sticky="e", padx=(4, 0), pady=2)
            self._row_widgets[key] = {
                "name": name_lbl,
                "ratio": ratio_lbl,
                "rpm": rpm_lbl,
                "angle": ang_lbl,
            }

        ttk.Label(
            kin,
            text="Shortcuts: Space (Play/Pause) · R (Reset) · ←/→ (Step ±5°) · Toolbar to Zoom/Pan",
            style="CardMuted.TLabel",
            wraplength=310,
            justify="left",
        ).grid(row=3, column=0, sticky="sw", pady=(10, 0))

    def _element_label(self, key: str) -> str:
        if key == "Carrier":
            return f"Carrier ({self.snap.num_planets}p)"
        z_map = {
            "Gs1": self.snap.zs1,
            "Gp1": self.snap.zp1,
            "Gr1": self.snap.zr1,
            "Gp2": self.snap.zp2,
            "Gr2": self.snap.zr2,
        }
        z = z_map[key]
        z_str = f"{int(round(z))}" if abs(z - round(z)) < 1e-6 else f"{z:.1f}"
        return f"{key} ({z_str}T)"

    def _dir_label(self) -> str:
        return "CCW (+)" if self.direction > 0 else "CW (-)"

    def _speed_text(self) -> str:
        rpm_vis = self.speed_deg_s / 6.0  # 360 deg/s = 60 rpm
        return f"{self.speed_deg_s:.0f}°/s ({rpm_vis:.1f} rpm)"

    # -------------------------------------------------------- plot artists
    def _build_plot_artists(self) -> None:
        ax = self.ax
        ax.clear()
        ax.set_aspect("equal", adjustable="box")
        ax.grid(True, linestyle=":", alpha=0.45, color="#94a3b8")
        ax.set_xlabel("X [mm]", fontsize=9, color=FG)
        ax.set_ylabel("Y [mm]", fontsize=9, color=FG)
        ax.tick_params(labelsize=8, colors=MUTED)

        lim = self.snap.bounding_radius * 1.12
        ax.set_xlim(-lim, lim)
        ax.set_ylim(-lim, lim)

        # Static reference: carrier orbit circle (non-animated or animated; animated lets us toggle cleanly)
        self._animated_artists: list = []

        # Per-profile tooth artists: list of dicts per profile
        # Primary profile: solid lines in element colors; secondary ("All"): dashed translucent
        self._gear_lines: list[dict[str, list]] = []
        self._pitch_lines: dict[str, list] = {}
        self._rim_lines: dict[str, object] = {}
        self._marker_artists: dict[str, list] = {}

        primary = self.snap.profiles[0]

        # 1. Carrier orbit circle & spider arms (behind gears)
        theta_c = np.linspace(0.0, 2.0 * math.pi, 181)
        rc = self.snap.dc / 2.0
        (self._carrier_orbit_line,) = ax.plot(
            rc * np.cos(theta_c),
            rc * np.sin(theta_c),
            color=ELEMENT_COLORS["Carrier"],
            linestyle="--",
            linewidth=1.0,
            alpha=0.55,
            animated=True,
            zorder=1,
        )
        self._animated_artists.append(self._carrier_orbit_line)

        self._carrier_arm_lines = []
        for _ in range(self.snap.num_planets):
            (arm_l,) = ax.plot(
                [], [],
                color=ELEMENT_COLORS["Carrier"],
                linewidth=1.6,
                alpha=0.55,
                animated=True,
                zorder=2,
            )
            self._carrier_arm_lines.append(arm_l)
            self._animated_artists.append(arm_l)

        (self._carrier_pins,) = ax.plot(
            [], [],
            linestyle="None",
            marker="o",
            markersize=4.5,
            markerfacecolor=CARD,
            markeredgecolor=ELEMENT_COLORS["Carrier"],
            markeredgewidth=1.4,
            animated=True,
            zorder=6,
        )
        self._animated_artists.append(self._carrier_pins)

        # 2. Pitch circles (from primary profile)
        gear_keys = ("Gs1", "Gp1", "Gr1", "Gp2", "Gr2") if self.snap.is_wolfrom else ("Gs1", "Gp1", "Gr1")
        for key in gear_keys:
            geom = primary.gears[key]
            style = ":" if key in ("Gs1", "Gp1", "Gr1") else "--"
            lst = []
            count = self.snap.num_planets if key.startswith("Gp") else 1
            for _ in range(count):
                (pl,) = ax.plot(
                    geom.pc_x0,
                    geom.pc_y0,
                    color=ELEMENT_COLORS[key],
                    linestyle=style,
                    linewidth=0.8,
                    alpha=0.45,
                    animated=True,
                    zorder=2,
                )
                lst.append(pl)
                self._animated_artists.append(pl)
            self._pitch_lines[key] = lst

        # 3. Ring outer reference rims (Gr1, Gr2)
        for key in ("Gr1", "Gr2"):
            if key not in primary.gears:
                continue
            geom = primary.gears[key]
            r_rim = geom.r_outer + 1.5 * geom.module
            (rim,) = ax.plot(
                r_rim * np.cos(theta_c),
                r_rim * np.sin(theta_c),
                color=ELEMENT_COLORS[key],
                linewidth=0.9,
                alpha=0.35,
                animated=True,
                zorder=2,
            )
            self._rim_lines[key] = rim
            self._animated_artists.append(rim)

        # 4. Gear tooth outlines (primary + optional secondary overlay)
        for prof_idx, prof in enumerate(self.snap.profiles):
            is_overlay = prof_idx > 0
            ls = "--" if is_overlay else "-"
            lw = 0.95 if is_overlay else 1.25
            alpha = 0.55 if is_overlay else 0.95
            z_base = 3 if is_overlay else 4
            prof_lines: dict[str, list] = {}
            for key in gear_keys:
                color = ELEMENT_COLORS[key]
                count = self.snap.num_planets if key.startswith("Gp") else 1
                lst = []
                for _ in range(count):
                    (gl,) = ax.plot(
                        [], [],
                        color=color,
                        linestyle=ls,
                        linewidth=lw,
                        alpha=alpha,
                        animated=True,
                        zorder=z_base + (1 if key in ("Gp2", "Gr2") else 0),
                    )
                    lst.append(gl)
                    self._animated_artists.append(gl)
                prof_lines[key] = lst
            self._gear_lines.append(prof_lines)

        # 5. Rotation reference markers (spokes & indicator dots) so every gear's
        #    rotation speed and direction is immediately legible!
        for key in gear_keys:
            color = ELEMENT_COLORS[key]
            if key == "Gs1":
                (spoke,) = ax.plot(
                    [], [],
                    color=color,
                    linewidth=1.8,
                    alpha=0.85,
                    animated=True,
                    zorder=7,
                )
                (dot,) = ax.plot(
                    [], [],
                    linestyle="None",
                    marker="o",
                    markersize=5.0,
                    color=color,
                    animated=True,
                    zorder=8,
                )
                self._marker_artists[key] = [spoke, dot]
                self._animated_artists.extend([spoke, dot])
            elif key.startswith("Gp"):
                lst = []
                for _ in range(self.snap.num_planets):
                    (spoke,) = ax.plot(
                        [], [],
                        color=color,
                        linewidth=1.5,
                        alpha=0.85,
                        animated=True,
                        zorder=7,
                    )
                    (dot,) = ax.plot(
                        [], [],
                        linestyle="None",
                        marker="o",
                        markersize=4.0,
                        color=color,
                        animated=True,
                        zorder=8,
                    )
                    lst.extend([spoke, dot])
                self._marker_artists[key] = lst
                self._animated_artists.extend(lst)
            else:  # Ring1 / Ring2 outer marker tick + prominent dot
                (tick,) = ax.plot(
                    [], [],
                    color=color,
                    linewidth=2.4,
                    alpha=0.95,
                    animated=True,
                    zorder=7,
                )
                (dot,) = ax.plot(
                    [], [],
                    linestyle="None",
                    marker="o",
                    markersize=6.5,
                    markerfacecolor=color,
                    markeredgecolor=CARD,
                    markeredgewidth=1.0,
                    animated=True,
                    zorder=8,
                )
                self._marker_artists[key] = [tick, dot]
                self._animated_artists.extend([tick, dot])

        self._update_axes_title()

    def _update_axes_title(self) -> None:
        kind = "3K-Wolfrom" if self.snap.is_wolfrom else "Simple"
        self.ax.set_title(
            f"{kind} — {self.mode.label}   |   Ratio: {self.mode.ratio_display}",
            fontsize=10,
            fontweight="bold",
            color=FG,
            pad=8,
        )

    def _apply_visibility(self) -> None:
        visible_keys = set(VIEW_TO_KEYS[self.current_view])
        show_pitch = bool(self.show_pitch_var.get())
        show_markers = bool(self.show_markers_var.get())

        for prof_lines in self._gear_lines:
            for key, lst in prof_lines.items():
                vis = key in visible_keys
                for artist in lst:
                    artist.set_visible(vis)

        for key, lst in self._pitch_lines.items():
            vis = show_pitch and (key in visible_keys)
            for artist in lst:
                artist.set_visible(vis)

        for key, rim in self._rim_lines.items():
            rim.set_visible(key in visible_keys)

        for key, lst in self._marker_artists.items():
            vis = show_markers and (key in visible_keys)
            for artist in lst:
                artist.set_visible(vis)

        self._carrier_orbit_line.set_visible(show_markers)
        for arm in self._carrier_arm_lines:
            arm.set_visible(show_markers)
        self._carrier_pins.set_visible(show_markers)

    def _update_artists_geometry(self) -> None:
        """Compute and assign transformed coordinates for every gear & marker."""
        angles = compute_element_angles(self.mode, self.theta_s1)
        th_s1 = angles["Gs1"]
        th_c = angles["Carrier"]
        th_p = angles["Gp1"]
        th_r1 = angles["Gr1"]
        th_r2 = angles.get("Gr2", 0.0)

        poses = compute_planet_poses(self.snap, th_c, th_p)
        primary = self.snap.profiles[0]

        # 1. Carrier spider arms & planet pins
        pin_xs: list[float] = []
        pin_ys: list[float] = []
        for i, (cx, cy, _, _) in enumerate(poses):
            self._carrier_arm_lines[i].set_data([0.0, cx], [0.0, cy])
            pin_xs.append(cx)
            pin_ys.append(cy)
        self._carrier_pins.set_data(pin_xs, pin_ys)

        # 2. Moving planet pitch circles (sun/ring pitch circles stay centered at origin)
        for key in ("Gp1", "Gp2"):
            if key not in self._pitch_lines:
                continue
            geom = primary.gears[key]
            for i, (cx, cy, _, _) in enumerate(poses):
                self._pitch_lines[key][i].set_data(geom.pc_x0 + cx, geom.pc_y0 + cy)

        # 3. Gear teeth outlines (all active profiles)
        for prof_idx, prof in enumerate(self.snap.profiles):
            lines = self._gear_lines[prof_idx]

            # Sun1
            gs1 = prof.gears["Gs1"]
            sx, sy = rotate_translate(gs1.x0, gs1.y0, self.snap.sun_phase0 + th_s1)
            lines["Gs1"][0].set_data(sx, sy)

            # Ring1
            gr1 = prof.gears["Gr1"]
            r1x, r1y = rotate_translate(gr1.x0, gr1.y0, th_r1)
            lines["Gr1"][0].set_data(r1x, r1y)

            # Planet1 array
            gp1 = prof.gears["Gp1"]
            for i, (cx, cy, ang_p1, _) in enumerate(poses):
                px, py = rotate_translate(gp1.x0, gp1.y0, ang_p1, cx, cy)
                lines["Gp1"][i].set_data(px, py)

            # Wolfrom stage-2 elements
            if self.snap.is_wolfrom:
                gp2 = prof.gears["Gp2"]
                for i, (cx, cy, _, ang_p2) in enumerate(poses):
                    p2x, p2y = rotate_translate(gp2.x0, gp2.y0, ang_p2, cx, cy)
                    lines["Gp2"][i].set_data(p2x, p2y)

                gr2 = prof.gears["Gr2"]
                r2x, r2y = rotate_translate(gr2.x0, gr2.y0, th_r2)
                lines["Gr2"][0].set_data(r2x, r2y)

        # 4. Rotation reference markers
        # Sun1 spoke along initial +y rotated by th_s1
        gs1_g = primary.gears["Gs1"]
        r_s = max(0.35 * gs1_g.r_pitch, gs1_g.r_inner * 0.85)
        ang_s = math.pi / 2.0 + self.snap.sun_phase0 + th_s1
        msx, msy = r_s * math.cos(ang_s), r_s * math.sin(ang_s)
        self._marker_artists["Gs1"][0].set_data([0.0, msx], [0.0, msy])
        self._marker_artists["Gs1"][1].set_data([msx], [msy])

        # Planet1 markers
        gp1_g = primary.gears["Gp1"]
        r_p1 = max(0.35 * gp1_g.r_pitch, gp1_g.r_inner * 0.82)
        for i, (cx, cy, ang_p1, _) in enumerate(poses):
            a = math.pi / 2.0 + ang_p1
            mx, my = cx + r_p1 * math.cos(a), cy + r_p1 * math.sin(a)
            self._marker_artists["Gp1"][2 * i].set_data([cx, mx], [cy, my])
            self._marker_artists["Gp1"][2 * i + 1].set_data([mx], [my])

        # Ring1 marker tick (starts at +y top of ring rim)
        gr1_g = primary.gears["Gr1"]
        r1_in = gr1_g.r_outer
        r1_out = gr1_g.r_outer + 2.2 * gr1_g.module
        a_r1 = math.pi / 2.0 + th_r1
        self._marker_artists["Gr1"][0].set_data(
            [r1_in * math.cos(a_r1), r1_out * math.cos(a_r1)],
            [r1_in * math.sin(a_r1), r1_out * math.sin(a_r1)],
        )
        self._marker_artists["Gr1"][1].set_data(
            [r1_out * math.cos(a_r1)], [r1_out * math.sin(a_r1)]
        )

        # Wolfrom stage-2 markers
        if self.snap.is_wolfrom:
            gp2_g = primary.gears["Gp2"]
            r_p2 = max(0.35 * gp2_g.r_pitch, gp2_g.r_inner * 0.78)
            for i, (cx, cy, _, ang_p2) in enumerate(poses):
                a = math.pi / 2.0 + ang_p2
                mx, my = cx + r_p2 * math.cos(a), cy + r_p2 * math.sin(a)
                self._marker_artists["Gp2"][2 * i].set_data([cx, mx], [cy, my])
                self._marker_artists["Gp2"][2 * i + 1].set_data([mx], [my])

            gr2_g = primary.gears["Gr2"]
            r2_in = gr2_g.r_outer
            r2_out = gr2_g.r_outer + 2.2 * gr2_g.module
            # Offset initial visual tick slightly if rings share nearly identical radii
            base_r2 = math.pi / 2.0 if abs(r2_out - r1_out) > 2.5 else (math.pi / 2.0 - 0.14)
            a_r2 = base_r2 + th_r2
            self._marker_artists["Gr2"][0].set_data(
                [r2_in * math.cos(a_r2), r2_out * math.cos(a_r2)],
                [r2_in * math.sin(a_r2), r2_out * math.sin(a_r2)],
            )
            self._marker_artists["Gr2"][1].set_data(
                [r2_out * math.cos(a_r2)], [r2_out * math.sin(a_r2)]
            )

    def _draw_animated(self) -> None:
        for artist in self._animated_artists:
            if artist.get_visible():
                self.ax.draw_artist(artist)

    def _on_draw(self, _event) -> None:
        if self._closed:
            return
        self._bg = self.canvas.copy_from_bbox(self.ax.bbox)
        self._draw_animated()

    def _render_frame(self) -> None:
        if self._closed:
            return
        if self._bg is None:
            self.canvas.draw()
            return
        try:
            self.canvas.restore_region(self._bg)
            self._draw_animated()
            self.canvas.blit(self.ax.bbox)
        except Exception:
            self._bg = None
            self.canvas.draw_idle()

    # ------------------------------------------------------------ HUD table
    def _refresh_mode_table(self) -> None:
        self.summary_label.configure(
            text=f"Total Ratio ({self.mode.output_element} out) = {self.mode.ratio_display}"
        )
        omegas = {
            "Gs1": self.mode.omega_s1,
            "Gp1": self.mode.omega_p,
            "Gr1": self.mode.omega_r1,
            "Carrier": self.mode.omega_c,
            "Gp2": self.mode.omega_p,
            "Gr2": self.mode.omega_r2 if self.mode.omega_r2 is not None else 0.0,
        }
        for key, widgets in self._row_widgets.items():
            w = omegas[key]
            if key in self.mode.fixed_elements or abs(w) < 1e-12:
                widgets["ratio"].configure(text="Fixed", foreground=MUTED)
                widgets["rpm"].configure(text="0.00", foreground=MUTED)
            else:
                widgets["ratio"].configure(text=f"{w:+.4f}", foreground=FG)
                rpm = w * self.snap.ns1
                widgets["rpm"].configure(text=f"{rpm:+.2f}", foreground=FG)

    def _update_hud(self, *, force: bool = False) -> None:
        now = time.perf_counter()
        if not force and (now - self._last_hud_time) < HUD_UPDATE_INTERVAL_S:
            return
        self._last_hud_time = now
        angles = compute_element_angles(self.mode, self.theta_s1)
        for key, widgets in self._row_widgets.items():
            if key in self.mode.fixed_elements:
                widgets["angle"].configure(text="0.0°", foreground=MUTED)
                continue
            deg = math.degrees(angles.get(key, 0.0))
            if abs(deg) >= 10000.0:
                widgets["angle"].configure(text=f"{deg / 360.0:+.1f} rev", foreground=FG)
            else:
                widgets["angle"].configure(text=f"{deg:+.1f}°", foreground=FG)

    # -------------------------------------------------------- animation loop
    def _schedule_next_tick(self) -> None:
        if self._closed:
            return
        self._after_id = self.win.after(FRAME_INTERVAL_MS, self._tick)

    def _tick(self) -> None:
        self._after_id = None
        if self._closed or not self.win.winfo_exists():
            return
        now = time.perf_counter()
        dt = min(max(now - self._last_time, 0.0), 0.1)
        self._last_time = now

        if self.playing:
            dtheta = math.radians(self.speed_deg_s * dt) * self.direction
            self.theta_s1 += dtheta
            self._update_artists_geometry()
            self._render_frame()
            self._update_hud()

        self._schedule_next_tick()

    # ------------------------------------------------------------- callbacks
    def toggle_play(self) -> None:
        self.playing = not self.playing
        self.play_btn.configure(text="Pause" if self.playing else "Play")
        self._last_time = time.perf_counter()

    def reset_angles(self) -> None:
        self.theta_s1 = 0.0
        self._update_artists_geometry()
        self._render_frame()
        self._update_hud(force=True)

    def toggle_direction(self) -> None:
        self.direction = -self.direction
        self.dir_btn.configure(text=self._dir_label())

    def _step_by(self, delta_deg: float) -> None:
        if self.playing:
            self.toggle_play()
        self.theta_s1 += math.radians(delta_deg)
        self._update_artists_geometry()
        self._render_frame()
        self._update_hud(force=True)

    def _on_speed_changed(self, _val: str) -> None:
        self.speed_deg_s = float(self.speed_var.get())
        self.speed_label.configure(text=self._speed_text())

    def _on_mode_changed(self, _event=None) -> None:
        idx = self.mode_cb.current()
        if idx < 0 or idx >= len(self.snap.modes):
            return
        self.mode_index = idx
        self.mode = self.snap.modes[idx]
        self.theta_s1 = 0.0
        self._update_axes_title()
        self._refresh_mode_table()
        self._update_artists_geometry()
        self._update_hud(force=True)
        self._bg = None
        self.canvas.draw_idle()

    def _on_view_changed(self, _event=None) -> None:
        sel = self.view_var.get()
        if sel not in VIEW_TO_KEYS:
            return
        self.current_view = sel
        self._apply_visibility()
        self._render_frame()

    def _on_overlay_toggled(self) -> None:
        self._apply_visibility()
        self._render_frame()

    def _on_space(self, event) -> str | None:
        if isinstance(event.widget, (ttk.Combobox, ttk.Entry)):
            return None
        self.toggle_play()
        return "break"

    def _on_reset_key(self, event) -> str | None:
        if isinstance(event.widget, (ttk.Combobox, ttk.Entry)):
            return None
        self.reset_angles()
        return "break"

    def is_alive(self) -> bool:
        return (not self._closed) and bool(self.win.winfo_exists())

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._after_id is not None:
            try:
                self.win.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None
        for cid in self._mpl_cids:
            try:
                self.canvas.mpl_disconnect(cid)
            except Exception:
                pass
        self._mpl_cids.clear()
        try:
            if self.win.winfo_exists():
                self.win.destroy()
        except tk.TclError:
            pass
        if self._on_close is not None:
            self._on_close()


def open_animation_window(
    master: tk.Misc,
    pgs,
    profile_sets: list[tuple[str, dict]],
    *,
    initial_view: str | None = None,
    on_close: Callable[[], None] | None = None,
) -> GearboxAnimationWindow:
    """Create and open a new planetary gearbox animation popup window."""
    snap = build_snapshot(pgs, profile_sets)
    return GearboxAnimationWindow(
        master,
        snap,
        initial_view=initial_view,
        on_close=on_close,
    )
