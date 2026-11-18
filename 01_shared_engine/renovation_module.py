"""Cohort-state engine v3.2 (additive surface/boundary event contract). Historical replay >=2011; forecast branches share baseline.
No monetary feasibility gate. No national calibration or automatic promotion.
"""
from copy import deepcopy
from datetime import date
from collections import defaultdict
from itertools import chain
from math import isclose, isfinite
from archetype_physics import heat,package_effect,positive
from surface_state import apply_physical_change, check_historical_state_evidence
from airtightness_research import apply_completed_event
from construction_flow import prepare,wlc
from renovation_stock import totals,validate,take,match,check_conservation,QUANTITIES,substitute
from recipient_priority import rank
from actor_formation import evaluate as evaluate_actor_formation

def dt(s):return date.fromisoformat(s)

def periods_for(bundle,cell,year):
    key=cell.get('climate_id',cell['place_id'])
    climate=bundle['weather'][key]
    return climate.get(str(year),climate.get('reference')) or climate[str(year)]

def capacity_fraction(inv,area,year,region,bundle,used,reserved=None):
    fraction=1.;unknown=list(inv.get('unknown',[]))
    cap=bundle.get('capacity',{}).get(region,{}).get(str(year),{})
    for kind in ('task_hours','installed_kg'):
        for name,rate in inv.get(kind,{}).items():
            positive(rate,'resource intensity')
            if not rate:continue
            key=(region,year,kind,name)
            available=cap.get(kind,{}).get(name)
            if available is None:unknown.append('capacity:'+':'.join(map(str,key)));continue
            positive(available,'capacity')
            held=reserved.get(key,0.) if reserved is not None else 0.
            fraction=min(fraction,max(0,available-used[key]-held)/(rate*area))
    return max(0,min(1,fraction)),unknown

CAPACITY_KINDS=('task_hours','installed_kg')
QUEUE_KINDS=('renovation','conversion','airtightness')
EPS=1e-8

def _quantity(value,label):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not isfinite(value) or value<0:
        raise ValueError('Invalid '+label)
    return value

def _resources(design):
    return {k:design.get(k,{}) for k in CAPACITY_KINDS}

def _resource_amounts(inv,region,year,area):
    for kind in CAPACITY_KINDS:
        for name,rate in inv.get(kind,{}).items():
            _quantity(rate,'resource intensity')
            if rate:
                yield (region,year,kind,name),rate*area

# Purposes are supplied by Essential Housing / the construction owner, not inferred
# from building age, location, or renovation priority. A legacy residential event
# without a label remains discretionary for backward compatibility; a zero-dwelling
# event without a label is protected as UNCLASSIFIED_NONRES (not "essential").
CONSTRUCTION_PURPOSES={
    'DISCRETIONARY_ADDITIONAL_RES','ESSENTIAL_ADDITIONAL_RES',
    'SAFETY_REPLACEMENT','ESSENTIAL_NONRES'
}
PROTECTED_PURPOSES={'ESSENTIAL_ADDITIONAL_RES','SAFETY_REPLACEMENT','ESSENTIAL_NONRES',
                    'UNCLASSIFIED_NONRES'}


def _construction_purpose(e):
    purpose=e.get('construction_purpose')
    if purpose is None:
        return 'LEGACY_DISCRETIONARY_RES' if e['dwellings']>EPS else 'UNCLASSIFIED_NONRES'
    if purpose not in CONSTRUCTION_PURPOSES:
        raise ValueError('Unknown construction purpose: '+str(purpose))
    if purpose=='ESSENTIAL_NONRES' and e['dwellings']>EPS:
        raise ValueError('ESSENTIAL_NONRES cannot carry dwelling counts; split mixed projects')
    if purpose!='ESSENTIAL_NONRES' and e['dwellings']<=EPS:
        raise ValueError('Residential construction purpose requires positive dwellings')
    if purpose=='SAFETY_REPLACEMENT' and not e.get('replacement_source_ref'):
        raise ValueError('Safety replacement requires replacement_source_ref')
    if purpose.startswith('ESSENTIAL_') and not e.get('essential_source_ref'):
        raise ValueError('Essential construction requires essential_source_ref')
    return purpose


def _pas_construction(bundle,events,baseline,end):
    """Protect essential, replacement and nonres events; reduce discretionary homes.

    The dwelling trajectory is by COMPLETION year, released resources by precise
    cancelled START date (capacity itself is still supplied annually).
    """
    raw=bundle['pas_newbuild_dwellings']
    if not isinstance(raw,dict):
        raise ValueError('PAS newbuild trajectory must map capacity region to completion year and dwellings')
    targets={}
    last_completion_year=date.fromordinal(end.toordinal()-1).year
    for region,years in raw.items():
        if not region or not isinstance(years,dict):
            raise ValueError('Invalid PAS newbuild region')
        for year,value in years.items():
            y=int(year)
            if str(y)!=year or not baseline.year<=y<=last_completion_year:
                raise ValueError('Invalid PAS newbuild completion year')
            targets[region,y]=_quantity(value,'PAS newbuild dwellings')
    groups=defaultdict(list)
    for e in events:
        if e['kind']=='newbuild' and dt(e['start_date'])>=baseline:
            if dt(e['completion_date'])>=end:
                raise ValueError('PAS trajectory cannot target newbuild completion outside the horizon')
            _construction_purpose(e)
            groups[e.get('capacity_region',e['place_id']),dt(e['completion_date']).year].append(e)
    # No zero-dwelling hospital group needs a dummy residential target.
    required={key for key,members in groups.items() if sum(e['dwellings'] for e in members)>EPS}
    if required-targets.keys():
        raise ValueError('PAS trajectory missing forecast newbuild region/year: '+str(sorted(required-targets.keys())))
    if targets.keys()-groups.keys() and any(targets[k]>EPS for k in targets.keys()-groups.keys()):
        raise ValueError('PAS dwelling target without matching planned construction group')
    reserve=defaultdict(float);released=defaultdict(float);activated={}
    release_events=[];bookings={};report=[];omitted=set()
    for group in sorted(groups.keys() | targets.keys()):
        members=groups[group]
        protected=[e for e in members if e.get('committed') is True or _construction_purpose(e) in PROTECTED_PURPOSES]
        discretionary=[e for e in members if e not in protected]
        locked=sum(e['dwellings'] for e in protected)
        uncommitted=sum(e['dwellings'] for e in discretionary)
        target=targets.get(group,0.)
        if target<locked-EPS or target>locked+uncommitted+EPS:
            raise ValueError(f'PAS newbuild target {group}={target} outside committed/planned bounds [{locked}, {locked+uncommitted}]')
        factor=min(1.,max(0.,(target-locked)/uncommitted)) if uncommitted else 1.
        report.append({'region':group[0],'completion_year':group[1],
                       'original_dwellings':locked+uncommitted,'retained_dwellings':target,
                       'protected_dwellings':locked,
                       'protected_event_ids':[e['id'] for e in protected],
                       'scaled_event_ids':[e['id'] for e in discretionary]})
        for e in members:
            purpose=_construction_purpose(e)
            scale=1. if e in protected else factor
            original=e['area_m2'];day=dt(e['start_date']);year=day.year;region=group[0]
            if scale<1.-EPS and original*(1.-scale)>EPS:
                _,design,_=prepare(e,bundle['library'],bundle.get('standards',[]))
                resources=dict(_resource_amounts(_resources(design),region,year,original*(1.-scale)))
                for key,amount in resources.items():released[key]+=amount
                activated[region]=min(day,activated.get(region,day))
                release_events.append({'event_id':e['id'],'construction_purpose':purpose,
                   'capacity_region':region,'start_date':day.isoformat(),
                   'completion_year':group[1],'cancelled_area_m2':original*(1.-scale),
                   'resources':[{'kind':k[2],'name':k[3],'amount':v} for k,v in sorted(resources.items())]})
            if scale<=EPS:
                omitted.add(e['id']);continue
            for quantity in QUANTITIES:e[quantity]*=scale
            _,design,_=prepare(e,bundle['library'],bundle.get('standards',[]))
            amounts=dict(_resource_amounts(_resources(design),region,year,e['area_m2']))
            bookings[e['id']]=amounts
            for key,amount in amounts.items():reserve[key]+=amount
    # The RETAINED construction must be feasible in the named annual caps.
    # The uncut PI pipeline may itself be infeasible; a matched comparison will
    # then be UNQUALIFIED, not silently assumed to deliver all original events.
    for (region,year,kind,name),amount in reserve.items():
        cap=bundle.get('capacity',{}).get(region,{}).get(str(year),{}).get(kind,{}).get(name)
        if cap is not None and amount>_quantity(cap,'PAS retained newbuild capacity')+EPS:
            raise ValueError(f'PAS retained newbuild exceeds {region}/{year}/{kind}/{name} capacity')
    # A November cancellation cannot lend its annual resource reservation to
    # ordinary February work. Hold the eliminated PI allocation until its
    # original start; this can conservatively block work if original PI was
    # over-capacity, but will never invent pre-release capacity.
    for key,amount in released.items():reserve[key]+=amount
    return ([e for e in events if e['id'] not in omitted],reserve,bookings,
            activated,released,report,release_events)


def _pas_queue(events,baseline,end,activated,scenario,*,early_headroom=False):
    """Stage eligible requests no earlier than the first actual cancelled start."""
    if not activated:return {},{},set()
    plans={};checkpoints={};extra_dates=set(activated.values())
    for e in events:
        if dt(e['start_date'])<baseline or e['kind'] not in QUEUE_KINDS:continue
        ready=dt(e.get('pas_ready_from',e['start_date']))
        if ready>dt(e['start_date']):
            raise ValueError('PAS ready date cannot follow the ordinary start; update the ordinary schedule')
        if e.get('diffusion_dates'):
            ready=max(ready,dt(e['diffusion_dates'][scenario['timing']]))
        limit=_quantity(e.get('pas_eligible_area_m2',e['area_m2']),'PAS eligible work area')
        if limit<e['area_m2']:
            raise ValueError('PAS eligible work area cannot be less than scheduled area')
        plans[e['id']]=(e,ready,limit,dt(e['completion_date'])-dt(e['start_date']))
    for year in range(min(day.year for day in activated.values()),end.year+1):
        # The PI-headroom comparator may use real idle capacity before a later
        # PI construction start. Original construction is already reserved,
        # so this cannot borrow resources booked for that future project.
        latest=(max(baseline,date(year,1,1)) if early_headroom else
                max([max(baseline,date(year,1,1))]+[dt(e['start_date']) for e in events
                    if dt(e['start_date']).year==year and dt(e['start_date'])>=baseline]))
        for e,ready,_,duration in plans.values():
            # Renovation requests often select cohorts without a place_id.
            # A candidate's actual place is checked again at dispatch.
            regions=([e['capacity_region']] if e.get('capacity_region') else activated.keys())
            for region in regions:
                if region not in activated:continue
                day=max(latest,ready,activated[region])
                if day.year!=year or day>=end or day+duration>end:continue
                checkpoints.setdefault(day,set()).add(e['id'])
                extra_dates.update((day,day+duration))
    return plans,checkpoints,extra_dates


def _counterfactual_targets(events,baseline,end):
    """Exact uncut PI events in the SAME PAS programme, not a different PI package."""
    result=defaultdict(dict)
    by=defaultdict(float)
    for e in events:
        if e['kind']=='newbuild' and baseline<=dt(e['start_date']) and dt(e['completion_date'])<end:
            by[e.get('capacity_region',e['place_id']),dt(e['completion_date']).year]+=e['dwellings']
    for (region,year),quantity in by.items():result[region][str(year)]=quantity
    return dict(result)


def _work_by_request(result):
    """Compare TOTAL admitted work, not just PAS_EXTRA: PI headroom counts too."""
    areas=defaultdict(float)
    for row in result['ledger']:
        if row.get('status')=='START_ACCOUNT' and row.get('pas_request_id'):
            areas[row['pas_request_id']]+=row['committed_area_m2']
    return areas


def _pas_attribution(pas,pi):
    actual=_work_by_request(pas);counter=_work_by_request(pi)
    def extra_days(result):
        days=defaultdict(set)
        for item in result['ledger']:
            if item.get('status')=='START_ACCOUNT' and item.get('pas_extra') and item.get('committed_area_m2',0)>EPS:
                days[item['pas_request_id']].add(item['date'])
        return days
    actual_days=extra_days(pas);counter_days=extra_days(pi)
    names=sorted(set(actual)|set(counter))
    rows=[{'request_id':name,'pas_admitted_area_m2':actual[name],
            'pi_headroom_counterfactual_area_m2':counter[name],
            'incremental_area_m2':max(0.,actual[name]-counter[name]),
            'signed_difference_area_m2':actual[name]-counter[name],
            'headroom_or_other_non_incremental_area_m2':min(actual[name],counter[name]),
            'pas_extra_start_dates':sorted(actual_days.get(name,())),
            'pi_headroom_extra_start_dates':sorted(counter_days.get(name,()))}
          for name in names]
    return {'status':'MATCHED_SAME_PAS_PROGRAMME_PI_NEWBUILD_UNCUT',
        'method':'Paired rerun with identical work, dates, stock, institutional readiness and resource caps; only the newbuild trajectory changes. The counterfactual can use pre-existing PI headroom. Annual caps are NOT subannual capacity observations.',
        'requests':rows,
        'total_net_incremental_area_m2':sum(r['incremental_area_m2'] for r in rows),
        'total_signed_difference_area_m2':sum(r['signed_difference_area_m2'] for r in rows),
        'total_pi_headroom_or_other_area_m2':sum(r['headroom_or_other_non_incremental_area_m2'] for r in rows)}

def run(bundle,scenario,*,_counterfactual_regions=None):
    if bundle.get('schema')!='building-stock/2':raise ValueError('Expected building-stock/2; legacy aggregate inputs require explicit translation')
    from archetype_integration import prepare_bundle, validate_snapshot
    bundle=prepare_bundle(bundle)
    start=dt(bundle['history_start']);end=dt(bundle['end_date']);baseline=dt(bundle['forecast_start'])
    if not start<baseline<end:raise ValueError('Opening must precede forecast and end')
    # The national historical engine opens in/before 2011. A later snapshot is
    # permitted only as an EXPLICIT, unpromoted modelled stock state. This does
    # not backdate 2024 archetype conditions to the 2011 stock owner.
    snapshot=bundle.get('research_opening_snapshot')
    generic_snapshot=isinstance(snapshot,dict) and snapshot.get('schema')=='research-stock-snapshot/1'
    if generic_snapshot:validate_snapshot(bundle)
    if start.year>2011:
        if not generic_snapshot and (not isinstance(snapshot,dict) or snapshot.get('country')!=bundle.get('country') or \
           snapshot.get('as_of_date')!=bundle.get('history_start') or \
           snapshot.get('evidence_class')!='CONDITIONAL_MODEL_PRIOR_NOT_OBSERVED' or \
           snapshot.get('stock_boundary')!='FIXED_2021_KOSICE_PANEL_FAMILY_SURVIVORS' or \
           not snapshot.get('source_ref') or bundle.get('historical_events') or bundle.get('spatial_substitutions')):
            raise ValueError('Post-2011 opening requires a sourced research-only fixed-cohort snapshot, no historical replay')
    elif snapshot is not None:
        raise ValueError('Research snapshot cannot replace the historical 2011 opening')
    lib=bundle['library'];cells=deepcopy(bundle['opening_cells']);validate(cells,lib)
    for c in cells:
        if c['construction_period'][1]>=start.year:raise ValueError('Opening stock includes future construction')
        c.setdefault('origin',('RESEARCH_DATED_MODEL_SNAPSHOT' if generic_snapshot else 'RESEARCH_2024_MODEL_SNAPSHOT') if snapshot is not None else 'PRE_2011');c.setdefault('history',[])
        check_historical_state_evidence(c,bundle['history_start'])
        c['baseline_heat_intensity']=heat(c,lib,periods_for(bundle,c,baseline.year),20)['useful_heat_kwh']/c['area_m2']
    for sub in bundle.get('spatial_substitutions',[]):
        cells=substitute(cells,sub['parent_id'],sub['children'],lib)
    for c in cells:
        c.setdefault('origin',('RESEARCH_DATED_MODEL_SNAPSHOT' if generic_snapshot else 'RESEARCH_2024_MODEL_SNAPSHOT') if snapshot is not None else 'PRE_2011');c.setdefault('history',[])
        c.setdefault('baseline_heat_intensity',heat(c,lib,periods_for(bundle,c,baseline.year),20)['useful_heat_kwh']/c['area_m2'])
    expected=totals(cells);initial=deepcopy(expected);used=defaultdict(float)
    events=[];jobs=[];ledger=[];annual=[];snapshots={};warnings=[];sequence=0
    historical=deepcopy(bundle.get('historical_events',[]));future=deepcopy(scenario.get('events',[]))
    for e in historical:
        if not start<=dt(e['start_date'])<baseline:raise ValueError('Historical event outside historical period')
        if not e.get('source_ref'):raise ValueError('Historical event source required')
    for e in future:
        if dt(e['start_date'])<baseline:raise ValueError('Forecast cannot rewrite history')
        if snapshot is not None and e['kind']=='renovation':
            if e.get('site_access_basis')!='ASSUMED_CAPABLE_STRESS_NOT_OBSERVED' or \
               e.get('commissioning_basis')!='ASSUMED_PASS_STRESS_NOT_OBSERVED' or \
               not e.get('source_ref'):
                raise ValueError('Research renovation requires explicit conditional site access and commissioning assumptions')
    for e in historical+future:
        if e['kind'] not in ('renovation','demolition','newbuild','conversion','airtightness'):raise ValueError('Unknown flow')
        if dt(e['completion_date'])<dt(e['start_date']):raise ValueError('Completion before start')
        if dt(e['start_date'])>=end:raise ValueError('Start outside horizon')
        if not dt(e['start_date'])<baseline and e.get('diffusion_dates'):
            anchor=dt(e['diffusion_dates'][scenario['timing']]);old=dt(e['start_date'])
            if anchor>old:
                e['start_date']=anchor.isoformat();e['completion_date']=(dt(e['completion_date'])+(anchor-old)).isoformat()
        if dt(e['start_date'])>=end:
            ledger.append({'event_id':e['id'],'status':'DIFFUSION_AFTER_HORIZON','unmet_area_m2':e['area_m2']})
        else:events.append(e)
    if len({e['id'] for e in events})!=len(events):raise ValueError('Duplicate event ID')
    pas_active=scenario['pathway']=='PAS' and ('pas_newbuild_dwellings' in bundle or _counterfactual_regions is not None)
    reserved={};bookings={};activated={};released={};construction=[];release_events=[]
    plans={};checkpoints={};extra_dates=set()
    queue_used=defaultdict(float)
    if pas_active:
        if any(e['id'].startswith('PAS_EXTRA:') for e in events):
            raise ValueError('PAS_EXTRA: is a reserved generated event prefix')
        if _counterfactual_regions is not None:
            # Keep every source-planned event (including its nonres resource
            # demands) and permit the identical PAS programme to spend PI
            # headroom from forecast opening, without a newbuild reduction.
            shadow={**bundle,'pas_newbuild_dwellings':_counterfactual_targets(events,baseline,end)}
            events,reserved,bookings,_,released,construction,release_events=_pas_construction(shadow,events,baseline,end)
            activated={region:baseline for region in _counterfactual_regions}
        else:
            events,reserved,bookings,activated,released,construction,release_events=_pas_construction(bundle,events,baseline,end)
        plans,checkpoints,extra_dates=_pas_queue(events,baseline,end,activated,scenario,
                                                      early_headroom=_counterfactual_regions is not None)
    dates={start,end,baseline}|{date(y,1,1) for y in range(start.year,end.year+1)}
    dates|={dt(e[k]) for e in events for k in ('start_date','completion_date') if start<=dt(e[k])<=end}
    dates|=extra_dates
    dates=sorted(d for d in dates if start<=d<=end)
    energy_by_year=defaultdict(lambda:defaultdict(float))
    def finish(day):
        for j in list(jobs):
            if dt(j['event']['completion_date'])!=day:continue
            e=j['event'];c=j['cell'];inv=j['inventory'];kind=e['kind']
            if kind=='newbuild':
                cells.append(c)
                for k in QUANTITIES:expected[k]+=c[k]
            elif kind=='conversion':
                if not e.get('source_ref'):raise ValueError('Conversion requires a source/prior reference')
                fraction=c['area_m2']/e.get('_pas_basis_area_m2',e['area_m2'])
                if 'area_m2' in e.get('quantity_delta',{}) and e.get('physical_change',{}).get('conditioned_area_delta_m2'):
                    raise ValueError('Conditioned-area change counted twice')
                physical=apply_physical_change(c,e.get('physical_change'),fraction)
                if e.get('physical_change'):
                    c['physical_history'][-1]['date']=day.isoformat()
                    c['physical_history'][-1]['event_id']=e['id']
                expected['area_m2']+=physical['conditioned_area_delta_m2']
                for key,delta in e.get('quantity_delta',{}).items():
                    if key not in QUANTITIES:raise ValueError('Unknown conversion quantity')
                    c[key]+=delta*fraction;expected[key]+=delta*fraction
                c.pop('reserved_by',None)
                c.update(deepcopy(e.get('service_update',{})))
                c['history'].append({'event_id':e['id'],'date':day.isoformat(),'kind':'conversion',
                                     'physical_change':physical})
            elif kind=='airtightness':
                previous=c.get('leakage_state',{})
                c['leakage_state']=apply_completed_event(previous,{**e,'treated_parts':e['treated_parts']},day.isoformat())
                c.pop('reserved_by',None)
                c['history'].append({'event_id':e['id'],'date':day.isoformat(),
                                     'kind':'airtightness','outcome':c['leakage_state']['outcome']})
                # Leakage changes affect energy only when an explicit physical
                # airflow model consumes them. Use the unchanged original-state
                # technical heat reference, never award a depth bonus from n50.
                current=heat(c,lib,periods_for(bundle,c,baseline.year),20)['useful_heat_kwh']/c['area_m2']
                base=c.get('baseline_heat_intensity',current)
                if (not generic_snapshot or 'ra60_original_technical_baseline_kwh_m2a' in c) and base>0 and current<0.4*base and not c.get('deep_achieved'):
                    c['deep_achieved']=True;c['first_deep_date']=day.isoformat()
            elif kind=='demolition':
                cells.remove(c)
                for k in QUANTITIES:expected[k]-=c[k]
            else:
                before=j['before'];c['state']=deepcopy(j['after']['state']);c['heating']=deepcopy(j['after']['heating']);
                if j['after'].get('surface_states'):
                    c['surface_states']=deepcopy(j['after']['surface_states'])
                else:c.pop('surface_states',None)
                c.pop('reserved_by',None)
                c['history'].append({'event_id':e['id'],'date':day.isoformat(),'components':j['changed']})
                ref=periods_for(bundle,c,baseline.year)
                current=heat(c,lib,ref,20)['useful_heat_kwh']/c['area_m2']
                # RA60 is a separate cumulative milestone against a fixed
                # comparable ORIGINAL technical baseline (if source-qualified),
                # not against the transient 2024 survivor opening heat and not
                # an alternative definition of the recurring-stock RA III.
                base=c.get('ra60_original_technical_baseline_kwh_m2a',c.get('baseline_heat_intensity',before))
                if (not generic_snapshot or 'ra60_original_technical_baseline_kwh_m2a' in c) and base>0 and current<0.4*base and not c.get('deep_achieved'):
                    c['deep_achieved']=True;c['first_deep_date']=day.isoformat()
                    c['first_deep_method']=('FIXED_ORIGINAL_TECHNICAL_SERVICE_BASELINE__MODEL_MILESTONE'
                      if 'ra60_original_technical_baseline_kwh_m2a' in c else
                      'EXISTING_OPENING_SERVICE_BASELINE__LEGACY_MILESTONE')
            row={'event_id':e['id'],'kind':kind,'date':day.isoformat(),'cell_id':c['id'],
                 'area_m2':c['area_m2'],'work_area_m2':j['work_area_m2'],'buildings':c['buildings'],'dwellings':c['dwellings'],
                 'components':j.get('changed',[]),'status':'COMPLETED',
                 'inventory':{k:{n:v*j['work_area_m2'] for n,v in inv.get(k,{}).items()} for k in ('installed_kg','removed_kg','task_hours')},
                 'inventory_unknown':inv.get('unknown',[])}
            if snapshot is not None:
                row['evidence_class']='MODELLED_SCENARIO_COMPLETION_NOT_OBSERVED_OR_2024_BASELINE'
                row['capacity_scenario']=bundle.get('capacity_scenario_id','UNSPECIFIED_MODEL')
            if e.get('_pas_request_id'):
                # This mark is copied when a cohort is split. It also covers
                # conversion/airtightness requests without a component change.
                c.setdefault('pas_completed_request_ids',[]).append(e['_pas_request_id'])
                row['pas_request_id']=e['_pas_request_id']
                row['pas_extra']=e.get('_pas_extra',False)
            if kind=='conversion' and e.get('physical_change'):
                row['physical_change']=physical
            if kind=='airtightness':row['leakage_outcome']=deepcopy(c['leakage_state']['outcome'])
            if kind=='newbuild':row.update(design_id=j['design']['design_id'],standards=j['standards'],wlc=wlc(j['design'],c['area_m2']))
            ledger.append(row);jobs.remove(j)
    def extra_requests(day):
        for parent in sorted(checkpoints.get(day,()),key=lambda k:(
                dt(plans[k][0]['start_date'])>day,plans[k][0].get('priority',100),k)):
            src,_,limit,duration=plans[parent]
            remaining=limit-queue_used[parent]
            if remaining<=EPS:continue
            yield {**src,'id':f'PAS_EXTRA:{parent}:{day.isoformat()}',
                   'start_date':day.isoformat(),'completion_date':(day+duration).isoformat(),
                   'area_m2':remaining,'_pas_request_id':parent,'_pas_extra':True,
                   '_pas_basis_area_m2':src['area_m2']}

    for index,day in enumerate(dates):
        finish(day)
        # The avoided construction was provisionally held up to this instant;
        # only now can its cancelled resources enter the ordinary annual pool.
        for removal in release_events:
            if dt(removal['start_date'])!=day:continue
            region=removal['capacity_region']
            for item in removal['resources']:
                key=(region,day.year,item['kind'],item['name'])
                reserved[key]=max(0.,reserved.get(key,0.)-item['amount'])
        # Explicit priorities; no hidden preference for newbuild over renovation.
        ordinary=sorted((e for e in events if dt(e['start_date'])==day),key=lambda e:(e.get('priority',100),e['id']))
        for e in chain(ordinary,extra_requests(day)):
            if e['id'] in plans:
                original=e['area_m2']
                wanted=original-queue_used[e['id']]
                if wanted<=EPS:continue
                e={**e,'area_m2':wanted,'_pas_request_id':e['id'],'_pas_basis_area_m2':original}
            if e['id'] in bookings:
                for key,amount in bookings[e['id']].items():
                    reserved[key]=max(0.,reserved[key]-amount)
            historical_event=day<baseline;kind=e['kind'];wanted=positive(e['area_m2'],'requested area',False);remaining=wanted
            if not historical_event and e.get('readiness_required'):
                ready=deepcopy(scenario.get('readiness',{}))
                for donor in scenario.get('donor_effects',[]):
                    if donor.get('qualified') and dt(donor['operational_date'])<=day and donor.get('recipient') in (e.get('capacity_region'),e.get('place_id'),bundle['country']):
                        if not donor.get('source_ref'):raise ValueError('Donor effect requires evidence/prior reference')
                        for k,v in donor['effects'].items():ready[k]=min(donor.get('scale_max',5),ready.get(k,0)+v)
                if any(ready.get(k,0)<v for k,v in e['readiness_required'].items()):
                    if e['id'] in bookings:
                        raise ValueError('PAS retained newbuild fails scheduled readiness: '+e['id'])
                    ledger.append({'event_id':e['id'],'status':'READINESS_GAP','unmet_area_m2':wanted});continue
            if kind=='newbuild':
                c,design,standards=prepare(e,lib,bundle.get('standards',[]))
                c['climate_id']=e.get('climate_id',e['place_id'])
                candidates=[c];inv={k:design.get(k,{}) for k in ('installed_kg','removed_kg','task_hours')}
                inv['unknown']=[k for k in ('installed_kg','task_hours') if k not in design]
            else:
                candidates=[c for c in cells if not c.get('reserved_by') and match(c,e.get('selector',{}))]
                if e.get('recipient_policy'):
                    sizes=e.get('modelled_archetype_areas',{})
                    package=lib['packages'][e['package_id']] if kind=='renovation' else {}
                    candidates.sort(key=lambda c: rank(c,e['recipient_policy'],package,lib,sizes))
            for c in list(candidates):
                if remaining<1e-8:break
                changed=[];after=None
                if kind=='demolition':
                    protected=c.get('heritage',False) or c['construction_period'][0]>=2011
                    if protected and not e.get('risk_exception_source') and not historical_event:continue
                    inv=deepcopy(e.get('inventory_per_m2',{'unknown':['demolition_inventory']}))
                elif kind=='conversion':
                    if any(k not in ('service_indoor_c','occupied','use') for k in e.get('service_update',{})):raise ValueError('Invalid service update')
                    inv=deepcopy(e.get('inventory_per_m2',{'unknown':['conversion_inventory']}))
                elif kind=='airtightness':
                    # A pressure-test outcome is a state update, not a second heat loss.
                    # Its measured bounds must not be converted to operating ACH here.
                    if not e.get('source_ref') or not e.get('treated_parts') or not e.get('junction_scope'):
                        raise ValueError('Airtightness event source and scope required')
                    if e.get('outcome',{}).get('role') not in ('measured','assumed_achieved'):
                        raise ValueError('An airtightness design target is not achieved leakage')
                    inv=deepcopy(e.get('inventory_per_m2',{'unknown':['airtightness_work_inventory']}))
                elif kind=='renovation':
                    after,changed,inv=package_effect(c,lib['packages'][e['package_id']],lib)
                    if not changed:continue
                area=min(remaining,c['area_m2']);region=e.get('capacity_region',c['place_id'])
                parent=e.get('_pas_request_id')
                if parent and parent in c.get('pas_completed_request_ids',()):continue
                extra=e.get('_pas_extra',False)
                if extra and day<activated.get(region,date.max):continue
                fraction,unknown=capacity_fraction(inv,area,day.year,region,bundle,used,reserved)
                if extra:
                    has_work=any(rate>0 for kind in CAPACITY_KINDS for rate in inv.get(kind,{}).values())
                    delivery_unknown=[x for x in unknown if not x.endswith(':removed_kg_m2') and x!='removed_kg']
                    if delivery_unknown or not has_work:
                        warnings.extend(unknown or [f'PAS_EXTRA_NO_RESOURCE_INVENTORY:{parent}'])
                        continue
                # Actual history is not rewritten to fit a forecast resource prior.
                if historical_event:fraction=1
                delivered=area*fraction
                if unknown:warnings.extend(unknown)
                if delivered<1e-8:continue
                sequence+=1
                if kind=='newbuild':
                    piece=deepcopy(c)
                    for k in QUANTITIES:piece[k]*=delivered/c['area_m2']
                    piece['baseline_heat_intensity']=heat(piece,lib,periods_for(bundle,piece,baseline.year),20)['useful_heat_kwh']/delivered
                else:
                    piece=take(cells,c,delivered,e['id']+':'+str(sequence));piece['reserved_by']=e['id'];cells.append(piece)
                if not historical_event:
                    for typ in ('task_hours','installed_kg'):
                        for n,v in inv.get(typ,{}).items():used[(region,day.year,typ,n)]+=v*delivered
                j={'event':e,'cell':piece,'inventory':inv,'work_area_m2':delivered}
                if kind=='renovation':j.update(after=after,changed=changed,before=piece['baseline_heat_intensity'])
                if kind=='newbuild':j.update(design=design,standards=standards)
                jobs.append(j);remaining-=delivered
            if e['id'] in bookings and remaining>EPS:
                raise ValueError('PAS retained newbuild could not be fully scheduled: '+e['id'])
            row={'event_id':e['id'],'kind':kind,'date':day.isoformat(),'status':'START_ACCOUNT',
                 'requested_area_m2':wanted,'committed_area_m2':wanted-remaining,'unmet_area_m2':remaining}
            if e.get('_pas_request_id'):
                parent=e['_pas_request_id'];queue_used[parent]+=wanted-remaining
                row.update(pas_request_id=parent,pas_extra=e.get('_pas_extra',False))
            ledger.append(row)
            finish(day)
        validate(cells,lib);check_conservation(cells,expected)
        snapshots[day.isoformat()]=deepcopy(cells)
        if index+1==len(dates):break
        nxt=dates[index+1];year=day.year
        # Interpolate annual weather exposure uniformly within year; exported explicitly.
        fraction=(nxt-day).days/(date(year+1,1,1)-date(year,1,1)).days
        for c in cells:
            h=heat(c,lib,periods_for(bundle,c,year))
            group=('research_dated_conditional_cohort' if generic_snapshot and c['origin']=='RESEARCH_DATED_MODEL_SNAPSHOT' else
                   'research_2024_conditional_fixed_cohort' if snapshot is not None and c['origin']=='RESEARCH_2024_MODEL_SNAPSHOT' else
                   'new_since_2011' if c['origin']=='NEW_CONSTRUCTION' else 'pre_2011')
            for key in ('useful_heat_kwh','final_heat_kwh','ambient_heat_kwh','fan_electricity_kwh'):
                energy_by_year[year][group+'_'+key]+=h[key]*fraction
            energy_by_year[year]['carrier_'+h['carrier']+'_kwh']+=h['final_heat_kwh']*fraction
            if h['fan_electricity_kwh']:
                energy_by_year[year]['ventilation_fan_electricity_kwh']+=h['fan_electricity_kwh']*fraction
    for year,values in sorted(energy_by_year.items()):annual.append({'year':year,**dict(values)})
    if scenario.get('actor_events') and scenario['pathway']!='PAS':
        raise ValueError('PAS actor formation events cannot be assigned to non-PAS pathway')
    actor_ledger=evaluate_actor_formation(scenario.get('actor_events',[]),ledger,bundle.get('verified_nonres_completions',[]))
    result={'schema':'cohort-result/2','scenario':scenario['id'],'pathway':scenario['pathway'],
       'timing':scenario.get('timing','central'),'initial_totals':initial,'final_totals':totals(cells),
       'cells':cells,'snapshots':snapshots,'annual':annual,'ledger':ledger,'actor_formation_ledger':actor_ledger,
       'resource_use':[{'region':k[0],'year':k[1],'kind':k[2],'resource':k[3],'amount':v} for k,v in used.items()],
       'in_progress':[{'event_id':j['event']['id'],'completion_date':j['event']['completion_date'],'area_m2':j['cell']['area_m2']} for j in jobs],
       'unknowns':sorted(set(warnings)),'runtime_promoted':False,
       'energy_timing_method':'Annual weather exposure prorated by event-date duration; use separate city solver for period-specific tests',
       'research_opening_snapshot':deepcopy(snapshot) if snapshot is not None else None,
       'completion_evidence':'MODELLED_CONDITIONAL_NOT_OBSERVED' if snapshot is not None else 'STANDARD_EVENT_CONTRACT'}
    if pas_active:
        def resource_rows(values):
            return [{'region':k[0],'year':k[1],'kind':k[2],'resource':k[3],'amount':v}
                    for k,v in sorted(values.items())]
        unused={}
        for region,first in activated.items():
            for year,cap in bundle.get('capacity',{}).get(region,{}).items():
                if not first.year<=int(year) or date(int(year),1,1)>=end:continue
                for kind in CAPACITY_KINDS:
                    for name,value in cap.get(kind,{}).items():
                        if value is None:continue
                        key=(region,int(year),kind,name)
                        unused[key]=max(0.,value-used.get(key,0.))
        result['pas_newbuild_reallocation']={
            'newbuild_trajectory':construction,'avoided_newbuild_requirements':resource_rows(released),
             'avoided_construction_starts':release_events,
            'unused_capacity':resource_rows(unused),
            'queue':[{'request_id':k,'eligible_area_m2':v[2],'committed_area_m2':queue_used[k],
                      'remaining_area_m2':max(0.,v[2]-queue_used[k])} for k,v in sorted(plans.items())]}
        if _counterfactual_regions is None:
            if activated:
                try:
                    # Like-for-like baseline: identical PAS needs / institutional
                    # readiness, with the full ordinary newbuild uncut.
                    counter=run(bundle,scenario,_counterfactual_regions=frozenset(activated))
                    result['pas_newbuild_reallocation']['pi_headroom_comparison']=_pas_attribution(result,counter)
                except ValueError as exc:
                    # Infeasible uncut PI is not a valid source of net causation.
                    result['pas_newbuild_reallocation']['pi_headroom_comparison']={
                        'status':'UNQUALIFIED_PI_COUNTERFACTUAL','reason':str(exc),
                        'requests':[],'total_net_incremental_area_m2':None}
            else:
                result['pas_newbuild_reallocation']['pi_headroom_comparison']={
                    'status':'NO_AVOIDED_NEWBUILD','requests':[],
                    'total_net_incremental_area_m2':0.}
    return result
