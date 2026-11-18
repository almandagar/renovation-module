"""Independent stock-energy checkpoint diagnostics. All energy quantities are TWh.

No parameter fitting or automatic attribution of residuals to renovation.
"""
import csv,json,math
from pathlib import Path
from renovation_heating_accounting import HeatingCohort,carrier_energy,closing_units
from renovation_cohort_checks import simulate as cohort_simulate,compare_target
from renovation_gas_attribution import decompose

CARRIERS=('electricity','gas','bioenergy','oil','district_heat','coal','other')
BOUNDARY=('country','year','population','geography','service','energy_stage','weather_basis','energy_basis','timing_basis')

def number(x,name,lo=0,hi=None):
 if isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or x<lo or (hi is not None and x>hi):raise ValueError(name+': invalid finite number')
 return float(x)

def bounded(x,name):
 if isinstance(x,dict):
  v=[number(x[k],name) for k in ('low','central','high')]
  if v!=sorted(v):raise ValueError(name+': unordered bounds')
  if not x.get('evidence_ref'):raise ValueError(name+': bounds require evidence')
  return dict(zip(('low','central','high'),v))
 n=number(x,name);return dict(low=n,central=n,high=n)

def degree_days(records,base_temperature_c):
 base=number(base_temperature_c,'degree-day base',-50,60);days=set();out=0
 from datetime import date
 for r in records:
  d=date.fromisoformat(r['date'])
  if d in days:raise ValueError('Duplicate weather day')
  days.add(d);out+=max(0,base-number(r['mean_outdoor_c'],'outdoor temperature',-90,70))
 return out

def weather_inputs(cp):
 w=cp['weather'];actual=number(w['actual_hdd'],'actual HDD',1e-12);reference=number(w['reference_hdd'],'reference HDD',1e-12)
 if not w.get('reference_period') or not w.get('source') or w.get('base_temperature_c') is None:raise ValueError('Weather definition/source incomplete')
 if w.get('daily_temperatures') is not None:
  from datetime import date
  rows=w['daily_temperatures'];dates={date.fromisoformat(r['date']) for r in rows}
  year=cp['boundary']['year'];expected=(date(year+1,1,1)-date(year,1,1)).days
  if len(dates)!=expected or any(d.year!=year for d in dates):raise ValueError('Full matching calendar year required for annual HDD')
  computed=degree_days(rows,w['base_temperature_c'])
  if not math.isclose(actual,computed,rel_tol=1e-6,abs_tol=1e-6):raise ValueError('HDD does not match temperature record')
 number(w['base_temperature_c'],'degree-day base',-50,60)
 return actual/reference

def observations(cp):
 out={}
 for k,v in cp.get('observed_carriers_twh',{}).items():
  if k not in CARRIERS:raise ValueError('Unknown observed carrier')
  out[k]=None if v is None else bounded(v,k)
 e=cp.get('electricity_meter')
 if e:
  if 'electricity' in out:raise ValueError('Choose total electricity or meter reconstruction, not both')
  # Imports are gross imports, never net of export. Storage losses are already
  # part of consumed electricity; annual storage inventory change is explicit.
  if e.get('basis')!='GROSS_IMPORTS_PLUS_ONSITE_SELF_CONSUMPTION':raise ValueError('Net-metered electricity needs explicit reconstruction')
  imp=bounded(e['gross_imports_twh'],'imports');onsite=bounded(e['onsite_self_consumption_twh'],'self consumption')
  delta=number(e.get('storage_inventory_change_twh',0),'storage change',-1e9)
  out['electricity']={c:imp[c]+onsite[c]-delta for c in ('low','central','high')}
  if out['electricity']['low']<0:raise ValueError('Negative consumed electricity')
 return out

def predict(cp,reference=False):
 ratio=1 if reference else weather_inputs(cp)
 cases={c:{k:0. for k in CARRIERS} for c in ('low','central','high')};useful={c:0. for c in cases};ambient={c:0. for c in cases};standard=0.;covered=0.
 ids=set();origins={origin:{c:{k:0. for k in CARRIERS} for c in cases} for origin in ('EXISTING','NEW_BUILD')}
 for cohort in cp['cohorts']:
  if cohort['cohort_id'] in ids:raise ValueError('Duplicate cohort ID')
  ids.add(cohort['cohort_id'])
  if cohort['stock_origin'] not in ('EXISTING','NEW_BUILD'):raise ValueError('Explicit stock origin required')
  if cohort.get('area_basis')!='CONDITIONED_M2':raise ValueError('Qualified conditioned area required')
  if cohort.get('installed_year',0)>cp['boundary']['year']:raise ValueError('Future equipment in historical stock')
  area=number(cohort['area_m2'],'area');qref=area*number(cohort['standard_useful_kwh_m2_reference'],'intensity')/1e9;standard+=qref;covered+=area
  service=bounded(cohort['service_factor'],'service factor')
  fraction=bounded(cohort.get('heated_fraction',1),'heated fraction')
  if fraction['high']>1:raise ValueError('Heated fraction >1')
  poverty=bounded(cohort.get('energy_poverty_service_factor',1),'energy poverty service')
  if poverty['high']>1:raise ValueError('Energy poverty service factor >1')
  systems=cohort['systems']
  if not math.isclose(sum(s['share'] for s in systems),1,abs_tol=1e-8):raise ValueError('System useful-heat shares must sum to one')
  before={c:dict(v) for c,v in cases.items()}
  for case in cases:
   q=qref*ratio*service[case]*fraction[case]*poverty[case];useful[case]+=q
   for s in systems:
    share=number(s['share'],'system share',0,1)
    if s.get('heat_pump'):
     spf=bounded(s['reference_spf' if reference else 'actual_spf'],'SPF')
     backup=number(s.get('backup_efficiency',.9),'backup efficiency',1e-12,1)
     hp_share=number(s.get('hp_share',1),'HP fraction',0,1)
     # Higher SPF -> lower final electricity; energy case bounds preserve this.
     eff=spf['high' if case=='low' else 'low' if case=='high' else 'central']
     r=carrier_energy([HeatingCohort(s.get('technology','HP'),cohort.get('installed_year',cp['boundary']['year']),q*share,eff,hp_share,backup)],cp['boundary']['year'])
     for k in ('electricity','gas'):cases[case][k]+=r[k]
     ambient[case]+=r['ambient']
    else:
     if s['carrier'] not in CARRIERS:raise ValueError('Unknown heating carrier')
     efficiency=bounded(s['efficiency'],'efficiency')
     if efficiency['high']>1:raise ValueError('Use consistent final-energy basis: efficiency >1 requires conversion')
     eff=efficiency['high' if case=='low' else 'low' if case=='high' else 'central']
     if eff<=0:raise ValueError('Zero efficiency')
     cases[case][s['carrier']]+=q*share/eff
  for c in cases:
   for k in CARRIERS:origins[cohort['stock_origin']][c][k]+=cases[c][k]-before[c][k]
 for k,v in cp.get('other_end_uses_twh',{}).items():
  if k not in CARRIERS:raise ValueError('Unknown nonheating carrier')
  b=bounded(v,'other end uses')
  for c in cases:cases[c][k]+=b[c]
 return dict(space_heat_by_stock_origin_twh=origins,carriers_twh=cases,useful_space_heat_twh=useful,ambient_heat_twh=ambient,
             standard_reference_useful_twh=standard,covered_conditioned_m2=covered,
             uncertainty='INPUT_SCENARIO_BOUNDS_NOT_CONFIDENCE_INTERVAL')

def checkpoint(cp,country):
 b=cp['boundary']
 if b['country']!=country:raise ValueError('Checkpoint country mismatch')
 if any(k not in b or b[k] is None or b[k]=='' for k in BOUNDARY):raise ValueError('Incomplete prediction boundary')
 if b['energy_stage']!='FINAL' or b['energy_basis']!='TWH_FINAL_LHV_EXCLUDING_AMBIENT':raise ValueError('Convert observations to explicit final LHV boundary')
 if b['timing_basis']!='CALENDAR_YEAR' or b['weather_basis']!='ACTUAL':raise ValueError('Checkpoint needs calendar-year actual-weather predictions')
 if b['service'] not in ('SPACE_HEAT','ALL_HOUSEHOLD'):raise ValueError('Unsupported service scope')
 if b['service']=='SPACE_HEAT' and cp.get('other_end_uses_twh'):raise ValueError('Nonheating demand in space-heat test')
 if b['service']=='ALL_HOUSEHOLD' and not cp.get('other_end_uses_complete'):raise ValueError('Household totals require complete nonheating scope')
 if cp.get('already_price_adjusted'):raise ValueError('Physical prediction must precede Social overlay')
 physical=predict(cp);normal=predict(cp,True);obs=observations(cp);diagnostics=[];rows=[]
 match=all(cp['observation_boundary'].get(k)==b[k] for k in BOUNDARY)
 overlay=cp.get('social_overlay');adjusted=None
 if overlay:
  if overlay.get('already_embedded_in_service') or not overlay.get('evidence_ref') or overlay.get('boundary')!=b:raise ValueError('Overlay unmatched, unreferenced or already embedded')
  adjusted={c:dict(values) for c,values in physical['carriers_twh'].items()}
  for k,f in overlay['carrier_factors'].items():
   if k not in CARRIERS:raise ValueError('Unknown overlay carrier')
   factor=number(f,'overlay factor')
   for c in adjusted:adjusted[c][k]*=factor
 if not match:diagnostics.append('INCOMPATIBLE_OBSERVATION_BOUNDARY')
 phase=cp.get('test_role','UNSPECIFIED')
 if phase not in ('CALIBRATION','HOLDOUT','UNSPECIFIED'):raise ValueError('Unknown test role')
 sources=set(cp.get('calibration_source_families',[]));obs_family=cp.get('observation_source_family')
 independence='SHARED_LINEAGE' if obs_family in sources else 'HELD_OUT_DECLARED' if phase=='HOLDOUT' and obs_family and cp.get('independence_reviewed') is True else 'UNASSESSED'
 if phase=='CALIBRATION':independence='CALIBRATION_FIT_NOT_VALIDATION'
 tol=number(cp.get('relative_tolerance',.1),'relative tolerance',0,1)
 for k in CARRIERS:
  o=obs.get(k);p={c:physical['carriers_twh'][c][k] for c in ('low','central','high')};target=p if adjusted is None else {c:adjusted[c][k] for c in p}
  residual=None if o is None or not match else target['central']-o['central']
  overlap=None if residual is None else target['low']<=o['high'] and target['high']>=o['low']
  status='INCOMPATIBLE_BOUNDARY' if not match else 'OPEN_OBSERVATION' if o is None else 'WITHIN_INPUT_BOUNDS' if overlap else 'REVIEW_MULTICAUSAL_RESIDUAL'
  if o is not None and match and not overlap and abs(residual)<=tol*max(o['central'],1e-12):status='WITHIN_DECLARED_TOLERANCE'
  rows.append(dict(carrier=k,observed_twh=o,physical_prediction_twh=p,overlay_prediction_twh=None if adjusted is None else target,residual_twh=residual,status=status))
 for s in cp.get('equipment_inventories',[]):
  result=closing_units(s['opening'],s['commissioned'],s['retired']);diagnostics.append(dict(equipment_id=s['equipment_id'],closing=result,observed_closing=s.get('observed_closing'),residual=None if s.get('observed_closing') is None else result-number(s['observed_closing'],'observed inventory')))
 for t in cp.get('indoor_temperature_checks',[]):
  low=number(t['observed_low_c'],'indoor low',-20,60);high=number(t['observed_high_c'],'indoor high',low,60)
  target=number(t['declared_comfort_c'],'comfort',-20,60)
  if not t.get('source'):raise ValueError('Temperature observation needs source')
  diagnostics.append(dict(temperature_check=t['cohort_id'],comfort_in_observed_range=low<=target<=high,observed_range_c=[low,high],declared_comfort_c=target,inference='NO_AUTOMATIC_FABRIC_OR_RENOVATION_INFERENCE'))
 total=None
 if match and all(obs.get(k) is not None for k in CARRIERS):
  total=dict(observed_twh={c:sum(obs[k][c] for k in CARRIERS) for c in ('low','central','high')},physical_twh={c:sum(physical['carriers_twh'][c].values()) for c in ('low','central','high')})
  total['residual_twh']=(sum(adjusted['central'].values()) if adjusted else total['physical_twh']['central'])-total['observed_twh']['central']
 stock=cp.get('observed_conditioned_m2');stock_residual=None if stock is None else physical['covered_conditioned_m2']-number(stock,'observed stock area')
 return dict(checkpoint_id=cp['checkpoint_id'],boundary=b,test_role=phase,independence=independence,
             physical=physical,reference_climate=normal,carrier_checks=rows,diagnostics=diagnostics,
             total_final_energy_check=total,stock_area_residual_m2=stock_residual,hidden_renovation_inferred=False,
             missing_carriers=[k for k in CARRIERS if obs.get(k) is None],
             uncertainty_note='Joint scenario extremes; no probability or causal attribution. Reference-climate output is a separate physical run, not automatic normalisation of measured totals.')

def run_validation(config,country,output_dir):
 if config.get('schema')!='stock-validation/1':raise ValueError('Unsupported validation schema')
 ids=[c['checkpoint_id'] for c in config.get('checkpoints',[])]
 if len(set(ids))!=len(ids):raise ValueError('Duplicate checkpoints')
 results=[checkpoint(c,country) for c in config.get('checkpoints',[])]
 cohort=[]
 for c in config.get('cohort_outcome_checks',[]):
  r=cohort_simulate(c['inputs']);target=None
  if c.get('target') and r['status']!='OPEN_PHYSICAL_INPUTS':target=compare_target(-r['gas_saving_fraction'],c['target'],matched=c.get('matched') is True,price_already_in_effect=c.get('apply_second_price_correction',False))
  cohort.append(dict(check_id=c['check_id'],prediction=r,target_check=target))
 gas=[dict(check_id=c['check_id'],evidence_ref=c.get('evidence_ref'),result=decompose(**c['inputs']),interpretation='ACCOUNTING_IDENTITY_NOT_CAUSAL_RENOVATION') for c in config.get('gas_attribution_checks',[])]
 report=dict(schema='stock-validation/1',country=country,status='OPEN_NO_CHECKPOINTS' if not results else 'DIAGNOSTICS_NOT_NATIONAL_CERTIFICATION',checkpoints=results,cohort_outcomes=cohort,gas_attribution=gas,runtime_promoted=False)
 out=Path(output_dir);out.mkdir(parents=True,exist_ok=True);j=out/'stock_validation.json';j.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
 rows=[]
 for cp in results:
  for r in cp['carrier_checks']:rows.append(dict(checkpoint_id=cp['checkpoint_id'],year=cp['boundary']['year'],carrier=r['carrier'],status=r['status'],residual_twh=r['residual_twh'],independence=cp['independence']))
 p=out/'checkpoint_dashboard.csv'
 with p.open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=['checkpoint_id','year','carrier','status','residual_twh','independence']);w.writeheader();w.writerows(rows)
 return {'stock_validation':j,'checkpoint_dashboard':p}

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inputs',required=True,type=Path);p.add_argument('--country',required=True);p.add_argument('--output-dir',required=True,type=Path);a=p.parse_args()
 for k,v in run_validation(json.loads(a.inputs.read_text()),a.country,a.output_dir).items():print(f'{k}: {v}')
