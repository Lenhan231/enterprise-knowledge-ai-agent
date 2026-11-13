# Dashboard Agent Report

**Date:** 2026-11-13

**Status:** Implemented locally; selected live workflows verified.

## Overview

The Dashboard Agent converts a natural-language question into one source-backed chart. It replaces the previous fixed inventory dashboard and is available through both the web application and Streamlit. Users select Dashboard explicitly; Auto continues to route Knowledge and SQL requests.

## Architecture

`Question -> Jev clarity check -> SQL Agent -> validated read-only query -> result rows -> chart specification -> Web/Streamlit`

The Dashboard Agent reuses the existing SQL Agent rather than generating or executing SQL independently. Chart values come directly from executed query results. Responses retain the underlying data table, SQL, parameters, sources, date scope, and limitations.

Authorization requires server-verified `analytics:read` permission. The SQL workflow retains approved-source restrictions, parameterization, semantic validation, read-only transactions, and timeouts. Jev requires at least 80% clarity before a new request proceeds.

## Supported Charts

| Type | Purpose | Example |
|---|---|---|
| Line | Trends over time | Monthly revenue during 2022 |
| Bar | Category comparisons | Count products with `stockout_flag = true` by category at 2022-12-31 |
| Donut | Composition of a complete total | Session share by traffic source during 2022 |

The chart contract allows one dimension, up to 200 categories, and up to four comparable numeric series. Missing values remain unknown, negative values are supported in line/bar charts, and temporal lines reflect actual date intervals. Unsuitable results return a table with an explanation; clarification, query failure, and empty results produce no chart.

## Current Limitations

- Approved Supabase sources only; arbitrary CSV uploads and raw document tables are unsupported.
- One chart per request; no saved dashboards, multi-chart layouts, or interactive filter builder.
- Ambiguous metric names can require clarification. Explicit definitions such as counting products with a true stockout flag work better than “total stockout.”
- Donut charts require complete, exclusive groups and a positive, nonnegative additive total. Complex queries and potentially truncated distributions remain table-only. Overlapping inventory flags cannot be exclusive slices.
- Inspected inventory, sales, and traffic history ends in 2022. These observations cannot establish current stock or performance.
- Currency is not inferred. Missing invoice currency and incompatible units restrict monetary visualizations.
- Accepted-scope follow-up memory is inventory-specific, process-local, and reset by backend restarts. Other domains generally require full scope to be restated.
- Availability depends on Supabase and the configured OpenRouter/Jev and SQL-generation providers.

## Verification and Findings

- **Automated:** 58 focused Python tests and five JavaScript renderer tests passed during implementation. A subsequent repeated-date regression fix passed 40 focused tests. These runs overlap and should not be added together.
- **Live data:** Read-only queries verified 12 monthly revenue observations, four stockout categories, and six traffic-source totals.
- **Live agent:** The stockout request passed the real Jev/model/SQL/chart flow and returned the following counts for 2022-12-31:

| Category | Flagged products |
|---|---:|
| Casual | 31 |
| GenZ | 25 |
| Outdoor | 95 |
| Streetwear | 134 |

A clarification bug was fixed: repeated mentions of the same snapshot date were incorrectly treated as a date range. The validator now deduplicates identical dates while continuing to reject mismatched scopes.

The complete repository test suite is not green; baseline failures and previously hidden stale document tests remain. Browser visual/keyboard checks and broader live prompt coverage are outstanding.

## Next Priorities

1. Verify representative line, bar, and donut requests end to end in both interfaces.
2. Improve metric aliases and clarification messages without weakening validation.
3. Complete browser accessibility/responsive checks and resolve the outstanding repository test failures before release.

Implementation details and verification commands: [SQL-backed dashboard agent](dashboard-agent.md).
