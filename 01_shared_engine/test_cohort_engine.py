import unittest,copy,tempfile,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'04_parallel_city_physical_tests'))
from pathlib import Path
from make_acceptance_fixture import fixture
from renovation_module import run
from archetype_physics import heat,package_effect,local_hypothesis
from construction_flow import assess,wlc
from renovation_stock import substitute
from renovation_pipeline import run_pipeline

class CohortAcceptance(unittest.TestCase):
 def setUp(self):self.b=fixture();self.s=self.b['scenarios'][0]
 def result(self):return run(self.b,self.s)
 def test_conservation(self):self.assertEqual(self.result()['final_totals']['area_m2'],1300)
 def test_buildings_count_separate(self):self.assertEqual(self.result()['final_totals']['buildings'],13)
 def test_history_2011(self):self.assertEqual(self.result()['annual'][0]['year'],2011)
 def test_new_only_on_completion(self):self.assertEqual(sum(c['area_m2'] for c in self.result()['snapshots']['2011-01-01']),1000)
 def test_history_not_lost(self):self.assertEqual(sum(c['area_m2'] for c in self.result()['snapshots']['2025-01-01']),1200)
 def test_two_stages_deep(self):
  c=next(c for c in self.result()['cells'] if c.get('root_id')=='old_cube_cohort');self.assertTrue(c['deep_achieved']);self.assertEqual(len(c['history']),2)
 def test_no_second_roof(self):
  c=self.b['opening_cells'][0];a,_,_=package_effect(c,self.b['library']['packages']['roof_windows'],self.b['library']);_,changed,_=package_effect(a,self.b['library']['packages']['deep'],self.b['library']);self.assertEqual(set(changed),{'wall','floor'})
 def test_no_repeated_same_package(self):
  self.s['events'][1]['package_id']='roof_windows';self.assertEqual(sum(x.get('area_m2',0) for x in self.result()['ledger'] if x.get('kind')=='renovation' and x['status']=='COMPLETED'),1000)
 def test_resource_shared(self):
  self.b['capacity']={'district':{'2025':{'task_hours':{'installer':350}}}};r=self.result();row=next(x for x in r['ledger'] if x['event_id']=='stage1' and x['status']=='START_ACCOUNT');self.assertAlmostEqual(row['committed_area_m2'],500)
 def test_material_constraint(self):
  self.b['capacity']={'district':{'2025':{'installed_kg':{'insulation':3500}}}};r=self.result();self.assertAlmostEqual(next(x['committed_area_m2'] for x in r['ledger'] if x['event_id']=='stage1' and x['status']=='START_ACCOUNT'),500)
 def test_history_not_capacity_limited(self):
  self.b['capacity']={'district':{'2011':{'task_hours':{'installer':0}}}};self.assertEqual(self.result()['final_totals']['area_m2'],1300)
 def test_hp_ambient(self):
  c=copy.deepcopy(self.b['opening_cells'][0]);c['heating']={'carrier':'HP_ELECTRICITY','useful_per_final':4};q=heat(c,self.b['library'],self.b['weather']['district']['reference']);self.assertAlmostEqual(q['useful_heat_kwh'],q['final_heat_kwh']+q['ambient_heat_kwh'])
 def test_geometry_changes_heat(self):
  c=copy.deepcopy(self.b['opening_cells'][0]);p=self.b['weather']['district']['reference'];q=heat(c,self.b['library'],p);c['geometry_override']={'wall':.1};c['geometry_source_ref']='TEST';self.assertLess(heat(c,self.b['library'],p)['useful_heat_kwh'],q['useful_heat_kwh'])
 def test_missing_geometry_source_fails(self):
  self.b['opening_cells'][0]['geometry_override']={'wall':.1}
  with self.assertRaises(ValueError):self.result()
 def test_new_demolition_protected(self):
  self.s['events'].append({'id':'demo','kind':'demolition','start_date':'2031-01-01','completion_date':'2032-01-01','area_m2':200,'selector':{'id':'new2012'}});self.assertEqual(self.result()['final_totals']['area_m2'],1300)
 def test_heritage_protected(self):
  self.b['opening_cells'][0]['heritage']=True;self.s['events']=[{'id':'demo','kind':'demolition','start_date':'2025-01-01','completion_date':'2026-01-01','area_m2':500,'selector':{'id':'old_cube_cohort'}}];self.assertEqual(self.result()['final_totals']['area_m2'],1200)
 def test_demolition_removes(self):
  self.s['events']=[{'id':'demo','kind':'demolition','start_date':'2025-01-01','completion_date':'2026-01-01','area_m2':500,'selector':{'id':'old_cube_cohort'}}];self.assertEqual(self.result()['final_totals']['area_m2'],700)
 def test_future_cannot_rewrite_past(self):
  self.s['events'][0]['start_date']='2020-01-01'
  with self.assertRaises(ValueError):self.result()
 def test_no_2015_origin(self):
  self.b['history_start']='2015-01-01'
  with self.assertRaises(ValueError):self.result()
 def test_duplicate_stock_rejected(self):
  self.b['opening_cells']*=2
  with self.assertRaises(ValueError):self.result()
 def test_standards_failure(self):
  self.b['library']['newbuild_designs']['efficient']['metrics']['onsite_fossil_co2']=1
  with self.assertRaises(ValueError):self.result()
 def test_permit_date_changes_rule(self):
  self.b['standards'][0]['date_basis']='permit_date';self.b['library']['newbuild_designs']['efficient']['metrics']['onsite_fossil_co2']=1;self.assertEqual(self.result()['final_totals']['area_m2'],1300)
 def test_unknown_is_not_pass(self):
  r=assess(self.s['events'][-1],{},self.b['standards']);self.assertEqual(r[0]['status'],'UNASSESSED')
 def test_wlc_D_not_netted(self):
  r=wlc(self.b['library']['newbuild_designs']['efficient'],100);self.assertEqual(r['A_to_C_kgco2e'],16000)
 def test_incomplete_wlc_is_unknown(self):self.assertIsNone(wlc({},100)['A_to_C_kgco2e'])
 def test_city_replaces_parent(self):
  c=copy.deepcopy(self.b['opening_cells'][0]);c.update(id='actual_building',area_m2=100,buildings=1,dwellings=1);r=substitute(self.b['opening_cells'],'old_cube_cohort',[c],self.b['library']);self.assertEqual(sum(x['area_m2'] for x in r),1000)
 def test_city_overallocation_fails(self):
  c=copy.deepcopy(self.b['opening_cells'][0]);c.update(id='local',area_m2=2000)
  with self.assertRaises(ValueError):substitute(self.b['opening_cells'],'old_cube_cohort',[c],self.b['library'])
 def test_diffusion_delays_real_work(self):
  self.s['events'][0]['diffusion_dates']={'central':'2029-01-01'};r=self.result();self.assertTrue(any(x.get('event_id')=='stage1' and x.get('date')=='2030-01-01' and x['status']=='COMPLETED' for x in r['ledger']))
 def test_readiness_blocks(self):
  self.s['events'][0]['readiness_required']={'institution':2};self.assertTrue(any(x['status']=='READINESS_GAP' for x in self.result()['ledger']))
 def test_parallel_solver_identical_physics(self):
  from city_physical_tests import evaluate
  c=self.b['opening_cells'][0];p=self.b['weather']['district']['reference'];h=local_hypothesis(c,self.b['library'],p)
  self.assertAlmostEqual(evaluate(h,p)['required_useful_kwh'],heat(c,self.b['library'],p)['useful_heat_kwh'])
 def test_pipeline_nine_strategies(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'input.json';p.write_text(json.dumps(self.b));paths=run_pipeline(p,Path(tmp)/'out');r=json.loads(paths['cohort_results'].read_text());self.assertEqual(len(r['results']),9);self.assertEqual(r['selection']['PI']['default'],'PI_0');self.assertEqual(len(r['selection']['PI']['details']),2)
if __name__=='__main__':unittest.main(verbosity=2)

class AdditionalAcceptance(unittest.TestCase):
 def test_marginals_reconcile(self):
  from renovation_reconciliation import rake
  rows=[{'id':str(i),'share':.25,'attributes':{'W':i%2,'R':i//2}} for i in range(4)]
  r=rake(rows,[{'selector':{'W':1},'share':.6},{'selector':{'R':1},'share':.3}]);self.assertAlmostEqual(sum(x['share'] for x in r['rows'] if x['attributes']['W']==1),.6)
 def test_structural_zero_rejected(self):
  from renovation_reconciliation import rake
  with self.assertRaises(ValueError):rake([{'id':'a','share':1,'attributes':{'W':0}}],[{'selector':{'W':1},'share':1}])
 def test_qualified_donor_effect(self):
  b=fixture();s=b['scenarios'][0];s['events'][0]['readiness_required']={'institution':2};s['readiness']={'institution':1}
  s['donor_effects']=[{'qualified':True,'recipient':'TEST','operational_date':'2025-01-01','effects':{'institution':1},'source_ref':'TEST'}]
  self.assertTrue(any(x['status']=='COMPLETED' and x['event_id']=='stage1' for x in run(b,s)['ledger']))
 def test_unqualified_donor_not_effective(self):
  b=fixture();s=b['scenarios'][0];s['events'][0]['readiness_required']={'institution':2};s['readiness']={'institution':1}
  s['donor_effects']=[{'qualified':False,'recipient':'TEST','operational_date':'2025-01-01','effects':{'institution':1},'source_ref':'TEST'}]
  self.assertTrue(any(x['status']=='READINESS_GAP' for x in run(b,s)['ledger']))
 def test_standard_selects_better_design(self):
  b=fixture();s=b['scenarios'][0];bad=copy.deepcopy(b['library']['newbuild_designs']['efficient']);bad['metrics']['onsite_fossil_co2']=3;b['library']['newbuild_designs']['bad']=bad
  s['events'][-1]['design_candidates']=['bad','efficient'];r=run(b,s);x=next(x for x in r['ledger'] if x['event_id']=='new2030' and x['status']=='COMPLETED');self.assertEqual(x['design_id'],'efficient')
 def test_wlc_product_factors(self):
  d={'installed_kg':{'steel':10},'product_factors_kgco2e_kg':{'steel':2}};self.assertEqual(wlc(d,100)['modules_kgco2e']['A1_A3'],2000)
 def test_actual_identity_city_bridge(self):
  from building_neighbourhood_adapter import export_case
  from city_physical_tests import run as local_run
  b=fixture();c=b['opening_cells'][0];c['id']='REGISTER_BUILDING_17_TEST_ONLY';c.update(area_m2=100,buildings=1,dwellings=1)
  boundary={'country':'TEST','city':'district','population':'REGISTER_BUILDING_17_TEST_ONLY','period_start':'2025-01-01T00:00:00Z','period_end':'2025-01-02T00:00:00Z','service':'SPACE_HEAT','unit':'kWh_USEFUL_DELIVERED','area_basis':'CONDITIONED','conditioned_area_m2':100}
  case={'id':'building_test','cell_ids':[c['id']],'place_id':'district','boundary':boundary,'bounds_basis':'SYNTHETIC_PHYSICS_CHECK','energy_observation':{'mode':'NONE'},'transfer_scope':'THIS_BUILDING_ONLY',
   'periods':[{'id':'day','start':boundary['period_start'],'end':boundary['period_end'],'hours':24,'outdoor_c':0,'indoor_c':20,'usable_gains_w_m2':2}]}
  data=export_case([c],b['library'],case,'test','SYNTHETIC');r=local_run(data);self.assertEqual(len(r['results']),1)

class ConversionAcceptance(unittest.TestCase):
 def test_reoccupation_no_new_building(self):
  b=fixture();b['opening_cells'][0]['service_indoor_c']=5
  s=b['scenarios'][0];s['events']=[{'id':'reuse','kind':'conversion','start_date':'2025-01-01','completion_date':'2026-01-01','area_m2':1000,'selector':{'id':'old_cube_cohort'},'quantity_delta':{'dwellings':5},'service_update':{'service_indoor_c':20,'occupied':True},'source_ref':'TEST_REUSE'}]
  r=run(b,s);self.assertEqual(r['final_totals']['buildings'],12);self.assertEqual(r['final_totals']['dwellings'],17)
 def test_late_diffusion_reported(self):
  b=fixture();s=b['scenarios'][0];s['events'][0]['diffusion_dates']={'central':'2040-01-01'};self.assertTrue(any(x['status']=='DIFFUSION_AFTER_HORIZON' for x in run(b,s)['ledger']))

class PortableRecipientPolicyRegression(unittest.TestCase):
 def base(self, with_source=True):
  from copy import deepcopy
  b=fixture()
  c=b['opening_cells'][0]
  a=deepcopy(c);a.update(id='Z_eligible_social',root_id='Z_eligible_social',area_m2=500,buildings=5,dwellings=5,allocation_tier=1)
  if with_source:a['allocation_evidence']='TEST_MODEL_PRIOR_NOT_OBSERVED'
  n=deepcopy(c);n.update(id='A_other',root_id='A_other',area_m2=500,buildings=5,dwellings=5,allocation_tier=4)
  b['opening_cells']=[n,a]
  e={'id':'priority_selection','kind':'renovation','start_date':'2025-01-01','completion_date':'2026-01-01',
     'area_m2':500,'package_id':'roof_windows','recipient_policy':'PAS_DEEP','selector':{}}
  s=b['scenarios'][0];s['events']=[e]
  return b,s
 def test_priority_overrides_source_order(self):
  b,s=self.base();r=run(b,s)
  got=next(z for z in r['ledger'] if z.get('event_id')=='priority_selection' and z['status']=='COMPLETED')
  self.assertTrue(got['cell_id'].startswith('priority_selection:'))
  cell=next(c for c in r['cells'] if c['id']==got['cell_id'])
  self.assertEqual(cell['root_id'],'Z_eligible_social')
 def test_reverse_source_order_invariance(self):
  b,s=self.base();a=run(b,s);b['opening_cells'].reverse();z=run(b,s)
  self.assertEqual([c['root_id'] for c in a['cells'] if c.get('history') and any(h.get('event_id')=='priority_selection' for h in c['history'])],
                   [c['root_id'] for c in z['cells'] if c.get('history') and any(h.get('event_id')=='priority_selection' for h in c['history'])])
 def test_no_invented_social_source(self):
  b,s=self.base(False)
  with self.assertRaisesRegex(ValueError,'requires evidence provenance'):run(b,s)
 def test_unknown_policy_fails_closed(self):
  b,s=self.base();s['events'][0]['recipient_policy']='PAS_UNKNOWN'
  with self.assertRaisesRegex(ValueError,'Unknown recipient policy'):run(b,s)

class ActorFormationPortableRegression(unittest.TestCase):
 def plan(self):
  b=fixture();s=b['scenarios'][0];s['pathway']='PAS'
  base={'locality_id':'TEST_NEIGHBOURHOOD','capability_scope':'occupied_MFH_deep',
        'date':'2025-01-01','source_ref':'TEST_BOUND_PRIOR_NOT_REAL','inhabited_service_area_ref':'TEST_POPULATED_PLACE'}
  def step(i,**kwargs):
   return {**base,'id':str(i),'stage':('NO_VISIBLE_PRECEDENT','PROGRAMME_FORMED','DEMO_DESIGNED',
             'BUILT','QUALIFIED_PUBLIC_DONOR','REPLICATED_BY_CARRIER','INDEPENDENT_CARRIER_REPLICATION')[i],**kwargs}
  return b,s,step
 def test_first_demonstration_without_local_donor(self):
  b,s,step=self.plan();s['donor_effects']=[]
  s['actor_events']=[step(0,precedent_audit='AUDITED_NOT_IDENTIFIED'),
    step(1,commissioner_id='PUBLIC',carrier_id='NEW_TEAM'),step(2,strategy_package='PAS_DEEP'),
    step(3,date='2026-01-01',physical_event_id='stage1')]
  r=run(b,s);self.assertEqual(r['actor_formation_ledger'][-1]['stage'],'BUILT')
  self.assertEqual(sum(x.get('actor_m2_credited',0) for x in r['actor_formation_ledger']),0)
 def test_unsearched_absence_not_observed(self):
  b,s,step=self.plan();s['actor_events']=[step(0,precedent_audit='NOT_SEARCHED')]
  with self.assertRaisesRegex(ValueError,'bounded audit'):run(b,s)
 def test_no_qualified_donor_from_unverified_demo(self):
  b,s,step=self.plan();s['actor_events']=[step(0,precedent_audit='AUDITED_NOT_IDENTIFIED'),
   step(1,commissioner_id='PUBLIC',carrier_id='NEW_TEAM'),step(2,strategy_package='PAS_RETENTION'),
   step(3,date='2026-01-01',physical_event_id='stage1'),step(4,date='2026-02-01')]
  with self.assertRaisesRegex(ValueError,'independent QA'):run(b,s)
 def test_physical_completion_required(self):
  b,s,step=self.plan();s['actor_events']=[step(0,precedent_audit='AUDITED_NOT_IDENTIFIED'),
   step(1,commissioner_id='PUBLIC',carrier_id='NEW_TEAM'),step(2,strategy_package='PAS_DEEP'),
   step(3,date='2026-01-01',physical_event_id='UNKNOWN_PROJECT')]
  with self.assertRaisesRegex(ValueError,'completed physical'):run(b,s)
 def test_public_completion_remains_separate_from_housing(self):
  b,s,step=self.plan();b['verified_nonres_completions']=[{'event_id':'SCHOOL_A','status':'COMPLETED','source_ref':'PUBLIC_AUDIT','sector':'NONRES','date':'2025-12-31'}]
  s['actor_events']=[step(0,precedent_audit='AUDITED_NOT_IDENTIFIED'),
   step(1,commissioner_id='MUNICIPAL',carrier_id='NEW_TEAM'),step(2,strategy_package='PAS_RETENTION'),
   step(3,date='2026-01-01',physical_event_id='SCHOOL_A')]
  r=run(b,s);self.assertTrue(any(x['physical_event_id']=='SCHOOL_A' for x in r['actor_formation_ledger']))
  self.assertFalse(any(x.get('event_id')=='SCHOOL_A' for x in r['ledger']))
 def test_actor_stages_not_a_diffusion_multiplier(self):
  b,s,step=self.plan();base=run(b,s)
  s['actor_events']=[step(0,precedent_audit='AUDITED_NOT_IDENTIFIED'),
   step(1,commissioner_id='PUBLIC',carrier_id='NEW_TEAM'),step(2,strategy_package='PAS_DEEP'),
   step(3,date='2026-01-01',physical_event_id='stage1'),
   step(4,date='2026-04-01',independent_qa_ref='TEST_QA',post_performance_ref='TEST_PERF',public_transfer_ref='TEST_PUBLIC')]
  x=run(b,s)
  self.assertEqual(base['annual'],x['annual'])
  self.assertEqual(x['actor_formation_ledger'][-1]['stage'],'QUALIFIED_PUBLIC_DONOR')
  self.assertTrue(all(a['adoption_multiplier'] is None for a in x['actor_formation_ledger']))

class ActorFormationChronologyRegression(unittest.TestCase):
 def test_future_demo_not_credited_as_completed(self):
  b=fixture();s=b['scenarios'][0];s['pathway']='PAS'
  ref={'locality_id':'TEST_NEIGHBOURHOOD','capability_scope':'MFH','source_ref':'TEST',
       'inhabited_service_area_ref':'TEST_POPULATION'}
  s['actor_events']=[{**ref,'id':'0','stage':'NO_VISIBLE_PRECEDENT','date':'2025-01-01','precedent_audit':'AUDITED_NOT_IDENTIFIED'},
    {**ref,'id':'1','stage':'PROGRAMME_FORMED','date':'2025-01-01','commissioner_id':'CITY','carrier_id':'NEW'},
    {**ref,'id':'2','stage':'DEMO_DESIGNED','date':'2025-01-02','strategy_package':'PAS_DEEP'},
    {**ref,'id':'3','stage':'BUILT','date':'2025-06-01','physical_event_id':'stage1'}]
  with self.assertRaisesRegex(ValueError,'predate physical completion'):run(b,s)
 def test_non_pas_actor_lane_rejected(self):
  b=fixture();s=b['scenarios'][0];s['pathway']='HDE';s['actor_events']=[{'id':'any'}]
  with self.assertRaisesRegex(ValueError,'non-PAS'):run(b,s)
