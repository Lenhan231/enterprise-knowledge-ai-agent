"""A report-only library, with server-owned facts and editable presentation."""
import asyncio
from datetime import date, timedelta
import logging
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import JSONResponse, Response
from pydantic import Field

from app.agents import _agent_request, _get_runtime
from app.security import require_permission, _require_same_origin
from core.agents.dashboard.models import StrictModel
from core.agents.dashboard.store import Conflict, StoreUnavailable
from core.agents.language import is_vietnamese
from core.agents.report.document import ReportDocument, ReportEdit
from core.agents.report.labels import COMBINED_REPORT, LABELS, uses_vietnamese_labels
from core.agents.report.store import create_report_store

router = APIRouter(prefix='/api/reports', tags=['reports'])
principal = require_permission('view_analytics')
_slots = asyncio.Semaphore(2)
logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_store():
    return create_report_store()


def get_store():
    try:
        yield _get_store()
    except StoreUnavailable:
        raise HTTPException(503, 'Saved reports are temporarily unavailable. Please retry.') from None


async def owned(store, user, identifier):
    document = await asyncio.to_thread(store.get, user['sub'], identifier)
    if document is None: raise HTTPException(404, 'Report not found')
    return document


def _accessible_document_ids(identifiers, roles):
    from core.database.document_repository import DocumentRepository
    repository = DocumentRepository()
    try:
        return repository.accessible_document_ids(identifiers, roles)
    finally:
        repository.close()


async def scoped_document(document, user):
    kind = document.report['report_type']
    inventory = document.inventory_context if kind in {'inventory_operations', COMBINED_REPORT} else None
    sales = document.sales_context if kind in {'sales_performance', COMBINED_REPORT} else None
    identifiers = list(dict.fromkeys(e.metadata['document_id'] for context in (inventory, sales) if context
                                     for e in context.documents))
    if not identifiers:
        return document
    from core.agents.runtime import run_sync
    from core.agents.report.sales_context import SalesContext
    identity = _agent_request(user, 'Saved report document access').identity
    allowed = set()
    status = 'access_denied'
    if identity and 'documents:read' in identity.permissions and identity.document_roles:
        try:
            allowed = await run_sync(_accessible_document_ids,
                identifiers, sorted(identity.document_roles), _timeout=10)
        except Exception:
            status = 'unavailable'
    copy = document.model_copy(deep=True)
    if inventory and inventory.documents:
        from core.agents.report.inventory_operations import InventoryContext
        documents = [e for e in inventory.documents if e.metadata['document_id'] in allowed]
        copy.inventory_context = InventoryContext(retrieval_status='available' if documents else status, documents=documents)
        if len(documents) != len(inventory.documents):
            copy.status = 'partial'
    if sales and sales.documents:
        documents = [e for e in sales.documents if e.metadata['document_id'] in allowed]
        limited = len(documents) != len(sales.documents)
        copy.sales_context = SalesContext.model_validate({**sales.model_dump(), 'documents':documents,
            'retrieval_status':'available' if documents else status, 'access_limited':limited})
        if limited and kind == COMBINED_REPORT:
            copy.status = 'partial'
    return ReportDocument.model_validate(copy.model_dump())


async def bundle(document, user, status=200):
    document = await scoped_document(document, user)
    return JSONResponse({'document': document.model_dump(mode='json')}, status_code=status, headers={'Cache-Control': 'no-store'})


class ReportRequest(StrictModel):
    question: str = Field(min_length=3, max_length=2000)


@router.get('')
async def library(user=Depends(principal), store=Depends(get_store)):
    return JSONResponse({'reports': await asyncio.to_thread(store.list, user['sub'])}, headers={'Cache-Control': 'no-store'})


@router.post('')
async def generate(payload: ReportRequest, request: Request, user=Depends(principal), store=Depends(get_store)):
    _require_same_origin(request)
    runtime = await _get_runtime(request.app)
    identity = _agent_request(user, payload.question)
    try:
        async with _slots:
            result, _, _ = await runtime.report_agent.generate_from_template(identity, source_mode='analytics')
        if 'report' not in result.data:
            raise HTTPException(422, detail=result.answer)
        report = result.data['report']
        title = payload.question[:160]
        if uses_vietnamese_labels(report):
            scope = report['reports']['sales_performance'] if report['report_type'] == COMBINED_REPORT else report
            period = scope['request']['period']
            end = date.fromisoformat(period['end_exclusive']) - timedelta(days=1)
            title = f'{LABELS[report["report_type"]]} · {period["start"]} đến {end}'
        document = ReportDocument(report=report, monthly_decisions=result.data.get('monthly_decisions', []),
                                  sales_context=result.data.get('sales_context', {}),
                                  inventory_context=result.data.get('inventory_context', {}),
                                  title=title, status=result.metadata.get('status', 'partial'))
        document = await asyncio.to_thread(store.create, user['sub'], document)
        return await bundle(document, user, 201)
    except PermissionError:
        raise HTTPException(403, 'Verified analytics permission is required') from None
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    except HTTPException:
        raise
    except StoreUnavailable:
        raise
    except Exception:
        logger.exception('Report generation failed')
        message = ('Chưa tạo được báo cáo. Vui lòng thử lại.'
                   if is_vietnamese(payload.question) else 'The report could not be generated. Please retry.')
        raise HTTPException(503, message) from None


@router.get('/{identifier}')
async def reopen(identifier: str, user=Depends(principal), store=Depends(get_store)):
    return await bundle(await owned(store, user, identifier), user)


@router.put('/{identifier}')
async def edit(identifier: str, payload: ReportEdit, request: Request, user=Depends(principal), store=Depends(get_store)):
    _require_same_origin(request)
    document = await owned(store, user, identifier)
    document.title, document.presentation = payload.title, payload.presentation
    try:
        return await bundle(await asyncio.to_thread(store.save, user['sub'], document, payload.revision), user)
    except Conflict as error:
        raise HTTPException(409, str(error)) from None
    except ValueError as error:
        raise HTTPException(422, str(error)) from None


@router.delete('/{identifier}')
async def delete(identifier: str, request: Request, revision: int = Query(ge=1), user=Depends(principal), store=Depends(get_store)):
    _require_same_origin(request)
    await owned(store, user, identifier)
    try:
        await asyncio.to_thread(store.delete, user['sub'], identifier, revision)
    except Conflict as error:
        raise HTTPException(409, str(error)) from None
    return Response(status_code=204)


@router.get('/{identifier}/pdf')
async def download(identifier: str, revision: int | None = Query(None, ge=1), user=Depends(principal), store=Depends(get_store)):
    from core.agents.report.export import export_pdf
    document = await owned(store, user, identifier)
    if revision is not None and revision != document.revision:
        raise HTTPException(409, 'Report changed. Reopen it before downloading.')
    document = await scoped_document(document, user)
    return Response(await asyncio.to_thread(export_pdf, document), media_type='application/pdf',
                    headers={'Content-Disposition': f'attachment; filename="{document.report["report_type"].replace("_", "-")}-report.pdf"', 'Cache-Control': 'no-store'})
