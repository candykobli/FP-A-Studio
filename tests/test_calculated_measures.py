from pathlib import Path
from datetime import date
import pandas as pd
import pytest
from workspace import prepare,prepare_measures,fingerprint
from engine import combine,summary,grouped,monthly,compare
from calculated_measures import calculate_measure,approve_calculation,active_calculations,available_input,model_signature
from page_questions import answer_question


def base_model():
    raw=pd.DataFrame({'date':['2026-01-01','2026-02-01'],'country':['France','Germany'],
        'revenue':[100,900],'cost':[50,810],'rev_budget':[100,900],'cost_budget':[60,720],'currency':['EUR','EUR']})
    model,_=prepare_measures(raw,{'date':'date','currency':'currency'},'Financials',[
        {'name':'Revenue','actual':'revenue','budget':'rev_budget'},
        {'name':'Cost of sales','actual':'cost','budget':'cost_budget'}],dimensions={'Country':'country'})
    return model


def preview(base,source,name,inputs,grain,registry):
    data,derived=available_input({source:base},registry,source)
    active=active_calculations({source:base},registry)
    deps={derived[m]:active[derived[m]]['signature'] for m in inputs.values() if m in derived}
    result,evidence,formula=calculate_measure(data,name,inputs,grain)
    sig=model_signature(base,source,name,inputs,grain,deps)
    return {'data':result,'evidence':evidence,'formula':formula,'signature':sig,'source_key':source,
        'base_fingerprint':fingerprint(base),'name':name,'dependencies':deps,'inputs':inputs,'grain':grain}


def model_and_margin():
    base=base_model();state={'calculated_measures':{}}
    gross=preview(base,'Financials','Gross profit',{'Revenue':'Revenue','Cost of sales':'Cost of sales'},['dimension::Country'],{})
    approve_calculation(state,'Financials::Gross profit',gross,gross['signature'])
    margin=preview(base,'Financials','Gross profit margin (%)',{'Gross profit':'Gross profit','Revenue':'Revenue'},['dimension::Country'],state['calculated_measures'])
    approve_calculation(state,'Financials::Gross profit margin (%)',margin,margin['signature'])
    return base,state,gross,margin


def test_source_measure_names_do_not_compute_formulas_or_allow_ambiguous_profit():
    raw=pd.DataFrame({'date':['2026-01-01'],'actual':[123],'currency':['EUR']})
    mapping={'date':'date','actual':'actual','currency':'currency'}
    model,_=prepare(raw,mapping,'s','Gross profit')
    assert model.actual.iloc[0]==123 and model.measure_origin.iloc[0]=='Source-provided'
    for label in ('Profit','Profit margin','Net profit margin (%)'):
        with pytest.raises(ValueError):prepare(raw,mapping,'s',label)


def test_amount_calculation_is_explicit_and_keeps_source_inputs_unchanged():
    model=base_model();before=model.copy(deep=True)
    p=preview(model,'Financials','Gross profit',{'Revenue':'Revenue','Cost of sales':'Cost of sales'},['dimension::Country'],{})
    assert p['data'].actual.tolist()==[50,90]
    assert p['data'].budget.tolist()==[40,180]
    assert p['formula']=='Revenue − Cost of sales'
    text,_=answer_question('How do you calculate Gross profit from Revenue?','Analysis',p['data'],{'available_measures':['Revenue','Cost of sales','Gross profit']})
    assert '1,000.00 (Revenue)' in text and '860.00 (Cost of sales)' in text and '140.00 EUR' in text
    pd.testing.assert_frame_equal(model,before)


def test_margin_recomputes_ratios_of_sums_instead_of_averaging_percentages():
    base,state,gross,margin=model_and_margin()
    data=margin['data'];s=summary(data)
    assert data.actual.tolist()==[50,10]  # Row mean is 30%; correct total is 14%.
    assert s['actual']==pytest.approx(14) and s['budget']==pytest.approx(22) and s['variance']==pytest.approx(-8) and s['variance_pct'] is None
    assert s['unit']=='%' and s['variance_unit']=='pp'
    assert summary(data[data['dimension::Country']=='France'])['actual']==50
    assert grouped(data,'source').Actual.iloc[0]==pytest.approx(14)
    assert monthly(data).Actual.tolist()==[50,10]
    table,a,b=compare(data,date(2026,1,1),date(2026,1,31),date(2026,2,1),date(2026,2,28),'source')
    assert a['actual']==50 and b['actual']==10 and table['Contribution %'].isna().all()
    text,_=answer_question('How do you calculate variance?','Overview',data)
    assert '140.00 ÷ 1,000.00' in text and '-8.00 pp' in text
    text,_=answer_question('How do you calculate Gross profit margin (%) from Revenue?','Overview',data,{'available_measures':['Revenue','Gross profit','Gross profit margin (%)']})
    assert '140.00 ÷ 1,000.00' in text


def test_unmatched_keys_and_percentage_inputs_are_blocked_without_unsafe_joins():
    model=base_model();model.loc[model.measure=='Cost of sales','date']+=pd.Timedelta(days=1)
    with pytest.raises(ValueError,match='same dates'):calculate_measure(model,'Gross profit',{'Revenue':'Revenue','Cost of sales':'Cost of sales'},['dimension::Country'])
    _,_,_,margin=model_and_margin()
    data=combine([base_model(),margin['data']])
    with pytest.raises(ValueError,match='not percentages'):calculate_measure(data,'Gross profit',{'Revenue':'Revenue','Cost of sales':'Gross profit margin (%)'},[])
    with pytest.raises(ValueError,match='distinct source measure'):calculate_measure(base_model(),'Gross profit',{'Revenue':'Revenue','Cost of sales':'Revenue'},[])
    counts=base_model();counts.loc[counts.measure=='Revenue','measure_unit']='count'
    with pytest.raises(ValueError,match='comparable monetary'):calculate_measure(counts,'Gross profit',{'Revenue':'Revenue','Cost of sales':'Cost of sales'},[])


def test_zero_denominator_and_missing_budgets_stay_unknown():
    _,_,gross,margin=model_and_margin()
    data=margin['data'].copy();data['ratio_actual_denominator']=0
    assert summary(data)['actual'] is None and summary(data)['variance'] is None
    data=margin['data'].copy();data.loc[0,'ratio_budget_numerator']=float('nan')
    assert summary(data)['budget'] is None and grouped(data,'source').Budget.isna().all()
    # A zero individual denominator does not turn the complete aggregate into a row-average.
    data=margin['data'].copy();data.loc[0,'ratio_actual_numerator']=0;data.loc[0,'ratio_actual_denominator']=0
    assert summary(data)['actual']==10


def test_approval_staleness_dependency_cascade_and_cycles():
    base,state,gross,margin=model_and_margin()
    assert len(active_calculations({'Financials':base},state['calculated_measures']))==2
    changed=base.copy();changed.loc[0,'actual']=999
    assert not active_calculations({'Financials':changed},state['calculated_measures'])
    with pytest.raises(ValueError,match='changed'):approve_calculation(state,'another',gross,'new')
    with pytest.raises(ValueError,match='replacement'):approve_calculation(state,'Financials::Gross profit',gross,gross['signature'])
    altered={**gross,'dependencies':{'Financials::Gross profit margin (%)':margin['signature']}}
    with pytest.raises(ValueError,match='circular'):approve_calculation(state,'Financials::Gross profit',altered,altered['signature'],replace=True)
    # A changed approved parent invalidates its descendants, even before a source edit.
    state['calculated_measures']['Financials::Gross profit']['signature']='revised'
    active=active_calculations({'Financials':base},state['calculated_measures'])
    assert 'Financials::Gross profit margin (%)' not in active


def test_calculated_measure_ui_requires_preview_approval_then_aggregates_margin():
    from streamlit.testing.v1 import AppTest
    app=AppTest.from_file(str(Path(__file__).parents[1]/'app.py'),default_timeout=45).run()
    app.session_state['sources']={'Dummy':pd.DataFrame({'date':['2026-01-01'],'actual':[1],'currency':['EUR']})}
    app.session_state['facts']={'Financials':base_model()}
    app.sidebar.radio[0].set_value('Data Workspace').run()
    assert not app.exception
    app.button(key='calc_preview_button').click().run()
    assert not app.exception and app.button(key='calc_approve_button').disabled
    assert not app.session_state['calculated_measures']
    next(x for x in app.checkbox if x.label.startswith('I verified the input meanings')).check().run()
    app.button(key='calc_approve_button').click().run()
    assert not app.exception and len(app.session_state['calculated_measures'])==1
    app.selectbox(key='calc_recipe').select('Gross profit margin (%)').run()
    # A new recipe cannot approve the previous preview.
    assert not any(x.key=='calc_approve_button' for x in app.button)
    app.button(key='calc_preview_button').click().run()
    next(x for x in app.checkbox if x.label.startswith('I verified the input meanings')).check().run()
    app.button(key='calc_approve_button').click().run()
    assert not app.exception and len(app.session_state['calculated_measures'])==2
    app.sidebar.radio[0].set_value('Overview').run()
    next(x for x in app.selectbox if x.label=='Overview measure').select('Gross profit margin (%)').run()
    assert not app.exception
    metric=next(x for x in app.metric if x.label=='Actual (%)')
    assert metric.value=='14.00'
    app.sidebar.radio[0].set_value('Analysis').run()
    next(x for x in app.selectbox if x.label=='Measure to analyze').select('Gross profit margin (%)').run()
    assert not app.exception
    app.chat_input[0].set_value('Show how this margin is calculated').run()
    assert not app.exception and any('140.00 ÷ 1,000.00' in x.value for x in app.markdown)
