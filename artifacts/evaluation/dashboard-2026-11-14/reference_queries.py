"""Read-only reference observations for the five priority regression cases."""
import asyncio,json
from pathlib import Path
import asyncpg
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
QUERIES={
 'DB-03-monthly': "SELECT date_trunc('month',date) AS month, SUM(revenue) AS revenue FROM commerce.sales WHERE date >= DATE '2026-01-01' AND date < DATE '2027-01-01' GROUP BY 1 ORDER BY 1",
 'DB-03-total': "SELECT SUM(revenue) AS revenue FROM commerce.sales WHERE date >= DATE '2026-01-01' AND date < DATE '2027-01-01'",
 'DB-11': "SELECT p.category, COUNT(DISTINCT o.order_id) AS distinct_orders FROM commerce.orders o JOIN commerce.order_items oi ON oi.order_id=o.order_id JOIN commerce.products p ON p.product_id=oi.product_id WHERE o.order_date>=DATE '2026-01-01' AND o.order_date<DATE '2027-01-01' GROUP BY 1 ORDER BY 1",
 'DB-13': "SELECT i.snapshot_date,i.category,SUM(i.stock_on_hand) AS stock_on_hand FROM commerce.inventory i WHERE i.snapshot_date IN (SELECT DISTINCT snapshot_date FROM commerce.inventory ORDER BY snapshot_date DESC LIMIT 3) GROUP BY 1,2 ORDER BY 1,2",
 'DB-20-monthly': "SELECT date_trunc('month',date) AS month, SUM(revenue) AS revenue FROM commerce.sales WHERE date>=DATE '2026-07-01' AND date<DATE '2026-10-01' GROUP BY 1 ORDER BY 1",
 'DB-20-total': "SELECT SUM(revenue) AS revenue FROM commerce.sales WHERE date>=DATE '2026-07-01' AND date<DATE '2026-10-01'",
 'DB-22-source-coverage': "SELECT COUNT(*) AS joined_rows, COUNT(DISTINCT o.order_id) AS recorded_distinct_orders, COUNT(DISTINCT p.category) AS categories FROM commerce.orders o LEFT JOIN commerce.order_items oi ON oi.order_id=o.order_id LEFT JOIN commerce.products p ON p.product_id=oi.product_id WHERE o.order_date>=DATE '2026-01-01' AND o.order_date<DATE '2027-01-01'"
}
async def main():
 c=await asyncpg.connect(json.loads((ROOT/'artifacts/local/dashboard-benchmark-connection.json').read_text())['url'])
 result={}
 async with c.transaction(readonly=True):
  for name,query in QUERIES.items(): result[name]={'sql':query,'observations':[dict(row) for row in await c.fetch(query)]}
 await c.close()
 (OUT/'priority_references.json').write_text(json.dumps(result,default=str,ensure_ascii=False,indent=2),encoding='utf-8')
 print('Saved',len(result),'reference queries')
if __name__=='__main__': asyncio.run(main())
