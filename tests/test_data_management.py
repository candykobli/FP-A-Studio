import pandas as pd
import pytest
from data_management import safe_join, join_candidates, duplicate_review, deduplicate, convert_currency, reconcile

def test_join_blocks_many_to_many_and_handles_null_keys():
    a=pd.DataFrame({'id':['1','1',None], 'amount':[10,20,30]})
    b=pd.DataFrame({'id':['1','1',None], 'label':['x','y','z']})
    with pytest.raises(ValueError,match='Many-to-many'):safe_join(a,b,'id','id')
    result,audit=safe_join(a,b,'id','id',allow_many_to_many=True)
    assert len(result)==5
    assert audit['Unmatched left rows']==1
    assert len(join_candidates(a,b))==1

def test_duplicate_review_never_modifies_original():
    df=pd.DataFrame({'id':['a','a','b'],'amount':[10,10,20]})
    flagged,groups=duplicate_review(df,['id'])
    cleaned,audit=deduplicate(df,['id'])
    assert len(flagged)==2 and len(cleaned)==2 and len(df)==3
    assert audit['Rows removed']==1

def test_fx_missing_rates_are_visible():
    df=pd.DataFrame({'date':['2026-01-01','2026-02-01'],'currency':['USD','USD'],'actual':[100,200]})
    rates=pd.DataFrame({'date':['2026-01-01'],'currency':['USD'],'target_currency':['EUR'],'rate':[0.9],'rate_type':['monthly_average']})
    result,audit=convert_currency(df,rates)
    assert result.loc[0,'converted_amount']==90
    assert pd.isna(result.loc[1,'converted_amount'])
    assert audit['Missing FX rates']==1

def test_reconciliation_exceptions_and_tolerance():
    a=pd.DataFrame({'cost_center':['A','B'],'amount':[100,200]})
    b=pd.DataFrame({'cost_center':['A','C'],'amount':[100.005,300]})
    result,audit=reconcile(a,b,['cost_center'],'amount','amount',tolerance=.01)
    assert dict(zip(result.cost_center,result.Status))=={'A':'Matched','B':'Missing right','C':'Missing left'}
    assert audit['Exception groups']==2
