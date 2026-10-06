# Catwalk static verification skill

Start with [SKILL.md](SKILL.md). The self-contained package includes seven detailed execution references, Python scripts, six verified INP files, the original 118-page engineering report and machine-readable benchmarks.

The bundled validation run completed P1–P6 with CalculiX. Gmsh reproduced 1,125 nodes and 1,194 line elements with identical coordinates and connectivity. Maximum absolute differences were 0.860% for displacement, 0.854% for bottom-cable force and 1.126% for portal-cable force.

Examples: [17-page PDF](examples/catwalk_static_review.pdf), [Word report](examples/catwalk_static_review.docx), [complete validation evidence](examples/validated-run.zip).

```bash
python -m pip install -r requirements.txt
python scripts/run.py --verify-only
python scripts/run.py --out /absolute/path/to/new-run
```

Automatic solver download supports Linux x86_64. See [execution instructions](references/01-execution.md) for offline and Windows use. The folder is relocatable and carries its own inputs and references.

Contract tests: `python -m unittest discover -s tests -v`.
Rebuild a completed run's report: `python scripts/rebuild_report.py --run /path/to/completed-run`.

Version 1.2.0 provides English skill instructions and technical references. Numerical inputs, executable scripts, benchmark results and the approved Chinese report typography retain the version 1.1.0 definitions. Mesh refinement follows the migration procedure in [reference 03](references/03-gmsh.md).
