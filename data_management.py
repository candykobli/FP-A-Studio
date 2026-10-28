"""Auditable, opt-in controls for joining, duplicates, FX and reconciliation."""
import pandas as pd
import numpy as np


def join_candidates(left, right):
    """Suggest common keys; return observed match coverage and cardinality."""
    rows=[]
    for key in sorted(set(left.columns)&set(right.columns)):
        a=left[key].dropna(); b=right[key].dropna()
        if a.empty or b.empty: continue
        # Numeric amounts are rarely meaningful join keys; don't suggest them.
        if pd.api.types.is_float_dtype(a) or pd.api.types.is_float_dtype(b): continue
        overlap=len(set(a.astype(str))&set(b.astype(str)))
        if not overlap:continue
        rows.append({'Key':key,'Left unique':a.is_unique,'Right unique':b.is_unique,
                     'Left match %':round(a.astype(str).isin(set(b.astype(str))).mean()*100,1),
                     'Right match %':round(b.astype(str).isin(set(a.astype(str))).mean()*100,1),
                     'Cardinality':('1:1' if a.is_unique and b.is_unique else '1:many' if a.is_unique else 'many:1' if b.is_unique else 'many:many')})
    return pd.DataFrame(rows)


def safe_join(left,right,left_key,right_key,how='left',allow_many_to_many=False,max_rows=500000):
    if left_key not in left or right_key not in right:raise ValueError('Choose valid join keys.')
    if how not in ('left','inner','outer'):raise ValueError('Unsupported join type.')
    a=left.copy();b=right.copy()
    # Never match null keys (pandas otherwise matches null to null).
    a['_fpa_left_row']=np.arange(len(a))
    b['_fpa_right_row']=np.arange(len(b))
    a_null=a[a[left_key].isna()];a_valid=a[a[left_key].notna()]
    b_null=b[b[right_key].isna()];b_valid=b[b[right_key].notna()]
    many_a=a_valid[left_key].duplicated().any();many_b=b_valid[right_key].duplicated().any()
    if many_a and many_b and not allow_many_to_many:
        raise ValueError('Many-to-many join blocked: duplicate keys on both sides could multiply financial amounts.')
    counts_a=a_valid.groupby(left_key,dropna=False).size()
    counts_b=b_valid.groupby(right_key,dropna=False).size()
    projected=int(sum(int(v)*int(counts_b.get(k,0)) for k,v in counts_a.items()))
    if how in ('left','outer'):projected+=int(sum(v for k,v in counts_a.items() if k not in counts_b))+len(a_null)
    if how=='outer':projected+=int(sum(v for k,v in counts_b.items() if k not in counts_a))+len(b_null)
    if projected>max_rows:raise ValueError(f'Join would create approximately {projected:,} rows; safety limit is {max_rows:,}.')
    result=a_valid.merge(b_valid,left_on=left_key,right_on=right_key,how=how,suffixes=('_left','_right'),indicator=True)
    if how in ('left','outer') and not a_null.empty:
        # Merge with empty right schema so columns and indicator are consistent.
        extra=a_null.merge(b_valid.iloc[:0],left_on=left_key,right_on=right_key,how='left',suffixes=('_left','_right'),indicator=True)
        result=pd.concat([result,extra],ignore_index=True)
    if how=='outer' and not b_null.empty:
        extra=a_valid.iloc[:0].merge(b_null,left_on=left_key,right_on=right_key,how='right',suffixes=('_left','_right'),indicator=True)
        result=pd.concat([result,extra],ignore_index=True)
    audit={'Left rows':len(left),'Right rows':len(right),'Output rows':len(result),
           'Matched output rows':int((result['_merge']=='both').sum()),
           'Unmatched left rows':int((result['_merge']=='left_only').sum()),
           'Unmatched right rows':int((result['_merge']=='right_only').sum()),
           'Cardinality':'many:many' if many_a and many_b else 'many:1' if many_a else '1:many' if many_b else '1:1'}
    return result.drop(columns=['_fpa_left_row','_fpa_right_row']),audit


def duplicate_review(df,keys):
    if not keys or any(k not in df for k in keys):raise ValueError('Select valid duplicate identification columns.')
    flags=df.duplicated(subset=keys,keep=False)
    groups=df.loc[flags].groupby(keys,dropna=False).size().rename('Occurrences').reset_index()
    return df.loc[flags].copy(),groups.sort_values('Occurrences',ascending=False)


def deduplicate(df,keys,keep='first'):
    if keep not in ('first','last'):raise ValueError('Unsupported retention rule.')
    duplicates,_=duplicate_review(df,keys)
    result=df.drop_duplicates(subset=keys,keep=keep).copy()
    return result,{'Original rows':len(df),'Rows removed':len(df)-len(result),'Remaining rows':len(result),'Flagged rows':len(duplicates)}


def convert_currency(df,rates,amount_col='actual',currency_col='currency',date_col='date',target='EUR',rate_type='monthly_average'):
    """Convert using user-supplied, auditable rates: 1 unit source = rate units target.
    Rates must contain date,currency,target_currency,rate,rate_type.
    Missing rates remain null and are reported; never silently use rate=1.
    """
    required={'date','currency','target_currency','rate','rate_type'}
    if not required.issubset(rates.columns):raise ValueError('Rate table requires date, currency, target_currency, rate, rate_type.')
    if any(c not in df for c in (amount_col,currency_col,date_col)):raise ValueError('Missing source amount, currency or date column.')
    if rate_type not in ('daily','monthly_average','closing'):raise ValueError('Invalid rate type.')
    r=rates.copy();r['date']=pd.to_datetime(r['date'],errors='coerce');r['rate']=pd.to_numeric(r['rate'],errors='coerce')
    r=r[(r['target_currency']==target)&(r['rate_type']==rate_type)].copy()
    if r['date'].isna().any() or r['rate'].isna().any() or (r['rate']<=0).any():raise ValueError('Rate dates must be valid and rates positive.')
    d=df.copy();d[date_col]=pd.to_datetime(d[date_col],errors='coerce')
    d['_fpa_fx_key']=d[date_col].dt.to_period('M').astype(str) if rate_type=='monthly_average' else d[date_col].dt.strftime('%Y-%m-%d')
    r['_fpa_fx_key']=r['date'].dt.to_period('M').astype(str) if rate_type=='monthly_average' else r['date'].dt.strftime('%Y-%m-%d')
    # Closing rates require an explicit date match, never implicit month-end assumption.
    if r.duplicated(['currency','_fpa_fx_key']).any():raise ValueError('Multiple FX rates for the same currency and period; resolve before conversion.')
    r=r.rename(columns={'currency':'_fpa_fx_currency','rate':'fx_rate'})
    d=d.merge(r[['_fpa_fx_currency','_fpa_fx_key','fx_rate']],left_on=[currency_col,'_fpa_fx_key'],right_on=['_fpa_fx_currency','_fpa_fx_key'],how='left',validate='many_to_one')
    same=d[currency_col]==target
    d.loc[same,'fx_rate']=1.0
    d['converted_amount']=pd.to_numeric(d[amount_col],errors='coerce')*d['fx_rate']
    d['reporting_currency']=target
    audit={'Rows':len(d),'Converted rows':int(d['converted_amount'].notna().sum()),'Missing FX rates':int((~same & d['fx_rate'].isna()).sum()),'Rate type':rate_type,'Target':target}
    return d.drop(columns=['_fpa_fx_currency','_fpa_fx_key']),audit


def reconcile(left,right,keys,left_amount,right_amount,tolerance=0.01):
    """Aggregate both sides before comparing, retaining missing groups and counts."""
    if not keys:raise ValueError('Select at least one reconciliation key.')
    if tolerance<0:raise ValueError('Tolerance cannot be negative.')
    for df,amount in ((left,left_amount),(right,right_amount)):
        if any(k not in df for k in keys) or amount not in df:raise ValueError('Missing reconciliation columns.')
    a=left.copy();b=right.copy()
    a['_amount']=pd.to_numeric(a[left_amount],errors='coerce');b['_amount']=pd.to_numeric(b[right_amount],errors='coerce')
    if a['_amount'].isna().any() or b['_amount'].isna().any():raise ValueError('Amounts contain null or non-numeric values; resolve before reconciliation.')
    x=a.groupby(keys,dropna=False).agg(Left=('_amount','sum'),Left_rows=('_amount','size')).reset_index()
    y=b.groupby(keys,dropna=False).agg(Right=('_amount','sum'),Right_rows=('_amount','size')).reset_index()
    out=x.merge(y,on=keys,how='outer',indicator=True,validate='one_to_one')
    out['Difference']=out['Left'].fillna(0)-out['Right'].fillna(0)
    out['Status']=np.select([out['_merge']=='left_only',out['_merge']=='right_only',out['Difference'].abs()<=tolerance],['Missing right','Missing left','Matched'],default='Difference')
    audit={'Left total':float(a['_amount'].sum()),'Right total':float(b['_amount'].sum()),'Net difference':float(a['_amount'].sum()-b['_amount'].sum()),'Matched groups':int((out['Status']=='Matched').sum()),'Exception groups':int((out['Status']!='Matched').sum()),'Tolerance':tolerance}
    return out.drop(columns=['_merge']),audit
