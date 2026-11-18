"""Attach source-library geometry and country condition evidence to physical profiles.
No invented U-values, conditioned floor conversion, Orava prevalence, or dwellings/count ratios.
Explicit priors are allowed, provided their references accompany the profile.
"""
from copy import deepcopy

def iwu_physical_library(reference,profiles):
    result={'schema':'physical-archetype-library/1','archetypes':{},'packages':{},'newbuild_designs':{}}
    source={a['archetype_id']:a for a in reference['archetypes']}
    for aid,profile in profiles.items():
        a=source[aid];p=deepcopy(profile)
        for k in ('components','construction_period','ventilation_w_k_m2','bridges_w_k_m2','geometry'):p[k]
        p['geometry'].update(wall=float(a['opaque_external_wall_per_living_m2']),
            window=float(a['window_area_per_living_m2']),roof=float(a['roof_per_living_m2']))
        p['source_ref']='shared_archetype_reference_v01/renovation_shared_archetype_reference_v01.json'+aid
        p['source_area_basis']='living_floor; explicit conditioned-area translation required in profile'
        factor=p.pop('living_to_conditioned_ratio')
        if factor<=0:raise ValueError('Invalid area conversion')
        for k in ('wall','window','roof'):p['geometry'][k]/=factor
        result['archetypes'][aid]=p
    return result

def slovakia_checkpoint(source,age_profiles):
    """2021 snapshot, NOT 2011 opening. Age profiles include archetype shares by age.
    The supplied WFR joint is inferred; the resulting rows retain that status.
    """
    cells=[]
    for row in source['latent_WFR_2021']['rows']:
        age=row['age_id']
        if age not in age_profiles:continue
        profiles=age_profiles[age]
        if abs(sum(p['archetype_share'] for p in profiles)-1)>1e-8:raise ValueError('Archetype shares must conserve age group')
        for p in profiles:
            if row['conditional_source_floor_area_m2'] is None:raise ValueError('Supply an explicit area prior for unknown age')
            if not 0<p['conditioned_fraction']<=1:raise ValueError('Invalid conditioned fraction')
            share=p['archetype_share'];buildings=row['occupied_family_house_building_equivalents']*share
            state={'window':p['states']['window'][str(row['W'])],'wall':p['states']['wall'][str(row['F'])],
                   'roof':p['states']['roof'][str(row['R'])],**p['other_states']}
            cells.append({'id':age+':'+row['reported_state']+':'+p['archetype_id'],'country':'SK',
               'place_id':p['place_id'],'archetype_id':p['archetype_id'],'state':state,
               'construction_period':p['construction_period'],'heating':deepcopy(p['heating']),
               'area_m2':row['conditional_source_floor_area_m2']*share*p['conditioned_fraction'],
               'buildings':buildings,'dwellings':buildings*p['dwellings_per_building'],
               'source_ref':p['source_ref'],'condition_status':row['crosswalk_status'],
               'snapshot_date':'2021-01-01','area_status':'SOURCE_FLOOR_TIMES_EXPLICIT_CONDITIONED_PRIOR'})
    return cells
