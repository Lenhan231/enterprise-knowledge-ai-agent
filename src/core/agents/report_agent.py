"""Draft a cited report from role-visible passages and verified database facts."""

import re
import logging
import json
from decimal import Decimal


from core.agents.base import BaseAgent
from core.agents.knowledge_agent import KnowledgeAgent
from core.agents.sql_analytics_agent import SQLAnalyticsAgent, UnsupportedCommerceDimension
from core.analytics.metric_ontology import resolve_metric_names
from core.analytics.business_metric_catalog import (
    BUSINESS_DECISION_PROFILES,
    BUSINESS_METRIC_CATALOG,
    SUPPORTED_BUSINESS_DECISION_DOMAINS,
    resolve_business_metric_domain,
    resolve_business_metric_names,
)
from core.analytics.commerce_decision_support import (
    COMMERCE_QUERY_TABLES,
    COMMERCE_DECISION_PROFILES,
    resolve_commerce_decision_domain,
)
from core.analytics.sql_safety import UnsafeAnalyticsQuery
from core.llm.groq_provider import GroqProvider
from core.llm.provider_fallback import (
    accumulate_token_usage, generate_with_provider_fallback, is_retryable_provider_error,
    sum_token_usage,
)
from core.models.agents import AgentRequest, AgentResult, Evidence
from core.rag.rag_service import INSUFFICIENT_ANSWER

_CITATION = re.compile(r"(?:\[|【)([A-Z]\d+)(?:\]|】)")
_NUMERIC_CITATION = re.compile(r"(?:\[|【)(\d+)(?:\]|】)")
_NUMBER = re.compile(r"(?<![\w])\d+(?:(?:[.,]\d{3})|(?:[\s\u00a0\u202f]\d{3}))*(?:[.,]\d+)?")
_UNIT_SCALE_PATTERNS = {
    "billion": re.compile(r"\b(?:billion|tỷ)\b", re.IGNORECASE),
    "million": re.compile(r"\b(?:million|triệu)\b", re.IGNORECASE),
    "thousand": re.compile(r"\b(?:thousand|nghìn)\b", re.IGNORECASE),
    "trillion": re.compile(r"\btrillion\b|(?<=\d)T\b", re.IGNORECASE),
}
_CURRENCY_PATTERNS = {
    "vnd": re.compile(r"\b(?:VND|đồng)\b|₫", re.IGNORECASE),
    "usd": re.compile(r"\b(?:USD|US dollars?)\b|\$", re.IGNORECASE),
    "eur": re.compile(r"\b(?:EUR|euros?)\b|€", re.IGNORECASE),
}
_VIETNAMESE_DIACRITICS = frozenset("ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ")
_INVALID_REPORT = "The answer was withheld because it could not be validated against the verified evidence. Please retry the question."
logger = logging.getLogger(__name__)
_REVENUE_HEADLINE = ("total consolidated revenue", "tổng doanh thu hợp nhất")
_PROFIT_HEADLINE = ("consolidated profit after tax", "consolidated net profit after tax", "lợi nhuận sau thuế hợp nhất")


def _is_financial_summary(question: str) -> bool:
    text = question.casefold()
    if any(term in text for term in ("gross profit", "gross margin", "lợi nhuận gộp", "biên lợi nhuận gộp")):
        return False
    return (
        any(term in text for term in ("revenue", "sales", "doanh thu"))
        and any(term in text for term in ("profit", "earnings", "net income", "lợi nhuận"))
    )


def _is_financial_change_explanation(question: str) -> bool:
    text = question.casefold()
    return (
        bool(resolve_metric_names(text))
        and len(set(re.findall(r"\b(?:19|20)\d{2}\b", text))) >= 2
        and any(term in text for term in ("why", "reason", "cause", "tại sao", "vì sao", "nguyên nhân"))
    )


def _is_decision_support_request(question: str) -> bool:
    text = question.casefold()
    if any(term in text for term in (
        "should", "recommend", "decision", "decide", "strategy", "what should", "which market",
        "which option", "prioritize", "scale", "scaling", "expand", "repeat", "pilot", "target", "reallocat",
        "enough evidence", "increase budget", "raise budget", "budget increase", "increase spend",
        "investment", "nên", "đề xuất", "quyết định", "chiến lược", "ưu tiên", "mở rộng", "phân bổ",
        "đủ cơ sở", "chứng minh", "tăng ngân sách", "dồn ngân sách", "thiết kế lại", "điều chỉnh",
    )):
        return True
    action_verbs = (
        "improve", "reduce", "lower", "increase", "optimize", "optimise", "prevent", "mitigate", "minimize", "maximize",
    )
    action_pattern = r"(?:" + "|".join(action_verbs) + r")\b"
    if re.search(
        r"\b(?:how can|how should|what can|what should|can we|could we|how do we|how to|ways to)\b"
        r"[^.!?\n]{0,100}\b" + action_pattern,
        text,
    ) or re.search(
        r"\b(?:làm sao|làm thế nào|cách|các cách)\b[^.!?\n]{0,100}"
        r"(?:cải thiện|giảm|tăng|tối ưu|ngăn ngừa|hạn chế)\b",
        text,
    ):
        return True
    return bool(re.search(
        r"\b(?:what|which|how much)\s+(?:(?:additional|more|other)\s+)?"
        r"(?:evidence|data|information)\b.{0,160}\b(?:needed|required|missing|before|to decide|to choose)\b",
        text,
    ))


def _is_vietnamese_text(text: str) -> bool:
    return any(character in _VIETNAMESE_DIACRITICS for character in text.casefold())


def _has_untranslated_prose(answer: str, question: str) -> bool:
    """Catch long English narration in a Vietnamese answer, ignoring quoted source text."""
    if not _is_vietnamese_text(question):
        return False
    narration = re.sub(r"“[^”]*”|\"[^\"]*\"|'[^']*'", " ", answer)
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", narration):
        letters = [character for character in sentence if character.isalpha()]
        if len(letters) >= 24 and not _is_vietnamese_text(sentence):
            return True
    return False


def _is_inventory_service_target_question(question: str) -> bool:
    text = question.casefold()
    return any(term in text for term in (
        "service target", "service-level target", "fill rate target", "service level target",
        "mục tiêu dịch vụ", "target dịch vụ", "chỉ tiêu dịch vụ",
    ))


def _asks_both_inventory_flags(question: str) -> bool:
    text = question.casefold()
    stockout_terms = ("stockout", "out of stock", "hết hàng", "thiếu hàng")
    overstock_terms = ("overstock", "dư hàng", "tồn kho dư")
    return any(term in text for term in stockout_terms) and any(term in text for term in overstock_terms)


def _suggests_unsupported_inventory_transfer(answer: str) -> bool:
    return bool(re.search(
        r"\b(?:consider|recommend|suggest|should)\s+(?:(?:that\s+)?(?:we|you)\s+)?"
        r"(?:transfer\w*|reallocat\w*|rebalanc\w*|move\s+(?:stock|inventory))\b"
        r"|\b(?:cân nhắc|khuyến nghị|nên|hãy)\s+(?:thử\s+)?"
        r"(?:điều chuyển|chuyển hàng|phân bổ lại|tái cân bằng)\b",
        answer,
        re.IGNORECASE,
    ))


def _is_business_metric_decision_question(question: str) -> bool:
    text = question.casefold()
    return bool(resolve_business_metric_names(question)) and (
        _is_decision_support_request(question)
        or any(term in text for term in ("why", "reason", "cause", "tại sao", "vì sao", "nguyên nhân"))
    )


def _is_business_metric_trend_question(question: str) -> bool:
    text = question.casefold()
    trend_request = any(term in text for term in (
        "summarize", "summary", "trend", "compare", "performance", "tóm tắt", "xu hướng",
        "so sánh", "hiệu quả", "thay đổi", "improv", "worsen", "rebound", "deteriorat",
    ))
    return trend_request and bool(resolve_business_metric_names(question))


def _is_decision_suggestions_request(question: str) -> bool:
    text = question.casefold()
    return text.startswith((
        "generate conditional management actions", "generate decision opportunities",
        "suggest management decisions", "suggest decisions",
        "gợi ý quyết định", "gợi ý các quyết định", "gợi ý hành động", "khuyến nghị hành động",
    ))


def _has_unsupported_numeric_decision_gate(answer: str, evidence: list[Evidence]) -> bool:
    comparison_terms = re.compile(
        r"\b(?:exceeds?|surpasses?|greater than|less than|higher than|lower than|faster than|slower than|"
        r"more than|above|below|"
        r"at least|at most|minimum|maximum)\b|vượt(?: quá)?|cao hơn|thấp hơn|lớn hơn|nhỏ hơn|"
        r"ít nhất|tối đa",
        re.IGNORECASE,
    )
    number_pattern = re.compile(r"(?<![\w])\d+(?:(?:[.,]\d{3})|(?:[\s\u00a0\u202f]\d{3}))*(?:[.,]\d+)?")
    reported_threshold = re.compile(
        r"(?:target|threshold|hurdle|minimum|maximum|limit|goal|criterion|standard|floor|ceiling|mục tiêu|ngưỡng)"
        r"(?:\s+(?:of|is|was|at|là|tối thiểu|tối đa|từ|đạt))?\s*[:=]?\s*"
        r"(?P<value>\d+(?:(?:[.,]\d{3})|(?:[\s\u00a0\u202f]\d{3}))*(?:[.,]\d+)?)",
        re.IGNORECASE,
    )

    def normalized_number(value: str) -> str:
        value = value.replace(" ", "").replace("\u00a0", "").replace("\u202f", "")
        if "," in value and "." in value:
            value = value.replace(",", "")
        elif "," in value:
            left, right = value.rsplit(",", 1)
            value = left + right if len(right) == 3 else left + "." + right
        elif "." in value:
            left, right = value.rsplit(".", 1)
            value = left + right if len(right) == 3 and len(left) <= 3 else value
        return value

    conditionals = re.finditer(
        r"\bif\b(.*?)(?:\bthen\b)|\bnếu\b(.*?)(?:\bthì\b)", answer,
        re.IGNORECASE | re.DOTALL,
    )
    conditional_matches = list(conditionals)
    evidence_by_citation = {item.citation_id: item for item in evidence if item.citation_id}
    for index, match in enumerate(conditional_matches):
        gate = _CITATION.sub("", next((part for part in match.groups() if part is not None), ""))
        if not comparison_terms.search(gate):
            continue
        gate_numbers = [number for number in number_pattern.findall(gate)
                        if not re.fullmatch(r"(?:19|20)\d{2}", number)]
        if not gate_numbers:
            continue
        segment_end = (conditional_matches[index + 1].start()
                       if index + 1 < len(conditional_matches) else len(answer))
        cited_ids = set(_CITATION.findall(answer[match.start():segment_end]))
        sourced_thresholds = set()
        for citation_id in cited_ids:
            item = evidence_by_citation.get(citation_id)
            if not item:
                continue
            source_text = f"{item.source or ''} {item.content or ''}"
            sourced_thresholds.update(
                normalized_number(threshold.group("value"))
                for threshold in reported_threshold.finditer(source_text)
            )
        if any(normalized_number(number) not in sourced_thresholds for number in gate_numbers):
            return True

    # A historical observation may be accurately cited yet still be an invented future hurdle.
    future_action = re.compile(
        r"\b(?:pilot|proceed|scale|increase|improve|reduce|decrease|raise|lower|target|goal|condition|"
        r"future|next|should|continue|expand|trigger|justify|after)\b|"
        r"nên|tiếp tục|mở rộng|điều kiện|sau khi|thí điểm",
        re.IGNORECASE,
    )
    for sentence in re.split(r"(?<=[.!?])\s+(?!\[[A-Z]\d+\])|(?<=\])\s+|\n+", answer):
        if not future_action.search(sentence) or not comparison_terms.search(sentence):
            continue
        gate_numbers = [number for number in number_pattern.findall(sentence)
                        if not re.fullmatch(r"(?:19|20)\d{2}", number)]
        if not gate_numbers:
            continue
        cited_ids = set(_CITATION.findall(sentence))
        sourced_thresholds = set()
        for citation_id in cited_ids:
            item = evidence_by_citation.get(citation_id)
            if not item:
                continue
            source_text = f"{item.source or ''} {item.content or ''}"
            sourced_thresholds.update(
                normalized_number(threshold.group("value"))
                for threshold in reported_threshold.finditer(source_text)
            )
        if any(normalized_number(number) not in sourced_thresholds for number in gate_numbers):
            return True
    return False


def _has_unsupported_logistics_intervention(answer: str) -> bool:
    """Reject concrete network changes when the available evidence is only regional aggregates."""
    action = re.compile(
        r"\b(?:add|build|open|relocate|move|shift|reallocate|switch|change|replace|redesign|optimize)\b"
        r"[^.!?;\n]{0,90}\b(?:warehouse|carrier|capacity|route|network)\b|"
        r"\b(?:mở|xây|thêm|di chuyển|điều chuyển|thay đổi|đổi|thiết kế lại|tái thiết kế|tối ưu)\b"
        r"[^.!?;\n]{0,90}\b(?:kho|carrier|hãng vận chuyển|năng lực|tuyến|mạng lưới)\b",
        re.IGNORECASE,
    )
    refusal = re.compile(
        r"\b(?:do not|don't|cannot|can not|should not|must not|avoid|not yet|no need to)\b|"
        r"\b(?:chưa|không|đừng|tránh)\b",
        re.IGNORECASE,
    )
    return any(
        action.search(sentence) and not refusal.search(sentence)
        for sentence in re.split(r"[.!?;\n]+", answer)
    )


def _has_unprovided_logistics_fields(answer: str) -> bool:
    return bool(re.search(
        r"\b(?:warehouse processing time|processing time at (?:the )?warehouse|traffic|weather|distance|"
        r"regional coverage|geographic coverage)\b|thời gian xử lý tại kho|giao thông|thời tiết|"
        r"khoảng cách|độ phủ vùng|độ phủ địa lý",
        answer,
        re.IGNORECASE,
    ))


def _omits_cited_logistics_method(answer: str, references: list[Evidence]) -> bool:
    """Reject a logistics recommendation that cites a method but never states it."""
    cited_ids = set(_CITATION.findall(answer))
    method_pairs = (
        (("closest location", "shortest distance"), ("closest location", "nearest location", "vị trí gần", "điểm gần")),
        (("split fulfillment", "split shipment"), ("split fulfillment", "split shipment", "tách đơn", "chia đơn")),
        (("inventory available", "inventory availability"), ("inventory available", "tồn kho khả dụng", "tồn kho sẵn có")),
        (("destination market",), ("destination market", "thị trường đích")),
        (("business priorities", "customer needs"), ("business priorities", "customer needs", "ưu tiên kinh doanh", "nhu cầu khách")),
        (("balance speed and cost", "speed and cost"), ("balance speed and cost", "speed and cost", "cân bằng tốc độ và chi phí", "tốc độ và chi phí")),
    )
    for item in references:
        if not item.citation_id or item.citation_id not in cited_ids:
            continue
        source_text = (item.content or "").casefold()
        applicable_methods = [
            answer_terms for source_terms, answer_terms in method_pairs
            if any(term in source_text for term in source_terms)
        ]
        if applicable_methods and not any(
            any(term in answer.casefold() for term in answer_terms)
            for answer_terms in applicable_methods
        ):
            return True
    return False


def _has_undisclosed_approved_hurdle(answer: str) -> bool:
    """Require the answer to disclose when an approved decision hurdle is absent from evidence."""
    missing_disclosure = re.compile(
        r"\b(?:not supplied|not provided|not stated|do not provide|does not provide|"
        r"must (?:first )?be set|set one first)\b",
        re.IGNORECASE,
    )
    segments = [segment for segment in re.split(r"(?=\bIf\b)", answer, flags=re.IGNORECASE)
                if re.match(r"\s*If\b", segment, flags=re.IGNORECASE)]
    first_action = re.search(r"\bIf\b", answer, re.IGNORECASE)
    preamble = answer[:first_action.start()] if first_action else answer
    if (re.search(r"\b(?:approved|management[- ]approved|company[- ]approved)\b[^.\n]{0,60}"
                  r"\b(?:hurdle|target|threshold|standard)\b", preamble, re.IGNORECASE)
            and missing_disclosure.search(preamble)):
        return False
    for segment in segments:
        has_hurdle = re.search(r"\b(?:approved|management[- ]approved|company[- ]approved)\b[^.\n]{0,60}"
                               r"\b(?:hurdle|target|threshold|standard)\b", segment, re.IGNORECASE)
        if has_hurdle and not missing_disclosure.search(segment):
            return True
    return False


def _has_uncited_environmental_intervention(answer: str, evidence: list[Evidence]) -> bool:
    patterns = (
        r"\bcompost(?:ing)?\b",
        r"\banaerobic digestion\b",
        r"\bmembrane filtration\b",
        r"\blow[-‐‑ ]emission boilers?\b",
        r"\bfeedstock logistics\b",
    )
    by_id = {item.citation_id: item for item in evidence if item.citation_id}
    segments = [segment for segment in re.split(r"(?=\bIf\b)", answer, flags=re.IGNORECASE)
                if re.match(r"\s*If\b", segment, flags=re.IGNORECASE)]
    for segment in segments:
        cited_text = " ".join(
            by_id[citation_id].content or ""
            for citation_id in set(_CITATION.findall(segment))
            if citation_id in by_id
        ).casefold().replace("‑", "-").replace("–", "-")
        normalized_segment = segment.casefold().replace("‑", "-").replace("–", "-")
        example = re.search(r"(?:\be\.g\.?\s*|\bfor example\b\s*|\bsuch as\b\s*)([^.;\n)]*)",
                            normalized_segment, re.IGNORECASE)
        if example:
            candidate = example.group(1).strip(" ,:")
            if candidate and candidate not in cited_text:
                return True
        if any(re.search(pattern, normalized_segment) and not re.search(pattern, cited_text)
               for pattern in patterns):
            return True
    return False


def _generate_conditional_draft(llm, prompt: str, instructions: str) -> tuple[str, str]:
    return generate_with_provider_fallback(llm, prompt, instructions=instructions)


def _provider_failure_reason(error: Exception) -> str:
    return "provider_rate_limited" if getattr(error, "status_code", None) == 429 else "provider_unavailable"


def _conditional_decision_suggestions(
    metric_data: AgentResult, domain: str | None, llm,
) -> AgentResult:
    """Generate cited if/then decision gates from the latest verified annual KPI periods."""
    if domain not in BUSINESS_DECISION_PROFILES:
        return metric_data.model_copy(update={
            "answer": "Chọn một domain có dữ liệu đã xác minh trước khi tạo khuyến nghị.",
            "agent": "report",
            "metadata": {**metric_data.metadata, "insufficient_context": True,
                         "decision_analysis": "decision_domain_required"},
        })

    rows = [row for row in metric_data.data.get("business_metrics", [])
            if row.get("fiscal_year") is not None
            and row.get("reporting_period", "FY") == "FY"]
    years = sorted({int(row["fiscal_year"]) for row in rows})[-3:]
    recent_rows = [row for row in rows if int(row["fiscal_year"]) in years]
    by_series = {}
    for row in recent_rows:
        key = row.get("metric_name"), row.get("unit")
        by_series.setdefault(key, set()).add(int(row["fiscal_year"]))
    usable_series = sum(all(year in observed_years for year in years) for observed_years in by_series.values())
    consecutive_years = len(years) == 3 and all(
        year == years[index - 1] + 1 for index, year in enumerate(years) if index > 0
    )
    if not consecutive_years or usable_series < 2:
        return metric_data.model_copy(update={
            "answer": (
                f"Domain {BUSINESS_DECISION_PROFILES[domain]['label']} chưa có đủ ít nhất hai KPI "
                "đã xác minh trong ba năm tài chính liên tiếp gần nhất để tạo khuyến nghị có căn cứ."
            ),
            "agent": "report",
            "metadata": {**metric_data.metadata, "insufficient_context": True,
                         "decision_analysis": "insufficient_recent_metric_coverage",
                         "analysis_periods": years},
        })

    selected_ids = {row.get("business_metric_id") for row in recent_rows}
    evidence = [item for item in metric_data.evidence
                if item.metadata.get("business_metric_id") in selected_ids]
    evidence_by_id = {item.metadata.get("business_metric_id"): item for item in evidence}
    recent_rows = [row for row in recent_rows if row.get("business_metric_id") in evidence_by_id]
    evidence_series = {}
    for row in recent_rows:
        key = row.get("metric_name"), row.get("unit")
        evidence_series.setdefault(key, set()).add(int(row["fiscal_year"]))
    cited_series_count = sum(all(year in observed_years for year in years)
                             for observed_years in evidence_series.values())
    if cited_series_count < 2:
        return metric_data.model_copy(update={
            "answer": "Các KPI gần nhất chưa có đủ chuỗi số liệu với trích dẫn nguồn cho cả ba năm.",
            "agent": "report",
            "metadata": {**metric_data.metadata, "insufficient_context": True,
                         "decision_analysis": "recent_kpi_sources_missing"},
        })

    topic_instruction = ""
    supported_topics = []
    topics = {}
    if domain == "environmental_performance":
        complete_metric_names = {
            name for (name, _unit), observed_years in evidence_series.items()
            if all(year in observed_years for year in years)
        }
        topics = {
            "waste": {"total_waste_generated", "waste_recovered_recycled", "waste_treated_disposed"},
            "water": {"total_raw_water_intake", "total_water_consumption", "recycled_reused_water", "wastewater_discharge"},
            "emissions": {"scope_1_2_ghg_emissions", "scope_1_ghg_emissions", "scope_2_ghg_emissions",
                          "dairy_product_ghg_intensity", "sugar_product_ghg_intensity"},
        }
        supported_topics = [name for name, metrics in topics.items() if complete_metric_names & metrics]
        if len(supported_topics) > 1:
            topic_instruction = (
                "Environmental decision coverage is available for these distinct, three-year-supported topics: "
                + ", ".join(supported_topics) + ". Produce one distinct action for each listed topic, and ground each "
                "action only in citations for that topic. Do not repeat the same action or reuse one topic's evidence "
                "for every action. Keep source-scope caveats and site-level evidence requirements specific to each topic. "
            )
    elif domain == "market_performance":
        topic_instruction = (
            "Market-allocation guard: revenue growth and segment gross margin can justify further diligence, not a "
            "capital-allocation decision. Do not recommend opening stores, entering countries, expanding exports, or "
            "shifting investment from these aggregate series alone. Keep any immediate action to a bounded market or "
            "channel diligence task. Make any later investment conditional on comparable market-level operating profit, "
            "incremental CAPEX, working capital, competitive conditions, currency/regulatory risk, and management's "
            "approved return hurdle. Otherwise hold the allocation and request those data. "
        )

    context = []
    for row in sorted(recent_rows, key=lambda item: (int(item["fiscal_year"]), item["metric_name"])):
        source = evidence_by_id[row["business_metric_id"]]
        context.append(
            f"[{source.citation_id}] FY{row['fiscal_year']} {row['metric_label']}: "
            f"{_qualified_business_metric_value(row)}; scope: {row.get('scope') or 'not stated'}; "
            f"source excerpt: {source.content or 'not available'}"
        )

    system_instructions = (
        "You are a source-grounded enterprise decision-support analyst. Respond in the user's language. "
        "Generate up to three useful management actions to consider from the supplied verified observations; "
        "do not return a menu of generic questions or merely summarize numbers. "
        "Write every action in this exact form: 'If [future observable condition], then [bounded next action]; "
        "otherwise [hold, continue checking, or gather evidence]. Evidence: [M#]'. Include the literal words If, "
        "then and otherwise in every action. Do not put a number, percentage, or comparison of prior-year values "
        "inside a condition. Never use an increase, decrease, greater-than/lower-than comparison, prior-year value, "
        "or completed historical trend as an action trigger, even if the number is cited. Do not make a future fiscal "
        "year compared with a previous-year value the gate. Instead, condition action on a future operational finding "
        "that is not yet in the data, such as a site audit identifying a controllable process and confirming an "
        "approved cost, quality, and compliance hurdle. Begin with one short note before the actions stating that "
        "the cited reports do not provide a management-approved operational hurdle and management must set one "
        "before judging any pilot. Keep every action conditional on a future audit and that hurdle being set. State "
        "historical KPI values only after 'Evidence:', outside the condition. "
        "Prefer a diligence step or bounded pilot over a technical prescription that the evidence does not support. "
        "Never turn a reported observation or prior-year value into a decision "
        "target, hurdle, or cutoff. A numeric threshold is allowed only when the cited source explicitly labels that "
        "number as a target, threshold, standard, or hurdle. Do not compare rates to levels, compare unlike units, or "
        "call a reported value a target. The supplied evidence contains no management-approved operational hurdle "
        "unless a cited source explicitly says otherwise. Do not phrase an approval as if it already exists. State the "
        "missing-hurdle disclosure once in the opening note, then condition any pilot on management first setting "
        "the hurdle and a future audit confirming a controllable opportunity meets it; do not invent a threshold. Use three-year-complete series "
        "as trend evidence; treat "
        "one-year-only measures as "
        "single-period signals for diligence, never as a trend or a threshold. Distinguish a diligence step or pilot "
        "from approval to scale or allocate capital. For each action, state the cited evidence, the condition that "
        "would trigger action, and missing data needed to test that condition. Preserve source scope and qualifiers, "
        "make the immediate action only an audit, measurement, or bounded pilot at one selected site or line. "
        "Do not name a specific technology, equipment, treatment, production protocol, or initiative unless a cited source "
        "explicitly identifies it as an existing practice or reported option. A hypothetical future audit does not "
        "support naming a candidate technology today. If the reports do not name a practice, recommend an audit to "
        "identify and compare options; do not list examples, use parenthetical examples, choose, or prescribe one. "
        "Never recommend rollout, deployment, or expansion across all sites; scaling requires a separate later decision "
        "after pilot results. Do not imply an intervention or process already exists unless the evidence says so; "
        "frame it as an option to test if a future audit confirms the opportunity. "
        "Do not claim causes from correlation, and cite every source-derived fact with its exact [M#] citation. "
        "Use only the evidence in the user message. If it does not support an action, return fewer than three. "
        + topic_instruction
    )
    prompt = (
        f"Analyze only the latest available annual periods {years} for the selected decision domain "
        f"{BUSINESS_DECISION_PROFILES[domain]['label']}. The data are source-backed observations, not targets. "
        "Use only the evidence below.\n\nEvidence:\n"
        + "\n".join(context)
    )
    raw_answer, generation_provider = _generate_conditional_draft(llm, prompt, system_instructions)
    answer = _normalize_numeric_citations(raw_answer, evidence)
    validation_failure = _report_validation_failure(answer, evidence, {item.citation_id for item in evidence}, "")
    unsupported_numeric_gate = _has_unsupported_numeric_decision_gate(answer, evidence)
    undisclosed_hurdle = _has_undisclosed_approved_hurdle(answer)
    unsupported_intervention = (
        domain == "environmental_performance"
        and _has_uncited_environmental_intervention(answer, evidence)
    )
    repaired = False
    citation_repair_attempted = False
    numeric_gate_repair_attempted = False
    hurdle_repair_attempted = False
    intervention_repair_attempted = False
    if validation_failure or unsupported_numeric_gate or undisclosed_hurdle or unsupported_intervention:
        repaired = True
        corrections = []
        if validation_failure:
            citation_repair_attempted = True
            corrections.append(
                "Citation validation failed: " + validation_failure + ". Use only the supplied citation IDs."
            )
        if unsupported_numeric_gate:
            numeric_gate_repair_attempted = True
            corrections.append(
                "The previous draft failed because its condition used historical values as a comparison gate. This is "
                "prohibited even when cited. Remove all numeric comparisons, increase/decrease trends, and past-year "
                "values from every gate. Use only a future site/process audit finding and a management-approved "
                "cost/quality/compliance hurdle as the condition; if no hurdle is supplied, make setting one a "
                "prerequisite. Put historical values only in the separate Evidence clause and retain otherwise."
            )
        if undisclosed_hurdle:
            hurdle_repair_attempted = True
            corrections.append(
                "The previous draft did not disclose that the evidence lacks an approved hurdle. Add this exact note "
                "before the actions: 'The cited reports do not provide a management-approved operational hurdle; "
                "management must set one before judging any pilot.' Then condition each action on a future audit "
                "confirming a controllable opportunity after management sets the hurdle. Do not imply the hurdle "
                "already exists."
            )
        if unsupported_intervention:
            intervention_repair_attempted = True
            corrections.append(
                "The previous draft named a specific environmental technology or process that its cited passages do "
                "not support. Remove that name and all parenthetical examples. Recommend only an audit that measures "
                "the relevant waste, water, or emissions stream and identifies and compares candidate options; do not "
                "select or prescribe an option unless a cited passage explicitly names it."
            )
        repair_prompt = prompt + "\n\n" + " ".join(corrections)
        raw_answer, repair_provider = _generate_conditional_draft(llm, repair_prompt, system_instructions)
        if repair_provider == "huggingface_inference":
            generation_provider = repair_provider
        answer = _normalize_numeric_citations(raw_answer, evidence)
        validation_failure = _report_validation_failure(
            answer, evidence, {item.citation_id for item in evidence}, "",
        )
        unsupported_numeric_gate = _has_unsupported_numeric_decision_gate(answer, evidence)
        undisclosed_hurdle = _has_undisclosed_approved_hurdle(answer)
        unsupported_intervention = (
            domain == "environmental_performance"
            and _has_uncited_environmental_intervention(answer, evidence)
        )
    if unsupported_numeric_gate:
        return metric_data.model_copy(update={
            "answer": (
                "Chưa thể phát hành khuyến nghị: bản trả lời dùng số liệu quan sát như ngưỡng quyết định, nhưng nguồn "
                "không xác nhận đó là mục tiêu hoặc hurdle đã được phê duyệt. Cần đặt hurdle quản trị rõ ràng; trong "
                "lúc đó chỉ nên xem các KPI gần nhất là tín hiệu để điều tra hoặc thử nghiệm giới hạn."
            ),
            "agent": "report",
            "evidence": evidence,
            "data": {**metric_data.data, "business_metrics": recent_rows},
            "metadata": {**metric_data.metadata, "insufficient_context": True,
                         "decision_threshold_validation_failed": True,
                         "decision_analysis": "unsupported_numeric_decision_gate"},
        })
    if undisclosed_hurdle:
        return metric_data.model_copy(update={
            "answer": (
                "Recommendations were withheld because they referred to management-approved hurdles that the cited "
                "evidence does not establish. Set and document the relevant hurdle before evaluating a bounded pilot."
            ),
            "agent": "report",
            "evidence": evidence,
            "data": {**metric_data.data, "business_metrics": recent_rows},
            "metadata": {**metric_data.metadata, "insufficient_context": True,
                         "decision_hurdle_validation_failed": True,
                         "decision_analysis": "undisclosed_approved_hurdle"},
        })
    if unsupported_intervention:
        topic_actions = {
            "waste": (
                "If a site audit confirms a controllable waste stream and management sets a measurable waste-reduction "
                "hurdle, then run a bounded measurement pilot selected by that audit at one line; otherwise collect "
                "comparable waste-composition, output, recovery, disposal, compliance and cost data."
            ),
            "water": (
                "If a site water balance confirms a controllable intake or discharge opportunity and management sets "
                "water-quality, compliance and cost criteria, then run a bounded measurement pilot selected after "
                "comparing options; otherwise collect comparable intake, reuse, discharge, output, quality and cost data."
            ),
            "emissions": (
                "If a site audit identifies a controllable emissions source and management sets a reduction hurdle on "
                "a like-for-like output basis, then measure a bounded pilot selected after comparing options; otherwise "
                "collect site energy-source, output, emissions and abatement-cost data."
            ),
        }
        fallback_actions = []
        for topic in supported_topics:
            topic_rows = [row for row in recent_rows if row.get("metric_name") in topics[topic]]
            if not all(any(int(row["fiscal_year"]) == year for row in topic_rows) for year in years):
                continue
            citation_ids = sorted({
                evidence_by_id[row["business_metric_id"]].citation_id
                for row in topic_rows
                if row.get("business_metric_id") in evidence_by_id
            })
            if citation_ids:
                fallback_actions.append(f"{topic.title()}: {topic_actions[topic]} Evidence: "
                                        + ", ".join(f"[{citation_id}]" for citation_id in citation_ids) + ".")
        fallback_answer = (
            "The queried KPI evidence does not provide a management-approved operational hurdle; management must set one "
            "before judging a pilot. These are audit-first decision steps, not reported Vinamilk initiatives.\n\n"
            + "\n\n".join(fallback_actions)
        )
        fallback_invalid = (
            not fallback_actions
            or _report_validation_failure(fallback_answer, evidence, {item.citation_id for item in evidence}, "")
            or _has_unsupported_numeric_decision_gate(fallback_answer, evidence)
            or _has_undisclosed_approved_hurdle(fallback_answer)
            or _has_uncited_environmental_intervention(fallback_answer, evidence)
        )
        if not fallback_invalid:
            return metric_data.model_copy(update={
                "answer": fallback_answer,
                "agent": "report",
                "evidence": evidence,
                "data": {**metric_data.data, "business_metrics": recent_rows},
                "metadata": {**metric_data.metadata, "insufficient_context": False,
                             "decision_analysis": "environmental_audit_first_fallback",
                             "analysis_periods": years,
                             "generation_provider": "deterministic_safety_fallback",
                             "recommendation_repair_attempted": True,
                             "intervention_repair_attempted": True},
            })
        return metric_data.model_copy(update={
            "answer": (
                "Recommendations were withheld because the cited KPI passages do not identify a specific waste, water, "
                "or emissions intervention. Start with a site-level audit to identify and compare options against "
                "management-set criteria before choosing a bounded pilot."
            ),
            "agent": "report",
            "evidence": evidence,
            "data": {**metric_data.data, "business_metrics": recent_rows},
            "metadata": {**metric_data.metadata, "insufficient_context": True,
                         "environmental_intervention_validation_failed": True,
                         "decision_analysis": "uncited_environmental_intervention"},
        })
    if validation_failure:
        logger.warning("Conditional recommendation citation validation failed after repair (%s)", validation_failure)
        return metric_data.model_copy(update={
            "answer": _INVALID_REPORT,
            "agent": "report",
            "evidence": evidence,
            "data": {**metric_data.data, "business_metrics": recent_rows},
            "metadata": {**metric_data.metadata, "insufficient_context": True,
                         "citation_validation_failed": True,
                         "decision_analysis": "conditional_recommendation_validation_failed"},
        })
    return metric_data.model_copy(update={
        "answer": answer,
        "agent": "report",
        "evidence": evidence,
        "data": {**metric_data.data, "business_metrics": recent_rows},
        "metadata": {**metric_data.metadata, "insufficient_context": False,
                     "decision_analysis": "conditional_recommendations_from_recent_verified_kpis",
                     "analysis_periods": years,
                     "generation_provider": generation_provider,
                     **({"hurdle_repair_attempted": True} if hurdle_repair_attempted else {}),
                     **({"recommendation_repair_attempted": True} if repaired else {}),
                     **({"citation_repair_attempted": True} if citation_repair_attempted else {}),
                     **({"numeric_gate_repair_attempted": True} if numeric_gate_repair_attempted else {}),
                     **({"intervention_repair_attempted": True} if intervention_repair_attempted else {})},
    })


def _normalize_numeric_citations(answer: str, evidence: list[Evidence]) -> str:
    ids = [item.citation_id for item in evidence if item.citation_id]

    def replace(match: re.Match) -> str:
        index = int(match.group(1))
        if 1 <= index <= len(ids):
            return f"[{ids[index - 1]}]"
        return match.group(0)

    return _NUMERIC_CITATION.sub(replace, answer)


def _ordered_report_evidence(evidence: list[Evidence], question: str) -> list[Evidence]:
    if not _is_financial_summary(question):
        return evidence

    def priority(item: Evidence) -> int:
        content = (item.content or "").casefold()
        has_revenue = any(term in content for term in _REVENUE_HEADLINE)
        has_profit = any(term in content for term in _PROFIT_HEADLINE)
        return 0 if has_revenue and has_profit else 1 if has_revenue or has_profit else 2

    return [item for _, item in sorted(enumerate(evidence), key=lambda pair: (priority(pair[1]), pair[0]))]


def _format_prompt_evidence(item: Evidence) -> str:
    """Keep report context compact while retaining a traceable cited fact."""
    evidence_class = item.metadata.get("evidence_class")
    publisher = item.metadata.get("source_publisher")
    applicability = item.metadata.get("reference_applicability")
    if evidence_class == "company_policy_reference":
        if item.metadata.get("synthetic_company_policy") is True:
            provenance = f"Synthetic policy for fictional Commerce Demo from {publisher or 'the demo organization'}; apply only to this synthetic scenario, never as policy of a real company. "
        else:
            provenance = f"Company-issued operating policy attributed to {publisher or 'the issuing organization'}; treat its stated scope and approval status as binding. "
        if applicability:
            provenance += f"Scope: {applicability} "
    elif evidence_class == "company_practice_reference":
        provenance = f"External operating reference published by {publisher or 'the cited organization'}; not Commerce Demo policy. "
        if applicability:
            provenance += f"Scope: {applicability} "
    elif evidence_class == "management_cookbook_reference":
        provenance = f"Management cookbook published by {publisher or 'the cited organization'}; an attributed decision method, not Commerce Demo policy. "
        if applicability:
            provenance += f"Scope: {applicability} "
    elif evidence_class == "platform_operating_rule":
        provenance = f"Platform-specific operating rule from {publisher or 'the cited platform'}; apply only if this platform is in scope. "
        if applicability:
            provenance += f"Source applicability and caveats: {applicability} "
    elif item.source_type == "commerce_schema":
        provenance = "Curated Commerce schema/data-coverage constraint; this describes unavailable fields, not a measured business observation. "
    else:
        provenance = ""
    if item.source_type == "verified_metric":
        metadata = item.metadata
        qualifier = {
            "approximately": "approximately",
            "more_than": "more than",
            "at_least": "at least",
            "less_than": "less than",
            "at_most": "at most",
        }.get(metadata.get("value_qualifier", "exact"), "")
        period = metadata.get("reporting_period", "FY")
        fiscal_year = metadata.get("fiscal_year", "")
        fact = (
            f"Verified KPI: {metadata.get('metric_label', item.source)}; "
            f"{period} {fiscal_year} = {qualifier + ' ' if qualifier else ''}{metadata.get('metric_value', '')} "
            f"{metadata.get('unit', '')}."
        )
        page = metadata.get("page_number")
        return f"[{item.citation_id}] {item.source}, page {page}. {provenance}{fact}"
    content = (item.content or "").strip()
    if len(content) > 1200:
        content = content[:1200].rsplit(" ", 1)[0] + " …"
    page = item.metadata.get("page_number")
    page_text = f", page {page}" if page is not None else ""
    return f"[{item.citation_id}] {item.source}{page_text}. {provenance}\n{content}"


def _financial_facts_match_cited_evidence(answer: str, evidence: list[Evidence]) -> bool:
    cited_ids = set(_CITATION.findall(answer))
    cited_text = " ".join(
        item.content or "" for item in evidence if item.citation_id in cited_ids
    )
    answer_text = _CITATION.sub("", answer)

    def numbers(text: str) -> set[str]:
        return {
            re.sub(r"(?<=\d)[\s.,]+(?=\d)", "", match)
            for match in _NUMBER.findall(text)
        }

    def scales(text: str) -> set[str]:
        return {scale for scale, pattern in _UNIT_SCALE_PATTERNS.items() if pattern.search(text)}

    def currencies(text: str) -> set[str]:
        return {currency for currency, pattern in _CURRENCY_PATTERNS.items() if pattern.search(text)}

    answer_numbers = numbers(answer_text)
    evidence_numbers = numbers(cited_text)
    answer_scales = scales(answer_text)
    evidence_scales = scales(cited_text)
    answer_currencies = currencies(answer_text)
    evidence_currencies = currencies(cited_text)
    return (
        bool(answer_numbers)
        and answer_numbers.issubset(evidence_numbers)
        and bool(answer_scales)
        and answer_scales.issubset(evidence_scales)
        and (not evidence_currencies or answer_currencies.issubset(evidence_currencies))
    )


def _decision_numeric_facts_match_cited_evidence(answer: str, evidence: list[Evidence]) -> bool:
    """Require numeric decision-report claims to be source-reported, not calculated in prose."""
    cited_ids = set(_CITATION.findall(answer))
    cited = [item for item in evidence if item.citation_id in cited_ids]
    answer_text = _CITATION.sub("", answer)
    source_text = " ".join(
        " ".join((
            item.source or "",
            str(item.metadata.get("title", "")),
            item.content or "",
            str(item.metadata.get("metric_value", "")),
            str(item.metadata.get("fiscal_year", "")),
        ))
        for item in cited
    )

    def numbers(text: str) -> set[str]:
        return {
            re.sub(r"(?<=\d)[\s.,]+(?=\d)", "", match)
            for match in _NUMBER.findall(text)
        }

    # Ordered-list markers are formatting, not business facts to cite.
    answer_text = re.sub(r"(?m)^\s*\d{1,2}\.\s+", "", answer_text)
    answer_numbers = numbers(answer_text)
    return answer_numbers.issubset(numbers(source_text))


def _has_unsupported_inventory_overlap_count(answer: str, evidence: list[Evidence]) -> bool:
    """Require a joint stockout/overstock field before asserting their overlap count."""
    overlap_claim = re.compile(
        r"\b(?:both|overlap(?:ping)?|joint)\b[^.!?\n]{0,70}\b(?:flags?|stockout|overstock|rows?|products?)\b|"
        r"\b(?:flags?|stockout|overstock|rows?|products?)\b[^.!?\n]{0,70}\b(?:both|overlap(?:ping)?|joint)\b|"
        r"cả hai cờ|đồng thời[^.!?\n]{0,70}(?:cờ|stockout|overstock)",
        re.IGNORECASE,
    )
    overlap_source = re.compile(r"\bboth[_ -]?flagged(?:[_ -]?(?:rows|products))?\b", re.IGNORECASE)
    joint_sql_predicate = re.compile(
        r"\bstockout_flag\b[^;]{0,180}\bAND\b[^;]{0,180}\boverstock_flag\b|"
        r"\boverstock_flag\b[^;]{0,180}\bAND\b[^;]{0,180}\bstockout_flag\b",
        re.IGNORECASE,
    )
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", answer):
        if not overlap_claim.search(sentence) or not _NUMBER.search(sentence):
            continue
        cited_ids = set(_CITATION.findall(sentence))
        for item in evidence:
            if item.citation_id not in cited_ids or item.source_type != "commerce_sql":
                continue
            source = f"{item.content or ''} {item.metadata.get('sql_query', '')}"
            trusted_dashboard_overlap = (
                item.metadata.get("commerce_aggregate_key") == "inventory_latest_flag_overlap"
                and re.search(r'"both_flagged_rows"\s*:\s*\d+', item.content or "")
            )
            if trusted_dashboard_overlap or overlap_source.search(source) or joint_sql_predicate.search(source):
                break
        else:
            return True
    return False


def _report_validation_failure(
    answer: str, evidence: list[Evidence], allowed: set[str], question: str,
) -> str | None:
    citations = set(_CITATION.findall(answer))
    if not citations or citations - allowed:
        return "missing_or_unknown_citations"
    if _is_financial_summary(question) and not _financial_facts_match_cited_evidence(answer, evidence):
        return "financial_values_or_units_do_not_match_cited_evidence"
    if _is_decision_support_request(question) and _has_unsupported_numeric_decision_gate(answer, evidence):
        return "decision_gate_uses_an_unsourced_numeric_threshold"
    if _is_decision_support_request(question) and _has_unsupported_inventory_overlap_count(answer, evidence):
        return "inventory_overlap_count_not_present_in_cited_sql"
    if _is_decision_support_request(question) and not _decision_numeric_facts_match_cited_evidence(answer, evidence):
        return "decision_numeric_claim_not_present_in_cited_evidence"
    return None


def _has_unsolicited_commerce_recommendation(answer: str) -> bool:
    """Catch recommendations or experiments in a Commerce answer to a descriptive query."""
    return bool(re.search(
        r"\b(?:recommended next move|recommend(?:ation)?|should (?:we|you)|next step|holdout|"
        r"treatment\s*/\s*control|experiment|pilot|expand the campaign|prioriti[sz]e)\b|"
        r"(?:khuyến nghị|bước tiếp theo|nên ưu tiên|hãy (?:thử|dùng|thu thập|mở rộng))",
        answer,
        re.IGNORECASE,
    ))


def _has_verbatim_synthetic_policy_quote(answer: str, evidence: list[Evidence]) -> bool:
    """Do not surface copied OCR errors from fictional policy scans as authoritative wording."""
    quotes = re.findall(r"[“\"]([^”\"]{30,})[”\"]", answer)
    if not quotes:
        return False
    normalized_answer_quotes = [" ".join(quote.split()).casefold() for quote in quotes]
    source_texts = [
        " ".join((item.content or "").split()).casefold()
        for item in evidence
        if item.metadata.get("synthetic_company_policy") is True and item.content
    ]
    return any(quote in source for quote in normalized_answer_quotes for source in source_texts)


def _commerce_schema_gap_citation_failure(answer: str, evidence: list[Evidence], question: str) -> bool:
    if not _is_inventory_service_target_question(question):
        return False
    target_limitations = {
        item.citation_id for item in evidence
        if item.source_type == "commerce_schema" and item.citation_id
        and "approved service-level target" in (item.content or "").casefold()
    }
    claims_target_missing = bool(re.search(
        r"(?:no|not an? approved|does not (?:establish|include)|without|missing)[^.!?\n]{0,60}"
        r"(?:service[- ]level target|service target|target)|"
        r"(?:không có|chưa có|không thể đặt|chưa thể đặt)[^.!?\n]{0,60}(?:service[- ]level target|service target|mục tiêu dịch vụ)",
        answer,
        re.IGNORECASE,
    ))
    return bool(claims_target_missing and target_limitations and target_limitations.isdisjoint(_CITATION.findall(answer)))


def _has_unsupported_monotonic_commerce_trend(answer: str, evidence: list[Evidence]) -> bool:
    """Reject a claim of a steady direction when the cited yearly observations reverse."""
    trend_claims = (
        r"\b(?:steadily|consistently|continuously|each year|every year|year after year)\b",
        r"\b(?:giảm dần|tăng dần|liên tục|đều đặn|mỗi năm đều)\b",
    )
    if not any(re.search(pattern, answer, re.IGNORECASE) for pattern in trend_claims):
        return False

    observations = []
    for item in evidence:
        match = re.search(r"observations:\s*(\[.*\])", item.content or "", re.DOTALL)
        if not match:
            continue
        try:
            rows = json.loads(match.group(1))
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(rows, list):
            observations.extend(row for row in rows if isinstance(row, dict))
    if not observations:
        return False

    requested_measures = set()
    measure_terms = {
        "avg_shipping_fee": (("avg_shipping_fee",), ("shipping fee", "shipping cost", "phí vận chuyển", "cước vận chuyển")),
        "avg_transit_days": (("avg_transit_days", "avg_transit_time", "avg_transit_time_days"),
                             ("transit time", "delivery time", "thời gian giao", "thời gian vận chuyển")),
        "fill_rate": (("fill_rate", "avg_fill_rate"), ("fill rate", "availability", "tỷ lệ đáp ứng", "khả dụng")),
        "units_sold": (("units_sold", "units"), ("units sold", "số lượng bán", "lượng bán")),
        "net_sales": (("net_sales", "net_item_sales"), ("net sales", "doanh thu thuần")),
        "delivered_orders": (("delivered_orders",), ("delivered orders", "đơn hàng đã giao")),
    }
    answer_folded = answer.casefold()
    requested_measures = {
        key for key, (_, terms) in measure_terms.items() if any(term in answer_folded for term in terms)
    }
    if not requested_measures:
        return False
    all_measure_aliases = {
        alias for aliases, _ in measure_terms.values() for alias in aliases
    }

    for measure in requested_measures:
        groups: dict[tuple, list[tuple[int, float]]] = {}
        for row in observations:
            aliases, _ = measure_terms[measure]
            year, value = row.get("year"), next((row[key] for key in aliases if row.get(key) is not None), None)
            if isinstance(year, bool) or isinstance(value, bool):
                continue
            try:
                year = int(Decimal(str(year)))
                value = float(Decimal(str(value)))
            except (ArithmeticError, ValueError):
                continue
            group = tuple(sorted(
                (key, str(value)) for key, value in row.items()
                if key != "year" and key not in all_measure_aliases and isinstance(value, (str, bool))
            ))
            groups.setdefault(group, []).append((year, float(value)))
        for series in groups.values():
            series.sort()
            values = [value for _, value in series]
            if len(values) >= 3 and not (
                all(left <= right for left, right in zip(values, values[1:]))
                or all(left >= right for left, right in zip(values, values[1:]))
            ):
                return True
    return False
def _commerce_sql_fallback_facts(domain: str, question: str, evidence: list[Evidence]) -> str:
    """Keep requested SQL observations visible when both generated drafts fail validation."""
    requested_years = {int(year) for year in re.findall(r"\b(?:19|20)\d{2}\b", question)}
    year_range = re.search(
        r"\b((?:19|20)\d{2})\s*(?:-|–|—|to|through|đến)\s*((?:19|20)\d{2})\b",
        question,
        re.IGNORECASE,
    )
    if year_range:
        first, last = map(int, year_range.groups())
        if first <= last and last - first <= 20:
            requested_years.update(range(first, last + 1))
    observations = []
    service_target_limitations = [
        item.citation_id for item in evidence
        if item.source_type == "commerce_schema" and item.citation_id
        and "approved service-level target" in (item.content or "").casefold()
    ]
    service_target_citation = "".join(f"[{citation}]" for citation in service_target_limitations)
    for item in evidence:
        if item.source_type != "commerce_sql" or not item.citation_id:
            continue
        prefix, separator, payload = (item.content or "").partition(" aggregate observations: ")
        if not separator:
            continue
        try:
            rows = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            continue
        rows = [row for row in rows if isinstance(row, dict)]
        if requested_years:
            rows = [row for row in rows if "year" not in row or row.get("year") in requested_years]
        observations.append((prefix, rows, item.citation_id))

    query_text = question.casefold()
    asks_transfer = any(term in query_text for term in (
        "transfer", "reallocat", "rebalanc", "chuyển hàng", "điều chuyển", "phân bổ lại", "tái cân bằng",
    ))
    overlap_fact = ""
    if domain == "inventory_allocation" and asks_transfer:
        for name, rows, citation in observations:
            if name == "inventory_latest_flag_overlap" and rows:
                row = rows[0]
                both = row.get("both_flagged_rows")
                if both is not None:
                    overlap_fact = (
                        f"Trong snapshot {row.get('snapshot_date', 'mới nhất')}, {both} dòng sản phẩm "
                        f"có đồng thời cờ stockout và overstock; hai tổng cờ có thể chồng lấp [{citation}].\n"
                    )
                break

    for name, rows, citation in observations:
        if (domain == "inventory_allocation" and name == "inventory_by_year" and rows
                and (requested_years or any(term in question.casefold() for term in (
                    "availability", "fill rate", "thay đổi", "xu hướng",
                )))):
            details = "; ".join(
                f"FY{row.get('year')}: " + ", ".join(
                    f"{key}={row[key]}" for key in (
                        "avg_fill_rate", "stockout_snapshots", "sku_snapshots",
                    ) if row.get(key) is not None
                )
                for row in rows
            )
            if details:
                historical = "Annual inventory observations (historical fill-rate ratio): "
                if _is_vietnamese_text(question):
                    historical = "Quan sát tồn kho hằng năm (fill rate lịch sử): "
                facts = f"{historical}{details} [{citation}]."
                if not _is_inventory_service_target_question(question):
                    return facts + "\n"
                if _is_vietnamese_text(question):
                    return (
                        facts + " Dữ liệu không có service-level target đã được phê duyệt "
                        f"{service_target_citation or f'[{citation}]'}.\n"
                    )
                return (
                    facts + " The data has no approved service-level target "
                    f"{service_target_citation or f'[{citation}]'}.\n"
                )
        if domain == "inventory_allocation" and name == "inventory_latest_by_category" and rows:
            query = question.casefold()
            asks_low_stock = any(term in query for term in (
                "low stock", "low-stock", "sắp hết hàng", "sắp hết tồn", "cảnh báo tồn kho thấp",
            ))
            asks_overstock = "overstock" in query or "dư hàng" in query or "tồn kho dư" in query
            asks_stockout = any(term in query for term in (
                "stockout", "out of stock", "hết hàng", "thiếu hàng",
            )) and not asks_low_stock
            asks_category_ranking = any(term in query for term in (
                "category", "categories", "nhóm hàng", "danh mục",
            ))
            if asks_low_stock:
                continue
            if not asks_category_ranking:
                continue
            metric = (
                "overstock_products" if asks_overstock and not asks_stockout else
                "stockout_products" if asks_stockout else None
            )
            if not metric:
                continue
            ranked = sorted((row for row in rows if isinstance(row.get(metric), (int, float))),
                            key=lambda row: row[metric], reverse=True)
            if ranked:
                details = "; ".join(f"{row.get('category')}={row[metric]}" for row in ranked)
                date = ranked[0].get("snapshot_date")
                if _is_vietnamese_text(question):
                    metric_label = "sản phẩm bị gắn cờ overstock" if metric == "overstock_products" else "sản phẩm bị gắn cờ stockout"
                    return (
                        overlap_fact + f"So sánh theo danh mục trong snapshot {date}: {details} ({metric_label}) [{citation}]. "
                        f"Cao nhất là {ranked[0].get('category')} với {ranked[0][metric]} {metric_label} [{citation}].\n"
                    )
                return overlap_fact + f"SQL comparison{f' ({date})' if date else ''}: {details} [{citation}]. Highest: {ranked[0].get('category')}={ranked[0][metric]} [{citation}].\n"
        if domain == "nationwide_logistics" and name == "logistics_by_year_region" and rows:
            query = question.casefold()
            asks_trend = bool(requested_years) or any(term in query for term in (
                "trend", "change", "changed", "over time", "during", "thay đổi", "xu hướng", "giai đoạn",
            ))
            if not requested_years and not asks_trend:
                latest_year = max((row.get("year") for row in rows if isinstance(row.get("year"), int)), default=None)
                if latest_year is not None:
                    rows = [row for row in rows if row.get("year") == latest_year]
            transit = any(term in question.casefold() for term in (
                "avg_transit_days", "average transit", "transit time", "thời gian vận chuyển",
            ))
            fee = any(term in question.casefold() for term in (
                "fee", "shipping cost", "shipping fee", "chi phí", "cước",
            ))
            metrics = [key for key, enabled in (("avg_transit_days", transit or not fee),
                                                 ("avg_shipping_fee", fee),
                                                 ("median_transit_days", "median" in question.casefold() or "trung vị" in question.casefold())) if enabled]
            # For a multi-year question, summarize endpoints per region instead of
            # dumping every annual row. Report direction, not calculated deltas:
            # numeric claims must appear verbatim in the cited observations.
            if asks_trend and len({row.get("year") for row in rows}) > 1:
                by_region: dict[str, list[dict]] = {}
                for row in rows:
                    if row.get("region") and isinstance(row.get("year"), int):
                        by_region.setdefault(str(row["region"]), []).append(row)
                trend_lines = []
                metric_labels = {
                    "avg_transit_days": "thời gian vận chuyển trung bình (ngày)",
                    "avg_shipping_fee": "phí giao hàng trung bình",
                    "median_transit_days": "trung vị thời gian vận chuyển (ngày)",
                }
                for region, yearly_rows in sorted(by_region.items()):
                    yearly_rows.sort(key=lambda row: row["year"])
                    first, last = yearly_rows[0], yearly_rows[-1]
                    changes = []
                    for metric in metrics:
                        start, end = first.get(metric), last.get(metric)
                        if isinstance(start, (int, float)) and isinstance(end, (int, float)):
                            delta = end - start
                            label = metric_labels.get(metric, metric) if _is_vietnamese_text(question) else metric
                            direction = (
                                "gần như ổn định" if round(delta, 2) == 0 else
                                "tăng" if delta > 0 else "giảm"
                            )
                            if not _is_vietnamese_text(question):
                                direction = (
                                    "roughly stable" if round(delta, 2) == 0 else
                                    "increased" if delta > 0 else "decreased"
                            )
                            changes.append(
                                f"{label}: FY{first['year']} {start:g} → FY{last['year']} {end:g} "
                                f"({direction})"
                            )
                    if changes:
                        trend_lines.append(f"{region}: " + "; ".join(changes))
                if trend_lines:
                    if _is_vietnamese_text(question):
                        return ("So sánh mô tả đầu-cuối theo vùng: " + "; ".join(trend_lines)
                                + f". Chênh lệch này không cho biết nguyên nhân. [{citation}]\n")
                    return ("Descriptive endpoint comparison by region: " + "; ".join(trend_lines)
                            + f". These differences do not establish a cause. [{citation}]\n")
            details = "; ".join(
                f"FY{row.get('year')} {row.get('region')}: " + ", ".join(f"{metric}={row[metric]}" for metric in metrics if row.get(metric) is not None)
                for row in rows if any(row.get(metric) is not None for metric in metrics)
            )
            if details:
                asks_ranking = any(term in query for term in (
                    "highest", "longest", "slowest", "most", "cao nhất", "dài nhất", "lâu nhất", "chậm nhất",
                ))
                years = {row.get("year") for row in rows}
                ranked = [row for row in rows if isinstance(row.get("avg_transit_days"), (int, float))]
                highest = ""
                if transit and asks_ranking and len(years) == 1 and ranked:
                    maximum = max(row["avg_transit_days"] for row in ranked)
                    leaders = sorted({row.get("region") for row in ranked if row["avg_transit_days"] == maximum})
                    highest = f" Highest average transit time in FY{next(iter(years))}: {', '.join(leaders)}={maximum} days [{citation}]."
                if _is_vietnamese_text(question):
                    metric_labels = {
                        "avg_transit_days": "thời gian vận chuyển trung bình (ngày)",
                        "avg_shipping_fee": "phí giao hàng trung bình",
                        "median_transit_days": "trung vị thời gian vận chuyển (ngày)",
                    }
                    localized_details = "; ".join(
                        f"FY{row.get('year')} {row.get('region')}: " + ", ".join(
                            f"{metric_labels.get(metric, metric)}={row[metric]}"
                            for metric in metrics if row.get(metric) is not None
                        ) for row in rows if any(row.get(metric) is not None for metric in metrics)
                    )
                    highest = ""
                    if transit and asks_ranking and len(years) == 1 and ranked:
                        maximum = max(row["avg_transit_days"] for row in ranked)
                        leaders = sorted({row.get("region") for row in ranked if row["avg_transit_days"] == maximum})
                        highest = f" Vùng có thời gian vận chuyển trung bình cao nhất FY{next(iter(years))}: {', '.join(leaders)}={maximum} ngày [{citation}]."
                    return f"Quan sát vận chuyển theo vùng: {localized_details} [{citation}].{highest}\n"
                return f"SQL regional observations: {details} [{citation}].{highest}\n"
        asks_roi = any(term in question.casefold() for term in (
            "roi", "return on investment", "tỷ suất hoàn vốn", "hiệu quả đầu tư", "lợi tức trên",
        ))
        if domain == "promotion_planning" and asks_roi:
            if _is_vietnamese_text(question):
                return (
                    "Không thể tính ROI theo kênh/chiến dịch từ các quan sát này: dữ liệu không có chi phí chiến dịch, "
                    "traffic gắn với chiến dịch hoặc kết quả đối chứng. Có thể tính proxy lãi gộp hàng hóa từ doanh số "
                    "từng dòng trừ COGS trong catalog, nhưng proxy đó không phải biên lợi nhuận đóng góp hay ROI; "
                    f"cần xác thực giả định COGS và bổ sung chi phí/đo lường nhân quả trước khi phân bổ ngân sách [{citation}].\n"
                )
            return (
                "Channel or campaign ROI cannot be calculated from these observations: the Commerce tables do not provide "
                "campaign spend, campaign-attributed traffic, or a counterfactual outcome. A merchandise gross-profit "
                "proxy can be computed from item sales less catalog COGS, but it is not contribution margin or ROI; "
                f"validate the COGS assumption and add campaign cost and causal measurement before allocating budget [{citation}].\n"
            )
        if (domain == "promotion_planning" and name == "promotions_by_campaign" and rows
                and any(term in question.casefold() for term in ("campaign", "chiến dịch"))):
            asks_profit = any(term in question.casefold() for term in (
                "gross profit", "profitability", "profit", "lợi nhuận", "lãi gộp",
            ))
            metric = "merchandise_gross_profit_proxy" if asks_profit else "net_item_sales"
            asks_single_winner = any(term in question.casefold() for term in (
                "highest", "largest", "best-performing", "top campaign", "cao nhất", "lớn nhất", "tốt nhất",
            ))
            campaigns = sorted(rows, key=lambda row: row.get(metric, 0), reverse=True)[:1 if asks_single_winner else 5]
            details = "; ".join(
                f"{row.get('campaign')} ({row.get('campaign_start')} to {row.get('campaign_end')}): {metric}={row.get(metric)}"
                for row in campaigns
            )
            if details:
                basis = (
                    "estimated merchandise gross-profit proxy from transaction prices, discounts and catalog COGS; "
                    "not contribution margin, causal profit impact, or ROI"
                    if asks_profit else "campaign-window tagged net item sales"
                )
                if _is_vietnamese_text(question):
                    basis = (
                        "proxy lãi gộp hàng hóa ước tính (không phải biên lợi nhuận đóng góp, ROI hay lợi nhuận tăng thêm do chiến dịch)"
                        if asks_profit else "doanh thu thuần mặt hàng gắn tag trong thời gian chạy"
                    )
                    return (
                        f"Kết quả chiến dịch, xếp theo {basis} (mặt hàng gắn hai chiến dịch có thể được tính ở cả hai): "
                        f"{details} [{citation}].\n"
                    )
                return (
                    f"Campaign-window outcomes ranked by {basis} (dual-tagged items may appear under both campaigns): "
                    f"{details} [{citation}].\n"
                )
        if domain == "promotion_planning" and rows and "campaign" not in question.casefold():
            comparisons = []
            query = question.casefold()
            requested_metrics = []
            metric_labels = {
                "delivered_orders": "đơn hàng đã giao" if _is_vietnamese_text(question) else "delivered orders",
                "units": "số lượng bán" if _is_vietnamese_text(question) else "units sold",
                "net_sales": "doanh thu thuần" if _is_vietnamese_text(question) else "net sales",
                "discounts": "mức giảm giá" if _is_vietnamese_text(question) else "discounts",
                "merchandise_gross_profit_proxy": "proxy lãi gộp hàng hóa" if _is_vietnamese_text(question) else "merchandise gross-profit proxy",
                "merchandise_gross_margin_proxy": "proxy biên lãi gộp hàng hóa" if _is_vietnamese_text(question) else "merchandise gross-margin proxy",
            }
            metric_terms = {
                "delivered_orders": ("delivered order", "đơn hàng", "đã giao"),
                "units": ("units", "số lượng", "sản lượng"),
                "net_sales": ("net sales", "revenue", "doanh thu", "sales"),
                "discounts": ("discount", "giảm giá", "chiết khấu"),
                "merchandise_gross_profit_proxy": ("gross profit", "lợi nhuận", "lãi gộp"),
                "merchandise_gross_margin_proxy": ("gross margin", "biên lợi nhuận", "biên lãi"),
            }
            for metric, terms in metric_terms.items():
                if any(term in query for term in terms):
                    requested_metrics.append(metric)
            if not requested_metrics:
                requested_metrics = ["delivered_orders", "net_sales"]
            for row in rows:
                if "used_promotion" not in row:
                    continue
                period = f"FY{row['year']}" if row.get("year") else "period"
                group = (
                    ("gắn khuyến mãi" if _is_vietnamese_text(question) else "tagged")
                    if row["used_promotion"] else
                    ("không gắn khuyến mãi" if _is_vietnamese_text(question) else "untagged")
                )
                metrics = [
                    f"{metric_labels[metric]}={row[metric]}"
                    for metric in requested_metrics if row.get(metric) is not None
                ]
                comparisons.append(f"{period} {group}: {'; '.join(metrics)} [{citation}]")
            if comparisons:
                if _is_vietnamese_text(question):
                    return "So sánh mô tả giữa đơn gắn và không gắn khuyến mãi (không chứng minh quan hệ nhân quả): " + "; ".join(comparisons) + ".\n"
                return "SQL tagged-versus-untagged observations (descriptive, not causal): " + "; ".join(comparisons) + ".\n"
    return overlap_fact


def _commerce_safe_fallback(
    domain: str, question: str, evidence: list[Evidence], *, decision_request: bool | None = None,
) -> str:
    """Return cited SQL facts and a qualitative next step when both drafts fail validation."""
    if decision_request is None:
        decision_request = _is_decision_support_request(question)
    sql_facts = _commerce_sql_fallback_facts(domain, question, evidence)
    sql_ids = [item.citation_id for item in evidence if item.source_type == "commerce_sql" and item.citation_id]
    if not decision_request:
        if sql_facts:
            return sql_facts
        if domain == "inventory_allocation" and any(term in question.casefold() for term in (
            "low-stock", "low stock", "sắp hết hàng", "cảnh báo tồn kho thấp",
        )):
            citations = "".join(f"[{item.citation_id}]" for item in evidence if item.source_type == "commerce_schema" and item.citation_id)
            sql_citation = f"[{sql_ids[0]}]" if sql_ids else ""
            return (
                "Category aggregates provide stockout/overstock flags, not a low-stock alert count. "
                f"{citations}{sql_citation}"
            ).strip()
        citation = f"[{sql_ids[0]}]" if sql_ids else ""
        return f"Không tìm thấy quan sát SQL phù hợp để trả lời câu hỏi này. {citation}".strip()
    references = [item for item in evidence if item.metadata.get("evidence_class") in {
        "company_policy_reference", "management_cookbook_reference", "platform_operating_rule",
        "company_practice_reference",
    }]
    reference = next((item for item in references if item.metadata.get("evidence_class") == "company_policy_reference"), None)
    reference = reference or next((item for item in references if item.metadata.get("evidence_class") == "management_cookbook_reference"), None)
    reference = reference or next((item for item in references if item.metadata.get("evidence_class") == "platform_operating_rule"), None)
    reference = reference or next((item for item in references if item.metadata.get("evidence_class") == "company_practice_reference"), None)
    refs = [reference.citation_id] if reference and reference.citation_id else []
    is_vietnamese = _is_vietnamese_text(question)
    sql_citation = "".join(f"[{item}]" for item in sql_ids)
    limitation_ids = [
        item.citation_id for item in evidence
        if item.source_type == "commerce_schema" and item.citation_id
    ]
    limitation_citation = "".join(f"[{item}]" for item in limitation_ids)
    service_target_citation = "".join(
        f"[{item.citation_id}]" for item in evidence
        if item.source_type == "commerce_schema" and item.citation_id
        and "approved service-level target" in (item.content or "").casefold()
    )
    ref_citation = "".join(f"[{item}]" for item in refs)
    publisher = reference.metadata.get("source_publisher", "the cited company") if reference else ""
    reference_excerpt = ""
    if reference and reference.content:
        normalized_reference = " ".join(reference.content.split())
        if domain == "nationwide_logistics":
            sentences = re.split(r"(?<=[.!?])\s+", normalized_reference)
            method_terms = (
                "closest location", "shortest distance", "split fulfillment", "split shipment",
                "inventory available", "inventory availability", "destination market",
                "business priorities", "customer needs", "balance speed and cost", "route optimization",
            )
            best_method = max(
                sentences,
                key=lambda sentence: sum(term in sentence.casefold() for term in method_terms),
                default="",
            )
            if sum(term in best_method.casefold() for term in method_terms):
                normalized_reference = best_method
        excerpt_limit = min(len(normalized_reference), 420)
        if len(normalized_reference) <= excerpt_limit:
            reference_excerpt = normalized_reference
        else:
            sentence_end = max(normalized_reference.rfind(mark, 150, excerpt_limit) for mark in (".", "!", "?"))
            reference_excerpt = (
                normalized_reference[:sentence_end + 1]
                if sentence_end >= 150 else normalized_reference[:excerpt_limit].rstrip() + "…"
            )
    is_platform_rule = bool(reference and reference.metadata.get("evidence_class") == "platform_operating_rule")
    applicability_note = reference.metadata.get("reference_applicability", "") if reference else ""
    applicability_note = re.sub(r"\s{2,}", " ", re.sub(r"\b(?:19|20)\d{2}\b", "", applicability_note)).strip()
    if reference and reference.metadata.get("evidence_class") == "company_policy_reference":
        synthetic_policy = reference.metadata.get("synthetic_company_policy") is True
        if synthetic_policy:
            intro = ("Policy giả lập Commerce Demo đã được truy xuất; xem nguồn để đối chiếu nội dung OCR. "
                     if is_vietnamese else
                     "A synthetic Commerce Demo policy was retrieved; consult the source to verify its OCR text. ")
            scope = (f"Chỉ áp dụng cho kịch bản dữ liệu giả lập này, không phải chính sách của doanh nghiệp thật. {ref_citation}"
                     if is_vietnamese else f"Apply only to this fictional demo scenario, not to a real company's operations. {ref_citation}")
        else:
            intro = (f"Chính sách nội bộ do {publisher} phát hành nêu: “{reference_excerpt}” " if is_vietnamese
                     else f"The company-issued policy from {publisher} states: “{reference_excerpt}” ")
            scope = (f"Áp dụng trong phạm vi chính sách đã nêu; xác minh hiệu lực trước khi thực hiện. {ref_citation}"
                     if is_vietnamese else f"Apply only within its stated scope and verify that it is current before acting. {ref_citation}")
        reference_basis = intro + scope
    elif reference and is_platform_rule and is_vietnamese:
        localized_caveat = (
            "Đây là hướng dẫn lịch sử; nhãn giao diện và ngưỡng trong tài liệu có thể đã thay đổi."
            if "historical" in applicability_note.casefold()
            else "Chỉ áp dụng hướng dẫn sau khi xác nhận Shop đang dùng nền tảng này."
        )
        reference_basis = (
            f"Tài liệu vận hành của {publisher} mô tả quy trình cho nền tảng được nêu. "
            f"Hướng dẫn chỉ áp dụng trong phạm vi nền tảng đó. {localized_caveat} "
            f"Tài liệu không xác nhận trạng thái tồn kho hiện tại của Shop. {ref_citation}"
        )
    elif reference_excerpt and is_vietnamese:
        if reference and reference.metadata.get("evidence_class") == "management_cookbook_reference":
            reference_basis = (
                f"Cookbook quản lý của {publisher} đề xuất phương pháp: “{reference_excerpt}” "
                f"Đây là phương pháp tham khảo bên ngoài, không phải chính sách của Commerce Demo. {ref_citation}"
            )
        else:
            reference_basis = (
                f"Đoạn tài liệu được truy xuất từ {publisher}: “{reference_excerpt}” "
                f"Đây là hướng dẫn tham khảo bên ngoài, không phải chính sách của Commerce Demo. {ref_citation}"
            )
    elif reference and is_platform_rule:
        reference_basis = (
            f"The guide from {publisher} provides an operating workflow for the named platform. "
            f"This guidance applies only within the named platform. Source caveats: {applicability_note} "
            f"The guide does not establish this Shop's current inventory state. {ref_citation}"
        )
    elif reference_excerpt:
        reference_basis = (
            f"Retrieved passage from {publisher}: “{reference_excerpt}” "
            f"This is external guidance, not Commerce Demo policy. {ref_citation}"
        )
    else:
        reference_basis = ""
    if domain == "inventory_allocation":
        if _is_inventory_service_target_question(question):
            if is_vietnamese:
                answer = (
                    "Kết luận: Chưa thể đặt service target mới chỉ từ các quan sát lịch sử. Fill rate mô tả availability đã ghi nhận, "
                    "không phải mục tiêu đã được phê duyệt. Hãy xin service-level policy được người có thẩm quyền duyệt và xác định "
                    f"mức dịch vụ cùng chi phí thiếu hàng trước khi chốt target. {service_target_citation}{sql_citation}\n"
                )
            else:
                answer = (
                    "Conclusion: Historical observations alone do not justify a new service target. Fill rate describes recorded "
                    "availability; it is not an approved target. Obtain an authorized service-level policy and define the service/cost "
                    f"trade-off before setting one. {service_target_citation}{sql_citation}\n"
                )
            example = reference_basis
        elif is_vietnamese and is_platform_rule:
            answer = (
                "Khuyến nghị: Với nền tảng được nêu, dùng quy trình cảnh báo theo SKU trong tài liệu để kiểm tra tình trạng "
                "và nhu cầu bổ sung của chính Shop trước khi hành động. Dữ liệu Commerce chỉ có aggregate theo danh mục, "
                "nên chưa xác nhận được SKU hay Shop Shopee cụ thể nào đang sắp hết hàng. "
                f"Hãy xác minh tồn kho và nhu cầu của SKU trong Shop; chỉ cân nhắc bổ sung khi cảnh báo được xác nhận. {sql_citation}\n"
            )
            example = reference_basis
        elif is_vietnamese:
            answer = (
                "Khuyến nghị: Chưa điều chuyển tồn kho. Aggregate theo danh mục không xác định được SKU nào dư ở đâu "
                "và đang thiếu ở đâu. Hãy ghép dữ liệu nhu cầu, tồn kho SKU theo địa điểm, lead time và chi phí trước "
                f"khi thử điều chuyển. {limitation_citation}{sql_citation}\n"
            )
            example = reference_basis
        elif is_platform_rule:
            answer = (
                "Recommended next move: For the named platform, use the cited SKU-level alert workflow to check the Shop's "
                "own status and replenishment need before acting. Commerce only provides category aggregates, so it does "
                "not establish that a particular Shopee Shop or SKU has a low-stock alert. Verify that Shop's SKU-level "
                f"stock and demand; consider replenishment only if the alert is confirmed. {sql_citation}\n"
            )
            example = reference_basis
        else:
            answer = (
                "Recommended next move: Do not rebalance inventory yet. Category aggregates do not identify which SKU "
                "is surplus at one location and short at another. First match SKU-level demand and on-hand stock by "
                f"location, then add lead time and costs before testing a transfer. {limitation_citation}{sql_citation}\n"
            )
            example = reference_basis
    elif domain == "promotion_planning":
        if not reference:
            if is_vietnamese:
                answer = (
                    "Chưa đủ bằng chứng để mở rộng chiến dịch: dữ liệu hiện có không xác định chi phí và phần kết quả "
                    "tăng thêm có thể quy cho chiến dịch. Cần bổ sung chi phí campaign, biên lợi nhuận và kết quả "
                    f"đối chứng trước khi quyết định phân bổ ngân sách. {limitation_citation}{sql_citation}\n"
                )
            else:
                answer = (
                    "There is not enough evidence to expand a campaign: the available data does not establish campaign "
                    "cost or the outcome attributable to it. Add campaign cost, margin, and a counterfactual outcome "
                    f"before deciding budget allocation. {limitation_citation}{sql_citation}\n"
                )
            example = ""
        elif is_vietnamese:
            answer = (
                "Khuyến nghị: Chưa mở rộng chiến dịch chỉ từ doanh số hoặc đơn hàng quan sát được; dữ liệu hiện có không "
                "cho biết phần kết quả tăng thêm có thể quy cho chiến dịch. Trước tiên, dùng thử nghiệm treatment/control hoặc holdout để ước lượng "
                "doanh số tăng thêm; sau đó cần chi phí campaign, mức giảm giá, tồn kho và mua lại để đánh giá phần "
                f"đóng góp lợi nhuận tăng thêm. {limitation_citation}{sql_citation}\n"
            )
            example = reference_basis
        else:
            answer = (
                "Recommended next move: Do not expand a campaign from observed sales or orders alone; the available data "
                "does not establish which outcomes are incremental to the campaign. First use a treatment/control or holdout experiment to "
                "estimate incremental sales. Then collect campaign cost, discount, availability, and repeat-purchase data "
                f"to assess incremental contribution margin. {limitation_citation}{sql_citation}\n"
            )
            example = reference_basis
    else:
        if is_vietnamese:
            answer = (
                "Khuyến nghị: Chưa thiết kế lại mạng lưới giao hàng từ thời gian vận chuyển theo vùng. Bổ sung điểm đi/đến, "
                "hãng vận chuyển, loại dịch vụ, SLA cam kết, năng lực tuyến và chi phí kiểm soát được; sau đó mới so sánh "
                f"dịch vụ và chi phí theo vùng. {limitation_citation}{sql_citation}\n"
            )
            example = reference_basis
        else:
            answer = (
                "Recommended next move: Do not redesign the delivery network from regional transit summaries alone. "
                "Collect origin/destination, carrier and service type, promised SLA, route capacity, and controllable "
                f"cost; then compare service and cost by region before considering a bounded test. {limitation_citation}{sql_citation}\n"
            )
            example = reference_basis
    return sql_facts + (answer + example if reference else answer)


def _commerce_question_safe_fallback(question: str, evidence: list[Evidence], *, decision_request: bool) -> str:
    """Expose validated dynamic-query rows as a compact table when model drafting fails."""
    sql_item = next((item for item in evidence if item.source_type == "commerce_sql"), None)
    if sql_item is None:
        return INSUFFICIENT_ANSWER
    rows = sql_item.content.partition(": ")[2]
    if not rows:
        return INSUFFICIENT_ANSWER
    citation = f"[{sql_item.citation_id}]" if sql_item.citation_id else ""
    domain = sql_item.metadata.get("commerce_domain")
    try:
        observations = json.loads(rows)
    except json.JSONDecodeError:
        observations = None
    table = ""
    omitted_note = ""
    if isinstance(observations, list) and observations and all(isinstance(row, dict) for row in observations):
        localized_labels = {
            "year": "Năm", "region": "Vùng", "category": "Danh mục", "snapshot_date": "Ngày snapshot",
            "avg_shipping_fee": "Phí vận chuyển TB", "avg_transit_time": "Thời gian vận chuyển TB (ngày)",
            "avg_transit_time_days": "Thời gian vận chuyển TB (ngày)", "avg_transit_days": "Thời gian vận chuyển TB (ngày)",
            "campaign": "Chiến dịch", "net_item_sales": "Doanh thu thuần", "net_sales": "Doanh thu thuần",
            "discounts": "Giảm giá", "delivered_orders": "Đơn đã giao", "units": "Số lượng",
            "stockout_count": "Cờ stockout", "stockout_products": "Sản phẩm có cờ stockout",
            "overstock_count": "Cờ overstock", "overstock_products": "Sản phẩm có cờ overstock",
        }
        columns = list(dict.fromkeys(key for row in observations for key in row))
        localized = _is_vietnamese_text(question)
        headings = [localized_labels.get(key, key.replace("_", " ").title()) if localized else key.replace("_", " ").title()
                    for key in columns]
        visible = observations[:20]
        table = "| " + " | ".join(headings) + " |\n| " + " | ".join("---" for _ in headings) + " |\n"
        for row in visible:
            values = []
            for key in columns:
                value = row.get(key)
                if isinstance(value, bool):
                    value = ("Có" if value else "Không") if localized else ("Yes" if value else "No")
                elif value is None:
                    value = "—"
                elif isinstance(value, (dict, list)):
                    value = json.dumps(value, ensure_ascii=False, sort_keys=True)
                values.append(str(value).replace("|", "\\|").replace("\n", " "))
            table += "| " + " | ".join(values) + " |\n"
        omitted = len(observations) - len(visible)
        if omitted:
            omitted_note = f"\n(Đã lược {omitted} dòng khác.)" if localized else f"\n({omitted} additional rows omitted.)"
    if decision_request and domain and _is_decision_support_request(question):
        if table:
            if _is_vietnamese_text(question):
                facts = f"Quan sát SQL theo câu hỏi:\n{table}{omitted_note} {citation}. "
            else:
                facts = f"SQL observations matching the question:\n{table}{omitted_note} {citation}. "
            return facts + _commerce_safe_fallback(
                domain, question, evidence, decision_request=True,
            )
    if _is_vietnamese_text(question):
        prefix = (
            "Chưa thể tổng hợp khuyến nghị cho câu hỏi này; đây là kết quả truy vấn SQL đúng theo lát cắt đã hỏi: "
            if decision_request else "Kết quả truy vấn SQL theo câu hỏi: "
        )
    else:
        prefix = (
            "A recommendation could not be synthesized for this question; these are the matching SQL observations: "
            if decision_request else "SQL observations matching the question: "
        )
    reference = next((item for item in evidence if item.citation_id and item.metadata.get("evidence_class") in {
        "company_policy_reference", "company_practice_reference", "platform_operating_rule",
        "management_cookbook_reference",
    }), None)
    reference_note = ""
    if decision_request and reference:
        source_citation = f"[{reference.citation_id}]"
        if reference.metadata.get("synthetic_company_policy") is True:
            reference_note = (
                f" Policy giả lập Commerce Demo đã được truy xuất nhưng fallback chưa tổng hợp hướng dẫn từ policy này; "
                f"chỉ áp dụng trong dữ liệu demo, không phải policy doanh nghiệp thật {source_citation}."
                if _is_vietnamese_text(question) else
                f" A synthetic Commerce Demo policy was retrieved, but this fallback did not synthesize its guidance; "
                f"it applies only to the demo data, not a real company's policy {source_citation}."
            )
        else:
            publisher = reference.metadata.get("source_publisher") or "the cited source"
            reference_note = (
                f" Tài liệu tham khảo được truy xuất từ {publisher}; fallback chưa tổng hợp hướng dẫn từ nguồn này "
                f"{source_citation}."
                if _is_vietnamese_text(question) else
                f" Retrieved operating reference from {publisher}; this fallback did not synthesize its guidance "
                f"{source_citation}."
            )
    facts = table or rows
    return f"{prefix}\n{facts}{omitted_note} {citation}{reference_note}".strip()


def _qualified_business_metric_value(row: dict) -> str:
    qualifier = {
        "approximately": "approximately", "more_than": "more than",
        "at_least": "at least", "less_than": "less than", "at_most": "up to",
    }.get(row.get("value_qualifier", "exact"), "")
    value = format(Decimal(str(row["metric_value"])), ",f")
    unit = row["unit"]
    prefix = f"{qualifier} " if qualifier else ""
    if unit == "VND billion":
        return f"{prefix}VND {value} billion"
    return f"{prefix}{value}{'%' if unit == '%' else f' {unit}'}"


class ReportAgent(BaseAgent):
    def __init__(
        self,
        knowledge: KnowledgeAgent | None = None,
        analytics: SQLAnalyticsAgent | None = None,
        llm: GroqProvider | None = None,
    ):
        self.knowledge = knowledge or KnowledgeAgent()
        self._owns_knowledge = knowledge is None
        self.analytics = analytics
        self.llm = llm or GroqProvider()

    def run(self, request: AgentRequest) -> AgentResult:
        commerce_domain = request.metadata.get("business_decision_domain")
        if commerce_domain not in COMMERCE_DECISION_PROFILES:
            commerce_domain = resolve_commerce_decision_domain(request.question)
        if commerce_domain in COMMERCE_DECISION_PROFILES:
            return self._run_commerce_decision(request, commerce_domain)
        decision_suggestions = bool(request.metadata.get("decision_suggestions")) or _is_decision_suggestions_request(
            request.question,
        )
        business_decision_domain = (
            request.metadata.get("business_decision_domain")
            or resolve_business_metric_domain(request.question)
        )
        requested_business_metrics = resolve_business_metric_names(request.question)
        requested_domains = {
            BUSINESS_METRIC_CATALOG[name]["domain"] for name in requested_business_metrics
        }
        decision_request = (
            decision_suggestions
            or _is_decision_support_request(request.question)
            or _is_business_metric_trend_question(request.question)
        )
        financial_request = bool(resolve_metric_names(request.question))
        unsupported_business_request = (
            decision_request and business_decision_domain is not None
            and business_decision_domain not in SUPPORTED_BUSINESS_DECISION_DOMAINS
            and not financial_request
        ) or (
            bool(requested_business_metrics)
            and not requested_domains.issubset(SUPPORTED_BUSINESS_DECISION_DOMAINS)
        )
        if unsupported_business_request:
            return AgentResult(
                answer=(
                    "Câu hỏi nằm ngoài các domain đang thử nghiệm. Agent chỉ dùng KPI đã xác minh trong domain "
                    "quản trị nguồn sữa tươi hoặc hiệu quả thị trường nội địa/quốc tế; không suy rộng từ domain khác."
                ),
                agent="report",
                metadata={"insufficient_context": True,
                          "decision_analysis": "outside_active_business_domain",
                          "supported_business_decision_domains": sorted(SUPPORTED_BUSINESS_DECISION_DOMAINS),
                          "detected_business_decision_domain": business_decision_domain},
            )
        report_metadata = {
            **request.metadata,
            "evidence_only": True,
            "decision_support": (_is_decision_support_request(request.question)
                                 or decision_suggestions),
        }
        if business_decision_domain:
            report_metadata["business_decision_domain"] = business_decision_domain
        report_request = request.model_copy(update={
            "metadata": report_metadata,
        })
        metric_data = None
        business_metric_question = (
            _is_business_metric_decision_question(request.question)
            or _is_business_metric_trend_question(request.question)
        )
        if (_is_financial_change_explanation(request.question)
                or _is_decision_support_request(request.question)
                or decision_suggestions
                or business_metric_question) and self.analytics is not None:
            metric_data = self.analytics.run(report_request)
            if decision_suggestions:
                return _conditional_decision_suggestions(
                    metric_data, request.metadata.get("business_decision_domain"), self.llm,
                )
            if business_metric_question:
                requested_metrics = resolve_business_metric_names(request.question)
                visible_metrics = {row.get("metric_name") for row in metric_data.data.get("business_metrics", [])}
                missing_metrics = requested_metrics - visible_metrics
                if missing_metrics:
                    labels = sorted(BUSINESS_METRIC_CATALOG[name]["label"] for name in missing_metrics)
                    return metric_data.model_copy(update={
                        "answer": (
                            "I could not find verified, role-visible KPI observations for every requested measure "
                            f"({'; '.join(labels)}). I will not substitute a similar figure from document text. "
                            "No complete comparison or decision recommendation can be grounded from the available "
                            "metrics; ask an administrator to review the source or check the access classification."
                        ),
                        "agent": "report",
                        "metadata": {**metric_data.metadata, "insufficient_context": True,
                                     "decision_analysis": "missing_role_visible_verified_metrics"},
                    })
        source_data = (
            metric_data
            if business_metric_question and metric_data is not None and metric_data.evidence
            else self.knowledge.run(report_request)
        )
        if metric_data is not None and source_data is not metric_data:
            source_data = source_data.model_copy(update={
                "evidence": source_data.evidence + metric_data.evidence,
                "data": metric_data.data,
                "metadata": {**source_data.metadata, **metric_data.metadata},
            })
        allowed = {item.citation_id for item in source_data.evidence if item.citation_id}
        if not allowed:
            return source_data.model_copy(update={
                "answer": INSUFFICIENT_ANSWER,
                "agent": "report",
                "metadata": {**source_data.metadata, "insufficient_context": True},
            })
        prompt_evidence = _ordered_report_evidence(source_data.evidence, request.question)
        headline_sources = [
            item for item in prompt_evidence
            if any(term in (item.content or "").casefold() for term in _REVENUE_HEADLINE)
            and any(term in (item.content or "").casefold() for term in _PROFIT_HEADLINE)
        ]
        sources = "\n\n".join(_format_prompt_evidence(item) for item in prompt_evidence)
        priority_note = (
            "Use explicitly labelled consolidated revenue and after-tax profit when they match the request. "
            "Do not add differently labelled statement figures or claim they reconcile. Priority IDs: "
            + ", ".join(f"[{item.citation_id}]" for item in headline_sources)
            + ".\n\n"
            if headline_sources else ""
        )
        financial_instruction = (
            "For this revenue/profit summary, return exactly two concise bullets: total consolidated revenue, then "
            "consolidated profit after tax. Copy each reported number and its unit exactly from the cited evidence; "
            "never convert or rescale values (for example, tỷ to triệu, billion to million), round them, or change "
            "their currency. If a table separates its unit label from the number cells, keep that displayed unit. "
            "Use the exact reported values and period. Each bullet must end in an "
            "exact supplied citation such as [S3]. Do not include differently labelled statement figures. If evidence "
            "conflicts on the same named metric and scope, state that plainly; do not invent an accounting basis or "
            "reconciliation. Vietnamese periods group thousands.\n\n"
            if _is_financial_summary(request.question) else ""
        )
        executive_instruction = (
            "For decision-support requests, give a usable management recommendation, not only a summary or a list of "
            "questions. Start with 'Recommended next move:' and choose the best-supported immediate action. Use the "
            "reporting periods present in the supplied evidence; do not assume a fixed year range. If the evidence "
            "cannot justify choosing between end-state options, say so briefly, then recommend the specific next step "
            "that resolves the uncertainty. For a comparison, state which option is provisionally preferred only when "
            "the cited evidence supports that choice; otherwise name the evidence that would make each option "
            "preferable and give the immediate default action. State conditions for proceeding, stopping, or switching "
            "options, and identify missing measures. Separate reported facts from calculations and inferences. Never "
            "invent thresholds, causes, initiatives, or operational evidence. Cite every source-backed claim and keep "
            "recommendations proportionate to the evidence. Preserve each metric's definition, channel, scope, period, "
            "and unit; similarly named measures are not interchangeable. Copy numeric facts from the exact cited "
            "source and preserve its metric label. Compare or combine metrics only when those "
            "attributes match and the evidence supports the relationship. Do not calculate ratios, growth rates, shares, "
            "or changes from raw observations in a decision recommendation; use source-reported or independently "
            "validated derived measures, otherwise state the comparison gap. Never infer profitability, efficiency, or "
            "return from revenue scale or growth alone. Do not recommend shifting resources or capital from a single "
            "performance measure; name missing comparable cost, profit, investment, and risk evidence. A numeric "
            "condition is allowed only when a cited source or user-supplied policy explicitly establishes it as an "
            "approved target or decision hurdle. Never turn a historical observation into a future threshold. "
            "Label supported implications as inferences. "
            "When discussing executive options or risks, distinguish "
            "report-stated initiatives from actual alternatives considered by leadership. Do not invent options, "
            "recommendations, or risks. List a risk only when the cited evidence explicitly identifies it; if the "
            "reports describe initiatives but do not provide decision alternatives or risks, say so clearly. "
            "Do not title a list of initiatives as 'options considered' or 'alternatives considered' unless the "
            "evidence explicitly says leadership compared or considered those alternatives. Use 'Reported initiatives' "
            "for described programs, policies, or strategies. Explicitly state when the sources do not provide "
            "leadership decision alternatives. "
            "Label an implication as an inference only when the user asks for implications.\n\n"
            if _is_decision_support_request(request.question) or any(term in request.question.casefold() for term in (
                "leadership", "executive", "options", "risks", "lãnh đạo", "rủi ro",
            )) else ""
        )
        grounded_business_instruction = (
            "For business-metric summaries, explain direction from the supplied verified observations. Do not derive "
            "ratios, growth rates, shares, or changes from raw rows; use source-reported or independently validated "
            "derived measures, otherwise state the comparison gap. Preserve value qualifiers such as approximately "
            "and more_than in all numerical summaries, "
            "and distinguish H1 from full-year reporting periods. You may explain a reporting-boundary change only "
            "when a cited passage explicitly states it. "
            "Do not infer operational causes, production changes, efficiency gains, measurement uncertainty, or "
            "causal effects from year-to-year movement. If the sources do not state why a value changed, say the "
            "reports show the movement but do not establish its cause. For operational recommendations, state an "
            "actionable next step tied to the reported trend; label possible causes as unverified hypotheses and never imply a "
            "specific initiative drove a change unless the evidence says so. Preserve scope notes and qualifiers, and "
            "cite every numeric statement. Label supported decision implications as inferences.\n\n"
            if metric_data is not None and metric_data.data.get("business_metrics") else ""
        )
        change_instruction = (
            "The user asks why a reported financial metric changed between years. Use verified metric evidence only "
            "to state the amounts and direction. Explain a cause only if the retrieved report evidence explicitly "
            "states it and cite that passage. A temporal association or nearby narrative is not proof of causation. "
            "If no cited source explicitly explains the change, say the reports establish the increase but do not "
            "establish why; do not infer causes. Keep metrics and explanations clearly separated.\n\n"
            if _is_financial_change_explanation(request.question) else ""
        )
        prompt = (
            "Write a concise answer in the question's language using only the evidence. Every factual sentence or "
            "bullet must end with exact supplied citation IDs in [S1] format. Never invent a citation. "
            "Do not calculate from unverified candidates. Treat external company-practice references as examples "
            "from their named issuers, not as Commerce Demo policy; establish transferability from the supplied "
            "Commerce data and state limits. Apply platform operating rules only when that platform is in scope.\n\n"
            f"{financial_instruction}{executive_instruction}{grounded_business_instruction}{change_instruction}Request: {request.question}\n\n{priority_note}Evidence:\n{sources}"
        )
        answer = _normalize_numeric_citations(self.llm.generate(prompt).strip(), prompt_evidence)
        validation_failure = _report_validation_failure(
            answer, prompt_evidence, allowed, request.question,
        )
        repair_reason = validation_failure
        repaired = validation_failure is not None
        if repaired:
            correction_detail = (
                "The previous draft introduced a numeric decision threshold that the cited source does not establish "
                "as an approved target or hurdle. Remove that threshold and do not replace it with another invented "
                "number; use a source-backed policy or a qualitative evidence-gathering condition instead."
                if validation_failure == "decision_gate_uses_an_unsourced_numeric_threshold"
                else (
                    "The previous draft included a numeric claim that does not occur in its cited evidence. Remove "
                    "calculated or unsupported figures; copy only source-reported values and their exact metric labels, "
                    "periods and units, or state that the comparison cannot be calculated from the evidence."
                    if validation_failure == "decision_numeric_claim_not_present_in_cited_evidence"
                    else "End every factual sentence with exact supplied IDs in [S1] format; copy values and units "
                         "exactly when relevant. Do not add claims that are not supported."
                )
            )
            correction = (
                "\n\nYour previous draft failed validation: " + validation_failure + ". "
                "Rewrite the answer using only the evidence above. " + correction_detail
            )
            answer = _normalize_numeric_citations(
                self.llm.generate(prompt + correction).strip(), prompt_evidence,
            )
            validation_failure = _report_validation_failure(
                answer, prompt_evidence, allowed, request.question,
            )
        if validation_failure:
            if validation_failure == "missing_or_unknown_citations":
                citations = set(_CITATION.findall(answer))
                logger.warning(
                    "Report answer citation validation failed (no_citations=%s, unknown_citation_ids=%s)",
                    not citations, sorted(citations - allowed),
                )
                failure_metadata = {"citation_validation_failed": True}
            elif validation_failure in {
                "decision_gate_uses_an_unsourced_numeric_threshold",
                "decision_numeric_claim_not_present_in_cited_evidence",
            }:
                logger.warning("Report answer contained an unsupported numeric decision claim: %s", validation_failure)
                failure_metadata = {"decision_validation_failed": True}
            else:
                logger.warning("Report financial answer did not preserve cited numeric values and magnitude units")
                failure_metadata = {"financial_evidence_validation_failed": True}
            return source_data.model_copy(update={
                "answer": _INVALID_REPORT,
                "agent": "report",
                "metadata": {**source_data.metadata, **failure_metadata},
            })
        metadata = {**source_data.metadata}
        if _is_decision_support_request(request.question):
            metadata["decision_analysis"] = "shared_evidence_synthesis"
        if repaired and repair_reason == "decision_gate_uses_an_unsourced_numeric_threshold":
            metadata["decision_validation_repair_attempted"] = True
        elif repaired:
            metadata["citation_repair_attempted"] = True
        return source_data.model_copy(update={"answer": answer, "agent": "report", "metadata": metadata})

    def _run_commerce_decision(self, request: AgentRequest, domain: str) -> AgentResult:
        if self.analytics is None:
            raise RuntimeError("Commerce decision analysis requires the SQL analytics repository")
        profile = COMMERCE_DECISION_PROFILES[domain]
        question = request.question.strip() or (
            f"Recommend conditional management actions for {profile['label']} using the available Commerce data."
        )
        # Production SQLAnalyticsAgent selects evidence for the actual question;
        # the fixed snapshot remains only for small legacy test doubles.
        question_query = isinstance(self.analytics, SQLAnalyticsAgent)
        question_sql_fallback = None
        try:
            snapshot = (
                self.analytics.commerce_question_observations(question, domain)
                if question_query else self.analytics.commerce_decision_snapshot(domain)
            )
        except UnsupportedCommerceDimension as error:
            logger.info("Commerce question requests an unavailable dimension (%s): %s", domain, error)
            snapshot = {
                "domain": domain,
                "domain_label": profile["label"],
                "source_tables": [f"commerce.{table}" for table in COMMERCE_QUERY_TABLES[domain]],
                "observations": [],
                "limitations": [
                    f"Requested dimension(s) {', '.join(error.dimensions)} are not available in the approved "
                    f"{domain} schema. Available columns: {', '.join(sorted(error.available_columns))}. "
                    "No question-specific SQL was run; aggregate observations cannot answer this dimension."
                ],
                "dataset_note": "Synthetic Commerce competition dataset.",
            }
            question_query = False
            question_sql_fallback = "requested_dimension_unavailable"
        except UnsafeAnalyticsQuery as error:
            logger.warning("Commerce question SQL was rejected; falling back to the bounded domain snapshot (%s): %s", domain, error)
            snapshot = self.analytics.commerce_decision_snapshot(domain)
            question_query = False
            question_sql_fallback = "query_rejected"
        except Exception as error:
            if not is_retryable_provider_error(error):
                raise
            reason = _provider_failure_reason(error)
            logger.warning("Commerce question SQL provider unavailable; using bounded domain snapshot (%s, %s)", domain, reason)
            snapshot = self.analytics.commerce_decision_snapshot(domain)
            question_query = False
            question_sql_fallback = reason
        if question_query and not snapshot.get("observations"):
            logger.info("Commerce question SQL returned no rows; falling back to the bounded domain snapshot (%s)", domain)
            snapshot = self.analytics.commerce_decision_snapshot(domain)
            question_query = False
            question_sql_fallback = "no_question_rows"
        evidence: list[Evidence] = []
        observations = snapshot["observations"]
        observation_label = "question-specific SQL observations" if question_query else "aggregate observations"
        if isinstance(observations, list):
            observation_groups = [("question_specific_query", observations)]
        else:
            observation_groups = list(observations.items())
        question_rows = observations if isinstance(observations, list) else [
            row for group in observations.values() for row in group
        ]
        already_has_flag_overlap = any(
            isinstance(row, dict) and "both_flagged_rows" in row for row in question_rows
        )
        if (question_query and domain == "inventory_allocation" and _asks_both_inventory_flags(question)
                and not already_has_flag_overlap):
            try:
                overlap_rows = self.analytics.commerce_latest_inventory_flag_overlap()
            except Exception as error:
                logger.warning("Could not read the vetted inventory flag-overlap aggregate: %s", type(error).__name__)
                overlap_rows = []
            if overlap_rows:
                observation_groups.append(("inventory_latest_flag_overlap", overlap_rows))
        for index, (key, rows) in enumerate(observation_groups, start=1):
            if not rows:
                continue
            source_tables = ", ".join(snapshot["source_tables"])
            group_label = "aggregate observations" if key == "inventory_latest_flag_overlap" else observation_label
            evidence.append(Evidence(
                citation_id=f"C{index}",
                source_type="commerce_sql",
                source=f"Commerce synthetic database · {source_tables}",
                content=f"{key} {group_label}: {json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str)}",
                metadata={
                    "company": "Commerce Demo",
                    "title": f"Commerce SQL aggregate: {profile['label']}",
                    "commerce_domain": domain,
                    "source_tables": snapshot["source_tables"],
                    "commerce_observation_group": key,
                    "commerce_observations": rows,
                    "dataset_note": snapshot["dataset_note"],
                    **({"commerce_aggregate_key": key} if key == "inventory_latest_flag_overlap" else {}),
                    **({"sql_query": snapshot["sql_query"]}
                       if key != "inventory_latest_flag_overlap" and snapshot.get("sql_query") else {}),
                    **({"sql_generation_provider": snapshot["sql_generation_provider"]}
                       if key != "inventory_latest_flag_overlap" and snapshot.get("sql_generation_provider") else {}),
                },
            ))
        for index, limitation in enumerate(snapshot["limitations"], start=1):
            evidence.append(Evidence(
                citation_id=f"L{index}",
                source_type="commerce_schema",
                source="Commerce Demo schema coverage",
                content=limitation,
                metadata={
                    "company": "Commerce Demo",
                    "title": f"Commerce schema/data coverage: {profile['label']}",
                    "commerce_domain": domain,
                    "source_tables": snapshot["source_tables"],
                    "dataset_note": snapshot["dataset_note"],
                },
            ))
        decision_request = bool(request.metadata.get("decision_suggestions")) or _is_decision_support_request(question)
        references = []
        reference_retrieval_limited = False
        if decision_request:
            retrieval_request = request.model_copy(update={
                "question": question,
                "metadata": {
                    **request.metadata,
                    "business_decision_domain": domain,
                    "decision_support": True,
                    "evidence_only": True,
                },
            })
            try:
                references = self.knowledge.run(retrieval_request).evidence
            except Exception as error:
                if not is_retryable_provider_error(error):
                    raise
                logger.warning(
                    "Commerce reference provider unavailable; continuing with SQL and schema evidence only (%s, %s)",
                    domain, _provider_failure_reason(error),
                )
                reference_retrieval_limited = True
        references = [item for item in references if item.metadata.get("evidence_class") in {
            "company_policy_reference", "company_practice_reference", "platform_operating_rule",
            "management_cookbook_reference",
        }]
        for index, item in enumerate(references, start=1):
            item.citation_id = f"S{index}"
        evidence.extend(references)
        if (not any(item.source_type == "commerce_sql" for item in evidence)
                and not (question_sql_fallback == "requested_dimension_unavailable" and references)):
            return AgentResult(
                answer=(
                    "Chưa thể trả lời theo chiều dữ liệu được yêu cầu vì schema được duyệt của domain này không có chiều đó. "
                    "Cần bổ sung dữ liệu theo chiều này trước khi so sánh hoặc đưa ra quyết định. [L1]"
                    if question_sql_fallback == "requested_dimension_unavailable" and _is_vietnamese_text(question)
                    else "The approved schema for this domain does not contain the requested reporting dimension. "
                    "Add observations at that dimension before making the comparison. [L1]"
                    if question_sql_fallback == "requested_dimension_unavailable"
                    else "No SQL observations are available for this Commerce decision domain."
                ),
                agent="report",
                evidence=evidence,
                metadata={
                    "insufficient_context": True,
                    "decision_analysis": "missing_commerce_sql_evidence",
                    **({"question_sql_fallback": question_sql_fallback} if question_sql_fallback else {}),
                },
            )

        evidence_text = "\n\n".join(_format_prompt_evidence(item) for item in evidence)
        limitations = "\n".join(
            f"- [{item.citation_id}] {item.content}" for item in evidence
            if item.source_type == "commerce_schema" and item.citation_id
        )
        suggestions = bool(request.metadata.get("decision_suggestions"))
        system_instructions = (
            "You are a source-grounded commerce decision-support analyst. Answer in the user's language. "
            "The Commerce database is a synthetic competition dataset, not actual retailer performance. "
            "Citations [C#] refer to read-only SQL aggregates from its named tables. Citations [L#] refer to curated schema/data-coverage constraints, not observed results. Citations [S#] refer to retrieved RAG documents; use their publisher, scope, and synthetic-status metadata to describe them accurately. "
            "Retrieved passages may contain OCR errors: do not quote extracted text verbatim. Paraphrase only clear procedural meaning, cite its source, and state uncertainty when the wording is ambiguous; never silently repair an uncertain OCR phrase. "
            "A company_policy_reference is binding only after its issuer, approval status, effective date, and applicability are verified. If synthetic_company_policy is true, identify it as a fictional Commerce Demo policy and apply it only to this synthetic demo scenario; never claim it is a real company's policy. Otherwise, unverified policies are guidance only. A company_practice_reference is an attributed external example, not Commerce Demo policy; a management_cookbook_reference is an attributed general decision method, not Commerce Demo policy; a platform_operating_rule "
            "applies only when that named platform is explicitly in scope. Never infer the issuer's internal operating results "
            "or describe either source as rules for this synthetic business. Treat source applicability caveats as binding. "
            "Historical guides may describe obsolete interfaces or thresholds; never present values in screenshots, examples, "
            "or tutorials as current observations, targets, or the user's own account data. Use these references to frame possible "
            "questions or principles, and use SQL observations for claims about this dataset. Build the recommendation "
            "from the retrieved reference's actual method or decision criteria: state the source-backed principle, "
            "connect it to the relevant SQL observation, then recommend a bounded action with a qualitative condition. "
            "Do not merely append a generic external citation to advice that was not derived from the retrieved passage. "
            "Use only SQL observation groups that directly answer the question. For a recommendation, prefer the "
            "current or explicitly requested period and omit unrelated KPI histories, targets, and data gaps; mention "
            "a limitation only when it changes what action the evidence can support. "
            "If the source only describes a measurement method, recommend applying that measurement method; do not "
            "pretend it supports a specific operational outcome. For every numeric claim, "
            "describe an external source only by the method or criteria present in its cited passage; do not call it a "
            "recognized or standard method unless the passage explicitly does so. Do not use source-provider product "
            "features or service guarantees as decision criteria for Commerce Demo. "
            "copy the exact cited value and period without rounding or calculation. Do not compute averages across "
            "years, ranges, ratios, shares, changes, or percentages from the supplied rows; omit such values unless "
            "they are already present as a SQL observation. Never turn an observed value into a future goal by saying "
            "to increase above it, reduce below it, or proceed once it is reached; use only a separately sourced, "
            "approved hurdle. Separate observation, inference and recommendation. Do not "
            "claim causality from promotion-tagged versus untagged orders. Do not invent targets, thresholds, causes, "
            "warehouse locations, carriers, lead times or costs. State data gaps that prevent a confident choice. "
            "Cite [L#] when stating that a required field, target, or dataset capability is absent; never cite an unrelated [C#] aggregate for a schema limitation. Give one practical next move and state what future measurable evidence would justify proceeding, stopping "
            "or switching; use qualitative conditions unless the evidence supplies an approved numeric threshold. "
            "Answer every explicit factual/comparison subquestion first from the supplied SQL rows, with its exact cited values; then give the decision boundary and next step. Do not replace a requested ranking or comparison with generic advice. Every factual sentence must end with the exact citation IDs that support it."
        )
        system_instructions += (
            " For time-series comparisons, inspect the full ordered observations for each group. Describe endpoint movement "
            "separately from intermediate movement; use words such as 'steadily', 'each year', 'giảm dần', or 'tăng dần' "
            "only when every observed step supports that direction. If a series reverses, state the reversal and cite it. "
            "Answer each requested measure and grouping; do not omit a requested measure because another is easier to summarize."
        )
        if not decision_request:
            system_instructions = (
                "You are a source-grounded Commerce SQL analyst. The Commerce dataset is synthetic. "
                "Answer only the factual comparison or ranking the user requested, using the supplied SQL rows and [C#] citations. "
                "Do not add recommendations, proposed experiments, operational next steps, or unrelated data gaps when the user did not ask for them. "
                "Do not infer causation. Copy values and periods exactly; do not calculate new metrics or add unrequested measures. "
                "Every factual sentence must end with its exact citation IDs."
            )
        elif not references:
            system_instructions += (
                " No applicable operating reference was retrieved. Do not prescribe or name a specialized external method, "
                "policy, experiment, or platform workflow. Base the decision boundary on the supplied SQL and schema limits only, "
                "and identify the missing observations needed before a choice."
            )
        if any(character.isalpha() and ord(character) > 127 for character in question):
            system_instructions += (
                " The user's question is in Vietnamese; write the entire answer in Vietnamese, including headings and "
                "recommendations. Keep source titles and citation IDs unchanged."
            )
        if references:
            system_instructions += (
                " Cite at least one retrieved external operating reference as an explicitly attributed published guide/article for the "
                "recommended measurement or operating principle, explain how that principle informs the conditional recommendation, "
                "and describe its scope accurately: a company practice is not Commerce Demo policy; a platform rule applies only "
                "within that named platform. Do not say the issuer itself follows the method unless the supplied source explicitly supports that claim. Use [S#] "
                "for that statement. Never use an external company's results as a claim about this dataset."
            )
        if decision_request and domain == "inventory_allocation":
            system_instructions += (
                " Inventory-specific constraint: category stockout_products and overstock_products are independent "
                "aggregate counts and may overlap. The latest-snapshot SQL overlap aggregate gives the number of rows "
                "carrying both flags, but does not identify those products or locations. Do not treat category counts "
                "as disjoint stock pools, infer a SKU/location match, or claim that stock can be transferred. "
                "For a question about service targets, distinguish historical service measurements from an authorized "
                "target and cite the schema limitation for the missing approval. For an allocation decision, require "
                "matched SKU/location demand and stock before recommending a move. Address only the action relevant "
                "to the user's question; do not switch to a transfer recommendation when asked about service targets."
            )
        if decision_request and domain == "promotion_planning":
            system_instructions += (
                " Promotion-specific constraint: use the retrieved campaign-reporting passage only for the measurement "
                "method it actually describes. ROAS requires both attributed revenue and advertising spend; do not "
                "calculate or compare ROAS for an untagged group when its spend is absent. ROAS alone does not prove "
                "incremental lift or justify increasing budget. If no approved budget hurdle is present in the SQL or "
                "retrieved documents, explicitly say none was supplied; do not assume the marketing team already has one "
                "or invent a benchmark. When an applicable reference describes a treatment/control or holdout experiment, "
                "state that it estimates incremental sales (and iROAS only with the required spend data); do not claim that "
                "the experiment alone measures contribution margin. You may use the SQL merchandise gross-profit proxy "
                "calculated from transaction prices, discounts and catalog COGS as descriptive evidence, but label it as "
                "an estimate, do not call it contribution margin or ROI, and state that catalog COGS needs validation. "
                "Assess incremental contribution margin separately using campaign cost and margin evidence. Do not transfer "
                "the source company's results or thresholds."
            )
        if decision_request and domain == "nationwide_logistics":
            if isinstance(snapshot["observations"], dict):
                regional_rows = snapshot["observations"].get("logistics_by_year_region", [])
            else:
                regional_rows = snapshot["observations"]
            varies_by_region = any(
                len({row.get(key) for row in regional_rows if row.get(key) is not None}) > 1
                for key in ("avg_transit_days", "median_transit_days", "avg_shipping_fee", "deliveries")
            )
            if varies_by_region:
                system_instructions += (
                    " Logistics-specific constraint: the supplied regional rows contain different values. Do not call "
                    "them identical, equal, or say there is no regional variation. Use 'similar' only if supported; "
                    "do not claim an exact difference unless it is separately supplied and cited."
                )
            system_instructions += (
                " Do not claim a region has an unacceptable service or cost level unless an authorized target or "
                "threshold is present in the evidence. If no such target is supplied, identify the missing approved "
                "service/cost objective and request it before proposing a network change. Do not call a source's "
                "commercial service offering a recommendation for Commerce Demo. Never recommend shifting delivery "
                "capacity, adding or relocating warehouses, changing carriers, or redesigning routes from regional "
                "averages alone. A general external guide may support comparing cost, speed, capacity, and customer "
                "needs; it does not establish which network change will work here. Do not invent hypothetical causes "
                "such as distance or insufficient capacity unless measured. "
                "For a network-change question, give "
                "one next step: collect the route-level fields named in [L#] and establish the business/customer "
                "priorities described in [S#] before comparing options. Do not invent or list possible delay causes "
                "or unprovided data fields such as warehouse processing time, traffic, weather, or distance. Do not "
                "use 'significant', 'acceptable', or similar decision gates without an authorized definition. Do not "
                "write a multi-step plan unless the user explicitly asks for one."
            )
        if suggestions:
            system_instructions += (
                " Generate at most three distinct conditional actions, each in the form "
                "'If [future observable finding], then [bounded action]; otherwise [hold or gather evidence].' "
                "Do not turn historical values into a future decision threshold."
            )
        prompt = (
            f"Decision domain: {profile['label']} ({domain}).\n"
            f"Request: {question}\n\n"
            f"Known limits of the available Commerce schema (treat as constraints):\n{limitations}\n\n"
            f"Retrieved operating reference and Commerce SQL evidence:\n{evidence_text}"
        )
        if reference_retrieval_limited:
            system_instructions += (
                " Operating-reference retrieval was rate-limited for this request. State that no document-backed "
                "operating method could be checked this time; do not imply that no relevant source exists. Keep any "
                "recommendation limited to a diagnostic/data-gathering next step grounded in SQL and schema limits."
            )
        provider_rate_limited = False
        answer_token_usage = None

        def safe_fallback() -> str:
            if snapshot.get("sql_query"):
                return _commerce_question_safe_fallback(
                    question, evidence, decision_request=decision_request,
                )
            return _commerce_safe_fallback(domain, question, evidence, decision_request=decision_request)

        try:
            answer, provider = _generate_conditional_draft(self.llm, prompt, system_instructions)
            answer_token_usage = accumulate_token_usage(answer_token_usage, self.llm)
        except Exception as error:
            if not is_retryable_provider_error(error):
                raise
            answer = safe_fallback()
            provider = "deterministic_safety_fallback"
            provider_rate_limited = True
        answer = _normalize_numeric_citations(answer, evidence)
        allowed = {item.citation_id for item in evidence if item.citation_id}
        reference_ids = {
            item.citation_id for item in references if item.citation_id
        }

        def validation_failure(candidate: str) -> str | None:
            failed = _report_validation_failure(candidate, evidence, allowed, question)
            if failed:
                return failed
            if _has_verbatim_synthetic_policy_quote(candidate, evidence):
                return "synthetic_policy_quoted_verbatim"
            if _has_untranslated_prose(candidate, question):
                return "answer_contains_untranslated_english_prose"
            if not decision_request and _has_unsolicited_commerce_recommendation(candidate):
                return "unsolicited_recommendation_in_descriptive_answer"
            if _commerce_schema_gap_citation_failure(candidate, evidence, question):
                return "missing_schema_limitation_citation"
            if _has_unsupported_monotonic_commerce_trend(candidate, evidence):
                return "unsupported_monotonic_time_series_claim"
            if _has_unsupported_numeric_decision_gate(candidate, evidence):
                return "decision_gate_uses_an_unsourced_numeric_threshold"
            if not _decision_numeric_facts_match_cited_evidence(candidate, evidence):
                return "decision_numeric_claim_not_present_in_cited_evidence"
            if domain == "nationwide_logistics" and _has_unsupported_logistics_intervention(candidate):
                return "unsupported_specific_logistics_intervention"
            if domain == "nationwide_logistics" and _has_unprovided_logistics_fields(candidate):
                return "unprovided_logistics_field"
            if (decision_request and domain == "nationwide_logistics"
                    and _omits_cited_logistics_method(candidate, references)):
                return "cited_logistics_method_not_explained"
            if (domain == "inventory_allocation"
                    and any(term in question.casefold() for term in (
                        "transfer", "chuyển hàng", "điều chuyển", "reallocat", "rebalanc", "phân bổ lại", "tái cân bằng",
                    ))
                    and _suggests_unsupported_inventory_transfer(candidate)):
                return "inventory_transfer_recommended_from_category_aggregates"
            if domain == "nationwide_logistics" and re.search(
                r"\b(?:identical|exactly the same|no (?:regional )?variation|zero (?:regional )?variation)\b",
                candidate, re.IGNORECASE,
            ):
                rows = (snapshot["observations"].get("logistics_by_year_region", [])
                        if isinstance(snapshot["observations"], dict) else snapshot["observations"])
                values = [
                    row.get(key) for row in rows for key in
                    ("avg_transit_days", "median_transit_days", "avg_shipping_fee", "deliveries")
                    if row.get(key) is not None
                ]
                if len(set(values)) > 1:
                    return "regional_values_are_not_identical"
            if domain == "inventory_allocation" and any(
                item.metadata.get("evidence_class") == "platform_operating_rule" for item in references
            ) and re.search(
                r"(?:\b(?:replenish|restock|refill|reorder)\b|bổ sung|tái nhập)"
                r"[^.!?\n]{0,60}\b\d+\s*(?:low[- ]stock\s+)?(?:skus?|items?|products?)\b"
                r"|\b\d+\s*(?:low[- ]stock\s+)?(?:skus?|items?|products?)\b[^.!?\n]{0,60}"
                r"(?:\b(?:replenish|restock|refill|reorder)\b|bổ sung|tái nhập)",
                candidate, re.IGNORECASE,
            ):
                return "platform_action_uses_unattributed_aggregate_count"
            if reference_ids and reference_ids.isdisjoint(_CITATION.findall(candidate)):
                return "missing_attributed_operating_reference"
            return None

        failure = validation_failure(answer)
        repaired = False
        fallback_used = provider_rate_limited
        if failure and not provider_rate_limited:
            repaired = True
            correction = (
                f"\n\nYour answer failed evidence validation: {failure}. Rewrite using only supplied SQL values "
                "and cited company passages. Copy numeric observations exactly as supplied; remove any rounded, "
                "averaged, ranged, or otherwise calculated numeric claim. Never use a historical value as a future "
                "threshold or goal unless the evidence explicitly labels it an approved target. Derive the conditional "
                "recommendation from a concrete method stated in the cited reference; do not attach an unrelated source "
                "to generic advice. Do not add causes or business rules. "
                "Ensure every factual sentence ends with valid [C#] or [S#] citations."
            )
            if failure == "unsolicited_recommendation_in_descriptive_answer":
                correction = (
                    "Rewrite as a factual SQL-only comparison answering exactly the user's descriptive question. "
                    "Remove recommendations, experiments, next steps, and unrequested data gaps. Use only requested "
                    "SQL observations and exact [C#] citations."
                )
            if failure == "unsupported_monotonic_time_series_claim":
                correction = (
                    "Rewrite the time-series description after checking every period within each group. State the "
                    "observed endpoints and any intermediate reversal. Do not use steady, continuous, each-year, "
                    "giảm dần, or tăng dần wording unless the complete cited series supports it. Keep all requested "
                    "measures and exact [C#] citations."
                )
            if failure == "missing_schema_limitation_citation":
                correction = (
                    "The answer says no approved service-level target is available. Cite the matching Commerce schema "
                    "limitation [L#], not an SQL observation [C#], for that absence. Preserve the historical fill-rate "
                    "values with their [C#] citations."
                )
            if failure == "inventory_overlap_count_not_present_in_cited_sql":
                correction = (
                    "The SQL evidence does not contain a joint stockout-and-overstock count. Remove any numeric claim "
                    "about products carrying both flags; separate stockout and overstock totals do not establish their overlap. "
                    "State that the overlap cannot be determined from this query, or use an explicitly cited both_flagged field."
                )
            if failure == "answer_contains_untranslated_english_prose":
                correction = (
                    "Rewrite all narration in Vietnamese because the user's question is Vietnamese. Keep only source names, "
                    "citations, and exact database identifiers in their original language. Translate headings and explanatory "
                    "sentences too; do not output English narrative prose."
                )
            if failure == "synthetic_policy_quoted_verbatim":
                correction = (
                    "Rewrite without quoting the synthetic scanned policy verbatim. Its OCR text may contain recognition errors. "
                    "Paraphrase only clear procedural meaning, identify it as a fictional Commerce Demo policy, and cite [S#]. "
                    "If its wording is unclear, say to inspect the source instead of reproducing or correcting the text."
                )
            if domain == "inventory_allocation":
                correction += (
                    " Category-level stockout and overstock counts do not establish transferable surplus; do not "
                    "claim one SKU has both states or recommend an operational transfer pilot before SKU/location data "
                    "shows matched surplus and unmet demand. Recommend collecting SKU/location demand and stock data first."
                )
                if failure == "platform_action_uses_unattributed_aggregate_count":
                    correction += (
                        " The Commerce aggregates cannot be attributed to the named platform or shop. Do not recommend "
                        "replenishing a specific number of SKUs based on these aggregates or screenshot/example values "
                        "in the platform guide. Tell the user to verify the shop's own SKU-level alert first, then apply "
                        "the guide's workflow only if that alert is confirmed. Preserve any historical-interface or threshold caveat."
                    )
            if failure == "regional_values_are_not_identical":
                correction += (
                    " The supplied regional logistics values differ; do not call them identical or claim there is no "
                    "regional variation. Describe each region only from its cited SQL row."
                )
            if failure == "unsupported_specific_logistics_intervention":
                correction += (
                    " Do not recommend moving capacity, opening or relocating warehouses, changing carriers, or redesigning routes. "
                    "The only supported next action is collecting route-level evidence and comparing options after the missing "
                    "service/cost objectives are established. Remove hypothetical causes and specific network interventions."
                )
            if failure == "unprovided_logistics_field":
                correction += (
                    " Remove every field or cause that is not present in the supplied [L#] schema constraints. "
                    "Use only origin/destination, carrier/service type, promised SLA, route capacity, and controllable cost."
                )
            if failure == "cited_logistics_method_not_explained":
                correction += (
                    " State a concrete decision criterion from the cited logistics passage (for example, if that passage "
                    "contains it: inventory availability, location proximity, split fulfillment, destination market, "
                    "or a speed/cost trade-off). Explain it as the publisher's external method and connect it to the "
                    "missing Commerce evidence. If the cited passage only advertises a service, do not present it as a method."
                )
            if failure == "missing_attributed_operating_reference":
                correction += (
                    " Cite one supplied [S#] reference and describe it according to its evidence class: a platform rule "
                    "applies only when that named platform is in scope; a company practice reference is an attributed "
                    "example, while a management cookbook is an attributed general method; neither is Commerce Demo policy. "
                    "Do not describe them as internal rules. "
                    "Do not claim either source describes Commerce Demo's actual operations."
                )
            try:
                answer, provider = _generate_conditional_draft(self.llm, prompt + correction, system_instructions)
                answer_token_usage = accumulate_token_usage(answer_token_usage, self.llm)
                answer = _normalize_numeric_citations(answer, evidence)
            except Exception as error:
                if not is_retryable_provider_error(error):
                    raise
                answer = safe_fallback()
                provider = "deterministic_safety_fallback"
                fallback_used = True
                provider_rate_limited = True
            failure = validation_failure(answer)
        if failure and not provider_rate_limited:
            answer = safe_fallback()
            fallback_used = True
            failure = validation_failure(answer)
        if failure:
            logger.warning(
                "Withholding Commerce answer after validation failed (%s; fallback_used=%s; domain=%s)",
                failure, fallback_used, domain,
            )
            answer = _INVALID_REPORT
        sql_token_usage = snapshot.get("sql_generation_usage")
        total_token_usage = sum_token_usage(sql_token_usage, answer_token_usage)
        return AgentResult(
            answer=answer,
            agent="report",
            evidence=evidence,
            data={"commerce_decision": snapshot},
            metadata={
                "insufficient_context": False,
                "commerce_decision_domain": domain,
                "decision_analysis": "commerce_sql_and_operating_references",
                "decision_reference_retrieval_limited": reference_retrieval_limited,
                "citation_validation_failed": failure is not None,
                "decision_validation_repair_attempted": repaired,
                "decision_fallback_used": fallback_used,
                "generation_provider": provider,
                "question_sql_fallback": question_sql_fallback,
                **({"token_usage": {
                    "sql_generation": sql_token_usage,
                    "answer_generation": answer_token_usage,
                    "total": total_token_usage,
                }} if total_token_usage else {}),
            },
        )

    def close(self) -> None:
        if self._owns_knowledge:
            self.knowledge.close()
        if hasattr(self.llm, "close"):
            self.llm.close()
