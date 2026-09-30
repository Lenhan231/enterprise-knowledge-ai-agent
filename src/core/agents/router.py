from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from core.models.agents import AgentRequest, AgentResult


class _AgentWorkflowState(TypedDict, total=False):
    request: AgentRequest
    destination: str
    result: AgentResult


class AgentRouter:
    def __init__(
        self,
        classifier,
        knowledge_agent,
        analytics_agent,
        hybrid_agent,
        dashboard_agent,
        report_agent=None,
    ):
        self.classifier = classifier
        self.knowledge_agent = knowledge_agent
        self.analytics_agent = analytics_agent
        self.hybrid_agent = hybrid_agent
        self.dashboard_agent = dashboard_agent
        self.report_agent = report_agent
        self.last_destination = "unrouted"
        self.workflow = self._build_workflow()

    def _build_workflow(self):
        agents = {
            "knowledge": self.knowledge_agent,
            "analytics": self.analytics_agent,
            "hybrid": self.hybrid_agent,
            "dashboard": self.dashboard_agent,
        }
        if self.report_agent:
            agents["report"] = self.report_agent

        graph = StateGraph(_AgentWorkflowState)
        graph.add_node("classify", self._classify)
        for name, agent in agents.items():
            graph.add_node(name, lambda state, selected=agent: {
                "result": selected.run(state["request"]),
            })
            graph.add_edge(name, END)
        graph.add_conditional_edges(
            "classify",
            lambda state: state["destination"],
            {name: name for name in agents},
        )
        graph.add_edge(START, "classify")
        return graph.compile()

    def _classify(self, state: _AgentWorkflowState) -> dict[str, str]:
        request = state["request"]
        intent = self.classifier.classify(request.question)

        if intent.intent == "report" and self.report_agent:
            destination = "report"
        elif intent.output_mode == "dashboard":
            destination = "dashboard"
        elif intent.needs_knowledge and intent.needs_sql:
            destination = "hybrid"
        elif intent.needs_sql:
            destination = "analytics"
        else:
            destination = "knowledge"
        self.last_destination = destination
        return {"destination": destination}

    def route(self, request: AgentRequest) -> AgentResult:
        result = self.workflow.invoke({"request": request})["result"]
        return AgentResult.model_validate(result)
