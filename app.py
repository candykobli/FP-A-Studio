"""FP&A Studio — multi-source financial analytics with optional AI commentary."""

import hashlib
import os
from datetime import date

import altair as alt
import pandas as pd
import streamlit as st
from engine import (
    calculate,
    combine,
    compare,
    grouped,
    harmonize,
    monthly,
    profile,
    read_upload,
    suggestions,
    summary,
)
from connectors import read_api, read_sql
from dimensions import dimension_choices, display_group
from page_questions import render_page_questions
from calculated_measures import active_calculations
from measure_math import is_ratio
from data_management import (
    join_candidates,
    safe_join,
    duplicate_review,
    deduplicate,
    convert_currency,
    reconcile,
)

st.set_page_config(
    page_title="FP&A Studio | Financial Intelligence",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(
    """<style>
/* FP&A Studio | Executive light theme */
:root { color-scheme: light; }
.stApp { background: #F6F8FB; color: #172B4D; }
.block-container { padding-top: 1.65rem; padding-bottom: 3rem; max-width: 1460px; }
#MainMenu, footer { visibility: hidden; }
h1,h2,h3,h4 { color: #172B4D !important; letter-spacing: -.025em; }
[data-testid="stSidebar"] { background: #FFFFFF; border-right: 1px solid #E1E7EF; }
[data-testid="stSidebar"] h3 { color: #17365D !important; letter-spacing: -.025em; }
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] { color: #718198; }
[data-testid="stSidebar"] div[role="radiogroup"] label { border-radius: 9px; padding: .35rem .5rem; }
[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) { background: #EAF2FD; }
.hero { background: linear-gradient(112deg,#FFFFFF 0%,#F8FBFF 62%,#EDF5FF 100%); border: 1px solid #DEE8F5; border-radius: 20px; padding: 28px 32px; margin-bottom: 25px; box-shadow: 0 7px 28px rgba(27,53,90,.035); }
.hero h1 { font-size: clamp(1.7rem,3vw,2.5rem); letter-spacing: -1.2px; margin: 0; color: #172B4D; font-weight: 750; }
.hero p { color: #64748B; margin: 10px 0 0; font-size: .98rem; }
.eyebrow { color: #2763AC; text-transform: uppercase; letter-spacing: 1.7px; font-size: .72rem; font-weight: 750; margin-bottom: 8px; }
[data-testid="stMetric"] { background: #FFFFFF; border: 1px solid #E1E7EF; padding: 19px 21px; border-radius: 14px; box-shadow: 0 3px 15px rgba(25,50,85,.025); }
[data-testid="stMetricLabel"] { color: #66778D; }
[data-testid="stMetricValue"] { color: #172B4D; letter-spacing: -.025em; }
[data-testid="stVerticalBlockBorderWrapper"] { border-color: #E1E7EF; }
[data-testid="stDataFrame"], [data-testid="stTable"] { border-radius: 12px; overflow: hidden; }
div.stButton>button[kind="primary"],div.stFormSubmitButton>button[kind="primary"] { background: #2763AC; color: white; border: 1px solid #2763AC; border-radius: 9px; }
div.stButton>button[kind="primary"]:hover,div.stFormSubmitButton>button[kind="primary"]:hover { background: #1C508F; color: white; border-color: #1C508F; }
[data-testid="stTabs"] [data-baseweb="tab-list"] { gap: 8px; }
[data-testid="stTabs"] button[aria-selected="true"] { color: #2763AC; }
.small-note { color: #718198; font-size: .85rem; }
</style>""",
    unsafe_allow_html=True,
)

if "sources" not in st.session_state:
    st.session_state.sources = {}
if "facts" not in st.session_state:
    st.session_state.facts = {}
if "messages" not in st.session_state:
    st.session_state.messages = []
if "dm_outputs" not in st.session_state:
    st.session_state.dm_outputs = {}
for key in ("lineage", "published_parents", "mapping_drafts", "calculated_measures"):
    if key not in st.session_state:
        st.session_state[key] = {}
if "approvals" not in st.session_state:
    st.session_state.approvals = []

with st.sidebar:
    st.markdown("### ◈ FP&A Studio")
    st.caption("FINANCIAL INTELLIGENCE WORKSPACE")
    page = st.radio(
        "Workspace",
        [
            "Data Workspace",
            "Overview",
            "Analysis",
            "Income statement",
            "Period comparison",
            "AI analyst",
            "Calculator",
        ],
        label_visibility="collapsed",
    )
    st.divider()
    st.caption(f"{len(st.session_state.facts)} mapped source(s) active")
    if st.button("Clear workspace", use_container_width=True):
        for k in [
            "sources",
            "facts",
            "messages",
            "dm_outputs",
            "lineage",
            "published_parents",
            "mapping_drafts",
            "calculated_measures",
            "page_conversations",
            "approvals",
            "income_statement_reports",
        ]:
            st.session_state[k] = (
                [] if k in ("messages", "approvals", "income_statement_reports") else {}
            )
        for k in list(st.session_state):
            if k.startswith(("repair_", "is_", "calc_")) or k == "calculation_preview":
                st.session_state.pop(k, None)
        for k in ("dm_join_preview", "dm_recon"):
            st.session_state.pop(k, None)
        st.rerun()
    st.caption(
        "Local session • Uploads and credentials are not intentionally written to disk"
    )

st.markdown(
    '<div class="hero"><div class="eyebrow">Unified FP&A workspace</div><h1>Financial clarity, across every source.</h1><p>Connect • Understand • Harmonize • Analyze • Explain</p></div>',
    unsafe_allow_html=True,
)

valid_calculated = active_calculations(
    st.session_state.facts, st.session_state.calculated_measures
)
facts = combine(
    list(st.session_state.facts.values())
    + [entry["data"] for entry in valid_calculated.values()]
)
page_data = None
page_metadata = {}


def fmt(v):
    return "—" if v is None or pd.isna(v) else f"{v:,.0f}"


def reporting_table(data, table):
    return (
        table.rename(
            columns={
                "Actual": "Actual (%)",
                "Budget": "Budget (%)",
                "Variance": "Variance (pp)",
            }
        ).drop(columns=["Variance %"], errors="ignore")
        if is_ratio(data)
        else table
    )


def explain_measure(data):
    if is_ratio(data):
        st.info(
            "Calculated margin: Actual and Budget are percentages recomputed from their total profit and revenue inputs. Variance is in percentage points (pp). Percentages are never summed or averaged; Variance % is not used for margins."
        )
    elif "measure_origin" in data and data.measure_origin.eq("Calculated").all():
        st.caption("Calculated measure · " + str(data.measure_formula.iloc[0]))
    else:
        st.caption(
            "Source-provided measure: the selected amount column supplies these values; its business label does not calculate a formula."
        )


def filtered_data(data, prefix):
    if data.empty:
        return data
    a, b, c = st.columns([1.2, 1, 1])
    with a:
        lo, hi = data["date"].min().date(), data["date"].max().date()
        chosen = st.date_input(
            "Reporting dates",
            (lo, hi),
            min_value=lo,
            max_value=hi,
            key=f"{prefix}_dates",
        )
    with b:
        names = sorted(data["source"].unique().tolist())
        selected = st.multiselect(
            "Sources", names, default=names, key=f"{prefix}_sources"
        )
    with c:
        currencies = sorted(data["currency"].unique().tolist())
        currency = st.multiselect(
            "Currencies", currencies, default=currencies, key=f"{prefix}_currency"
        )
    out = data[data["source"].isin(selected) & data["currency"].isin(currency)]
    if len(chosen) == 2:
        out = out[out["date"].dt.date.between(*chosen)]
    dims = dimension_choices(out)
    with st.expander("Filter confirmed business dimensions"):
        for label, col in dims.items():
            if label == "Source":
                continue
            values = sorted(out[col].dropna().astype(str).unique().tolist())
            selected_values = st.multiselect(
                label, values, default=values, key=prefix + "_dimension_" + col
            )
            missing = True
            if out[col].isna().any():
                missing = st.checkbox(
                    "Include missing " + label, True, key=prefix + "_missing_" + col
                )
            out = out[
                out[col].astype("string").isin(selected_values)
                | (out[col].isna() & missing)
            ]
    return out


if page == "Data Workspace":
    from workspace_ui import render_workspace

    render_workspace()

elif page == "Income statement":
    from income_statement_ui import render_income_statement

    render_income_statement()

elif page == "Calculator":
    st.subheader("Financial calculator")
    st.caption(
        "A safe, standalone calculator for checking percentages, margins and reconciliations."
    )
    examples = [
        "(125000 - 100000) / 100000 * 100",
        "(250000 - 175000) / 250000 * 100",
        "120000 + 85000 - 42000",
    ]
    example = st.selectbox(
        "Example calculations",
        ["Custom expression", "Growth %", "Margin %", "Reconciliation"],
    )
    default = {
        "Custom expression": "",
        "Growth %": examples[0],
        "Margin %": examples[1],
        "Reconciliation": examples[2],
    }[example]
    expression = st.text_input(
        "Expression", value=default, placeholder="(actual - budget) / abs_budget * 100"
    )
    if st.button("Calculate", type="primary"):
        try:
            st.metric("Result", f"{calculate(expression):,.6g}")
        except Exception as exc:
            st.error(f"Invalid expression: {exc}")
    st.info(
        "Supported: +, −, × (*), ÷ (/), %, powers (**) and parentheses. Use numbers rather than variable names. No Python code is executed."
    )

elif facts.empty:
    st.info(
        "Your workspace is ready. Open **Data Workspace** in the sidebar, load a file or connect a source, then confirm its financial mappings."
    )
    st.markdown(
        "**Quick start:** upload `sample_data/sales.csv` → map Month / Net_Sales / Sales_Budget / Region → open Overview."
    )

elif page == "Overview":
    st.subheader("Executive overview")
    data = filtered_data(facts, "overview")
    if data.empty:
        st.warning("No records match the filters.")
        render_page_questions(page, data)
        st.stop()
    overview_measure = st.selectbox(
        "Overview measure", sorted(data["measure"].unique().tolist())
    )
    data = data[data["measure"] == overview_measure]
    overview_currency = st.selectbox(
        "Overview currency", sorted(data["currency"].unique().tolist())
    )
    data = data[data["currency"] == overview_currency]
    explain_measure(data)
    currencies = data["currency"].unique().tolist()
    measures = data["measure"].unique().tolist()
    if len(currencies) > 1:
        st.warning(
            "Multiple currencies selected. Totals are not converted; filter to a single currency before interpreting consolidated values."
        )
    if len(measures) > 1:
        st.warning(
            "Different financial measures are selected. Totals may not be meaningful; use Analysis to filter to one measure."
        )
    s = summary(data)
    cols = st.columns(4)
    labels = (
        ["Actual (%)", "Budget (%)", "Variance (pp)", "Revenue denominator"]
        if is_ratio(data)
        else ["Actual", "Budget", "Variance", "Variance %"]
    )
    values = (
        [
            f"{s['actual']:.2f}" if s["actual"] is not None else "—",
            f"{s['budget']:.2f}" if s["budget"] is not None else "—",
            f"{s['variance']:+.2f}" if s["variance"] is not None else "—",
            fmt(s.get("denominator_actual")),
        ]
        if is_ratio(data)
        else [
            fmt(s["actual"]),
            fmt(s["budget"]),
            fmt(s["variance"]),
            f"{s['variance_pct']:+.1f}%" if s["variance_pct"] is not None else "—",
        ]
    )
    for col, label, value in zip(cols, labels, values):
        col.metric(label, value)
    st.markdown("#### Performance trend")
    trend = (
        monthly(data)
        .melt(
            "Month",
            value_vars=["Actual", "Budget"],
            var_name="Scenario",
            value_name="Value",
        )
        .dropna(subset=["Value"])
    )
    chart = (
        alt.Chart(trend)
        .mark_line(point=True, strokeWidth=3)
        .encode(
            x=alt.X("Month:T", title=None),
            y=alt.Y("Value:Q", title="Margin (%)" if is_ratio(data) else "Amount"),
            color=alt.Color(
                "Scenario:N",
                scale=alt.Scale(
                    domain=["Actual", "Budget"], range=["#2763AC", "#B3BFCE"]
                ),
            ),
            tooltip=["Month:T", "Scenario:N", alt.Tooltip("Value:Q", format=",.2f")],
        )
        .properties(height=340)
    )
    st.altair_chart(chart, use_container_width=True)
    dims = dimension_choices(data)
    labels = list(dims)
    c1, c2 = st.columns(2)
    with c1:
        left = st.selectbox("Break down by — left table", labels, key="overview_left")
        st.dataframe(
            reporting_table(data, display_group(data, dims[left], left)),
            hide_index=True,
            use_container_width=True,
        )
    with c2:
        right = st.selectbox(
            "Break down by — right table",
            labels,
            index=labels.index("Source") if "Source" in labels else 0,
            key="overview_right",
        )
        st.dataframe(
            reporting_table(data, display_group(data, dims[right], right)),
            hide_index=True,
            use_container_width=True,
        )
    page_data = data
    page_metadata = {"dimension": left, "right_dimension": right}
    st.caption(
        "Variance = Actual − Budget. For margins, the difference is percentage points (pp). Favorability depends on the financial meaning of the measure."
    )

elif page == "Analysis":
    st.subheader("Explore & reconcile")
    data = filtered_data(facts, "analysis")
    if data.empty:
        st.warning("No matching data")
        render_page_questions(page, data)
        st.stop()
    measures = sorted(data["measure"].unique().tolist())
    chosen = st.selectbox("Measure to analyze", measures)
    if len(measures) == 1:
        st.info(
            "Only one measure is published in this scope. To add more, use Data Workspace → Review & approve and choose how measures are stored, then approve the updated dataset."
        )
    data = data[data["measure"] == chosen]
    currency = st.selectbox(
        "Currency to analyze", sorted(data["currency"].unique().tolist())
    )
    data = data[data["currency"] == currency]
    explain_measure(data)
    dims = dimension_choices(data)
    dim = st.selectbox("Break down by", list(dims))
    table = display_group(data, dims[dim], dim).sort_values("Actual", ascending=False)
    page_data = data
    page_metadata = {"dimension": dim}
    st.dataframe(
        reporting_table(data, table), hide_index=True, use_container_width=True
    )
    bars = (
        alt.Chart(table.rename(columns={dim: "Dimension"}))
        .mark_bar(cornerRadiusEnd=5)
        .encode(
            x=alt.X("Actual:Q"),
            y=alt.Y("Dimension:N", sort="-x", title=dim),
            color=alt.value("#2763AC"),
            tooltip=["Dimension:N", alt.Tooltip("Actual:Q", format=",.2f")],
        )
        .properties(height=max(250, len(table) * 34))
    )
    st.altair_chart(bars, use_container_width=True)
    with st.expander("View harmonized records and download CSV"):
        st.dataframe(data, use_container_width=True, hide_index=True)
        st.download_button(
            "Download filtered records",
            data.to_csv(index=False).encode(),
            file_name="fpa_records.csv",
            mime="text/csv",
        )

elif page == "Period comparison":
    st.subheader("Compare two reporting periods")
    measures = sorted(facts["measure"].unique().tolist())
    measure = st.selectbox("Financial measure", measures)
    data = facts[facts["measure"] == measure]
    currencies = sorted(data["currency"].unique().tolist())
    ccy = st.selectbox("Currency", currencies)
    data = data[data["currency"] == ccy]
    explain_measure(data)
    sources = st.multiselect(
        "Sources",
        sorted(data["source"].unique()),
        default=sorted(data["source"].unique()),
    )
    data = data[data["source"].isin(sources)]
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**First period**")
        a1 = st.date_input("From", date(2025, 1, 1), key="a1")
        a2 = st.date_input("To", date(2025, 3, 31), key="a2")
    with c2:
        st.markdown("**Second period**")
        b1 = st.date_input("From", date(2026, 1, 1), key="b1")
        b2 = st.date_input("To", date(2026, 3, 31), key="b2")
    dims = dimension_choices(data)
    dim = st.selectbox("Contribution dimension", list(dims))
    if a1 > a2 or b1 > b2:
        st.error("Period start must not be after period end.")
        st.stop()
    table, first, second = compare(data, a1, a2, b1, b2, dims[dim])
    table = table.rename(columns={dims[dim]: dim})
    page_data = data[
        data.date.dt.date.between(a1, a2) | data.date.dt.date.between(b1, b2)
    ]
    page_metadata = {
        "dimension": dim,
        "comparison": table.to_dict(orient="records"),
        "first": first["actual"],
        "second": second["actual"],
        "first_rows": first["rows"],
        "second_rows": second["rows"],
        "unit": "pp" if is_ratio(data) else ccy,
        "periods": (str(a1), str(a2), str(b1), str(b2)),
    }
    if first["rows"] == 0 or second["rows"] == 0:
        st.warning("One or both periods have no data. Verify your dates and filters.")
    d = (
        second["actual"] - first["actual"]
        if first["actual"] is not None and second["actual"] is not None
        else None
    )
    c1, c2, c3 = st.columns(3)
    first_value = (
        f"{first['actual']:.2f}%"
        if is_ratio(data) and first["actual"] is not None
        else fmt(first["actual"])
    )
    second_value = (
        f"{second['actual']:.2f}%"
        if is_ratio(data) and second["actual"] is not None
        else fmt(second["actual"])
    )
    change_value = f"{d:+.2f}" if is_ratio(data) and d is not None else fmt(d)
    c1.metric("First period", first_value)
    c2.metric("Second period", second_value)
    c3.metric(
        "Change (pp)" if is_ratio(data) else "Net change",
        change_value,
        delta=(
            f'{d/abs(first["actual"])*100:+.1f}%'
            if d is not None and first["actual"] and not is_ratio(data)
            else None
        ),
    )
    st.markdown("#### Contribution bridge")
    st.dataframe(
        (
            table.rename(columns={"Change": "Change (pp)"}).drop(
                columns=["Contribution %"]
            )
            if is_ratio(data)
            else table
        ),
        hide_index=True,
        use_container_width=True,
    )
    chart = (
        alt.Chart(table.rename(columns={dim: "Dimension"}))
        .mark_bar()
        .encode(
            x=alt.X("Change:Q"),
            y=alt.Y("Dimension:N", sort="-x", title=dim),
            color=alt.condition(
                alt.datum.Change >= 0, alt.value("#16846C"), alt.value("#C84B54")
            ),
            tooltip=[
                "Dimension:N",
                alt.Tooltip("Change:Q", format=",.2f"),
                alt.Tooltip("Contribution %:Q", format=".1f"),
            ],
        )
        .properties(height=max(250, len(table) * 35))
    )
    st.altair_chart(chart, use_container_width=True)
    if not table.empty and not is_ratio(data):
        top = table.iloc[0]
        bottom = table.iloc[-1]
        st.info(
            f"Largest positive change: **{top[dim]}** ({top['Change']:+,.0f}). Lowest change: **{bottom[dim]}** ({bottom['Change']:+,.0f}). Contribution percentages use net change as denominator; they may exceed 100% or be negative."
        )
    if d is not None and abs(d) < 1e-12:
        st.caption("Net change is zero, so contribution percentages are undefined.")
    if is_ratio(data):
        st.caption(
            "Period changes are percentage points. Group margins are not additive, so contribution percentages are not calculated."
        )
    st.caption(
        "Coverage is based on available records only. Missing months, currencies, or business units may affect comparisons."
    )

elif page == "AI analyst":
    st.subheader("Dedicated financial analyst")
    data = filtered_data(facts, "analyst")
    if data.empty:
        st.warning("No matching records.")
        render_page_questions(page, data, dedicated=True)
        st.stop()
    measure = st.selectbox(
        "Measure for conversation", sorted(data.measure.unique().tolist())
    )
    data = data[data.measure == measure]
    currency = st.selectbox(
        "Currency for conversation", sorted(data.currency.unique().tolist())
    )
    data = data[data.currency == currency]
    explain_measure(data)
    dims = dimension_choices(data)
    dimension = st.selectbox("Default breakdown for questions", list(dims))
    page_data = data
    page_metadata = {"dimension": dimension}

if page not in ("Data Workspace", "Income statement"):
    if page == "Calculator":
        page_metadata = {"expression": expression}
    if not facts.empty:
        page_metadata["available_measures"] = sorted(facts.measure.unique().tolist())
    render_page_questions(
        page, page_data, page_metadata, dedicated=page == "AI analyst"
    )
