"""Single country entry point for component-state stock and distinct construction flow."""
import json,hashlib
from pathlib import Path
from renovation_module import run

def run_pipeline(input_path,output_dir,modifiers_csv=None):
    source=Path(input_path);bundle=json.loads(source.read_text(encoding='utf-8'))
    if modifiers_csv:raise ValueError('Translate modifiers to dated packages/capacity/readiness; generic energy multipliers are unsupported')
    if bundle.get('schema')!='building-stock/2':raise ValueError('Old aggregate inputs are archived. Supply building-stock/2 component-state bundle.')
    if 'library_path' in bundle:
        bundle['library']=json.loads((source.parent/bundle['library_path']).read_text(encoding='utf-8'))
    from archetype_integration import prepare_bundle, checklist
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    checklist_path=out/'archetype_integration_checklist.json'
    try:
        bundle=prepare_bundle(bundle)
        report=checklist(bundle)
        if report['blocking_checks']:
            raise ValueError('Archetype intake blocked: '+','.join(report['blocking_checks']))
    except (KeyError,ValueError,TypeError) as exc:
        report={'schema':'archetype-integration-checklist/1','status':'BLOCKED',
                'error':str(exc),'runtime_promoted':False}
        checklist_path.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
        raise
    report['input_sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
    checklist_path.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    scenarios=bundle['scenarios']
    if len({s['id'] for s in scenarios})!=len(scenarios):raise ValueError('Duplicate scenario')
    try:
        results=[run(bundle,s) for s in scenarios]
    except (KeyError,ValueError,TypeError) as exc:
        report=checklist(bundle,error=str(exc))
        report['input_sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
        checklist_path.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
        raise
    report=checklist(bundle,results)
    report['input_sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
    checklist_path.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    selection={}
    for path in sorted({s['pathway'] for s in scenarios}):
        rows=[r for r in results if r['pathway']==path and r['timing']=='central']
        if rows:
            # Compare final-year carrier heat on same opening stock; record adequacy separately.
            if bundle.get('research_opening_snapshot'):
                # No fictional carrier choice or national final-energy winner
                # may be inferred from unknown 2024 heating equipment.
                selection[path]={'default':None,'details':[r['scenario'] for r in rows],
                  'metric':'NOT_APPLICABLE_UNKNOWN_CARRIER_SERVICE_PROXY',
                  'adequacy':'Research-only, no pathway winner, metered energy or runtime promotion'}
            else:
                rank=sorted(rows,key=lambda r:(sum(v for k,v in r['annual'][-1].items() if k.startswith('carrier_')),r['scenario']))
                selection[path]={'default':rank[0]['scenario'],'details':[r['scenario'] for r in rank[1:]],
                   'metric':'final_year_final_space_heating_kwh','adequacy':'Requires independent comfort test; ranking is conditional'}
    from renovation_materials import export_inventory
    payload={'results':results,'selection':selection}
    materials=export_inventory(results)
    paths={'archetype_integration_checklist':checklist_path}
    for name,data in [('cohort_results',payload),('resolved_country_inputs',bundle),('material_inventory',materials)]:
        p=out/(name+'.json');p.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n');paths[name]=p
    if 'stock_validation' in bundle:
        from renovation_validation import run_validation
        paths.update(run_validation(bundle['stock_validation'],bundle['country'],out/'validation'))
    # Optional SOURCE-CONSTRAINED categorical geography calibration. This is a
    # diagnostic sidecar, never a second population, a generator installation,
    # or a mutation of the shared 2011/2024 physical opening stock.
    if 'spatial_heating_calibration' in bundle:
        from renovation_reconciliation import reconstruct_geographic_joint
        spec=bundle['spatial_heating_calibration']
        if spec.get('country',bundle['country'])!=bundle['country']:
            raise ValueError('Spatial heating sidecar country boundary disagrees')
        for field in ('national_joint','place_totals','place_marginals','source_ref','reference_year'):
            if field not in spec:raise ValueError('Spatial calibration missing '+field)
        if not spec['source_ref'] or int(spec['reference_year'])>=int(bundle['forecast_start'][:4]):
            raise ValueError('Spatial heating calibration must reference an observed pre-forecast population')
        if spec.get('population_unit')!='dwellings':
            raise ValueError('Heating-source census calibration currently requires dwelling counts')
        calibrated=reconstruct_geographic_joint(spec['national_joint'],spec['place_totals'],
                 spec['place_marginals'],population_unit='dwellings',
                 place_category_priors=spec.get('place_category_priors'))
        calibrated.update(reference_year=int(spec['reference_year']),source_ref=spec['source_ref'],
             use='RESEARCH_SIDE_CAR_NOT_PHYSICAL_STOCK_OR_HOUSING_HEAT_PUMP_COUNTS')
        if spec.get('place_category_priors'):
            calibrated['place_category_priors']=spec['place_category_priors']
            calibrated['prior_role']='SOFT_WEIGHTS_NOT_OBSERVED_LOCAL_MARGINALS'
        p=out/'spatial_heating_calibration.json'
        p.write_text(json.dumps(calibrated,indent=2,allow_nan=False)+'\n')
        paths['spatial_heating_calibration']=p
    # Optional nonadditive AP building-system and component reporting sidecar.
    # This consumes source-owned district x vintage x dwelling-size bins,
    # period-compatible original family priors and a separate current-state
    # indicator joint. It never inserts these 2021 estimates into the 2011
    # opening stock, never credits RA/deep renovation and never alters heat.
    if 'spatial_panel_archetype_calibration' in bundle:
        from renovation_reconciliation import (allocate_bounded_dwelling_bins,
             allocate_original_family_overlay, component_flag_joint)
        spec=bundle['spatial_panel_archetype_calibration']
        mandatory=('country','source_ref','reference_year','place_totals',
                   'cohorts','size_bounds','scenarios')
        for field in mandatory:
            if field not in spec:raise ValueError('Panel spatial sidecar missing '+field)
        if spec['country']!=bundle['country']:
            raise ValueError('Panel spatial sidecar country boundary disagrees')
        if not spec['source_ref'] or int(spec['reference_year'])>=int(bundle['forecast_start'][:4]):
            raise ValueError('Panel sidecar requires a sourced preforecast census stock')
        if not spec['scenarios'] or len({s['id'] for s in spec['scenarios']})!=len(spec['scenarios']):
            raise ValueError('Missing/duplicate panel scenario')
        if not spec['place_totals'] or not spec['cohorts']:
            raise ValueError('Panel sidecar requires observed local denominators')
        by_place={}
        for record in spec['cohorts']:
            place=record['place_id']
            if place not in spec['place_totals']:
                raise ValueError('Cohort place is absent from source totals')
            by_place.setdefault(place,[]).append(record)
        if set(by_place)!=set(spec['place_totals']):
            raise ValueError('Source place totals lack a complete cohort partition')
        sidecar=[]
        for scenario in spec['scenarios']:
            if 'unit_prior_means' not in scenario or 'family_weights' not in scenario:
                raise ValueError('Panel scenario requires explicit bin/era family priors')
            cells=[];place_checks=[]
            for place,records in by_place.items():
                observed=spec['place_totals'][place]
                total_bins={k:0. for k in spec['size_bounds']}
                for record in records:
                    if set(record['buildings_by_bin'])!=set(total_bins):
                        raise ValueError('Cohort source bin definitions must match')
                    for k,v in record['buildings_by_bin'].items():total_bins[k]+=v
                if abs(sum(total_bins.values())-observed['buildings'])>1e-6:
                    raise ValueError('Source building count mismatch within place')
                res=allocate_bounded_dwelling_bins(total_bins,observed['dwellings'],
                        spec['size_bounds'],scenario['unit_prior_means'])
                for record in records:
                    period=record['original_period']
                    rules=scenario['family_weights'].get(period)
                    if rules is None:raise ValueError('No prior for original construction period '+str(period))
                    bins=record['buildings_by_bin']
                    d_bin={k:bins[k]*(res['per_building'][k] or 0) for k in bins}
                    form=allocate_original_family_overlay(bins,d_bin,rules)
                    for family,totals in form['families'].items():
                        if totals['buildings']:
                            cells.append({'place_id':place,'original_period':period,
                              'original_family':family,**totals,
                              'evidence_class':'SOURCE_2021_BUILDING_BIN__INFERRED_FAMILY_DWELLINGS',
                              'ra_status':'NOT_IDENTIFIED','conditioned_area_m2':None,
                              'carrier_capability':'UNKNOWN_NOT_ZERO'})
                B=sum(x['buildings'] for x in cells if x['place_id']==place)
                D=sum(x['dwellings'] for x in cells if x['place_id']==place)
                if abs(B-observed['buildings'])>1e-5 or abs(D-observed['dwellings'])>1e-5:
                    raise ValueError('Panel system overlay broke place stock conservation')
                place_checks.append({'place_id':place,'observed_buildings':observed['buildings'],
                                     'observed_dwellings':observed['dwellings'],
                                     'model_buildings':B,'model_dwellings':D,
                                     'source_mass_balance':'PASS'})
            block={'id':scenario['id'],'original_family_cells':cells,'place_qa':place_checks,
                   'evidence_class':'SCENARIO_ORIGINAL_SYSTEM_MIX_NOT_2021_OBSERVED_SYSTEMS'}
            if 'national_component_reporting_marginals' in spec:
                rho=scenario.get('common_project_fraction')
                if rho is None:raise ValueError('Panel component association prior must be explicit')
                block['component_reporting_joint']=component_flag_joint(
                  spec['national_component_reporting_marginals'],rho)
            sidecar.append(block)
        p=out/'spatial_panel_archetype_calibration.json'
        p.write_text(json.dumps({'country':bundle['country'],
             'reference_year':spec['reference_year'],'source_ref':spec['source_ref'],
             'scenarios':sidecar,'status':'RESEARCH_ONLY_NOT_NEW_STOCK_OR_ENERGY',
             'stock_rule':'NONADDITIVE_PANEL_SYSTEM_OVERLAY__NO_2011_BACKDATING',
             'unidentified':['site_named_original_system','2021 RA thermal state',
                'actual conditioned area','local carriers','delivered renovation']},
             indent=2,allow_nan=False)+'\n')
        paths['spatial_panel_archetype_calibration']=p
    # Optional thermal sidecar over the EXISTING original-system overlay.
    # Calls the maintained archetype_physics.heat via renovation_reconciliation;
    # no second stock owner, equipment substitution, or renovation completion.
    if 'panel_ra_technical_screen' in bundle:
        from renovation_reconciliation import screen_panel_ra_service_and_packages
        physical_spec=bundle['panel_ra_technical_screen']
        if physical_spec.get('country')!=bundle['country']:
            raise ValueError('Panel RA sidecar country boundary disagrees')
        if not physical_spec.get('source_ref') or int(physical_spec['reference_year'])>=int(bundle['forecast_start'][:4]):
            raise ValueError('Panel RA must be a sourced preforecast physical research input')
        screen=screen_panel_ra_service_and_packages(physical_spec)
        p=out/'panel_ra_technical_screen.json'
        p.write_text(json.dumps(screen,indent=2,allow_nan=False)+'\n')
        paths['panel_ra_technical_screen']=p
    # Dated panel recipient request/preparation only. The nine governed
    # strategies and physical frontier sensitivities do not authorise a
    # completion in the cohort stock ledger, or a historic event assertion.
    if 'dated_panel_recipient_requests' in bundle:
        from renovation_reconciliation import prepare_dated_panel_delivery_requests
        spec=bundle['dated_panel_recipient_requests']
        if spec.get('country')!=bundle['country']:
            raise ValueError('Dated panel recipient country boundary disagrees')
        if int(spec['reference_year'])>=int(bundle['forecast_start'][:4]):
            raise ValueError('Dated panel reference must precede scenario forecast')
        dated=prepare_dated_panel_delivery_requests(spec)
        p=out/'dated_panel_recipient_requests.json'
        p.write_text(json.dumps(dated,indent=2,allow_nan=False)+'\n')
        paths['dated_panel_recipient_requests']=p
    manifest={'schema':'building-stock/2','version':'3.6-archetype-intake-checklist','country':bundle['country'],
      'history_start':bundle['history_start'],'forecast_start':bundle['forecast_start'],
      'input_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
      'research_opening_snapshot':bundle.get('research_opening_snapshot'),
      'energy_boundary':'MODELLED_USEFUL_SPACE_HEAT_SERVICE_PROXY_NO_KNOWN_CARRIER' if bundle.get('research_opening_snapshot') else 'EXISTING_COUNTRY_STAGE',
      'resolved_sha256':hashlib.sha256(paths['resolved_country_inputs'].read_bytes()).hexdigest(),
      'files':{k:str(v.relative_to(out)) for k,v in paths.items()},'runtime_promoted':False,
      'pas_newbuild_reallocation':{
          'enabled':any('pas_newbuild_reallocation' in r for r in results),
          'entry_point':'SHARED_COHORT_RUNTIME',
          'trajectory_input':'pas_newbuild_dwellings',
           'purpose_input':'construction_purpose',
           'timing_gate':'cancelled_start_date_not_start_year',
           'attribution':'same_pas_work_untouched_PI_newbuild_counterfactual'},
      'limitations':['No country is automatically calibrated by software tests',
      'Resources reserved in start year; multiyear work must be supplied as stages',
      'Recovery inventories do not automatically become certified usable supply',
      'Country/date standards registry requires nationally qualified rules and exceptions',
      'Heating is quasi-steady; annual event exposure uses duration weighting',
      'City tests remain separate; no automatic coefficient rewrite',
       'Explicit conditioned-area/surface semantics are optional and require evidence-bound priors',
       'Qualified balanced operating airflow or explicit bounded natural/extract pressure scenarios replace fixed ventilation; natural/extract prediction remains unvalidated',
       'Ventilation fan electricity is reported separately from space-heating carrier energy',
       'Cell-local signed adjacent-zone temperature boundaries are sourced alternatives, not a coupled multizone solver',
       'Spatial heating-source marginal calibration is a pre-forecast research sidecar only, not a measured local joint or heat-pump count',
       'Spatial panel archetype original-family and component-reporting joint is a nonadditive historical research sidecar, never current RA or delivered renovation',
       'Panel RA technical comparison uses explicit source-labeled U, geometry, weather, conditioned-area, and effective-renovation priors, never automatically calibrates 2024 heat or books 2025-2035 completion',
       'Dated panel recipient requests and annual throughput/capacity fronts are conditional preparations only; the existing cohort scheduler alone can commit dated physical events, and neither newbuilds nor city 2024 state are retrospectively measured']}
    p=out/'run_manifest.json';p.write_text(json.dumps(manifest,indent=2)+'\n');paths['manifest']=p
    return paths
