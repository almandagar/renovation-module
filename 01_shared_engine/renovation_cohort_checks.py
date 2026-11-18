"""French gas-heated cohort bridge. Conditional physics, not national calibration.

Inputs/outputs use kWh PCI and one unchanged cohort/weather definition.
Physical inputs are at fixed service, before any Social price overlay.
"""
import math

REQUIRED = ('baseline_gas_kwh_pci', 'heating_fraction', 'old_gas_efficiency',
            'fabric_saving', 'service_factor', 'gas_heat_fraction_after',
            'new_gas_efficiency', 'hp_spf', 'nonheat_gas_retained')

def numeric(x, key, lo=0, hi=None):
    if isinstance(x, bool) or not isinstance(x, (float, int)) or not math.isfinite(x):
        raise ValueError(key + ': finite number required')
    if x < lo or (hi is not None and x > hi):
        raise ValueError(key + ': outside physical range')
    return float(x)

def simulate(p):
    missing = [k for k in REQUIRED if p.get(k) is None]
    if missing:
        return {'status':'OPEN_PHYSICAL_INPUTS', 'missing': missing}
    if p.get('already_price_adjusted', False):
        raise ValueError('Physical baseline must precede Social price adjustment')
    b = numeric(p['baseline_gas_kwh_pci'], 'baseline', 1e-12)
    h = numeric(p['heating_fraction'], 'heating_fraction', 0, 1)
    e0 = numeric(p['old_gas_efficiency'], 'old_efficiency', 1e-12, 1)
    s = numeric(p['fabric_saving'], 'fabric_saving', 0, 1)
    t = numeric(p['service_factor'], 'service_factor', 1e-12)
    r = numeric(p['gas_heat_fraction_after'], 'retained_heat_fraction', 0, 1)
    e1 = numeric(p['new_gas_efficiency'], 'new_efficiency', 1e-12, 1)
    spf = numeric(p['hp_spf'], 'hp_spf', 1)
    n = numeric(p['nonheat_gas_retained'], 'nonheat_retained', 0, 1)
    u0 = b*h*e0
    uf = u0*(1-s)
    u = uf*t
    gas = u*r/e1 + b*(1-h)*n
    electric = u*(1-r)/spf
    ambient = u*(1-r)-electric
    out = dict(status='CONDITIONAL_PHYSICS', baseline_useful_heat=u0,
               fixed_service_post_heat=uf, served_post_heat=u,
               fabric_avoided_useful_heat=u0-uf, service_change_useful_heat=u-uf,
               post_gas_kwh_pci=gas, hp_electricity_kwh=electric,
               hp_ambient_kwh=ambient, gas_saving_fraction=1-gas/b,
               adjusted_gas_kwh_pci=None, adjusted_hp_electricity_kwh=None,
               price_component_gas=None, price_component_hp=None,
               overlay_status='OPEN_SOCIAL_OVERLAY')
    if p.get('boundaries_matched') is True and p.get('evidence_id'):
        if p.get('gas_price_factor') is not None:
            fg=numeric(p['gas_price_factor'],'gas_price_factor',1e-12)
            out.update(adjusted_gas_kwh_pci=gas*fg,price_component_gas=gas*(fg-1),
                       overlay_status='CANDIDATE_MATCHED_GAS_OVERLAY')
        if p.get('hp_price_factor') is not None:
            fe=numeric(p['hp_price_factor'],'hp_price_factor',1e-12)
            out.update(adjusted_hp_electricity_kwh=electric*fe,price_component_hp=electric*(fe-1),
                       overlay_status='CANDIDATE_MATCHED_HP_OVERLAY')
        if out['adjusted_gas_kwh_pci'] is not None and out['adjusted_hp_electricity_kwh'] is not None:
            out['overlay_status']='CANDIDATE_MATCHED_OVERLAY'
    return out

def staged_saving(stages):
    remaining=1.0
    seen=set()
    for stage in stages:
        if not stage.get('measure_id') or stage['measure_id'] in seen:
            raise ValueError('Distinct completed component/stage IDs required')
        seen.add(stage['measure_id'])
        remaining *= 1-numeric(stage['saving_remaining'],'stage saving',0,1)
    return 1-remaining

def compare_target(predicted_change, target, *, matched=False, price_already_in_effect=False):
    if not matched:
        return {'status':'OPEN_COHORT_COMPARABILITY','residual_pp':None}
    # Observed meter ATT already contains the treatment cohort's realised usage.
    # Applying the price overlay to an empirical ATT again is not permissible.
    if price_already_in_effect:
        raise ValueError('Do not apply a second price correction to empirical ATT')
    v=numeric(predicted_change,'predicted change',-1)
    return {'status':'MATCHED_SAMPLE_DIAGNOSTIC','residual_pp':(v-target['effect_fraction'])*100,
            'within_reported_95ci':target['ci_low_fraction']<=v<=target['ci_high_fraction']}
