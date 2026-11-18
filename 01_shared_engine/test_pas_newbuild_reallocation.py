"""End-to-end PAS allocation regressions using the existing synthetic stock."""
import json
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from make_acceptance_fixture import fixture
from renovation_module import run
from renovation_pipeline import run_pipeline


class PASRuntimeTests(TestCase):
    def setUp(self):
        self.bundle=fixture()
        self.bundle['pas_newbuild_dwellings']={'district':{'2030':0}}
        self.bundle['capacity']={'district':{
            '2029':{'task_hours':{'installer':500},'installed_kg':{'concrete':10000,'insulation':6000}},
            '2030':{'task_hours':{'installer':300},'installed_kg':{'insulation':9000}},
        }}
        self.scenario=deepcopy(self.bundle['scenarios'][3])
        self.stage=self.scenario['events'][1]
        self.stage.update(start_date='2029-01-01',completion_date='2030-01-01',
                          area_m2=200,pas_eligible_area_m2=600)

    def capped(self,result):
        for row in result['resource_use']:
            cap=self.bundle['capacity'].get(row['region'],{}).get(str(row['year']),{}).get(row['kind'],{}).get(row['resource'])
            if cap is not None:self.assertLessEqual(row['amount'],cap+1e-8)

    def by_request(self,r,id):
        return next(row for row in r['pas_newbuild_reallocation']['queue'] if row['request_id']==id)

    def test_active_pipeline_each_strategy_uses_its_own_work_and_keeps_selection(self):
        self.bundle['library']['packages']['repair_floor']={'targets':{'floor':'improved'}}
        deep=deepcopy(self.scenario);deep['id']='PAS_DEEP'
        deep['events'][1]['recipient_policy']='PAS_DEEP'
        retention=deepcopy(deep);retention['id']='PAS_RETENTION'
        retention['events'][1].update(package_id='repair_floor',recipient_policy='PAS_RETENTION')
        adaptive=deepcopy(deep);adaptive['id']='PAS_ADAPTIVE'
        ev=adaptive['events'][1]
        ev.pop('package_id')
        ev.update(kind='conversion',recipient_policy='PAS_ADAPTIVE',source_ref='SYNTHETIC',
                  quantity_delta={'dwellings':2},inventory_per_m2={'task_hours':{'installer':1.5}})
        pi=deepcopy(deep);pi.update(id='PI',pathway='PI')
        hde=deepcopy(deep);hde.update(id='HDE',pathway='HDE')
        self.bundle['scenarios']=[deep,retention,adaptive,pi,hde]
        with TemporaryDirectory() as tmp:
            src=Path(tmp)/'input.json';src.write_text(json.dumps(self.bundle))
            paths=run_pipeline(src,Path(tmp)/'out')
            out=json.loads(paths['cohort_results'].read_text())
            self.assertTrue(json.loads(paths['manifest'].read_text())['pas_newbuild_reallocation']['enabled'])
        results={r['scenario']:r for r in out['results']}
        self.assertEqual(set(results),{'PAS_DEEP','PAS_RETENTION','PAS_ADAPTIVE','PI','HDE'})
        self.assertNotIn('pas_newbuild_reallocation',results['PI'])
        self.assertNotIn('pas_newbuild_reallocation',results['HDE'])
        self.assertEqual(results['PI']['final_totals']['dwellings'],13)
        for strategy in ('PAS_DEEP','PAS_RETENTION','PAS_ADAPTIVE'):
            r=results[strategy]
            self.capped(r)
            self.assertEqual(r['pas_newbuild_reallocation']['newbuild_trajectory'][0]['retained_dwellings'],0)
            self.assertFalse(any(e['event_id']=='new2030' for e in r['ledger']))
            self.assertTrue(any(e.get('pas_extra') and e['status']=='COMPLETED' for e in r['ledger']))
            self.assertGreater(self.by_request(r,'stage2')['committed_area_m2'],200)
        self.assertGreater(results['PAS_ADAPTIVE']['final_totals']['dwellings'],12)
        self.assertEqual(results['PAS_DEEP']['final_totals']['dwellings'],12)
        self.assertEqual(out['selection']['PAS']['metric'],'final_year_final_space_heating_kwh')
        ranked=sorted((results[k] for k in ('PAS_DEEP','PAS_RETENTION','PAS_ADAPTIVE')),
                      key=lambda r:(sum(v for k,v in r['annual'][-1].items() if k.startswith('carrier_')),r['scenario']))
        self.assertEqual(out['selection']['PAS']['default'],ranked[0]['scenario'])

    def test_completion_target_preserves_later_newbuild_and_protected_work(self):
        early=deepcopy(self.scenario['events'][-1])
        early.update(id='protected',committed=True,start_date='2029-10-01')
        self.scenario['events'].append(early)
        self.scenario['events'][-2]['start_date']='2029-11-01'
        # Original uncut PI also needs to be feasible to compare the reallocation.
        self.bundle['capacity']['district']['2029']['installed_kg']['concrete']=20000
        self.bundle['pas_newbuild_dwellings']['district']['2030']=1.5
        r=run(self.bundle,self.scenario);self.capped(r)
        rows={e['event_id']:e for e in r['ledger'] if e['status']=='COMPLETED'}
        self.assertEqual(rows['protected']['dwellings'],1)
        self.assertEqual(rows['new2030']['dwellings'],.5)
        self.assertEqual(rows['new2030']['area_m2'],50)
        self.assertAlmostEqual(rows['new2030']['inventory']['task_hours']['installer'],100)
        self.assertAlmostEqual(self.by_request(r,'stage2')['committed_area_m2'],200/1.5+200)
        self.bundle['pas_newbuild_dwellings']['district']['2030']=.5
        with self.assertRaisesRegex(ValueError,'committed/planned bounds'):run(self.bundle,self.scenario)
        self.bundle['pas_newbuild_dwellings']['district']['2030']=1.5
        self.scenario['events'][-1]['readiness_required']={'crew':1}
        with self.assertRaisesRegex(ValueError,'fails scheduled readiness'):run(self.bundle,self.scenario)

    def test_missing_caps_do_not_become_discretionary_capacity(self):
        for y in self.bundle['capacity']['district'].values():
            y['installed_kg'].pop('insulation',None)
        r=run(self.bundle,self.scenario)
        self.assertEqual(self.by_request(r,'stage2')['committed_area_m2'],200)
        self.assertFalse(any(e.get('pas_extra') and e['status']=='COMPLETED' for e in r['ledger']))

    def test_pull_forward_and_retry_use_each_conversion_area_only_once(self):
        self.stage.pop('package_id')
        self.stage.update(kind='conversion',source_ref='SYNTHETIC',
            selector={'root_id':'old_cube_cohort'},quantity_delta={'dwellings':2},
            inventory_per_m2={'task_hours':{'installer':2}},
            start_date='2031-01-01',completion_date='2031-01-01',
            pas_ready_from='2029-01-01',pas_eligible_area_m2=450)
        self.stage['diffusion_dates']={'central':'2029-07-01'}
        self.bundle['capacity']['district']['2031']={'task_hours':{'installer':200}}
        r=run(self.bundle,self.scenario);self.capped(r)
        start=[e for e in r['ledger'] if e.get('pas_request_id')=='stage2' and e['status']=='START_ACCOUNT']
        self.assertEqual([(e['date'],e['committed_area_m2']) for e in start],
                         [('2029-07-01',250),('2030-01-01',150),('2031-01-01',50)])
        self.assertAlmostEqual(r['final_totals']['dwellings'],16.5)
        self.assertEqual(self.by_request(r,'stage2')['remaining_area_m2'],0)
        self.assertTrue(all(c.get('pas_completed_request_ids',[]).count('stage2')<=1 for c in r['cells']))

    def test_unscaled_trajectory_does_not_enable_extra_works(self):
        self.bundle['pas_newbuild_dwellings']['district']['2030']=1
        r=run(self.bundle,self.scenario)
        self.assertFalse(r['pas_newbuild_reallocation']['queue'])
        self.assertEqual(r['final_totals']['dwellings'],13)
        self.assertEqual(next(e['committed_area_m2'] for e in r['ledger']
                              if e['event_id']=='stage2' and e['status']=='START_ACCOUNT'),200)
        self.bundle['pas_newbuild_dwellings']['district']['2030']=0
        reduced=run(self.bundle,self.scenario)
        delivered=sum(e['committed_area_m2'] for e in reduced['ledger']
                      if e.get('pas_request_id')=='stage2' and e['status']=='START_ACCOUNT'
                      and e['date'].startswith('2029'))
        self.assertAlmostEqual(delivered,500/1.5)
