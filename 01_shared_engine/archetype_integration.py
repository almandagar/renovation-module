"""Executable archetype intake and output-specific research checklist.
No inferred national shares, physical profiles, or resource coefficients.
"""
from copy import deepcopy
from math import isclose
from archetype_physics import resolve, positive, package_effect
from renovation_stock import totals, QUANTITIES

STATUSES = ('PASS', 'CONDITIONAL', 'BLOCKED', 'NOT_APPLICABLE')


def prepare_bundle(bundle):
    """Resolve explicitly supplied compatible fallbacks without changing quantities.

    The country adapter owns compatibility and state assignment. This function
    enforces declared country/use/period scope; it never guesses from a label.
    """
    b = deepcopy(bundle)
    library = b['library']
    rules = b.get('archetype_fallbacks', {})
    for c in b['opening_cells']:
        if c.get('archetype_id') in library['archetypes']:
            validate_compatibility(c, library['archetypes'][c['archetype_id']], b['country'])
            continue
        key = c.get('fallback_key')
        r = rules.get(key)
        if not r:
            raise ValueError('No compatible physical archetype/fallback for '+str(c.get('id')))
        for field in ('archetype_id', 'source_ref', 'compatibility_basis', 'country', 'use', 'construction_period'):
            if not r.get(field):
                raise ValueError('Fallback rule missing '+field)
        if r['country'] != b['country'] or c.get('use') != r['use']:
            raise ValueError('Fallback country/use mismatch')
        period = c['construction_period']; scope = r['construction_period']
        if len(scope) != 2 or not scope[0] <= period[0] <= period[1] <= scope[1]:
            raise ValueError('Fallback period mismatch')
        if r['archetype_id'] not in library['archetypes']:
            raise ValueError('Fallback physical profile is missing')
        if r.get('place_ids') is not None and c['place_id'] not in r['place_ids']:
            raise ValueError('Fallback geography mismatch')
        c['archetype_assignment'] = {
            'kind': 'PHYSICAL_FALLBACK', 'requested_archetype_id': c.get('archetype_id'),
            'fallback_key': key, 'source_ref': r['source_ref'],
            'compatibility_basis': r['compatibility_basis'], 'family_id':r.get('family_id'),
            'evidence_class':r.get('evidence_class','MODEL_ASSUMPTION')}
        c['archetype_id'] = r['archetype_id']
        # Existing component state and heating remain independent.
        validate_compatibility(c, library['archetypes'][c['archetype_id']], b['country'])
        resolve(c, library)
    return b


def validate_snapshot(bundle):
    """Country-neutral dated research opening; no invented historical replay."""
    s = bundle['research_opening_snapshot']
    if s.get('schema') != 'research-stock-snapshot/1':
        return False  # Legacy fixed Košice route retains its original checks.
    for k in ('country', 'as_of_date', 'stock_boundary', 'source_ref', 'state_basis', 'uncertainty_ref'):
        if not isinstance(s.get(k), str) or not s[k].strip():
            raise ValueError('Research snapshot missing '+k)
    if s['country'] != bundle['country'] or s['as_of_date'] != bundle['history_start']:
        raise ValueError('Research snapshot country/date mismatch')
    if s.get('evidence_class') != 'CONDITIONAL_MODEL_PRIOR_NOT_OBSERVED':
        raise ValueError('Research snapshot must preserve inferred status')
    if bundle.get('historical_events') or bundle.get('spatial_substitutions'):
        raise ValueError('Reconcile dated snapshot before intake; no historical replay or runtime substitutions')
    if any(c.get('history') or c.get('first_deep_date') or c.get('deep_achieved') for c in bundle['opening_cells']):
        raise ValueError('Snapshot cannot assert historical first-deep events')
    expected = s.get('population_totals', {})
    actual = totals(bundle['opening_cells'])
    for k in QUANTITIES:
        positive(expected.get(k), 'snapshot '+k)
        if not isclose(actual[k], expected[k], rel_tol=1e-9, abs_tol=1e-6):
            raise ValueError('Research snapshot population mismatch: '+k)
    return True


def checklist(bundle, results=None, error=None):
    """Report evidence and execution separately; never certify empirical accuracy."""
    rows = []
    def add(key, status, reason, affected, evidence=None):
        rows.append(dict(id=key, status=status, reason=reason,
                         affected_outputs=affected, evidence=evidence or []))
    cells = bundle.get('opening_cells', [])
    library = bundle.get('library', {})
    review = bundle.get('archetype_evidence_review', [])
    review_ok = bool(review) and all(r.get('source_ref') and r.get('decision') in ('USED','EXCLUDED','PROXY_ONLY') and r.get('reason') for r in review)
    add('existing_evidence', 'PASS' if review_ok else 'CONDITIONAL',
        'Source assessment supplied; relevance remains human-reviewed.' if review_ok else 'Supply review of applicable shared/country families and exclusions; no empirical certification inferred.',
        ['integration_claim'], review)
    coverage = {k: {q: 0.0 for q in QUANTITIES} for k in ('SPECIFIC','PHYSICAL_FALLBACK','UNCLASSIFIED_PHYSICAL','UNRESOLVED')}
    failures = []; identities = set()
    for c in cells:
        try:
            if c['id'] in identities: raise ValueError('Duplicate stock identity')
            identities.add(c['id'])
            for q in QUANTITIES: positive(c[q],q)
            validate_compatibility(c, library['archetypes'][c['archetype_id']], bundle['country'])
            resolve(c, library)
            kind = c.get('archetype_assignment',{}).get('kind','UNCLASSIFIED_PHYSICAL')
            if kind not in ('SPECIFIC','PHYSICAL_FALLBACK'): kind='UNCLASSIFIED_PHYSICAL'
        except (KeyError, ValueError, TypeError) as exc:
            kind='UNRESOLVED'; failures.append({'cell_id':c.get('id'),'reason':str(exc)})
        for q in QUANTITIES:
            v=c.get(q)
            if isinstance(v,(int,float)) and not isinstance(v,bool):
                try:positive(v,q);coverage[kind][q]+=v
                except ValueError:pass
    add('physical_inputs','BLOCKED' if failures else 'PASS',
        'Resolved component physics for all supplied opening cells.' if not failures else 'Invalid cells are not silently dropped.', ['baseline_heat','interventions'],failures)
    unresolved=bundle.get('unresolved_stock',[])
    for r in unresolved:
        for q in QUANTITIES: positive(r.get(q),'unresolved '+q);coverage['UNRESOLVED'][q]+=r[q]
        if not r.get('source_ref') or not r.get('reason'):raise ValueError('Unresolved remainder requires source and reason')
    controls=bundle.get('stock_controls')
    balance=[]
    if controls:
        if not controls.get('source_ref') or controls.get('as_of_date')!=bundle.get('history_start'):
            raise ValueError('Stock controls need source and matching opening date')
        for q in QUANTITIES:
            target=positive(controls['totals'].get(q),'stock control '+q)
            got=sum(v[q] for v in coverage.values())
            if not isclose(got,target,rel_tol=1e-9,abs_tol=1e-6):balance.append(q)
    add('stock_allocation','BLOCKED' if balance else 'PASS' if controls else 'CONDITIONAL',
        'Control mismatch: '+','.join(balance) if balance else 'Parent totals reconciled; physical disjointness remains source-reviewed.' if controls else 'No independent opening parent controls supplied.', ['whole_stock_claim'],[controls] if controls else [])
    u=bundle.get('archetype_uncertainty',{})
    add('uncertainty','PASS' if u.get('source_ref') and u.get('central_basis') and u.get('alternatives') else 'CONDITIONAL',
        'Alternative references recorded; this checklist does not claim they have been executed.', ['robustness_claim'],[u] if u else [])
    add('opening_date','CONDITIONAL' if bundle.get('research_opening_snapshot') else 'PASS',
        'Dated inferred state; no historical first-deep claim.' if bundle.get('research_opening_snapshot') else 'Historical chronology is checked by the scheduler.', ['historical_claim'])
    package_errors=[];unknown=[];work=0
    for scenario in bundle.get('scenarios',[]):
        for e in scenario.get('events',[]):
            if e.get('kind')!='renovation':continue
            from renovation_stock import match
            for c in cells:
                if not match(c,e.get('selector',{})):continue
                work+=1
                try:
                    _,_,inv=package_effect(c,library['packages'][e['package_id']],library)
                    unknown.extend(inv.get('unknown',[]))
                except (KeyError,ValueError,TypeError) as exc:package_errors.append(str(exc))
    add('interventions','BLOCKED' if package_errors else 'PASS' if work else 'NOT_APPLICABLE',
        'Opening-cohort package checks; later event states remain scheduler-validated.', ['intervention_heat','work_quantities'],package_errors)
    if results:unknown.extend(x for r in results for x in r.get('unknowns',[]))
    add('resources','CONDITIONAL' if unknown or not bundle.get('capacity') else 'PASS',
        'Missing inventories/capacities restrict delivery claims, not baseline physics; supplied coefficients are not empirically certified.',
        ['resource_constrained_delivery'],sorted(set(unknown)))
    add('execution','BLOCKED' if error else 'PASS' if results else 'CONDITIONAL',
        error or ('Shared scheduler completed with conservation checks.' if results else 'Not yet executed.'),['integration_claim'])
    add('coverage','CONDITIONAL' if unresolved or failures or coverage['UNCLASSIFIED_PHYSICAL']['area_m2'] else 'PASS',
        'Coverage is opening-stock quantities, not number of catalogue rows. Unresolved stock is excluded from computed heat and remains visible.', ['whole_stock_claim'])
    add('claim_boundary','CONDITIONAL','Research calculation only; software success is not independent validation or authoritative publication.', ['empirical_accuracy','authoritative_forecast'])
    blockers=[r['id'] for r in rows if r['status']=='BLOCKED']
    total={q:sum(v[q] for v in coverage.values()) for q in QUANTITIES}
    details = integration_details(bundle, coverage, results, error, blockers)
    return {**details, 'schema':'archetype-integration-checklist/1','country':bundle.get('country'),
            'status':'BLOCKED' if blockers else 'EXECUTED_CONDITIONAL' if results else 'READY_CONDITIONAL',
            'checks':rows,'blocking_checks':blockers,'coverage':coverage,'coverage_totals':total,
            'coverage_fraction':{k:{q:(v[q]/total[q] if total[q] else None) for q in QUANTITIES} for k,v in coverage.items()},
            'runtime_promoted':False,'independent_validation':'NOT_ESTABLISHED_BY_THIS_CHECKLIST'}


def validate_compatibility(cell, profile, country):
    """Apply declared physical-profile scope to direct and fallback IDs alike."""
    if cell.get('country', country) != country:
        raise ValueError('Cell country mismatch')
    for key, value in (('country', country), ('use', cell.get('use'))):
        if profile.get(key) is not None and profile[key] != value:
            raise ValueError('Physical profile '+key+' mismatch')
    scope=profile.get('construction_period'); period=cell.get('construction_period')
    if scope and (not period or not scope[0] <= period[0] <= period[1] <= scope[1]):
        raise ValueError('Physical profile period mismatch')
    if profile.get('place_ids') is not None and cell.get('place_id') not in profile['place_ids']:
        raise ValueError('Physical profile geography mismatch')


def source_scope_review(bundle):
    """Coverage of a declared registry scope; not proof of source exhaustiveness."""
    m=bundle.get('source_scope_manifest', {})
    issues=[]
    for key in ('registry_ref','registry_version','country','families'):
        if not m.get(key):issues.append('manifest_missing:'+key)
    if m.get('country') != bundle.get('country'):issues.append('manifest_country')
    reviews=bundle.get('archetype_evidence_review',[])
    indexed={}
    for r in reviews:
        key=r.get('family_id')
        if key in indexed:issues.append('duplicate_review:'+str(key))
        indexed[key]=r
    seen=set()
    for f in m.get('families',[]):
        key=f.get('family_id')
        if not key or key in seen:issues.append('invalid_or_duplicate_family:'+str(key))
        seen.add(key)
        for field in ('source_ref','date','population_unit','geography','cohort_scope'):
            if not f.get(field):issues.append(str(key)+':missing_'+field)
        r=indexed.get(key,{})
        if r.get('decision') not in ('USED','EXCLUDED','PROXY_ONLY','UNRESOLVED') or not r.get('reason') or not r.get('source_ref'):
            issues.append(str(key)+':missing_disposition')
        for field in ('date','population_unit','geography','cohort_scope'):
            if r.get(field)!=f.get(field):issues.append(str(key)+':scope_mismatch_'+field)
    for c in bundle.get('opening_cells',[]):
        family=c.get('archetype_assignment',{}).get('family_id')
        r=indexed.get(family,{})
        if family not in seen or r.get('decision')!='USED':issues.append(str(c.get('id'))+':assignment_not_linked_to_used_family')
    return {'status':'INCOMPLETE' if issues else 'COMPLETE_AGAINST_DECLARED_SCOPE',
            'issues':issues,'registry_ref':m.get('registry_ref'),'registry_version':m.get('registry_version'),
            'exhaustiveness':'NOT_MACHINE_VERIFIED'}


def integration_details(bundle, coverage, results, error, blockers):
    scope=bundle.get('integration_scope')
    allowed=('DONOR_PHYSICS','STOCK_PHYSICS','RESOURCE_DELIVERY')
    missing=[]
    if scope not in allowed:missing.append('integration_scope')
    review=source_scope_review(bundle)
    if review['status']=='INCOMPLETE':missing.append('source_scope_review')
    u=bundle.get('archetype_uncertainty',{})
    if not (u.get('source_ref') and u.get('central_basis') and (u.get('alternatives') or u.get('not_applicable_reason'))):missing.append('uncertainty_design')
    if u.get('alternatives') and not bundle.get('alternative_run_evidence'):missing.append('alternative_execution_evidence')
    if scope in ('STOCK_PHYSICS','RESOURCE_DELIVERY') and not bundle.get('stock_controls'):missing.append('stock_controls')
    if scope=='RESOURCE_DELIVERY':
        if not bundle.get('capacity'):missing.append('capacity')
        if not results or any(r.get('unknowns') for r in results):missing.append('resource_execution_or_inventory')
    resolution={'RESOLVED':{q:sum(coverage[k][q] for k in ('SPECIFIC','PHYSICAL_FALLBACK','UNCLASSIFIED_PHYSICAL')) for q in QUANTITIES},'UNRESOLVED':coverage['UNRESOLVED']}
    assignments=[]
    for c in bundle.get('opening_cells',[]):
        a=c.get('archetype_assignment',{})
        profile=bundle.get('library',{}).get('archetypes',{}).get(c.get('archetype_id'),{})
        assignments.append({'cell_id':c.get('id'),'archetype_id':c.get('archetype_id'),
            'selection_route':'FALLBACK_RULE' if a.get('fallback_key') else 'EXPLICIT_LIBRARY_ID',
            'assignment_evidence':a.get('evidence_class','UNSPECIFIED'),
            'family_id':a.get('family_id'),
            'profile_scope_fields_present':[k for k in ('country','use','construction_period','place_ids') if k in profile]})
    return {'execution_status':'FAILED' if error or blockers else 'SUCCEEDED' if results else 'NOT_EXECUTED',
        'integration_completeness':{'scope':scope,'status':'BLOCKED' if blockers or error else 'INCOMPLETE' if missing or not results else 'COMPLETE_AGAINST_DECLARED_SCOPE','missing_requirements':missing},
        'source_scope_review':review,'physical_resolution':resolution,'assignments':assignments,
        'physical_coverage_complete':not any(coverage['UNRESOLVED'].values()),
        'empirical_qualification':{'status':'NOT_ESTABLISHED','scope':'No independent prediction evidence evaluated by this checklist'}}


def aggregate_population_branches(branches, parent, weight_unit='dwellings'):
    """Aggregate already calculated disjoint branches; never average assemblies.

    Each branch supplies quantities and total useful heat. An unresolved branch
    must explicitly set resolved=False and heat=None. No renormalisation.
    """
    if weight_unit not in QUANTITIES:raise ValueError('Unknown weight unit')
    if len({b['id'] for b in branches})!=len(branches):raise ValueError('Duplicate branch')
    for q in QUANTITIES:
        positive(parent.get(q),'parent '+q,False)
        for b in branches:positive(b[q],'branch '+q)
        if not isclose(sum(b[q] for b in branches),parent[q],rel_tol=1e-9,abs_tol=1e-6):raise ValueError('Branch conservation '+q)
    heat=0.; unresolved={q:0. for q in QUANTITIES};weights={}
    for b in branches:
        weights[b['id']]=b[weight_unit]/parent[weight_unit]
        if b.get('resolved') is True:
            heat+=positive(b.get('useful_heat_kwh'),'branch heat')
        elif b.get('resolved') is False and b.get('useful_heat_kwh') is None:
            for q in QUANTITIES:unresolved[q]+=b[q]
        else:raise ValueError('Explicit branch resolution and heat required')
    resolved_area=parent['area_m2']-unresolved['area_m2']
    return {'resolved_useful_heat_kwh':heat,'resolved_area_intensity_kwh_m2':heat/resolved_area if resolved_area else None,
            'whole_parent_useful_heat_kwh':None if any(unresolved.values()) else heat,
            'parent_quantities':dict(parent),'unresolved_quantities':unresolved,'weights':weights,'weight_unit':weight_unit}
