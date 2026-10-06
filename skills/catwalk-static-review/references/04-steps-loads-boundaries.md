# 04 Steps, loads, temperatures and supports

## Six independent cases

| Case | Final combination | Steps | Temperature |
|---|---|---:|---|
| P1 | Dead load | 1 | No temperature card |
| P2 | Dead + construction | 2 | No temperature card |
| P3 | Dead + construction + 15°C cooling | 2 | 0 to -15°C |
| P4 | Dead + construction + construction wind | 2 | No temperature card |
| P5 | Dead + maximum gust | 2 | No temperature card |
| P6 | Dead + construction + 34°C cooling | 2 | 0 to -34°C |

Each file defines an independent complete analysis. Every two-step case first establishes its own dead-load state, then applies its final total combination.

All steps use `*STEP, NLGEOM`. The first `*STATIC` card has no explicit time parameters; the locked solver uses defaults (1, 1) and records a warning. Preserve this original behavior. The second step is:

```text
*STEP, NLGEOM
*STATIC
1., 1., 1e-6, 1.
```

The entries are initial increment, step duration, minimum increment and maximum increment. These are static load-path parameters. Retain the supplied solution controls for baseline reproduction.

## Gravity and total nodal loads

Each step applies:

```text
*DLOAD
E_CABLE, GRAV, 9806, 0.0, 0.0, -1.0
E_FRAME, GRAV, 9806, 0.0, 0.0, -1.0
```

Nodal CLOAD resultants in N, excluding gravity:

| Step/case | Sum Fx | Sum Fy | Sum Fz |
|---|---:|---:|---:|
| First step, every file | 0 | 0 | -4725567.874 |
| Second step, P2/P3/P6 | 0 | 0 | -8069828.486 |
| Second step, P4 | 0 | 2246926.048 | -8312299.4553 |
| Second step, P5 | 0 | 15303735.373 | -6377029.291 |

Second-step CLOAD records specify the final **total**, including the permanent nodal load. Apply that total once. The earlier daughter-file version supplied an increment where a total was required, replacing the first-step permanent contribution; the packaged inputs carry the corrected totals.

The parser's load summation follows the supplied files' card semantics. For new inputs containing amplitudes, different OP behavior or multiple independent load blocks, extend and verify parsing against those semantics first.

Each input audit records CLOAD moments about the global origin in N·mm, allowing load-position checks. Preserve the actual nodal-load list from the INP.

## Temperature

P3/P6 use alpha = 1.2e-5 /°C for all three materials:

```text
*NSET, NSET=N_THERM, GENERATE
1, 80000
*INITIAL CONDITIONS, TYPE=TEMPERATURE
N_THERM, 0.
```

The first step sets `N_THERM, 0.`. The final P3 step sets:

```text
*TEMPERATURE
N_THERM, 0.
N_MCT, -15
```

P6 uses -34. This first assigns the base temperature to the broad set, then the temperature change to the original N_MCT nodes. The locked solver clips the N_THERM range beyond existing nodes and issues a warning. Preserve the original set definition. When evaluating another solver build, explicitly check temperature transfer through expanded T3D2/B31 elements and compare P3/P6 results.

## Global support directions

DOF 1 = UX; DOF 2 = UY; DOF 3 = UZ. All 1,125 original nodes have UY = 0.

Additional UX = 0 nodes:

`1, 154, 450, 728, 729, 730, 1001, 1066, 1280, 1395`

Additional UZ = 0 nodes:

`1, 3, 6, 154, 157, 447, 450, 608, 723, 726, 728, 729, 730, 1001, 1003, 1063, 1066, 1280, 1283, 1347, 1393, 1395`

Use the parsed input sets as the executable source. Preserve freedom in all remaining translational/rotational DOFs.

## Output contract

The input requests nodal U for N_MCT, printed S for E_CABLE, and file output S/E. P2–P6 specify FREQUENCY=99 in the second step; the locked solver produces final output. Verify its actual time and completeness.

The DAT postprocessor reads original-node U and cable-element S. To obtain support reactions or B31 section forces, create an output-enhanced derived input, configure the relevant cards for the actual solver version, record its hash and verify the unchanged baseline displacement/cable-force response.
