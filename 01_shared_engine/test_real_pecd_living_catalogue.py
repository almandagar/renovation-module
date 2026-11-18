"""Offline executable checks for source-grounded cross-country PECD weather research."""
import sys,unittest, json, tempfile, os
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).parent))
import build_real_pecd_living_catalogue as m
ROOT=Path(os.environ.get('RENOVATION_PECD_RESULTS', Path(__file__).parent/'external_fixtures/pecd_weather_catalogue/results'))
RAW=Path(os.environ.get('RENOVATION_PECD_RAW', Path(__file__).parent/'external_fixtures/pecd_weather_source'))
MODEL=Path(os.environ.get('RENOVATION_PECD_MODELS', Path(__file__).parent/'external_fixtures/pecd_climate_models'))
class TestCatalog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d=pd.read_csv(ROOT/'WS36_EU8_living_weather_exposure_metrics.csv')
        cls.e=pd.read_csv(ROOT/'WS36_EU8_living_weather_episodes.csv')
        cls.s=json.loads((ROOT/'WS36_EU8_living_weather_qualification.json').read_text())
    def test_source_year_to_ws_id(self):
        self.assertEqual(m.member('CMR5',2025),'WS01')
        self.assertEqual(m.member('CMR5',2036),'WS12')
        self.assertEqual(m.member('ECE3',2030),'WS18')
        self.assertEqual(m.member('MEHR',2032),'WS32')
    def test_eight_countries_thirtysix_members(self):
        self.assertEqual(len(self.d),288)
        self.assertEqual(self.d.member.nunique(),36)
        self.assertEqual(self.d.country.nunique(),8)
        self.assertTrue((self.d.groupby('member').country.nunique()==8).all())
    def test_three_climate_families(self):
        self.assertEqual(self.d.groupby('model').member.nunique().to_dict(),{'CMR5':12,'ECE3':12,'MEHR':12})
    def test_source_checksums_12(self):
        self.assertEqual(len(self.s['source_manifest']['source_file_sha256']),12)
        for name,digest in self.s['source_manifest']['source_file_sha256'].items():
            self.assertEqual(m.sha(MODEL/name),digest)
    def test_no_fake_2025_weather_observations(self):
        self.assertIn('model projections',self.s['source_manifest']['model_scenario_years'])
        self.assertEqual(self.s['status'],'RESEARCH_METEOROLOGICAL_EXPOSURE_NO_RUNTIME_PROMOTION')
    def test_leap_day_removed(self):
        dates,xx,dig=m.read_model_file(MODEL,'MEHR','temperature_c')
        self.assertEqual(len(dates),105120)
        self.assertFalse(((dates.dt.month==2)&(dates.dt.day==29)).any())
    def test_no_missing_outdoor_temperatures(self):
        self.assertTrue(self.d[['min_hourly_t_c','max_hourly_t_c']].notna().all().all())
        self.assertTrue((self.d.max_hourly_t_c>=self.d.min_hourly_t_c).all())
    def test_episode_minimum_lengths(self):
        self.assertTrue((self.e[self.e.kind=='heatwave'].duration_days>=3).all())
        self.assertTrue((self.e[self.e.kind=='cold_spell'].duration_days>=3).all())
        self.assertTrue((self.e[self.e.kind=='warm_night_sequence'].duration_days>=2).all())
    def test_three_outdoor_episode_types(self):
        self.assertEqual(set(self.e.kind),{'cold_spell','heatwave','warm_night_sequence'})
        self.assertEqual(self.s['episodes'],len(self.e))
    def test_episodes_no_indoor_or_health_claim(self):
        self.assertTrue((self.e.interpretation=='OUTDOOR_METEOROLOGICAL_EXPOSURE_NOT_INDOOR_COMFORT').all())
        self.assertTrue(self.e.timebase.str.contains('unverified').all())
    def test_slova_hot_reference(self):
        a=self.d[(self.d.member=='WS32')&(self.d.country=='SK')].iloc[0]
        self.assertAlmostEqual(a.max_heatwave_severity_dd,81.113,places=3)
    def test_nl_cold_reference(self):
        a=self.d[(self.d.member=='WS17')&(self.d.country=='NL')].iloc[0]
        self.assertAlmostEqual(a.max_cold_spell_severity_dd,30.419,places=3)
    def test_source_reference_thresholds(self):
        th=pd.read_csv(ROOT/'PECD_ERA5_historical_research_thresholds.csv')
        self.assertEqual(set(th.country),set(m.CC))
        self.assertTrue((th.hot_p95_summer_daily_max_c>th.cold_p05_winter_daily_mean_c).all())
    def test_keep_12_years_provisional(self):
        x=self.s['compact_full_year_options']
        self.assertEqual(len(x['12']['selected']),12)
        self.assertEqual(x['12']['missed_country_extrema'],2)
        self.assertTrue(x['12']['not_validated_as_national_thermal_ensemble'])
    def test_13_retain_all_selected_extrema(self):
        x=self.s['compact_full_year_options']['13']
        self.assertEqual(x['missed_country_extrema'],0)
        self.assertEqual(x['worst_normalized_regret'],0.)
    def test_nl_cold_missing_from_12(self):
        miss=self.s['compact_full_year_options']['12']['missed']
        self.assertEqual({x['country'] for x in miss},{'NL'})
        self.assertTrue(all(x['metric'] in ('max_cold_spell_severity_dd','coldest_7d_mean_daily_mean_c') for x in miss))
    def test_exposure_selector_does_not_force_12(self):
        self.assertEqual(self.s['selection']['status'],'BUDGET_BLOCKED_COUNTRY_EXTREMES')
        self.assertGreater(self.s['selection']['minimum_distinct_years'],12)
    def test_weather_fingerprint_check_detects_mutation(self):
        import hashlib
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'x.csv.gz';p.write_bytes(b'bad');self.assertNotEqual(m.sha(p), self.s['source_manifest']['historical_raw_temperature_sha256'])
    def test_wind_and_solar_source_was_used(self):
        self.assertTrue((self.e.mean_wind_m_s>=0).all());self.assertTrue((self.e.mean_ghi_w_m2>=0).all())
    def test_no_source_rh_assumed(self):
        self.assertEqual(self.s['source_manifest']['relative_humidity_and_river_water'],'NOT_AVAILABLE')
    def test_negative_ghi_tolerance_is_bounded(self):
        self.assertTrue(np.isfinite(self.e.mean_ghi_w_m2).all())
if __name__=='__main__':unittest.main(verbosity=2)
