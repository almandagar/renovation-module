"""Non-destructive, fail-closed urban weather input boundary for pyBuildingEnergy.

No UHI magnitudes are invented here. Input is either a measured/modelled hourly
urban-minus-background air-temperature increment (and optional other variables),
or a complete urban EPW from a qualified external urban climate model (UWG etc).

Source trace: UWG can morph rural EPW to an urban canyon; UrbClim provides spatial
urban air temperature. This adapter itself is NEITHER an urban microclimate model
nor an ISO 52016 solver. Surface thermal imagery is not ambient air temperature.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,math
from pathlib import Path
import numpy as np
import pandas as pd

N=8760
# EnergyPlus EPW zero-based fields.
DRYBULB=6; DEWPOINT=7; RH=8; GHI=13; DNI=14; DHI=15; WIND=21


def sha256(path:Path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for x in iter(lambda:f.read(1024*1024),b''):h.update(x)
    return h.hexdigest()


def read_epw(path:Path)->tuple[list[list[str]],list[list[str]]]:
    with path.open(newline='',encoding='utf-8-sig',errors='replace') as f:rows=list(csv.reader(f))
    if len(rows)!=N+8 or not rows[0] or rows[0][0].upper()!='LOCATION':
        raise ValueError('EPW must contain 8 header rows and exactly 8760 hourly rows')
    if any(len(z)<35 for z in rows[8:]):raise ValueError('Malformed EPW data columns')
    key=[(int(y[1]),int(y[2]),int(y[3])) for y in rows[8:]]
    if len(set(key))!=N:raise ValueError('EPW contains duplicate calendar positions')
    if not all(int(y[3]) in range(1,25) for y in rows[8:]):raise ValueError('EPW hour outside 1..24')
    for z in rows[8:]:
        for c in (DRYBULB,DEWPOINT,RH,WIND):
            if not math.isfinite(float(z[c])):raise ValueError('Non-finite weather field')
    return rows[:8],rows[8:]


def _svp(temp_c:float)->float:
    return 610.94*math.exp(17.625*temp_c/(temp_c+243.04))


def _rh_at_fixed_dewpoint(dewpoint_c:float,new_air_c:float)->float:
    return max(0.0,min(100.0,100*_svp(dewpoint_c)/_svp(new_air_c)))


def _check_evidence(meta:dict,mode:str):
    required=('climate_member','background_source_id','background_class','urban_zone_id',
              'urban_source_id','urban_source_method','validation_status','reference_alignment')
    missing=[x for x in required if not meta.get(x)]
    if missing:raise ValueError('Missing urban provenance: '+','.join(missing))
    if meta['background_class']!='nonurban_background':
        raise ValueError('UHI correction would be double-counted or reference ambiguous')
    if meta['reference_alignment']!='same_hour_same_weather_member':
        raise ValueError('Urban delta and baseline weather member/time alignment unverified')
    if mode=='qualified' and meta['validation_status']!='held_out_local_air_measurement_validated':
        raise ValueError('Qualified urban weather needs held-out air-temperature validation')
    if mode not in ('qualified','research'):
        raise ValueError('mode must be research or qualified')


def apply_urban_delta(base_epw:Path,delta_csv:Path,out_epw:Path,metadata:dict,mode:str='research')->dict:
    """Input CSV: sequential hour_of_year 0..8759, delta_t_air_C, optional local wind_speed_m_s and local_relative_humidity_pct.

    By default retain original dew point and recompute relative humidity at
    new temperature (constant water vapour approximation, NOT complete humidity
    simulation). If local RH measured/modelled, revise dewpoint consistently.
    Global radiation and ground temperature are UNMODIFIED; the external urban
    model must supply radiation/shading/boundary corrections separately.
    """
    _check_evidence(metadata,mode)
    hdr,rows=read_epw(base_epw)
    d=pd.read_csv(delta_csv)
    expected={'hour_of_year','delta_t_air_C'}
    if not expected.issubset(d.columns) or len(d)!=N or not np.array_equal(d.hour_of_year.to_numpy(),np.arange(N)):
        raise ValueError('Urban delta must cover precisely the aligned 8760 hourly positions')
    if not np.isfinite(d.delta_t_air_C).all() or (d.delta_t_air_C.abs()>20).any():
        raise ValueError('Unreasonable or invalid UHI air temperature delta; inspect sources')
    if 'wind_speed_m_s' in d:
        if not np.isfinite(d.wind_speed_m_s).all() or (d.wind_speed_m_s<0).any():raise ValueError('Invalid wind')
    if 'local_relative_humidity_pct' in d:
        if not np.isfinite(d.local_relative_humidity_pct).all() or not d.local_relative_humidity_pct.between(0,100).all():raise ValueError('Invalid relative humidity')
    out=[]
    for i,row in enumerate(rows):
        a=row.copy(); t=float(row[DRYBULB]);td=float(row[DEWPOINT]);new_t=t+float(d.delta_t_air_C.iloc[i]);
        if new_t< -100 or new_t>70:raise ValueError('Air temperature out of physical range')
        a[DRYBULB]=f'{new_t:.3f}'
        if 'local_relative_humidity_pct' in d:
            rh=float(d.local_relative_humidity_pct.iloc[i]);a[RH]=f'{rh:.1f}'
            # Invert saturation vapor pressure for dewpoint from new local RH.
            vp=max(_svp(new_t)*rh/100,0.01);z=math.log(vp/610.94);a[DEWPOINT]=f'{243.04*z/(17.625-z):.3f}'
        else:
            a[RH]=f'{_rh_at_fixed_dewpoint(td,new_t):.1f}'
            # Keep dewpoint, i.e., constant absolute humidity approximation.
        if 'wind_speed_m_s' in d:a[WIND]=f'{float(d.wind_speed_m_s.iloc[i]):.2f}'
        out.append(a)
    out_epw.parent.mkdir(parents=True,exist_ok=True)
    with out_epw.open('w',newline='',encoding='utf-8') as f:
        writer=csv.writer(f,lineterminator='\n');writer.writerows(hdr+out)
    read_epw(out_epw)
    report={'status':'QUALIFIED_EXTERNAL_DELTA' if mode=='qualified' else 'RESEARCH_ONLY_UNVALIDATED_URBAN_DELTA',
        'method':'external_urban_minus_nonurban_air_temperature_hourly',
        'not_an_urban_physics_model':True,'metadata':metadata,'base_epw_sha256':sha256(base_epw),
        'delta_csv_sha256':sha256(delta_csv),'urban_epw_sha256':sha256(out_epw),
        'delta_t_min_C':float(d.delta_t_air_C.min()),'delta_t_max_C':float(d.delta_t_air_C.max()),
        'delta_t_mean_C':float(d.delta_t_air_C.mean()),'hours':N,
        'radiation_change':'NONE; external shading/surface radiation needed',
        'ground_temperature_change':'NONE; urban ground separate input',
        'humidity_assumption':'hourly_local_RH' if 'local_relative_humidity_pct' in d else 'fixed_dewpoint_approximation',
        'wind_assumption':'hourly_local_wind' if 'wind_speed_m_s' in d else 'background_unchanged',
        'no_direct_scenario_probabilities':True,'not_an_energy_model':True}
    (out_epw.with_suffix('.urban_provenance.json')).write_text(json.dumps(report,indent=2)+'\n')
    return report


def validate_external_urban_epw(base_epw:Path,urban_epw:Path,meta:dict,mode:str='research')->dict:
    """Use this instead of applying another UHI correction to UWG output."""
    _check_evidence(meta,mode)
    bh,b=read_epw(base_epw);uh,u=read_epw(urban_epw)
    a=[(x[1],x[2],x[3]) for x in b];aa=[(x[1],x[2],x[3]) for x in u]
    if a!=aa:raise ValueError('Urban EPW hours do not match background EPW')
    diff=np.array([float(u[i][DRYBULB])-float(b[i][DRYBULB]) for i in range(N)])
    return {'status':'QUALIFIED_EXTERNAL_URBAN_EPW' if mode=='qualified' else 'RESEARCH_ONLY_EXTERNAL_URBAN_EPW',
        'mode':mode,'source':meta,'delta_t_min_C':float(diff.min()),'delta_t_max_C':float(diff.max()),
        'delta_t_mean_C':float(diff.mean()),'sha256_background':sha256(base_epw),'sha256_urban':sha256(urban_epw),
        'double_count_guard':'urban EPW is already adjusted; never apply another UHI delta'}


def main():
    p=argparse.ArgumentParser();p.add_argument('--base-epw',type=Path,required=True)
    p.add_argument('--urban-delta-csv',type=Path,required=True);p.add_argument('--out-epw',type=Path,required=True)
    p.add_argument('--metadata',type=Path,required=True);p.add_argument('--mode',choices=['research','qualified'],default='research')
    a=p.parse_args();res=apply_urban_delta(a.base_epw,a.urban_delta_csv,a.out_epw,json.loads(a.metadata.read_text()),a.mode)
    print(json.dumps(res,indent=2))
if __name__=='__main__':main()


def run_uwg_from_parameters(background_epw:Path,output_dir:Path,
                            parameters:dict,metadata:dict,mode:str='research')->dict:
    """Optional *real UWG* execution path; never substitutes made-up deltas.

    Mandatory morphology values must come from a documented urban zone, and
    the input EPW MUST be nonurban background for the matching weather member.
    No runtime use or derived results are claimed unless uwg is installed.
    """
    _check_evidence(metadata,mode)
    required={'bldheight','blddensity','vertohor','treecover','grasscover','zone'}
    missing=required-set(parameters)
    if missing:raise ValueError('Missing urban morphology parameters: '+','.join(sorted(missing)))
    if not 0 <= parameters['blddensity'] <= 1 or not 0 <= parameters['treecover'] <= 1 or not 0 <= parameters['grasscover'] <= 1:
        raise ValueError('Invalid neighbourhood cover fractions')
    if parameters['treecover']+parameters['grasscover']>1.000001:
        raise ValueError('Urban vegetation cover fractions exceed one')
    if parameters['bldheight']<=0 or parameters['vertohor']<0:
        raise ValueError('Invalid urban morphology')
    try:
        from uwg import UWG
    except ImportError as exc:
        raise RuntimeError('UWG is not installed: external weather model execution was not performed') from exc
    read_epw(background_epw)
    output_dir.mkdir(parents=True,exist_ok=True)
    target_name=f"{background_epw.stem}_{metadata['urban_zone_id']}_UWG.epw"
    model=UWG.from_param_args(epw_path=str(background_epw),new_epw_dir=str(output_dir),new_epw_name=target_name,**parameters)
    model.generate();model.simulate();model.write_epw()
    result_path=Path(model.new_epw_path)
    result=validate_external_urban_epw(background_epw,result_path,metadata,mode)
    result.update({'urban_model':'UWG','parameters':parameters,'output_file':result_path.name})
    result_path.with_suffix('.urban_provenance.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
