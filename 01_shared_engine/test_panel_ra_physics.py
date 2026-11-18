"""Source-conditioned physical RA sidecar; tests are not empirical validation."""
from copy import deepcopy
from pathlib import Path
import json,tempfile,unittest
from sk_kosice_panel_ra_country_input import physical_specs
from renovation_reconciliation import screen_panel_ra_service_and_packages
from renovation_pipeline import run_pipeline
from make_acceptance_fixture import fixture
class TestPanelRAPhysics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec=physical_specs()
        cls.r=screen_panel_ra_service_and_packages(cls.spec)
    def test_parent_population(self):
        p=self.r['population']
        self.assertAlmostEqual(p['buildings'],2701.462207792208,places=5)
        self.assertAlmostEqual(p['dwellings'],60190.51877599867,places=5)
    def test_ra_candidates_sum_to_one_per_family(self):
        for f in self.r['ra_groups']:
            self.assertAlmostEqual(sum(f['ra_technical_probabilities'].values()),1.)
            self.assertGreater(f['ra_technical_probabilities']['RA_I'],.1)
    def test_ra_not_conflated_with_three_reported_flags(self):
        all_reported=next(x['share'] for x in self.r['reporting_joint']['rows'] if all(x['flags'].values()))
        for f in self.r['ra_groups']:
            self.assertNotAlmostEqual(f['ra_technical_probabilities']['RA_III_TECHNICAL_CANDIDATE'], all_reported)
    def test_same_recipients_equal_service(self):
        packs=self.r['package_comparison']
        self.assertAlmostEqual(packs['PI']['requested_qualified_area_m2'],packs['PAS']['requested_qualified_area_m2'])
        self.assertAlmostEqual(packs['PAS']['expected_affected_buildings'],packs['HDE']['expected_affected_buildings'])
        self.assertEqual(packs['HDE']['equipment_heat_and_DHW'], 'NOT_INCLUDED_DIFFERENT_NUMERICAL_OWNER')
    def test_better_package_not_worse_heat(self):
        z=self.r['package_comparison']
        self.assertGreater(z['PI']['useful_heat_savings_kwh_a'],0)
        self.assertGreaterEqual(z['PAS']['useful_heat_savings_kwh_a'],z['PI']['useful_heat_savings_kwh_a'])
        self.assertAlmostEqual(z['HDE']['useful_heat_savings_kwh_a'],z['PAS']['useful_heat_savings_kwh_a'])
    def test_fabric_material_not_double_counted(self):
        z=self.r['package_comparison']
        self.assertLess(z['PI']['material_and_component_work']['additional_eps_kg_equivalent'],
                       z['PAS']['material_and_component_work']['additional_eps_kg_equivalent'])
        self.assertEqual(z['PI']['material_and_component_work']['floor_m2'],0)
        self.assertEqual(z['PAS']['material_and_component_work']['floor_m2'],0)
        legacy=screen_panel_ra_service_and_packages(physical_specs(legacy_universal_floor=True))
        self.assertGreater(legacy['package_comparison']['PAS']['material_and_component_work']['floor_m2'],0)
        self.assertGreaterEqual(legacy['package_comparison']['PAS']['useful_heat_savings_kwh_a'],
                                z['PAS']['useful_heat_savings_kwh_a'])
    def test_no_pas_hde_finance_veto(self):
        z=self.r['package_comparison']
        for p in ('PAS','HDE'):self.assertIn('NOT_APPLICABLE',z[p]['finance_gate'])
    def test_bad_area_source(self):
        v=deepcopy(self.spec);v['area_source_ref']=''
        with self.assertRaisesRegex(ValueError,'provenance'):screen_panel_ra_service_and_packages(v)
    def test_bad_floor_probability(self):
        v=deepcopy(self.spec);v['floor_after_three_effective']=1.5
        with self.assertRaises(ValueError):screen_panel_ra_service_and_packages(v)
    def test_bad_family_u(self):
        v=deepcopy(self.spec);v['profiles']['SINGLE_LAYER']['reference_u']['wall']=-1
        with self.assertRaises(ValueError):screen_panel_ra_service_and_packages(v)
    def test_warmer_service_weather_increases_heat(self):
        low=screen_panel_ra_service_and_packages(physical_specs(hdd=2800))
        high=screen_panel_ra_service_and_packages(physical_specs(hdd=4000))
        self.assertGreater(high['ra_groups'][0]['expected_current_q_kwh_m2a'],low['ra_groups'][0]['expected_current_q_kwh_m2a'])
    def test_pipeline_research_only_and_nine_scenarios_unchanged(self):
        b=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);p=base/'b.json';p.write_text(json.dumps(b))
            z=run_pipeline(p,base/'old');old=json.loads(z['cohort_results'].read_text())
            spec=deepcopy(self.spec);spec['country']='TEST'
            b['panel_ra_technical_screen']=spec;p.write_text(json.dumps(b))
            z=run_pipeline(p,base/'new');new=json.loads(z['cohort_results'].read_text())
            self.assertEqual(old,new)
            self.assertFalse(json.loads(z['manifest'].read_text())['runtime_promoted'])
            self.assertIn('panel_ra_technical_screen',z)
    def test_crosscountry_rejected(self):
        b=fixture();b['panel_ra_technical_screen']=self.spec
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'b.json';p.write_text(json.dumps(b))
            with self.assertRaisesRegex(ValueError,'country boundary'):run_pipeline(p,Path(tmp)/'out')
if __name__=='__main__':unittest.main()
