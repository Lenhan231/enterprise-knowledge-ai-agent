"""Select the specialist route for one user request."""
import json
import logging
from dataclasses import dataclass
from urllib.error import HTTPError

from core.agents.decision_support.intent_classifier import (
    JEV_ROUTE_THRESHOLD,
    classify_jev_route,
)
from core.agents.runtime import run_sync


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RouteSelection:
    agent: str | None
    selected_tools: list[str] | None


class AgentRouter:
    """Choose a direct specialist route or leave decomposition to the planner."""

    def __init__(self, classifier=None):
        self.classifier = classifier

    async def select(
        self, question, history, approved_schema, *, allow_direct=True, classifier=None,
    ):
        classifier = classifier or self.classifier or classify_jev_route
        try:
            decision = await run_sync(
                classifier, question, approved_schema, history, _timeout=12,
            )
        except Exception as error:
            http_status = getattr(error, 'code', None)
            provider_code = None
            limit_source = None
            if isinstance(error, HTTPError):
                try:
                    payload = json.loads(error.read(16_384))
                    details = payload.get('error')
                    if isinstance(details, dict):
                        provider_code = details.get('code')
                        metadata = details.get('metadata')
                        if isinstance(metadata, dict):
                            limit_source = metadata.get('limit_source')
                except Exception:
                    pass
            if not isinstance(provider_code, (int, str)) or not str(provider_code).replace('_', '').isalnum():
                provider_code = None
            if not isinstance(limit_source, str) or not limit_source.replace('_', '').isalnum():
                limit_source = None
            logger.warning(
                'JEV route selection failed; falling back to planner '
                '(error_type=%s, http_status=%s, provider_code=%s, limit_source=%s)',
                type(error).__name__, http_status, provider_code, limit_source,
            )
            return RouteSelection(agent=None, selected_tools=None)
        if not isinstance(decision, dict):
            return RouteSelection(agent=None, selected_tools=None)

        latest_turn = history[-1] if history else {}
        pending_clarification = bool(
            isinstance(latest_turn.get('clarification'), str)
            and latest_turn['clarification'].strip()
        )
        direct_agent = decision.get('route')
        confidence = decision.get('confidence')
        confidence = confidence if isinstance(confidence, (int, float)) else 0
        if not (
            direct_agent in {'knowledge', 'sql'}
            and confidence >= JEV_ROUTE_THRESHOLD
            and not pending_clarification
            and allow_direct
        ):
            direct_agent = None

        selected_tools = decision.get('selected_tools')
        return RouteSelection(
            agent=direct_agent,
            selected_tools=selected_tools if isinstance(selected_tools, list) else None,
        )
