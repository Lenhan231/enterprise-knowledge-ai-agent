"""Evaluation-only direct-field eligibility and an independent SQL intent contract."""
from decimal import Context, Decimal
import re

from sqlglot import exp, parse
from sqlglot.optimizer.scope import traverse_scope

from core.analytics.join_validation import PRIMARY_KEYS
from core.analytics.metric_validation import MetricDefinitionError, _canonical, _conjuncts
from core.analytics.text_to_sql import APPROVED_COLUMNS, MAX_RESULT_ROWS, validate_commerce_sql


def _reject(message,*,clarification=True):
    raise MetricDefinitionError(message,code='field_contract_mismatch',clarification=clarification)


def field_contract(question):
    """Recognize a complete literal field request; all other requests retain production behavior."""
    # shortcut: explicit field names and SQL-style clauses only; broaden after independent intent tests.
    match=re.fullmatch(r'(?:list|show|retrieve)\s+(?:recorded\s+)?([a-z_]+(?:(?:\s*,\s*|\s+and\s+)[a-z_]+)*)'
        r'\s+from\s+(?:commerce\.)?(inventory|products)(.*)',question.strip().removesuffix('.'),re.I|re.S)
    if not match:
        return None
    fields=re.split(r'\s*,\s*|\s+and\s+',match[1].lower())
    table=match[2].lower()
    if table=='inventory' and any(f not in {'snapshot_date','product_id','year','month'} for f in fields):
        return None  # Inventory measures retain canonical mapping and deterministic compilation.
    if len(set(fields))!=len(fields) or not set(fields)<=APPROVED_COLUMNS['commerce.'+table]:
        _reject('Use unique approved raw field names for this table.')
    if match[3].strip() and not re.match(r'\s*(where\b|order\s+by\b|limit\b)',match[3],re.I):
        _reject('Use explicit WHERE, ORDER BY and LIMIT clauses for a direct field request.')
    try:
        statements=parse('SELECT '+','.join(fields)+' FROM commerce.'+table+match[3],read='postgres')
    except Exception as error:
        raise MetricDefinitionError('The field request has invalid clauses.',clarification=True) from error
    if len(statements)!=1 or not isinstance(statements[0],exp.Select):
        _reject('A field request must describe one read-only table retrieval.')
    tree=statements[0]
    if any(node.comments for node in tree.walk()):
        _reject('Comments cannot hide additional constraints in a direct field request.')
    if any(tree.args.get(key) for key in ('joins','with_','group','having','distinct','qualify','offset','locks')):
        _reject('Direct field retrieval supports one table, literal filters and field ordering only.')
    if any(not isinstance(p,exp.Column) for p in tree.selects):
        _reject('Direct retrieval cannot replace raw fields with calculations.')
    for column in tree.find_all(exp.Column):
        if column.table not in {'',table} or column.db not in {'','commerce'} or column.name.lower() not in APPROVED_COLUMNS['commerce.'+table]:
            _reject('A field or filter refers to an unsupported source.')
        if table=='inventory' and column.name.lower() not in {'snapshot_date','product_id','year','month'}:
            return None
        column.set('this',exp.to_identifier(column.name.lower()))
        column.set('table',exp.to_identifier(table))
        column.set('db',None)
    def literal(value):
        return (isinstance(value,(exp.Literal,exp.Boolean,exp.Null)) or
                isinstance(value,exp.Neg) and isinstance(value.this,exp.Literal) and not value.this.is_string or
                isinstance(value,exp.Cast) and value.to.this==exp.DataType.Type.DATE and isinstance(value.this,exp.Literal))
    for predicate in _conjuncts(tree.args.get('where')):
        value=predicate.this if isinstance(predicate,exp.Not) else predicate
        if not isinstance(value,(exp.EQ,exp.NEQ,exp.GT,exp.GTE,exp.LT,exp.LTE,exp.In,exp.Is)) or not isinstance(value.this,exp.Column):
            _reject('Use AND-connected field comparisons, literal IN lists or NULL checks.')
        values=value.expressions if isinstance(value,exp.In) else [value.expression]
        if not values or not all(literal(v) for v in values):
            _reject('Field filters require explicit literal values, not expressions or subqueries.')
    orders=tree.args.get('order')
    if orders and any(not isinstance(o.this,exp.Column) for o in orders.expressions):
        _reject('Rank raw fields directly; expressions are outside direct retrieval.')
    present={o.this.name for o in orders.expressions} if orders else set()
    stable=[exp.Ordered(this=exp.column(k,table=table),desc=False) for k in sorted(PRIMARY_KEYS[table]-present)]
    tree.set('order',exp.Order(expressions=[*(orders.expressions if orders else []),*stable]))
    if not tree.args.get('limit'):
        tree.limit(MAX_RESULT_ROWS,copy=False)
    for value in tree.find_all(exp.Literal):
        if not value.is_string and abs(Decimal(value.this).adjusted())>1000:
            _reject('Use finite numeric filter values within the existing report magnitude bound.')
    try:
        validate_commerce_sql(tree.sql(dialect='postgres'))
    except ValueError as error:
        raise MetricDefinitionError(str(error),clarification=True) from error
    return tree


def validate_field_sql(plan,expected):
    """The generated query may vary syntax, but not the independently parsed request."""
    actual=exp.maybe_parse(plan.sql,dialect='postgres')
    table=expected.args['from_'].this.name
    scopes=list(traverse_scope(actual))
    if (len(scopes)!=1 or len(scopes[0].selected_sources)!=1 or
            any(actual.args.get(k) for k in ('joins','with_','group','having','distinct','qualify','offset','locks'))):
        _reject('Generated SQL changed the one-table raw-field population.',clarification=False)
    source=next(iter(scopes[0].selected_sources.values()))[1]
    if not isinstance(source,exp.Table) or source.db.casefold()!='commerce' or source.name.casefold()!=table:
        _reject('Generated SQL changed the requested source.',clarification=False)
    reference_scope=list(traverse_scope(expected))[-1]
    def canonical(node,scope,parameters):
        value=_canonical(node,scope,parameters,{})
        def normalize(n):
            if isinstance(n,exp.Literal) and not n.is_string:
                number=Decimal(n.this)
                if not number.is_finite() or abs(number.adjusted())>1000:
                    _reject('Generated SQL has an out-of-bound numeric literal.',clarification=False)
                return exp.Literal.number(format(number.normalize(Context(prec=max(28,len(number.as_tuple().digits)))),'f'))
            if isinstance(n,exp.Not) and isinstance(n.this,exp.Is):
                result=n.this.copy();result.set('negate',not bool(result.args.get('negate')));return result
            reverse={exp.EQ:exp.EQ,exp.NEQ:exp.NEQ,exp.LT:exp.GT,exp.LTE:exp.GTE,exp.GT:exp.LT,exp.GTE:exp.LTE}
            if type(n) in reverse and isinstance(n.expression,exp.Column) and not isinstance(n.this,exp.Column):
                return reverse[type(n)](this=n.expression.copy(),expression=n.this.copy())
            if isinstance(n,exp.In):
                result=n.copy();result.set('expressions',sorted(result.expressions,key=lambda v:v.sql()));return result
            return n
        return value.transform(normalize)
    a=lambda n:canonical(n,scopes[0],plan.parameters)
    e=lambda n:canonical(n,reference_scope,())
    if ([a(p) for p in actual.selects]!=[e(p) for p in expected.selects] or
            [p.alias_or_name.lower() for p in actual.selects]!=[p.name for p in expected.selects]):
        _reject('Generated SQL changed or omitted requested fields or their output names.',clarification=False)
    filters=lambda tree,fn:sorted(fn(p).sql() for p in _conjuncts(tree.args.get('where')))
    if filters(actual,a)!=filters(expected,e):
        _reject('Generated SQL changed, omitted or added a requested filter/date.',clarification=False)
    def ordered(tree,fn):
        values=[]
        for order in (tree.args['order'].expressions if tree.args.get('order') else []):
            value=order.this
            if isinstance(value,exp.Literal) and value.is_int and 1<=int(value.this)<=len(tree.selects):
                value=tree.selects[int(value.this)-1]
            column=fn(value)
            nullable=table=='products' and isinstance(column,exp.Column) and column.name in {'color','size','segment'}
            values.append((column.sql(),bool(order.args.get('desc')),bool(order.args.get('nulls_first')) if nullable else None))
        return values
    if (ordered(actual,a)!=ordered(expected,e) or not actual.args.get('limit') or
            int(actual.args['limit'].expression.this)!=int(expected.args['limit'].expression.this)):
        _reject('Generated SQL changed the requested ranking, stable ordering or row bound.',clarification=False)
