# Financial model repair assistant — first version

Open **Data Workspace → Model repair assistant** after loading and selecting a source.

This simple version reviews a single financial table and its column meanings. It uses local, deterministic rules; it is not yet an LLM-powered agent and does not require an API key. Power BI/TMDL repair and master-data management are later stages, not implemented in this release.

## Try the supplied example

1. Upload `sample_data/messy_model.json`, click Load and include it in Sources.
2. Open Model repair assistant and select the example source.
3. Review the proposed meanings for reporting date, actual, budget, entity and currency. Ambiguous names require a choice instead of selecting an arbitrary candidate. Enter Revenue as the business measure.
4. Select Month and Region as the fields identifying a business record. These fields define review keys; repeated keys never trigger automatic deletion.
5. Read the diagnosis. Choose standardized names, text trimming, uppercase currency codes and plain numeric conversion. Choose ISO date (YYYY-MM-DD).
6. Click Check and preview proposed model. Inspect the old/new column mapping, the original/proposed tables, retained row count and totals per currency. In the sample, actual totals EUR 375 and budget coverage is incomplete.
7. Confirm the draft review statement and save the proposed model as a prepared draft.
8. Add the prepared draft to Sources and choose it in Review & approve. Select Quick verify & approve if necessary. The mapping, measure and sign choice carry over. Publication still requires the existing approval checkbox and button. Existing published snapshots remain unchanged until you explicitly publish a replacement.

## What is checked

- Missing or repeated role assignments and ambiguous column-name candidates.
- Inconsistent column names and collisions after normalization.
- Invalid or missing actuals, incomplete budgets, non-finite numbers and mixed signs.
- Numeric date fields, non-ISO text requiring explicit interpretation and invalid ISO calendar dates.
- Malformed currency codes and multiple currencies. Only uppercase three-letter format is checked, not membership in an authoritative currency registry.
- Unclear measure names, unspecified business keys, missing identifiers and repeated business keys.

Selected corrections are applied to a deep copy. The preview blocks invalid conversions; it never guesses separators, currency symbols, numeric spreadsheet dates, joins, deduplication or sign conventions. Explicit date formats include ISO, day-first and month-first. Text trimming is optional because spaces can be meaningful in identifiers.

The report and the financial totals help review a proposed mapping; they do not prove accounting meaning or completeness. No repair can infer whether Actual should mean gross revenue or net revenue from values alone. Users confirm those choices.

Changes to any mapping, measure, sign, key or fix selection invalidate the old preview. Approval is scoped to that preview. The draft inherits original-source lineage, so publication still protects against counting an input and its derived copy together.

Review reports can be downloaded as JSON. Working data and mapping drafts remain session-local. Save reports and exports you need before closing or clearing the workspace.
