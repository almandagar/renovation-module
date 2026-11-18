"""Optional, provenance-bearing surface and physical-transformation contract.

Legacy building-stock/2 ratio inputs remain supported. Explicit inventories are
complete thermal-boundary inventories; their entries are never added to ratios.
An adjacency factor is an externally supplied bounded approximation for ground
and unheated zones, NOT a coupled/interzone heat solver.
"""
from copy import deepcopy
from math import isfinite

ADJACENCIES = {'exterior', 'ground', 'unheated_enclosure', 'heated_neighbour'}
AREA_BASES = {'surface_net', 'surface_gross', 'ceiling_under_attic', 'roof_slope',
              'floor_to_ground', 'floor_to_unheated', 'party_wall'}

def num(v, label, allow_zero=False):
    if isinstance(v, bool) or not isinstance(v,(int,float)) or not isfinite(v) or v < 0 or (not allow_zero and v == 0):
        raise ValueError('Invalid '+label)
    return v

def floor_area_alternatives(source_areas, assumptions):
    """Preserve the supplied measure, make explicitly assumed conditioned bounds.

    An area reported as built-up is not an observation of internal/conditioned
    space. Unheated attic or annex can be represented with conditioned_fraction=0.
    """
    out=[]
    if len({s.get('id') for s in source_areas}) != len(source_areas):
        raise ValueError('Duplicate source-area level ID')
    for s in source_areas:
        if s.get('kind') not in ('built_up','internal','usable','conditioned') or not s.get('source_ref'):
            raise ValueError('Area kind and source required')
        num(s['area_m2'], 'source area')
        a=assumptions.get(s['id'])
        if a is None:
            out.append({'id':s['id'],'reported':deepcopy(s),'conditioned_m2':None,
                        'status':'UNKNOWN_NO_CONVERSION'});continue
        if not a.get('source_ref') or len(a.get('conditioned_fraction_bounds',[]))!=2:
            raise ValueError('Explicit sourced/prior conditioned-area bounds required')
        lo,hi=a['conditioned_fraction_bounds']
        num(lo,'conditioned fraction',True);num(hi,'conditioned fraction',True)
        if lo>hi or hi>1: raise ValueError('Conditioned fraction bounds')
        out.append({'id':s['id'],'reported':deepcopy(s),
                    'conditioned_m2':[s['area_m2']*lo,s['area_m2']*hi],
                    'status':'BOUNDED_ASSUMPTION_NOT_OBSERVED', 'assumption_ref':a['source_ref']})
    return out

def surface_inventory(cell, library):
    """Absolute area inventory; one row per distinct component and boundary.

    In legacy mode, construct a visible ratio-derived inventory instead of
    silently claiming observed geometry. The explicit mode is authoritative.
    """
    a=library['archetypes'][cell['archetype_id']]
    area=num(cell['area_m2'],'conditioned area')
    if cell.get('area_basis','conditioned')!='conditioned':
        raise ValueError('Stock area_m2 must be conditioned, not built-up/internal/usable')
    explicit=cell.get('surface_inventory') is not None
    rows=deepcopy(cell['surface_inventory']) if explicit else [
        {'id':'legacy:'+key,'component':key,'area_m2':num(ratio,'legacy ratio',True)*area,
         'adjacent':'exterior','area_basis':'surface_net','source_ref':a.get('source_ref'),
         'assumption_status':'LEGACY_RATIO_WITH_EMBEDDED_EXPOSURE'}
        for key,ratio in {**a['geometry'], **cell.get('geometry_override',{})}.items()
        if key in a['components']]
    if explicit and cell.get('geometry_override'):
        raise ValueError('Explicit inventory and geometry_override cannot both own surfaces')
    if explicit and cell.get('surface_inventory_scope')!='complete_thermal_boundary':
        raise ValueError('Complete thermal-boundary declaration required')
    if len({r.get('id') for r in rows})!=len(rows):raise ValueError('Duplicate surface ID')
    if not rows:raise ValueError('Empty thermal surface inventory')
    result=[]
    for r in rows:
        component=r.get('component')
        if component not in a['components']:raise ValueError('Unknown surface component')
        if not r.get('source_ref'):raise ValueError('Surface requires provenance')
        adj=r.get('adjacent')
        if adj not in ADJACENCIES:raise ValueError('Explicit adjacent environment required')
        if r.get('area_basis') not in AREA_BASES:raise ValueError('Explicit surface area basis required')
        if 'orientation_deg' in r and not 0<=num(r['orientation_deg'],'orientation',True)<360:
            raise ValueError('Invalid orientation')
        ar=num(r['area_m2'],'surface area',True)
        state=cell.get('surface_states',{}).get(r['id'],cell['state'][component])
        if state not in a['components'][component]:raise ValueError('Unknown surface component state')
        profile=a['components'][component][state]
        if not profile.get('source_ref'):raise ValueError('Component condition/assembly provenance missing')
        u=num(profile['u_w_m2k'],'U value',True)
        if explicit:
            factor=r.get('boundary_factor')
            if adj=='heated_neighbour':
                if factor not in (None,0):raise ValueError('Heated neighbour represented as transmission outdoors')
                factor=0
            elif adj=='exterior':
                if factor not in (None,1):raise ValueError('Exterior factor must be one')
                factor=1
            else:
                if factor is None:raise ValueError('Ground/unheated boundary needs evidenced factor')
                num(factor,'boundary factor',True)
                if factor>1:raise ValueError('Boundary factor exceeds one')
        else:
            factor=num(profile.get('exposure_factor',1),'legacy exposure',True)
        result.append({**r,'state':state,'u_w_m2k':u,'boundary_factor':factor,
                       'ua_w_k':u*ar*factor,'assembly_source_ref':profile['source_ref'],
                       'area_denominator':'conditioned_floor_m2',
                       'area_m2_per_conditioned_m2':ar/area})
    return result

def split_surface_inventory(cell, share):
    if cell.get('surface_inventory') is not None:
        for r in cell['surface_inventory']:r['area_m2']*=share

def apply_physical_change(cell, change, scale=1):
    """Apply a dated bounded transformation to its reserved, disjoint stock cell.

    Scaled physical areas are defined for the original affected work scope;
    addition of conditioned area is stock growth, not a renovation saving.
    """
    if not change:return {'conditioned_area_delta_m2':0,'surface_changes':[]}
    if not change.get('source_ref'):raise ValueError('Physical transformation provenance required')
    if cell.get('surface_inventory') is None and change.get('surface_changes'):
        raise ValueError('Surface changes require explicit existing inventory')
    changes=deepcopy(change.get('surface_changes',[])); seen=set()
    rows=cell.get('surface_inventory',[])
    for ch in changes:
        if ch['id'] in seen:raise ValueError('Duplicate physical surface change')
        seen.add(ch['id']); op=ch['operation']; sid=ch['id']
        old=next((r for r in rows if r['id']==sid),None)
        if op=='remove':
            if old is None:raise ValueError('Missing surface for removal')
            rows.remove(old)
            cell.get('surface_states',{}).pop(sid,None)
        elif op in ('add','replace'):
            if (old is None) != (op=='add'):raise ValueError('Surface add/replace identity conflict')
            fresh=deepcopy(ch['surface']);fresh['id']=sid
            fresh['area_m2']=num(fresh['area_m2'],'new surface area',True)*scale
            if old is not None:
                rows.remove(old)
                cell.get('surface_states',{}).pop(sid,None)
            rows.append(fresh)
        else:raise ValueError('Unknown surface operation')
    delta=change.get('conditioned_area_delta_m2',0)*scale
    if not isinstance(delta,(int,float)) or isinstance(delta,bool) or not isfinite(delta):
        raise ValueError('Invalid conditioned-area delta')
    if cell['area_m2']+delta <= 0:raise ValueError('Transformation eliminates conditioned cohort')
    cell['area_m2']+=delta
    cell.setdefault('physical_history',[]).append({'source_ref':change['source_ref'],
       'conditioned_area_delta_m2':delta,'surface_changes':[c['id'] for c in changes]})
    if change.get('surface_states'):
        for sid,state in change['surface_states'].items():cell.setdefault('surface_states',{})[sid]=state
    return {'conditioned_area_delta_m2':delta,'surface_changes':[c['id'] for c in changes]}

def check_historical_state_evidence(cell, opening_date):
    """Do not backdate known present-day condition to earlier reconstructed stock."""
    for row in cell.get('surface_inventory',[]):
        observed=row.get('observed_as_of')
        if observed and observed > opening_date:
            raise ValueError('Present-day surface observation cannot establish historical opening state')
    for row in cell.get('condition_observations',[]):
        if row.get('observed_as_of','') > opening_date:
            raise ValueError('Present-day condition observation cannot establish historical opening state')

def evidence_independence(candidate, holdout):
    """Conservative ID/lineage overlap screen; nonoverlap alone is not proof."""
    def lineage(x):return set(x.get('source_ids',[])) | set(x.get('derived_from_ids',[]))
    if not candidate.get('source_ids') or not holdout.get('source_ids'):
        return {'status':'INDEPENDENCE_UNVERIFIED','reason':'Source identifiers missing'}
    overlap=sorted(lineage(candidate)&lineage(holdout))
    if overlap:return {'status':'CIRCULAR_EVIDENCE','overlap':overlap}
    return {'status':'NO_DECLARED_LINEAGE_OVERLAP_INDEPENDENCE_STILL_REQUIRES_REVIEW',
            'overlap':[]}
