"""Exact accounting decomposition. Components are associations, not causal estimates."""
from math import isclose

def decompose(q0,q1,s0,s1,g0,g1,n0=1,n1=1):
    if not len(s0)==len(s1)==len(g0)==len(g1):raise ValueError('State dimension mismatch')
    if any(x<0 for x in [q0,q1,n0,n1,*s0,*s1,*g0,*g1]) or sum(s0)>1.001 or sum(s1)>1.001:raise ValueError('Invalid source inputs')
    mix=sum((a+b)/2*(t-s) for s,t,a,b in zip(s0,s1,g0,g1))
    intensity=sum((s+t)/2*(b-a) for s,t,a,b in zip(s0,s1,g0,g1))
    u0=q0-sum(s*g for s,g in zip(s0,g0));u1=q1-sum(s*g for s,g in zip(s1,g1))
    unallocated=u1-u0
    mean_n=(n0+n1)/2
    population=(n1-n0)*(q0+q1)/2
    return dict(mean_change=q1-q0,mix=mix,within=intensity,unallocated=unallocated,
                national_change=n1*q1-n0*q0,mix_scaled=mean_n*mix,
                within_scaled=mean_n*intensity,unallocated_scaled=mean_n*unallocated,population_scaled=population)

def read_numeric_cohort(rows):
    out=[]
    for r in rows:
        if not isinstance(r[0],int) or len(r)<7 or r[3] not in ('Zonder gasverbruik','Met gasverbruik'):continue
        if not all(isinstance(r[i],(int,float)) for i in [4,5,6]):continue
        out.append(dict(key=(r[1],r[2],r[3]),n=r[4],base=r[5],season=r[6],zero_2024=r[3]=='Zonder gasverbruik'))
    return out
