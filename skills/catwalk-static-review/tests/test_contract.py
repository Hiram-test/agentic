import sys, unittest, tempfile, shutil, json
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from model import forces,parse,dat_results
import run

class ContractTests(unittest.TestCase):
    def test_deformed_axis_and_shear_tensor(self):
        # Current chord rotated 45 degrees; S=[[50,50,0],[50,50,0],[0,0,0]].
        # n^T S n=100; A=20mm2 -> 2kN. Undeformed-axis projection would wrongly give 1kN.
        m={'nodes':{1:[0,0,0],2:[1,0,0]},'elements':{7:{'type':'T3D2','nodes':[1,2],'section':'s'}},'sections':{'s':{'area_mm2':20}}}
        u={1:[0,0,0],2:[0,1,0]};s={7:{i:[50,50,0,50,0,0] for i in range(1,9)}}
        self.assertAlmostEqual(forces(m,u,s)[7]['N_kN'],2)
        for v in s[7].values():
            for i in range(6):v[i]*=-1
        self.assertAlmostEqual(forces(m,u,s)[7]['N_kN'],-2) # Do not hide compression.

    def test_locked_inputs_verify(self):
        m,a,g=run.verify();self.assertEqual(len(m),6)
        self.assertAlmostEqual(a['P5']['steps'][1]['cload_sum_N']['3'],-6377029.291)

    def test_one_byte_change_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);shutil.copytree(ROOT/'assets',root/'assets')
            p=root/'assets/inputs/migrate_P5.inp'
            with p.open('ab') as f:f.write(b'\n')
            with patch.object(run,'ROOT',root):
                with self.assertRaisesRegex(ValueError,'Asset changed'):run.verify()

    def test_external_include_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'bad.inp';p.write_text('*INCLUDE, INPUT=elsewhere.inp\n')
            with self.assertRaisesRegex(ValueError,'INCLUDE'):parse(p)

    def test_mismatched_result_time_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'bad.dat'
            p.write_text(' displacements (vx,vy,vz) for set N_MCT and time 2.0\n1 0 0 0\n stresses (elem, integ.pnt.,sxx,syy,szz,sxy,sxz,syz) for set E_CABLE and time 1.0\n1 1 0 0 0 0 0 0\n')
            with self.assertRaisesRegex(AssertionError,'times differ'):dat_results(p)

    def test_missing_final_stress_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'bad.dat';p.write_text(' displacements (vx,vy,vz) for set N_MCT and time 2.0\n1 0 0 0\n')
            with self.assertRaises(StopIteration):dat_results(p)

if __name__=='__main__':unittest.main()
