from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from core.agents.report_agent import (
    _is_business_metric_decision_question,
    _is_business_metric_trend_question,
    _is_decision_suggestions_request,
    _is_decision_support_request,
)
from core.analytics.commerce_decision_support import (
    COMMERCE_DECISION_PROFILES,
    resolve_commerce_decision_domain,
)
from core.models.agents import AgentRequest, AgentResult


def _is_method_only_question(question: str) -> bool:
    text = " ".join(question.casefold().split())
    return text.startswith((
        "how to ", "how do i ", "how do you ", "what are the steps", "steps to ",
        "explain how to ", "explain the steps", "cách ", "các bước", "hướng dẫn", "quy trình", "làm thế nào",
    )) and not _is_decision_support_request(text)


def _applies_method_to_commerce_data(question: str) -> bool:
    text = " ".join(question.casefold().split())
    refers_to_observations = any(term in text for term in (
        "flag", "snapshot", "current data", "latest data", "observations", "dataset",
        "sql result", "the data", "these rows", "các cờ", "dữ liệu hiện tại", "snapshot mới nhất",
    ))
    applies_method = any(term in text for term in (
        "review", "check", "inspect", "compare", "interpret", "apply", "before", "based on",
        "rà soát", "kiểm tra", "đánh giá", "so sánh", "dựa trên", "trước khi",
    ))
    return refers_to_observations and applies_method


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
        if self.report_agent and (
            request.metadata.get("decision_suggestions")
            or _is_decision_suggestions_request(request.question)
        ):
            self.last_destination = "report"
            return {"destination": "report"}
        commerce_domain = request.metadata.get("business_decision_domain")
        if commerce_domain not in COMMERCE_DECISION_PROFILES:
            commerce_domain = resolve_commerce_decision_domain(request.question)
        question_text = request.question.casefold()
        dashboard_request = any(term in question_text for term in (
            "dashboard", "chart", "visualize", "visualise", "plot", "graph", "biểu đồ", "đồ thị",
        ))
        if dashboard_request and commerce_domain:
            request.metadata["business_decision_domain"] = commerce_domain
            self.last_destination = "dashboard"
            return {"destination": "dashboard"}
        policy_question = any(term in question_text for term in (
            "policy", "policies", "chính sách",
        )) and not any(term in question_text for term in (
            "should", "recommend", "decision", "can we", "nên", "khuyến nghị", "quyết định",
            "compare", "trend", "how much", "how many", "sales", "revenue", "transit",
            "so sánh", "xu hướng", "bao nhiêu", "doanh thu", "đơn hàng", "thời gian giao",
        ))
        if commerce_domain and policy_question:
            request.metadata["business_decision_domain"] = commerce_domain
            request.metadata["policy_reference_only"] = True
            self.last_destination = "knowledge"
            return {"destination": "knowledge"}
        named_external_source = any(name in request.question.casefold() for name in (
            "shopify", "amazon", "walmart", "shopee", "tiktok shop", "doordash", "sam's club",
        ))
        source_how_to_question = named_external_source and any(term in request.question.casefold() for term in (
            "what does", "what do", "according to", "how does", "how do", "what guidance", "the guide",
            "what policy", "nói gì", "hướng dẫn", "theo tài liệu",
        ))
        if self.report_agent and commerce_domain and source_how_to_question:
            request.metadata["business_decision_domain"] = commerce_domain
            self.last_destination = "knowledge"
            return {"destination": "knowledge"}
        if self.report_agent and commerce_domain in COMMERCE_DECISION_PROFILES:
            if (request.metadata.get("commerce_decision_support")
                    or _is_decision_support_request(request.question)):
                self.last_destination = "report"
                return {"destination": "report"}
            if _is_method_only_question(request.question) and _applies_method_to_commerce_data(request.question):
                request.metadata["decision_support"] = True
                self.last_destination = "report"
                return {"destination": "report"}
            # Let the shared intent model identify new document-only questions;
            # keep the established report route when classification falls back.
            intent = self.classifier.classify(request.question)
            knowledge_only = intent.intent == "knowledge" and intent.needs_knowledge and not intent.needs_sql
            if knowledge_only or (_is_method_only_question(request.question)
                                  and not _applies_method_to_commerce_data(request.question)):
                request.metadata["business_decision_domain"] = commerce_domain
                self.last_destination = "knowledge"
                return {"destination": "knowledge"}
            if intent.intent == "hybrid":
                request.metadata["decision_support"] = True
            self.last_destination = "report"
            return {"destination": "report"}
        if self.report_agent and commerce_domain:
            self.last_destination = "report"
            return {"destination": "report"}
        if (self.report_agent and not dashboard_request
                and (_is_business_metric_decision_question(request.question)
                     or _is_business_metric_trend_question(request.question))):
            self.last_destination = "report"
            return {"destination": "report"}
        intent = self.classifier.classify(request.question)

        if intent.intent == "report" and self.report_agent:
            destination = "report"
        elif intent.output_mode == "dashboard":
            destination = "dashboard"
        elif (self.report_agent and
              (_is_business_metric_decision_question(request.question)
               or _is_business_metric_trend_question(request.question))):
            destination = "report"
        elif (self.report_agent and intent.intent == "hybrid"
              and _is_decision_support_request(request.question)):
            destination = "report"
        elif intent.needs_knowledge and intent.needs_sql:
            destination = "hybrid"
        elif intent.needs_sql:
            destination = "analytics"
        else:
            destination = "knowledge"
        self.last_destination = destination
        return {"destination": destination}

    def route(self, request: AgentRequest) -> AgentResult:
        auto_detected_domain = False
        if request.metadata.get("commerce_decision_support") and not request.metadata.get("business_decision_domain"):
            classify_domain = getattr(self.classifier, "classify_commerce_domain", None)
            domain = (
                classify_domain(request.question)
                if callable(classify_domain)
                else resolve_commerce_decision_domain(request.question)
            )
            if domain not in COMMERCE_DECISION_PROFILES:
                self.last_destination = "commerce_domain_router"
                labels = ", ".join(profile["label"] for profile in COMMERCE_DECISION_PROFILES.values())
                return AgentResult(
                    answer=f"I couldn't determine one Commerce decision domain with enough confidence. Please clarify whether the question is about {labels}.",
                    agent="commerce_domain_router",
                    metadata={"needs_domain_clarification": True},
                )
            request.metadata["business_decision_domain"] = domain
            auto_detected_domain = True
        elif not request.metadata.get("business_decision_domain"):
            domain = resolve_commerce_decision_domain(request.question)
            if domain in COMMERCE_DECISION_PROFILES:
                request.metadata["business_decision_domain"] = domain
                auto_detected_domain = True
        result = self.workflow.invoke({"request": request})["result"]
        result = AgentResult.model_validate(result)
        domain = request.metadata.get("business_decision_domain")
        if domain in COMMERCE_DECISION_PROFILES:
            result.metadata.update({
                "business_decision_domain": domain,
                "business_domain_auto_detected": auto_detected_domain,
            })
        return result
