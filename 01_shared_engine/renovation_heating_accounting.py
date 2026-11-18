"""Heating-system accounting alongside the two building flows. Energy units: TWh."""
from dataclasses import dataclass
from math import isclose

@dataclass(frozen=True)
class HeatingCohort:
    technology: str
    installed_year: int
    useful_heat: float
    spf: float
    hp_share: float = 1.0
    backup_efficiency: float = .9
    active_fraction: float = 1.0
    service: str = 'SPACE_HEAT'

def closing_units(opening, commissioned, retired):
    if min(opening, commissioned, retired) < 0 or retired > opening + commissioned:
        raise ValueError('Invalid unit inventory')
    return opening + commissioned - retired

def useful_heat(opening, removed, fabric_reduction, newbuild, service_factor=1.0):
    if opening < 0 or not 0 <= removed <= opening or not 0 <= fabric_reduction <= 1 or newbuild < 0 or service_factor < 0:
        raise ValueError('Invalid useful-heat balance')
    return ((opening-removed)*(1-fabric_reduction)+newbuild)*service_factor

def carrier_energy(cohorts, year, service='SPACE_HEAT'):
    out=dict(useful_heat=0., electricity=0., gas=0., ambient=0.)
    for c in cohorts:
        if c.installed_year > year or c.useful_heat < 0 or c.spf < 1 or not 0 <= c.hp_share <= 1 or not 0 < c.backup_efficiency <= 1 or not 0 <= c.active_fraction <= 1:
            raise ValueError('Invalid heating cohort or vintage')
        if c.service != service:
            continue
        q=c.useful_heat*c.active_fraction
        hp=q*c.hp_share
        out['useful_heat']+=q
        out['electricity']+=hp/c.spf
        out['ambient']+=hp-hp/c.spf
        out['gas']+=(q-hp)/c.backup_efficiency
    return out

def validation_gate(*, observed=None, predicted=None, heating=False, stock=False, boundaries=False, weather_service=False, independence=False):
    if observed is None or predicted is None:
        return 'OPEN_ENERGY_INPUTS'
    if not all((heating,stock,boundaries,weather_service)):
        return 'DIAGNOSTIC_UNATTRIBUTED'
    return 'READY_INDEPENDENT_TEST' if independence else 'CONDITIONAL_SHARED_LINEAGE'
