"""Source-independent profiling, semantic mapping, and deterministic FP&A calculations."""
import ast
import io
import json
import operator
import re
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

ALIASES = {
    'date': ['date','period','month','posting_date','transaction_date','fiscal_date','reporting_date'],
    'actual': ['actual','actuals','amount','actual_amount','revenue','net_sales','sales','net_revenue','act_rev_eur','revenueamount','actual_expense','expense','cost','manufacturing_cost'],
    'budget': ['budget','plan','planned','target','forecast','budget_amount','planned_expense','sales_budget'],
    'category': ['account','account_name','metric','measure','kpi','line_item','expense_category','category'],
    'entity': ['country','region','department','business_unit','product','factory','cost_center','entity'],
    'scenario': ['scenario','version','type'],
    'currency': ['currency','ccy','currency_code'],
}


def normalize_name(s):
    return re.sub(r'[^a-z0-9]+','_',str(s).strip().lower()).strip('_')


def suggestions(df):
    columns = {normalize_name(c): c for c in df.columns}
    result = {}
    for role, aliases in ALIASES.items():
        result[role] = next((columns[a] for a in aliases if a in columns), None)
    return result


def profile(df):
    rows = []
    for c in df.columns:
        s = df[c]
        rows.append({'Column':str(c), 'Type':str(s.dtype), 'Missing %':round(s.isna().mean()*100,1),
                     'Unique':int(s.nunique(dropna=True)), 'Example':str(s.dropna().iloc[0])[:65] if s.notna().any() else '—'})
    return pd.DataFrame(rows)


def read_upload(name, data, sheet=None):
    lower=name.lower()
    if lower.endswith(('.xlsx','.xls')):
        return pd.read_excel(io.BytesIO(data), sheet_name=sheet or 0)
    if lower.endswith('.csv'):
        return pd.read_csv(io.BytesIO(data), sep=None, engine='python')
    if lower.endswith('.json'):
        obj=json.loads(data.decode('utf-8-sig'))
        if isinstance(obj,dict):
            for key in ('data','records','results','items'):
                if isinstance(obj.get(key),list): obj=obj[key]; break
        return pd.json_normalize(obj)
    raise ValueError('Supported uploads: Excel, CSV, JSON')


def harmonize(df, mapping, source_name, measure_name='Amount', sign=1.0):
    """Create a common *long-form* fact table. Missing optional fields stay null.
    A mapping may include date, actual, budget, category, entity, currency.
    """
    if not mapping.get('date') or not mapping.get('actual'):
        raise ValueError('Map at least a date and an actual amount.')
    result=pd.DataFrame(index=df.index)
    result['date']=pd.to_datetime(df[mapping['date']],errors='coerce')
    for col in ('actual','budget'):
        result[col]=pd.to_numeric(df[mapping[col]],errors='coerce')*sign if mapping.get(col) else np.nan
    for col, default in [('category',measure_name),('entity','All'),('currency','Unspecified')]:
        result[col]=df[mapping[col]].astype('string').fillna(default) if mapping.get(col) else default
    result['source']=source_name
    result['measure']=df[mapping['measure']].astype('string').str.strip() if mapping.get('measure') else measure_name
    result['source_row']=df.index.astype(str)
    result=result.dropna(subset=['date','actual']).reset_index(drop=True)
    if result.empty: raise ValueError('No rows with both valid dates and actual amounts.')
    return result


def combine(facts):
    if not facts: return pd.DataFrame()
    return pd.concat(facts,ignore_index=True)


def summary(df):
    from measure_math import financial_summary
    return financial_summary(df)


def grouped(df, by='entity'):
    rows=[]
    for key,part in df.groupby(by,dropna=False):
        s=summary(part)
        rows.append({by:key,'Actual':s['actual'],'Budget':s['budget'],'Rows':s['rows'],'Variance':s['variance'],'Variance %':s['variance_pct']})
    return pd.DataFrame(rows,columns=[by,'Actual','Budget','Rows','Variance','Variance %'])


def monthly(df):
    d=df.copy(); d['Month']=d['date'].dt.to_period('M').dt.to_timestamp()
    return grouped(d,'Month')[['Month','Actual','Budget']]


def compare(df, start_a, end_a, start_b, end_b, dimension='entity'):
    a=df[df['date'].dt.date.between(start_a,end_a)]
    b=df[df['date'].dt.date.between(start_b,end_b)]
    left=grouped(a,dimension).set_index(dimension)['Actual'].rename('First')
    right=grouped(b,dimension).set_index(dimension)['Actual'].rename('Second')
    out=pd.concat([left,right],axis=1)
    out=out.apply(pd.to_numeric,errors='coerce')
    from measure_math import is_ratio
    ratio=is_ratio(df)
    if not ratio:out=out.fillna(0)
    out=out.reset_index()
    out['Change']=out['Second']-out['First']
    net=out['Change'].sum()
    out['Contribution %']=out['Change']/net*100 if not ratio and abs(net)>1e-12 else np.nan
    first,second=summary(a),summary(b)
    if ratio:
        for part,metrics in ((a,first),(b,second)):
            if part.empty:metrics.update(actual=None,budget=None,variance=None,variance_pct=None,unit='%',variance_unit='pp')
    return out.sort_values('Change',ascending=False), first, second


OPS={ast.Add:operator.add,ast.Sub:operator.sub,ast.Mult:operator.mul,ast.Div:operator.truediv,
     ast.Pow:operator.pow,ast.Mod:operator.mod,ast.USub:operator.neg,ast.UAdd:operator.pos}

def calculate(expression):
    """Safe arithmetic only: no eval, variables, calls or attribute access."""
    if len(expression)>160: raise ValueError('Expression too long')
    def walk(node):
        if isinstance(node,ast.Expression):return walk(node.body)
        if isinstance(node,ast.Constant) and type(node.value) in (int,float):return node.value
        if isinstance(node,ast.UnaryOp) and type(node.op) in (ast.USub,ast.UAdd):return OPS[type(node.op)](walk(node.operand))
        if isinstance(node,ast.BinOp) and type(node.op) in OPS:
            x,y=walk(node.left),walk(node.right)
            if type(node.op) is ast.Pow and abs(y)>12:raise ValueError('Exponent too large')
            if abs(x)>1e15 or abs(y)>1e15:raise ValueError('Numbers too large')
            return OPS[type(node.op)](x,y)
        raise ValueError('Only arithmetic operators and parentheses are supported')
    result=walk(ast.parse(expression,mode='eval'))
    if not np.isfinite(result):raise ValueError('Result is not finite')
    return result
