"""Independent benchmark oracles, authored before agent generation.

These fixed SELECTs run only in a read-only transaction. They are evaluator data,
not prompts, patches to the agents, or agent-generated answers.
"""

SNAP = "i.snapshot_date = DATE '2022-12-31'"
YEAR_I = "i.snapshot_date >= DATE '2022-01-01' AND i.snapshot_date < DATE '2023-01-01'"
YEAR_O = "o.order_date >= DATE '2022-01-01' AND o.order_date < DATE '2023-01-01'"
YEAR_R = "r.return_date >= DATE '2022-01-01' AND r.return_date < DATE '2023-01-01'"
DEC_O = "o.order_date >= DATE '2022-12-01' AND o.order_date < DATE '2023-01-01'"
IP = 'commerce.inventory i JOIN commerce.products p ON i.product_id=p.product_id'
OP = 'commerce.orders o JOIN commerce.order_items oi ON o.order_id=oi.order_id JOIN commerce.products p ON oi.product_id=p.product_id'
RP = 'commerce.returns r JOIN commerce.products p ON r.product_id=p.product_id'

SQL = {
 'S01': 'SELECT MAX(snapshot_date) AS latest_snapshot FROM commerce.inventory',
 'S02': f'SELECT COUNT(DISTINCT i.product_id) AS product_count FROM commerce.inventory i WHERE {SNAP}',
 'S03': f'SELECT i.product_id,p.product_name,i.stock_on_hand FROM {IP} WHERE {SNAP} ORDER BY i.stock_on_hand DESC NULLS LAST,i.product_id LIMIT 20',
 'S04': f'SELECT p.category,SUM(i.stock_on_hand) AS stock_on_hand FROM {IP} WHERE {SNAP} GROUP BY p.category ORDER BY stock_on_hand DESC NULLS LAST,p.category',
 'S05': 'SELECT COUNT(DISTINCT product_id) AS product_count FROM commerce.inventory WHERE snapshot_date=(SELECT MAX(snapshot_date) FROM commerce.inventory) AND reorder_flag=TRUE',
 'S06': f'SELECT i.product_id,p.product_name,i.stockout_days FROM {IP} WHERE {SNAP} AND i.stockout_flag=TRUE ORDER BY i.product_id LIMIT 200',
 'S07': f'SELECT p.category,COUNT(DISTINCT i.product_id) AS product_count FROM {IP} WHERE {SNAP} AND i.overstock_flag=TRUE GROUP BY p.category ORDER BY product_count DESC,p.category',
 'S08': f'SELECT i.product_id,p.product_name,i.days_of_supply FROM {IP} WHERE {SNAP} AND i.days_of_supply IS NOT NULL ORDER BY i.days_of_supply,i.product_id LIMIT 200',
 'S09': f'SELECT i.product_id,p.product_name,i.stock_on_hand FROM {IP} WHERE {SNAP} AND i.product_id IN (1,3) ORDER BY i.product_id',
 'S10': f'SELECT p.category,AVG(i.fill_rate) AS fill_rate FROM {IP} WHERE {SNAP} GROUP BY p.category ORDER BY p.category',
 'S11': f'SELECT i.product_id,p.product_name,i.stockout_days FROM {IP} WHERE {SNAP} ORDER BY i.stockout_days DESC NULLS LAST,i.product_id LIMIT 200',
 'S12': f"SELECT DATE_TRUNC('month',i.snapshot_date)::date AS month,SUM(i.units_sold) AS units_sold FROM commerce.inventory i WHERE {YEAR_I} GROUP BY 1 ORDER BY 1",
 'S13': "SELECT a.product_id,a.stock_on_hand AS november_stock,b.stock_on_hand AS december_stock,b.stock_on_hand-a.stock_on_hand AS stock_change FROM commerce.inventory a JOIN commerce.inventory b ON a.product_id=b.product_id WHERE a.snapshot_date=DATE '2022-11-30' AND b.snapshot_date=DATE '2022-12-31' ORDER BY a.product_id LIMIT 200",
 'S14': "SELECT p.product_id,p.product_name FROM commerce.products p WHERE NOT EXISTS (SELECT 1 FROM commerce.inventory i WHERE i.product_id=p.product_id AND i.snapshot_date=DATE '2022-12-31') ORDER BY p.product_id LIMIT 200",
 'S15': f'SELECT i.snapshot_date,i.product_id,i.stock_on_hand,i.units_received,i.units_sold,i.stockout_days,i.days_of_supply,i.fill_rate,i.stockout_flag,i.overstock_flag,i.reorder_flag,i.sell_through_rate FROM commerce.inventory i WHERE {SNAP} AND i.product_id=8',
 'S16': f'SELECT p.category,SUM(i.units_received) AS units_received FROM {IP} WHERE {YEAR_I} GROUP BY p.category ORDER BY units_received DESC NULLS LAST,p.category',
 'S17': f"SELECT p.product_id,p.product_name,SUM(oi.quantity) AS ordered_units FROM {OP} WHERE {YEAR_O} AND LOWER(o.order_status) NOT IN ('cancelled','canceled') GROUP BY p.product_id,p.product_name ORDER BY ordered_units DESC,p.product_id LIMIT 20",
 'S18': f'SELECT p.category,COUNT(DISTINCT o.order_id) AS order_count FROM {OP} WHERE {DEC_O} GROUP BY p.category ORDER BY p.category',
 'S19': f'SELECT p.category,SUM(oi.quantity*oi.unit_price) AS gross_line_value FROM {OP} WHERE {YEAR_O} GROUP BY p.category ORDER BY p.category',
 'S20': f'SELECT p.category,SUM(oi.quantity*oi.unit_price-COALESCE(oi.discount_amount,0)) AS net_line_value FROM {OP} WHERE {YEAR_O} GROUP BY p.category ORDER BY p.category',
 'S21': f'SELECT r.product_id,SUM(r.return_quantity) AS returned_units FROM commerce.returns r WHERE {YEAR_R} GROUP BY r.product_id ORDER BY returned_units DESC,r.product_id LIMIT 10',
 'S22': f'SELECT p.category,SUM(r.refund_amount) AS refund_amount FROM {RP} WHERE {YEAR_R} GROUP BY p.category ORDER BY p.category',
 'S23': f'WITH ret AS (SELECT r.product_id,SUM(r.return_quantity) AS returned_units FROM commerce.returns r WHERE {YEAR_R} GROUP BY r.product_id), ord AS (SELECT oi.product_id,SUM(oi.quantity) AS ordered_units FROM commerce.orders o JOIN commerce.order_items oi ON o.order_id=oi.order_id WHERE {YEAR_O} GROUP BY oi.product_id) SELECT ret.product_id,ret.returned_units,ord.ordered_units,ret.returned_units::numeric/NULLIF(ord.ordered_units,0) AS returned_to_ordered_ratio FROM ret JOIN ord ON ret.product_id=ord.product_id ORDER BY returned_to_ordered_ratio DESC NULLS LAST,ret.product_id LIMIT 200',
 'S24': f'SELECT r.return_reason,SUM(r.return_quantity) AS returned_units FROM commerce.returns r WHERE {YEAR_R} GROUP BY r.return_reason ORDER BY r.return_reason',
 'S25': 'SELECT DISTINCT r.order_id,r.product_id FROM commerce.returns r WHERE NOT EXISTS (SELECT 1 FROM commerce.order_items oi WHERE oi.order_id=r.order_id AND oi.product_id=r.product_id) ORDER BY r.order_id,r.product_id LIMIT 200',
 'S26': f'SELECT i.product_id,p.product_name FROM {IP} WHERE {SNAP} AND i.stockout_flag=TRUE AND EXISTS (SELECT 1 FROM commerce.orders o JOIN commerce.order_items oi ON o.order_id=oi.order_id WHERE oi.product_id=i.product_id AND {DEC_O}) ORDER BY i.product_id LIMIT 200',
 'S27': f'WITH inv AS (SELECT p.category,SUM(i.units_sold) AS inventory_units_sold FROM {IP} WHERE {SNAP} GROUP BY p.category), ord AS (SELECT p.category,SUM(oi.quantity) AS ordered_units FROM {OP} WHERE {DEC_O} GROUP BY p.category) SELECT inv.category,inv.inventory_units_sold,ord.ordered_units FROM inv FULL JOIN ord ON inv.category=ord.category ORDER BY inv.category',
 'S28': 'SELECT COALESCE(SUM(n-1),0) AS duplicate_rows FROM (SELECT COUNT(*) AS n FROM commerce.inventory GROUP BY snapshot_date,product_id HAVING COUNT(*)>1) d',
}

EXTRA = {
 'health': f'SELECT COUNT(DISTINCT i.product_id) AS observed_products,SUM(i.stock_on_hand) AS stock_on_hand,SUM(i.units_sold) AS units_sold,SUM(i.units_received) AS units_received,COUNT(*) FILTER(WHERE i.stockout_flag) AS stockout_products,COUNT(*) FILTER(WHERE i.overstock_flag) AS overstock_products,COUNT(*) FILTER(WHERE i.reorder_flag) AS reorder_products FROM commerce.inventory i WHERE {SNAP}',
 'category_health': f'SELECT p.category,COUNT(DISTINCT i.product_id) AS observed_products,SUM(i.stock_on_hand) AS stock_on_hand,SUM(i.stockout_days) AS stockout_product_days,AVG(i.fill_rate) AS mean_stored_fill_rate,COUNT(*) FILTER(WHERE i.stockout_flag) AS stockout_products,COUNT(*) FILTER(WHERE i.overstock_flag) AS overstock_products,COUNT(*) FILTER(WHERE i.reorder_flag) AS reorder_products FROM {IP} WHERE {SNAP} GROUP BY p.category ORDER BY p.category',
 'details': f'SELECT i.product_id,p.product_name,p.category,i.stock_on_hand,i.days_of_supply,i.stockout_days,i.stockout_flag,i.overstock_flag,i.reorder_flag FROM {IP} WHERE {SNAP} ORDER BY i.product_id LIMIT 200',
 'overstock': f'SELECT i.product_id,p.product_name,p.category,i.stock_on_hand,i.days_of_supply,i.stockout_days FROM {IP} WHERE {SNAP} AND i.overstock_flag ORDER BY i.stock_on_hand DESC NULLS LAST,i.product_id LIMIT 200',
 'trends': f"SELECT DATE_TRUNC('month',i.snapshot_date)::date AS month,SUM(i.units_sold) AS units_sold,SUM(i.units_received) AS units_received,SUM(i.stock_on_hand) AS stock_on_hand,COUNT(DISTINCT i.product_id) AS observed_products,COUNT(*) FILTER(WHERE i.reorder_flag) AS reorder_products,COUNT(*) FILTER(WHERE i.stockout_flag) AS stockout_products FROM commerce.inventory i WHERE {YEAR_I} GROUP BY 1 ORDER BY 1",
 'pair_history': "SELECT snapshot_date,product_id,stock_on_hand FROM commerce.inventory WHERE snapshot_date IN (DATE '2022-11-30',DATE '2022-12-31') AND product_id IN (1,3) ORDER BY snapshot_date,product_id",
 'selected': f'SELECT i.product_id,p.product_name,p.category,i.stock_on_hand,i.days_of_supply,i.stockout_days,i.stockout_flag,i.overstock_flag,i.reorder_flag FROM {IP} WHERE {SNAP} AND i.product_id IN (1,8,17) ORDER BY i.product_id',
 'annual_category': f'SELECT p.category,SUM(i.units_sold) AS units_sold,SUM(i.units_received) AS units_received,AVG(i.fill_rate) AS mean_stored_fill_rate,SUM(i.stockout_days) AS stockout_product_days FROM {IP} WHERE {YEAR_I} GROUP BY p.category ORDER BY p.category',
 'q4': f"SELECT i.snapshot_date,p.category,COUNT(*) FILTER(WHERE i.reorder_flag) AS reorder_products,SUM(i.stock_on_hand) AS stock_on_hand,SUM(i.units_received) AS units_received FROM {IP} WHERE i.snapshot_date>=DATE '2022-10-01' AND i.snapshot_date<DATE '2023-01-01' GROUP BY i.snapshot_date,p.category ORDER BY i.snapshot_date,p.category",
 'coverage': "SELECT (SELECT COUNT(*) FROM commerce.products) AS catalog_products,(SELECT COUNT(DISTINCT product_id) FROM commerce.inventory WHERE snapshot_date=DATE '2022-12-31') AS observed_products,(SELECT COUNT(*) FROM commerce.products p WHERE NOT EXISTS(SELECT 1 FROM commerce.inventory i WHERE i.product_id=p.product_id AND i.snapshot_date=DATE '2022-12-31')) AS missing_catalog_products",
 'valuation': f'SELECT p.category,SUM(i.stock_on_hand*p.cogs) AS catalog_cost_stock_proxy FROM {IP} WHERE {SNAP} GROUP BY p.category ORDER BY p.category',
 'margin': f'SELECT p.category,SUM(oi.quantity*oi.unit_price) AS gross_line_value,SUM(oi.quantity*p.cogs) AS catalog_cost_proxy,SUM(oi.quantity*(oi.unit_price-p.cogs)) AS gross_margin_proxy FROM {OP} WHERE {YEAR_O} GROUP BY p.category ORDER BY p.category',
 'top_sales': f'SELECT p.product_id,p.product_name,SUM(oi.quantity) AS ordered_units,(SELECT i.stock_on_hand FROM commerce.inventory i WHERE i.product_id=p.product_id AND {SNAP}) AS december_stock FROM {OP} WHERE {YEAR_O} GROUP BY p.product_id,p.product_name ORDER BY ordered_units DESC,p.product_id LIMIT 15',
 'returns_reason': f'SELECT p.category,r.return_reason,SUM(r.return_quantity) AS returned_units,SUM(r.refund_amount) AS refund_amount FROM {RP} WHERE {YEAR_R} GROUP BY p.category,r.return_reason ORDER BY p.category,r.return_reason',
 'return_overstock': f'SELECT p.product_id,p.product_name,SUM(r.return_quantity) AS returned_units,i.stock_on_hand,i.days_of_supply FROM {RP} JOIN commerce.inventory i ON i.product_id=p.product_id WHERE {YEAR_R} AND {SNAP} AND i.overstock_flag GROUP BY p.product_id,p.product_name,i.stock_on_hand,i.days_of_supply ORDER BY returned_units DESC,p.product_id LIMIT 200',
 'demand': f'WITH ord AS (SELECT oi.product_id,SUM(oi.quantity) AS ordered_units FROM commerce.orders o JOIN commerce.order_items oi ON o.order_id=oi.order_id WHERE {DEC_O} GROUP BY oi.product_id) SELECT i.product_id,p.category,i.stockout_flag,i.stockout_days,i.units_sold,COALESCE(ord.ordered_units,0) AS ordered_units FROM {IP} LEFT JOIN ord ON ord.product_id=i.product_id WHERE {SNAP} ORDER BY i.product_id LIMIT 200',
 'quality': "SELECT COUNT(*) AS inventory_rows,COUNT(*) FILTER(WHERE fill_rate IS NULL) AS null_fill_rate,COUNT(*) FILTER(WHERE days_of_supply IS NULL) AS null_days_of_supply,COUNT(*) FILTER(WHERE sell_through_rate IS NULL) AS null_sell_through_rate,COUNT(*) FILTER(WHERE NOT EXISTS(SELECT 1 FROM commerce.products p WHERE p.product_id=i.product_id)) AS unmatched_product_rows FROM commerce.inventory i",
 'reconcile': f'SELECT (SELECT SUM(i.units_sold) FROM commerce.inventory i WHERE {YEAR_I}) AS inventory_units_sold,(SELECT SUM(oi.quantity) FROM commerce.orders o JOIN commerce.order_items oi ON oi.order_id=o.order_id WHERE {YEAR_O}) AS ordered_units',
 'segment': f'SELECT p.segment,p.category,SUM(i.units_sold) AS inventory_units_sold,SUM(i.units_received) AS units_received,SUM(i.stockout_days) AS stockout_product_days FROM {IP} WHERE {YEAR_I} GROUP BY p.segment,p.category ORDER BY p.segment,p.category',
 'range': 'SELECT MIN(snapshot_date) AS first_snapshot,MAX(snapshot_date) AS latest_snapshot,COUNT(DISTINCT snapshot_date) AS snapshot_count FROM commerce.inventory',
}

REPORT_TASKS = {
 'R01':['health','category_health'], 'R02':['category_health','S06'],
 'R03':['overstock','category_health'], 'R04':['health','details'],
 'R05':['details'], 'R06':['trends'], 'R07':['pair_history'],
 'R08':['annual_category'], 'R09':['q4'], 'R10':['selected'],
 'R11':['coverage','S14'], 'R12':['valuation'], 'R13':['margin'],
 'R14':['top_sales'], 'R15':['trends','annual_category','S19'],
 'R16':['returns_reason'], 'R17':['S23'], 'R18':['return_overstock'],
 'R19':['demand','category_health'], 'R20':['quality','S28','coverage'],
 'R21':['reconcile'], 'R22':['trends'], 'R23':['segment'],
 'R24':['category_health','S06'], 'R25':['details','category_health'],
 'R26':[], 'R27':[], 'R28':['range'], 'R29':[],
 'R30':['trends','annual_category','health','S19','S22'],
}

COMMON_LIMITATIONS = (
 'Historical snapshots are observations, not live stock or proof of operational execution. '
 'Missing snapshots are not zero. Stored ratios are unweighted averages unless stated; '
 'stockout_days sums are product-days. Flags can overlap. Detail references are capped at 200 '
 'with stable ordering; aggregates are computed before limits. No currency may be inferred. '
 'Inventory units_sold and order quantities are different sources, not automatically reconcilable. '
 'Catalog cogs is only a labelled cost proxy, not approved valuation or accounting margin. '
 'Returned units divided by ordered units in separate calendar-year windows is a unit ratio, '
 'not the canonical order-based return_rate or a matched-cohort rate. '
 'No approved reorder quantities, safety stock, lead times, supplier receipt compliance, '
 'warehouse sellable stock, actual product ages, or returned-stock disposition are available. '
 'Recommendations require human approval and do not authorize purchase orders or stock changes.'
)
