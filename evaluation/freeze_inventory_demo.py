"""Author-reviewed independent inventory oracles; freeze before any model generations."""
import asyncio
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'src')]
OUT = ROOT/'artifacts/evaluation/inventory-demo-2026-11-04/fixtures'

# References are authored here, independently of the candidate parser/compiler.
CASES = [
('direct', 'List product_id and product_name from products limit 10.', 'SELECT product_id,product_name FROM commerce.products ORDER BY product_id LIMIT 10'),
('direct', "Show product_id, color and price from products where color='blue' order by price desc limit 5.", "SELECT product_id,color,price FROM commerce.products WHERE color='blue' ORDER BY price DESC,product_id LIMIT 5"),
('direct', "Get product_id and size from products where size IS NULL limit 20.", 'SELECT product_id,size FROM commerce.products WHERE size IS NULL ORDER BY product_id LIMIT 20'),
('direct', "Display product_id, category from products where category IN ('Streetwear','Activewear') limit 12.", "SELECT product_id,category FROM commerce.products WHERE category IN ('Streetwear','Activewear') ORDER BY product_id LIMIT 12"),
('direct', 'Please show product_id and cogs from products where cogs>100000 order by cogs asc limit 7.', 'SELECT product_id,cogs FROM commerce.products WHERE cogs>100000 ORDER BY cogs ASC,product_id LIMIT 7'),
('direct', 'List product_id,price from products where price>=200000 and price<500000 order by price desc limit 8.', 'SELECT product_id,price FROM commerce.products WHERE price>=200000 AND price<500000 ORDER BY price DESC,product_id LIMIT 8'),
('direct', "List snapshot_date,product_id from inventory where snapshot_date='2022-12-31' and product_id IN (1,3,5) limit 10.", "SELECT snapshot_date,product_id FROM commerce.inventory WHERE snapshot_date=DATE '2022-12-31' AND product_id IN (1,3,5) ORDER BY product_id,snapshot_date LIMIT 10"),
('direct', "Retrieve product_id,segment from products where segment IS NOT NULL order by segment asc limit 9.", 'SELECT product_id,segment FROM commerce.products WHERE segment IS NOT NULL ORDER BY segment ASC,product_id LIMIT 9'),
('direct', 'List product_id,product_name from products where product_id>400 order by product_id desc limit 6.', 'SELECT product_id,product_name FROM commerce.products WHERE product_id>400 ORDER BY product_id DESC LIMIT 6'),
('direct', "Show snapshot_date,product_id,year,month from inventory where snapshot_date='2022-11-30' order by product_id limit 15.", "SELECT snapshot_date,product_id,year,month FROM commerce.inventory WHERE snapshot_date=DATE '2022-11-30' ORDER BY product_id,snapshot_date LIMIT 15"),
('structural', 'What is the latest available inventory snapshot date?', 'SELECT MAX(snapshot_date) AS snapshot_date FROM commerce.inventory'),
('structural', 'How many master product records are in commerce.products?', 'SELECT COUNT(*) AS product_count FROM commerce.products'),
('structural', 'Count products by category in the master products table.', 'SELECT category,COUNT(*) AS product_count FROM commerce.products GROUP BY category ORDER BY category LIMIT 200'),
('structural', 'Which distinct snapshot dates were observed in inventory during December 2022?', "SELECT DISTINCT snapshot_date FROM commerce.inventory WHERE snapshot_date>=DATE '2022-12-01' AND snapshot_date<DATE '2023-01-01' ORDER BY snapshot_date LIMIT 200"),
('structural', 'Count excess duplicate inventory rows beyond the first per (snapshot_date, product_id) key.', 'WITH d AS (SELECT snapshot_date,product_id,COUNT(*) AS n FROM commerce.inventory GROUP BY snapshot_date,product_id) SELECT COALESCE(SUM(n-1),0) AS duplicate_rows FROM d'),
('inventory', 'Show total stock_on_hand at snapshot 2022-12-31.', "SELECT snapshot_date,SUM(stock_on_hand) AS stock_on_hand FROM commerce.inventory WHERE snapshot_date=DATE '2022-12-31' GROUP BY snapshot_date"),
('inventory', 'Show stock_on_hand by category at snapshot 2022-12-31.', "SELECT i.snapshot_date,p.category,SUM(i.stock_on_hand) AS stock_on_hand FROM commerce.inventory i JOIN commerce.products p ON p.product_id=i.product_id WHERE i.snapshot_date=DATE '2022-12-31' GROUP BY i.snapshot_date,p.category ORDER BY i.snapshot_date,p.category LIMIT 200"),
('inventory', 'Show stock_on_hand by segment at snapshot 2022-11-30.', "SELECT i.snapshot_date,p.segment,SUM(i.stock_on_hand) AS stock_on_hand FROM commerce.inventory i JOIN commerce.products p ON p.product_id=i.product_id WHERE i.snapshot_date=DATE '2022-11-30' GROUP BY i.snapshot_date,p.segment ORDER BY i.snapshot_date,p.segment LIMIT 200"),
('inventory', 'Show the 10 products with lowest stock_on_hand at snapshot 2022-12-31; include product_id and product_name.', "SELECT i.snapshot_date,i.product_id,p.product_name,i.stock_on_hand FROM commerce.inventory i JOIN commerce.products p ON p.product_id=i.product_id WHERE i.snapshot_date=DATE '2022-12-31' ORDER BY i.stock_on_hand ASC,i.product_id LIMIT 10"),
('inventory', 'Show the top 7 products by stock_on_hand at snapshot 2022-11-30, with product_id and category.', "SELECT i.snapshot_date,i.product_id,p.category,i.stock_on_hand FROM commerce.inventory i JOIN commerce.products p ON p.product_id=i.product_id WHERE i.snapshot_date=DATE '2022-11-30' ORDER BY i.stock_on_hand DESC,i.product_id LIMIT 7"),
('inventory', "Show stock_on_hand by category at snapshot 2022-12-31 where color='blue'.", "SELECT i.snapshot_date,p.category,SUM(i.stock_on_hand) AS stock_on_hand FROM commerce.inventory i JOIN commerce.products p ON p.product_id=i.product_id WHERE i.snapshot_date=DATE '2022-12-31' AND p.color='blue' GROUP BY i.snapshot_date,p.category ORDER BY i.snapshot_date,p.category LIMIT 200"),
('inventory', 'Show mean stored fill_rate by category at snapshot 2022-12-31.', "SELECT i.snapshot_date,p.category,AVG(i.fill_rate) AS fill_rate FROM commerce.inventory i JOIN commerce.products p ON p.product_id=i.product_id WHERE i.snapshot_date=DATE '2022-12-31' GROUP BY i.snapshot_date,p.category ORDER BY i.snapshot_date,p.category LIMIT 200"),
('inventory', 'Show mean stored days_of_supply by category at snapshot 2022-11-30.', "SELECT i.snapshot_date,p.category,AVG(i.days_of_supply) AS days_of_supply FROM commerce.inventory i JOIN commerce.products p ON p.product_id=i.product_id WHERE i.snapshot_date=DATE '2022-11-30' GROUP BY i.snapshot_date,p.category ORDER BY i.snapshot_date,p.category LIMIT 200"),
('inventory', 'Show units_received by category at snapshot 2022-12-31.', "SELECT i.snapshot_date,p.category,SUM(i.units_received) AS units_received FROM commerce.inventory i JOIN commerce.products p ON p.product_id=i.product_id WHERE i.snapshot_date=DATE '2022-12-31' GROUP BY i.snapshot_date,p.category ORDER BY i.snapshot_date,p.category LIMIT 200"),
('inventory', 'Show inventory_units_sold by category at snapshot 2022-11-30.', "SELECT i.snapshot_date,p.category,SUM(i.units_sold) AS inventory_units_sold FROM commerce.inventory i JOIN commerce.products p ON p.product_id=i.product_id WHERE i.snapshot_date=DATE '2022-11-30' GROUP BY i.snapshot_date,p.category ORDER BY i.snapshot_date,p.category LIMIT 200"),
('inventory', 'Count observed products at snapshot 2022-12-31.', "SELECT COUNT(DISTINCT product_id) AS observed_product_count FROM commerce.inventory WHERE snapshot_date=DATE '2022-12-31'"),
('inventory', "Count observed products at snapshot 2022-12-31 where category='__absent_category__'.", "SELECT COUNT(DISTINCT i.product_id) AS observed_product_count FROM commerce.inventory i JOIN commerce.products p ON p.product_id=i.product_id WHERE i.snapshot_date=DATE '2022-12-31' AND p.category='__absent_category__'"),
('inventory', 'Count observed products with stockout_flag=true by category at snapshot 2022-12-31.', "SELECT i.snapshot_date,p.category,COUNT(DISTINCT i.product_id) AS observed_product_count FROM commerce.inventory i JOIN commerce.products p ON p.product_id=i.product_id WHERE i.snapshot_date=DATE '2022-12-31' AND i.stockout_flag=TRUE GROUP BY i.snapshot_date,p.category ORDER BY i.snapshot_date,p.category LIMIT 200"),
('inventory', 'Show recorded reorder_flag for each product at snapshot 2022-12-31; include product_id.', "SELECT snapshot_date,product_id,reorder_flag FROM commerce.inventory WHERE snapshot_date=DATE '2022-12-31' ORDER BY snapshot_date,product_id LIMIT 200"),
('inventory', 'Show stock_on_hand history for product_id=1 in 2022, separately for each snapshot.', "SELECT snapshot_date,product_id,stock_on_hand FROM commerce.inventory WHERE product_id=1 AND snapshot_date>=DATE '2022-01-01' AND snapshot_date<DATE '2023-01-01' ORDER BY snapshot_date,product_id LIMIT 200"),
('inventory', 'Show units_sold by category for each exact snapshot in December 2022.', "SELECT i.snapshot_date,p.category,SUM(i.units_sold) AS inventory_units_sold FROM commerce.inventory i JOIN commerce.products p ON p.product_id=i.product_id WHERE i.snapshot_date>=DATE '2022-12-01' AND i.snapshot_date<DATE '2023-01-01' GROUP BY i.snapshot_date,p.category ORDER BY i.snapshot_date,p.category LIMIT 200"),
('inventory', 'Show stock_on_hand by color and size at snapshot 2022-12-31.', "SELECT i.snapshot_date,p.color,p.size,SUM(i.stock_on_hand) AS stock_on_hand FROM commerce.inventory i JOIN commerce.products p ON p.product_id=i.product_id WHERE i.snapshot_date=DATE '2022-12-31' GROUP BY i.snapshot_date,p.color,p.size ORDER BY i.snapshot_date,p.color,p.size LIMIT 200"),
('inventory', 'Show stock_on_hand at snapshot 1900-01-01 without substituting zero for missing observations.', "SELECT snapshot_date,SUM(stock_on_hand) AS stock_on_hand FROM commerce.inventory WHERE snapshot_date=DATE '1900-01-01' GROUP BY snapshot_date"),
('inventory', 'Show observed stock_on_hand per product at snapshot 2022-12-31 where stock_on_hand<10; include product_id.', "SELECT snapshot_date,product_id,stock_on_hand FROM commerce.inventory WHERE snapshot_date=DATE '2022-12-31' AND stock_on_hand<10 ORDER BY snapshot_date,product_id LIMIT 200"),
('inventory', 'Show mean stored sell_through_rate by category at snapshot 2022-12-31.', "SELECT i.snapshot_date,p.category,AVG(i.sell_through_rate) AS sell_through_rate FROM commerce.inventory i JOIN commerce.products p ON p.product_id=i.product_id WHERE i.snapshot_date=DATE '2022-12-31' GROUP BY i.snapshot_date,p.category ORDER BY i.snapshot_date,p.category LIMIT 200"),
('inventory', 'Show stock_on_hand by category at the latest available inventory snapshot.', "SELECT i.snapshot_date,p.category,SUM(i.stock_on_hand) AS stock_on_hand FROM commerce.inventory i JOIN commerce.products p ON p.product_id=i.product_id WHERE i.snapshot_date=(SELECT MAX(snapshot_date) FROM commerce.inventory) GROUP BY i.snapshot_date,p.category ORDER BY i.snapshot_date,p.category LIMIT 200"),
('inventory', 'Show total units_received for each separate exact snapshot in 2022.', "SELECT snapshot_date,SUM(units_received) AS units_received FROM commerce.inventory WHERE snapshot_date>=DATE '2022-01-01' AND snapshot_date<DATE '2023-01-01' GROUP BY snapshot_date ORDER BY snapshot_date LIMIT 200"),
('inventory', 'Count observed products by category and segment at snapshot 2022-11-30.', "SELECT i.snapshot_date,p.category,p.segment,COUNT(DISTINCT i.product_id) AS observed_product_count FROM commerce.inventory i JOIN commerce.products p ON p.product_id=i.product_id WHERE i.snapshot_date=DATE '2022-11-30' GROUP BY i.snapshot_date,p.category,p.segment ORDER BY i.snapshot_date,p.category,p.segment LIMIT 200"),
('inventory', 'Show stockout_days for each product at snapshot 2022-12-31; include product_id.', "SELECT snapshot_date,product_id,stockout_days FROM commerce.inventory WHERE snapshot_date=DATE '2022-12-31' ORDER BY snapshot_date,product_id LIMIT 200"),
('clarification', 'Which products have low stock at snapshot 2022-12-31?', None),
('clarification', 'What is the approved reorder quantity for each product?', None),
('clarification', 'Show safety stock by category.', None),
('clarification', 'Show stock_on_hand by warehouse at snapshot 2022-12-31.', None),
('clarification', 'Show current stock_on_hand today.', None),
('clarification', 'What is the combined annual total stock_on_hand across every snapshot in 2022?', None),
('clarification', 'What is the total units_received across all snapshots during 2022?', None),
('clarification', 'Show inventory turnover at snapshot 2022-12-31.', None),
('clarification', 'Show stock_on_hand at snapshot 2022-02-30.', None),
]

COMPARISON = """SELECT a.product_id,p.product_name,DATE '2022-11-30' AS before_date,DATE '2022-12-31' AS after_date,
 a.stock_on_hand AS stock_before,b.stock_on_hand AS stock_after,b.stock_on_hand-a.stock_on_hand AS stock_delta
 FROM commerce.inventory a JOIN commerce.inventory b ON a.product_id=b.product_id
 JOIN commerce.products p ON p.product_id=a.product_id
 WHERE a.snapshot_date=DATE '2022-11-30' AND b.snapshot_date=DATE '2022-12-31'
 ORDER BY a.product_id LIMIT 200"""
CASES += [
('comparison', 'How did stock_on_hand change between November 30 and December 31, 2022, for products present on both dates?', COMPARISON),
('comparison', 'Show the stock_on_hand difference between 2022-11-30 and 2022-12-31 for product_id=1, with product_name, using only products observed on both dates.', COMPARISON.replace('ORDER BY a.product_id', 'AND a.product_id=1 ORDER BY a.product_id')),
]

PARAPHRASES = {
1: 'Liệt kê mã sản phẩm và tên sản phẩm từ sản phẩm giới hạn 10.',
2: "Hãy hiển thị mã sản phẩm, màu sắc và giá từ sản phẩm với màu sắc='blue' sắp xếp theo giá giảm dần giới hạn 5.",
6: 'Hiển thị mã sản phẩm và giá từ sản phẩm với giá>=200000 và giá<500000 sắp xếp theo giá giảm dần giới hạn 8.',
16: 'Tổng stock_on_hand tại snapshot 2022-12-31 là bao nhiêu?',
17: 'Cho biết tồn kho theo danh mục tại snapshot 2022-12-31.',
19: 'Liệt kê 10 sản phẩm có tồn kho thấp nhất tại snapshot 2022-12-31, kèm product_id và product_name.',
22: 'Cho biết fill_rate trung bình theo category tại snapshot 2022-12-31.',
24: 'Tổng số lượng hàng nhập kho theo category tại snapshot 2022-12-31.',
27: "Count the observed inventory products in category='__absent_category__' at snapshot 2022-12-31.",
47: 'Tồn kho thay đổi thế nào giữa 30/11/2022 và 31/12/2022 cho các sản phẩm có mặt ở cả hai ngày? Kèm product_id và product_name.',
}


async def freeze():
    from dotenv import load_dotenv
    from core.database.commerce_repository import create_repository_from_env
    from evaluation.run_inventory_agents_benchmark import dumps, save
    load_dotenv(ROOT.parents[2]/'.env')
    if OUT.exists():
        raise RuntimeError('Frozen fixtures already exist; never overwrite them.')
    assert len(CASES) == 50, len(CASES)
    cases = [dict(id=f'I{i:02}', category=category, question=question,
        expected_behavior='Answer with approved inventory/product observations and preserve all explicit constraints; clarify ambiguous or unavailable definitions.')
        for i,(category,question,sql) in enumerate(CASES,1)]
    repo = await create_repository_from_env()
    refs = {}
    try:
        async with repo.pool.acquire() as conn:
            async with conn.transaction(readonly=True, isolation='repeatable_read'):
                await conn.execute("SET LOCAL statement_timeout='5000ms'")
                for case,(_,_,sql) in zip(cases, CASES):
                    rows = [dict(r) for r in await conn.fetch(sql)] if sql else None
                    refs[case['id']] = dict(supported=sql is not None, expected_behavior=case['expected_behavior'],
                        reference=dict(sql=sql, rows=rows, returned_rows=len(rows), detail_ceiling=200 if 'LIMIT 200' in sql else None) if sql else None)
    finally:
        await repo.close()
    for source, question in PARAPHRASES.items():
        key = f'P{source:02}'
        original = cases[source-1]
        cases.append(dict(original, id=key, question=question, paraphrase_of=original['id']))
        refs[key] = refs[original['id']]
    OUT.mkdir(parents=True)
    (OUT/'questions.jsonl').write_text(''.join(dumps(c)+'\n' for c in cases), encoding='utf-8', newline='\n')
    save(OUT/'references.json', json.loads(dumps(refs)))
    save(OUT/'manifest.json', dict(sql_ids=[c['id'] for c in cases], report_ids=['R01','R06','R16'],
        independent_intents=50, paraphrases=len(PARAPHRASES),
        oracle_status='Hand-authored SQL, author-reviewed only. No candidate compiler/model used. Self-join comparison gold runs only in evaluator read-only transaction.',
        hashes={name:hashlib.sha256((OUT/name).read_bytes()).hexdigest() for name in ['questions.jsonl','references.json']}))
    print('Frozen',len(cases),'cases before generation.')


if __name__ == '__main__':
    asyncio.run(freeze())
