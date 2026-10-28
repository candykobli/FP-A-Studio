"""Local, rule-based financial mapping review; never executes generated code."""
import numpy as np
import pandas as pd
from engine import ALIASES, normalize_name
from workspace import fingerprint, prepare

ROLES=('date','actual','budget','category','entity','currency')
DATE_FORMATS={'ISO date (YYYY-MM-DD)':'%Y-%m-%d',
              'Day first (DD/MM/YYYY)':'%d/%m/%Y',
              'Month first (MM/DD/YYYY)':'%m/%d/%Y'}


def candidates(df):
    """Aliases propose meaning; neither numeric values nor column order prove it."""
    return {role:[c for c in df.columns if normalize_name(c) in ALIASES[role]] for role in ROLES}


def blank_mask(series):
    return series.isna() | series.astype('string').str.strip().eq('').fillna(False)


def diagnose(df,mapping,measure='Amount',grain=()):
    findings=[]
    def add(level,area,issue,next_step):
        findings.append({'Priority':level,'Area':area,'Finding':issue,'Suggested next step':next_step})
    choices=candidates(df)
    used=[v for v in mapping.values() if v is not None]
    if len(used)!=len(set(used)):
        add('Blocker','Mapping','One column is assigned to several financial roles.','Choose a different column for each role.')
    normalized=[normalize_name(c) for c in df]
    if len(set(normalized))!=len(normalized) or any(not n for n in normalized):
        add('Review','Names','Standardized column names would collide or be empty.','Rename these columns individually before standardizing.')
    elif list(df.columns)!=normalized:
        add('Suggestion','Names','Column names use inconsistent spaces, case or punctuation.','Preview standardized column names; meaning is unchanged.')
    for role in ROLES:
        col=mapping.get(role)
        if not col:
            if role in ('date','actual','currency'):
                add('Blocker',role.title(),'No column selected.','Choose its meaning explicitly; the assistant cannot infer your accounting policy.')
            if len(choices[role])>1:
                add('Review',role.title(),'Several plausible columns: '+', '.join(map(str,choices[role])), 'Select the intended field. Names alone do not determine meaning.')
            continue
        if col not in df:
            add('Blocker',role.title(),'The mapped column does not exist.','Choose an existing column.'); continue
        s=df[col]; present=s[~blank_mask(s)]
        if role in ('actual','budget'):
            n=pd.to_numeric(present,errors='coerce')
            invalid=int((~np.isfinite(n.astype(float))).sum())
            if invalid:add('Blocker',role.title(),f'{invalid} non-blank amounts are not finite plain numbers.','Correct them manually. Separators, symbols and locale conventions are not guessed.')
            if role=='actual' and blank_mask(s).any():
                add('Blocker','Actual',f'{int(blank_mask(s).sum())} amounts are blank.','Correct the source copy; missing actuals will not be replaced by zero.')
            if role=='budget' and blank_mask(s).any():
                add('Review','Budget','Budget coverage is incomplete.','Missing budget stays unknown, not zero.')
            if not invalid and not pd.api.types.is_numeric_dtype(s):
                add('Suggestion',role.title(),'Amounts are stored as text.','Preview numeric conversion only if every non-blank value parses.')
            if (n<0).any() and (n>0).any():
                add('Review',role.title(),'Positive and negative amounts are both present.','Confirm reversals, credits and the source sign convention. Signs are never inferred.')
        if role=='date':
            if blank_mask(s).any():add('Blocker','Date','Some reporting dates are blank.','Correct the missing dates before publishing.')
            if pd.api.types.is_numeric_dtype(s):
                add('Blocker','Date','Dates are numeric; these may be spreadsheet serials or year codes.','Convert them with a known date convention manually. Numeric dates are not guessed.')
            elif not pd.api.types.is_datetime64_any_dtype(s):
                non_iso=~present.astype('string').str.fullmatch(r'\d{4}-\d{2}-\d{2}').fillna(False)
                if non_iso.any():
                    add('Review','Date','Text dates need an explicit interpretation.','Select ISO, day-first or month-first. Review the parsed dates in the preview.')
                else:
                    parsed=pd.to_datetime(present,format='%Y-%m-%d',errors='coerce')
                    if parsed.isna().any():add('Blocker','Date','Some ISO dates are invalid.','Correct invalid calendar dates.')
        if role=='currency':
            cleaned=s.astype('string').str.strip().str.upper()
            if (~cleaned.str.fullmatch('[A-Z]{3}').fillna(False)).any():
                add('Blocker','Currency','Missing or malformed currency codes.','Use explicit three-letter codes. Currency symbols are ambiguous and are not translated.')
            elif s.astype('string').ne(cleaned).any():
                add('Suggestion','Currency','Currency codes have spacing or case differences.','Preview trimming and uppercase normalization; this does not convert amounts.')
            if cleaned.nunique()>1:add('Review','Currency','Multiple currencies are present.','Keep currency in your business keys and compare totals separately.')
    whitespace=sum(int(s.map(lambda v:isinstance(v,str) and v!=v.strip()).sum()) for _,s in df.items())
    if whitespace:add('Suggestion','Values',f'{whitespace} cells have leading or trailing whitespace.','Preview trimming text values; repeated rows are still retained.')
    if not measure.strip() or measure.strip().lower() in ('amount','value','metric','profit','margin','profit margin'):
        add('Review','Measure','The measure does not yet have a clear business definition.','Enter Revenue, Expenses, Headcount or another precise measure; confirm its unit and meaning.')
    if not grain:
        add('Review','Business keys','The meaning of one row has not been defined.','Select the fields identifying a row, such as transaction ID or date + entity + account. These are review keys, not a deletion rule.')
    elif any(c not in df for c in grain):
        add('Blocker','Business keys','A selected key column is missing.','Choose valid columns.')
    else:
        blanks=sum(int(blank_mask(df[c]).sum()) for c in grain)
        repeated=int(df.duplicated(list(grain),keep=False).sum())
        if blanks:add('Review','Business keys',f'{blanks} key cells are blank.','Check missing identifiers; they may group unrelated records together.')
        if repeated:add('Review','Business keys',f'{repeated} rows repeat the selected business keys.','Inspect their grain. They may be valid separate transactions; no rows will be deleted.')
    return pd.DataFrame(findings,columns=['Priority','Area','Finding','Suggested next step'])


def repair_preview(df,mapping,*,rename=False,trim=False,uppercase_currency=False,numeric=False,date_format=None):
    """All-or-nothing, opt-in transformations. No row drops, joins or sign changes."""
    before=fingerprint(df)
    out=df.copy(deep=True); log=[]; mapped=dict(mapping)
    for role,col in mapped.items():
        if col is not None and col not in out:raise ValueError(f'Missing {role} column: {col}')
    date_col=mapped.get('date')
    if date_col and not date_format and not pd.api.types.is_datetime64_any_dtype(out[date_col]):
        values=out[date_col]
        if pd.api.types.is_numeric_dtype(values):raise ValueError('Numeric dates are not interpreted automatically.')
        text=values[~blank_mask(values)].astype('string').str.strip()
        if not text.str.fullmatch(r'\d{4}-\d{2}-\d{2}').fillna(False).all():
            raise ValueError('Choose an explicit reporting date format before previewing non-ISO text dates.')
    if trim:
        for c in out:
            out[c]=out[c].map(lambda v:v.strip() if isinstance(v,str) else v)
        log.append('Trimmed leading/trailing whitespace in text cells.')
    c=mapped.get('currency')
    if uppercase_currency and c:
        out[c]=out[c].astype('string').str.upper()
        log.append('Uppercased currency codes; no FX conversion performed.')
    if numeric:
        for role in ('actual','budget'):
            c=mapped.get(role)
            if c is None:continue
            mask=blank_mask(out[c])
            if role=='actual' and mask.any():raise ValueError('Actual amounts contain blanks; correct them manually.')
            values=pd.to_numeric(out[c].mask(mask),errors='coerce')
            if (~np.isfinite(values[~mask].astype(float))).any():
                raise ValueError(f'{role.title()} has invalid numbers. No conversion applied. Correct them manually; separators and currency symbols are not guessed.')
            out[c]=values
            log.append(f'Converted {role} to numbers; missing budget remains unknown.')
    if date_format:
        if date_format not in DATE_FORMATS.values():raise ValueError('Choose one of the supported explicit date formats.')
        c=mapped.get('date')
        if not c:raise ValueError('Choose a reporting-date column first.')
        if pd.api.types.is_numeric_dtype(out[c]):raise ValueError('Numeric dates are not interpreted automatically.')
        # strptime formats alone allow some non-padded input; require the declared shape too.
        pattern=r'\d{4}-\d{2}-\d{2}' if date_format=='%Y-%m-%d' else r'\d{2}/\d{2}/\d{4}'
        if pd.api.types.is_datetime64_any_dtype(out[c]):parsed=out[c]
        else:
            text=out[c].astype('string')
            if not text.str.fullmatch(pattern).fillna(False).all():raise ValueError('Some dates do not match the selected format. No date conversion applied.')
            parsed=pd.to_datetime(text,format=date_format,errors='coerce')
        if parsed.isna().any():raise ValueError('Invalid calendar dates. No date conversion applied.')
        out[c]=parsed
        log.append('Parsed reporting dates using '+date_format+'.')
    renames={c:normalize_name(c) for c in out} if rename else {c:c for c in out}
    if rename:
        if any(not v for v in renames.values()) or len(set(renames.values()))!=len(renames):
            raise ValueError('Standardized names would be empty or duplicated. Rename the conflicting columns manually.')
        out=out.rename(columns=renames)
        mapped={k:renames.get(v,v) for k,v in mapped.items()}
        log.append('Standardized column names and updated the mapping references.')
    assert len(out)==len(df) and fingerprint(df)==before
    return out,mapped,renames,log


def verify_model(df,mapping,measure,sign):
    """The publication validator is the final authority, not the suggestions."""
    return prepare(df,mapping,'Model repair preview',measure,sign)
