# 07 Troubleshooting and regression acceptance

Diagnose in this order: file identity, physical definitions, solver execution, postprocessing.

## Wrong input version

A historical symptom is approximately 3 m upward P5 displacement near node 302. First verify SHA256. The packaged P5 hash is:

`3ba72d5d9c50561f6cdde3b17930d4668151d66a0ef7f10540aa59091320fc1f`

Its source is branch `feat/catwalk-ccx-20260826`, commit `ebd0e3d8eea740de6d2d4539feda51885d80e3f8`, in the model repository. Resolve the correct file before changing any physical parameter.

## Gmsh mismatch

Check mesh dimension, element order, entity merging and tag namespaces. The default result is 1,125 nodes and 1,194 first-order line elements with identical ordered connectivity. Restore this contract before continuing baseline execution.

## Solver startup failure

Check file existence, execute permission, platform binary format and native dependencies. Use WSL for the locked Linux ELF on Windows, or explicitly select a native solver variant and record its identity.

## Nonconvergence or singularity

Retain the first failed log/DAT/STA. Check initial stress, units, UY constraints, node identity, section assignment, B31 orientation and repeated loading. After verifying these, create a separate derived case if solution-control changes are needed; preserve the original input and identify each parameter set.

## Expected warnings

The first STATIC step uses default parameters (1, 1). P3/P6 clip the N_THERM range beyond existing nodes. Record both messages. Read every additional warning and diagnose its cause.

## P3/P6 version sensitivity

Check EXPANSION, initial temperature, final N_MCT temperature, N_THERM membership, solver version and final output time. Expanded-element temperature handling can vary between solver builds; quantify the resulting response difference with unchanged physical properties.

## Correct forces but wrong displacements

Check final-step selection, USUM versus UZ and the original-node peak search domain. Compare DAT times with STA. Use the original 1,125 nodes for comparison with the displacement benchmark.

## Large cable-force difference

Check stress-component order, units, area, deformed chord direction, cable family and span group. Recover signed axial stress with all six tensor components. Match T3D2 results to the cable sets.

## Bundled validation values for diagnosis

| Case | Approximate USUM / mm | Peak node |
|---|---:|---:|
| P1 | 42.259 | 304 |
| P2 | 2662.041 | 1176 |
| P3 | 1897.223 | 1176 |
| P4 | 2846.280 | 1176 |
| P5 | 1325.314 | 306 |
| P6 | 927.260 | 1166 |

The bundled run's maximum absolute differences are approximately 0.86% for displacement, 0.85% for bottom-cable force and 1.13% for portal-cable force. Recompute these metrics from each new run.

## Tests and reproducibility

Run `python -m unittest discover -s tests -v` for the input-contract and tensor-projection checks. Run `scripts/run.py` for complete six-case execution.

Evaluate asset identity, mesh equivalence, solver completion and DAT completeness before numerical regression and cable safety factors. Present each acceptance category in the report.

Use normal Python execution. The scripts rely on internal assertions; the entry point rejects optimized `python -O` execution.
