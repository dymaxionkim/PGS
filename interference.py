"""Kinematic 1-pitch rolling-sweep tip interference verification.

Works uniformly on both Involute (``GPG``) and Cycloid (``CPG``) gear sets:
sweeps each meshing pair (``Gs1-Gp1``, ``Gp1-Gr1``, and ``Gp2-Gr2`` for
Wolfrom) across one full tooth pitch in the carrier frame, detects
bidirectional polygon interference via exact point-to-segment penetration
depth, checks planet-to-planet tip clearance, and renders zoomed worst-phase
inspection plots with interfering points highlighted in red.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.path import Path

DEFAULT_SWEEP_STEPS: int = 36


@dataclass
class MeshInterferenceResult:
    """Interference check result for one mesh or planet-to-planet pair."""

    mesh_name: str
    profile_name: str
    passed: bool
    max_penetration: float = 0.0
    min_clearance: float | None = None
    tolerance: float = 0.002
    worst_angle_deg: float = 0.0
    worst_theta_a: float = 0.0
    worst_theta_b: float = 0.0
    hit_points: np.ndarray = field(default_factory=lambda: np.empty((0, 2)))
    detail: str = ""


@dataclass
class ProfileInterferenceReport:
    """Complete kinematic tip-interference report for one tooth profile."""

    profile_name: str
    meshes: list[MeshInterferenceResult] = field(default_factory=list)
    planets: list[MeshInterferenceResult] = field(default_factory=list)
    analytical_notes: list[str] = field(default_factory=list)

    @property
    def all_results(self) -> list[MeshInterferenceResult]:
        return self.meshes + self.planets

    @property
    def has_fail(self) -> bool:
        return any(not r.passed for r in self.all_results)


# --------------------------------------------------------------- geometry math
def _rot2(x: np.ndarray, y: np.ndarray, angle: float) -> tuple[np.ndarray, np.ndarray]:
    c, s = np.cos(angle), np.sin(angle)
    return c * x - s * y, s * x + c * y


def _close_xy(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if len(x) > 0 and (x[0] != x[-1] or y[0] != y[-1]):
        return np.append(x, x[0]), np.append(y, y[0])
    return x, y


def _min_seg_dist(pts: np.ndarray, px: np.ndarray, py: np.ndarray) -> np.ndarray:
    """Exact minimum Euclidean distance from each point in ``pts`` to segments of ``(px, py)``."""
    if len(pts) == 0 or len(px) < 2:
        return np.empty(0, dtype=float)
    a = np.column_stack([px[:-1], py[:-1]])
    b = np.column_stack([px[1:], py[1:]])
    ab = b - a
    ab2 = np.sum(ab * ab, axis=1) + 1e-18

    # Bounding-box cull of segments near the candidate points for speed.
    pad = 1.5
    xmin, ymin = pts.min(axis=0) - pad
    xmax, ymax = pts.max(axis=0) + pad
    seg_mask = (
        (np.maximum(a[:, 0], b[:, 0]) >= xmin)
        & (np.minimum(a[:, 0], b[:, 0]) <= xmax)
        & (np.maximum(a[:, 1], b[:, 1]) >= ymin)
        & (np.minimum(a[:, 1], b[:, 1]) <= ymax)
    )
    if not np.any(seg_mask):
        # Fallback to all segments if points are far from boundary.
        seg_mask = np.ones(len(a), dtype=bool)
    a = a[seg_mask]
    ab = ab[seg_mask]
    ab2 = ab2[seg_mask]

    ap = pts[:, None, :] - a[None, :, :]
    t = np.clip(np.sum(ap * ab[None, :, :], axis=2) / ab2[None, :], 0.0, 1.0)
    proj = a[None, :, :] + t[:, :, None] * ab[None, :, :]
    return np.min(np.linalg.norm(pts[:, None, :] - proj, axis=2), axis=1)


def _mesh_tolerance(module: float) -> float:
    """Polygonal chord tolerance [mm] separating discretization noise from real interference."""
    return max(0.003 * abs(module), 0.002)


# --------------------------------------------------------------- pair sweeps
def _sweep_external(
    sun,
    planet,
    dc: float,
    profile_name: str,
    n_steps: int,
) -> MeshInterferenceResult:
    """1-pitch bidirectional rolling sweep for external mesh ``Gs1-Gp1``."""
    tol = _mesh_tolerance(sun.module)
    if sun.teeth <= 0 or planet.teeth <= 0 or len(sun.all_teeth_x) < 3 or len(planet.all_teeth_x) < 3:
        return MeshInterferenceResult(
            "Gs1-Gp1", profile_name, False, tolerance=tol,
            detail="Fail (invalid gear geometry)",
        )

    sun0 = (np.pi / sun.teeth) if round(planet.teeth) % 2 == 0 else 0.0
    dc2 = dc / 2.0
    sx0, sy0 = _close_xy(sun.all_teeth_x, sun.all_teeth_y)
    px0, py0 = _close_xy(planet.all_teeth_x, planet.all_teeth_y)
    rs_max = float(np.hypot(sx0, sy0).max())
    rp_max = float(np.hypot(px0, py0).max())

    max_pen = 0.0
    worst_th_s = sun0
    worst_th_p = 0.0
    worst_deg = 0.0
    worst_hits = np.empty((0, 2))

    for k in range(n_steps):
        dth_s = (2.0 * np.pi / sun.teeth) * (k / n_steps)
        th_s = sun0 + dth_s
        th_p = -(sun.teeth / planet.teeth) * dth_s
        sx, sy = _rot2(sx0, sy0, th_s)
        px, py = _rot2(px0, py0, th_p)
        py = py + dc2

        step_hits_list: list[np.ndarray] = []
        step_pen = 0.0

        # Planet vertices inside Sun polygon
        mp = np.hypot(px, py) <= rs_max + 1e-6
        if np.any(mp):
            cand = np.column_stack([px[mp], py[mp]])
            ins = Path(np.column_stack([sx, sy])).contains_points(cand)
            if np.any(ins):
                pts = cand[ins]
                dists = _min_seg_dist(pts, sx, sy)
                pmax = float(dists.max())
                if pmax > step_pen:
                    step_pen = pmax
                sig = dists > tol
                if np.any(sig):
                    step_hits_list.append(pts[sig])

        # Sun vertices inside Planet polygon
        ms = np.hypot(sx, sy - dc2) <= rp_max + 1e-6
        if np.any(ms):
            cand = np.column_stack([sx[ms], sy[ms]])
            ins = Path(np.column_stack([px, py])).contains_points(cand)
            if np.any(ins):
                pts = cand[ins]
                dists = _min_seg_dist(pts, px, py)
                pmax = float(dists.max())
                if pmax > step_pen:
                    step_pen = pmax
                sig = dists > tol
                if np.any(sig):
                    step_hits_list.append(pts[sig])

        if step_pen > max_pen:
            max_pen = step_pen
            worst_th_s = th_s
            worst_th_p = th_p
            worst_deg = float(np.rad2deg(dth_s))
            worst_hits = (
                np.vstack(step_hits_list)
                if step_hits_list
                else np.empty((0, 2))
            )

    passed = max_pen <= tol
    if passed:
        detail = f"OK (max pen = {max_pen:.4f} [mm], tol = {tol:.4f} [mm])"
    else:
        detail = (
            f"Fail (max pen = {max_pen:.4f} [mm] > tol {tol:.4f} [mm] "
            f"@ dtheta_s = {worst_deg:.2f} [deg])"
        )
    return MeshInterferenceResult(
        mesh_name="Gs1-Gp1",
        profile_name=profile_name,
        passed=passed,
        max_penetration=max_pen,
        tolerance=tol,
        worst_angle_deg=worst_deg,
        worst_theta_a=worst_th_s,
        worst_theta_b=worst_th_p,
        hit_points=worst_hits,
        detail=detail,
    )


def _sweep_internal(
    planet,
    ring,
    dc: float,
    mesh_name: str,
    profile_name: str,
    n_steps: int,
) -> MeshInterferenceResult:
    """1-pitch bidirectional rolling sweep for an internal mesh ``Gp-Gr``."""
    tol = _mesh_tolerance(planet.module)
    if planet.teeth <= 0 or ring.teeth <= 0 or len(planet.all_teeth_x) < 3 or len(ring.all_teeth_x) < 3:
        return MeshInterferenceResult(
            mesh_name, profile_name, False, tolerance=tol,
            detail="Fail (invalid gear geometry)",
        )

    dc2 = dc / 2.0
    px0, py0 = _close_xy(planet.all_teeth_x, planet.all_teeth_y)
    rx0, ry0 = _close_xy(ring.all_teeth_x, ring.all_teeth_y)
    rp_max = float(np.hypot(px0, py0).max())
    rr_min = float(np.hypot(rx0, ry0).min())

    max_pen = 0.0
    worst_th_p = 0.0
    worst_th_r = 0.0
    worst_deg = 0.0
    worst_hits = np.empty((0, 2))

    for k in range(n_steps):
        th_p = (2.0 * np.pi / planet.teeth) * (k / n_steps)
        th_r = +(planet.teeth / ring.teeth) * th_p
        px, py = _rot2(px0, py0, th_p)
        py = py + dc2
        rx, ry = _rot2(rx0, ry0, th_r)

        step_hits_list: list[np.ndarray] = []
        step_pen = 0.0

        # Planet vertices protruding outside Ring inner boundary
        mp = np.hypot(px, py) >= rr_min - 1e-6
        if np.any(mp):
            cand = np.column_stack([px[mp], py[mp]])
            out = ~Path(np.column_stack([rx, ry])).contains_points(cand)
            if np.any(out):
                pts = cand[out]
                dists = _min_seg_dist(pts, rx, ry)
                pmax = float(dists.max())
                if pmax > step_pen:
                    step_pen = pmax
                sig = dists > tol
                if np.any(sig):
                    step_hits_list.append(pts[sig])

        # Ring inner tooth vertices protruding inside Planet polygon
        mr = np.hypot(rx, ry - dc2) <= rp_max + 1e-6
        if np.any(mr):
            cand = np.column_stack([rx[mr], ry[mr]])
            ins = Path(np.column_stack([px, py])).contains_points(cand)
            if np.any(ins):
                pts = cand[ins]
                dists = _min_seg_dist(pts, px, py)
                pmax = float(dists.max())
                if pmax > step_pen:
                    step_pen = pmax
                sig = dists > tol
                if np.any(sig):
                    step_hits_list.append(pts[sig])

        if step_pen > max_pen:
            max_pen = step_pen
            worst_th_p = th_p
            worst_th_r = th_r
            worst_deg = float(np.rad2deg(th_p))
            worst_hits = (
                np.vstack(step_hits_list)
                if step_hits_list
                else np.empty((0, 2))
            )

    passed = max_pen <= tol
    if passed:
        detail = f"OK (max pen = {max_pen:.4f} [mm], tol = {tol:.4f} [mm])"
    else:
        detail = (
            f"Fail (max pen = {max_pen:.4f} [mm] > tol {tol:.4f} [mm] "
            f"@ dtheta_p = {worst_deg:.2f} [deg])"
        )
    return MeshInterferenceResult(
        mesh_name=mesh_name,
        profile_name=profile_name,
        passed=passed,
        max_penetration=max_pen,
        tolerance=tol,
        worst_angle_deg=worst_deg,
        worst_theta_a=worst_th_p,
        worst_theta_b=worst_th_r,
        hit_points=worst_hits,
        detail=detail,
    )


def _check_planet_tip_clearance(
    planet,
    dc: float,
    num_planets: int,
    mesh_name: str,
    profile_name: str,
) -> MeshInterferenceResult:
    """Exact tip-to-tip clearance between adjacent planets on the carrier circle."""
    if num_planets < 2 or len(planet.all_teeth_x) < 3:
        return MeshInterferenceResult(
            mesh_name, profile_name, True, min_clearance=float("inf"),
            detail="OK (single planet)",
        )
    r_outer = float(np.hypot(planet.all_teeth_x, planet.all_teeth_y).max())
    center_dist = dc * float(np.sin(np.pi / num_planets))
    clearance = center_dist - 2.0 * r_outer
    passed = clearance > 0.0
    pen = max(0.0, -clearance)
    if passed:
        detail = f"OK (tip clearance = +{clearance:.4f} [mm])"
    else:
        detail = f"Fail (tip overlap = {pen:.4f} [mm])"
    return MeshInterferenceResult(
        mesh_name=mesh_name,
        profile_name=profile_name,
        passed=passed,
        max_penetration=pen,
        min_clearance=clearance,
        tolerance=0.0,
        detail=detail,
    )


# --------------------------------------------------------------- public API
def check_profile_interference(
    pgs,
    gear_set: dict,
    profile_name: str,
    *,
    n_steps: int = DEFAULT_SWEEP_STEPS,
) -> ProfileInterferenceReport:
    """Run analytical + 1-pitch kinematic tip-interference checks for ``gear_set``."""
    report = ProfileInterferenceReport(profile_name=profile_name)

    # Analytical pre-notes (bottom clearance & cycloid hypocycloid undercut)
    gs1 = gear_set["Gs1"]
    if gs1.addendum_factor >= gs1.dedendum_factor:
        report.analytical_notes.append(
            f"{profile_name} Bottom Clearance Note : A ({gs1.addendum_factor:g}) "
            f">= D ({gs1.dedendum_factor:g}) -> tip-to-root bottoming expected"
        )
    if hasattr(gs1, "_r_roll"):
        gear_keys = ["Gs1", "Gp1", "Gr1"] + (["Gp2", "Gr2"] if pgs.is_wolfrom else [])
        for key in gear_keys:
            g = gear_set[key]
            if g._rp < 2.0 * g._r_roll:
                report.analytical_notes.append(
                    f"{profile_name} Undercut Note ({key}) : "
                    f"rp ({g._rp:.3f} mm) < 2*r_roll ({2.0 * g._r_roll:.3f} mm)"
                )

    report.meshes.append(
        _sweep_external(gear_set["Gs1"], gear_set["Gp1"], pgs.dc, profile_name, n_steps)
    )
    report.meshes.append(
        _sweep_internal(
            gear_set["Gp1"], gear_set["Gr1"], pgs.dc, "Gp1-Gr1", profile_name, n_steps
        )
    )
    report.planets.append(
        _check_planet_tip_clearance(
            gear_set["Gp1"], pgs.dc, pgs.num_planets, "Planets Stage1", profile_name
        )
    )

    if pgs.is_wolfrom:
        report.meshes.append(
            _sweep_internal(
                gear_set["Gp2"], gear_set["Gr2"], pgs.dc, "Gp2-Gr2", profile_name, n_steps
            )
        )
        report.planets.append(
            _check_planet_tip_clearance(
                gear_set["Gp2"], pgs.dc, pgs.num_planets, "Planets Stage2", profile_name
            )
        )

    return report


def format_report_lines(reports: list[ProfileInterferenceReport]) -> list[str]:
    """Compose pure-ASCII Markdown lines for '## Check Geometrical Conditions'."""
    lines: list[str] = []
    for rep in reports:
        for note in rep.analytical_notes:
            lines.append(f"* {note}\n")
        for res in rep.all_results:
            lines.append(
                f"* Kinematic Tip Interference [{rep.profile_name}] ({res.mesh_name}) : "
                f"{res.detail}\n"
            )
    return lines


def print_interference_summary(reports: list[ProfileInterferenceReport]) -> None:
    """Print kinematic tip interference results to stdout."""
    for rep in reports:
        for note in rep.analytical_notes:
            print(f"# {note}")
        for res in rep.all_results:
            print(f"# Kinematic Tip Interference [{rep.profile_name}] ({res.mesh_name}) : ")
            print(res.detail)


# --------------------------------------------------------------- visualization
def _zoom_window(
    gear_a,
    gear_b,
    dc2: float,
    is_external: bool,
    hit_points: np.ndarray,
) -> tuple[float, float, float, float]:
    """Compute a zoomed (xmin, xmax, ymin, ymax) box around the contact / hit zone."""
    span = max(3.8 * gear_a.module, 2.5)
    if len(hit_points) > 0:
        cx, cy = float(hit_points[:, 0].mean()), float(hit_points[:, 1].mean())
        hx = float(np.max(np.abs(hit_points[:, 0] - cx)))
        hy = float(np.max(np.abs(hit_points[:, 1] - cy)))
        half = max(span, max(hx, hy) + 2.0 * gear_a.module)
        return cx - half, cx + half, cy - half, cy + half

    if is_external:
        rp_a = (
            gear_a.pitch_circle_radius
            if gear_a.pitch_circle_radius is not None
            else gear_a.module * (gear_a.teeth / 2.0 + gear_a.shift_factor)
        )
        cy = float(rp_a)
    else:
        rp_a = (
            gear_a.pitch_circle_radius
            if gear_a.pitch_circle_radius is not None
            else gear_a.module * (gear_a.teeth / 2.0 + gear_a.shift_factor)
        )
        cy = float(dc2 + rp_a)
    return -span, span, cy - span, cy + span


def plot_interference_report(
    pgs,
    gear_set: dict,
    report: ProfileInterferenceReport,
    *,
    out_path: str | None = None,
    fig_name: str | None = None,
    show: bool = True,
) -> None:
    """Render zoomed worst-phase mesh views with red markers on interfering points."""
    dc2 = pgs.dc / 2.0
    n_panels = len(report.meshes)
    if n_panels == 0:
        return

    name = fig_name or f"PGS Tip Interference ({report.profile_name})"
    fig, axes = plt.subplots(
        1, n_panels, num=name, figsize=(5.2 * n_panels, 5.2), clear=True
    )
    if n_panels == 1:
        axes = [axes]

    for ax, res in zip(axes, report.meshes):
        if res.mesh_name == "Gs1-Gp1":
            ga, gb = gear_set["Gs1"], gear_set["Gp1"]
            is_ext = True
            xa, ya = _rot2(*_close_xy(ga.all_teeth_x, ga.all_teeth_y), res.worst_theta_a)
            xb, yb = _rot2(*_close_xy(gb.all_teeth_x, gb.all_teeth_y), res.worst_theta_b)
            yb = yb + dc2
            label_a, label_b = "Gs1", "Gp1"
            col_a, col_b = "#2563eb", "#ea580c"
        elif res.mesh_name == "Gp1-Gr1":
            ga, gb = gear_set["Gp1"], gear_set["Gr1"]
            is_ext = False
            xa, ya = _rot2(*_close_xy(ga.all_teeth_x, ga.all_teeth_y), res.worst_theta_a)
            ya = ya + dc2
            xb, yb = _rot2(*_close_xy(gb.all_teeth_x, gb.all_teeth_y), res.worst_theta_b)
            label_a, label_b = "Gp1", "Gr1"
            col_a, col_b = "#ea580c", "#1f2937"
        else:  # Gp2-Gr2
            ga, gb = gear_set["Gp2"], gear_set["Gr2"]
            is_ext = False
            xa, ya = _rot2(*_close_xy(ga.all_teeth_x, ga.all_teeth_y), res.worst_theta_a)
            ya = ya + dc2
            xb, yb = _rot2(*_close_xy(gb.all_teeth_x, gb.all_teeth_y), res.worst_theta_b)
            label_a, label_b = "Gp2", "Gr2"
            col_a, col_b = "#0d9488", "#1f2937"

        ax.plot(xa, ya, color=col_a, linewidth=1.4, label=label_a)
        ax.plot(xb, yb, color=col_b, linewidth=1.4, label=label_b)
        ax.plot(ga.pitch_circle_x, ga.pitch_circle_y, color="gray", linestyle=":", linewidth=0.9)
        ax.plot(gb.pitch_circle_x, gb.pitch_circle_y, color="gray", linestyle="--", linewidth=0.9)

        if len(res.hit_points) > 0:
            ax.scatter(
                res.hit_points[:, 0], res.hit_points[:, 1],
                color="#dc2626", s=26, zorder=5, label="Interference",
            )

        xmin, xmax, ymin, ymax = _zoom_window(ga, gb, dc2, is_ext, res.hit_points)
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlim(xmin, xmax)
        ax.set_ylim(ymin, ymax)
        ax.grid(True, alpha=0.4)
        status = "OK" if res.passed else "FAIL"
        title_col = "#15803d" if res.passed else "#dc2626"
        ax.set_title(
            f"{res.mesh_name} [{status}]\n"
            f"pen={res.max_penetration:.4f} mm @ {res.worst_angle_deg:.1f} deg",
            color=title_col,
            fontsize=10,
            fontweight="bold",
        )
        ax.legend(loc="upper right", fontsize=8)

    fig.suptitle(
        f"Kinematic Tip Interference Check — {report.profile_name} Profile",
        fontsize=12,
        fontweight="bold",
    )
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.93))
    if out_path is not None:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        fig.savefig(out_path, dpi=120)
        plt.close(fig)
    elif show:
        plt.show()
