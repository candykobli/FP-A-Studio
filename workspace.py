"""Non-destructive quality checks and explicit publication controls."""
import hashlib
import numpy as np
import pandas as pd
from engine import harmonize


def fingerprint(df):
    return hashlib.sha256((df.to_json(date_format='iso', orient='split') + str(df.dtypes)).encode()).hexdigest()


def quality(df):
    rows = []
    for col in df:
        s = df[col]
        text = s.astype('string')
        blank = s.isna() | text.str.strip().eq('').fillna(False)
        whitespace = (text.ne(text.str.strip()) & ~blank).fillna(False)
        present = s[~blank]
        numeric = pd.to_numeric(present, errors='coerce')
        mixed = int(numeric.isna().sum()) if numeric.notna().any() else 0
        rows.append({'Column': str(col), 'Type': str(s.dtype), 'Blanks': int(blank.sum()),
                     'Whitespace': int(whitespace.sum()), 'Mixed numeric values': mixed})
    table = pd.DataFrame(rows)
    duplicates = int(df.duplicated(keep=False).sum())
    issues = duplicates + (int(table[['Blanks', 'Whitespace', 'Mixed numeric values']].sum().sum()) if len(table) else 0)
    return table, duplicates, issues


def prepare(df, mapping, source, measure, sign=1, dimensions=None):
    if df.empty or not df.columns.is_unique:
        raise ValueError('Use a non-empty table with unique column names.')
    if not measure.strip():
        raise ValueError('Enter a financial measure name.')
    from measure_catalog import validate_source_measure
    validate_source_measure(measure)
    roles = [v for k,v in mapping.items() if v and k!='measure']
    if len(roles) != len(set(roles)):
        raise ValueError('Map each source column to only one financial role.')
    if mapping.get('measure'):
        col=mapping['measure']
        if col not in df:raise ValueError('Choose an existing measure-name column.')
        if col in [mapping.get(k) for k in ('date','actual','budget','currency')]:
            raise ValueError('The measure-name column must be separate from date, amounts and currency.')
        if (df[col].isna() | df[col].astype('string').str.strip().eq('').fillna(False)).any():
            raise ValueError('Every row needs a measure name; blank names are not published.')
        for label in df[col].astype('string').str.strip().unique():validate_source_measure(label)
    for role in ('date', 'actual'):
        if not mapping.get(role):
            raise ValueError('Map both a reporting date and an actual amount.')
    if mapping.get('actual') == 'converted_amount':
        if mapping.get('currency') != 'reporting_currency':
            raise ValueError('For converted amounts, map reporting_currency as currency.')
        if mapping.get('budget'):
            raise ValueError('Do not compare converted actuals with a native-currency budget. Leave budget unmapped or prepare both scenarios in the same reporting currency first.')
    dates = pd.to_datetime(df[mapping['date']], errors='coerce')
    if dates.isna().any():
        raise ValueError(f'{int(dates.isna().sum())} invalid or blank dates. Correct them before approval; rows will not be silently dropped.')
    for role in ('actual', 'budget'):
        if mapping.get(role):
            values = df[mapping[role]]
            numeric = pd.to_numeric(values, errors='coerce')
            bad = ~np.isfinite(numeric.astype(float))
            if role == 'budget':
                bad &= values.notna() & values.astype('string').str.strip().ne('').fillna(False)
            if bad.any():
                raise ValueError(f'{int(bad.sum())} invalid {role} amounts. Correct them before approval.')
    result = harmonize(df, mapping, source, measure.strip(), sign)
    result['measure_origin']='Source-provided'
    result['measure_type']='amount'
    result['measure_unit']=result.measure.map(lambda x:'count' if str(x).casefold() in ('headcount','units sold') else 'amount')
    ccy = result.currency.astype('string')
    if (~ccy.str.fullmatch('[A-Z]{3}').fillna(False)).any():
        raise ValueError('Map a currency column containing uppercase three-letter currency codes for every row.')
    if len(result) != len(df):
        raise ValueError('Mapping would exclude rows. Correct the input first.')
    from dimensions import retain_dimensions
    result=retain_dimensions(result,df,dimensions)
    totals = result.groupby(['measure','currency']).agg(Rows=('actual', 'size'), Actual=('actual', 'sum'),
        Budget=('budget', lambda x: x.sum() if x.notna().all() else np.nan)).reset_index()
    return result, totals


def prepare_measures(df,shared_mapping,source,specs,dimensions=None):
    """Explicit wide-to-long mapping: each chosen amount column becomes one measure."""
    if not specs:raise ValueError('Define at least one measure.')
    names=[s['name'].strip().casefold() for s in specs]
    if any(not n for n in names) or len(set(names))!=len(names):
        raise ValueError('Enter a distinct, non-blank name for each measure.')
    amounts=[s.get(k) for s in specs for k in ('actual','budget') if s.get(k)]
    if len(set(amounts))!=len(amounts):
        raise ValueError('Each amount column can belong to only one measure and scenario; reusing it could double count.')
    outputs=[]
    for spec in specs:
        mapping={k:v for k,v in shared_mapping.items() if k not in ('actual','budget','measure')}
        mapping.update(actual=spec.get('actual'),budget=spec.get('budget'))
        facts,_=prepare(df,mapping,source,spec['name'],spec.get('sign',1),dimensions=dimensions)
        outputs.append(facts)
    result=pd.concat(outputs,ignore_index=True)
    totals=result.groupby(['measure','currency']).agg(Rows=('actual','size'),Actual=('actual','sum'),
        Budget=('budget',lambda x:x.sum() if x.notna().all() else np.nan)).reset_index()
    return result,totals


def publish(state, name, data, signature, current_signature, parents, replace=False):
    if signature != current_signature:
        raise ValueError('The draft changed. Verify it again before publishing.')
    conflicts = [n for n, p in state['published_parents'].items() if n != name and set(p) & set(parents)]
    if conflicts and not replace:
        raise ValueError('This overlaps published inputs: ' + ', '.join(conflicts) + '. Explicitly replace them to avoid double counting.')
    for n in conflicts:
        state['facts'].pop(n, None)
        state['published_parents'].pop(n, None)
    state['facts'][name] = data.copy(deep=True)
    state['published_parents'][name] = set(parents)
