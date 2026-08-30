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

    # --------------------------------------------------------------- output
    def output(self) -> None:
        """Print ratios and gear sizes to stdout."""
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