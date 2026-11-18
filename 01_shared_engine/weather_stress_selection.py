"""Research-only ERAA WS01-WS36 stress-diversity selector.

Inputs: identical 8760h x 36-member ENTSO-E ERAA 2035 selected weather profiles
for 8 countries. Avoids probabilities and unidentifiable physical peak deficits.
Output: scenario IDs, feature table, marginal-extreme retention and provenance.

This module NEVER samples cities/weather independently by country; one WS ID is
selected across ALL participating countries and variables.
"""
from __future__ import annotations
import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

COUNTRIES = ('AT','BE','CZ','DE','ES','FR','NL','SK')
WEATHER_IDS = tuple(f'WS{i:02d}' for i in range(1,37))
CATEGORIES = ('demand_total','demand_heat_pumps','solar','wind_onshore','wind_offshore')
W = len(WEATHER_IDS)
H = 8760
WINTER = np.concatenate([np.arange(0, 90*24), np.arange(304*24, H)])
SUMMER = np.arange(151*24, 243*24)
SPRING = np.arange(59*24, 151*24)
METRIC_DIRECTIONS = {
    'winter_7d_demand': 'max',
    'winter_7d_hp': 'max',
    'winter_7d_joint_netstress': 'max',
    'winter_14d_joint_netstress': 'max',
    'winter_7d_crosscountry_wind_lull': 'max',
    'annual_14d_wind_lull': 'max',
    'winter_1d_total_demand': 'max',
    'summer_7d_total_demand': 'max',
    'spring_7d_solar_over_demand': 'max',
    'annual_7d_solar_over_demand': 'max',
    'country_divergence_winter': 'max',
    'annual_wind_shortfall': 'max',
}


def _sha(p:Path)->str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for c in iter(lambda:f.read(1024*1024),b''):h.update(c)
    return h.hexdigest()


def _rolling_mean(a:np.ndarray,hours:int)->np.ndarray:
    """Full contiguous windows, no wrap across end-of-year boundary."""
    if a.shape[0]<hours:raise ValueError('Not enough hours')
    c=np.vstack([np.zeros((1,a.shape[1])),np.cumsum(a,axis=0,dtype=np.float64)])
    return (c[hours:]-c[:-hours])/hours


def _sel_rolling_max(a:np.ndarray,hours:int,valid_start:np.ndarray)->np.ndarray:
    return np.max(_rolling_mean(a,hours)[valid_start],axis=0)


def _sel_rolling_min(a:np.ndarray,hours:int,valid_start:np.ndarray)->np.ndarray:
    return np.min(_rolling_mean(a,hours)[valid_start],axis=0)


def _valid_start(h:int,season:np.ndarray)->np.ndarray:
    s=np.zeros(H,dtype=bool);s[season]=True
    c=np.concatenate(([0],np.cumsum(s.astype(int))))
    valid=(c[h:]-c[:-h])==h
    if not valid.any():raise ValueError('Empty season for rolling span')
    return valid


def _validate_load_csv(path:Path)->np.ndarray:
    df=pd.read_csv(path,compression='gzip')
    if df.shape!=(H,W+1) or list(df.columns)!=['hour_of_year',*WEATHER_IDS]:
        raise ValueError(f'{path}: invalid 8760 x 36 weather-member schema: {df.shape}')
    if not np.array_equal(df.hour_of_year.to_numpy(),np.arange(H)):
        raise ValueError(f'{path}: nonsequential hour_of_year')
    x=df.loc[:,WEATHER_IDS].to_numpy(dtype=float)
    if not np.isfinite(x).all() or (x<0).any():raise ValueError(f'{path}: nonfinite/negative data')
    if 'wind_' in path.name or '_solar.' in path.name:
        if (x>1.001).any():raise ValueError(f'{path}: renewable capacity factor >1')
    return x


def load_profiles(directory:Path)->tuple[dict,dict]:
    profiles,provenance={},{}
    for cc in COUNTRIES:
        profiles[cc]={}
        for cat in CATEGORIES:
            name=f'{cc}_2035_{cat}.csv.gz'
            p=directory/name
            if not p.exists():
                if cat in ('wind_offshore','demand_heat_pumps'):continue
                raise FileNotFoundError(p)
            a=_validate_load_csv(p)
            # Zero-only HP matrix is a missing climate signal, not no cold weather.
            if cat=='demand_heat_pumps' and a.max()==0:
                provenance[name]={'sha256':_sha(p),'status':'ZERO_ONLY_HP_EXCLUDED_FROM_FEATURE','bytes':p.stat().st_size}
                continue
            profiles[cc][cat]=a
            provenance[name]={'sha256':_sha(p),'status':'SOURCE_2035_ERAA','bytes':p.stat().st_size}
    return profiles,provenance


def calculate_features(profiles:dict)->pd.DataFrame:
    """Supply-neutral, normalized stress *indices*, not adequacy or temperatures.

    Each country carries equal weight, and offshore/onshore wind are averaged
    per technology (NOT installed-capacity weighted). These priors are disclosed.
    Solar generation uses daylight CF; winter night is never labelled a solar
    shortfall. Demand normalized by country's 36x8760 mean; HP demand likewise.
    """
    demand=[];hp=[];wind=[];solar=[];country_risk=[]
    for cc in COUNTRIES:
        x=profiles[cc]
        d=x['demand_total']/np.mean(x['demand_total'])
        demand.append(d)
        if 'demand_heat_pumps' in x:
            h=x['demand_heat_pumps'];hp.append(h/np.mean(h))
        ww=[x['wind_onshore']]
        if 'wind_offshore' in x:ww.append(x['wind_offshore'])
        wind.append(np.mean(ww,axis=0))
        solar.append(x['solar'])
    d=np.mean(demand,axis=0);w=np.mean(wind,axis=0);s=np.mean(solar,axis=0)
    hpav=np.mean(hp,axis=0)
    # A comparative composite, not physical net load. Solar daytime-only
    # contributions are normalized within full 7-/14-day blocks.
    # Climate-synchronized wind+solar scarcity and demand high each have
    # explicit bounded weights, NOT inferred installed capacities.
    stress=.5*d+.35*(1-w)+.15*(1-s)
    winter_week=_valid_start(168,WINTER);winter_14d=_valid_start(336,WINTER)
    summer_week=_valid_start(168,SUMMER);spring_week=_valid_start(168,SPRING)
    all_7=np.ones(H-168+1,dtype=bool)
    all_14=np.ones(H-336+1,dtype=bool)
    # Long synchronized wind lull: each country wind 7d mean below its
    # 36-year, 7-day bottom quartile; peak concurrent country count.
    wind_week=np.stack([_rolling_mean(wc,168) for wc in wind],axis=0)
    thresholds=np.quantile(wind_week,0.25,axis=(1,2))[:,None,None]
    n_lull=np.sum(wind_week<thresholds,axis=0)
    diversity=np.std(np.stack([_rolling_mean(z,168) for z in wind],axis=0),axis=0)
    # Solar/daylight and demand: coarse curtailment opportunity, no modeled generation.
    solar_ratio=_rolling_mean(s,168)/np.maximum(_rolling_mean(d,168),1.e-9)
    m={
        'winter_7d_demand':_sel_rolling_max(d,168,winter_week),
        'winter_7d_hp':_sel_rolling_max(hpav,168,winter_week),
        'winter_7d_joint_netstress':_sel_rolling_max(stress,168,winter_week),
        'winter_14d_joint_netstress':_sel_rolling_max(stress,336,winter_14d),
        'winter_7d_crosscountry_wind_lull':np.max(n_lull[winter_week],axis=0).astype(float),
        'annual_14d_wind_lull':1-_sel_rolling_min(w,336,all_14),
        'winter_1d_total_demand':_sel_rolling_max(d,24,_valid_start(24,WINTER)),
        'summer_7d_total_demand':_sel_rolling_max(d,168,summer_week),
        'spring_7d_solar_over_demand':np.max(solar_ratio[spring_week],axis=0),
        'annual_7d_solar_over_demand':np.max(solar_ratio[all_7],axis=0),
        'country_divergence_winter':np.max(diversity[winter_week],axis=0),
        'annual_wind_shortfall':1-np.mean(w,axis=0),
    }
    return pd.DataFrame(m,index=pd.Index(WEATHER_IDS,name='weather_member'))


def _robust_features(f:pd.DataFrame)->np.ndarray:
    a=f.to_numpy(float)
    scale=np.ptp(a,axis=0)
    scale=np.where(scale>1e-9,scale,1)
    return (a-np.min(a,axis=0))/scale


def _dist(x):
    return np.sqrt(np.mean((x[:,None,:]-x[None,:,:])**2,axis=2))


def choose(f:pd.DataFrame,k:int=12,anchors:tuple[str,...]=('WS08','WS18','WS19','WS24','WS32'))->tuple[list[str],dict]:
    """Protect each distinct single-metric worst year, then maximize coverage.

    There are <=12 risk metrics, but many share the same extreme member.
    If unique protected extremes exceed k, fail rather than quietly drop one.
    """
    if k<1 or k>len(f):raise ValueError('Invalid subset size')
    missing=set(anchors)-set(f.index)
    if missing:raise ValueError(f'Invalid anchor years: {missing}')
    protected=[];reason={}
    for a in anchors:
        if a not in protected:protected.append(a)
        reason.setdefault(a,[]).append('legacy_comparison_anchor')
    for col,direction in METRIC_DIRECTIONS.items():
        s=f[col];year=s.idxmax() if direction=='max' else s.idxmin()
        if year not in protected:protected.append(year)
        reason.setdefault(year,[]).append('extreme_'+col)
    if len(protected)>k:
        raise ValueError(f'Minimum {len(protected)} weather members needed for all extreme anchors; requested k={k}')
    x=_robust_features(f);distance=_dist(x);ids=list(f.index)
    selected=[ids.index(y) for y in protected]
    while len(selected)<k:
        remaining=[j for j in range(len(ids)) if j not in selected]
        # Farthest point from all selected, maximizing diversity of 36-member features.
        best=max(remaining,key=lambda j:(float(np.min(distance[j,selected])), -j))
        selected.append(best);reason[ids[best]]=['risk_feature_diversity']
    # Selection order = anchoring/priority order; sorted report separately.
    nearest=np.min(distance[:,selected],axis=1)
    qa={'requested_k':k,'captured_extreme_metrics':int(sum(any(y==f[c].idxmax() for y in (ids[i] for i in selected)) for c in METRIC_DIRECTIONS)),
        'total_extreme_metrics':len(METRIC_DIRECTIONS),'maximum_nearest_feature_distance':float(np.max(nearest)),
        'mean_nearest_feature_distance':float(np.mean(nearest)),
        'selection_reasons':reason,'anchors':list(anchors)}
    return [ids[i] for i in selected],qa


def select_and_export(root:Path,out:Path,count:int=12,anchors:tuple[str,...]=('WS08','WS18','WS19','WS24','WS32'))->dict:
    profiles,provenance=load_profiles(root)
    f=calculate_features(profiles)
    selected,qa=choose(f,count,anchors)
    out.mkdir(parents=True,exist_ok=True)
    f.to_csv(out/'WS36_2035_joint_risk_features.csv',float_format='%.9g')
    membership=pd.DataFrame({'member':list(WEATHER_IDS),'selected_12':[z in selected for z in WEATHER_IDS],
                            'selection_order':[selected.index(z)+1 if z in selected else '' for z in WEATHER_IDS],
                            'role':[';'.join(qa['selection_reasons'].get(z,[])) for z in WEATHER_IDS]})
    membership.to_csv(out/'WS36_to_stress12_selection.csv',index=False)
    qa_sizes={}
    for n in (8,10,12):
        try:
            subset,details=choose(f,n,anchors)
            qa_sizes[str(n)]={'subset':sorted(subset),'captured_extremes':details['captured_extreme_metrics'],
                              'max_dist':details['maximum_nearest_feature_distance'],
                              'mean_dist':details['mean_nearest_feature_distance']}
        except ValueError as exc:qa_sizes[str(n)]={'blocked':str(exc)}
    summary={'status':'PROVISIONAL_WEATHER_PROFILE_DIVERSITY_ONLY','selected':sorted(selected),
        'ordered_selection':selected,'not_probability_weighted':True,'member_ids_not_calendar_years':True,
        'number_of_source_weather_members':36,'countries':list(COUNTRIES),'weather_member_alignment':'same WS across all 8 countries',
        'coverage':qa,'subset_sensitivity':qa_sizes,
        'profile_source':'ERAA selected 2035 profiles, eight-country dispatch module, 36 weather members',
        'sources_sha256':provenance,
        'limitations':['Demand profiles are ERAA 2035 assumptions; not observed air temperature.',
          'Heat-pump profiles for CZ and FR are all zero and excluded from HP weather signal.',
          'Offshore and onshore wind are equal-weighted technologies, not installed-capacity-weighted.',
          'Eight countries are equal-weighted; scenario does not calculate MW net load, EENS or grid flows.',
          'Missing explicit temperature, humidity, precipitation, hydrology, river water, drought and UHI data.',
          'The full 36 weather members must be retained for out-of-sample risk checks.',
          'A climate-synchronized city EPW for each member has not been matched to ERAA weather IDs.',
          'Selected values are conditional stress cases, not sampling probabilities.']}
    (out/'stress12_selection_manifest.json').write_text(json.dumps(summary,indent=2)+'\n')
    return summary


def main():
    p=argparse.ArgumentParser();p.add_argument('--profiles',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--count',type=int,default=12)
    p.add_argument('--anchors',nargs='*',default=['WS08','WS18','WS19','WS24','WS32']);a=p.parse_args()
    s=select_and_export(a.profiles,a.output_dir,a.count,tuple(a.anchors))
    print(json.dumps({'status':s['status'],'selected':s['selected'],'coverage':s['coverage'],'sensitivity':s['subset_sensitivity']},indent=2))
if __name__=='__main__':main()
