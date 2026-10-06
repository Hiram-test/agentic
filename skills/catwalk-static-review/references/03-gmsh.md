# 03 Gmsh API, tag mapping and mesh refinement

## Default meshing contract

Reconstruct the original line geometry in Gmsh and generate the identical first-order, one-dimensional mesh. Verify topology and coordinates, then solve the complete original INP with its physical cards. This preserves the association of every node and element with its initial stress, loading, support and reporting group.

## API sequence

```python
import gmsh
gmsh.initialize()
gmsh.model.add('catwalk_static')
# nodes: {original_node_id: [X, Y, Z]}, in mm
for nid, xyz in nodes.items():
    gmsh.model.geo.addPoint(*xyz, 0, nid)
# elements: {original_element_id: {'nodes': [start_id, end_id], ...}}
for eid, el in elements.items():
    gmsh.model.geo.addLine(*el['nodes'], eid)
gmsh.model.geo.synchronize()
for eid in elements:
    gmsh.model.mesh.setTransfiniteCurve(eid, 2)
# Create a 1D physical group for each E_SEC1/E_SEC2/E_SEC3 line set:
# gmsh.model.addPhysicalGroup(1, element_ids, physical_id)
# gmsh.model.setPhysicalName(1, physical_id, 'E_SEC1')
gmsh.option.setNumber('Mesh.ElementOrder', 1)
gmsh.option.setNumber('Mesh.MshFileVersion', 4.1)
gmsh.model.mesh.generate(1)
gmsh.write('catwalk.msh')
gmsh.finalize()
```

Execute the complete implementation in `scripts/mesh_gmsh.py`. The planar structural system consists of line members, so mesh dimension is 1.

## Tag mapping and verification

Treat geometric point tags, mesh-node tags and INP node IDs as separate namespaces. Likewise distinguish geometric line tags, mesh-element tags and INP element IDs.

For each geometric point, `getNodes(0, nid)` identifies its unique mesh node. Build `gmsh_node_to_inp_node`. For each line, `getElements(1, eid)` identifies its mesh elements. Build `inp_element_to_gmsh_elements`.

With two nodes per original curve, require:

- 1,125 mesh nodes and 1,194 first-order line elements, Gmsh element type 1.
- Coordinate error at each original node at most 1e-7 mm.
- Each mapped element's endpoints matching the original ordered INP connectivity.
- Preservation of separate topological nodes even when their coordinates coincide.
- Physical groups matching the section sets, with all material/load/support definitions retained in the complete INP.

Keep geometric entities separate throughout this operation; node deduplication and Boolean merging would change the topology contract.

Outputs: `mesh/catwalk.msh`, `catwalk.geo_unrolled` and `mesh_map.json`. The mapping records the Gmsh version, tag associations, coordinate error and eligibility for baseline reproduction.

```bash
python scripts/mesh_gmsh.py --inp assets/inputs/migrate_P1.inp --out /new/mesh
```

## Candidate refinement

```bash
python scripts/mesh_gmsh.py --inp assets/inputs/migrate_P1.inp --out /new/refined-mesh --subdivisions 2
```

This splits each original line into two elements and marks the output `refined_mesh_is_unsolved_candidate=true`. Original nodes remain. New nodes/elements require physical-card migration before analysis.

For a requested refinement study, implement a derived-INP converter with this sequence:

1. Preserve anchors, corners, loading points, portal nodes and coincident but topologically distinct points. Save parent/child node and element mappings.
2. Inherit material, section and B31 orientation for every child element.
3. Transfer initial stress to child integration points using the parent physical state and appropriate global tensor direction/measure.
4. Keep original point loads at their physical locations. If re-discretizing a distributed load, integrate the original line load over the new mesh.
5. Verify total force and moment about the same global origin for every step, including the permanent-load contribution in second-step totals.
6. Transfer gravity, temperature sets and internal expanded-element temperature behavior. Apply supports to new nodes according to physical constraints.
7. Extend N_MCT, cable stress output and all eight span groups to include their child entities.
8. Write a separate manifest/audit; verify dead-load equilibrium, reactions and six-case response; compare displacement and cable force for 1/2/4 subdivisions.

The supplied default execution uses one element per original line. The refinement option supplies the geometric candidate for the conversion sequence above.
