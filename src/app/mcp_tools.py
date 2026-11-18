"""Authenticated, read-only MCP tools for the existing agent runtime."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.security import _current_user
from core.agents.decision_support.execution import authorize
from core.models.agents import AgentRequest

logger = logging.getLogger(__name__)
MCP_QUERY_TIMEOUT_SECONDS = 60
MCP_SEARCH_TIMEOUT_SECONDS = 30


def _transport_security() -> TransportSecuritySettings:
    hosts = {"localhost", "127.0.0.1", "testserver"}
    hosts.update(value.strip() for value in os.getenv("MCP_ALLOWED_HOSTS", "").split(",") if value.strip())
    origins = {value.strip().rstrip("/") for value in os.getenv("TRUSTED_FRONTEND_ORIGINS", "").split(",")
               if value.strip()}
    return TransportSecuritySettings(allowed_hosts=sorted(hosts), allowed_origins=sorted(origins))


class SessionAuthASGI:
    """Authenticate every MCP HTTP exchange with the app's existing session JWT."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive)
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        credentials = (HTTPAuthorizationCredentials(scheme=scheme, credentials=token)
                       if scheme.casefold() == "bearer" and token else None)
        try:
            user = _current_user(request, credentials)
        except HTTPException as error:
            response = JSONResponse({"detail": error.detail}, status_code=error.status_code)
            await response(scope, receive, send)
            return
        scope.setdefault("state", {})["mcp_user"] = user
        await self.app(scope, receive, send)


_host_app = None
server = FastMCP(
    "enterprise-knowledge-agent",
    instructions="Authenticated read-only tools for authorized enterprise documents and Commerce analytics.",
    streamable_http_path="/",
    stateless_http=True,
    json_response=True,
    transport_security=_transport_security(),
)


def configure_host_app(app) -> ASGIApp:
    global _host_app
    _host_app = app
    return SessionAuthASGI(server.streamable_http_app())


def _request_and_user(ctx: Context) -> tuple[Request, dict[str, Any]]:
    request = ctx.request_context.request
    if not isinstance(request, Request):
        raise PermissionError("An authenticated HTTP session is required")
    user = request.scope.get("state", {}).get("mcp_user")
    if not isinstance(user, dict):
        raise PermissionError("An authenticated HTTP session is required")
    return request, user


def _agent_request(user: dict[str, Any], question: str) -> AgentRequest:
    from app.agents import _agent_request as create_request

    return create_request(user, question)


async def _runtime():
    if _host_app is None:
        raise RuntimeError("MCP host application is not configured")
    from app.agents import _get_runtime

    return await _get_runtime(_host_app)


@server.tool()
async def get_commerce_schema(ctx: Context) -> dict[str, list[str]]:
    """List Commerce tables and columns available to the analytics agent."""
    _, user = _request_and_user(ctx)
    request = _agent_request(user, "List the approved Commerce analytics schema")
    authorize(request, "sql")
    runtime = await _runtime()
    sql_agent = runtime.analytics_agent
    table_columns = getattr(sql_agent, "table_columns", None)
    if not isinstance(table_columns, dict):
        raise RuntimeError("The analytics schema is unavailable")
    return {str(table): sorted(map(str, columns)) for table, columns in sorted(table_columns.items())}


@server.tool()
async def query_commerce_readonly(question: str, ctx: Context) -> dict[str, Any]:
    """Answer an analytics question using the approved read-only Commerce SQL agent."""
    _, user = _request_and_user(ctx)
    request = _agent_request(user, question)
    authorize(request, "sql")
    try:
        async with asyncio.timeout(MCP_QUERY_TIMEOUT_SECONDS):
            result = await (await _runtime()).analytics_agent.run(request)
    except PermissionError:
        raise
    except Exception as error:
        logger.warning("MCP Commerce query failed: %s", type(error).__name__)
        raise RuntimeError("Commerce query could not be completed") from None
    return result.model_dump(mode="json")


@server.tool()
async def search_documents(query: str, ctx: Context) -> list[dict[str, Any]]:
    """Search enterprise documents within the caller's assigned document role."""
    _, user = _request_and_user(ctx)
    request = _agent_request(user, query)
    authorize(request, "knowledge")
    try:
        async with asyncio.timeout(MCP_SEARCH_TIMEOUT_SECONDS):
            evidence = await (await _runtime()).knowledge_agent.retrieve(request)
    except PermissionError:
        raise
    except Exception as error:
        logger.warning("MCP document search failed: %s", type(error).__name__)
        raise RuntimeError("Document search could not be completed") from None
    return [item.model_dump(mode="json") for item in evidence]
