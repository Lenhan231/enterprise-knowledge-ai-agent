"""Evaluation-only deterministic safeguards; never imported by production routing."""
import re

from sqlglot import exp, parse_one
from sqlglot.optimizer.scope import traverse_scope

from core.analytics.metric_mapping import requested_ranking_limit
from core.analytics.metric_ontology import get_metric_definition, resolve_metric_names
from core.analytics.metric_validation import (
    MetricDefinitionError, _canonical, _conjuncts, _formula, _latest_snapshot, _validate_inventory_time,
)
from core.analytics.text_to_sql import APPROVED_COLUMNS


def requested_metrics(question):
    metrics=resolve_metric_names(question)
    for name in list(metrics):
        definition=get_metric_definition(name)
        field=definition.get('formula','').split(' within ')[0]
        if (len(metrics)>1 and definition.get('unit')=='boolean' and re.fullmatch(r'[a-z_]+',field)
                and re.search(r'\b'+field+r'\s*=\s*(true|false)',question,re.I)):
            metrics.remove(name)
    if (len(metrics)==1 and re.search(r'how many|\bcount\b|number of|most.*products|bao nhiêu',question,re.I)
            and get_metric_definition(next(iter(metrics))).get('unit')=='boolean'):
        return {'observed_product_count'}
    return metrics


def validate_single_pass_plan(plan,question,metrics):
    """Keep explicit dates, bounds, NULL populations and field predicates independently of SQL generation."""
    tree=parse_one(plan.sql,read='postgres')
    scopes=list(traverse_scope(tree))
    root=scopes[-1]
    measures=APPROVED_COLUMNS['commerce.inventory']-{'snapshot_date','product_id','year','month'}
    if not metrics:
        for projection in tree.selects:
            value=_canonical(projection,root,plan.parameters,{})
            if not isinstance(value,exp.Column) and any(
                    c.table=='inventory' and c.name in measures for c in value.find_all(exp.Column)):
                raise MetricDefinitionError('Ordinary inventory fields cannot acquire unreviewed calculations.')
    for scope in scopes:
        for value in scope.expression.find_all(exp.Coalesce):
            if value.find_ancestor(exp.Select) is scope.expression:
                resolved=_canonical(value,scope,plan.parameters,{})
                if any(c.table=='inventory' and c.name in measures for c in resolved.find_all(exp.Column)):
                    raise MetricDefinitionError('Stored inventory values cannot acquire unapproved NULL substitution.')
    diagnostic=tree.copy()
    diagnostic.set('limit',None)
    if (any(t.db=='commerce' and t.name=='inventory' for t in tree.find_all(exp.Table))
            and not _latest_snapshot(exp.Subquery(this=diagnostic))):
        _validate_inventory_time(scopes,plan.parameters,question)
    predicates=[]
    for scope in scopes:
        for predicate in _conjuncts(scope.expression.args.get('where')):
            if (isinstance(predicate,exp.EQ) and isinstance(predicate.this,exp.Column)
                    and predicate.this.name=='snapshot_date' and _latest_snapshot(predicate.expression)):
                continue
            # EXISTS itself is validated by the existing approved-key and metric validators.
            if not predicate.find(exp.Exists):
                predicates.append(_canonical(predicate,scope,plan.parameters,{}))
    fields=set().union(*APPROVED_COLUMNS.values())-{'snapshot_date','order_date','return_date'}
    pattern=r'\b('+'|'.join(sorted(fields,key=len,reverse=True))+r')\s*(<=|>=|=|<|>)\s*(true|false|\d+(?:\.\d+)?|\x27[^\x27]+\x27|"[^"]+")'
    for field,operator,raw in re.findall(pattern,question,re.I):
        field=field.casefold()
        value=(raw.casefold()=='true') if raw.casefold() in {'true','false'} else (
            raw[1:-1] if raw[0] in {'\x27','"'} else float(raw) if '.' in raw else int(raw))
        kind={'=':exp.EQ,'<':exp.LT,'>':exp.GT,'<=':exp.LTE,'>=':exp.GTE}[operator]
        if not any(isinstance(p,kind) and isinstance(p.this,exp.Column) and p.this.name==field
                   and p.expression==exp.convert(value) for p in predicates):
            raise MetricDefinitionError('SQL omitted the explicit requested '+field+' predicate.')
    ids={int(value) for value in re.findall(r'\bproduct_id\s*(?:=|:)?\s*(\d+)\b',question,re.I)}
    if ids:
        filtered=set()
        for p in predicates:
            if isinstance(p,exp.EQ) and isinstance(p.this,exp.Column) and p.this.name=='product_id':
                filtered.add(p.expression.sql())
            if isinstance(p,exp.In) and isinstance(p.this,exp.Column) and p.this.name=='product_id':
                filtered.update(v.sql() for v in p.expressions)
        if filtered!={str(value) for value in ids}:
            raise MetricDefinitionError('SQL product identity scope differs from the explicit product IDs.')
    null_fields=[]
    if re.search(r'non[ -]?null|not null',question,re.I):
        for name in metrics:
            definition=get_metric_definition(name)
            field=definition.get('scalar_formula')
            if field and re.fullmatch(r'[a-z_]+',field):
                null_fields.append(field)
    for field in null_fields:
        if not any(isinstance(p,exp.Not) and isinstance(p.this,exp.Is)
                   and isinstance(p.this.this,exp.Column) and p.this.this.name==field
                   and isinstance(p.this.expression,exp.Null) for p in predicates):
            raise MetricDefinitionError('The requested non-NULL population is missing.')
    requested=requested_ranking_limit(question)
    scalar=(not tree.args.get('group') and any(p.find(exp.AggFunc) for p in tree.selects)
            and not any(p.find(exp.Window) for p in tree.selects))
    limit=int(tree.args['limit'].expression.this)
    if limit!=(requested or 200) and not (requested is None and scalar):
        raise MetricDefinitionError('A safety ceiling must not become an invented TOP-N.')
    if re.search(r'highest|lowest|greatest|fewest|\bmost\b(?!\s+recent)',question,re.I) and len(metrics)==1:
        definition=get_metric_definition(next(iter(metrics)))
        if definition.get('domain')=='inventory_management':
            expected=_formula(definition,APPROVED_COLUMNS)
            if not any(p.find(exp.AggFunc) for p in tree.selects):
                field=definition.get('scalar_formula') or definition.get('formula','').split(' within ')[0]
                expected=exp.column(field,table='inventory',db='commerce')
            orders=tree.args.get('order')
            if not orders:
                raise MetricDefinitionError('Requested inventory ranking is missing.')
            first=orders.expressions[0]
            value=first.this
            if isinstance(value,exp.Literal) and value.is_int and 1<=int(value.this)<=len(tree.selects):
                value=tree.selects[int(value.this)-1]
            descending=not bool(re.search(r'lowest|fewest',question,re.I))
            # NOT NULL declarations in the approved commerce inventory schema migration.
            not_null={'snapshot_date','product_id','year','month','stock_on_hand','units_received',
                      'units_sold','stockout_days','stockout_flag','overstock_flag','reorder_flag'}
            nullable=any(c.table=='inventory' and c.name not in not_null for c in expected.find_all(exp.Column))
            if (_canonical(value,root,plan.parameters,{})!=expected or bool(first.args.get('desc'))!=descending
                    or (nullable and first.args.get('nulls_first'))):
                raise MetricDefinitionError('Inventory ranking measure, direction or NULL order changed.')
