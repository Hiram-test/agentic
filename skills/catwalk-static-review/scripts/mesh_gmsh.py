"""Generate a 1-D Gmsh mesh and explicitly recover the source INP identities."""
import argparse, math
from pathlib import Path
from model import parse,dump

def mesh(inp,out,subdivisions=1):
    import gmsh
    m=parse(inp);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    gmsh.initialize();gmsh.option.setNumber('General.Terminal',0)
    try:
        gmsh.model.add('catwalk_static')
        for n,xyz in m['nodes'].items():gmsh.model.geo.addPoint(*xyz,0,n)
        for e,v in m['elements'].items():gmsh.model.geo.addLine(*v['nodes'],e)
        gmsh.model.geo.synchronize()
        for e in m['elements']:gmsh.model.mesh.setTransfiniteCurve(e,subdivisions+1)
        for k,(name,sec) in enumerate(m['sections'].items(),1):
            gmsh.model.addPhysicalGroup(1,m['sets'][name],k);gmsh.model.setPhysicalName(1,k,name)
        gmsh.option.setNumber('Mesh.ElementOrder',1)
        gmsh.option.setNumber('Mesh.MshFileVersion',4.1)
        gmsh.model.mesh.generate(1)
        nmap={};emap={};maxerr=0.
        for n,xyz in m['nodes'].items():
            tags,coords,_=gmsh.model.mesh.getNodes(0,n)
            assert len(tags)==1,'Geometric endpoint did not receive exactly one mesh node'
            nmap[int(tags[0])]=n;maxerr=max(maxerr,math.dist(xyz,coords.tolist()))
        for e,v in m['elements'].items():
            types,tags,conn=gmsh.model.mesh.getElements(1,e)
            assert list(types)==[1] and len(tags[0])==subdivisions
            emap[e]=list(map(int,tags[0]))
            if subdivisions==1:
                actual=[nmap[int(x)] for x in conn[0]]
                assert actual==v['nodes'],f'Connectivity changed for {e}'
        assert maxerr<1e-7
        gmsh.write(str(out/'catwalk.msh'));gmsh.write(str(out/'catwalk.geo_unrolled'))
        nodes=gmsh.model.mesh.getNodes()[0]
        if subdivisions==1:assert len(nodes)==len(m['nodes'])
        result={'gmsh_version':gmsh.__version__,'subdivisions':subdivisions,'node_count':len(nodes),
            'line_element_count':sum(map(len,emap.values())),'maximum_coordinate_error_mm':maxerr,
            'connectivity_identical':subdivisions==1,'gmsh_node_to_inp_node':nmap,'inp_element_to_gmsh_elements':emap,
            'analysis_deck_policy':'Use original locked INP; Gmsh contains geometry only, no sections/loads/prestress',
            'refined_mesh_is_unsolved_candidate':subdivisions!=1}
        dump(out/'mesh_map.json',result);return result
    finally:gmsh.finalize()
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--inp',required=True);p.add_argument('--out',required=True);p.add_argument('--subdivisions',type=int,default=1)
    a=p.parse_args();assert a.subdivisions>=1;mesh(a.inp,a.out,a.subdivisions)
