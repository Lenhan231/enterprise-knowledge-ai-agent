# Pilot-overlap and duplicate review

**Status:** internal author-side comparison; independent reviewers must confirm the dispositions before freeze. The check is semantic, not a claim that string similarity proves independence.

Method: compare metric, population, entity/grain, time scope, grouping/ranking and expected behavior against P01–P05. Exact wording differences alone do not make a case independent.

| v2 case | Closest pilot | Disposition | Evidence / reviewer action |
|---|---|---|---|
| B40-001 | P01 | Related metric, distinct contract | Web sessions by month/source in 2024 vs company revenue total in 2025. Confirm acceptable metric-level proximity. |
| B40-004 | P01 | Related metric, distinct population/grain | Delivered-order AOV by month in 2025; not total company revenue. |
| B40-007 | P02 | Original replaced | Original was the same delivered-customer top-five 2025 ranking. v2 is daily company sales rows filtered by COGS > revenue. |
| B40-009 | P03 | Original replaced | Original product/category quantity query overlaps P03; v2 is inventory units_sold for Outdoor at a different snapshot. |
| B40-011 | P03 | Original replaced | Original top products by units sold 2025; v2 ranks catalog COGS, a different metric/source. |
| B40-012 | P02 | Original replaced | Original top customers by net revenue 2025 shares customer/time/ranking intent; v2 is all-status order-source count. |
| B40-013 | P04 | Related inventory family, distinct contract | Same inventory domain and ranking form, but units_received by segment, not stock_on_hand by product. |
| B40-015 | P01/P03 | Related source/measure family | Delivered item net revenue by current category in 2025. Preserve as a distinct groupby contract only if reviewers agree it does not leak the P03/P01 oracle. |
| B40-021 | P04 | Original replaced | Original exact latest-snapshot top-stock ranking; v2 counts stockout products by category. |
| B40-023 | P04 | Related inventory metric, distinct contract | Compares stock balances at two earlier exact snapshots for common products; P04 is one-snapshot top-five. |
| B40-026 | P01 | Original replaced | Original revenue 2025 monthly follow-up; v2 is COGS by month in 2024. |
| B40-027 | P02 | Related population, distinct grain | Delivered orders in inherited 2024 scope grouped by source; P02 ranks customers in 2025. |
| B40-028 | P01 | Original replaced | Original compared 2025 revenue to prior year; v2 compares 2023/2024 gross profit by month. |
| B40-029 | P03 | Original replaced | Original ranked products for top three; v2 ranks return_reason by return quantity. |
| B40-030 | P04/P05 | Related inventory domain, distinct contract | Follow-up at 2025-10-31 ranks stockout_days per product; P04/P05 use 2026-11-13 and stock/warehouse/supplier dimensions. |
| B40-031 | P01 | Original replaced | Original asked total revenue in 2025 exactly like P01; v2 is intentionally underspecified and requires clarification. |
| B40-036 | P05 | Original replaced | Original warehouse-level stock duplicated unsupported P05 dimensions; v2 abstains on absent campaign ROAS inputs. |
| B40-037 | P05 | Original replaced | Original supplier lead time duplicated unsupported P05 dimension; v2 abstains on absent employee commission data. |

Other cases: no direct pilot duplicate identified by the author-side metric/population/grain/time review; this does not replace independent review.

## Freeze gate

- Reviewer 1 and Reviewer 2 must independently approve every surviving case and the replacements.
- Explicitly adjudicate the related cases B40-001, 004, 013, 015, 023, 027 and 030.
- If a replacement is rejected, version the dataset and hash again before any SQL Agent evaluation.
