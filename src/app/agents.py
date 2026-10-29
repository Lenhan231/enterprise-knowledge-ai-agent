"""Authenticated API routes for the four-agent runtime."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from time import perf_counter
from typing import Literal

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.security import ROLE_PERMISSIONS, require_permission
from core.latency import latency_events, snapshot

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agents", tags=["agents"])
_runtime_lock = asyncio.Lock()


class AgentChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2_000)
    agent_mode: Literal["auto", "knowledge", "sql", "dashboard", "agentic", "report"] = "agentic"
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
        if len(value) > 20:
            raise ValueError("Metadata cannot exceed 20 fields")
        return value


async def _get_runtime(application):
    runtime = getattr(application.state, "agent_router", None)
    if runtime is not None:
        return runtime
    async with _runtime_lock:
        runtime = getattr(application.state, "agent_router", None)
        if runtime is not None:
            return runtime
        from core.agents.analytics_agent import AnalyticsAgent
        from core.agents.dashboard_agent import InventoryDashboardAgent
        from core.agents.main import _FallbackClassifier, _LazyKnowledgeAgent
        from core.agents.report_agent import ReportAgent
        from core.agents.router import AgentRouter
        from core.agents.sql_analytics_agent import SQLAnalyticsAgent
        from core.database.commerce_repository import LazyCommerceRepository

        load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
        repository = LazyCommerceRepository()
        knowledge = _LazyKnowledgeAgent()
        analytics = AnalyticsAgent(SQLAnalyticsAgent(repository))
        runtime = AgentRouter(
            _FallbackClassifier(), knowledge, analytics,
            dashboard_agent=InventoryDashboardAgent(repository),
            report_agent=ReportAgent(knowledge, analytics.sql_agent),
        )
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


def _record_agent_run(**event):
    from core.database.agent_run_repository import AgentRunRepository

    repository = None
    try:
        repository = AgentRunRepository()
        repository.record_event(**event)
    except Exception:
        logger.exception("Could not record agent run telemetry")
    finally:
        if repository is not None:
            try:
                repository.close()
            except Exception:
                logger.exception("Could not close agent telemetry connection")


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
        report_status = result.metadata.get("status") if result.agent == "report" else None
        status = "failed" if report_status in {"partial", "failed", "clarification_required"} else "completed"
        error_type = {"partial": "ReportPartial", "failed": "ReportFailed",
                      "clarification_required": "ReportClarificationRequired"}.get(report_status)
        citation_count = len(result.evidence)
        return result
    except PermissionError as error:
        error_type = type(error).__name__
        raise HTTPException(403, "Your role cannot access Commerce analytics") from None
    except Exception as error:
        error_type = type(error).__name__
        logger.exception("Agent request failed")
        raise HTTPException(503, "The agent service is unavailable") from error
    finally:
        timing = snapshot()
        timing["request_total_ms"] = (perf_counter() - started) * 1000
        latency_events.reset(timing_token)
        if result is not None:
            result.metadata["latency"] = timing
        logger.warning("agent_latency %s", json.dumps({"agent": agent_name, "status": status, **timing}))
        await asyncio.to_thread(
            _record_agent_run,
            actor_role=user["role"], agent_name=agent_name,
            retrieval_method=retrieval_method, status=status,
            elapsed_ms=max(0, int((perf_counter() - started) * 1000)),
            citation_count=citation_count, error_type=error_type,
        )


@router.post("/report")
async def generate_agent_report(
    http_request: Request, question: str = Form(...), template: UploadFile | None = File(None),
    source_mode: Literal["documents", "analytics", "combined"] = Form("documents"),
    output_format: Literal["markdown", "docx"] | None = Form(None),
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
        agent_request = _agent_request(user, AgentChatRequest(question=question).question)
        from core.reports.sources import authorize_sources
        from core.reports.http import report_response
        authorize_sources(agent_request, source_mode)
        runtime = await _get_runtime(http_request.app)
        filename = Path(template.filename or "").name if template else None
        result, output, media_type = await runtime.report_agent.generate_from_template(
            agent_request, filename, content, source_mode=source_mode, output_format=output_format)
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
        await asyncio.to_thread(
            _record_agent_run,
            actor_role=user["role"], agent_name="report", retrieval_method="hybrid",
            status="completed" if status == "complete" else "failed",
            elapsed_ms=max(0, int((perf_counter() - started) * 1000)),
            citation_count=citation_count, error_type="ReportPartial" if status == "partial" else error_type,
        )
