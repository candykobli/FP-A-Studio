"""Grounded page questions with explicit scopes and deterministic calculations."""
import hashlib
import json
import re
import pandas as pd
from dimensions import dimension_choices,display_group
from engine import summary,monthly,calculate
from workspace import fingerprint,quality
from measure_math import is_ratio


def money(value):
    return 'unknown' if value is None or pd.isna(value) else f'{value:,.2f}'


def scope_label(data):
    if data is None or data.empty:return 'No approved financial records in this view.'
    return (f"{', '.join(map(str,data.measure.unique()))} · {', '.join(map(str,data.currency.unique()))} · "
            f"{data.date.min():%d %b %Y} to {data.date.max():%d %b %Y} · {len(data):,} records")


def answer_question(question,page,data=None,metadata=None,raw_sources=None):
    """Return text and optional supporting table; never mutate data or execute actions."""
    q=question.lower().strip(); meta=metadata or {}
    formula=('**Variance = Actual − Budget.**\n\n'
        '**Variance % = (Actual − Budget) ÷ |Budget| × 100.** '
        'With actual 120,000 and budget 100,000: variance is 20,000 and variance % is 20%. '
        'The percentage is undefined when budget is zero. Missing budget is unknown, not zero. '
        'A positive variance means actual exceeds budget; favorability depends on the measure and accounting convention.')
    if any(word in q for word in ('publish','approve','delete','remove rows','merge','change my','fix my')):
        if page=='Income statement':return 'Questions do not change or approve reports. Use Preview income statement and reconciliation, review all mappings and checks, then explicitly approve a snapshot on this page.',None
        return 'Questions do not change data or approve publication. Use the preview and approval controls in Data Workspace; originals remain unchanged.',None
    if page=='Income statement':
        rows=meta.get('income_statement',[])
        if not rows:return 'Load account-level activity, map every account to a reporting line or an explicit exclusion, then preview the reconciliation. Questions cannot approve a report. This first version is a management view before intercompany eliminations and FX translation.',None
        table=pd.DataFrame(rows)
        scope='**Report scope:** '+meta.get('report_scope','Current report selection')
        if 'ebitda' in q or 'cash flow' in q or 'balance sheet' in q:
            return scope+'\n\nThis first income statement does not separately model depreciation/amortization, cash flows or balance-sheet balances, so I cannot calculate those figures from these reporting lines. They require additional mapped data and schedules.',None
        if any(w in q for w in ('source','reconcil','exclude','unmapped')):
            recon=pd.DataFrame(meta.get('reconciliation',[]))
            return scope+'\n\nSource actual = included + excluded + unmapped, using original source signs. The row-level bridge retains source and row identifiers, account classifications, signs and exclusion reasons. Net profit separately equals the sum of included signed profit impacts. A zero difference verifies this mapping arithmetic, not the completeness of your accounting source.',recon
        if re.search(r'\b(?:in|for|from)\s+(?!this\b|the current\b|the selected\b|my report\b)',q):
            return scope+'\n\nUse the visible report filters to select an entity, business unit, month or currency before asking for its figures. I will not recalculate a different report scope from an ambiguous phrase.',None
        requested=next((line for line in sorted(table.Line,key=len,reverse=True) if line.lower() in q),'Net profit')
        from income_statement import SUBTOTALS
        record=table[table.Line==requested].iloc[0]
        text=scope+'\n\n**'+requested+'**: actual **'+money(record.Actual)+'**, budget **'+money(record.Budget)+'**.'
        if requested in SUBTOTALS:
            parts=SUBTOTALS[requested]
            text+='\n\n'+requested+' = '+' '.join(('+' if sign>0 and i else '−' if sign<0 else '')+' '+label for i,(label,sign) in enumerate(parts.items())).strip()+'.'
            text+='\n\nUsing this view: '+' '.join(('+' if sign>0 and i else '−' if sign<0 else '')+' '+money(table.loc[table.Line==label,'Actual'].iloc[0]) for i,(label,sign) in enumerate(parts.items())).strip()+' = '+money(record.Actual)+'.'
        else:text+='\n\nThis line sums its explicitly mapped account activity after the selected sign multipliers. Drill into this line on the page for original rows.'
        if 'variance' in q or 'budget' in q:
            text+='\n\n'+formula+'\n\nThis line: '+money(record.Actual)+' − '+money(record.Budget)+' = '+money(record.Variance)+'.'
            if pd.isna(record.Budget):text+=' Budget coverage is incomplete; variance is unknown.'
            elif record.Budget==0:text+=' Percentage variance is undefined at zero budget.'
            else:text+=' Percentage variance = '+money(record.Variance)+' ÷ |'+money(record.Budget)+'| × 100 = '+money(record['Variance %'])+'%.'
        text+='\n\nNo business cause, accounting completeness or statutory consolidation is inferred.'
        return text,table
    if page=='Data Workspace':
        if any(w in q for w in ('blank','whitespace','spacing','duplicate','repeat','flag','quality','issue','missing')):
            rows=[]
            for name,raw in (raw_sources or {}).items():
                report,duplicates,issues=quality(raw)
                for record in report.to_dict(orient='records'):rows.append({'Source':name,**record})
                rows.append({'Source':name,'Column':'Whole-row review','Repeated rows':duplicates})
            return ('These are quality checks for the selected workspace inputs, including unpublished working copies. '
                'Blanks and repeated keys may be legitimate. Whitespace is leading/trailing spacing; mixed numeric values indicate a column containing both numeric-looking and non-numeric values. No rows are removed automatically.'),pd.DataFrame(rows)
        if 'mapping' in q or 'model' in q:
            return ('Map the reporting date, actual, currency and optional budget. Confirm measure names and descriptive dimensions. '
                'Model repair can preview explicit corrections; save a prepared draft and separately review it for publication. '
                'The assistant cannot infer accounting meaning from column names alone.'),None
        if 'variance' in q:return formula+'\n\nWorkspace inputs are not approved analysis. Publish a verified snapshot before asking for its financial variance.',None
        return ('This page handles source intake, quality review, mapping, model repair and approval. '
                'Ask why rows were flagged, what a quality finding means, or how to map a model. Financial totals are answered from approved data on Overview, Analysis or AI Analyst.'),None
    if page=='Calculator':
        if 'variance' in q:return formula,None
        expression=meta.get('expression','').strip()
        if re.fullmatch(r'[\d\s.+*/()%\-]+',q):expression=q
        if expression:
            try:return f'For the expression **{expression}**, the result is **{calculate(expression):,.6g}**. Parentheses are evaluated before the surrounding arithmetic.',None
            except (ValueError,SyntaxError,ZeroDivisionError,OverflowError) as exc:return 'The expression cannot be calculated: '+str(exc),None
        return 'Enter an arithmetic expression, or ask how variance is calculated. Example: (120000 − 100000) ÷ 100000 × 100 = 20%.',None
    if data is None or data.empty:
        return (formula if 'variance' in q else 'No approved financial records are available in this view. Load, map and explicitly approve a dataset in Data Workspace, then select the relevant scope.'),None
    if data.measure.nunique()!=1 or data.currency.nunique()!=1:
        return 'Choose one financial measure and one currency before asking for totals. Unlike measures or currencies cannot be added safely.',None
    measure=str(data.measure.iloc[0]);ccy=str(data.currency.iloc[0]);dims=dimension_choices(data)
    allowed_inputs=set()
    if 'measure_inputs' in data and data.measure_inputs.notna().all():
        for encoded in data.measure_inputs.unique():
            try:
                definition=json.loads(encoded)
                allowed_inputs.update(str(x).casefold() for x in list(definition)+list(definition.values()))
            except (ValueError,TypeError):pass
    other_measures=[str(m) for m in meta.get('available_measures',[]) if str(m)!=measure and str(m).casefold() not in allowed_inputs and str(m).casefold() not in measure.casefold() and re.search(r'(?<!\w)'+re.escape(str(m).lower())+r'(?!\w)',q)]
    if other_measures:
        return 'This view is scoped to '+measure+'. Select '+', '.join(other_measures)+' on the page before asking for its figures; I will not substitute another measure silently.',None
    # Refuse unrequested scope expansion or FX conversion.
    requested_ccy=re.findall(r'\b(?:EUR|USD|GBP|DKK|SEK|NOK|CHF|JPY|CAD|AUD)\b',question.upper())
    if any(c!=ccy for c in requested_ccy):return f'This view is in {ccy}. Select the requested currency or prepare an approved FX conversion; I will not convert amounts implicitly.',None
    years=re.findall(r'\b20\d{2}\b',q)
    for year in years:
        if int(year) not in set(data.date.dt.year):return 'That year is outside the selected data. Adjust the page date filters; the answer will stay within the current view.',None
    requested_dim=next((label for label in dims if label.lower() in q),None)
    known={'country','region','product','category','customer','department','supplier','cost center'}
    unavailable=[word for word in known if re.search(r'\b'+re.escape(word)+r'\b',q) and not any(word==d.lower() for d in dims)]
    if unavailable:return 'This view has no confirmed '+', '.join(unavailable)+' dimension. Retain and approve the relevant source column in Data Workspace. Available breakdowns: '+', '.join(dims)+'.',None
    # A follow-up may narrow the current selection using an exact retained value.
    filters=[]
    if years and page!='Period comparison':
        data=data[data.date.dt.year.isin([int(y) for y in years])]
        filters.append('Year = '+', '.join(years))
    matched_values=[]
    for label,col in dims.items():
        if label=='Source':continue
        matches=[]
        for value in data[col].dropna().unique():
            text=str(value)
            if len(text)>1 and re.search(r'(?<!\w)'+re.escape(text.lower())+r'(?!\w)',q):matches.append(value)
        if matches:
            data=data[data[col].isin(matches)]
            filters.append(label+' = '+', '.join(map(str,matches)))
            matched_values.extend(str(v).lower() for v in matches)
    # Unsupported free-text qualifiers must not be silently ignored while giving
    # a full-view total that looks filtered. Users can instead use page filters.
    for qualifier in re.findall(r'\b(?:in|for|from)\s+(.+?)(?=\s+(?:by|for|in|during|versus|vs)\b|[?.!,]|$)',q):
        safe=any(term in qualifier for term in matched_values+list(allowed_inputs)+[measure.lower(),ccy.lower(),'this view','the current','my data','our data','example','percent','the selected','budget','actual'])
        safe=safe or bool(re.search(r'\b20\d{2}\b',qualifier))
        if not safe:return 'I could not match the requested qualifier “'+qualifier+'” to this view. Use the page filters or an exact confirmed dimension value so I do not answer with an unfiltered total.',None
    if data.empty:return 'No records match that question inside the current page scope.',None
    lead=f'**Scope:** {measure} · {ccy} · {len(data):,} records'
    if filters:lead+=' · '+ '; '.join(filters)
    lead+='.'
    if page=='Period comparison' and meta.get('comparison'):
        table=pd.DataFrame(meta['comparison'])
        if filters:return 'The displayed period bridge uses the page filters. Change those filters to compare a narrower group; I will not reuse the full bridge for a different selection.',None
        if years:return 'Use the two period controls to select the dates. The displayed bridge compares '+str(meta.get('periods'))+'; it is not recalculated from a year mentioned only in the question.',None
        if requested_dim and requested_dim!=meta.get('dimension'):return 'Select '+requested_dim+' in Contribution dimension to recalculate the period bridge for that breakdown.',None
        if meta.get('first_rows',1)==0 or meta.get('second_rows',1)==0:return 'One of the selected periods has no records. Missing coverage is not a verified zero; select periods with comparable data before interpreting the change.',table
        first=meta['first'];second=meta['second']
        if first is None or second is None:return lead+'\n\nThe selected period has an undefined measure, such as a margin with zero revenue. A numeric change cannot be calculated.',table
        delta=second-first
        if meta.get('unit')=='pp':
            return lead+f'\n\nEach period margin is total profit ÷ total revenue × 100. Period change = {money(second)}% − {money(first)}% = **{money(delta)} percentage points (pp)**. Group margins are not additive, so contribution percentages are not calculated.',table
        text=f'**Period change = second period actual − first period actual.**\n\n{money(second)} − {money(first)} = **{money(delta)} {ccy}**. '
        text+='Contribution % = group change ÷ total net change × 100; it is undefined at zero net change. This is a period comparison, not actual minus budget.'
        if 'variance' in q:text=formula+'\n\n**On this page:** '+text
        return lead+'\n\n'+text,table
    s=summary(data)
    dim=requested_dim or (meta.get('right_dimension') if 'right table' in q or 'second table' in q else meta.get('dimension'))
    if dim not in dims:dim=next(iter(dims))
    table=display_group(data,dims[dim],dim)
    if s.get('unit')=='%':
        formula_text='**Margin = total profit ÷ total revenue × 100.** Row percentages are never added or averaged. '
        formula_text+='Budget margin uses its own budget profit and budget revenue. Margin variance = Actual margin − Budget margin, in **percentage points (pp)**.'
        if s['actual'] is None:formula_text+='\n\nActual margin is undefined: the revenue denominator is zero or an input is unknown.'
        else:formula_text+=f"\n\nThis view: {money(s['numerator_actual'])} ÷ {money(s['denominator_actual'])} × 100 = **{s['actual']:.2f}%**."
        if s['budget'] is None:formula_text+='\n\nBudget margin and its variance are unknown when budget coverage is incomplete or budget revenue is zero.'
        else:
            formula_text+=f"\n\nBudget: {money(s['numerator_budget'])} ÷ {money(s['denominator_budget'])} × 100 = **{s['budget']:.2f}%**."
            if s['variance'] is not None:formula_text+=f"\n\n{money(s['actual'])}% − {money(s['budget'])}% = **{s['variance']:+.2f} pp**."
        formula_text+='\n\nThe table recomputes each group margin from its own profit and revenue totals. Group margins are not additive and do not establish business causes.'
        return lead+'\n\n'+formula_text,table
    if any(w in q for w in ('how','formula','calculate')) and 'variance' not in q:
        from calculated_measures import RECIPES
        if 'measure_origin' in data and data.measure_origin.eq('Calculated').all() and measure in RECIPES:
            terms=RECIPES[measure]['terms']
            workings=[]
            for i,(role,sign) in enumerate(terms.items()):
                col='component_actual::'+role
                value=data[col].sum() if col in data and data[col].notna().all() else None
                workings.append(('+' if sign>0 and i else '−' if sign<0 else '')+' '+money(value)+' ('+role+')')
            text='**'+measure+' = '+str(data.measure_formula.iloc[0])+'**.\n\nThis view: '+' '.join(workings).strip()+' = **'+money(s['actual'])+' '+ccy+'**. The inputs are approved compatible amounts; missing budget components stay unknown.'
            return lead+'\n\n'+text,None
        from measure_catalog import CATALOG
        if measure in CATALOG:
            return lead+'\n\n'+CATALOG[measure]+'\n\nThis is a **source-provided** measure: the mapped column supplies the figures. A name does not prove that the underlying accounting formula was applied. Use Calculated measures if you want a reviewed formula and its inputs.',None
    if 'variance' in q or 'budget' in q:
        text=formula+'\n\n'
        if s['budget'] is None:
            text+='**Current data:** budget coverage is incomplete. I cannot calculate a complete variance from a partial budget.'
        else:
            text+=f"**Using this view:** {money(s['actual'])} − {money(s['budget'])} = **{money(s['variance'])} {ccy}**."
            if s['budget']==0:text+=' Variance % is undefined because budget is zero.'
            else:text+=f"\n\n{money(s['variance'])} ÷ |{money(s['budget'])}| × 100 = **{s['variance_pct']:+.2f}%**."
        if 'why' in q or 'explain' in q or 'contribut' in q or requested_dim:
            table=table.assign(_magnitude=table.Variance.abs()).sort_values('_magnitude',ascending=False).drop(columns='_magnitude')
            text+=f'\n\nThe table attributes variance by **{dim}**. It shows where the numerical difference sits; it does not establish business causes. Missing dimension values form a separate group, and incomplete group budgets remain unknown.'
            return lead+'\n\n'+text,table
        return lead+'\n\n'+text,None
    if any(w in q for w in ('largest','highest','top','contribut')):
        table=table.sort_values('Actual',ascending=False)
        top=table.iloc[0]
        return lead+f'\n\nLargest **{dim}** by actual {measure}: **{top[dim]}**, **{money(top.Actual)} {ccy}**. This ranks actual totals, not period changes or variance favorability.',table
    if 'trend' in q or 'month' in q:
        return lead+'\n\nMonthly actual and budget totals from the selected records. Missing periods are not filled with invented values; a partial monthly budget remains unknown.',monthly(data)
    if 'dimension' in q or 'breakdown' in q or q.startswith('by '):
        return lead+'\n\nAvailable confirmed breakdowns: '+', '.join(dims)+'.',table
    if 'actual' in q or 'total' in q or 'summary' in q or 'overview' in q:
        return lead+f"\n\nActual **{money(s['actual'])} {ccy}**, budget **{money(s['budget'])} {ccy}**. Figures use the selected dates, sources, measure, currency and dimension filters.",None
    return lead+'\n\nI can explain variance calculations, show actual/budget totals, attribute variance by a confirmed dimension, rank actual totals or show monthly trends. I cannot establish a business cause or answer from missing data. Try “How do you calculate variance?” or “Explain variance by '+dim+'.”',None


def render_page_questions(page,data=None,metadata=None,raw_sources=None,dedicated=False):
    import streamlit as st
    st.divider()
    st.subheader('Ask your financial data' if dedicated else 'Ask about this page')
    if page=='Income statement':st.caption((metadata or {}).get('report_scope','Income statement setup — no approved report selected.'))
    else:st.caption(scope_label(data) if page!='Data Workspace' else 'Workspace scope: '+(', '.join(raw_sources or {}) or 'No selected source'))
    st.caption('Calculated answers and explicit scope checks. Questions do not modify data. This local assistant handles the supported financial questions; it is not an unrestricted conversational model.')
    meta=metadata or {}
    signature=(fingerprint(data) if data is not None else '')+json.dumps(meta,sort_keys=True,default=str)
    signature+=''.join(name+fingerprint(df) for name,df in (raw_sources or {}).items())
    scope=hashlib.sha256((page+signature).encode()).hexdigest()[:20]
    if 'page_conversations' not in st.session_state:st.session_state.page_conversations={}
    history=st.session_state.page_conversations.setdefault(page,{}).setdefault(scope,[])
    st.caption('Conversation is separate for each page and selection. Changing filters starts a separate scoped conversation.')
    use_ai=False
    if dedicated:
        import os
        use_ai=st.toggle('Expand answers with OpenAI (optional)',value=False,disabled=not bool(os.getenv('OPENAI_API_KEY')))
        st.caption('When enabled, the question, calculated answer and aggregated figures are sent to OpenAI. Raw records are not sent.')
    for msg in history:
        with st.chat_message(msg['role']):
            st.markdown(msg['text'])
            if msg.get('table') is not None:
                table=msg['table']
                if data is not None and is_ratio(data):table=table.rename(columns={'Actual':'Actual (%)','Budget':'Budget (%)','First':'First (%)','Second':'Second (%)','Variance':'Variance (pp)','Change':'Change (pp)'}).drop(columns=['Variance %','Contribution %'],errors='ignore')
                st.dataframe(table,hide_index=True,use_container_width=True)
    question=st.chat_input('Ask about the current view or how a calculation works',key='page_question_'+page)
    if question:
        text,table=answer_question(question,page,data,meta,raw_sources)
        if dedicated and use_ai:
            import os
            try:
                from openai import OpenAI
                aggregate=summary(data) if data is not None and not data.empty else {}
                response=OpenAI(api_key=os.getenv('OPENAI_API_KEY')).responses.create(model=os.getenv('OPENAI_MODEL','gpt-5.4-mini'),
                    instructions='Explain only the supplied calculated answer and aggregates. Do not change numbers, claim causality, invent facts or expand scope. State limitations clearly.',
                    input=json.dumps({'question':question,'scope':scope_label(data),'calculated_answer':text,'summary':aggregate},default=str))
                text+='\n\n**Optional AI interpretation**\n\n'+response.output_text
            except Exception:st.warning('Optional AI commentary is unavailable; the calculated answer is retained.')
        history.extend([{'role':'user','text':question},{'role':'assistant','text':text,'table':table}])
        st.rerun()
