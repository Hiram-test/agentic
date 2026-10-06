# 05 Result validation, force recovery and contours

## Select the final state

DAT can contain repeated U/S blocks for different steps or increments. Select the last displacement block and last cable-stress block, require matching times and compare with the expected total time: 1 for P1; 2 for P2–P6.

Require U for 1,125 original nodes and S at eight integration points of all 1,123 cable elements. Match actual node/element ID sets. U component order is UX/UY/UZ; S order is Sxx/Syy/Szz/Sxy/Sxz/Syz. Require every value to be finite.

`run.py` validates STA/log completion before invoking `dat_results()` and `process()`. An incorrect count or time fails the result contract.

## Displacements

Compute `Uabs = sqrt(UX² + UY² + UZ²)` and identify its maximum over the 1,125 original nodes. Record the node ID and all three components. Compute the maximum absolute UZ separately when needed.

Line-contour colors use the mean of endpoint nodal values. Exact nodal extrema remain in `nodes.csv` and `summary.json`. Require maximum absolute UY below 1e-6 mm as a check on the planar constraint and result mapping.

## Signed cable-force recovery

For original coordinates Xi/Xj and final displacements ui/uj:

```text
xi = Xi + ui
xj = Xj + uj
n = (xj - xi) / ||xj - xi||
Sbar = mean(S at the 8 integration points)
sigma_axial = n.T @ Sbar @ n
N_kN = sigma_axial * A0_mm2 / 1000
```

Expanded tensor projection:

```text
sigma = Sxx*nx² + Syy*ny² + Szz*nz²
      + 2*Sxy*nx*ny + 2*Sxz*nx*nz + 2*Syz*ny*nz
```

Interpret output S as the global Cauchy tensor. Use the deformed chord direction and original area A0, which define the benchmark's recovery convention. A derived finite-strain recovery using current area requires explicit area/stress-measure conversion and a separately identified comparison series.

Retain signed force, save the minimum cable force and require positive tension throughout the cable set. Use the six-component axial projection rather than an equivalent-stress scalar.

B31 lies outside the E_CABLE DAT stress set. Its cable-force/stress VTU values are NaN with `cable_result_valid=0`.

## Span maxima and safety factors

Read the eight explicit element groups from `span_groups.json`. Bottom-cable group sizes, ordered north side/main/south side/south auxiliary, are 149/295/160/115. Portal-cable sizes are 64/216/67/47. Together these reporting groups contain 1,113 elements; the remaining ten cable connection elements are retained in full-system CSV/VTU.

For each case/group, find the maximum positive axial force. Compare it with the same cable family and span in the original report. Calculate `K = Nbreak / Nmax` using 38,080 kN for bottom cables and 14,280 kN for portal cables. Preserve both the governing element and signed comparison error.

## Per-case graphics

Generate seven PNGs:

1. `USUM.png`: total displacement, mm.
2. `UZ.png`: signed vertical displacement, mm, with a symmetric color scale.
3. `bottom_N_kN.png`: bottom-cable axial force, kN.
4. `portal_N_kN.png`: portal-cable axial force, kN.
5. `bottom_sigma_axial_MPa.png`: bottom-cable axial stress, MPa.
6. `portal_sigma_axial_MPa.png`: portal-cable axial stress, MPa.
7. `deformed_1x.png`: deformed centerlines at displacement scale factor 1.

Identify the case, units, X–Z projection and deformation scale. Display X/Z coordinates in metres and label independently scaled axes. Draw colors on line members. Force/stress graphics use the union of each family's four reporting groups, aligning plotted extrema with the span tables. Retain all cable elements in CSV/VTU.

## ParaView

Open `results.vtu` and select Apply. Point coordinates and `U_mm` are in mm; `N_kN` and `sigma_axial_MPa` are cell fields. Increase Line Width for clarity. A Tube filter can improve visibility; document its display radius.

For deformation, use Warp By Vector with `U_mm` and Scale Factor=1. Label any larger display factor. Filter on `cable_result_valid` before displaying cable-force fields. Preserve CSV/VTU alongside screenshots.
