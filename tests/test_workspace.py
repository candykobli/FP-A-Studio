import pandas as pd
import pytest
from workspace import quality, prepare, publish


def sample():
    return pd.DataFrame({'date':['2026-01-01','2026-02-01'], 'amount':[100,200], 'ccy':['EUR','EUR']})


def test_profile_detects_blank_spacing_duplicate_and_mixed_values():
    df=pd.DataFrame({'value':['  a ','',None,'2','bad','bad']})
    before=df.copy(deep=True)
    table,duplicates,issues=quality(df)
    assert table.iloc[0]['Blanks']==2
    assert table.iloc[0]['Whitespace']==1
    assert table.iloc[0]['Mixed numeric values']==3
    assert duplicates==2 and issues>0
    pd.testing.assert_frame_equal(df,before)


def test_verification_retains_all_rows_and_separates_currencies():
    df=sample(); df.loc[1,'ccy']='USD'
    before=df.copy(deep=True)
    result,totals=prepare(df,{'date':'date','actual':'amount','currency':'ccy'},'sales','Revenue')
    assert len(result)==2 and len(totals)==2
    pd.testing.assert_frame_equal(df,before)
    for column,value in [('date','bad'),('amount','bad'),('ccy','')]:
        broken=df.astype(object).copy(); broken.loc[0,column]=value
        with pytest.raises(ValueError):prepare(broken,{'date':'date','actual':'amount','currency':'ccy'},'x','Revenue')


def test_publication_blocks_stale_drafts_and_double_counted_lineage():
    state={'facts':{},'published_parents':{}}
    df=sample()
    with pytest.raises(ValueError):publish(state,'x',df,'old','new',{'a'})
    assert not state['facts']
    publish(state,'x',df,'v1','v1',{'a'})
    df.loc[0,'amount']=999
    assert state['facts']['x'].loc[0,'amount']==100
    with pytest.raises(ValueError):publish(state,'joined',df,'v1','v1',{'a','b'})
    publish(state,'joined',df,'v1','v1',{'a','b'},replace=True)
    assert list(state['facts'])==['joined']


def test_app_navigation_and_approval_flow():
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    app=AppTest.from_file(str(Path(__file__).parents[1]/'app.py'),default_timeout=30).run()
    assert not app.exception
    app.sidebar.radio[0].set_value('Calculator').run()
    assert not app.exception
    assert any(x.label=='Calculate' for x in app.button)
    app.session_state['sources']={'Sales':sample()}
    app.sidebar.radio[0].set_value('Data Workspace').run()
    assert not app.exception
    assert not app.session_state['facts']
    button=next(x for x in app.button if x.label=='Approve & publish to analysis')
    assert button.disabled
    next(x for x in app.checkbox if x.label.startswith('I reviewed the quality')).check().run()
    next(x for x in app.button if x.label=='Approve & publish to analysis').click().run()
    assert not app.exception
    assert len(app.session_state['facts'])==1
    app.sidebar.radio[0].set_value('Overview').run()
    assert not app.exception
    for page in ('Analysis','Period comparison','AI analyst'):
        app.sidebar.radio[0].set_value(page).run()
        assert not app.exception
    app.session_state['sources']={'Sales':sample(),'Other':sample(),'Third':sample()}
    app.sidebar.radio[0].set_value('Data Workspace').run()
    assert not app.exception
    app.multiselect(key='workspace_sources').set_value(['Original · Sales','Original · Other','Original · Third']).run()
    assert not app.exception
    assert not app.session_state['dm_outputs']
    next(x for x in app.button if x.label=='Preview validated join').click().run()
    assert not app.exception
    next(x for x in app.button if x.label=='Save joined dataset to workspace').click().run()
    assert not app.exception
    assert len(app.session_state['dm_outputs'])==1
    assert len(app.session_state['facts'])==1  # A prepared model is never auto-published.


def test_fx_mapping_and_partial_budgets_are_guarded():
    from engine import grouped,monthly
    df=sample().rename(columns={'amount':'converted_amount','ccy':'reporting_currency'})
    df['native_budget']=[110,220]
    mapping={'date':'date','actual':'converted_amount','currency':'reporting_currency','budget':'native_budget'}
    with pytest.raises(ValueError,match='native-currency budget'):
        prepare(df,mapping,'fx','Revenue')
    mapping.pop('budget')
    facts,_=prepare(df,mapping,'fx','Revenue')
    facts['budget']=[100,float('nan')]
    assert pd.isna(grouped(facts,'entity').iloc[0]['Budget'])
    facts['date']=pd.to_datetime(['2026-01-01','2026-01-02'])
    assert pd.isna(monthly(facts).iloc[0]['Budget'])
