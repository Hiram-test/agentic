import csv,math,xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from model import dat_results, forces, dump

def write_csv(path,header,rows):
    with Path(path).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(header);w.writerows(rows)

def vtu(path,m,u,force):
    ns=sorted(m['nodes']);es=sorted(m['elements']);index={n:i for i,n in enumerate(ns)}
    root=ET.Element('VTKFile',type='UnstructuredGrid',version='0.1',byte_order='LittleEndian')
    piece=ET.SubElement(ET.SubElement(root,'UnstructuredGrid'),'Piece',NumberOfPoints=str(len(ns)),NumberOfCells=str(len(es)))
    def arr(parent,name,values,typ='Float64',components=None):
        attrs={'type':typ,'format':'ascii','Name':name}
        if components:attrs['NumberOfComponents']=str(components)
        x=ET.SubElement(parent,'DataArray',attrs);x.text=' '.join(map(str,values))
    pts=ET.SubElement(piece,'Points');arr(pts,'Points',(x for n in ns for x in m['nodes'][n]),components=3)
    cells=ET.SubElement(piece,'Cells');arr(cells,'connectivity',(index[n] for e in es for n in m['elements'][e]['nodes']),'Int32')
    arr(cells,'offsets',range(2,len(es)*2+1,2),'Int32');arr(cells,'types',[3]*len(es),'UInt8')
    pd=ET.SubElement(piece,'PointData');arr(pd,'node_id',ns,'Int32');arr(pd,'U_mm',(x for n in ns for x in u[n]),components=3)
    arr(pd,'U_magnitude_mm',(math.sqrt(sum(x*x for x in u[n])) for n in ns));arr(pd,'UZ_mm',(u[n][2] for n in ns))
    cd=ET.SubElement(piece,'CellData');arr(cd,'element_id',es,'Int32')
    arr(cd,'cable_result_valid',[int(e in force) for e in es],'UInt8')
    for key in ('N_kN','sigma_axial_MPa'):arr(cd,key,[force[e][key] if e in force else 'NaN' for e in es])
    ET.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)

def plot(path,m,u,values,title,units,elements=None,deformation=0,diverging=False):
    es=elements or sorted(m['elements']);segments=[];colors=[]
    for e in es:
        ns=m['elements'][e]['nodes'];segments.append([[(m['nodes'][n][0]+deformation*u[n][0])/1000,(m['nodes'][n][2]+deformation*u[n][2])/1000] for n in ns]);colors.append(values[e])
    from matplotlib.font_manager import FontProperties
    from matplotlib.colors import BoundaryNorm
    font=FontProperties(fname=str(Path(__file__).resolve().parents[1]/'assets/fonts/simsun.ttf'))
    fig,ax=plt.subplots(figsize=(12,3.8));fig.subplots_adjust(left=.025,right=.88,top=.91,bottom=.10)
    vals=np.asarray(colors);lo=float(vals.min());hi=float(vals.max())
    if diverging: hi=max(abs(lo),abs(hi),1e-12);lo=-hi
    if hi-lo<1e-12:hi=lo+1
    bounds=np.linspace(lo,hi,13);cmap=plt.get_cmap('jet',12)
    lc=LineCollection(segments,array=vals,cmap=cmap,norm=BoundaryNorm(bounds,12),linewidths=1.05)
    ax.add_collection(lc);ax.autoscale();ax.margins(x=.025,y=.30);ax.axis('off')
    cb=fig.colorbar(lc,ax=ax,fraction=.027,pad=.035,spacing='uniform',ticks=bounds[::2],drawedges=True)
    cb.ax.set_title(units,fontproperties=font,fontsize=15,pad=10);cb.ax.tick_params(labelsize=13,length=2)
    ix=int(np.argmax(np.abs(vals))) if diverging else int(np.argmax(vals));seg=segments[ix]
    xy=np.mean(seg,axis=0);ax.plot(*xy,'o',color='#c13a3a',markersize=2)
    label=('最大绝对值' if diverging else '最大值')+f'：{vals[ix]:.3f}'
    left,right=ax.get_xlim();ha='left' if xy[0]<left+.2*(right-left) else 'right' if xy[0]>right-.2*(right-left) else 'center'
    ax.annotate(label,xy,xytext=(0,16),textcoords='offset points',color='#b54b4b',fontproperties=font,fontsize=16,ha=ha,arrowprops={'arrowstyle':'-','color':'#b54b4b','lw':.4})
    note=f'X–Z投影；线形显示倍率 {deformation:g}；纵横比例独立；' + ('线段平均位移' if units=='mm' else '线单元结果')
    fig.text(.03,.018,note,fontproperties=font,fontsize=12,color='#555555')
    fig.savefig(path,dpi=200,facecolor='white');plt.close(fig)

def process(folder,m,case,reference,groups):
    folder=Path(folder);t,u,s=dat_results(folder/'job.dat')
    assert set(u)==set(m['nodes']),'Missing or extra source nodes'
    expected={e for e,v in m['elements'].items() if v['type']=='T3D2'}
    assert set(s)==expected,'Incomplete cable stress output'
    assert all(set(v)==set(range(1,9)) for v in s.values()),'Expected 8 cable integration points'
    assert abs(t-len(m['steps']))<1e-6,'Did not reach final analysis time'
    assert all(math.isfinite(x) for v in u.values() for x in v)
    assert all(math.isfinite(x) for v in s.values() for ip in v.values() for x in ip)
    force=forces(m,u,s);peak=max(u,key=lambda n:sum(x*x for x in u[n]));umax=math.sqrt(sum(x*x for x in u[peak]))
    uy=max(abs(v[1]) for v in u.values());assert uy<1e-6,'UY constraints not satisfied'
    row={'case':case,'final_time':t,'umax_mm':umax,'peak_node':peak,'peak_displacement_mm':u[peak],
      'max_abs_UY_mm':uy,'reference_umax_mm':reference['umax_mm'],'reference_peak_node':reference['peak_node'],
      'displacement_error_percent':100*(umax/reference['umax_mm']-1),'force_recovery':'Mean global Cauchy stress projected onto deformed chord times original area',
      'minimum_cable_force_kN':min(v['N_kN'] for v in force.values()),'span_forces':[]}
    for typ,names in [('bottom',list(groups)[:4]),('portal',list(groups)[4:])]:
        for j,name in enumerate(names):
            ids=[e for e in groups[name] if e in force];assert ids
            eid=max(ids,key=lambda e:force[e]['N_kN']);val=force[eid]['N_kN'];ref=reference[typ+'_kN'][j]
            breaking=38080 if typ=='bottom' else 14280;k=breaking/val
            row['span_forces'].append({'type':typ,'span':name,'element':eid,'N_kN':val,'report_kN':ref,'error_percent':100*(val/ref-1),
                'breaking_force_kN':breaking,'safety_factor':k,'required_factor':reference['required_factor'],'meets_report_factor':k>=reference['required_factor']})
    row['comparison_pass']=abs(row['displacement_error_percent'])<=1 and peak==reference['peak_node'] and max(abs(x['error_percent']) for x in row['span_forces'])<=1.5
    # Comparison tolerance is a regression criterion, not a structural code limit.
    row['tension_only_assumption_ok']=row['minimum_cable_force_kN']>0
    dump(folder/'summary.json',row)
    write_csv(folder/'nodes.csv',['node','X_mm','Y_mm','Z_mm','UX_mm','UY_mm','UZ_mm','USUM_mm'],
        [[n,*m['nodes'][n],*u[n],math.sqrt(sum(x*x for x in u[n]))] for n in sorted(u)])
    write_csv(folder/'cables.csv',['element','section','N_kN','axial_stress_MPa'],
        [[e,m['elements'][e]['section'],force[e]['N_kN'],force[e]['sigma_axial_MPa']] for e in sorted(force)])
    vtu(folder/'results.vtu',m,u,force)
    for name,values,unit,div in [
      ('USUM',{e:sum(math.sqrt(sum(x*x for x in u[n])) for n in v['nodes'])/2 for e,v in m['elements'].items()},'mm',False),
      ('UZ',{e:sum(u[n][2] for n in v['nodes'])/2 for e,v in m['elements'].items()},'mm',True)]:
        plot(folder/f'{name}.png',m,u,values,f'{case}: {name} (line colour = endpoint mean)',unit,diverging=div)
    for sec,label in [('E_SEC1','bottom'),('E_SEC2','portal')]:
        for key,unit in [('N_kN','kN'),('sigma_axial_MPa','MPa')]:
            plot(folder/f'{label}_{key}.png',m,u,{e:v[key] for e,v in force.items()},f'{case}: {label} cable {key}',unit,sorted({e for name,ids in groups.items() if name.startswith('门架索')==(label=='portal') for e in ids}))
    # Separate actual 1x deformed geometry export in the PNG; authoritative values remain in nodes.csv.
    plot(folder/'deformed_1x.png',m,u,{e:0 for e in m['elements']},f'{case}: deformed centreline','geometry only',deformation=1)
    return row
