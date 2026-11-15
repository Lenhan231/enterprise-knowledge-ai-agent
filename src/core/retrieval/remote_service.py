"""HTTP client implementing the local retrieval-service contract."""

from __future__ import annotations

import os
import contextvars
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from core.latency import STAGES, latency_events, stage_listener
from core.retrieval.retrieval import RetrievalRequest, RetrievalResponse

remote_session_context = contextvars.ContextVar("remote_retrieval_session", default=None)
_MAX_RESPONSE_BYTES = 64 * 1024 * 1024  # same cap as core.services.client.post


def _elapsed(event: dict) -> float | None:
    try:
        return max(0.0, float(event.get("elapsed_ms") or 0))
    except (TypeError, ValueError):
        return None


def _replay_stage_events(response: RetrievalResponse) -> RetrievalResponse:
    """Add the retrieval service's stage timings to this request's timings and progress stream."""
    events = latency_events.get()
    if events is None:
        return response  # nothing records timings here (e.g. the public proxy), so pass them on unchanged
    listener = stage_listener.get()
    for event in response.retrieval_details.pop("stage_events", None) or []:
        if not isinstance(event, dict) or event.get("stage") not in STAGES or (elapsed := _elapsed(event)) is None:
            continue
        status = "completed" if event.get("status") == "completed" else "failed"
        events.append({"stage": event["stage"], "elapsed_ms": elapsed, "status": status})
        if listener:
            listener(event["stage"], "started")
            listener(event["stage"], status)
    return response


def _post_streaming(url: str, payload: dict, timeout: float) -> RetrievalResponse:
    """Call /retrieve?stream=1 and forward each stage to this request as it happens (so the page shows it live)."""
    token = os.environ.get("INTERNAL_SERVICE_TOKEN", "")
    if not token:
        raise RuntimeError("INTERNAL_SERVICE_TOKEN is required")
    request = Request(url + "/retrieve?stream=1", data=json.dumps(payload).encode(), method="POST",
                      headers={"Content-Type": "application/json", "Authorization": "Bearer " + token})
    events, listener = latency_events.get(), stage_listener.get()
    try:
        with urlopen(request, timeout=timeout) as response:
            if "ndjson" not in response.headers.get("Content-Type", ""):
                # An older retrieval service ignores stream=1 and answers with one JSON body.
                content = response.read(_MAX_RESPONSE_BYTES + 1)
                if len(content) > _MAX_RESPONSE_BYTES:
                    raise RuntimeError("Internal service response exceeds limit")
                return _replay_stage_events(RetrievalResponse.model_validate(json.loads(content)))
            seen, received = [], 0
            for raw in response:
                received += len(raw)
                if received > _MAX_RESPONSE_BYTES:
                    raise RuntimeError("Internal service response exceeds limit")
                line = json.loads(raw)
                if "result" in line:
                    result = RetrievalResponse.model_validate(line["result"])
                    if events is None:
                        result.retrieval_details["stage_events"] = seen  # pass on, as the non-streaming path does
                    else:
                        result.retrieval_details.pop("stage_events", None)
                    return result
                if "error" in line:
                    raise RuntimeError("Internal backend service unavailable or invalid response")
                stage, state = line.get("stage"), line.get("state")
                if stage not in STAGES or state not in {"started", "completed", "failed"}:
                    continue
                if listener:
                    listener(stage, state)
                if state != "started" and (elapsed := _elapsed(line)) is not None:
                    event = {"stage": stage, "elapsed_ms": elapsed, "status": state}
                    seen.append(event)
                    if events is not None:
                        events.append(event)
    except (URLError, TimeoutError, ValueError) as error:
        raise RuntimeError("Internal backend service unavailable or invalid response") from error
    raise RuntimeError("Internal backend service unavailable or invalid response")  # stream ended without a result


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
            return _replay_stage_events(self._retrieve_with_session(payload, timeout))
        return _post_streaming(self.url, payload, timeout)

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
