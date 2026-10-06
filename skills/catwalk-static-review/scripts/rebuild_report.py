"""Rebuild formatting only from a completed run; no solver rerun, no editing numeric results."""
import argparse,json
from pathlib import Path
from run import verify
from model import sha
from report import generate
p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);a=p.parse_args();out=a.run.resolve()
# Require completed source and unchanged input/raw data/summary via the prior output manifest.
for line in (out/'SHA256SUMS').read_text().splitlines():
    digest,name=line.split('  ',1)
    if name.endswith(('.docx','.pdf')):continue
    if sha(out/name)!=digest:raise RuntimeError(f'Output evidence changed: {name}')
models,audits,groups=verify();record=json.loads((out/'run.json').read_text());rows=json.loads((out/'summary.json').read_text())
assert record['status']=='completed'
for k,m in models.items():assert sha(out/k/'job.inp')==m['sha256']
root=Path(__file__).resolve().parents[1];bench=json.loads((root/'assets/reference/benchmarks.json').read_text())['cases']
generate(out,record,models,rows,bench)
(out/'SHA256SUMS').write_text(''.join(f'{sha(f)}  {f.relative_to(out).as_posix()}\n' for f in sorted(out.rglob('*')) if f.is_file() and f.name!='SHA256SUMS'),encoding='utf-8')
print('Rebuilt DOCX/PDF and refreshed output hashes:',out)
