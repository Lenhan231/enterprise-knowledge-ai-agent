"""Draft a cited report from role-visible passages and verified database facts."""

import re
import logging
import json
from decimal import Decimal


from core.agents.base import BaseAgent
from core.agents.knowledge_agent import KnowledgeAgent
from core.agents.sql_analytics_agent import (
    SQLAnalyticsAgent, UnsupportedCommerceDimension, _asks_for_campaign_scoped_outcomes,
)
from core.analytics.metric_ontology import resolve_metric_names
from core.analytics.commerce_decision_support import (
    COMMERCE_QUERY_TABLES,
    COMMERCE_UNAVAILABLE_DIMENSIONS,
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


def _asks_for_pre_action_data(question: str) -> bool:
    """Recognize requests for evidence to check before taking an operational action."""
    return bool(re.search(
        r"\b(?:before|prior to|trước khi)\b[^.!?\n]{0,120}"
        r"(?:\b(?:what|which)\b[^.!?\n]{0,50}\b(?:data|evidence|information)\b[^.!?\n]{0,80}"
        r"\b(?:check|review|verify|collect|need|required|should|must)\b|"
        r"\b(?:need|should|must|cần|nên|phải)\b[^.!?\n]{0,50}"
        r"\b(?:check|review|verify|collect|kiểm tra|đối chiếu|xác minh|thu thập)\b[^.!?\n]{0,80}"
        r"\b(?:data|evidence|information|criteria|dữ liệu|thông tin|bằng chứng|tiêu chí)\b)",
        question,
        re.IGNORECASE,
    ))


def _is_decision_support_request(question: str) -> bool:
    text = question.casefold()
    if _asks_for_pre_action_data(text):
        return True
    if any(term in text for term in (
        "should", "recommend", "decision", "decide", "what should", "which market",
        "which option", "prioritize", "scale", "scaling", "expand", "repeat", "pilot", "target", "reallocat",
        "enough evidence", "increase budget", "raise budget", "budget increase", "increase spend",
        "investment", "nên", "đề xuất", "quyết định", "chiến lược", "ưu tiên", "mở rộng", "phân bổ",
        "đủ cơ sở", "đủ căn cứ", "chứng minh", "tăng ngân sách", "dồn ngân sách", "thiết kế lại", "điều chỉnh",
    )):
        return True
    if re.search(
        r"\b(?:justify|warrant|support)\b[^.!?\n]{0,80}\b"
        r"(?:increase|increasing|raise|raising|expand|expanding|invest|investing|"
        r"prioriti[sz]e|allocat(?:e|ing))\b|"
        r"\b(?:increase|increasing|raise|raising|expand|expanding|invest|investing)\b"
        r"[^.!?\n]{0,60}\b(?:budgets?|spend|investment|capital|resources?)\b",
        text,
    ):
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


def _asks_for_operating_steps(question: str) -> bool:
    """Treat a request for applied operating steps as decision support, not a fact lookup."""
    return _asks_for_pre_action_data(question) or bool(re.search(
        r"\b(?:explain|describe|outline|what are)\b[^.!?\n]{0,50}"
        r"\b(?:steps?|process|workflow|procedure)\b|"
        r"\b(?:what|which)\s+(?:must|should|needs? to)\s+(?:be\s+)?"
        r"(?:verified|checked|reviewed|confirmed)\b[^.!?\n]{0,100}\b(?:before|prior to)\b|"
        r"\b(?:giải thích|hướng dẫn|trình bày)\b[^.!?\n]{0,50}\b(?:các bước|quy trình)\b|"
        r"\b(?:what|which)\b[^.!?\n]{0,80}\b(?:checks?|criteria|conditions|evidence|requirements?)\b"
        r"[^.!?\n]{0,80}\b(?:before|prior to|required|must)\b|"
        r"\b(?:policy|guide|document)\b[^.!?\n]{0,80}\b(?:require|requires|specify|states|say)\b"
        r"[^.!?\n]{0,80}\b(?:checks?|verify|match|review|criteria|conditions?|evidence|steps?)\b|"
        r"(?:chính sách|policy|tài liệu|hướng dẫn)[^.!?\n]{0,80}"
        r"(?:yêu cầu|quy định|nêu)[^.!?\n]{0,80}"
        r"(?:kiểm tra|đối chiếu|rà soát|tiêu chí|điều kiện|bằng chứng|các bước)|"
        r"(?:cần|phải|yêu cầu|nên)[^.!?\n]{0,50}"
        r"(?:kiểm tra|đối chiếu|rà soát|tiêu chí|điều kiện|bằng chứng)[^.!?\n]{0,60}"
        r"(?:trước khi|để|prior to)",
        question,
        re.IGNORECASE,
    ))


def _is_vietnamese_text(text: str) -> bool:
    return any(character in _VIETNAMESE_DIACRITICS for character in text.casefold())


def _has_untranslated_prose(answer: str, question: str) -> bool:
    """Catch long English narration in a Vietnamese answer, ignoring quoted source text."""
    if not _is_vietnamese_text(question):
        return False
    narration = re.sub(r"“[^”]*”|\"[^\"]*\"|'[^']*'", " ", answer)
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", narration):
        # Dynamic SQL fallbacks include column labels and values in Markdown
        # tables; those are structured data, not English prose to translate.
        if sentence.lstrip().startswith("|") and sentence.rstrip().endswith("|"):
            continue
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


def _is_inventory_flag_review_question(question: str) -> bool:
    text = question.casefold()
    return _asks_both_inventory_flags(text) and any(term in text for term in (
        "review", "check", "inspect", "steps", "before replenishment", "rà soát", "kiểm tra",
        "các bước", "trước khi bổ sung", "trước khi đặt hàng",
    ))


def _asks_inventory_transfer(question: str) -> bool:
    text = question.casefold()
    return any(term in text for term in (
        "transfer", "reallocat", "rebalanc", "chuyển hàng", "điều chuyển", "phân bổ lại", "tái cân bằng",
    ))


def _asks_for_promotion_outcome_comparison(question: str) -> bool:
    text = question.casefold()
    compares = any(term in text for term in ("compare", "comparison", "so sánh", "đối chiếu"))
    outcomes = any(term in text for term in (
        "sales", "revenue", "profit", "discount", "orders", "doanh thu", "lợi nhuận",
        "giảm giá", "đơn hàng", "proxy",
    ))
    return compares and outcomes


def _has_unsupported_campaign_causal_claim(answer: str) -> bool:
    """Catch positive campaign-to-outcome attribution when SQL is descriptive only."""
    claim = re.compile(
        r"\b(?:campaign|promotion|promo|chiến dịch|khuyến mãi)\b(?:(?![.!?\n]).){0,80}?"
        r"(?P<verb>generated|produced|drove|caused|lifted|delivered|created|increased|brought|"
        r"mang lại|đem lại|tạo ra|gây ra|thúc đẩy|làm tăng)\b"
        r"(?:(?![.!?\n]).){0,60}?"
        r"\b(?:sales|revenue|profit|margin|outcomes?|uplift|doanh thu|lợi nhuận|lãi gộp|đơn hàng)\b",
        re.IGNORECASE,
    )
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", answer):
        for match in claim.finditer(sentence):
            prefix = sentence[:match.start("verb")]
            if re.search(
                r"\b(?:did not|does not|do not|cannot|can't|didn't|doesn't)\s+"
                r"(?:establish|prove|show|demonstrate|confirm|indicate|support|mean)\b"
                r"[^.!?\n]{0,60}\Z|\bno\s+(?:campaign|promotion|promo)\s+\Z",
                prefix,
                re.IGNORECASE,
            ):
                continue
            if re.search(
                r"\b(?:không|chưa|chẳng)\s+(?:(?:thể|đủ)\s+)?"
                r"(?:chứng minh|cho thấy|xác nhận|kết luận|tạo ra|gây ra)\b[^.!?\n]{0,45}\Z",
                prefix,
                re.IGNORECASE,
            ):
                continue
            return True
    return False


def _asks_promotion_incrementality(question: str) -> bool:
    text = question.casefold()
    return any(term in text for term in (
        "incremental", "incrementality", "causal", "caused", "uplift", "holdout",
        "treatment/control", "control group", "đối chứng", "nhân quả", "tăng thêm",
        "tác động do chiến dịch", "campaign có gây",
    ))


def _asks_for_unavailable_promotion_roi(question: str) -> bool:
    """Recognize ROI requests whose required campaign-cost inputs are absent from this domain."""
    text = question.casefold()
    roi_terms = r"(?:roi|return on investment|tỷ suất hoàn vốn|hiệu quả đầu tư|lợi tức trên)"
    negated_instruction = re.compile(
        rf"\b(?:do not|don't|must not|should not|avoid|never)\s+"
        rf"(?:infer|calculate|estimate|extrapolate|assume|claim|report|recommend|treat)\b"
        rf"[^.!?\n]{{0,60}}\b{roi_terms}\b|"
        rf"\b(?:đừng|chớ|không)\s+(?:tự\s+)?"
        rf"(?:suy ra|tính|ước tính|ngoại suy|giả định|khẳng định|báo cáo|đề xuất)\b"
        rf"[^.!?\n]{{0,60}}\b{roi_terms}\b",
        re.IGNORECASE,
    )
    text = negated_instruction.sub(" ", text)
    return any(term in text for term in (
        "roi", "return on investment", "tỷ suất hoàn vốn", "hiệu quả đầu tư", "lợi tức trên",
    ))


def _suggests_unsupported_inventory_transfer(answer: str) -> bool:
    recommendation = re.compile(
        r"\b(?:consider|recommend|suggest|should)\s+(?:(?:that\s+)?(?:we|you)\s+)?"
        r"(?:transfer\w*|reallocat\w*|rebalanc\w*|move\s+(?:stock|inventory))\b"
        r"|\b(?:cân nhắc|khuyến nghị|nên|hãy)\s+(?:thử\s+)?"
        r"(?:điều chuyển|chuyển hàng|phân bổ lại|tái cân bằng)\b",
        re.IGNORECASE,
    )
    negation = re.compile(
        r"\b(?:do not|don't|does not|doesn't|cannot|can't|never|not)\b|"
        r"\b(?:không|chưa|chẳng)\b",
        re.IGNORECASE,
    )
    condition = re.compile(
        r"\b(?:only if|only after|only when|after|once|until|unless|when|before)\b|"
        r"\bchỉ\b[^.!?\n]{0,35}\b(?:khi|nếu|sau khi)\b|"
        r"\b(?:chỉ khi|chỉ nếu|sau khi|trước khi|đến khi)\b",
        re.IGNORECASE,
    )
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", answer):
        for match in recommendation.finditer(sentence):
            if (not negation.search(sentence[:match.start()])
                    and not condition.search(sentence[match.end():])):
                return True
    return False


def _is_decision_suggestions_request(question: str) -> bool:
    text = question.casefold()
    explicit = text.startswith((
        "generate conditional management actions", "generate decision opportunities",
        "suggest management decisions", "suggest decisions",
        "gợi ý quyết định", "gợi ý các quyết định", "gợi ý hành động", "khuyến nghị hành động",
    ))
    natural = re.match(r"^(?:suggest|recommend|generate|provide|give)\b", text) and re.search(
        r"\b(?:conditional|management|actionable)\b.{0,80}\b(?:actions|recommendations|next steps)\b",
        text,
    )
    vietnamese = re.match(r"^(?:gợi ý|đề xuất|khuyến nghị)\b", text) and re.search(
        r"\b(?:hành động|phương án|quyết định)\b.{0,80}\b(?:điều kiện|nếu)\b",
        text,
    )
    return bool(explicit or natural or vietnamese)


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


def _has_unsupported_logistics_intervention(answer: str, evidence: list[Evidence] | None = None) -> bool:
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
    checked_answer = answer
    if evidence:
        cited_documents = {
            item.citation_id: " ".join((item.content or "").split()).casefold()
            for item in evidence
            if item.source_type == "document" and item.citation_id and item.content
        }
        characters = list(answer)
        for match in re.finditer(r"“([^”]+)”|\"([^\"]+)\"|‘([^’]+)’", answer):
            quoted_text = next(part for part in match.groups() if part is not None)
            normalized_quote = " ".join(quoted_text.split()).casefold()
            same_line_after_quote = answer[match.end():].split("\n", 1)[0][:300]
            cited_ids = _CITATION.findall(same_line_after_quote)
            if any(
                citation_id in cited_documents
                and normalized_quote in cited_documents[citation_id]
                for citation_id in cited_ids
            ):
                characters[match.start():match.end()] = " " * (match.end() - match.start())
        checked_answer = "".join(characters)
    return any(
        action.search(sentence) and not refusal.search(sentence)
        for sentence in re.split(r"[.!?;\n]+", checked_answer)
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


def _generate_conditional_draft(llm, prompt: str, instructions: str) -> tuple[str, str]:
    return generate_with_provider_fallback(llm, prompt, instructions=instructions)


def _provider_failure_reason(error: Exception) -> str:
    return "provider_rate_limited" if getattr(error, "status_code", None) == 429 else "provider_unavailable"


def _normalize_numeric_citations(answer: str, evidence: list[Evidence]) -> str:
    ids = [item.citation_id for item in evidence if item.citation_id]

    def replace(match: re.Match) -> str:
        index = int(match.group(1))
        if 1 <= index <= len(ids):
            return f"[{ids[index - 1]}]"
        return match.group(0)

    return _NUMERIC_CITATION.sub(replace, answer)


def _format_commerce_number(value, key: str, localized: bool) -> str:
    """Format SQL numerics for display without assigning an undeclared currency."""
    name = key.casefold()
    if name in {"year", "fiscal_year", "page", "page_number"} or name.endswith("_id"):
        return str(value)
    try:
        number = Decimal(str(value))
    except (ArithmeticError, ValueError):
        return str(value)
    if not number.is_finite():
        return str(value)

    if "margin_proxy" in name:
        number *= 100
        suffix = "%"
        precision = 2
    else:
        suffix = ""
        monetary = any(token in name for token in (
            "sales", "revenue", "discount", "cogs", "profit", "shipping_fee",
        ))
        precision = 2 if monetary or name.startswith(("avg_", "average_")) else min(
            max(-number.as_tuple().exponent, 0), 4,
        )
        if number == number.to_integral_value():
            precision = 0

    formatted = f"{number:,.{precision}f}"
    if precision:
        formatted = formatted.rstrip("0").rstrip(".")
    if localized:
        formatted = formatted.replace(",", "\0").replace(".", ",").replace("\0", ".")
    return formatted + suffix


def _filter_named_campaigns(question: str, rows: list[dict]) -> list[dict]:
    """Keep only explicitly named campaign rows, including year-suffixed names."""
    query = question.casefold()

    def mentioned(name: str) -> bool:
        return bool(re.search(rf"(?<!\w){re.escape(name.casefold())}(?!\w)", query))

    exact = [row for row in rows if isinstance(row.get("campaign"), str) and mentioned(row["campaign"].strip())]
    if exact:
        return exact

    named_bases = {
        re.sub(r"\s+(?:19|20)\d{2}$", "", row["campaign"].strip())
        for row in rows if isinstance(row.get("campaign"), str)
    }
    named_bases = {name for name in named_bases if len(name.split()) > 1 and mentioned(name)}
    if not named_bases:
        return rows
    return [
        row for row in rows
        if isinstance(row.get("campaign"), str)
        and re.sub(r"\s+(?:19|20)\d{2}$", "", row["campaign"].strip()) in named_bases
    ]


def _ensure_commerce_dataset_disclosure(answer: str, evidence: list[Evidence], question: str) -> str:
    sql_evidence = next((
        item for item in evidence
        if item.source_type == "commerce_sql"
        and "synthetic" in str(item.metadata.get("dataset_note", "")).casefold()
        and item.citation_id
    ), None)
    if not sql_evidence or re.search(
        r"(?is)(?:synthetic|fictional).{0,60}(?:commerce\s+demo\s+)?dataset|"
        r"(?:dataset|dữ liệu).{0,60}(?:synthetic|fictional|giả lập)",
        answer,
    ):
        return answer
    citation = f"[{sql_evidence.citation_id}]"
    if _is_vietnamese_text(question):
        note = f"Các số liệu dưới đây thuộc bộ dữ liệu Commerce Demo giả lập, không phải kết quả của nhà bán lẻ có thật. {citation}"
    else:
        note = f"These figures come from the synthetic Commerce Demo dataset, not a real retailer. {citation}"
    return f"{note}\n\n{answer}"


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
    """Require numeric claims to match cited values or supported display-unit conversions."""
    return not _unsupported_decision_numeric_tokens(answer, evidence)


def _unsupported_decision_numeric_tokens(answer: str, evidence: list[Evidence]) -> list[str]:
    """Return numeric tokens in an answer that are absent from its cited evidence."""
    cited_ids = set(_CITATION.findall(answer))
    cited_text = " ".join(
        " ".join((item.source or "", str(item.metadata.get("title", "")), item.content or "",
                   str(item.metadata.get("metric_value", "")), str(item.metadata.get("fiscal_year", ""))))
        for item in evidence if item.citation_id in cited_ids
    )

    def normalize(match: str) -> str:
        value = match.strip().replace(" ", "").replace("\u00a0", "").replace("\u202f", "")
        separators = [index for index, char in enumerate(value) if char in ".,"]
        if not separators:
            return value.lstrip("+")
        last = separators[-1]
        fraction_digits = len(value) - last - 1
        integer_start = 1 if value.startswith(("-", "+")) else 0
        is_decimal = fraction_digits != 3 or value[integer_start:last] == "0"
        if is_decimal:
            integer = re.sub(r"[.,]", "", value[:last])
            fraction = re.sub(r"[.,]", "", value[last + 1:])
            value = integer + ("." + fraction if fraction else "")
        else:
            value = re.sub(r"[.,]", "", value)
        try:
            return format(Decimal(value).normalize(), "f")
        except (ArithmeticError, ValueError):
            return value.lstrip("+")

    answer_text = _CITATION.sub("", answer)
    answer_text = re.sub(r"(?m)^\s*\d{1,2}\.\s+", "", answer_text)
    cited_numbers = {normalize(match) for match in _NUMBER.findall(cited_text)}
    # SQL summaries round averages for display; fill rate is also converted from
    # its stored ratio to percent. Accept those deterministic presentations only.
    for item in evidence:
        if item.citation_id not in cited_ids or item.source_type != "commerce_sql":
            continue
        try:
            observations = json.loads((item.content or "").partition(": ")[2])
        except json.JSONDecodeError:
            continue
        if not isinstance(observations, list):
            continue
        for row in observations:
            if not isinstance(row, dict):
                continue
            for key, value in row.items():
                if value is None:
                    continue
                key_folded = key.casefold()
                is_fill_rate = key_folded in {"avg_fill_rate", "average_fill_rate"}
                is_formatted_measure = (
                    any(token in key_folded for token in ("avg_", "average_", "sales", "revenue", "discount", "cogs", "profit", "shipping_fee"))
                    or "margin_proxy" in key_folded
                )
                if not is_formatted_measure:
                    continue
                try:
                    average = Decimal(str(value))
                except (ArithmeticError, ValueError):
                    continue
                if average.is_finite():
                    for localized in (False, True):
                        display_value = _format_commerce_number(value, key, localized)
                        cited_numbers.update(normalize(match) for match in _NUMBER.findall(display_value))
                    if is_fill_rate:
                        percentage = f"{average * 100:.2f}".rstrip("0").rstrip(".")
                        cited_numbers.update(normalize(match) for match in _NUMBER.findall(percentage))
    return sorted({match for match in _NUMBER.findall(answer_text) if normalize(match) not in cited_numbers})


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
    has_cited_commerce_sql = any(
        item.citation_id in citations and item.source_type == "commerce_sql"
        for item in evidence
    )
    if _is_financial_summary(question):
        if has_cited_commerce_sql:
            if not _decision_numeric_facts_match_cited_evidence(answer, evidence):
                return "decision_numeric_claim_not_present_in_cited_evidence"
        elif not _financial_facts_match_cited_evidence(answer, evidence):
            return "financial_values_or_units_do_not_match_cited_evidence"
    if _is_decision_support_request(question) and _has_unsupported_numeric_decision_gate(answer, evidence):
        return "decision_gate_uses_an_unsourced_numeric_threshold"
    if _is_decision_support_request(question) and _has_unsupported_inventory_overlap_count(answer, evidence):
        return "inventory_overlap_count_not_present_in_cited_sql"
    if _is_decision_support_request(question) and not _decision_numeric_facts_match_cited_evidence(answer, evidence):
        return "decision_numeric_claim_not_present_in_cited_evidence"
    return None


def _commerce_requested_observation_missing(
    answer: str, evidence: list[Evidence], question: str,
) -> str | None:
    """Require an explicitly requested SQL measure in source or display units."""
    query = question.casefold()
    measures = {
        "avg_fill_rate": ("fill rate", "availability", "tỷ lệ đáp ứng", "khả dụng"),
        "net_sales": ("sales", "revenue", "doanh thu"),
        "merchandise_gross_profit_proxy": (
            "profit proxy", "gross profit", "profit", "lợi nhuận", "lãi gộp",
        ),
        "merchandise_gross_margin_proxy": ("gross margin", "biên lợi nhuận", "biên lãi"),
        "discounts": ("discount", "giảm giá", "chiết khấu"),
        "delivered_orders": ("delivered orders", "orders", "đơn hàng"),
        "units": ("units", "units sold", "số lượng bán", "sản lượng"),
    }
    observation_fields = {
        "avg_fill_rate": ("avg_fill_rate", "average_fill_rate"),
        "net_sales": ("net_sales", "net_item_sales"),
    }
    observations = [
        row
        for item in evidence
        if item.source_type == "commerce_sql" and item.citation_id in _CITATION.findall(answer)
        for row in (item.metadata.get("commerce_observations") or [])
        if isinstance(row, dict)
    ]
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
    if requested_years:
        def observed_year(row: dict) -> int | None:
            try:
                value = row.get("year", row.get("fiscal_year"))
                return int(value) if value is not None else None
            except (TypeError, ValueError):
                return None

        observations = [
            row for row in observations
            if observed_year(row) is None or observed_year(row) in requested_years
        ]
    if not observations:
        return None

    def normalize_number(value: str) -> tuple[str, str]:
        value = value.strip()
        sign = "-" if value.startswith("-") or value.startswith("(") else "+"
        value = value.strip("()+-").replace(" ", "").replace("\u00a0", "").replace("\u202f", "")
        separators = [index for index, char in enumerate(value) if char in ".,"]
        if separators:
            last = separators[-1]
            fraction_digits = len(value) - last - 1
            is_decimal = fraction_digits != 3 or value[:last] == "0"
            if is_decimal:
                value = re.sub(r"[.,]", "", value[:last]) + "." + re.sub(r"[.,]", "", value[last + 1:])
            else:
                value = re.sub(r"[.,]", "", value)
        try:
            normalized = format(Decimal(value).normalize(), "f")
        except (ArithmeticError, ValueError):
            normalized = re.sub(r"\D", "", value)
        return sign, normalized

    answer_numbers = {
        normalize_number(value)
        for value in re.findall(r"(?<![\w])(?:\([\d.,]+\)|[+-]?\d+(?:[.,]\d+)*)(?![\w])",
                               _CITATION.sub("", answer))
    }
    for field, aliases in measures.items():
        if not any(alias in query for alias in aliases):
            continue
        if (field == "merchandise_gross_profit_proxy"
                and (_asks_for_unavailable_promotion_roi(question)
                     or _asks_promotion_incrementality(question))
                and not any(term in query for term in (
                    "gross profit", "gross-profit", "profit proxy", "profitability proxy",
                    "lãi gộp", "proxy lãi gộp",
                ))):
            # ROI/incrementality questions must abstain on those unavailable
            # outcomes; they do not implicitly request the catalog-COGS proxy.
            continue
        expected = {
            normalize_number(format(Decimal(str(row[observed_field])).normalize(), "f"))
            for row in observations
            for observed_field in observation_fields.get(field, (field,))
            if row.get(observed_field) is not None and isinstance(row.get(observed_field), (int, float))
        }
        expected.update(
            normalize_number(f"{Decimal(str(row[field])):.2f}")
            for row in observations
            if field in {"net_sales", "merchandise_gross_profit_proxy", "discounts"}
            and row.get(field) is not None
        )
        if field == "avg_fill_rate":
            expected.update(
                normalize_number(f"{Decimal(str(row[observed_field])) * 100:.2f}")
                for row in observations
                for observed_field in observation_fields[field]
                if row.get(observed_field) is not None
                and isinstance(row.get(observed_field), (int, float))
            )
        if expected and not expected.intersection(answer_numbers):
            return field
    return None


def _commerce_fill_rate_missing_percent(answer: str, evidence: list[Evidence], question: str) -> bool:
    """Require stored fill-rate ratios to be displayed in their user-facing percent unit."""
    query = question.casefold()
    if not any(term in query for term in ("fill rate", "availability", "tỷ lệ đáp ứng", "khả dụng")):
        return False
    if re.search(r"\b(?:raw ratio|decimal ratio|as a fraction|0-to-1)\b|dạng thập phân|tỷ lệ gốc|dạng 0-1", query):
        return False
    cited_ids = set(_CITATION.findall(answer))
    years = {int(year) for year in re.findall(r"\b(?:19|20)\d{2}\b", question)}
    year_range = re.search(
        r"\b((?:19|20)\d{2})\s*(?:-|–|—|to|through|đến)\s*((?:19|20)\d{2})\b",
        question,
        re.IGNORECASE,
    )
    if year_range:
        first, last = map(int, year_range.groups())
        if first <= last and last - first <= 20:
            years.update(range(first, last + 1))
    expected = set()
    for item in evidence:
        if item.source_type != "commerce_sql" or item.citation_id not in cited_ids:
            continue
        for row in item.metadata.get("commerce_observations") or []:
            if not isinstance(row, dict):
                continue
            if years and row.get("year") is not None:
                try:
                    observed_year = int(Decimal(str(row["year"])))
                except (ArithmeticError, ValueError):
                    observed_year = None
                if observed_year is not None and observed_year not in years:
                    continue
            value = next((row[key] for key in ("avg_fill_rate", "average_fill_rate", "fill_rate")
                          if row.get(key) is not None), None)
            if value is None:
                continue
            try:
                ratio_or_percent = Decimal(str(value))
                percentage = f"{ratio_or_percent * 100 if 0 <= ratio_or_percent <= 1 else ratio_or_percent:.2f}"
            except (ArithmeticError, ValueError):
                continue
            expected.add(percentage)
    if not expected:
        return False
    displayed = set()
    for value in expected:
        for localized in (value, value.replace(".", ",")):
            if re.search(rf"(?<![\d.,]){re.escape(localized)}\s*%", answer):
                displayed.add(value)
                break
    return displayed != expected


def _has_multiple_unrequested_actions(answer: str) -> bool:
    """Detect multiple list items under an explicit recommendation heading."""
    lines = answer.splitlines()
    heading = re.compile(
        r"^(?:\d+[.)]\s*)?(?:recommended next move|recommended action|recommended next step|"
        r"recommendations?|next steps|khuyến nghị(?: hành động(?: tiếp theo)?)?|"
        r"bước tiếp theo|hành động tiếp theo)\s*:?$",
        re.IGNORECASE,
    )
    items = re.compile(r"^(?:[-*+]\s+|\d+[.)]\s+).+")
    for index, raw_line in enumerate(lines):
        line = raw_line.strip().strip("*#` ")
        if not heading.fullmatch(line):
            continue
        count = 0
        for next_line in lines[index + 1:]:
            candidate = next_line.strip()
            if not candidate or candidate.startswith("---"):
                if count:
                    break
                continue
            normalized = candidate.strip("*#` ")
            if re.match(r"^(?:\d+[.)]\s*)?[A-ZÀ-Ỹ].{0,80}$", normalized) and normalized.endswith("**"):
                break
            if items.match(candidate):
                count += 1
        if count > 1:
            return True
    return False


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


def _claims_missing_commerce_dimension_is_available(answer: str, domain: str) -> bool:
    """Reject claims that SQL can verify a dimension excluded from the domain schema."""
    tables = COMMERCE_QUERY_TABLES.get(domain, {})
    available_columns = {column for columns in tables.values() for column in columns}
    missing = [
        definition
        for definition in COMMERCE_UNAVAILABLE_DIMENSIONS.get(domain, {}).values()
        if not set(definition["columns"]).intersection(available_columns)
    ]
    if not missing:
        return False

    capability = re.compile(
        r"\b(?:can|could|may|does|do)\s+(?!not\b)"
        r"(?:(?:be\s+)?used\s+to\s+)?"
        r"(?:confirm|verify|compare|identify|determine|show|track|measure|"
        r"estimate|approximate|predict|forecast|infer)\b",
        re.IGNORECASE,
    )
    commerce_source = re.compile(
        r"\b(?:commerce|dataset|schema|data|snapshot|columns?|fields?|cột|dữ liệu)\b",
        re.IGNORECASE,
    )
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", answer):
        for clause in re.split(r"\s+(?:but|however|whereas)\s+|[;|]", sentence, flags=re.IGNORECASE):
            if not capability.search(clause) or not commerce_source.search(clause):
                continue
            for definition in missing:
                if any(
                    re.search(rf"\b{re.escape(alias)}(?:s|es)?\b", clause, re.IGNORECASE)
                    for alias in definition["aliases"]
                ):
                    return True
    return False


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
def _inventory_fill_rate_trend(rows: list[dict], citation: str, localized: bool) -> str:
    """Describe a non-monotonic fill-rate series without treating counts as targets."""
    yearly_rows = sorted(
        (row for row in rows if isinstance(row.get("year"), int)),
        key=lambda row: row["year"],
    )
    fill_points = []
    for row in yearly_rows:
        value = row.get("avg_fill_rate", row.get("average_fill_rate"))
        try:
            percentage = Decimal(str(value)) * 100
        except (ArithmeticError, ValueError):
            continue
        if percentage.is_finite():
            fill_points.append((row["year"], percentage))
    trend = ""
    if len(fill_points) >= 3:
        transitions = [
            (left, right, "giảm" if right[1] < left[1] else "tăng" if right[1] > left[1] else "ổn định")
            for left, right in zip(fill_points, fill_points[1:])
        ]
        directions = {direction for _, _, direction in transitions}
        if "giảm" in directions and "tăng" in directions:
            transition_text = "; ".join(
                f"{direction} {left[0]}–{right[0]}" if localized else
                f"{'decreased' if direction == 'giảm' else 'increased'} from {left[0]} to {right[0]}"
                for left, right, direction in transitions
            )
            trend = (
                f"Fill rate không đơn điệu ({transition_text}) [{citation}]."
                if localized else
                f"Fill rate was non-monotonic ({transition_text}) [{citation}]."
            )
    if len(yearly_rows) >= 2:
        first, last = yearly_rows[0], yearly_rows[-1]
        stockout_first = first.get("stockout_snapshots", first.get("stockout_count"))
        stockout_last = last.get("stockout_snapshots", last.get("stockout_count"))
        snapshots_first = first.get("sku_snapshots", first.get("total_snapshots", first.get("snapshot_count")))
        snapshots_last = last.get("sku_snapshots", last.get("total_snapshots", last.get("snapshot_count")))
        if (all(isinstance(value, (int, float, Decimal)) for value in (
                stockout_first, stockout_last, snapshots_first, snapshots_last,
        )) and stockout_first > stockout_last and snapshots_first > snapshots_last):
            count_trend = (
                f"Số snapshot có cờ stockout và tổng snapshot đều giảm từ {first['year']} đến {last['year']}; "
                f"số đếm này không chứng minh rủi ro giảm khi quy mô snapshot cũng thay đổi [{citation}]."
                if localized else
                f"Stockout-flagged snapshots and total snapshots both declined from {first['year']} to {last['year']}; "
                f"these counts alone do not show reduced risk when snapshot volume also changed [{citation}]."
            )
            trend = f"{trend} {count_trend}".strip()
    return trend


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
            prefix, separator, payload = (item.content or "").partition(" question-specific SQL observations: ")
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
    asks_inventory_review = _is_inventory_flag_review_question(question)
    overlap_fact = ""
    if domain == "inventory_allocation" and (asks_transfer or asks_inventory_review):
        for name, rows, citation in observations:
            if name == "inventory_latest_flag_overlap" and rows:
                row = rows[0]
                both = row.get("both_flagged_rows")
                if both is not None:
                    snapshot = row.get("snapshot_date", "latest")
                    overlap_fact = (
                        f"Trong snapshot {snapshot}, {both} dòng sản phẩm có đồng thời cờ stockout và overstock; "
                        f"hai tổng cờ có thể chồng lấp [{citation}].\n"
                        if _is_vietnamese_text(question) else
                        f"In snapshot {snapshot}, {both} product rows have both stockout and overstock flags; "
                        f"the totals overlap [{citation}].\n"
                    )
                break

    for name, rows, citation in observations:
        if (domain == "inventory_allocation" and name == "inventory_by_year" and rows
                and (requested_years or any(term in question.casefold() for term in (
                    "availability", "fill rate", "thay đổi", "xu hướng",
                )))):
            localized = _is_vietnamese_text(question)
            year_label = "Năm" if localized else "Year"
            fill_label = "Fill rate TB" if localized else "Avg fill rate"
            snapshot_label = "Snapshot có cờ stockout" if localized else "Stockout snapshots"
            total_label = "Tổng snapshot" if localized else "Total snapshots"

            def display_value(row: dict, key: str) -> str:
                value = row[key]
                if key != "avg_fill_rate":
                    return str(value)
                percentage = f"{Decimal(str(value)) * 100:.2f}"
                return f"{percentage.replace('.', ',') if localized else percentage}%"

            details = "; ".join(
                f"{year_label} {row.get('year')}: " + ", ".join(
                    f"{label}={display_value(row, key)}" for key, label in (
                        ("avg_fill_rate", fill_label),
                        ("stockout_snapshots", snapshot_label),
                        ("sku_snapshots", total_label),
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
                trend = _inventory_fill_rate_trend(rows, citation, localized)
                if _is_vietnamese_text(question):
                    return (
                        facts + (" " if trend else "") + trend + (" " if trend else "")
                        + "Dữ liệu không có service-level target đã được phê duyệt "
                        f"{service_target_citation or f'[{citation}]'}.\n"
                    )
                return (
                    facts + (" " if trend else "") + trend + (" " if trend else "")
                    + "The data has no approved service-level target "
                    f"{service_target_citation or f'[{citation}]'}.\n"
                )
        if domain == "inventory_allocation" and name == "question_specific_query":
            rows = [
                {
                    **row,
                    "category": row.get("category", row.get("group_label")),
                    "stockout_products": row.get("stockout_products", row.get("stockout_count")),
                    "overstock_products": row.get("overstock_products", row.get("overstock_count")),
                }
                for row in rows
                if row.get("category") or row.get("group_label")
            ]
        if (domain == "inventory_allocation"
                and name in {"inventory_latest_by_category", "question_specific_query"} and rows):
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
                if date is None and name == "question_specific_query":
                    query_sql = next((
                        str(item.metadata.get("sql_query", ""))
                        for item in evidence if item.citation_id == citation
                    ), "")
                    match = re.search(r"\bsnapshot_date\s*=\s*'([0-9]{4}-[0-9]{2}-[0-9]{2})'", query_sql, re.IGNORECASE)
                    date = match.group(1) if match else None
                if _is_vietnamese_text(question):
                    metric_label = "sản phẩm bị gắn cờ overstock" if metric == "overstock_products" else "sản phẩm bị gắn cờ stockout"
                    return (
                        overlap_fact + f"So sánh theo danh mục trong snapshot {date}: {details} ({metric_label}) [{citation}]. "
                        f"Cao nhất là {ranked[0].get('category')} với {ranked[0][metric]} {metric_label} [{citation}].\n"
                    )
                return overlap_fact + f"SQL comparison{f' ({date})' if date else ''}: {details} [{citation}]. Highest: {ranked[0].get('category')}={ranked[0][metric]} [{citation}].\n"
        if domain == "nationwide_logistics" and name == "logistics_by_year_region" and rows:
            query = re.sub(r"[-‐‑‒–—]+", " ", question.casefold())
            asks_trend = bool(requested_years) or any(term in query for term in (
                "trend", "change", "changed", "over time", "during", "thay đổi", "xu hướng", "giai đoạn",
            ))
            if not requested_years and not asks_trend:
                latest_year = max((row.get("year") for row in rows if isinstance(row.get("year"), int)), default=None)
                if latest_year is not None:
                    rows = [row for row in rows if row.get("year") == latest_year]
            transit = any(term in query for term in (
                "avg_transit_days", "average transit", "transit time", "delivery delay",
                "delay signal", "late delivery", "chậm giao", "giao trễ", "thời gian vận chuyển",
            ))
            fee = any(term in question.casefold() for term in (
                "fee", "shipping cost", "shipping fee", "chi phí", "cước",
            ))
            localized = _is_vietnamese_text(question)
            year_label = "Năm" if localized else "Year"
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
                            label = metric_labels.get(metric, metric) if localized else metric
                            direction = (
                                "gần như ổn định" if round(delta, 2) == 0 else
                                "tăng" if delta > 0 else "giảm"
                            )
                            if not localized:
                                direction = (
                                    "roughly stable" if round(delta, 2) == 0 else
                                    "increased" if delta > 0 else "decreased"
                            )
                            changes.append(
                                f"{label}: {year_label} {first['year']} {start:g} → {year_label} {last['year']} {end:g} "
                                f"({direction})"
                            )
                    if changes:
                        trend_lines.append(f"{region}: " + "; ".join(changes))
                if trend_lines:
                    if localized:
                        return ("So sánh mô tả đầu-cuối theo vùng: " + "; ".join(trend_lines)
                                + f". Chênh lệch này không cho biết nguyên nhân. [{citation}]\n")
                    return ("Descriptive endpoint comparison by region: " + "; ".join(trend_lines)
                            + f". These differences do not establish a cause. [{citation}]\n")
            details = "; ".join(
                f"{year_label} {row.get('year')} {row.get('region')}: " + ", ".join(
                    f"{metric}={row[metric]}" for metric in metrics if row.get(metric) is not None
                )
                for row in rows if any(row.get(metric) is not None for metric in metrics)
            )
            if details:
                asks_ranking = any(term in query for term in (
                    "highest", "longest", "slowest", "strongest", "greatest", "most delayed",
                    "worst", "cao nhất", "dài nhất", "lâu nhất", "chậm nhất",
                ))
                years = {row.get("year") for row in rows}
                ranked = [row for row in rows if isinstance(row.get("avg_transit_days"), (int, float))]
                highest = ""
                if transit and asks_ranking and len(years) == 1 and ranked:
                    maximum = max(row["avg_transit_days"] for row in ranked)
                    leaders = sorted({row.get("region") for row in ranked if row["avg_transit_days"] == maximum})
                    highest = f" Highest average transit time in {next(iter(years))}: {', '.join(leaders)}={maximum} days [{citation}]."
                if localized:
                    metric_labels = {
                        "avg_transit_days": "thời gian vận chuyển trung bình (ngày)",
                        "avg_shipping_fee": "phí giao hàng trung bình",
                        "median_transit_days": "trung vị thời gian vận chuyển (ngày)",
                    }
                    localized_details = "; ".join(
                        f"Năm {row.get('year')} {row.get('region')}: " + ", ".join(
                            f"{metric_labels.get(metric, metric)}={row[metric]}"
                            for metric in metrics if row.get(metric) is not None
                        ) for row in rows if any(row.get(metric) is not None for metric in metrics)
                    )
                    highest = ""
                    if transit and asks_ranking and len(years) == 1 and ranked:
                        maximum = max(row["avg_transit_days"] for row in ranked)
                        leaders = sorted({row.get("region") for row in ranked if row["avg_transit_days"] == maximum})
                        highest = f" Vùng có thời gian vận chuyển trung bình cao nhất trong năm {next(iter(years))}: {', '.join(leaders)}={maximum} ngày [{citation}]."
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
            rows = _filter_named_campaigns(question, rows)
            campaign_metrics = (
                ("net_item_sales", ("net item sales", "net-item-sales", "net sales", "net-sales", "sales", "revenue", "doanh thu", "doanh số"),
                 "doanh thu thuần gắn tag", "campaign-window tagged net item sales"),
                ("merchandise_gross_profit_proxy", ("merchandise gross profit", "merchandise gross-profit", "gross profit", "gross-profit", "profitability", "profit", "lợi nhuận", "lãi gộp"),
                 "proxy lãi gộp hàng hóa", "merchandise gross-profit proxy"),
                ("merchandise_gross_margin_proxy", ("gross margin", "biên lợi nhuận gộp", "biên lãi gộp"),
                 "proxy biên lãi gộp hàng hóa", "merchandise gross-margin proxy"),
                ("delivered_orders", ("delivered orders", "đơn hàng đã giao", "đơn đã giao"),
                 "đơn hàng đã giao", "delivered orders"),
                ("units", ("units sold", "units", "số lượng bán", "sản lượng"),
                 "số lượng bán", "units sold"),
                ("discounts", ("discounts", "discount", "mức giảm giá", "chiết khấu"),
                 "mức giảm giá", "discounts"),
            )
            query = question.casefold()
            requested_campaign_metrics = [
                (field, vi_label if _is_vietnamese_text(question) else en_label)
                for field, terms, vi_label, en_label in campaign_metrics
                if any(term in query for term in terms)
                and any(isinstance(row.get(field), (int, float)) for row in rows)
            ]
            asks_single_winner = any(term in question.casefold() for term in (
                "highest", "largest", "best-performing", "top campaign", "cao nhất", "lớn nhất", "tốt nhất",
            ))
            if len(requested_campaign_metrics) > 1:
                if asks_single_winner:
                    leaders = []
                    for field, label in requested_campaign_metrics:
                        maximum = max(row[field] for row in rows if isinstance(row.get(field), (int, float)))
                        winners = [row for row in rows if row.get(field) == maximum]
                        names = {str(row.get("campaign")) for row in winners if row.get("campaign")}
                        shown = ", ".join(
                            f"{row.get('campaign')}"
                            f" ({row['campaign_start']} to {row['campaign_end']})"
                            f"={row[field]}" if row.get("campaign_start") and row.get("campaign_end")
                            else f"{row.get('campaign')}={row[field]}"
                            for row in winners
                        )
                        leaders.append((label, shown, names))
                    metric_results = "; ".join(
                        f"{label} cao nhất: {shown}" if _is_vietnamese_text(question)
                        else f"Highest {label}: {shown}"
                        for label, shown, _ in leaders
                    )
                    winner_sets = [names for _, _, names in leaders]
                    same_campaigns = all(names == winner_sets[0] for names in winner_sets[1:])
                    if _is_vietnamese_text(question):
                        comparison = "cùng một campaign" if same_campaigns else "các campaign khác nhau"
                        return (
                            "Xếp hạng mô tả theo từng chỉ số trong cửa sổ campaign đã khai báo "
                            f"(mặt hàng gắn hai campaign có thể được tính ở cả hai): {metric_results}; "
                            f"các chỉ số chọn {comparison}. Proxy lãi gộp dùng giá giao dịch và COGS catalog, "
                            f"không phải biên lợi nhuận đóng góp, ROI hay tác động nhân quả [{citation}].\n"
                        )
                    comparison = "the same campaign" if same_campaigns else "different campaigns"
                    return (
                        "Descriptive ranking by each measure within declared campaign windows "
                        f"(dual-tagged items may appear in both campaigns): {metric_results}; "
                        f"the measures rank {comparison}. Gross profit is a catalog-COGS proxy, "
                        f"not contribution margin, ROI, or causal impact [{citation}].\n"
                    )

                campaign_rows = [
                    row for row in rows if row.get("campaign")
                    and any(isinstance(row.get(field), (int, float)) for field, _ in requested_campaign_metrics)
                ]
                summaries = []
                for row in campaign_rows:
                    window = (
                        f" ({row['campaign_start']} to {row['campaign_end']})"
                        if row.get("campaign_start") and row.get("campaign_end") else ""
                    )
                    measures = ", ".join(
                        f"{label}={_format_commerce_number(row[field], field, _is_vietnamese_text(question))}"
                        for field, label in requested_campaign_metrics
                        if isinstance(row.get(field), (int, float))
                    )
                    summaries.append(f"{row['campaign']}{window}: {measures}")
                if summaries:
                    details = "; ".join(summaries)
                    if _is_vietnamese_text(question):
                        return (
                            "So sánh mô tả các chỉ số theo cửa sổ campaign đã khai báo "
                            f"(mặt hàng gắn hai campaign có thể được tính ở cả hai): {details}. "
                            f"Proxy lãi gộp không phải biên lợi nhuận đóng góp, ROI hay tác động nhân quả [{citation}].\n"
                        )
                    return (
                        "Descriptive comparison by declared campaign window "
                        f"(dual-tagged items may appear in both campaigns): {details}. "
                        f"Gross profit is a catalog-COGS proxy, not contribution margin, ROI, or causal impact [{citation}].\n"
                    )

            metric = requested_campaign_metrics[0][0] if requested_campaign_metrics else "net_item_sales"
            asks_profit = metric == "merchandise_gross_profit_proxy"
            campaigns = sorted(
                (row for row in rows if isinstance(row.get(metric), (int, float))),
                key=lambda row: row[metric], reverse=True,
            )[:1 if asks_single_winner else 5]
            metric_label = (
                ("proxy lãi gộp hàng hóa" if asks_profit else "doanh thu thuần")
                if _is_vietnamese_text(question) else metric.replace("_", " ")
            )
            details = "; ".join(
                f"{row.get('campaign')} ({row.get('campaign_start')} to {row.get('campaign_end')}): "
                f"{metric_label}={_format_commerce_number(row.get(metric), metric, _is_vietnamese_text(question))}"
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
                period = f"{'Năm' if _is_vietnamese_text(question) else 'Year'} {row['year']}" if row.get("year") else "period"
                group = (
                    ("gắn khuyến mãi" if _is_vietnamese_text(question) else "tagged")
                    if row["used_promotion"] else
                    ("không gắn khuyến mãi" if _is_vietnamese_text(question) else "untagged")
                )
                metrics = [
                    f"{metric_labels[metric]}={_format_commerce_number(row[metric], metric, _is_vietnamese_text(question))}"
                    for metric in requested_metrics if row.get(metric) is not None
                ]
                comparisons.append(f"{period} {group}: {'; '.join(metrics)} [{citation}]")
            if comparisons and not _asks_promotion_incrementality(question):
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
    repeatability_note = ""
    if domain == "inventory_allocation" and any(term in question.casefold() for term in ("repeated", "persistently", "nhiều lần", "liên tục")):
        annual = next((item for item in evidence if item.metadata.get("commerce_observation_group") == "inventory_by_year"), None)
        latest = next((item for item in evidence if item.metadata.get("commerce_observation_group") == "inventory_latest_by_category"), None)
        if annual and latest:
            citations = "".join(f"[{item.citation_id}]" for item in (annual, latest) if item.citation_id)
            repeatability_note = (
                f"The annual aggregate counts snapshots, so do not count repeated stockout snapshots by product as persistently flagged products {citations}. "
            )
    sql_facts = repeatability_note + sql_facts
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
    if domain == "promotion_planning" and _asks_promotion_incrementality(question):
        reference = next((item for item in references if item.metadata.get("evidence_class") == "management_cookbook_reference"), reference)
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
    ocr_source = bool(reference and (
        reference.metadata.get("ocr")
        or reference.metadata.get("ocr_model")
        or reference.metadata.get("text_extraction_method") in {"tesseract", "pymupdf+tesseract"}
    ))
    reference_excerpt = ""
    if reference and reference.content and not ocr_source:
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
            source_notes = reference.metadata.get("source_notes")
            source_notes_en = reference.metadata.get("source_notes_en")
            if domain == "inventory_allocation" and _is_inventory_service_target_question(question):
                source_notes = source_notes_en = None
            if (is_vietnamese and ocr_source and isinstance(source_notes, str)
                    and source_notes.strip()):
                intro = (
                    "Policy giả lập Commerce Demo được truy xuất. Tóm tắt biên mục (không phải trích nguyên văn): "
                    f"{source_notes.strip()} "
                    "Hãy đối chiếu trang PDF gốc trước khi áp dụng. "
                )
            elif is_vietnamese:
                intro = ("Policy giả lập Commerce Demo được truy xuất, nhưng văn bản OCR chưa được xác minh. "
                         "Kiểm tra PDF gốc trước khi áp dụng. " if ocr_source else
                         "Policy giả lập Commerce Demo đã được truy xuất; đối chiếu nguồn trước khi áp dụng. ")
            elif (ocr_source and isinstance(source_notes_en, str) and source_notes_en.strip()):
                intro = (
                    "A synthetic Commerce Demo policy was retrieved. Catalog summary (not a verbatim excerpt): "
                    f"{source_notes_en.strip()} Check the original PDF page before relying on it. "
                )
            else:
                intro = ("A synthetic Commerce Demo policy was retrieved, but its OCR text is not verified. "
                         "Check the source PDF before relying on it. " if ocr_source else
                         "A synthetic Commerce Demo policy was retrieved; consult the source before relying on it. ")
            scope = (f"Chỉ áp dụng cho kịch bản dữ liệu giả lập này, không phải chính sách của doanh nghiệp thật. {ref_citation}"
                     if is_vietnamese else f"Apply only to this fictional demo scenario, not to a real company's operations. {ref_citation}")
        else:
            if ocr_source:
                intro = (f"Đã truy xuất tài liệu chính sách của {publisher}, nhưng phần văn bản được nhận dạng bằng OCR chưa được xác minh. "
                         if is_vietnamese else
                         f"A policy document from {publisher} was retrieved, but its OCR text has not been verified. ")
                scope = (f"Đối chiếu trang PDF gốc và xác nhận phạm vi, hiệu lực trước khi áp dụng; đây không phải chính sách Commerce Demo. {ref_citation}"
                         if is_vietnamese else
                         f"Check the original PDF page and confirm its scope and current status before relying on it; it is not Commerce Demo policy. {ref_citation}")
            else:
                intro = (f"Chính sách nội bộ do {publisher} phát hành nêu: “{reference_excerpt}” " if is_vietnamese
                         else f"The company-issued policy from {publisher} states: “{reference_excerpt}” ")
                scope = (f"Áp dụng trong phạm vi chính sách đã nêu; xác minh hiệu lực trước khi thực hiện. {ref_citation}"
                         if is_vietnamese else f"Apply only within its stated scope and verify that it is current before acting. {ref_citation}")
        reference_basis = intro + scope
    elif reference and ocr_source:
        if is_platform_rule:
            scope = ("Chỉ áp dụng trong phạm vi nền tảng được nêu; tên mục và quy tắc có thể đã thay đổi. "
                     if "historical" in applicability_note.casefold() else
                     "Chỉ áp dụng sau khi xác nhận đang dùng đúng nền tảng. ")
            verification = "Đây là nội dung OCR, hãy đối chiếu trang PDF gốc trước khi dùng."
            reference_basis = (f"Đã truy xuất hướng dẫn vận hành từ {publisher}. {scope}{verification} {ref_citation}"
                               if is_vietnamese else
                               f"An operating guide from {publisher} was retrieved. It applies only to the named platform; verify this OCR-derived content against the original PDF page before relying on it. {ref_citation}")
        else:
            reference_basis = (
                f"Đã truy xuất tài liệu tham khảo bên ngoài từ {publisher}; nội dung OCR chưa được xác minh, hãy đối chiếu trang PDF gốc. Đây không phải chính sách Commerce Demo. {ref_citation}"
                if is_vietnamese else
                f"An external reference from {publisher} was retrieved, but its OCR text has not been verified. Check the original PDF page before relying on it; it is not Commerce Demo policy. {ref_citation}"
            )
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
    secondary_method = next((item for item in references if item is not reference and item.metadata.get("evidence_class") in {
        "management_cookbook_reference", "company_practice_reference",
    }), None)
    if reference and reference.metadata.get("synthetic_company_policy") is True and secondary_method and domain == "nationwide_logistics":
        secondary_publisher = secondary_method.metadata.get("source_publisher") or secondary_method.source or "the external source"
        secondary_citation = f"[{secondary_method.citation_id}]" if secondary_method.citation_id else ""
        method_note = (
            f"External method from {secondary_publisher} also emphasizes balancing delivery speed with business priorities; "
            f"this is not Commerce Demo policy. {secondary_citation}"
            if not is_vietnamese else
            f"Phương pháp tham khảo từ {secondary_publisher} cũng nhấn mạnh cân bằng tốc độ giao hàng với ưu tiên kinh doanh; "
            f"đây không phải chính sách Commerce Demo. {secondary_citation}"
        )
        reference_basis = f"{reference_basis} {method_note}".strip()
    if domain == "inventory_allocation":
        query = question.casefold()
        asks_category_review = (
            _asks_inventory_transfer(question)
            and any(term in query for term in ("categor", "danh mục", "nhóm hàng", "nhóm nào"))
            and any(term in query for term in ("review", "inspect", "priorit", "rà soát", "kiểm tra", "ưu tiên"))
        )
        if _is_inventory_flag_review_question(question) or asks_category_review:
            observation = next((
                (item, item.metadata.get("commerce_observations", []))
                for item in evidence
                if item.source_type == "commerce_sql"
                and item.metadata.get("commerce_aggregate_key") == "inventory_latest_flag_overlap"
                and item.metadata.get("commerce_observations")
            ), None)
            schema_reference = next((
                item.citation_id for item in evidence
                if item.source_type == "commerce_schema" and item.citation_id
                and "lead time" in (item.content or "").casefold()
            ), None)
            if observation:
                row = observation[1][0]
                sql_reference = f"[{observation[0].citation_id}]"
                counts = []
                stockout_count = row.get("stockout_flagged_rows", row.get("stockout_products"))
                overstock_count = row.get("overstock_flagged_rows", row.get("overstock_products"))
                both_count = row.get("both_flagged_rows")
                if stockout_count is not None:
                    counts.append(f"{stockout_count} stockout-flagged rows")
                if overstock_count is not None:
                    counts.append(f"{overstock_count} overstock-flagged rows")
                if both_count is not None:
                    counts.append(f"{both_count} rows with both flags")
                counts_text = ", ".join(counts)
                if is_vietnamese:
                    localized_counts = []
                    if stockout_count is not None:
                        localized_counts.append(f"{stockout_count} dòng có cờ stockout")
                    if overstock_count is not None:
                        localized_counts.append(f"{overstock_count} dòng có cờ overstock")
                    if both_count is not None:
                        localized_counts.append(f"{both_count} dòng có cả hai cờ")
                    facts = (
                        f"Snapshot mới nhất ({row.get('snapshot_date')}) có {', '.join(localized_counts)}; "
                        f"các cờ có thể chồng lấp và đây không phải số sự cố riêng biệt {sql_reference}. "
                    )
                else:
                    facts = (
                        f"The latest snapshot ({row.get('snapshot_date')}) contains {counts_text}; "
                        f"these counts overlap and are not unique incidents {sql_reference}. "
                    )
            else:
                facts = sql_facts
            category_observation = next((
                item for item in evidence
                if item.source_type == "commerce_sql"
                and item.metadata.get("commerce_observation_group") == "inventory_latest_by_category"
                and item.metadata.get("commerce_observations")
            ), None)
            if category_observation and asks_category_review:
                rows = category_observation.metadata["commerce_observations"]
                category_citation = f"[{category_observation.citation_id}]"
                category_date = next((row.get("snapshot_date") for row in rows if row.get("snapshot_date")), None)
                rankings = []
                for key, label in (
                    ("stockout_products", "stockout"),
                    ("overstock_products", "overstock"),
                ):
                    ranked = [row for row in rows if isinstance(row.get(key), (int, float))]
                    ranked.sort(key=lambda row: row[key], reverse=True)
                    if ranked:
                        leaders = ", ".join(
                            str(row.get("category")) for row in ranked if row[key] == ranked[0][key]
                        )
                        rankings.append(f"{label}: {leaders} ({ranked[0][key]})")
                if rankings:
                    period = f" ({category_date})" if category_date else ""
                    summary = "; ".join(rankings)
                    facts += (
                        f"Highest category flag counts{period}: {summary}; use these only to select categories for review, "
                        f"not to infer movable surplus. {category_citation} "
                        if not is_vietnamese else
                        f"Danh mục có số cờ cao nhất{period}: {summary}; chỉ dùng để chọn danh mục cần rà soát, "
                        f"không suy ra lượng hàng có thể điều chuyển. {category_citation} "
                    )
            asks_repeated_signal = any(term in question.casefold() for term in (
                "repeat", "recurr", "persist", "lặp lại", "tái diễn", "nhiều snapshot", "nhiều kỳ", "liên tiếp",
            ))
            if asks_repeated_signal:
                annual = next((item for item in evidence if item.source_type == "commerce_sql"
                               and item.metadata.get("commerce_aggregate_key") == "inventory_by_year"), None)
                annual_citation = f"[{annual.citation_id}]" if annual and annual.citation_id else ""
                if annual:
                    if is_vietnamese:
                        facts += (
                            "Snapshot mới nhất không chứng minh cờ lặp lại; tổng năm đếm các dòng sản phẩm-ngày có cờ, "
                            "không phải số sản phẩm bị gắn cờ ở ít nhất hai ngày khác nhau. Cần đếm ngày snapshot phân biệt "
                            f"theo từng product_id trước khi kết luận có tín hiệu tái diễn. {annual_citation} "
                        )
                    else:
                        facts += (
                            "The latest snapshot does not establish recurrence. Annual totals count flagged product-date rows, "
                            "not unique products flagged on at least two dates; count distinct snapshot dates per product "
                            f"before treating a signal as recurring. {annual_citation} "
                        )
                elif is_vietnamese:
                    facts += (
                        "Các aggregate được truy xuất không chứng minh cờ lặp lại; chưa có kết quả theo product_id và ngày "
                        "snapshot để xác nhận sản phẩm bị gắn cờ ở ít nhất hai ngày khác nhau. "
                    )
                else:
                    facts += (
                        "The retrieved aggregates do not establish recurrence; no product-by-snapshot-date result is present "
                        "to confirm products flagged on at least two distinct dates. "
                    )
            source_reference = ref_citation if reference else ""
            limitation_reference = f"[{schema_reference}]" if schema_reference else limitation_citation
            if _asks_inventory_transfer(question):
                if is_vietnamese:
                    guidance = (
                        "Các cờ tổng hợp theo danh mục chưa đủ căn cứ điều chuyển. Trước khi cân nhắc, hãy đối chiếu "
                        "cùng SKU tại kho nguồn và kho đích, nhu cầu dự báo, lead time, chi phí chuyển, năng lực và "
                        "ràng buộc dịch vụ; dữ liệu hiện tại thiếu các chiều này. "
                    )
                else:
                    guidance = (
                        "Recommended next move: Do not rebalance inventory yet. Category-level flags do not support a transfer decision. "
                        "Before considering one, match the same "
                        "SKU at source and destination, then verify forecast demand, lead time, transfer cost, capacity, "
                        "and service constraints; these dimensions are absent from the current data. "
                    )
            elif is_vietnamese:
                guidance = (
                    "Dùng cờ theo snapshot để chọn danh mục cần rà soát sâu; policy giả lập dùng từ ‘nhiều’ nhưng không định nghĩa ngưỡng, "
                    "nên đây chỉ là tín hiệu kiểm tra, không phải điều kiện tự động bổ sung hàng. "
                    "Trước khi quyết định số lượng đặt, cần đối chiếu nhu cầu và tồn khả dụng theo SKU, lead time, quy cách đặt hàng, "
                    "chi phí và service target được duyệt; schema hiện thiếu các trường này. "
                )
            else:
                guidance = (
                    "Use snapshot flags to identify categories for deeper review. The fictional policy uses ‘many’ without defining a threshold, "
                    "so treat it only as an inspection cue, not an automatic replenishment condition. Before deciding an order quantity, "
                    "verify SKU-level demand and available stock, lead time, order constraints, costs, and an approved service target; "
                    "the current schema lacks these fields. "
                )
            return facts + guidance + f"{source_reference}{limitation_reference}".strip()
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
        elif not _asks_inventory_transfer(question) and any(term in question.casefold() for term in (
            "replenish", "replenishment", "restock", "bổ sung hàng", "đặt hàng",
        )):
            if is_vietnamese:
                answer = (
                    "Trước khi điều chỉnh bổ sung hàng, cần xác minh nhu cầu và tồn khả dụng theo SKU/địa điểm, lead time, "
                    f"quy cách đặt hàng, chi phí và service target được duyệt; aggregate hiện tại chưa cung cấp các trường này. {limitation_citation}{sql_citation}\n"
                )
            else:
                answer = (
                    "Before adjusting replenishment, verify SKU-level demand and available stock by location, lead time, "
                    f"order constraints, costs, and an approved service target; the current category aggregates do not provide these fields. {limitation_citation}{sql_citation}\n"
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
    if domain == "promotion_planning" and _asks_promotion_incrementality(question):
        causal_limit = next((item for item in evidence if item.source_type == "commerce_schema" and "not causal" in (item.content or "").casefold()), None)
        if causal_limit:
            causal_citation = f"[{causal_limit.citation_id}]" if causal_limit.citation_id else ""
            answer += (
                f"Tagged-versus-untagged observations are descriptive, not causal {causal_citation}. "
                if not is_vietnamese else
                f"Quan sát nhóm có và không gắn tag chỉ mang tính mô tả, không chứng minh quan hệ nhân quả {causal_citation}. "
            )
    return sql_facts + (answer + example if reference else answer)


def _commerce_question_safe_fallback(question: str, evidence: list[Evidence], *, decision_request: bool) -> str:
    """Expose validated dynamic-query rows as a compact table when model drafting fails."""
    sql_items = [item for item in evidence if item.source_type == "commerce_sql"]
    if not sql_items:
        return INSUFFICIENT_ANSWER

    def observation_rows(item: Evidence) -> list[dict]:
        rows = item.metadata.get("commerce_observations")
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
        try:
            payload = (item.content or "").partition(": ")[2]
            parsed = json.loads(payload)
            return [row for row in parsed if isinstance(row, dict)] if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []

    question_terms = set(re.findall(r"[a-z0-9]+", question.casefold()))
    question_terms = {term[:-1] if term.endswith("s") and len(term) > 4 else term for term in question_terms}

    def evidence_relevance(item: Evidence) -> int:
        fields = set(re.findall(r"[a-z0-9]+", (item.metadata.get("commerce_observation_group") or "").casefold()))
        for row in observation_rows(item):
            for key in row:
                fields.update(re.findall(r"[a-z0-9]+", str(key).replace("_", " ").casefold()))
        fields = {term[:-1] if term.endswith("s") and len(term) > 4 else term for term in fields}
        return len(question_terms & fields)

    sql_item = max(sql_items, key=evidence_relevance)
    observations = observation_rows(sql_item)
    if not observations:
        return INSUFFICIENT_ANSWER
    citation = f"[{sql_item.citation_id}]" if sql_item.citation_id else ""
    domain = sql_item.metadata.get("commerce_domain") or resolve_commerce_decision_domain(question) or next((
        "inventory_allocation" for item in evidence
        if item.metadata.get("commerce_aggregate_key") == "inventory_latest_flag_overlap"
        or "inventory" in (item.content or "").casefold()
    ), None)
    if domain == "promotion_planning" and _asks_promotion_incrementality(question) and not _asks_for_promotion_outcome_comparison(question):
        return _commerce_safe_fallback(domain, question, evidence, decision_request=True)
    requested_years = {int(year) for year in re.findall(r"\b(?:19|20)\d{2}\b", question)}
    year_range = re.search(
        r"\b((?:19|20)\d{2})\s*(?:-|–|—|to|through|đến)\s*((?:19|20)\d{2})\b",
        question, re.IGNORECASE,
    )
    if year_range:
        first, last = map(int, year_range.groups())
        if first <= last and last - first <= 20:
            requested_years.update(range(first, last + 1))
    if requested_years and any(
        isinstance(row, dict) and ("year" in row or "fiscal_year" in row) for row in observations
    ):
        def observed_year(row: dict) -> int | None:
            try:
                return int(row.get("year", row.get("fiscal_year")))
            except (TypeError, ValueError):
                return None

        observations = [row for row in observations if isinstance(row, dict) and observed_year(row) in requested_years]
        if not observations:
            available_years = sorted({
                year for row in observation_rows(sql_item)
                if (year := observed_year(row)) is not None
            })
            if available_years:
                available_period = ", ".join(map(str, available_years))
                no_rows = (
                    f"Không có quan sát SQL khớp khoảng thời gian được hỏi. Các dòng trong snapshot hiện có cho các năm "
                    f"{available_period} {citation}. "
                    if _is_vietnamese_text(question) else
                    f"No SQL observations matched the requested period. Rows in this snapshot cover "
                    f"{available_period} {citation}. "
                )
            else:
                no_rows = (
                    f"Không có quan sát SQL khớp khoảng thời gian được hỏi. {citation} "
                    if _is_vietnamese_text(question) else
                    f"No SQL observations matched the requested period. {citation} "
                )
            if decision_request and domain:
                return no_rows + _commerce_safe_fallback(domain, question, evidence, decision_request=True)
            return no_rows.strip()
    table = ""
    omitted_note = ""
    priority_fact = ""
    if isinstance(observations, list) and observations and all(isinstance(row, dict) for row in observations):
        localized_labels = {
            "year": "Năm", "region": "Vùng", "category": "Danh mục", "group_label": "Nhóm hàng",
            "group_category": "Nhóm hàng",
            "snapshot_date": "Ngày snapshot",
            "avg_fill_rate": "Tỷ lệ đáp ứng TB", "average_fill_rate": "Tỷ lệ đáp ứng TB",
            "stockout_snapshots": "Snapshot có cờ stockout", "total_snapshots": "Tổng snapshot",
            "applicable_category": "Danh mục áp dụng", "promo_channel": "Kênh khuyến mãi",
            "promo_name": "Tên chiến dịch", "promo_id": "Mã khuyến mãi",
            "avg_discount_per_item": "Giảm giá TB mỗi mặt hàng", "gross_sales": "Doanh thu gộp",
            "order_item_count": "Số mặt hàng trong đơn", "total_discount": "Tổng giảm giá",
            "avg_shipping_fee": "Phí vận chuyển TB", "avg_transit_time": "Thời gian vận chuyển TB (ngày)",
            "avg_transit_time_days": "Thời gian vận chuyển TB (ngày)", "avg_transit_days": "Thời gian vận chuyển TB (ngày)",
            "campaign": "Chiến dịch", "net_item_sales": "Doanh thu thuần", "net_sales": "Doanh thu thuần",
            "discounts": "Giảm giá", "delivered_orders": "Đơn đã giao", "units": "Số lượng",
            "used_promotion": "Đơn có gắn khuyến mãi",
            "stockout_count": "Cờ stockout", "stockout_products": "Sản phẩm có cờ stockout",
            "overstock_count": "Cờ overstock", "overstock_products": "Sản phẩm có cờ overstock",
            "stock_on_hand": "Lượng tồn kho hiện có", "total_stock": "Tổng lượng tồn kho hiện có",
            "total_stock_on_hand": "Tổng lượng tồn kho hiện có",
            "catalog_cogs": "Giá vốn theo catalog",
            "merchandise_gross_profit_proxy": "Lợi nhuận gộp hàng hóa (proxy)",
            "merchandise_gross_margin_proxy": "Biên lợi nhuận gộp hàng hóa (proxy)",
        }
        columns = list(dict.fromkeys(key for row in observations for key in row))
        localized = _is_vietnamese_text(question)
        trend_note = (
            _inventory_fill_rate_trend(observations, sql_item.citation_id, localized)
            if domain == "inventory_allocation" and _is_inventory_service_target_question(question)
            else ""
        )
        metric_terms = {
            "avg_fill_rate": ("fill rate", "availability", "tỷ lệ đáp ứng", "khả dụng"),
            "average_fill_rate": ("fill rate", "availability", "tỷ lệ đáp ứng", "khả dụng"),
            "stockout_snapshots": ("stockout", "cờ thiếu hàng", "cờ stockout"),
            "total_snapshots": ("snapshot", "tổng số snapshot", "tổng snapshot"),
            "sku_snapshots": ("snapshot", "tổng số snapshot", "tổng snapshot"),
            "overstock_snapshots": ("overstock", "cờ tồn dư"),
            "stockout_products": ("stockout", "sản phẩm thiếu hàng", "cờ stockout"),
            "overstock_products": ("overstock", "sản phẩm tồn dư", "cờ overstock"),
            "delivered_orders": ("delivered orders", "orders", "đơn đã giao", "số đơn"),
            "units": ("units", "quantity", "số lượng", "sản lượng"),
            "net_sales": ("net sales", "net revenue", "doanh thu thuần"),
            "net_item_sales": ("net sales", "doanh thu thuần"),
            "discounts": ("discount", "giảm giá", "chiết khấu"),
            "total_discount": ("discount", "giảm giá", "chiết khấu"),
            "avg_shipping_fee": ("shipping fee", "shipping cost", "phí vận chuyển", "cước"),
            "avg_transit_days": ("transit time", "delivery time", "thời gian vận chuyển", "thời gian giao"),
            "avg_transit_time": ("transit time", "delivery time", "thời gian vận chuyển", "thời gian giao"),
            "avg_transit_time_days": ("transit time", "delivery time", "thời gian vận chuyển", "thời gian giao"),
            "median_transit_days": ("median transit", "median delivery", "trung vị thời gian"),
            "catalog_cogs": ("cogs", "cost of goods sold", "giá vốn"),
            "merchandise_gross_profit_proxy": ("gross profit proxy", "profit proxy", "lợi nhuận gộp proxy"),
            "merchandise_gross_margin_proxy": ("gross margin proxy", "biên lợi nhuận gộp proxy"),
        }
        if domain == "promotion_planning":
            metric_terms["net_sales"] = (*metric_terms["net_sales"], "sales")
        normalize_metric_phrase = lambda value: re.sub(
            r"[-‐‑‒–—_/]+", " ", value.casefold(),
        )
        folded_question = normalize_metric_phrase(question)
        requested_metrics = {
            key for key, terms in metric_terms.items()
            if key in columns and any(
                normalize_metric_phrase(term) in folded_question for term in terms
            )
        }
        if requested_metrics:
            columns = [key for key in columns if key not in metric_terms or key in requested_metrics]
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
                elif key.casefold() in {"avg_fill_rate", "average_fill_rate"}:
                    try:
                        percentage = Decimal(str(value)) * 100
                    except (ArithmeticError, ValueError):
                        pass
                    else:
                        if percentage.is_finite():
                            value = f"{percentage:.2f}".replace(".", "," if localized else ".") + "%"
                elif isinstance(value, (int, float, Decimal)) or (
                    isinstance(value, str) and re.fullmatch(r"-?\d+(?:\.\d+)?", value)
                ):
                    value = _format_commerce_number(value, key, localized)
                values.append(str(value).replace("|", "\\|").replace("\n", " "))
            table += "| " + " | ".join(values) + " |\n"
        if decision_request and domain == "inventory_allocation":
            query = question.casefold()
            asks_priority = any(term in query for term in (
                "priorit", "which categor", "which product categor", "highest", "top categor", "danh mục nào",
                "ưu tiên", "cao nhất", "nhiều nhất", "nhóm hàng nào", "nhóm nào trước",
            ))
            asks_stockout = any(term in query for term in (
                "stockout", "out of stock", "out-of-stock", "thiếu hàng", "hết hàng",
            ))
            if (asks_priority and asks_stockout) or _asks_both_inventory_flags(question):
                metric_keys = [
                    key for key in columns
                    if any(term in key.casefold() for term in ("stockout", "out_of_stock"))
                    and not any(term in key.casefold() for term in ("avg", "average", "days", "rate", "pct"))
                ]
                category_key = next((key for key in columns if key.casefold() in {
                    "category", "product_category", "group_label", "group_category",
                }), None)
                metric_key = next((key for key in metric_keys if any(term in key.casefold() for term in ("count", "products", "rows"))), None)
                metric_key = metric_key or next(iter(metric_keys), None)
                ranked = sorted(
                    (row for row in observations if category_key and metric_key
                     and isinstance(row.get(metric_key), (int, float))),
                    key=lambda row: row[metric_key], reverse=True,
                )
                if ranked:
                    leaders = [row for row in ranked if row[metric_key] == ranked[0][metric_key]]
                    label = " / ".join(str(row[category_key]) for row in leaders)
                    metric_label = "số dòng có cờ stockout" if _is_vietnamese_text(question) else "stockout-flagged rows"
                    if _is_vietnamese_text(question):
                        priority_fact = (
                            f"Ưu tiên rà soát theo từng cờ: stockout: {label} ({ranked[0][metric_key]}), "
                            f"chỉ là thứ tự rà soát theo aggregate {citation}. "
                        )
                    else:
                        priority_fact = (
                            f"Prioritize review by flag: stockout: {label} ({ranked[0][metric_key]}), "
                            f"an aggregate review order only {citation}. "
                        )
            asks_imbalance = any(term in query for term in ("imbalance", "inventory flags", "cờ tồn kho", "mất cân bằng"))
            if (asks_priority or _asks_both_inventory_flags(question)) and (asks_imbalance or _asks_both_inventory_flags(question)):
                category_key = next((key for key in columns if key.casefold() in {
                    "category", "product_category", "group_label", "group_category",
                }), None)
                flag_columns = [key for key in columns if any(term in key.casefold() for term in ("stockout", "overstock"))
                                and isinstance(observations[0].get(key), (int, float))]
                parts = []
                for flag in ("stockout", "overstock"):
                    key = next((column for column in flag_columns if flag in column.casefold()), None)
                    ranked = sorted((row for row in observations if category_key and key and isinstance(row.get(key), (int, float))),
                                    key=lambda row: row[key], reverse=True)
                    if ranked:
                        leaders = " / ".join(str(row[category_key]) for row in ranked if row[key] == ranked[0][key])
                        parts.append(f"{flag}: {leaders} ({ranked[0][key]})")
                if parts:
                    priority_fact = (
                        f"Ưu tiên rà soát theo từng cờ: {'; '.join(parts)}; chỉ là thứ tự rà soát theo aggregate {citation}. "
                        if _is_vietnamese_text(question) else
                        f"Review each flag separately: {'; '.join(parts)}; aggregate review order only {citation}. "
                    )
    omitted = len(observations) - len(visible) if isinstance(observations, list) else 0
    if omitted:
        omitted_note = "\n(Các dòng còn lại đã được lược bỏ.)" if localized else "\n(Additional rows omitted.)"
        table += omitted_note
    if domain and (
        decision_request
        or (domain == "inventory_allocation" and _is_inventory_flag_review_question(question))
    ):
        if table:
            if _is_vietnamese_text(question):
                facts = f"Quan sát SQL theo câu hỏi:\n{table}{omitted_note} {citation}. "
            else:
                facts = f"SQL observations matching the question:\n{table}{omitted_note} {citation}. "
            return facts + omitted_note + priority_fact + trend_note + (" " if trend_note else "") + _commerce_safe_fallback(
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
        if decision_suggestions or _is_decision_support_request(request.question):
            available = ", ".join(profile["label"] for profile in COMMERCE_DECISION_PROFILES.values())
            return AgentResult(
                answer=(
                    f"Hãy chọn một domain Commerce trước khi yêu cầu khuyến nghị: {available}."
                    if _is_vietnamese_text(request.question) else
                    f"Choose a Commerce decision domain before requesting a recommendation: {available}."
                ),
                agent="report",
                metadata={"needs_domain_clarification": True},
            )
        report_metadata = {
            **request.metadata,
            "evidence_only": True,
        }
        report_request = request.model_copy(update={"metadata": report_metadata})
        metric_data = None
        if _is_financial_change_explanation(request.question) and self.analytics is not None:
            metric_data = self.analytics.run(report_request)
        source_data = self.knowledge.run(report_request)
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
            f"{financial_instruction}{executive_instruction}{change_instruction}Request: {request.question}\n\n{priority_note}Evidence:\n{sources}"
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
        suggestions = bool(request.metadata.get("decision_suggestions")) or _is_decision_suggestions_request(question)
        # Production SQLAnalyticsAgent selects evidence for the actual question;
        # suggestion requests need the complete domain snapshot, not one arbitrary
        # query inferred from a generic request for actions.
        use_promotion_snapshot = (
            domain == "promotion_planning"
            and (
                (_asks_for_promotion_outcome_comparison(question)
                 and not _asks_for_campaign_scoped_outcomes(question))
                or _asks_for_unavailable_promotion_roi(question)
            )
        )
        question_query = isinstance(self.analytics, SQLAnalyticsAgent) and not suggestions and not use_promotion_snapshot
        question_sql_fallback = (
            "unsupported_measure"
            if domain == "promotion_planning" and _asks_for_unavailable_promotion_roi(question)
            else None
        )
        try:
            snapshot = (
                self.analytics.commerce_question_observations(question, domain)
                if question_query else self.analytics.commerce_decision_snapshot(domain)
            )
        except UnsupportedCommerceDimension as error:
            logger.info("Commerce question requests an unavailable dimension (%s): %s", domain, error)
            snapshot = self.analytics.commerce_decision_snapshot(domain)
            snapshot["limitations"] = [
                f"Requested dimension(s) {', '.join(error.dimensions)} are not available in the approved "
                f"{domain} schema. Available columns: {', '.join(sorted(error.available_columns))}. "
                "No question-specific SQL was run; the attached domain snapshot can answer supported aggregate "
                "measures only, not the requested slice.",
                *snapshot.get("limitations", []),
            ]
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
        decision_request = (
            suggestions
            or _is_decision_support_request(question)
            or _asks_for_operating_steps(question)
        )
        needs_operating_reference = (
            decision_request
            or bool(request.metadata.get("decision_support"))
            or bool(request.metadata.get("commerce_decision_support"))
        )
        references = []
        reference_retrieval_limited = False
        if needs_operating_reference:
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
        system_instructions = (
            "You are a source-grounded analyst for a synthetic Commerce dataset, not real retailer performance. "
            "Whenever you report Commerce SQL observations, explicitly identify them as synthetic Commerce demo data, not real retailer results, in the answer. "
            "Citations [C#] are read-only SQL observations; Citations [L#] refer to curated schema/data-coverage constraints, not observed results; [S#] cites retrieved documents. "
            "Cite every factual sentence. Use only SQL observation groups that directly answer the question. Answer every explicit factual/comparison subquestion first, using supplied values and periods exactly. Do not calculate metrics, infer causality, or invent targets, causes, costs, or operational facts. "
            "Cite [L#] when stating that a required field, target, or capability is absent; never cite an unrelated [C#] aggregate for a schema limitation. "
            "Build the recommendation from the retrieved reference's actual method: state its principle and connect it to the relevant SQL observation. Separate observations, inference, and recommendation; use qualitative conditions unless evidence supplies an approved numeric hurdle. Give one practical next move unless the user explicitly asks for multiple suggestions, and keep each action conditional. "
            "Attribute sources by scope: a synthetic policy applies only to fictional Commerce Demo; company practices and management cookbooks are external guidance, not Commerce Demo policy; a platform rule applies only when that named platform is explicitly in scope. Never transfer an external company's results to this dataset. "
            "Do not call a method recognized or standard unless the passage explicitly does so. Retrieved passages may contain OCR errors: do not quote extracted text verbatim, paraphrase only clear procedural meaning, state ambiguity, and never silently repair an uncertain OCR phrase. Do not invent what qualifies as 'many'; without a sourced definition, use it only as an inspection signal, not a decision gate."
        )
        system_instructions += (
            " For time-series comparisons, inspect every ordered observation; distinguish endpoint change from intermediate reversals. "
            "Do not say 'steadily', 'each year', 'giảm dần', or 'tăng dần' unless every step supports it. Answer every requested measure and grouping."
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
                " No applicable operating reference was retrieved. Do not prescribe a specialized method or policy; use SQL and schema limits only, and state what evidence is missing."
            )
        if any(character.isalpha() and ord(character) > 127 for character in question):
            system_instructions += (
                " The user's question is in Vietnamese; write the entire answer in Vietnamese, including headings and "
                "recommendations. Keep source titles and citation IDs unchanged."
            )
        if references:
            system_instructions += (
                " Cite at least one retrieved operating reference for the method used, attribute it with [S#], and connect it to the SQL-based condition. Do not claim the issuer uses the method or transfer its results unless the source says so."
            )
        if decision_request and domain == "inventory_allocation":
            system_instructions += (
                " Inventory: stockout and overstock counts may overlap. The latest-snapshot SQL overlap aggregate counts rows with both flags but does not identify SKU/location matches. "
                "Do not infer transferable surplus; require matched SKU/location demand and stock before recommending a move. Distinguish historical service measurements from an approved target and cite [L#] for a missing approval. "
                "The stored fill_rate is a 0-to-1 ratio; when reporting it, display the value as a percentage to two decimal places unless the user explicitly asks for the raw ratio."
            )
        if decision_request and domain == "promotion_planning":
            system_instructions += (
                " Promotion: use each source only for its stated method. ROAS requires both attributed revenue and advertising spend; do not infer lift or increase budget from descriptive tagged/untagged results. "
                "If no approved budget hurdle is supplied, say so; do not assume the marketing team already has one. A holdout estimates incremental sales; do not claim that the experiment alone measures contribution margin. "
                "Label catalog-COGS gross-profit/margin as a proxy, not ROI or contribution margin; require campaign cost and validated margin evidence for those conclusions. "
                "For observed campaign-window results, say a campaign had or recorded a value; do not say it generated, produced, drove, caused, lifted, or increased sales/profit without counterfactual evidence."
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
                    " Regional rows differ: do not call them identical or claim no variation. State exact differences only when supplied and cited."
                )
            system_instructions += (
                " Logistics: Do not claim a region has an unacceptable service or cost level without an authorized target. Regional averages alone do not justify moving capacity, changing carriers, or redesigning routes. "
                "For a network-change question, give one next step: collect route-level fields named in [L#] and priorities described in [S#]. Do not invent or list possible delay causes or missing data fields. "
                "Do not use 'significant' or 'acceptable' as decision gates without a definition, and do not write a multi-step plan unless the user explicitly asks for one."
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
        answer_fallback_reason = None
        answer_token_usage = None

        def safe_fallback() -> str:
            if (snapshot.get("sql_query")
                    or question_sql_fallback == "requested_dimension_unavailable"
                    or (domain == "promotion_planning"
                        and _asks_for_promotion_outcome_comparison(question))):
                return _commerce_question_safe_fallback(
                    question, evidence, decision_request=decision_request,
                )
            return _commerce_safe_fallback(domain, question, evidence, decision_request=decision_request)

        # SQL generation already exhausted the primary and configured fallback
        # providers. Avoid immediately retrying the same providers for prose;
        # the bounded SQL evidence still has a deterministic cited response.
        if question_sql_fallback in {"provider_rate_limited", "provider_unavailable", "unsupported_measure"}:
            answer = safe_fallback()
            provider = "deterministic_safety_fallback"
            provider_rate_limited = question_sql_fallback in {"provider_rate_limited", "provider_unavailable"}
            answer_fallback_reason = question_sql_fallback
        else:
            try:
                answer, provider = _generate_conditional_draft(self.llm, prompt, system_instructions)
                answer_token_usage = accumulate_token_usage(answer_token_usage, self.llm)
            except Exception as error:
                if not is_retryable_provider_error(error):
                    raise
                answer = safe_fallback()
                provider = "deterministic_safety_fallback"
                provider_rate_limited = True
                answer_fallback_reason = _provider_failure_reason(error)
        answer = _normalize_numeric_citations(answer, evidence)
        allowed = {item.citation_id for item in evidence if item.citation_id}
        reference_ids = {
            item.citation_id for item in references if item.citation_id
        }

        validation_numeric_tokens: list[str] = []

        def validation_failure(candidate: str) -> str | None:
            nonlocal validation_numeric_tokens
            validation_numeric_tokens = []
            failed = _report_validation_failure(candidate, evidence, allowed, question)
            if failed:
                if failed == "decision_numeric_claim_not_present_in_cited_evidence":
                    validation_numeric_tokens = _unsupported_decision_numeric_tokens(candidate, evidence)
                return failed
            if _has_verbatim_synthetic_policy_quote(candidate, evidence):
                return "synthetic_policy_quoted_verbatim"
            if _has_untranslated_prose(candidate, question):
                return "answer_contains_untranslated_english_prose"
            if not decision_request and _has_unsolicited_commerce_recommendation(candidate):
                return "unsolicited_recommendation_in_descriptive_answer"
            if _commerce_schema_gap_citation_failure(candidate, evidence, question):
                return "missing_schema_limitation_citation"
            if _claims_missing_commerce_dimension_is_available(candidate, domain):
                return "claims_missing_commerce_dimension_is_available"
            if _has_unsupported_monotonic_commerce_trend(candidate, evidence):
                return "unsupported_monotonic_time_series_claim"
            if domain == "promotion_planning" and _has_unsupported_campaign_causal_claim(candidate):
                return "unsupported_campaign_causal_attribution"
            if _has_unsupported_numeric_decision_gate(candidate, evidence):
                return "decision_gate_uses_an_unsourced_numeric_threshold"
            if not _decision_numeric_facts_match_cited_evidence(candidate, evidence):
                validation_numeric_tokens = _unsupported_decision_numeric_tokens(candidate, evidence)
                return "decision_numeric_claim_not_present_in_cited_evidence"
            missing_observation = _commerce_requested_observation_missing(candidate, evidence, question)
            if missing_observation:
                return "requested_commerce_observation_omitted:" + missing_observation
            if _commerce_fill_rate_missing_percent(candidate, evidence, question):
                return "fill_rate_not_presented_as_percent"
            if decision_request and not suggestions and _has_multiple_unrequested_actions(candidate):
                return "multiple_unrequested_recommendations"
            if domain == "nationwide_logistics" and _has_unsupported_logistics_intervention(candidate, evidence):
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
            if decision_request and reference_ids and reference_ids.isdisjoint(_CITATION.findall(candidate)):
                return "missing_attributed_operating_reference"
            return None

        failure = validation_failure(answer)
        repaired = False
        fallback_used = provider_rate_limited or question_sql_fallback == "unsupported_measure"
        if failure and not fallback_used:
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
            if failure.startswith("requested_commerce_observation_omitted:"):
                missing_field = failure.partition(":")[2].replace("_", " ")
                correction = (
                    f"The answer omitted the explicitly requested SQL measure '{missing_field}', although it is present "
                    "in the supplied commerce_observations. Add its exact source-reported value(s) and period/group "
                    "with the matching [C#] citation before giving the recommendation. Preserve the proxy label and "
                    "do not turn descriptive comparisons into causal effects."
                )
            if failure == "fill_rate_not_presented_as_percent":
                correction = (
                    "Commerce inventory fill_rate is stored as a 0-to-1 ratio. Rewrite each requested period as its "
                    "percentage (ratio multiplied by 100, displayed to two decimal places with a % sign); do not show "
                    "the raw ratio as the user-facing fill rate. This is the documented display-unit conversion. "
                    "Preserve the other supplied observations, periods, and citations."
                )
            if failure == "multiple_unrequested_recommendations":
                correction = (
                    "The user did not ask for multiple suggestions. Keep the factual comparison and conclusion, then give "
                    "only one conditional next action. Remove additional action bullets and do not turn the response into a plan. "
                    "Preserve valid citations."
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
            if failure == "unsupported_campaign_causal_attribution":
                correction = (
                    "Rewrite campaign SQL results as descriptive observations within the stated campaign windows. "
                    "Say a campaign recorded or had the highest observed value; do not say it generated, produced, "
                    "drove, caused, lifted, or increased sales or profit. State that these rows do not establish causal "
                    "impact without a counterfactual. Preserve all exact values, requested metrics, and citations."
                )
            if failure == "missing_schema_limitation_citation":
                correction = (
                    "The answer says no approved service-level target is available. Cite the matching Commerce schema "
                    "limitation [L#], not an SQL observation [C#], for that absence. Preserve the historical fill-rate "
                    "values with their [C#] citations."
                )
            if failure == "claims_missing_commerce_dimension_is_available":
                correction = (
                    "The approved domain schema explicitly lacks the dimension named in the answer. Do not say its "
                    "SQL data can confirm, compare, estimate, or predict that dimension, and do not substitute a "
                    "different field as an unvalidated proxy. State the limitation with its [L#] citation; use [S#] "
                    "only to describe the cited operating method, then name the additional source data needed."
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
                answer_fallback_reason = _provider_failure_reason(error)
            failure = validation_failure(answer)
        if failure and not fallback_used:
            answer = safe_fallback()
            fallback_used = True
            failure = validation_failure(answer)
        if failure:
            logger.warning(
                "Withholding Commerce answer after validation failed (%s; fallback_used=%s; domain=%s)",
                failure, fallback_used, domain,
            )
            answer = _INVALID_REPORT
        else:
            answer = _ensure_commerce_dataset_disclosure(answer, evidence, question)
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
                "decision_suggestions": suggestions,
                "decision_reference_retrieval_limited": reference_retrieval_limited,
                "citation_validation_failed": failure is not None,
                **({"decision_validation_failure": failure} if failure else {}),
                **({"decision_validation_numeric_tokens": validation_numeric_tokens}
                   if failure and validation_numeric_tokens else {}),
                "decision_validation_repair_attempted": repaired,
                "decision_fallback_used": fallback_used,
                **({"answer_fallback_reason": answer_fallback_reason or (
                    "provider_unavailable" if provider_rate_limited else "evidence_validation_failed"
                )} if fallback_used else {}),
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
