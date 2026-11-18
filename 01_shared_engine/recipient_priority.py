"""Country-neutral recipient ordering for cohort-state renovation research.

Policy fields are supplied by the country/programme owner. This module ranks a
fully specified eligible candidate set; it does not invent social evidence,
finance constraints, actor presence, delivery, or any country coefficient.
"""
from surface_state import surface_inventory
from archetype_physics import floor_target_is_eligible

POLICIES = {'PI_SOURCE_NEUTRAL','PAS_DEEP','PAS_RETENTION','PAS_ADAPTIVE',
            'HDE_ELECTRIFICATION','HDE_INDUSTRIAL','HDE_REDEVELOP'}

def _form(cell,lib):
    explicit = cell.get('dwelling_form') or cell.get('form') or lib['archetypes'][cell['archetype_id']].get('dwelling_form')
    if explicit:
        return explicit
    parts=cell['archetype_id'].split('_')
    return parts[1] if len(parts)>1 and parts[1] in ('SFH','TH','MFH','AB') else 'UNKNOWN'

def _gain(c,lib,package):
    """Marginal exposed-UA reduction, using exactly the candidate work surfaces.

    Partial existing renovations and zero-loss party walls cannot be credited
    again. This is an ordering proxy, not a realised energy-saving prediction.
    """
    a=lib['archetypes'][c['archetype_id']]
    specific=package.get('surface_targets',{})
    targets=package.get('targets',{})
    rows=surface_inventory(c,lib)
    if any(k not in {r['id'] for r in rows} for k in specific):
        raise ValueError('Unknown targeted surface ID')
    result=0.
    for r in rows:
        comp=r['component']
        target=specific.get(r['id'],targets.get(comp))
        if target is None:continue
        if comp=='floor' and not floor_target_is_eligible(c,package):continue
        if r['adjacent']=='heated_neighbour' and r['id'] not in specific and not package.get('include_zero_heat_surfaces',False):
            continue
        if target not in a['components'][comp]:raise ValueError('Unknown target variant')
        old=r['u_w_m2k'];new=a['components'][comp][target]['u_w_m2k']
        result+=max(0,old-new)*r['area_m2']*r['boundary_factor']/c['area_m2']
    return result

def rank(cell,policy,package,lib,archetype_areas):
    if policy not in POLICIES: raise ValueError('Unknown recipient policy: '+str(policy))
    tie=(str(cell.get('root_id',cell['id'])),str(cell['id']))
    if policy=='PI_SOURCE_NEUTRAL':return tie
    gain=_gain(cell,lib,package)
    form=_form(cell,lib)
    vintage=cell['construction_period'][1]
    carrier=cell['heating']['carrier']
    # Unknown carriers are not evidence of fossil use. Future HDE heating
    # conversion must be a separately evidenced device event.
    fossil=int(carrier in ('GAS','OIL','COAL','DIESEL','LPG','FOSSIL_GAS'))
    conv=int(fossil and package.get('heating') is not None)
    tier=cell.get('allocation_tier',4)
    if policy.startswith('PAS_'):
        if tier not in (1,2,3,4):raise ValueError('Unknown PAS tier')
        if tier<4 and not cell.get('allocation_evidence'):
            raise ValueError('PAS priority tier requires evidence provenance')
    if policy=='PAS_DEEP': key=(tier,-round(gain,8),-fossil,vintage)
    elif policy=='PAS_RETENTION':key=(tier,-int(form in ('MFH','AB')),-round(gain,8),vintage)
    elif policy=='PAS_ADAPTIVE':key=(tier,-int(form in ('MFH','AB')),-fossil,-round(gain,8),vintage)
    elif policy=='HDE_ELECTRIFICATION':key=(-conv,-fossil,-round(gain,8),vintage)
    elif policy=='HDE_INDUSTRIAL':key=(-round(archetype_areas.get(cell['archetype_id'],0)/1e6,5),-round(gain,8),vintage)
    else:key=(-round(gain,8),-fossil,-int(form in ('MFH','AB')),vintage)
    return (*key,*tie)
