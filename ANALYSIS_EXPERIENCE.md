# Configurable analysis and contextual questions

This release implements the analysis foundation discussed before financial statements: confirmed dimensions, two independent Overview breakdowns and a question box on each page. It retains Data Workspace, multi-measure mapping, model repair, period comparison, the dedicated AI Analyst, calculator and the light theme.

## Try it

1. Start the application with `python -m streamlit run app.py` from the extracted FPA_Studio folder after installing requirements.
2. Upload `sample_data/financial_dimensions.csv` under Data Workspace and click Load.
3. In Review & approve, choose Quick verify & approve. Confirm Date, Actual, Budget, Country, Category and Currency. Enter Revenue as the measure.
4. The mapped entity is shown using a business label. For this source it defaults to Country. You can change it for other source meanings (Department, Business unit, etc.). This is a user-confirmed display label, not an automatic geographic inference. Older snapshots without label metadata display their legacy entity field as Country for compatibility with the current demo.
5. Select Region, Product and Department under Additional dimensions. Confirm or edit their display labels. Extra source columns are not all silently published: amount fields and identifiers may have inappropriate meanings as breakdowns.
6. Review the proposed facts and per-measure/per-currency totals, then explicitly approve publication.
7. In Overview, use either Break down by dropdown. Both have the same available confirmed dimensions; each operates independently. Defaults are the first retained dimension (Country in the example) and Source. Category is available only when mapped, and synthetic All/measure defaults are not shown as extra dimensions.
8. Expand Filter confirmed business dimensions to narrow the selected records. Missing dimension values can be included or excluded explicitly. Overview and Analysis still use one measure and one currency at a time.
9. Ask a question in Ask about this page, or open the dedicated AI Analyst for its separate conversation and scope controls.

## Example questions

- How do you calculate variance?
- Show my variance.
- Explain variance by Product in France.
- Which Country has the largest actual total?
- Show the monthly trend.
- Explain variance in the right table.
- Why were rows flagged? (Data Workspace)
- Explain the change. (Period comparison)
- Explain the result. (Calculator, after entering an expression)

The answer engine explains Actual − Budget and (Actual − Budget) / |Budget| × 100, using the selected records where possible. Zero budgets have an undefined percentage, missing budgets stay unknown, and mixed measures/currencies are not added. Attribution tables identify numerical contributions, not proven business causes. Period comparison uses its displayed bridge and distinguishes period change from actual-versus-budget variance.

The local question assistant supports these financial intents and conservative scope checks. It is not an unrestricted language-model agent. It refuses recognized out-of-scope currencies, years, measures, unavailable dimensions and unmatched qualifiers rather than inventing a result. Supported exact dimension values can narrow the current scope; complex requests should use the visible page filters. It cannot interpret every natural-language filter or infer business causes. No chat action edits, joins, deduplicates or approves data.

Conversations are separate by page and by data/filter/breakdown scope. Changing a selection hides the previous scoped conversation; returning to the exact scope restores it. All conversations and data remain session-local and clear with Clear workspace.

Optional OpenAI commentary remains on AI Analyst only, off by default, with the existing environment-key configuration. If enabled, the question, calculated answer, scope and aggregate summary are sent; raw records are not sent. External AI calls were not tested. All page chats work locally without an API key.

## Data preservation and limits

Retained dimensions are stored alongside approved facts, including in multi-measure reshaping; original tables are not modified. Missing values remain missing and appear as a separate group, not invented classifications. If a dimension is absent from one of several selected sources, those records have missing values for that dimension. Matching labels across sources is a user modeling decision, not entity resolution.

To expose extra dimensions in an older dataset, map and approve it again. Approved snapshots are not retroactively changed. Model repair currently focuses on a single actual/budget mapping; configure the retained dimensions in Review & approve after saving its draft.

The Income statement page now provides the first management-reporting stage; see INCOME_STATEMENT.md. Balance sheets, calculated cash flow, forecasting, Power BI repair and master-data management remain later stages.
