VIETSTYLE COMMERCE — INVENTORY POLICY PACK
Version: v1.0 | 16/10/2026
Status: SIMULATION DRAFT — requires business-owner approval before real use.

FILES
01_Inventory_Management_Policy_Manual.docx
  Policy manual: governance, replenishment, ABC cycle counting, overstock, returns, promotions, approvals, data quality.
02_SOP_Cycle_Count_and_Stock_Adjustment.pdf
  Operational SOP for cycle counts, discrepancy investigation, approval and stock adjustment.
03_Policy_Rules_Registry.csv
  Machine-readable policy registry (INV-POL-001 ... INV-POL-012), suitable for policy lookup / RAG ingestion.
04_Inventory_Control_and_Reorder_Planner.xlsx
  README, Policy Matrix, Inventory Control (latest available snapshot), KPI Summary and Exception Log.
05_Inventory_Policy_Training_Deck.pptx
  Training deck for inventory staff and reviewers.

DATA BASIS
- Source: datathon-2026-round-1.zip
- inventory.csv records: 60,247
- unique inventory product IDs: 1,624
- product master SKUs: 2,412
- inventory date range: 2012-07-31 to 2022-12-31
- latest snapshot: 2022-12-31 (424 SKU rows)
- product categories in the latest snapshot: Casual, GenZ, Outdoor, Streetwear

IMPORTANT LIMITATIONS
- The latest snapshot is historical (31/12/2022), not current operational stock.
- Lead time 14 days, safety days 7 and review period 7 are assumed starting parameters.
- The dataset does not include inbound purchase orders or backorders; the workbook defaults these to 0 and expects manual input.
- The source reorder_flag is always 0; stockout_flag and overstock_flag can be simultaneously active.
- Dataset currency is not confirmed. Do not use price/cogs as a real monetary approval limit without validation.
- Policies and KPI thresholds are proposed for simulation, not approved corporate policy.
