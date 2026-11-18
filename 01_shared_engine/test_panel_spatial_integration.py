"""Regression tests of the maintained, opt-in panel archetype reconciliation."""
import copy, json, tempfile, unittest
from pathlib import Path
from renovation_reconciliation import (allocate_bounded_dwelling_bins,
    allocate_original_family_overlay,component_flag_joint)
from renovation_pipeline import run_pipeline
from make_acceptance_fixture import fixture


class BoundedApartmentStock(unittest.TestCase):
    def base(self):
        return dict(buildings_by_bin={'3_4':2.,'10_19':1.},dwelling_target=21.,
                    bin_bounds={'3_4':[3.,4.],'10_19':[10.,19.]},
                    prior_means={'3_4':3.5,'10_19':14.})
    def test_conserves_all_dwellings(self):
        got=allocate_bounded_dwelling_bins(**self.base())
        self.assertAlmostEqual(sum(got['dwelling_bins'].values()),21.)
    def test_each_mean_within_declared_bin(self):
        data=self.base();z=allocate_bounded_dwelling_bins(**data)
        for b in data['bin_bounds']:
            self.assertLessEqual(z['per_building'][b],data['bin_bounds'][b][1])
            self.assertGreaterEqual(z['per_building'][b],data['bin_bounds'][b][0])
    def test_open_high_bin_requires_declared_cap(self):
        with self.assertRaises(ValueError):allocate_bounded_dwelling_bins({'50+':1},190,{'50+':[50,120]},{'50+':85})
    def test_positive_dwellings_no_buildings_rejected(self):
        with self.assertRaises(ValueError):allocate_bounded_dwelling_bins({'3_4':0},4,{'3_4':[3,4]},{'3_4':3.5})
    def test_explicit_empty_place_allowed(self):
        res=allocate_bounded_dwelling_bins({'3_4':0},0,{'3_4':[3,4]},{'3_4':3.5})
        self.assertEqual(res['dwelling_bins']['3_4'],0)
    def test_no_unsourced_prior(self):
        with self.assertRaises(ValueError):allocate_bounded_dwelling_bins({'3_4':1},3.5,{'3_4':[3,4]},{'3_4':10})
    def test_family_partition(self):
        z=allocate_original_family_overlay({'3_4':2,'10_19':1},{'3_4':7,'10_19':14},
            {'3_4':{'OTHER':1},'10_19':{'PANEL_KE':.8,'OTHER':.2}})
        self.assertAlmostEqual(sum(x['buildings'] for x in z['families'].values()),3)
        self.assertAlmostEqual(sum(x['dwellings'] for x in z['families'].values()),21)
        self.assertEqual(z['ra_status'],'UNIDENTIFIED_INDEPENDENT_CURRENT_THERMAL_STATE')
    def test_nonconserving_family_rejected(self):
        with self.assertRaises(ValueError):allocate_original_family_overlay({'a':1},{'a':4},{'a':{'panel':.8}})
    def test_component_2021_source_margins_conserved(self):
        p={'facade':.5746,'roof':.613,'windows':.7654}
        for rho in (0,.35,.7,1):
            j=component_flag_joint(p,rho)
            self.assertAlmostEqual(sum(x['share'] for x in j['rows']),1)
            for k in p:self.assertAlmostEqual(sum(x['share'] for x in j['rows'] if x['flags'][k]),p[k])
    def test_joint_association_not_raIII(self):
        p={'facade':.5746,'roof':.613,'windows':.7654}
        a=component_flag_joint(p,0);b=component_flag_joint(p,.7)
        get=lambda j:next(x['share'] for x in j['rows'] if all(x['flags'].values()))
        self.assertGreater(get(b),get(a));self.assertIn('RA_NOT_IDENTIFIABLE',b['ra_status'])
    def test_component_invalid_input_rejected(self):
        with self.assertRaises(ValueError):component_flag_joint({'facade':.5,'roof':.5},.35)


class PanelSidecarContract(unittest.TestCase):
    def sample_spec(self):
        return {'country':'TEST','source_ref':'SODB2021_TEST_ONLY','reference_year':2021,
            'place_totals':{'p':{'buildings':2,'dwellings':7}},
            'cohorts':[{'place_id':'p','original_period':'1961 - 1980',
                        'buildings_by_bin':{'3_4':2}}],
            'size_bounds':{'3_4':[3,4]},
            'scenarios':[{'id':'CENTRAL','unit_prior_means':{'3_4':3.5},
                          'family_weights':{'1961 - 1980':{'3_4':{'PANEL_SINGLE':.7,'OTHER':.3}}},
                          'common_project_fraction':.35}],
            'national_component_reporting_marginals':{'facade':.5746,'roof':.613,'windows':.7654}}
    def run_case(self,bundle):
        with tempfile.TemporaryDirectory() as d:
            file=Path(d)/'source.json';file.write_text(json.dumps(bundle))
            paths=run_pipeline(file,Path(d)/'out')
            results=json.loads(paths['cohort_results'].read_text())
            meta=json.loads(paths['manifest'].read_text())
            side=json.loads(paths['spatial_panel_archetype_calibration'].read_text()) if 'spatial_panel_archetype_calibration' in paths else None
            return results,meta,side
    def test_sidecar_does_not_change_original_nine_scenarios(self):
        b=fixture();old,_,_=self.run_case(b)
        b['spatial_panel_archetype_calibration']=self.sample_spec()
        new,meta,side=self.run_case(b)
        self.assertEqual(old,new)
        self.assertFalse(meta['runtime_promoted'])
        self.assertEqual(len(side['scenarios']),1)
        self.assertEqual(sum(x['buildings'] for x in side['scenarios'][0]['original_family_cells']),2)
        self.assertEqual(sum(x['dwellings'] for x in side['scenarios'][0]['original_family_cells']),7)
    def test_sidecar_no_default_current_RA_or_area(self):
        b=fixture();b['spatial_panel_archetype_calibration']=self.sample_spec()
        _,_,s=self.run_case(b)
        self.assertTrue(all(x['ra_status']=='NOT_IDENTIFIED' and x['conditioned_area_m2'] is None
                            for x in s['scenarios'][0]['original_family_cells']))
    def test_reject_cross_country_stock(self):
        b=fixture();spec=self.sample_spec();spec['country']='SK';b['spatial_panel_archetype_calibration']=spec
        with self.assertRaisesRegex(ValueError,'country boundary'):self.run_case(b)
    def test_reject_incompatible_place_buildings(self):
        b=fixture();spec=self.sample_spec();spec['place_totals']['p']['buildings']=3
        b['spatial_panel_archetype_calibration']=spec
        with self.assertRaisesRegex(ValueError,'building count mismatch'):self.run_case(b)
    def test_reject_missing_period_prior(self):
        b=fixture();spec=self.sample_spec();spec['scenarios'][0]['family_weights']={}
        b['spatial_panel_archetype_calibration']=spec
        with self.assertRaisesRegex(ValueError,'No prior'):self.run_case(b)

if __name__=='__main__':unittest.main()
