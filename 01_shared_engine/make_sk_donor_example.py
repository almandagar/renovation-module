"""Build a conditional nine-profile execution example from frozen workbook rows.
One hypothetical building per form/state: not observed stock or prevalence.
"""
import json
from pathlib import Path
from renovation_pipeline import run_pipeline
from archetype_physics import heat

ROOT=Path(__file__).parent
SOURCE='data/sk_fh_donor_snapshot_v36.json'

def build():
    rows=json.loads((ROOT/'data/sk_fh_donor_snapshot_v36.json').read_text())['values']
    cells=[];arches={};rules={}
    for n,r in enumerate(rows[1:],2):
        key=r[0]+'_'+r[1]; area=r[2];ref=SOURCE+'&range=A'+str(n)+':AR'+str(n)
        names=['wall','window','door','top','ground','cellar']
        comps={k:{'current':{'u_w_m2k':r[11+j],'source_ref':ref}} for j,k in enumerate(names)}
        arches[key]={'source_ref':ref,'construction_period':[1961,1980],
            'geometry':{k:r[4+j]/area for j,k in enumerate(names)},'components':comps,
            'ventilation_w_k_m2':r[19]/area,'bridges_w_k_m2':r[20]/area}
        surfaces=[]
        for j,k in enumerate(names):
            adj='ground' if k=='ground' else 'unheated_enclosure' if k in ('cellar','top') and (k=='cellar' or r[0]!='CUBE') else 'exterior'
            basis='floor_to_ground' if k=='ground' else 'floor_to_unheated' if k=='cellar' else 'ceiling_under_attic' if k=='top' and r[0]!='CUBE' else 'surface_net'
            surfaces.append({'id':k,'component':k,'area_m2':r[4+j],'adjacent':adj,'area_basis':basis,'boundary_factor':r[17] if k=='ground' else r[18] if k=='cellar' else 1,'source_ref':ref,'assumption_status':'MODEL_PRIOR'})
        cells.append({'id':key,'country':'SK','place_id':'donor_comparison','archetype_id':None,'fallback_key':key,'use':'residential','construction_period':[1961,1980],
            'area_m2':area,'buildings':1,'dwellings':1,'area_basis':'conditioned',
            'state':{k:'current' for k in names},'surface_inventory':surfaces,'surface_inventory_scope':'complete_thermal_boundary',
            'heating':{'carrier':'USEFUL_HEAT_PROXY','useful_per_final':1},'source_ref':ref,
            'area_assumption':'Workbook model_served_net_m2 adopted as conditional conditioned-area proxy; not measured.'})
        rules[key]={'archetype_id':key,'country':'SK','use':'residential','construction_period':[1961,1980],
            'source_ref':ref,'compatibility_basis':'Explicit form and current RA-state scenario; no inferred national prevalence.'}
    totals={'area_m2':sum(c['area_m2'] for c in cells),'buildings':9,'dwellings':9}
    b={'schema':'building-stock/2','country':'SK','history_start':'2024-01-01','forecast_start':'2025-01-01','end_date':'2026-01-01',
       'opening_cells':cells,'library':{'schema':'physical-archetype-library/1','archetypes':arches,'packages':{},'newbuild_designs':{}},
       'archetype_fallbacks':rules,'historical_events':[],'scenarios':[{'id':'SK_DONOR_SCREEN','pathway':'PI','timing':'central','events':[]}],
       'weather':{'donor_comparison':{'reference':[{'id':'3000_HDD_zero_gain_screen','hours':6000,'outdoor_c':8,'indoor_c':20,'usable_gains_w_m2':0}]}},
       'research_opening_snapshot':{'schema':'research-stock-snapshot/1','country':'SK','as_of_date':'2024-01-01','stock_boundary':'NINE_HYPOTHETICAL_DONOR_EXAMPLES_NOT_NATIONAL_STOCK','source_ref':SOURCE,'state_basis':'Existing workbook conditional RA states; no historical work inferred','uncertainty_ref':SOURCE,'evidence_class':'CONDITIONAL_MODEL_PRIOR_NOT_OBSERVED','population_totals':totals},
       'stock_controls':{'source_ref':'EXAMPLE_DESIGN_ONE_BUILDING_PER_DONOR_NOT_EMPIRICAL_COUNTS','as_of_date':'2024-01-01','totals':totals},
       'archetype_evidence_review':[{'source_ref':SOURCE,'decision':'USED','reason':'Existing component geometry/U/airflow/bridge priors used directly, not fitted to workbook heat intensities.'},
          {'source_ref':'data/sk_fh_donor_snapshot_v36.json','decision':'PROXY_ONLY','reason':'189/120/62 effective intensities cannot specify components; excluded from component library.'}],
       'limitations':['Hypothetical counts, not archetype shares.','All nine RA states are alternatives, not an observed nine-building neighbourhood.','Zero gains screen differs from workbook net-loss factors .75/.76; compare H, not annual heat equality.','USEFUL_HEAT_PROXY is not observed carrier use.','No material/task-hour or delivery inference.']}
    return b,rows[1:]

if __name__=='__main__':
    b,rows=build();p=ROOT/'SK_DONOR_EXAMPLE_INPUT.json';p.write_text(json.dumps(b,indent=2)+'\n')
    out=ROOT/'sk_donor_example_output';run_pipeline(p,out)
    from archetype_integration import prepare_bundle
    resolved=prepare_bundle(b);checks=[]
    for c,r in zip(resolved['opening_cells'],rows):
        h=heat(c,resolved['library'],b['weather']['donor_comparison']['reference'])['h_w_k']
        assert abs(h-r[21])<1e-8,(c['id'],h,r[21])
        checks.append({'id':c['id'],'engine_H_W_K':h,'workbook_H_W_K':r[21],'status':'PASS'})
    (out/'donor_component_parity.json').write_text(json.dumps(checks,indent=2)+'\n')
    print('9 workbook component heat-loss parity checks passed; conditional example only')
