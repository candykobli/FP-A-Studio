"""Additive amounts and ratios of sums have different aggregation rules."""
import pandas as pd


def is_ratio(data):
    return 'measure_type' in data and not data.empty and data.measure_type.eq('ratio').all()


def total(s):return float(s.sum()) if len(s)>0 and s.notna().all() else None


def financial_summary(data):
    ratio=is_ratio(data)
    if 'measure_type' in data and data.measure_type.fillna('amount').nunique()>1:
        raise ValueError('Select one measure type before aggregating amounts and percentages.')
    extra={}
    if ratio:
        nums={s:total(data['ratio_'+s+'_numerator']) for s in ('actual','budget')}
        dens={s:total(data['ratio_'+s+'_denominator']) for s in ('actual','budget')}
        result={s:nums[s]/dens[s]*100 if nums[s] is not None and dens[s] not in (None,0) else None for s in ('actual','budget')}
        actual,budget=result['actual'],result['budget']
        extra={**{'numerator_'+s:v for s,v in nums.items()},**{'denominator_'+s:v for s,v in dens.items()}}
    else:
        actual=total(data.actual) if len(data) else 0.0
        budget=total(data.budget)
    variance=actual-budget if actual is not None and budget is not None else None
    return {'actual':actual,'budget':budget,'variance':variance,
        'variance_pct':variance/abs(budget)*100 if not ratio and variance is not None and budget else None,
        'rows':len(data),'unit':'%' if ratio else 'amount','variance_unit':'pp' if ratio else 'amount',**extra}
