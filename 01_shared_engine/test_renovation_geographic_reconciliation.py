import unittest
from renovation_reconciliation import reconstruct_geographic_joint, rake

class SpatialHeatingMarginals(unittest.TestCase):
    def setup_data(self):
        joint=[{'id':'G-C','count':45,'attributes':{'fuel':'G','mode':'CENTRAL'}},
               {'id':'G-R','count':15,'attributes':{'fuel':'G','mode':'ROOM'}},
               {'id':'W-C','count':10,'attributes':{'fuel':'W','mode':'CENTRAL'}},
               {'id':'W-R','count':30,'attributes':{'fuel':'W','mode':'ROOM'}}]
        places={'P1':55,'P2':45}
        marginals=[{'place_id':'P1','selector':{'fuel':'G'},'count':40},
                   {'place_id':'P2','selector':{'fuel':'G'},'count':20},
                   {'place_id':'P1','selector':{'mode':'ROOM'},'count':20},
                   {'place_id':'P2','selector':{'mode':'ROOM'},'count':25}]
        return joint,places,marginals
    def test_fit_to_both_observed_margins(self):
        x=reconstruct_geographic_joint(*self.setup_data())
        rows=x['rows']
        self.assertEqual(len(rows),8)
        self.assertAlmostEqual(x['national_population'],100)
        for p,t in [('P1',55),('P2',45)]:
            self.assertAlmostEqual(sum(r['estimated_count'] for r in rows if r['attributes']['place_id']==p),t,places=5)
        self.assertAlmostEqual(sum(r['estimated_count'] for r in rows if r['attributes']['place_id']=='P1' and r['attributes']['fuel']=='G'),40,places=5)
        self.assertAlmostEqual(sum(r['estimated_count'] for r in rows if r['attributes']['mode']=='ROOM'),45,places=5)
        self.assertEqual(x['evidence_class'],'MODEL_PRIOR_NOT_LOCAL_JOINT_OBSERVATION')
    def test_absent_joint_state_remains_structural_zero(self):
        joint,places,marginals=self.setup_data()
        joint=joint[:-1]
        places={'P1':40,'P2':30}
        marginals=[]
        x=reconstruct_geographic_joint(joint,places,marginals)
        self.assertTrue(all(not (r['attributes']['fuel']=='W' and r['attributes']['mode']=='ROOM') for r in x['rows']))
    def test_bad_population_is_not_silently_adjusted(self):
        joint,places,marginals=self.setup_data()
        with self.assertRaisesRegex(ValueError,'disagree'):
            reconstruct_geographic_joint(joint,{'P1':55,'P2':40},marginals)
    def test_local_marginal_cannot_exceed_parent(self):
        joint,places,marginals=self.setup_data()
        marginals[0]['count']=60
        with self.assertRaisesRegex(ValueError,'parent'):
            reconstruct_geographic_joint(joint,places,marginals)
    def test_unknown_category_does_not_become_heat_pump(self):
        joint,places,marginals=self.setup_data()
        joint[0]['attributes']['fuel']='HP'
        with self.assertRaises(ValueError):reconstruct_geographic_joint(joint,places,marginals)
    def test_pipeline_sidecar_does_not_change_stock_or_cohort_results(self):
        import json,tempfile
        from pathlib import Path
        from make_acceptance_fixture import fixture
        from renovation_pipeline import run_pipeline
        joint,places,marginals=self.setup_data()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            baseline=fixture()
            input_file=root/'input.json'
            input_file.write_text(json.dumps(baseline))
            base_outputs=run_pipeline(input_file,root/'baseline')
            expected=json.loads(base_outputs['cohort_results'].read_text())
            baseline['spatial_heating_calibration']={
                'reference_year':2021,'population_unit':'dwellings',
                'national_joint':joint,'place_totals':places,'place_marginals':marginals,
                'source_ref':'TEST_SAME_CENSUS_2021_NOT_REAL'}
            input_file.write_text(json.dumps(baseline))
            result=run_pipeline(input_file,root/'reconciled')
            self.assertIn('spatial_heating_calibration',result)
            self.assertEqual(json.loads(result['cohort_results'].read_text()),expected)
            mix=json.loads(result['spatial_heating_calibration'].read_text())
            self.assertAlmostEqual(mix['national_population'],100)
            self.assertEqual(mix['use'],'RESEARCH_SIDE_CAR_NOT_PHYSICAL_STOCK_OR_HOUSING_HEAT_PUMP_COUNTS')
    def test_pipeline_rejects_post_forecast_spatial_observations(self):
        import json,tempfile
        from pathlib import Path
        from make_acceptance_fixture import fixture
        from renovation_pipeline import run_pipeline
        joint,places,marginals=self.setup_data()
        b=fixture()
        b['spatial_heating_calibration']={'reference_year':2035,'population_unit':'dwellings',
             'national_joint':joint,'place_totals':places,'place_marginals':marginals,'source_ref':'TEST'}
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'fixture.json';p.write_text(json.dumps(b))
            with self.assertRaisesRegex(ValueError,'pre-forecast'):
                run_pipeline(p,Path(d)/'out')
    def test_existing_rake_contract_unchanged(self):
        x=rake([{'id':'A','attributes':{'a':0},'share':.5},{'id':'B','attributes':{'a':1},'share':.5}],
               [{'selector':{'a':1},'share':.8}]);self.assertAlmostEqual(x['rows'][1]['share'],.8)
if __name__=='__main__':unittest.main()


class NestedKosiceSpatialSourceAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from sk_2021_heating_joint_source_bridge import build_kosice_nested
        here=__import__('pathlib').Path(__file__).resolve().parent
        cls.case=build_kosice_nested(here/'kosice_margins.csv',here/'kosice_vintage.csv')
    def test_kosice_22_geography_not_synthetic(self):
        r=self.case
        self.assertEqual(len(r['places']),22)
        self.assertEqual(len({p['place_id'] for p in r['places']}),22)
        self.assertEqual(r['parent_FH_dwellings_2021'],128773)
        self.assertEqual(r['city_FH_dwellings_observed'],12542)
        self.assertEqual(r['out_of_city_region_FH_dwellings_remainder'],116231)
    def test_observed_vintage_buildings_conserved_all_forms(self):
        r=self.case; cells=r['original_vintage_form']
        self.assertEqual(len(cells),594)
        for form,category in [('FH','houses_family'),('AP','houses_apartment'),('OTHER','houses_other')]:
            self.assertEqual(sum(c['houses_observed'] for c in cells if c['building_form']==form),r['city_observed_totals'][category])
    def test_apartment_dwelling_vintage_is_unobserved(self):
        cells=self.case['original_vintage_form']
        self.assertTrue(all(x['dwellings_for_period_model_prior'] is None for x in cells if x['building_form']!='FH'))
        self.assertTrue(all(x['current_fabric_RA']=='UNKNOWN_NOT_ZERO' for x in cells))
    def test_inferred_family_dwelling_by_period_conserves_local_census(self):
        r=self.case
        for p in r['places']:
            num=sum(c['dwellings_for_period_model_prior'] or 0 for c in r['original_vintage_form']
                    if c['place_id']==p['place_id'] and c['building_form']=='FH')
            self.assertAlmostEqual(num,p['family_dwelling_count_observed'],places=5)
    def test_heating_variants_each_conserve_observed_regional_parent(self):
        r=self.case
        for name,v in r['heating_source_variants'].items():
            self.assertAlmostEqual(sum(s['family_dwellings_source_or_residual'] for s in v['modelled_marginals']),128773,places=5)
            for fuel in ('plyn','elektrina','pevné palivo'):
                target={'plyn':86341,'elektrina':4459,'pevné palivo':33533}[fuel]
                self.assertAlmostEqual(sum(s['source_modelled'][fuel] for s in v['modelled_marginals']),target,places=3)
            self.assertLess(v['max_parent_joint_fit_error_dwellings'],.01)
    def test_no_2025_heat_pump_or_apartment_renovation_imputed(self):
        r=self.case
        self.assertFalse(r['runtime_promoted'])
        self.assertTrue(all(c['commissioned_HP_count']=='UNKNOWN_NOT_ZERO' for c in r['original_vintage_form']))
        self.assertTrue(all(c['current_fabric_RA']=='UNKNOWN_NOT_ZERO' for c in r['original_vintage_form']))
        self.assertTrue(all(x['observed_local_heat_sources'] is False for v in r['heating_source_variants'].values() for x in v['modelled_marginals']))
    def test_local_electricity_eco_prior_is_nontrivial_but_not_observed(self):
        r=self.case
        v=r['heating_source_variants']
        key=r['places'][12]['place_id']
        a=next(t for t in v['NEUTRAL']['modelled_marginals'] if t['place_id']==key)
        b=next(t for t in v['PARTIAL_POOL_50']['modelled_marginals'] if t['place_id']==key)
        self.assertNotAlmostEqual(a['source_modelled']['elektrina'],b['source_modelled']['elektrina'],places=2)
        cv=r['ecological_source_model'];self.assertLess(cv['mean_abs_model_dwellings_per_region'],cv['mean_abs_baseline_dwellings_per_region'])
    def test_zero_positive_row_not_physical_structural_zero(self):
        rows=[x for x in self.case['original_vintage_form'] if x['no_published_positive_row']]
        self.assertTrue(rows)
        self.assertTrue(all(x['zero_semantics']=='NO_POSITIVE_SOURCE_ROW_NOT_VERIFIED_STRUCTURAL_ZERO' for x in rows))
    def test_prior_multiplier_conservation_and_positivity(self):
        joint,places,marginals=SpatialHeatingMarginals().setup_data()
        base=reconstruct_geographic_joint(joint,places,marginals)
        perturbed=reconstruct_geographic_joint(joint,places,marginals,place_category_priors=[{'place_id':'P1','selector':{'fuel':'G'},'multiplier':1.5}])
        self.assertAlmostEqual(sum(x['estimated_count'] for x in perturbed['rows']),100,places=5)
        self.assertEqual(len(base['rows']),len(perturbed['rows']))
        with self.assertRaisesRegex(ValueError,'positive'):
            reconstruct_geographic_joint(joint,places,marginals,place_category_priors=[{'place_id':'P1','selector':{'fuel':'G'},'multiplier':0}])
    def test_missing_source_vintage_marginal_fails_not_silently_replaced(self):
        import csv,tempfile
        from pathlib import Path
        from sk_2021_heating_joint_source_bridge import build_kosice_nested
        here=Path(__file__).resolve().parent
        with open(here/'kosice_vintage.csv',encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f)); fields=list(rows[0])
        rows[0]['houses_family']=str(int(rows[0]['houses_family'])+1)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'invalid.csv'
            with open(path,'w',newline='',encoding='utf-8') as f:
                writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
            with self.assertRaisesRegex(ValueError,'do not reconcile'):
                build_kosice_nested(here/'kosice_margins.csv',path)


class SpatialCountryBoundaries(unittest.TestCase):
    def test_pipeline_rejects_cross_country_sidecar(self):
        import json,tempfile
        from pathlib import Path
        from make_acceptance_fixture import fixture
        from renovation_pipeline import run_pipeline
        joint,places,marginals=SpatialHeatingMarginals().setup_data()
        b=fixture();b['spatial_heating_calibration']={
            'country':'SK','reference_year':2021,'population_unit':'dwellings',
            'national_joint':joint,'place_totals':places,'place_marginals':marginals,
            'source_ref':'SYNTHETIC_TEST_ONLY'}
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'fixture.json';p.write_text(json.dumps(b))
            with self.assertRaisesRegex(ValueError,'country'):
                run_pipeline(p,Path(d)/'out')
