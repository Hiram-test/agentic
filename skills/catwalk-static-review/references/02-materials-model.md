# 02 Materials, sections, initial stresses and units

## Units

Use a consistent system: length mm, force N, time s, mass tonne, stress MPa = N/mm² and temperature °C. Density is tonne/mm³ and gravity is 9,806 mm/s². Conversions: 1 kN = 1,000 N; 1 m = 1,000 mm; 1 tonne/mm³ = 10¹² kg/m³.

Pass the original millimetre coordinates to Gmsh. Plot X/Z in metres by dividing by 1,000; CSV/VTU coordinates remain millimetres. Stress times area gives N; divide by 1,000 for kN.

## Actual INP properties

| Set | Element | Material | E / MPa | Poisson ratio | Density / tonne/mm³ | Section |
|---|---|---|---:|---:|---:|---|
| E_SEC1 | T3D2 | MAT1 | 120000 | 0.3 | 1.26484805e-08 | A = 22298.692 mm² |
| E_SEC2 | T3D2 | MAT2 | 120000 | 0.3 | 8.59881705e-09 | A = 8402.9797 mm² |
| E_SEC3 | B31 | MAT3 | 206000 | 0.31 | 1.01978381e-17 | Rectangle 98.954535 × 98.954535 mm |

P3/P6 define `*EXPANSION` with alpha = 1.2e-5 /°C for all three materials. P1/P2/P4/P5 omit that card. The B31 orientation vector is (1, 1, 1). Calculate its area from the supplied dimensions at full precision.

MAT1 represents the equivalent bottom cable bundle, MAT2 the portal support cable bundle and MAT3 the equivalent portal members. The report describes 15 conventional bottom ropes plus one smart-core rope, and six portal ropes. Use the INP equivalent areas directly.

MAT1/MAT2 densities correspond to approximately 12648.48/8598.82 kg/m³ and implement the supplied equivalent-weight model. MAT3's near-zero density assigns negligible member self-weight; other portal weight is already represented by nodal loads. Retain these weight definitions together.

### Card example

```text
*MATERIAL, NAME=MAT1
*ELASTIC
120000, 0.3
*DENSITY
1.26484805e-08
*SOLID SECTION, ELSET=E_SEC1, MATERIAL=MAT1
22298.692
```

Temperature cases include this card under each material:

```text
*EXPANSION
1.2e-05
```

Parse properties within the current `*MATERIAL` context so density and expansion remain associated with the correct material.

## Geometry and element semantics

The model contains 1,123 T3D2 elements and 71 B31 elements. Node IDs are non-contiguous and their maximum exceeds the node count. Preserve actual node/element IDs across geometry, loads, initial stresses, boundaries and output groups.

The migrated INP uses B31 equivalent portal members, including their bending stiffness and section orientation. Retain that formulation when describing or reconstructing the model. T3D2 supports signed axial force; check all recovered cable forces for positive tension and investigate any zero/negative force before acceptance.

## Initial stress

Each record following `*INITIAL CONDITIONS, TYPE=STRESS` contains:

`element, integration_point, Sxx, Syy, Szz, Sxy, Sxz, Syz`

There are eight records per cable element: 1,123 × 8 = 8,984. Original comments identify a global PK2 initial-stress tensor compatible with the locked solver. Preserve all supplied records in the reproduction run.

The source is the MCT initial element/cable force. For an axial initial stress s and unit direction n, the global tensor is `s * n ⊗ n`, including off-diagonal terms for inclined cables. Initial stress and initial geometry together define the reference state. During a derived-mesh conversion, migrate parent-element identity, direction, integration points and stress measure. Convert between stress measures explicitly if using output Cauchy stress to construct a new initial state.

## Cable resistance

The original rope strength grade is 1960 MPa. The report's bundle breaking forces used for this verification are 38,080 kN and 14,280 kN. Evaluate cable safety through those breaking forces and the calculated span maxima, following reference 05.
