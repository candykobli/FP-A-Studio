from pathlib import Path
import pandas as pd
import pytest
from dimensions import dimension_choices,display_group
from page_questions import answer_question
from workspace import prepare,prepare_measures


def raw():
    return pd.DataFrame({'date':['2025-01-01','2025-01-01','2026-01-01'],
        'actual':[120,80,150],'budget':[100,90,140],'country':['France','Germany','France'],
        'product':['A','B','A'],'currency':['EUR']*3})


def facts():
    return prepare(raw(),{'date':'date','actual':'actual','budget':'budget','entity':'country','currency':'currency'},
        'Sales','Revenue',dimensions={'Country':'country','Product':'product'})[0]


def test_confirmed_dimensions_survive_and_unavailable_choices_stay_hidden():
    df=raw(); original=df.copy(deep=True)
    f=facts(); dims=dimension_choices(f)
    assert list(dims)==['Country','Product','Source']
    assert 'Category' not in dims and 'Actual' not in dims
    table=display_group(f,dims['Country'],'Country')
    assert table.Actual.sum()==350
    assert table.set_index('Country').loc['France','Variance']==30
    pd.testing.assert_frame_equal(df,original)
    with pytest.raises(ValueError,match='reserved'):
        prepare(df,{'date':'date','actual':'actual','currency':'currency'},'s','Revenue',dimensions={'Variance':'product'})


def test_wide_measures_keep_dimensions_without_merging_rows():
    f,_=prepare_measures(raw(),{'date':'date','currency':'currency'},'s',[
        {'name':'Revenue','actual':'actual'},{'name':'Budget reference','actual':'budget'}],dimensions={'Product':'product'})
    assert len(f)==6
    assert f.groupby('measure')['dimension::Product'].apply(tuple).nunique()==1


def test_variance_answers_show_formula_and_selected_data_workings():
    text,table=answer_question('How do you calculate variance?','Overview',facts())
    assert 'Actual − Budget' in text and '350.00 − 330.00' in text and '+6.06%' in text
    assert table is None
    text,table=answer_question('Explain variance by Product in France','Overview',facts())
    assert '270.00 − 240.00' in text and table.Actual.sum()==270 and 'Product' in table
    assert 'does not establish business causes' in text


def test_zero_partial_negative_budgets_and_missing_dimensions():
    f=facts(); f['budget']=0
    text,_=answer_question('What is the variance?','Analysis',f)
    assert 'undefined because budget is zero' in text
    f['budget']=[100,None,140]
    text,_=answer_question('Show variance','Analysis',f)
    assert 'coverage is incomplete' in text
    f['budget']=[-100,-90,-140]
    text,_=answer_question('How calculate variance?','Analysis',f)
    assert '|-330.00|' in text
    text,_=answer_question('Variance by Category','Analysis',f)
    assert 'no confirmed category' in text


def test_questions_refuse_scope_expansion_unknown_filters_and_mutations():
    f=facts()
    for question,expected in [('Variance in USD','will not convert'),('Variance in Spain','could not match'),
        ('Variance in 2030','outside'),('Approve and publish this','do not change')]:
        text,_=answer_question(question,'Overview',f)
        assert expected in text
    text,_=answer_question('Revenue variance','Analysis',f.assign(measure='Expenses'),{'available_measures':['Revenue','Expenses']})
    assert 'scoped to Expenses' in text
    text,_=answer_question('Variance in 2026','Overview',f)
    assert '150.00 − 140.00' in text


def test_period_chat_uses_bridge_not_combined_actual_budget():
    meta={'dimension':'Country','comparison':[{'Country':'France','Change':30}],
        'first':120,'second':150,'first_rows':1,'second_rows':1}
    text,table=answer_question('Explain the change','Period comparison',facts(),meta)
    assert '150.00 − 120.00' in text and 'Period change' in text
    text,_=answer_question('Explain variance','Period comparison',facts(),meta)
    assert 'On this page' in text and '150.00 − 120.00' in text
    text,_=answer_question('Explain change','Period comparison',facts(),{**meta,'first_rows':0})
    assert 'not a verified zero' in text


def test_page_chats_work_in_empty_workspace_and_calculator():
    text,table=answer_question('Why are rows flagged?','Data Workspace',raw_sources={'test':raw()})
    assert 'No rows are removed' in text and len(table)>0
    text,_=answer_question('Explain the result','Calculator',metadata={'expression':'(120-100)/100*100'})
    assert '**20**' in text
    text,_=answer_question('How calculate variance?','AI analyst')
    assert 'Actual − Budget' in text


def test_overview_dropdowns_context_chat_filters_and_history_isolation():
    from streamlit.testing.v1 import AppTest
    app=AppTest.from_file(str(Path(__file__).parents[1]/'app.py'),default_timeout=45).run()
    app.session_state['facts']={'Sales':facts()}
    app.run()
    assert not app.exception
    left=app.selectbox(key='overview_left');right=app.selectbox(key='overview_right')
    assert left.options==right.options==['Country','Product','Source']
    assert left.value=='Country' and right.value=='Source'
    right.select('Product').run()
    assert app.selectbox(key='overview_left').value=='Country'
    app.chat_input[0].set_value('How do you calculate variance?').run()
    assert not app.exception
    assert any('350.00 − 330.00' in m.value for m in app.markdown)
    app.multiselect(key='overview_dimension_dimension::Country').set_value(['France']).run()
    assert not app.exception
    assert not any('350.00 − 330.00' in m.value for m in app.markdown)
    app.chat_input[0].set_value('Show my variance').run()
    assert any('270.00 − 240.00' in m.value for m in app.markdown)
    app.sidebar.radio[0].set_value('Analysis').run()
    assert not app.exception and not any('270.00 − 240.00' in m.value for m in app.markdown)
    assert len(app.chat_input)==1
    app.sidebar.radio[0].set_value('AI analyst').run()
    assert not app.exception and len(app.chat_input)==1
    app.sidebar.radio[0].set_value('Calculator').run()
    assert not app.exception and len(app.chat_input)==1
