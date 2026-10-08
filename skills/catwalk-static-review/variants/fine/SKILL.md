---
name: catwalk-static-review-fine
description: Read the model-relevant catwalk construction drawings into fixed component, property, weight and state tables, then execute end-to-end nonlinear static verification of the Zhangjinggao Bridge catwalk and portal support cables using the version-locked P1–P6 INP files. Audit materials, sections, initial stresses, loads and constraints; regenerate and verify the one-dimensional mesh with Gmsh; run CalculiX; recover cable forces; generate contours, CSV/VTU data and Word/PDF engineering reports.
---

# Catwalk static verification: end-to-end execution skill

## 0. Task and model contract

Complete the drawing-to-model input readback, then run the six supplied INP files from asset verification through numerical solution and report delivery. Populate calculated results from this execution's solver output. Preserve raw input, logs and results so every reported value can be traced to its source.

The model contains the bottom catwalk cables, portal support cables and equivalent connecting members: **1,125 nodes, 1,194 elements, an X–Z planar system with UY fixed at all original nodes**. P5 is the dead-load-plus-maximum-gust combination. Resolve case identity from the manifest and input hash; filenames such as C05 in other datasets have their own identities.

The requested engineering report covers the overall catwalk and portal cable system. Its contents and templates are specified in reference 06.

### Executed-model source precedence

1. Assets locked by `assets/integrity.json` and `assets/reference/manifest.json`.
2. Actual INP cards: values, node IDs, connectivity and step definitions.
3. Original PDF Table 1-7 on physical page 11, Table 1-11 on page 30 and Table 1-14 on page 39; independently sourced MAPDL displacement benchmarks.
4. Explanatory documentation and historical results.

Use this precedence to identify the executed model. Keep drawing, report and INP values in separate rows of the input readback; use the actual drawing revision or confirmation sheet to establish physical design values. Preserve the original material, area, support and initial-stress definitions during reproduction.

Use `assets/inputs/migrate_P1.inp` through `migrate_P6.inp`. The historical `model/catwalk-fem/eval/formfind_974211b2/daughters/migrate_P*.inp` files belong to an earlier load definition. In the supplied files, second-step CLOAD values **already include the permanent nodal load**. Apply these totals once.

## Drawing-readback contract shared by all three versions

Read [08 Drawing-to-model input contract](../../references/08-drawing-input-contract.md) before the sequence below. It fixes the component families, property names, eight table layouts, source locators, units and comparison checkpoints for V1, V2 and V3. Select one version for the task. All three perform the same work and produce the same deliverables; only the size of each written operation differs.

Resolve `SKILL_ROOT` to the directory containing `assets/inputs`, `references` and `scripts/run.py`. For a version inside `variants/`, use the enclosing `catwalk-static-review` directory. Set `INPUT_READBACK_DIR` to a separate working output directory and reserve a new/empty `SOLVER_RUN_DIR` for the solver. Each variant shares the same assets and scripts.

Read the bottom ropes, portal ropes, down-pull branches, equivalent portal assemblies and support interfaces as the structural scope. Read the deck, handrail, crossbeam, cross-passage and equipment families listed in reference 08 for their assigned weights. Preserve physical component counts separately from equivalent finite-element counts.

Write these tables in this fixed order:

| Table | Fixed output | Content |
|---|---|---|
| T01 | `01_sources.csv` | File identity, drawing revision, view, source locator and evidence crop |
| T02 | `02_control_points.csv` | Named geometry points, explicit state, station/coordinates and support DOFs |
| T03 | `03_components.csv` | Physical families, quantities, locations and model representation |
| T04 | `04_properties.csv` | Source-specific physical and equivalent-model properties |
| T05 | `05_distributed_weights.csv` | Component-by-component longitudinal permanent weights |
| T06 | `06_point_weights.csv` | Located assembly weights, sharing and recipient nodes |
| T07 | `07_model_mapping.csv` | Physical-to-INP mapping and numerical differences |
| T08 | `08_actions_states.csv` | Construction, temperature, wind, initial state and case/step identities |

Use the exact columns in reference 08. Keep all source facts available by row ID. Use `input_readback.md` to display the same records. Record differences as values and source locations. For an absent source value, leave the numeric cell empty and identify the requested source in its row.

## Fixed sequence - V3 (36 actions)

### 01. Locate the actual files

Enumerate the supplied construction drawings, report, confirmation sheets and the six manifest-listed input files. Create source IDs. Distinguish a cited document title from an actual file available for reading.

### 02. Register identities and revisions

Hash each file and record its revision, page/sheet range, units and source type in T01. Verify the report and six INP hashes against assets/integrity.json and the manifest.

### 03. Read the report in page order

Read pp4-5, p6, pp7-8, pp9-10 and p11 for arrangement, physical properties, weights, geometry and combinations. Read the later profile/force tables as comparison outputs. Associate each extracted fact with its table/row or paragraph.

### 04. Select and inspect drawing views

Select only the views serving reference 08 component families. Read native dimensions/text or OCR the scanned view, inspect the image and save crops. Record each view scale, coordinate datum and evidence locator in T01.

### 05. Parse geometry and constitutive cards

Call scripts/model.py on each INP. Read NODE, ELEMENT, ELSET, NSET, MATERIAL, ELASTIC, DENSITY, EXPANSION and section cards with their actual set membership. Seed model-side T04/T07 records.

### 06. Parse state and load cards

Read INITIAL CONDITIONS, BOUNDARY, STEP, STATIC, DLOAD, CLOAD and TEMPERATURE with their block/step identity. Compare each parse with P1_input_audit.json through P6_input_audit.json. Seed T08 and preserve the source line locators.

### 07. Normalize drawing coordinates

Convert station notation to metres, retain printed coordinates and declare the elevation datum. Record drawing-to-global transformations explicitly in T02 and the source view convention in T01.

### 08. Check the INP station transform

Test station_m=x_mm/1000+16000 against the lower north anchorage and two tower points. Compute residuals for these control pairs, then apply the checked relation to other input nodes. Retain the original millimetre coordinates by source reference.

### 09. Read bottom-rope control points

Enter all Table 1-5 and corresponding drawing points in T02. Include anchors, turning points, tower saddles, both down-pull attachment points and the midspan target. Associate each point with its connected cable segments and explicit state.

### 10. Read portal-rope control points

Enter all Table 1-6 and corresponding drawing points in T02. Include anchorages, saddle/split points and the midspan target. Map input nodes by topology and point identity. Record printed and input coordinate differences individually.

### 11. Read support kinematics

At each anchorage and saddle, read the attached rope and declared free/fixed or sliding directions. Enter physical support wording and parsed model UX/UY/UZ/RX/RY/RZ in separate T02 rows. Identify the all-node UY constraint as a model convention.

### 12. Read both down-pull assemblies

Map input element 728 to nodes 729/160 and element 729 to nodes 444/730. Read the associated drawing route, endpoints and physical section/count. Separate fixed anchorage points from main-rope attachment points and include both branch weights.

### 13. Read single-rope properties

Read conventional and smart-core rope construction, diameter, metallic area, modulus, strength and unit mass. Record physical quantity basis: 15 conventional plus one smart-core bottom rope and six upper ropes. Give the rope families separate T03/T04 records.

### 14. Calculate and compare bundle properties

Calculate the physical bundle areas from the single-rope areas and counts. Enter the exact E_SEC1/E_SEC2 input areas, E, Poisson ratio, density and thermal expansion in source-specific T04 rows. Calculate area differences in T07.

### 15. Read physical portal arrangements

Read each portal station/type, physical member sections, height, attachment geometry and assembly quantity. Reference its ordinary or triangular weight identity. Record physical members/assemblies in T03; keep finite-element count in T07.

### 16. Map equivalent portal members

Trace E_SEC3 connectivity between bottom and portal ropes. Map all 71 B31 members to the located assemblies, recording 98.954535 mm rectangular dimensions, MAT3 and orientation from the input. Retain the report truss description with its own source.

### 17. Read continuous deck and handrail items

Read D01-D09: rope routes/counts, tread geometry/spacing, upper and lower mesh sizes/widths/layers, side mesh height/sides, small crossbeams and electrical allowances. Record actual piece/areal/unit masses and unit definitions.

### 18. Read located assemblies

Read P01-P11: large and portal crossbeams, PWS rollers, cross passages, restraints, displacement frames, ordinary/triangular portal assemblies and guide wheels. Record every required station, assembly count, mass basis, share and load recipient.

### 19. Calculate line-weight contributions

For each uniform interval, calculate rope_count*unit_mass, areal_mass*covered_width*layers, or piece_mass*pieces_per_station/spacing. Enter formula operands, length basis, sharing factor and source refs in T05. Keep allowances as their stated input type.

### 20. Sum line weights by recipient

Group T05 by bottom/portal system and loaded interval. Convert mass to force using the recorded g. Compare with Table 1-1 and the Table 1-3 rope row; preserve rounded report forces and calculated values separately.

### 21. Calculate located assembly weights

For each T06 station, calculate piece_mass*quantity*sharing_factor. Use sharing_factor=1 for an already tabulated half-cross-passage mass. Convert to kN with the recorded g and retain the source table weight for comparison.

### 22. Resolve ordinary and triangular portal locations

Use the arrangement to assign ordinary portals and cross-passage triangular portals to their respective stations. Attach the guide-wheel sets according to their own quantity definition. Reconcile assembly identities so each physical weight is listed once.

### 23. Assign recipients and tributary weights

Map each T05/T06 contribution to its cable system and node/element recipients. Record density/gravity group or CLOAD group and any distribution factors in T07. Use the documented arc/projected length and load-transfer relation.

### 24. Check permanent-load force and moment

Integrate each physical contribution and sum its force and moment about the model origin. Independently compute INP rho*A*L*g and nodal-load resultants/moments. Record the residuals in T07, retaining physical and model totals.

### 25. Read action magnitudes and directions

Read bottom construction line/point actions, portal traction, cooling and wind definitions. Record value, unit, direction, recipient and source in T08. Link permanent actions to their existing T05/T06 row IDs.

### 26. Read the six case definitions

Match Table 1-7 to P1-P6 by the manifest and actual loads. Record one step for P1 and two for P2-P6, including OP behavior and final total CLOAD. Check final resultant sums and P3/P6 temperature records against reference 04.

### 27. Register the initial-stress field

Reference the stress block containing 8984 integration-point records on 1123 cable elements. Retain tensor component order, element identity and source hash. Register initial temperature definitions in the same T08 state record group.

### 28. Associate geometry with its stated state

Record specified formed targets, reported empty/formed profiles, INP reference coordinates and solved case/step labels separately. Supply the actual source locator for each documented target/load relationship. Enter numerical coincidence only as a T07 comparison.

### 29. Compare physical and model properties

Compute differences for rope bundle areas, portal properties, coordinates, support conventions and counts. Keep physical assembly counts separate from finite-element counts. Complete T07 rows for each required component family and aggregate.

### 30. Record document-specific differences

Record p6 lower-mesh 50x75 mm and Table 1-1 50x70 mm, the Table 1-5 bottom midspan station versus the input, and the report truss versus INP B31 descriptions. Add supplied drawing/confirmation values as separate source rows and reference the resulting choice.

### 31. Check table completeness and references

Verify all eight headers, unique row identities where applicable, foreign IDs, units, quantity bases and source locators. Verify T03 weight assignments resolve to T05/T06 and all T07 input references exist. Mark each unprovided field in its own row.

### 32. Finish the readback package

Write input_readback.md from T01-T08 in their fixed order. Attach the used evidence crops and hashes. Confirm unchanged input identities and reserve a separate empty SOLVER_RUN_DIR. Use this package as the input-review hand-off.

### 33. Verify assets and mesh

Execute the existing verify-only command and Gmsh workflow in Sections 1-2 and references 01-03. Compare generated coordinates, tags and connectivity to the input. Record the actual solver identity and execution paths.

### 34. Solve and verify numerical results

Run the existing locked P1-P6 sequence with CalculiX. Check completion, final step/time, node/stress coverage, signed forces, numerical comparison and strength criteria using Sections 2-4 and references 04-05/07.

### 35. Generate the engineering report

Generate the existing Chinese Word/PDF report from the actual solver outputs using reference 06. Place readback summaries with materials, loads, control points and model definition. Use the prescribed source terminology, fonts and table style.

### 36. Verify and deliver the review

Check report numbers against computed summaries; visually inspect the generated report. Include T01-T08, input_readback.md, evidence, source/input hashes, original inputs, solver records and result files. Refresh delivery checksums.

## 1. Read the execution references

On the first execution, read these in order:

1. [Installation, file contracts and execution](../../references/01-execution.md)
2. [Materials, sections, initial stresses and units](../../references/02-materials-model.md)
3. [Gmsh API, tag mapping and mesh refinement](../../references/03-gmsh.md)
4. [Steps, loads, temperatures and supports](../../references/04-steps-loads-boundaries.md)
5. [Result validation, force recovery and contours](../../references/05-postprocessing.md)
6. [Engineering report typography and generation](../../references/06-report.md)
7. [Troubleshooting and regression acceptance](../../references/07-troubleshooting.md)

Machine-readable input details are in `assets/reference/P1_input_audit.json` through `P6_input_audit.json`. Copy and parse the original files programmatically, including all 8,984 initial-stress records and nodal loads.

## 2. Execute the complete workflow

Resolve `SKILL_ROOT` to the actual installed folder. Scripts locate assets relative to themselves, independently of the working directory.

```bash
SKILL_ROOT=/absolute/path/to/catwalk-static-review
python3 -m venv "$SKILL_ROOT/.venv"
"$SKILL_ROOT/.venv/bin/python" -m pip install -r "$SKILL_ROOT/requirements.txt"
"$SKILL_ROOT/.venv/bin/python" "$SKILL_ROOT/scripts/run.py" --verify-only
"$SKILL_ROOT/.venv/bin/python" "$SKILL_ROOT/scripts/run.py" --out /absolute/path/to/new-run
```

To use an already downloaded, version-locked solver:

```bash
"$SKILL_ROOT/.venv/bin/python" "$SKILL_ROOT/scripts/run.py" \
  --solver /absolute/path/to/ccx \
  --out /absolute/path/to/new-run
```

Automatic solver download supports Linux x86_64. See reference 01 for Windows, dependencies and explicit solver variants. Select an absent or empty output directory.

The orchestration script performs these operations:

1. Verify every asset SHA256 and compare parsed input values against the audit snapshots.
2. Verify common geometry, elements, sections, initial stresses and boundaries across all six cases.
3. Build points and lines in Gmsh; call `setTransfiniteCurve(eid, 2)` and `generate(1)`; save MSH, GEO and tag mappings; verify coordinates and ordered connectivity.
4. Copy each complete INP to an independent case directory as `job.inp`; run CalculiX single-threaded with a default 600-second timeout per case.
5. Check solver completion, final step/time, node and integration-point coverage, and finite U/S values.
6. Recover signed cable forces; write nodal and element CSV, VTU and displacement/force/stress line contours.
7. Compare against benchmarks, calculate cable safety factors and check positive cable tension; generate the Word and PDF reports from those results.
8. Write `run.json`, comparison CSV/JSON and output SHA256 records; deliver the reports and complete evidence package.

## 3. Evaluate three acceptance criteria

- **Execution:** the solver finishes, every expected step reaches its final time and all required finite results are present.
- **Numerical regression:** peak displacement node matches the benchmark; absolute USUM difference is at most 1%; absolute span-force difference is at most 1.5%.
- **Cable safety factors:** calculate `K = Nbreak / Nmax` using the current run. Breaking forces are 38,080 kN for the bottom cable bundle and 14,280 kN for the portal cable bundle. Required K is 3.2 for P1, 2.7 for P2/P3/P4/P6 and 2.5 for P5.

Report these criteria separately. The regression tolerances define numerical agreement. The safety factors follow the engineering report. For P6, use Table 1-7's requirement of 2.7; record its difference from the 2.5 appearing in part of the original prose. The original output cards provide U and cable S; additional response quantities require their own output contract.

## 4. Stop conditions

Preserve all available evidence and mark the run unsuccessful when any of these occurs:

- An asset hash or expected count differs: 1,125 nodes, 1,194 elements or 8,984 initial-stress records.
- The input introduces external includes, unknown element types or card semantics outside the supplied parser's contract.
- Gmsh coordinates or ordered connectivity differ, tags are lost, or elements have the wrong order.
- The solver fails its version policy without an explicitly selected variant.
- `*ERROR` occurs, `Job finished` is absent, final time is incomplete or required output is missing.
- Final U and S belong to different times or steps.
- A recovered cable force is zero or negative, requiring review of the tension-carrying model.
- A numerical regression or cable safety criterion fails.

Keep failed cases visible in the result summary and report.

## 5. Deliverables

Deliver `catwalk_static_review.pdf`, `catwalk_static_review.docx`, `comparison.csv`, `summary.json`, `run.json` and `SHA256SUMS`, together with accessible P1–P6 inputs, solver logs, DAT/FRD/STA files, CSV, VTU, PNG and Gmsh mapping files.

Include the eight input-readback tables, evidence crops and input_readback.md in the delivery. In the final response, identify the cases actually executed; state the maximum displacement, bottom-cable and portal-cable differences; list any failed criteria; link the reports and data. Identify the model as the planar overall cable system. If only preparing the skill, state its preparation status and identify example results as the bundled validation run.

## 6. Derived models

For requested changes to mesh, sections, loading or spatial representation, create separate derived inputs and manifests while retaining the baseline. Gmsh `--subdivisions 2` generates a candidate refined mesh. Complete physical-card migration and the validation sequence in reference 03 before solving that candidate.

## 7. Fixed report typography

Use `scripts/report_style.py` and `assets/reference/report_style.json`: SimSun body text at 12 pt, SimHei headings, Times New Roman Latin text/numerals, and white, thin-rule four-span calculation tables. Embed the bundled fonts in PDF and Word. Preserve the approved Chinese engineering-report style when executing this English-language skill.
