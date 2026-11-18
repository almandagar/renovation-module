"""Research-only airtightness state and adapter; no national defaults or auto-promotion.

qE50: m3/(h m2 envelope); n50: h-1 at 50 Pa; flow: m3/h.
The area prognosis is draft-inspired engineering sensitivity, not WTA certification.
"""
from copy import deepcopy
from datetime import date
from math import isfinite


def number(x, name, positive=False):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not isfinite(x) or x < 0 or (positive and x == 0):
        raise ValueError('Invalid ' + name)
    return x


def leakage(value, metric, envelope_m2, volume_m3):
    number(value, 'leakage'); number(envelope_m2, 'envelope', True); number(volume_m3, 'volume', True)
    if metric not in ('qE50', 'n50'):
        raise ValueError('Explicit pressure-test metric required')
    flow = value * (envelope_m2 if metric == 'qE50' else volume_m3)
    return dict(q50_m3_h=flow, qE50=flow/envelope_m2, n50=flow/volume_m3)


def area_prognosis(parts, total_envelope_m2, source_ref):
    """Disjoint retained/treated sections; not a measured or expected achieved state."""
    number(total_envelope_m2, 'envelope', True)
    if not source_ref or not parts or len({p['id'] for p in parts}) != len(parts):
        raise ValueError('Unique parts and assumption/source reference required')
    area = flow = 0
    for p in parts:
        a = number(p['area_m2'], 'section area', True)
        q = number(p['qE50'], 'section leakage')
        if p['status'] not in ('retained', 'treated'):
            raise ValueError('Section status')
        area += a; flow += a*q
    if abs(area-total_envelope_m2) > 1e-8*total_envelope_m2:
        raise ValueError('Incomplete or overlapping area partition')
    return dict(qE50=flow/area, role='engineering_target', source_ref=source_ref,
                final_WTA_equivalence_verified=False)


def apply_completed_event(state, event, as_of):
    """Attach achieved bounds or measurement once; never apply a design target as fact."""
    result = deepcopy(state)
    done = date.fromisoformat(event['completion_date'])
    if done > date.fromisoformat(as_of):
        return result
    if event['id'] in result.get('applied_event_ids', []):
        raise ValueError('Duplicate airtightness event')
    if result.get('as_of') and done < date.fromisoformat(result['as_of']):
        raise ValueError('Out-of-order state transition')
    if not event.get('treated_parts') or not event.get('junction_scope') or not event.get('quality_basis'):
        raise ValueError('Scope, junctions and achieved quality basis required')
    outcome = event['outcome']
    if outcome.get('role') not in ('measured', 'assumed_achieved') or not outcome.get('source_ref'):
        raise ValueError('A design target is not achieved evidence')
    lo, hi = outcome['bounds']
    number(lo, 'lower'); number(hi, 'upper')
    if lo > hi or outcome.get('metric') not in ('qE50', 'n50'):
        raise ValueError('Invalid achieved bounds/metric')
    if outcome['role'] == 'measured' and not outcome.get('test_boundary_ref'):
        raise ValueError('Measurement boundary/preparation required')
    result.update(outcome=deepcopy(outcome), as_of=event['completion_date'])
    result['applied_event_ids'] = result.get('applied_event_ids', []) + [event['id']]
    result.setdefault('events', []).append(deepcopy(event))
    return result


def balanced_airflow(row, floor_m2):
    """Consume externally resolved outdoor flow, never convert n50 by a universal divisor.

    Supports balanced supply/extract with heat recovery only. Natural/exhaust-only
    systems need a qualified interaction model upstream; not silently added here.
    """
    number(floor_m2, 'conditioned floor', True)
    if row.get('system') != 'balanced' or not row.get('interaction_resolved') or not row.get('source_ref'):
        raise ValueError('Qualified, non-overlapping balanced outdoor flows required')
    if row.get('recovery_basis') != 'intentional_stream_only':
        raise ValueError('Whole-concept savings include imbalance: not a stream recovery efficiency')
    if row.get('operating_mode') != 'balanced_recovery':
        raise ValueError('Bypass/frost/supply-off modes need separately resolved airflow')
    inf = number(row['infiltration_m3_h'], 'infiltration')
    window = number(row['window_airing_m3_h'], 'window airing')
    fresh = number(row['intentional_m3_h'], 'intentional fresh air')
    eta = number(row['effective_recovery'], 'effective recovery')
    if eta > 1:
        raise ValueError('Recovery above one')
    cp = number(row['air_heat_capacity_wh_m3k'], 'air heat capacity', True)
    fan = number(row['fan_w'], 'fan power')
    minimum = number(row['required_outdoor_m3_h'], 'outdoor service requirement')
    return dict(hve_w_k_m2=cp*(inf+window+fresh*(1-eta))/floor_m2,
                fan_w=fan, outdoor_m3_h=inf+window+fresh,
                service_screen_pass=inf+window+fresh >= minimum,
                service_screen_note='Bulk-flow screen only; no room-level IAQ certification')


def baseline_check(old_hve, proposed_infiltration_h, proposed_total_h):
    for x in (old_hve, proposed_infiltration_h, proposed_total_h):
        number(x, 'coefficient')
    if proposed_infiltration_h > proposed_total_h:
        raise ValueError('Infiltration cannot exceed candidate total loss')
    return dict(old_hve=old_hve, candidate_hve=proposed_total_h,
                old_minus_candidate=old_hve-proposed_total_h,
                old_compatible_with_infiltration=old_hve >= proposed_infiltration_h,
                fitted_residual=None)


def shadow_heat(cell, library, periods, airflow_by_period):
    """Run existing archetype_physics.heat with explicitly supplied period Hve.

    Inputs remain unchanged. Leakage target alone cannot call this adapter.
    Same thermal method/gains/service are used for the comparison.
    """
    from archetype_physics import heat
    ids = [p['id'] for p in periods]
    if len(set(ids)) != len(ids) or set(ids) != set(airflow_by_period):
        raise ValueError('Exactly one airflow record per unique weather period')
    baseline = heat(cell, library, periods)
    candidate = 0.; fans = 0.; adequate = True
    for p in periods:
        air = balanced_airflow(airflow_by_period[p['id']], cell['area_m2'])
        lib = deepcopy(library)
        lib['archetypes'][cell['archetype_id']]['ventilation_w_k_m2'] = air['hve_w_k_m2']
        candidate += heat(cell, lib, [p])['useful_heat_kwh']
        fans += air['fan_w']*p['hours']/1000
        adequate &= air['service_screen_pass']
    return dict(status='RESEARCH_ONLY', baseline_useful_heat_kwh=baseline['useful_heat_kwh'],
                candidate_useful_heat_kwh=candidate, fan_electricity_kwh=fans,
                bulk_fresh_air_screen_pass=adequate, production_promoted=False)
