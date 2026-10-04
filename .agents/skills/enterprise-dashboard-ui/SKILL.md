---
name: enterprise-dashboard-ui
description: Design principles and UI implementation standards for enterprise business dashboards, financial KPI visualizations, and grounded document intelligence interfaces without relying on decorative emojis or generic icons.
---

# Enterprise Dashboard UI Standards

This skill provides guidelines and patterns for building clean, rigorous, and accessible enterprise dashboards. It emphasizes typographic clarity, structured data presentation, and source-grounded intelligence for analytical systems.

## Core Design Principles

1. **No Decorative Emojis or Pictograms**
   - Professional enterprise platforms communicate authority through clean typography, structured hierarchy, and functional badges.
   - Replace pictorial emojis and decorative glyphs with concise textual labels, structured data pills, or neutral SVG strokes when necessary.

2. **Source-Grounded Citations and Provenance**
   - Every factual or financial statement derived by AI or retrieval must link to its verifiable primary source document and page number.
   - Display quantitative retrieval metrics (e.g. relevance score percentage) with deterministic color bands rather than figurative ratings.

3. **Data Hierarchy and Metric Visualization**
   - KPI cards must prioritize the numeric value, followed by unit, period (fiscal year), and period-over-period comparative delta.
   - Use semantically distinct indicators for variance (e.g. positive delta versus negative delta) with appropriate high-contrast tokens.
   - Format numeric quantities using standard localized conventions (e.g. `en-US` comma grouping and dot decimals).
   - Maintain 100% English interface copy across all titles, badges, tooltips, actions, and status messages.

4. **Progressive States and Performance**
   - Provide shimmer skeleton placeholders during retrieval and analysis instead of generic spinners.
   - Support instant copy-to-clipboard interactions with clear visual confirmation states.
   - Ensure native light and dark theme contrast conformance across all analytical surfaces.
