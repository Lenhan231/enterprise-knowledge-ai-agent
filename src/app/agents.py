"""Authenticated API routes for the four-agent runtime."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from pathlib import Path
from time import perf_counter
from typing import Literal

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.security import ACCESS_DENIED_MESSAGE, ROLE_PERMISSIONS, require_permission
from core.latency import latency_events, snapshot, stage_listener

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agents", tags=["agents"])
_runtime_lock = asyncio.Lock()


class AgentChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2_000)
    agent_mode: Literal["auto", "knowledge", "sql", "dashboard", "agentic", "report"] = "auto"
    retrieval_method: Literal[
        "dense", "bm25", "hybrid", "parent", "translated_hybrid", "translated_hybrid_rerank",
    ] = "translated_hybrid_rerank"
    conversation_id: str | None = Field(default=None, max_length=128)
    metadata: dict = Field(default_factory=dict)

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Question cannot be empty")
        return value.strip()

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict) -> dict:
        from core.models.agents import validate_chat_metadata
        return validate_chat_metadata(value)


async def _get_runtime(application):
    runtime = getattr(application.state, "agent_router", None)
    if runtime is not None:
        return runtime
    async with _runtime_lock:
        runtime = getattr(application.state, "agent_router", None)
        if runtime is not None:
            return runtime
        from core.sql_agent.analytics_agent import AnalyticsAgent
        from core.agents.dashboard_agent import InventoryDashboardAgent
        from core.agents.main import _FallbackClassifier, _LazyKnowledgeAgent
        from core.agents.report_agent import ReportAgent
        from core.agents.router import AgentRouter
        from core.sql_agent.agent import SQLAnalyticsAgent
        from core.database.commerce_repository import LazyCommerceRepository

        load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
        repository = LazyCommerceRepository()
        knowledge = _LazyKnowledgeAgent()
        analytics = AnalyticsAgent(SQLAnalyticsAgent(
            repository, metric_retriever=knowledge.retrieve_metric_definition,
        ))
        runtime = AgentRouter(
            _FallbackClassifier(), knowledge, analytics,
            dashboard_agent=InventoryDashboardAgent(repository),
            report_agent=ReportAgent(knowledge, analytics.sql_agent),
        )
        runtime.report_agent.source_router = runtime
        application.state.agent_router = runtime
        return runtime


def _agent_request(user: dict, question: str, **values):
    from core.models.agents import AgentRequest, VerifiedIdentity

    permissions = {"analytics:read"} if "view_analytics" in ROLE_PERMISSIONS[user["role"]] else set()
    if "ask_documents" in ROLE_PERMISSIONS[user["role"]]:
        permissions.add("documents:read")
    identity = VerifiedIdentity(subject=user["sub"], permissions=frozenset(permissions),
                                document_roles={user["role"]} if "documents:read" in permissions else set())
    return AgentRequest(question=question, user_id=user["sub"], identity=identity, **values)


_telemetry_repository = None
_telemetry_lock = threading.Lock()


def _record_agent_run(**event):
    """Insert on one reused connection; a failed connection is dropped and reopened on the next event."""
    global _telemetry_repository
    from core.database.agent_run_repository import AgentRunRepository

    with _telemetry_lock:
        try:
            if _telemetry_repository is None:
                _telemetry_repository = AgentRunRepository()
            _telemetry_repository.record_event(**event)
        except Exception:
            logger.exception("Could not record agent run telemetry")
            if _telemetry_repository is not None:
                try:
                    _telemetry_repository.close()
                except Exception:
                    logger.exception("Could not close agent telemetry connection")
                _telemetry_repository = None


def _record_in_background(**event):
    # Supabase is ~0.4 s per round trip from the VPS; the user should not wait for the insert.
    # The loop's default executor is joined on shutdown, so a clean stop still writes the row.
    asyncio.get_running_loop().run_in_executor(None, lambda: _record_agent_run(**event))


@router.post("/chat")
async def agent_chat(
    payload: AgentChatRequest, http_request: Request,
    user: dict = Depends(require_permission("ask_documents")),
):
    started = perf_counter()
    timing_token = latency_events.set([])
    result = None
    agent_name = payload.agent_mode
    retrieval_method = payload.retrieval_method
    if retrieval_method not in {"dense", "bm25", "hybrid", "parent"}:
        retrieval_method = "hybrid"
    status = "failed"
    error_type = "RequestFailed"
    citation_count = 0
    try:
        runtime = await _get_runtime(http_request.app)
        agent_request = _agent_request(
            user, payload.question, conversation_id=payload.conversation_id,
            metadata={**payload.metadata, "retrieval_method": payload.retrieval_method},
        )
        if payload.agent_mode == "auto":
            result = await runtime.run(agent_request)
        else:
            result = await runtime.run_mode(agent_request, payload.agent_mode)
        agent_name = result.agent
        report_status = result.metadata.get("status")
        status = "failed" if report_status in {"partial", "failed", "clarification_required"} or not result.metadata.get("ok", True) else "completed"
        prefix = 'Report' if result.agent == 'report' else 'Agent'
        error_type = {"partial": prefix + "Partial", "failed": prefix + "Failed",
                      "clarification_required": prefix + "ClarificationRequired"}.get(report_status)
        if status == "failed" and error_type is None:
            error_type = "InsufficientContext" if result.metadata.get("insufficient_context") else prefix + "Failed"
        citation_count = len(result.evidence)
        return result
    except PermissionError as error:
        error_type = type(error).__name__
        raise HTTPException(403, ACCESS_DENIED_MESSAGE) from None
    except Exception as error:
        error_type = type(error).__name__
        logger.exception("Agent request failed")
        raise HTTPException(503, "The agent service is unavailable") from error
    finally:
        handler_ms = (perf_counter() - started) * 1000
        try:
            _record_in_background(
                actor_role=user["role"], agent_name=agent_name,
                retrieval_method=retrieval_method, status=status,
                elapsed_ms=max(0, int(handler_ms)),
                citation_count=citation_count, error_type=error_type,
            )
        finally:
            timing = snapshot()
            timing["request_total_ms"] = handler_ms
            timing["response_ready_ms"] = (perf_counter() - started) * 1000
            latency_events.reset(timing_token)
            if result is not None:
                result.metadata["latency"] = timing
            logger.warning("agent_latency %s", json.dumps({"agent": agent_name, "status": status, **timing}))


class AnswerFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rating: Literal["up", "down"]
    question: str = Field(min_length=1, max_length=2_000)
    answer: str = Field(min_length=1, max_length=20_000)
    agent: str = Field(default="unknown", max_length=40)
    comment: str | None = Field(default=None, max_length=1_000)
    claim_status: str | None = Field(default=None, max_length=40)


def _record_feedback(**values):
    from core.database.answer_feedback_repository import AnswerFeedbackRepository

    repository = AnswerFeedbackRepository()
    try:
        repository.record(**values)
    finally:
        repository.close()


@router.post("/feedback")
async def answer_feedback(payload: AnswerFeedbackRequest,
                          user: dict = Depends(require_permission("ask_documents"))):
    try:
        await asyncio.to_thread(
            _record_feedback, actor_role=user["role"], agent_name=payload.agent, rating=payload.rating,
            question=payload.question, answer=payload.answer, comment=(payload.comment or "").strip() or None,
            claim_status=payload.claim_status)
    except Exception as error:
        logger.exception("Could not record answer feedback")
        raise HTTPException(503, "Feedback could not be saved") from error
    return {"saved": True}


def _sse(kind: str, data) -> str:
    return f"event: {kind}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat/stream")
async def agent_chat_stream(
    payload: AgentChatRequest, http_request: Request,
    user: dict = Depends(require_permission("ask_documents")),
):
    """Same work as /chat; streams stage progress, then the answer only after verification (never draft tokens)."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def notify(stage: str, state: str):
        # Stages run on worker threads via asyncio.to_thread, so hand events back to the loop.
        loop.call_soon_threadsafe(queue.put_nowait, _sse("stage", {"stage": stage, "state": state}))

    async def run():
        token = stage_listener.set(notify)
        try:
            result = await agent_chat(payload, http_request, user)
            await asyncio.sleep(0)  # deliver stage events already scheduled before the result
            queue.put_nowait(_sse("result", jsonable_encoder(result)))
        except HTTPException as error:
            await asyncio.sleep(0)
            queue.put_nowait(_sse("error", {"status": error.status_code, "detail": error.detail}))
        finally:
            stage_listener.reset(token)
            queue.put_nowait(None)

    task = asyncio.create_task(run())

    async def events():
        try:
            yield ": stream open\n\n"  # flushes headers so the browser knows streaming works
            while (item := await queue.get()) is not None:
                yield item
        finally:
            if not task.done():
                task.cancel()

    # X-Accel-Buffering stops Nginx from holding events until the response ends.
    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/report")
async def generate_agent_report(
    http_request: Request, question: str = Form(...), template: UploadFile | None = File(None),
    source_mode: Literal["documents", "analytics", "orchestrated", "combined"] = Form("documents"),
    output_format: Literal["markdown", "docx"] | None = Form(None),
    template_choice: Literal['uploaded', 'suggested'] | None = Form(None),
    accept_supported_scope: bool = Form(False),
    conversation_id: str | None = Form(None, max_length=128),
    user: dict = Depends(require_permission("ask_documents")),
):
    started = perf_counter()
    status = "failed"
    error_type = "RequestFailed"
    citation_count = 0
    try:
        content = await template.read(10 * 1024 * 1024 + 1) if template else None
        if content is not None and len(content) > 10 * 1024 * 1024:
            raise HTTPException(413, "Report template exceeds 10 MiB")
        agent_request = _agent_request(user, AgentChatRequest(question=question).question,
                                       conversation_id=conversation_id)
        from core.reports.sources import authorize_sources
        from core.reports.http import report_response
        authorize_sources(agent_request, source_mode)
        runtime = await _get_runtime(http_request.app)
        filename = Path(template.filename or "").name if template else None
        result, output, media_type = await runtime.report_agent.generate_from_template(
            agent_request, filename, content, source_mode=source_mode, output_format=output_format,
            template_choice=template_choice, accept_supported_scope=accept_supported_scope)
        status = result.metadata.get("status", "complete" if result.metadata.get("ok", True) else "partial")
        error_type = None
        citation_count = len(result.evidence)
        return report_response(result, output, media_type)
    except PermissionError as error:
        error_type = type(error).__name__
        raise HTTPException(403, "Verified permission for the selected report sources is required") from None
    except HTTPException as error:
        error_type = f"HTTP{error.status_code}"
        raise
    except ValueError as error:
        error_type = type(error).__name__
        raise HTTPException(422, str(error)) from None
    except Exception as error:
        error_type = type(error).__name__
        logger.exception("Report agent request failed")
        raise HTTPException(503, "The report service is unavailable") from error
    finally:
        _record_in_background(
            actor_role=user["role"], agent_name="report", retrieval_method="hybrid",
            status="completed" if status == "complete" else "failed",
            elapsed_ms=max(0, int((perf_counter() - started) * 1000)),
            citation_count=citation_count, error_type="ReportPartial" if status == "partial" else error_type,
        )
