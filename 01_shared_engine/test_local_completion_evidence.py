"""Source-qualification acceptance tests, no new stock simulation owner."""
import unittest,copy,json
from pathlib import Path
from renovation_reconciliation import audit_completed_local_renovation_decisions
DATA=Path(__file__).with_name('SK_KE_V08_OBSERVED_COMPLETION_DECISIONS.json')

class LocalSourceAudit(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.p=json.loads(DATA.read_text())
 def test_curated_counts_and_years(self):
  x=audit_completed_local_renovation_decisions(self.p)
  self.assertEqual(x['source_count'],10)
  self.assertEqual(x['by_issued_year'],{2020:1,2023:2,2024:3,2025:4})
 def test_snapshot_scope_and_future_2025(self):
  x=audit_completed_local_renovation_decisions(self.p)
  self.assertEqual(x['cohort_counts'],{'PRE_2021':1,'2021_TO_2024':5,'AFTER_2024':4})
  self.assertEqual(sum(z['as_of_status']=='AFTER_SNAPSHOT_NOT_OPENING' for z in x['audit']),4)
 def test_no_citywide_calibration(self):
  x=audit_completed_local_renovation_decisions(self.p)
  self.assertEqual(x['physical_stock_events_booked'],0)
  self.assertTrue(all(not z['citywide_completed_area_m2_promotable'] for z in x['audit']))
 def test_roof_waterproofing_not_roof_insulation(self):
  x=audit_completed_local_renovation_decisions(self.p)
  h=next(z for z in x['audit'] if z['address'].startswith('Hemerkova'))
  self.assertFalse(h['roof_thermal_insulation_evidenced'])
 def test_lower_area_unquantified(self):
  x=audit_completed_local_renovation_decisions(self.p)
  self.assertTrue(all(z['lower_area_m2'] is None for z in x['audit']))
 def test_duplicate_blocked(self):
  y=copy.deepcopy(self.p);y['records'].append(copy.deepcopy(y['records'][0]))
  with self.assertRaisesRegex(ValueError,'Duplicate'):audit_completed_local_renovation_decisions(y)
 def test_unknown_area_cannot_be_invented(self):
  y=copy.deepcopy(self.p);y['records'][0]['installed_lower_area_m2']=100
  with self.assertRaises(ValueError):audit_completed_local_renovation_decisions(y)
 def test_unqualified_site_status_no_stock_promotion(self):
  x=audit_completed_local_renovation_decisions(self.p)
  self.assertTrue(all(not a['ra_opening_state_calibrated'] for a in x['audit']))
 def test_source_stage_not_permit_application(self):
  y=copy.deepcopy(self.p);y['records'][0]['decision_type']='PERMIT_APPLICATION'
  with self.assertRaises(ValueError):audit_completed_local_renovation_decisions(y)
 def test_no_nonmunicipal_source(self):
  y=copy.deepcopy(self.p);y['records'][0]['source']='https://example.com/claim'
  with self.assertRaises(ValueError):audit_completed_local_renovation_decisions(y)
 def test_independent_cutoff(self):
  x=audit_completed_local_renovation_decisions(self.p,as_of='2023-12-31')
  self.assertEqual(sum(a['as_of_status']=='AFTER_SNAPSHOT_NOT_OPENING' for a in x['audit']),7)
 def test_original_family_unknown_not_fake_system_match(self):
  x=audit_completed_local_renovation_decisions(self.p)
  self.assertTrue(all(not a['original_archetype_matched'] for a in x['audit']))

if __name__=='__main__':unittest.main()
