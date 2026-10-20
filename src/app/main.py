from __future__ import annotations

import logging
import os
import re
import inspect
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.agents.analytics_agent import AnalyticsAgent
from core.agents.intent_classifier import IntentClassifier
from core.agents.knowledge_agent import KnowledgeAgent
from core.agents.router import AgentRouter
from core.agents.sql_analytics_agent import AnalyticsPermissionDenied, SQLAnalyticsAgent
from core.database.commerce_repository import create_repository_from_env
from core.models.agents import AgentRequest, AgentResult, VerifiedIdentity


LOGGER = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[2]


def _local_development_identity() -> VerifiedIdentity | None:
    """Return an explicitly opted-in local identity; never use this in production."""
    if os.getenv("APP_ENV", "").casefold() != "development":
        return None
    if os.getenv("ALLOW_DEV_ANALYTICS", "").casefold() != "true":
        return None
    subject = os.getenv("DEV_ANALYTICS_IDENTITY", "").strip()
    if not subject:
        return None
    return VerifiedIdentity(subject=subject, permissions={"analytics:read"})


class _FallbackClassifier:
    """Use the local deterministic classifier for the chat entrypoint."""

    @staticmethod
    def classify(question: str):
        intent = IntentClassifier.fallback(question)
        text = question.casefold()
        if intent.needs_knowledge and any(term in text for term in
                ("chính sách", "quy trình", "tài liệu", "policy", "procedure", "document")) and not (
                re.search(r"\b(?:19|20)\d{2}\b", text) or
                any(term in text for term in ("bao nhiêu", "so sánh", "tính toán", "thống kê"))):
            return intent.model_copy(update={"intent": "knowledge", "needs_sql": False,
                                             "needs_knowledge": True})
        return intent


class _LazyKnowledgeAgent:
    def __init__(self) -> None:
        self.agent: KnowledgeAgent | None = None

    async def run(self, request: AgentRequest) -> AgentResult:
        if self.agent is None:
            self.agent = KnowledgeAgent()
        return await self.agent.run(request)

    async def close(self) -> None:
        if self.agent is not None:
            await self.agent.close()


class _UnsupportedRoute:
    async def run(self, _request: AgentRequest) -> AgentResult:
        return AgentResult(answer="Loại yêu cầu này chưa được hỗ trợ trong trò chuyện.",
                           agent="unsupported", metadata={"ok": False})


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2_000)
    agent_mode: Literal["auto", "knowledge", "sql", "agentic"] = "auto"
    conversation_id: str | None = Field(default=None, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Câu hỏi không được để trống")
        return normalized

    @field_validator("metadata")
    @classmethod
    def bound_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(value) > 20:
            raise ValueError("metadata không được vượt quá 20 trường")
        return value


def create_app(*, chat_agent: Any | None = None, commerce_repository: Any | None = None,
               knowledge_agent: Any | None = None, classifier: Any | None = None,
               identity_resolver: Any | None = None, llm: Any | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        runtime_agent = chat_agent
        owns_agent = runtime_agent is None
        if runtime_agent is None:
            load_dotenv(REPO_ROOT / ".env", override=False)
            repository = commerce_repository or await create_repository_from_env()
            knowledge = knowledge_agent or _LazyKnowledgeAgent()
            analytics_agent = AnalyticsAgent(SQLAnalyticsAgent(repository, llm=llm))
            runtime_agent = AgentRouter(
                classifier or _FallbackClassifier(), knowledge, analytics_agent,
                dashboard_agent=_UnsupportedRoute(),
            )
        application.state.chat_agent = runtime_agent
        try:
            yield
        finally:
            if owns_agent:
                await runtime_agent.close()

    application = FastAPI(
        title="Trợ lý tri thức doanh nghiệp",
        version="0.1.0",
        lifespan=lifespan,
    )
    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.post("/api/chat", response_model=AgentResult)
    async def chat(payload: ChatRequest, request: Request) -> AgentResult:
        try:
            identity = None
            if identity_resolver is not None:
                identity = identity_resolver(request)
                if inspect.isawaitable(identity):
                    identity = await identity
            else:
                identity = getattr(request.state, "verified_identity", None)
                if identity is None:
                    identity = _local_development_identity()
            if identity is not None and not isinstance(identity, VerifiedIdentity):
                raise AnalyticsPermissionDenied("Request identity was not verified")
            agent_request = AgentRequest(
                question=payload.question,
                conversation_id=payload.conversation_id,
                metadata=payload.metadata,
                user_id=identity.subject if identity else None,
                identity=identity,
            )
            chat_agent = request.app.state.chat_agent
            if payload.agent_mode == "auto":
                result = await chat_agent.run(agent_request)
            else:
                result = await chat_agent.run_mode(agent_request, payload.agent_mode)
            return AgentResult.model_validate(result)
        except AnalyticsPermissionDenied:
            raise HTTPException(
                status_code=403,
                detail="Bạn không có quyền truy cập dữ liệu phân tích.",
            ) from None
        except Exception as error:
            LOGGER.error("api_chat_failed error_type=%s", type(error).__name__)
            raise HTTPException(
                status_code=503,
                detail="Hệ thống tạm thời không thể xử lý yêu cầu.",
            ) from None

    return application


app = create_app()
