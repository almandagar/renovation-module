import unittest
from copy import deepcopy
from airtightness_research import *


def event():
    return dict(id='roof-1', completion_date='2025-06-01', treated_parts=['roof'],
                junction_scope='roof-wall seals included; other junctions retained', quality_basis='illustrative bounds',
                outcome=dict(role='assumed_achieved', metric='n50', bounds=[2, 4], source_ref='sensitivity'))


def flow():
    return dict(system='balanced', interaction_resolved=True, source_ref='synthetic resolved-flow fixture',
                recovery_basis='intentional_stream_only', operating_mode='balanced_recovery',
                infiltration_m3_h=25, window_airing_m3_h=0, intentional_m3_h=75, effective_recovery=.8,
                air_heat_capacity_wh_m3k=.33, fan_w=20, required_outdoor_m3_h=90)


class Tests(unittest.TestCase):
    def test_units(self):
        self.assertEqual(leakage(2, 'n50', 200, 250), dict(q50_m3_h=500, qE50=2.5, n50=2))

    def test_invalid_numbers(self):
        for x in (True, float('nan'), float('inf'), -1):
            with self.assertRaises(ValueError): leakage(x, 'n50', 200, 250)

    def test_area_target(self):
        r=area_prognosis([dict(id='a',area_m2=75,qE50=4,status='retained'),dict(id='b',area_m2=25,qE50=1,status='treated')],100,'illustration')
        self.assertEqual(r['qE50'],3.25)
        self.assertEqual(r['role'],'engineering_target')

    def test_area_mismatch(self):
        with self.assertRaises(ValueError): area_prognosis([dict(id='a',area_m2=90,qE50=4,status='retained')],100,'illustration')

    def test_future_event(self):
        self.assertEqual(apply_completed_event({},event(),'2025-01-01'),{})

    def test_target_rejected(self):
        e=event(); e['outcome']['role']='engineering_target'
        with self.assertRaises(ValueError): apply_completed_event({},e,'2026-01-01')

    def test_duplicate_rejected(self):
        s=apply_completed_event({},event(),'2026-01-01')
        with self.assertRaises(ValueError): apply_completed_event(s,event(),'2026-01-01')

    def test_measurement_boundary(self):
        e=event();e['outcome']['role']='measured'
        with self.assertRaises(ValueError): apply_completed_event({},e,'2026-01-01')

    def test_measured_replaces_assumption(self):
        s=apply_completed_event({},event(),'2026-01-01');e=event()
        e.update(id='windows-2',completion_date='2026-06-01',treated_parts=['windows'])
        e['outcome'].update(role='measured',bounds=[1.5,1.7],test_boundary_ref='test report')
        r=apply_completed_event(s,e,'2026-12-01')
        self.assertEqual(r['outcome']['bounds'],[1.5,1.7]);self.assertEqual(len(r['events']),2)
        self.assertEqual(s['outcome']['bounds'],[2,4])

    def test_heat_recovery(self):
        r=balanced_airflow(flow(),100)
        self.assertAlmostEqual(r['hve_w_k_m2'],.132)
        self.assertTrue(r['service_screen_pass'])

    def test_insufficient_fresh_air(self):
        f=flow();f['required_outdoor_m3_h']=101
        self.assertFalse(balanced_airflow(f,100)['service_screen_pass'])

    def test_unresolved_airflow(self):
        f=flow();f['interaction_resolved']=False
        with self.assertRaises(ValueError): balanced_airflow(f,100)

    def test_whole_concept_savings_rejected(self):
        f=flow(); f.update(effective_recovery=.67,recovery_basis='whole_concept_savings')
        with self.assertRaises(ValueError): balanced_airflow(f,100)

    def test_frost_supply_off_rejected(self):
        f=flow(); f['operating_mode']='frost_supply_off'
        with self.assertRaises(ValueError): balanced_airflow(f,100)

    def test_windows_do_not_receive_heat_recovery(self):
        f=flow(); f['window_airing_m3_h']=10
        self.assertAlmostEqual(balanced_airflow(f,100)['hve_w_k_m2'],.165)

    def test_old_baseline_incompatibility(self):
        r=baseline_check(.425,.5775,.65)
        self.assertFalse(r['old_compatible_with_infiltration']);self.assertIsNone(r['fitted_residual'])

    def test_adapter_and_input_immutability(self):
        cell=dict(id='actual-location-placeholder',archetype_id='a',area_m2=100,state={'wall':'old'},heating=dict(carrier='GAS',useful_per_final=.9))
        lib={'archetypes':{'a':dict(source_ref='synthetic',construction_period=[1900,1910],geometry={'wall':1},components={'wall':{'old':dict(source_ref='synthetic',u_w_m2k=1)}},ventilation_w_k_m2=.425,bridges_w_k_m2=0)}}
        p=[dict(id='winter',hours=100,indoor_c=20,outdoor_c=0,usable_gains_w_m2=0)]
        before=deepcopy((cell,lib,p))
        r=shadow_heat(cell,lib,p,{'winter':flow()})
        self.assertAlmostEqual(r['baseline_useful_heat_kwh'],285)
        self.assertAlmostEqual(r['candidate_useful_heat_kwh'],226.4)
        self.assertEqual(r['fan_electricity_kwh'],2)
        self.assertEqual((cell,lib,p),before)
        self.assertFalse(r['production_promoted'])
        with self.assertRaises(ValueError): shadow_heat(cell,lib,p,{})

    def test_sensitivity_arithmetic(self):
        self.assertAlmostEqual(.33*2.5*.10*3326.4*24/1000,6.586272)


if __name__=='__main__': unittest.main(verbosity=2)
