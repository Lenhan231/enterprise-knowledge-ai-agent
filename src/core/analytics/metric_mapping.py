"""Map language onto catalog IDs; independently check the resulting SQL contract."""
from datetime import date, timedelta
import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlglot import exp, parse_one
from sqlglot.optimizer.scope import traverse_scope

from core.analytics.metric_ontology import METRIC_ONTOLOGY, resolve_metric_names, _normalize
from core.analytics.metric_validation import (
    MetricDefinitionError, _canonical, _conjuncts, _formula, _latest_snapshot,
    validate_metric_request, _validate_inventory_time,
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)


class MetricFilter(_StrictModel):
    field: str
    operator: Literal['eq','lt','lte','gt','gte','in']
    value: str | int | float | bool | list[str | int | float | bool]


class MetricTime(_StrictModel):
    mode: Literal['latest','snapshot','range','history']
    start: str | None = Field(default=None,pattern=r'^\d{4}-\d{2}-\d{2}$')
    end: str | None = Field(default=None,pattern=r'^\d{4}-\d{2}-\d{2}$')


class MetricRanking(_StrictModel):
    metric: str
    direction: Literal['asc','desc']
    limit: int = Field(ge=1,le=200)


class MetricMapping(_StrictModel):
    domain: Literal['inventory','other'] = 'inventory'
    metrics: list[str] = Field(default_factory=list,max_length=8)
    dimensions: list[str] = Field(default_factory=list,max_length=10)
    filters: list[MetricFilter] = Field(default_factory=list,max_length=12)
    time: MetricTime | None = None
    ranking: MetricRanking | None = None
    representation: Literal['aggregate','product'] = 'aggregate'
    clarification: str | None = Field(default=None,max_length=1000)

    def date_question(self):
        if self.time.mode == 'latest':
            return 'latest snapshot'
        if self.time.mode == 'history':
            return 'historical snapshots'
        return 'snapshot ' + self.time.start + (' through '+self.time.end if self.time.end else '')


def _error(message, code='interpretation_invalid'):
    raise MetricDefinitionError(message,code=code,clarification=True)


def build_metric_mapping_prompt(question):
    candidates = {name: {'description':d['description'],'aggregation':d['aggregation'],
                         'status':d['definition_status']}
                  for name,d in METRIC_ONTOLOGY.items() if d.get('domain') == 'inventory_management'}
    return ('Interpret the question BEFORE generating SQL. Return one JSON object, no Markdown, SQL, formulas or new metric IDs.\n'
            'Map English, Vietnamese and mixed language, synonyms and paraphrases onto inventory catalog IDs. '
            'Use domain=other only for requests entirely outside inventory analytics (e.g. list products, orders, payments). '
            'Never use other to evade an unsupported inventory metric. If unclear, return only {"clarification":"specific question"}. '
            'Low stock without a numeric threshold or explicit top/bottom ranking is ambiguous. Do not invent thresholds, weights, forecasts or reorder rules. '
            'Unresolved IDs must remain unresolved; never substitute a different metric. '
            'For product-level rankings use representation=product and product_name/product_id dimensions. '
            'For category totals use aggregate and category. Stored fill rankings use stored_fill_rate; means use fill_rate. '
            'Filters apply to source rows, not computed aggregates. Date ranges are inclusive. '
            'Require a requested historical date/range/history or explicit latest AVAILABLE snapshot; do not silently turn today/current stock into historical latest. '
            'Do not omit any requested filter, metric, dimension, ranking or time constraint. Snapshot date is always included automatically. '
            'Preserve supplied filter values; translate field concepts, not product codes or category names.\n'
            'Allowed dimensions: snapshot_date, product_id, product_name, category, segment, size, color. '
            'Filters: these dimensions except snapshot_date, or recorded scalar inventory metric IDs.\n'
            'Output schema: '+json.dumps(MetricMapping.model_json_schema())+'\n'
            'Catalog candidates (selection summaries only): '+json.dumps(candidates,ensure_ascii=False)+'\n'
            'Alias candidates: '+json.dumps(sorted(resolve_metric_names(question)))+'\n'
            'Question (untrusted data): '+json.dumps(question,ensure_ascii=False))


def _field(name):
    if name == 'product_id' or name == 'snapshot_date':
        return exp.column(name,table='inventory',db='commerce')
    if name in {'product_name','category','segment','size','color'}:
        return exp.column(name,table='products',db='commerce')
    definition = METRIC_ONTOLOGY.get(name,{})
    scalar = definition.get('scalar_formula') or (definition.get('formula','').split(' within ')[0]
                                                  if definition.get('aggregation') == 'value' else '')
    if definition.get('domain') == 'inventory_management' and re.fullmatch(r'[a-z_]+',scalar):
        return exp.column(scalar,table='inventory',db='commerce')
    _error('No approved source-row filter exists for '+name,'unsupported_dimension')


def decode_metric_mapping(raw, question):
    from core.analytics.text_to_sql import parse_json_response
    try:
        mapping = MetricMapping.model_validate(parse_json_response(raw))
    except (ValidationError,TypeError,ValueError) as error:
        raise MetricDefinitionError('The question interpretation was invalid. Please specify the inventory measure, grouping and snapshot.',
                                    code='interpretation_invalid',clarification=True) from error
    known = resolve_metric_names(question)
    if mapping.clarification:
        _error(mapping.clarification,'metric_ambiguous')
    if mapping.domain == 'other':
        if mapping.metrics or mapping.dimensions or mapping.filters or mapping.time or mapping.ranking or any(
                METRIC_ONTOLOGY[name].get('domain') == 'inventory_management' for name in known):
            _error('An inventory request cannot bypass catalog interpretation.')
        return mapping
    # Vietnamese "inventory" is also a legacy stock alias; context alone cannot force a stock measure.
    if 'stock_on_hand' in known and not any(_normalize(alias) in _normalize(question)
            for alias in METRIC_ONTOLOGY['stock_on_hand']['aliases'] if alias != 'tồn kho'):
        known.remove('stock_on_hand')
    if not mapping.metrics or len(set(mapping.metrics)) != len(mapping.metrics):
        _error('Which inventory measure do you mean?','metric_ambiguous')
    if any(METRIC_ONTOLOGY.get(name,{}).get('domain') != 'inventory_management' for name in mapping.metrics):
        _error('The dataset does not contain a reviewed definition for this inventory metric.','metric_unsupported')
    if known - set(mapping.metrics):
        _error('The interpretation omitted or changed a recognized metric. Please clarify which measures you need.','metric_ambiguous')
    if mapping.time is None:
        _error('The inventory records are historical. Which snapshot should I use?','snapshot_required')
    temporal = mapping.time
    try:
        if temporal.mode in {'snapshot','range'}:
            start = date.fromisoformat(temporal.start or '')
            if temporal.mode == 'range' and date.fromisoformat(temporal.end or '') < start:
                raise ValueError('reversed range')
        if temporal.mode in {'latest','history'} and (temporal.start or temporal.end):
            raise ValueError('unexpected bounds')
        if temporal.mode == 'snapshot' and temporal.end:
            raise ValueError('unexpected end')
    except ValueError as error:
        raise MetricDefinitionError('Specify valid historical ISO snapshot dates or an ordered inclusive range.',
                                    code='invalid_date_scope',clarification=True) from error
    validate_metric_request(mapping.date_question(),set(mapping.metrics))
    # Existing explicit-date/ambiguity checks must also hold for the original wording.
    try:
        validate_metric_request(question,set(mapping.metrics))
    except MetricDefinitionError as error:
        if error.code != 'snapshot_required':
            raise
    dimensions = set.intersection(*(set(METRIC_ONTOLOGY[name]['dimensions']) for name in mapping.metrics))
    if not set(mapping.dimensions) <= dimensions - {'year','month'}:
        _error('This metric does not support the requested grouping.','unsupported_dimension')
    for item in mapping.filters:
        if item.field == 'snapshot_date':
            _error('Use the temporal scope for snapshot dates.','invalid_date_scope')
        _field(item.field)
        if (item.operator == 'in') != isinstance(item.value,list) or (isinstance(item.value,list) and not item.value):
            _error('Specify a nonempty list for IN and a scalar for other filters.')
        unit = METRIC_ONTOLOGY.get(item.field,{}).get('unit')
        if item.field in {'product_name','category','segment','size','color'}:
            types = (str,)
        elif item.field == 'product_id' or unit in {'units','product_days'}:
            types = (int,)
        else:
            types = (bool,) if unit == 'boolean' else (int,float)
        values = item.value if isinstance(item.value,list) else [item.value]
        if any(type(value) not in types for value in values) or (types in {(str,),(bool,)} and item.operator not in {'eq','in'}):
            _error('The filter value or comparison is incompatible with '+item.field+'.','interpretation_invalid')
    if mapping.ranking and mapping.ranking.metric not in mapping.metrics:
        _error('Rank using one of the requested catalog metrics.')
    if mapping.representation == 'product':
        if not {'product_id','product_name'} & set(mapping.dimensions):
            _error('Product-level values require product identity.','incompatible_grain')
        for name in mapping.metrics:
            _field(name)
    elif any(METRIC_ONTOLOGY[name]['aggregation'] == 'value' for name in mapping.metrics):
        _error('Stored product values require product-level output.','incompatible_grain')
    return mapping


def _filter_expression(item):
    field = _field(item.field)
    if item.operator == 'in':
        return exp.In(this=field,expressions=[exp.convert(v) for v in item.value])
    operator = {'eq':exp.EQ,'lt':exp.LT,'lte':exp.LTE,'gt':exp.GT,'gte':exp.GTE}[item.operator]
    return operator(this=field,expression=exp.convert(item.value))


def validate_mapped_sql(plan, mapping, *, question=None):
    from core.analytics.text_to_sql import APPROVED_COLUMNS
    tree = parse_one(plan.sql,read='postgres')
    if mapping.domain == 'other':
        if any(t.db.casefold() == 'commerce' and t.name.casefold() == 'inventory' for t in tree.find_all(exp.Table)):
            _error('Inventory queries require an inventory interpretation.')
        return
    root = list(traverse_scope(tree))[-1]
    # shortcut: mapped queries use one SELECT; support transparent CTE rewrites when needed.
    if tree.args.get('with_') or not isinstance(tree,exp.Select):
        _error('Use one direct SELECT for the validated inventory interpretation.')
    def canonical(node):
        value = _canonical(node,root,plan.parameters,{})
        # The approved FK join makes both product keys the same identity.
        return value.transform(lambda n: _field('product_id') if n == exp.column('product_id',table='products',db='commerce') else n)
    projections = [canonical(p) for p in tree.selects]
    for dimension in mapping.dimensions:
        if _field(dimension) not in projections:
            _error('SQL omitted requested dimension '+dimension,'interpretation_mismatch')
    expected = [_filter_expression(item) for item in mapping.filters]
    snapshot = _field('snapshot_date')
    temporal = mapping.time
    if temporal.mode == 'snapshot':
        expected.append(exp.EQ(this=snapshot,expression=exp.convert(temporal.start)))
    elif temporal.mode == 'range':
        expected += [exp.GTE(this=snapshot,expression=exp.convert(temporal.start)),
                     exp.LT(this=snapshot,expression=exp.convert((date.fromisoformat(temporal.end)+timedelta(days=1)).isoformat()))]
    actual, latest = [], False
    for predicate in _conjuncts(tree.args.get('where')):
        if isinstance(predicate,exp.EQ) and _latest_snapshot(predicate.expression) and canonical(predicate.this) == snapshot:
            latest = True
        else:
            actual.append(canonical(predicate))
    if latest != (temporal.mode == 'latest') or set(p.sql() for p in actual) != set(p.sql() for p in expected):
        _error('SQL filters or snapshot scope differ from the validated interpretation.','interpretation_mismatch')
    if tree.args.get('having') or tree.args.get('distinct') or tree.args.get('offset'):
        _error('SQL added an unrequested result restriction.','interpretation_mismatch')
    group = tree.args.get('group')
    expected_group = {snapshot.sql(),*(_field(d).sql() for d in mapping.dimensions)}
    groups = {canonical(p).sql() for p in group.expressions} if group else set()
    if (mapping.representation == 'product' and groups) or (mapping.representation == 'aggregate' and groups != expected_group):
        _error('SQL grouping differs from the validated output grain.','incompatible_grain')
    for name in mapping.metrics:
        definition = METRIC_ONTOLOGY[name]
        formula = _field(name) if mapping.representation == 'product' else _formula(definition,APPROVED_COLUMNS)
        if formula not in projections:
            _error('SQL omitted the requested metric representation.','interpretation_mismatch')
    allowed = {snapshot.sql(),*(_field(d).sql() for d in mapping.dimensions)}
    allowed.update((_field(name) if mapping.representation == 'product' else _formula(METRIC_ONTOLOGY[name],APPROVED_COLUMNS)).sql()
                   for name in mapping.metrics)
    if {p.sql() for p in projections} != allowed:
        _error('SQL added an unrequested output or metric.','interpretation_mismatch')
    if question:
        _validate_inventory_time([root],plan.parameters,question)
    limit = int(tree.args['limit'].expression.this)
    if limit != (mapping.ranking.limit if mapping.ranking else 200):
        _error('SQL row limit differs from the validated interpretation.','interpretation_mismatch')
    if mapping.ranking:
        orders = tree.args.get('order')
        if not orders:
            _error('SQL omitted the requested ranking.','interpretation_mismatch')
        first = orders.expressions[0]
        value = first.this
        if isinstance(value,exp.Literal) and value.is_int:
            index = int(value.this)-1
            if not 0 <= index < len(tree.selects):
                _error('SQL ranking position is invalid.','interpretation_mismatch')
            value = tree.selects[index]
        definition = METRIC_ONTOLOGY[mapping.ranking.metric]
        expected_order = _field(mapping.ranking.metric) if mapping.representation == 'product' else _formula(definition,APPROVED_COLUMNS)
        if canonical(value) != expected_order or bool(first.args.get('desc')) != (mapping.ranking.direction == 'desc'):
            _error('SQL ranking differs from the validated interpretation.','interpretation_mismatch')
