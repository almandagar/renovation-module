"""Regression tests for dated panel candidate request handoff. No adoption validation."""
import json, tempfile, unittest
from copy import deepcopy
from pathlib import Path
from renovation_reconciliation import prepare_dated_panel_delivery_requests
from renovation_pipeline import run_pipeline
from make_acceptance_fixture import fixture
from sk_panel_dated_country_input import source_input

class TestPanelDatedRequests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec=source_input(); cls.r=prepare_dated_panel_delivery_requests(cls.spec)
    def test_2024_fixed_cohort_survivors(self):
        r=self.r; self.assertLess(r['survival']['survivor_dwellings'],60191)
        self.assertGreater(r['survival']['survivor_dwellings'],60000)
        self.assertEqual(r['reference_2024'],'MODELLED_FIXED_2021_COHORT_SURVIVOR_NOT_OBSERVED_CITY_STOCK')
    def test_source_family_dwellings_are_conserved(self):
        x={k:0 for k in ('SINGLE_LAYER','RC_EPS_SANDWICH','LATER_P114_P115_PS82')}
        for r in self.r['place_family_2024_priors']:x[r['family']]+=r['2021_source_dwellings']
        for f in self.spec['family_stock']:
            self.assertAlmostEqual(x[f['family']],f['dwellings'],places=5)
    def test_2024_area_RA_conservation(self):
        z=self.r['2024_technical_ra_survivor_area_m2']
        self.assertAlmostEqual(sum(z.values()),self.r['survival']['survivor_conditioned_area_m2'],places=5)
        self.assertTrue(all(v>=0 for v in z.values()))
    def test_observed_2024_stock_not_asserted(self):
        self.assertIn('NOT_OBSERVED',self.r['reference_2024'])
        self.assertIn('NOT_INFERRED',self.r['method']['2024_newbuild_outside_fixed_cohort'])
    def test_all_nine_strategies_each_year(self):
        r=self.r; self.assertEqual(len(r['strategy_annual_requests']),9*11)
        self.assertEqual(len(r['strategy_recipient_rankings']),9*66)
        self.assertEqual(len(r['conditional_capacity_frontiers']),9*11*3)
        self.assertTrue(all(q['event_status']=='REQUEST_NOT_COMMITTED_OR_COMPLETED' for q in r['strategy_annual_requests']))
    def test_pas_hde_finance_absent_priority(self):
        for q in self.r['strategy_annual_requests']:
            if q['pathway'] in ('PAS','HDE'): self.assertEqual(q['financing_rule'],'NO_FINANCE_VETO_FUTURE_PRIORITY_RENOVATION')
    def test_HDE_fabric_at_least_PI(self):
        a=next(q for q in self.r['strategy_annual_requests'] if q['strategy']=='PI_CONVENTIONAL')
        b=next(q for q in self.r['strategy_annual_requests'] if q['strategy']=='HDE_ELECTRIFICATION')
        self.assertGreaterEqual(b['requested_fabric_area_m2'],a['requested_fabric_area_m2'])
    def test_yearly_frontier_upper_bound_and_nonnegative(self):
        for q in self.r['conditional_capacity_frontiers']:
            self.assertLessEqual(q['conditional_max_start_m2'],q['requested_m2']+1e-6)
            self.assertGreaterEqual(q['unmet_request_m2'],-1e-6)
    def test_coverage_unique_never_exceeds_cohort(self):
        eligible=sum(x['2024_eligible_not_good_area_m2'] for x in self.r['place_family_2024_priors'])
        for q in self.r['cumulative_coverage_alternatives']:
            self.assertLessEqual(q['max_unique_if_no_repeats_m2'],eligible+1e-6)
            self.assertLessEqual(q['expected_unique_if_independent_random_reselection_m2'],q['max_unique_if_no_repeats_m2']+1e-6)
    def test_missing_distinct_diffusion_carrier_left_unknown(self):
        for q in self.r['strategy_recipient_rankings']:
            self.assertEqual(q['status'],'CONDITIONAL_RECIPIENT_ORDER_NOT_COMMITTED_DELIVERY')
        self.assertTrue(any('UNIDENTIFIED' in q['missing_local_determinant'] for q in self.r['strategy_recipient_rankings']))
    def test_bad_local_double_count_rejected(self):
        bad=deepcopy(self.spec);bad['place_family_dwellings'].append(deepcopy(bad['place_family_dwellings'][0]))
        with self.assertRaisesRegex(ValueError,'Duplicate place-family'):prepare_dated_panel_delivery_requests(bad)
    def test_unsupported_country_rejected(self):
        bad=deepcopy(self.spec);bad['country']='CZ'
        with self.assertRaisesRegex(ValueError,'qualifies only SK'):prepare_dated_panel_delivery_requests(bad)
    def test_absent_actual_capacity_does_not_zero_requests(self):
        for q in self.r['strategy_annual_requests']:
            self.assertGreater(q['requested_fabric_area_m2'],0)
            self.assertEqual(q['actor_catchment_capacity'],'UNKNOWN_NOT_ZERO')
    def test_pipeline_research_nonbooking(self):
        b=fixture();b['country']='SK'
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'source.json';p.write_text(json.dumps(b));
            baseline=run_pipeline(p,Path(tmp)/'base')
            base=json.loads(baseline['cohort_results'].read_text())
            b['dated_panel_recipient_requests']=deepcopy(self.spec)
            p.write_text(json.dumps(b))
            newer=run_pipeline(p,Path(tmp)/'research')
            new=json.loads(newer['cohort_results'].read_text())
            self.assertEqual(base,new)
            s=json.loads(newer['dated_panel_recipient_requests'].read_text())
            self.assertFalse(json.loads(newer['manifest'].read_text())['runtime_promoted'])
            self.assertEqual(s['acceptance'],'RESEARCH_PRIOR__NO_PHYSICAL_EVENTS_COMMITTED_NO_RUNTIME_PROMOTION')
    def test_crosscountry_pipeline_rejected(self):
        b=fixture();b['dated_panel_recipient_requests']=self.spec
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'source.json';p.write_text(json.dumps(b))
            with self.assertRaisesRegex(ValueError,'country boundary'):run_pipeline(p,Path(tmp)/'out')

if __name__=='__main__':unittest.main()
