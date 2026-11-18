"""2026-11-04 source-bound lower thermal boundary / RAIII floor-gate tests.

The national Slovak SIEA example demonstrates a *possible* basement-ceiling
intervention, not 2024 site or country-specific prevalence.  No test asserts
that a Košice building has been observed with such a basement.
"""
import copy
import unittest
from sk_kosice_panel_event_bridge import (make_bundle,make_library,qualify_lower_boundaries,
        snapshot_cells,HDD_WEATHER,BOUNDARY_SOURCE, audit_2021_to_2024_component_coarsening)
from sk_panel_dated_country_input import source_input
from renovation_reconciliation import prepare_dated_panel_delivery_requests
from renovation_module import run
from renovation_stock import totals
from archetype_physics import heat,package_effect
from recipient_priority import _gain

class TestBoundedLowerBoundary(unittest.TestCase):
    def test_default_deep_has_floor_gate_but_not_floor_work(self):
        b=make_bundle(selected_strategies=['PAS_DEEP'],end_year=2025,component_passports=False)
        p=b['library']['packages']['SINGLE_LAYER_deep_from_RA_I']
        self.assertIn('floor',p['targets'])
        self.assertEqual(p['floor_gate'],'RAIII_SOURCE_BOUNDARY')
        c=next(x for x in b['opening_cells'] if x['ra_screen_prior']=='RA_I' and x['area_m2']>1000)
        after,changed,inv=package_effect(c,p,b['library'])
        self.assertNotIn('floor',changed)
        self.assertEqual(after['state']['floor'],c['state']['floor'])
        self.assertNotIn('FLOOR_INSULATION_EQUIVALENT',inv['installed_kg'])
        self.assertGreater(sum(inv['task_hours'].values()),0)
        self.assertNotIn('floor',b['scope_sensitivity']['qualified_lower_boundaries'])

    @staticmethod
    def spec(b,area=64):
        c=next(x for x in b['opening_cells'] if x['archetype_id']=='SINGLE_LAYER' and x['ra_screen_prior']=='RA_I' and x['area_m2']>1000)
        return {'place_id':c['place_id'],'family':c['archetype_id'],'ra_state':c['ra_screen_prior'],
                'area_m2':area,'boundary_type':'UNHEATED_BASEMENT_CEILING','boundary_factor':.55,
                'source_ref':BOUNDARY_SOURCE,'evidence_class':'EXPLICIT_SCENARIO_HYPOTHESIS'}

    def test_standard_raiii_70_does_not_require_floor_even_when_basement_hypothesized(self):
        b=make_bundle(selected_strategies=['PAS_DEEP'],end_year=2025,component_passports=False)
        spec=self.spec(b)
        special=qualify_lower_boundaries(b['opening_cells'],b['library'],[spec],70)
        c=next(z for z in special if z['lower_boundary_qualification']['boundary_type']=='UNHEATED_BASEMENT_CEILING')
        e=c['lower_boundary_qualification'];self.assertFalse(e['required_for_raiii'])
        self.assertEqual(e['reason'],'FLOOR_NOT_NEEDED_FOR_DECLARED_RAIII')
        self.assertLess(e['post_envelope_without_floor_kwh_m2a'],70)
        _,changed,inv=package_effect(c,b['library']['packages']['SINGLE_LAYER_deep_from_RA_I'],b['library'])
        self.assertNotIn('floor',changed)
        self.assertNotIn('FLOOR_INSULATION_EQUIVALENT',inv['installed_kg'])

    def test_stricter_performance_objective_53_can_enable_only_source_hypothesized_cell(self):
        a=make_bundle(selected_strategies=['PAS_DEEP'],end_year=2025,component_passports=False)
        spec=self.spec(a)
        b=make_bundle(selected_strategies=['PAS_DEEP'],end_year=2025,component_passports=False,
                      qualified_lower_boundaries=[spec],raiii_service_target_kwh_m2a=53)
        c=next(x for x in b['opening_cells'] if x['lower_boundary_qualification']['boundary_type']=='UNHEATED_BASEMENT_CEILING')
        e=c['lower_boundary_qualification']
        self.assertTrue(e['required_for_raiii']);self.assertGreater(e['post_envelope_without_floor_kwh_m2a'],53)
        self.assertLess(e['post_envelope_with_floor_kwh_m2a'],53)
        after,changes,inv=package_effect(c,b['library']['packages']['SINGLE_LAYER_deep_from_RA_I'],b['library'])
        self.assertIn('floor',changes)
        self.assertGreater(inv['installed_kg']['FLOOR_INSULATION_EQUIVALENT'],0)
        self.assertGreater(_gain(c,b['library'],b['library']['packages']['SINGLE_LAYER_deep_from_RA_I']),0)
        unknown=next(x for x in b['opening_cells'] if x['ra_screen_prior']=='RA_I' and x['archetype_id']=='SINGLE_LAYER' and x['lower_boundary_qualification']['boundary_type']=='UNRESOLVED' and x['area_m2']>0)
        u_after,u_changed,u_inv=package_effect(unknown,b['library']['packages']['SINGLE_LAYER_deep_from_RA_I'],b['library'])
        self.assertNotIn('floor',u_changed)
        self.assertNotIn('FLOOR_INSULATION_EQUIVALENT',u_inv['installed_kg'])
        for kind in ('area_m2','buildings','dwellings'):
            self.assertAlmostEqual(totals(a['opening_cells'])[kind],totals(b['opening_cells'])[kind],places=4)

    def test_ra_coarsening_decomposition_identifies_heat_gap(self):
        z=audit_2021_to_2024_component_coarsening()
        self.assertAlmostEqual(z['year_2021_detailed_component_joint_gwh'],341.93559494,places=5)
        self.assertGreater(z['coarsening_increment_gwh'],24)
        self.assertLess(z['three_year_survivor_progression_effect_gwh'],0)
        self.assertAlmostEqual(z['reconciliation_residual_gwh'],0,places=8)
        self.assertEqual(z['next_physical_owner'],'KEEP_2021_COMPONENT_COMBINATIONS_IN_DATED_STOCK; RA_CLASSIFICATION_ONLY')

    def test_unqualified_floor_not_assumed_to_have_zero_heat_loss(self):
        b=make_bundle(selected_strategies=['PAS_DEEP'],end_year=2025,component_passports=False)
        c=next(x for x in b['opening_cells'] if x['archetype_id']=='SINGLE_LAYER' and x['ra_screen_prior']=='RA_I' and x['area_m2']>1000)
        self.assertEqual(c['lower_boundary_qualification']['boundary_type'],'UNRESOLVED')
        self.assertGreater(b['library']['archetypes']['SINGLE_LAYER']['geometry']['floor'],0)
        self.assertGreater(b['library']['archetypes']['SINGLE_LAYER']['components']['floor'][c['state']['floor']]['u_w_m2k'],0)
        self.assertGreater(heat(c,b['library'],HDD_WEATHER)['useful_heat_kwh'],0)

    def test_explicit_cold_floor_comfort_exception_not_raiii_automatic(self):
        base=make_bundle(selected_strategies=['PAS_DEEP'],end_year=2025,component_passports=False)
        spec=self.spec(base)
        spec['comfort_defect_source_ref']='EXPLICIT_MODEL_PRIOR_COLD_FLOOR_NOT_OBSERVED_SITE'
        b=make_bundle(selected_strategies=['PAS_DEEP'],end_year=2025,component_passports=False,
                      qualified_lower_boundaries=[spec],raiii_service_target_kwh_m2a=70)
        c=next(x for x in b['opening_cells'] if x['lower_boundary_qualification']['boundary_type']=='UNHEATED_BASEMENT_CEILING')
        d=c['lower_boundary_qualification']
        self.assertFalse(d['required_for_raiii'])
        self.assertEqual(d['reason'],'SOURCE_QUALIFIED_COLD_FLOOR_COMFORT_DEFECT')
        _,components,inv=package_effect(c,b['library']['packages']['SINGLE_LAYER_deep_from_RA_I'],b['library'])
        self.assertIn('floor',components)
        self.assertGreater(inv['installed_kg']['FLOOR_INSULATION_EQUIVALENT'],0)

    def test_no_unqualified_ground_or_heated_space_as_basement(self):
        b=make_bundle(selected_strategies=['PAS_DEEP'],end_year=2025,component_passports=False)
        spec=self.spec(b);spec['boundary_type']='GROUND_CONTACT'
        with self.assertRaisesRegex(ValueError,'Ground or heated-neighbour'):
            qualify_lower_boundaries(b['opening_cells'],b['library'],[spec],53)
        spec['boundary_type']='UNHEATED_BASEMENT_CEILING';spec['source_ref']=''
        with self.assertRaisesRegex(ValueError,'explicit scenario hypothesis'):
            qualify_lower_boundaries(b['opening_cells'],b['library'],[spec],53)
        spec['source_ref']=BOUNDARY_SOURCE;spec['area_m2']=1e9
        with self.assertRaisesRegex(ValueError,'exceeds parent'):
            qualify_lower_boundaries(b['opening_cells'],b['library'],[spec],53)

    def test_narrow_stress_2025_event_finishes_and_only_qualified_floor_uses_resource(self):
        b0=make_bundle(selected_strategies=['PAS_DEEP'],end_year=2025,component_passports=False)
        b=make_bundle(selected_strategies=['PAS_DEEP'],end_year=2025,component_passports=False,
                      qualified_lower_boundaries=[self.spec(b0,area=128)],raiii_service_target_kwh_m2a=53)
        result=run(b,b['scenarios'][0])
        # Depending on resource / ranking order, the 128-m² qualified cohort
        # may or may not be selected in the first year. It is never mandatory.
        floor_completed=[z for z in result['ledger'] if z.get('status')=='COMPLETED' and 'floor' in z.get('components',[])]
        for z in floor_completed:
            self.assertTrue(z['cell_id'].startswith('PAS_DEEP'))
            self.assertGreater(z['inventory']['installed_kg']['FLOOR_INSULATION_EQUIVALENT'],0)
        for kind in ('area_m2','buildings','dwellings'):
            self.assertAlmostEqual(result['initial_totals'][kind],result['final_totals'][kind],places=4)
        self.assertEqual(result['completion_evidence'],'MODELLED_CONDITIONAL_NOT_OBSERVED')


# V07 source-conditional component passports; RA stock labels do not define endpoints.
from copy import deepcopy
from renovation_reconciliation import prepare_component_dated_panel_state

class TestComponentPassports(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=source_input()
        cls.dated=prepare_component_dated_panel_state(cls.source)
        cls.bundle=make_bundle(selected_strategies=['PI_CONVENTIONAL'],end_year=2025)

    def test_2021_physical_passport_shares_per_original_form(self):
        for fam,rows in self.source['component_passports_2021'].items():
            self.assertAlmostEqual(sum(r['share'] for r in rows),1.,places=9)
            self.assertEqual(len({r['mask'] for r in rows}),len(rows))
            self.assertGreater(len(rows),3)
            self.assertTrue(all(len(r['mask'])==4 for r in rows))

    def test_ra_labels_not_component_variants_in_current_library(self):
        lib=self.bundle['library'];self.assertIn('COMPONENT_PASSPORT',self.bundle['physical_state_interpretation'])
        for fam,a in lib['archetypes'].items():
            for k,variants in a['components'].items():
                self.assertIn('passport_0',variants);self.assertIn('passport_1',variants)
                self.assertFalse(any(k.startswith('current_RA') for k in variants))
            self.assertIn(f'{fam}_deep_from_C1110',lib['packages'])
            self.assertNotIn(f'{fam}_deep_from_RA_I',lib['packages'])

    def test_source_state_and_future_endpoint_are_separate(self):
        lib=self.bundle['library'];candidate=next(c for c in self.bundle['opening_cells']
                if c['archetype_id']=='SINGLE_LAYER' and c['component_mask']=='1110')
        pkg=lib['packages']['SINGLE_LAYER_deep_from_C1110']
        before=heat(candidate,lib,HDD_WEATHER)['useful_heat_kwh'];after,changed,inv=package_effect(candidate,pkg,lib)
        after_q=heat(after,lib,HDD_WEATHER)['useful_heat_kwh']
        self.assertLess(after_q,before)
        self.assertEqual(candidate['component_mask'],'1110')
        self.assertEqual(after['opening_stock_ra_descriptor_research_only'],candidate['opening_stock_ra_descriptor_research_only'])
        self.assertEqual(pkg['endpoint_contract'],'PATHWAY_PHYSICAL_VARIANT_INDEPENDENT_OF_OPENING_STOCK_RA')
        self.assertNotIn('floor',changed)
        self.assertNotIn('FLOOR_INSULATION_EQUIVALENT',inv['installed_kg'])

    def test_pi_does_not_retrofit_already_pi_quality_component_state(self):
        cells=[c for c in self.bundle['opening_cells'] if c['component_mask']=='1110']
        self.assertTrue(cells)
        self.assertTrue(all(not c['eligible_fabric_pi'] for c in cells))
        self.assertTrue(all(c['eligible_fabric_deep'] for c in cells))

    def test_no_mandatory_floor_or_heating_device(self):
        b=self.bundle
        self.assertEqual({c['heating']['carrier'] for c in b['opening_cells']},{'UNKNOWN_HEATING_CARRIER_SERVICE_PROXY'})
        self.assertTrue(all('floor' not in b['library']['packages'][e['package_id']]['targets']
                            for e in b['scenarios'][0]['events']))
        self.assertTrue(all('component_mask' in e['selector'] for e in b['scenarios'][0]['events']))
        self.assertTrue(all('ra_screen_prior' not in e['selector'] for e in b['scenarios'][0]['events']))

    def test_source_cohort_conservation(self):
        b=self.bundle;t=totals(b['opening_cells']);source=self.dated['survival']
        for k,target in [('area_m2','survivor_conditioned_area_m2'),('dwellings','survivor_dwellings'),('buildings','survivor_buildings')]:
            self.assertAlmostEqual(t[k],source[target],places=4)
        self.assertEqual(len({c['id'] for c in b['opening_cells']}),len(b['opening_cells']))

    def test_component_coarsening_does_not_inflate_energy(self):
        q=self.dated['component_energy'];self.assertAlmostEqual(q['2024_component_physics_gwh'],337.5424616988179,places=4)
        self.assertLess(q['2024_component_physics_gwh'],q['2021_component_legacy_weather_same_survivor_gwh'])
        self.assertGreater(360.80039362885185-q['2024_component_physics_gwh'],20)
        self.assertAlmostEqual(sum(heat(c,self.bundle['library'],HDD_WEATHER)['useful_heat_kwh']
                                   for c in self.bundle['opening_cells'])/1e6,q['2024_component_physics_gwh'],places=5)

    def test_2021_floor_priors_are_explicit_sensitivity_not_observed(self):
        default=source_input()
        zero=source_input(floor_after_three=0)
        self.assertEqual(default['lower_boundary_2021_effective_after_three_prior'],.25)
        self.assertEqual(zero['lower_boundary_2021_effective_after_three_prior'],0)
        self.assertTrue(all(r['mask']!='1111' for v in zero['component_passports_2021'].values() for r in v if r['share']>1e-12))
        no_floor=prepare_component_dated_panel_state(zero)
        self.assertGreater(no_floor['component_energy']['2024_component_physics_gwh'],
                           self.dated['component_energy']['2024_component_physics_gwh'])
        self.assertAlmostEqual(no_floor['survival']['survivor_conditioned_area_m2'],
                               self.dated['survival']['survivor_conditioned_area_m2'],places=5)

    def test_dated_progression_zero_is_well_defined(self):
        source=source_input(technical_progression=0)
        z=prepare_component_dated_panel_state(source)
        self.assertAlmostEqual(z['component_energy']['2022_2024_modelled_change_gwh'],0,places=6)
        self.assertAlmostEqual(z['survival']['survivor_conditioned_area_m2'],
                               self.dated['survival']['survivor_conditioned_area_m2'],places=5)

    def test_transition_hazard_invalid_rejected(self):
        wrong=deepcopy(self.source);wrong['technical_progression_given_exposure']=40
        with self.assertRaisesRegex(ValueError,'rate or population share|hazard'):
            prepare_component_dated_panel_state(wrong)

    def test_duplicate_component_population_rejected(self):
        bad=deepcopy(self.source);key='SINGLE_LAYER';bad['component_passports_2021'][key][0]['share']+=.3
        with self.assertRaisesRegex(ValueError,'shares'):
            prepare_component_dated_panel_state(bad)

    def test_independent_pas_package_does_not_require_fictitious_fourth_RA(self):
        lib=make_library(component_passports=True)
        a=lib['archetypes']['LATER_P114_P115_PS82']['components']['wall']
        self.assertTrue(all(k not in a for k in ('RA_IV','current_RA_I','current_RA_II','current_RA_III')))
        for mask in ('0000','1110'):
            pi=lib['packages'][f'LATER_P114_P115_PS82_pi_from_C{mask}']
            deep=lib['packages'][f'LATER_P114_P115_PS82_deep_from_C{mask}']
            self.assertNotEqual(pi['targets']['wall'],deep['targets']['wall'])

    def test_ra60_uses_fixed_original_technical_reference_not_opening_ra(self):
        b=self.bundle
        from sk_kosice_panel_event_bridge import P
        for c in b['opening_cells']:
            base=c['ra60_original_technical_baseline_kwh_m2a']
            current=heat(c,b['library'],HDD_WEATHER)['useful_heat_kwh']/c['area_m2']
            self.assertGreaterEqual(base,current-1e-8)
            self.assertGreater(base,0)
        self.assertFalse(any(c.get('deep_achieved') for c in b['opening_cells']))

    def test_universal_floor_legacy_switch_rejected_for_component_passports(self):
        with self.assertRaisesRegex(ValueError,'Universal floor'):
            make_bundle(selected_strategies=['PAS_DEEP'],end_year=2025,deep_floor=True)

    def test_legacy_three_ra_method_remains_explicit_opt_in_diagnostic(self):
        old=make_library(component_passports=False)
        self.assertIn('current_RA_I',old['archetypes']['SINGLE_LAYER']['components']['wall'])
        self.assertNotIn('current_RA_I',self.bundle['library']['archetypes']['SINGLE_LAYER']['components']['wall'])

    def test_current_one_year_scheduler_accepts_component_passports(self):
        r=run(self.bundle,self.bundle['scenarios'][0])
        for key in ('area_m2','dwellings','buildings'):
            self.assertAlmostEqual(r['initial_totals'][key],r['final_totals'][key],places=4)
        self.assertEqual(r['completion_evidence'],'MODELLED_CONDITIONAL_NOT_OBSERVED')
        self.assertGreater(sum(v['work_area_m2'] for v in r['ledger'] if v.get('status')=='COMPLETED'),0)
        self.assertTrue(all(v['amount'] <= self.bundle['capacity'][v['region']][str(v['year'])][v['kind']][v['resource']]+1e-4
                     for v in r['resource_use']))


if __name__=='__main__':unittest.main(verbosity=2)
