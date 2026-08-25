"""Planetary Gear Set (PGS) sizing.

Computes gear ratios, gear sizes and geometric feasibility checks for
simple and Wolfrom planetary gear sets.

Gear type codes
---------------
0   Simple planetary gear set
1   Wolfrom (teeth difference = 1)
2   Wolfrom (teeth difference = 0.5)
3   Wolfrom (teeth difference = 2)
4   Wolfrom (teeth difference = 3)
5   Wolfrom (teeth difference = 4)
6   Wolfrom (teeth difference = 5)
7   Wolfrom (teeth difference = 6)
8   Wolfrom (teeth difference = 7)
9   Wolfrom (teeth difference = 8)
10  Wolfrom (teeth difference = 9)
11  Wolfrom (teeth difference = 10)
12  Wolfrom (teeth difference = 11)
13  Wolfrom (teeth difference = 12)
14  Wolfrom (teeth difference = 13)
15  Wolfrom (teeth difference = 14)
16  Wolfrom (teeth difference = 15)
17  Wolfrom (teeth difference = 16)
18  Wolfrom (teeth difference = 17)
19  Wolfrom (teeth difference = 18)
20  Wolfrom (teeth difference = 19)
21  Wolfrom (teeth difference = 20)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

STANDARD_PRESSURE_ANGLE: float = 20.0
MIN_RIM_FOR_TRIMMING: float = 16.0
ROUND_PRECISION: int = 6

# Teeth-difference lookup keyed by gear type code.
_TYPE_DIFFERENCE: dict[int, float] = {
    0: 1.0,
    1: 1.0,
    2: 0.5,
    3: 2.0,
    4: 3.0,
    5: 4.0,
    6: 5.0,
    7: 6.0,
    8: 7.0,
    9: 8.0,
    10: 9.0,
    11: 10.0,
    12: 11.0,
    13: 12.0,
    14: 13.0,
    15: 14.0,
    16: 15.0,
    17: 16.0,
    18: 17.0,
    19: 18.0,
    20: 19.0,
    21: 20.0,
}


@dataclass
class CheckResult:
    """Results of every geometric feasibility check (status strings)."""

    non_factorizing_1: str = ""
    non_factorizing_2: str = ""
    equal_distance_1: str = ""
    equal_distance_2: str = ""
    planets_interference_1: str = ""
    planets_interference_2: str = ""
    involute_interference_1: str = ""
    involute_interference_2: str = ""
    trimming_interference_1: str = ""
    trimming_interference_2: str = ""
    teeth_number_integer_1: str = ""
    teeth_number_integer_2: str = ""


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
        # --- Derived constants ---
        self.type_diff: float = 1.0
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
        # --- Simple-only ratios ---
        self.g3: float = 0.0
        self.g4: float = 0.0
        # --- Check results ---
        self.checks: CheckResult = CheckResult()

    @property
    def is_wolfrom(self) -> bool:
        """Whether this design is a Wolfrom (two-stage) gear set."""
        return self.gear_type != 0

    # ------------------------------------------------------------------ calc
    def calc(self) -> None:
        """Compute derived teeth counts, diameters and ratios."""
        self.type_diff = _TYPE_DIFFERENCE.get(self.gear_type, 1.0)

        # Ring tooth counts are decided in the zero-shift state: solve the
        # layout with standard pitch circles (no shift factors) and round
        # the ring teeth to integers, so both ring gears always have whole
        # tooth numbers:
        #   |zr1| = |zr2| + diff*Np
        #   |zr2| = zp2 + dc0/m2        (ring2 internal mesh at carrier)
        #   dc0   = m1*(zs1 + |zr1|)/2  (zero-shift carrier diameter)
        # which reduces to
        #   |zr1|*(m2 - m1/2) = m1*zs1/2 + m2*(zp2 + diff*Np)
        denom = self.module2 - self.module1 / 2.0
        numer = (self.module1 * self.zs1 / 2.0
                 + self.module2 * (self.zp2 + self.type_diff * self.num_planets))
        zr1_real = numer / denom
        self.zr1 = -float(np.floor(zr1_real + 0.5))
        self.zr2 = -float(np.floor(zr1_real - self.type_diff * self.num_planets + 0.5))
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

    def _calc_stage2(self) -> None:
        # Ring2 keeps its integer tooth count from calc(); the stage-2
        # planets sit on the carrier radius and the ring's profile shift
        # absorbs the remaining mismatch (see finalize_parameters).
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
        print("### Size")
        print("Sun = ", self.ds1, " [mm],  ", self.zs1, " [ea]")
        print("Planet1 = ", self.dp1, " [mm],  ", self.zp1, " [ea]")
        print("Ring1 = ", self.dr1, " [mm],  ", self.zr1, " [ea]")
        print("Planet2 = ", self.dp2, " [mm],  ", self.zp2, " [ea]")
        print("Ring2 = ", self.dr2, " [mm],  ", self.zr2, " [ea]")

    def _output_simple(self) -> None:
        print("\n##### Simple Planetary Gear Set")
        print("### Ratio")
        print("Ratio (Sun-Planet1) = ", self.gp1s, "")
        print("Ratio (Total, Carrier Output) = ", self.g3, " (1-stage),  ",
              self.g3 ** 2, " (2-stages),  ", self.g3 ** 3, " (3-stages)")
        print("Ratio (Total, Ring1 Output) = ", self.g4, " (1-stage),  ",
              self.g4 ** 2, " (2-stages),  ", self.g4 ** 3, " (3-stages)")
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

    def _check_non_factorizing(self) -> None:
        cond = (self.zs1 % self.num_planets != 0
                and (-self.zr1) % self.num_planets != 0)
        self.checks.non_factorizing_1 = self._label(cond, "Good for noise", "No good for noise")
        self._emit("Sequential Mesh Condition (Non-Factorizing, Not Required) 1",
                   self.checks.non_factorizing_1)
        if self.is_wolfrom:
            cond = (-self.zr2) % self.num_planets != 0
            self.checks.non_factorizing_2 = self._label(cond, "Good for noise", "No good for noise")
            self._emit("Sequential Mesh Condition (Non-Factorizing, Not Required) 2",
                       self.checks.non_factorizing_2)

    def _check_equal_distance(self) -> None:
        modulus = (self.num_planets * self.type_diff
                   if self.gear_type == 2 else self.num_planets)
        cond = (self.zs1 - self.zr1) % modulus == 0
        self.checks.equal_distance_1 = self._label(cond, "OK", "Fail")
        self._emit("Planet Numbers (Equal Distance Condition) 1",
                   self.checks.equal_distance_1)
        if self.is_wolfrom:
            cond = (-self.zr2) % self.num_planets == 0
            self.checks.equal_distance_2 = self._label(cond, "OK", "Fail")
            self._emit("Planet Numbers (Equal Distance Condition) 2",
                       self.checks.equal_distance_2)

    def _check_planets_interference(self) -> None:
        cond = (self.pressure_angle == STANDARD_PRESSURE_ANGLE
                and self.num_planets < np.pi / np.arcsin((self.zp1 + 2) / (self.zp1 + self.zs1)))
        self.checks.planets_interference_1 = self._label(cond, "OK", "Fail")
        self._emit("Planets Interference (Non-Overlap Condition) 1",
                   self.checks.planets_interference_1)
        if self.is_wolfrom:
            cond = (self.pressure_angle == STANDARD_PRESSURE_ANGLE
                    and self.num_planets < np.pi / np.arcsin(
                        self.module2 * (self.zp2 + 2) / self.dc))
            self.checks.planets_interference_2 = self._label(cond, "OK", "Fail")
            self._emit("Planets Interference (Non-Overlap Condition) 2",
                       self.checks.planets_interference_2)
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
        if self.is_wolfrom:
            cond = (self.pressure_angle == STANDARD_PRESSURE_ANGLE
                    and (-self.zr2) >= self._involute_thresh(self.zp2))
            self.checks.involute_interference_2 = self._label(cond, "OK", "Fail")
            self._emit("Involute Interference Condition 2", self.checks.involute_interference_2)
        if self.pressure_angle != STANDARD_PRESSURE_ANGLE:
            print("No Check (Non-Standard) ")

    def _check_trimming_interference(self) -> None:
        cond = (self.pressure_angle == STANDARD_PRESSURE_ANGLE
                and (-self.zr1 - self.zp1) >= MIN_RIM_FOR_TRIMMING)
        self.checks.trimming_interference_1 = self._label(cond, "OK", "Fail")
        self._emit("Trimming Interference 1", self.checks.trimming_interference_1)
        if self.is_wolfrom:
            cond = (self.pressure_angle == STANDARD_PRESSURE_ANGLE
                    and (-self.zr2 - self.zp2) >= MIN_RIM_FOR_TRIMMING)
            self.checks.trimming_interference_2 = self._label(cond, "OK", "Fail")
            self._emit("Trimming Interference 2", self.checks.trimming_interference_2)
        if self.pressure_angle != STANDARD_PRESSURE_ANGLE:
            print("No Check (Non-Standard) ")
            self.checks.trimming_interference_1 = "No Check (Non-Standard)"

    def _check_teeth_integer(self) -> None:
        def is_int(v: float) -> bool:
            return round(float(v), ROUND_PRECISION).is_integer()

        cond = is_int(self.zs1) and is_int(self.zp1) and is_int(self.zr1)
        self.checks.teeth_number_integer_1 = self._label(cond, "OK", "Fail")
        self._emit("Teeth Numbers which is Integer 1", self.checks.teeth_number_integer_1)
        if self.is_wolfrom:
            cond = is_int(self.zp2) and is_int(self.zr2)
            self.checks.teeth_number_integer_2 = self._label(cond, "OK", "Fail")
            self._emit("Teeth Numbers which is Integer 2", self.checks.teeth_number_integer_2)