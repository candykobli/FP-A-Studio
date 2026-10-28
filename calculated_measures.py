"""Reviewed formulas over a single approved source model; safe aggregate alignment."""
import copy
import hashlib
import json
from datetime import datetime,timezone
import numpy as np
import pandas as pd
from workspace import fingerprint
from dimensions import PREFIX

# No missing component is inferred as zero. Each selected role needs a measure.
RECIPES={
    'Gross profit':{'kind':'amount','terms':{'Revenue':1,'Cost of sales':-1}},
    'Operating profit':{'kind':'amount','terms':{'Gross profit':1,'Other operating income':1,'Operating expenses':-1,'Other operating expenses':-1}},
    'Net profit':{'kind':'amount','terms':{'Operating profit':1,'Finance income':1,'Finance expenses':-1,'Income tax':-1}},
    'Gross profit margin (%)':{'kind':'ratio','terms':{'Gross profit':1,'Revenue':1}},
    'Operating profit margin (%)':{'kind':'ratio','terms':{'Operating profit':1,'Revenue':1}},
    'Net profit margin (%)':{'kind':'ratio','terms':{'Net profit':1,'Revenue':1}}}


def strict_sum(s):return s.sum() if len(s) and s.notna().all() else np.nan


def active_calculations(base,registry):
    """Resolve dependencies transitively; stale approved results are retained but hidden."""
    active={};pending=dict(registry)
    while pending:
        changed=False
        for key,entry in list(pending.items()):
            source=entry['source_key']
            if source not in base or fingerprint(base[source])!=entry['base_fingerprint']:
                pending.pop(key);changed=True;continue
            deps=entry.get('dependencies',{})
            if any(k not in registry or registry[k]['signature']!=v for k,v in deps.items()):
                pending.pop(key);changed=True;continue
            if all(k in active for k in deps):
                active[key]=entry;pending.pop(key);changed=True
        if not changed:break
    return active


def available_input(base,registry,source):
    active=active_calculations(base,registry)
    parts=[base[source].copy(deep=True)]
    deps={}
    for key,entry in active.items():
        if entry['source_key']==source:
            parts.append(entry['data'].copy(deep=True));deps[entry['name']]=key
    return pd.concat(parts,ignore_index=True),deps


def model_signature(base,source,recipe,inputs,grain,dependencies):
    return hashlib.sha256(json.dumps({'source':source,'base':fingerprint(base),'recipe':recipe,'inputs':inputs,'grain':grain,'dependencies':dependencies},sort_keys=True).encode()).hexdigest()


def calculate_measure(data,name,inputs,grain):
    if name not in RECIPES:raise ValueError('Choose a supported, explicit calculation.')
    recipe=RECIPES[name];roles=list(recipe['terms'])
    if data.empty or data.source.nunique()!=1:raise ValueError('Use a single approved source model; independent sources are not automatically joined.')
    if set(inputs)!=set(roles):raise ValueError('Map every required formula input explicitly.')
    if name in inputs.values():raise ValueError('A calculated measure cannot use itself as a formula input.')
    if 'measure_origin' in data and (data.measure.eq(name)&data.measure_origin.eq('Source-provided')).any():
        raise ValueError('This model already provides the target measure. Do not add a second version alongside it without reviewing a separate model.')
    if len(set(inputs.values()))!=len(inputs):raise ValueError('Use a distinct source measure for every formula role.')
    allowed=[c for c in data if c.startswith(PREFIX)]
    if any(c not in allowed for c in grain) or len(set(grain))!=len(grain):raise ValueError('Choose distinct confirmed business dimensions as calculation keys.')
    keys=['date','currency']+list(grain)
    combined=None
    for i,role in enumerate(roles):
        selected=data[data.measure==inputs[role]]
        if selected.empty:raise ValueError('Required input is missing: '+role)
        if 'measure_type' in selected and selected.measure_type.fillna('amount').ne('amount').any():raise ValueError('Formula inputs must be amount measures, not percentages or period-end counts.')
        if 'measure_unit' in selected and selected.measure_unit.fillna('amount').ne('amount').any():raise ValueError('Use comparable monetary amount inputs; counts and stock measures are not interchangeable with revenue.')
        if selected[keys].isna().any().any():raise ValueError('Calculation keys contain missing values. Correct them or explicitly aggregate at a coarser complete grain.')
        amounts=selected.groupby(keys,dropna=False,as_index=False).agg(**{f'a{i}':('actual',strict_sum),f'b{i}':('budget',strict_sum)})
        if not np.isfinite(amounts[f'a{i}'].astype(float)).all():raise ValueError('Required actual inputs have missing or invalid amounts.')
        if not np.isfinite(amounts[f'b{i}'].dropna().astype(float)).all():raise ValueError('The aggregated budget input is not finite.')
        if combined is None:combined=amounts
        else:
            combined=combined.merge(amounts,on=keys,how='outer',validate='one_to_one',indicator=True)
            if combined['_merge'].ne('both').any():
                raise ValueError('Inputs do not cover the same dates, currencies and selected business keys. No unmatched group is filled with zero; align the source or choose an explicitly coarser grain.')
            combined=combined.drop(columns='_merge')
    out=combined[keys].copy(deep=True)
    out['entity']=out[next((c for c in grain if c.casefold().endswith('country')),grain[0])] if grain else 'All'
    out['category']=name;out['source']=str(data.source.iloc[0]);out['measure']=name
    out['source_row']=['calculated group '+str(i) for i in range(len(out))]
    out['measure_origin']='Calculated';out['measure_type']=recipe['kind'];out['measure_unit']='%' if recipe['kind']=='ratio' else 'amount'
    out['measure_inputs']=json.dumps(inputs,sort_keys=True)
    if recipe['kind']=='amount':
        for i,role in enumerate(roles):
            out['component_actual::'+role]=combined['a'+str(i)]
            out['component_budget::'+role]=combined['b'+str(i)]
        for scenario,pre in [('actual','a'),('budget','b')]:
            values=combined[[pre+str(i) for i in range(len(roles))]].copy()
            for i,role in enumerate(roles):values[pre+str(i)]*=recipe['terms'][role]
            out[scenario]=values.sum(axis=1,min_count=len(roles))
        formula=' '.join(('+' if sign>0 and i else '−' if sign<0 else '')+' '+role for i,(role,sign) in enumerate(recipe['terms'].items())).strip()
    else:
        for scenario,pre in [('actual','a'),('budget','b')]:
            out['ratio_'+scenario+'_numerator']=combined[pre+'0']
            out['ratio_'+scenario+'_denominator']=combined[pre+'1']
            out[scenario]=combined[pre+'0'].div(combined[pre+'1'].replace(0,np.nan))*100
        formula=roles[0]+' ÷ Revenue × 100'
    out['measure_formula']=formula
    if recipe['kind']=='amount' and (not np.isfinite(out.actual.astype(float)).all() or not np.isfinite(out.budget.dropna().astype(float)).all()):raise ValueError('The calculation produced a non-finite amount.')
    if recipe['kind']=='ratio':
        for scenario in ('actual','budget'):
            vals=out[scenario].dropna()
            if not np.isfinite(vals.astype(float)).all():raise ValueError('The ratio produced a non-finite value.')
    evidence=combined.rename(columns={f'{p}{i}':f'{role} {scenario}' for i,role in enumerate(roles) for p,scenario in [('a','actual'),('b','budget')]})
    return out,evidence,formula


def approve_calculation(state,key,preview,current_signature,replace=False):
    if preview['signature']!=current_signature:raise ValueError('The formula inputs changed. Preview and approve again.')
    if key in state.setdefault('calculated_measures',{}) and not replace:raise ValueError('Confirm replacement of the existing calculated definition.')
    registry=state['calculated_measures']
    def reaches_target(node,seen):
        if node==key:return True
        if node in seen:return False
        seen.add(node)
        return any(reaches_target(child,seen) for child in registry.get(node,{}).get('dependencies',{}))
    if any(reaches_target(dep,set()) for dep in preview.get('dependencies',{})):
        raise ValueError('This definition would create a circular calculation. Choose independent inputs.')
    stored=copy.deepcopy(preview)
    stored['approved_at']=datetime.now(timezone.utc).isoformat()
    state['calculated_measures'][key]=stored
    return stored
