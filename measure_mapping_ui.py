"""Select how financial measures are represented, without guessing business meaning."""
import json
import streamlit as st
from engine import suggestions,normalize_name
from workspace import prepare, prepare_measures, fingerprint
from measure_catalog import source_measure_input


def map_measures(name,raw,draft):
    layout=st.radio('How are measures stored in this source?',[
        'One measure for this source','Measure names are in a column',
        'Each measure has its own amount columns'],key='measure_layout_'+name)
    wide=layout=='Each measure has its own amount columns'
    long=layout=='Measure names are in a column'
    proposed={**suggestions(raw),**draft.get('mapping',{})}
    options=['(none)']+list(raw.columns); mapping={}; cols=st.columns(3)
    roles=['date','category','entity','currency'] if wide else ['date','actual','budget','category','entity','currency']
    for i,role in enumerate(roles):
        with cols[i%3]:
            guess=proposed.get(role)
            value=st.selectbox(role.title()+' column',options,index=options.index(guess) if guess in options else 0,key=name+role)
            mapping[role]=None if value=='(none)' else value
    specs=[]; reverse=False
    if wide:
        st.caption('Define each measure explicitly. Each source row creates one fact per defined measure; no join or deduplication occurs. Do not map a total and its components as if they were separate transactions.')
        count=st.number_input('Number of measures',min_value=2,max_value=20,value=2,step=1,key='measure_count_'+name)
        for i in range(int(count)):
            st.markdown(f'**Measure {i+1}**')
            a,b,c=st.columns(3)
            with a:label=source_measure_input(f'wide_name_{name}_{i}',default='',custom_label='Measure name')
            with b:actual=st.selectbox('Actual amount column',options,key=f'wide_actual_{name}_{i}')
            with c:budget=st.selectbox('Budget amount column (optional)',options,key=f'wide_budget_{name}_{i}')
            sign=st.checkbox('Reverse signs for this measure',key=f'wide_reverse_{name}_{i}')
            specs.append({'name':label,'actual':None if actual=='(none)' else actual,'budget':None if budget=='(none)' else budget,'sign':-1 if sign else 1})
        measure='Multiple measures'
    else:
        if long:
            guess=proposed.get('measure') or proposed.get('category')
            selected=st.selectbox('Measure-name column',options,index=options.index(guess) if guess in options else 0,key='measure_column_'+name)
            mapping['measure']=None if selected=='(none)' else selected
            measure='From measure-name column'
        else:
            measure=source_measure_input('measure_'+name,default=draft.get('measure','Amount'),custom_label='Measure name (Revenue, Expenses, Headcount…)')
        reverse=st.checkbox('Reverse actual and budget signs',value=draft.get('reverse',False),key='sign_'+name)
    if draft:st.info('Mapping choices were carried over from model repair. Review them and the figures before approving publication.')
    st.markdown('#### Choose business dimensions to retain')
    dimensions={}
    if mapping.get('entity'):
        original=mapping['entity']
        default='Country' if normalize_name(original) in ('country','region','entity') else str(original).replace('_',' ').title()
        label=st.text_input('Business label for the mapped entity column',value=default,key='entity_label_'+name)
        dimensions[label]=original
    if mapping.get('category'):
        label=st.text_input('Business label for the mapped category column',value='Category',key='category_label_'+name)
        if label in dimensions:st.warning('Business dimension labels must be distinct.'); return None
        dimensions[label]=mapping['category']
    excluded={v for v in mapping.values() if v is not None}
    excluded.update(s.get(k) for s in specs for k in ('actual','budget') if s.get(k))
    candidates=[c for c in raw if c not in excluded]
    extra=st.multiselect('Additional dimensions for filters, breakdowns and questions',candidates,key='extra_dimensions_'+name)
    st.caption('Only confirmed dimensions are published. Choose descriptive fields such as Product, Region or Department. Numeric amounts and identifiers are not automatically included. Missing dimension values remain missing.')
    for c in extra:
        label=st.text_input('Business label · '+str(c),value=str(c).replace('_',' ').strip().title(),key='dim_label_'+name+'_'+str(c))
        if label in dimensions:st.warning('Business dimension labels must be distinct.'); return None
        dimensions[label]=c
    config={'layout':layout,'mapping':mapping,'measure':measure,'reverse_sign':reverse,'measures':specs,'dimensions':dimensions}
    signature=fingerprint(raw)+json.dumps(config,sort_keys=True)
    try:
        if long and not mapping.get('measure'):raise ValueError('Select the column containing measure names.')
        if wide:result,totals=prepare_measures(raw,mapping,name,specs,dimensions=dimensions)
        else:result,totals=prepare(raw,mapping,name,measure,-1 if reverse else 1,dimensions=dimensions)
    except (ValueError,TypeError,KeyError) as exc:
        st.warning(str(exc)); return None
    return result,totals,signature,config
