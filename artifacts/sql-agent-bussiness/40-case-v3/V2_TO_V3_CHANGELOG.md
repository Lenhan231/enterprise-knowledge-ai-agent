# v2 to v3 changelog

Source v2 case SHA-256: 6036477937037c12dd90c10a1b00c90735ec8d48ba08ebbb8775f217f8a01677

Source v2 Gold SQL SHA-256: 422d82e809b646477af4295e3e01561b27c08ed3e505f4bafa2928fe3ea45e6d

Source v2 provisional result SHA-256: 56dbddbf953d411c538bb0b7eef3db15cbb23358a5d56221463f50decd9b60bb

The source artifacts remain in ../40-case-preparation/ and are not overwritten.

| Case | v2 weakness | v3 change | Snapshot evidence |
|---|---|---|---|
| B40-002 | 2024 shipment population had no missing delivery dates | Move to 2025; report monthly completed average and missing delivery-date count | 728 shipments, 7 missing delivery dates |
| B40-006 | East and non-NULL age filters did not reduce the selected population | Use profile ZIP mapped to Hai Phong and age_group 25-34 | 711 signups; city 79; age 143; intersection 17 |
| B40-008 | All selected reasons were non-NULL | Preserve the business question and explicitly mark NULL-filter detection as unsupported by available data | Zero NULL reasons in 2023, 2024, and 2025 |
| B40-015 | TOP 5 exceeded the four available categories | Use TOP 3 | Four delivered-order categories in 2025 |
| B40-017 | Each 2025 product had only one return row | Widen return_date to 2023-2025 | 56 of 60 product groups combine multiple rows; maximum 3 rows |
| B40-020 | All selected shipping fees were non-NULL | Preserve shipping-fee metric and remove any claim of NULL-fee coverage | 728 recorded, 0 missing |
| B40-021 | “Has a flag” did not define the required boolean population | Ask for stockout_flag = TRUE; add a negative IS NOT NULL probe | 17 TRUE, 80 FALSE, 0 NULL |
| B40-023 | Both exact snapshots contain the same products | Preserve the requested comparison and state the membership-intersection limitation | 97 common, 0 before-only, 0 after-only |
| B40-026 | Full metric and year were repeated in follow-up wording | Shorten follow-up to “Hãy trình bày theo từng tháng.” so COGS/year must come from frozen context | Deterministic adapter test covers prior question and typed state |
| B40-027 | Delivered filter did not change the 2024 result | Inherit 2025 all-status order_source context; follow-up adds delivered status | 733 total, 719 delivered, 14 other statuses |
| B40-028 | Returned separate year/month rows rather than aligned monthly comparison | Inherit 2024 gross profit, compare 2023, return month and paired profit/difference fields | Gold structure pairs same calendar month and keeps missing values NULL |
| B40-029 | Exactly three reasons made TOP 3 ineffective | Change follow-up to TOP 2 | Three return reasons in inherited 2024 scope |
| B40-033 | Clarification omitted product identity | Ask for product, historical snapshot, and whether real-time was intended | Schema has no warehouse dimension or live-stock source |

Other cases retain their v2 wording and intended business metric. Every v3 Gold SQL and result remains pending independent review.
