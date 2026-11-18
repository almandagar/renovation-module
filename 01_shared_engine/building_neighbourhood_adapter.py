"""Read-only snapshot bridge to city-physical-tests/2. Never replaces the city solver."""
from copy import deepcopy
from datetime import datetime
from archetype_physics import heat,local_hypothesis

def export_case(cells,library,case,version,source_ref,calibration_sources=()):
    # Exact IDs and same period/area/service are mandatory. No national median fallback.
    ids=case['cell_ids'];selected=[c for c in cells if c['id'] in ids]
    if len(selected)!=len(set(ids)) or len(ids)!=len(set(ids)):raise ValueError('Unknown/duplicate local cell')
    if not selected:raise ValueError('No local stock')
    if any(c['place_id']!=case['place_id'] for c in selected):raise ValueError('Place boundary mismatch')
    area=sum(c['area_m2'] for c in selected)
    boundary=deepcopy(case['boundary'])
    if abs(area-boundary['conditioned_area_m2'])>1e-5:raise ValueError('Local area mismatch')
    periods=deepcopy(case['periods'])
    for p in periods:
        start=datetime.fromisoformat(p['start'].replace('Z','+00:00'));end=datetime.fromisoformat(p['end'].replace('Z','+00:00'))
        if start.tzinfo is None or end.tzinfo is None:raise ValueError('Timezone required')
        hours=(end-start).total_seconds()/3600
        if 'hours' in p and abs(p['hours']-hours)>1e-6:raise ValueError('Period hours mismatch')
        p['hours']=hours
    predicted=sum(heat(c,library,periods)['useful_heat_kwh'] for c in selected)
    h={'id':'cohort_state','zones':[local_hypothesis(c,library,periods) for c in selected]}
    local=deepcopy(case);local.pop('cell_ids');local.pop('place_id')
    local['model_prediction_id']=case['id'];local.setdefault('hypotheses',[h])
    return {'schema':'city-physical-tests/2','model_snapshot':{'version':version,'source_ref':source_ref,
       'calibration_source_families':list(calibration_sources),'predictions':{
        case['id']:{'boundary':boundary,'useful_heat_kwh':predicted}}},'cases':[local]}
