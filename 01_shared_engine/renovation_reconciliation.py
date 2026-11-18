"""Bounded sparse condition inference. Marginal observations do not identify a joint.
Raking preserves structural zeros in supplied priors; alternative priors remain explicit.
"""
from copy import deepcopy
from math import isfinite

def rake(priors,constraints,tolerance=1e-9,iterations=10000):
    """Iterative proportional fitting with reusable constrained-cell membership.

    Does not alter the semantic contract: source counts/marginals determine
    constraints; unsupported joint cells remain inferred model-prior values.
    """
    rows=deepcopy(priors)
    if not rows or any(not isfinite(r['share']) or r['share']<0 for r in rows):raise ValueError('Invalid prior')
    if sum(r['share'] for r in rows)<=0:raise ValueError('Zero prior mass')
    total=sum(r['share'] for r in rows)
    for r in rows:r['share']/=total
    targets=[{'selector':{},'share':1.}]+constraints
    for c in targets:
        if not 0<=c['share']<=1:raise ValueError('Invalid marginal')
    # The selector membership does not change during IPF. Caching it avoids
    # repeated dictionary scans for large PLACE x category reconstructions.
    members=[[i for i,r in enumerate(rows) if all(r['attributes'].get(k)==v
              for k,v in c['selector'].items())] for c in targets]
    for m,c in zip(members,targets):
        if not m and c['share']>0:raise ValueError('Marginal conflicts with structural zero')
    for iteration in range(iterations):
        for m,con in zip(members,targets):
            mass=sum(rows[i]['share'] for i in m)
            if mass==0 and con['share']>0:raise ValueError('Marginal conflicts with structural zero')
            if mass:
                factor=con['share']/mass
                for i in m:rows[i]['share']*=factor
        residual=max(abs(sum(rows[i]['share'] for i in m)-c['share'])
                     for m,c in zip(members,targets))
        if residual<tolerance:return {'rows':rows,'iterations':iteration+1,'max_residual':residual,'status':'INFERRED_JOINT_NOT_OBSERVED'}
    raise ValueError('Incompatible or nonconverging marginal constraints')

def allocate(parent,fit,library_mapping):
    """Each mapping identifies a complete component state; preserves all three quantities."""
    cells=[]
    for r in fit['rows']:
        if r['share']<=0:continue
        c=deepcopy(parent);c['id']=parent['id']+':'+r['id'];c['state']=deepcopy(library_mapping[r['id']])
        c['condition_status']='INFERRED_FROM_MARGINALS';c['condition_prior_id']=r['id']
        for key in ('area_m2','buildings','dwellings'):c[key]*=r['share']
        cells.append(c)
    return cells

def resolve_parameter(record):
    """Explicit centre selection; never midpoint a structural category or invent a bound."""
    if 'central' in record:return record['central']
    if record.get('centre_method')=='midpoint' and 'low' in record and 'high' in record:
        if record['low']>record['high']:raise ValueError('Reversed interval')
        return (record['low']+record['high'])/2
    raise ValueError('Central value or explicit centre method required')


def reconstruct_geographic_joint(national_joint, place_totals, place_marginals, *,
                                 geography_key='place_id', population_unit='dwellings',
                                 tolerance_counts=0.01, place_category_priors=None):
    """Infer a PLACE x category joint from compatible observed marginals.

    `national_joint`: rows {id, count, attributes}, where attributes specify
    mutually exclusive nationally *observed* categories (e.g. heating method
    x reported source). `place_totals`: {place_id: count} for the SAME census
    year, population, unit and boundary. `place_marginals`: [{place_id,
    selector: {category: value}, count}] observed local partial margins.

    Optional place_category_priors multiply positive starting weights for
    a known place and category selector. They are soft MODEL_PRIOR weights,
    not observations or constraints; raking still preserves the hard margins.
    Overlapping rules multiply and cannot add support to structural zeros.

    The initial independence structure is a MODEL_PRIOR. Reusing the same
    source margins in fitting and QA is NOT predictive validation. Unknown
    combinations stay inferred and HP equipment is never identified from a
    census 'electricity' or 'other' heating-source field.

    This calculates category shares/counts only. It does not construct
    buildings, fabricate neighbourhood geometry, assign physical component
    states or book heating/renovation completion events in building-stock/2.
    Spatial STOCK_CELL attribution remains the existing stock owner.
    """
    if not national_joint or not place_totals or population_unit not in ('dwellings','buildings','area_m2'):
        raise ValueError('An identified compatible population/unit is required')
    source_ids=[r['id'] for r in national_joint]
    if len(source_ids)!=len(set(source_ids)):
        raise ValueError('Duplicate national joint identities')
    categories=set(national_joint[0]['attributes'])
    if not categories or geography_key in categories or any(set(r['attributes'])!=categories for r in national_joint):
        raise ValueError('Joint categories are inconsistent with geographic key')
    if any(not isinstance(r['count'],(int,float)) or not isfinite(r['count']) or r['count']<0 for r in national_joint):
        raise ValueError('Invalid national joint observation count')
    if any(not isinstance(v,(int,float)) or not isfinite(v) or v<0 for v in place_totals.values()):
        raise ValueError('Invalid place population count')
    national=sum(r['count'] for r in national_joint)
    regional=sum(place_totals.values())
    if national<=0 or abs(national-regional)>tolerance_counts:
        raise ValueError('National joint and place populations disagree')
    # Every national category-state is observed; its sample frequency is not
    # yet an observed distribution within any individual place.
    seeded=[]
    for place,pop in place_totals.items():
        for r in national_joint:
            if r['count']>0 and pop>0:
                seeded.append({'id':str(place)+'::'+str(r['id']),
                               'share':(pop/national)*(r['count']/national),
                               'attributes':{geography_key:place,**r['attributes']}})
    if place_category_priors is not None:
        if not isinstance(place_category_priors,(list,tuple)):
            raise ValueError('Place category priors must be a sequence')
        for rule in place_category_priors:
            if not isinstance(rule,dict):
                raise ValueError('Invalid place category prior')
            place=rule.get('place_id')
            selector=rule.get('selector')
            multiplier=rule.get('multiplier')
            if not isinstance(place,str) or place not in place_totals:
                raise ValueError('Prior has an unrecognised place')
            if not isinstance(selector,dict) or not selector or not set(selector)<=categories:
                raise ValueError('Prior has an invalid category selector')
            if (isinstance(multiplier,bool) or not isinstance(multiplier,(int,float)) or
                    not isfinite(multiplier) or multiplier<=0):
                raise ValueError('Prior multiplier must be finite and positive')
            matching=[r for r in seeded if r['attributes'][geography_key]==place and
                      all(r['attributes'][k]==v for k,v in selector.items())]
            if not matching:
                raise ValueError('Prior selector has no positive stock support')
            for r in matching:
                value=r['share']*multiplier
                if not isfinite(value) or value<=0:
                    raise ValueError('Prior weight outside finite positive range')
                r['share']=value
    constraints=[]
    for place,pop in place_totals.items():
        constraints.append({'selector':{geography_key:place},'share':pop/national})
    for r in national_joint:
        if r['count']:
            constraints.append({'selector':dict(r['attributes']), 'share':r['count']/national})
    for record in place_marginals:
        place=record['place_id']
        if place not in place_totals or not record['selector'] or any(k not in categories for k in record['selector']):
            raise ValueError('Local marginal has an unrecognised place/category')
        count=record['count']
        if not isinstance(count,(int,float)) or not isfinite(count) or not 0<=count<=place_totals[place]:
            raise ValueError('Local marginal count outside its parent')
        constraints.append({'selector':{geography_key:place,**record['selector']}, 'share':count/national})
    fit=rake(seeded,constraints,tolerance=min(1e-11,tolerance_counts/national/2),iterations=10000)
    rows=[{**r,'estimated_count':r['share']*national,
           'evidence_class':'MODEL_PRIOR_CONSTRAINED_2021_JOINT_NOT_OBSERVED_LOCAL'} for r in fit['rows']]
    error=max(abs(sum(r['estimated_count'] for r in rows
                if all(r['attributes'].get(k)==v for k,v in c['selector'].items()))
                -c['share']*national) for c in constraints)
    if error>tolerance_counts:raise ValueError('Joint reconstruction failed counted marginal fit')
    return {'rows':rows,'national_population':national,'population_unit':population_unit,
            'geography_key':geography_key,'max_counted_marginal_error':error,
            'iterations':fit['iterations'], 'evidence_class':'MODEL_PRIOR_NOT_LOCAL_JOINT_OBSERVATION',
            'source_use':'IN_SAMPLE_MARGINAL_RECONCILIATION_NOT_INDEPENDENT_VALIDATION'}


def allocate_bounded_dwelling_bins(buildings_by_bin, dwelling_target, bin_bounds, prior_means,
                                   *, tolerance=1e-6):
    """Source-bounded estimate of dwellings by building-size bin for one PLACE.

    Only building-bin counts and the total dwelling count are OBSERVED.  The
    within-bin mean and age/bin joint are MODEL_PRIORS.  A shared log-odds
    tilt chooses means within each declared size interval and conserves the
    observed place dwelling total.  The 50+ upper bound MUST be supplied as
    a scenario assumption; it is not a census maximum.
    """
    from math import exp, log
    keys=list(buildings_by_bin)
    if set(bin_bounds)!=set(keys) or set(prior_means)!=set(keys):
        raise ValueError('Building-size bins, bounds and prior means must match')
    if not isinstance(dwelling_target,(int,float)) or not isfinite(dwelling_target) or dwelling_target<0:
        raise ValueError('Invalid dwelling target')
    if any(not isinstance(buildings_by_bin[k],(int,float)) or
           not isfinite(buildings_by_bin[k]) or buildings_by_bin[k]<0 for k in keys):
        raise ValueError('Invalid bin building count')
    if sum(buildings_by_bin.values())==0:
        if dwelling_target>tolerance:raise ValueError('Positive dwellings without buildings')
        return {'per_building':{k:None for k in keys},'dwelling_bins':{k:0. for k in keys},
                'residual':0.,'evidence_class':'MODEL_PRIOR_NOT_OBSERVED_BIN_DWELLINGS'}
    mn=mx=0.
    logits={}
    for k in keys:
        lo,hi=bin_bounds[k]
        p=prior_means[k]
        if any(not isinstance(v,(int,float)) or not isfinite(v) for v in (lo,hi,p)) or lo<0 or hi<lo or not lo<=p<=hi:
            raise ValueError('Invalid bin bounds/prior')
        n=buildings_by_bin[k]
        mn+=n*lo;mx+=n*hi
        if hi>lo:
            fraction=max(1e-12,min(1-1e-12,(p-lo)/(hi-lo)))
            logits[k]=log(fraction/(1-fraction))
    if dwelling_target<mn-tolerance or dwelling_target>mx+tolerance:
        raise ValueError('Observed dwelling total outside declared bin ranges')
    def conditioned(shift):
        result={}
        for k in keys:
            lo,hi=bin_bounds[k]
            if hi==lo:result[k]=lo
            else:
                x=logits[k]+shift
                prob=1/(1+exp(-x)) if x>=0 else exp(x)/(1+exp(x))
                result[k]=lo+(hi-lo)*prob
        return result
    a,b=-90.,90.
    for _ in range(90):
        mid=(a+b)/2;values=conditioned(mid)
        if sum(values[k]*buildings_by_bin[k] for k in keys)<dwelling_target:a=mid
        else:b=mid
    per=conditioned((a+b)/2)
    allocated={k:buildings_by_bin[k]*per[k] for k in keys}
    residual=sum(allocated.values())-dwelling_target
    if abs(residual)>tolerance:raise ValueError('Bin projection did not conserve observed dwellings')
    return {'per_building':per,'dwelling_bins':allocated,'residual':residual,
            'source_bound':'PLACE_TOTAL_OBSERVED_BIN_DWELLINGS_INFERRED',
            'evidence_class':'MODEL_PRIOR_NOT_OBSERVED_BIN_DWELLINGS'}


def allocate_original_family_overlay(cohort_bins, estimated_dwellings_by_bin,
                                     conditional_weights, *, tolerance=1e-6):
    """Nonadditive original-system overlay, never a second population.

    Inputs share the same PLACE x original-construction-period x bin frame.
    For each source bin, `conditional_weights` gives the explicit research
    probability of one mutually exclusive original system family. This does
    NOT identify a named panel at an address, a current U-value or RA state.
    """
    if set(cohort_bins)!=set(estimated_dwellings_by_bin) or set(cohort_bins)!=set(conditional_weights):
        raise ValueError('Incompatible family-overlay size bins')
    output={};known={}
    for b,n in cohort_bins.items():
        dw=estimated_dwellings_by_bin[b]
        if not isinstance(n,(int,float)) or n<0 or not isfinite(n) or not isinstance(dw,(int,float)) or dw<0 or not isfinite(dw):
            raise ValueError('Negative/invalid source/estimated stock')
        if n<=0 and dw>tolerance:raise ValueError('Inferred dwellings in empty source bin')
        weights=conditional_weights[b]
        if not weights or any(not isinstance(v,(int,float)) or not isfinite(v) or v<0 for v in weights.values()):
            raise ValueError('Invalid original family mixture')
        if abs(sum(weights.values())-1)>tolerance:raise ValueError('Non-conserving original family mixture')
        for family,w in weights.items():
            x=output.setdefault(family,{'buildings':0.,'dwellings':0.})
            x['buildings']+=n*w;x['dwellings']+=dw*w
    if abs(sum(v['buildings'] for v in output.values())-sum(cohort_bins.values()))>tolerance:
        raise ValueError('Building overlay does not conserve its source population')
    if abs(sum(v['dwellings'] for v in output.values())-sum(estimated_dwellings_by_bin.values()))>tolerance:
        raise ValueError('Dwelling overlay does not conserve its source population')
    return {'families':output,'evidence_class':'CONDITIONAL_ORIGINAL_FAMILY_NOT_ASBUILT',
            'stock_rule':'NONADDITIVE_ONE_SOURCE_BUILDING_POPULATION',
            'ra_status':'UNIDENTIFIED_INDEPENDENT_CURRENT_THERMAL_STATE'}


def component_flag_joint(observed_national_marginals, common_project_fraction):
    """Eight component *reporting flag* probabilities from compatible marginals.

    Convex mixture of independent occurrence and a comonotonic latent project.
    It is a scenario for the unknown joint, NOT measured local renovation,
    effective component U, RA I/II/III, deep-renovated area or delivered work.
    """
    if not isinstance(common_project_fraction,(int,float)) or not 0<=common_project_fraction<=1:
        raise ValueError('Invalid joint association scenario')
    keys=('facade','roof','windows')
    if set(observed_national_marginals)!=set(keys) or any(
            not isinstance(observed_national_marginals[k],(int,float)) or
            not isfinite(observed_national_marginals[k]) or
            not 0<=observed_national_marginals[k]<=1 for k in keys):
        raise ValueError('Exactly three compatible observed component marginal rates required')
    states=[]
    for n in range(8):
        flags={k:bool(n&(1<<i)) for i,k in enumerate(keys)}
        indep=1.;lower=0.;upper=1.
        for k in keys:
            p=observed_national_marginals[k]
            indep*=p if flags[k] else 1-p
            if flags[k]:upper=min(upper,p)
            else:lower=max(lower,p)
        common=max(0.,upper-lower)
        prob=(1-common_project_fraction)*indep+common_project_fraction*common
        states.append({'flags':flags,'share':prob})
    if abs(sum(s['share'] for s in states)-1)>1e-10:raise ValueError('Component joint normalization failed')
    for k in keys:
        implied=sum(s['share'] for s in states if s['flags'][k])
        if abs(implied-observed_national_marginals[k])>1e-10:raise ValueError('Component marginal not conserved')
    return {'rows':states,'evidence_class':'MODEL_PRIOR_JOINT_OF_REPORTED_COMPONENT_WORK',
            'ra_status':'RA_NOT_IDENTIFIABLE_FROM_COMPONENT_FLAGS',
            'scope':'NATIONAL_AP_BUILDING_REPORTING_RATES_NOT_LOCAL_PROVENANCE'}


def screen_panel_ra_service_and_packages(spec):
    """Source-qualified MFH original-family × effective-component response sidecar.

    Reuses archetype_physics.heat, not an alternative heat solver or a stock
    scheduler. Reported census component work is converted to *possible*
    effective envelope changes with declared probabilities; technical RA
    classes depend on same-service computed useful heat, never on a reported
    three-component flag alone. One common priority recipient set is used
    for the PI/PAS/HDE package comparison. All outputs are research estimates.
    """
    from itertools import product
    from archetype_physics import heat
    from math import isfinite
    required=('source_ref','country','reference_year','stock','profiles','weather',
              'reporting_marginals','reporting_common_fraction','effective_given_reported',
              'effective_without_report','floor_after_three_effective',
              'pathway_packages','treatment_fraction_of_panel_area','area_source_ref')
    if any(k not in spec for k in required):
        raise ValueError('Panel RA physical screen missing source-qualified input')
    if not spec['source_ref'] or not spec['area_source_ref']:
        raise ValueError('Panel RA stock and conditioned-area assumptions require explicit provenance')
    if spec['reference_year']<2011 or spec['reference_year']>2024:
        raise ValueError('Panel RA screen does not rewrite 2011 opening or future stock')
    names=('facade','roof','windows')
    for k in names:
        for kk in ('effective_given_reported','effective_without_report'):
            v=spec[kk][k]
            if isinstance(v,bool) or not isinstance(v,(int,float)) or not isfinite(v) or not 0<=v<=1:
                raise ValueError('Invalid effective component probability')
    floorp=spec['floor_after_three_effective']
    if isinstance(floorp,bool) or not isinstance(floorp,(int,float)) or not 0<=floorp<=1:
        raise ValueError('Invalid prior for floor/thermal-junction package')
    fr=spec['treatment_fraction_of_panel_area']
    if not isinstance(fr,(int,float)) or not 0<fr<=1:
        raise ValueError('Invalid explicit recipient treatment fraction')
    if set(spec['pathway_packages'])!={'PI','PAS','HDE'}:
        raise ValueError('Exactly the governed PI/PAS/HDE comparator profiles required')
    joint=component_flag_joint(spec['reporting_marginals'],spec['reporting_common_fraction'])
    weather=spec['weather']
    if not weather or not all('id' in x and 'hours' in x for x in weather):
        raise ValueError('Source-prior weather/service must be explicitly specified')
    family_output=[];recipient_states=[];area_sum=0.;b_sum=0.;dw_sum=0.
    for item in spec['stock']:
        fam=item['family'];base=spec['profiles'][fam]
        for k in ('buildings','dwellings','conditioned_area_m2'):
            v=item[k]
            if isinstance(v,bool) or not isinstance(v,(int,float)) or not isfinite(v) or v<0:
                raise ValueError('Invalid family stock area/count')
        if not base.get('source_ref') or set(base['geometry'])!=set(('wall','roof','window','floor')):
            raise ValueError('Original family geometry/source is not identified')
        if set(base['reference_u'])!=set(('wall','roof','window','floor')) or set(base['effective_u'])!=set(('wall','roof','window','floor')):
            raise ValueError('Original/effective component thermal planes not complete')
        if not base.get('original_period') or base['ventilation_w_k_m2']<0 or base['bridges_w_k_m2']<0:
            raise ValueError('Service/age/airflow information missing')
        for k in base['reference_u']:
            if base['effective_u'][k]<=0 or base['reference_u'][k]<=0 or base['effective_u'][k]>base['reference_u'][k]:
                raise ValueError('Effective component would worsen or invalidate source state')
        a={'source_ref':base['source_ref'],'construction_period':base['original_period'],
           'geometry':base['geometry'],'ventilation_w_k_m2':base['ventilation_w_k_m2'],
           'bridges_w_k_m2':base['bridges_w_k_m2'],
           'components':{k:{'source':{'u_w_m2k':base['reference_u'][k], 'source_ref':base['source_ref']}}
                for k in base['reference_u']}}
        library={'archetypes':{fam:a}}
        def thermal(current_u):
            for k in current_u:
                a['components'][k]['active']={'u_w_m2k':current_u[k],
                    'source_ref':base['source_ref']+'__EXPLICIT_PHYSICAL_SCENARIO'}
            c={'id':fam+'_SERVICE_SCREEN','country':spec['country'],'place_id':'SK_KE_CITY_2021_RESEARCH',
               'archetype_id':fam,'construction_period':base['original_period'],
               'area_m2':1.,'buildings':1.,'dwellings':1.,'state':{k:'active' for k in current_u},
               'heating':{'carrier':'DISTRICT_HEAT_UTILITY_SCREEN','useful_per_final':1},
               'source_ref':base['source_ref'],'service_indoor_c':spec.get('service_indoor_c',20)}
            r=heat(c,library,weather)
            return r['useful_heat_kwh'],r['h_w_k']
        original,original_h=thermal(base['reference_u'])
        states=[];sum_weights=0.;expected=0.;rais={'RA_I':0.,'RA_II':0.,'RA_III_TECHNICAL_CANDIDATE':0.}
        for report in joint['rows']:
            pp=[(spec['effective_given_reported'] if report['flags'][k] else spec['effective_without_report'])[k] for k in names]
            for mask in product((0,1),repeat=3):
                w=report['share']
                for j,x in enumerate(mask):w*=pp[j] if x else (1-pp[j])
                if w<=1e-15:continue
                fb=floorp if all(mask) else 0.
                for fl in (0,1):
                    aweight=w*(fb if fl else 1-fb)
                    if aweight<=1e-15:continue
                    improved={('wall','roof','window')[j] for j,v in enumerate(mask) if v}
                    if fl:improved.add('floor')
                    thermal_u={k:(base['effective_u'][k] if k in improved else base['reference_u'][k])
                               for k in base['reference_u']}
                    q,h=thermal(thermal_u)
                    if q>original+1e-8:raise ValueError('Current effective state increases reference useful heating')
                    saving=1-q/original if original>1e-12 else 0
                    if q<=70 and any(mask):ra='RA_III_TECHNICAL_CANDIDATE'
                    elif saving>=.25:ra='RA_II'
                    else:ra='RA_I'
                    rais[ra]+=aweight;expected+=aweight*q;sum_weights+=aweight
                    states.append({'family':fam,'weight':aweight,'ra_technical':ra,
                        'q_kwh_m2a':q,'h_w_k_m2':h,'u_current':thermal_u,
                        'source_state':'INFERRED_EFFECTIVE_COMPONENTS_NOT_SODB_RA',
                        'conditioned_area_m2':item['conditioned_area_m2']*aweight,
                        'buildings':item['buildings']*aweight,'dwellings':item['dwellings']*aweight})
        if abs(sum_weights-1)>1e-8:raise ValueError('Component reporting/effective states not conserved')
        if abs(sum(rais.values())-1)>1e-8:raise ValueError('Physical RA candidate states not conserved')
        area_sum+=item['conditioned_area_m2'];b_sum+=item['buildings'];dw_sum+=item['dwellings']
        family_output.append({'family':fam,'buildings':item['buildings'],
            'dwellings':item['dwellings'],'conditioned_area_m2':item['conditioned_area_m2'],
            'reference_q_kwh_m2a':original,'expected_current_q_kwh_m2a':expected,
            'ra_technical_probabilities':rais,'source_ref':base['source_ref']})
        recipient_states.extend(states)
    # Select the same ready-to-improve recipients for each pathway. This is
    # a demand-normalised COMPATIBILITY test, never an endogenous annual forecast.
    panel_area=area_sum
    recipient_need=fr*panel_area;remaining=recipient_need;selected=[]
    for row in sorted(recipient_states,key=lambda r:(r['ra_technical']=='RA_III_TECHNICAL_CANDIDATE',-r['q_kwh_m2a'])):
        if remaining<1e-8:break
        if row['ra_technical']=='RA_III_TECHNICAL_CANDIDATE':continue
        a=min(remaining,row['conditioned_area_m2'])
        if a>0:selected.append((row,a));remaining-=a
    if remaining>1e-4:raise ValueError('Insufficient technically deficient recipient area for requested treatment share')
    output={}
    for path,package in spec['pathway_packages'].items():
        if not package.get('source_ref') or set(package['target_u'])-set(('wall','roof','window','floor')):
            raise ValueError('Pathway package needs physical source and valid target components')
        work={'facade_m2':0.,'roof_m2':0.,'windows_m2':0.,'floor_m2':0.,
              'additional_eps_kg_equivalent':0.,'additional_roof_mw_kg_equivalent':0.}
        q_before=q_after=peak_saved_w=0.;addressed_buildings=0.
        for r,a_sel in selected:
            fam=r['family'];base=spec['profiles'][fam];old=r['u_current'];new=dict(old)
            for k,v in package['target_u'].items():
                if not isinstance(v,(int,float)) or v<=0:
                    raise ValueError('Invalid pathway physical target U')
                new[k]=min(old[k],v)
            arch={'source_ref':base['source_ref'],'construction_period':base['original_period'],
                  'geometry':base['geometry'],'ventilation_w_k_m2':base['ventilation_w_k_m2'],
                  'bridges_w_k_m2':base['bridges_w_k_m2'],
                  'components':{k:{'screen':{'u_w_m2k':v,'source_ref':package['source_ref']}}
                                for k,v in new.items()}}
            obj={'id':'PACKAGE_'+path,'country':spec['country'],'place_id':'SK_KE_CITY_2021_RESEARCH',
                 'archetype_id':fam,'area_m2':1.,'buildings':1.,'dwellings':1.,
                 'construction_period':base['original_period'],
                 'state':{k:'screen' for k in new},
                 'heating':{'carrier':'DISTRICT_HEAT_UTILITY_SCREEN','useful_per_final':1},
                 'service_indoor_c':spec.get('service_indoor_c',20)}
            rr=heat(obj,{'archetypes':{fam:arch}},weather)
            q_before+=r['q_kwh_m2a']*a_sel;q_after+=rr['useful_heat_kwh']*a_sel
            peak_saved_w+=max(0,r['h_w_k_m2']-rr['h_w_k'])*a_sel*spec.get('design_delta_k',32)
            addressed_buildings+=r['buildings']*a_sel/r['conditioned_area_m2']
            for k,field in [('wall','facade_m2'),('roof','roof_m2'),('window','windows_m2'),('floor','floor_m2')]:
                if new[k]<old[k]-1e-12:
                    work[field]+=a_sel*base['geometry'][k]
                    # Additional-equivalent insulation is not a complete bill
                    # of materials. Original EPS is NOT charged a second time.
                    add_r=1/new[k]-1/old[k]
                    if k=='wall':work['additional_eps_kg_equivalent']+=a_sel*base['geometry'][k]*add_r*.036*16
                    if k=='roof':work['additional_roof_mw_kg_equivalent']+=a_sel*base['geometry'][k]*add_r*.04*45
        if q_after>q_before+1e-6:raise ValueError('Renovation makes same-service useful heat larger')
        output[path]={'requested_qualified_area_m2':recipient_need,
          'treatment_basis':'COMMON_TECHNICAL_RECIPIENT_AREA_NOT_ANNUAL_ADOPTION_FORECAST',
          'expected_affected_buildings':addressed_buildings,
          'useful_heat_before_kwh_a':q_before,'useful_heat_after_kwh_a':q_after,
          'useful_heat_savings_kwh_a':q_before-q_after,
          'savings_fraction_same_service':(q_before-q_after)/q_before if q_before else 0,
          'screen_peak_space_heat_reduction_kw':peak_saved_w/1000,
          'material_and_component_work':work,
          'unidentified_delivery':['productive_trade_hours','workforce_and_competence',
             'QA_and_commissioning_time','roof_and_facade_access','existing_layers_and_demolition',
             'actual_named_carrier_capacity','workforce_competing_commitments'],
          'finance_gate':'NOT_APPLICABLE_PAS_HDE_PRIORITY_RENOVATION' if path in ('PAS','HDE') else 'PI_SEPARATE_FINANCE_OWNER',
          'equipment_heat_and_DHW':'NOT_INCLUDED_DIFFERENT_NUMERICAL_OWNER',
          'package_source_ref':package['source_ref']}
    return {'schema':'panel-archetype-ra/1','country':spec['country'],'reference_year':spec['reference_year'],
       'source_ref':spec['source_ref'],'area_source_ref':spec['area_source_ref'],
       'population':{'buildings':b_sum,'dwellings':dw_sum,'conditional_conditioned_area_m2':area_sum},
       'reporting_joint':joint,'ra_groups':family_output,'component_passports_2021':_conserve_component_passports(recipient_states,spec),'package_comparison':output,
       'model_qualification':'RA_TECHNICAL_CANDIDATES_NOT_OBSERVED_CURRENT_STATE_OR_HEAT',
       'source_validation':'SOURCE_FITTED_2021_STOCK_ONLY; PHYSICAL_STUDIES_EXTERNAL_PLAUSIBILITY_NOT_KOSICE_CALIBRATION',
       'non_additivity':'2021_SPACE_HEAT_REFERENCE_IS_SEPARATE_FROM_2011_OPENING_AND_2024_NATIONAL_CALIBRATION',
       'unidentified':['actual_2024_conditioned_area','actual_2024_RAs','current_local_thermal_bridges',
                       'actual_2021_equipment_and_energy','local_delivery_actor_capacities','safe_ventilation_IAQ']}


def _conserve_component_passports(recipient_states,spec):
    """Keep the recurrent 2021 component combinations, rather than RA-mean U.

    Names RA I/II/III are provisional stock *descriptors* only. The true
    physical state is the four-component passport, and a future renovation
    endpoint is a separate operation. Marginal census flags do not identify
    the real joint distribution; all rows remain conditional model priors.
    """
    out={}
    for r in recipient_states:
        family=r['family'];profile=spec['profiles'][family]
        bits=''.join('1' if abs(r['u_current'][part]-profile['effective_u'][part])<1e-10 else '0'
                     for part in ('wall','roof','window','floor'))
        bucket=out.setdefault(family,{})
        x=bucket.setdefault(bits,{'mask':bits,'share':0.,'u_current':dict(r['u_current']),
             'ra_stock_proxy':r['ra_technical'],'q_kwh_m2a':r['q_kwh_m2a'],
             'evidence_class':'SODB2021_NATIONAL_COMPONENT_MARGINALS__INFERRED_JOINT_NOT_ASBUILT'})
        if any(abs(x['u_current'][k]-r['u_current'][k])>1e-10 for k in x['u_current']):
            raise ValueError('Ambiguous physical passport encoding')
        x['share']+=r['weight']
    for family,groups in out.items():
        total=sum(x['share'] for x in groups.values())
        if abs(total-1)>1e-8:raise ValueError('Component passport population fails conservation')
    return {k:[v for _,v in sorted(groups.items())] for k,groups in out.items()}


def prepare_component_dated_panel_state(spec, dated=None):
    """Source-conditioned 2021 -> 2024 component-preserving survivor bridge.

    Uses the existing dated parent population and its annual survival factors.
    One component upgrade per exposure event is a visible 2022-24 MODEL prior;
    no observed Košice completion is asserted. RA labels are *derived* as
    diagnostic candidates from component physics; they are never target U.
    """
    from archetype_physics import heat
    from collections import defaultdict
    from math import isfinite
    dated=dated if dated is not None else prepare_dated_panel_delivery_requests(spec)
    profiles=spec.get('component_physical_profiles')
    passports=spec.get('component_passports_2021')
    if not isinstance(profiles,dict) or not isinstance(passports,dict):
        raise ValueError('Dated component bridge requires original/effective physical passports')
    components=('wall','roof','window','floor')
    weather=spec.get('component_weather')
    if not weather:raise ValueError('Component passport weather/service not defined')
    def mask_u(p,mask):
        return {k:(p['effective_u'][k] if mask[i]=='1' else p['reference_u'][k])
                for i,k in enumerate(components)}
    heat_cache={}
    def q(fam,mask):
        if (fam,mask) in heat_cache:return heat_cache[(fam,mask)]
        p=profiles[fam];u=mask_u(p,mask)
        lib={'archetypes':{fam:{'source_ref':p['source_ref'],'construction_period':p['original_period'],
             'geometry':p['geometry'],'ventilation_w_k_m2':p['ventilation_w_k_m2'],
             'bridges_w_k_m2':p['bridges_w_k_m2'],
             'components':{k:{'active':{'u_w_m2k':v,'source_ref':p['source_ref']}} for k,v in u.items()}}}}
        cell={'id':'SOURCE_CONDITIONAL_2024_COMPONENT_PASSPORT','country':'SK','place_id':'KE_CITY',
              'archetype_id':fam,'construction_period':p['original_period'],'area_m2':1,
              'buildings':1,'dwellings':1,'state':{k:'active' for k in components},
              'heating':{'carrier':'UNKNOWN_HEATING_CARRIER_SERVICE_PROXY','useful_per_final':1}}
        result=heat(cell,lib,weather)['useful_heat_kwh']
        heat_cache[(fam,mask)]=result
        return result
    hazard=(spec['historical_apartment_renovation_exposure_rate']*
            spec['technical_progression_given_exposure'])
    if not isinstance(hazard,(int,float)) or not isfinite(hazard) or not 0<=hazard<=1:
        raise ValueError('Invalid component progression hazard')
    annual_stocks={};source_energy=survivor_2021_energy=energy2024=0.;all_rows=[]
    for fam,profiles_rows in passports.items():
        p=profiles[fam]
        if set(p['reference_u'])!=set(components) or set(p['effective_u'])!=set(components):
            raise ValueError('Physical family missing relevant component')
        state={v['mask']:float(v['share']) for v in profiles_rows}
        if any(len(m)!=4 or any(b not in '01' for b in m) or w<0 for m,w in state.items()) or abs(sum(state.values())-1)>1e-8:
            raise ValueError('Invalid source component passport shares')
        original_q=q(fam,'0000')
        prior_q=sum(q(fam,m)*w for m,w in state.items())
        annual_stocks[fam]={'2021_mean_q_kwh_m2a':prior_q,'2021_original_q_kwh_m2a':original_q}
        for _ in range(2022,2025):
            next_state=defaultdict(float)
            for mask,w in state.items():
                possible=[]
                for i,k in enumerate(components[:3]):
                    if mask[i]=='0' and p['reference_u'][k]>p['effective_u'][k]+1e-10:
                        possible.append((p['geometry'][k]*(p['reference_u'][k]-p['effective_u'][k]),i))
                if not possible:
                    next_state[mask]+=w;continue
                # Largest thermal-marginal component is a declared prototype
                # progression PRIOR, not an inferred historic project order.
                i=max(possible)[1];newmask=mask[:i]+'1'+mask[i+1:]
                next_state[mask]+=w*(1-hazard)
                next_state[newmask]+=w*hazard
            state=dict(next_state)
        if abs(sum(state.values())-1)>1e-8:raise ValueError('Passport transitions not normalized')
        annual_stocks[fam]['2024_mean_q_kwh_m2a']=sum(q(fam,m)*w for m,w in state.items())
        annual_stocks[fam]['2024_mean_worse_than_2021']=annual_stocks[fam]['2024_mean_q_kwh_m2a']>prior_q+1e-8
        if annual_stocks[fam]['2024_mean_worse_than_2021']:raise ValueError('Component progression increases service heat')
        for place in dated['place_family_2024_priors']:
            if place['family']!=fam:continue
            area=place['2024_conditional_conditioned_area_m2'];source_energy+=area*prior_q
            for mask,w in sorted(state.items()):
                if w<=1e-15:continue
                actual_q=q(fam,mask);u=mask_u(p,mask)
                # Only an EXPLORATORY stock-state proxy, not the definition
                # of RA I/II/III and not an endpoint target.
                savings=1-actual_q/original_q if original_q else 0
                proxy=('RA_III_TECHNICAL_CANDIDATE' if actual_q<=70 and mask!='0000' else
                       'RA_II' if savings>=.25 else 'RA_I')
                all_rows.append({'place_id':place['place_id'],'family':fam,'mask':mask,
                    'share_within_family':w,'area_m2':area*w,
                    'buildings':place['2024_conditional_survivor_buildings']*w,
                    'dwellings':place['2024_conditional_survivor_dwellings']*w,
                    'u_current':u,'q_kwh_m2a':actual_q,'ra_stock_proxy':proxy,
                    'eligible_pi':any(u[k]>v+1e-10 for k,v in {'wall':.30,'roof':.20,'window':1.30}.items()),
                    'eligible_deep':any(u[k]>v+1e-10 for k,v in {'wall':.16,'roof':.12,'window':.90}.items()),
                    'evidence_class':'2024_SOURCE_CONDITIONAL_COMPONENT_PASSPORT_NOT_OBSERVED'})
                energy2024+=area*w*actual_q
    bsum=sum(x['buildings'] for x in all_rows);dsum=sum(x['dwellings'] for x in all_rows);asum=sum(x['area_m2'] for x in all_rows)
    s=dated['survival']
    if any(abs(actual-s[key])>1e-4 for actual,key in [(bsum,'survivor_buildings'),(dsum,'survivor_dwellings'),(asum,'survivor_conditioned_area_m2')]):
        raise ValueError('Detailed passports violate 2024 parent stock conservation')
    if energy2024>source_energy+1e-6:raise ValueError('Dated component transition increased heat')
    if len(all_rows)>2000:raise ValueError('Unbounded detailed passport cross-product')
    return {**dated,'schema':'panel-dated-component-state/2',
      'place_family_2024_component_priors':all_rows,
      'component_energy':{'2021_component_legacy_weather_same_survivor_gwh':source_energy/1e6,
        '2024_component_physics_gwh':energy2024/1e6,
        '2022_2024_modelled_change_gwh':(energy2024-source_energy)/1e6,
        'note':'Same surviving area comparison; true 2021 source area includes attrition and differs',
        'per_family':annual_stocks},
      'component_state_contract':'2021_PHYSICAL_MASKS_SURVIVE_DATED_TRANSITIONS; RA_LABELS_DIAGNOSTIC_ONLY',
      'no_new_stock':True,
      'progression_stage':'EXPLICIT_ONE_COMPONENT_PER_EXPOSURE_PRIOR_NOT_2022_24_OBSERVED_PROJECTS'}


def prepare_dated_panel_delivery_requests(spec):
    """Dated, non-booking 2021->2024 panel survivor / 2025->2035 delivery handoff.

    PREPARES scenario request/physical-frontier tables for the maintained cohort
    executor. It does NOT create committed renovation events, a new stock owner,
    a delivery multiplier, or a retrospective measured Košice RA population.

    Observed local 2021 apartment-building/dwelling counts are immutable parents.
    2022--24 attrition is an explicitly transferred national ALL-dwelling proxy;
    national older renovation throughput is an exposure prior, not a completed
    2022--24 unique-house renovation observation. Technical RA probabilities are
    conditional engineering states, never achieved RA certification.
    """
    req=('country','source_ref','reference_year','forecast_start_year','forecast_end_year',
         'family_stock','place_family_dwellings','annual_all_dwelling_withdrawal_proxies',
         'historical_apartment_renovation_exposure_rate','technical_progression_given_exposure',
         'strategy_demands','capacity_frontiers','historical_throughput_source_ref',
         'attrition_source_ref','ra_physics_source_ref')
    if any(k not in spec for k in req):
        raise ValueError('Dated panel bridge requires source-qualified stock, historical priors, strategies and frontiers')
    if spec['country']!='SK' or spec['reference_year']!=2021 or spec['forecast_start_year']!=2025:
        raise ValueError('Dated panel bridge currently qualifies only SK 2021 to 2025 reference')
    if not 2025<=spec['forecast_end_year']<=2050 or any(not spec[k] for k in ('source_ref','historical_throughput_source_ref','attrition_source_ref','ra_physics_source_ref')):
        raise ValueError('Missing qualified period or provenance')
    from math import isfinite
    def rate(x):
        if isinstance(x,bool) or not isinstance(x,(int,float)) or not isfinite(x) or not 0<=x<=1:
            raise ValueError('Invalid prior rate or population share')
        return float(x)
    rate(spec['historical_apartment_renovation_exposure_rate'])
    rate(spec['technical_progression_given_exposure'])
    if set(map(str,spec['annual_all_dwelling_withdrawal_proxies']))!=set(('2022','2023','2024')):
        raise ValueError('Need exact preforecast 2022, 2023 and 2024 survival proxies')
    survival=1.
    year_factors=[]
    for y in range(2022,2025):
        z=rate(spec['annual_all_dwelling_withdrawal_proxies'][str(y)])
        survival*=1-z
        year_factors.append({'year':y,'national_all_dwelling_withdrawal_rate_proxy':z,
                             'remaining_2021_cohort_share':survival})
    rs=('RA_I','RA_II','RA_III_TECHNICAL_CANDIDATE')
    family={};baseline_area=0.;baseline_dw=0.;baseline_building=0.
    for f in spec['family_stock']:
        k=f['family']
        if k in family or set(f['ra_technical_probabilities'])!=set(rs):
            raise ValueError('Duplicate family or incomplete technical RA state')
        for v in (f['buildings'],f['dwellings'],f['conditioned_area_m2']):
            if isinstance(v,bool) or not isinstance(v,(int,float)) or not isfinite(v) or v<0:
                raise ValueError('Invalid source family stock')
        p=f['ra_technical_probabilities']
        if any(rate(x)<0 for x in p.values()) or abs(sum(p.values())-1)>1e-7:
            raise ValueError('Technical RA probabilities not conserved')
        family[k]=f;baseline_area+=f['conditioned_area_m2']
        baseline_dw+=f['dwellings'];baseline_building+=f['buildings']
    if not family or baseline_area<=0:raise ValueError('Empty baseline panel cohort')
    places={};d_by_family={k:0. for k in family}
    for item in spec['place_family_dwellings']:
        k=item['family'];place=item['place_id'];v=item['dwellings']
        if k not in family or not place or not isinstance(v,(int,float)) or not isfinite(v) or v<0:
            raise ValueError('Invalid district x original-family source joint')
        pair=(place,k)
        if pair in places:raise ValueError('Duplicate place-family joint')
        places[pair]=float(v);d_by_family[k]+=v
    if not places or any(abs(d_by_family[k]-f['dwellings'])>1e-3 for k,f in family.items()):
        raise ValueError('District original-family distribution does not conserve source family dwellings')
    hazard=rate(spec['historical_apartment_renovation_exposure_rate'])*rate(spec['technical_progression_given_exposure'])
    current=[]
    totals={r:0. for r in rs};b2024=d2024=a2024=0.
    for (place,k),dw in sorted(places.items()):
        f=family[k];ratio=dw/f['dwellings'] if f['dwellings'] else 0.
        a=f['conditioned_area_m2']*ratio*survival;b=f['buildings']*ratio*survival;d=dw*survival
        p=dict(f['ra_technical_probabilities'])
        for y in range(2022,2025):
            moved_I=p['RA_I']*hazard;moved_II=p['RA_II']*hazard
            p={'RA_I':p['RA_I']-moved_I,
               'RA_II':p['RA_II']+moved_I-moved_II,
               'RA_III_TECHNICAL_CANDIDATE':p['RA_III_TECHNICAL_CANDIDATE']+moved_II}
        if min(p.values())<-1e-12 or abs(sum(p.values())-1)>1e-9:
            raise ValueError('Technical RA transition violates state conservation')
        for label in rs:totals[label]+=a*p[label]
        b2024+=b;d2024+=d;a2024+=a
        current.append({'place_id':place,'family':k,'2021_source_dwellings':dw,
                        '2024_conditional_survivor_buildings':b,
                        '2024_conditional_survivor_dwellings':d,
                        '2024_conditional_conditioned_area_m2':a,
                        '2024_technical_ra_area_share':p,
                        '2024_eligible_not_good_area_m2':a*(p['RA_I']+p['RA_II']),
                        'evidence_class':'HISTORICAL_EXPOSURE_SURVIVOR_MODEL_NOT_OBSERVED_2024_SITE'})
    if abs(sum(totals.values())-a2024)>1e-4:
        raise ValueError('Spatial RA technical areas do not conserve 2024 survivor area')
    full={
        'PI_CONVENTIONAL':('PI','PI_SOURCE_NEUTRAL','CONVENTIONAL_CONTINUATION'),
        'PI_INDUSTRIALISATION':('PI','PI_SOURCE_NEUTRAL','GRADUAL_INDUSTRIALISATION'),
        'PI_EXEMPLAR':('PI','PI_SOURCE_NEUTRAL','SELECTIVE_EXEMPLAR_DIFFUSION'),
        'PAS_DEEP':('PAS','PAS_DEEP','DEEP_PERFORMANCE_PRODUCTISED'),
        'PAS_RETENTION':('PAS','PAS_RETENTION','RETENTION_FIRST_TRANSFORMATION'),
        'PAS_ADAPTIVE':('PAS','PAS_ADAPTIVE','ADAPTIVE_REUSE_ADDITIVE_DENSITY'),
        'HDE_ELECTRIFICATION':('HDE','HDE_ELECTRIFICATION','ELECTRIFICATION_FIRST'),
        'HDE_INDUSTRIAL':('HDE','HDE_INDUSTRIAL','INDUSTRIAL_HIGH_THROUGHPUT'),
        'HDE_REDEVELOPMENT':('HDE','HDE_REDEVELOP','REDEVELOPMENT_ADDITION')}
    if set(spec['strategy_demands'])!=set(full):
        raise ValueError('Exactly nine governed strategy-specific annual demand rates required')
    capacities={}
    for name,value in spec['capacity_frontiers'].items():capacities[name]=rate(value)
    if not capacities:raise ValueError('Provide at least one conditional capacity frontier')
    requests=[];frontier=[]
    eligible=sum(r['2024_eligible_not_good_area_m2'] for r in current)
    for strategy,(path,policy,physical_strategy) in full.items():
        demand=rate(spec['strategy_demands'][strategy]);annual=a2024*demand
        # These are proposed activities and hypothetical physical throughput
        # frontiers, NOT qualifying programme completion or recipient transitions.
        for year in range(spec['forecast_start_year'],spec['forecast_end_year']+1):
            requests.append({'year':year,'strategy':strategy,'pathway':path,
               'physical_strategy':physical_strategy,'recipient_priority_policy':policy,
               'requested_fabric_area_m2':annual,'max_eligible_2024_cohort_area_m2':eligible,
               'financing_rule':('NO_FINANCE_VETO_FUTURE_PRIORITY_RENOVATION'
                                 if path in ('PAS','HDE') else 'PI_FINANCE_SCOPED_SEPARATELY'),
               'heating_generator_switch':'SEPARATE_PHYSICAL_EVENT',
               'newbuild_or_conversion':'SEPARATE_STOCK_EVENT',
               'actor_catchment_capacity':'UNKNOWN_NOT_ZERO',
               'event_status':'REQUEST_NOT_COMMITTED_OR_COMPLETED'})
            for cap_name,cap_rate in capacities.items():
                possible=min(annual,cap_rate*a2024,eligible)
                frontier.append({'year':year,'strategy':strategy,'pathway':path,
                    'capacity_prior':cap_name,'requested_m2':annual,
                    'conditional_max_start_m2':possible,'unmet_request_m2':annual-possible,
                    'evidence_class':'CAPACITY_EQUIVALENT_STRESS_NOT_MEASURED_CREWS_OR_BUILT_WORK'})
    # Spatial ranking is informational: it identifies compatible recipient
    # populations, never a city-sponsored project or actor's actual catchment.
    # Strategies retain their governed physical differences as priority rules.
    # Where carrier/tenure/conversion evidence is absent, its policy-specific
    # selection criterion stays unidentified instead of becoming a zero.
    rankings=[]
    for strategy,(path,policy,physical_strategy) in full.items():
        def order(row):
            unmet=row['2024_eligible_not_good_area_m2']
            p=row['2024_technical_ra_area_share']
            if strategy in ('PAS_DEEP','PAS_RETENTION'):
                return (-row['2024_conditional_conditioned_area_m2']*p['RA_I'],-unmet,row['place_id'])
            if strategy in ('PI_INDUSTRIALISATION','HDE_INDUSTRIAL'):
                return (-row['2024_conditional_survivor_buildings'],-unmet,row['place_id'])
            if strategy=='PI_EXEMPLAR':
                return (-unmet,-row['2024_conditional_survivor_buildings'],row['place_id'])
            return (-unmet,row['place_id'])
        for index,row in enumerate(sorted(current,key=order),start=1):
            extra=''
            if strategy=='HDE_ELECTRIFICATION':extra='HEATING_CARRIER_JOINT_UNIDENTIFIED'
            elif strategy=='PAS_ADAPTIVE':extra='CONVERSION_SITE_AND_RETENTION_RIGHTS_UNIDENTIFIED'
            elif strategy=='HDE_REDEVELOPMENT':extra='REDEVELOPMENT_AND_ADDITION_FLOW_UNIDENTIFIED'
            elif strategy=='PI_EXEMPLAR':extra='DEMONSTRATOR_AND_CARRIER_ID_UNIDENTIFIED'
            rankings.append({'strategy':strategy,'rank':index,
               'place_id':row['place_id'],'family':row['family'],
               'eligible_not_good_area_m2':row['2024_eligible_not_good_area_m2'],
               'technical_ra_i_area_m2':row['2024_conditional_conditioned_area_m2']*row['2024_technical_ra_area_share']['RA_I'],
               'repeatable_candidate_buildings':row['2024_conditional_survivor_buildings'],
               'selection_policy':policy,'missing_local_determinant':extra,
               'status':'CONDITIONAL_RECIPIENT_ORDER_NOT_COMMITTED_DELIVERY'})
    coverage=[]
    # Distinguish unique cumulative coverage from annual flow. With no
    # identifiable building IDs two defensible allocation structures bracket
    # the repeated-work uncertainty, not a statistical confidence interval.
    for strategy in full:
        for cap_name in capacities:
            cumulative=0.;product=1.
            for year in range(spec['forecast_start_year'],spec['forecast_end_year']+1):
                possible=next(r['conditional_max_start_m2'] for r in frontier
                              if r['year']==year and r['strategy']==strategy and r['capacity_prior']==cap_name)
                cumulative+=possible
                product*=1-min(1,possible/eligible) if eligible else 0
                coverage.append({'year':year,'strategy':strategy,'capacity_prior':cap_name,
                    'cumulative_requested_started_area_m2':cumulative,
                    'max_unique_if_no_repeats_m2':min(cumulative,eligible),
                    'expected_unique_if_independent_random_reselection_m2':eligible*(1-product),
                    'rule':'ALTERNATIVE_RESELECTION_STRUCTURES_NOT_COMPLETION_OR_CERTIFIED_DEEP'})
    return {'schema':'panel-dated-recipient-requests/1','country':'SK','reference_year':2021,
       'reference_2024':'MODELLED_FIXED_2021_COHORT_SURVIVOR_NOT_OBSERVED_CITY_STOCK',
       'source_ref':spec['source_ref'],'method':{
         'national_exposure_prior':spec['historical_throughput_source_ref'],
         'national_retirements_transfer_prior':spec['attrition_source_ref'],
         'thermal_state_source':spec['ra_physics_source_ref'],
         'historical_progression_given_exposure':spec['technical_progression_given_exposure'],
         'historical_exposure_rate':spec['historical_apartment_renovation_exposure_rate'],
         '2024_newbuild_outside_fixed_cohort':'NOT_INFERRED_CITY_COUNTS',
         'throughput_rule':'REQUEST_AND_EXPLICIT_PHYSICAL_FRONTIER_ONLY__EXISTING_COHORT_SCHEDULER_BOOKS_ACTUAL_EVENTS',
         'stage_rule':'D0-D8_DIFFUSION_STATES_NOT_GENERIC_ADOPTION_MULTIPLIERS'},
       'survival':{'annual_factors':year_factors,'three_year_factor':survival,
          'survivor_buildings':b2024,'survivor_dwellings':d2024,
          'survivor_conditioned_area_m2':a2024},
       '2024_technical_ra_survivor_area_m2':totals,
       'place_family_2024_priors':current,
       'strategy_annual_requests':requests,'strategy_recipient_rankings':rankings,
       'conditional_capacity_frontiers':frontier,
       'cumulative_coverage_alternatives':coverage,
       'acceptance':'RESEARCH_PRIOR__NO_PHYSICAL_EVENTS_COMMITTED_NO_RUNTIME_PROMOTION'}


def audit_completed_local_renovation_decisions(payload, *, as_of='2024-12-31'):
    """Read-only primary-document qualification; never infer city RA shares/rates.

    Municipal use-permission decisions are selected event exemplars. Even a
    completion-stage decision does not identify a whole-building thermal state,
    per-component U, installation area, legal finality, or the true citywide
    activity sampling frame. The returned records may be matched to the stock
    event ledger by a separate physical-identity/site qualification. They do not
    alter opening populations, national pathways or annual delivery capacity.
    """
    from datetime import date
    from urllib.parse import urlsplit
    if payload.get('schema')!='sk-ke-observed-decisions-evidence-v08/1':
        raise ValueError('Expected source-qualified local completion decisions')
    if payload.get('source_selection')=='COMPLETE_PROBABILITY_SAMPLE':
        raise ValueError('This evidence ledger does not establish a probability sampling frame')
    records=payload.get('records')
    if not isinstance(records,list): raise ValueError('Decision record list required')
    cutoff=date.fromisoformat(as_of)
    seen=set();audited=[];by_year={};known_scope={'PRE_2021':0,'2021_TO_2024':0,'AFTER_2024':0}
    for r in records:
        for field in ('id','address','decision_date','decision_type','source','original_archetype','stage'):
            if not r.get(field):raise ValueError('Missing primary decision provenance: '+field)
        if r['id'] in seen:raise ValueError('Duplicate municipal decision id')
        seen.add(r['id'])
        if r['decision_type']!='MUNICIPAL_USE_PERMISSION_ISSUED':
            raise ValueError('Permit application is not an issued use decision')
        if r.get('source_evidence')!='PRIMARY_MUNICIPAL_DOCUMENT':
            raise ValueError('Evidence not tied to a primary municipal document')
        url=urlsplit(r['source'])
        if url.scheme!='https' or not url.hostname or 'kosice.sk' not in url.hostname:
            raise ValueError('Source URL outside qualified municipality')
        date_issued=date.fromisoformat(r['decision_date'])
        cohort=('PRE_2021' if date_issued.year<=2020 else
                '2021_TO_2024' if date_issued.year<=2024 else 'AFTER_2024')
        known_scope[cohort]+=1
        by_year[date_issued.year]=by_year.get(date_issued.year,0)+1
        lower=r.get('lower','UNKNOWN')
        if not isinstance(lower,str) or not lower:raise ValueError('Missing lower boundary scope')
        if r.get('installed_lower_area_m2') not in (None,''):
            raise ValueError('Unverified lower area cannot be entered in this source-only case set')
        if r.get('conditioned_area_m2') not in (None,''):
            raise ValueError('Unverified conditioned area cannot be entered in this source-only case set')
        status=('AFTER_SNAPSHOT_NOT_OPENING' if date_issued>cutoff else
                'ISSUED_BEFORE_SNAPSHOT__SITE_SPECIFIC_ONLY')
        is_thermal_roof='INSULATION' in r.get('roof','') and 'WATERPROOFING_ONLY' not in r.get('roof','')
        audited.append({'id':r['id'],'address':r['address'],
          'issued':date_issued.isoformat(),'cohort':cohort,'as_of_status':status,
          'facade_evidence':r.get('wall','UNKNOWN'),
          'roof_thermal_insulation_evidenced':is_thermal_roof,
          'roof_scope':r.get('roof','UNKNOWN'),
          'opening_scope':r.get('windows','UNKNOWN'),
          'lower_scope':lower,'lower_area_m2':None,
          'original_archetype_matched':r['original_archetype'] not in ('UNVERIFIED_BY_SOURCE','UNKNOWN'),
          'ra_opening_state_calibrated':False,
          'citywide_completed_area_m2_promotable':False,
          'source_ref':r['source']})
    if sum(by_year.values())!=len(records):raise AssertionError('History count mismatch')
    return {'schema':'local-renovation-decision-source-audit/1',
       'as_of':as_of,'source_count':len(records),'by_issued_year':dict(sorted(by_year.items())),
       'cohort_counts':known_scope,'audit':audited,
       'allowed_use':'DATED_LOCAL_EXEMPLAR_SCOPE_AND_ACTOR_RESEARCH_ONLY',
       'forbidden_transfer':'NO_CITY_WIDE_SHARE_OR_RA_PRIOR_FROM_SELECTED_DOCUMENTS',
       'physical_stock_events_booked':0,'historical_opening_stock_mutation':False,
       'empirical_calibration':'LOCAL_ASSEMBLY_AND_EVENT_STAGE_ONLY__NO_PREVALENCE_DENOMINATOR',
       'reason':'Selected municipal decisions lack a complete building sampling frame, site-matched component areas/U, legally final dates and 2024 stock-owner joins.'}


def audit_local_site_identity_matches(decisions, site_evidence, *, as_of='2024-12-31'):
    """Qualify a primary decision -> site identity, not stock or original-panel type.

    This augments the V08 municipal decision evidence with source-cited cadastral
    parcels and separately graded secondary catalogue/contractor references.
    A parcel/registration identity is NOT an INSPIRE polygon footprint join,
    as-built original construction-system match, treated-component surface,
    measured energy, or representative denominator. No numerical population,
    RA share or physical event is returned. Missing quantities remain None.
    """
    from datetime import date
    from urllib.parse import urlsplit
    if site_evidence.get('schema') != 'sk-ke-local-physical-identity-evidence-v09/1':
        raise ValueError('Expected V09 municipal site identity evidence')
    prior = audit_completed_local_renovation_decisions(decisions, as_of=as_of)
    original = {x['id']: x for x in decisions['records']}
    observed_ids = set(original)
    matched = site_evidence.get('records')
    if not isinstance(matched, list) or len(matched) != len(observed_ids):
        raise ValueError('Site match must cover the same municipal decision IDs')
    seen = set(); validated = []
    for record in matched:
        ident = record.get('decision_id')
        if ident in seen or ident not in observed_ids:
            raise ValueError('Duplicate or unknown municipal site-match ID')
        seen.add(ident)
        source = original[ident]
        if (record.get('municipal_decision_source') != source['source']
                or record.get('address') != source['address']
                or record.get('decision_issued') != source['decision_date']):
            raise ValueError('Site record disagrees with primary decision identity/date')
        cad = record.get('cadastral_identity', {})
        if not cad.get('cadastre') or not isinstance(cad.get('parcel_numbers'), list) or not cad['parcel_numbers']:
            raise ValueError('Site requires explicit primary cadastral area and parcels')
        if any(not isinstance(p, str) or not p.strip() for p in cad['parcel_numbers']):
            raise ValueError('Invalid cadastral parcel number')
        if len(cad['parcel_numbers']) != len(set(cad['parcel_numbers'])):
            raise ValueError('Duplicate parcel within municipal project')
        build_number = cad.get('building_registration_number')
        grade = cad.get('building_number_evidence')
        if build_number is not None and grade not in ('MUNICIPAL_USE_DECISION', 'SECONDARY_BUILDING_CATALOGUE'):
            raise ValueError('Building number needs an explicit primary or secondary source grade')
        if record.get('original_panel_system') != 'UNIDENTIFIED_NO_ASBUILT_TYPOLOGY':
            raise ValueError('Original panel series cannot be asserted by a parcel match')
        if record.get('asbuilt_geometry_footprint_id') is not None:
            raise ValueError('No source-qualified GKU/INSPIRE footprint identity has been linked')
        for k in ('matched_insulated_lower_area_m2', 'matched_treated_roof_area_m2',
                  'matched_treated_facade_area_m2', 'observed_conditioned_area_m2',
                  'observed_work_start', 'observed_work_end'):
            if record.get(k) is not None:
                raise ValueError('Site evidence is insufficient to promote '+k)
        permit = record.get('earlier_building_permit', {})
        if permit.get('issued') and date.fromisoformat(permit['issued']) > date.fromisoformat(record['decision_issued']):
            raise ValueError('Building permit issued after use-permission decision')
        if permit.get('legal_finality_date') and date.fromisoformat(permit['legal_finality_date']) > date.fromisoformat(record['decision_issued']):
            raise ValueError('Building-permit finality after use-permission decision')
        secondary = record.get('independent_crossreferences') or []
        if build_number is not None and grade == 'SECONDARY_BUILDING_CATALOGUE' and not any(
                x.get('reported_building_number') == build_number and x.get('source') for x in secondary):
            raise ValueError('Secondarily reported building number is not supported')
        secondary_dwellings = []
        disputed_area = False
        for x in secondary:
            parsed = urlsplit(x.get('source', ''))
            if parsed.scheme != 'https' or not parsed.netloc or not x.get('type'):
                raise ValueError('Independent crossreference needs link and evidence type')
            n = x.get('reported_total_flats_scenario')
            if n is not None:
                per=x.get('reported_flats_per_entrance'); entries=x.get('reported_entrances')
                if any(type(z) is not int or z<=0 for z in (per, entries, n)) or per*entries != n:
                    raise ValueError('Inconsistent secondarily reported flats/entrance count')
                secondary_dwellings.append(n)
            if 'reported_facade_area_m2' in x:
                if x.get('match')!='DO_NOT_PROMOTE_ORIGINAL_SITE_FACADE_AREA':
                    raise ValueError('Unqualified contractor area must be quarantined')
                disputed_area = True
        validated.append({'decision_id':ident,'address':record['address'],
            'municipal_cadastre':cad['cadastre'],'municipal_parcels':cad['parcel_numbers'],
            'building_number':build_number,'building_number_grade':grade,
            'municipal_use_decision_issued':record['decision_issued'],
            'building_permit_issued':permit.get('issued'),
            'earlier_permit_final':permit.get('legal_finality_date'),
            'decision_precedes_opening_2024':date.fromisoformat(record['decision_issued'])<=date.fromisoformat(as_of),
            'secondary_dwellings_scenario':secondary_dwellings[0] if len(secondary_dwellings)==1 else None,
            'secondary_dwellings_not_stock_observation':True,
            'contractor_area_quarantined':disputed_area,
            'verified_original_panel_series':None,'verified_asbuilt_footprint_id':None,
            'verified_treated_facade_area_m2':None,'verified_treated_roof_area_m2':None,
            'verified_treated_lower_area_m2':None,
            'modelled_stock_and_events_modified':False,
            'evidence_class':'MUNICIPAL_PARCEL_ID_WITH_OPTIONAL_GRADED_SECONDARY_REFERENCES'})
    if seen != observed_ids: raise ValueError('Unmatched municipal decisions')
    return {'schema':'sk-ke-site-identity-validation-v09/1',
        'source_count':len(validated),'municipal_cadastre_identity_count':len(validated),
        'municipal_building_number_count':sum(x['building_number'] is not None and
             x['building_number_grade']=='MUNICIPAL_USE_DECISION' for x in validated),
        'secondary_building_number_count':sum(x['building_number_grade']=='SECONDARY_BUILDING_CATALOGUE' for x in validated),
        'secondary_dwelling_scenarios_count':sum(x['secondary_dwellings_scenario'] is not None for x in validated),
        'contractor_area_quarantined_count':sum(x['contractor_area_quarantined'] for x in validated),
        'pre_2025_site_decision_count':sum(x['decision_precedes_opening_2024'] for x in validated),
        'records':validated,'primary_decision_audit':{'count':prior['source_count'], 'cohorts':prior['cohort_counts']},
        'site_area_m2_qualified':None,'city_ra_stock_shares_calibrated':False,
        'observed_heat_kwh_calibrated':False,'building_geometry_gku_join_completed':False,
        'scheduled_physical_events_booked':0,'historical_2011_stock_changed':False,
        'national_2024_or_2035_promoted':False,
        'status':'IDENTITY_PARTIAL_COMPLETION_NO_PHYSICAL_AREA_OR_SYSTEM_PROMOTION'}
