"""Unified source intake, preparation, modeling and approval interface."""
import hashlib
import json
import pandas as pd
import streamlit as st
from engine import read_upload, suggestions
from connectors import read_api, read_sql
from workspace import fingerprint, quality, prepare, publish
from data_management import join_candidates, safe_join, duplicate_review, deduplicate, convert_currency, reconcile


def register_source(label, frame):
    if frame.empty or not frame.columns.is_unique:
        raise ValueError('Use a non-empty table with unique column names.')
    name=label
    i=2
    while name in st.session_state.sources:
        name=f'{label} ({i})'; i+=1
    st.session_state.sources[name]=frame.copy(deep=True)


def save_prepared(label, frame, inputs):
    if frame.empty or not frame.columns.is_unique:
        st.error('The result must contain rows and unique column names.'); return
    name=f'{label} {len(st.session_state.dm_outputs)+1}'
    st.session_state.dm_outputs[name]=frame.copy(deep=True)
    parents=set()
    for key in inputs:
        parents.update(st.session_state.lineage.get(key,{key}))
    st.session_state.lineage['Prepared · '+name]=parents
    st.success('Prepared copy created. Select it under Review & approve to verify and publish.')


def intake():
    tab1,tab2,tab3=st.tabs(['Upload files','SQL / warehouse','REST API'])
    with tab1:
        files=st.file_uploader('Upload Excel, CSV or JSON',type=['xlsx','xls','csv','json'],accept_multiple_files=True)
        for uploaded in files or []:
            data=uploaded.getvalue(); ident=hashlib.sha256(data).hexdigest()[:12]
            sheet=None
            if uploaded.name.lower().endswith(('.xlsx','.xls')):
                try:
                    xl=pd.ExcelFile(uploaded)
                    sheet=st.selectbox(f'Worksheet · {uploaded.name}',xl.sheet_names,key=f'sheet_{ident}')
                except Exception as exc:st.error(str(exc));continue
            source_id=f'{uploaded.name} · {sheet or "data"} · {ident}'
            if st.button(f'Load {uploaded.name}',key=f'load_{ident}_{sheet}'):
                try:register_source(source_id,read_upload(uploaded.name,data,sheet));st.success('Loaded. Configure the mapping below.')
                except Exception as exc:st.error(f'Unable to load file: {exc}')
    with tab2:
        st.info('Use a read-only database account. Drivers for your database may need separate installation. Avoid exposing this app publicly with database access enabled.')
        with st.form('sql_form'):
            name=st.text_input('Source label',value='Warehouse')
            url=st.text_input('SQLAlchemy connection URL',type='password',placeholder='postgresql+psycopg://user:password@host/db')
            query=st.text_area('Read-only SQL query',value='SELECT * FROM finance_data LIMIT 10000')
            submit=st.form_submit_button('Connect and preview')
        if submit:
            try:
                result=read_sql(url,query);register_source(name,result);st.success(f'{len(result):,} rows loaded')
            except Exception as exc:st.error(f'Connection failed: {exc}')
    with tab3:
        st.info('HTTPS JSON endpoints only. Use a trusted endpoint; the API token is used for this request only.')
        with st.form('api_form'):
            name=st.text_input('API source label',value='Finance API')
            url=st.text_input('HTTPS endpoint')
            token=st.text_input('Bearer token (optional)',type='password')
            path=st.text_input('Nested records path (optional)',placeholder='data.items')
            submit=st.form_submit_button('Fetch data')
        if submit:
            try:
                result=read_api(url,token or None,path or None);register_source(name,result);st.success(f'{len(result):,} rows loaded')
            except Exception as exc:st.error(f'API request failed: {exc}')


def controls(pool):
    if not pool:
        st.info('Select sources above to use these controls.'); return
    tabs=st.tabs(['Connect related tables','Review repeated records','Convert currency','Check figures against another source'])
    with tabs[0]:
        if len(pool)<2:st.info('Load two datasets to inspect possible relationships.')
        else:
            c1,c2=st.columns(2)
            with c1:ln=st.selectbox('Left dataset',list(pool),key='join_left')
            with c2:rn=st.selectbox('Right dataset',list(pool),index=1,key='join_right')
            if ln==rn:st.warning('Choose two different datasets.')
            else:
                left,right=pool[ln],pool[rn]
                candidates=join_candidates(left,right)
                if not candidates.empty:st.dataframe(candidates,hide_index=True,use_container_width=True)
                else:st.info('No matching same-name keys detected; you may select keys manually.')
                a,b,c=st.columns(3)
                with a:lk=st.selectbox('Left key',list(left.columns),key='lk')
                with b:rk=st.selectbox('Right key',list(right.columns),index=list(right.columns).index(lk) if lk in right else 0,key='rk')
                with c:how=st.selectbox('Join type',['left','inner','outer'])
                allow=False
                st.caption('Many-to-many joins are blocked. Aggregate to the correct business grain before connecting tables.')
                join_signature=(ln,rn,lk,rk,how,fingerprint(left),fingerprint(right))
                if st.button('Preview validated join',type='primary'):
                    try:
                        joined,audit=safe_join(left,right,lk,rk,how,allow)
                        st.session_state.dm_join_preview=(joined,audit,join_signature)
                    except Exception as exc:st.error(str(exc));st.session_state.pop('dm_join_preview',None)
                if 'dm_join_preview' in st.session_state and st.session_state.dm_join_preview[2]==join_signature:
                    joined,audit,_=st.session_state.dm_join_preview
                    st.json(audit);st.dataframe(joined.head(100),hide_index=True,use_container_width=True)
                    st.warning('A join is not automatically a valid financial consolidation. Check row counts, business grain and overlapping amounts.')
                    if st.button('Save joined dataset to workspace'):
                        save_prepared('Join',joined,[ln,rn]);st.success('Joined dataset saved as Prepared · Validated join.')
    with tabs[1]:
        name=st.selectbox('Dataset for duplicate review',list(pool),key='dedup_ds')
        df=pool[name]
        keys=st.multiselect('Business keys defining a duplicate',list(df.columns),key='dedup_keys')
        if keys:
            duplicates,groups=duplicate_review(df,keys)
            st.metric('Rows flagged as possible duplicates',len(duplicates))
            st.dataframe(groups.head(100),hide_index=True,use_container_width=True)
            st.dataframe(duplicates.head(100),hide_index=True,use_container_width=True)
            st.caption('Rows with the same selected keys may still be legitimate distinct transactions.')
            keep=st.selectbox('If confirmed, retain',['first','last'])
            confirmed=st.checkbox('I reviewed these groups and confirm the retention rule removes only duplicate transactions.')
            if st.button('Create deduplicated copy',disabled=not confirmed):
                cleaned,audit=deduplicate(df,keys,keep)
                save_prepared('Reviewed duplicates',cleaned,[name])
                st.json(audit);st.success('Prepared copy created. Original data was not modified.')
    with tabs[2]:
        name=st.selectbox('Financial dataset',list(pool),key='fx_ds')
        df=pool[name]
        st.caption('Upload your approved FX table. Required columns: date, currency, target_currency, rate, rate_type. Rate = units of target per 1 unit of source.')
        uploaded=st.file_uploader('Approved FX rates (CSV, Excel, JSON)',type=['csv','xlsx','json'],key='fx_file')
        if uploaded:
            try:
                rates=read_upload(uploaded.name,uploaded.getvalue())
                st.dataframe(rates.head(15),hide_index=True,use_container_width=True)
                a,b,c=st.columns(3)
                with a:amount=st.selectbox('Amount column',list(df.columns),index=list(df.columns).index('actual') if 'actual' in df else 0)
                with b:ccy=st.selectbox('Source currency column',list(df.columns),index=list(df.columns).index('currency') if 'currency' in df else 0)
                with c:dt=st.selectbox('Transaction / reporting date',list(df.columns),index=list(df.columns).index('date') if 'date' in df else 0)
                target=st.text_input('Reporting currency (ISO code)',value='EUR').upper().strip()
                rt=st.selectbox('Rate policy',['monthly_average','daily','closing'])
                if st.button('Convert using supplied rates',type='primary'):
                    converted,audit=convert_currency(df,rates,amount,ccy,dt,target,rt)
                    save_prepared('FX converted',converted,[name])
                    st.json(audit);st.dataframe(converted.head(100),hide_index=True,use_container_width=True)
                    if audit['Missing FX rates']:st.error('Some records have no rate. Their converted amounts are blank; do not use incomplete totals.')
                    else:st.success('Converted copy created; original amounts and currencies retained.')
            except Exception as exc:st.error(str(exc))
    with tabs[3]:
        if len(pool)<2:st.info('Load two datasets to reconcile.')
        else:
            a,b=st.columns(2)
            with a:left_name=st.selectbox('Ledger / left source',list(pool),key='rec_left')
            with b:right_name=st.selectbox('Comparison / right source',list(pool),index=1,key='rec_right')
            if left_name==right_name:st.warning('Choose different datasets.')
            else:
                left,right=pool[left_name],pool[right_name]
                common=sorted(set(left.columns)&set(right.columns))
                keys=st.multiselect('Matching business dimensions',common,key='rec_keys')
                a,b,c=st.columns(3)
                with a:la=st.selectbox('Left amount',list(left.columns),index=list(left.columns).index('actual') if 'actual' in left else 0)
                with b:ra=st.selectbox('Right amount',list(right.columns),index=list(right.columns).index('actual') if 'actual' in right else 0)
                with c:tol=st.number_input('Absolute tolerance',min_value=0.0,value=0.01,format='%.4f')
                rec_signature=(left_name,right_name,tuple(keys),la,ra,tol,fingerprint(left),fingerprint(right))
                if st.button('Run reconciliation',type='primary'):
                    try:
                        result,audit=reconcile(left,right,keys,la,ra,tol)
                        st.session_state.dm_recon=(result,audit,rec_signature)
                    except Exception as exc:st.error(str(exc));st.session_state.pop('dm_recon',None)
                if 'dm_recon' in st.session_state and st.session_state.dm_recon[2]==rec_signature:
                    result,audit,_=st.session_state.dm_recon
                    st.json(audit)
                    st.dataframe(result,hide_index=True,use_container_width=True)
                    st.download_button('Download reconciliation CSV',result.to_csv(index=False).encode(),file_name='reconciliation.csv',mime='text/csv')
                    st.caption('Reconcile only equivalent measures, periods and currencies. Net differences can hide offsetting exceptions.')



def review(name, raw):
    st.subheader(name)
    st.caption('Originals stay unchanged. Corrections create separate working copies; only approved data feeds analysis.')
    report, duplicates, issues=quality(raw)
    a,b,c=st.columns(3)
    a.metric('Rows',len(raw)); b.metric('Repeated rows to review',duplicates); c.metric('Quality findings',issues)
    st.dataframe(report,hide_index=True,use_container_width=True)
    if issues:
        st.warning('Review the findings below. Blanks in optional fields and repeated records may be legitimate; nothing is removed automatically.')
    else:
        st.success('Basic checks passed. Quick verify & approve lets you check the financial mapping and totals without corrections.')
    choice=st.radio('What would you like to do?', ['Quick verify & approve','Review / correct'],index=1 if issues else 0,key='route_'+name)
    st.dataframe(raw.head(100),hide_index=True,use_container_width=True)
    st.download_button('Download input copy',raw.to_csv(index=False).encode(),file_name='workspace_input.csv',key='download_'+name)
    if choice=='Review / correct':
        trim=st.multiselect('Columns to trim leading / trailing whitespace',list(raw.columns),key='trim_'+name)
        working=raw.copy(deep=True)
        for col in trim:
            working[col]=working[col].map(lambda v:v.strip() if isinstance(v,str) else v)
        st.caption('Edit cells or select individual rows to delete. No rows are automatically deduplicated.')
        edited=st.data_editor(working,num_rows='dynamic',use_container_width=True,key='edit_'+name)
        if st.button('Save corrections as a prepared copy',key='save_'+name):
            save_prepared('Corrected',edited,[name]); st.rerun()
        st.info('To approve corrections, save the copy and select it above.')
        return
    draft=st.session_state.get('mapping_drafts',{}).get(name,{})
    from measure_mapping_ui import map_measures
    prepared=map_measures(name,raw,draft)
    if prepared is None:return
    result,totals,signature,config=prepared
    st.markdown('#### Verify the financial figures')
    st.dataframe(totals,hide_index=True,use_container_width=True)
    st.write(f"Period: {result.date.min():%d %b %Y} to {result.date.max():%d %b %Y} · {len(raw):,} input rows · {len(result):,} financial records · {int(result.budget.isna().sum())} records without budget")
    st.caption('Totals are separated by measure and currency. No currency conversion is implied. A missing budget is unknown, not zero. Confirm period coverage and sign convention against your source.')
    st.dataframe(result.head(50),hide_index=True,use_container_width=True)
    parents=st.session_state.lineage.get(name,{name})
    conflicts=[n for n,p in st.session_state.published_parents.items() if n!=name and set(p)&set(parents)]
    replace=False
    if conflicts:
        st.warning('This copy overlaps approved inputs: '+', '.join(conflicts))
        replace=st.checkbox('Replace these published inputs with this copy to avoid double counting',key='replace_'+name)
    checks=st.checkbox('I reviewed the quality findings, dates, currency, signs, budget coverage and totals, and checked that this input does not overlap other published sources.',key='checks_'+hashlib.sha256(signature.encode()).hexdigest())
    if st.button('Approve & publish to analysis',disabled=not checks,key='publish_'+name,type='primary'):
        try:
            publish(st.session_state,name,result,signature,signature,parents,replace)
            st.session_state.approvals.append({'dataset':name,'fingerprint':fingerprint(raw),'model_config':config,'rows':len(result),'approved_at':pd.Timestamp.now(tz='UTC').isoformat()})
            st.success('Approved and published. Open Overview or Analysis to use these figures.')
        except ValueError as exc:st.error(str(exc))


def render_workspace():
    st.markdown("""<div style="padding-left: 32px;"><h2 style="color: #172B4D; margin-bottom: 8px;">Connect your financial data</h2><p style="color: #64748B;">Each source is mapped to a shared financial schema. No fixed revenue/cost columns are required.</p></div>""",unsafe_allow_html=True)
    st.write('Add your sources, check their quality, then approve them for analysis. Clean data can go straight to verification. Prepare corrections or model multiple sources only when needed.')
    intake()
    pool={**{'Original · '+k:v for k,v in st.session_state.sources.items()},**{'Prepared · '+k:v for k,v in st.session_state.dm_outputs.items()}}
    for name in pool:
        st.session_state.lineage.setdefault(name,{name})
    if not pool:
        st.info('Upload sample_data/sales.csv or connect your own source to begin.')
        from page_questions import render_page_questions
        render_page_questions('Data Workspace')
        return
    selected=st.multiselect('Sources — select one or several',list(pool),default=list(pool),key='workspace_sources')
    overview=[]
    for name in selected:
        _,dup,issues=quality(pool[name])
        overview.append({'Source':name,'Rows':len(pool[name]),'Quality':'Review findings' if issues else 'Ready for quick verification','Repeated rows':dup,'Published':name in st.session_state.facts})
    st.dataframe(pd.DataFrame(overview),hide_index=True,use_container_width=True)
    inspect,calculated,repair,model,published=st.tabs(['Review & approve','Calculated measures','Model repair assistant','Model selected sources','Published data'])
    with inspect:
        if selected:
            name=st.selectbox('Source to review',selected,key='review_source')
            review(name,pool[name])
        else:st.info('Choose at least one source above.')
    with repair:
        from model_repair_ui import render_model_repair
        render_model_repair({n:pool[n] for n in selected})
    with calculated:
        from calculated_measures_ui import render_calculated_measures
        render_calculated_measures()
    with model:
        st.info('Select any number of sources above. Work through explicit relationships one at a time; saved outputs can be selected for the next step. Different source names do not prove that transactions are distinct.')
        if len(selected)>1:
            st.caption('For compatible, non-overlapping financial tables, map and approve each source separately. Analysis appends approved rows; it never guesses joins or removes duplicates.')
        controls({n:pool[n] for n in selected})
    with published:
        st.caption('Only these approved snapshots feed dashboards. Editing a working copy does not change an approved snapshot.')
        for name,frame in list(st.session_state.facts.items()):
            st.write(f'{name} · {len(frame):,} approved rows')
            if st.button('Withdraw from analysis',key='withdraw_'+name):
                st.session_state.facts.pop(name); st.session_state.published_parents.pop(name,None); st.rerun()
        st.download_button('Download approval history',json.dumps(st.session_state.approvals,indent=2).encode(),file_name='approval_history.json')
    from page_questions import render_page_questions
    render_page_questions('Data Workspace',raw_sources={n:pool[n] for n in selected})
