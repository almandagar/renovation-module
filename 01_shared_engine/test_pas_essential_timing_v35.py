"""Regression gate for the Essential Housing PAS newbuild preservation / timing patch.
Synthetic only: no national trajectory, site construction or calibrated workforce.
"""
from copy import deepcopy
from unittest import TestCase
from make_acceptance_fixture import fixture
from renovation_module import run


class EssentialConstructionTimingTests(TestCase):
    def setUp(self):
        self.bundle=fixture()
        self.bundle['pas_newbuild_dwellings']={'district': {'2030':0}}
        self.bundle['capacity']={'district': {
            '2029':{'task_hours':{'installer':750},
                    'installed_kg':{'concrete':20000,'insulation':10000}},
            '2030':{'task_hours':{'installer':400},
                    'installed_kg':{'concrete':20000,'insulation':10000}},
        }}
        self.scenario=deepcopy(self.bundle['scenarios'][3])
        stage=self.scenario['events'][1]
        stage.update(start_date='2029-02-01',completion_date='2030-02-01',
                     area_m2=200,pas_eligible_area_m2=600)
        self.new=next(e for e in self.scenario['events'] if e['kind']=='newbuild')
        self.new.update(start_date='2029-11-01',
                        construction_purpose='DISCRETIONARY_ADDITIONAL_RES')

    def _hospital(self):
        hospital=deepcopy(self.new)
        hospital.update(id='regional_hospital',construction_purpose='ESSENTIAL_NONRES',
            essential_source_ref='SYNTHETIC_ESSENTIAL_HOSPITAL',
            start_date='2029-04-01',area_m2=100,buildings=1,dwellings=0)
        self.scenario['events'].append(hospital)
        return hospital

    def _starts(self,r):
        return [x for x in r['ledger'] if x['status']=='START_ACCOUNT']

    def _comparison(self,r):
        return r['pas_newbuild_reallocation']['pi_headroom_comparison']

    def test_november_cancellation_cannot_enable_february_extra_or_ordinary(self):
        # With annual installer cap 400, the November project reserves 200h
        # and February can use only 200h (133.33 m²). Without the chronology
        # fix, PAS could incorrectly deliver all 200 m² before November.
        self.bundle['capacity']['district']['2029']['task_hours']['installer']=400
        r=run(self.bundle,self.scenario)
        starts=self._starts(r)
        extra=[e for e in starts if e.get('pas_extra')]
        self.assertTrue(extra)
        self.assertTrue(all(e['date']>='2029-11-01' for e in extra))
        ordinary=[e for e in starts if e['event_id']=='stage2']
        self.assertEqual(ordinary[0]['date'],'2029-02-01')
        self.assertAlmostEqual(ordinary[0]['committed_area_m2'],200/1.5)
        released=r['pas_newbuild_reallocation']['avoided_construction_starts']
        self.assertEqual([x['start_date'] for x in released],['2029-11-01'])
        self.assertEqual(self._comparison(r)['status'],'MATCHED_SAME_PAS_PROGRAMME_PI_NEWBUILD_UNCUT')
        self.assertGreater(self._comparison(r)['total_net_incremental_area_m2'],0)

    def test_available_pi_headroom_is_not_attributed_to_avoided_construction(self):
        # Both uncut PI and PAS can already deliver the complete eligible area.
        self.bundle['capacity']['district']['2029']['task_hours']['installer']=2000
        self.bundle['capacity']['district']['2029']['installed_kg']['insulation']=15000
        r=run(self.bundle,self.scenario)
        comparison=self._comparison(r)
        self.assertEqual(comparison['status'],'MATCHED_SAME_PAS_PROGRAMME_PI_NEWBUILD_UNCUT')
        self.assertAlmostEqual(comparison['total_net_incremental_area_m2'],0)
        self.assertGreater(comparison['total_pi_headroom_or_other_area_m2'],0)
        stage=next(x for x in comparison['requests'] if x['request_id']=='stage2')
        self.assertIn('2029-02-01',stage['pi_headroom_extra_start_dates'])
        self.assertIn('2029-11-01',stage['pas_extra_start_dates'])
        self.assertTrue(any(x.get('pas_extra') for x in self._starts(r)))

    def test_essential_hospital_is_not_scaled_by_residential_dwelling_target(self):
        self._hospital()
        r=run(self.bundle,self.scenario)
        hospitals=[e for e in r['ledger'] if e['event_id']=='regional_hospital' and e['status']=='COMPLETED']
        self.assertEqual(len(hospitals),1)
        self.assertAlmostEqual(hospitals[0]['buildings'],1)
        self.assertEqual(hospitals[0]['dwellings'],0)
        self.assertFalse(any(x['event_id']=='regional_hospital' for x in r['pas_newbuild_reallocation']['avoided_construction_starts']))
        self.assertIn('regional_hospital',r['pas_newbuild_reallocation']['newbuild_trajectory'][0]['protected_event_ids'])
        self.assertEqual(r['pas_newbuild_reallocation']['newbuild_trajectory'][0]['retained_dwellings'],0)

    def test_protected_safety_replacement_remains_despite_zero_discretionary(self):
        replacement=deepcopy(self.new)
        replacement.update(id='damage_replacement',construction_purpose='SAFETY_REPLACEMENT',
              replacement_source_ref='SYNTHETIC_DOCUMENTED_DAMAGE',
              start_date='2029-06-01')
        self.scenario['events'].append(replacement)
        self.bundle['pas_newbuild_dwellings']['district']['2030']=1
        r=run(self.bundle,self.scenario)
        complete={e['event_id']:e for e in r['ledger'] if e['status']=='COMPLETED'}
        self.assertIn('damage_replacement',complete)
        self.assertNotIn('new2030',complete)
        self.assertAlmostEqual(complete['damage_replacement']['dwellings'],1)
        self.bundle['pas_newbuild_dwellings']['district']['2030']=0
        with self.assertRaisesRegex(ValueError,'committed/planned bounds'):
            run(self.bundle,self.scenario)

    def test_unclassified_nondwelling_event_protected_without_claiming_essential(self):
        hospital=self._hospital()
        hospital.pop('construction_purpose')
        hospital.pop('essential_source_ref')
        r=run(self.bundle,self.scenario)
        self.assertIn('regional_hospital',r['pas_newbuild_reallocation']['newbuild_trajectory'][0]['protected_event_ids'])
        self.assertTrue(any(e['event_id']=='regional_hospital' and e['status']=='COMPLETED' for e in r['ledger']))

    def test_essential_purpose_must_have_source_and_sensible_unit(self):
        hospital=self._hospital()
        hospital.pop('essential_source_ref')
        with self.assertRaisesRegex(ValueError,'essential_source_ref'):
            run(self.bundle,self.scenario)
        hospital['essential_source_ref']='SYNTHETIC'
        hospital['dwellings']=1
        with self.assertRaisesRegex(ValueError,'cannot carry dwelling counts'):
            run(self.bundle,self.scenario)

    def test_no_avoidance_keeps_PI_and_PAS_admitted_work_equal(self):
        self.bundle['pas_newbuild_dwellings']['district']['2030']=1
        r=run(self.bundle,self.scenario)
        self.assertEqual(r['pas_newbuild_reallocation']['pi_headroom_comparison']['status'],'NO_AVOIDED_NEWBUILD')
        self.assertEqual(r['pas_newbuild_reallocation']['avoided_construction_starts'],[])

    def test_invalid_legacy_pi_cap_marks_attribution_unqualified_not_success(self):
        # Original PI can exceed the documented cap even though reduced PAS fits.
        self.bundle['capacity']['district']['2029']['task_hours']['installer']=150
        # 150 is insufficient to keep ordinary planned PAS renovation? permissible
        # partial delivery; the uncut 200h construction is infeasible.
        r=run(self.bundle,self.scenario)
        self.assertEqual(self._comparison(r)['status'],'UNQUALIFIED_PI_COUNTERFACTUAL')
        self.assertIsNone(self._comparison(r)['total_net_incremental_area_m2'])
