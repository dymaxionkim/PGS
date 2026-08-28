# PGS

_Sizing Tool for Planetary Gear Set (Simple & Wolfrom)_

Computes gear ratios, gear sizes, and geometric feasibility checks for
simple and Wolfrom-type planetary gear sets. The tool is built with Python
and provides a ttk-based graphical interface.

## Gear Types

| Type | Code | Description |
|------|------|-------------|
| Simple | 0 | Standard single-stage planetary set |
| Wolfrom (diff=1) | 1 | Wolfrom set, teeth difference = 1 |
| Wolfrom (diff=0.5) | 2 | Wolfrom set, teeth difference = 0.5 |
| Wolfrom (diff=2) | 3 | Wolfrom set, teeth difference = 2 |
| Wolfrom (diff=3) | 4 | Wolfrom set, teeth difference = 3 |
| Wolfrom (diff=4) | 5 | Wolfrom set, teeth difference = 4 |
| Wolfrom (diff=5) | 6 | Wolfrom set, teeth difference = 5 |
| Wolfrom (diff=6) | 7 | Wolfrom set, teeth difference = 6 |
| Wolfrom (diff=7) | 8 | Wolfrom set, teeth difference = 7 |
| Wolfrom (diff=8) | 9 | Wolfrom set, teeth difference = 8 |
| Wolfrom (diff=9) | 10 | Wolfrom set, teeth difference = 9 |
| Wolfrom (diff=10) | 11 | Wolfrom set, teeth difference = 10 |
| Wolfrom (diff=11) | 12 | Wolfrom set, teeth difference = 11 |
| Wolfrom (diff=12) | 13 | Wolfrom set, teeth difference = 12 |
| Wolfrom (diff=13) | 14 | Wolfrom set, teeth difference = 13 |
| Wolfrom (diff=14) | 15 | Wolfrom set, teeth difference = 14 |
| Wolfrom (diff=15) | 16 | Wolfrom set, teeth difference = 15 |
| Wolfrom (diff=16) | 17 | Wolfrom set, teeth difference = 16 |
| Wolfrom (diff=17) | 18 | Wolfrom set, teeth difference = 17 |
| Wolfrom (diff=18) | 19 | Wolfrom set, teeth difference = 18 |
| Wolfrom (diff=19) | 20 | Wolfrom set, teeth difference = 19 |
| Wolfrom (diff=20) | 21 | Wolfrom set, teeth difference = 20 |

## Gear Set Architecture

The model contains six gears arranged in two stages:

| Gear | Description |
|------|-------------|
| Gs1 | Sun gear, stage 1 |
| Gp1 | Planet gear, stage 1 |
| Gr1 | Ring gear, stage 1 |
| Gs2 | Sun gear, stage 2 |
| Gp2 | Planet gear, stage 2 |
| Gr2 | Ring gear, stage 2 |

## Geometric Checks

The following checks are performed on each stage:

- Non-factorizing (sequential mesh condition)
- Equal distance condition (planet spacing)
- Planets interference (non-overlap condition)
- Involute interference
- Trimming interference
- Integer tooth numbers

## Prerequisites

- [uv](https://docs.astral.sh/uv/) package manager

## Installation

```bash
git clone https://codeberg.org/dymaxionkim/PGS.git
cd PGS
uv sync
```

## Usage

Run the GUI:

```bash
uv run design.py
```

Or use the platform launcher:

- `PGS.bat` on MS Windows
- `./PGS.sh` on Linux

### Input Parameters

![](./img/PGS_01.png)

| Parameter | Description |
|-----------|-------------|
| Type | Gearbox type from the table above |
| Module1, m1 | Stage-1 gear module [mm], > 0 |
| Module2, m2 | Stage-2 gear module [mm], > 0 |
| Np | Number of planets [ea], > 2 |
| Zp2 | Stage-2 planet gear teeth number [ea], > 0; stage-2 planets are placed on the stage-1 carrier radius and ring2 adapts to mesh with them |
| Zs1 | Sun gear stage 1 teeth number [ea], > 0; defines gear ratio |
| Input speed, ns1 | Input speed of the stage-1 sun gear Gs1 [rpm]; used to compute the operating speeds shown in the Speed block |
| Shift factor, Gs1.X | Profile shift coefficient of stage-1 sun gear |
| Shift factor, Gp1.X | Profile shift coefficient of stage-1 planet gear; together with Gs1.X it determines the carrier radius |
| Shift factor, Gp2.X | Profile shift coefficient of stage-2 planet gear |
| Backlash factor, B | Backlash adjustment |
| Addendum factor, A | Addendum coefficient |
| Dedendum factor, D | Dedendum coefficient |
| Pressure angle, α | Pressure angle [deg] (default 20°) |
| Hob end radius, C | Radius of hob tip [mm] |
| Tooth end radius, E | Radius of tooth tip [mm] |
| Plot option | `Stage1` / `Stage2` / `Total` for the whole-stage layouts, or a single gear: `Gs1`, `Gp1`, `Gr1` (stage 1), `Gp2`, `Gr2` (stage 2) — only the selected gear is drawn. Files: `PGS1.png`, `PGS2.png`, `PGS.png`, or `Gs1.png` / `Gp1.png` / `Gr1.png` / `Gp2.png` / `Gr2.png` |
| Teeth profile | `Involute Teeth` (GPG) / `Cycloid Teeth` (CPG), or **`All`** to overlay both profiles in one plot (involute grey/black, cycloid blue) |

Press **Run** to compute and plot.

The ring gear shift factors (Gr1.X, Gr2.X) are not inputs: they are computed automatically so that the ring teeth mesh with the planet teeth without flank clearance (zero backlash) at the carrier radius, taking the input shift factors (Gs1.X, Gp1.X, Gp2.X) into account. With backlash B = 0 there is no tooth gap for any shift combination; the B input adds flank clearance on top of this, as intended.

Ring gear tooth counts (Zr1, Zr2) are determined in the zero-shift state: the layout is solved with standard pitch circles and each ring tooth count is rounded to the nearest integer, so the ring gears always have whole tooth numbers regardless of the shift factor inputs.

### Cycloidal teeth

Choosing **Cycloid Teeth** generates tooth profiles with epicycloidal/hypocycloidal flanks (`CPG.py`, the same interface as `GPG`). The tooth circular thickness is `πm/2 − mB` regardless of the profile shift, so shifted mates mesh without interference. Choosing **All** overlays the involute and cycloid profiles in a single plot for direct comparison.

> Limitation: a cycloidal tooth profile requires a whole tooth count. In Wolfrom layouts the stage-2 sun `Zs2` can be fractional (e.g. 15.0667); in that case `Cycloid Teeth` / `All` abort — use `Involute Teeth`, or adjust `Zs1`, `Np`, `k` so `Zs2` becomes an integer.

![](./img/PGS_02.png)

### Output

The result panel displays:

- **Ratio** — gear ratios for each stage and total (carrier fixed / ring fixed / 3K type)
- **Speed** — operating speeds of the input sun (Gs1), carrier, both rings (Gr1, Gr2) and compound planets (Gp1,Gp2) in [rpm], reported for all three lockup configurations (Type-3K with ring1 fixed / ring2 fixed with carrier output / carrier fixed with ring2 output); each value carries an explicit +/- direction sign relative to the input rotation of Gs1
- **Size** — pitch circle diameters and tooth counts for all six gears
- **Checks** — pass/fail status for each geometric feasibility check

## Files

| File | Purpose |
|------|---------|
| `design.py` | GUI entry point (ttk theme, layout, event handlers, matplotlib plotting, report/CSV output) |
| `PGS.py` | Planetary gear sizing logic |
| `GPG.py` | Generic involute gear profile generation (external/internal gears) |
| `CPG.py` | Cycloidal gear profile generator, drop-in replacement sharing the `GPG` interface |
| `PGS.bat` / `PGS.sh` | Platform launcher scripts |

## Thank you!