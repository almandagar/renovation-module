"""Research-only weather -> living-conditions *exposure* screening.

This module is NOT a thermal solver, epidemiological risk estimator, climate model,
urban weather generator, or replacement for the three existing visual-only duck-
curve overlays. It selects *weather events*, not buildings, from qualified hourly
meteorology and reports exposure and possible adaptation relevance, not measured
indoor comfort or health outcomes. ERAA demand/renewable CF matrices cannot be
substituted for meteorology. No national runtime side effects.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from datetime import timedelta
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd

KINDS = ("heatwave", "cold_spell")
REQUIRED = ("timestamp_utc", "weather_member", "country", "site_id", "air_temperature_c")
HOUR_NS = pd.Timedelta(hours=1)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open('rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _require_string(obj:dict, name:str):
    if not isinstance(obj.get(name), str) or not obj[name].strip():
        raise ValueError(f'missing/invalid provenance: {name}')


def read_hourly(path:Path, provenance:dict) -> pd.DataFrame:
    """Read one chronologically real, contiguous site/member hourly UTC series.

    A declared, complete provenance is still not independent verification.
    Non-real chronologies (e.g. TMY) are allowed for other uses, but refused here.
    """
    for name in ('source_id','source_provider','weather_member','country', 'site_id',
                 'local_timezone','source_calendar','member_chronology_id','unit'):
        _require_string(provenance,name)
    if provenance.get('unit') != 'degree_Celsius':
        raise ValueError('air-temperature unit must be degree_Celsius')
    if provenance.get('source_calendar') != 'real_chronological_hourly_UTC':
        raise ValueError('TMY, stitched or unqualified chronology cannot determine event duration')
    if provenance.get('source_type') != 'hourly_meteorological_air_temperature':
        raise ValueError('electricity profiles and model demand cannot substitute for hourly meteorology')
    if provenance.get('data_alignment_status') != 'verified_source_hour_mapping':
        raise ValueError('hour/member chronology is not qualified')
    try: ZoneInfo(provenance['local_timezone'])
    except Exception as e: raise ValueError('unknown local timezone') from e
    if provenance.get('source_sha256') != sha256_file(path):
        raise ValueError('source fingerprint mismatch')

    df = pd.read_csv(path)
    absent = [x for x in REQUIRED if x not in df.columns]
    if absent: raise ValueError('required weather columns missing: ' + ','.join(absent))
    if len(df) < 24 * 7:
        raise ValueError('at least seven full days required for event screening')
    for key in ('weather_member','country','site_id'):
        vals=df[key].dropna().unique().tolist()
        if vals!=[provenance[key]]:
            raise ValueError(f'{key}: mixed/mismatched member or location')
    raw=df['timestamp_utc'].astype(str)
    if not raw.str.contains(r'(?:Z|[+-]\d\d:\d\d)$',regex=True).all():
        raise ValueError('timestamp_utc requires explicit UTC offset, not naive local time')
    t=pd.to_datetime(raw,utc=True,errors='raise')
    if t.isna().any() or not t.is_monotonic_increasing or t.duplicated().any():
        raise ValueError('duplicate/nonmonotonic timestamp')
    dt=(t[1:].array-t[:-1].array)
    if not (dt == HOUR_NS).all():
        raise ValueError('missing/non-hourly weather timestamps')
    if not np.isfinite(pd.to_numeric(df['air_temperature_c'],errors='coerce')).all():
        raise ValueError('missing/invalid outdoor air temperature')
    temp=df['air_temperature_c'].astype(float)
    if not temp.between(-90,65).all():
        raise ValueError('implausible air temperature')
    if 'relative_humidity_pct' in df:
        rh=pd.to_numeric(df['relative_humidity_pct'],errors='coerce')
        if not np.isfinite(rh).all() or not rh.between(0,100).all():
            raise ValueError('invalid relative humidity')
    if 'wind_speed_m_s' in df:
        wind=pd.to_numeric(df['wind_speed_m_s'],errors='coerce')
        if not np.isfinite(wind).all() or (wind<0).any():
            raise ValueError('invalid wind speed')
    out=df.copy();out['timestamp_utc']=t
    local=t.dt.tz_convert(ZoneInfo(provenance['local_timezone']))
    out['local_date']=local.dt.date
    out['local_hour']=local.dt.hour
    return out


def _thresholds(cfg:dict, provenance:dict):
    """All numerical thresholds must have traceable site-specific source/basis."""
    for k in ('country','site_id','threshold_source','threshold_basis'):
        _require_string(cfg,k)
    if cfg['country']!=provenance['country'] or cfg['site_id']!=provenance['site_id']:
        raise ValueError('site threshold mismatch')
    if cfg['threshold_basis'] not in ('official_local_definition','declared_research_sensitivity'):
        raise ValueError('invalid threshold qualification')
    p=('hot_daily_max_c','warm_night_min_c','cold_daily_mean_c')
    if any(k not in cfg for k in p):
        raise ValueError('site-specific cold, hot and warm-night thresholds all required')
    for k in p:
        v=cfg[k]
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not np.isfinite(v):
            raise ValueError(f'invalid threshold {k}')
    if cfg['cold_daily_mean_c']>=cfg['hot_daily_max_c']:
        raise ValueError('cold threshold must be lower than hot threshold')
    for name in ('min_heatwave_days','min_cold_spell_days'):
        if not isinstance(cfg.get(name),int) or cfg[name]<2:
            raise ValueError(f'need explicit episode duration: {name}')


def _runs(mask: pd.Series, min_length:int):
    """Consecutive true dated days, broken by any false day."""
    hits=[];lo=None
    for pos,value in enumerate(mask.to_numpy(bool)):
        if value and lo is None:lo=pos
        if not value and lo is not None:
            if pos-lo>=min_length:hits.append((lo,pos))
            lo=None
    if lo is not None and len(mask)-lo>=min_length:hits.append((lo,len(mask)))
    return hits


def _daily_weather(df:pd.DataFrame)->pd.DataFrame:
    d=df.groupby('local_date',sort=True)['air_temperature_c'].agg(['min','max','mean','count'])
    # DST days legitimately have 23 or 25 hours. Do not emit incomplete edge days.
    d=d[d['count'].between(23,25)].copy()
    # Night to morning of date D = 21:00-23:00 on D-1 plus 00:00-07:00 on D.
    night_date=pd.to_datetime(df['local_date']) + pd.to_timedelta((df['local_hour']>=21).astype(int),unit='D')
    night=df[(df['local_hour']>=21)|(df['local_hour']<=7)].copy()
    night['night_end_date']=night_date.loc[night.index].dt.date
    n=night.groupby('night_end_date')['air_temperature_c'].agg(['min','count'])
    # Full night: 11 hours, or 10/12 across clock shifts.
    n=n[n['count'].between(10,12)]
    d['night_min']=n['min']
    return d


def _event_row(days:pd.DataFrame, weather:pd.DataFrame, cfg:dict, prov:dict,
               kind:str, first:int,last:int)->dict:
    cut=days.iloc[first:last];start=cut.index[0];end=cut.index[-1]
    # 7 days prior in original synchronized UTC chronology; no stitched weather.
    region=weather[(weather['local_date']>=start)&(weather['local_date']<=end)]
    begin_utc=region['timestamp_utc'].min()
    before=begin_utc-pd.Timedelta(days=7)
    has_pre=(weather['timestamp_utc'].min()<=before)
    night=cut['night_min'].dropna()
    warm=night.ge(cfg['warm_night_min_c'])
    run_max=max([end-start for start,end in _runs(warm,1)],default=0) if not warm.empty else 0
    if kind=='heatwave':
        severity=(cut['max']-cfg['hot_daily_max_c']).clip(lower=0).sum()
        descriptor='Sustained hot days; repeated warm nights may limit relief during sleep.'
        adaptation='Evaluate shading, safe night ventilation, urban cooling and heat-health preparedness.'
    else:
        severity=(cfg['cold_daily_mean_c']-cut['mean']).clip(lower=0).sum()
        descriptor='Sustained cold exposure; heating demand and dependence on heating-service continuity may rise.'
        adaptation='Evaluate priority envelope improvements, reliable heat service and cold-weather assistance.'
    return {'weather_member':prov['weather_member'],'country':prov['country'],'site_id':prov['site_id'],
            'event_kind':kind,'start_local':str(start),'end_local':str(end),'duration_days':len(cut),
            'max_air_temperature_c':round(float(cut['max'].max()),3),
            'min_air_temperature_c':round(float(cut['min'].min()),3),
            'min_night_temperature_c':round(float(night.min()),3) if not night.empty else None,
            'warm_night_count':int(warm.sum()),'longest_warm_night_run':int(run_max),
            'degree_days_beyond_threshold':round(float(severity),3),
            'antecedent_7d_available':bool(has_pre),'first_event_utc':begin_utc.isoformat(),
            'threshold_basis':cfg['threshold_basis'],'threshold_source':cfg['threshold_source'],
            'exposure_interpretation':descriptor,'adaptation_signal':adaptation,
            'indoor_temperature':None,'measured_health_effect':None,
            'data_status':'METEOROLOGICAL_EXPOSURE_ONLY_NOT_INDOOR_COMFORT'}


def detect_events(data:pd.DataFrame, provenance:dict, thresholds:dict)->list[dict]:
    _thresholds(thresholds,provenance)
    daily=_daily_weather(data)
    # Interruption in dates is forbidden; partial calendar end days excluded.
    if len(daily)<3:raise ValueError('insufficient complete local days')
    dates=pd.to_datetime(daily.index)
    if not ((dates[1:].values-dates[:-1].values)==np.timedelta64(1,'D')).all():
        raise ValueError('missing calendar day in event weather series')
    out=[]
    for kind,threshold_col,check,minlen in (
        ('heatwave','max',lambda a:a>=thresholds['hot_daily_max_c'],thresholds['min_heatwave_days']),
        ('cold_spell','mean',lambda a:a<=thresholds['cold_daily_mean_c'],thresholds['min_cold_spell_days'])):
        for start,end in _runs(check(daily[threshold_col]),minlen):
            out.append(_event_row(daily,data,thresholds,provenance,kind,start,end))
    return sorted(out,key=lambda x:(x['start_local'],x['event_kind']))


def propose_weather_members(episodes:list[dict],budget:int=12):
    """Country/site event protection, NOT a national or probability-weighted sample.

    Protect different weather responses: hottest, longest heatwave, warmest
    nights, coldest, longest cold spell; no country aggregation or legacy WS locks.
    With >budget protected IDs return blocked, never silently discard extremes.
    """
    if budget<1:raise ValueError('budget must be positive')
    if not episodes:
        return {'status':'BLOCKED_NO_QUALIFIED_METEOROLOGICAL_EVENTS', 'members':[], 'protected_by':{}}
    m={};reasons={}
    for key in sorted({(r['country'],r['site_id']) for r in episodes}):
        subset=[r for r in episodes if (r['country'],r['site_id'])==key]
        hot=[r for r in subset if r['event_kind']=='heatwave']
        cold=[r for r in subset if r['event_kind']=='cold_spell']
        criteria=[]
        if hot:
            criteria.extend([('hottest_spell', max(hot,key=lambda x:(x['degree_days_beyond_threshold'],x['duration_days']))),
                             ('longest_heatwave',max(hot,key=lambda x:(x['duration_days'],x['degree_days_beyond_threshold']))),
                             ('warm_night_run',max(hot,key=lambda x:(x['longest_warm_night_run'],x['warm_night_count'],x['duration_days'])))])
        if cold:
            criteria.extend([('coldest_spell',max(cold,key=lambda x:(x['degree_days_beyond_threshold'],x['duration_days']))),
                             ('longest_cold_spell',max(cold,key=lambda x:(x['duration_days'],x['degree_days_beyond_threshold'])))])
        for tag,row in criteria:
            ws=row['weather_member'];reasons.setdefault(ws,[]).append(f'{key[0]}:{key[1]}:{tag}')
    protected=sorted(reasons)
    if len(protected)>budget:
        return {'status':'BLOCKED_EXTREME_COVERAGE_EXCEEDS_BUDGET', 'required_distinct_members':len(protected),
                'budget':budget,'protected_members':protected,'protected_by':reasons,
                'recommendation':'retain a compact event library or increase full-year budget; do not erase country extremes'}
    return {'status':'PROVISIONAL_METEOROLOGICAL_EVENT_COVERAGE', 'members':protected, 'budget':budget,
            'protected_by':reasons,'not_probability_weighted':True,'not_adequacy_selected':True,
            'qualification':'No whole-stock energy/comfort validation; country/site meteorology only.'}


def produce(path:Path,manifest:Path,thresholds:Path,output_dir:Path,budget:int=12)->dict:
    provenance=json.loads(manifest.read_text(encoding='utf8'))
    cfg=json.loads(thresholds.read_text(encoding='utf8'))
    d=read_hourly(path,provenance);events=detect_events(d,provenance,cfg)
    select=propose_weather_members(events,budget)
    output_dir.mkdir(parents=True,exist_ok=True)
    out={'schema':'weather-living-exposure/1','status':'RESEARCH_NOT_MODEL_RUNTIME','source':provenance,
         'thresholds':cfg,'events':events,'selection':select,
         'notes':['Extreme weather affects everyday living; no building-specific resilience certification.',
                  'Indoor comfort and health outcomes require additional evidence and are NOT inferred here.',
                  'Dunkelflaute, cold still spell, river-temperature curtailment remain separate visual-only duck-curve overlays.',
                  'No automatic link from ERAA electricity-profile weather IDs to qualified meteorology.']}
    (output_dir/'weather_living_events.json').write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    return out


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--weather',type=Path,required=True)
    p.add_argument('--provenance',type=Path,required=True)
    p.add_argument('--thresholds',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--max-years',type=int,default=12)
    a=p.parse_args()
    result=produce(a.weather,a.provenance,a.thresholds,a.output_dir,a.max_years)
    print(json.dumps({'status':result['status'],'episodes':len(result['events']),
                      'selection':result['selection']},indent=2))

if __name__=='__main__':main()
