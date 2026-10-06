#!/usr/bin/env python3
"""End-to-end locked six-case static reproduction: verify -> mesh -> solve -> plot -> report."""
import argparse,json,os,platform,shutil,subprocess,sys,urllib.request
from pathlib import Path
from datetime import datetime,timezone
from model import parse,audit,sha,dump
ROOT=Path(__file__).resolve().parents[1]
SOLVER_SHA='b498dad80b0415d53ab112409adc85b8a1fd19eb7846dc31e778f4c83b437a0e'
SOLVER_URL='https://github.com/Hiram-test/model/releases/download/c3-ft14-parser-safe-667c5047/ccx-2.23-UCOR6-UCAB3-FT14-linux-x86_64'

def verify():
    integrity=json.loads((ROOT/'assets/integrity.json').read_text())
    for path,expected in integrity.items():
        actual=sha(ROOT/path)
        if actual!=expected:raise ValueError(f'Asset changed: {path}: {actual} != {expected}')
    manifest=json.loads((ROOT/'assets/reference/manifest.json').read_text())
    models={};audits={}
    for entry in manifest['inputs']:
        k=entry['case'];path=ROOT/'assets'/entry['path']
        assert sha(path)==entry['sha256'],f'Wrong version {path}'
        m=parse(path);a=audit(m)
        assert a==json.loads((ROOT/f'assets/reference/{k}_input_audit.json').read_text()),f'Audit mismatch {k}'
        assert a['node_count']==1125 and a['element_types']=={'T3D2':1123,'B31':71}
        assert a['all_UY_fixed'] and a['prestress_ip_count']==8984
        assert all(s['nlgeom'] for s in a['steps'])
        assert len(m['steps'])==(1 if k=='P1' else 2)
        models[k]=m;audits[k]=a
    # A single Gmsh check covers all six only if their topology/geometry is identical.
    for k,m in models.items():
        for prop in ('nodes','elements','sections','boundary','initial_stress'):
            assert m[prop]==models['P1'][prop],f'Geometry/section/prestress differs at {k}:{prop}'
    groups=json.loads((ROOT/'assets/reference/span_groups.json').read_text())['groups']
    for name,ids in groups.items():
        assert len(ids)==len(set(ids)) and all(e in models['P1']['elements'] for e in ids)
        sec='E_SEC2' if name.startswith('门架索') else 'E_SEC1'
        assert all(models['P1']['elements'][e]['section']==sec for e in ids)
    return models,audits,groups

def get_solver(args,out):
    if args.solver:p=Path(args.solver).expanduser().resolve()
    else:
        if platform.system()!='Linux' or platform.machine() not in ('x86_64','AMD64'):
            raise RuntimeError('Automatic solver download supports Linux x86_64 only. Supply --solver and explicitly --allow-solver-variant on other systems.')
        p=out/'solver/ccx';p.parent.mkdir();urllib.request.urlretrieve(SOLVER_URL,p);p.chmod(0o755)
    if not p.is_file():raise FileNotFoundError(p)
    digest=sha(p)
    if digest!=SOLVER_SHA and not args.allow_solver_variant:
        raise RuntimeError('Solver hash differs; choose the locked solver, or explicitly request a variant run with --allow-solver-variant')
    return p,digest

def main():
    if sys.flags.optimize: raise RuntimeError('Do not run with Python -O: integrity assertions must remain enabled')
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',type=Path,help='New/empty run directory; never overwrite a previous run')
    ap.add_argument('--solver',help='CalculiX executable; otherwise download locked Linux solver')
    ap.add_argument('--allow-solver-variant',action='store_true')
    ap.add_argument('--verify-only',action='store_true');ap.add_argument('--timeout',type=int,default=600)
    args=ap.parse_args();models,audits,groups=verify();print('All six inputs and reference assets verified.',flush=True)
    if args.verify_only:return
    if args.out is None:ap.error('--out is required for a run')
    out=args.out.expanduser().resolve()
    if out.exists() and any(out.iterdir()):raise RuntimeError('Output directory is not empty. Choose a new directory.')
    out.mkdir(parents=True,exist_ok=True)
    start=datetime.now(timezone.utc)
    run={'run_id':start.strftime('%Y%m%dT%H%M%SZ'),'started_utc':start.isoformat(),'status':'running',
         'python':sys.version,'platform':platform.platform(),'audits':audits,'executions':[],
         'original_pdf_sha256':sha(ROOT/'assets/reference/original_review_0324.pdf')}
    dump(out/'run.json',run)
    try:
        from mesh_gmsh import mesh
        from postprocess import process,write_csv
        from report import generate
        solver,digest=get_solver(args,out);run.update(solver_path=str(solver),solver_sha256=digest,solver_variant=digest!=SOLVER_SHA)
        run['mesh']=mesh(ROOT/'assets/inputs/migrate_P1.inp',out/'mesh')
        assert run['mesh']['connectivity_identical']
        bench=json.loads((ROOT/'assets/reference/benchmarks.json').read_text())['cases'];rows=[]
        for case,m in models.items():
            folder=out/case;folder.mkdir();shutil.copyfile(ROOT/f'assets/inputs/migrate_{case}.inp',folder/'job.inp')
            assert sha(folder/'job.inp')==m['sha256'];dump(folder/'input_audit.json',audits[case])
            cmd=[str(solver),'-i','job'];print('Solving',case,flush=True)
            t0=datetime.now(timezone.utc)
            with (folder/'solver.log').open('w') as log:
                p=subprocess.run(cmd,cwd=folder,stdout=log,stderr=subprocess.STDOUT,
                    env={**os.environ,'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1'},timeout=args.timeout)
            log=(folder/'solver.log').read_text(errors='replace')
            warnings=[];lines=log.splitlines()
            for i,line in enumerate(lines):
                if '*WARNING' in line.upper():warnings.append(' '.join(x.strip() for x in lines[i:i+3]))
            execution={'case':case,'command':cmd,'exit_code':p.returncode,'elapsed_s':(datetime.now(timezone.utc)-t0).total_seconds(),'warnings':warnings}
            run['executions'].append(execution);dump(out/'run.json',run)
            assert p.returncode==0 and 'Job finished' in log and '*ERROR' not in log.upper(),f'{case} solver did not finish successfully'
            sta=[]
            for line in (folder/'job.sta').read_text().splitlines():
                v=line.split()
                if len(v)==7:
                    try:sta.append((int(v[0]),float(v[4]),float(v[5])))
                    except ValueError:pass
            assert sta and sta[-1][0]==len(m['steps']) and abs(sta[-1][1]-len(m['steps']))<1e-6 and abs(sta[-1][2]-1)<1e-6,'Incomplete STA final step'
            rows.append(process(folder,m,case,bench[case],groups));print(case,'Umax',round(rows[-1]['umax_mm'],3),'mm',flush=True)
        dump(out/'summary.json',rows)
        write_csv(out/'comparison.csv',['case','Umax_mm','reference_mm','error_percent','peak_node','reference_peak_node'],[[r['case'],r['umax_mm'],r['reference_umax_mm'],r['displacement_error_percent'],r['peak_node'],r['reference_peak_node']] for r in rows])
        run['status']='completed';run['comparison_pass']=all(r['comparison_pass'] for r in rows)
        run['all_report_factors_met']=all(s['meets_report_factor'] for r in rows for s in r['span_forces'])
        run['all_cables_tension']=all(r['tension_only_assumption_ok'] for r in rows)
        run['finished_utc']=datetime.now(timezone.utc).isoformat();dump(out/'run.json',run)
        generate(out,run,models,rows,bench)
        (out/'SHA256SUMS').write_text(''.join(f'{sha(p)}  {p.relative_to(out).as_posix()}\n' for p in sorted(out.rglob('*')) if p.is_file() and p.name!='SHA256SUMS'),encoding='utf-8')
        print('Reports and evidence:',out,flush=True)
        if not run['comparison_pass'] or not run['all_report_factors_met'] or not run['all_cables_tension']:
            raise RuntimeError('Completed calculation has failed comparison/strength/tension checks. Read the report; do not declare success.')
    except Exception as e:
        run['status']='failed';run['error']=str(e);dump(out/'run.json',run);raise
if __name__=='__main__':main()
