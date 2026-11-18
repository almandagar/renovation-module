"""Separate construction flow: date-qualified standards and explicit lifecycle inventory.
Rules are input records, never silently inferred from completion year or pathway.
"""
from datetime import date
from copy import deepcopy
from archetype_physics import positive,heat

def wlc(design, area):
    inventory=deepcopy(design.get('wlc_kgco2e_m2',{}))
    if 'product_factors_kgco2e_kg' in design:
        masses=design['installed_kg'];factors=design['product_factors_kgco2e_kg']
        if all(k in factors for k in masses):inventory['A1_A3']=sum(v*factors[k] for k,v in masses.items())
        else:inventory.pop('A1_A3',None)
    modules=('A1_A3','A4_A5','B1_B3_B5','B4','B6','B7','C1_C4')
    for k,v in inventory.items():
        if not isinstance(v,(int,float)):raise ValueError('Non-numeric WLC')
    missing=[m for m in modules if m not in inventory]
    return {'modules_kgco2e':{m:v*area for m,v in inventory.items()},
      'A_to_C_kgco2e':None if missing else sum(inventory[m]*area for m in modules),
      'missing_modules':missing,'assessment_years':design.get('assessment_years'),
      'method_ref':design.get('wlc_method_ref'),'D_separate_not_netted':True}

def assess(request, design, rules):
    reports=[]; metrics=design.get('metrics',{})
    for r in rules:
        if r['jurisdiction'] not in (request['country'],'EU','*'):continue
        if r.get('owner') and r['owner']!=request.get('owner'):continue
        if r.get('target_only') and r['id'] not in request.get('targets',[]):continue
        basis=r['date_basis']
        if basis not in request:
            reports.append({'rule':r['id'],'status':'UNASSESSED','reason':'missing '+basis});continue
        d=date.fromisoformat(request[basis])
        if d<date.fromisoformat(r['valid_from']) or (r.get('valid_until') and d>=date.fromisoformat(r['valid_until'])):continue
        if request.get('exemptions',{}).get(r['id']):
            reports.append({'rule':r['id'],'status':'EXEMPT','source_ref':request['exemptions'][r['id']]});continue
        if r.get('floor_area_gt') is not None and request['building_floor_area_m2']<=r['floor_area_gt']:continue
        checks=[]
        for group in r.get('any_maximums',[]):
            statuses=['UNKNOWN' if k not in metrics else 'PASS' if metrics[k]<=v else 'FAIL' for k,v in group.items()]
            checks.append((' OR '.join(group),'PASS' if 'PASS' in statuses else 'UNKNOWN' if 'UNKNOWN' in statuses else 'FAIL'))
        for k,limit in r.get('maximums',{}).items():
            checks.append((k,'UNKNOWN' if k not in metrics else 'PASS' if metrics[k]<=limit else 'FAIL'))
        for k,expected in r.get('equals',{}).items():
            checks.append((k,'UNKNOWN' if k not in metrics else 'PASS' if metrics[k]==expected else 'FAIL'))
        if r.get('wlc_required'):
            report=wlc(design,request['area_m2'])
            ok=not report['missing_modules'] and report['method_ref'] and report['assessment_years']
            checks.append(('wlc_documented','PASS' if ok else 'UNKNOWN'))
        if not checks: checks=[('country_implementation','UNKNOWN')]
        status='FAIL' if any(v=='FAIL' for _,v in checks) else 'UNASSESSED' if any(v=='UNKNOWN' for _,v in checks) else 'PASS_DECLARED_METRICS'
        reports.append({'rule':r['id'],'status':status,'checks':dict(checks),'source_ref':r['source_ref'],
                        'date_basis':basis,'applicability_date':request[basis]})
    return reports or [{'rule':'national_requirements','status':'UNASSESSED','reason':'No applicable supplied rule'}]

def prepare(request, library, rules):
    designs=request.get('design_candidates',[request.get('design_id')])
    assessed=[]
    for design_id in designs:
        candidate=deepcopy(library['newbuild_designs'][design_id]);candidate['design_id']=design_id
        if candidate.get('standard_weather'):
            physical={'archetype_id':candidate['archetype_id'],'area_m2':1.,'state':candidate['state'],'heating':candidate['heating']}
            candidate.setdefault('metrics',{})['model_useful_heat_kwh_m2_a']=heat(physical,library,candidate['standard_weather'],20)['useful_heat_kwh']
        report=assess(request,candidate,rules)
        assessed.append((candidate,report))
    eligible=[pair for pair in assessed if not any(r['status']=='FAIL' for r in pair[1])]
    if not eligible and not request.get('observed_noncompliance_source'):
        raise ValueError('No construction design meets supplied dated requirements')
    # Prefer complete supplied screens; unknown national compliance is never a claimed pass.
    eligible.sort(key=lambda pair:sum(r['status']=='UNASSESSED' for r in pair[1]))
    design,reports=(eligible or assessed)[0]
    if any(r['status']=='FAIL' for r in reports) and not request.get('observed_noncompliance_source'):
        raise ValueError('Newbuild design fails declared standard: '+request['id'])
    for q in ('area_m2','buildings','building_floor_area_m2'):positive(request[q],q,False)
    # A clinic, hospital, school or workshop can add buildings and area but ZERO
    # dwellings. Protect typed nonres projects without inventing residential stock.
    positive(request['dwellings'],'dwellings')
    c={k:deepcopy(request[k]) for k in ('area_m2','buildings','dwellings','place_id','country')}
    c.update(id=request['id'],origin='NEW_CONSTRUCTION',archetype_id=design['archetype_id'],
       construction_period=[int(request['completion_date'][:4])]*2,state=design['state'],heating=design['heating'],
       source_ref=request['source_ref'],history=[],heritage=False)
    return c,design,reports
