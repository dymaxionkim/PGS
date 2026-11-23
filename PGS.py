"""Planetary Gear Set (PGS) sizing.

Computes gear ratios, gear sizes and geometric feasibility checks for
simple and Wolfrom planetary gear sets.

Gear type codes
---------------
0   Simple planetary gear set
1   Wolfrom (3K) planetary gear set; both ring tooth counts (Zr1, Zr2)
    are independent inputs supplied directly via the UI, and the stage-2
    mesh mismatch is absorbed by the ring2 profile shift
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

STANDARD_PRESSURE_ANGLE: float = 20.0
MIN_RIM_FOR_TRIMMING: float = 16.0
ROUND_PRECISION: int = 6
DEFAULT_FRICTION_COEFF: float = 0.08
DEFAULT_BEARING_COEFF: float = 0.002
DEFAULT_SEAL_LOSS: float = 0.01
DEFAULT_CHURNING_COEFF: float = 0.005
CHURNING_REF_SPEED_RPM: float = 1000.0
BACKDRIVE_MARGINAL_THRESHOLD: float = 0.20


@dataclass
class MeshLossInfo:
    """Single-mesh sliding friction loss summary (carrier-fixed frame)."""

    contact_ratio: float = 0.0
    loss_factor_hv: float = 1.0
    geom_factor_k: float = 0.0
    efficiency: float = 1.0
    used_fallback: bool = False


@dataclass
class LossBreakdown:
    """Bearing, seal and speed-dependent churning loss breakdown."""

    pin_dia: float = 0.0
    bearing_mesh1: float = 0.0
    bearing_mesh2: float = 0.0
    bearing_mesh3: float = 0.0
    bearing_shaft_eff: float = 1.0
    seal_loss: float = 0.0
    churning_loss: float = 0.0
    sun_pitch_vel: float = 0.0


@dataclass
class EfficiencyResult:
    """Expected efficiency and backdrivability summary for one lockup config."""

    forward_eff: float | None = None
    reverse_eff: float | None = None
    forward_load_eff: float | None = None
    reverse_load_eff: float | None = None
    parasitic_loss: float = 0.0
    stages_forward: list[float] | None = None
    stages_reverse: list[float] | None = None
    backdrive_tier: str = ""
    backdrive_detail: str = ""
    backdrivable: bool = False
    mu_lock: float | None = None
    singular: bool = False

    @property
    def conclusion(self) -> str:
        """Two-tier backdrivability conclusion ('Possible' / 'Not Possible')."""
        return "Possible" if self.backdrivable else "Not Possible"


def ring_shift_factor(
    zp: float,
    xp: float,
    zr: float,
    module: float,
    dc: float,
    alpha_deg: float,
) -> float:
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
    return float((zr - zp) * (inv_a0 - inv_aw) / (2.0 * np.tan(a0)) - xp)


def _hv_piecewise(s_start: float, s_end: float) -> float:
    """Exact tooth loss factor ``Hv`` over contact path ``[s_start, s_end]``.

    Positions are normalised by the base pitch ``p_b`` with the pitch point
    at ``s = 0`` (so ``s_start = -eps_1``, ``s_end = +eps_2`` and transverse
    contact ratio ``eps_a = s_end - s_start``).  Uses piecewise equal load
    sharing ``w(s) = 1 / N(s)`` across the ``N(s)`` simultaneously engaged
    tooth pairs:

        Hv = 2 * integral_{s_start}^{s_end} (|s| / N(s)) ds

    For standard pitch-straddling contact (``0 <= eps_1, eps_2 <= 1`` and
    ``1 <= eps_a <= 2``), this reduces identically to Ohlendorf's formula
    ``1 - eps_a + eps_1**2 + eps_2**2``.  Unlike the closed-form formula, it
    remains exact for profile-shifted all-recess / all-approach meshes and
    for high contact ratios (``eps_a > 2``).
    """
    eps_a = s_end - s_start
    if eps_a <= 0.0:
        return 1.0

    # Discontinuous theoretical contact (eps_a < 1): average |s| over the
    # active contact arc rather than artificially scaling down toward zero.
    if eps_a < 1.0:
        if s_start < 0.0 < s_end:
            return (s_start * s_start + s_end * s_end) / eps_a
        return abs(s_end * s_end - s_start * s_start) / eps_a

    n = int(np.floor(eps_a))
    frac = eps_a - n

    # Breakpoints where the number of simultaneous tooth pairs N(s) changes,
    # plus s = 0 if the contact path crosses the pitch point.
    pts: list[float] = [s_start, s_end]
    for k in range(n + 1):
        p1 = s_start + k
        if s_start < p1 < s_end:
            pts.append(p1)
        if frac > 1e-12:
            p2 = s_start + k + frac
            if s_start < p2 < s_end:
                pts.append(p2)
    if s_start < 0.0 < s_end:
        pts.append(0.0)
    pts.sort()

    hv = 0.0
    for a, b in zip(pts[:-1], pts[1:]):
        if b - a <= 1e-12:
            continue
        mid_u = 0.5 * (a + b) - s_start
        rem = mid_u - np.floor(mid_u)
        n_pairs = (n + 1) if (frac > 1e-12 and rem < frac) else n
        hv += abs(b * b - a * a) / n_pairs
    return float(hv)


def _calc_mesh_loss_ext(
    z1: float,
    x1: float,
    z2: float,
    x2: float,
    module: float,
    dc: float,
    addendum: float,
    alpha_deg: float,
    mu: float,
) -> MeshLossInfo:
    """External gear mesh sliding loss (Sun1-Planet1)."""
    if z1 <= 0.0 or z2 <= 0.0 or module <= 0.0 or dc <= 0.0:
        return MeshLossInfo(used_fallback=True)
    base_geom = np.pi * (1.0 / z1 + 1.0 / z2)
    a0 = np.deg2rad(alpha_deg)
    cos_a0 = np.cos(a0)
    if cos_a0 <= 0.0:
        k = float(base_geom)
        return MeshLossInfo(0.0, 1.0, k, max(0.0, 1.0 - mu * k), True)

    aw_cd = dc / 2.0
    rb1 = 0.5 * module * z1 * cos_a0
    rb2 = 0.5 * module * z2 * cos_a0
    cos_aw = (rb1 + rb2) / aw_cd
    ra1 = module * (0.5 * z1 + x1 + addendum)
    ra2 = module * (0.5 * z2 + x2 + addendum)
    pb = np.pi * module * cos_a0

    if not (0.0 < cos_aw < 1.0) or ra1 <= rb1 or ra2 <= rb2 or pb <= 0.0:
        k = float(base_geom)
        return MeshLossInfo(0.0, 1.0, k, max(0.0, 1.0 - mu * k), True)

    aw = np.arccos(cos_aw)
    tan_aw = np.tan(aw)
    eps1 = (np.sqrt(ra2 * ra2 - rb2 * rb2) - rb2 * tan_aw) / pb
    eps2 = (np.sqrt(ra1 * ra1 - rb1 * rb1) - rb1 * tan_aw) / pb
    eps_a = float(eps1 + eps2)
    if eps_a <= 0.0:
        k = float(base_geom)
        return MeshLossInfo(0.0, 1.0, k, max(0.0, 1.0 - mu * k), True)

    hv = _hv_piecewise(-float(eps1), float(eps2))
    k = float(base_geom * hv)
    eta = max(0.0, 1.0 - mu * k)
    return MeshLossInfo(eps_a, hv, k, eta, False)


def _calc_mesh_loss_int(
    zp: float,
    xp: float,
    zr_pos: float,
    xr_pre: float,
    module: float,
    dc: float,
    addendum: float,
    alpha_deg: float,
    mu: float,
) -> MeshLossInfo:
    """Internal gear mesh sliding loss (Planet-Ring, ``zr_pos > zp > 0``)."""
    if zp <= 0.0 or zr_pos <= zp or module <= 0.0 or dc <= 0.0:
        return MeshLossInfo(used_fallback=True)
    base_geom = np.pi * (1.0 / zp - 1.0 / zr_pos)
    a0 = np.deg2rad(alpha_deg)
    cos_a0 = np.cos(a0)
    if cos_a0 <= 0.0:
        k = float(base_geom)
        return MeshLossInfo(0.0, 1.0, k, max(0.0, 1.0 - mu * k), True)

    aw_cd = dc / 2.0
    rbp = 0.5 * module * zp * cos_a0
    rbr = 0.5 * module * zr_pos * cos_a0
    cos_aw = (rbr - rbp) / aw_cd
    rap = module * (0.5 * zp + xp + addendum)
    # Internal ring gear tip circle (innermost tooth tip radius):
    # GPG negates xr_pre internally, so post-convention shift is -xr_pre.
    rar = module * (0.5 * zr_pos - xr_pre - addendum)
    pb = np.pi * module * cos_a0

    if not (0.0 < cos_aw < 1.0) or rap <= rbp or rar <= rbr or pb <= 0.0:
        k = float(base_geom)
        return MeshLossInfo(0.0, 1.0, k, max(0.0, 1.0 - mu * k), True)

    aw = np.arccos(cos_aw)
    tan_aw = np.tan(aw)
    eps_p = (np.sqrt(rap * rap - rbp * rbp) - rbp * tan_aw) / pb
    eps_r = (rbr * tan_aw - np.sqrt(rar * rar - rbr * rbr)) / pb
    eps_a = float(eps_p + eps_r)
    if eps_a <= 0.0:
        k = float(base_geom)
        return MeshLossInfo(0.0, 1.0, k, max(0.0, 1.0 - mu * k), True)

    hv = _hv_piecewise(-float(eps_r), float(eps_p))
    k = float(base_geom * hv)
    eta = max(0.0, 1.0 - mu * k)
    return MeshLossInfo(eps_a, hv, k, eta, False)


@dataclass
class CheckResult:
    """Results of every geometric feasibility check (status strings)."""

    non_factorizing_1: str = ""
    equal_distance_1: str = ""
    planets_interference_1: str = ""
    involute_interference_1: str = ""
    trimming_interference_1: str = ""
    teeth_number_integer_1: str = ""


class PGS:
    """Planetary Gear Set sizing calculator.

    Set the input attributes, then call :meth:`calc`, optionally followed
    by :meth:`output` (stdout report) and :meth:`checks_run` (geometric
    feasibility checks).
    """

    def __init__(self) -> None:
        # --- Inputs ---
        self.gear_type: int = 1
        self.pressure_angle: float = 20.0
        self.module1: float = 0.5
        self.module2: float = 0.5
        self.num_planets: int = 4
        self.zp2: float = 18.0
        self.zs1: float = 16.0
        self.shift_s1: float = 0.0
        self.shift_p1: float = 0.0
        self.shift_p2: float = 0.0
        self.addendum_factor: float = 1.0
        self.friction_coeff: float = DEFAULT_FRICTION_COEFF
        self.bearing_coeff: float = DEFAULT_BEARING_COEFF
        self.seal_loss: float = DEFAULT_SEAL_LOSS
        self.churning_coeff: float = DEFAULT_CHURNING_COEFF
        self.ns1: float = 1000.0
        # --- Stage-1 teeth & diameters ---
        self.zr1: float = 0.0
        self.zp1: float = 0.0
        self.ds1: float = 0.0
        self.dp1: float = 0.0
        self.dr1: float = 0.0
        self.dc: float = 0.0
        self.gp1s: float = 0.0
        # --- Stage-2 (Wolfrom) teeth, diameters & ratios ---
        self.zr2: float = 0.0
        self.zs2: float = 0.0
        self.dp2: float = 0.0
        self.ds2: float = 0.0
        self.dr2: float = 0.0
        self.gr2p2: float = 0.0
        self.g1: float = 0.0
        self.g2: float = 0.0
        self.g22: float = 0.0
        self.l1: float = 0.0
        self.l2: float = 0.0
        # --- Wolfrom operating speeds [rpm] (Ring1 fixed, Type-3K) ---
        self.n_carrier: float = 0.0
        self.n_ring1: float = 0.0
        self.n_planet: float = 0.0
        self.n_output: float = 0.0
        # --- Operating speeds of the other two lockup configurations ---
        # Ring2 fixed, carrier output (ratio g1):
        self.n_g1_carrier: float = 0.0
        self.n_g1_ring1: float = 0.0
        self.n_g1_planet: float = 0.0
        # Carrier fixed, ring2 output (ratio g2):
        self.n_g2_planet: float = 0.0
        self.n_g2_ring1: float = 0.0
        self.n_g2_ring2: float = 0.0
        # --- Simple-only ratios ---
        self.g3: float = 0.0
        self.g4: float = 0.0
        # --- Simple operating speeds [rpm] ---
        # "Carrier Fixed, Ring1 Output" (star train; carrier stationary):
        self.n_cf_sun: float = 0.0
        self.n_cf_carrier: float = 0.0
        self.n_cf_ring: float = 0.0
        self.n_cf_planet: float = 0.0
        # "Ring1 Fixed, Carrier Output" (classic reduction):
        self.n_rf_sun: float = 0.0
        self.n_rf_carrier: float = 0.0
        self.n_rf_ring: float = 0.0
        self.n_rf_planet: float = 0.0
        # --- Efficiency & backdrivability ---
        self.mesh_losses: dict[str, MeshLossInfo] = {}
        self.loss_breakdown: LossBreakdown = LossBreakdown()
        self.eff: dict[str, EfficiencyResult] = {}
        # --- Check results ---
        self.checks: CheckResult = CheckResult()

    @property
    def is_wolfrom(self) -> bool:
        """Whether this design is a Wolfrom (two-stage) gear set."""
        return self.gear_type != 0

    # ------------------------------------------------------------------ calc
    def calc(self) -> None:
        """Compute derived teeth counts, diameters and ratios."""
        # Both ring tooth counts (Zr1 and, for a Wolfrom, Zr2) are entered
        # directly in the UI (stored negative for the internal rings) and
        # kept as whole numbers.  The stage-1 equal-distance condition fixes
        # the planet1 count:  |zr1| = zs1 + 2*zp1.
        self.zr1 = -float(np.floor(abs(self.zr1) + 0.5))
        if self.is_wolfrom:
            self.zr2 = -float(np.floor(abs(self.zr2) + 0.5))
        self.zp1 = (-self.zr1 - self.zs1) / 2

        self.ds1 = self.zs1 * self.module1
        self.dp1 = self.zp1 * self.module1
        self.dr1 = -self.zr1 * self.module1
        # Carrier diameter: operating centre distance of the shifted
        # sun-planet mesh (linear model - consistent with the offset
        # circle radii m*(z/2 + X) drawn by the generators):
        #   dc/2 = m1*(zs1 + zp1)/2 + m1*(xs1 + xp1)
        self.dc = (self.ds1 + self.dp1
                   + 2.0 * self.module1 * (self.shift_s1 + self.shift_p1))
        self.gp1s = self.dp1 / self.ds1

        if self.is_wolfrom:
            self._calc_stage2()
        else:
            self.g3 = round(1 - self.zr1 / self.zs1, ROUND_PRECISION)
            self.g4 = -round(-self.zr1 / self.zs1, ROUND_PRECISION)
            self._calc_simple_speeds()

        self._calc_efficiency()

    def _calc_simple_speeds(self) -> None:
        """Stage-1 operating speeds [rpm] for the two Simple lockups."""
        # Carrier fixed, Ring1 output (star train): the carrier is clamped at
        # 0.  The external sun-planet mesh gives
        #   n_p = -(zs/zp)*ns1,  then the internal planet-ring mesh gives
        #   n_r = n_c + (zp/|zr|)*(n_p - n_c).
        self.n_cf_sun = self.ns1
        self.n_cf_carrier = 0.0
        self.n_cf_planet = -self.ns1 / self.gp1s
        self.n_cf_ring = round(
            (self.zp1 / -self.zr1) * self.n_cf_planet,
            ROUND_PRECISION)

        # Ring1 fixed, carrier output (classic reduction):
        #   n_c = ns1/g3,  n_p = n_c*(1 - |zr|/zp),  n_r = 0.
        self.n_rf_sun = self.ns1
        self.n_rf_carrier = self.ns1 / self.g3
        self.n_rf_ring = 0.0
        self.n_rf_planet = (
            self.n_rf_carrier * (1.0 - (-self.zr1) / self.zp1))

    def _calc_stage2(self) -> None:
        # Stage-2 planets sit on the shared carrier radius; both ring
        # counts are independent inputs and Ring2's profile shift absorbs
        # the mesh mismatch (see finalize_parameters).
        self.dp2 = self.zp2 * self.module2
        self.ds2 = self.dc - self.dp2
        self.zs2 = self.ds2 / self.module2
        self.dr2 = -self.zr2 * self.module2
        self.gr2p2 = self.dr2 / self.dp2

        self.g1 = round(1 + self.gr2p2 * self.gp1s, ROUND_PRECISION)
        self.g2 = -round(self.gr2p2 * self.gp1s, ROUND_PRECISION)
        self.l1 = self.dr1 / self.ds1
        self.l2 = (self.dr1 * self.dp2) / (self.dr2 * self.dp1)
        self.g22 = round((1 + self.l1) / (1 - self.l2), ROUND_PRECISION)
        if self.l2 > 1:
            self.g22 = -self.g22

        # Operating speeds [rpm] for the Type-3K assembly (Ring1 fixed,
        # Sun1 input, Ring2 output, carrier free):
        #   Ring1 fixed:  n_s1 = (1 + l1) * n_c            ->  n_c
        #   Stage-1 mesh: n_p - n_c = (zr1/zp1) * (n_r1 - n_c)  ->  n_p (Gp1, Gp2)
        #   Stage-2 mesh: n_r2 = (1 - l2) * n_c            ->  n_r2
        #   Ring1 back-solved from the same chain:         ->  n_r1 (= 0 by design)
        self.n_carrier = self.ns1 / (1.0 + self.l1)
        # Note: self.zr1 is stored negative (internal teeth); using its
        # magnitude keeps the fixed-frame directions physical:
        #   n_p - n_c = -(|zr1|/zp1) * n_c  (planet walks on the fixed ring)
        self.n_planet = self.n_carrier * (1.0 - (-self.zr1) / self.zp1)
        self.n_output = self.n_carrier * (1.0 - self.l2)
        self.n_ring1 = round(
            self.n_carrier
            + (self.zp1 / -self.zr1) * (self.n_planet - self.n_carrier),
            ROUND_PRECISION)

        # Config B -- Ring2 fixed, carrier output (ns1/g1 = nc):
        #   Stage-2 internal mesh:  n_p - n_c = -(zr2/zp2) * n_c
        #   Stage-1 external mesh:  n_s1 - n_c = -gp1s * (n_p - n_c)
        #   -> n_s1 = (1 + gp1s*gr2p2) * n_c, i.e. nc = ns1 / g1
        #   Stage-1 internal mesh back-solves ring1.
        self.n_g1_carrier = self.ns1 / self.g1
        self.n_g1_planet = self.n_g1_carrier * (1.0 - self.gr2p2)
        self.n_g1_ring1 = round(
            self.n_g1_carrier
            + (self.zp1 / -self.zr1) * (self.n_g1_planet - self.n_g1_carrier),
            ROUND_PRECISION)

        # Config C -- Carrier fixed, ring2 output:
        #   Stage-1 external mesh:  n_p = -(zs1/zp1) * ns1
        #   Stage-1 internal mesh:  n_r1 = (zp1/zr1) * n_p
        #   Stage-2 internal mesh:  n_r2 = (zp2/zr2) * n_p (= ns1 / g2)
        self.n_g2_planet = -self.ns1 / self.gp1s
        self.n_g2_ring1 = round((self.zp1 / -self.zr1) * self.n_g2_planet,
                                ROUND_PRECISION)
        self.n_g2_ring2 = round(self.n_g2_planet / self.gr2p2,
                                ROUND_PRECISION)

    # ----------------------------------------------------------- efficiency
    @staticmethod
    def _build_eff_result(
        eta_f: float | None,
        eta_r: float | None,
        *,
        eta_f_load: float | None = None,
        eta_r_load: float | None = None,
        parasitic: float = 0.0,
        stages_forward: list[float] | None = None,
        stages_reverse: list[float] | None = None,
        mu_lock: float | None = None,
        singular: bool = False,
    ) -> EfficiencyResult:
        """Build an EfficiencyResult with 3-tier detail and 2-tier conclusion."""
        if singular or eta_f is None or eta_r is None:
            return EfficiencyResult(
                forward_eff=None,
                reverse_eff=None,
                forward_load_eff=None,
                reverse_load_eff=None,
                parasitic_loss=parasitic,
                backdrive_tier="Self-Locking",
                backdrive_detail=(
                    "Self-Locking (Singular ratio l2 = 1: kinematic speed ratio "
                    "is infinite; non-backdrivable)"
                ),
                backdrivable=False,
                mu_lock=mu_lock,
                singular=True,
            )

        if mu_lock is not None:
            if mu_lock <= 0.0:
                lock_note = (
                    "self-locks even at mu = 0.0000 "
                    "(due to bearing/seal/churning losses)"
                )
            else:
                lock_note = f"self-locks at mu >= {mu_lock:.4f}"
        else:
            lock_note = "no kinematic self-locking"

        if eta_r <= 0.0:
            return EfficiencyResult(
                forward_eff=max(0.0, eta_f),
                reverse_eff=eta_r,
                forward_load_eff=eta_f_load,
                reverse_load_eff=eta_r_load,
                parasitic_loss=parasitic,
                stages_forward=stages_forward,
                stages_reverse=stages_reverse,
                backdrive_tier="Self-Locking",
                backdrive_detail=(
                    "Self-Locking (eta_R <= 0%: non-backdrivable due to "
                    f"combined losses; {lock_note})"
                ),
                backdrivable=False,
                mu_lock=mu_lock,
            )
        if eta_r < BACKDRIVE_MARGINAL_THRESHOLD:
            return EfficiencyResult(
                forward_eff=max(0.0, eta_f),
                reverse_eff=eta_r,
                forward_load_eff=eta_f_load,
                reverse_load_eff=eta_r_load,
                parasitic_loss=parasitic,
                stages_forward=stages_forward,
                stages_reverse=stages_reverse,
                backdrive_tier="Marginal",
                backdrive_detail=(
                    "Marginal (0% < eta_R < 20%: theoretically backdrivable, "
                    "but sensitive to static friction & drag variation; "
                    f"{lock_note})"
                ),
                backdrivable=True,
                mu_lock=mu_lock,
            )
        return EfficiencyResult(
            forward_eff=max(0.0, eta_f),
            reverse_eff=eta_r,
            forward_load_eff=eta_f_load,
            reverse_load_eff=eta_r_load,
            parasitic_loss=parasitic,
            stages_forward=stages_forward,
            stages_reverse=stages_reverse,
            backdrive_tier="Good",
            backdrive_detail=(
                "Good (eta_R >= 20%: smoothly backdrivable; "
                f"{lock_note})"
            ),
            backdrivable=True,
            mu_lock=mu_lock,
        )

    @staticmethod
    def _wolfrom_3k_reverse_total(
        mu: float,
        l1: float,
        l2: float,
        k1: float,
        k2: float,
        k3: float,
        psi_b1: float,
        psi_b2: float,
        psi_b3: float,
        eta_b_shaft: float,
        parasitic: float,
    ) -> float:
        """Evaluate total Type-3K reverse efficiency as a function of ``mu``."""
        e1 = max(0.0, 1.0 - mu * k1 - psi_b1)
        e2 = max(0.0, 1.0 - mu * k2 - psi_b2)
        e3 = max(0.0, 1.0 - mu * k3 - psi_b3)
        if e1 <= 0.0 or e2 <= 0.0 or e3 <= 0.0 or eta_b_shaft <= 0.0:
            return -1.0
        if l2 < 1.0:
            eta_r_core = (e1 * (1.0 + l1) / (e3 * (e1 * e2 + l1))) * (
                (e2 * e3 - l2) / (1.0 - l2)
            )
        else:
            eta_r_core = (e1 * (1.0 + l1) / (e1 + e2 * l1)) * (
                (e2 * e3 * l2 - 1.0) / (l2 - 1.0)
            )
        return eta_b_shaft * eta_r_core - parasitic

    def _solve_mu_lock_wolfrom(
        self,
        l1: float,
        l2: float,
        k1: float,
        k2: float,
        k3: float,
        psi_b1: float,
        psi_b2: float,
        psi_b3: float,
        eta_b_shaft: float,
        parasitic: float,
    ) -> float | None:
        """Solve for the critical mesh friction coefficient ``mu_lock`` where
        total Type-3K reverse efficiency reaches zero (including bearing, seal,
        and speed-dependent churning losses).
        """
        if abs(1.0 - l2) < 1e-12 or l2 <= 0.0:
            return None
        if k1 <= 0.0 and k2 <= 0.0 and k3 <= 0.0:
            return None

        def f(mu_val: float) -> float:
            return self._wolfrom_3k_reverse_total(
                mu_val, l1, l2, k1, k2, k3,
                psi_b1, psi_b2, psi_b3, eta_b_shaft, parasitic,
            )

        if f(0.0) <= 0.0:
            return 0.0

        # Upper bracket where at least one mesh efficiency drops to zero.
        caps = [
            (1.0 - pb) / k
            for k, pb in ((k1, psi_b1), (k2, psi_b2), (k3, psi_b3))
            if k > 0.0 and pb < 1.0
        ]
        if not caps:
            return 0.0
        hi = min(caps)
        if f(hi) > 0.0:
            return None
        lo = 0.0
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            if f(mid) > 0.0:
                lo = mid
            else:
                hi = mid
        return float(0.5 * (lo + hi))

    def _calc_loss_breakdown(self) -> LossBreakdown:
        """Compute bearing, seal and speed-dependent churning loss terms.

        - Bearing loss (load-dependent):
          * Planet pin bearings resist planet rotation inside the carrier
            frame with loss fraction ``psi_b = (mu_b / cos(alpha0)) * (d_pin / dp)``
            per mesh, where ``d_pin`` follows the carrier-pin sizing rule
            ``dp_min - 10*m_min`` clamped to ``[0.25, 0.70] * dp_min``.
          * Input and output shaft support bearings contribute an external
            efficiency factor ``eta_b_shaft = max(0, 1 - 0.5*mu_b/cos(alpha0))**2``.
        - Seal loss (load-independent parasitic): ``zeta_s = max(0, seal_loss)``.
        - Churning loss (load-independent, speed-dependent parasitic):
          ``zeta_c = max(0, churning_coeff) * (|ns1| / 1000 rpm)**2``.
        """
        mu_b = max(0.0, float(self.bearing_coeff))
        seal = max(0.0, float(self.seal_loss))
        kc = max(0.0, float(self.churning_coeff))
        a0 = np.deg2rad(self.pressure_angle)
        cos_a0 = float(np.cos(a0)) if np.cos(a0) > 1e-6 else 1.0

        if self.is_wolfrom and self.dp1 > 0.0 and self.dp2 > 0.0:
            if self.dp1 <= self.dp2:
                dp_min, m_min = self.dp1, self.module1
            else:
                dp_min, m_min = self.dp2, self.module2
        else:
            dp_min, m_min = max(0.0, self.dp1), self.module1

        if dp_min > 0.0:
            pin_dia = float(
                np.clip(dp_min - 10.0 * m_min, 0.25 * dp_min, 0.70 * dp_min)
            )
        else:
            pin_dia = 0.0

        psi_b1 = (mu_b / cos_a0) * (pin_dia / self.dp1) if self.dp1 > 0.0 else 0.0
        psi_b2 = psi_b1
        psi_b3 = (
            (mu_b / cos_a0) * (pin_dia / self.dp2)
            if (self.is_wolfrom and self.dp2 > 0.0)
            else 0.0
        )
        psi_shaft = 0.5 * (mu_b / cos_a0)
        eta_b_shaft = max(0.0, 1.0 - psi_shaft) ** 2

        speed_ratio = abs(float(self.ns1)) / CHURNING_REF_SPEED_RPM
        churning = kc * (speed_ratio ** 2)
        sun_pitch_vel = float(
            np.pi * abs(self.ds1) * abs(float(self.ns1)) / 60000.0
        )

        return LossBreakdown(
            pin_dia=pin_dia,
            bearing_mesh1=psi_b1,
            bearing_mesh2=psi_b2,
            bearing_mesh3=psi_b3,
            bearing_shaft_eff=eta_b_shaft,
            seal_loss=seal,
            churning_loss=churning,
            sun_pitch_vel=sun_pitch_vel,
        )

    def _calc_efficiency(self) -> None:
        """Compute expected meshing, bearing, seal & churning efficiency."""
        mu = max(0.0, float(self.friction_coeff))
        zr1_pos = -self.zr1
        xr1 = (
            ring_shift_factor(
                self.zp1, self.shift_p1, zr1_pos,
                self.module1, self.dc, self.pressure_angle,
            )
            if self.dc > 0.0 and zr1_pos > self.zp1 > 0.0
            else 0.0
        )
        m1_ext = _calc_mesh_loss_ext(
            self.zs1, self.shift_s1, self.zp1, self.shift_p1,
            self.module1, self.dc, self.addendum_factor,
            self.pressure_angle, mu,
        )
        m2_int = _calc_mesh_loss_int(
            self.zp1, self.shift_p1, zr1_pos, xr1,
            self.module1, self.dc, self.addendum_factor,
            self.pressure_angle, mu,
        )
        self.loss_breakdown = self._calc_loss_breakdown()

        if self.is_wolfrom:
            zr2_pos = -self.zr2
            xr2 = (
                ring_shift_factor(
                    self.zp2, self.shift_p2, zr2_pos,
                    self.module2, self.dc, self.pressure_angle,
                )
                if self.dc > 0.0 and zr2_pos > self.zp2 > 0.0
                else 0.0
            )
            m3_int = _calc_mesh_loss_int(
                self.zp2, self.shift_p2, zr2_pos, xr2,
                self.module2, self.dc, self.addendum_factor,
                self.pressure_angle, mu,
            )
            self.mesh_losses = {
                "Gs1-Gp1": m1_ext,
                "Gp1-Gr1": m2_int,
                "Gp2-Gr2": m3_int,
            }
            self._calc_efficiency_wolfrom(m1_ext, m2_int, m3_int)
        else:
            self.mesh_losses = {
                "Gs1-Gp1": m1_ext,
                "Gp1-Gr1": m2_int,
            }
            self._calc_efficiency_simple(m1_ext, m2_int)

    def _calc_efficiency_wolfrom(
        self,
        m1: MeshLossInfo,
        m2: MeshLossInfo,
        m3: MeshLossInfo,
    ) -> None:
        lb = self.loss_breakdown
        e1 = max(0.0, m1.efficiency - lb.bearing_mesh1)
        e2 = max(0.0, m2.efficiency - lb.bearing_mesh2)
        e3 = max(0.0, m3.efficiency - lb.bearing_mesh3)
        eta_shaft = lb.bearing_shaft_eff
        parasitic = lb.seal_loss + lb.churning_loss
        l1, l2 = self.l1, self.l2

        # Config A: Type-3K (Carrier Free, Ring1 Fixed, Ring2 Output)
        if abs(1.0 - l2) < 1e-12 or l2 <= 0.0:
            eff_3k = self._build_eff_result(
                None, None, parasitic=parasitic, singular=True
            )
        else:
            if l2 < 1.0:
                eta_f_core = ((1.0 + e1 * e2 * l1) / (1.0 + l1)) * (
                    (1.0 - l2) / (1.0 - e2 * e3 * l2)
                )
                if e1 <= 0.0 or e2 <= 0.0 or e3 <= 0.0:
                    eta_r_core = -1.0
                else:
                    eta_r_core = (e1 * (1.0 + l1) / (e3 * (e1 * e2 + l1))) * (
                        (e2 * e3 - l2) / (1.0 - l2)
                    )
            else:
                eta_f_core = (e3 * (e2 + e1 * l1) / (1.0 + l1)) * (
                    (l2 - 1.0) / (l2 - e2 * e3)
                )
                if e1 <= 0.0 or e2 <= 0.0 or e3 <= 0.0:
                    eta_r_core = -1.0
                else:
                    eta_r_core = (e1 * (1.0 + l1) / (e1 + e2 * l1)) * (
                        (e2 * e3 * l2 - 1.0) / (l2 - 1.0)
                    )
            eta_f_load = eta_shaft * eta_f_core
            eta_r_load = eta_shaft * eta_r_core if eta_r_core > 0.0 else eta_r_core
            eta_f_tot = max(0.0, eta_f_load - parasitic)
            eta_r_tot = eta_r_load - parasitic
            mu_lock = self._solve_mu_lock_wolfrom(
                l1, l2,
                m1.geom_factor_k, m2.geom_factor_k, m3.geom_factor_k,
                lb.bearing_mesh1, lb.bearing_mesh2, lb.bearing_mesh3,
                eta_shaft, parasitic,
            )
            eff_3k = self._build_eff_result(
                eta_f_tot, eta_r_tot,
                eta_f_load=eta_f_load,
                eta_r_load=eta_r_load,
                parasitic=parasitic,
                mu_lock=mu_lock,
            )

        # Config B: Ring2 Fixed, Carrier Output (Ring1 idling; Mesh 1 + Mesh 3)
        e13 = e1 * e3
        p_b = self.gr2p2 * self.gp1s
        eta_f_b_load = eta_shaft * ((1.0 + e13 * p_b) / (1.0 + p_b))
        eta_r_b_load = (
            eta_shaft * ((e13 * (1.0 + p_b)) / (e13 + p_b))
            if (e13 + p_b) > 0.0
            else 0.0
        )
        eff_b = self._build_eff_result(
            max(0.0, eta_f_b_load - parasitic),
            eta_r_b_load - parasitic,
            eta_f_load=eta_f_b_load,
            eta_r_load=eta_r_b_load,
            parasitic=parasitic,
        )

        # Config C: Carrier Fixed, Ring2 Output (simple 2-mesh train)
        eta_c_load = eta_shaft * e13
        eff_c = self._build_eff_result(
            max(0.0, eta_c_load - parasitic),
            eta_c_load - parasitic,
            eta_f_load=eta_c_load,
            eta_r_load=eta_c_load,
            parasitic=parasitic,
        )

        self.eff = {
            "type_3k": eff_3k,
            "ring2_fixed": eff_b,
            "carrier_fixed": eff_c,
        }

    def _simple_stage_efficiencies(
        self,
        eta_f_stage: float,
        eta_r_stage: float,
        stage_ratio: float,
    ) -> tuple[list[float], list[float]]:
        """Compute 1-, 2- and 3-stage Simple total efficiencies.

        Load-dependent (mesh + bearing) efficiencies multiply per stage,
        housing seal loss applies once, and each downstream stage's churning
        loss scales down with ``1 / stage_ratio**(2*j)``.
        """
        lb = self.loss_breakdown
        r = max(1.0, abs(stage_ratio))
        fwd: list[float] = []
        rev: list[float] = []
        churn_acc = 0.0
        for stage in range(1, 4):
            churn_acc += lb.churning_loss / (r ** (2 * (stage - 1)))
            parasitic_k = lb.seal_loss + churn_acc
            ef_k = max(0.0, (eta_f_stage ** stage) - parasitic_k)
            er_k = (eta_r_stage ** stage) - parasitic_k
            fwd.append(ef_k)
            rev.append(er_k)
        return fwd, rev

    def _calc_efficiency_simple(
        self,
        m1: MeshLossInfo,
        m2: MeshLossInfo,
    ) -> None:
        lb = self.loss_breakdown
        e1 = max(0.0, m1.efficiency - lb.bearing_mesh1)
        e2 = max(0.0, m2.efficiency - lb.bearing_mesh2)
        e0 = e1 * e2
        eta_shaft = lb.bearing_shaft_eff
        parasitic = lb.seal_loss + lb.churning_loss
        p = (-self.zr1) / self.zs1 if self.zs1 > 0.0 else 0.0

        # Config 1: Carrier Fixed, Ring1 Output (star train)
        eta_cf_load = eta_shaft * e0
        cf_fwd, cf_rev = self._simple_stage_efficiencies(
            eta_cf_load, eta_cf_load, self.g4
        )
        eff_cf = self._build_eff_result(
            cf_fwd[0], cf_rev[0],
            eta_f_load=eta_cf_load,
            eta_r_load=eta_cf_load,
            parasitic=parasitic,
            stages_forward=cf_fwd,
            stages_reverse=cf_rev,
        )

        # Config 2: Ring1 Fixed, Carrier Output (classic 2K-H reduction)
        eta_f_rf_load = (
            eta_shaft * ((1.0 + p * e0) / (1.0 + p))
            if (1.0 + p) > 0.0
            else 0.0
        )
        eta_r_rf_load = (
            eta_shaft * ((e0 * (1.0 + p)) / (e0 + p))
            if (e0 + p) > 0.0
            else 0.0
        )
        rf_fwd, rf_rev = self._simple_stage_efficiencies(
            eta_f_rf_load, eta_r_rf_load, self.g3
        )
        eff_rf = self._build_eff_result(
            rf_fwd[0], rf_rev[0],
            eta_f_load=eta_f_rf_load,
            eta_r_load=eta_r_rf_load,
            parasitic=parasitic,
            stages_forward=rf_fwd,
            stages_reverse=rf_rev,
        )

        self.eff = {
            "carrier_fixed": eff_cf,
            "ring1_fixed": eff_rf,
        }

    @staticmethod
    def _fmt_pct(value: float | None, *, clamp_zero: bool = False) -> str:
        if value is None:
            return "N/A"
        if clamp_zero and value <= 0.0:
            return "0.00 [%] (Self-Locking)"
        return f"{value * 100.0:.2f} [%]"

    def _mesh_summary_text(self) -> str:
        names = list(self.mesh_losses.keys())
        effs = " / ".join(
            f"{self.mesh_losses[n].efficiency * 100.0:.2f}%" for n in names
        )
        crs = " / ".join(
            f"{self.mesh_losses[n].contact_ratio:.2f}"
            if not self.mesh_losses[n].used_fallback
            else "N/A*"
            for n in names
        )
        suffix = (
            " (*fallback Hv=1.0 used for degenerate mesh)"
            if any(self.mesh_losses[n].used_fallback for n in names)
            else ""
        )
        return (
            f"Mesh Efficiency ({' / '.join(names)}) = {effs} "
            f"(Contact Ratio = {crs}){suffix}"
        )

    def _bearing_summary_text(self) -> str:
        lb = self.loss_breakdown
        shaft_loss = (1.0 - lb.bearing_shaft_eff) * 100.0
        if self.is_wolfrom:
            return (
                f"Bearing Loss (d_pin = {lb.pin_dia:.2f} [mm]; "
                f"Pin M1 / M2 / M3 / Shafts) = "
                f"{lb.bearing_mesh1 * 100.0:.2f}% / "
                f"{lb.bearing_mesh2 * 100.0:.2f}% / "
                f"{lb.bearing_mesh3 * 100.0:.2f}% / "
                f"{shaft_loss:.2f}%"
            )
        return (
            f"Bearing Loss (d_pin = {lb.pin_dia:.2f} [mm]; "
            f"Pin M1 / M2 / Shafts) = "
            f"{lb.bearing_mesh1 * 100.0:.2f}% / "
            f"{lb.bearing_mesh2 * 100.0:.2f}% / "
            f"{shaft_loss:.2f}%"
        )

    def efficiency_markdown_lines(self) -> list[str]:
        """Compose Markdown lines for the '### Efficiency & Backdrivability' block."""
        lb = self.loss_breakdown
        lines: list[str] = [
            "### Efficiency & Backdrivability (Involute Mesh + Bearing + Seal + Churning)\n",
            (
                f"* Loss Inputs : mu = {self.friction_coeff:g}, "
                f"mu_b = {self.bearing_coeff:g}, "
                f"zeta_s = {self.seal_loss:g}, "
                f"kc = {self.churning_coeff:g} (@{CHURNING_REF_SPEED_RPM:g} rpm), "
                f"ns1 = {self.ns1:g} [rpm]\n"
            ),
            f"* {self._mesh_summary_text()}\n",
            f"* {self._bearing_summary_text()}\n",
            (
                f"* Parasitic Losses : Seal = {lb.seal_loss * 100.0:.2f} [%], "
                f"Churning = {lb.churning_loss * 100.0:.2f} [%] "
                f"(at ns1 = {self.ns1:g} [rpm], vt_s1 = {lb.sun_pitch_vel:.2f} [m/s])\n"
            ),
        ]
        if self.is_wolfrom:
            configs = [
                ("Type-3K : Carrier Free, Ring2 Output", self.eff["type_3k"]),
                ("Ring2 Fixed, Carrier Output", self.eff["ring2_fixed"]),
                ("Carrier Fixed, Ring2 Output", self.eff["carrier_fixed"]),
            ]
            for label, res in configs:
                lines.append(f"* {label} :\n")
                if res.forward_load_eff is not None:
                    lines.append(
                        f"  * Forward Efficiency = {self._fmt_pct(res.forward_eff)} "
                        f"(Mesh+Bearing = {res.forward_load_eff * 100.0:.2f} [%], "
                        f"Parasitic = {res.parasitic_loss * 100.0:.2f} [%])\n"
                    )
                else:
                    lines.append(
                        f"  * Forward Efficiency = {self._fmt_pct(res.forward_eff)}\n"
                    )
                if res.reverse_load_eff is not None and res.reverse_eff is not None and res.reverse_eff > 0.0:
                    lines.append(
                        f"  * Reverse Efficiency = "
                        f"{self._fmt_pct(res.reverse_eff, clamp_zero=True)} "
                        f"(Mesh+Bearing = {res.reverse_load_eff * 100.0:.2f} [%], "
                        f"Parasitic = {res.parasitic_loss * 100.0:.2f} [%])\n"
                    )
                else:
                    lines.append(
                        f"  * Reverse Efficiency = "
                        f"{self._fmt_pct(res.reverse_eff, clamp_zero=True)}\n"
                    )
                lines.append(
                    f"  * Backdrivability Assessment (3-Tier) = {res.backdrive_detail}\n"
                )
                lines.append(
                    f"  * Backdrivable (Conclusion) = {res.conclusion}\n"
                )
        else:
            configs = [
                ("Carrier Fixed, Ring1 Output", self.eff["carrier_fixed"]),
                ("Ring1 Fixed, Carrier Output", self.eff["ring1_fixed"]),
            ]
            for label, res in configs:
                lines.append(f"* {label} :\n")
                if res.stages_forward is not None and res.stages_reverse is not None:
                    sf = res.stages_forward
                    sr = res.stages_reverse
                    lines.append(
                        f"  * Forward Efficiency = "
                        f"{sf[0] * 100.0:.2f} [%] (1-stage), "
                        f"{sf[1] * 100.0:.2f} [%] (2-stages), "
                        f"{sf[2] * 100.0:.2f} [%] (3-stages)\n"
                    )
                    if sr[0] <= 0.0:
                        lines.append(
                            "  * Reverse Efficiency = 0.00 [%] (Self-Locking)\n"
                        )
                    else:
                        lines.append(
                            f"  * Reverse Efficiency = "
                            f"{max(0.0, sr[0]) * 100.0:.2f} [%] (1-stage), "
                            f"{max(0.0, sr[1]) * 100.0:.2f} [%] (2-stages), "
                            f"{max(0.0, sr[2]) * 100.0:.2f} [%] (3-stages)\n"
                        )
                else:
                    lines.append("  * Forward Efficiency = N/A\n")
                    lines.append("  * Reverse Efficiency = N/A\n")
                lines.append(
                    f"  * Backdrivability Assessment (3-Tier) = {res.backdrive_detail}\n"
                )
                lines.append(
                    f"  * Backdrivable (Conclusion) = {res.conclusion}\n"
                )
        lines.append("\n")
        return lines

    def _print_efficiency(self) -> None:
        """Print the efficiency & backdrivability block to stdout."""
        for line in self.efficiency_markdown_lines():
            text = line.rstrip("\n")
            if text.startswith("  * "):
                print("  " + text[4:])
            elif text.startswith("* "):
                print(text[2:])
            elif text:
                print(text)

    # --------------------------------------------------------------- output
    def output(self) -> None:
        """Print ratios, speeds, efficiency/backdrivability and gear sizes to stdout."""
        if self.is_wolfrom:
            self._output_wolfrom()
        else:
            self._output_simple()

    def _output_wolfrom(self) -> None:
        print("\n##### Wolfrom Planetary Gear Set")
        print("### Ratio")
        print("Ratio (Sun-Planet1) = ", self.gp1s, "")
        print("Ratio (Planet2-Ring2) = ", self.gr2p2, "")
        print("Ratio Total (Ring2 Fiexed, Carrier Output) = ", self.g1, "")
        print("Ratio Total (Carrier Fixed, Ring2 Output) = ", self.g2, "")
        print("Ratio Total (Type-3K : Carrier Free, Ring2 Output) = ", self.g22, "")
        print("(Sign + / - : co-rotating / counter-rotating relative to Gs1) ")
        self._print_speed(
            "(Type-3K : Carrier Free, Ring2 Output)",
            [("Input Gear Speed (Gs1)", self.ns1),
             ("Carrier Speed", self.n_carrier),
             ("1st Ring Gear Speed (Gr1)", self.n_ring1),
             ("Planet Gear Speed (Gp1,Gp2)", self.n_planet),
             ("2nd Ring Gear Speed (Gr2)", self.n_output)])
        self._print_speed(
            "(Ring2 Fiexed, Carrier Output)",
            [("Input Gear Speed (Gs1)", self.ns1),
             ("Carrier Speed", self.n_g1_carrier),
             ("1st Ring Gear Speed (Gr1)", self.n_g1_ring1),
             ("Planet Gear Speed (Gp1,Gp2)", self.n_g1_planet),
             ("2nd Ring Gear Speed (Gr2)", 0.0)])
        self._print_speed(
            "(Carrier Fixed, Ring2 Output)",
            [("Input Gear Speed (Gs1)", self.ns1),
             ("Carrier Speed", 0.0),
             ("1st Ring Gear Speed (Gr1)", self.n_g2_ring1),
             ("Planet Gear Speed (Gp1,Gp2)", self.n_g2_planet),
             ("2nd Ring Gear Speed (Gr2)", self.n_g2_ring2)])
        self._print_efficiency()
        print("### Size")
        print("Sun = ", self.ds1, " [mm],  ", self.zs1, " [ea]")
        print("Planet1 = ", self.dp1, " [mm],  ", self.zp1, " [ea]")
        print("Ring1 = ", self.dr1, " [mm],  ", self.zr1, " [ea]")
        print("Planet2 = ", self.dp2, " [mm],  ", self.zp2, " [ea]")
        print("Ring2 = ", self.dr2, " [mm],  ", self.zr2, " [ea]")

    def _print_speed(self, config: str, rows: list[tuple[str, float]]) -> None:
        """Print one '### Speed (...)' block for the given lockup config."""
        print("### Speed", config, "")
        for label, value in rows:
            print(label, " = ", self._signed(value), " [rpm]")

    def _output_simple(self) -> None:
        print("\n##### Simple Planetary Gear Set")
        print("### Ratio")
        print("Ratio (Sun-Planet1) = ", self.gp1s, "")
        print("Ratio (Total, Carrier Output) = ", self.g3, " (1-stage),  ",
              self.g3 ** 2, " (2-stages),  ", self.g3 ** 3, " (3-stages)")
        print("Ratio (Total, Ring1 Output) = ", self.g4, " (1-stage),  ",
              self.g4 ** 2, " (2-stages),  ", self.g4 ** 3, " (3-stages)")
        self._print_speed(
            "(Carrier Fixed, Ring1 Output)",
            [("Input Gear Speed (Gs1)", self.n_cf_sun),
             ("Carrier Speed", self.n_cf_carrier),
             ("Ring Gear Speed (Gr1)", self.n_cf_ring),
             ("Planet Gear Speed (Gp1)", self.n_cf_planet)])
        self._print_speed(
            "(Ring1 Fixed, Carrier Output)",
            [("Input Gear Speed (Gs1)", self.n_rf_sun),
             ("Carrier Speed", self.n_rf_carrier),
             ("Ring Gear Speed (Gr1)", self.n_rf_ring),
             ("Planet Gear Speed (Gp1)", self.n_rf_planet)])
        self._print_efficiency()
        print("### Size")
        print("Sun = ", self.ds1, " [mm],  ", self.zs1, " [ea]")
        print("Planet1 = ", self.dp1, " [mm],  ", self.zp1, " [ea]")
        print("Ring1 = ", self.dr1, " [mm],  ", self.zr1, " [ea]")

    # --------------------------------------------------------------- checks
    def checks_run(self) -> None:
        """Run all geometric feasibility checks and print the results."""
        print("\n\n### Checks")
        self._check_non_factorizing()
        self._check_equal_distance()
        self._check_planets_interference()
        self._check_involute_interference()
        self._check_trimming_interference()
        self._check_teeth_integer()

    @staticmethod
    def _label(condition: bool, ok: str, fail: str) -> str:
        return ok if condition else fail

    @staticmethod
    def _emit(heading: str, result: str) -> None:
        print(f"# {heading} : ")
        print(result)

    @staticmethod
    def _signed(value: float) -> str:
        """Format a speed value with an explicit +/- direction sign."""
        return f"{float(value):+.6g}"

    def _check_non_factorizing(self) -> None:
        cond = (self.zs1 % self.num_planets != 0
                and (-self.zr1) % self.num_planets != 0)
        self.checks.non_factorizing_1 = self._label(cond, "Good for noise", "No good for noise")
        self._emit("Sequential Mesh Condition (Non-Factorizing, Not Required) 1",
                   self.checks.non_factorizing_1)

    def _check_equal_distance(self) -> None:
        cond = (self.zs1 - self.zr1) % self.num_planets == 0
        self.checks.equal_distance_1 = self._label(cond, "OK", "Fail")
        self._emit("Planet Numbers (Equal Distance Condition) 1",
                   self.checks.equal_distance_1)

    def _check_planets_interference(self) -> None:
        cond = (self.pressure_angle == STANDARD_PRESSURE_ANGLE
                and self.num_planets < np.pi / np.arcsin((self.zp1 + 2) / (self.zp1 + self.zs1)))
        self.checks.planets_interference_1 = self._label(cond, "OK", "Fail")
        self._emit("Planets Interference (Non-Overlap Condition) 1",
                   self.checks.planets_interference_1)
        if self.pressure_angle != STANDARD_PRESSURE_ANGLE:
            print("No Check (Non-Standard) ")

    def _involute_thresh(self, zp: float) -> float:
        sin_a = np.sin(np.deg2rad(self.pressure_angle))
        temp = (zp * sin_a) ** 2
        return (temp - 4) / (2 * temp - 4)

    def _check_involute_interference(self) -> None:
        cond = (self.pressure_angle == STANDARD_PRESSURE_ANGLE
                and (-self.zr1) >= self._involute_thresh(self.zp1))
        self.checks.involute_interference_1 = self._label(cond, "OK", "Fail")
        self._emit("Involute Interference Condition 1", self.checks.involute_interference_1)
        if self.pressure_angle != STANDARD_PRESSURE_ANGLE:
            print("No Check (Non-Standard) ")

    def _check_trimming_interference(self) -> None:
        cond = (self.pressure_angle == STANDARD_PRESSURE_ANGLE
                and (-self.zr1 - self.zp1) >= MIN_RIM_FOR_TRIMMING)
        self.checks.trimming_interference_1 = self._label(cond, "OK", "Fail")
        self._emit("Trimming Interference 1", self.checks.trimming_interference_1)
        if self.pressure_angle != STANDARD_PRESSURE_ANGLE:
            print("No Check (Non-Standard) ")
            self.checks.trimming_interference_1 = "No Check (Non-Standard)"

    def _check_teeth_integer(self) -> None:
        def is_int(v: float) -> bool:
            return round(float(v), ROUND_PRECISION).is_integer()

        cond = is_int(self.zs1) and is_int(self.zp1) and is_int(self.zr1)
        self.checks.teeth_number_integer_1 = self._label(cond, "OK", "Fail")
        self._emit("Teeth Numbers which is Integer 1", self.checks.teeth_number_integer_1)