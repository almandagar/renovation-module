"""Contract tests for city-physical-tests/2; no production data required."""
import copy
import json
import unittest
from pathlib import Path
from city_physical_tests import run, evaluate, periods_of

HERE=Path(__file__).parent

def sample():
    return json.loads((HERE/'SYNTHETIC_EXAMPLE.json').read_text(encoding='utf-8'))

class CityPhysicalTests(unittest.TestCase):
    def test_forward_energy(self):
        self.assertAlmostEqual(run(sample())['results'][0]['hypotheses'][0]['required_useful_kwh'],52.8)
    def test_no_mutation(self):
        d=sample(); prior=copy.deepcopy(d);run(d);self.assertEqual(d,prior)
    def test_inverse_temperatures(self):
        inv=run(sample())['results'][0]['hypotheses'][0]['constant_setpoint_inversion']
        self.assertAlmostEqual(inv['temperature_c_low'], 19.7222, places=3)
        self.assertAlmostEqual(inv['temperature_c_high'], 20.4167, places=3)
    def test_comfort_energy(self):
        v=run(sample())['results'][0]['hypotheses'][0]
        self.assertAlmostEqual(v['required_for_declared_comfort_kwh'],47.04)
        self.assertEqual(v['comfort_heat_shortfall_kwh'],0)
    def test_national_falsification_separate(self):
        d=sample();d['model_snapshot']['predictions']['p']['useful_heat_kwh']=500
        r=run(d)['results'][0]
        self.assertEqual(r['physical_hypothesis_status'],'ONE_COMPATIBLE_NOT_IDENTIFIED')
        self.assertEqual(r['national_prediction_status'],'NATIONAL_PREDICTION_OUTSIDE_OBSERVATION')
        self.assertAlmostEqual(r['national_prediction_distance_to_observation_kwh'],446)
    def test_structural_challenge_without_meter(self):
        d=sample();d['cases'][0]['observation']={'mode':'NONE'}
        d['model_snapshot']['predictions']['p']['useful_heat_kwh']=500
        r=run(d)['results'][0]
        self.assertFalse(r['national_prediction_within_tested_physical_envelope'])
        self.assertEqual(r['national_tested_envelope_verdict'],'STRUCTURAL_SCREEN_NOT_EMPIRICAL_VALIDATION')
        self.assertEqual(r['national_prediction_status'],'NO_INDEPENDENT_ENERGY_TEST')
    def test_input_bounds(self):
        d=sample();d['cases'][0]['hypotheses'][0]['usable_gains_w_by_period']['day']=1000000
        with self.assertRaises(ValueError):run(d)
        d=sample();d['cases'][0]['hypotheses'][0]['indoor_c_by_period']['day']=250
        with self.assertRaises(ValueError):run(d)
    def test_no_energy_observation_physical_mode(self):
        d=sample();d['cases'][0]['observation']={'mode':'NONE'}
        r=run(d)['results'][0]
        self.assertEqual(r['physical_hypothesis_status'],'UNCONSTRAINED_PHYSICAL_SCREEN')
        self.assertEqual(r['national_prediction_status'],'NO_INDEPENDENT_ENERGY_TEST')
        self.assertIsNone(r['hypotheses'][0]['constant_setpoint_inversion'])
    def test_carrier_conversion(self):
        d=sample(); c=d['cases'][0]
        c['observation']={'mode':'CARRIER','boundary':copy.deepcopy(c['boundary']),
            'carriers':[{'carrier':'GAS','final_low_kwh':65,'final_high_kwh':70,
             'space_heat_fraction_low':1,'space_heat_fraction_high':1,
             'useful_per_final_low':0.8,'useful_per_final_high':0.8,
             'source_ref':'SYNTHETIC_GAS','source_family_id':'GAS_METER',
             'instrument':'METER','conversion_basis':'ASSUMED_BOILER_EFFICIENCY'}]}
        r=run(d)['results'][0]
        self.assertEqual(r['observation_mode'],'CARRIER')
        self.assertEqual(r['observed_useful_heat_interval_kwh'],[52,56])
    def test_heat_pump_spf_ambient_once(self):
        d=sample();c=d['cases'][0]
        c['observation']={'mode':'CARRIER','boundary':copy.deepcopy(c['boundary']),
         'carriers':[{'carrier':'HP_ELECTRICITY','final_low_kwh':16,'final_high_kwh':18,
           'space_heat_fraction_low':1,'space_heat_fraction_high':1,
           'useful_per_final_low':3,'useful_per_final_high':3,
           'source_ref':'SYN_HP','source_family_id':'HP','instrument':'METER',
           'conversion_basis':'ASSUMED_SPF_INCLUDES_AMBIENT'}]}
        self.assertEqual(run(d)['results'][0]['observed_useful_heat_interval_kwh'],[48,54])
    def test_duplicate_carrier_rejected(self):
        d=sample(); c=d['cases'][0]; c['observation']={'mode':'CARRIER','boundary':copy.deepcopy(c['boundary']),
         'carriers':[{ 'carrier':'GAS','final_low_kwh':10,'final_high_kwh':10,
           'space_heat_fraction_low':1,'space_heat_fraction_high':1,
           'useful_per_final_low':0.8,'useful_per_final_high':0.8,
           'source_ref':'S','source_family_id':'SF','instrument':'M','conversion_basis':'ASSUMED'}]*2}
        with self.assertRaises(ValueError):run(d)
    def test_energy_population_boundary(self):
        d=sample(); d['cases'][0]['observation']['boundary']['area_basis']='SOURCE_M2'
        with self.assertRaises(ValueError):run(d)
    def test_forecast_date_boundary(self):
        d=sample();d['model_snapshot']['predictions']['p']['boundary']['period_start']='2025-01-01T00:00:00+00:00'
        with self.assertRaises(ValueError):run(d)
    def test_time_overlap(self):
        d=sample();c=d['cases'][0]
        c['periods']=[dict(id='a',start='2026-01-15T00:00:00+00:00',end='2026-01-15T16:00:00+00:00',outdoor_c=0),
         dict(id='b',start='2026-01-15T12:00:00+00:00',end='2026-01-16T00:00:00+00:00',outdoor_c=0)]
        with self.assertRaises(ValueError):run(d)
    def test_time_gap(self):
        d=sample();c=d['cases'][0]
        c['periods']=[dict(id='a',start='2026-01-15T00:00:00+00:00',end='2026-01-15T12:00:00+00:00',outdoor_c=0),
         dict(id='b',start='2026-01-15T13:00:00+00:00',end='2026-01-16T00:00:00+00:00',outdoor_c=0)]
        with self.assertRaises(ValueError):run(d)
    def test_adjacent_heated_same_temp_no_delta(self):
        d=sample();z=d['cases'][0]['hypotheses'][0]
        z['adjacent_spaces']=[{'adjacent_id':'UNMODELLED_HEATED_FLAT','h_w_k':40,
                              'temperature_c_by_period':{'day':20}}]
        self.assertAlmostEqual(run(d)['results'][0]['hypotheses'][0]['required_useful_kwh'],52.8)
    def test_partly_heated_explicit_zones(self):
        d=sample();h=d['cases'][0]['hypotheses'][0];h.pop('conditioned_area_m2');h.pop('external_surfaces');h.pop('ventilation_w_k')
        h.pop('indoor_c_by_period');h.pop('usable_gains_w_by_period');
        h['zones']=[{'id':'HEATED','conditioned_area_m2':50,'external_surfaces':[{'area_m2':50,'u_w_m2k':1}],
                     'ventilation_w_k':10,'indoor_c_by_period':{'day':20},'usable_gains_w_by_period':{'day':100}},
                    {'id':'COOLER','conditioned_area_m2':50,'external_surfaces':[{'area_m2':50,'u_w_m2k':1}],
                     'ventilation_w_k':10,'indoor_c_by_period':{'day':17},'usable_gains_w_by_period':{'day':100}}]
        v=run(d)['results'][0]['hypotheses'][0]
        self.assertAlmostEqual(v['required_useful_kwh'],48.48)
        self.assertAlmostEqual(v['conditional_period_peak_kw'],2.02)
    def test_no_adjacency_double_count(self):
        d=sample();z=d['cases'][0]['hypotheses'][0]
        z['adjacent_spaces']=[{'adjacent_id':'base','h_w_k':50,'temperature_c_by_period':{'day':20}}]
        with self.assertRaises(ValueError):run(d)
    def test_independence_shared_source_family(self):
        d=sample();d['model_snapshot']['calibration_source_families']=['SYNTHETIC_FAMILY']
        self.assertEqual(run(d)['results'][0]['independence'],'SHARED_LINEAGE')
    def test_independence_declared_not_certified(self):
        self.assertEqual(run(sample())['results'][0]['independence'],'PREDECLARED_SOURCE_INDEPENDENCE_AUDIT_REQUIRED')
    def test_independence_not_preregistered(self):
        d=sample();d['cases'][0].pop('hypotheses_locked_at')
        self.assertEqual(run(d)['results'][0]['independence'],'DECLARED_INDEPENDENCE_NO_PREREGISTRATION')
    def test_post_observation_hypotheses(self):
        d=sample();d['cases'][0]['hypotheses_locked_at']='2026-01-04T00:00:00+00:00'
        self.assertEqual(run(d)['results'][0]['independence'],'POST_OBSERVATION_HYPOTHESES_NOT_HELD_OUT')
    def test_multiple_hypotheses(self):
        d=sample();h=copy.deepcopy(d['cases'][0]['hypotheses'][0]);h['id']='other'
        d['cases'][0]['hypotheses'].append(h)
        self.assertEqual(run(d)['results'][0]['physical_hypothesis_status'],'MULTIPLE_COMPATIBLE_EXPLANATIONS')
    def test_temperature_constraint(self):
        d=sample();d['cases'][0]['temperature_observations']=[{'period_id':'day', 'zone_id':'base',
            'low_c':15,'high_c':18,'source_ref':'SYNTHETIC_THERMOMETER'}]
        self.assertEqual(run(d)['results'][0]['physical_hypothesis_status'],'NO_FEASIBLE_TESTED_STATE')
    def test_wrong_schema(self):
        d=sample();d['schema']='city-physical-tests/1'
        with self.assertRaises(ValueError):run(d)
    def test_missing_bounds_basis(self):
        d=sample();d['cases'][0].pop('bounds_basis')
        with self.assertRaises(ValueError):run(d)

if __name__=='__main__':unittest.main()
