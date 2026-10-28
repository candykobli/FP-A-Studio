# Guided source measures and reviewed calculated measures

This release builds on the income-statement project. Keep your installed folder or downloaded ZIP as a backup, and extract this new ZIP into a separate folder. The original data workspace, income statement, analysis, model repair, contextual questions, AI Analyst, calculator and light theme are retained.

## Two different workflows

**Source-provided measure:** In Review & approve or Model repair, Business measure choice offers Revenue, Cost, Cost of sales, Operating expenses, Gross profit, Operating profit, Net profit and other definitions, plus Custom measure. Select the business meaning, then map the actual/budget columns. These names label existing values; choosing Gross profit does not subtract costs. The interface and analytical views identify these values as Source-provided. Confirm the source's business scope and sign convention. A generic Cost amount is not automatically cost of sales, and Profit alone is rejected as ambiguous.

**Calculated measure:** After approving the source inputs, open Data Workspace → Calculated measures. Choose a formula, explicitly map its required input measures, choose matching business keys, preview the aligned inputs and results, then approve the definition. No source column, original table or existing published measure is overwritten.

| Formula | Required input definitions |
|---|---|
| Gross profit | Revenue − Cost of sales |
| Operating profit | Gross profit + Other operating income − Operating expenses − Other operating expenses |
| Net profit | Operating profit + Finance income − Finance expenses − Income tax |
| Gross profit margin (%) | Gross profit ÷ Revenue × 100 |
| Operating profit margin (%) | Operating profit ÷ Revenue × 100 |
| Net profit margin (%) | Net profit ÷ Revenue × 100 |

Missing components are not guessed as zero. If a required component genuinely has no activity, supply an explicitly defined zero-valued input at the appropriate dates/currencies/business keys. An incomplete subset of expenses must not be presented as net profit. Formula-role selections still require finance judgment: names alone cannot prove accounting meaning.

Percentage and ambiguous margin labels are not accepted as additive source measures. In this version, calculate a margin from its profit and revenue totals. For a monetary gross-margin amount, use the unambiguous Gross profit label. Custom measures remain source-provided amounts unless covered by one of the reviewed calculation recipes. Count measures cannot be used in the monetary profit/margin formulas. Period-end measures such as headcount need their own aggregation policy; a source label alone does not establish that policy.

## Try the supplied example

1. Upload `sample_data/calculated_profit_demo.csv`, click Load, and choose Quick verify & approve.
2. Choose Each measure has its own amount columns, with two measures. Confirm Date, Currency and Country as the shared mapping; leave Category unmapped.
3. For measure 1, choose Revenue; map Revenue as actual and Revenue_Budget as budget. For measure 2, choose Cost of sales; map Cost_of_sales as actual and Cost_of_sales_Budget as budget. Keep the example's positive signs.
4. Review and approve the source. It now supplies Revenue and Cost of sales in the same approved dataset.
5. In Calculated measures, select that dataset and Gross profit. Confirm Revenue and Cost of sales as the formula inputs and Country as a business key. Preview, review the inputs/formula, tick the calculation approval and approve.
6. Choose Gross profit margin (%). Gross profit and Revenue should now be available as inputs. Preview and approve this definition separately.
7. In Overview or Analysis, select Gross profit or Gross profit margin (%). Calculated results use the source dataset's source label, so existing source filters still apply.

Expected totals: Revenue EUR 1,000; Cost of sales EUR 860; Gross profit EUR 140. Actual gross profit margin is **14%**. Budget gross profit is EUR 220; budget margin **22%**; margin variance **−8 percentage points**. France's individual margin is 50% and Germany's is 10%; their simple average of 30% would be wrong for the overall dataset.

Ask “How do you calculate Gross profit?” or “How do you calculate Gross profit margin (%)?” in the scoped page chat to see the formula and numbers behind the result.

## Alignment and aggregation rules

- Each calculation uses one approved dataset, plus its active calculated measures. Independent source tables are not automatically joined. Prepare a compatible approved multi-measure model before creating cross-source formulas.
- Exact reporting date and currency are always matching keys. Additional keys are confirmed retained business dimensions, such as Country or Product. Inputs are aggregated independently at the chosen grain, then aligned one-to-one. This avoids transaction-level many-to-many joins.
- Unmatched dates/currencies/business groups block the preview. Missing groups are never filled with zero. Missing business keys block alignment until corrected or deliberately omitted from a coarser aggregation.
- Omitting a dimension aggregates it away; calculated results cannot then be broken down by that omitted field. A category column that is merely the measure name is not treated as a matching business key.
- Formula inputs must be distinct monetary amount measures. A percentage cannot be used as a cost or revenue input. Inputs are not multiplied by guessed signs or converted into another currency.
- Source-provided target measures are not duplicated by a calculated definition in the same model. Replacing an existing approved calculated definition requires explicit confirmation; self-reference and dependency cycles are blocked.

Profit amounts are additive at their retained grain. Margin records retain their underlying numerator and denominator. All Overview totals, breakdown tables, monthly trends, comparison periods and question answers recompute **sum(profit) ÷ sum(revenue) × 100** for the current selection. Ratios are never summed or averaged. A zero aggregate denominator is undefined, shown as unknown/— rather than zero. A zero individual group's denominator does not prevent a valid aggregate ratio when the aggregate revenue is nonzero. Negative revenue denominators are not made absolute; review the source signs and business interpretation.

Missing budget components remain unknown, so a partial budget is not treated as a complete target. Actual/budget margins are percentages and their variance is percentage points (pp), not currency and not an actual/budget relative-variance percentage. Group margin changes are not additive, so period comparison does not produce contribution percentages for margins.

## Approval, dependency changes and exports

Preview is not publication. Each calculated definition needs a separate approval tied to its source fingerprint, formula inputs and grain. The definition stores a copy of the calculated values, evidence, inputs, formula, dependencies and UTC approval time. Replacing the base source or a referenced calculated definition makes dependent calculations stale. Stale values remain in the local definition registry for review but are excluded from current analysis until explicitly rebuilt and approved. No automatic recalculation silently replaces an approved definition.

Source originals and existing income-statement snapshots are unchanged. Model repair remains a source-mapping review; use Calculated measures for profit formulas and margin aggregation.

Download aligned input evidence while reviewing, and download approved definitions and calculated values from the definition list. Session data and approvals are not a durable audit database; export what you need before closing or clearing the workspace. An approved definition should still be checked against your actual business/accounting rules and source completeness.

The feature uses deterministic calculation rules, not AI-generated financial formulas. Optional external AI commentary remains off by default on the dedicated AI Analyst. Live external services were not tested.
