"""Bounded provider response contracts for dashboard SQL generation."""
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from copy import deepcopy
from sqlglot import exp, parse
from sqlglot.errors import ParseError, TokenError

from core.agents.sql.counting import CountQuery
from core.agents.sql.metric_mapping import MetricMapping
from core.agents.dashboard.models import DashboardOutput, MAX_DATASETS

SYSTEM_RULES = (
    'You are a dashboard data planner. Follow the approved data rules and JSON schema. '
    'Return every requested representation. Reuse a dataset when source set, grain and filters match. '
    f'You may return up to {MAX_DATASETS} independent SQL datasets in one response. '
    'Allocate a separate dataset for each independent fact source and requested grain. '
    'Independent charts from different fact sources MUST use independent datasets, even at the same time grain. '
    'Never join independent chart sources together, including through monthly CTEs. '
    'Include only requested outputs. Monthly or category measures alone do not request overall KPI tiles. '
    'An explicitly requested overall total is a scalar KPI unless the user specifies another representation. '
    'Descriptive statistics are computed from returned observations by the renderer; do not query them separately. '
    'An underlying observation table reuses the chart dataset unless raw source records are explicitly requested. '
    'Do not ask to confirm supplied chart types, measures, columns or time scope. '
    'Write dataset questions, explanations and clarification in the language of the original user request. '
    'Ask a focused business clarification only when required information is genuinely missing.'
)


class ResponseModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Dataset(ResponseModel):
    question: str
    sql: str
    parameters: list[str | int | float | bool | None]
    explanation: str


class ChartOutput(DashboardOutput):
    kind: Literal['line', 'bar', 'donut']
    dimension: str
    measures: list[str] = Field(min_length=1, max_length=4)
    group_by: list[str] = Field(max_length=0)


class KPIOutput(DashboardOutput):
    kind: Literal['kpi']
    dimension: None
    measures: list[str] = Field(min_length=1, max_length=1)
    group_by: list[str] = Field(max_length=0)


class SummaryOutput(DashboardOutput):
    kind: Literal['summary']
    dimension: None
    measures: list[str] = Field(min_length=1, max_length=4)
    group_by: list[str] = Field(max_length=0)


class TableOutput(DashboardOutput):
    kind: Literal['table']


Output = ChartOutput | KPIOutput | SummaryOutput | TableOutput


class SingleSQL(ResponseModel):
    operation: Literal['sql']
    sql: str
    parameters: list[str | int | float | bool | None]
    explanation: str
    outputs: list[Output] = Field(max_length=8)


class SQLBundle(ResponseModel):
    operation: Literal['queries']
    queries: list[Dataset] = Field(min_length=1, max_length=MAX_DATASETS)
    outputs: list[Output] = Field(max_length=8)


class Clarification(ResponseModel):
    operation: Literal['clarification']
    clarification: str


class SQLResponse(ResponseModel):
    result: SingleSQL | SQLBundle | Clarification


class InventoryPlan(MetricMapping):
    operation: Literal['inventory']
    outputs: list[Output] = Field(max_length=8)


class CountPlan(ResponseModel):
    operation: Literal['count']
    count_query: CountQuery
    outputs: list[Output] = Field(max_length=8)


class InventoryResponse(ResponseModel):
    result: InventoryPlan | Clarification


class CountResponseFormat(ResponseModel):
    result: CountPlan | Clarification


class OutputResponse(ResponseModel):
    outputs: list[Output] = Field(min_length=1, max_length=8)


def response_schema(model, *, allow_kpi=True):
    schema = model.model_json_schema()
    schema['description'] = SYSTEM_RULES
    single_dataset = model in {InventoryResponse, CountResponseFormat, OutputResponse}
    if single_dataset:
        schema['description'] += (' This contract has exactly one server-compiled dataset, not a SQL bundle. '
                                  'Every output must use query: 0, irrespective of its position or measures. '
                                  'Do not generate SQL or additional datasets.')
        # Groq cannot disambiguate output unions with both kind and a fixed query reference.
        schema['$defs']['DashboardOutput'] = DashboardOutput.model_json_schema()
        if not allow_kpi:
            schema['$defs']['DashboardOutput']['properties']['kind']['enum'].remove('kpi')
        for output in (ChartOutput, KPIOutput, SummaryOutput, TableOutput):
            schema['$defs'].pop(output.__name__, None)
        for node in [schema, *schema['$defs'].values()]:
            if 'outputs' in node.get('properties', {}):
                node['properties']['outputs']['items'] = {'$ref': '#/$defs/DashboardOutput'}

    def strict(node):
        if isinstance(node, dict):
            node.pop('default', None)
            variants = node.get('anyOf', [])
            if any(value.get('type') == 'number' for value in variants):
                node['anyOf'] = [value for value in variants if value.get('type') != 'integer']
            if node.get('type') == 'object':
                node['required'] = list(node.get('properties', {}))
                node['additionalProperties'] = False
                if single_dataset and 'query' in node.get('properties', {}):
                    node['properties']['query']['maximum'] = 0
            for value in node.values():
                strict(value)
        elif isinstance(node, list):
            for value in node:
                strict(value)

    strict(schema)
    return schema


def normalize_generation(value, *, summarize_returned=False, required_kinds=()):
    """Normalize transport and unambiguous returned summaries; all validators still run afterward."""
    result = deepcopy(value)
    if not isinstance(result, dict):
        return result
    result = result.get('result', result)
    if not isinstance(result, dict):
        return result
    result.pop('operation', None)
    if len(result) == 1:
        nested = next(iter(result.values()))
        if isinstance(nested, dict) and {'domain', 'metrics'} <= set(nested):
            result = nested
    queries = result.get('queries')
    if isinstance(queries, list) and all(isinstance(item, dict) for item in queries):
        outputs = []
        for index, item in enumerate(queries):
            item.pop('operation', None)
            if 'question' not in item and isinstance(item.get('explanation'), str):
                item['question'] = item['explanation']
            nested = item.get('outputs', [])
            if isinstance(nested, list) and all(isinstance(output, dict) for output in nested):
                item.pop('outputs', None)
                for output in nested:
                    outputs.append({**output, 'query': index})
        if 'outputs' not in result and outputs:
            result['outputs'] = outputs
    for item in queries if isinstance(queries, list) else [result]:
        if not isinstance(item, dict) or not isinstance(item.get('sql'), str):
            continue
        try:
            statements = parse(item['sql'], read='postgres')
        except (ParseError, TokenError):
            continue
        if len(statements) == 1 and isinstance(statements[0], exp.Select) and not statements[0].args.get('limit'):
            from core.agents.sql.sql_validation import MAX_RESULT_ROWS
            item['sql'] = statements[0].limit(MAX_RESULT_ROWS).sql(dialect='postgres')
    if len(required_kinds) == 1:
        kind, = required_kinds
        if kind in {'line', 'bar', 'donut'}:
            _reuse_grouped_table_for_chart(result, kind)
    if (summarize_returned and isinstance(queries, list) and isinstance(result.get('outputs'), list)
            and all(isinstance(output, dict) for output in result['outputs'])):
        candidate = deepcopy(result)
        try:
            _reuse_summary_observations(candidate)
        except (TypeError, ValueError, KeyError, AttributeError):
            pass  # Preserve malformed plans for the normal validator and bounded repair.
        else:
            result = candidate
    if summarize_returned:
        _complete_returned_summary(result)
    return result


def _reuse_grouped_table_for_chart(result, kind):
    """Apply an explicit chart choice when the returned table already binds its exact fields."""
    from core.agents.dashboard.presentation import aggregate_outputs, output_roles

    outputs, queries = result.get('outputs'), result.get('queries', [result])
    if not isinstance(outputs, list) or len(outputs) != 1 or not isinstance(queries, list) or len(queries) != 1:
        return
    output, dataset = outputs[0], queries[0]
    if not isinstance(output, dict) or output.get('kind') != 'table' or not isinstance(dataset, dict):
        return
    try:
        binding = DashboardOutput.model_validate(output)
    except ValueError:
        return
    if binding.query != 0 or not binding.dimension or not binding.measures or binding.group_by not in ([], [binding.dimension]):
        return
    _, grouped = output_roles(dataset)
    if grouped == {binding.dimension} and set(binding.measures) <= aggregate_outputs(dataset) - grouped:
        outputs[0] = {**output, 'kind': kind, 'group_by': []}


def _complete_returned_summary(result):
    from core.agents.dashboard.presentation import aggregate_outputs, output_roles
    outputs = result.get('outputs')
    queries = result.get('queries', [result])
    if (not isinstance(outputs, list) or not isinstance(queries, list) or len(outputs) >= 8
            or not all(isinstance(output, dict) for output in outputs)
            or any(output.get('kind') == 'summary' for output in outputs)):
        return
    candidates = {}
    for output in outputs:
        index, measures = output.get('query'), output.get('measures')
        if (output.get('kind') not in {'line', 'bar', 'donut'} or type(index) is not int
                or not 0 <= index < len(queries) or not isinstance(queries[index], dict)
                or not isinstance(queries[index].get('sql'), str)
                or not isinstance(measures, list) or not measures or not all(isinstance(m, str) for m in measures)):
            continue
        _, grouped = output_roles(queries[index])
        if set(measures) <= aggregate_outputs(queries[index]) - grouped:
            candidates[index, tuple(measures)] = {'kind': 'summary', 'query': index, 'dimension': None,
                                                 'measures': measures.copy(), 'group_by': []}
    # shortcut: complete only one unambiguous observation set; multiple targets still need an explicit manifest.
    if len(candidates) == 1:
        outputs.append(next(iter(candidates.values())))


def _reuse_summary_observations(result):
    from sqlglot.optimizer.scope import traverse_scope
    from core.agents.sql.metric_validation import _canonical
    from core.agents.sql.sql_validation import validate_sql_security
    from core.agents.dashboard.requirements import scalar_result

    def proof(item):
        try:
            tree = validate_sql_security(item['sql'])
            scopes = list(traverse_scope(tree))
            parameters = item.get('parameters', [])
            fields = {projection.alias_or_name: {column.sql() for column in
                _canonical(projection, scopes[-1], parameters, {}).find_all(exp.Column)}
                for projection in tree.selects}
            filters = sorted((kind, _canonical(scope.expression.args[kind], scope, parameters, {}).sql())
                             for scope in scopes for kind in ('where', 'having', 'qualify')
                             if scope.expression.args.get(kind))
            # Source aliases differ between otherwise equivalent plans.
            sources = {table.db + '.' + table.name for table in tree.find_all(exp.Table) if table.db}
            return fields, filters, sources
        except (ValueError, TypeError, KeyError, IndexError, AttributeError, ParseError):
            return None

    queries, outputs = result['queries'], result['outputs']
    proofs = [proof(item) for item in queries]
    removed, replacements = set(), []
    for index, item in enumerate(queries):
        owned = [out for out in outputs if out.get('query') == index]
        if not owned or any(out.get('kind') != 'summary' for out in owned) or proofs[index] is None:
            continue
        try:
            if not scalar_result(item['sql']):
                continue
        except ValueError:
            continue
        fields, filters, sources = proofs[index]
        measures = set().union(*fields.values())
        if not measures:
            continue
        covered, planned = set(), []
        for output in outputs:
            target = output.get('query')
            if output.get('kind') not in {'line', 'bar', 'donut'} or target == index or not isinstance(target, int) or not 0 <= target < len(proofs) or proofs[target] is None:
                continue
            target_fields, target_filters, target_sources = proofs[target]
            if filters != target_filters or sources != target_sources:
                continue
            selected = [name for name in output.get('measures', [])
                        if target_fields.get(name) and target_fields[name] <= measures]
            if selected:
                covered.update(set().union(*(target_fields[name] for name in selected)))
                planned.append({'kind': 'summary', 'query': target, 'dimension': None,
                                'measures': selected, 'group_by': []})
        if covered == measures:
            removed.add(index)
            replacements.extend(planned)
    if removed:
        retained = [index for index in range(len(queries)) if index not in removed]
        remap = {old: new for new, old in enumerate(retained)}
        result['queries'] = [queries[index] for index in retained]
        result['outputs'], seen = [], set()
        for out in outputs + replacements:
            if out.get('query') not in remap:
                continue
            normalized = {**out, 'query': remap[out['query']]}
            key = (normalized['query'], normalized['kind'], normalized.get('dimension'),
                   tuple(normalized.get('measures', [])), tuple(normalized.get('group_by', [])))
            if key not in seen:
                seen.add(key)
                result['outputs'].append(normalized)


OUTPUT_RULES = f'''
Dashboard data request: generate SQL-backed datasets and the requested representations.
Dashboard response rules (override legacy presentation examples):
Wrap the complete response in {{"result": ...}}; result includes operation="sql", "queries",
"inventory", "count" or "clarification" with its matching fields. Put the plan inside result.
Return SQL with parameters, explanation and outputs, or queries plus outputs for up to {MAX_DATASETS} independent datasets.
Every dataset owns its question, SQL, parameters and explanation. Each question must retain the requested
period and filters so refreshing that saved dataset preserves the original scope. Every query must
contain exactly one SELECT statement and explicitly selected columns. Never concatenate statements in a sql
string. A single SQL dataset uses query: 0 for every output, including its descriptive summaries.
Put period predicates directly on source dates in WHERE; do not create a parameter CTE or join to parameters.
Every query must
include all requested date/filter bounds, including an overall KPI query. Outputs with the same source set,
grain and filters share one dataset. Independent charts from different fact sources use separate datasets;
this is required even when the chart sources share a month axis. Do not join their raw facts or aggregated
CTEs to combine chart datasets. Keep approved dimension joins needed to calculate a requested metric.
An overall KPI uses its own overall aggregate dataset, separate from grouped observations.
Return every requested representation in outputs. An overall KPI requires an aggregate SQL
row, never a raw source value. The renderer computes descriptive summaries from returned chart aggregates;
do not add window statistics or a second summary query. Output group_by is empty for charts
and global summaries. Chart measures must have comparable units, at most four per chart.
If the request leaves the measures ambiguous, ask which measures, offering concrete choices
from the available schema. Do not ask users to confirm explicitly requested chart types,
known columns or an already specified date scope. Clarifications return only clarification.
Do not add optional outputs. Do not guess missing business definitions or missing periods.
Use source.date >= $start AND source.date < $end_exclusive for period predicates, not BETWEEN
or casts on bound parameters. Bind native ISO dates. This lets the server prove the exact scope.
'''
