import pandas as pd
import pytest
from engine import calculate,harmonize,compare
from datetime import date

def test_calculator():
    assert calculate('(120-100)/100*100') == 20
    with pytest.raises(ValueError): calculate('__import__("os")')

def test_harmonization_and_comparison():
    source=pd.DataFrame({'Period':['2025-01-01','2026-01-01'],'Sales':[100,150],'Region':['FR','FR']})
    facts=harmonize(source,{'date':'Period','actual':'Sales','entity':'Region'},'test')
    table,a,b=compare(facts,date(2025,1,1),date(2025,3,31),date(2026,1,1),date(2026,3,31))
    assert table.iloc[0]['Change']==50
    assert table.iloc[0]['Contribution %']==100
