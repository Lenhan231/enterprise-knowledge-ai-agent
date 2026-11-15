"""HTTP client implementing the local retrieval-service contract."""

from __future__ import annotations

import os
import contextvars
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from core.retrieval.retrieval import RetrievalRequest, RetrievalResponse
from core.services.client import post

remote_session_context = contextvars.ContextVar("remote_retrieval_session", default=None)


class RemoteRetrievalService:
    def __init__(self, url: str | None = None) -> None:
        self.url = (url or os.getenv("RETRIEVAL_SERVICE_URL", "")).rstrip("/")
        if not self.url:
            raise ValueError("RETRIEVAL_SERVICE_URL is required")

    def retrieve(
        self,
        request: RetrievalRequest,
        company: str | None = None,
        roles: list[str] | None = None,
        method: str = "translated_hybrid_rerank",
        dense_weight: float = 1.0,
        bm25_weight: float = 2.0,
        rrf_k: int = 60,
        document_ids: list[str] | None = None,
        metadata_filter: dict | None = None,
        query_language: str = "auto",
        document_languages: dict[str, str] | None = None,
    ) -> RetrievalResponse:
        if not roles:
            raise PermissionError("Role-scoped retrieval requires verified document roles")
        payload = {
            "query": request.query,
            "top_k": request.top_k,
            "company": company,
            "roles": roles,
            "method": method,
            "dense_weight": dense_weight,
            "bm25_weight": bm25_weight,
            "rrf_k": rrf_k,
            "document_ids": document_ids,
            "metadata_filter": metadata_filter,
            "query_language": query_language,
            "document_languages": document_languages,
        }
        timeout = float(os.getenv("RETRIEVAL_SERVICE_TIMEOUT_SECONDS", "90"))
        if os.getenv("RETRIEVAL_SERVICE_AUTH", "internal") == "session":
            return self._retrieve_with_session(payload, timeout)
        result = post(self.url, "/retrieve", payload, timeout=timeout)
        return RetrievalResponse.model_validate(result)

    def _retrieve_with_session(self, payload: dict, timeout: float) -> RetrievalResponse:
        context = remote_session_context.get()
        if not context or not context.get("token"):
            raise PermissionError("A remote retrieval session is required")
        parsed = urlsplit(self.url)
        if parsed.path.rstrip("/") != "/api/retrieval" or parsed.scheme != "https":
            raise ValueError("Session-authenticated retrieval requires an HTTPS /api/retrieval URL")
        origin = f"{parsed.scheme}://{parsed.netloc}"
        headers = {"Authorization": "Bearer " + context["token"]}
        try:
            with urlopen(Request(origin + "/api/auth/me", headers=headers), timeout=timeout) as response:
                identity = json.loads(response.read())
            if (identity.get("username") != context.get("subject")
                    or identity.get("role") != context.get("role")):
                raise PermissionError("Remote retrieval account does not match the signed-in local account")
            # The remote API derives document roles from the verified session; never trust caller-supplied scope.
            safe_payload = {key: value for key, value in payload.items() if key not in {"roles", "company"}}
            request = Request(
                self.url + "/retrieve", data=json.dumps(safe_payload).encode(),
                headers={**headers, "Content-Type": "application/json"}, method="POST",
            )
            with urlopen(request, timeout=timeout) as response:
                result = json.loads(response.read())
        except HTTPError as error:
            if error.code in {401, 403}:
                raise PermissionError("Remote retrieval session was rejected") from None
            raise RuntimeError("Remote retrieval request failed") from None
        except (URLError, TimeoutError, ValueError) as error:
            raise RuntimeError("Remote retrieval service is unavailable or returned an invalid response") from error
        return RetrievalResponse.model_validate(result)

    def close(self) -> None:
        return None
