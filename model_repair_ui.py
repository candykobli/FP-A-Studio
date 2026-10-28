"""A reviewable first version of the semantic model repair assistant."""
import hashlib
import json
import pandas as pd
import streamlit as st
from workspace import fingerprint
from model_repair import ROLES, DATE_FORMATS, candidates, diagnose, repair_preview, verify_model
from measure_catalog import source_measure_input


def render_model_repair(pool):
    st.subheader('Financial model repair assistant')
    st.write('Here, a model means the meaning of your columns: which field is the reporting date, actual amount, budget, entity and currency. The assistant checks those choices and proposes changes you can inspect before saving.')
    st.caption('This first version uses local rules and explicit choices. It does not call an AI service, change relationships, remove repeated rows or publish data.')
    if not pool:
        st.info('Load and select a source above to begin.'); return
    name=st.selectbox('Source for model review',list(pool),key='repair_source')
    raw=pool[name]; choices=candidates(raw)
    token=hashlib.sha256((name+fingerprint(raw)).encode()).hexdigest()[:16]
    draft=st.session_state.get('mapping_drafts',{}).get(name,{})
    st.markdown('#### 1. Confirm what the columns mean')
    mapping={}; cols=st.columns(3)
    options=['(none)']+list(raw.columns)
    for i,role in enumerate(ROLES):
        guess=draft.get('mapping',{}).get(role)
        if guess not in raw.columns:guess=choices[role][0] if len(choices[role])==1 else None
        with cols[i%3]:
            value=st.selectbox(role.title()+' meaning',options,index=options.index(guess) if guess in options else 0,key=f'repair_{token}_{role}')
            mapping[role]=None if value=='(none)' else value
    measure=source_measure_input('repair_measure_'+token,default=draft.get('measure','Amount'),custom_label='Business measure')
    reverse=st.checkbox('Reverse both actual and budget signs in the financial mapping',value=draft.get('reverse',False),key='repair_sign_'+token)
    grain=st.multiselect('What identifies one business record?',list(raw.columns),default=[c for c in draft.get('grain',[]) if c in raw],key='repair_grain_'+token)
    st.caption('Examples: transaction ID, or reporting date + entity + account. Repeated keys are flagged for review, never automatically deleted.')
    report=diagnose(raw,mapping,measure,grain)
    st.markdown('#### 2. Review the diagnosis')
    if report.empty:st.success('No issues found by these rules. Financial meaning still needs your confirmation.')
    else:st.dataframe(report,hide_index=True,use_container_width=True)
    st.markdown('#### 3. Choose proposed fixes')
    rename=st.checkbox('Standardize column names (for example, Net Sales → net_sales)',key='repair_rename_'+token)
    trim=st.checkbox('Trim leading and trailing spaces in text values',key='repair_trim_'+token)
    uppercase=st.checkbox('Uppercase currency codes (does not convert amounts)',key='repair_upper_'+token)
    numeric=st.checkbox('Convert plain actual / budget values to numeric types',key='repair_numeric_'+token)
    dates=st.selectbox('Reporting date interpretation',['Keep source values']+list(DATE_FORMATS),key='repair_dates_'+token)
    st.caption('No separator, currency symbol or date-locale guessing. Invalid conversions block the proposed copy; no rows are silently lost.')
    config={'mapping':mapping,'measure':measure,'reverse':reverse,'grain':grain,'rename':rename,'trim':trim,'uppercase':uppercase,'numeric':numeric,'dates':dates}
    signature=fingerprint(raw)+json.dumps(config,sort_keys=True)
    key='repair_preview_'+token
    if st.button('Check and preview proposed model',key='repair_preview_button_'+token,type='primary'):
        try:
            working,new_mapping,renames,log=repair_preview(raw,mapping,rename=rename,trim=trim,uppercase_currency=uppercase,numeric=numeric,date_format=DATE_FORMATS.get(dates))
            mapped,totals=verify_model(working,new_mapping,measure,-1 if reverse else 1)
            new_grain=[renames[c] for c in grain]
            after=diagnose(working,new_mapping,measure,new_grain)
            st.session_state[key]={'signature':signature,'working':working,'mapping':new_mapping,'renames':renames,'log':log,'totals':totals,'after':after,'grain':new_grain}
        except (ValueError,TypeError,KeyError) as exc:
            st.session_state.pop(key,None); st.error('Preview blocked: '+str(exc))
    preview=st.session_state.get(key)
    if not preview:return
    if preview['signature']!=signature:
        st.info('Your inputs changed. Run the preview again before saving.'); return
    st.markdown('#### 4. Inspect the proposed working copy')
    st.write(f'{len(raw):,} original rows → {len(preview["working"]):,} proposed rows. No rows removed.')
    st.dataframe(pd.DataFrame([{'Role':r,'Original column':mapping.get(r),'Proposed column':preview['mapping'].get(r)} for r in ROLES]),hide_index=True,use_container_width=True)
    for item in preview['log']:st.write('• '+item)
    if not preview['log']:st.caption('No values changed; this draft records the mapping choices only.')
    a,b=st.columns(2)
    with a:
        st.markdown('**Original**'); st.dataframe(raw.head(20),hide_index=True,use_container_width=True)
    with b:
        st.markdown('**Proposed**'); st.dataframe(preview['working'].head(20),hide_index=True,use_container_width=True)
    st.markdown('**Financial totals after mapping — per currency**')
    st.dataframe(preview['totals'],hide_index=True,use_container_width=True)
    st.caption('These totals describe the proposed mapping. Verify them against your financial source; the assistant cannot know which column or sign convention your business intends.')
    if not preview['after'].empty:
        st.markdown('**Items still requiring judgment**'); st.dataframe(preview['after'],hide_index=True,use_container_width=True)
    export={'source':name,'input_fingerprint':fingerprint(raw),'config':config,'proposed_mapping':preview['mapping'],'changes':preview['log'],'remaining_findings':preview['after'].to_dict(orient='records')}
    st.download_button('Download model review report',json.dumps(export,indent=2,default=str).encode(),file_name='model_review.json',key='repair_report_'+token)
    approved=st.checkbox('I reviewed the mapping, date interpretation, sign convention, business keys and proposed totals. Save this as a draft only.',key='repair_accept_'+hashlib.sha256(signature.encode()).hexdigest())
    if st.button('Save proposed model as a prepared draft',disabled=not approved,key='repair_save_'+token):
        label=f'Model repair {len(st.session_state.dm_outputs)+1}'
        full='Prepared · '+label
        st.session_state.dm_outputs[label]=preview['working'].copy(deep=True)
        st.session_state.lineage[full]=set(st.session_state.lineage.get(name,{name}))
        if 'mapping_drafts' not in st.session_state:st.session_state.mapping_drafts={}
        st.session_state.mapping_drafts[full]={'mapping':preview['mapping'],'measure':measure,'reverse':reverse,'grain':preview['grain'],'repair_report':export}
        st.success('Draft saved as '+full+'. Add it to Sources above, then open Review & approve. Your mapping choices will be prefilled; publication still needs explicit approval.')
