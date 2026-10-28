from pathlib import Path
import pandas as pd
import pytest
from model_repair import candidates, diagnose, repair_preview, verify_model


def messy():
    return pd.DataFrame({' Month ':['2026-01-01','2026-02-01'],
        ' Net Sales ':[' 100 ','200'], 'Sales Budget':['110',''],
        'Region':[' France ','France'], 'Currency':[' eur ','eur']})


def mapping():
    return {'date':' Month ','actual':' Net Sales ','budget':'Sales Budget','entity':'Region','currency':'Currency','category':None}


def test_repairs_preserve_original_and_update_mapping_references():
    df=messy(); before=df.copy(deep=True)
    out,mapped,renames,log=repair_preview(df,mapping(),rename=True,trim=True,uppercase_currency=True,numeric=True,date_format='%Y-%m-%d')
    pd.testing.assert_frame_equal(df,before)
    assert mapped['actual']=='net_sales' and renames[' Month ']=='month'
    assert out.net_sales.tolist()==[100,200]
    assert out.currency.tolist()==['EUR','EUR']
    assert out.region.tolist()==['France','France'] and len(log)==6
    facts,totals=verify_model(out,mapped,'Revenue',1)
    assert len(facts)==len(df) and totals.iloc[0]['Actual']==300
    assert pd.isna(facts.loc[1,'budget'])


def test_collision_invalid_amounts_and_dates_block_repairs():
    df=messy()
    df['net sales']=[1,2]
    with pytest.raises(ValueError,match='duplicated'):repair_preview(df,mapping(),rename=True)
    df=messy();df.loc[0,' Net Sales ']='1,200'
    with pytest.raises(ValueError,match='invalid numbers'):repair_preview(df,mapping(),numeric=True)
    df=messy();df.loc[0,' Month ']='2026-02-30'
    with pytest.raises(ValueError,match='Invalid calendar'):repair_preview(df,mapping(),date_format='%Y-%m-%d')
    df[' Month ']=[46000,46001]
    with pytest.raises(ValueError,match='Numeric dates'):repair_preview(df,mapping(),date_format='%Y-%m-%d')


def test_ambiguous_dates_only_change_under_explicit_format():
    df=messy();df[' Month ']=['01/02/2026','02/03/2026']
    with pytest.raises(ValueError,match='explicit reporting date format'):repair_preview(df,mapping())
    a,_,_,_=repair_preview(df,mapping(),date_format='%d/%m/%Y')
    b,_,_,_=repair_preview(df,mapping(),date_format='%m/%d/%Y')
    assert a[' Month '].iloc[0].month==2 and b[' Month '].iloc[0].month==1
    assert any('explicit' in x for x in diagnose(df,mapping()).Finding)


def test_duplicate_grain_and_ambiguous_names_are_never_resolved_automatically():
    df=messy();df['Actual']=[100,200]
    assert len(candidates(df)['actual'])==2
    report=diagnose(df,{**mapping(),'actual':None},'Amount',['Currency'])
    assert any('Several plausible' in x for x in report.Finding)
    df=pd.concat([df,df.iloc[[0]]],ignore_index=True)
    before=df.copy(deep=True)
    report=diagnose(df,mapping(),'Revenue',[' Month ','Region'])
    assert any('repeat the selected' in x for x in report.Finding)
    out,*_=repair_preview(df,mapping(),trim=True)
    assert len(out)==3
    pd.testing.assert_frame_equal(df,before)


def test_model_repair_ui_draft_handoff_and_stale_preview():
    from streamlit.testing.v1 import AppTest
    app=AppTest.from_file(str(Path(__file__).parents[1]/'app.py'),default_timeout=45).run()
    original=messy()
    app.session_state['sources']={'Messy model':original.copy(deep=True)}
    app.sidebar.radio[0].set_value('Data Workspace').run()
    assert not app.exception
    app.text_input(key=next(x.key for x in app.text_input if x.label=='Business measure')).set_value('Revenue').run()
    for label in ('Standardize column names (for example, Net Sales → net_sales)',
                  'Trim leading and trailing spaces in text values',
                  'Uppercase currency codes (does not convert amounts)',
                  'Convert plain actual / budget values to numeric types'):
        next(x for x in app.checkbox if x.label==label).check().run()
    next(x for x in app.selectbox if x.label=='Reporting date interpretation').select('ISO date (YYYY-MM-DD)').run()
    next(x for x in app.button if x.label=='Check and preview proposed model').click().run()
    assert not app.exception
    save=lambda:next(x for x in app.button if x.label=='Save proposed model as a prepared draft')
    assert save().disabled
    next(x for x in app.checkbox if x.label.startswith('I reviewed the mapping, date')).check().run()
    assert not save().disabled
    # Changing semantics invalidates the preview and its approval.
    next(x for x in app.text_input if x.label=='Business measure').set_value('Expenses').run()
    assert not any(x.label=='Save proposed model as a prepared draft' for x in app.button)
    next(x for x in app.button if x.label=='Check and preview proposed model').click().run()
    next(x for x in app.checkbox if x.label.startswith('I reviewed the mapping, date')).check().run()
    save().click().run()
    assert not app.exception and not app.session_state['facts']
    assert len(app.session_state['dm_outputs'])==1
    pd.testing.assert_frame_equal(app.session_state['sources']['Messy model'],original)
    prepared=next(iter(app.session_state['mapping_drafts']))
    app.multiselect(key='workspace_sources').set_value([prepared]).run()
    assert not app.exception
    next(x for x in app.radio if x.label=='What would you like to do?').set_value('Quick verify & approve').run()
    assert not app.exception
    assert next(x for x in app.selectbox if x.label=='Actual column').value=='net_sales'
    assert next(x for x in app.text_input if x.label.startswith('Measure name')).value=='Expenses'
    assert not app.session_state['facts']
