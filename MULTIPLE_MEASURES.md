# Multiple measures in one source

Previously, each approved dataset received one fixed measure label. Analysis therefore showed only that label, even when the file contained other amount columns. Existing published snapshots retain their original mapping; re-map and explicitly re-publish to expose more measures.

## Measures in separate amount columns

1. Upload `sample_data/multiple_measures.csv` and click Load.
2. Under Review & approve, select Quick verify & approve.
3. Choose Each measure has its own amount columns.
4. Confirm the shared date, entity and currency columns. Category is optional.
5. Define Revenue using actual `revenue` and budget `revenue_budget`.
6. Define Expenses using actual `expenses` and budget `expenses_budget`.
7. Review separate totals per measure and currency and explicitly approve publication. You can define 2–20 measures, each with its own sign choice and optional budget.
8. Open Analysis and choose Revenue or Expenses in Measure to analyze. Overview, Period comparison and AI analyst also let you select a measure.

For the supplied example: Revenue actual EUR 450,000, budget EUR 447,000; Expenses actual EUR 299,000, budget EUR 296,000.

The output has one financial fact per input row and measure. Four input rows with two measures create eight financial records. Original row IDs and source labels are retained. This is explicit reshaping, not a join or deduplication. Amount columns cannot be reused across measures/scenarios, and measure names must be distinct. Invalid amounts in any measure block publication of the whole proposal. Unmapped columns are not automatically included.

## Measure names in a column

If each row already has fields such as date, measure, actual, budget and currency, choose Measure names are in a column. Map the measure-name column explicitly. Every row must have a non-blank measure name. A measure column can also serve as category when appropriate. Actual and budget still come from their mapped columns.

## One measure

The default One measure for this source route is unchanged. It is suitable for a table holding only Revenue or only Expenses.

Analysis and Overview now select one measure and one currency for displayed totals to avoid adding unlike measures or currencies. No financial statement formula is implied: revenue, expense, headcount, totals and their components must not be treated as interchangeable transactions. Only publish measures whose definitions, units and source coverage you have verified.

The simple Model repair assistant still reviews a single actual/budget mapping at a time. Use Review & approve for multi-measure configuration; the repair assistant does not infer multiple measure definitions.
