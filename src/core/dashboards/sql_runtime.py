"""Dashboard-only extensions; the canonical SQL runtime remains unchanged."""
from copy import copy
from datetime import date, timedelta
from functools import partial
import inspect
import json
import re

from core.agents.runtime import generate
from core.agents.sql.agent import SQLAnalyticsAgent, parse_json_response
from core.analytics.counting import COUNT_QUERY_INSTRUCTIONS, compile_count_query
from core.analytics.metric_mapping import decode_metric_mapping, compile_inventory_query, _required_metrics
from core.analytics.metric_ontology import METRIC_ONTOLOGY
from core.analytics.metric_validation import MetricDefinitionError, validate_metric_definitions, inventory_time_scope, inventory_month_selection
from core.analytics.sql_validation import APPROVED_DATE_COLUMNS, INVENTORY_SOURCES, QueryPlan, SQLValidationError, validate_sql_security, decode_query_plan
from core.dashboards.requirements import validate_outputs, validate_requested_kinds
from core.dashboards.models import MAX_DATASETS
from core.prompts.sql import DASHBOARD_OUTPUT_INSTRUCTIONS
from core.dashboards.generation import SQLResponse, InventoryResponse, CountResponseFormat, OutputResponse, response_schema, OUTPUT_RULES, normalize_generation


class CountResponse(Exception):
    def __init__(self, response):
        self.response = response


class DashboardSQLAgent(SQLAnalyticsAgent):
    async def run_payload(self, request):
        # Refresh can execute two saved datasets concurrently; repair state belongs to one request.
        self._authorize(request)
        upstream = getattr(self, '_upstream_agent', None)
        if upstream is not None:
            self.llm = upstream._provider()
        session = copy(self)
        session._dashboard_provider = None
        return await super(DashboardSQLAgent, session).run_payload(request)

    async def _execute_plan(self, plan, definitions, table_columns, approved_joins,
                            primary_keys, date_columns, interpretation=None, *, allowed_sources=None,
                            allow_unverified=False):
        if allow_unverified:
            return self._generation_error(MetricDefinitionError(
                'The SQL must pass schema and calculation validation before it can supply a dashboard. No unverified query was executed.',
                code='dashboard_unverified_sql'))
        return await super()._execute_plan(plan, definitions, table_columns, approved_joins,
                                          primary_keys, date_columns, interpretation, allowed_sources=allowed_sources)

    @classmethod
    def from_agent(cls, agent):
        # Keep repository, provider configuration and schema discovery from main.
        result = copy(agent)
        result.__class__ = cls
        result._dashboard_provider = None
        result._upstream_agent = agent
        return result

    def _provider(self):
        backend = super()._provider()
        if getattr(self, '_dashboard_provider', None) is None:
            provider = copy(backend)
            if inspect.iscoroutinefunction(backend.generate):
                async def augmented(prompt, **kwargs):
                    try:
                        raw = await backend.generate(self._prompt(prompt), **self._options(backend, prompt, kwargs))
                    except Exception as error:
                        raw = self._recover_format_error(error)
                    return await self._response(raw)
            else:
                # runtime.generate also awaits a coroutine returned by a synchronous provider.
                def augmented(prompt, **kwargs):
                    try:
                        raw = backend.generate(self._prompt(prompt), **self._options(backend, prompt, kwargs))
                    except Exception as error:
                        raw = self._recover_format_error(error)
                    return self._response(raw)
            provider.generate = augmented
            self._dashboard_provider = provider
        return self._dashboard_provider

    @staticmethod
    def _recover_format_error(error):
        body = getattr(error, 'body', None)
        detail = body.get('error', body) if isinstance(body, dict) else {}
        if detail.get('code') == 'json_validate_failed':
            # A rejected generation is still untrusted input to all normal SQL/output validators.
            failed = detail.get('failed_generation')
            if isinstance(failed, str) and failed.strip():
                try:
                    parse_json_response(failed)
                except (SQLValidationError, ValueError, TypeError):
                    pass
                else:
                    return failed
            raise SQLValidationError('The generated response did not match the dashboard JSON schema. '
                                     'Return the required outputs and correct field types. ' + str(detail.get('message', ''))[:500]) from error
        raise error

    def _options(self, backend, prompt, kwargs):
        from core.llm.groq_provider import GroqProvider
        if isinstance(backend, GroqProvider):
            model = (InventoryResponse if 'Catalog candidates (selection summaries only):' in prompt else SQLResponse)
            if self._inventory_count_intent() or model is InventoryResponse and self._count_intent():
                model = CountResponseFormat
            kwargs = {**kwargs, 'max_output_tokens': 2048, 'response_schema': response_schema(model)}
        return kwargs

    def _count_intent(self):
        return (bool(re.search(r'\bcounts?\b|number of|how many|đếm|bao nhiêu', self._question, re.I))
                and not re.search(r'\brates?\b|tỷ lệ|tỉ lệ', self._question, re.I))

    def _inventory_count_intent(self):
        if not getattr(self, '_question', ''):
            return False
        names = _required_metrics(self._question)
        sources = set(re.findall(r'\bcommerce\.\w+', self._question.casefold()))
        return (self._count_intent() and bool(names) and sources <= INVENTORY_SOURCES
                and all(METRIC_ONTOLOGY[name].get('domain') == 'inventory_management'
                        and (METRIC_ONTOLOGY[name].get('aggregation') == 'count_distinct'
                             or METRIC_ONTOLOGY[name].get('aggregation') == 'value'
                             and METRIC_ONTOLOGY[name].get('unit') == 'boolean') for name in names))

    async def _repair(self, prompt, model):
        from core.llm.groq_provider import GroqProvider
        backend = super()._provider()
        provider = copy(backend)
        if isinstance(backend, GroqProvider):
            provider.generate = partial(backend.generate, max_output_tokens=2048, response_schema=response_schema(model))
        try:
            return await generate(provider, prompt, timeout=30)
        except Exception as error:
            return self._recover_format_error(error)

    def _prompt(self, prompt, *, inventory_repair=False):
        if 'Repair only the outputs' in prompt:
            return prompt
        if not inventory_repair and not self._inventory_count_intent() and 'Catalog candidates (selection summaries only):' not in prompt:
            if not hasattr(self, '_columns') or 'Repair only the outputs' in prompt:
                return prompt + OUTPUT_RULES
            from core.analytics.text_to_sql import build_sql_prompt
            # Reuse main's business/safety context without its legacy single-dataset presentation instructions.
            context = build_sql_prompt(self._question, schema_columns=self._columns,
                                       approved_joins=self._joins, primary_keys=self._keys)
            context = re.sub(r'Return only JSON: .*? Never use writes',
                             'Follow the dashboard response schema below. Never use writes', context, count=1)
            context = context.split('\nInclude request_contract in SQL JSON:', 1)[0]
            # Main's single-result CTE advice conflicts with independent dashboard datasets.
            context = re.sub(r'When a request needs measures from independent fact tables[^\n]*', '', context)
            context = context.replace('Generate one read-only PostgreSQL SELECT',
                                      f'Generate up to {MAX_DATASETS} independent read-only PostgreSQL SELECTs', 1)
            mentioned = {}
            for source, columns in self._columns.items():
                for field in columns:
                    words = field.replace('_', ' ')
                    spelling = re.escape(words).replace(r'\ ', r'[ _]')
                    if words.endswith('s'):
                        spelling = spelling[:-1] + 's?'
                    if re.search(r'(?<!\w)' + spelling + r'(?!\w)', self._question, re.I):
                        mentioned.setdefault(field, []).append(source)
            context += '\nExplicitly mentioned source fields (including grammatical singulars): ' + json.dumps(mentioned)
            period = inventory_time_scope(self._question)
            context += '\nServer-resolved period and selected months: ' + json.dumps({
                'period': period, 'selected_months': sorted(inventory_month_selection(self._question))})
            if period and period[0] == 'range':
                context += '\nRequired source-date WHERE bounds: ' + json.dumps({
                    'start_inclusive': period[1],
                    'end_exclusive': (date.fromisoformat(period[2] or period[1]) + timedelta(days=1)).isoformat()})
            context += '\nClarification history: ' + json.dumps(getattr(self, '_clarifications', []))
            context += '\nUse explicitly mentioned recorded fields without asking for confirmation. Selected months require EXTRACT(MONTH FROM the source date) IN those month numbers, in addition to the period bounds.'
            if 'The previous plan failed validation:' in prompt:
                context += '\nThe previous plan failed validation:' + prompt.split('The previous plan failed validation:', 1)[1][:6000]
            return context + OUTPUT_RULES
        sources = {source: sorted(columns) for source, columns in self._columns.items() if source in INVENTORY_SOURCES}
        dates = {source: sorted(field for table, field in APPROVED_DATE_COLUMNS | set(self._dates or ())
                                if table == source and field in columns) for source, columns in sources.items()}
        catalog = {name: {key: value.get(key) for key in ('description', 'aggregation', 'formula', 'dimensions')}
                   for name, value in METRIC_ONTOLOGY.items() if value.get('domain') == 'inventory_management'}
        context = '\nRequest context: ' + json.dumps({'requested_metrics': sorted(_required_metrics(self._question)),
            'clarification_history': getattr(self, '_clarifications', [])})
        context += ('\nUse the supplied answers to resolve slots; do not repeat answered questions. '
                    'Requested charts and observation tables use the requested metrics unless the user explicitly assigns different ones. '
                    'Do not ask for the same measure separately for a chart and its observation table.\n')
        if self._count_intent():
            return ('Interpret this structural count request using only recorded entity fields. '
                'Choose the entity catalog, not a historical observation table, unless the user requested observations or a snapshot. '
                'Do not introduce a time restriction or latest snapshot when none was requested. '
                'Declare each requested grouping field in dimensions. Return exactly the requested counts, with independent conditions, no extra counts. '
                'Return {"result": {"operation": "count", "count_query": ..., "outputs": [...]}} or a specific clarification. '
                'Do not generate SQL or a metric interpretation.\n'
                + self._question + context + COUNT_QUERY_INSTRUCTIONS
                + '\nChart outputs need dimension plus one to four count aliases; table outputs may show all columns. '
                  'An overall scalar count can be a KPI. Preserve every requested representation. '
                + json.dumps({'approved_sources': sources, 'date_fields': dates})
                + ('\nRepair context: ' + prompt if inventory_repair else ''))
        return ('Interpret this dashboard request with the approved inventory catalog and source fields.\n'
            + self._question + context
            + json.dumps({'catalog': catalog}) + '\n'
            + OUTPUT_RULES
            + '\nReturn a flat inventory interpretation with outputs, or clarification only. '
              'For inventory time, use latest if explicitly requested. Only ask for a snapshot when the user omitted it. '
              'A vague category chart without a measure needs a business question about the measure, not a guessed stock metric. '
            + ('\nRepair context: ' + prompt if inventory_repair else '')
            + '\nChoose suitable representations if unspecified: scalar counts can use KPIs; '
              'comparisons and trends need a suitable chart. Explicit observation tables are additional outputs. '
              'Do not add unrequested KPIs or summaries. Chart group_by must be empty. '
              'Use the one server-known date field without asking the user to choose it.\n'
            + json.dumps({'approved_inventory_count_sources': sources, 'date_fields': dates}))

    async def _response(self, raw):
        self._responses.append(raw)
        try:
            response = parse_json_response(raw)
        except SQLValidationError:
            return raw
        response = normalize_generation(response, summarize_returned=bool(re.search(
            r'statistical summar|summary statistics?|descriptive statistics?|thống kê mô tả|tóm tắt thống kê', self._question, re.I)))
        raw = json.dumps(response)
        if isinstance(response, dict) and 'result' in response:
            response = response['result']
            response.pop('operation', None)
            raw = json.dumps(response)
        if isinstance(response, dict) and 'interpretation' in response:
            if response.get('clarification'):
                return json.dumps({'clarification': response['clarification']})
            if response.get('count_query') is not None:
                response = {'count_query': response['count_query'], 'outputs': response.get('outputs')}
            elif response.get('interpretation') is not None:
                response = {**response['interpretation'], 'outputs': response.get('outputs')}
            raw = json.dumps(response)
        if isinstance(response, dict) and 'queries' in response:
            if response.get('clarification'):
                return json.dumps({'clarification': response['clarification']})
            response.pop('clarification', None)
            if len(response['queries']) == 1:
                response = {**{k: v for k, v in response['queries'][0].items() if k != 'question'},
                            'outputs': response.get('outputs')}
            raw = json.dumps(response)
        if isinstance(response, dict) and 'count_query' in response:
            raise CountResponse(response)
        if not isinstance(response, dict) or 'metrics' not in response:
            if isinstance(response, dict) and ('sql' in response or 'queries' in response):
                for dataset in response.get('queries', [response]):
                    if isinstance(dataset, dict) and isinstance(dataset.get('sql'), str):
                        validate_sql_security(dataset['sql'])
                try:
                    validate_requested_kinds(response.get('outputs') or [], self._question, self._clarifications)
                except MetricDefinitionError as error:
                    raise SQLValidationError(str(error)) from error
            return raw
        mapping = {key: value for key, value in response.items() if key != 'outputs'}
        try:
            interpretation = decode_metric_mapping(json.dumps(mapping), self._question)
            if interpretation.domain != 'inventory':
                return raw
            sql, parameters = compile_inventory_query(interpretation)
            plan = QueryPlan(sql=sql, parameters=parameters)
            definitions = {name: METRIC_ONTOLOGY[name] for name in interpretation.metrics}
            validate_requested_kinds(response.get('outputs') or [], self._question, self._clarifications)
            validate_outputs(response.get('outputs'), [(self._question, plan, definitions)], self._question, self._dates)
        except (MetricDefinitionError, SQLValidationError) as error:
            code = getattr(error, 'code', None)
            repairable = code in {'interpretation_invalid', 'interpretation_mismatch', 'incompatible_grain', 'dashboard_requirements', 'invalid_date_scope'}
            if not repairable:
                return raw
            if len(self._responses) >= 2:
                raise MetricDefinitionError('The generated inventory interpretation could not be repaired: ' + str(error)[:300], code='interpretation_mismatch')
            if code == 'dashboard_requirements':
                repaired = parse_json_response(await self._repair(
                    self._prompt(DASHBOARD_OUTPUT_INSTRUCTIONS + '\nRepair only the outputs for this validated interpretation. Return exactly {"outputs": [...]}.\n'
                        + json.dumps({'question': self._question, 'interpretation': mapping, 'sql': sql, 'error': str(error)})), OutputResponse))
                self._responses.append(json.dumps(repaired))
                if isinstance(repaired, dict) and set(repaired) == {'outputs'}:
                    response['outputs'] = repaired['outputs']
                    return json.dumps(response)
                return raw
            names = mapping.get('metrics', [])
            aggregations = [METRIC_ONTOLOGY[name].get('aggregation') for name in names if name in METRIC_ONTOLOGY]
            counts = 'count_distinct' in aggregations and set(aggregations) <= {'count_distinct', 'value'}
            repair = (('Return the count_query response schema only, with outputs; do not use the legacy metric mapping.\n' if counts else
                       'Repair the complete typed inventory interpretation and its outputs.\n')
                + json.dumps({'request': self._question, 'previous_response': response, 'validation_error': str(error)}))
            repaired = await self._repair(self._prompt(repair, inventory_repair=True), CountResponseFormat if counts else InventoryResponse)
            return await self._response(repaired)
        return raw

    def _decode_dashboard_queries(self, raw, question, options, metric_names, allowed_sources,
                                  table_columns, approved_joins, primary_keys, date_columns):
        response = parse_json_response(raw)
        parent = super()._decode_dashboard_queries
        arguments = (table_columns, approved_joins, primary_keys, date_columns)
        if not isinstance(response, dict) or 'queries' not in response:
            return parent(raw, question, options, metric_names, allowed_sources, *arguments)
        items = response['queries']
        if not isinstance(items, list) or not 1 <= len(items) <= MAX_DATASETS:
            raise SQLValidationError(f'A dashboard accepts at most {MAX_DATASETS} independent queries.')
        if set(response) - {'queries', 'outputs'}:
            raise SQLValidationError('Each data query must own its parameters and explanation; do not put them at the dashboard level.')
        expected = inventory_time_scope(question)
        selected = inventory_month_selection(question)
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get('question'), str):
                raise SQLValidationError('Each independent query needs its own self-contained question.')
            scoped = item['question'] + '\n' + (options.get('_dashboard_scope') or '')
            if ((expected and inventory_time_scope(scoped) != expected)
                    or (selected and inventory_month_selection(scoped) != selected)):
                raise SQLValidationError('Each saved dataset question must retain the requested period and selected months, so refresh cannot change its scope.')
        if len(items) <= 2:
            return parent(raw, question, options, metric_names, allowed_sources, *arguments)
        # Reuse all of main's per-query guards; only the dashboard's total bound changes.
        bundle, names, sources = [], set(), set()
        from core.analytics.metric_ontology import resolve_metric_names
        from sqlglot import parse_one, exp
        for item in items:
            metric_question = item['question']
            for source in table_columns:
                metric_question = re.sub(r'\b' + re.escape(source) + r'\b', '', metric_question, flags=re.I)
            requested = resolve_metric_names(metric_question)
            if requested - metric_names:
                raise SQLValidationError('Independent queries cannot introduce unrequested canonical metrics.')
            checked = parent(json.dumps({'queries': [item], 'outputs': []}), item['question'], options,
                             requested, allowed_sources, *arguments)
            names.update(requested)
            for _, plan, _ in checked:
                sources.update(table.db + '.' + table.name for table in parse_one(plan.sql, read='postgres').find_all(exp.Table) if table.db)
            bundle.extend(checked)
        if names != metric_names:
            raise SQLValidationError('Independent queries must retain every requested canonical metric.')
        explicit_sources = set(re.findall(r'\bcommerce\.\w+', re.sub(r"'(?:[^']|'')*'", '', question).casefold()))
        if not explicit_sources <= sources:
            raise SQLValidationError('Independent queries must retain every explicitly requested source.')
        if len({item[0].casefold() for item in bundle}) != len(bundle) or len({(item[1].sql, item[1].parameters) for item in bundle}) != len(bundle):
            raise SQLValidationError('Reuse a dataset instead of duplicating its query.')
        return bundle

    @staticmethod
    def _validation_message(detail, question):
        detail = detail.removeprefix('Please clarify the requested measures, grouping, scope or representation. ').strip()[:700]
        if re.search(r'[ăâđêôơưáàảãạấầẩẫậắằẳẵặếềểễệốồổỗộớờởỡợứừửữựýỳỷỹỵ]', question, re.I):
            return ('Mình chưa tạo được dashboard vì kế hoạch dữ liệu hoặc cách hiển thị chưa hợp lệ. '
                    f'Nguyên nhân kiểm tra: {detail} Chưa thực thi query dữ liệu dashboard. Yêu cầu bạn đã nhập vẫn được giữ nguyên.')
        return (f'I could not build the dashboard because its data/output plan failed validation. Reason: {detail} '
                'No dashboard data query was executed. Your original request is retained.')

    async def _resolve_snapshot(self, request, context_info, columns, date_columns):
        latest = r'\b(?:latest(?:\s+available)?|most recent)\b|mới nhất(?:\s+hiện có)?|gần nhất'
        names = _required_metrics(self._question)
        if (not re.search(latest, self._question, re.I) or not names or self._count_intent()
                or any(METRIC_ONTOLOGY[name].get('domain') != 'inventory_management' for name in names)):
            return request
        period = inventory_time_scope(self._question)
        if not period or period[0] != 'range':
            return request
        start, end = period[1], period[2] or period[1]
        stop = (date.fromisoformat(end) + timedelta(days=1)).isoformat()
        plan = decode_query_plan(json.dumps({
            'sql': 'SELECT MAX(i.snapshot_date) AS snapshot_date FROM commerce.inventory AS i WHERE i.snapshot_date >= $1 AND i.snapshot_date < $2 LIMIT 1',
            'parameters': [start, stop]}), schema_columns=columns, allowed_sources=set(columns), date_columns=date_columns)
        rows = await self.repository.execute_approved_query(plan.sql, *plan.parameters)
        snapshot = str(rows[0].get('snapshot_date')) if rows else ''
        try:
            valid = date.fromisoformat(start) <= date.fromisoformat(snapshot) <= date.fromisoformat(end)
        except ValueError:
            valid = False
        if not valid:
            raise MetricDefinitionError('No inventory snapshot is available within the requested period. No dashboard data query was executed.',
                                        code='dashboard_snapshot_unavailable')
        context_info['dashboard_snapshot_scope'] = {'requested_question': self._question, 'start': start,
                                                    'end': end, 'snapshot_date': snapshot}
        self._question = re.sub(latest, 'snapshot ' + snapshot, self._question, flags=re.I)
        return request.model_copy(update={'question': self._question})

    async def _run_payload(self, request, context_info, table_columns, approved_joins, primary_keys, date_columns):
        self._columns, self._dates = table_columns, date_columns
        self._joins, self._keys = approved_joins, primary_keys
        self._clarifications = request.metadata.get('_dashboard_clarifications', [])
        self._question, self._responses = self._query_text(request), []
        try:
            request = await self._resolve_snapshot(request, context_info, table_columns, date_columns)
        except (MetricDefinitionError, SQLValidationError) as error:
            return self._generation_error(error)
        except Exception as error:
            return self._database_error(error, None, ())
        result = await super()._run_payload(request, context_info, table_columns, approved_joins, primary_keys, date_columns)
        datasets = [item['payload'] for item in result['datasets']] if 'datasets' in result else [result]
        for payload in datasets:
            if payload.get('metadata', {}).get('metric_validation', {}).get('status') == 'unverified':
                payload.update(ok=False, rows=[], query_status='unsupported',
                    answer='The returned calculation could not be verified. Correct the metric or query before using it in a dashboard.')
        if 'datasets' in result:
            result['ok'] = all(payload.get('ok') for payload in datasets)
        response = result.pop('_dashboard_count_response', None)
        if response is None:
            if result.get('metadata', {}).get('metric_error_code') == 'dashboard_requirements':
                result['answer'] = self._validation_message(result['metadata'].get('error_detail', ''), self._question)
                result['metadata'].update(status='generation_failed', clarification_required=False)
            return result
        for attempt in range(2):
            try:
                return await self._count_response(response, request, table_columns, approved_joins, primary_keys, date_columns)
            except (MetricDefinitionError, SQLValidationError) as error:
                if attempt or len(self._responses) >= 2 or (getattr(error, 'clarification', False) and getattr(error, 'code', None) != 'dashboard_requirements'):
                    return self._generation_error(error)
                try:
                    if getattr(error, 'code', None) == 'dashboard_requirements':
                        raw = await self._repair(
                            'Repair only the outputs for this validated count query. Return exactly {"outputs": [...]}. '
                            'The count query, grouping, population and snapshot are fixed. Do not change them. '
                            'Grouped counts use a chart or table, not an overall KPI. Preserve explicitly requested outputs; '
                            'do not add unrequested KPIs or counts.\n'
                            + json.dumps({'request': self._question, 'previous_response': response, 'validation_error': str(error)}),
                            OutputResponse)
                        self._responses.append(raw)
                        repaired = parse_json_response(raw)
                        if not isinstance(repaired, dict) or set(repaired) != {'outputs'}:
                            raise MetricDefinitionError('The output repair did not return the required outputs list. Original failure: ' + str(error),
                                                        code='dashboard_requirements')
                        response = {**response, 'outputs': repaired['outputs']}
                        continue
                    raw = await self._repair(self._prompt(
                        'Repair this count_query and outputs without changing the requested population, measures or dates.\n'
                        + json.dumps({'request': self._question, 'previous_response': response, 'validation_error': str(error)}), inventory_repair=True), CountResponseFormat)
                    self._responses.append(raw)
                    response = parse_json_response(raw)
                    if isinstance(response, dict) and 'result' in response:
                        response = response['result']
                        response.pop('operation', None)
                    if isinstance(response, dict) and 'interpretation' in response:
                        response = {'count_query': response.get('count_query'), 'outputs': response.get('outputs')}
                except Exception as repair_error:
                    return self._generation_error(repair_error)

    async def _count_response(self, response, request, columns, joins, keys, dates):
        if not isinstance(response, dict) or set(response) - {'count_query', 'outputs'} or 'count_query' not in response:
            raise MetricDefinitionError('Return a count_query and its outputs only.', code='count_plan_invalid')
        plan, definitions, spec = compile_count_query(response['count_query'], columns, self._question, dates)
        if self.inventory_only and spec.source not in INVENTORY_SOURCES:
            raise MetricDefinitionError('This deployment supports inventory counts only.', code='count_unsupported')
        if spec.source != 'commerce.inventory':
            from core.analytics.metric_ontology import resolve_metric_names
            names = {name for name in resolve_metric_names(self._question)
                     if METRIC_ONTOLOGY[name].get('domain') != 'inventory_management'}
            validate_metric_definitions(plan.sql, names, plan.parameters, columns, question=self._question)
        declared = validate_outputs(response.get('outputs'), [(self._question, plan, definitions)], self._question, dates)[0]
        validate_requested_kinds(response.get('outputs') or [], self._question, self._clarifications)
        result = await self._execute_plan(plan, definitions, columns, joins, keys, dates)
        if (result.get('ok') and spec.source == 'commerce.inventory' and spec.time.mode == 'latest'
                and result.get('rows') and all(row.get('snapshot_date') is None for row in result['rows'])):
            result.update(ok=False, rows=[], query_status='unsupported', answer='No inventory snapshots are available within the requested period.')
            result.setdefault('metadata', {})['status'] = 'unsupported'
        result.setdefault('metadata', {}).update(count_query=spec.model_dump(), dashboard_outputs=declared)
        return result

    @staticmethod
    def _generation_error(error, sql=None, parameters=(), *, question=''):
        if isinstance(error, CountResponse):
            return {'_dashboard_count_response': error.response}
        result = SQLAnalyticsAgent._generation_error(error, sql, parameters, question=question)
        code = getattr(error, 'code', None)
        if code in {'interpretation_invalid', 'interpretation_mismatch', 'count_plan_invalid', 'dashboard_requirements'}:
            result.update(answer=DashboardSQLAgent._validation_message(str(error), question))
            result['metadata'].update(status='generation_failed', clarification_required=False)
        elif code in {'count_unsupported', 'metric_unsupported', 'incompatible_grain', 'dashboard_snapshot_unavailable'}:
            result.update(answer=str(error), query_status='unsupported')
            result['metadata'].update(status='unsupported', clarification_required=False)
        return result
