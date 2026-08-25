"""Gear Profile Generator (GPG).

Computes the point cloud of an involute gear tooth (external or internal)
and assembles all teeth, the pitch/outer/root circles and the final
positioned gear outline that the PGS design tool plots.

Input attributes follow common gear conventions:

    module             pitch-circle-tooth-count ratio (mm / tooth)
    teeth              number of teeth (negative selects internal gear)
    pressure_angle     pressure angle in degrees
    shift_factor       profile shift coefficient (X)
    backlash_factor    normalised backlash (B)
    addendum_factor    addendum coefficient (A)
    dedendum_factor    dedendum coefficient (D)
    hob_tip_radius_factor    tip-corner radius of the cutting hob (C)
    tooth_tip_radius_factor  tip-round radius of the tooth itself (E)
    x0, y0                   position offset of the gear centre
    rotate_angle             rotation of the full gear (degrees)
"""

from __future__ import annotations

import numpy as np

ROUND_PRECISION: int = 6


class GPG:
    """Involute gear profile generator."""

    def __init__(self) -> None:
        # --- Gear specification ---
        self.module: float = 1.0
        self.teeth: float = -18.0
        self.pressure_angle: float = 20.0
        self.shift_factor: float = 0.0
        self.backlash_factor: float = 0.05
        self.addendum_factor: float = 1.0
        self.dedendum_factor: float = 1.25
        self.hob_tip_radius_factor: float = 0.2
        self.tooth_tip_radius_factor: float = 0.1
        self.x0: float = 0.0
        self.y0: float = 0.0
        self.rotate_angle: float = 0.0
        # --- Segment counts for each domain ---
        self.seg_circle: int = 360
        self.seg_involute: int = 15
        self.seg_edge_round: int = 5
        self.seg_root_round: int = 5
        self.seg_outer: int = 5
        self.seg_root: int = 5
        # --- Calculated parameters (filled by _compute_params) ---
        self.alpha0: float = 0.0          # pressure angle in radians
        self.alpha_m: float = 0.0          # half tooth-pitch angle
        self.alpha_is: float = 0.0         # start angle of the involute curve
        self.theta_is: float = 0.0         # involute parameter range start
        self.theta_ie: float = 0.0         # involute parameter range end
        self.alpha_e: float = 0.0          # angle of the tooth's end point
        self.x_e: float = 0.0              # tooth end-point coordinates
        self.y_e: float = 0.0
        self.x_e0: float = 0.0             # edge-round centre coordinates
        self.y_e0: float = 0.0
        self.theta3_min: float = 0.0       # edge-round sweep range
        self.theta3_max: float = 0.0
        self.alpha_ts: float = 0.0         # start angle of the root round
        self.theta_te: float = 0.0         # end angle of the root round
        self.pitch_angle: float = 0.0      # per-tooth pitch angle (rad)
        self.align_angle: float = 0.0      # rotation that aligns tooth to x-axis
        # --- Linspaces ---
        self.theta1: np.ndarray = np.empty(0)   # invololute
        self.theta3: np.ndarray = np.empty(0)   # edge round
        self.theta_t: np.ndarray = np.empty(0)  # root round
        self.theta_s: np.ndarray = np.empty(0)  # root-round tangent direction
        self.theta6: np.ndarray = np.empty(0)   # outer arc
        self.theta7: np.ndarray = np.empty(0)   # root arc
        # --- Per-tooth curve segments (later concatenated into a tooth) ---
        self.involute_x: np.ndarray = np.empty(0)
        self.involute_y: np.ndarray = np.empty(0)
        self.edge_round_x: np.ndarray = np.empty(0)
        self.edge_round_y: np.ndarray = np.empty(0)
        self.root_round_x: np.ndarray = np.empty(0)
        self.root_round_y: np.ndarray = np.empty(0)
        self.outer_arc_x: np.ndarray = np.empty(0)
        self.outer_arc_y: np.ndarray = np.empty(0)
        self.root_arc_x: np.ndarray = np.empty(0)
        self.root_arc_y: np.ndarray = np.empty(0)
        # --- Combined single-tooth geometry ---
        self.half_tooth_x: np.ndarray = np.empty(0)
        self.half_tooth_y: np.ndarray = np.empty(0)
        self.mirror_x: np.ndarray = np.empty(0)
        self.mirror_y: np.ndarray = np.empty(0)
        self.tooth_x: np.ndarray = np.empty(0)
        self.tooth_y: np.ndarray = np.empty(0)
        self.aligned_x: np.ndarray = np.empty(0)
        self.aligned_y: np.ndarray = np.empty(0)
        # --- Full-gear geometry ---
        self.all_teeth_x: np.ndarray = np.empty(0)
        self.all_teeth_y: np.ndarray = np.empty(0)
        self.single_tooth_x: np.ndarray = np.empty(0)
        self.single_tooth_y: np.ndarray = np.empty(0)
        self.rotated_teeth_x: np.ndarray = np.empty(0)
        self.rotated_teeth_y: np.ndarray = np.empty(0)
        self.plot_x: np.ndarray = np.empty(0)   # final positioned outline
        self.plot_y: np.ndarray = np.empty(0)
        # --- Reference circles ---
        self.pitch_circle_radius: float | None = None  # drawn pitch radius override
        self.pitch_circle_x: np.ndarray = np.empty(0)
        self.pitch_circle_y: np.ndarray = np.empty(0)
        self.outer_circle_x: np.ndarray = np.empty(0)
        self.outer_circle_y: np.ndarray = np.empty(0)
        self.root_circle_x: np.ndarray = np.empty(0)
        self.root_circle_y: np.ndarray = np.empty(0)

    # ----------------------------------------------------------- step helpers
    def _apply_internal_convention(self) -> None:
        """Normalise an internal (ring) gear to external-equivalent form.

        Negates teeth/shift/backlash and swaps addendum/dedendum and the
        two tip-radius coefficients so the same tooth-generation math can
        be reused for ring gears.
        """
        if self.teeth >= 0:
            return
        self.teeth = -self.teeth
        self.shift_factor = -self.shift_factor
        self.backlash_factor = -self.backlash_factor
        self.addendum_factor, self.dedendum_factor = (
            self.dedendum_factor, self.addendum_factor)
        self.hob_tip_radius_factor, self.tooth_tip_radius_factor = (
            self.tooth_tip_radius_factor, self.hob_tip_radius_factor)

    def _compute_params(self) -> None:
        a0 = self.alpha0 = self.pressure_angle * (2 * np.pi / 360)
        z = self.teeth
        self.alpha_m = np.pi / z
        self.alpha_is = (
            a0 + np.pi / (2 * z)
            + self.backlash_factor / (z * np.cos(a0))
            - (1 + 2 * self.shift_factor / z) * np.sin(a0) / np.cos(a0)
        )
        self.theta_is = (
            np.sin(a0) / np.cos(a0)
            + 2 * (self.hob_tip_radius_factor * (1 - np.sin(a0))
                   + self.shift_factor - self.dedendum_factor)
            / (z * np.cos(a0) * np.sin(a0))
        )
        self.theta_ie = (
            2 * self.tooth_tip_radius_factor / (z * np.cos(a0))
            + np.sqrt(((z + 2 * (self.shift_factor + self.addendum_factor
                                  - self.tooth_tip_radius_factor)) / (z * np.cos(a0))) ** 2 - 1)
        )
        self.alpha_e = (
            self.alpha_is + self.theta_ie
            - np.arctan(np.sqrt(((z + 2 * (self.shift_factor + self.addendum_factor
                                            - self.tooth_tip_radius_factor)) / (z * np.cos(a0))) ** 2 - 1))
        )
        self.x_e = self.module * (z / 2 + self.shift_factor + self.addendum_factor) * np.cos(self.alpha_e)
        self.y_e = self.module * (z / 2 + self.shift_factor + self.addendum_factor) * np.sin(self.alpha_e)
        self.x_e0 = self.module * (z / 2 + self.shift_factor + self.addendum_factor
                                   - self.tooth_tip_radius_factor) * np.cos(self.alpha_e)
        self.y_e0 = self.module * (z / 2 + self.shift_factor + self.addendum_factor
                                   - self.tooth_tip_radius_factor) * np.sin(self.alpha_e)
        self.alpha_ts = (
            (2 * (self.hob_tip_radius_factor * (1 - np.sin(a0)) - self.dedendum_factor) * np.sin(a0)
             + self.backlash_factor) / (z * np.cos(a0))
            - 2 * self.hob_tip_radius_factor * np.cos(a0) / z
            + np.pi / (2 * z)
        )
        self.theta_te = (
            2 * self.hob_tip_radius_factor * np.cos(a0) / z
            - 2 * (self.dedendum_factor - self.shift_factor
                   - self.hob_tip_radius_factor * (1 - np.sin(a0))) * np.cos(a0)
            / (z * np.sin(a0))
        )
        # Trim the tooth-tip radius when it would otherwise overrun the
        # involute/outer-arc intersection point.
        if (self.alpha_e > self.alpha_m
                and self.alpha_m > self.alpha_is + self.theta_ie - np.arctan(self.theta_ie)):
            self.tooth_tip_radius_factor = (
                (self.tooth_tip_radius_factor / 2) * np.cos(a0)
                * (self.theta_ie - np.sqrt((1 / np.cos(self.alpha_is + self.theta_ie - self.alpha_m)) ** 2 - 1))
            )
        self.pitch_angle = 2 * np.pi / z
        self.align_angle = np.pi / 2 - np.pi / z

    def _involute_curve(self) -> None:
        self.theta1 = np.linspace(self.theta_is, self.theta_ie, self.seg_involute)
        r = 0.5 * self.module * self.teeth * np.cos(self.alpha0)
        angle = self.alpha_is + self.theta1 - np.arctan(self.theta1)
        self.involute_x = r * np.sqrt(1 + self.theta1 ** 2) * np.cos(angle)
        self.involute_y = r * np.sqrt(1 + self.theta1 ** 2) * np.sin(angle)

    def _edge_round_curve(self) -> None:
        self.theta3_min = np.arctan((self.involute_y[-1] - self.y_e0)
                                    / (self.involute_x[-1] - self.x_e0))
        self.theta3_max = np.arctan((self.y_e - self.y_e0) / (self.x_e - self.x_e0))
        self.theta3 = np.linspace(self.theta3_min, self.theta3_max, self.seg_edge_round)
        self.edge_round_x = self.module * self.tooth_tip_radius_factor * np.cos(self.theta3) + self.x_e0
        self.edge_round_y = self.module * self.tooth_tip_radius_factor * np.sin(self.theta3) + self.y_e0

    def _root_round_curve(self) -> None:
        """Generate the root-round transition between the involute and root arcs."""
        self.theta_t = np.linspace(0, self.theta_te, self.seg_root_round)
        root_offset = (self.dedendum_factor - self.shift_factor
                       - self.hob_tip_radius_factor)
        if self.hob_tip_radius_factor != 0 and root_offset == 0:
            self.theta_s = (np.pi / 2) * np.ones(len(self.theta_t))
        elif root_offset != 0:
            denom = (self.module * self.dedendum_factor
                     - self.module * self.shift_factor
                     - self.module * self.hob_tip_radius_factor)
            self.theta_s = np.arctan(
                (self.module * self.teeth * self.theta_t / 2) / denom)
        ang = self.theta_t + self.alpha_ts
        ang_full = self.theta_s + self.theta_t + self.alpha_ts
        self.root_round_x = self.module * (
            (self.teeth / 2 + self.shift_factor - self.dedendum_factor
             + self.hob_tip_radius_factor) * np.cos(ang)
            + (self.teeth / 2) * self.theta_t * np.sin(ang)
            - self.hob_tip_radius_factor * np.cos(ang_full))
        self.root_round_y = self.module * (
            (self.teeth / 2 + self.shift_factor - self.dedendum_factor
             + self.hob_tip_radius_factor) * np.sin(ang)
            - (self.teeth / 2) * self.theta_t * np.cos(ang)
            - self.hob_tip_radius_factor * np.sin(ang_full))

    def _outer_arc(self) -> None:
        self.theta6 = np.linspace(self.alpha_e, self.alpha_m, self.seg_outer)
        self.outer_arc_x = self.module * (self.teeth / 2 + self.addendum_factor
                                          + self.shift_factor) * np.cos(self.theta6)
        self.outer_arc_y = self.module * (self.teeth / 2 + self.addendum_factor
                                          + self.shift_factor) * np.sin(self.theta6)

    def _root_arc(self) -> None:
        self.theta7 = np.linspace(0, self.alpha_ts, self.seg_root)
        self.root_arc_x = self.module * (self.teeth / 2 - self.dedendum_factor
                                         + self.shift_factor) * np.cos(self.theta7)
        self.root_arc_y = self.module * (self.teeth / 2 - self.dedendum_factor
                                         + self.shift_factor) * np.sin(self.theta7)

    def _reverse(self) -> None:
        """Reverse every per-tooth segment so they concatenate cleanly."""
        pairs = (
            (self.involute_x, self.involute_y, "involute_x", "involute_y"),
            (self.edge_round_x, self.edge_round_y, "edge_round_x", "edge_round_y"),
            (self.root_round_x, self.root_round_y, "root_round_x", "root_round_y"),
            (self.outer_arc_x, self.outer_arc_y, "outer_arc_x", "outer_arc_y"),
            (self.root_arc_x, self.root_arc_y, "root_arc_x", "root_arc_y"),
        )
        for x, y, xname, yname in pairs:
            setattr(self, xname, np.flip(x))
            setattr(self, yname, np.flip(y))

    def _combine_half_tooth(self) -> None:
        self.half_tooth_x = np.concatenate((
            self.outer_arc_x, self.edge_round_x, self.involute_x,
            self.root_round_x, self.root_arc_x))
        self.half_tooth_y = np.concatenate((
            self.outer_arc_y, self.edge_round_y, self.involute_y,
            self.root_round_y, self.root_arc_y))

    def _mirror_tooth(self) -> None:
        self.mirror_x = np.flip(self.half_tooth_x)
        self.mirror_y = -np.flip(self.half_tooth_y)

    def _combine_tooth(self) -> None:
        self.tooth_x = np.concatenate((self.half_tooth_x, self.mirror_x))
        self.tooth_y = np.concatenate((self.half_tooth_y, self.mirror_y))

    def _align_tooth(self) -> None:
        self.aligned_x = (np.cos(self.align_angle) * self.tooth_x
                          - np.sin(self.align_angle) * self.tooth_y)
        self.aligned_y = (np.sin(self.align_angle) * self.tooth_x
                          + np.cos(self.align_angle) * self.tooth_y)

    # ----------------------------------------------------------- full gear
    def _build_one_tooth(self) -> None:
        self._apply_internal_convention()
        self._compute_params()
        self._involute_curve()
        self._edge_round_curve()
        self._root_round_curve()
        self._outer_arc()
        self._root_arc()
        self._reverse()
        self._combine_half_tooth()
        self._mirror_tooth()
        self._combine_tooth()
        self._align_tooth()

    def _build_all_teeth(self) -> None:
        xs = np.empty(0)
        ys = np.empty(0)
        n = int(round(self.teeth, ROUND_PRECISION))
        for i in range(n):
            angle = -self.pitch_angle * i
            ca, sa = np.cos(angle), np.sin(angle)
            xs = np.concatenate((xs, ca * self.aligned_x - sa * self.aligned_y))
            ys = np.concatenate((ys, sa * self.aligned_x + ca * self.aligned_y))
        self.all_teeth_x = xs
        self.all_teeth_y = ys

    def _move_one_tooth(self) -> None:
        self.single_tooth_x = self.aligned_x + self.x0
        self.single_tooth_y = self.aligned_y + self.y0

    def _rotate_all_teeth(self) -> None:
        angle = np.deg2rad(self.rotate_angle)
        ca, sa = np.cos(angle), np.sin(angle)
        self.rotated_teeth_x = ca * self.all_teeth_x - sa * self.all_teeth_y
        self.rotated_teeth_y = sa * self.all_teeth_x + ca * self.all_teeth_y

    def _move_all_teeth(self) -> None:
        self.plot_x = self.rotated_teeth_x + self.x0
        self.plot_y = self.rotated_teeth_y + self.y0

    def _pitch_circle(self) -> None:
        theta = np.linspace(0, 2 * np.pi, self.seg_circle)
        radius = (self.pitch_circle_radius
                  if self.pitch_circle_radius is not None
                  else self.module * (self.teeth / 2 + self.shift_factor))
        self.pitch_circle_x = radius * np.cos(theta) + self.x0
        self.pitch_circle_y = radius * np.sin(theta) + self.y0

    def _outer_circle(self) -> None:
        theta = np.linspace(0, 2 * np.pi, self.seg_circle)
        radius = self.module * (self.teeth + self.shift_factor) / 2 + self.module * self.addendum_factor
        self.outer_circle_x = radius * np.cos(theta) + self.x0
        self.outer_circle_y = radius * np.sin(theta) + self.y0

    def _root_circle(self) -> None:
        theta = np.linspace(0, 2 * np.pi, self.seg_circle)
        radius = self.module * (self.teeth + self.shift_factor) / 2 - self.module * self.dedendum_factor
        self.root_circle_x = radius * np.cos(theta) + self.x0
        self.root_circle_y = radius * np.sin(theta) + self.y0

    def calc(self) -> None:
        """Generate the complete gear outline and reference circles."""
        self._build_one_tooth()
        self._build_all_teeth()
        self._move_one_tooth()
        self._rotate_all_teeth()
        self._move_all_teeth()
        self._pitch_circle()
        self._outer_circle()
        self._root_circle()