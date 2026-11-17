"""Validate SQL/output consistency without interpreting prose or making model calls."""
from pydantic import ValidationError
from sqlglot import exp, parse_one
from sqlglot.optimizer.scope import Scope, traverse_scope

from core.analytics.metric_validation import MetricDefinitionError, validate_independent_query_period
from core.analytics.sql_validation import APPROVED_DATE_COLUMNS
from core.dashboards.models import DashboardOutput, MAX_DATASETS
from core.dashboards.presentation import aggregate_outputs, output_roles
import re


def validate_requested_kinds(outputs, question, clarifications=()):
    patterns = {
        'line': r'\bline[ -]*charts?\b|biểu đồ đường',
        'bar': r'\bbar[ -]*charts?\b|biểu đồ (?:cột|thanh)',
        'donut': r'\bdonut\b|\bdoughnut\b|biểu đồ tròn',
        'table': r'\b(?:include|show|display|add|use|with|and|as)\s+(?:an?\s+)?(?:data\s+)?table\b|hiển thị.*\bbảng\b',
        'kpi': r'\bkpis?\b',
        'summary': r'statistical summar|summary statistics?|descriptive statistics?|thống kê mô tả|tóm tắt thống kê',
    }
    requested = {kind for kind, pattern in patterns.items() if re.search(pattern, question, re.I)}
    for turn in clarifications:
        reply = turn['reply']
        choices = {kind for kind, pattern in patterns.items() if re.search(pattern, reply, re.I)}
        if choices:
            if re.search(r'\bonly\b|\binstead\b|chỉ|thay', reply, re.I):
                requested = choices
            elif choices & {'line', 'bar', 'donut'}:
                requested = (requested - {'line', 'bar', 'donut'}) | choices
    missing = requested - {output.get('kind') for output in outputs if isinstance(output, dict)}
    if missing:
        raise MetricDefinitionError('The generated outputs omitted explicitly requested representations: '
                                    + ', '.join(sorted(missing)) + '. Preserve each requested representation and its measures.',
                                    code='dashboard_requirements')


def require(condition, message):
    if not condition:
        raise MetricDefinitionError(message, code='dashboard_requirements', clarification=True)


def scalar_result(sql):
    def scalar(scope, visited=()):
        if id(scope) in visited:
            return False
        select = scope.expression
        if select.args.get('group'):
            return False
        aggregates = [node for projection in select.selects for node in projection.find_all(exp.AggFunc)
                      if node.find_ancestor(exp.Select) is select and not node.find_ancestor(exp.Window)]
        if aggregates:
            return True
        sources = [source for _, source in scope.selected_sources.values()]
        return len(sources) == 1 and isinstance(sources[0], Scope) and scalar(sources[0], (*visited, id(scope)))
    scopes = list(traverse_scope(parse_one(sql, read='postgres')))
    return bool(scopes) and scalar(scopes[-1])


def validate_outputs(raw, plans, question, date_columns=None):
    require(isinstance(raw, list) and 1 <= len(raw) <= 8,
            f'A dashboard supports one to eight outputs across at most {MAX_DATASETS} independent datasets.')
    try:
        outputs = [DashboardOutput.model_validate(value) for value in raw]
    except ValidationError as error:
        raise MetricDefinitionError('Please clarify the output type and measures. Supported outputs are line, bar, donut, table, KPI and descriptive summary.',
                                    code='dashboard_requirements', clarification=True) from error
    seen = set()
    query_outputs = {index: [] for index in range(len(plans))}
    for index, output in enumerate(outputs):
        require(output.query in query_outputs, f'A requested output has no data query. Keep the plan within {MAX_DATASETS} independent datasets.')
        _, plan, _ = plans[output.query]
        projections, grouped = output_roles({'sql': plan.sql})
        columns = set(projections)
        fields = set(output.measures + output.group_by + ([output.dimension] if output.dimension else []))
        require(fields <= columns, 'A requested output refers to measures or dimensions absent from its query. Please clarify which fields to show.')
        if output.kind in {'line', 'bar', 'donut'} and output.group_by:
            require(output.group_by == [output.dimension], 'Chart grouping must match its single returned dimension; additional grouping is unsupported.')
            output = output.model_copy(update={'group_by': []})
        require(output.kind == 'table' or not output.group_by, 'Statistics within each group are not supported yet. Choose a summary across returned observations, or request grouped aggregates as a table.')
        require(output.kind == 'table' or bool(output.measures), 'Each chart, KPI or summary needs its own requested measures.')
        require(output.kind == 'table' or not set(output.measures) & grouped,
                'Grouping dimensions may be table columns, but cannot be numeric chart, KPI or summary measures.')
        if output.kind in {'line', 'bar', 'donut'}:
            require(output.dimension is not None and output.dimension not in output.measures,
                    'Each chart needs one returned date or category dimension, separate from its measures.')
        if output.kind in {'kpi', 'summary'}:
            require(output.dimension is None, 'Specify a global summary or KPI, or request grouped values as a table.')
            aggregates = aggregate_outputs({'sql': plan.sql})
            require(set(output.measures) <= aggregates, 'KPI and summary measures need verified aggregates, not identifiers, raw fields or window calculations.')
        if output.kind == 'kpi':
            require(len(output.measures) == 1 and scalar_result(plan.sql),
                    'An overall KPI needs a separate overall aggregate query. Monthly or category rows cannot supply an overall total KPI.')
        signature = (output.query, output.kind, output.dimension, tuple(output.measures))
        require(signature not in seen, 'The output plan duplicates the same representation and measures. Please reuse that output.')
        seen.add(signature)
        query_outputs[output.query].append({'id': f'output{index}', **output.model_dump()})
    for index, (_, plan, definitions) in enumerate(plans):
        require(bool(query_outputs[index]), 'A query has no requested output. Remove it or bind the output it supplies.')
        require(sum(output['kind'] in {'line', 'bar', 'donut'} for output in query_outputs[index]) <= 2,
                'Each dataset supports at most two explicitly mapped charts. Please narrow the chart request.')
        dates = APPROVED_DATE_COLUMNS | set(date_columns or ())
        sources = {source for definition in definitions.values()
                   for source in (definition.get('source_columns') or {definition.get('source'): ()}) if source}
        if not sources:
            sources = {table.db + '.' + table.name for table in parse_one(plan.sql, read='postgres').find_all(exp.Table) if table.db}
        dated = {source for source in sources if any(table == source for table, _ in dates)}
        if definitions and all('count_kind' in value for value in definitions.values()):
            from core.analytics.counting import validate_count_period
            validate_count_period(plan, question, dated or sources, dates)
        else:
            validate_independent_query_period(plan.sql, plan.parameters, question, dated or sources, dates)
    return query_outputs
