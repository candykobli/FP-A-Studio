"""Business definitions, separate from source columns and calculation recipes."""
CATALOG={
    'Revenue':'Revenue recorded in the mapped source amounts; confirm gross/net scope and sign convention.',
    'Cost':'Source-provided costs. Specify the scope in your source/model; this does not mean cost of sales automatically.',
    'Cost of sales':'Costs attributable to the goods/services sold, using your approved accounting classification.',
    'Expenses':'Source-provided expenses. This label alone does not establish a complete income statement.',
    'Operating expenses':'Source-provided operating expenses; confirm which expenses are included.',
    'Other operating income':'Operating income outside the chosen Revenue definition.',
    'Other operating expenses':'Operating expenses outside the chosen Operating expenses definition.',
    'Finance income':'Source-provided finance income.',
    'Finance expenses':'Source-provided finance expenses.',
    'Income tax':'Source-provided income tax expense for the reporting period.',
    'Gross profit':'Revenue minus cost of sales. Mapping a column labels its existing values; it does not calculate this formula.',
    'Operating profit':'Gross profit plus other operating income minus operating expenses and other operating expenses.',
    'Net profit':'Operating profit plus finance income minus finance expenses and income tax.',
    'Headcount':'A source-provided count. Period-end headcount must not be summed over time as though it were period activity.',
    'Units sold':'A source-provided activity count, using a consistent unit.',
    'Gross profit margin (%)':'Gross profit divided by Revenue × 100. Calculate from compatible totals; never sum or average row percentages.',
    'Operating profit margin (%)':'Operating profit divided by Revenue × 100.',
    'Net profit margin (%)':'Net profit divided by Revenue × 100.'}
RATIO_NAMES={'gross profit margin','operating profit margin','net profit margin','profit margin','margin','gross margin','operating margin','net margin','gross profit margin (%)','operating profit margin (%)','net profit margin (%)'}


def is_ratio_name(name):return str(name).strip().casefold() in RATIO_NAMES or '%' in str(name)


def validate_source_measure(name):
    if str(name).strip().casefold()=='profit':
        raise ValueError('Profit is ambiguous. Choose Gross profit, Operating profit, Net profit, or define a precise custom amount measure.')
    if is_ratio_name(name):
        raise ValueError('Percentage or ambiguous margin labels need underlying totals. Use Calculated measures for a percentage, or a precise profit label for a source-provided amount. Source percentages are not summed or averaged.')


def source_measure_input(key,default='Amount',custom_label='Business measure'):
    import streamlit as st
    choice=st.selectbox('Business measure choice',list(CATALOG)+['Custom measure'],index=len(CATALOG),key=key+'_choice')
    if choice=='Custom measure':name=st.text_input(custom_label,value=default,key=key)
    else:name=choice
    st.caption(CATALOG.get(name,'Custom source-provided amount. Enter a precise definition; naming a measure does not calculate it.'))
    st.caption('Source-provided: the mapped column supplies the values. For formulas, use the Calculated measures tab after publishing the inputs.')
    return name
