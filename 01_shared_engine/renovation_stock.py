"""One conserved ledger. Cells are disjoint; national residual cells are explicit."""
from copy import deepcopy
from math import isclose
from archetype_physics import positive,resolve
from surface_state import split_surface_inventory
QUANTITIES=('area_m2','buildings','dwellings')

def totals(cells):return {k:sum(c[k] for c in cells) for k in QUANTITIES}

def validate(cells,library):
    if len({c['id'] for c in cells})!=len(cells):raise ValueError('Duplicate stock identity')
    for c in cells:
        for k in ('id','place_id','archetype_id','construction_period','source_ref','state','heating'):c[k]
        for k in QUANTITIES:positive(c[k],k)
        period=c['construction_period']
        if len(period)!=2 or period[0]>period[1]:raise ValueError('Invalid age interval')
        resolve(c,library)
    return totals(cells)

def take(cells,cell,area,new_id):
    if not 0<area<=cell['area_m2']+1e-8:raise ValueError('Withdrawal exceeds stock')
    result=deepcopy(cell);share=min(1,area/cell['area_m2']);result['id']=new_id
    result.setdefault('root_id',cell.get('root_id',cell['id']))
    for k in QUANTITIES:
        result[k]=cell[k]*share;cell[k]-=result[k]
    split_surface_inventory(result,share)
    split_surface_inventory(cell,1-share)
    if cell['area_m2']<1e-8:cells.remove(cell)
    return result

def check_conservation(cells,expected):
    actual=totals(cells)
    if any(not isclose(actual[k],expected[k],rel_tol=1e-9,abs_tol=1e-6) for k in QUANTITIES):
        raise ValueError('Stock conservation failed: '+str((actual,expected)))

def match(c,selector):
    return all((c.get(k)==v or (k=='root_id' and c.get('root_id',c['id'])==v)) for k,v in selector.items())

def substitute(cells,parent_id,children,library):
    """Local children replace parent quantity; remainder retains original state."""
    cells=deepcopy(cells);parent=next(c for c in cells if c['id']==parent_id)
    before=totals(cells); ct=totals(children)
    if any(ct[k]>parent[k]+1e-6 for k in QUANTITIES):raise ValueError('City exceeds parent')
    if any(c['archetype_id']!=parent['archetype_id'] for c in children):raise ValueError('Incompatible city parent')
    original_parent_area=parent['area_m2']
    for k in QUANTITIES:parent[k]-=ct[k]
    split_surface_inventory(parent,max(0,1-ct['area_m2']/original_parent_area))
    if parent['area_m2']<1e-8:
        if parent['buildings']>1e-8 or parent['dwellings']>1e-8:raise ValueError('Area/count mismatch')
        cells.remove(parent)
    cells.extend(deepcopy(children));validate(cells,library);check_conservation(cells,before)
    return cells
