"""Material ledger derived from completed physical interventions, never energy fractions."""
from collections import defaultdict

def export_inventory(results):
    rows=[]
    for result in results:
        for event in result['ledger']:
            if event['status']!='COMPLETED':continue
            rows.append({'scenario':result['scenario'],**event})
    return rows
