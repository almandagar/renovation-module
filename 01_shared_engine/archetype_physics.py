"""Component-resolved physical library. SI units; useful SPACE heat only.
Period steady-state screen, not a dynamic simulation or comfort certification.
"""
from copy import deepcopy
from math import isfinite
from surface_state import surface_inventory

def positive(x, name, zero=True):
    if isinstance(x, bool) or not isinstance(x, (int,float)) or not isfinite(x) or x < 0 or (not zero and x == 0):
        raise ValueError('Invalid '+name)
    return x

def resolve(cell, library):
    a=deepcopy(library['archetypes'][cell['archetype_id']])
    for key in ('source_ref','construction_period','geometry','components','ventilation_w_k_m2','bridges_w_k_m2'):
        if key not in a: raise ValueError('Archetype missing '+key)
    a['geometry'].update(cell.get('geometry_override',{}))
    if cell.get('geometry_override') and not cell.get('geometry_source_ref'):
        raise ValueError('Local geometry requires a source or explicit prior reference')
    state=cell['state']; surfaces={}
    if set(state)!=set(a['components']): raise ValueError('Incomplete component state')
    for component, variants in a['components'].items():
        p=deepcopy(variants[state[component]])
        if not p.get('source_ref'): raise ValueError('Component source/prior missing')
        positive(p['u_w_m2k'],'U value')
        surfaces[component]=p
    inventory=surface_inventory(cell,library)
    for comp,p in surfaces.items():
        related=[r for r in inventory if r['component']==comp]
        total=sum(r['area_m2'] for r in related)
        p['surface_m2_per_floor_m2']=total/cell['area_m2']
        p['u_w_m2k']=sum(r['ua_w_k'] for r in related)/total if total else 0
        p['exposure_factor']=1
    return a,surfaces

def heat(cell, library, periods, indoor_c=None):
    """Quasi-steady space heat, with optional direct signed adjacent-zone exchange.

    Cell-level `adjacent_zone_temperatures_by_period` is a *complete*,
    source-identified temperature boundary for every non-exterior surface. It replaces that period's
    equivalent exposure factors, not its ventilation coefficient. It does not imply
    connected heat/air equations, neighbour setpoint predictions or dynamic comfort.
    """
    a,surfaces=resolve(cell,library); area=positive(cell['area_m2'],'area',False)
    inventory=surface_inventory(cell,library)
    fixed_h=sum(p['u_w_m2k']*p['surface_m2_per_floor_m2'] for p in surfaces.values())
    bridge=positive(a['bridges_w_k_m2'],'bridges')
    q=0.; hours=0.; fan_electricity=0.; interzone_signed_kwh=0.
    airflow_by_period=cell.get('operating_airflow_by_period')
    pressure_model=cell.get('airflow_model')
    if pressure_model is not None and airflow_by_period is not None:
        raise ValueError('One authoritative airflow route required')
    if len({p['id'] for p in periods})!=len(periods):
        raise ValueError('Duplicate weather period IDs')
    if airflow_by_period is not None and set(airflow_by_period)!={p['id'] for p in periods}:
        raise ValueError('Operating airflow records must match all periods')
    # Local neighbour temperatures must never leak into shared country weather.
    if any('adjacent_zone_temperatures_c' in p for p in periods):
        raise ValueError('Adjacent temperatures belong to a specific stock cell, not shared weather')
    zone_by_period=cell.get('adjacent_zone_temperatures_by_period')
    uses_direct=zone_by_period is not None
    if uses_direct and (not isinstance(zone_by_period,dict) or not {p['id'] for p in periods}.issubset(zone_by_period)):
        raise ValueError('Direct adjacent-zone mode requires local temperatures for every period')
    if uses_direct and cell.get('surface_inventory') is None:
        raise ValueError('Direct adjacent-zone mode requires an explicit thermal inventory')
    if uses_direct:
        required={r.get('adjacent_zone_id') for r in inventory if r['adjacent']!='exterior'}
        if None in required or '' in required:
            raise ValueError('Every non-exterior surface requires an adjacent_zone_id')
        if any(r.get('adjacent_zone_id') for r in inventory if r['adjacent']=='exterior'):
            raise ValueError('Exterior surfaces cannot use adjacent-zone temperature IDs')
    h=fixed_h+positive(a['ventilation_w_k_m2'],'ventilation')+bridge
    for p in periods:
        t=indoor_c if indoor_c is not None else cell.get('service_indoor_c',p['indoor_c'])
        if not -10<=t<=40 or not -70<=p['outdoor_c']<=60:
            raise ValueError('Temperature outside domain')
        duration=positive(p['hours'],'hours',False);hours+=duration
        ventilation=positive(a['ventilation_w_k_m2'],'ventilation')
        if pressure_model is not None:
            from airflow_pressure import resolve_airflow
            flow=resolve_airflow(cell,p,t)
            fan_electricity+=flow['fan_w']*duration/1000
            ventilation=flow['hve_w_k_m2']
        if airflow_by_period is not None:
            from airtightness_research import balanced_airflow
            flow=balanced_airflow(airflow_by_period[p['id']],area)
            fan_electricity+=flow['fan_w']*duration/1000
            ventilation=flow['hve_w_k_m2']
        if uses_direct:
            records=zone_by_period[p['id']]
            if not isinstance(records,dict) or set(records)!=required:
                raise ValueError('Adjacent-zone IDs must match the complete non-exterior boundary')
            zone_t={}
            for zid,v in records.items():
                if not isinstance(v,dict) or not v.get('source_ref') or v.get('evidence_class') not in ('OBSERVED','SOURCE_DERIVED','MODEL_PRIOR'):
                    raise ValueError('Adjacent-zone temperature requires source and evidence class')
                tv=v.get('temperature_c')
                if isinstance(tv,bool) or not isinstance(tv,(int,float)) or not isfinite(tv) or not -70<=tv<=60:
                    raise ValueError('Invalid adjacent-zone temperature')
                zone_t[zid]=tv
            transmitted=0.;interzone=0.
            for r in inventory:
                boundary_t=p['outdoor_c'] if r['adjacent']=='exterior' else zone_t[r['adjacent_zone_id']]
                watts=r['u_w_m2k']*r['area_m2']*(t-boundary_t)
                transmitted+=watts
                if r['adjacent']=='heated_neighbour':interzone+=watts
            # Signed internal heat transfer happens *before* the heating demand is
            # clipped at zero; never clip each individual wall or zone exchange.
            interzone_signed_kwh+=interzone*duration/1000
            demand_w=transmitted+(bridge+ventilation)*area*(t-p['outdoor_c'])-positive(p['usable_gains_w_m2'],'gains')*area
        else:
            period_h=fixed_h+bridge+ventilation
            demand_w=period_h*(t-p['outdoor_c'])*area-positive(p['usable_gains_w_m2'],'gains')*area
        q+=max(0,demand_w)*duration/1000
    if hours>8784.01:raise ValueError('Overlapping/excess annual weather exposure')
    system=cell['heating']; eff=positive(system['useful_per_final'],'efficiency/SPF',False)
    if system['carrier']!='HP_ELECTRICITY' and eff>1:raise ValueError('Non-HP efficiency >1')
    if system['carrier']=='HP_ELECTRICITY' and eff<=1:raise ValueError('HP SPF must exceed one')
    final=q/eff
    return {'useful_heat_kwh':q,'final_heat_kwh':final,'carrier':system['carrier'],
            'ambient_heat_kwh':q-final if system['carrier']=='HP_ELECTRICITY' else 0,
            'h_w_k':h*area if airflow_by_period is None and pressure_model is None and not uses_direct else None,'area_m2':area,
            'fan_electricity_kwh':fan_electricity,
            'adjacent_zone_mode':'DIRECT_SOURCE_TAGGED_PERIOD_TEMPERATURES' if uses_direct else 'EQUIVALENT_SCREEN',
            'interzone_exchange_kwh_signed':interzone_signed_kwh if uses_direct else None,
            'pm_kg':final*system['pm_kg_per_final_kwh'] if 'pm_kg_per_final_kwh' in system else None}

def floor_target_is_eligible(cell, package):
    """Optional, country-specified RAIII lower-boundary eligibility gate.

    A source/conditional-site status and a same-service performance screen
    are required. Unknown basement/ground condition is *not* absence of
    normal façade/roof/window renovation, nor zero floor heat loss.
    """
    if package.get('floor_gate')!='RAIII_SOURCE_BOUNDARY':return True
    e=cell.get('lower_boundary_qualification',{})
    if e.get('required_for_raiii') is not True and not e.get('comfort_defect_source_ref'):return False
    if (e.get('boundary_type') not in ('UNHEATED_BASEMENT_CEILING','EXPOSED_LOWER_SLAB')
            or e.get('evidence_class') not in ('SOURCE_MATCHED_ASSEMBLY','EXPLICIT_SCENARIO_HYPOTHESIS')
            or not e.get('source_ref') or not e.get('heat_screen_source_ref')
            or e.get('reason') not in ('FLOOR_CLOSES_RAIII_GAP','SOURCE_QUALIFIED_COLD_FLOOR_COMFORT_DEFECT')):
        raise ValueError('Floor RA III eligibility requires source-qualified thermal boundary and heat screen')
    a=e.get('post_envelope_without_floor_kwh_m2a')
    b=e.get('post_envelope_with_floor_kwh_m2a')
    limit=e.get('raiii_target_kwh_m2a')
    if any(not isinstance(v,(float,int)) or not isfinite(v) for v in (a,b,limit)) or not (0<limit<=70 and b<a):
        raise ValueError('Floor thermal screen is inconsistent')
    if e.get('required_for_raiii') and not (limit<a and b<=limit):
        raise ValueError('Floor RA III thermal target evidence is inconsistent')
    if not e.get('required_for_raiii') and e.get('reason')!='SOURCE_QUALIFIED_COLD_FLOOR_COMFORT_DEFECT':
        raise ValueError('Floor comfort exception requires a qualified symptom')
    return True

def package_effect(cell, package, library):
    """Actual explicit surfaces govern both UA and component work quantities.

    Package-level targets apply to all matching surfaces; surface_targets can
    override individual facade, glazing or attic surface states independently.
    """
    a,_=resolve(cell,library); items=surface_inventory(cell,library)
    result=deepcopy(cell);changed=[]; materials={};removed={};labour={};unknown=[]
    targets=package.get('targets',{});specific=package.get('surface_targets',{})
    if any(k not in {r['id'] for r in items} for k in specific):
        raise ValueError('Unknown targeted surface ID')
    for r in items:
        comp=r['component']; target=specific.get(r['id'],targets.get(comp))
        # Party walls are not energy-retrofit exterior facades; explicit work may still target them.
        if r['adjacent']=='heated_neighbour' and r['id'] not in specific and not package.get('include_zero_heat_surfaces',False):
            continue
        if target is None: continue
        # A performance-grade lower thermal boundary is optional, not a
        # generic component of every deep fabric package. The parent country
        # adapter qualifies this cell using actual/source-labelled adjacency
        # and a before/after same-service heat screen. Other components remain
        # eligible when the lower thermal boundary is unobserved.
        if comp=='floor' and not floor_target_is_eligible(cell,package):continue
        if target not in a['components'][comp]:raise ValueError('Unknown target variant')
        old=a['components'][comp][r['state']];new=a['components'][comp][target]
        if target==r['state'] or (new['u_w_m2k']>=old['u_w_m2k'] and not package.get('explicit_renewal',False)):
            continue
        result.setdefault('surface_states',{})[r['id']]=target
        changed.append(comp)
        ratio=r['area_m2']/cell['area_m2']
        for field,dest in [('installed_kg_m2',materials),('removed_kg_m2',removed),('task_hours_m2',labour)]:
            if field not in new:unknown.append(r['id']+':'+field);continue
            for name,qty in new[field].items():dest[name]=dest.get(name,0)+positive(qty,field)*ratio
    # Keep legacy component-state naming and successive-stage behaviour.
    for comp,target in targets.items():
        if comp not in a['components']:raise ValueError('Unknown targeted component')
        related=[r for r in items if r['component']==comp]
        if related and all(result.get('surface_states',{}).get(r['id'],r['state'])==target for r in related):
            result['state'][comp]=target
            for r in related:result.get('surface_states',{}).pop(r['id'],None)
    if 'heating' in package and package['heating']!=cell['heating']:
        result['heating']=deepcopy(package['heating']);changed.append('heating')
        for field,dest in [('installed_kg_m2',materials),('removed_kg_m2',removed),('task_hours_m2',labour)]:
            if field not in package:unknown.append('heating:'+field)
            for name,qty in package.get(field,{}).items():dest[name]=dest.get(name,0)+positive(qty,field)
    return result,list(dict.fromkeys(changed)),{'installed_kg':materials,'removed_kg':removed,'task_hours':labour,'unknown':unknown}

def local_hypothesis(cell, library, periods):
    """Export identifiable local geometry to the independent city-physical-tests/2 solver."""
    a,s=resolve(cell,library);area=cell['area_m2']
    inventory=surface_inventory(cell,library)
    if cell.get('airflow_model') is not None:
        raise ValueError('City physical tests v2 cannot represent pressure-network airflow')
    if cell.get('adjacent_zone_temperatures_by_period') is not None:
        raise ValueError('City physical tests v2 cannot represent local adjacent-zone temperatures')
    vent=a['ventilation_w_k_m2']*area
    if 'operating_airflow_by_period' in cell:
        from airtightness_research import balanced_airflow
        flows=cell['operating_airflow_by_period']
        if set(flows)!={p['id'] for p in periods}:
            raise ValueError('Local ventilation records must match all periods')
        values=[balanced_airflow(flows[p['id']],area)['hve_w_k_m2']*area for p in periods]
        if values and max(values)-min(values)>1e-8:
            raise ValueError('City physical tests v2 cannot represent varying period ventilation')
        vent=values[0]
    return {'id':cell['id'],'conditioned_area_m2':area,
      'external_surfaces':[{'area_m2':r['area_m2'],
         'u_w_m2k':r['u_w_m2k']*r['boundary_factor']} for r in inventory],
      'ventilation_w_k':vent,'thermal_bridges_w_k':area*a['bridges_w_k_m2'],
      'indoor_c_by_period':{p['id']:cell.get('service_indoor_c',p['indoor_c']) for p in periods},
      'usable_gains_w_by_period':{p['id']:p['usable_gains_w_m2']*area for p in periods}}
