from core.models.agents import AgentRequest, AgentResult

class AgentRouter:
    def __init__(
        self,
        classifier,
        knowledge_agent,
        analytics_agent,
        hybrid_agent,
        dashboard_agent,
    ):
        self.classifier = classifier
        self.knowledge_agent = knowledge_agent
        self.analytics_agent = analytics_agent
        self.hybrid_agent = hybrid_agent
        self.dashboard_agent = dashboard_agent

    def route(self, request: AgentRequest) -> AgentResult:
        intent = self.classifier.classify(request.question)

        if intent.output_mode == "dashboard":
            return self.dashboard_agent.run(request)

        if intent.needs_knowledge and intent.needs_sql:
            return self.hybrid_agent.run(request)

        if intent.needs_sql:
            return self.analytics_agent.run(request)

        return self.knowledge_agent.run(request)

