import re

from core.analytics.commerce_decision_support import COMMERCE_DECISION_PROFILES
from core.agents.base import BaseAgent
from core.models.agents import (
    AgentRequest,
    AgentResult,
    Evidence,
)
from core.rag.rag_service import RAGResult, RAGService


def _requested_page_number(question: str) -> int | None:
    match = re.search(r"\b(?:page|p\.|trang)\s*(\d+)\b", question.casefold())
    return int(match.group(1)) if match else None


def _rank_commerce_reference_evidence(
    contexts: list[dict], question: str, domain: str, limit: int,
) -> list[dict]:
    """Rank only curated Commerce references; platform rules require a named platform."""
    profile = COMMERCE_DECISION_PROFILES[domain]
    question_text = question.casefold()
    scored = []
    seen = set()
    for index, context in enumerate(contexts):
        metadata = context.get("metadata") or {}
        if metadata.get("commerce_reference_active") is not True:
            continue
        identity = (metadata.get("document_id"), context.get("chunk_index"), context.get("content"))
        if identity in seen:
            continue
        seen.add(identity)
        evidence_class = metadata.get("evidence_class")
        domains = metadata.get("knowledge_domains") or []
        if evidence_class not in {
            "company_policy_reference", "company_practice_reference", "platform_operating_rule",
            "management_cookbook_reference",
        }:
            continue
        issuer = str(metadata.get("source_publisher") or "").casefold()
        generic_terms = {"shop", "seller", "university", "help", "center", "marketplace", "vietnam", "education", "hub", "guide"}
        issuer_terms = {
            term for term in re.findall(r"[a-z0-9]+", issuer)
            if len(term) > 3 and term not in generic_terms
        }
        named_source = bool(issuer_terms.intersection(set(re.findall(r"[a-z0-9]+", question_text))))
        if evidence_class == "platform_operating_rule" and not named_source:
            continue
        if domain not in domains:
            continue
        content = " ".join((
            str(context.get("content") or ""),
            str(metadata.get("section_title") or ""),
            str(metadata.get("table_title") or ""),
        )).casefold()
        mentions_service_target = domain == "inventory_allocation" and any(term in question_text for term in (
            "service target", "service-level target", "fill rate target", "set a target",
            "service level goal", "mục tiêu dịch vụ", "đặt mục tiêu", "target mới",
        ))
        negates_service_target_use = bool(re.search(
            r"\bwithout\b.{0,60}\b(?:service(?:-level)?|fill rate|in-stock)?\s*target\b|"
            r"\bnot\s+(?:an?\s+)?(?:approved\s+)?(?:service(?:-level)?|fill rate|in-stock)\s+target\b|"
            r"\b(?:không|đừng|chưa)\b.{0,50}\b(?:mục tiêu dịch vụ|service target|fill rate target)\b",
            question_text,
        ))
        asks_service_target = mentions_service_target and not negates_service_target_use
        if asks_service_target:
            target_terms = (
                "service target", "service-level target", "service level target", "fill rate target",
                "in-stock target", "service level goal", "service level policy", "mức dịch vụ mục tiêu",
            )
            if not any(term in content for term in target_terms):
                continue
        if domain == "promotion_planning" and any(term in question_text for term in (
            "roi", "return on investment", "lợi tức đầu tư", "tỷ suất hoàn vốn",
        )):
            has_profitability_method = any(term in content for term in (
                "return on investment", "incremental roi", "contribution margin", "incremental profit",
            ))
            has_incrementality_method = (
                any(term in content for term in ("holdout", "treatment group", "control group", "ghost ads"))
                and any(term in content for term in ("incremental sales", "incrementality", "causal lift"))
            )
            if not has_profitability_method and not has_incrementality_method:
                # ROAS explains revenue per ad spend; only causal-test passages
                # can still ground the measurement prerequisite for an ROI decision.
                continue
        descriptive_logistics_comparison = (
            domain == "nationwide_logistics"
            and any(term in question_text for term in ("shipping fee", "shipping cost", "cước vận chuyển", "chi phí vận chuyển"))
            and any(term in question_text for term in ("transit time", "delivery time", "thời gian giao", "thời gian vận chuyển"))
            and any(term in question_text for term in ("change", "trend", "compare", "thay đổi", "biến động", "so sánh"))
            and not any(term in question_text for term in ("should", "recommend", "optimize", "nên", "khuyến nghị", "tối ưu"))
        )
        if descriptive_logistics_comparison:
            continue
        topic_hits = sum(term in content for term in profile["query_terms"])
        source_preference = {
            "company_policy_reference": 100,
            "company_practice_reference": 0,
            "platform_operating_rule": 0,
            "management_cookbook_reference": 1,
        }.get(evidence_class, 0)
        # Section headings provide a small, generic signal that a passage is
        # about the user's wording, without letting broad source categories
        # outrank more directly relevant passages.
        question_terms = set(re.findall(r"\w{4,}", question_text))
        content_terms = set(re.findall(r"\w{4,}", content))
        section_terms = set(re.findall(r"\w{4,}", str(metadata.get("section_title") or "").casefold()))
        score = topic_hits + 2 * len(question_terms & content_terms) + 3 * len(question_terms & section_terms)
        if context.get("retrieval_method") == "bm25":
            # Preserve exact lexical matches when OCR tokenization weakens
            # Vietnamese word overlap against the broad domain vocabulary.
            score += 2 * float(context.get("retrieval_score") or 0)
        if domain == "inventory_allocation":
            asks_stock_state = any(term in question_text for term in (
                "service target", "service-level target", "fill rate", "availability", "stockout",
                "out of stock", "low stock", "tình trạng tồn kho", "mức sẵn có", "tỷ lệ đáp ứng",
            ))
            asks_transfer = any(term in question_text for term in (
                "transfer", "reallocate", "chuyển hàng", "điều chuyển", "phân bổ lại",
            ))
            if asks_stock_state and not asks_transfer:
                stock_state_hits = sum(term in content for term in (
                    "fill rate", "in-stock rate", "out-of-stock rate", "out of stock", "low stock",
                    "in stock", "oos %", "stockout", "inventory health",
                ))
                score += 25 * stock_state_hits
        asks_network_comparison = (
            domain == "nationwide_logistics"
            and any(re.search(rf"\b{re.escape(term)}\b", question_text) for term in (
                "network", "logistics", "routing", "distribution network", "mạng lưới", "phân tuyến",
            ))
            and any(re.search(rf"\b{re.escape(term)}\b", question_text) for term in (
                "compare", "comparison", "evaluate", "criteria", "guide", "choose", "select",
                "priorities", "should guide", "so sánh", "tiêu chí", "ưu tiên",
            ))
        )
        if domain == "nationwide_logistics" and (asks_network_comparison or any(term in question_text for term in (
            "redesign", "network design", "network optimization", "thiết kế lại mạng lưới",
            "điều chỉnh mạng lưới", "shipping cost", "shipping fee", "transit time",
            "chi phí vận chuyển", "cước vận chuyển", "thời gian vận chuyển", "chuyển năng lực",
            "phân bổ năng lực", "giảm trễ",
        ))):
            strong_network_method_hits = sum(term in content for term in (
                "network design", "network optimization", "transportation cost",
                "shipment consolidation", "what-if scenario", "what if scenario",
                "carrier score-carding", "route optimization", "geographic gaps",
                "long-distance shipping costs", "capacity and demand", "inventory availability",
                "location proximity", "split shipment", "fulfillment location", "route capacity by lane",
            ))
            direct_routing_method_hits = sum(term in content for term in (
                "ship from the closest location", "location with the shortest distance",
                "minimize split fulfillment", "minimizing split fulfillments",
                "stay within the destination market", "ranked locations",
                "order routing logic", "inventory available for all items",
            ))
            supporting_priority_hits = sum(term in content for term in (
                "business priorities", "customer needs", "fast shipping", "shipping modes",
            ))
            asks_network_decision = any(term in question_text for term in (
                "redesign", "network design", "network optimization", "shift capacity",
                "transfer capacity", "thiết kế lại mạng lưới", "điều chỉnh mạng lưới",
                "chuyển năng lực", "phân bổ năng lực",
            ))
            if asks_network_decision and not strong_network_method_hits and not direct_routing_method_hits:
                continue
            if (asks_network_comparison and not asks_network_decision
                    and not strong_network_method_hits and not direct_routing_method_hits
                    and not supporting_priority_hits):
                continue
            score += (
                12 * strong_network_method_hits
                + 20 * direct_routing_method_hits
                + 12 * supporting_priority_hits
            )
        if score:
            policy_priority = evidence_class == "company_policy_reference"
        scored.append((named_source, policy_priority, score, source_preference, -index, context))
    ordered = sorted(scored, reverse=True, key=lambda item: item[:5])
    # Keep the small prompt context useful across references; fill remaining
    # slots with additional passages only when there are fewer sources than slots.
    selected = []
    seen_documents = set()
    for item in ordered:
        document_id = (item[5].get("metadata") or {}).get("document_id") or item[5].get("document_name")
        if document_id in seen_documents:
            continue
        selected.append(item)
        seen_documents.add(document_id)
        if len(selected) == limit:
            break
    if len(selected) < limit:
        selected_ids = {id(item[5]) for item in selected}
        selected.extend(item for item in ordered if id(item[5]) not in selected_ids and len(selected) < limit)
    result = [dict(item[5]) for item in selected]
    for index, context in enumerate(result, start=1):
        context["source_id"] = f"S{index}"
    return result


class KnowledgeAgent(BaseAgent):
    def __init__(
        self,
        rag_service: RAGService | None = None,
    ):
        self.rag = rag_service or RAGService()

    def run(
        self,
        request: AgentRequest,
    ) -> AgentResult:
        role = request.metadata.get("role")
        if not isinstance(role, str) or not role:
            raise ValueError("Knowledge retrieval requires a trusted authenticated role")
        rag_options = {
            "limit": 10,
            "company": request.metadata.get("company"),
            "roles": [role],
        }
        requested_page = _requested_page_number(request.question)
        if requested_page is not None:
            rag_options["metadata_filter"] = {"page_number": requested_page}
        if request.metadata.get("retrieval_method", "hybrid") != "hybrid":
            rag_options["retrieval_method"] = request.metadata["retrieval_method"]
        decision_domain = request.metadata.get("business_decision_domain")
        if decision_domain in COMMERCE_DECISION_PROFILES:
            rag_options["metadata_filter"] = {
                **rag_options.get("metadata_filter", {}),
                "commerce_reference_active": True,
                "knowledge_domains": [decision_domain],
            }
            if request.metadata.get("policy_reference_only"):
                rag_options["metadata_filter"]["evidence_class"] = "company_policy_reference"
        if request.metadata.get("evidence_only"):
            # Report synthesis uses one generation over its evidence; keep its
            # ranked context small enough for the configured model's TPM cap.
            rag_options["limit"] = 3 if request.metadata.get("decision_support") else 5
            if decision_domain in COMMERCE_DECISION_PROFILES:
                rag_options["limit"] = 50
            if decision_domain in COMMERCE_DECISION_PROFILES:
                retrieval_query = " ".join((request.question, COMMERCE_DECISION_PROFILES[decision_domain]["retrieval_query"]))
            else:
                retrieval_query = request.question
            contexts = self.rag.retrieve_contexts(retrieval_query, **rag_options)
            if decision_domain in COMMERCE_DECISION_PROFILES:
                contexts = _rank_commerce_reference_evidence(
                    contexts, request.question, decision_domain, 3,
                )
            result = RAGResult(
                answer="",
                contexts=contexts,
                insufficient_context=not contexts,
            )
        elif decision_domain in COMMERCE_DECISION_PROFILES:
            rag_options["limit"] = 50
            retrieval_query = " ".join((
                request.question,
                COMMERCE_DECISION_PROFILES[decision_domain]["retrieval_query"],
            ))
            contexts = self.rag.retrieve_contexts(retrieval_query, **rag_options)
            contexts = _rank_commerce_reference_evidence(
                contexts, request.question, decision_domain, 5,
            )
            result = self.rag.generate_answer(
                request.question,
                company=rag_options["company"],
                roles=rag_options["roles"],
                retrieved_contexts=contexts,
            )
        else:
            result = self.rag.generate_answer(request.question, **rag_options)
        evidence = [
            Evidence(
                citation_id=context["source_id"],
                source_type="document",
                source=context["document_name"],
                content=context["content"],
                metadata={
                    **context["metadata"],
                    **({"retrieval_chunk_id": context["chunk_id"]}
                       if context.get("chunk_id") else {}),
                    "chunk_index": context["chunk_index"],
                    "retrieval_score": context["retrieval_score"],
                    "retrieval_method": context["retrieval_method"],
                },
            )
            for context in result.contexts
        ]

        return AgentResult(
            answer=result.answer,
            agent="knowledge",
            evidence=evidence,
            metadata={
                "insufficient_context": result.insufficient_context,
                **({"answer_fallback_reason": result.answer_fallback_reason}
                   if result.answer_fallback_reason else {}),
                **({"generation_provider": result.generation_provider}
                   if result.generation_provider else {}),
                **({"token_usage": {
                    "answer_generation": result.token_usage,
                    "total": result.token_usage,
                }} if result.token_usage else {}),
            },
        )

    def close(self) -> None:
        self.rag.close()
