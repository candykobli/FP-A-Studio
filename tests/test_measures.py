from pathlib import Path
import pandas as pd
import pytest
from workspace import prepare,prepare_measures


def wide():
    return pd.DataFrame({'date':['2026-01-01','2026-02-01'],'revenue':[100,200],
        'revenue_budget':[110,210],'expense':[60,80],'expense_budget':[55,75],'currency':['EUR','EUR']})


def specs():
    return [{'name':'Revenue','actual':'revenue','budget':'revenue_budget'},
            {'name':'Expenses','actual':'expense','budget':'expense_budget'}]


def test_wide_expansion_preserves_values_and_lineage():
    raw=wide();before=raw.copy(deep=True)
    facts,totals=prepare_measures(raw,{'date':'date','currency':'currency'},'test',specs())
    assert len(facts)==4
    assert facts.groupby('measure').actual.sum().to_dict()=={'Revenue':300,'Expenses':140}
    assert facts.groupby('measure').budget.sum().to_dict()=={'Revenue':320,'Expenses':130}
    assert facts.groupby('measure').source_row.apply(list).to_dict()=={'Expenses':['0','1'],'Revenue':['0','1']}
    assert len(totals)==2 and facts.source.nunique()==1
    pd.testing.assert_frame_equal(raw,before)


def test_wide_reuse_names_and_invalid_values_block_entire_model():
    shared={'date':'date','currency':'currency'}
    bad=specs();bad[1]['actual']='revenue'
    with pytest.raises(ValueError,match='double count'):prepare_measures(wide(),shared,'x',bad)
    bad=specs();bad[1]['name']=' revenue '
    with pytest.raises(ValueError,match='distinct'):prepare_measures(wide(),shared,'x',bad)
    raw=wide().astype(object);raw.loc[1,'expense']='bad'
    with pytest.raises(ValueError,match='invalid actual'):prepare_measures(raw,shared,'x',specs())


def test_long_measure_column_retains_each_row_and_rejects_blanks():
    raw=pd.DataFrame({'date':['2026-01-01']*2,'amount':[100,60],'kind':['Revenue','Expenses'],'currency':['EUR']*2})
    mapping={'date':'date','actual':'amount','measure':'kind','category':'kind','currency':'currency'}
    facts,totals=prepare(raw,mapping,'test','From column')
    assert facts.measure.tolist()==['Revenue','Expenses'] and len(totals)==2
    raw.loc[1,'kind']=' '
    with pytest.raises(ValueError,match='blank names'):prepare(raw,mapping,'test','From column')


def test_multi_measure_ui_publish_and_analysis_selector():
    from streamlit.testing.v1 import AppTest
    app=AppTest.from_file(str(Path(__file__).parents[1]/'app.py'),default_timeout=45).run()
    app.session_state['sources']={'Financials':wide()}
    app.sidebar.radio[0].set_value('Data Workspace').run()
    next(x for x in app.radio if x.label=='How are measures stored in this source?').set_value('Each measure has its own amount columns').run()
    name='Original · Financials'
    for i,s in enumerate(specs()):
        app.text_input(key=f'wide_name_{name}_{i}').set_value(s['name']).run()
        app.selectbox(key=f'wide_actual_{name}_{i}').select(s['actual']).run()
        app.selectbox(key=f'wide_budget_{name}_{i}').select(s['budget']).run()
    assert not app.exception and not app.session_state['facts']
    next(x for x in app.checkbox if x.label.startswith('I reviewed the quality')).check().run()
    next(x for x in app.button if x.label=='Approve & publish to analysis').click().run()
    assert not app.exception
    assert set(app.session_state['facts'][name].measure)=={'Revenue','Expenses'}
    app.sidebar.radio[0].set_value('Analysis').run()
    selector=next(x for x in app.selectbox if x.label=='Measure to analyze')
    assert selector.options==['Expenses','Revenue']
    selector.select('Revenue').run()
    assert not app.exception
    # Defaults retain the existing single-measure route and remain backwards compatible.
    app.sidebar.radio[0].set_value('Overview').run()
    assert next(x for x in app.selectbox if x.label=='Overview measure').options==['Expenses','Revenue']
