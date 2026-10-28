# Management income statement — first version

This release adds the first financial-reporting stage: one shared management P&L structure, explicit account classification, multiple business-unit inputs, per-source reconciliation and approved report snapshots. It retains the existing data workspace, model repair, multi-measure analysis, page questions and light theme.

It is a **combined management view before intercompany eliminations**, not a statutory consolidated financial statement. It performs no automatic currency translation, entity allocation, intercompany matching/elimination, consolidation ownership calculation or accounting certification. Account classifications, sign conventions and source completeness require finance review.

## Run

Extract the whole ZIP into a new folder, open a terminal inside FPA_Studio, install requirements and start:

```powershell
py -m pip install -r requirements.txt
py -m streamlit run app.py
```

## Try the two-unit demonstration

1. Open Income statement in the sidebar. It works before any analytical facts have been published.
2. Click Load two-business-unit demonstration, then select Original · Demo France and Original · Demo Germany under Account-level activity sources.
3. Review the source mappings: Date, Account, Actual, Budget and Currency. The demo supplies France SAS and Germany GmbH as explicit reporting entities. Business-unit labels can be changed. Country alone is not a legal-entity identifier.
4. Map the account identifiers below. The app does not classify them automatically.

| France account | Germany account | Reporting line | Reverse source sign? |
|---|---|---|---|
| 4000 | 7000 | Revenue | France: yes; Germany: no |
| 5000 | 8000 | Cost of sales | No |
| 6000 | 9000 | Operating expenses | No |
| 1000 | 2000 | Exclude from income statement | No |

For the excluded demonstration accounts, enter the reason: Balance-sheet activity, outside P&L. These rows remain in the reconciliation and row bridge; they are not deleted.

5. For these fictional sample files only, confirm the absent reporting lines have no activity. Other operating income/expenses, finance income/expenses and income tax are therefore zero. Do not use this checkbox to hide a missing source or missing period in real data.
6. Preview the income statement and reconciliation. Actual revenue is EUR 462,000, cost of sales EUR 270,000, operating expenses EUR 114,000 and net profit EUR 78,000. Budget net profit is EUR 76,000; variance is EUR 2,000 (approximately 2.63%). France contributes EUR 45,000 actual net profit and Germany EUR 33,000.
7. Filter the preview by currency, month, reporting entity or business unit. Drill into a reporting line, then inspect its original account/row records and the source-signed reconciliation.
8. Review the complete source coverage, classifications, exclusions, signs and reconciliation. Tick the approval statement and save an income statement snapshot. Approval covers the entire preview model, including all its periods and currencies, not only the filtered display.
9. Choose Approved reports to view the saved snapshot. Download its report pack, including statement CSV, reconciliation CSV, source-row bridge and a JSON approval/mapping manifest. No raw source or approved analytical fact is overwritten.

## Supported source shape

Each source represents one reporting/legal entity. It may contain multiple business units through an explicitly mapped column, or use one entered unit label. Required columns are reporting date, account identifier, actual activity and currency; a budget-activity column is optional. This version supports up to 100 account identifiers per source in the mapping screen.

Use monthly activity or transaction activity. Year-to-date balances, cumulative snapshots and closing balances need an explicit conversion before this page can use them; they are blocked when declared. Dates use a selected ISO, day-first or month-first format. Numeric date serials are blocked. Currency values must be uppercase three-letter codes; format is checked, not currency-registry membership. Verify account identifiers during loading, especially text identifiers with leading zeroes, since file parsers may infer numeric types.

Original rows are retained one-for-one. An account must be mapped to Revenue, Cost of sales, Other operating income, Operating expenses, Other operating expenses, Finance income, Finance expenses, Income tax, or an explicitly reasoned exclusion. Unmapped accounts block approval. Invalid dates, blank actuals and non-finite numeric values block the proposal rather than losing rows. Optional missing budgets remain unknown.

Use a sign multiplier of +1 or -1 per account. The reporting formulas expect expense lines to be subtracted; they do not apply absolute values. Genuine credits, refunds and reversals can remain negative. Review the negative-activity notice to distinguish them from an incorrect sign convention. Both actual and budget use the selected multiplier, so prepare data separately if their source conventions differ.

## Formulas and checks

- Gross profit = Revenue − Cost of sales.
- Operating profit = Gross profit + Other operating income − Operating expenses − Other operating expenses.
- Profit before tax = Operating profit + Finance income − Finance expenses.
- Net profit = Profit before tax − Income tax.
- Variance = Actual − Budget. Variance % = Variance / |Budget| × 100, undefined when budget is zero. A positive expense variance is not automatically favorable.

Absent reporting lines default to Not provided, with unknown subtotals. They become zero only after explicit no-activity confirmation. Checks examine period/currency groups so a line in one month cannot silently fill a missing line in another. Missing budget cells in existing rows are not filled by that confirmation. Missing entire business units or months cannot be detected without an external submission calendar; verify source coverage yourself.

The reconciliation separates included, excluded and unmapped original-signed amounts and row counts for each source, month and currency. It also retains each row’s sign multiplier and effect on net profit. Approved net profit must agree with that included profit-impact bridge. A zero reconciliation difference confirms coverage of the loaded rows and arithmetic; it does not prove that an account was classified correctly or that the loaded source is complete. Offsetting source amounts can net to zero, so review row counts and drill-downs as well as net totals.

Source currencies are reported separately. Selecting a currency filters amounts; it does not convert them. Original/derived inputs sharing known lineage are blocked from the same report; independently loaded files may still overlap, and finance must check their business coverage. Imported duplicates are never automatically removed.

## Questions and report lifecycle

Ask how net profit or gross profit is calculated, how a line’s variance is calculated, or how the report reconciles to its sources. The local answer engine uses the current preview or approved report selection and labels that scope. Use visible filters to change entities/units/months/currencies. Chat never changes classifications or approves reports. It does not model EBITDA, cash flow, balance-sheet balances or inferred business causes.

Mapping or source changes invalidate the working preview and require a new review. Saved snapshots hold copies of the detail, configuration, totals, reconciliation, source fingerprints and UTC approval time; later working changes do not alter them. Reports are stored in the Streamlit session, not a durable audit database. Download packs you need before closing or clearing the workspace. Clear workspace also clears report snapshots and question history.

Balance sheets, linked cash-flow schedules, forecasting and planning remain later stages. This implementation is a reviewable management-reporting foundation, not a production accounting or consolidation system.
