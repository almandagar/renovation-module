"""V09 identity bridge stays nonadditive; independently reported flats remain unpromoted."""
import copy, json, unittest
from pathlib import Path
from renovation_reconciliation import audit_local_site_identity_matches
ROOT=Path(__file__).resolve().parent

class TestKošiceSiteIdentity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v08=json.loads((ROOT/'SK_KE_V08_Observed_Decisions_SourceLedger.json').read_text())
        cls.v09=json.loads((ROOT/'SK_KE_V09_PhysicalIdentity_SourceJoin.json').read_text())
        cls.audit=audit_local_site_identity_matches(cls.v08,cls.v09)
    def test_all_ten_qualified_parcels_without_geometry_promotion(self):
        self.assertEqual(self.audit['source_count'],10)
        self.assertEqual(self.audit['municipal_cadastre_identity_count'],10)
        self.assertFalse(self.audit['building_geometry_gku_join_completed'])
    def test_original_stock_and_ra_not_mutated(self):
        self.assertFalse(self.audit['city_ra_stock_shares_calibrated'])
        self.assertFalse(self.audit['historical_2011_stock_changed'])
        self.assertFalse(self.audit['national_2024_or_2035_promoted'])
        self.assertEqual(self.audit['scheduled_physical_events_booked'],0)
    def test_secondary_counts_stay_only_optional_scenarios(self):
        self.assertEqual(self.audit['secondary_dwelling_scenarios_count'],3)
        self.assertEqual(self.audit['secondary_building_number_count'],1)
        self.assertEqual(self.audit['municipal_building_number_count'],5)
        self.assertTrue(all(x['secondary_dwellings_not_stock_observation'] for x in self.audit['records']))
    def test_disputed_contractor_area_quarantined(self):
        self.assertEqual(self.audit['contractor_area_quarantined_count'],1)
        x=next(x for x in self.audit['records'] if x['decision_id']=='MK/A/2024/16498-03/I/STS')
        self.assertIsNone(x['verified_treated_facade_area_m2'])
    def test_no_2025_backdating(self):
        self.assertEqual(self.audit['pre_2025_site_decision_count'],6)
    def test_source_cannot_change_decision_identity(self):
        copyv=copy.deepcopy(self.v09)
        copyv['records'][0]['address']='DIFFERENT'
        with self.assertRaisesRegex(ValueError,'disagrees'):audit_local_site_identity_matches(self.v08,copyv)
    def test_secondary_reported_flats_require_internal_arithmetic(self):
        copyv=copy.deepcopy(self.v09)
        r=next(x for x in copyv['records'] if x['decision_id']=='MK/A/2025/09763-04/II/PER')
        r['independent_crossreferences'][0]['reported_total_flats_scenario']=65
        with self.assertRaisesRegex(ValueError,'Inconsistent'):audit_local_site_identity_matches(self.v08,copyv)
    def test_cannot_invent_full_floor_area(self):
        copyv=copy.deepcopy(self.v09)
        copyv['records'][0]['matched_insulated_lower_area_m2']=200
        with self.assertRaisesRegex(ValueError,'insufficient'):audit_local_site_identity_matches(self.v08,copyv)
    def test_no_unverified_original_panel_type(self):
        copyv=copy.deepcopy(self.v09)
        copyv['records'][0]['original_panel_system']='T06B_KE'
        with self.assertRaisesRegex(ValueError,'Original panel series'):audit_local_site_identity_matches(self.v08,copyv)
    def test_no_fake_geospatial_footprint(self):
        copyv=copy.deepcopy(self.v09)
        copyv['records'][0]['asbuilt_geometry_footprint_id']='FAKE'
        with self.assertRaisesRegex(ValueError,'footprint'):audit_local_site_identity_matches(self.v08,copyv)
    def test_bad_permit_chronology(self):
        copyv=copy.deepcopy(self.v09)
        copyv['records'][3]['earlier_building_permit']['issued']='2026-01-01'
        with self.assertRaisesRegex(ValueError,'issued after'):audit_local_site_identity_matches(self.v08,copyv)
    def test_contractor_area_requires_quarantine(self):
        copyv=copy.deepcopy(self.v09)
        x=next(x for x in copyv['records'] if x['decision_id']=='MK/A/2024/16498-03/I/STS')
        x['independent_crossreferences'][0]['match']='EXACT_CONFIRMED'
        with self.assertRaisesRegex(ValueError,'quarantined'):audit_local_site_identity_matches(self.v08,copyv)

if __name__=='__main__':unittest.main()
