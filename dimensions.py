"""Explicitly retained business dimensions, carried with each approved fact row."""
import pandas as pd

PREFIX='dimension::'


def dimension_choices(data):
    result={c[len(PREFIX):]:c for c in data if c.startswith(PREFIX) and data[c].notna().any()}
    # Older snapshots have no dimension metadata. Keep their real mapped dimension
    # available, without presenting synthetic All/measure defaults as extra fields.
    if not any(c.startswith(PREFIX) for c in data):
        if 'entity' in data and data.entity.notna().any() and not data.entity.eq('All').all():result['Country']='entity'
        if 'category' in data and data.category.notna().any() and not data.category.eq(data['measure']).all():result['Category']='category'
    if 'source' in data:result['Source']='source'
    return result


def retain_dimensions(result,raw,dimensions):
    used=set()
    for label,col in (dimensions or {}).items():
        label=str(label).strip()
        if not label or label.casefold() in used or label.casefold() in ('source','measure','currency','date','actual','budget','rows','variance','variance %','dimension','month','change','contribution %','first','second'):
            raise ValueError('Use distinct business dimension labels; Source and financial field names are reserved.')
        if col not in raw:raise ValueError(f'Dimension column is missing: {col}')
        used.add(label.casefold())
        # Harmonization retains every row in the publication path; positional
        # assignment also supports non-unique source indices without a join.
        if len(result)!=len(raw):raise ValueError('Cannot retain dimensions after excluding source rows.')
        result[PREFIX+label]=raw[col].astype('string').replace(r'^\s*$',pd.NA,regex=True).to_numpy()
    return result


def display_group(data,column,label):
    from engine import grouped
    return grouped(data,column).rename(columns={column:label})
