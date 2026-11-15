"""Authenticated saved dashboard workspace; no client-authored SQL or HTML."""
import asyncio
from functools import lru_cache
import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse

from app.agents import _agent_request, _get_runtime
from app.security import require_permission, _require_same_origin
from core.agents.conversation_context import ConversationStore
from core.dashboards.agent import DashboardDocumentAgent
from core.dashboards.models import BuildRequest, DashboardEdit, DashboardDocument, RefreshRequest, PendingDashboard, ClarificationTurn
from core.dashboards.render import CSP, render_dashboard
from core.dashboards.presentation import presentation_clarification, presentation_choice
from core.dashboards.store import DashboardStore, Conflict

router = APIRouter(prefix='/api/dashboards', tags=['dashboards'])
principal = require_permission('view_analytics')
logger = logging.getLogger(__name__)
_build_slots = asyncio.Semaphore(2)


@lru_cache(maxsize=1)
def get_store():
    return DashboardStore()


@lru_cache(maxsize=1)
def get_conversations():
    return ConversationStore(max_turns=1, max_chars=40_000)


def owned(store, user, identifier):
    doc = store.get(user['sub'], identifier)
    if doc is None:
        raise HTTPException(404, 'Dashboard not found')
    return doc


def revision(doc, expected):
    if doc.revision != expected:
        raise HTTPException(409, 'Dashboard changed. Reopen it before saving.')


def bundle(doc, status=200):
    return JSONResponse({'dashboard': doc.model_dump(mode='json'), 'html': render_dashboard(doc),
                         'html_url': f'/api/dashboards/{doc.id}/html'}, status_code=status,
                        headers={'Cache-Control': 'no-store'})


async def build(request, user, *, description=None, scope='', document=None, clarifications=(), presentation_choices=None):
    runtime = await _get_runtime(request.app)
    sql_engine = getattr(runtime.analytics_agent, 'sql_agent', runtime.analytics_agent)
    agent = DashboardDocumentAgent(sql_engine)
    identity = _agent_request(user, description or document.description)
    try:
        async with asyncio.timeout(190):
            async with _build_slots:
                if description is not None:
                    return await agent.build(identity, description, scope, clarifications=clarifications,
                                             presentation_choices=presentation_choices)
                return await agent.refresh(identity, document)
    except TimeoutError:
        raise HTTPException(504, 'Dashboard query timed out. Try a more specific metric and period.')
    except ValueError as error:
        raise HTTPException(422, str(error))
    except Exception:
        logger.exception('Dashboard composition failed')
        raise HTTPException(503, 'Dashboard data is unavailable. Check the SQL provider and data connection, then retry.')


def persist(store, user, doc, expected=None):
    try:
        return store.save(user['sub'], doc, expected)
    except Conflict as error:
        raise HTTPException(409, str(error))
    except ValueError as error:
        raise HTTPException(422, str(error))


def clarification_reply(draft, conversation_id, *, can_reply=True):
    return JSONResponse({'status': 'clarification_required', 'message': draft.question,
        'scope': draft.scope, 'description': draft.description, 'conversation_id': conversation_id if can_reply else None,
        'can_reply': can_reply}, headers={'Cache-Control': 'no-store'})


def pause_draft(draft, conversation_id, history):
    can_reply = len(draft.clarifications) < 3
    history[:] = [{'draft': draft.model_dump_json()}] if can_reply else []
    if not can_reply:
        draft.question = draft.question[:1000] + '\nPlease start a new dashboard request with the complete requirements.'
    return clarification_reply(draft, conversation_id, can_reply=can_reply)


async def run_draft(request, user, store, draft, conversation_id, history):
    original = owned(store, user, draft.target_id) if draft.target_id else None
    if original:
        revision(original, draft.revision)
    if draft.presentation_tile_id and draft.clarifications:
        reply = draft.clarifications[-1].reply
        kind = presentation_choice(reply)
        if kind:
            draft.presentation_choices[draft.presentation_tile_id] = kind
    if draft.operation in {'create', 'rebuild'}:
        doc = await build(request, user, description=draft.description, scope=draft.scope,
                          clarifications=draft.clarifications, presentation_choices=draft.presentation_choices)
        if original:
            doc.id, doc.created_at = original.id, original.created_at
    else:
        doc = original.model_copy(deep=True)
        if draft.edit:
            doc = DashboardDocument.model_validate(doc.model_dump() | draft.edit.model_dump(exclude={'revision'}, exclude_unset=True))
        doc.scope, doc.clarifications = draft.scope, draft.clarifications
        for tile in doc.tiles:
            if tile.id in draft.presentation_choices:
                tile.kind = draft.presentation_choices[tile.id]
                if tile.kind == 'table':
                    tile.measures, tile.dimension = [], None
        doc = await build(request, user, document=doc)
    pending = next((result for result in doc.results if result.status == 'clarification_required'), None)
    if pending:
        draft.question = pending.message or 'Please clarify the metric, grouping and period you want.'
        return pause_draft(draft, conversation_id, history)
    chart_question = presentation_clarification(doc)
    if chart_question:
        draft.presentation_tile_id, draft.question = chart_question
        return pause_draft(draft, conversation_id, history)
    failure = next((result for result in doc.results if result.status == 'failed'), None)
    if failure and not any(result.status in {'complete', 'empty'} for result in doc.results):
        # Preserve a draft for retry when no dataset executed successfully.
        can_reply = len(draft.clarifications) < 3
        history[:] = [{'draft': draft.model_dump_json()}] if draft.question and can_reply else []
        return JSONResponse({'status': 'failed', 'message': failure.message or 'The data query could not complete. Try again.',
            'scope': draft.scope, 'description': draft.description,
            'conversation_id': conversation_id if history else None, 'can_reply': can_reply}, headers={'Cache-Control': 'no-store'})
    result = bundle(persist(store, user, doc, original.revision if original else None), 200 if original else 201)
    history.clear()
    return result


async def start_draft(request, user, store, conversations, draft, *, question=None):
    identifier = uuid4().hex
    identity = _agent_request(user, draft.description, conversation_id=identifier)
    async with conversations.session(identity) as history:
        if question is not None:
            draft.question = question
            return pause_draft(draft, identifier, history)
        return await run_draft(request, user, store, draft, identifier, history)


@router.get('')
async def list_dashboards(user=Depends(principal), store=Depends(get_store)):
    return JSONResponse({'dashboards': store.list(user['sub'])}, headers={'Cache-Control': 'no-store'})


@router.post('', dependencies=[Depends(_require_same_origin)])
async def create_dashboard(body: BuildRequest, request: Request, user=Depends(principal), store=Depends(get_store), conversations=Depends(get_conversations)):
    if not body.conversation_id:
        return await start_draft(request, user, store, conversations, PendingDashboard(description=body.description, scope=body.scope))
    identity = _agent_request(user, body.description, conversation_id=body.conversation_id)
    async with conversations.session(identity) as history:
        if not history:
            raise HTTPException(409, 'This clarification expired or is unavailable in this session. Start a new dashboard request.')
        draft = PendingDashboard.model_validate_json(history[-1]['draft'])
        if len(draft.clarifications) >= 3:
            return pause_draft(draft, body.conversation_id, history)
        if 'scope' in body.model_fields_set and body.scope != draft.scope:
            raise HTTPException(422, 'Keep the original scope while clarifying, or start a new dashboard request.')
        draft.clarifications.append(ClarificationTurn(question=draft.question, reply=body.description))
        return await run_draft(request, user, store, draft, body.conversation_id, history)


@router.get('/{identifier}')
async def get_dashboard(identifier: str, request: Request, user=Depends(principal), store=Depends(get_store), conversations=Depends(get_conversations)):
    doc = owned(store, user, identifier)
    pending = next((result for result in doc.results if result.status == 'clarification_required'), None)
    if pending:
        return await start_draft(request, user, store, conversations,
            PendingDashboard(description=doc.description, scope=doc.scope, operation='rebuild',
                target_id=doc.id, revision=doc.revision, clarifications=doc.clarifications),
            question=pending.message or 'Please clarify the dashboard you want.')
    return bundle(doc)


@router.patch('/{identifier}', dependencies=[Depends(_require_same_origin)])
async def edit_dashboard(identifier: str, body: DashboardEdit, request: Request, user=Depends(principal), store=Depends(get_store), conversations=Depends(get_conversations)):
    doc = owned(store, user, identifier)
    revision(doc, body.revision)
    try:
        updated = DashboardDocument.model_validate(doc.model_dump() | body.model_dump(exclude={'revision'}, exclude_unset=True))
    except ValueError:
        raise HTTPException(422, 'Tile identifiers and dataset references must be valid and unique.')
    if updated.scope != doc.scope:
        return await start_draft(request, user, store, conversations, PendingDashboard(
            description=doc.description, scope=updated.scope, operation='edit', target_id=doc.id,
            revision=doc.revision, edit=body, clarifications=doc.clarifications))
    return bundle(persist(store, user, updated, doc.revision))


@router.post('/{identifier}/refresh', dependencies=[Depends(_require_same_origin)])
async def refresh_dashboard(identifier: str, body: RefreshRequest, request: Request, user=Depends(principal), store=Depends(get_store), conversations=Depends(get_conversations)):
    doc = owned(store, user, identifier)
    revision(doc, body.revision)
    scope = doc.scope if body.scope is None else body.scope
    return await start_draft(request, user, store, conversations, PendingDashboard(
        description=body.description if body.description is not None else doc.description,
        scope=scope, target_id=doc.id, revision=doc.revision,
        operation='rebuild' if body.description is not None else 'refresh',
        clarifications=doc.clarifications if body.description is None or body.description == doc.description else []))


@router.get('/{identifier}/html')
async def get_html(identifier: str, download: bool = False, user=Depends(principal), store=Depends(get_store)):
    doc = owned(store, user, identifier)
    headers = {'Cache-Control': 'no-store', 'Content-Security-Policy': CSP + '; sandbox',
               'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer'}
    if download:
        headers['Content-Disposition'] = f'attachment; filename="dashboard-{doc.id}.html"'
    return HTMLResponse(render_dashboard(doc), headers=headers)


@router.delete('/{identifier}', dependencies=[Depends(_require_same_origin)])
async def delete_dashboard(identifier: str, revision_number: int = Query(alias='revision', ge=1), user=Depends(principal), store=Depends(get_store)):
    doc = owned(store, user, identifier)
    revision(doc, revision_number)
    try:
        store.delete(user['sub'], identifier, revision_number)
    except Conflict as error:
        raise HTTPException(409, str(error))
    return JSONResponse({'deleted': True}, headers={'Cache-Control': 'no-store'})
