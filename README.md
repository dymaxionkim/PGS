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
| Module, m | Gear module [mm], > 0 |
| Np | Number of planets [ea], > 2 |
| Zr2 / Np | Ring gear stage 2 teeth ÷ Np; defines outer diameter |
| Zs1 / Np | Sun gear stage 1 teeth ÷ Np; defines gear ratio |
| Shift factor, Gs1.X | Profile shift coefficient of stage-1 sun gear |
| Shift factor, Gs2.X | Profile shift coefficient of stage-2 sun gear |
| Backlash factor, B | Backlash adjustment |
| Addendum factor, A | Addendum coefficient |
| Dedendum factor, D | Dedendum coefficient |
| Pressure angle, α | Pressure angle [deg] (default 20°) |
| Hob end radius, C | Radius of hob tip [mm] |
| Tooth end radius, E | Radius of tooth tip [mm] |
| Plot option | Stage1 / Stage2 / Total |

Press **Run** to compute and plot.

![](./img/PGS_02.png)

### Output

The result panel displays:

- **Ratio** — gear ratios for each stage and total (carrier fixed / ring fixed / 3K type)
- **Size** — pitch circle diameters and tooth counts for all six gears
- **Checks** — pass/fail status for each geometric feasibility check

## Files

| File | Purpose |
|------|---------|
| `design.py` | GUI entry point (ttk theme, layout, event handlers) |
| `PGS.py` | Planetary gear sizing logic |
| `GPG.py` | Generic involute gear profile generation |
| `PGS.bat` / `PGS.sh` | Platform launcher scripts |

## Thank you!