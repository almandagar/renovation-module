import copy,unittest
from airflow_pressure import resolve_airflow
from archetype_physics import heat
from make_acceptance_fixture import fixture

def case(system='natural'):
 b=fixture();c=copy.deepcopy(b['opening_cells'][0]);c['area_m2']=100
 c['airflow_model']={'schema':'single-zone-pressure/1','system':system,'source_ref':'TEST_PRIOR','evidence_class':'MODEL_PRIOR',
  'reference_density_convention':'BOUSSINESQ_CONSTANT_REFERENCE_VOLUME','volume_m3_per_floor_m2':2.5,
  'leakage':{'metric':'n50','value':4,'test_boundary_ref':'closed vents assumption','source_ref':'TEST_PRIOR','evidence_class':'MODEL_PRIOR'},
  'pressure_exponent':.65,'pressure_exponent_source_ref':'TEST_PRIOR','reference_air_density_kg_m3':1.2,'air_heat_capacity_wh_m3k':.33,
  'fan_w_per_floor_m2':.2 if system=='extract' else 0,'extract_m3_h_per_floor_m2':.9 if system=='extract' else 0,
  'required_outdoor_m3_h_per_floor_m2':.5,'background_paths':[
   {'id':'low','share':.5,'height_m':0,'wind_pressure_coefficient':.6,'source_ref':'TEST_PRIOR','evidence_class':'MODEL_PRIOR'},
   {'id':'high','share':.5,'height_m':3,'wind_pressure_coefficient':-.6,'source_ref':'TEST_PRIOR','evidence_class':'MODEL_PRIOR'}]}
 p={'id':'winter','indoor_c':20,'outdoor_c':0,'wind_speed_m_s':4,'wind_source_ref':'TEST_PRIOR','hours':24,'usable_gains_w_m2':0}
 return c,b['library'],p

class PressureTests(unittest.TestCase):
 def test_no_driving_force(self):
  c,_,p=case();p.update(outdoor_c=20,wind_speed_m_s=0);self.assertAlmostEqual(resolve_airflow(c,p,20)['outdoor_m3_h'],0)
 def test_symmetric_wind_analytic(self):
  c,_,p=case();p['outdoor_c']=20;c['airflow_model']['background_paths'][1]['height_m']=0
  expected=1000/2*(.5*1.2*4**2*.6/50)**.65
  self.assertAlmostEqual(resolve_airflow(c,p,20)['outdoor_m3_h'],expected)
 def test_stack_low_in_high_out(self):
  c,_,p=case();p['wind_speed_m_s']=0;r=resolve_airflow(c,p,20);self.assertGreater(r['path_flows_m3_h']['low'],0);self.assertLess(r['path_flows_m3_h']['high'],0);self.assertAlmostEqual(r['airflow_balance_residual_m3_h'],0)
 def test_extract_not_added_twice(self):
  c,_,p=case('extract');p.update(outdoor_c=20,wind_speed_m_s=0);r=resolve_airflow(c,p,20);self.assertAlmostEqual(r['outdoor_m3_h'],90)
 def test_sealing_changes_pressure_under_fixed_extract(self):
  c,_,p=case('extract');p.update(outdoor_c=20,wind_speed_m_s=0);a=resolve_airflow(c,p,20);c['airflow_model']['leakage']['value']=2;b=resolve_airflow(c,p,20)
  self.assertAlmostEqual(a['outdoor_m3_h'],b['outdoor_m3_h']);self.assertGreater(abs(b['pressure_pa']),abs(a['pressure_pa']))
 def test_cohort_scaling_preserves_pressure(self):
  c,_,p=case('extract');a=resolve_airflow(c,p,20);c['area_m2']=40;b=resolve_airflow(c,p,20);self.assertAlmostEqual(a['pressure_pa'],b['pressure_pa']);self.assertAlmostEqual(b['outdoor_m3_h'],a['outdoor_m3_h']*.4)
 def test_heat_replaces_legacy_ventilation(self):
  c,lib,p=case();a=heat(c,lib,[p]);lib['archetypes'][c['archetype_id']]['ventilation_w_k_m2']=999;b=heat(c,lib,[p]);self.assertEqual(a['useful_heat_kwh'],b['useful_heat_kwh']);self.assertIsNone(a['h_w_k'])
 def test_fan_electricity(self):
  c,lib,p=case('extract');self.assertAlmostEqual(heat(c,lib,[p])['fan_electricity_kwh'],.48)
 def test_missing_wind_fails(self):
  c,_,p=case();p.pop('wind_source_ref')
  with self.assertRaises(ValueError):resolve_airflow(c,p,20)
 def test_double_airflow_route_fails(self):
  c,lib,p=case();c['operating_airflow_by_period']={}
  with self.assertRaises(ValueError):heat(c,lib,[p])
 def test_event_state_supersedes_prior(self):
  c,_,p=case();a=c['airflow_model'];a.update(use_cell_leakage=True,bounds_choice='upper',state_boundary_compatible_source='TEST_PRIOR');c['leakage_state']={'outcome':{'metric':'n50','bounds':[1,2],'role':'assumed_achieved','source_ref':'TEST','test_boundary_ref':'TEST'}}
  self.assertAlmostEqual(resolve_airflow(c,p,20)['leakage_q50_m3_h'],500)
 def test_invalid_path_partition(self):
  c,_,p=case();c['airflow_model']['background_paths'][0]['share']=.8
  with self.assertRaises(ValueError):resolve_airflow(c,p,20)
 def test_opening_overlap_fails(self):
  c,_,p=case();c['airflow_model']['openings']=[{'kind':'window','source_ref':'TEST','evidence_class':'MODEL_PRIOR'}]
  with self.assertRaises(ValueError):resolve_airflow(c,p,20)
 def test_no_heat_recovery_for_extract(self):
  c,_,p=case('extract');c['airflow_model']['effective_recovery']=.8
  with self.assertRaises(ValueError):resolve_airflow(c,p,20)
 def test_completed_event_drives_airflow_in_scheduler(self):
  from renovation_module import run
  b=fixture();c=b['opening_cells'][0];model=case()[0]['airflow_model'];model.update(use_cell_leakage=True,bounds_choice='upper',state_boundary_compatible_source='TEST_PRIOR')
  c['airflow_model']=model;c['leakage_state']={'outcome':{'metric':'n50','bounds':[4,4],'role':'assumed_achieved','source_ref':'TEST','test_boundary_ref':'TEST'}}
  b['historical_events']=[]
  for p in b['weather']['district']['reference']:p.update(wind_speed_m_s=4,wind_source_ref='TEST_PRIOR')
  s=b['scenarios'][0];s['events']=[{'id':'sealing','kind':'airtightness','area_m2':1000,'start_date':'2025-01-01','completion_date':'2026-01-01','selector':{'root_id':'old_cube_cohort'},'source_ref':'TEST','treated_parts':['window'],'junction_scope':'TEST','quality_basis':'explicit prior','outcome':{'metric':'n50','bounds':[2,2],'role':'assumed_achieved','source_ref':'TEST','test_boundary_ref':'TEST'}}]
  r=run(b,s);self.assertEqual(r['cells'][0]['leakage_state']['outcome']['bounds'],[2,2]);self.assertTrue(any(x.get('kind')=='airtightness' and x['status']=='COMPLETED' for x in r['ledger']))
 def test_zero_paths_rejected(self):
  c,_,p=case();c['airflow_model']['leakage']['value']=0
  with self.assertRaises(ValueError):resolve_airflow(c,p,20)

if __name__=='__main__':unittest.main()
