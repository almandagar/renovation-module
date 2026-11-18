"""Guarded 2024 model snapshot -> EXISTING physical event scheduler tests."""
import unittest,copy
from sk_kosice_panel_event_bridge import make_bundle,HDD_WEATHER,snapshot_cells,make_library
from sk_panel_dated_country_input import source_input
from renovation_reconciliation import prepare_dated_panel_delivery_requests
from renovation_module import run
from archetype_physics import heat

class TestConditionalPanelPhysicalEvents(unittest.TestCase):
    def short(self,strategies=('PI_CONVENTIONAL',),cap='CENTRAL_CONDITIONAL',**kwargs):
        return make_bundle(cap,selected_strategies=list(strategies),end_year=2025,**kwargs)
    def test_research_snapshot_parent_is_2024_not_2011(self):
        b=self.short();self.assertEqual(b['history_start'],'2024-12-31')
        self.assertEqual(b['research_opening_snapshot']['evidence_class'],'CONDITIONAL_MODEL_PRIOR_NOT_OBSERVED')
        self.assertAlmostEqual(sum(x['area_m2'] for x in b['opening_cells']),3375986.9319372834,places=4)
    def test_no_future_rewrite_to_2011_history(self):
        b=self.short();del b['research_opening_snapshot']
        with self.assertRaisesRegex(ValueError,'research-only fixed-cohort snapshot'):run(b,b['scenarios'][0])
    def test_false_observed_2024_snapshot_rejected(self):
        b=self.short();b['research_opening_snapshot']['evidence_class']='OBSERVED'
        with self.assertRaisesRegex(ValueError,'research-only fixed-cohort snapshot'):run(b,b['scenarios'][0])
    def test_unqualified_2024_site_pass_rejected(self):
        b=self.short();b['scenarios'][0]['events'][0].pop('site_access_basis')
        with self.assertRaisesRegex(ValueError,'site access and commissioning'):run(b,b['scenarios'][0])
    def test_unqualified_commissioning_rejected(self):
        b=self.short();b['scenarios'][0]['events'][0]['commissioning_basis']='PENDING'
        with self.assertRaisesRegex(ValueError,'site access and commissioning'):run(b,b['scenarios'][0])
    def test_all_2024_source_components_and_carrier_unknown(self):
        b=self.short();r=run(b,b['scenarios'][0]);self.assertEqual(r['completion_evidence'],'MODELLED_CONDITIONAL_NOT_OBSERVED')
        self.assertEqual({c['heating']['carrier'] for c in b['opening_cells']},{'UNKNOWN_HEATING_CARRIER_SERVICE_PROXY'})
        for z in r['ledger']:
            if z.get('status')=='COMPLETED':self.assertIn('NOT_OBSERVED',z['evidence_class'])
    def test_conservation_and_known_task_caps(self):
        b=self.short();r=run(b,b['scenarios'][0]);
        for key in ('area_m2','buildings','dwellings'):
            self.assertAlmostEqual(r['initial_totals'][key],r['final_totals'][key],places=4)
        for z in r['resource_use']:
            lim=b['capacity'][z['region']][str(z['year'])][z['kind']][z['resource']]
            self.assertLessEqual(z['amount'],lim+1e-5)
    def test_no_duplicate_work_for_same_target(self):
        b=self.short();e=copy.deepcopy(b['scenarios'][0]['events'][0]);e['id']='repeat';e['start_date']='2025-12-16';e['completion_date']='2025-12-20';b['scenarios'][0]['events'].append(e)
        r=run(b,b['scenarios'][0]);self.assertEqual(r['completion_evidence'],'MODELLED_CONDITIONAL_NOT_OBSERVED')
        self.assertTrue(all(x['status'] in ('START_ACCOUNT','COMPLETED') for x in r['ledger']))
    def test_pas_future_finance_not_a_cap(self):
        b=self.short(strategies=('PAS_DEEP',));self.assertNotIn('finance',str(b['capacity']).lower());
        self.assertGreater(sum(e['area_m2'] for e in b['scenarios'][0]['events']),0)
    def test_HDE_PI_scope_not_less_than_PI_under_same_caps(self):
        a=self.short(strategies=('PI_CONVENTIONAL',))
        b=self.short(strategies=('HDE_INDUSTRIAL',),fabric_mode_overrides={'HDE_INDUSTRIAL':'pi'})
        p=run(a,a['scenarios'][0]);h=run(b,b['scenarios'][0]);
        f=lambda r:sum(z['work_area_m2'] for z in r['ledger'] if z.get('status')=='COMPLETED')
        self.assertGreaterEqual(f(h)+1e-5,f(p))
    def test_deep_floor_sensitivity_is_not_silent(self):
        # V06 blanket floor work survives only as an explicit legacy diagnostic.
        # V07 component-passport production research never makes it mandatory.
        legacy=self.short(strategies=('PAS_DEEP',),component_passports=False,deep_floor=True)
        current=self.short(strategies=('PAS_DEEP',))
        self.assertIn('floor',legacy['library']['packages']['SINGLE_LAYER_deep_from_RA_I']['targets'])
        self.assertNotIn('floor',current['library']['packages']['SINGLE_LAYER_deep_from_C0000']['targets'])
    def test_2011_main_fixture_unmodified(self):
        from make_acceptance_fixture import fixture
        b=fixture();r=run(b,b['scenarios'][0]);self.assertEqual(r['initial_totals']['area_m2'],1000)
        self.assertIsNone(r['research_opening_snapshot'])

if __name__=='__main__':unittest.main(verbosity=2)
