"""Build, review, approve and drill into a management income statement."""
import hashlib
import io
import json
import zipfile
from pathlib import Path
import pandas as pd
import streamlit as st
from engine import normalize_name
from workspace import fingerprint
from income_statement import LINES,EXCLUDE,UNMAPPED,SUBTOTALS,map_source,check_report,statement_table,reconcile_sources,approve_report,reject_overlapping_sources
from page_questions import render_page_questions


def choose_column(label,columns,aliases,key,optional=False):
    options=['(none)']+list(columns)
    matches=[c for c in columns if normalize_name(c) in aliases]
    guess=matches[0] if len(matches)==1 else '(none)'
    value=st.selectbox(label,options,index=options.index(guess),key=key)
    return None if value=='(none)' else value


def configure_source(name,raw):
    token=hashlib.sha256((name+fingerprint(raw)).encode()).hexdigest()[:12]
    with st.expander('Map accounts · '+name,expanded=True):
        st.caption(f'{len(raw):,} rows. Map a single reporting/legal entity per source; Country is not an entity identifier. Use separate inputs when the source covers different legal entities.')
        mapping={}
        a,b,c=st.columns(3)
        with a:
            mapping['date']=choose_column('Reporting date',raw.columns,{'date','period','month'},'is_date_'+token)
            mapping['account']=choose_column('Account code or identifier',raw.columns,{'account','account_code','account_id'},'is_account_'+token)
        with b:
            mapping['actual']=choose_column('Actual activity amount',raw.columns,{'actual','amount','actual_amount'},'is_actual_'+token)
            mapping['budget']=choose_column('Budget activity amount (optional)',raw.columns,{'budget','plan','budget_amount'},'is_budget_'+token,True)
        with c:
            mapping['currency']=choose_column('Currency code',raw.columns,{'currency','ccy','currency_code'},'is_currency_'+token)
            mapping['business_unit']=choose_column('Business-unit column (optional)',raw.columns,{'business_unit','unit','department'},'is_unit_col_'+token,True)
        demos={'Original · Demo France':'France SAS','Original · Demo Germany':'Germany GmbH'}
        entity=st.text_input('Reporting / legal entity',value=demos.get(name,''),key='is_entity_'+token)
        unit=st.text_input('Business-unit label when no unit column is mapped',value=name.removeprefix('Original · '),key='is_unit_'+token)
        basis=st.selectbox('Source amounts represent',['Monthly activity','Transaction activity','Year-to-date balances','Closing balances'],key='is_basis_'+token)
        date_label=st.selectbox('Date format',['ISO YYYY-MM-DD','Day first DD/MM/YYYY','Month first MM/DD/YYYY'],key='is_date_format_'+token)
        date_format={'ISO YYYY-MM-DD':'%Y-%m-%d','Day first DD/MM/YYYY':'%d/%m/%Y','Month first MM/DD/YYYY':'%m/%d/%Y'}[date_label]
        st.caption('Do not load both a monthly total and its underlying transactions as separate inputs. Year-to-date and closing balances are blocked until converted to activity.')
        rules={}
        account_col=mapping.get('account')
        if account_col:
            accounts=raw[account_col].dropna().astype('string').unique().tolist()
            if len(accounts)>100:
                st.error('This first version supports up to 100 account identifiers per source. Prepare an aggregated account-level activity table first.'); return None
            for account in sorted(accounts):
                key=hashlib.sha256((token+str(account)).encode()).hexdigest()[:16]
                a,b,c=st.columns([2,2,1])
                with a:st.write('**Account '+str(account)+'**')
                with b:line=st.selectbox('Reporting line · '+str(account),[UNMAPPED]+list(LINES)+[EXCLUDE],key='is_line_'+key)
                with c:reverse=st.checkbox('Reverse source sign · '+str(account),key='is_sign_'+key)
                reason=''
                if line==EXCLUDE:reason=st.text_input('Reason for excluding '+str(account),key='is_reason_'+key)
                rules[str(account)]={'line':line,'sign':-1 if reverse else 1,'reason':reason}
        st.caption('Display income and expense lines as positive activity when appropriate; expenses are subtracted by the statement formulas. Review credits/reversals individually. The source-signed amounts remain visible in reconciliation.')
    return {'mapping':mapping,'entity':entity,'business_unit':unit,'basis':basis,'date_format':date_format},rules


def export_report(snapshot):
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
        for key,file in [('detail','source_row_bridge.csv'),('tables','income_statement_all_currencies.csv'),('reconciliation','source_reconciliation.csv')]:
            z.writestr(file,snapshot[key].to_csv(index=False))
        manifest={k:snapshot[k] for k in ('config','source_fingerprints','approved_at','signature')}
        z.writestr('approval_and_mappings.json',json.dumps(manifest,indent=2,default=str))
    return buf.getvalue()


def display_report(detail,zero_missing,prefix,approved=False):
    st.markdown('#### '+('Approved report view' if approved else 'Preview — not approved'))
    currency=st.selectbox('Reporting currency',sorted(detail.Currency.unique().tolist()),key=prefix+'_currency')
    scoped=detail[detail.Currency==currency]
    periods=st.multiselect('Reporting months',sorted(scoped.Period.unique().tolist()),default=sorted(scoped.Period.unique().tolist()),key=prefix+'_periods')
    entities=st.multiselect('Reporting entities',sorted(scoped.Entity.unique().tolist()),default=sorted(scoped.Entity.unique().tolist()),key=prefix+'_entities')
    units=st.multiselect('Business units',sorted(scoped['Business unit'].unique().tolist()),default=sorted(scoped['Business unit'].unique().tolist()),key=prefix+'_units')
    scoped=scoped[scoped.Period.isin(periods)&scoped.Entity.isin(entities)&scoped['Business unit'].isin(units)]
    if scoped.empty:
        st.info('No source rows match these report filters.');render_page_questions('Income statement',metadata={'income_statement':[],'report_scope':'No report rows selected.'});return
    table=statement_table(scoped,zero_missing)
    st.caption(f'{currency} · {len(scoped):,} source rows · combined management view, before intercompany eliminations. No FX conversion applied. Missing budgets remain unknown.')
    st.dataframe(table,hide_index=True,use_container_width=True)
    st.caption('Expense-line variance = actual − budget; positive expense variance is not automatically favorable. Subtotal variances use the calculated profit figures.')
    with st.expander('Show statement formulas'):
        for line,parts in SUBTOTALS.items():
            formula=' '.join(('+' if sign>0 and i else '−' if sign<0 else '')+' '+part for i,(part,sign) in enumerate(parts.items())).strip()
            st.write('**'+line+'** = '+formula)
    st.markdown('#### Business-unit contribution to net profit')
    contribution=[]
    for (entity,unit),group in scoped.groupby(['Entity','Business unit']):
        part=statement_table(group,zero_missing)
        net=part[part.Line=='Net profit'].iloc[0]
        contribution.append({'Entity':entity,'Business unit':unit,'Actual net profit':net.Actual,'Budget net profit':net.Budget})
    st.dataframe(pd.DataFrame(contribution),hide_index=True,use_container_width=True)
    line=st.selectbox('Drill into a statement line',list(table.Line),key=prefix+'_drill')
    def leaves(label):
        if label not in SUBTOTALS:return {label}
        return set().union(*(leaves(k) for k in SUBTOTALS[label]))
    drill=scoped[(scoped.Status=='Included')&scoped['Reporting line'].isin(leaves(line))]
    st.caption('For subtotals, the bridge lists contributing source lines; Profit impact shows each row’s signed effect on net profit.')
    st.dataframe(drill,hide_index=True,use_container_width=True)
    st.download_button('Download current statement CSV',table.to_csv(index=False).encode(),file_name='management_income_statement.csv',key=prefix+'_download_statement')
    with st.expander('Reconcile to original source activity',expanded=True):
        recon=reconcile_sources(scoped)
        st.dataframe(recon,hide_index=True,use_container_width=True)
        st.caption('Source actual = included + excluded + unmapped, all using original source signs. The sign-normalized profit-impact bridge separately reconciles to Net profit. Reconciliation proves row coverage and arithmetic, not that the source itself is complete or accounting classifications are correct.')
        st.download_button('Download current reconciliation CSV',recon.to_csv(index=False).encode(),file_name='source_reconciliation.csv',key=prefix+'_download_recon')
    render_page_questions('Income statement',metadata={'income_statement':table.to_dict(orient='records'),
        'report_scope':f'{"Approved" if approved else "Unapproved preview"} · {currency} · months {periods} · entities {entities} · business units {units}',
        'reconciliation':reconcile_sources(scoped).to_dict(orient='records')})


def render_income_statement():
    st.subheader('Management income statement')
    st.write('Map each business unit’s accounts into a shared reporting structure, inspect the source reconciliation, then approve a report snapshot. This first version is a combined management view; it does not perform statutory consolidation, intercompany elimination, allocation or FX translation.')
    if 'income_statement_reports' not in st.session_state:st.session_state.income_statement_reports=[]
    if st.button('Load two-business-unit demonstration',key='is_load_demo'):
        from workspace_ui import register_source
        for label,file in [('Demo France','income_statement_france.csv'),('Demo Germany','income_statement_germany.csv')]:
            if label not in st.session_state.sources:
                register_source(label,pd.read_csv(Path(__file__).parent/'sample_data'/file,dtype={'Account':'string'}))
        st.rerun()
    mode=st.radio('Income statement workspace',['Build & review','Approved reports'],horizontal=True,key='is_mode')
    chat_rendered=False
    if mode=='Build & review':
        pool={**{'Original · '+k:v for k,v in st.session_state.sources.items()},**{'Prepared · '+k:v for k,v in st.session_state.dm_outputs.items()}}
        selected=st.multiselect('Account-level activity sources',list(pool),key='is_sources')
        if not selected:st.info('Select loaded sources, or use the demonstration. Existing Revenue-only analytical files may not contain the account information required for a full statement.')
        configs={};rules={};valid=True
        for name in selected:
            configured=configure_source(name,pool[name])
            if configured is None:valid=False;continue
            configs[name],rules[name]=configured
        zero_missing=st.checkbox('I confirm reporting lines absent from these inputs have no activity for the selected entities and periods; show those absent lines as zero.',key='is_zero_missing')
        st.caption('Do not tick this merely to make subtotals appear. If a source or period is missing, load it instead. This does not fill missing actual cells or missing budgets in existing rows.')
        config={'sources':configs,'account_rules':rules,'zero_missing':zero_missing,'view':'Combined management view before intercompany eliminations'}
        fingerprints={n:fingerprint(pool[n]) for n in selected}
        signature=hashlib.sha256(json.dumps({'config':config,'inputs':fingerprints},sort_keys=True,default=str).encode()).hexdigest()
        if st.button('Preview income statement and reconciliation',disabled=not selected or not valid,key='is_preview_button',type='primary'):
            try:
                reject_overlapping_sources(selected,st.session_state.lineage)
                detail=pd.concat([map_source(pool[n],n,configs[n],rules[n]) for n in selected],ignore_index=True)
                tables,recon,issues=check_report(detail,zero_missing)
                st.session_state.is_preview={'signature':signature,'detail':detail,'tables':tables,'reconciliation':recon,'issues':issues,'config':config,'source_fingerprints':fingerprints}
            except (ValueError,TypeError,KeyError) as exc:
                st.session_state.pop('is_preview',None);st.error(str(exc))
        preview=st.session_state.get('is_preview')
        if preview and preview['signature']!=signature:st.info('Source selection, values or mappings changed. Preview again before approval.')
        elif preview:
            for issue in preview['issues']:st.error(issue)
            neg=preview['detail'][(preview['detail'].Status=='Included')&(preview['detail'].Actual<0)]
            if len(neg):st.warning(f'{len(neg)} mapped actuals are negative. Verify credits, reversals and sign conventions; no absolute-value conversion is applied.')
            if (preview['detail'].Status=='Excluded').any():
                st.markdown('**Explicit exclusions — included in source reconciliation**')
                st.dataframe(preview['detail'][preview['detail'].Status=='Excluded'],hide_index=True,use_container_width=True)
            display_report(preview['detail'],zero_missing,'is_preview',False)
            chat_rendered=True
            st.markdown('#### Approve the complete snapshot')
            st.caption('Approval covers every source, currency and period in the preview, not just the filtered display. All source mappings and fingerprints are saved with the snapshot.')
            accept=st.checkbox('I verified source coverage, account classifications, exclusions, sign conventions and reconciliation. I understand this combined view has no intercompany eliminations or FX translation.',key='is_approve_'+signature)
            if st.button('Approve and save income statement snapshot',disabled=not accept or bool(preview['issues']),key='is_approve_button'):
                try:
                    approve_report(st.session_state,preview['detail'],config,preview['signature'],signature,fingerprints)
                    st.success('Approved snapshot saved. Open Approved reports to view it. Source tables and analytical facts were not changed.')
                except ValueError as exc:st.error(str(exc))
    if mode=='Approved reports':
        snapshots=st.session_state.income_statement_reports
        if not snapshots:st.info('No approved income statement yet.')
        else:
            index=st.selectbox('Approved snapshot',list(range(len(snapshots))),format_func=lambda i:f'Report {i+1} · {snapshots[i]["approved_at"]}',key='is_snapshot')
            snap=snapshots[index]
            st.caption('Approved at '+snap['approved_at']+'. New source loads or mapping changes do not modify this snapshot.')
            st.download_button('Download approved report pack',export_report(snap),file_name=f'income_statement_report_{index+1}.zip',mime='application/zip',key='is_export_snapshot')
            display_report(snap['detail'],snap['config']['zero_missing'],'is_approved_'+str(index),True)
            chat_rendered=True
    if not chat_rendered:
        render_page_questions('Income statement')
