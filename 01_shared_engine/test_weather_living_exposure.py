import json,sys,hashlib,tempfile,unittest
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parent))
from weather_living_exposure import read_hourly,detect_events,propose_weather_members,produce,sha256_file

class WeatherLivingExposureTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        n=24*25
        t=pd.date_range('2024-07-01',periods=n,freq='h',tz='UTC')
        local=t.tz_convert('Europe/Bratislava')
        x=np.full(n,18.0)
        hot=((local.date>=pd.Timestamp('2024-07-08').date())&(local.date<=pd.Timestamp('2024-07-12').date()))
        x[hot]=np.where((local.hour[hot]>=12)&(local.hour[hot]<=18),35.,26.)
        cold=((local.date>=pd.Timestamp('2024-07-18').date())&(local.date<=pd.Timestamp('2024-07-22').date()))
        x[cold]=-12.
        self.df=pd.DataFrame({'timestamp_utc':t.strftime('%Y-%m-%dT%H:%M:%SZ'),'weather_member':'WS17',
            'country':'SK','site_id':'Bratislava_test','air_temperature_c':x})
        self.csv=self.root/'hourly.csv';self.df.to_csv(self.csv,index=False)
        self.meta={'source_id':'TEST_SYNTHETIC','source_provider':'TEST_ONLY',
                'weather_member':'WS17','country':'SK','site_id':'Bratislava_test',
                'local_timezone':'Europe/Bratislava','source_calendar':'real_chronological_hourly_UTC',
                'member_chronology_id':'synthetic:test:2024','unit':'degree_Celsius',
                'source_type':'hourly_meteorological_air_temperature',
                'data_alignment_status':'verified_source_hour_mapping','source_sha256':sha256_file(self.csv)}
        self.threshold={'country':'SK','site_id':'Bratislava_test','threshold_source':'TEST_NOT_NATIONAL_DEFINITION',
            'threshold_basis':'declared_research_sensitivity','hot_daily_max_c':32.0,'warm_night_min_c':23.0,
            'cold_daily_mean_c':-5.0,'min_heatwave_days':3,'min_cold_spell_days':3}
    def inp(self):return read_hourly(self.csv,self.meta)
    def test_detects_weather_not_indoor_comfort(self):
        d=detect_events(self.inp(),self.meta,self.threshold)
        self.assertEqual([e['event_kind'] for e in d],['heatwave','cold_spell'])
        self.assertEqual([e['duration_days'] for e in d],[5,5])
        self.assertTrue(d[0]['longest_warm_night_run']>=3)
        self.assertIsNone(d[0]['indoor_temperature']);self.assertIsNone(d[0]['measured_health_effect'])
        self.assertFalse(d[0]['antecedent_7d_available']);self.assertTrue(d[1]['antecedent_7d_available'])
    def test_real_utc_required(self):
        m={**self.meta,'source_calendar':'typical_meteorological_year'}
        with self.assertRaisesRegex(ValueError,'TMY'):read_hourly(self.csv,m)
    def test_cannot_use_electricity_matrices(self):
        with self.assertRaisesRegex(ValueError,'electricity'):read_hourly(self.csv,{**self.meta,'source_type':'ERAA_2035_demand'})
    def test_fingerprint(self):
        with self.assertRaisesRegex(ValueError,'fingerprint'):read_hourly(self.csv,{**self.meta,'source_sha256':'x'*64})
    def test_missing_hour(self):
        df=self.df.drop(index=50);df.to_csv(self.csv,index=False)
        m={**self.meta,'source_sha256':sha256_file(self.csv)}
        with self.assertRaisesRegex(ValueError,'non-hourly'):read_hourly(self.csv,m)
    def test_duplicate_hour(self):
        df=self.df.copy();df.loc[50,'timestamp_utc']=df.loc[49,'timestamp_utc'];df.to_csv(self.csv,index=False)
        m={**self.meta,'source_sha256':sha256_file(self.csv)}
        with self.assertRaisesRegex(ValueError,'duplicate'):read_hourly(self.csv,m)
    def test_mixed_country(self):
        df=self.df.copy();df.loc[8,'country']='AT';df.to_csv(self.csv,index=False)
        m={**self.meta,'source_sha256':sha256_file(self.csv)}
        with self.assertRaisesRegex(ValueError,'mixed'):read_hourly(self.csv,m)
    def test_missing_timezone(self):
        with self.assertRaisesRegex(ValueError,'timezone'):read_hourly(self.csv,{**self.meta,'local_timezone':'Mars/Olympus'})
    def test_thresholds_must_be_qualified(self):
        with self.assertRaisesRegex(ValueError,'threshold qualification'):
            detect_events(self.inp(),self.meta,{**self.threshold,'threshold_basis':'undefined'})
    def test_country_not_averaged(self):
        ev=detect_events(self.inp(),self.meta,self.threshold)
        e1={**ev[0],'weather_member':'WS07','country':'ES','site_id':'Valencia'}
        e2={**ev[1],'weather_member':'WS11','country':'SK','site_id':'Turiec'}
        x=propose_weather_members([e1,e2],12)
        self.assertEqual(x['members'],['WS07','WS11'])
    def test_budget_does_not_discard_extreme(self):
        e=detect_events(self.inp(),self.meta,self.threshold)
        e2={**e[0],'weather_member':'WS25'}
        x=propose_weather_members([e[0],e2,e[1]],budget=1)
        # Baseline ties have deterministic stable assignment, may leave 1 protected.
        self.assertIn(x['status'],('PROVISIONAL_METEOROLOGICAL_EVENT_COVERAGE','BLOCKED_EXTREME_COVERAGE_EXCEEDS_BUDGET'))
        distinct=[{**e[0],'weather_member':f'WS{j:02d}','country':chr(65+j),'site_id':str(j)} for j in range(1,5)]
        x=propose_weather_members(distinct,2)
        self.assertEqual(x['status'],'BLOCKED_EXTREME_COVERAGE_EXCEEDS_BUDGET')
    def test_full_export(self):
        m=self.root/'meta.json';c=self.root/'cfg.json';m.write_text(json.dumps(self.meta));c.write_text(json.dumps(self.threshold));out=self.root/'out';r=produce(self.csv,m,c,out)
        self.assertTrue((out/'weather_living_events.json').exists());self.assertEqual(len(r['events']),2)
        self.assertEqual(r['status'],'RESEARCH_NOT_MODEL_RUNTIME')
    def test_empty_episode_blocked(self):
        x=propose_weather_members([])
        self.assertEqual(x['status'],'BLOCKED_NO_QUALIFIED_METEOROLOGICAL_EVENTS')
    def test_date_alignment_dst(self):
        self.df['timestamp_utc']=pd.date_range('2024-03-17',periods=len(self.df),freq='h',tz='UTC').strftime('%Y-%m-%dT%H:%M:%SZ')
        self.df['air_temperature_c']=18.0
        self.df.to_csv(self.csv,index=False)
        m={**self.meta,'source_sha256':sha256_file(self.csv)}
        # DST spring transition creates 23h local day, not a missing UTC hour.
        d=detect_events(read_hourly(self.csv,m),m,self.threshold)
        self.assertEqual(d,[])

if __name__=='__main__': unittest.main()
