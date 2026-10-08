---
name: catwalk-static-review-coarse
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

## Fixed sequence - V1 (6 stages)

### 01. Identify sources and the executed model

Register the drawings, the original report, confirmation sheets and locked P1-P6 inputs in T01. Read the report and corresponding drawing views in the order in reference 08. Parse the actual INP definitions with scripts/model.py; check hashes, node/element families, materials, sections and stages against the stored input audits. Output the source register and the model-side starting records for T04/T07/T08.

### 02. Read geometry, control points and supports

Establish station units and the input coordinate transform. Read bottom and portal control points, main and auxiliary tower saddles, anchorages and both down-pull branches. Separate control targets, fixed supports and state labels. Map each point to its node and connected segments, preserving printed coordinates and input coordinates in separate T02 rows. Output the complete named-point and boundary map.

### 03. Read physical components and properties

Read only the structural and weight-carrying families listed in reference 08. Record quantities and physical properties for the conventional/smart-core bottom ropes, upper ropes, portal assemblies, deck and handrail parts, crossbeams, cross passages and equipment. Populate T03/T04 with member or assembly basis, source references and the equivalent-model correspondence. Output an inventory that distinguishes physical pieces from finite elements.

### 04. Calculate permanent weights and assign them

Calculate distributed and concentrated weights from unit masses, panel areas, repetition intervals and located assemblies. Apply each walkway share once. Use the documented arc-length or projected-length basis. Populate T05/T06 and map every contribution to the existing density/gravity or nodal-load representation. Check assigned force and moment totals. Output the complete physical weight ledger and its model mapping.

### 05. Read actions and reconcile the inputs

Read construction, temperature and wind actions and the six combinations into T08. Record initial-stress blocks and geometry states explicitly. Compare areas, member definitions, coordinates, supports and weight/load totals in T07. Preserve report, drawing and input values, including the documented mesh and midspan-station differences. Output the reconciled tables with numerical differences and exact source locators.

### 06. Complete the readback and execute the review

Finish T01-T08 and input_readback.md, attach evidence crops and verify the source/input hashes. Then follow Sections 1-7 below: verify assets, generate the equivalent Gmsh mesh, run the locked inputs with CalculiX, validate results, recover cable forces and generate the existing Chinese engineering report. Include the input-readback package in the final delivery. Output the same complete review as V2 and V3.

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
