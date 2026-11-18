"""Deterministic SOFTWARE fixture. Not measured Orava/Slovakia or a national forecast."""
import json
from copy import deepcopy
from pathlib import Path

def fixture():
    components={}
    for comp,u in [('wall',1.6),('roof',1.8),('window',2.8),('floor',1.2)]:
        components[comp]={
          'original':{'u_w_m2k':u,'source_ref':'SYNTHETIC_ENGINEERING_TEST'},
          'improved':{'u_w_m2k':0.15 if comp!='window' else 0.7,'source_ref':'SYNTHETIC_ENGINEERING_TEST',
             'installed_kg_m2':{'insulation':10},'removed_kg_m2':{'mixed':2},'task_hours_m2':{'installer':1}}}
    arch={'source_ref':'SYNTHETIC_CUBE_NOT_ORAVA_OBSERVATION','construction_period':[1961,1980],
       'geometry':{'wall':1.,'roof':.5,'window':.2,'floor':.5},'components':components,
       'ventilation_w_k_m2':.25,'bridges_w_k_m2':.05}
    state={k:'original' for k in components};gas={'carrier':'GAS','useful_per_final':.85}
    cell={'id':'old_cube_cohort','country':'TEST','place_id':'district','archetype_id':'cube','construction_period':[1961,1980],
       'area_m2':1000.,'buildings':10.,'dwellings':10.,'state':state,'heating':gas,'source_ref':'SYNTHETIC'}
    lib={'schema':'physical-archetype-library/1','archetypes':{'cube':arch},'packages':{
       'roof_windows':{'targets':{'roof':'improved','window':'improved'}},
       'walls_floor':{'targets':{'wall':'improved','floor':'improved'}},
       'deep':{'targets':{k:'improved' for k in components}}},
       'newbuild_designs':{'efficient':{'archetype_id':'cube','state':{k:'improved' for k in components},
       'heating':{'carrier':'HP_ELECTRICITY','useful_per_final':4},'installed_kg_m2':{'concrete':100},
       'task_hours':{'installer':2},'installed_kg':{'concrete':100},
       'metrics':{'onsite_fossil_co2':0},'wlc_method_ref':'SYNTHETIC_TEST_NOT_REGULATORY_ASSESSMENT','assessment_years':50,
       'wlc_kgco2e_m2':{'A1_A3':100,'A4_A5':10,'B1_B3_B5':0,'B7':0,'B4':10,'B6':30,'C1_C4':10,'D':-15}}}}
    def new(i,start,end,area):return {'id':i,'kind':'newbuild','country':'TEST','owner':'private',
       'start_date':start,'completion_date':end,'permit_date':start,'design_id':'efficient',
       'building_floor_area_m2':100,'area_m2':area,'buildings':area/100,'dwellings':area/100,
       'place_id':'district','source_ref':'SYNTHETIC'}
    historic=[new('new2012','2011-01-01','2012-01-01',200)]
    events=[{'id':'stage1','kind':'renovation','start_date':'2025-01-01','completion_date':'2026-01-01',
      'selector':{'root_id':'old_cube_cohort'},'area_m2':1000,'package_id':'roof_windows'},
      {'id':'stage2','kind':'renovation','start_date':'2027-01-01','completion_date':'2028-01-01',
       'selector':{'root_id':'old_cube_cohort'},'area_m2':1000,'package_id':'walls_floor'},
      new('new2030','2029-01-01','2030-01-01',100)]
    scenarios=[]
    for path in ['PI','PAS','HDE']:
        for idx in range(3):
            e=deepcopy(events)
            if idx==1:e=[x for x in e if x['id']!='stage2']
            if idx==2:e=[x for x in e if x['kind']=='newbuild']
            scenarios.append({'id':path+'_'+str(idx),'pathway':path,'timing':'central','events':e})
    return {'schema':'building-stock/2','country':'TEST','status':'SOFTWARE_ACCEPTANCE_ONLY',
       'history_start':'2011-01-01','forecast_start':'2025-01-01','end_date':'2036-01-01',
       'opening_cells':[cell],'library':lib,'historical_events':historic,'scenarios':scenarios,
       'standards':[{'id':'TEST_ZERO_FOSSIL','jurisdiction':'TEST','valid_from':'2030-01-01',
          'date_basis':'completion_date','equals':{'onsite_fossil_co2':0},'wlc_required':True,'source_ref':'SYNTHETIC'}],
       'weather':{'district':{'reference':[{'id':'winter','hours':4000,'outdoor_c':4,'indoor_c':20,'usable_gains_w_m2':2}]}}}
if __name__=='__main__':
    b=fixture();Path('COHORT_ACCEPTANCE_INPUT.json').write_text(json.dumps(b,indent=2)+'\n')
    Path('physical_archetype_library_TEST_ONLY.json').write_text(json.dumps(b['library'],indent=2)+'\n')
