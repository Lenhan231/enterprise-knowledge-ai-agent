# Inventory

snapshot_date: 2022-12-31 (source_field; snapshot_date=2022-12-31, product_id=1, product_name=DragonWear MA-01) [F1] [S1]

| snapshot_date | product_id | stock_on_hand |
| --- | --- | --- |
| 2022-12-31 [F1] [S1] | 1 [F2] [S1] | 3 [F4] [S1] |
| 2022-12-31 [F5] [S1] | 3 [F6] [S1] | 151 [F8] [S1] |

# Verified details: stock

Validated returned observations.

| snapshot_date | product_id | product_name | stock_on_hand |
| --- | --- | --- | --- |
| 2022-12-31 [F1] [S1] | 1 [F2] [S1] | DragonWear MA-01 [F3] [S1] | 3 [F4] [S1] |
| 2022-12-31 [F5] [S1] | 3 [F6] [S1] | DragonWear MA-03 [F7] [S1] | 151 [F8] [S1] |


## Report status and sources
Status: complete
Quantitative facts are checked against metric identity, value, unit, dimensions, filters and snapshot date. Generated interpretation is not fully semantically verified. Retained template text is user-provided and unverified.
Section Inventory: complete
- Historical monthly observations; every answer must state the selected snapshot date.
- Missing product snapshots are not zero inventory; denominators cover observed products only.
- No live warehouse balance, purchase-order, backorder, forecast or supplier lead-time evidence.
- Stored rate values are returned unchanged as fractions; 0.25 displays as 25 percent, without implying the original source formula.
- Inventory observations are historical; selected snapshot dates: 2022-12-31
- Narrative uses a bounded fact selection; detail tables contain returned validated observations, not an exhaustive export.
Coverage stock: {"requested": "Compare the 2022-12-31 stock_on_hand of DragonWear MA-01 (product_id 1) and DragonWear MA-03 (product_id 3).", "returned": 2, "included": 2, "omitted": 0, "completeness": "returned_query_scope", "snapshots": []}
Narrative coverage Inventory: {"facts_available": 8, "facts_included": 8, "facts_omitted": 0, "documents_included": 0, "documents_omitted": 0}
[S1] Validated report query: stock
