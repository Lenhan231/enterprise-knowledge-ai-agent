"""Authenticated saved dashboard workspace; no client-authored SQL or HTML."""
import asyncio
from functools import lru_cache
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse

from app.agents import _agent_request, _get_runtime
from app.security import require_permission, _require_same_origin
from core.dashboards.agent import DashboardDocumentAgent
from core.dashboards.models import BuildRequest, DashboardEdit, DashboardDocument, RefreshRequest
from core.dashboards.render import CSP, render_dashboard
from core.dashboards.store import DashboardStore, Conflict

router = APIRouter(prefix='/api/dashboards', tags=['dashboards'])
principal = require_permission('view_analytics')
logger = logging.getLogger(__name__)
_build_slots = asyncio.Semaphore(2)


@lru_cache(maxsize=1)
def get_store():
    return DashboardStore()


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


async def build(request, user, *, description=None, scope='', document=None, rescope=False):
    runtime = await _get_runtime(request.app)
    agent = DashboardDocumentAgent(runtime.analytics_agent.sql_agent)
    identity = _agent_request(user, description or document.description)
    try:
        async with asyncio.timeout(190):
            async with _build_slots:
                if description is not None:
                    return await agent.build(identity, description, scope)
                return await agent.refresh(identity, document, rescope=rescope)
    except TimeoutError:
        raise HTTPException(504, 'Dashboard build timed out. Try fewer datasets.')
    except ValueError as error:
        raise HTTPException(422, str(error))
    except Exception:
        logger.exception('Dashboard composition failed')
        raise HTTPException(503, 'Dashboard planning is unavailable. Check the SQL provider and data connection, then retry.')


def persist(store, user, doc, expected=None):
    try:
        return store.save(user['sub'], doc, expected)
    except Conflict as error:
        raise HTTPException(409, str(error))
    except ValueError as error:
        raise HTTPException(422, str(error))


@router.get('')
async def list_dashboards(user=Depends(principal), store=Depends(get_store)):
    return JSONResponse({'dashboards': store.list(user['sub'])}, headers={'Cache-Control': 'no-store'})


@router.post('', dependencies=[Depends(_require_same_origin)])
async def create_dashboard(body: BuildRequest, request: Request, user=Depends(principal), store=Depends(get_store)):
    doc = await build(request, user, description=body.description, scope=body.scope)
    return bundle(persist(store, user, doc), 201)


@router.get('/{identifier}')
async def get_dashboard(identifier: str, user=Depends(principal), store=Depends(get_store)):
    return bundle(owned(store, user, identifier))


@router.patch('/{identifier}', dependencies=[Depends(_require_same_origin)])
async def edit_dashboard(identifier: str, body: DashboardEdit, request: Request, user=Depends(principal), store=Depends(get_store)):
    doc = owned(store, user, identifier)
    revision(doc, body.revision)
    try:
        updated = DashboardDocument.model_validate(doc.model_dump() | body.model_dump(exclude={'revision'}, exclude_unset=True))
    except ValueError:
        raise HTTPException(422, 'Tile identifiers and dataset references must be valid and unique.')
    if updated.scope != doc.scope:
        updated = await build(request, user, document=updated, rescope=True)
    return bundle(persist(store, user, updated, doc.revision))


@router.post('/{identifier}/refresh', dependencies=[Depends(_require_same_origin)])
async def refresh_dashboard(identifier: str, body: RefreshRequest, request: Request, user=Depends(principal), store=Depends(get_store)):
    doc = owned(store, user, identifier)
    revision(doc, body.revision)
    scope = doc.scope if body.scope is None else body.scope
    if body.description is not None:
        updated = await build(request, user, description=body.description, scope=scope)
        updated.id, updated.created_at = doc.id, doc.created_at
    else:
        scope_changed = doc.scope != scope
        doc.scope = scope
        updated = await build(request, user, document=doc, rescope=scope_changed)
    return bundle(persist(store, user, updated, body.revision))


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
