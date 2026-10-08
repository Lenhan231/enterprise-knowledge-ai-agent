from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ConfigDict, Field, field_validator

from core.agents.analytics_agent import AnalyticsAgent
from core.agents.sql_analytics_agent import SQLAnalyticsAgent
from core.database.commerce_repository import create_repository_from_env
from core.models.agents import AgentRequest, AgentResult


LOGGER = logging.getLogger(__name__)
APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parents[1]
STATIC_DIR = APP_DIR / "static"


class ChatRequest(AgentRequest):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2_000)
    user_id: str | None = Field(default=None, max_length=128)
    conversation_id: str | None = Field(default=None, max_length=128)

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


def create_app(*, chat_agent: Any | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        runtime_agent = chat_agent
        owns_agent = runtime_agent is None
        if runtime_agent is None:
            load_dotenv(REPO_ROOT / ".env", override=False)
            repository = await create_repository_from_env()
            runtime_agent = AnalyticsAgent(SQLAnalyticsAgent(repository))
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
    application.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @application.get("/", include_in_schema=False)
    async def home() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.post("/api/chat", response_model=AgentResult)
    async def chat(payload: ChatRequest, request: Request) -> AgentResult:
        try:
            result = await request.app.state.chat_agent.run(
                AgentRequest.model_validate(payload.model_dump())
            )
            return AgentResult.model_validate(result)
        except Exception as error:
            LOGGER.error("api_chat_failed error_type=%s", type(error).__name__)
            raise HTTPException(
                status_code=503,
                detail="Hệ thống tạm thời không thể xử lý yêu cầu.",
            ) from None

    return application


app = create_app()
