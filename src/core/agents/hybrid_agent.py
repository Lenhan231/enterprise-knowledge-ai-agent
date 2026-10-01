"""Combine grounded document retrieval and verified database metrics."""

from core.agents.base import BaseAgent
from core.agents.knowledge_agent import KnowledgeAgent
from core.agents.sql_analytics_agent import SQLAnalyticsAgent
from core.models.agents import AgentRequest, AgentResult


class HybridAgent(BaseAgent):
    def __init__(self, knowledge: KnowledgeAgent | None = None, analytics: SQLAnalyticsAgent | None = None):
        self.knowledge = knowledge or KnowledgeAgent()
        self.analytics = analytics or SQLAnalyticsAgent()

    def run(self, request: AgentRequest) -> AgentResult:
        knowledge = self.knowledge.run(request)
        analytics = self.analytics.run(request)
        metrics = analytics.data.get("financial", []) or analytics.data.get("business_metrics", [])
        answer = knowledge.answer
        if metrics:
            answer += "\n\n" + analytics.answer
        return AgentResult(answer=answer, agent="hybrid",
                           evidence=knowledge.evidence + analytics.evidence,
                           data=analytics.data,
                           metadata={"insufficient_context": knowledge.metadata.get("insufficient_context", False)})

    def close(self) -> None:
        self.knowledge.close()
        self.analytics.close()
