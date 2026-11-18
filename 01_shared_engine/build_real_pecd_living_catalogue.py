"""Research-only source-grounded 36-member PECD extreme-weather catalogue.

Builds weather-living-exposure/2 from connected official source files. This is an
OUTDOOR exposure screen (not indoor, UHI, health, or probability assessment).
Climate model years 2025--2036 are model projection sequences, not actual observed
calendar years or independent measured forecasts. Source timezone not established.
Leap days were removed by upstream PECD importer: 8760 hour model-years.
"""
from __future__ import annotations
import argparse, hashlib, json, itertools
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd

CC=('AT','BE','CZ','DE','ES','FR','NL','SK')
MODELS=('CMR5','ECE3','MEHR')
YEAR0=2025
SOURCES=('temperature_c','population_weighted_temperature_c','wind_speed_10m_m_s','ghi_w_m2')

def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def member(model,year):
    return f'WS{1+MODELS.index(model)*12+year-YEAR0:02d}'

def read_model_file(root,model,var):
    p=root/f'{model}_{var}.csv.gz'
    d=pd.read_csv(p,compression='gzip')
    if list(d.columns)!=['climate_model_code','Date',*[c+'00' for c in CC]]: raise ValueError(f'{p}: invalid columns')
    if len(d)!=12*8760 or not (d.climate_model_code==model).all():raise ValueError(f'{p}: invalid length or model code')
    dt=pd.to_datetime(d.pop('Date'),errors='raise')
    d=d.drop(columns='climate_model_code')
    if not dt.is_monotonic_increasing or dt.duplicated().any():raise ValueError(f'{p}: timestamp errors')
    years=dt.dt.year.to_numpy()
    if set(years)!=set(range(2025,2037)) or not all(np.count_nonzero(years==y)==8760 for y in range(2025,2037)):
        raise ValueError(f'{p}: non-8760 calendar years')
    # The upstream importer drops leap day in 2028, 2032, 2036. Clock remains same time-of-day.
    if any((dt.dt.month.eq(2)&dt.dt.day.eq(29))):raise ValueError('Leap day unexpectedly present')
    # Per-year 365-day civil-clock progression; source deliberately removes Feb29.
    expected=pd.date_range('2025-01-01',periods=8760,freq='h').strftime('%m-%d %H:%M:%S').to_numpy()
    for yy in range(2025,2037):
        actual=dt[dt.dt.year.eq(yy)].dt.strftime('%m-%d %H:%M:%S').to_numpy()
        if not np.array_equal(actual,expected):raise ValueError(f'{p}: noncanonical missing/reordered 365-day hours for {yy}')

    x=d.to_numpy(float)
    if not np.isfinite(x).all():raise ValueError(f'{p}: nonfinite')
    if var.endswith('temperature_c') and ((x<-90)|(x>70)).any(): raise ValueError(f'{p}: implausible Celsius')
    if var == 'wind_speed_10m_m_s' and (x<0).any():raise ValueError(f'{p}: negative wind')
    if var == 'ghi_w_m2':
        # A single MEHR negative nighttime value (-0.01045 W/m2) is numerical noise;
        # normalize for the derived event-context mean only, retain source SHA.
        if (x<-.1).any():raise ValueError(f'{p}: negative irradiance outside rounding tolerance')
        x=np.maximum(0.0,x)
    return dt,x,sha(p)

def base_thresholds(raw_temperature):
    p=raw_temperature
    d=pd.read_csv(p,compression='gzip')
    if list(d.columns)!=['Date',*[c+'00' for c in CC]]:raise ValueError('Invalid historic ERA5 columns')
    t=pd.to_datetime(d.pop('Date'),errors='raise')
    y=t.dt.year.to_numpy()
    if y.min()!=1980 or y.max()!=2022:raise ValueError('Historical ERA5 missing 1980--2022')
    if not np.isfinite(d.to_numpy(float)).all():raise ValueError('ERA5 nonfinite')
    season=t.dt.month.to_numpy();date=t.dt.floor('D');hour=t.dt.hour.to_numpy()
    thresholds={}
    for c in CC:
        col=d[c+'00'].to_numpy(float)
        g=pd.DataFrame({'date':date,'T':col,'hour':hour,'month':season})
        summer=g[g.month.isin((6,7,8))].groupby('date').agg(daymax=('T','max'), nightmin=('T',lambda s: float(s.min())))
        # Explicit 00:00--06:00 SOURCE-CLOCK minimum, cannot yet label true local sleeping-night exposure.
        n=g[g.month.isin((6,7,8))&(g.hour<=6)].groupby('date').T.min()
        winter=g[g.month.isin((12,1,2))].groupby('date').T.mean()
        thresholds[c]={'hot_p95_summer_daily_max_c':float(summer.daymax.quantile(.95)),
          'cold_p05_winter_daily_mean_c':float(winter.quantile(.05)),
          'warm_p90_summer_00_06_min_c':float(n.quantile(.90)),
          'baseline':'ERA5 PECD national-zone 2m temperature 1980-2022',
          'classification':'declared_research_sensitivity_not_official_or_bias_corrected',
          'source_clock':'naive PECD Date; UTC alignment and local-zone timezone NOT independently confirmed'}
    return thresholds,sha(p)

def runs(flag,min_length):
    a=np.r_[False,np.asarray(flag,dtype=bool),False]
    boundaries=np.flatnonzero(np.diff(a.astype(np.int8)))
    return [(int(i),int(j)) for i,j in zip(boundaries[0::2],boundaries[1::2]) if j-i>=min_length]

def process(year,model,country,tvec,popvec,wvec,ghivec,thresholds):
    if len(tvec)!=8760:raise ValueError('expected 8760')
    # The importer writes a 365-day model year; not a local UTC-offset-corrected chronology.
    v=np.asarray(tvec).reshape(365,24)
    wp=np.asarray(wvec).reshape(365,24)
    solar=np.asarray(ghivec).reshape(365,24)
    pop=np.asarray(popvec).reshape(365,24)
    dailymax=v.max(1);dailymin=v.min(1);dailymean=v.mean(1)
    # 00--06 source-hour proxy, not confidently local night.
    overnight=v[:,:7].min(1)
    hot_thr=thresholds['hot_p95_summer_daily_max_c']
    cold_thr=thresholds['cold_p05_winter_daily_mean_c']
    night_thr=thresholds['warm_p90_summer_00_06_min_c']
    is_hot=dailymax>=hot_thr
    is_cold=dailymean<=cold_thr
    is_warm=overnight>=night_thr
    # 365-day calendar month/day locations taken from non-leap 2025 to avoid 2028/2032/2036 skipped leap days.
    dates=pd.date_range('2025-01-01',periods=365,freq='D')
    ev=[]
    for kind,flags,minimum in [('heatwave',is_hot,3),('cold_spell',is_cold,3),('warm_night_sequence',is_warm,2)]:
        for start,end in runs(flags,minimum):
            x=v[start:end].flatten();wm=wp[start:end].flatten();ss=solar[start:end].flatten()
            severity=float(np.maximum(dailymax[start:end]-hot_thr,0).sum()) if kind=='heatwave' else (
              float(np.maximum(cold_thr-dailymean[start:end],0).sum()) if kind=='cold_spell' else float(np.maximum(overnight[start:end]-night_thr,0).sum()))
            ev.append({'member':member(model,year),'model':model,'scenario_year':year,'country':country,
               'kind':kind,'start_mmdd':dates[start].strftime('%m-%d'),'end_mmdd':dates[end-1].strftime('%m-%d'),
               'start_day_index':start,'duration_days':end-start,'severity_degree_days':round(severity,3),
               'max_t_c':round(float(x.max()),3),'min_t_c':round(float(x.min()),3),
               'warm_nights_in_event':int(is_warm[start:end].sum()),
               'mean_wind_m_s':round(float(wm.mean()),3),'mean_ghi_w_m2':round(float(ss.mean()),3),
               'antecedent_7d_available':bool(start>=7),'date_semantics':'model_365_day_calendar_not_observed_year',
               'timebase':'source_clock_unverified_local_night_proxy',
               'interpretation':'OUTDOOR_METEOROLOGICAL_EXPOSURE_NOT_INDOOR_COMFORT'})
    row={'member':member(model,year),'model':model,'scenario_year':year,'country':country,
      'annual_mean_2m_t_c':round(float(v.mean()),3),'annual_mean_population_weighted_2m_t_c':round(float(pop.mean()),3),
      'min_hourly_t_c':round(float(v.min()),3),'max_hourly_t_c':round(float(v.max()),3),
      'hottest_7d_mean_daily_max_c':round(float(np.convolve(dailymax,np.ones(7)/7,'valid').max()),3),
      'coldest_7d_mean_daily_mean_c':round(float(np.convolve(dailymean,np.ones(7)/7,'valid').min()),3),
      'warm_nights_source_clock_count':int(is_warm.sum()),
      'longest_warm_night_run':max([e-s for s,e in runs(is_warm,1)],default=0),
      'heatwave_days':int(sum(e-s for s,e in runs(is_hot,3))),
      'cold_spell_days':int(sum(e-s for s,e in runs(is_cold,3))),
      'heatwave_episode_count':sum(e['kind']=='heatwave' for e in ev),
      'cold_spell_episode_count':sum(e['kind']=='cold_spell' for e in ev),
      'warm_night_episode_count':sum(e['kind']=='warm_night_sequence' for e in ev),
      'max_heatwave_severity_dd':round(max([e['severity_degree_days'] for e in ev if e['kind']=='heatwave'],default=0.),3),
      'max_cold_spell_severity_dd':round(max([e['severity_degree_days'] for e in ev if e['kind']=='cold_spell'],default=0.),3),
      'longest_heatwave_days':max([e['duration_days'] for e in ev if e['kind']=='heatwave'],default=0),
      'longest_cold_spell_days':max([e['duration_days'] for e in ev if e['kind']=='cold_spell'],default=0),
      'source_clock_not_time_zone_verified':True}
    return row,ev

def choose_member_coverage(df,budget=12):
    """Preserve country-level primary hazard max events. Fail when budget too small."""
    cols=['max_heatwave_severity_dd','max_cold_spell_severity_dd','longest_heatwave_days',
      'longest_cold_spell_days','longest_warm_night_run','hottest_7d_mean_daily_max_c']
    # coldest must use min not max.
    protected={}
    for c,g in df.groupby('country'):
        for feat in cols+['coldest_7d_mean_daily_mean_c']:
            ix=g[feat].idxmin() if feat=='coldest_7d_mean_daily_mean_c' else g[feat].idxmax()
            ws=g.loc[ix,'member'];protected.setdefault(ws,[]).append(f'{c}:{feat}')
    if len(protected)>budget:
        return {'status':'BUDGET_BLOCKED_COUNTRY_EXTREMES','minimum_distinct_years':len(protected),
                'budget_requested':budget,'mandatory_members':sorted(protected),
                'reasons':protected,'recommended':'Use event library; do not delete country-specific extremes to meet arbitrary year budget.'}
    return {'status':'PROVISIONAL_METEOROLOGICAL_EXTREME_COVERAGE','protected_members':sorted(protected),
            'count':len(protected),'budget_requested':budget,'reasons':protected}

def minimize_missed_extremes(df, protected_ids, sizes=(8,10,12,13)):
    """Exhaustive subsets of protected weather members, balanced by climate hazard.

    Normalized regret for each of seven country-level extrema; three hot, three
    cold and one night metric have equal *group* weight. This does not validate
    weather models or imply return probabilities.
    """
    hot=('max_heatwave_severity_dd','longest_heatwave_days','hottest_7d_mean_daily_max_c')
    cold=('max_cold_spell_severity_dd','longest_cold_spell_days','coldest_7d_mean_daily_mean_c')
    night=('longest_warm_night_run',)
    features=[]
    for cc,g in df.groupby('country'):
        for grp,metrics in (('heat',hot),('cold',cold),('warm_nights',night)):
            for metric in metrics:
                vals=dict(zip(g.member,g[metric]));lower=metric=='coldest_7d_mean_daily_mean_c'
                best=min(vals.values()) if lower else max(vals.values())
                worst=max(vals.values()) if lower else min(vals.values())
                spread=max(abs(best-worst),1e-9)
                features.append((cc,grp,metric,vals,best,spread,lower,1/(3*len(metrics)*len(CC))))
    results={}
    for k in sizes:
        if k>len(protected_ids):continue
        champion=None
        for case in itertools.combinations(protected_ids,k):
            regrets=[];weighted=0.;misses=[]
            for country,grp,m,vals,best,spread,lower,weight in features:
                observed=min(vals[y] for y in case) if lower else max(vals[y] for y in case)
                regret=max(0.,((observed-best) if lower else (best-observed))/spread)
                weighted+=regret*weight;regrets.append(regret)
                if regret>1e-8:misses.append({'country':country,'group':grp,'metric':m,
                  'all36_best':float(best),'subset_best':float(observed),'regret_on_36_range':float(regret)})
            key=(round(max(regrets),12),round(weighted,12),len(misses),case)
            if champion is None or key<champion[0]:champion=(key,case,misses)
        key,case,misses=champion
        results[str(k)]={'selected':list(case),'worst_normalized_regret':key[0],
           'mean_equal_group_weighted_regret':key[1],
           'missed_country_extrema':len(misses),'missed':misses,
           'event_only_members':sorted(set(protected_ids)-set(case)),
           'not_validated_as_national_thermal_ensemble':True}
    return results


def build(raw,climate,out,budget=12):
    out.mkdir(parents=True,exist_ok=True)
    thresholds,base_sha=base_thresholds(raw/'temperature_c.csv.gz')
    provenance={'historical_raw_temperature_sha256':base_sha,'source_mapping':'WeatherScenarios_Mapping.xlsx',
      'source_utc_timebase':'NOT_INDEPENDENTLY_VERIFIED',
      'weather_member_365day_model_calendar':True,
      'model_scenario_years':'2025..2036; physical model projections not observed climate years',
      'variables':'2m temp, population-weighted 2m temp, 10m wind, GHI',
      'source_file_sha256':{},'threshold_source':'1980-2022 ERA5 PECD country-zone historical 2m temperature',
      'not_official_climate_hazard_boundaries':True,'model_bias_correction':'NOT_PERFORMED',
      'not_actual_local_urban_meteorology':True,'relative_humidity_and_river_water':'NOT_AVAILABLE'}
    legacy_weighted=raw/'population_weighted_temperature_c.csv.gz'
    if legacy_weighted.exists():
        # PECD historical imported weighted-temperature data have a major unit defect.
        # Do not guess its cause or silently alter/repair the source.
        legacy_sample=pd.read_csv(legacy_weighted,compression='gzip',nrows=24)
        vals=legacy_sample[[c+'00' for c in CC]].to_numpy(float)
        provenance['historical_population_weighted_source_warning']={
            'sha256':sha(legacy_weighted),
            'first_day_range_c':[float(vals.min()),float(vals.max())],
            'status':'QUARANTINED_IMPLAUSIBLE_CELSIUS',
            'action':'EXCLUDED_FROM_HISTORICAL_THRESHOLDS; independent source/units audit needed'}
    provenance['small_ghi_rounding_anomaly']={
        'source':'MEHR_ghi_w_m2.csv.gz','observed_min_w_m2':-0.010445744,
        'negative_source_values':1,
        'analysis_handling':'clamped to zero for derived context; source fingerprint retained'}
    catalog=[];episodes=[]
    for model in MODELS:
        loaded={var:read_model_file(climate,model,var) for var in SOURCES}
        provenance['source_file_sha256'].update({f'{model}_{var}.csv.gz':val[2] for var,val in loaded.items()})
        all_dates=[val[0].to_numpy() for val in loaded.values()]
        if any(not np.array_equal(z,all_dates[0]) for z in all_dates[1:]):raise ValueError('Mismatched climate-family variable time axes')
        dt=loaded['temperature_c'][0]; yrs=dt.dt.year.to_numpy()
        for year in range(2025,2037):
            ix=np.flatnonzero(yrs==year)
            if len(ix)!=8760:raise ValueError('Bad member year')
            for i,c in enumerate(CC):
                x=loaded['temperature_c'][1][ix,i]
                pop=loaded['population_weighted_temperature_c'][1][ix,i]
                wind=loaded['wind_speed_10m_m_s'][1][ix,i]
                ghi=loaded['ghi_w_m2'][1][ix,i]
                row,ev=process(year,model,c,x,pop,wind,ghi,thresholds[c])
                catalog.append(row);episodes.extend(ev)
    df=pd.DataFrame(catalog).sort_values(['member','country'])
    edf=pd.DataFrame(episodes).sort_values(['member','country','start_day_index','kind'])
    sel=choose_member_coverage(df,budget)
    compact=minimize_missed_extremes(df,sel.get('mandatory_members',sel.get('protected_members',[])))
    # Retention ratio of previous electricity subset for local severe maxima.
    electrical={'WS01','WS06','WS08','WS18','WS19','WS22','WS24','WS25','WS30','WS31','WS32','WS33'}
    mandatory=set(sel.get('mandatory_members',sel.get('protected_members',[])))
    comparison={'electricity_provisional_members':sorted(electrical),'thermal_mandatory_count':len(mandatory),
       'thermal_mandatory_covered_by_electricity':len(mandatory&electrical),
       'thermal_mandatory_missing_from_electricity':sorted(mandatory-electrical),
       'electricity_members_not_mandatory_thermal':sorted(electrical-mandatory)}
    df.to_csv(out/'WS36_EU8_living_weather_exposure_metrics.csv',index=False)
    edf.to_csv(out/'WS36_EU8_living_weather_episodes.csv',index=False)
    pd.DataFrame([{'country':c,**v} for c,v in thresholds.items()]).to_csv(out/'PECD_ERA5_historical_research_thresholds.csv',index=False)
    summary={'schema':'living-weather-pecd-source/1','status':'RESEARCH_METEOROLOGICAL_EXPOSURE_NO_RUNTIME_PROMOTION',
      'members':36,'countries':list(CC),'source_manifest':provenance,'episodes':len(episodes),
      'threshold_method':'1980--2022 ERA5 JJA Tmax p95 / DJF Tmean p05 / JJA 00--06 min p90',
      'model_family_year_mapping':{member(m,y):{'model':m,'year':y} for m in MODELS for y in range(2025,2037)},
      'selection':sel,'compact_full_year_options':compact,'electricity_selection_comparison':comparison,
      'limits':['No humidity, dewpoint, river temperatures, soil moisture, local UHI or urban night-time observations.',
                'Model projection years, not actual 2025-2036 weather observations. Source clock timezone unverified.',
                'GCM versus ERA5 reference threshold bias uncorrected; qualitative exploratory rankings only.',
                'Area-aggregated national source zones; not cities, valleys or bedrooms.',
                'Leap days removed by PECD importer, preserve 365-day model-hour sequence.',
                'Exposure is outdoor weather; indoor temperature and health outcome not inferred.',
                'Existing risk overlays and national engine unchanged.']}
    pd.DataFrame([{'size':int(k),'selected_members':';'.join(v['selected']), 'event_only_members':';'.join(v['event_only_members']),
      'country_extreme_metrics_missed':v['missed_country_extrema'],'max_normalized_regret':v['worst_normalized_regret'],
      'equal_group_weighted_regret':v['mean_equal_group_weighted_regret']} for k,v in compact.items()]).to_csv(out/'WS36_living_weather_8_10_12_13_sensitivity.csv',index=False)
    (out/'WS36_EU8_living_weather_qualification.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n')
    return summary,df,edf

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--raw',type=Path,required=True);a.add_argument('--climate',type=Path,required=True)
    a.add_argument('--output-dir',type=Path,required=True);a.add_argument('--max-years',type=int,default=12)
    p=a.parse_args();s,d,e=build(p.raw,p.climate,p.output_dir,p.max_years)
    print(json.dumps({'members':s['members'],'zones':len(d),'episodes':s['episodes'],'selection':s['selection']['status'],
       'required_member_count':s['selection'].get('minimum_distinct_years',s['selection'].get('count')),
       'electric_overlap':s['electricity_selection_comparison']['thermal_mandatory_covered_by_electricity']},indent=2))
