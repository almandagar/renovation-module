import sys
import os
import unittest
import json
import tempfile
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parent))
from weather_stress_selection import (load_profiles,calculate_features,choose,select_and_export,
    WEATHER_IDS,METRIC_DIRECTIONS,_rolling_mean,_validate_load_csv)
from urban_climate_weather import (read_epw,apply_urban_delta,validate_external_urban_epw,run_uwg_from_parameters,DRYBULB)
ROOT=Path(os.environ.get("ERAA_PROFILE_DIR","__ERAA_PROFILE_DIR_REQUIRED__"))
EPW=Path(os.environ.get("EPW_SAMPLE", "__EPW_SAMPLE_REQUIRED__"))
@unittest.skipUnless(ROOT.is_dir(), "Set ERAA_PROFILE_DIR for real ERAA 2035 matrix tests")
class TestWeather(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles,cls.provenance=load_profiles(ROOT)
        cls.f=calculate_features(cls.profiles)
    def test_columns_and_dimensions(self):
        self.assertEqual(self.f.shape,(36,12));self.assertEqual(list(self.f.index),list(WEATHER_IDS))
    def test_all_eight_countries(self):self.assertEqual(len(self.profiles),8)
    def test_full_36_no_synthetic_years(self):self.assertEqual(len(WEATHER_IDS),36)
    def test_finite(self):self.assertTrue(np.isfinite(self.f.to_numpy()).all())
    def test_matrices_no_missing(self):self.assertEqual(self.profiles['DE']['solar'].shape,(8760,36))
    def test_not_probability(self):self.assertFalse(hasattr(self.f,'weights'))
    def test_zero_hp_not_weather_zero(self):
        self.assertNotIn('demand_heat_pumps',self.profiles['CZ'])
        self.assertNotIn('demand_heat_pumps',self.profiles['FR'])
    def test_extreme_protection(self):
        s,qa=choose(self.f,12,('WS18',));self.assertEqual(len(s),12)
        for col in METRIC_DIRECTIONS:self.assertIn(self.f[col].idxmax(),s)
    def test_anchors(self):self.assertIn('WS18',choose(self.f,12)[0])
    def test_determinism(self):self.assertEqual(choose(self.f,12),choose(self.f,12))
    def test_smaller_subset(self):self.assertEqual(len(choose(self.f,10)[0]),10)
    def test_impossible_k_raises(self):
        with self.assertRaises(ValueError):choose(self.f,4)
    def test_unknown_anchor_raises(self):
        with self.assertRaises(ValueError):choose(self.f,12,('WS99',))
    def test_no_wrap_rolling(self):
        x=np.arange(10,dtype=float)[:,None]
        self.assertEqual(len(_rolling_mean(x,3)),8)
        self.assertAlmostEqual(_rolling_mean(x,3)[-1,0],8)
    def test_selection_json(self):
        with tempfile.TemporaryDirectory() as t:
            x=select_and_export(ROOT,Path(t));self.assertEqual(len(x['selected']),12)
            self.assertTrue(x['not_probability_weighted']);self.assertTrue((Path(t)/'stress12_selection_manifest.json').exists())
    def test_bad_csv_schema(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'bad.csv.gz';pd.DataFrame({'hour_of_year':[0],'WS01':[-1]}).to_csv(p,compression='gzip',index=False)
            with self.assertRaises(ValueError):_validate_load_csv(p)

@unittest.skipUnless(EPW.is_file(), "Set EPW_SAMPLE for urban-weather input tests")
class TestUrban(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.root=Path(self.t.name)
        self.delta=self.root/'delta.csv';pd.DataFrame({'hour_of_year':range(8760),'delta_t_air_C':[0]*8760}).to_csv(self.delta,index=False)
        self.meta={'climate_member':'TMY_UNMATCHED_TO_ERAA','background_source_id':'V4_BERLIN_PVGIS_ERA',
          'background_class':'nonurban_background','urban_zone_id':'TEST_ONLY','urban_source_id':'SYNTHETIC_IDENTITY',
          'urban_source_method':'test_identity','validation_status':'unvalidated_test_fixture',
          'reference_alignment':'same_hour_same_weather_member'}
    def tearDown(self):self.t.cleanup()
    def test_epw(self):self.assertEqual(len(read_epw(EPW)[1]),8760)
    def test_strict_bkg_required(self):
        x=self.meta.copy();x['background_class']='already_urban'
        with self.assertRaises(ValueError):apply_urban_delta(EPW,self.delta,self.root/'urban.epw',x)
    def test_no_malformed_delta(self):
        pd.DataFrame({'hour_of_year':[0],'delta_t_air_C':[1]}).to_csv(self.delta,index=False)
        with self.assertRaises(ValueError):apply_urban_delta(EPW,self.delta,self.root/'urban.epw',self.meta)
    def test_strict_source_member_alignment(self):
        x=self.meta.copy();x['reference_alignment']='unknown'
        with self.assertRaises(ValueError):apply_urban_delta(EPW,self.delta,self.root/'urban.epw',x)
    def test_cannot_claim_qualified(self):
        with self.assertRaises(ValueError):apply_urban_delta(EPW,self.delta,self.root/'urban.epw',self.meta,'qualified')
    def test_identity_preserves_temperature(self):
        out=self.root/'urban.epw';r=apply_urban_delta(EPW,self.delta,out,self.meta)
        _,old=read_epw(EPW);_,new=read_epw(out)
        self.assertEqual([float(z[DRYBULB]) for z in old],[float(z[DRYBULB]) for z in new])
        self.assertEqual(r['status'],'RESEARCH_ONLY_UNVALIDATED_URBAN_DELTA')
    def test_synthetic_delta_temperature_response(self):
        d=pd.DataFrame({'hour_of_year':range(8760),'delta_t_air_C':[2.0]*8760})
        d.to_csv(self.delta,index=False);out=self.root/'u.epw';r=apply_urban_delta(EPW,self.delta,out,self.meta)
        self.assertAlmostEqual(r['delta_t_mean_C'],2.)
        _,a=read_epw(EPW);_,b=read_epw(out)
        self.assertAlmostEqual(float(b[0][DRYBULB])-float(a[0][DRYBULB]),2)
    def test_delta_extreme_rejected(self):
        pd.DataFrame({'hour_of_year':range(8760),'delta_t_air_C':[21]*8760}).to_csv(self.delta,index=False)
        with self.assertRaises(ValueError):apply_urban_delta(EPW,self.delta,self.root/'u.epw',self.meta)
    def test_uwg_require_morphology(self):
        with self.assertRaises(ValueError):
            run_uwg_from_parameters(EPW,self.root,{},self.meta)
    def test_uwg_missing_dependency_fails_closed(self):
        params={"bldheight":10,"blddensity":0.5,"vertohor":0.8,
                "grasscover":0.1,"treecover":0.1,"zone":"4A"}
        with self.assertRaisesRegex(RuntimeError,'UWG is not installed'):
            run_uwg_from_parameters(EPW,self.root,params,self.meta)
    def test_external_identity_accepts_research_only(self):
        r=validate_external_urban_epw(EPW,EPW,self.meta)
        self.assertAlmostEqual(r['delta_t_mean_C'],0.)
        self.assertEqual(r['status'],'RESEARCH_ONLY_EXTERNAL_URBAN_EPW')
    def test_mismatch_urban_epw_hours_rejected(self):
        _,raw=read_epw(EPW)
        # Copy+scramble one hour; weather timing gate needs fixed chronology.
        txt=EPW.read_text(); rows=txt.splitlines(); a,b=rows[8],rows[9];rows[8],rows[9]=b,a
        dest=self.root/'wrong.epw';dest.write_text('\n'.join(rows)+'\n')
        with self.assertRaises(ValueError):validate_external_urban_epw(EPW,dest,self.meta)
    def test_radiation_preserved(self):
        pd.DataFrame({'hour_of_year':range(8760),'delta_t_air_C':[3]*8760}).to_csv(self.delta,index=False)
        out=self.root/'u.epw';apply_urban_delta(EPW,self.delta,out,self.meta)
        _,a=read_epw(EPW);_,b=read_epw(out)
        self.assertEqual([x[13:16] for x in a],[x[13:16] for x in b])

if __name__=='__main__':unittest.main(verbosity=2)
