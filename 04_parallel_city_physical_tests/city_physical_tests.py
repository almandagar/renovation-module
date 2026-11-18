"""City physical tests v2: independent bounded thermal/service falsification.

Pure, standard-library-only research solver. No national model imports or writes.
Results are conditional, quasi-steady tests, not empirical certification or dynamic heat simulation.
"""
import argparse
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path

SCHEMA = 'city-physical-tests/2'
TEMP_MIN, TEMP_MAX = 5.0, 35.0


def number(v, label, low=None, high=None):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ValueError(f'{label}: finite numeric value required')
    if low is not None and v < low or high is not None and v > high:
        raise ValueError(f'{label}: outside [{low}, {high}]')
    return float(v)


def required(d, k, kind=str):
    value = d.get(k)
    if not isinstance(value, kind) or (isinstance(value, str) and not value.strip()):
        raise ValueError(f'Missing or invalid {k}')
    return value


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('Timestamp must be ISO 8601 with time zone')
    try:
        out = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError('Invalid period timestamp') from exc
    if out.tzinfo is None or out.utcoffset() is None:
        raise ValueError('Timezone required')
    return out


def periods_of(case):
    periods = required(case, 'periods', list)
    if not periods:
        raise ValueError('At least one weather period required')
    out = []
    for p in periods:
        start, end = timestamp(p['start']), timestamp(p['end'])
        hours = (end-start).total_seconds()/3600
        if not 0 < hours <= 8784:
            raise ValueError('Nonpositive/oversized weather period')
        out.append(dict(id=required(p, 'id'), start=start, end=end, hours=hours,
                        outdoor_c=number(p['outdoor_c'], 'outdoor', -90, 60)))
    if len({p['id'] for p in out}) != len(out):
        raise ValueError('Duplicate weather period IDs')
    for p, q in zip(out, out[1:]):
        if p['end'] != q['start']:
            raise ValueError('Noncontiguous or overlapping time coverage')
    if case.get('period_hours') is not None:
        target = number(case['period_hours'], 'period_hours', 0)
        if abs(target-sum(p['hours'] for p in out)) > 1e-6:
            raise ValueError('Period duration mismatch')
    return out


def boundary_match(a, b):
    keys = ('country', 'city', 'population', 'period_start', 'period_end', 'service', 'unit', 'area_basis')
    if not all(a.get(k) == b.get(k) for k in keys):
        raise ValueError('Observation/prediction population, period, area, service or energy-stage mismatch')
    for k in keys:
        required(a, k)
    if a['service'] != 'SPACE_HEAT' or a['unit'] != 'kWh_USEFUL_DELIVERED':
        raise ValueError('Canonical physical stage must be kWh_USEFUL_DELIVERED for SPACE_HEAT')


def observation_bounds(case, boundary):
    obs = case.get('observation')
    if obs is None or obs.get('mode') == 'NONE':
        return None, 'NO_ENERGY_OBSERVATION', []
    boundary_match(boundary, obs['boundary'])
    mode = required(obs, 'mode')
    sources = []
    if mode == 'USEFUL':
        for k in ('source_ref', 'source_family_id', 'instrument'):
            required(obs, k)
        low, high = number(obs['low_kwh'], 'useful low', 0), number(obs['high_kwh'], 'useful high', 0)
        sources.append({'source_ref':obs['source_ref'], 'source_family_id':obs['source_family_id'],
                        'instrument':obs['instrument']})
    elif mode == 'CARRIER':
        carrier_obs = required(obs, 'carriers', list)
        if not carrier_obs:
            raise ValueError('Empty carrier evidence')
        seen = set()
        low = high = 0.0
        for c in carrier_obs:
            key = required(c, 'carrier')
            if key in seen:
                raise ValueError('Duplicate carrier accounting; consolidate before conversion')
            seen.add(key)
            for k in ('source_ref', 'source_family_id', 'instrument', 'conversion_basis'):
                required(c, k)
            xlo = number(c['final_low_kwh'], 'carrier final low', 0)
            xhi = number(c['final_high_kwh'], 'carrier final high', 0)
            flo = number(c['space_heat_fraction_low'], 'space-heat fraction low', 0, 1)
            fhi = number(c['space_heat_fraction_high'], 'space-heat fraction high', 0, 1)
            elo = number(c['useful_per_final_low'], 'conversion low', 0, 12)
            ehi = number(c['useful_per_final_high'], 'conversion high', 0, 12)
            if xlo > xhi or flo > fhi or elo > ehi:
                raise ValueError('Reversed carrier/conversion intervals')
            # SPF >1 allowed for a heat pump: ambient energy is already included in useful output.
            if key == 'HP_ELECTRICITY' and ehi <= 1:
                raise ValueError('HP electricity must use explicitly specified SPF >1 or be reclassified')
            low += xlo*flo*elo
            high += xhi*fhi*ehi
            sources.append({'source_ref':c['source_ref'], 'source_family_id':c['source_family_id'],
                            'instrument':c['instrument']})
    else:
        raise ValueError('Unknown energy observation mode')
    if low > high:
        raise ValueError('Reversed energy bounds')
    return (low, high), mode, sources


def zones_of(h):
    if 'zones' in h:
        zones = required(h, 'zones', list)
        if not zones:
            raise ValueError('Explicit zone set cannot be empty')
        if any(k in h for k in ('external_surfaces', 'indoor_c_by_period', 'heated_fraction')):
            raise ValueError('Do not mix zone and global thermal parameters')
    else:
        zones = [h]
    if len({z.get('id') for z in zones}) != len(zones):
        raise ValueError('Duplicate zone IDs')
    return zones


def evaluate(h, periods, override_indoor=None):
    total, surfaces, qareas = 0.0, 0.0, 0.0
    period_heating_power = {p["id"]:0.0 for p in periods}
    details = []
    zones = zones_of(h)
    for z in zones:
        area = number(z['conditioned_area_m2'], 'conditioned zone area', 0.1, 100000)
        qareas += area
        ext = required(z, 'external_surfaces', list)
        h_external = 0.0
        for s in ext:
            surf_area = number(s['area_m2'], 'surface m2', 0, 100000)
            U = number(s['u_w_m2k'], 'surface U', 0, 10)
            surfaces += surf_area
            h_external += surf_area*U
        h_vent = number(z['ventilation_w_k'], 'ventilation W/K', 0, 50*area)
        h_bridge = number(z.get('thermal_bridges_w_k', 0), 'bridge W/K', 0, 30*area)
        htot = h_external+h_vent+h_bridge
        if htot == 0:
            raise ValueError('Zero thermal coupling; physically unidentified')
        qzone, qmax = 0.0, 0.0
        temps = required(z, 'indoor_c_by_period', dict)
        gains = required(z, 'usable_gains_w_by_period', dict)
        adjacent = z.get('adjacent_spaces', [])
        for p in periods:
            pid = p['id']
            ti = number(override_indoor if override_indoor is not None else temps[pid],
                        'indoor temperature', TEMP_MIN, TEMP_MAX)
            g = number(gains[pid], 'usable gains', 0, 200*area)
            loss = htot*(ti-p['outdoor_c'])
            for a in adjacent:
                # Adjacent temperatures must be explicitly outside the modelled heated zones.
                adjid = required(a, 'adjacent_id')
                if adjid in {zz.get('id') for zz in zones}:
                    raise ValueError('Internal represented-zone adjacency requires coupled thermal solver')
                loss += number(a['h_w_k'], 'adjacent exchange W/K', 0, 50*area) * (
                    ti-number(a['temperature_c_by_period'][pid], 'adjacent temperature', -30, 45))
            power = max(0, loss-g)
            qzone += power*p['hours']/1000
            period_heating_power[pid] += power
            qmax = max(qmax, power/1000)
        total += qzone
        details.append({'zone_id':z.get('id', 'SINGLE_ZONE'), 'area_m2':area,
                        'required_useful_kwh':round(qzone, 6), 'exterior_h_w_k':round(htot, 4)})
    return {'required_useful_kwh':round(total, 6), 'conditional_period_peak_kw':round(max(period_heating_power.values())/1000, 6),
            'conditioned_area_m2':round(qareas, 4), 'zones':details}


def invert_constant_setpoint(h, periods, energy):
    # A constant temperature equivalence, not an observed temperature or a dynamic prediction.
    if energy is None:
        return None
    def f(temp):
        return evaluate(h, periods, temp)['required_useful_kwh']
    fmin, fmax = f(TEMP_MIN), f(TEMP_MAX)
    def solve(q):
        if q < fmin-1e-6:
            return None, 'BELOW_TEST_DOMAIN'
        if q > fmax+1e-6:
            return None, 'ABOVE_TEST_DOMAIN'
        l, r = TEMP_MIN, TEMP_MAX
        for _ in range(60):
            m=(l+r)/2
            if f(m) < q:
                l=m
            else:
                r=m
        return round((l+r)/2, 4), 'WITHIN_TEST_DOMAIN'
    tl, sl = solve(energy[0])
    th, sh = solve(energy[1])
    return {'method':'CONSTANT_SETPOINT_QUASI_STEADY_EQUIVALENCE', 'temperature_c_low':tl,
            'temperature_c_high':th, 'low_status':sl, 'high_status':sh,
            'test_domain_c':[TEMP_MIN,TEMP_MAX], 'not_actual_indoor_temperature':True}


def distance(x, low, high):
    return round(low-x if x < low else x-high if x > high else 0, 6)


def independence(snapshot, case, sources):
    if not sources:
        return 'NO_ENERGY_OBSERVATION'
    a=set(snapshot.get('calibration_source_families', []))
    b={s['source_family_id'] for s in sources}
    if a.intersection(b):
        return 'SHARED_LINEAGE'
    if case.get('shared_lineage_possible'):
        return 'POSSIBLE_PARTIAL_OVERLAP'
    if not case.get('independence_reviewed'):
        return 'UNASSESSED'
    locked = case.get('hypotheses_locked_at')
    disclosed = case.get('observation_disclosed_at')
    if not locked or not disclosed:
        return 'DECLARED_INDEPENDENCE_NO_PREREGISTRATION'
    return ('PREDECLARED_SOURCE_INDEPENDENCE_AUDIT_REQUIRED' if timestamp(locked)<timestamp(disclosed)
            else 'POST_OBSERVATION_HYPOTHESES_NOT_HELD_OUT')


def run(data):
    if data.get('schema') != SCHEMA:
        raise ValueError(f'Expected schema {SCHEMA}')
    snapshot = required(data, 'model_snapshot', dict)
    required(snapshot, 'version')
    required(snapshot, 'source_ref')
    predictions = required(snapshot, 'predictions', dict)
    sha = hashlib.sha256(json.dumps(snapshot, sort_keys=True, allow_nan=False).encode()).hexdigest()
    cases = required(data, 'cases', list)
    if not cases or len({c['id'] for c in cases}) != len(cases):
        raise ValueError('Empty cases or duplicate IDs')
    results = []
    for case in cases:
        boundary = required(case, 'boundary', dict)
        periods = periods_of(case)
        if timestamp(boundary['period_start']) != periods[0]['start'] or timestamp(boundary['period_end']) != periods[-1]['end']:
            raise ValueError('Weather and boundary time intervals differ')
        required(case, 'bounds_basis')
        obs_range, mode, sources = observation_bounds(case, boundary)
        national = predictions[case['model_prediction_id']]
        boundary_match(boundary, national['boundary'])
        p = number(national['useful_heat_kwh'], 'national useful heat', 0)
        hypotheses = required(case, 'hypotheses', list)
        if not hypotheses or len({h['id'] for h in hypotheses}) != len(hypotheses):
            raise ValueError('No hypotheses or duplicate IDs')
        variants = []
        for h in hypotheses:
            evaluation = evaluate(h, periods)
            energy_ok = (obs_range is not None and obs_range[0]-1e-6 <= evaluation['required_useful_kwh'] <= obs_range[1]+1e-6)
            temp = case.get('temperature_observations', [])
            matched = True
            for t in temp:
                required(t, 'source_ref')
                zone = next((z for z in zones_of(h) if z.get('id') == t['zone_id']), None)
                if zone is None or t['period_id'] not in zone['indoor_c_by_period']:
                    raise ValueError('Temperature observation zone/period not represented')
                value = number(zone['indoor_c_by_period'][t['period_id']], 'temperature', TEMP_MIN, TEMP_MAX)
                lo = number(t['low_c'], 'temperature observation low', -30, 45)
                hi = number(t['high_c'], 'temperature observation high', -30, 45)
                if lo > hi:
                    raise ValueError('Reversed temperature observation interval')
                matched &= lo <= value <= hi
            # A physical-only case can test temperature constraints but not heating-energy agreement.
            feasible = matched and (obs_range is None or energy_ok)
            adequate = case.get('comfort_min_c')
            qcomfort = (evaluate(h, periods, number(adequate, 'comfort threshold', TEMP_MIN, TEMP_MAX))['required_useful_kwh']
                        if adequate is not None else None)
            variants.append({**evaluation, 'hypothesis_id':h['id'], 'energy_compatible':energy_ok if obs_range else None,
                             'temperature_compatible':matched, 'feasible_with_available_observations':feasible,
                             'constant_setpoint_inversion':invert_constant_setpoint(h, periods, obs_range),
                             'required_for_declared_comfort_kwh':qcomfort,
                             'comfort_heat_shortfall_kwh':(round(max(0, qcomfort-obs_range[1]),6)
                                if qcomfort is not None and obs_range is not None else None)})
        feasible = [v['hypothesis_id'] for v in variants if v['feasible_with_available_observations']]
        envelope = (min(v['required_useful_kwh'] for v in variants), max(v['required_useful_kwh'] for v in variants))
        structural_fit = envelope[0]-1e-6 <= p <= envelope[1]+1e-6
        national_ok = obs_range is not None and obs_range[0] <= p <= obs_range[1]
        national_status = ('NO_INDEPENDENT_ENERGY_TEST' if obs_range is None else
                           'NATIONAL_PREDICTION_WITHIN_OBSERVATION' if national_ok else
                           'NATIONAL_PREDICTION_OUTSIDE_OBSERVATION')
        expl = ('UNCONSTRAINED_PHYSICAL_SCREEN' if obs_range is None and not case.get('temperature_observations') else
                'NO_FEASIBLE_TESTED_STATE' if not feasible else 'MULTIPLE_COMPATIBLE_EXPLANATIONS'
                if len(feasible) > 1 else 'ONE_COMPATIBLE_NOT_IDENTIFIED')
        results.append({'case_id':case['id'], 'hypotheses':variants, 'compatible_hypotheses':feasible,
                        'physical_hypothesis_status':expl, 'national_prediction_status':national_status,
                        'national_prediction_kwh':p, 'national_prediction_within_observation':national_ok if obs_range else None,
                        'national_prediction_distance_to_observation_kwh':distance(p,*obs_range) if obs_range else None,
                        'national_prediction_within_tested_physical_envelope':structural_fit,
                        'national_prediction_distance_to_tested_envelope_kwh':distance(p,*envelope),
                        'national_tested_envelope_verdict':'STRUCTURAL_SCREEN_NOT_EMPIRICAL_VALIDATION',
                        'observation_mode':mode, 'observed_useful_heat_interval_kwh':list(obs_range) if obs_range else None,
                        'independence':independence(snapshot,case,sources), 'source_families':sorted({s['source_family_id'] for s in sources}),
                        'tested_useful_heat_envelope_kwh':list(envelope),
                        'transfer_scope':required(case, 'transfer_scope'), 'automatic_parameter_update':False})
    return {'schema':SCHEMA,'model_snapshot_sha256':sha,
            'test_spec_sha256':hashlib.sha256(json.dumps(data['cases'],sort_keys=True,allow_nan=False).encode()).hexdigest(),
            'results':results, 'method':'CONDITIONAL_QUASI_STEADY_WITH_INVERSE_CONSTANT_SETPOINT_SCREEN',
            'limitations':['Constant-setpoint inverse is NOT an observed indoor temperature or a dynamic simulation',
                           'No storage, cycling, thermal inertia or proven equipment cold-peak adequacy',
                           'Carrier-to-useful ranges depend on explicit, possibly overlapping assumptions',
                           'Local physical tests require source/selection review before national inference',
                           'A credible city sample need not contain complete historical renovations'],
            'runtime_promoted':False}


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        raise ValueError('Cannot overwrite input')
    result=run(json.loads(args.input.read_text(encoding='utf-8')))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
