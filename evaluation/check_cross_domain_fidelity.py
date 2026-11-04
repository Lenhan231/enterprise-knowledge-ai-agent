"""Independent fixture execution and intent/policy sidecars; never rewrite Ragas scores."""
import argparse
from collections import defaultdict
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]


def adversaries(sql):
    a,b,c=sql['S23'],sql['S26'],sql['S27']
    return [
        ('S23','missing_product_identity',a.replace('SELECT ret.product_id,ret.returned_units','SELECT ret.returned_units').replace('ORDER BY 4','ORDER BY 3')),
        ('S23','wrong_denominator',a.replace('NULLIF(ord.ordered_units,0)','NULLIF(ret.returned_units,0)')),
        ('S23','zero_substitution',a.replace('NULLIF(ord.ordered_units,0)','COALESCE(ord.ordered_units,0)')),
        ('S23','unstable_ratio_ties',a.replace(',ret.product_id LIMIT',' LIMIT')),
        ('S23','wrong_return_period',a.replace("r.return_date<DATE '2023-01-01'","r.return_date<DATE '2024-01-01'")),
        ('S23','raw_multi_fact_join',"SELECT p.product_id, SUM(r.return_quantity) AS returned_units,SUM(oi.quantity) AS ordered_units, CAST(SUM(r.return_quantity) AS NUMERIC)/NULLIF(SUM(oi.quantity),0) AS ratio FROM commerce.products p JOIN commerce.returns r ON r.product_id=p.product_id JOIN commerce.order_items oi ON oi.product_id=p.product_id JOIN commerce.orders o ON oi.order_id=o.order_id WHERE r.return_date>=DATE '2022-01-01' AND r.return_date<DATE '2023-01-01' AND o.order_date>=DATE '2022-01-01' AND o.order_date<DATE '2023-01-01' GROUP BY p.product_id ORDER BY 4 DESC NULLS LAST,p.product_id LIMIT 200"),
        ('S26','uncorrelated_existence',b.replace('oi.product_id=p.product_id AND ','')),
        ('S26','wrong_product_existence',b.replace('oi.product_id=p.product_id','oi.product_id=1')),
        ('S26','hidden_order_status',b.replace("AND o.order_date<DATE '2023-01-01'","AND o.order_date<DATE '2023-01-01' AND o.order_status='completed'")),
        ('S26','hidden_inventory_category',b.replace('AND i.stockout_flag=TRUE',"AND i.stockout_flag=TRUE AND p.category='A'")),
        ('S26','wrong_flag',b.replace('i.stockout_flag=TRUE','i.stockout_flag=FALSE')),
        ('S26','unstable_observation_ties',b.replace('ORDER BY i.snapshot_date,i.product_id','ORDER BY i.product_id')),
        ('S26','invented_top_n',b.replace('LIMIT 200','LIMIT 1')),
        ('S27','same_side_category_key',c.replace('COALESCE(inv.category,ord.category)','COALESCE(inv.category,inv.category)')),
        ('S27','lost_one_sided_categories',c.replace('FULL JOIN','INNER JOIN')),
        ('S27','zero_substitution',c.replace('inv.inventory_units_sold,ord.ordered_units','COALESCE(inv.inventory_units_sold,0),ord.ordered_units')),
        ('S27','truncated_source_aggregate',c.replace('GROUP BY p.category),','GROUP BY p.category LIMIT 1),')),
        ('S27','unstable_category_order',c.replace('ORDER BY 1','')),
        ('S27','invented_top_n',c.replace('LIMIT 200','LIMIT 1')),
    ]


def independent_expected(db):
    products={pid:category for pid,category in db.execute('SELECT product_id,category FROM commerce.products')}
    orders={oid:(when,status) for oid,when,status in db.execute('SELECT * FROM commerce.orders')}
    annual,monthly,returned=defaultdict(int),defaultdict(int),defaultdict(int)
    for _,oid,pid,qty in db.execute('SELECT * FROM commerce.order_items'):
        when=orders[oid][0]
        if '2022-01-01'<=when<'2023-01-01':annual[pid]+=qty
        if '2022-12-01'<=when<'2023-01-01':monthly[pid]+=qty
    for _,oid,pid,when,qty in db.execute('SELECT * FROM commerce.returns'):
        if '2022-01-01'<=when<'2023-01-01':returned[pid]+=qty
    ratio=sorted([(pid,n,annual[pid],float(Decimal(n)/Decimal(annual[pid])))
                  for pid,n in returned.items() if pid in annual],key=lambda r:(-r[3],r[0]))
    inv,ord_cat=defaultdict(int),defaultdict(int);presence=[]
    for when,pid,qty,flag in db.execute('SELECT * FROM commerce.inventory'):
        if '2022-12-01'<=when<'2023-01-01':
            inv[products[pid]]+=qty
            if flag and pid in monthly:presence.append((when,pid))
    for pid,qty in monthly.items():ord_cat[products[pid]]+=qty
    categories=[(cat,inv.get(cat),ord_cat.get(cat)) for cat in sorted(inv.keys()|ord_cat.keys())]
    return {'S23':ratio,'S26':sorted(presence),'S27':categories}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--application',type=Path,default=ROOT)
    parser.add_argument('--generations',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();work=args.application.resolve()
    os.environ['SQL_CROSS_DOMAIN_ROOT']=str(work)
    sys.path[:0]=[str(work),str(work/'src'),str(ROOT/'tests')]
    import test_sql_cross_domain_fidelity as fixtures
    from sqlglot import parse_one,exp
    results=[]
    for key,name,sql in adversaries(fixtures.SQL):
        try:
            fixtures.validate(key,sql);blocked=False;reason=None
        except (fixtures.MetricDefinitionError,ValueError) as error:
            blocked=True;reason=str(error)
        results.append(dict(case=key,mutation=name,blocked=blocked,reason=reason))
    data=dict(method='Supplemental checks only; frozen scores untouched.',adversarial_rejection=dict(
        blocked=sum(r['blocked'] for r in results),total=len(results)),adversaries=results,
        fixture_sha256=hashlib.sha256((ROOT/'tests/test_sql_cross_domain_fidelity.py').read_bytes()).hexdigest())
    if args.generations:
        observed={r['id']:r for r in map(json.loads,args.generations.read_text(encoding='utf-8').splitlines())}
        checks=[]
        with fixtures.fixture() as db:
            expected=independent_expected(db)
            for key,row in observed.items():
                raw=row['result']['data'];tree=parse_one(raw['sql'],read='postgres');params=raw.get('parameters',[])
                tree=tree.transform(lambda n:exp.convert(params[int(n.this.this)-1]) if isinstance(n,exp.Parameter) else n)
                rows=fixtures.execute_fixture(db,tree.sql(dialect='postgres'))
                if key=='S23':
                    ratio=next(p.alias_or_name for p in tree.selects if p.find(exp.Div))
                    values=[(r['product_id'],r['returned_units'],r['ordered_units'],r[ratio]) for r in rows]
                elif key=='S26':values=[(r['snapshot_date'],r['product_id']) for r in rows]
                else:
                    order_name=next(k for k in rows[0] if k.startswith('ordered_'))
                    values=[(r['category'],r['inventory_units_sold'],r[order_name]) for r in rows]
                matches=sorted(values,key=json.dumps)==sorted(expected[key],key=json.dumps)
                if key=='S23':
                    matches=matches and [r[3] for r in values]==sorted([r[3] for r in values],reverse=True)
                checks.append(dict(case=key,fixture_calculation='pass' if matches else 'fail',
                    intent_fidelity=('uncertain' if key=='S26' else 'pass') if matches else 'fail',
                    business_rule_compliance=('uncertain' if key=='S27' else 'pass') if matches else 'fail',
                    reason={'S23':'Explicit derived unit ratio, not canonical return_rate. Extra product-name enrichment is allowed.',
                            'S26':'Per-snapshot observations match the contract; a unique-product roster versus observation rows remains an output-grain decision.',
                            'S27':'Explicit observation sum is computed correctly; cross-snapshot business approval is not established by the per-snapshot catalog.'}[key],
                    actual=values,expected=expected[key]))
        data['intent_and_business_checks']=checks
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(data,indent=2),encoding='utf-8',newline='\n')
    print(data['adversarial_rejection'])


if __name__=='__main__':main()
