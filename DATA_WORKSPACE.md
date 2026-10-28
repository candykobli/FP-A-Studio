# Unified Data Workspace

This update is based on the supplied FPA_Studio_Light_Theme.zip. Data Sources and Data Management now share one Data Workspace. The light theme, dashboard, Analysis, Period comparison, AI analyst, calculator and connectors are retained.

## Run

Extract the ZIP, open a terminal inside FPA_Studio, then run:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

## Workflow

1. Add files or connect a read-only SQL source / trusted HTTPS JSON API. Each load creates a separate original table.
2. Select any number of Sources. Automatic screening shows blanks, leading/trailing whitespace, repeated whole rows, column types and mixed numeric/text values. These are screening checks, not proof of financial correctness.
3. In Review & approve, clean tables default to Quick verify & approve; tables with findings default to Review / correct. Both choices remain available: optional blanks and repeated transactions may be legitimate.
4. Corrections trim selected columns or let you edit cells and delete specific rows. Save a prepared copy, then select that copy for verification. These operations never edit the loaded originals.
5. Map date, actual, optional budget, entity/category and currency. Enter a measure name and confirm signs. Currency codes require uppercase three-letter format; there is no currency registry validation. Invalid required dates or amounts block publication instead of silently dropping rows. Review row counts, reporting dates, budget coverage and totals per currency.
6. Check the approval statement and click Approve & publish to analysis. Only approved snapshots feed analysis. Selecting sources or saving a prepared copy never publishes them.

Try sample_data/sales.csv: Month → date, Net_Sales → actual, Sales_Budget → budget, Region → entity, Currency → currency; measure Revenue. Open Overview after approval. Calculator also works before data is published.

## Multiple sources

Choose all relevant inputs in Sources. Map and approve compatible, non-overlapping financial tables separately. Analysis appends approved facts; it never guesses joins or removes duplicates.

Model selected sources includes:

- Connect related tables: explicitly choose two inputs, keys and join type; review cardinality and unmatched rows before saving. Many-to-many joins are blocked. One-to-many joins may still multiply amounts; check business grain and financial totals. Select a saved prepared output alongside the next source to model three or more sources in stages.
- Review repeated records: choose business keys, review groups and confirm the retention rule before creating a deduplicated copy. Repeated business keys may be legitimate. For individual corrections use Review / correct.
- Convert currency: supply approved rates with date,currency,target_currency,rate,rate_type. Rate means target units per source unit. Daily and closing policies require exact dates; monthly_average uses months. Missing rates remain blank. When approving, map converted_amount and reporting_currency. Mapping a native budget with converted actuals is blocked; prepare both scenarios in the same currency first.
- Check figures against another source: choose equivalent measures and business dimensions, including period/currency where applicable, and a tolerance. Review missing groups and differences and export the report. Net totals may hide offsetting exceptions.

Prepared outputs retain input lineage. Publishing a derivative alongside its published inputs is blocked unless you explicitly replace them. Independently uploaded tables may still overlap; verify business coverage yourself.

## Published data

Withdraw snapshots under Published data. Download session approval history with dataset fingerprint, mapping, signs, row count and UTC approval time. Editing working copies does not alter previously approved snapshots.

Variance is Actual − Budget; favorability depends on measure meaning. Missing or partial budgets are unknown, not zero. Do not combine unrelated measures or currencies. Overview warns when multiple measures/currencies are selected; use Analysis filters for a comparable scope.

This is a local session-based prototype. Tables and approval history are lost on session end or Clear workspace; download required results. Originals means loaded tables, not an archival copy of the uploaded file bytes. There is no durable audit database, accounting certification or authentication.

SQL drivers require separate installation. Use read-only database credentials and trusted endpoints. APIs fetch one response; pagination and OAuth require connector-specific work. Optional AI uses OPENAI_API_KEY and OPENAI_MODEL and sends aggregated context only when enabled.

## Validation

Run `python -m pytest tests -q`. Tests cover calculations, joins, duplicates, missing FX, reconciliation, profiling, invalid values, immutable publication snapshots, lineage conflicts, and Streamlit navigation/approval. Live SQL, external APIs and paid AI calls are not exercised by these tests.
