"""Bounded single-source counts compiled from data, never model-provided SQL."""
from datetime import date, timedelta
import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlglot import exp, parse_one

from core.agents.sql.metric_validation import MetricDefinitionError, inventory_time_scope
from core.agents.sql.metric_ontology import METRIC_ONTOLOGY
from core.agents.sql.sql_validation import APPROVED_DATE_COLUMNS, decode_query_plan


class StrictCountModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)


class CountFilter(StrictCountModel):
    field: str = Field(pattern=r'^[a-z][a-z0-9_]{0,62}$')
    operator: Literal['eq', 'lt', 'lte', 'gt', 'gte', 'in', 'is_null', 'is_not_null']
    value: str | int | float | bool | list[str | int | float | bool] | None = None

    @model_validator(mode='after')
    def check_value(self):
        if self.operator in {'is_null', 'is_not_null'}:
            valid = self.value is None
        elif self.operator == 'in':
            valid = isinstance(self.value, list) and 1 <= len(self.value) <= 50
        else:
            valid = self.value is not None and not isinstance(self.value, list)
        if not valid:
            raise ValueError('Use explicit NULL operators, a nonempty IN list, or a scalar comparison value.')
        if self.operator in {'lt', 'lte', 'gt', 'gte'} and type(self.value) is bool:
            raise ValueError('Boolean conditions use equality, not numeric ordering.')
        return self


class CountMeasure(StrictCountModel):
    alias: str = Field(pattern=r'^[a-z][a-z0-9_]{0,62}$')
    kind: Literal['rows', 'nonnull', 'distinct']
    field: str | None = Field(default=None, pattern=r'^[a-z][a-z0-9_]{0,62}$')
    filters: list[CountFilter] = Field(default_factory=list, max_length=12)

    @model_validator(mode='after')
    def check_target(self):
        if (self.kind == 'rows') != (self.field is None):
            raise ValueError('rows counts records without a field; nonnull/distinct require an explicit field.')
        return self


class CountTime(StrictCountModel):
    mode: Literal['all', 'latest', 'snapshot', 'range', 'history']
    field: str | None = None
    start: str | None = None
    end: str | None = None


class CountQuery(StrictCountModel):
    source: str = Field(pattern=r'^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$')
    counts: list[CountMeasure] = Field(min_length=1, max_length=8)
    dimensions: list[str] = Field(default_factory=list, max_length=4)
    filters: list[CountFilter] = Field(default_factory=list, max_length=12)
    time: CountTime


def reject(message):
    raise MetricDefinitionError(message, code='count_plan_invalid')


def compile_count_query(raw, table_columns, question, date_columns=None):
    """Return a checked QueryPlan, count metadata and its validated input contract."""
    if isinstance(raw, dict) and set(raw) & {'joins', 'having', 'windows', 'expressions'}:
        raise MetricDefinitionError('The count workflow supports one source table without joins or window calculations. Count records from one source, or use a separately validated SQL query for joined data.', code='count_unsupported')
    try:
        spec = CountQuery.model_validate(raw).model_copy(deep=True)
    except (ValidationError, TypeError, ValueError) as error:
        details = '; '.join('.'.join(map(str, item['loc'])) + ': ' + item['msg']
                            for item in error.errors(include_input=False, include_url=False)[:3]) if isinstance(error, ValidationError) else 'Expected a count_query object.'
        raise MetricDefinitionError('Invalid generated count plan: ' + details[:600],
                                    code='count_plan_invalid') from error
    columns = table_columns.get(spec.source)
    if not columns:
        reject('The count source is not in the approved database schema.')
    named = set(re.findall(r'\bcommerce\.\w+', question))
    if named - {spec.source}:
        reject('A count query must retain its explicitly requested source. Joined counts need a separately validated query.')
    aliases = [item.alias for item in spec.counts]
    if len(set(aliases)) != len(aliases) or len(set(spec.dimensions)) != len(spec.dimensions):
        reject('Count aliases and grouping fields must be unique.')
    for item in spec.counts:
        canonical = METRIC_ONTOLOGY.get(item.alias)
        if canonical:
            identity = re.search(r'COUNT\s*\(\s*DISTINCT\s+([a-z_]+)', canonical.get('formula') or '', re.I)
            sources = re.findall(r'commerce\.\w+', canonical.get('source', ''))
            if (canonical.get('aggregation') != 'count_distinct' or not identity
                    or item.kind != 'distinct' or item.field != identity[1]
                    or not sources or spec.source != sources[0]):
                reject('A count alias cannot redefine the canonical metric ' + item.alias + '.')
    fields = {*spec.dimensions, *(item.field for item in spec.counts if item.field),
              *(f.field for f in spec.filters), *(f.field for item in spec.counts for f in item.filters)}
    if not fields <= set(columns):
        reject('Unknown source fields: ' + ', '.join(sorted(fields - set(columns))) + '. Use recorded column names, not metric IDs.')
    temporal = spec.time
    dated = APPROVED_DATE_COLUMNS | set(date_columns or ())
    if temporal.mode != 'all' and not temporal.field:
        candidates = sorted(field for source, field in dated if source == spec.source and field in columns)
        if len(candidates) == 1:
            temporal.field = candidates[0]
        elif candidates:
            raise MetricDefinitionError('Which date field should define the count period: ' + ', '.join(candidates) + '?',
                                        code='count_time_field_required', clarification=True)
        else:
            raise MetricDefinitionError('This source has no approved date field for time-scoped counts. Choose an undated count or a source with recorded dates.', code='count_unsupported')
    if temporal.mode != 'all' and (spec.source, temporal.field) not in dated:
        reject('The count time scope needs an approved date field from its source.')
    expected = inventory_time_scope(question)
    latest = bool(re.search(r'\blatest\b|\bmost recent\b|mới nhất|gần nhất', question, re.I))
    try:
        start = date.fromisoformat(temporal.start) if temporal.start else None
        end = date.fromisoformat(temporal.end) if temporal.end else None
    except ValueError as error:
        raise MetricDefinitionError('The generated count plan contains an invalid date.', code='count_plan_invalid') from error
    if (temporal.mode == 'snapshot' and (not start or end)
            or temporal.mode == 'range' and (not start or not end or end < start)
            or temporal.mode in {'all', 'history'} and (start or end)
            or temporal.mode == 'latest' and (bool(start) != bool(end) or start and end < start)
            or temporal.mode == 'all' and temporal.field):
        reject('The count plan has inconsistent date boundaries.')
    bounded_latest = temporal.mode == 'latest' and start is not None
    matches_period = ((temporal.start, temporal.end) == (expected[1], expected[2] or expected[1])
                      if expected and bounded_latest else (temporal.mode, temporal.start, temporal.end) == expected)
    if expected and not matches_period:
        reject('The count plan changed or omitted the requested historical period.')
    if latest and temporal.mode != 'latest':
        reject('The count plan must use the latest available observation, not all dates or a guessed snapshot.')
    if bounded_latest and not expected:
        reject('The count plan introduced an unrequested historical window for the latest observation.')
    if not expected and not latest and temporal.mode in {'snapshot', 'range', 'latest'}:
        reject('The count plan introduced an unrequested date restriction.')
    inventory = spec.source == 'commerce.inventory'
    if inventory and temporal.mode == 'all':
        raise MetricDefinitionError('Which inventory snapshot should I count: the latest available snapshot, a specific date, or separate historical snapshots?',
                                    code='snapshot_required', clarification=not (expected or latest))
    if any(f.field == temporal.field for f in spec.filters):
        reject('Use the shared time scope instead of a hidden date filter.')
    dimensions = list(spec.dimensions)
    if inventory and temporal.mode in {'range', 'history'} and temporal.field not in dimensions:
        dimensions.insert(0, temporal.field)
    if set(aliases) & (set(dimensions) | ({'snapshot_date'} if inventory else set())):
        reject('Count aliases cannot replace dimensions or the inventory snapshot label.')
    table = spec.source.split('.')[1]
    column = lambda field: exp.column(field, table=table)

    def condition(item):
        left = column(item.field)
        if item.operator in {'is_null', 'is_not_null'}:
            value = exp.Is(this=left, expression=exp.Null())
            return exp.Not(this=value) if item.operator == 'is_not_null' else value
        if item.operator == 'in':
            return exp.In(this=left, expressions=[exp.convert(value) for value in item.value])
        operator = {'eq': exp.EQ, 'lt': exp.LT, 'lte': exp.LTE, 'gt': exp.GT, 'gte': exp.GTE}[item.operator]
        return operator(this=left, expression=exp.convert(item.value))

    projections = [column(field).as_(field) for field in dimensions]

    def date_bounds(alias):
        return (exp.GTE(this=exp.column(temporal.field, table=alias), expression=exp.convert(start.isoformat())),
                exp.LT(this=exp.column(temporal.field, table=alias), expression=exp.convert(((end or start) + timedelta(days=1)).isoformat())))

    maximum = None
    if temporal.mode == 'latest':
        last = exp.select(exp.Max(this=exp.column(temporal.field, table='latest'))).from_(exp.to_table(spec.source).as_('latest'))
        if bounded_latest:
            last = last.where(*date_bounds('latest'))
        maximum = last.subquery()
    if inventory and temporal.mode in {'latest', 'snapshot'} and 'snapshot_date' not in dimensions:
        snapshot = maximum.copy() if maximum is not None else exp.Cast(this=exp.convert(temporal.start), to=exp.DataType.build('DATE'))
        projections.insert(0, snapshot.as_('snapshot_date'))
    definitions = {}
    for item in spec.counts:
        target = exp.Star() if item.kind == 'rows' else column(item.field)
        if item.kind == 'distinct':
            target = exp.Distinct(expressions=[target])
        value = exp.Count(this=target)
        if item.filters:
            value = exp.Filter(this=value, expression=exp.Where(this=exp.and_(*(condition(f) for f in item.filters))))
        projections.append(value.as_(item.alias))
        definitions[item.alias] = {'source': spec.source, 'source_columns': {spec.source: sorted(fields)},
            'unit': 'count', 'aggregation': 'count_distinct' if item.kind == 'distinct' else 'count',
            'formula': value.sql(dialect='postgres'), 'count_kind': item.kind, 'count_field': item.field,
            'limitations': ['Counts describe recorded source rows. DISTINCT excludes NULL identities; NULL flags match neither true nor false. No joins are used.']}
    query = exp.select(*projections).from_(exp.to_table(spec.source).as_(table))
    for item in spec.filters:
        query = query.where(condition(item))
    if temporal.mode == 'latest':
        query = query.where(exp.EQ(this=column(temporal.field), expression=maximum))
        if bounded_latest:
            query = query.where(*date_bounds(table))
    elif temporal.mode in {'snapshot', 'range'}:
        query = query.where(*date_bounds(table))
    if dimensions:
        query = query.group_by(*(column(field) for field in dimensions)).order_by(*(column(field) for field in dimensions))
    query = query.limit(200 if dimensions else 1)
    parameters = []

    def bind(node):
        if isinstance(node, exp.Literal) and not isinstance(node.parent, exp.Limit):
            parameters.append(node.this if node.is_string else json.loads(node.this))
            return exp.Parameter(this=exp.Var(this=str(len(parameters))))
        return node

    sql = query.transform(bind).sql(dialect='postgres')
    plan = decode_query_plan(json.dumps({'sql': sql, 'parameters': parameters, 'explanation': 'Compiled from a validated single-source count contract.'}),
        schema_columns=table_columns, allowed_sources=set(table_columns), date_columns=date_columns)
    return plan, definitions, spec


COUNT_QUERY_INSTRUCTIONS = '''
For single-source requests consisting of counts (rows, distinct entities, or non-NULL recorded values), prefer a
count_query compiled by the server instead of generating SQL. Return {"count_query": {...}, "outputs": [...]}.
count_query has source (one approved schema.table), counts (one to eight {alias, kind: rows|distinct|nonnull,
field: null for rows or an actual source column, filters: [{field, operator, value}]}), dimensions: [],
filters: [] (shared population only), and time: {mode: all|latest|snapshot|range|history, field: source date
column or null, start: ISO date or null, end: inclusive ISO date or null}. All field names are source
columns, never metric IDs. Filter operators: eq, lt, lte, gt, gte, in, is_null, is_not_null.
When counting entities, EVERY conditional counter must count the SAME DISTINCT identity field as the
unfiltered entity counter. Put the flag only in filters, NEVER in the counted field. Counting a non-NULL
flag value counts records, not distinct entities. SKU/product counts in inventory use distinct product_id;
flagged SKU counts ALSO use distinct product_id with that recorded flag equal to true.
Each count owns its filters: never intersect separate count conditions
in shared filters. NULL is unknown, not false. rows counts records including duplicates; nonnull counts
non-NULL field occurrences; distinct excludes duplicates and NULL. Do not substitute SUM for counts or
COUNT for a requested SUM (e.g. total sessions). Use one count_query for multiple compatible counts.
Use the latest snapshot for all counters, unfiltered by count/population predicates. If the user adds
a period to a latest-snapshot request, retain mode=latest and set start/end to that inclusive window;
the server selects the latest snapshot WITHIN that period, not every snapshot in the range.
With one approved date field, use it without asking the user; if omitted the server resolves it.
Inventory ranges/history requested without latest keep separate snapshot groups.
The count compiler supports one source and raw grouping columns only, without joins or expressions.
For monthly/date-bucket counts or counts needing approved joins, use the existing SQL response schema
and its existing safety checks instead of forcing the request into count_query.
Ask a specific business question
only for genuinely missing count targets or time scope. Unsupported joins need a clear limitation.
For dashboards declare a separate KPI output per overall count, using count aliases, query: 0,
dimension: null and group_by: []. For grouped counts choose a supported chart or table. Do not return
metrics/domain/representation or SQL alongside count_query. Existing non-count requests keep their
existing response schema. Aliases must be unique plain column names. Dates/filters are shared only
when the user requested a shared population; conditions on individual counts stay on those counts.
'''


def validate_count_period(plan, question, sources, date_columns):
    """Prove explicit bounds independently from the latest-snapshot equality."""
    from core.agents.sql.metric_validation import _conjuncts, validate_independent_query_period
    tree = parse_one(plan.sql, read='postgres')
    for where in list(tree.find_all(exp.Where)):
        bounds = [item.copy() for item in _conjuncts(where.this) if not item.find(exp.Subquery)]
        if bounds:
            where.set('this', exp.and_(*bounds))
        else:
            where.parent.set('where', None)
    validate_independent_query_period(tree.sql(dialect='postgres'), plan.parameters, question, sources, date_columns)
