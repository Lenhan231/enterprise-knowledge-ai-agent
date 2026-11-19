# Sales report data needs

Verified on 18 November 2026 for `sales performance from 2025 to 2026`. The application now calculates these diagnostics per report, using authorized SQL coverage results rather than assuming that unavailable comparisons mean the whole database is missing.

| Source | Missing records | What to supply |
| --- | --- | --- |
| `commerce.sales` | 1–13 November 2025 | Genuine daily `date`, `revenue`, `cogs` values. The gap blocks November and December 2025 comparisons. |
| `commerce.sales` | 14–17 November 2026 | Genuine daily `date`, `revenue`, `cogs` values. November remains incomplete. |
| Current/future reporting days | 18 November–31 December 2026 | Collect actual records after each day closes. These are pending observations, not historical data to fabricate or backfill. |

The existing SQL Agent and four fixed decision rules already provide full results for 20 of the requested 24 months and partial results for three more. No additional decision policy is required to run S01–S04. Do not fill missing days with zero unless the source supplies an actual zero observation. Daily counts check completeness; comparisons use calendar-month totals.

For explanations, ingest existing business evidence through the current document upload, chunking and indexing flow. Useful evidence includes dated pricing approvals/change logs, COGS or supplier cost changes, actual campaign execution/outcome reports, and approved sales reviews. Identify the effective dates, company/source, and applicable scope; assign the existing document access roles. Keep company sales distinct from delivered order-line revenue. General policies provide context and do not prove why a reported movement occurred.

Retrieval failure or access denial does not establish that documents are absent. The report distinguishes these states from an empty retrieval result. The live finance-role search initially returned schema/metric-contract passages; these are excluded from business explanations. They define metrics and cannot establish why revenue or profit changed. Only qualitative source excerpts are retained in reports; SQL supplies all report metric values. Source excerpts are reauthorized against the current document ACL and active/ready state before returning a saved report, edit response or PDF. Removed/restricted sources are withheld while SQL facts remain available.

Previously saved reports gain the derived decision summary when reopened. Regenerate a report to collect document context and exact missing-date diagnostics; older snapshots are preserved.
