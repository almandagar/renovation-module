"""Evidenced, non-energy actor formation ledger. Country-neutral research interface.

No project, donor, or commissioning stage creates renovation m2 or readiness
multipliers. Physical housing and nonresidential books remain separate.
"""
from datetime import date

STAGES=('NO_VISIBLE_PRECEDENT','PROGRAMME_FORMED','DEMO_DESIGNED','BUILT',
        'QUALIFIED_PUBLIC_DONOR','REPLICATED_BY_CARRIER','INDEPENDENT_CARRIER_REPLICATION')


def evaluate(events,physical_ledger,external_completions=()):
    """Validate explicit dated stage evidence; return per-locality status records.

    For BUILT or replication, a source-qualified physical completed event is
    required. An externally verified public/nonres event is never added to the
    residential physical ledger by this function.
    """
    observed={x['event_id']:x['date'] for x in physical_ledger
              if x.get('status')=='COMPLETED' and x.get('kind') in ('renovation','conversion','newbuild')
              and x.get('date')}
    external={x['event_id']:x.get('date') for x in external_completions
              if x.get('status')=='COMPLETED' and x.get('source_ref')
              and x.get('sector')=='NONRES' and x.get('date')}
    groups={}
    for e in events:
        for key in ('id','locality_id','capability_scope','stage','date','source_ref'):
            if not e.get(key):raise ValueError('Missing actor formation field: '+key)
        if e['stage'] not in STAGES:raise ValueError('Unknown actor stage')
        date.fromisoformat(e['date'])
        key=(e['locality_id'],e['capability_scope'])
        groups.setdefault(key,[]).append(e)
    seen_global=set();rows=[]
    for (locality,scope),actions in sorted(groups.items()):
        actions.sort(key=lambda e:(e['date'],STAGES.index(e['stage'])))
        reached=-1;seen_carriers=set();used_projects=set();first_carrier=None
        for e in actions:
            if e['id'] in seen_global:raise ValueError('Duplicate actor stage identity')
            seen_global.add(e['id'])
            n=STAGES.index(e['stage'])
            if n!=reached+1:raise ValueError('Actor formation stages must be consecutive and separately evidenced')
            if n==0 and e.get('precedent_audit')!='AUDITED_NOT_IDENTIFIED':
                raise ValueError('Unknown local precedent cannot be called absent without bounded audit')
            if n==0 and not e.get('inhabited_service_area_ref'):
                raise ValueError('Actor formation priority requires inhabited service catchment evidence')
            if n==1 and (not e.get('commissioner_id') or not e.get('carrier_id')):
                raise ValueError('Formation needs commissioner and identified actor')
            if n==1:first_carrier=e['carrier_id']
            if n==2 and not e.get('strategy_package'):
                raise ValueError('Demonstrator requires strategy-dependent design')
            if n in (3,5,6):
                pid=e.get('physical_event_id')
                completed_at=observed.get(pid,external.get(pid))
                if not completed_at:raise ValueError('Actor stage requires independently evidenced completed physical project')
                if e['date']<completed_at:raise ValueError('Actor stage cannot predate physical completion')
                if pid in used_projects:raise ValueError('Independent replication cannot reuse demonstrator or previous physical project')
                used_projects.add(pid)
            if n==4 and not (e.get('independent_qa_ref') and e.get('post_performance_ref') and e.get('public_transfer_ref')):
                raise ValueError('Donor qualification requires independent QA, service performance, public transfer')
            if n in (5,6):
                carrier=e.get('carrier_id')
                if not carrier:raise ValueError('Replicating carrier identity required')
                if n==6 and carrier in seen_carriers|{first_carrier}:raise ValueError('Independent replication requires new carrier')
                seen_carriers.add(carrier)
            rows.append({'actor_event_id':e['id'],'locality_id':locality,'capability_scope':scope,
                         'date':e['date'],'stage':e['stage'],'evidence_ref':e['source_ref'],
                         'physical_event_id':e.get('physical_event_id'),
                         'actor_m2_credited':0,'adoption_multiplier':None})
            reached=n
    return rows
