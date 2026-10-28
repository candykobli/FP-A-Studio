"""Explicit management P&L mapping, arithmetic and source reconciliation."""
import copy
from datetime import datetime,timezone
import numpy as np
import pandas as pd
from workspace import fingerprint

LINES=('Revenue','Cost of sales','Other operating income','Operating expenses',
       'Other operating expenses','Finance income','Finance expenses','Income tax')
EXPENSES={'Cost of sales','Operating expenses','Other operating expenses','Finance expenses','Income tax'}
SUBTOTALS={
    'Gross profit':{'Revenue':1,'Cost of sales':-1},
    'Operating profit':{'Gross profit':1,'Other operating income':1,'Operating expenses':-1,'Other operating expenses':-1},
    'Profit before tax':{'Operating profit':1,'Finance income':1,'Finance expenses':-1},
    'Net profit':{'Profit before tax':1,'Income tax':-1}}
ORDER=('Revenue','Cost of sales','Gross profit','Other operating income','Operating expenses',
       'Other operating expenses','Operating profit','Finance income','Finance expenses',
       'Profit before tax','Income tax','Net profit')
EXCLUDE='Exclude from income statement'
UNMAPPED='Unmapped'


def blank(s):return s.isna()|s.astype('string').str.strip().eq('').fillna(False)


def map_source(raw,source,config,rules):
    """Create one traceable output row per input row. No joins or row deletion."""
    if raw.empty or not raw.columns.is_unique:raise ValueError('Use a non-empty source with unique column names.')
    if config.get('basis') not in ('Monthly activity','Transaction activity'):
        raise ValueError('Use monthly or transaction activity. Year-to-date and closing balances require an explicit conversion before reporting.')
    mapping=config['mapping']
    required=('date','account','actual','currency')
    if any(not mapping.get(k) or mapping[k] not in raw for k in required):raise ValueError('Map date, account, actual and currency for every source.')
    assigned=[mapping[k] for k in (*required,'budget') if mapping.get(k)]
    if len(assigned)!=len(set(assigned)):raise ValueError('Date, account, actual, budget and currency must use separate columns.')
    dates=raw[mapping['date']]
    if pd.api.types.is_numeric_dtype(dates):raise ValueError('Numeric dates are ambiguous. Supply real dates or explicitly formatted text dates.')
    fmt=config.get('date_format','%Y-%m-%d')
    if fmt not in ('%Y-%m-%d','%d/%m/%Y','%m/%d/%Y'):raise ValueError('Choose an explicit reporting date format.')
    parsed=pd.to_datetime(dates,format=fmt,errors='coerce')
    if parsed.isna().any():raise ValueError('Every source row needs a valid reporting date in the chosen format.')
    if getattr(parsed.dt,'tz',None) is not None:raise ValueError('Use local reporting dates without timezone offsets.')
    actual=pd.to_numeric(raw[mapping['actual']],errors='coerce')
    if not np.isfinite(actual.astype(float)).all():raise ValueError('Every actual amount must be a finite number; no rows are silently excluded.')
    budget=pd.Series(np.nan,index=raw.index)
    if mapping.get('budget'):
        values=raw[mapping['budget']];present=~blank(values)
        budget=pd.to_numeric(values.mask(~present),errors='coerce')
        if not np.isfinite(budget[present].astype(float)).all():raise ValueError('Non-blank budget amounts must be finite numbers.')
    accounts=raw[mapping['account']].astype('string')
    if blank(accounts).any():raise ValueError('Every source row needs an account identifier.')
    currencies=raw[mapping['currency']].astype('string')
    if not currencies.str.fullmatch('[A-Z]{3}').fillna(False).all():raise ValueError('Use uppercase three-letter currency codes. No currency conversion is inferred.')
    entity=config.get('entity','').strip()
    if not entity:raise ValueError('Enter the legal entity or reporting entity represented by this source.')
    unit_col=mapping.get('business_unit')
    if unit_col:
        if unit_col not in raw or blank(raw[unit_col]).any():raise ValueError('Every row needs a business unit in the selected column.')
        units=raw[unit_col].astype('string').to_numpy()
    else:
        unit=config.get('business_unit','').strip()
        if not unit:raise ValueError('Enter a business-unit label or map a business-unit column.')
        units=[unit]*len(raw)
    lines=[];signs=[];reasons=[]
    for account in accounts:
        rule=rules.get(str(account),{})
        line=rule.get('line',UNMAPPED);sign=rule.get('sign',1)
        if line not in (*LINES,EXCLUDE,UNMAPPED):raise ValueError('Map each account to a supported reporting line or explicitly exclude it.')
        if sign not in (1,-1):raise ValueError('Sign multipliers must be +1 or -1.')
        reason=rule.get('reason','').strip()
        if line==EXCLUDE and not reason:raise ValueError('An excluded account needs an explicit reason.')
        lines.append(line);signs.append(sign);reasons.append(reason)
    detail=pd.DataFrame({'Source':source,'Source row':np.arange(len(raw)),
        'Original index':raw.index.astype(str),'Period':parsed.dt.to_period('M').astype(str).to_numpy(),
        'Entity':entity,'Business unit':units,'Currency':currencies.to_numpy(),
        'Account':accounts.to_numpy(),'Reporting line':lines,'Sign multiplier':signs,
        'Exclusion reason':reasons,'Original actual':actual.to_numpy(),'Original budget':budget.to_numpy()})
    detail['Status']=np.where(detail['Reporting line'].eq(UNMAPPED),'Unmapped',np.where(detail['Reporting line'].eq(EXCLUDE),'Excluded','Included'))
    detail['Actual']=detail['Original actual']*detail['Sign multiplier']
    detail['Budget']=detail['Original budget']*detail['Sign multiplier']
    direction=detail['Reporting line'].map(lambda x:-1 if x in EXPENSES else 1)
    detail['Profit impact']=detail['Actual']*direction
    detail.loc[detail.Status!='Included','Profit impact']=np.nan
    return detail


def strict_sum(s):return s.sum() if len(s)>0 and s.notna().all() else np.nan


def reconcile_sources(detail):
    """Reconcile using ORIGINAL signs; sign-normalized profit is a separate bridge."""
    rows=[]
    for key,group in detail.groupby(['Source','Period','Currency'],dropna=False,sort=True):
        row=dict(zip(['Source','Period','Currency'],key))
        row['Source rows']=len(group)
        for status in ('Included','Excluded','Unmapped'):
            part=group[group.Status==status]
            row[status+' rows']=len(part)
            row[status+' actual (source signs)']=float(part['Original actual'].sum())
            row[status+' budget (source signs)']=strict_sum(part['Original budget']) if len(part) else 0.0
        row['Source actual']=float(group['Original actual'].sum())
        row['Actual difference']=row['Source actual']-sum(row[s+' actual (source signs)'] for s in ('Included','Excluded','Unmapped'))
        row['Source budget']=strict_sum(group['Original budget'])
        accounted=[row[s+' budget (source signs)'] for s in ('Included','Excluded','Unmapped')]
        row['Budget difference']=row['Source budget']-sum(accounted) if all(pd.notna(v) for v in accounted) else np.nan
        row['Included profit impact']=group.loc[group.Status=='Included','Profit impact'].sum()
        rows.append(row)
    return pd.DataFrame(rows)


def statement_table(detail,zero_missing=False):
    """One currency/scope at a time; no cross-currency aggregate."""
    if detail.empty:raise ValueError('No source rows match the reporting filters.')
    if detail.Currency.nunique()!=1:raise ValueError('Select one reporting currency; amounts are never converted implicitly.')
    included=detail[detail.Status=='Included']
    values={};rows=[]
    for line in ORDER:
        if line in SUBTOTALS:
            components=SUBTOTALS[line]
            amounts={scenario:sum(values[k][scenario]*sign for k,sign in components.items())
                if all(pd.notna(values[k][scenario]) for k in components) else np.nan for scenario in ('Actual','Budget')}
            coverage='Calculated subtotal'
        else:
            selected=included[included['Reporting line']==line]
            amounts={s:strict_sum(selected[s]) if len(selected) else (0.0 if zero_missing else np.nan) for s in ('Actual','Budget')}
            coverage='Mapped activity' if len(selected) else ('Confirmed no activity' if zero_missing else 'Not provided')
        values[line]=amounts
        actual=amounts['Actual'];budget=amounts['Budget']
        variance=actual-budget if pd.notna(actual) and pd.notna(budget) else np.nan
        rows.append({'Line':line,**amounts,'Variance':variance,'Variance %':variance/abs(budget)*100 if pd.notna(variance) and budget!=0 else np.nan,'Coverage':coverage})
    return pd.DataFrame(rows)


def check_report(detail,zero_missing):
    if detail.empty:raise ValueError('There are no source rows to report.')
    recon=reconcile_sources(detail)
    issues=[]
    unmapped=int((detail.Status=='Unmapped').sum())
    if unmapped:issues.append(f'{unmapped} rows have unmapped accounts. Assign or explicitly exclude every account before approval.')
    if not np.allclose(recon['Actual difference'],0,atol=1e-8,rtol=0):issues.append('Source actual reconciliation has a difference.')
    if not (detail.Status=='Included').any():issues.append('No income-statement activity is included.')
    tables=[]
    for (period,currency),group in detail.groupby(['Period','Currency']):
        monthly=statement_table(group,zero_missing)
        if pd.isna(monthly.loc[monthly.Line=='Net profit','Actual'].iloc[0]):
            issues.append(f'{period} {currency}: reporting lines are missing. Supply them or explicitly confirm no activity; a later month does not fill earlier gaps.')
    for currency,group in detail.groupby('Currency'):
        table=statement_table(group,zero_missing)
        table.insert(0,'Currency',currency);tables.append(table)
        net=table.loc[table.Line=='Net profit','Actual'].iloc[0]
        if pd.isna(net):issues.append(f'{currency}: actual subtotals are incomplete. Supply the missing reporting lines or explicitly confirm they have no activity.')
        elif not np.isclose(net,group['Profit impact'].sum(),atol=1e-8,rtol=0):issues.append(f'{currency}: net profit does not reconcile to the row-level profit-impact bridge.')
    return pd.concat(tables,ignore_index=True),recon,issues


def approve_report(state,detail,config,signature,current_signature,source_fingerprints):
    if signature!=current_signature:raise ValueError('The inputs changed. Preview and review the report again.')
    tables,recon,issues=check_report(detail,config.get('zero_missing',False))
    if issues:raise ValueError(' '.join(issues))
    snapshot={'detail':detail.copy(deep=True),'tables':tables.copy(deep=True),'reconciliation':recon.copy(deep=True),
        'config':copy.deepcopy(config),'source_fingerprints':dict(source_fingerprints),
        'approved_at':datetime.now(timezone.utc).isoformat(),'signature':signature}
    state.setdefault('income_statement_reports',[]).append(snapshot)
    return snapshot


def reject_overlapping_sources(selected,lineage):
    seen=set()
    for name in selected:
        parents=set(lineage.get(name,{name}))
        if seen&parents:raise ValueError('Selected inputs share original-source lineage. Choose either an original or its prepared copy to avoid double counting.')
        seen.update(parents)
