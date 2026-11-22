"""Select the specialist route for one user request."""
from dataclasses import dataclass

from core.agents.decision_support.intent_classifier import (
    JEV_ROUTE_THRESHOLD,
    classify_jev_route,
    is_product_profit_recommendation,
)
from core.agents.runtime import run_sync


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
        except Exception:
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
            and not is_product_profit_recommendation(question)
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
