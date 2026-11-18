"""Source semantics and integration REGRESSION tests, not empirical calibration."""
import copy,unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'04_parallel_city_physical_tests'))
from make_acceptance_fixture import fixture
from archetype_physics import heat, package_effect
from surface_state import (floor_area_alternatives,surface_inventory,
                           evidence_independence,apply_physical_change)
from renovation_module import run
from renovation_stock import take

SYN='SYNTHETIC_BOUNDARY_PRIOR_NOT_OBSERVED'

class Integration(unittest.TestCase):
    def setUp(self):
        self.b=fixture()
        self.p=self.b['weather']['district']['reference']
        self.c=copy.deepcopy(self.b['opening_cells'][0]);self.c['area_m2']=100
        self.c['buildings']=1;self.c['dwellings']=1
        self.c['surface_inventory_scope']='complete_thermal_boundary'
        self.c['surface_inventory']=[
            dict(id='street',component='wall',area_m2=40,adjacent='exterior',area_basis='surface_net',source_ref=SYN,orientation_deg=180),
            dict(id='courtyard',component='wall',area_m2=25,adjacent='exterior',area_basis='surface_net',source_ref=SYN,orientation_deg=0),
            dict(id='party',component='wall',area_m2=45,adjacent='heated_neighbour',area_basis='party_wall',source_ref=SYN),
            dict(id='roof',component='roof',area_m2=40,adjacent='unheated_enclosure',area_basis='ceiling_under_attic',boundary_factor=.7,source_ref=SYN),
            dict(id='windows',component='window',area_m2=20,adjacent='exterior',area_basis='surface_net',source_ref=SYN),
            dict(id='floor',component='floor',area_m2=100,adjacent='ground',area_basis='floor_to_ground',boundary_factor=.4,source_ref=SYN)]

    def test_orava_built_up_area_not_conditioned(self):
        # 2023 Dlha nad Oravou reported built-up area, not heated floor.
        source=[dict(id='1NP',kind='built_up',area_m2=130.11,source_ref='2023_Dlha_auction'),
                dict(id='2NP',kind='built_up',area_m2=130.08,source_ref='2023_Dlha_auction'),
                dict(id='attic',kind='built_up',area_m2=43.96,source_ref='2023_Dlha_auction')]
        options=floor_area_alternatives(source,{'1NP':dict(conditioned_fraction_bounds=[.65,.85],source_ref=SYN),
           '2NP':dict(conditioned_fraction_bounds=[.6,.9],source_ref=SYN),
           'attic':dict(conditioned_fraction_bounds=[0,.7],source_ref=SYN)})
        self.assertEqual(options[2]['conditioned_m2'][0],0)
        self.assertLess(options[0]['conditioned_m2'][1],130.11)
        self.assertEqual(options[0]['reported']['kind'],'built_up')
        self.assertEqual(floor_area_alternatives(source,{})[0]['conditioned_m2'],None)
        c=copy.deepcopy(self.c);c['area_basis']='built_up'
        with self.assertRaises(ValueError):heat(c,self.b['library'],self.p)

    def test_attached_courtyard_and_party_wall(self):
        rows=surface_inventory(self.c,self.b['library'])
        self.assertEqual(sum(x['area_m2'] for x in rows),270)
        self.assertEqual(next(r for r in rows if r['id']=='party')['ua_w_k'],0)
        q=heat(self.c,self.b['library'],self.p)
        self.c['surface_inventory'][2]['adjacent']='exterior'
        self.assertGreater(heat(self.c,self.b['library'],self.p)['useful_heat_kwh'],q['useful_heat_kwh'])

    def test_french_street_courtyard_mixed_assemblies(self):
        self.c['surface_states']={'courtyard':'improved'}
        q=heat(self.c,self.b['library'],self.p)
        self.c['surface_states']={}
        self.assertLess(q['useful_heat_kwh'],heat(self.c,self.b['library'],self.p)['useful_heat_kwh'])
        self.c['surface_states']={'courtyard':'improved'}
        after,changed,inv=package_effect(self.c,{'surface_targets':{'street':'improved'}},self.b['library'])
        self.assertEqual(after['surface_states']['courtyard'],'improved')
        self.assertEqual(changed,['wall'])
        self.assertAlmostEqual(inv['installed_kg']['insulation'],4) # 40/100 * 10 kg/m2 per conditioned m2
        self.assertEqual(after['state']['wall'],'original')

    def test_renovation_material_same_surface_as_heat(self):
        before=heat(self.c,self.b['library'],self.p)
        after,changed,inv=package_effect(self.c,{'targets':{'wall':'improved'}},self.b['library'])
        self.assertAlmostEqual(inv['installed_kg']['insulation'],6.5) # 65 m2 exterior, not 45 m2 heated party wall
        self.assertLess(heat(after,self.b['library'],self.p)['useful_heat_kwh'],before['useful_heat_kwh'])
        # 45 m2 party wall remains in physical inventory, but needs explicit scope to insulate.

    def test_conversion_change_and_conservation(self):
        b=fixture();b['opening_cells'][0]['surface_inventory']=copy.deepcopy(self.c['surface_inventory']);
        b['opening_cells'][0]['surface_inventory_scope']='complete_thermal_boundary'
        # Existing cohort represents 10 repetitions of the 100 m2 illustrative flat.
        for row in b['opening_cells'][0]['surface_inventory']:row['area_m2']*=10
        s=b['scenarios'][0];s['events']=[{
            'id':'attic','kind':'conversion','source_ref':SYN,'start_date':'2025-01-01',
            'completion_date':'2026-01-01','area_m2':100,'selector':{'root_id':'old_cube_cohort'},
            'physical_change':{'source_ref':SYN,'conditioned_area_delta_m2':20,
               'surface_changes':[{'id':'roof','operation':'replace','surface':dict(
                 component='roof',area_m2=55,adjacent='exterior',area_basis='roof_slope',source_ref=SYN)}]},
            'inventory_per_m2':{'unknown':['attic conversion BOM missing']}}]
        # One of ten physical flats is converted. Area growth must be +20, not another retrofit.
        r=run(b,s)
        self.assertEqual(r['final_totals']['area_m2'],1220)
        row=next(x for x in r['ledger'] if x.get('event_id')=='attic' and x['status']=='COMPLETED')
        self.assertEqual(row['physical_change']['conditioned_area_delta_m2'],20)
        self.assertEqual(row['work_area_m2'],100)
        self.assertEqual(len([x for x in r['cells'] if x.get('physical_history')]),1)
        self.assertTrue(any(x.get('history') and x['history'][-1]['kind']=='conversion' for x in r['cells']))

    def test_split_preserves_physical_area(self):
        cells=[copy.deepcopy(self.c)];parent=cells[0]
        child=take(cells,parent,25,'one_quarter')
        self.assertEqual(sum(r['area_m2'] for r in child['surface_inventory']),67.5)
        self.assertEqual(sum(r['area_m2'] for r in parent['surface_inventory']),202.5)

    def test_airtightness_records_no_heat_bonus(self):
        b=fixture();s=b['scenarios'][0];s['events']=[dict(
            id='leak-test',kind='airtightness',source_ref=SYN,start_date='2025-01-01',
            completion_date='2026-01-01',area_m2=1000,selector={'root_id':'old_cube_cohort'},
            treated_parts=['roof','wall'],junction_scope='all stated junctions',quality_basis=SYN,
            outcome=dict(role='measured',metric='n50',bounds=[2,2.3],source_ref=SYN,
                         test_boundary_ref='blower door fixture'))]
        r=run(b,s)
        self.assertEqual(r['final_totals']['area_m2'],1200)
        c=next(x for x in r['cells'] if x.get('leakage_state'))
        self.assertEqual(c['leakage_state']['outcome']['bounds'],[2,2.3])
        q=heat(c,b['library'],self.p)
        d=copy.deepcopy(c);d.pop('leakage_state')
        self.assertAlmostEqual(q['useful_heat_kwh'],heat(d,b['library'],self.p)['useful_heat_kwh'])
        self.assertTrue(any(row.get('leakage_outcome') for row in r['ledger']))

    def test_operating_airflow_replaces_flat_coefficient(self):
        c=copy.deepcopy(self.c)
        c['operating_airflow_by_period']={'winter':dict(
            system='balanced',interaction_resolved=True,source_ref=SYN,
            recovery_basis='intentional_stream_only',operating_mode='balanced_recovery',
            infiltration_m3_h=25,window_airing_m3_h=0,intentional_m3_h=75,
            effective_recovery=.8,air_heat_capacity_wh_m3k=.33,fan_w=20,required_outdoor_m3_h=80)}
        q=heat(c,self.b['library'],self.p)
        self.assertAlmostEqual(q['fan_electricity_kwh'],80)
        c['operating_airflow_by_period']['winter']['interaction_resolved']=False
        with self.assertRaises(ValueError):heat(c,self.b['library'],self.p)

    def test_historical_current_condition_not_backdated(self):
        b=fixture();b['opening_cells'][0]['surface_inventory']=copy.deepcopy(self.c['surface_inventory']);
        b['opening_cells'][0]['surface_inventory_scope']='complete_thermal_boundary'
        for row in b['opening_cells'][0]['surface_inventory']:row['area_m2']*=10
        b['opening_cells'][0]['surface_inventory'][0]['observed_as_of']='2023-01-01'
        with self.assertRaisesRegex(ValueError,'Present-day'):run(b,b['scenarios'][0])

    def test_evidence_cycle(self):
        self.assertEqual(evidence_independence({'source_ids':['FAC','PHOTO'],'derived_from_ids':['PHOTO']},
                {'source_ids':['PHOTO']})['status'],'CIRCULAR_EVIDENCE')
        self.assertEqual(evidence_independence({'source_ids':['model']},{})['status'],'INDEPENDENCE_UNVERIFIED')

if __name__=='__main__':unittest.main(verbosity=2)

class AdditionalRegression(unittest.TestCase):
    def test_main_engine_carries_partial_surface_renovation(self):
        b=fixture();c=b['opening_cells'][0]
        c['surface_inventory_scope']='complete_thermal_boundary'
        c['surface_inventory']=[dict(id='street',component='wall',area_m2=400,adjacent='exterior',area_basis='surface_net',source_ref=SYN),
            dict(id='courtyard',component='wall',area_m2=250,adjacent='exterior',area_basis='surface_net',source_ref=SYN),
            dict(id='party',component='wall',area_m2=450,adjacent='heated_neighbour',area_basis='party_wall',source_ref=SYN),
            dict(id='roof',component='roof',area_m2=400,adjacent='exterior',area_basis='surface_net',source_ref=SYN),
            dict(id='window',component='window',area_m2=200,adjacent='exterior',area_basis='surface_net',source_ref=SYN),
            dict(id='floor',component='floor',area_m2=1000,adjacent='ground',area_basis='floor_to_ground',boundary_factor=.5,source_ref=SYN)]
        b['library']['packages']['STREET_ONLY']={'surface_targets':{'street':'improved'}}
        b['scenarios'][0]['events']=[dict(id='street-work',kind='renovation',source_ref=SYN,
             start_date='2025-01-01',completion_date='2026-01-01',area_m2=1000,package_id='STREET_ONLY',
             selector={'root_id':'old_cube_cohort'})]
        r=run(b,b['scenarios'][0]);changed=[x for x in r['cells'] if x.get('surface_states',{}).get('street')=='improved']
        self.assertEqual(len(changed),1)
        self.assertEqual(changed[0]['surface_states'].get('courtyard'),None)
        self.assertEqual(changed[0]['state']['wall'],'original')
        self.assertTrue(any(row.get('inventory') for row in r['ledger'] if row.get('event_id')=='street-work'))

    def test_later_measured_leakage_supersedes_prior(self):
        b=fixture();b['scenarios'][0]['events']=[dict(
            id='assumption',kind='airtightness',source_ref=SYN,start_date='2025-01-01',completion_date='2025-05-01',
            area_m2=1000,selector={'root_id':'old_cube_cohort'},treated_parts=['wall'],junction_scope='windows',quality_basis=SYN,
            outcome=dict(role='assumed_achieved',metric='n50',bounds=[3,6],source_ref=SYN)),dict(
            id='measured',kind='airtightness',source_ref=SYN,start_date='2026-01-01',completion_date='2026-05-01',
            area_m2=1000,selector={'root_id':'old_cube_cohort'},treated_parts=['wall'],junction_scope='windows',quality_basis=SYN,
            outcome=dict(role='measured',metric='n50',bounds=[2,2.2],source_ref=SYN,test_boundary_ref='documented pressure test'))]
        r=run(b,b['scenarios'][0]);c=next(x for x in r['cells'] if x.get('leakage_state',{}).get('outcome',{}).get('role')=='measured')
        self.assertEqual(c['leakage_state']['outcome']['bounds'],[2,2.2]);self.assertEqual(len(c['leakage_state']['events']),2)
        self.assertEqual(len(c['leakage_state']['applied_event_ids']),2)

class PromotionBoundaryRegression(unittest.TestCase):
    def test_partial_prioritisation_uses_only_eligible_exposure(self):
        from recipient_priority import _gain
        from archetype_physics import package_effect
        b=fixture();c=copy.deepcopy(b['opening_cells'][0]);c['area_m2']=100
        c['surface_inventory_scope']='complete_thermal_boundary'
        c['surface_inventory']=[
          dict(id='street',component='wall',area_m2=40,adjacent='exterior',area_basis='surface_net',source_ref=SYN),
          dict(id='court',component='wall',area_m2=30,adjacent='exterior',area_basis='surface_net',source_ref=SYN),
          dict(id='party',component='wall',area_m2=30,adjacent='heated_neighbour',area_basis='party_wall',source_ref=SYN)]
        p={'targets':{'wall':'improved'}}
        expected=(1.6-.15)*.7
        self.assertAlmostEqual(_gain(c,b['library'],p),expected)
        c['surface_states']={'court':'improved'}
        self.assertAlmostEqual(_gain(c,b['library'],p),(1.6-.15)*.4)
        after,_,inv=package_effect(c,p,b['library'])
        self.assertAlmostEqual(inv['installed_kg']['insulation'],4)
        self.assertAlmostEqual(_gain(after,b['library'],p),0)

    def test_multiple_stages_retain_surface_status_and_no_repeat_resources(self):
        b=fixture();c=b['opening_cells'][0]
        c['surface_inventory_scope']='complete_thermal_boundary'
        c['surface_inventory']=[
          dict(id='street',component='wall',area_m2=400,adjacent='exterior',area_basis='surface_net',source_ref=SYN),
          dict(id='court',component='wall',area_m2=250,adjacent='exterior',area_basis='surface_net',source_ref=SYN),
          dict(id='party',component='wall',area_m2=450,adjacent='heated_neighbour',area_basis='party_wall',source_ref=SYN),
          dict(id='roof',component='roof',area_m2=500,adjacent='exterior',area_basis='surface_net',source_ref=SYN)]
        b['library']['packages'].update(STREET={'surface_targets':{'street':'improved'}},
                                      COURT={'surface_targets':{'court':'improved'}},
                                      REPEAT={'surface_targets':{'street':'improved'}})
        s=b['scenarios'][0];s['events']=[dict(id=n,kind='renovation',package_id=n,area_m2=1000,
          selector={'root_id':'old_cube_cohort'},start_date=f'{y}-01-01',completion_date=f'{y+1}-01-01')
          for n,y in [('STREET',2025),('COURT',2027),('REPEAT',2029)]]
        r=run(b,s)
        finished=[x for x in r['ledger'] if x['status']=='COMPLETED' and x['kind']=='renovation']
        self.assertEqual([x['event_id'] for x in finished],['STREET','COURT'])
        self.assertAlmostEqual(finished[0]['inventory']['installed_kg']['insulation'],4000)
        self.assertAlmostEqual(finished[1]['inventory']['installed_kg']['insulation'],2500)
        self.assertEqual(r['final_totals']['area_m2'],1200)
        c=next(c for c in r['cells'] if c.get('root_id')=='old_cube_cohort' and c.get('surface_states'))
        self.assertEqual(c['surface_states']['street'],'improved')
        self.assertEqual(c['surface_states']['court'],'improved')
        self.assertEqual(c['state']['wall'],'original')

    def test_proportional_city_substitution_cannot_duplicate_area_or_surface(self):
        from renovation_stock import substitute
        b=fixture();p=copy.deepcopy(b['opening_cells'][0])
        p['surface_inventory_scope']='complete_thermal_boundary'
        p['surface_inventory']=[dict(id='wall',component='wall',area_m2=800,adjacent='exterior',area_basis='surface_net',source_ref=SYN)]
        child=copy.deepcopy(p);child.update(id='matched_city',area_m2=250,buildings=2.5,dwellings=2.5)
        child['surface_inventory'][0]['area_m2']=200
        rows=substitute([p],p['id'],[child],b['library'])
        self.assertEqual(sum(c['area_m2'] for c in rows),1000)
        self.assertEqual(sum(c['surface_inventory'][0]['area_m2'] for c in rows),800)

    def test_ventilation_fans_have_distinct_annual_account(self):
        b=fixture();c=b['opening_cells'][0]
        c['operating_airflow_by_period']={'winter':dict(system='balanced',interaction_resolved=True,source_ref=SYN,
          recovery_basis='intentional_stream_only',operating_mode='balanced_recovery',infiltration_m3_h=10,
          window_airing_m3_h=0,intentional_m3_h=50,effective_recovery=.7,
          air_heat_capacity_wh_m3k=.33,fan_w=20,required_outdoor_m3_h=55)}
        s=b['scenarios'][0];s['events']=[]
        r=run(b,s)
        row=next(x for x in r['annual'] if x['year']==2025)
        self.assertAlmostEqual(row['pre_2011_fan_electricity_kwh'],80)
        self.assertAlmostEqual(row['ventilation_fan_electricity_kwh'],80)
        # Fan power must not be silently folded into useful heat or heat-carrier final.
        self.assertNotIn('carrier_ELECTRICITY_kwh',row)
        self.assertAlmostEqual(row['carrier_GAS_kwh'],row['pre_2011_final_heat_kwh'])

    def test_physical_conversion_dates_and_avoids_double_area_addition(self):
        b=fixture();s=b['scenarios'][0];s['events']=[dict(
          id='extension',kind='conversion',source_ref=SYN,start_date='2025-01-01',
          completion_date='2026-01-01',selector={'root_id':'old_cube_cohort'},area_m2=1000,
          physical_change=dict(source_ref=SYN,conditioned_area_delta_m2=200),
          inventory_per_m2={'unknown':['extension_bom_unknown']})]
        r=run(b,s); self.assertEqual(r['final_totals']['area_m2'],1400)
        c=next(c for c in r['cells'] if c.get('physical_history'))
        self.assertEqual(c['physical_history'][0]['date'],'2026-01-01')
        self.assertEqual(c['physical_history'][0]['event_id'],'extension')
        self.assertEqual(c['physical_history'][0]['conditioned_area_delta_m2'],200)
        self.assertIn('extension_bom_unknown',next(x for x in r['ledger'] if x.get('event_id')=='extension' and x['status']=='COMPLETED')['inventory_unknown'])
        double=s['events'][0].copy(); double['quantity_delta']={'area_m2':200};s['events']=[double]
        with self.assertRaisesRegex(ValueError,'counted twice'):run(b,s)

class CityAirflowParityRegression(unittest.TestCase):
    def test_explicit_balanced_flow_parity_with_city_solver(self):
        from city_physical_tests import evaluate
        from archetype_physics import local_hypothesis
        b=fixture();c=b['opening_cells'][0]
        c['operating_airflow_by_period']={'winter':dict(system='balanced',interaction_resolved=True,source_ref=SYN,
          recovery_basis='intentional_stream_only',operating_mode='balanced_recovery',infiltration_m3_h=10,
          window_airing_m3_h=0,intentional_m3_h=75,effective_recovery=.8,
          air_heat_capacity_wh_m3k=.33,fan_w=20,required_outdoor_m3_h=80)}
        self.assertAlmostEqual(evaluate(local_hypothesis(c,b['library'],b['weather']['district']['reference']),
          b['weather']['district']['reference'])['required_useful_kwh'],
          heat(c,b['library'],b['weather']['district']['reference'])['useful_heat_kwh'])

    def test_varying_ventilation_periods_fail_city_adapter_closed(self):
        from archetype_physics import local_hypothesis
        b=fixture();c=b['opening_cells'][0]
        periods=[dict(id='a',hours=100,outdoor_c=2,indoor_c=20,usable_gains_w_m2=1),
                 dict(id='b',hours=100,outdoor_c=2,indoor_c=20,usable_gains_w_m2=1)]
        flow=dict(system='balanced',interaction_resolved=True,source_ref=SYN,
          recovery_basis='intentional_stream_only',operating_mode='balanced_recovery',infiltration_m3_h=10,
          window_airing_m3_h=0,intentional_m3_h=75,effective_recovery=.8,
          air_heat_capacity_wh_m3k=.33,fan_w=20,required_outdoor_m3_h=80)
        c['operating_airflow_by_period']={'a':flow, 'b':{**flow,'infiltration_m3_h':35}}
        with self.assertRaisesRegex(ValueError,'varying period ventilation'):local_hypothesis(c,b['library'],periods)
