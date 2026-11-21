"""Build saved dashboards from SQL results without dashboard model calls."""
import asyncio
import logging
import time

from core.agents.runtime import deadline
from core.agents.sql.metric_validation import inventory_time_scope
from core.agents.dashboard.models import BuildRequest, DashboardDocument, QueryResult, QuerySpec, TileSpec, now, MAX_DATASETS, MAX_CONCURRENT_QUERIES
from core.agents.dashboard.presentation import automatic_tiles, automatic_chart_tiles, summary_tiles, bind_fields, reconcile, presentation_choice, set_representation
from core.agents.dashboard.presentation import vietnamese_tile_title
from core.agents.language import is_vietnamese
from core.agents.sql.agent import SQLAnalyticsAgent

logger = logging.getLogger(__name__)


class DashboardDocumentAgent:
    def __init__(self, sql_agent):
        from core.agents.dashboard.sql_runtime import DashboardSQLAgent
        self.sql_agent = (DashboardSQLAgent.from_agent(sql_agent)
                          if type(sql_agent) is SQLAnalyticsAgent else sql_agent)

    async def execute(self, request, document, *, allow_multiple=False):
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_QUERIES)
        vi = is_vietnamese(document.description)
        questions = {}
        for spec in document.queries:
            if document.scope:
                period = inventory_time_scope(spec.question)
                scope_period = inventory_time_scope(document.scope)
                if period and scope_period and period != scope_period:
                    raise ValueError('Phạm vi ngày mâu thuẫn với mô tả. Hãy sửa mô tả và tạo lại dashboard.'
                                     if vi else 'Scope conflicts with dates in the description or saved question. Edit the description and Rebuild.')
            questions[spec.id] = spec.question + (f'\nRequired dashboard date/filter scope: {document.scope}' if document.scope else '')
            if document.clarifications and (allow_multiple or len(document.queries) == 1):
                questions[spec.id] += ''.join('\nUser clarification: ' + turn.reply for turn in document.clarifications)

        async def query(spec):
            async with semaphore:
                question = questions[spec.id]
                metadata = {'_dashboard_request': True}
                if allow_multiple:
                    metadata.update(_dashboard_allow_multiple=True, _dashboard_scope=document.scope)
                if document.clarifications and (allow_multiple or len(document.queries) == 1):
                    metadata['_dashboard_clarifications'] = [turn.model_dump() for turn in document.clarifications]
                child = request.model_copy(update={'question': question, 'metadata': metadata, 'conversation_id': None})
                try:
                    payload = await asyncio.wait_for(self.sql_agent.run_payload(child), max(1, deadline.get() - time.monotonic()))
                    if 'datasets' in payload:
                        if not allow_multiple or not isinstance(payload['datasets'], list) or not 1 <= len(payload['datasets']) <= MAX_DATASETS:
                            raise ValueError('Unexpected independent query bundle')
                        datasets = []
                        for index, item in enumerate(payload['datasets']):
                            child_spec = QuerySpec(id=f'q{index}', question=item['question'])
                            datasets.append((child_spec, self.query_result(child_spec.id, child_spec.question, item['payload'], vi=vi)))
                        return datasets
                    return [(spec, self.query_result(spec.id, question, payload, vi=vi))]
                except Exception:
                    logger.exception('Dashboard dataset failed: %s', spec.id)
                    message = ('Không thể hoàn tất truy vấn nguồn. Hãy thử tải lại hoặc nêu rõ chỉ số và phạm vi.'
                               if vi else 'Source query could not complete. Retry refresh or make its metric and scope more explicit.')
                    return [(spec, QueryResult(id=spec.id, question=question, status='failed', message=message))]

        used = {tile.query_id for tile in document.tiles}
        batches = await asyncio.gather(*(query(spec) for spec in document.queries if spec.id in used))
        datasets = [dataset for batch in batches for dataset in batch]
        document.queries = [spec for spec, result in datasets]
        document.results = [result for spec, result in datasets]
        document.data_updated_at = now()
        return document

    bind_fields = staticmethod(bind_fields)

    @staticmethod
    def query_result(identifier, question, payload, *, vi=False):
        if payload.get('query_status') == 'executed' and (payload.get('ok') or not payload.get('rows')):
            status = 'complete' if payload.get('rows') else 'empty'
        else:
            metadata = payload.get('metadata', {})
            clarification = (payload.get('query_status') in {'clarification_required', 'needs_clarification'}
                             or metadata.get('status') == 'clarification_required' or metadata.get('clarification_required'))
            status = 'clarification_required' if clarification else 'failed'
        message = payload.get('answer') or payload.get('message') or payload.get('error') or ''
        if vi and message == 'Query completed.':
            message = 'Truy vấn đã hoàn tất.'
        # Retain provenance, excluding conversational/provider state.
        safe = {key: payload[key] for key in ('rows', 'sql', 'attempted_sql', 'parameters', 'metadata', 'query_status', 'evidence') if key in payload}
        safe['metadata'] = {key: value for key, value in safe.get('metadata', {}).items() if not key.startswith('_')}
        if payload.get('limitations'):
            safe['metadata']['limitations'] = payload['limitations']
        return QueryResult(id=identifier, question=question, status=status, payload=safe, message=str(message)[:1200])

    async def build(self, request, description, scope='', *, clarifications=(), presentation_choices=None):
        SQLAnalyticsAgent._authorize(request)
        body = BuildRequest(description=description, scope=scope)
        document = DashboardDocument(title=body.description[:120], description=body.description, scope=body.scope,
            clarifications=clarifications,
            queries=[QuerySpec(id='q0', question=body.description)],
            tiles=[TileSpec(id='data', title='Source data', kind='table', query_id='q0', span=2)])
        token = deadline.set(time.monotonic() + 180)
        try:
            async with asyncio.timeout(180):
                await self.execute(request, document, allow_multiple=True)
                document.tiles = []
                presentation_question = body.description
                for turn in document.clarifications:
                    if not presentation_choices and presentation_choice(turn.reply):
                        presentation_question = turn.reply
                summary_question = body.description + ''.join('\n' + turn.reply for turn in document.clarifications)
                for result in document.results:
                    question = presentation_question if len(document.results) == 1 or presentation_question != body.description else result.question
                    declared = result.payload.get('metadata', {}).get('dashboard_outputs')
                    if declared:
                        tiles = []
                        for output in declared:
                            title = output['kind'].title() + ': ' + ', '.join(output['measures']).replace('_', ' ')
                            tiles.append(TileSpec(id=output['id'], title=title[:120], kind=output['kind'], query_id=result.id,
                                measures=output['measures'], dimension=output['dimension'], span=1 if output['kind'] == 'kpi' else 2))
                    else:
                        tiles = automatic_tiles(result, question)
                    if not presentation_choices:
                        tiles = automatic_chart_tiles(tiles, result, summary_question)
                    if len(document.results) > 1:
                        if not declared and len(tiles) > 4:
                            tiles = [TileSpec(id='data', title=result.question[:120], kind='table', query_id=result.id, span=2)]
                        tiles = [tile.model_copy(update={'id': result.id + '_' + tile.id}) for tile in tiles]
                    for tile in tiles:
                        if tile.id in (presentation_choices or {}):
                            set_representation(tile, presentation_choices[tile.id], result)
                    summaries = [] if declared else summary_tiles(result, summary_question, tiles)
                    if len(document.results) > 1:
                        for summary in summaries:
                            summary.id = result.id + '_' + summary.id
                    document.tiles.extend([*tiles, *summaries])
                document = reconcile(document)
                if is_vietnamese(body.description):
                    for tile in document.tiles:
                        tile.title = vietnamese_tile_title(tile)
                if document.clarifications and document.tiles[0].kind in {'line', 'bar', 'donut', 'kpi'}:
                    document.title = document.tiles[0].title
                return document
        finally:
            deadline.reset(token)

    async def refresh(self, request, document):
        SQLAnalyticsAgent._authorize(request)
        token = deadline.set(time.monotonic() + 180)
        try:
            async with asyncio.timeout(180):
                # Saved questions exclude shared scope, so edits need no model rewrite.
                await self.execute(request, document)
                return reconcile(document)
        finally:
            deadline.reset(token)
