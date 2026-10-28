"""Preview and approve formulas separately from source-provided measures."""
import json
import pandas as pd
import streamlit as st
from workspace import fingerprint
from engine import summary
from dimensions import dimension_choices,PREFIX
from calculated_measures import RECIPES,active_calculations,available_input,model_signature,calculate_measure,approve_calculation


def render_calculated_measures():
    st.subheader('Create a calculated measure')
    st.write('Use published source measures as explicit formula inputs. Naming a source column Gross profit does not calculate it. Here, each definition has a formula, matching business keys, an evidence table and a separate approval.')
    base=st.session_state.facts
    registry=st.session_state.setdefault('calculated_measures',{})
    active=active_calculations(base,registry)
    if not base:
        st.info('First map and approve the required source amounts under Review & approve. No calculated measure can be built from unpublished inputs.');return
    source=st.selectbox('Approved financial dataset for the formula',list(base),key='calc_source')
    data,derived=available_input(base,registry,source)
    name=st.selectbox('Calculated business measure',list(RECIPES),key='calc_recipe')
    recipe=RECIPES[name]
    st.caption('Amount formulas subtract explicit cost components. Margin formulas divide the selected profit by revenue × 100. Net profit requires finance income, finance expenses and tax inputs; missing components are not assumed zero.')
    options=['(none)']+sorted(data.measure.unique().tolist())
    inputs={}
    for role in recipe['terms']:
        chosen=st.selectbox(role+' input measure',options,index=options.index(role) if role in options else 0,key='calc_input_'+name+'_'+role)
        inputs[role]=None if chosen=='(none)' else chosen
    dims=dimension_choices(data)
    dims={label:col for label,col in dims.items() if col.startswith(PREFIX) and not data[col].astype('string').eq(data.measure.astype('string')).fillna(False).all()}
    grain=st.multiselect('Business keys to match after aggregating each input',list(dims),default=list(dims),key='calc_grain_'+source)
    keys=[dims[g] for g in grain]
    st.caption('Exact reporting date and currency always form part of the keys. Each input is aggregated independently before one-to-one alignment. Omitted dimensions are deliberately aggregated away and will not appear in breakdowns of this calculated measure.')
    st.caption('This first version calculates within one approved dataset, plus its valid calculated measures. It does not guess joins across independent sources. Combine compatible measures into an approved model first.')
    deps={derived[m]:active[derived[m]]['signature'] for m in inputs.values() if m in derived}
    signature=model_signature(base[source],source,name,inputs,keys,deps)
    target=source+'::'+name
    provided_conflict=base[source].measure.astype('string').str.casefold().eq(name.casefold()).any()
    if provided_conflict:st.warning('This dataset already provides '+name+'. Use that source-provided value or prepare a separate reviewed model; a duplicate measure is not added alongside it.')
    if st.button('Preview calculated measure',key='calc_preview_button',type='primary',disabled=any(v is None for v in inputs.values()) or bool(provided_conflict)):
        try:
            result,evidence,formula=calculate_measure(data,name,inputs,keys)
            st.session_state.calculation_preview={'signature':signature,'data':result,'evidence':evidence,'formula':formula,'name':name,
                'source_key':source,'base_fingerprint':fingerprint(base[source]),'inputs':inputs,'grain':keys,'dependencies':deps}
        except (ValueError,TypeError,KeyError) as exc:
            st.session_state.pop('calculation_preview',None);st.error(str(exc))
    preview=st.session_state.get('calculation_preview')
    if preview and preview['signature']!=signature:
        st.info('The source, formula or business keys changed. Preview again before approval.')
    elif preview:
        st.markdown('**Formula:** '+preview['formula'])
        st.markdown('**Aligned input totals**');st.dataframe(preview['evidence'],hide_index=True,use_container_width=True)
        st.markdown('**Proposed calculated values**');st.dataframe(preview['data'],hide_index=True,use_container_width=True)
        st.download_button('Download aligned input evidence',preview['evidence'].to_csv(index=False).encode(),file_name='calculation_input_evidence.csv',key='calc_evidence_download')
        totals=[]
        for ccy,part in preview['data'].groupby('currency'):
            metrics=summary(part)
            totals.append({'Currency':ccy,'Measure':name,'Actual':metrics['actual'],'Budget':metrics['budget'],'Variance (pp)' if recipe['kind']=='ratio' else 'Variance':metrics['variance']})
        st.dataframe(pd.DataFrame(totals),hide_index=True,use_container_width=True)
        if recipe['kind']=='ratio':
            st.info('Margins are recalculated as total profit ÷ total revenue × 100 after each filter or grouping. They are not added or averaged. Actual and budget are percentages; variance is percentage points (pp). A zero denominator is undefined, and missing budgets remain unknown.')
        replace=False
        if target in registry:replace=st.checkbox('Replace the previously approved definition of this calculated measure',key='calc_replace_'+signature)
        accepted=st.checkbox('I verified the input meanings, signs, matching periods/currencies, business keys, aggregation level and formula. Approve this calculated definition for analysis.',key='calc_accept_'+signature)
        if st.button('Approve calculated measure',key='calc_approve_button',disabled=not accepted or (target in registry and not replace)):
            try:
                approve_calculation(st.session_state,target,preview,signature,replace)
                st.success('Calculated definition approved. It will appear in Overview, Analysis, period comparison and AI Analyst on the next page selection. Source-provided measures were not changed.')
            except ValueError as exc:st.error(str(exc))
    st.markdown('#### Approved calculated definitions')
    active=active_calculations(base,registry)
    for key,entry in list(registry.items()):
        st.write(entry['name']+' · '+entry['source_key']+' · '+('Active' if key in active else 'Stale or missing dependency — excluded from current analysis'))
        st.caption(entry['formula'])
        report={k:v for k,v in entry.items() if k not in ('data','evidence')}
        st.download_button('Download definition and approval',json.dumps(report,indent=2,default=str).encode(),file_name='calculated_measure_definition.json',key='calc_export_'+key)
        st.download_button('Download calculated values',entry['data'].to_csv(index=False).encode(),file_name='calculated_measure_values.csv',key='calc_values_'+key)
        if st.button('Withdraw calculated definition',key='calc_withdraw_'+key):
            registry.pop(key);st.rerun()
