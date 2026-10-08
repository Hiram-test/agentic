# 08 Drawing-to-model input contract

## Contents

1. Source set and reading order
2. Component scope
3. Eight fixed tables
4. Weight calculations and assignment
5. Report and INP checkpoints
6. Completion and hand-off

## 1. Source set and reading order

Use this contract with all three versions of the catwalk static review skill. Keep the component scope, table columns, units and numerical checks identical. V1 groups the work into six stages, V2 into eighteen operations, and V3 into thirty-six actions.

Read `assets/reference/original_review_0324.pdf` and the six inputs listed in `assets/reference/manifest.json`. Their identity is fixed by `assets/integrity.json`. Register the construction drawings actually supplied for the task. The report identifies the December 2025 construction drawings, January 2026 load/control-point files and January 2026 calculation confirmation sheet in Section 1.2. Read those files when supplied; give each its own source ID.

Use physical PDF page numbers, starting at 1. Read the report in this order:

| Order | Pages | Read for |
|---|---|---|
| 1 | 4-5, Figures 1-2 to 1-4 | Four-span catwalk arrangement, two walkways, cross passages, standard section and source-document identities |
| 2 | 6, Section 1.4 | Rope types, metallic areas, elastic modulus, steel grades and mesh specifications |
| 3 | 7, Tables 1-1 and 1-2 | Distributed and concentrated weights carried by the bottom ropes |
| 4 | 8, Tables 1-3 and 1-4 and Sections 1.5.2-1.5.4 | Portal-rope weights, construction actions, temperature changes and wind-speed definitions |
| 5 | 9-10, Tables 1-5 and 1-6, Figures 2-1 and 2-2 | Named control points, cable geometry, supports and model idealization |
| 6 | 11, Table 1-7 | Six combinations and their safety-factor requirements |
| 7 | 11-29 and 33-38 | Empty-cable, formed-cable and unstressed-length result tables, used as comparison data |
| 8 | 30 and 39, Tables 1-11 and 1-14 | Cable-force comparison values |

Read the corresponding drawing views in the same order: general arrangement -> longitudinal profile -> standard cross-section -> rope and portal details -> deck/handrail details -> cross-passage and concentrated-equipment layout -> anchorage/saddle/down-pull details -> material and quantity schedules. Read only the views and schedule rows needed by Section 2.

Use native CAD/PDF text, dimensions and table cells first. Render each used view and visually confirm its labels, units and attachment relationships. For a scanned view, retain the OCR text and a crop for each accepted dimension, quantity or material value. Obtain engineering dimensions from labels or a calibrated view. Store a measured dimension separately from a printed dimension.

## 2. Component scope

Interpret the input as one equivalent longitudinal catwalk system. The report describes two walkways 42.9 m apart and a clear walkway width of 5.6 m. Record those dimensions to interpret counts, widths and shared weights. Use the actual INP topology for the analysis.

Read the following physical families. Expand a family into individual locations whenever station, section, quantity, support relation or load assignment changes.

| ID | Physical family to read | Required drawing properties | Representation in the current INP |
|---|---|---|---|
| C01 | Conventional bottom carrying ropes | 15 ropes plus the separately listed smart-core rope; diameter, construction, metallic area, modulus, strength, unit mass, end/control-point coordinates | Part of `E_SEC1`, `MAT1`, `T3D2` |
| C02 | Smart-core bottom carrying rope | One rope; its own metallic area, construction, unit mass and position in the bundle | Combined with C01 in `E_SEC1`; retain its separate physical row |
| C03 | Portal carrying ropes | Six ropes; diameter, metallic area, modulus, strength, unit mass, control points and end coordinates | `E_SEC2`, `MAT2`, `T3D2` |
| C04 | Bottom-rope down-pull branches | Cable route, two end points, anchorage point, connection to the main rope and physical section/quantity stated in the detail | `E_SEC1`; explicitly map elements 728 and 729 and their node pairs |
| F01 | Portal assemblies linking upper and lower rope systems | Portal stations, height, member layout, physical sections/materials, connections and assembly counts | `E_SEC3`, `MAT3`, 71 equivalent `B31` members; relate each equivalent member to its physical assembly |
| B01 | Cable anchorages | Named point, station/elevation, attached rope and restrained/free directions | Node coordinates and `*BOUNDARY` |
| B02 | Anchorage, tower-top and auxiliary-tower saddles | Turning/split points, station/elevation, attached segments and sliding/continuity condition | Node coordinates, connectivity and `*BOUNDARY` |
| B03 | Down-pull anchorages and cable attachment points | Location, connection partner and restraint at each end | Nodes 729/730 and connected rope nodes; distinguish fixed anchorage from cable attachment |
| D01 | Upper handrail ropes | Diameter 36 mm, count, unit mass, length basis and route | Bottom-system permanent weight |
| D02 | Middle and lower handrail ropes | Diameter 22 mm, count, unit mass, length basis and route | Bottom-system permanent weight |
| D03 | Timber treads | 50 x 30 x 2000 mm detail, number per station, spacing and unit mass or density | Bottom-system permanent weight |
| D04 | Upper walking mesh | Wire diameter, mesh openings, panel width, layers, areal mass and covered length | Bottom-system permanent weight |
| D05 | Lower supporting mesh | Wire diameter, mesh openings, panel width, layers, areal mass and covered length | Bottom-system permanent weight |
| D06 | Side/handrail mesh | Wire diameter, openings, panel height, sides/layers and areal mass | Bottom-system permanent weight |
| D07 | Small crossbeams | 50 x 50 x 4 section specification, member length, unit/piece mass, spacing and quantity | Bottom-system permanent weight |
| D08 | Cables and lighting | Installed length, unit mass and any tabulated longitudinal allowance | Bottom-system permanent weight |
| D09 | Distribution boxes | Piece mass, number and stations, or the stated longitudinal allowance | Bottom-system permanent weight |
| P01 | Large crossbeams | 100 x 100 x 4 section specification, piece mass, quantity and stations | Concentrated bottom-system weight |
| P02 | Portal crossbeams | H175 x 175 x 8 x 12 section, piece mass, quantity and stations | Concentrated bottom-system weight |
| P03 | PWS rollers | Unit mass, rollers per assembly, assembly stations and supporting member | Concentrated bottom-system weight |
| P04 | Transverse cross passages | All 21 locations, assembly mass, two-walkway sharing and attachment locations | Each walkway's share of concentrated weight |
| P05 | Main-cable displacement restraints | Unit/assembly mass, number, stations and support path | Concentrated bottom-system weight |
| P06 | Main-tower displacement frames | Frame type, mass per assembly, quantity, side of tower and attachment points | Concentrated bottom-system weight |
| P07 | Auxiliary-tower displacement frames | Frame type, mass per assembly, quantity and attachment points | Concentrated bottom-system weight |
| P08 | Anchorage-front displacement frames | Frame type, mass per assembly, quantity and attachment points | Concentrated bottom-system weight |
| P09 | Ordinary portal assembly weight | Assembly mass/weight and ordinary-portal stations | Concentrated upper-system weight; weight aspect of F01 |
| P10 | Portal guide-wheel assemblies | Mass/weight, two-set definition, stations and supported system | Concentrated upper-system weight |
| P11 | Triangular portals at cross passages | Assembly mass/weight and cross-passage stations | Concentrated upper-system weight; alternative portal type at those stations |

For assemblies P04-P11, use the stated assembly mass and attachment locations. Expand their internal members only when needed to compute an absent assembly mass or to identify a connection. Read tower, main-cable and anchorage-body geometry only as reference coordinates or support interfaces. The model scope consists of the rope system, equivalent portals, supports and assigned weights listed above.

Keep the physical inventory distinct from the finite-element inventory. An equivalent `B31` is a model member, while a portal assembly may contain several physical members. Count physical items from their layouts and schedules and count finite elements from `*ELEMENT`.

## 3. Eight fixed tables

Write eight UTF-8 CSV tables in `INPUT_READBACK_DIR`. Preserve the following column names and order; use one header row, decimal-point numbers and quoted cells for commas/newlines. Use semicolons for lists within a cell. Leave an unprovided numeric value empty and set `check` to `source_required`, identifying the field in `note`. Use `matched`, `difference_recorded` or `source_required` for `check` throughout.

Create `input_readback.md` from the same rows, with tables T01-T08 in this order and the same English captions. Break wide tables into consecutive panels by column group for readable display. Keep complete columns in CSV.

Use stable IDs: `SRC-...`, `CP-...`, the family IDs above plus a location suffix, `MAT-...`, `SEC-...`, `DW-...`, `PW-...`, `MAP-...` and `ACT-...`. A source locator has the form `SRC-RPT:p7:Table1-1:row6`, `SRC-DWG-03:sheet2:viewB:crop17` or `SRC-P1:L2422:SOLID_SECTION:E_SEC1`. Store drawing revision and a file hash in T01. Place supporting crops in `evidence/` and reference them through source locators.

### T01 - Source and view register (`01_sources.csv`)

One row per source view, table or INP block used.

```text
source_id,file_name,sha256,source_type,revision,page_or_sheet,view_or_table,scale,length_unit,weight_unit,coordinate_datum,locator,evidence_path,check,note
```

`source_type` is `drawing`, `report`, `inp` or `confirmation`. Record the actual revision string; use `not_stated` for unprinted scale/datum fields. Each supplied drawing page may have several view rows. Include the six INP hashes even when their geometry is common. For a cited file that has not been supplied, register its title with an empty hash and locator and check=source_required; populate these fields after receiving the file.

### T02 - Control points and supports (`02_control_points.csv`)

One row per named point per source and state. Reuse `point_id` across its drawing, report and INP rows.

```text
point_id,system,point_role,state,station_text,station_m,x_m,y_m,z_m,coordinate_transform,inp_node_id,ux,uy,uz,rx,ry,rz,source_refs,check,note
```

`system`: `bottom`, `portal` or `reference`. `point_role`: `anchor`, `saddle`, `downpull_anchor`, `downpull_attachment`, `span_control` or `reference_point`. `state`: `specified_formed`, `reported_empty`, `reported_formed`, `inp_reference` or an explicit calculated case/step. Use `fixed`, `free`, `not_defined` for model DOFs and the actual detail wording for physical support rows. Populate all eight state/support attributes from evidence. In particular, a midspan geometry target is a control point, while a restrained node is a support.

Convert `Kaa+bbb.bbb` to station metres as `1000*aa + bbb.bbb`. For the locked input, test `station_m = x_mm/1000 + 16000` at the lower north anchorage and two tower points before applying it elsewhere. Retain raw stations and source precision. Pair points by identity, connected cable, role and neighbouring order; then compare coordinates.

### T03 - Physical component inventory (`03_components.csv`)

One row per homogeneous physical group or localized assembly.

```text
component_id,family_id,component_name,system,span,station_start_m,station_end_m,station_m,quantity,quantity_basis,spacing_m,length_m,width_or_height_m,material_id,section_id,attachment_ids,representation,inp_refs,source_refs,check,note
```

`quantity_basis` states `per_walkway`, `both_walkways`, `per_assembly`, `per_station` or `per_length`. `representation` is `cable_element`, `equivalent_beam`, `distributed_weight`, `point_weight` or `support_interface`. Record handedness/side in `note` when relevant. Reference the weight ledger for the mass of a structural assembly; retain one physical assembly identity.

### T04 - Material, section and model properties (`04_properties.csv`)

One row per property per source, grouped by `property_id`. Compare sources by their common property ID.

```text
property_id,entity_id,property_name,source_role,raw_value,raw_unit,value,unit,basis,used_by,source_refs,check,note
```

`source_role` is `drawing`, `report`, `inp` or `derived`. `basis` distinguishes `physical_single_rope`, `physical_bundle`, `physical_member`, `physical_assembly` and `model_equivalent`. `used_by` is `weight_inventory`, `geometry`, `stiffness`, `resistance` or `comparison`.

Use rows for rope diameter/construction/metallic area/count/modulus/strength/breaking force/unit mass; member dimensions/area/second moments/material; mesh wire diameter/openings/areal mass; and actual INP modulus/Poisson ratio/density/expansion/section dimensions/orientation. Keep a rope's metallic area separate from its nominal circular envelope area. Keep INP effective density separate from material density and measured unit mass.

Example record group:

| property_id | source_role | value | unit | basis | source_refs |
|---|---|---:|---|---|---|
| A-BOTTOM | derived | 22298.75 | mm2 | physical_bundle | Report p6; bottom-rope count in Table 1-1 |
| A-BOTTOM | inp | 22298.692 | mm2 | model_equivalent | P1 `SOLID SECTION`, `E_SEC1` |

### T05 - Distributed permanent weights (`05_distributed_weights.csv`)

One row per physical contribution per uniform loaded interval, including rope self-weight. Record the contribution exactly once.

```text
weight_id,component_id,system,station_start_m,station_end_m,length_basis,quantity,quantity_basis,unit_mass_kg_per_m,areal_mass_kg_per_m2,piece_mass_kg,spacing_m,covered_width_m,sharing_factor,mass_kg_per_m,gravity_m_per_s2,q_kN_per_m,formula,report_q_kN_per_m,inp_weight_representation,source_refs,check,note
```

`length_basis` is `rope_arc`, `catwalk_arc` or `horizontal_projection`, taken from the load definition. `inp_weight_representation` identifies `MAT1_DLOAD`, `MAT2_DLOAD`, `MAT3_DLOAD` or the assigned `CLOAD` group. Where only an aggregate assignment is documented, name that aggregate and record the physical contribution's amount without inventing a finer decomposition.

### T06 - Concentrated permanent weights (`06_point_weights.csv`)

One row per load-bearing location and assembly type.

```text
weight_id,component_id,system,station_m,x_m,y_m,z_m,piece_mass_kg,quantity,quantity_basis,sharing_factor,total_mass_kg,gravity_m_per_s2,P_kN,report_P_kN,recipient_node_ids,distribution_factors,formula,source_refs,check,note
```

Store mass and force in separate columns. Define whether a supplied mass is a full assembly, one walkway's share or a single set. For a located row with defined recipients, distribution factors must sum to 1. For a location awaiting a drawing, leave the coordinate, node and factor fields empty and set check=source_required. Use separate rows for ordinary and triangular portals at their respective stations and assign guide-wheel assemblies by the actual layout.

### T07 - Physical-to-INP correspondence (`07_model_mapping.csv`)

One row per physical group to model representation or per compared quantity. Add an aggregate row for each section and load group.

```text
mapping_id,component_ids,quantity_name,reference_role,compared_role,reference_value,compared_value,unit,difference,inp_file,step,keyword,inp_refs,reference_source_refs,compared_source_refs,assignment_basis,check,note
```

Set `difference = compared_value - reference_value` in the same units. Use `drawing`, `report`, `derived` or `inp` for the two source-role columns. For physical-to-model rows, put the physical value in reference_value and the INP value in compared_value with compared_role=inp. For a report-versus-calculated weight check, use reference_role=report and compared_role=derived and leave the INP fields empty. Preserve the actual numeric difference. Map bottom/upper ropes, down-pull branches, equivalent portal members, supports, gravity groups and nodal-load groups. Sum node/element contributions before comparing an aggregate. Use an explicit `assignment_basis` such as `section_membership`, `same_named_control_point`, `tributary_length` or `assembly_attachment`.

### T08 - Actions, states and combinations (`08_actions_states.csv`)

One row per case/step/action/recipient group and separate rows for documented geometry-state relationships.

```text
action_id,case_id,step_id,state_label,action_type,component_action_ids,recipient_system,value,unit,direction,application_basis,initial_state_ref,geometry_target_ref,inp_keyword,inp_refs,source_refs,check,note
```

`action_type` covers `permanent`, `construction`, `temperature`, `wind`, `initial_stress`, `geometry_state` and `combined_total`. Use combined_total for a case/step CLOAD resultant already containing several actions; link its known constituent rows in component_action_ids, and record its exact source block. Use a separate row for each force direction. Link permanent actions to T05/T06. Read construction actions from Table 1-4 and Section 1.5.2, temperature and wind definitions from p8, combinations from Table 1-7, and actual loads from each INP step. Preserve the initial-stress tensor records by reference to their source block and hash.

Record the report's named formed targets, reported empty profile, input reference geometry and solved P1 state as distinct states. Enter a relationship in `geometry_target_ref` only when a source explicitly supplies it. Numerical agreement is recorded as a comparison in T07. For an unstated state relationship, retain the two source labels and use `source_required` for that relationship alone.

## 4. Weight calculations and assignment

Use actual piece masses, areal masses and unit masses from the drawings, report and schedules. Use `g = 9.806 m/s2` when comparing with the locked INP's `GRAV, 9806` in mm/s2. Preserve printed report force values and their rounding independently.

| Contribution | Calculation |
|---|---|
| Parallel ropes | `mass_per_length = rope_count * unit_rope_mass` |
| Mesh | `mass_per_length = areal_mass * covered_width_or_height * layer_or_side_count` |
| Repeating treads or crossbeams | `mass_per_length = piece_mass * pieces_at_station / station_spacing` |
| Weight from a known steel section | `piece_mass = physical_density * physical_area * member_length`, using consistent SI units |
| Shared concentrated assembly | `P_kN = piece_mass_kg * quantity * sharing_factor * g / 1000` |
| Distributed gravity | `q_kN_per_m = mass_kg_per_m * g / 1000` |
| Element gravity in the INP | `W_N = rho_tonne_per_mm3 * A_mm2 * L_mm * 9806` |

If T1-2 already gives the half-cross-passage mass, use that half mass with `sharing_factor=1`. If a drawing gives the full mass, apply the documented half-share once. Apply the same distinction to the construction load from Table 1-4.

For a line load between two recipient nodes, use the load's stated length basis to integrate its resultant. Allocate uniform load by tributary length; split a point load between adjacent nodes by linear position weights when the load-transfer definition requires that interpolation. Verify total force and moment about the same origin before and after allocation. Record every load's recipient and active state.

Add all physical contributions independently. Compare their totals with both the report and the INP. Retain the INP's existing effective densities as model data; calculate the physical inventory from source quantities. Record any difference directly in T07. Attach permanent weights to one ledger entry and one model assignment so that density gravity and CLOAD totals can be reconciled.

## 5. Report and INP checkpoints

Use these as checks on extraction, with source values retained separately.

### Physical properties and weights

- Report p6: conventional rope diameter 50 mm, metallic area 1400.42 mm2, `E=120000 MPa`, strength grade 1960 MPa; smart-core rope area 1292.45 mm2. The physical bottom bundle gives `15*1400.42+1292.45=22298.75 mm2`; the six portal ropes give `8402.52 mm2`.
- T1-1 bottom-system masses in row order: `191.82, 10.84, 6.68, 6.48, 8.09, 31.07, 11.84, 10.06, 5.00, 0.05 kg/m`. Their printed sum is 281.93 kg/m. Preserve the printed total `2.766 kN/m` and the calculated conversion as separate values.
- T1-2 concentrated weights in row order: `1.32, 3.18, 1.21, 49.69, 14.72, 67.98, 59.70, 62.72 kN`; corresponding listed masses are `135.02, 324, 123, 5065, 1500, 6930, 6086, 6393 kg`. The roller row is two pieces at 61.50 kg each. The cross-passage row explicitly represents half an assembly.
- T1-3: portal-rope line load `0.709 kN/m`; ordinary portal `8.927 kN`; its two guide-wheel sets `9.196 kN`; triangular portal at a cross passage `12.360 kN`.
- Construction: bottom-system line load `0.521 kN/m`; cross-passage share `4.9 kN`; portal-rope traction line load `0.212 kN/m`. Record these as actions in T08, separately from permanent weights.
- Report p6 states lower mesh openings `50 x 75 mm`, while T1-1 prints `50 x 70 mm`. Record both source rows in T04 and the supplied construction detail's value in a third row. The source precision and discrepancy remain visible.

### Model identity

The locked P1-P6 input has 1,125 nodes and 1,194 elements: 729 `T3D2` in `E_SEC1`, 394 `T3D2` in `E_SEC2`, and 71 `B31` in `E_SEC3`. Every original node has UY fixed. The reference geometry lies in X-Z, with small floating-point Y residues. Preserve actual, non-contiguous IDs.

| Model set | Material | Section | E / MPa | Poisson ratio | INP density / tonne/mm3 |
|---|---|---|---:|---:|---:|
| E_SEC1 | MAT1 | 22298.692 mm2 | 120000 | 0.3 | 1.26484805e-08 |
| E_SEC2 | MAT2 | 8402.9797 mm2 | 120000 | 0.3 | 8.59881705e-09 |
| E_SEC3 | MAT3 | 98.954535 x 98.954535 mm rectangle | 206000 | 0.31 | 1.01978381e-17 |

The equivalent beam area is `9791.999997066227 mm2`, with orientation `(1,1,1)`. P3/P6 have `alpha=1.2e-5 /degC`. The report p10 calls the original portal idealization a truss; the current INP uses `B31`. Record both descriptions with their sources. Read the actual B31 definition for reproduction.

`E_SEC1` elements 728 and 729 connect nodes `(729,160)` and `(444,730)`. Include their self-weight and their two down-pull anchorages in the mapping. The input contains 8,984 initial-stress records on 1,123 cable elements; initial stress is carried by those records, with element and integration-point identity.

### Geometry and load checks

- T1-5 prints the bottom midspan station as `K19+836.000`, elevation 113.3 m. The named bottom midspan in the current input is node 302 at `x=2686000 mm`, or `K18+686.000` under the checked station transform. Preserve both rows and their difference. Read the drawing/confirmation sheet to establish the design value.
- T1-6 identifies the portal midspan at `K18+686.000`, elevation 121.300 m; the input node 1173 has `x=2686008.5 mm`, `z=121300 mm`. Preserve this coordinate precision.
- Compare all named anchors/saddles and down-pull attachments individually. Geometry control points and model restraint lists have different roles.
- First-step CLOAD sums for every input are `(0,0,-4725567.874) N`, excluding gravity. Final P2/P3/P6 CLOAD sums are `(0,0,-8069828.486) N`; P4 gives `(0,2246926.048,-8312299.4553) N`; P5 gives `(0,15303735.373,-6377029.291) N`.
- P1 has one step. P2-P6 each have a dead-load step followed by the final total combination. Their final CLOAD includes permanent nodal loads. Retain step identity, OP behavior, directions and temperature records when comparing loads.
- Keep report result tables as comparison data. Read physical sections, quantities and mass schedules for the physical input ledger; read the supplied INP for the executed model and its initial state.

## 6. Completion and hand-off

Finish T01-T08, the evidence crops and `input_readback.md` before entering the existing numerical workflow. Record populated rows, remaining `source_required` cells and every numerical difference by table/row ID. Use factual entries such as `report=50x75 mm; Table1-1=50x70 mm; drawing_detail=...`.

The hand-off consists of the eight tables, their Markdown rendering, source hashes, crops, preserved INP hashes and the component-to-model map. The existing `run.py` reads the locked INP assets; the eight tables document the readback and comparison. Incorporate a requested physical-model revision through the existing derived-model route and give its revised input a separate identity.

Keep `INPUT_READBACK_DIR` separate from the new/empty `SOLVER_RUN_DIR`. Attach the completed readback to the solver delivery after calculation. In the report, place the corresponding summaries with materials, loads, control points and model definition. Use the existing Chinese terminology and typography from reference 06 for the engineering report; write the skills and their input-table captions in English.
