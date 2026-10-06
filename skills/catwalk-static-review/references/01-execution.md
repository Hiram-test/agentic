# 01 Installation, file contracts and execution

## Package layout

- `assets/inputs/`: six original UTF-8 INP files, approximately 1 MB each. P1 has one step; P2–P6 have two.
- `assets/reference/original_review_0324.pdf`: the original 118-page report.
- `assets/reference/original_review_text.txt`: text indexed by physical PDF page.
- `assets/reference/manifest.json`: source repository, branch, fixed commit and input hashes.
- `assets/reference/span_groups.json`: eight cable-span element sets extracted from the source MCT model.
- `assets/reference/benchmarks.json`: report cable forces and independently sourced MAPDL displacements, with provenance.
- `assets/reference/P*_input_audit.json`: materials, sections, boundaries, mass, stepwise nodal-load resultants and moments, temperatures and initial-stress counts.
- `assets/integrity.json`: asset hashes, including the source PDF.
- `scripts/model.py`: input parsing, audit, DAT reading and axial-force recovery.
- `scripts/mesh_gmsh.py`: Gmsh geometry/mesh generation and tag mapping.
- `scripts/postprocess.py`: completeness checks, comparisons, contours and VTU.
- `scripts/report.py`: Chinese DOCX and PDF generation from the same results.
- `scripts/run.py`: complete orchestration, using the bundled files.

## Dependencies

Use Python 3.11 or 3.12. The example `run.json` records the actual validation environment. Install the pinned gmsh, numpy, matplotlib, python-docx and reportlab versions in `requirements.txt`. ReportLab generates PDF directly; Word can update the DOCX table-of-contents field.

The Gmsh Python package loads a native library. If Linux reports `libGLU.so.1` missing, install `libglu1-mesa`, for example with `apt-get install libglu1-mesa`. Verify with `python -c "import gmsh; print(gmsh.__version__)"`. The workflow uses the headless API.

## Linux execution

```bash
SKILL_ROOT=/absolute/path/to/catwalk-static-review
python3 -m venv "$SKILL_ROOT/.venv"
"$SKILL_ROOT/.venv/bin/python" -m pip install -r "$SKILL_ROOT/requirements.txt"
"$SKILL_ROOT/.venv/bin/python" "$SKILL_ROOT/scripts/run.py" --verify-only
"$SKILL_ROOT/.venv/bin/python" "$SKILL_ROOT/scripts/run.py" --out /absolute/path/to/run-001
```

Without `--solver`, Linux x86_64 downloads:

`https://github.com/Hiram-test/model/releases/download/c3-ft14-parser-safe-667c5047/ccx-2.23-UCOR6-UCAB3-FT14-linux-x86_64`

Required SHA256:

`b498dad80b0415d53ab112409adc85b8a1fd19eb7846dc31e778f4c83b437a0e`

For offline use, pass an existing executable with the same hash using `--solver /path/to/ccx`. Check native dependencies with `ldd /path/to/ccx` when necessary.

## Windows PowerShell

Prefer WSL2 to execute the locked Linux binary. For an explicitly selected native Windows solver:

```powershell
$SkillRoot = 'C:\work\catwalk-static-review'
py -3.12 -m venv "$SkillRoot\.venv"
& "$SkillRoot\.venv\Scripts\python.exe" -m pip install -r "$SkillRoot\requirements.txt"
& "$SkillRoot\.venv\Scripts\python.exe" "$SkillRoot\scripts\run.py" --verify-only
& "$SkillRoot\.venv\Scripts\python.exe" "$SkillRoot\scripts\run.py" `
  --solver 'C:\CalculiX\ccx.exe' --allow-solver-variant `
  --out 'C:\work\runs\run-001'
```

`--allow-solver-variant` accepts a supplied solver's different hash while retaining input, convergence and result checks. Record the executable hash/version and repeat all six comparisons. Use the same procedure with a compatible macOS binary. The bundled validation evidence was generated on Linux.

## Completion and failure

The per-case timeout is 600 seconds; increase it on slower hardware with `--timeout 1800`. Choose a new output directory for a retry and retain the failed run's files. The orchestrator records failures in `run.json` once an output directory exists; preflight failures can occur before directory creation.

A normal output contains P1–P6 case directories, `mesh/`, `run.json`, `summary.json`, `comparison.csv`, both reports and `SHA256SUMS`. Successful acceptance returns exit code 0. A comparison or safety-factor failure is reported with its actual values and a nonzero exit code.

Check all of these:

1. Solver exit code 0 and `Job finished` in the log.
2. Absence of `*ERROR` in `solver.log`.
3. Final STA step/time: step 1 / total time 1 for P1; step 2 / total time 2 for P2–P6. Each final step-local time is 1.
4. Matching final DAT displacement/stress times equal to the expected total time.
5. U for all 1,125 original nodes and S at eight integration points of each of 1,123 cable elements.
6. Finite values, near-zero UY, positive cable tension, accepted benchmark differences and cable safety factors.

## AI-assistant integration

Install the entire folder in the host's supported skill location, for example `skills/catwalk-static-review/` under BridgeMind. Preserve relative paths and use the host's documented discovery mechanism. Have the assistant read SKILL.md, run `--verify-only`, then run the complete workflow.

The assistant selects tools and explains recorded evidence; CalculiX computes the numerical solution. The scripts operate independently of an LLM account. Keep model-provider credentials in the host configuration. For a GLM-driven session, record the actual provider, model identifier and tool-call log in that session's evidence.
