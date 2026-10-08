from core.models.agents import AgentRequest, AgentResult

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

    def route(self, request: AgentRequest) -> AgentResult:
        intent = self.classifier.classify(request.question)

        if intent.intent == "report" and self.report_agent:
            destination, agent = "report", self.report_agent
        elif intent.output_mode == "dashboard":
            destination, agent = "dashboard", self.dashboard_agent
        elif intent.needs_knowledge and intent.needs_sql:
            destination, agent = "hybrid", self.hybrid_agent
        elif intent.needs_sql:
            destination, agent = "analytics", self.analytics_agent
        else:
            destination, agent = "knowledge", self.knowledge_agent

        self.last_destination = destination
        return AgentResult.model_validate(agent.run(request))

