"""Synthetic integration regressions, not national validation."""
import copy,json,tempfile,unittest
from pathlib import Path
from make_acceptance_fixture import fixture
from renovation_module import run
from renovation_pipeline import run_pipeline
from archetype_physics import heat
from archetype_integration import prepare_bundle,checklist
class Integration(unittest.TestCase):
 def setUp(self):self.b=fixture();self.s=self.b['scenarios'][0]
 def fallback(self):
  c=self.b['opening_cells'][0];c.update(archetype_id=None,fallback_key='ordinary',use='residential')
  self.b['archetype_fallbacks']={'ordinary':{'archetype_id':'cube','country':'TEST','use':'residential','construction_period':[1946,2000], 'source_ref':'SYNTHETIC','compatibility_basis':'Compatible period/form fixture'}}
 def test_fallback_matches_explicit(self):
  expected=run(self.b,self.s);self.fallback();actual=run(self.b,self.s)
  self.assertEqual(expected['annual'],actual['annual']);self.assertEqual(expected['final_totals'],actual['final_totals'])
 def test_no_input_mutation(self):
  self.fallback();old=copy.deepcopy(self.b);run(self.b,self.s);self.assertEqual(old,self.b)
 def test_label_does_not_change_heat(self):
  b=self.b;b['library']['archetypes']['renamed']=copy.deepcopy(b['library']['archetypes']['cube']);c=b['opening_cells'][0];p=b['weather']['district']['reference'];h=heat(c,b['library'],p);c['archetype_id']='renamed';self.assertEqual(h,heat(c,b['library'],p))
 def test_geometry_changes_heat(self):
  b=self.b;p=b['weather']['district']['reference'];c=b['opening_cells'][0];h=heat(c,b['library'],p);b['library']['archetypes']['cube']['geometry']['wall']*=2;self.assertGreater(heat(c,b['library'],p)['useful_heat_kwh'],h['useful_heat_kwh'])
 def test_country_mismatch(self):
  self.fallback();self.b['archetype_fallbacks']['ordinary']['country']='OTHER'
  with self.assertRaisesRegex(ValueError,'country/use'):run(self.b,self.s)
 def test_period_mismatch(self):
  self.fallback();self.b['archetype_fallbacks']['ordinary']['construction_period']=[1981,2000]
  with self.assertRaisesRegex(ValueError,'period'):run(self.b,self.s)
 def test_missing_system_not_dropped(self):
  self.b['opening_cells'][0]['archetype_id']='missing'
  with self.assertRaisesRegex(ValueError,'No compatible'):run(self.b,self.s)
 def test_state_not_invented(self):
  self.fallback();self.b['opening_cells'][0]['state'].pop('roof')
  with self.assertRaisesRegex(ValueError,'Incomplete'):run(self.b,self.s)
 def test_coverage(self):
  self.fallback();b=prepare_bundle(self.b);r=checklist(b,[run(b,self.s)]);self.assertEqual(r['coverage']['PHYSICAL_FALLBACK'],{'area_m2':1000.,'buildings':10.,'dwellings':10.})
 def test_missing_hours_does_not_block_heat(self):
  before=run(self.b,self.s)['annual']
  for v in self.b['library']['archetypes']['cube']['components'].values():v['improved'].pop('task_hours_m2')
  r=run(self.b,self.s);self.assertEqual(before,r['annual']);self.assertEqual(next(x for x in checklist(self.b,[r])['checks'] if x['id']=='resources')['status'],'CONDITIONAL')
 def test_overallocation(self):
  self.b['stock_controls']={'as_of_date':'2011-01-01','source_ref':'SYNTHETIC','totals':{'area_m2':999,'buildings':10,'dwellings':10}};self.assertIn('stock_allocation',checklist(self.b)['blocking_checks'])
 def test_duplicate(self):
  self.b['opening_cells']*=2;self.assertIn('physical_inputs',checklist(self.b)['blocking_checks'])
 def test_remainder_visible(self):
  self.b['unresolved_stock']=[{'area_m2':100,'buildings':1,'dwellings':1,'source_ref':'SYNTHETIC','reason':'Missing profile'}];self.assertAlmostEqual(checklist(self.b)['coverage_fraction']['UNRESOLVED']['area_m2'],1/11)
 def snapshot(self):
  self.b['history_start']='2024-01-01';self.b['historical_events']=[]
  self.b['research_opening_snapshot']={'schema':'research-stock-snapshot/1','country':'TEST','as_of_date':'2024-01-01','stock_boundary':'TEST_GENERIC_STOCK','source_ref':'SYNTHETIC','state_basis':'Conditional components','uncertainty_ref':'SYNTHETIC_BOUNDS','evidence_class':'CONDITIONAL_MODEL_PRIOR_NOT_OBSERVED','population_totals':{'area_m2':1000,'buildings':10,'dwellings':10}}
  for s in self.b['scenarios']:
   for e in s['events']:e.update(source_ref='SYNTHETIC',site_access_basis='ASSUMED_CAPABLE_STRESS_NOT_OBSERVED',commissioning_basis='ASSUMED_PASS_STRESS_NOT_OBSERVED')
 def test_generic_snapshot(self):
  self.snapshot();r=run(self.b,self.s);self.assertEqual(r['annual'][0]['year'],2024);self.assertFalse(r['runtime_promoted'])
 def test_no_historic_first_deep(self):
  self.snapshot();self.assertFalse(any(c.get('deep_achieved') for c in run(self.b,self.s)['cells']))
 def test_bad_snapshot_population(self):
  self.snapshot();self.b['research_opening_snapshot']['population_totals']['buildings']=9
  with self.assertRaisesRegex(ValueError,'population mismatch'):run(self.b,self.s)
 def test_snapshot_history_rejected(self):
  self.snapshot();self.b['historical_events']=fixture()['historical_events']
  with self.assertRaisesRegex(ValueError,'no historical'):run(self.b,self.s)
 def test_pipeline_checklist(self):
  self.fallback()
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'input.json';p.write_text(json.dumps(self.b));paths=run_pipeline(p,Path(d)/'out');r=json.loads(paths['archetype_integration_checklist'].read_text());self.assertEqual(r['status'],'EXECUTED_CONDITIONAL');self.assertEqual(len(r['checks']),10)
 def test_failure_checklist(self):
  self.b['opening_cells'][0]['archetype_id']='absent'
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'input.json';p.write_text(json.dumps(self.b));out=Path(d)/'out'
   with self.assertRaises(ValueError):run_pipeline(p,out)
   self.assertEqual(json.loads((out/'archetype_integration_checklist.json').read_text())['status'],'BLOCKED')
class VerificationRefinements(unittest.TestCase):
 def test_direct_id_not_observed(self):
  b=prepare_bundle(fixture());r=checklist(b)
  self.assertEqual(r['assignments'][0]['selection_route'],'EXPLICIT_LIBRARY_ID')
  self.assertEqual(r['assignments'][0]['assignment_evidence'],'UNSPECIFIED')
  self.assertEqual(r['physical_resolution']['RESOLVED']['buildings'],10)
 def test_direct_profile_scope_rejected(self):
  b=fixture();b['library']['archetypes']['cube']['country']='OTHER'
  with self.assertRaisesRegex(ValueError,'country mismatch'):prepare_bundle(b)
 def test_execution_not_completion(self):
  b=fixture();r=checklist(b,[run(b,b['scenarios'][0])])
  self.assertEqual(r['execution_status'],'SUCCEEDED')
  self.assertEqual(r['integration_completeness']['status'],'INCOMPLETE')
 def complete(self):
  b=fixture();b['integration_scope']='DONOR_PHYSICS'
  f={'family_id':'test','source_ref':'SYNTHETIC','date':'2011','population_unit':'buildings','geography':'TEST','cohort_scope':'1961-1980'}
  b['source_scope_manifest']={'registry_ref':'SYNTHETIC_REGISTRY','registry_version':'1','country':'TEST','families':[f]}
  b['archetype_evidence_review']=[dict(f,decision='USED',reason='test')]
  b['opening_cells'][0]['archetype_assignment']={'family_id':'test','evidence_class':'MODEL_ASSUMPTION'}
  b['archetype_uncertainty']={'source_ref':'TEST','central_basis':'Controlled software test','not_applicable_reason':'Fixed input regression'}
  return b
 def test_donor_complete_without_national_controls(self):
  b=self.complete();r=checklist(b,[run(b,b['scenarios'][0])]);self.assertEqual(r['integration_completeness']['status'],'COMPLETE_AGAINST_DECLARED_SCOPE')
 def test_stock_requires_controls(self):
  b=self.complete();b['integration_scope']='STOCK_PHYSICS';r=checklist(b,[run(b,b['scenarios'][0])]);self.assertIn('stock_controls',r['integration_completeness']['missing_requirements'])
 def test_missing_ap_family_detected(self):
  from archetype_integration import source_scope_review
  b=self.complete();b['source_scope_manifest']['families'].append(dict(b['source_scope_manifest']['families'][0],family_id='AP'))
  self.assertIn('AP:missing_disposition',source_scope_review(b)['issues'])
 def test_units_mismatch_detected(self):
  from archetype_integration import source_scope_review
  b=self.complete();b['archetype_evidence_review'][0]['population_unit']='dwellings'
  self.assertIn('test:scope_mismatch_population_unit',source_scope_review(b)['issues'])
 def test_panel_population_mixture(self):
  # Historical flat counts from SK_Socialist_MFH_Fallback_V01. Physics and
  # area/flat are deliberately synthetic: integration regression, not SK prediction.
  from archetype_integration import aggregate_population_branches
  counts=[357865,91783,172847];areas=[50,70,90];us=[1.6,.9,.6]
  b=fixture();branches=[]
  for i,(n,area,u) in enumerate(zip(counts,areas,us)):
   c=copy.deepcopy(b['opening_cells'][0]);lib=copy.deepcopy(b['library'])
   c.update(area_m2=n*area,dwellings=n,buildings=n/20)
   lib['archetypes']['cube']['components']['wall']['original']['u_w_m2k']=u
   q=heat(c,lib,b['weather']['district']['reference'])['useful_heat_kwh']
   branches.append(dict(id=str(i),area_m2=n*area,dwellings=n,buildings=n/20,resolved=True,useful_heat_kwh=q))
  parent={k:sum(r[k] for r in branches) for k in ('area_m2','buildings','dwellings')}
  r=aggregate_population_branches(branches,parent)
  self.assertAlmostEqual(r['whole_parent_useful_heat_kwh'],sum(x['useful_heat_kwh'] for x in branches))
  c=copy.deepcopy(b['opening_cells'][0]);c.update(parent)
  simple=heat(c,b['library'],b['weather']['district']['reference'])['useful_heat_kwh']
  self.assertNotEqual(simple,r['whole_parent_useful_heat_kwh'])
  flat_weighted=sum(x['dwellings']/parent['dwellings']*x['useful_heat_kwh']/x['area_m2'] for x in branches)
  self.assertNotAlmostEqual(flat_weighted,r['resolved_area_intensity_kwh_m2'])
  branches[2].update(resolved=False,useful_heat_kwh=None);r=aggregate_population_branches(branches,parent)
  self.assertIsNone(r['whole_parent_useful_heat_kwh']);self.assertEqual(r['unresolved_quantities']['dwellings'],172847)
  self.assertAlmostEqual(sum(r['weights'].values()),1)
  with self.assertRaisesRegex(ValueError,'conservation'):aggregate_population_branches(branches[:2],parent)

if __name__=='__main__':unittest.main()
