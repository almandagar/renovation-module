"""Bounded quasi-steady ONE-zone outdoor pressure network.

Not CONTAM, ISO certification, multizone IAQ or measured infiltration. All flows
use one reference-density volume convention (Boussinesq approximation). Leakage
and opening coefficients are normalised by conditioned FLOOR area, allowing
cohort splits without duplicating absolute fans or airflows. Wind coefficients,
leakage distribution and pressure exponents remain explicit evidence/priors.
"""
from math import isfinite

def number(x,label,minimum=None,maximum=None):
    if isinstance(x,bool) or not isinstance(x,(int,float)) or not isfinite(x):raise ValueError('Invalid '+label)
    if minimum is not None and x<minimum:raise ValueError('Invalid '+label)
    if maximum is not None and x>maximum:raise ValueError('Invalid '+label)
    return x

def evidence(x,label):
    if not isinstance(x,dict) or not x.get('source_ref') or x.get('evidence_class') not in ('OBSERVED','SOURCE_DERIVED','MODEL_PRIOR'):
        raise ValueError('Source and evidence class required: '+label)

def resolve_airflow(cell,period,indoor_c):
    a=cell['airflow_model'];evidence(a,'airflow model')
    if a.get('schema')!='single-zone-pressure/1' or a.get('system') not in ('natural','extract'):
        raise ValueError('Only natural/extract single-zone pressure models supported')
    if a.get('reference_density_convention')!='BOUSSINESQ_CONSTANT_REFERENCE_VOLUME':raise ValueError('Explicit reference-density convention required')
    area=number(cell['area_m2'],'conditioned area',1e-12)
    vol=number(a['volume_m3_per_floor_m2'],'volume ratio',1e-12)
    if a.get('use_cell_leakage'):
        leak=cell.get('leakage_state',{}).get('outcome')
        if not leak or leak.get('role') not in ('measured','assumed_achieved'):raise ValueError('Achieved cell leakage state required')
        if not a.get('state_boundary_compatible_source'):raise ValueError('Cell leakage boundary compatibility required')
        lo,hi=leak['bounds'];number(lo,'leakage lower',0);number(hi,'leakage upper',lo)
        choice=a.get('bounds_choice')
        if choice not in ('lower','upper','midpoint'):raise ValueError('Explicit leakage bound selection required')
        value={'lower':lo,'upper':hi,'midpoint':(lo+hi)/2}[choice]
    else:
        leak=a['leakage'];evidence(leak,'pressure leakage');value=number(leak['value'],'leakage',0)
    if not leak.get('test_boundary_ref') or not leak.get('source_ref'):raise ValueError('Leakage test boundary or explicit test-boundary prior required')
    if leak['metric']=='n50':q50=value*vol
    elif leak['metric']=='qE50':q50=value*number(a['test_envelope_m2_per_floor_m2'],'test envelope ratio',1e-12)
    else:raise ValueError('Unknown leakage metric')
    exponent=number(a['pressure_exponent'],'pressure exponent',.5,1)
    if not a.get('pressure_exponent_source_ref'):raise ValueError('Pressure exponent provenance required')
    tin=number(indoor_c,'indoor temperature',-10,40);tout=number(period['outdoor_c'],'outdoor temperature',-70,60)
    wind=number(period['wind_speed_m_s'],'local wind speed',0,50)
    if not period.get('wind_source_ref'):raise ValueError('Local wind evidence/prior required')
    rho=number(a['reference_air_density_kg_m3'],'reference density',.8,1.5)
    cp=number(a['air_heat_capacity_wh_m3k'],'air heat capacity',.2,.5)
    fan=number(a['fan_w_per_floor_m2'],'fan power intensity',0)
    extract=number(a['extract_m3_h_per_floor_m2'],'extract intensity',0)
    if a['system']=='natural' and (extract or fan):raise ValueError('Natural system cannot silently contain mechanical extract/fan')
    if a.get('effective_recovery',0)!=0:raise ValueError('No heat recovery in this natural/extract route')
    paths=a['background_paths']
    if not paths or abs(sum(number(p['share'],'leakage share',0,1) for p in paths)-1)>1e-9:raise ValueError('Leakage-path shares must sum to one')
    channels=[]
    for p in paths:
        evidence(p,'background path')
        channels.append((p,q50*p['share']/50**exponent,exponent,'background'))
    for p in a.get('openings',[]):
        evidence(p,'opening')
        if p.get('kind') not in ('intentional','window'):raise ValueError('Explicit opening type required')
        if not p.get('excluded_from_background_test_source'):raise ValueError('Opening/background nonoverlap evidence required')
        channels.append((p,number(p['coefficient_m3_h_per_floor_m2_pa_n'],'opening coefficient',0),number(p['pressure_exponent'],'opening exponent',.5,1),p['kind']))
    if len({p['id'] for p,_,_,_ in channels})!=len(channels):raise ValueError('Duplicate airflow path')
    if not any(c>0 for _,c,_,_ in channels):raise ValueError('No conductive outdoor airflow path')
    drivers=[]
    for p,c,n,kind in channels:
        z=number(p['height_m'],'path height',0,100);cw=number(p['wind_pressure_coefficient'],'wind pressure coefficient',-2,2)
        # Exterior minus interior pressure. Cold-weather stack drives low-level
        # ingress and high-level egress. Solve the shared indoor reference pressure.
        drive=.5*rho*wind**2*cw-rho*9.80665*z*(1-(tout+273.15)/(tin+273.15))
        drivers.append((p['id'],drive,c,n,kind))
    def flows(pressure):
        return [(sid,c*((d-pressure)**n if d>=pressure else -((pressure-d)**n)),kind) for sid,d,c,n,kind in drivers]
    def residual(pressure):return sum(q for _,q,_ in flows(pressure))-extract
    lo=-500.;hi=500.
    if residual(lo)<0 or residual(hi)>0:raise ValueError('Required pressure exceeds qualified +/-500 Pa screen')
    for _ in range(120):
        mid=(lo+hi)/2
        if residual(mid)>0:lo=mid
        else:hi=mid
    pressure=(lo+hi)/2;f=flows(pressure);incoming=sum(max(0,q) for _,q,_ in f);outgoing=sum(max(0,-q) for _,q,_ in f)
    error=incoming-outgoing-extract
    if abs(error)>1e-8*max(1,incoming,outgoing,extract):raise ValueError('Airflow balance failed')
    minimum=number(a['required_outdoor_m3_h_per_floor_m2'],'outdoor service intensity',0)
    return {'hve_w_k_m2':cp*incoming,'fan_w':fan*area,'outdoor_m3_h':incoming*area,
      'service_screen_pass':incoming>=minimum,'service_screen_note':'Bulk outdoor flow only; not room-level ventilation/IAQ qualification',
      'pressure_pa':pressure,'airflow_balance_residual_m3_h':error*area,'exhaust_m3_h':extract*area,
      'outdoor_ach':incoming/vol,'leakage_q50_m3_h':q50*area,
      'path_flows_m3_h':{sid:q*area for sid,q,_ in f},'evidence_class':a['evidence_class'],
      'status':'BOUNDED_SINGLE_ZONE_PRESSURE_SCENARIO_NOT_VALIDATED'}
