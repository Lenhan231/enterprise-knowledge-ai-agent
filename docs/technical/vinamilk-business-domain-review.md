# Vinamilk business-domain review

Last checked: 2026-10-01. This is a decision-domain audit of the verified
`business_metric_evidence` rows, not a claim that each domain has a complete
corpus. Counts are a live database snapshot; rerun the grouped domain query in
the project README before using them as a current total.

## Dashboard decision

Keep the focused business domains: market performance, milk supply, farm
operations, product portfolio, manufacturing efficiency, environmental
performance, and human resources. Keep consolidated financial results in their
separate financial tab. Do not turn a small number of current observations into
a reason to discard a decision area when Vinamilk's official reports contain
sourceable history that has not yet been backfilled.

For the current dashboard, prioritize market performance, environmental
performance, milk supply, and product portfolio as the most established
decision views. Keep manufacturing efficiency visible but flag its limited
repeatable year-over-year series. Keep farm operations and human resources as
specialist views until the official 2023 evidence is processed and reviewed;
they are source-supported domains, but their current database coverage is too
thin to give them equal dashboard prominence.

Merge two narrow domains into their natural parent decisions:

| Before | Current evidence | New parent | Reason |
| --- | ---: | --- | --- |
| Distribution reach | 2 verified rows, 2 metrics, 2024 | Market performance | Retail points of sale and owned stores are route-to-market signals; the official 2023 sustainability report also reports roughly 11,126 supermarket/convenience-store points and nearly 650 Vinamilk stores. |
| Manufacturing quality | 1 verified row, 1 metric, 2023 | Manufacturing efficiency | Defect-free streak is a factory quality/reliability signal alongside OEE, TPM, and production cost measures; it is not a separate decision domain by itself. |

After merging, the live snapshot is: market performance 43 rows / 27 metrics;
environmental performance 38 / 14; milk supply 17 / 11; product portfolio
12 / 9; manufacturing efficiency 20 / 20; farm operations 6 / 6; human
resources 4 / 3. Most recent fiscal coverage is not a completeness test: rows
can be sparse because source reports have not been processed into evidence yet.

## Backfill before pruning

Vinamilk's official Sustainable Development Report 2023 already provides
potential historical evidence for domains that look thin in the current
database:

- Farm operations: 14 dairy farms, 140,000 milk cows, and 75 raw-milk collection
  stations (report p. 9).
- Market performance: over 11,126 supermarket/convenience-store points of sale
  and nearly 650 Vinamilk stores (report p. 9).
- Human resources: over 300,000 training hours and a workforce table reporting
  693 hires and 708 departures (report pp. 109–110). Keep hiring and departures
  as separate counts; do not call their difference an attrition rate.
- Manufacturing efficiency and quality: the five-year TPM results include
  10% production-cost improvement, 14% OEE increase on A1 lines, 4 years
  without product defects, and rework/quality indicators (report p. 47).

These are candidate source observations, not yet added to the database by this
review. They should go through report processing, exact page/quote matching,
and admin verification before they appear on the dashboard. The 2024 annual
report also reports 358,741 training hours, 18.9% growth over 2020–2024, and
over 96% of production lines meeting target OEE; preserve the stated scope and
period rather than treating those as equivalent to every other report's KPI.

## Decision limits

- Market performance is the strongest multi-year commercial domain, but
  market-share claims and revenue growth alone do not establish attractive
  margins or return on investment.
- Milk supply is useful for annual sourcing mix and resilience signals; it
  cannot replace monthly supplier quality, accepted/rejected volume, purchase
  price, region, or factory-demand data.
- Product portfolio supports diligence on reported growth/consumer signals,
  not product-level contribution margin or launch ROI.
- Manufacturing measures are currently sparse and mostly company-reported
  one-off TPM/OEE indicators; factory-level denominators and consistent
  year-over-year series are missing.
- Farm operations and human resources stay separate because they support
  different decisions. Backfill the available report history before deciding
  whether their *current database coverage* warrants primary dashboard space.
- Environmental metrics have multi-year reporting, but 2025 waste assurance
  boundary changes and intensity rebounds must remain visible in comparisons.

## Official sources checked

- [Vinamilk Sustainable Development Report 2023 (English PDF)](https://www.vinamilk.com.vn/phat-trien-ben-vung/bao-cao/2023/pdf/RGB-ENG-Vinamilk-SR-2023.pdf), pp. 9, 47, 109–110.
- [Vinamilk Annual Report 2024 (English PDF)](https://www.vinamilk.com.vn/bao-cao-thuong-nien/bao-cao/2024/doc/en/vinamilk-ar-eng-full-layout-interactive.pdf), training and production sections.
- [Vinamilk official archive of sustainability reports](https://www.vinamilk.com.vn/investor/reports/sustainability/), confirming report availability for multiple years.
