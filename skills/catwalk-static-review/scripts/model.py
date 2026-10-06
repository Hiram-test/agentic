"""Strict parser for this versioned CalculiX T3D2/B31 deck, not a generic INP parser."""
from pathlib import Path
from collections import defaultdict, Counter
import hashlib, json, math

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def dump(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')

def cards(path):
    out=[]
    for lineno,line in enumerate(Path(path).read_text(encoding='utf-8-sig').splitlines(),1):
        line=line.strip()
        if not line or line.startswith('**'): continue
        if line.startswith('*'):
            words=[x.strip() for x in line[1:].split(',')]
            c={'key':words[0].upper(),'opts':{},'rows':[],'line':lineno};out.append(c)
            for x in words[1:]:
                k,sep,v=x.partition('=');c['opts'][k.upper()]=v.strip() if sep else True
        elif out: out[-1]['rows'].append([v.strip() for v in line.split(',') if v.strip()])
    return out

def parse(path):
    m={'nodes':{},'elements':{},'sets':{},'nsets':{},'materials':{},'sections':{},'boundary':[],
       'initial_stress':{},'steps':[],'sha256':sha(path)}
    mat=None;step=None
    for c in cards(path):
        k,o,rows=c['key'],c['opts'],c['rows']
        if k=='INCLUDE': raise ValueError('External INCLUDE unsupported; supply a reviewed self-contained deck')
        if k=='NODE':
            for r in rows:
                n=int(r[0]);assert n not in m['nodes'];m['nodes'][n]=list(map(float,r[1:4]))
        elif k=='ELEMENT':
            assert o['TYPE'] in ('T3D2','B31')
            ids=[]
            for r in rows:
                e=int(r[0]);assert e not in m['elements'];ids.append(e)
                m['elements'][e]={'type':o['TYPE'],'nodes':list(map(int,r[1:]))}
            if 'ELSET' in o:m['sets'].setdefault(o['ELSET'],[]).extend(ids)
        elif k in ('ELSET','NSET'):
            target=m['sets' if k=='ELSET' else 'nsets'];name=o[k];ids=[]
            for r in rows:
                nums=list(map(int,r))
                if 'GENERATE' in o:
                    assert len(nums) in (2,3);ids.extend(range(nums[0],nums[1]+1,nums[2] if len(nums)==3 else 1))
                else:ids.extend(nums)
            target.setdefault(name,[]).extend(ids)
        elif k=='MATERIAL': mat=o['NAME'];m['materials'][mat]={}
        elif k in ('ELASTIC','DENSITY','EXPANSION'):
            assert mat and len(rows)==1;m['materials'][mat][k.lower()]=list(map(float,rows[0]))
        elif k in ('SOLID SECTION','BEAM SECTION'):
            sec={'material':o['MATERIAL'],'kind':k,'data':list(map(float,rows[0]))}
            if k=='SOLID SECTION':sec['area_mm2']=sec['data'][0]
            else:
                assert o.get('SECTION')=='RECT';sec['area_mm2']=math.prod(sec['data']);sec['orientation']=list(map(float,rows[1]))
            m['sections'][o['ELSET']]=sec
        elif k=='INITIAL CONDITIONS' and o.get('TYPE')=='STRESS':
            for r in rows:
                e,ip=map(int,r[:2]);m['initial_stress'].setdefault(e,{})[ip]=list(map(float,r[2:8]))
        elif k=='BOUNDARY':
            for r in rows:
                n=int(r[0]);a=int(r[1]);b=int(r[2]) if len(r)>2 else a;v=float(r[3]) if len(r)>3 else 0
                m['boundary'].extend((n,d,v) for d in range(a,b+1))
        elif k=='STEP':
            step={'nlgeom':'NLGEOM' in o,'static':[],'cload':{},'dload':[],'temperature':[]};m['steps'].append(step)
        elif k=='END STEP':step=None
        elif step is not None:
            if k=='STATIC':step['static']=[float(x) for r in rows for x in r]
            elif k=='CLOAD':
                assert o.get('OP','MOD') in ('MOD','NEW');step['cload_op']=o.get('OP','MOD')
                for r in rows:
                    key=(int(r[0]),int(r[1]));step['cload'][key]=step['cload'].get(key,0)+float(r[2])
            elif k=='DLOAD':step['dload'].extend(rows)
            elif k=='TEMPERATURE':step['temperature'].extend(rows)
    for name,s in m['sections'].items():
        for e in m['sets'][name]:
            assert 'section' not in m['elements'][e];m['elements'][e]['section']=name
    for e,v in m['elements'].items():
        assert len(v['nodes'])==2 and all(n in m['nodes'] for n in v['nodes']) and 'section' in v
        assert math.dist(*(m['nodes'][n] for n in v['nodes']))>0
    return m

def audit(m):
    b=sorted(set(m['boundary']));steps=[]
    for i,s in enumerate(m['steps'],1):
        sums={str(d):sum(v for (n,k),v in s['cload'].items() if k==d) for d in (1,2,3)}
        # Moment of nodal forces about global origin; DLOAD not included.
        moment=[0.,0.,0.]
        for (n,d),v in s['cload'].items():
            x,y,z=m['nodes'][n];f=[0.,0.,0.];f[d-1]=v
            for j,w in enumerate((y*f[2]-z*f[1],z*f[0]-x*f[2],x*f[1]-y*f[0])):moment[j]+=w
        steps.append({'step':i,'nlgeom':s['nlgeom'],'static':s['static'],'cload_records':len(s['cload']),
                      'cload_sum_N':sums,'cload_moment_Nmm':moment,'dload':s['dload'],'temperature':s['temperature']})
    non_y=[list(x) for x in b if x[1]!=2]
    mass=defaultdict(float)
    for e in m['elements'].values():
        sec=m['sections'][e['section']];rho=m['materials'][sec['material']]['density'][0]
        mass[e['section']]+=math.dist(*(m['nodes'][n] for n in e['nodes']))*sec['area_mm2']*rho
    return {'input_sha256':m['sha256'],'node_count':len(m['nodes']),'element_count':len(m['elements']),
      'element_types':dict(Counter(e['type'] for e in m['elements'].values())),
      'materials':m['materials'],'sections':m['sections'],'mass_tonne_by_section':dict(mass),
      'boundary_dof_count':len(b),'all_UY_fixed':all((n,2,0.) in b for n in m['nodes']),
      'boundary_except_UY':non_y,'prestress_elements':len(m['initial_stress']),
      'prestress_ip_count':sum(len(v) for v in m['initial_stress'].values()),'steps':steps}

def dat_results(path):
    blocks=[];current=None
    for line in Path(path).read_text().splitlines():
        low=line.lower()
        if 'displacements (vx,vy,vz)' in low or 'stresses (elem, integ.pnt.' in low:
            current={'kind':'u' if 'displacements' in low else 's','time':float(low.split('time')[-1]),'values':{}};blocks.append(current);continue
        if current:
            p=line.split()
            try:
                if current['kind']=='u' and len(p)==4:current['values'][int(p[0])]=list(map(float,p[1:]))
                elif current['kind']=='s' and len(p)==8:
                    current['values'].setdefault(int(p[0]),{})[int(p[1])]=list(map(float,p[2:]))
            except ValueError: pass
    u=next(b for b in reversed(blocks) if b['kind']=='u');s=next(b for b in reversed(blocks) if b['kind']=='s')
    assert abs(u['time']-s['time'])<1e-8,'U and S output times differ'
    return u['time'],u['values'],s['values']

def forces(m,u,stress):
    out={}
    for eid,v in stress.items():
        e=m['elements'][eid];assert e['type']=='T3D2'
        a,b=([m['nodes'][n][i]+u[n][i] for i in range(3)] for n in e['nodes'])
        direction=[b[i]-a[i] for i in range(3)];length=math.sqrt(sum(x*x for x in direction));x,y,z=[q/length for q in direction]
        normal=sum(sx*x*x+sy*y*y+sz*z*z+2*txy*x*y+2*txz*x*z+2*tyz*y*z for sx,sy,sz,txy,txz,tyz in v.values())/len(v)
        out[eid]={'sigma_axial_MPa':normal,'N_kN':normal*m['sections'][e['section']]['area_mm2']/1000}
    return out
