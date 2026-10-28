import hashlib
from pathlib import Path
import pandas as pd
import pytest
from income_statement import EXCLUDE,LINES,map_source,statement_table,reconcile_sources,check_report,approve_report,reject_overlapping_sources
from workspace import fingerprint

SAMPLE=Path(__file__).parents[1]/'sample_data'


def sample(country):
    return pd.read_csv(SAMPLE/f'income_statement_{country}.csv',dtype={'Account':'string'})


def config(country):
    return {'mapping':{'date':'Date','account':'Account','actual':'Actual','budget':'Budget','currency':'Currency'},
        'entity':country,'business_unit':country,'basis':'Monthly activity','date_format':'%Y-%m-%d'}


def rules(country):
    if country=='france':codes=['4000','5000','6000','1000']
    else:codes=['7000','8000','9000','2000']
    lines=['Revenue','Cost of sales','Operating expenses',EXCLUDE]
    return {code:{'line':line,'sign':-1 if country=='france' and line=='Revenue' else 1,
        'reason':'Balance-sheet activity, outside P&L' if line==EXCLUDE else ''} for code,line in zip(codes,lines)}


def detail():
    return pd.concat([map_source(sample(c),c,config(c),rules(c)) for c in ('france','germany')],ignore_index=True)


def test_multiple_units_map_to_shared_lines_and_reconcile_every_source_row():
    before=sample('france')
    raw=before.copy(deep=True)
    map_source(raw,'france',config('france'),rules('france'))
    pd.testing.assert_frame_equal(raw,before)
    d=detail();table,recon,issues=check_report(d,True)
    assert not issues and len(d)==16 and recon['Actual difference'].eq(0).all()
    assert recon['Budget difference'].eq(0).all()
    assert (recon['Source rows']==recon['Included rows']+recon['Excluded rows']+recon['Unmapped rows']).all()
    t=table.set_index('Line')
    assert t.loc['Revenue','Actual']==462000
    assert t.loc['Cost of sales','Actual']==270000
    assert t.loc['Operating profit','Actual']==78000
    assert t.loc['Net profit','Budget']==76000
    assert t.loc['Net profit','Variance']==2000
    assert d['Profit impact'].sum()==78000
    assert d[d.Status=='Excluded']['Exclusion reason'].ne('').all()


def test_unmapped_and_missing_reporting_lines_block_approval():
    d=map_source(sample('france'),'france',config('france'),{})
    _,_,issues=check_report(d,True)
    assert any('unmapped' in x for x in issues)
    with pytest.raises(ValueError,match='unmapped'):approve_report({},d,{'zero_missing':True},'a','a',{})
    d=detail();table,_,issues=check_report(d,False)
    assert table[table.Line=='Net profit'].Actual.isna().all()
    assert any('reporting lines are missing' in x for x in issues)


def test_missing_monthly_line_is_not_filled_by_another_month():
    rows=[]
    for month in ('2026-01-01','2026-02-01'):
        for line in LINES:
            if month=='2026-01-01' and line=='Income tax':continue
            rows.append({'Date':month,'Account':line,'Actual':10,'Budget':9,'Currency':'EUR'})
    raw=pd.DataFrame(rows);r={line:{'line':line,'sign':1} for line in LINES}
    d=map_source(raw,'s',config('france'),r)
    _,_,issues=check_report(d,False)
    assert any('2026-01' in x for x in issues)


def test_partial_budgets_unknown_zero_percent_and_currency_separation():
    d=detail();d.loc[d.index[0],'Budget']=float('nan')
    t=statement_table(d,True).set_index('Line')
    assert pd.isna(t.loc['Revenue','Budget']) and pd.isna(t.loc['Net profit','Variance'])
    d=detail();d['Budget']=0
    assert statement_table(d,True)['Variance %'].isna().all()
    d.loc[d.Source=='germany','Currency']='USD'
    with pytest.raises(ValueError,match='one reporting currency'):statement_table(d,True)
    tables,recon,issues=check_report(d,True)
    assert set(tables.Currency)=={'EUR','USD'} and len(tables)==24 and not issues


def test_invalid_activity_dates_amounts_exclusions_and_lineage_are_blocked():
    raw=sample('france')
    with pytest.raises(ValueError,match='Year-to-date'):map_source(raw,'s',{**config('france'),'basis':'Year-to-date balances'},rules('france'))
    broken=raw.astype(object);broken.loc[0,'Actual']='not a number'
    with pytest.raises(ValueError,match='finite number'):map_source(broken,'s',config('france'),rules('france'))
    broken=raw.copy();broken['Date']=46000
    with pytest.raises(ValueError,match='Numeric dates'):map_source(broken,'s',config('france'),rules('france'))
    r=rules('france');r['1000']['reason']=''
    with pytest.raises(ValueError,match='explicit reason'):map_source(raw,'s',config('france'),r)
    with pytest.raises(ValueError,match='lineage'):reject_overlapping_sources(['Original','Prepared'],{'Prepared':{'Original'}})


def test_approved_snapshots_are_immutable_and_stale_previews_blocked():
    d=detail();state={};cfg={'zero_missing':True,'nested':{'line':'Revenue'}}
    with pytest.raises(ValueError,match='changed'):approve_report(state,d,cfg,'old','new',{})
    snap=approve_report(state,d,cfg,'a','a',{'france':'hash'})
    cfg['nested']['line']='Something else';d.loc[0,'Actual']=999
    assert snap['detail'].loc[0,'Actual']==120000
    assert snap['config']['nested']['line']=='Revenue'
    assert len(state['income_statement_reports'])==1
    from income_statement_ui import export_report
    import io,json,zipfile
    archive=zipfile.ZipFile(io.BytesIO(export_report(snap)))
    assert archive.testzip() is None and len(archive.namelist())==4
    assert json.loads(archive.read('approval_and_mappings.json'))['source_fingerprints']=={'france':'hash'}
    from page_questions import answer_question
    meta={'income_statement':snap['tables'].to_dict(orient='records'),'report_scope':'Approved EUR combined view'}
    text,_=answer_question('What is EBITDA?','Income statement',metadata=meta)
    assert 'cannot calculate' in text
    text,_=answer_question('Net profit for France','Income statement',metadata=meta)
    assert 'visible report filters' in text


def test_income_statement_page_end_to_end():
    from streamlit.testing.v1 import AppTest
    app=AppTest.from_file(str(Path(__file__).parents[1]/'app.py'),default_timeout=45).run()
    app.sidebar.radio[0].set_value('Income statement').run()
    assert not app.exception and len(app.chat_input)==1
    app.button(key='is_load_demo').click().run()
    names=['Original · Demo France','Original · Demo Germany']
    app.multiselect(key='is_sources').set_value(names).run()
    app.checkbox(key='is_zero_missing').check().run()
    app.button(key='is_preview_button').click().run()
    assert not app.exception and app.button(key='is_approve_button').disabled
    for country,name in zip(('france','germany'),names):
        raw=app.session_state['sources'][name.removeprefix('Original · ')]
        token=hashlib.sha256((name+fingerprint(raw)).encode()).hexdigest()[:12]
        for account,rule in rules(country).items():
            key=hashlib.sha256((token+account).encode()).hexdigest()[:16]
            app.selectbox(key='is_line_'+key).select(rule['line']).run()
            if rule['sign']==-1:app.checkbox(key='is_sign_'+key).check().run()
            if rule['line']==EXCLUDE:app.text_input(key='is_reason_'+key).set_value(rule['reason']).run()
    # Every mapping change invalidated the previous report, so approval is hidden.
    assert not any(x.key=='is_approve_button' for x in app.button)
    app.button(key='is_preview_button').click().run()
    assert not app.exception and len(app.chat_input)==1
    assert app.session_state['is_preview']['issues']==[]
    assert not app.session_state['income_statement_reports']
    next(x for x in app.checkbox if x.label.startswith('I verified source coverage')).check().run()
    app.button(key='is_approve_button').click().run()
    assert not app.exception and len(app.session_state['income_statement_reports'])==1
    app.radio(key='is_mode').set_value('Approved reports').run()
    assert not app.exception and len(app.chat_input)==1
    app.chat_input[0].set_value('How do you calculate net profit?').run()
    assert not app.exception
    assert any('Profit before tax' in x.value and '78,000.00' in x.value for x in app.markdown)
    # Saved reports remain available even if the working sources change.
    changed=app.session_state['sources']['Demo France'].copy();changed.loc[0,'Actual']=-999999
    app.session_state['sources']={'Demo France':changed}
    app.run()
    net=app.session_state['income_statement_reports'][0]['tables'].set_index('Line').loc['Net profit','Actual']
    assert net==78000 and not app.exception
