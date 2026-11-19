"""Typed matching and compilation for SQL requests with deterministic contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any, Callable

from sqlglot import exp

from core.analytics.field_retrieval import compile_field_query, field_contract
from core.analytics.metric_mapping import MetricMapping, compile_inventory_query
from core.analytics.metric_ontology import resolve_metric_names
from core.analytics.sql_validation import QueryPlan


class CompilerKind(str, Enum):
    PROMOTION = "promotion"
    ANNUAL_REVENUE = "annual_revenue"
    COMPLETED_MONTHS_REVENUE = "completed_months_revenue"
    EXPLICIT_MONTH_REVENUE = "explicit_month_revenue"
    MONTH_OVER_MONTH_REVENUE = "month_over_month_revenue"
    DIRECT_FIELD = "direct_field"
    INVENTORY_MAPPING = "inventory_mapping"


@dataclass(frozen=True)
class FixedQueryMatch:
    """A recognized request and the already-resolved inputs needed to compile it."""

    compiler: CompilerKind | None = None
    metric_names: frozenset[str] = frozenset()
    promotion_metric: str | None = None
    direct_contract: exp.Select | None = None
    explicit_order_item_formula: bool = False
    parameters: tuple[Any, ...] = ()
    limit: int | None = None

    @property
    def matched(self) -> bool:
        return self.compiler is not None


@dataclass(frozen=True)
class CompilationSelection:
    """Typed compiler metadata plus the optional plan produced at that stage."""

    compiler: CompilerKind | None = None
    plan: QueryPlan | None = None
    metric_names: frozenset[str] = frozenset()
    promotion_metric: str | None = None
    direct_contract: exp.Select | None = None
    explicit_order_item_formula: bool = False

    @property
    def matched(self) -> bool:
        return self.compiler is not None


_REVENUE_REQUEST_WORDS = frozenset({
    "a", "amount", "an", "are", "calendar", "calculate", "can", "could", "current",
    "during", "find", "for", "full", "get", "how", "in", "is", "it", "know", "last",
    "me", "month", "months", "much", "of", "overall", "please", "previous", "recent",
    "recently", "revenue", "sales", "show", "sum", "tell", "the", "this", "to", "total",
    "versus", "was", "what", "were", "within", "would", "year", "you", "vs", "with",
    "change", "comparison", "compare", "completed", "delta", "difference", "finished", "growth",
    "kpi", "month-over-month", "past", "percent", "percentage", "rate", "variance",
    "bao", "biết", "cho", "còn", "đây", "đã", "đối", "doanh", "gần", "giúp", "hãy",
    "hiện", "là", "lòng", "mình", "năm", "nay", "nhất", "nhiêu", "ngoái", "sao", "so",
    "tại", "tháng", "thì", "thu", "tính", "tôi", "trong", "trước", "tổng", "vậy", "vui",
    "xin", "sánh", "hoàn", "tất",
})

_PROMOTION_REQUEST_WORDS = frozenset({
    "active", "are", "best", "by", "code", "codes", "count", "coupon", "current", "currently",
    "discount", "gross", "highest", "how", "many", "me", "most", "net", "of", "please",
    "promo", "promos", "promotion", "promotions", "rank", "ranking", "revenue", "sales", "show",
    "the", "top", "total", "voucher", "with", "lowest", "bottom", "is", "there", "running",
    "bao", "cho", "chương", "đang", "động", "giá", "hoạt", "khuyến", "lượng", "mã", "mãi",
    "nhiêu", "số", "tôi", "trình", "doanh", "thu", "có", "cao", "hiện", "tại", "nhất", "giảm",
})


def _has_unrecognized_request_terms(
    question: str,
    allowed_words: frozenset[str],
    *,
    allowed_numbers: frozenset[str] = frozenset(),
    allow_years: bool = False,
) -> bool:
    """Reject residual words that a deterministic template cannot represent."""
    text = re.sub(r"(?<=\w)'s\b", "", question.casefold())
    terms = re.findall(r"[^\W_]+", text, flags=re.UNICODE)
    return any(
        term not in allowed_words
        and term not in allowed_numbers
        and not (allow_years and re.fullmatch(r"(?:19|20)\d{2}", term))
        for term in terms
    )


def _has_unrepresented_scope(question: str, *, promotion_ranking: bool = False,
                            month_comparison: bool = False,
                            allowed_words: frozenset[str] | None = None,
                            allowed_numbers: frozenset[str] = frozenset(),
                            allow_years: bool = False) -> bool:
    """Conservatively decline templates when the question asks for extra scope or outputs."""
    text = question.casefold()
    text = re.sub(r"^\s*(?:(?:hãy|xin|vui\s+lòng)\s+)?cho\s+(?:(?:tôi|mình)\s+)?biết\b", " ", text)
    if month_comparison:
        text = re.sub(r"\bwith\s+(?:the\s+)?(?:previous|last|current|this)\s+month\b", " ", text)
        text = re.sub(r"\b(?:compare|comparison|versus|vs\.?)\b", " ", text)
        text = re.sub(r"\b(?:growth|change|difference|delta|variance|rate|percent(?:age)?)\b", " ", text)
    if promotion_ranking:
        text = re.sub(r"^\s*(?:cho\s+tôi|please|show\s+me)\b", " ", text)
        text = re.sub(r"\b(?:top|bottom|highest|lowest|most|rank(?:ing)?|best)\b", " ", text)
        text = re.sub(r"\bby\s+(?:(?:total|net|gross)\s+)?(?:revenue|sales|doanh\s+thu)\b", " ", text)
        text = re.sub(r"\bwith\s+(?:the\s+)?(?:highest|most)\s+(?:total\s+)?(?:revenue|sales)\b", " ", text)
    if re.search(
        r"\b(?:by|per|group(?:ed)?|breakdown|according\s+to|rank(?:ing)?|top|bottom|"
        r"highest|lowest|include|including|also|along\s+with|as\s+well\s+as|output|column|field|"
        r"growth|change|difference|delta|variance|average|mean|median|profit|margin|rate|"
        r"percent(?:age)?|forecast|predict|trend|"
        r"where|with|filter(?:ed)?|only|excluding|except|between|through|until|before|after|"
        r"compare|comparison|versus|vs\.?)\b|"
        r"\bfor\s+(?!(?:(?:19|20)\d{2}|(?:the\s+)?year|(?:last|previous|this|current)\s+year)\b)|"
        r"\bin\s+(?!(?:(?:19|20)\d{2}|(?:the\s+)?year|(?:last|previous|this|current)\s+year|"
        r"january|february|march|april|may|june|july|august|september|october|november|december)\b)|"
        r"\bat\s+(?!(?:(?:19|20)\d{2}|(?:the\s+)?year)\b)|"
        r"theo\s+(?:từng|mỗi)?|từng\s+\w+|mỗi\s+\w+|"
        r"(?:cho|lọc|chỉ|bao gồm|ngoại trừ|trừ|tại|ở)\s+(?!năm\s+(?:(?:19|20)\d{2}|ngoái|trước|nay)\b)",
        text,
    ):
        return True
    if re.search(
        r"\b(?:region|regional|country|state|city|category|product|sku|brand|segment|"
        r"branch|channel|customer|store|warehouse|supplier|order|status|payment)\b|"
        r"khu vực|miền\s+(?:bắc|nam|trung)|tỉnh|thành phố|chi nhánh|kho\b|"
        r"danh mục|sản phẩm|mã hàng|thương hiệu|phân khúc|kênh|khách hàng|"
        r"cửa hàng|nhà cung cấp|đơn hàng|trạng thái|thanh toán",
        text,
    ):
        return True
    if allowed_words is not None and _has_unrecognized_request_terms(
            text, allowed_words, allowed_numbers=allowed_numbers, allow_years=allow_years):
        return True
    return False


def _annual_revenue_match(question: str, metric_names: frozenset[str], today: date | None) -> tuple[date, date] | None:
    if metric_names != {"revenue"}:
        return None
    text = question.casefold()
    if re.search(r"\btháng\s+(?:0?[1-9]|1[0-2])\b|\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b|\bmonth\b|\bq[1-4]\b|\bquarter\b|quý\s+[1-4]|\b(?:19|20)\d{2}[-/]\d{1,2}", text):
        return None
    if (re.search(r"\b(?:compare|comparison|versus|vs\.?|trend|monthly|daily|by|per|region|category|product|channel|quarter|year.over.year)\b|so sánh|xu hướng|theo\s+\w+", text)
            or _has_unrepresented_scope(
                text, allowed_words=_REVENUE_REQUEST_WORDS, allow_years=True)):
        return None
    years = set(re.findall(r"\b(?:19|20)\d{2}\b", text))
    if len(years) > 1:
        return None
    if years:
        year = int(next(iter(years)))
    elif re.search(r"\b(?:this year|current year|năm nay|năm hiện tại)\b", text):
        year = (today or date.today()).year
    elif re.search(r"\b(?:last year|previous year|năm ngoái|năm trước)\b", text):
        year = (today or date.today()).year - 1
    else:
        return None
    return date(year, 1, 1), date(year + 1, 1, 1)


def _completed_months_revenue_match(question: str, metric_names: frozenset[str], today: date | None) -> tuple[date, date] | None:
    if metric_names != {"revenue"}:
        return None
    count_words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                   "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
    match = re.search(
        r"\b(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
        r"(?:completed\s+)?months?\b|"
        r"\b(\d{1,2}|một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười)\s+tháng\b",
        question.casefold(),
    )
    completed = bool(re.search(
        r"completed|finished|đã\s+hoàn\s+tất|hoàn\s+tất|gần\s+(?:nhất|đây)|most\s+recent|last|past",
        question.casefold(),
    ))
    other_period = bool(re.search(
        r"\b(?:19|20)\d{2}\b|\b(?:january|february|march|april|may|june|july|august|september|"
        r"october|november|december)\b|\b(?:this|last|previous|current)\s+(?:year|quarter)\b|"
        r"\bq[1-4]\b|\bquarter\b|\btháng\s+\d{1,2}\s+(?:năm\s+)?(?:19|20)\d{2}\b",
        question.casefold(),
    ))
    raw_count = next(value for value in match.groups() if value) if match else None
    if not match or not completed or other_period or _has_unrepresented_scope(
            question,
            allowed_words=(_REVENUE_REQUEST_WORDS | ({raw_count} if raw_count and not raw_count.isdigit() else set())),
            allowed_numbers=frozenset({raw_count}) if raw_count and raw_count.isdigit() else frozenset()):
        return None
    vi_count = {"một": 1, "hai": 2, "ba": 3, "bốn": 4, "năm": 5,
                "sáu": 6, "bảy": 7, "tám": 8, "chín": 9, "mười": 10}
    count = int(raw_count) if raw_count.isdigit() else count_words.get(raw_count, vi_count.get(raw_count))
    if not count or count > 24:
        return None
    today = today or date.today()
    end = date(today.year, today.month, 1)
    month_index = end.year * 12 + end.month - 1 - count
    return date(month_index // 12, month_index % 12 + 1, 1), end


def _explicit_month_revenue_match(question: str, metric_names: frozenset[str], today: date | None) -> tuple[date, date] | None:
    match = re.search(r"\btháng\s+(0?[1-9]|1[0-2])(?:\s+năm\s+((?:19|20)\d{2}))?\b", question, re.I)
    if (metric_names != {"revenue"} or match is None
            or _has_unrepresented_scope(
                question,
                allowed_words=_REVENUE_REQUEST_WORDS,
                allowed_numbers=frozenset(group for group in match.groups() if group))):
        return None
    year, month = int(match.group(2) or (today or date.today()).year), int(match.group(1))
    start = date(year, month, 1)
    end = date(year + (month == 12), month % 12 + 1, 1)
    return start, end


def _month_over_month_revenue_match(question: str, metric_names: frozenset[str], today: date | None) -> tuple[date, date, date] | None:
    text = question.casefold()
    compares_months = bool(re.search(r"\b(?:compare|comparison|versus|vs\.?|month.over.month|mom)\b|so sánh|đối chiếu", text))
    mentions_previous_month = bool(re.search(r"previous month|last month|tháng trước", text))
    explicit_period = bool(re.search(r"\b(?:19|20)\d{2}\b|\btháng\s+(?:0?[1-9]|1[0-2])\b|\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b", text))
    if (metric_names != {"revenue"} or not compares_months or not mentions_previous_month
            or explicit_period or _has_unrepresented_scope(
                question, month_comparison=True, allowed_words=_REVENUE_REQUEST_WORDS)):
        return None
    today = today or date.today()
    current_start = date(today.year, today.month, 1)
    previous_start = date(today.year - 1, 12, 1) if today.month == 1 else date(today.year, today.month - 1, 1)
    next_start = date(today.year + (today.month == 12), today.month % 12 + 1, 1)
    return previous_start, current_start, next_start


def _promotion_match(question: str, today: date | None) -> FixedQueryMatch | None:
    text = question.casefold()
    mentions_promo = bool(re.search(r"promo(?:tion)?s?|promotion code|discount code|coupon|voucher|khuyến mãi|mã giảm giá|mã khuyến mãi", text))
    explicit_period = bool(re.search(
        r"\b(?:19|20)\d{2}\b|\b(?:january|february|march|april|may|june|july|august|"
        r"september|october|november|december)\b|\b(?:last|previous|this)\s+(?:month|year|week|day)\b|"
        r"\btháng\s+\d{1,2}\b|\bngày\s+\d{1,2}[/-]\d{1,2}", text))
    asks_active_count = bool(re.search(r"\bhow many\b|\bcount\b|bao nhiêu|số lượng", text)) and bool(
        re.search(r"\bactive\b|\bcurrent\b|currently|hiện tại|đang hoạt động", text))
    asks_top_revenue = bool(re.search(r"\b(?:top|highest|most|rank|best)\b|cao nhất|nhiều nhất|đứng đầu", text)) \
        and bool(re.search(r"revenue|sales|doanh thu", text))
    limit_match = (re.search(r"\btop\s+(\d{1,2})\b|(\d{1,2})\s+(?:mã|promo|promotion|discount)", text)
                   if asks_top_revenue else None)
    allowed_numbers = (frozenset(group for group in limit_match.groups() if group)
                       if limit_match else frozenset())
    if (not mentions_promo or explicit_period
            or (asks_top_revenue and re.search(r"\btoday\b|hôm nay", text))
            or _has_unrepresented_scope(
                text, promotion_ranking=True,
                allowed_numbers=allowed_numbers,
                allowed_words=(_PROMOTION_REQUEST_WORDS | {"today", "hôm", "nay"}
                               if asks_active_count else _PROMOTION_REQUEST_WORDS))):
        return None

    if asks_active_count:
        return FixedQueryMatch(CompilerKind.PROMOTION, promotion_metric="active_promotion_count",
                               parameters=(today or date.today(),))

    if asks_top_revenue:
        limit = min(int(next(group for group in limit_match.groups() if group)), 50) if limit_match else 10
        return FixedQueryMatch(CompilerKind.PROMOTION, promotion_metric="promotion_revenue", limit=limit)
    return None


def match_fixed_query(
    question: str,
    *,
    original_question: str | None = None,
    context: Any = None,
    today: date | None = None,
) -> FixedQueryMatch:
    """Match one fixed/direct request without constructing SQL."""
    original_question = original_question if isinstance(original_question, str) and original_question.strip() else question
    scope_question = question if original_question.strip() == question.strip() else question + "\n" + original_question.strip()
    direct = field_contract(question) if context is None else None
    explicit_order_item_formula = all(
        re.search(rf"\b{field}\b", scope_question, re.I)
        for field in ("quantity", "unit_price", "discount_amount")
    )
    promotion = _promotion_match(scope_question, today=today) if direct is None else None
    if promotion is not None:
        promotion = FixedQueryMatch(
            compiler=promotion.compiler,
            metric_names=promotion.metric_names,
            promotion_metric=promotion.promotion_metric,
            explicit_order_item_formula=explicit_order_item_formula,
            parameters=promotion.parameters,
            limit=promotion.limit,
        )
    metric_names = (frozenset() if direct is not None or promotion is not None or explicit_order_item_formula
                    else frozenset(resolve_metric_names(question)))
    relative_month_followup = bool(re.fullmatch(
        r"\s*(?:(?:vậy|còn)\s+)?(?:tháng trước(?: thì sao)?|last month|previous month)\s*[?!.]*\s*",
        original_question, re.I))

    annual_scope_supported = _annual_revenue_match(scope_question, metric_names, today) is not None
    if question.strip() == original_question.strip() and re.search(
        r"\b(?:19|20)\d{2}\b", scope_question,
    ) and re.search(
        r"\b(?:this|current|last|previous)\s+year\b|năm\s+(?:nay|hiện tại|ngoái|trước)",
        scope_question, re.I,
    ):
        annual_scope_supported = False
    annual = None
    if annual_scope_supported:
        annual = (_annual_revenue_match(original_question, metric_names, today)
                  or _annual_revenue_match(question, metric_names, today))

    completed_supported = _completed_months_revenue_match(scope_question, metric_names, today) is not None
    completed = (_completed_months_revenue_match(original_question, metric_names, today)
                 if completed_supported else None)
    explicit_supported = _explicit_month_revenue_match(scope_question, metric_names, today) is not None
    explicit = (_explicit_month_revenue_match(question, metric_names, today)
                if relative_month_followup and explicit_supported else None)
    month_supported = _month_over_month_revenue_match(scope_question, metric_names, today) is not None
    month_comparison = (_month_over_month_revenue_match(question, metric_names, today)
                        if month_supported else None)

    candidates = (
        (CompilerKind.PROMOTION, promotion),
        (CompilerKind.ANNUAL_REVENUE, annual),
        (CompilerKind.COMPLETED_MONTHS_REVENUE, completed),
        (CompilerKind.EXPLICIT_MONTH_REVENUE, explicit),
        (CompilerKind.MONTH_OVER_MONTH_REVENUE, month_comparison),
    )
    for compiler, parameters in candidates:
        if parameters is not None:
            if isinstance(parameters, FixedQueryMatch):
                return parameters
            return FixedQueryMatch(compiler, metric_names=metric_names, parameters=parameters)
    if direct is not None:
        return FixedQueryMatch(CompilerKind.DIRECT_FIELD, direct_contract=direct,
                               explicit_order_item_formula=explicit_order_item_formula)
    return FixedQueryMatch(metric_names=metric_names,
                           explicit_order_item_formula=explicit_order_item_formula)


def _compile_fixed_match(match: FixedQueryMatch) -> QueryPlan:
    parameters = match.parameters
    if match.compiler == CompilerKind.ANNUAL_REVENUE:
        return QueryPlan(
            sql=("SELECT SUM(s.revenue) AS revenue FROM commerce.sales AS s "
                 "WHERE s.date >= $1 AND s.date < $2 LIMIT 1"),
            parameters=parameters,
            explanation="Compile a calendar-year revenue total from commerce.sales.",
        )
    if match.compiler == CompilerKind.COMPLETED_MONTHS_REVENUE:
        return QueryPlan(
            sql=("SELECT DATE_TRUNC('month', s.date)::date AS month, SUM(s.revenue) AS revenue "
                 "FROM commerce.sales AS s WHERE s.date >= $1 AND s.date < $2 "
                 "GROUP BY DATE_TRUNC('month', s.date)::date ORDER BY month LIMIT 200"),
            parameters=parameters,
            explanation="Aggregate revenue by month over the most recent completed calendar months.",
        )
    if match.compiler == CompilerKind.EXPLICIT_MONTH_REVENUE:
        return QueryPlan(
            sql=("SELECT CAST($1 AS DATE) AS month, SUM(s.revenue) AS revenue "
                 "FROM commerce.sales AS s WHERE s.date >= $1 AND s.date < $2 LIMIT 1"),
            parameters=parameters,
            explanation="Compile a calendar-month revenue total from commerce.sales.",
        )
    if match.compiler == CompilerKind.MONTH_OVER_MONTH_REVENUE:
        return QueryPlan(
            sql=("SELECT CAST($2 AS DATE) AS month, CAST($1 AS DATE) AS previous_month, "
                 "SUM(s.revenue) FILTER (WHERE s.date >= $2 AND s.date < $3) AS revenue, "
                 "SUM(s.revenue) FILTER (WHERE s.date >= $1 AND s.date < $2) AS previous_month_revenue, "
                 "SUM(s.revenue) FILTER (WHERE s.date >= $2 AND s.date < $3) - "
                 "SUM(s.revenue) FILTER (WHERE s.date >= $1 AND s.date < $2) AS revenue_change, "
                 "(SUM(s.revenue) FILTER (WHERE s.date >= $2 AND s.date < $3) - "
                 "SUM(s.revenue) FILTER (WHERE s.date >= $1 AND s.date < $2)) / "
                 "NULLIF(SUM(s.revenue) FILTER (WHERE s.date >= $1 AND s.date < $2), 0) AS revenue_change_fraction "
                 "FROM commerce.sales AS s LIMIT 1"),
            parameters=parameters,
            explanation="Compare current and previous calendar month revenue using code-resolved date bounds.",
        )
    if match.compiler == CompilerKind.PROMOTION:
        if match.promotion_metric == "active_promotion_count":
            return QueryPlan(
                sql=("SELECT COUNT(*) AS active_promotion_count "
                     "FROM commerce.promotions AS p "
                     "WHERE p.start_date <= $1 AND p.end_date >= $1 LIMIT 1"),
                parameters=parameters,
                explanation="Count promotions whose recorded start and end dates include the server's current date.",
            )
        if match.promotion_metric == "promotion_revenue":
            return QueryPlan(
                sql=("SELECT p.promo_id, p.promo_name, "
                     "SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS revenue "
                     "FROM commerce.order_items AS oi "
                     "JOIN commerce.promotions AS p ON p.promo_id = oi.promo_id "
                     "WHERE oi.promo_id IS NOT NULL AND oi.promo_id_2 IS NULL "
                     "AND oi.quantity IS NOT NULL AND oi.unit_price IS NOT NULL "
                     "AND oi.discount_amount IS NOT NULL "
                     "GROUP BY p.promo_id, p.promo_name "
                     "ORDER BY revenue DESC, p.promo_id LIMIT " + str(match.limit or 10)),
                parameters=(),
                explanation="Rank promotions by recorded net item revenue, without double-attributing lines with a second promotion.",
            )
    if match.compiler == CompilerKind.DIRECT_FIELD and match.direct_contract is not None:
        return compile_field_query(match.direct_contract)
    raise ValueError(f"Cannot compile unmatched or unsupported request: {match.compiler!r}")


def compile_fixed_query(match: FixedQueryMatch, *, dashboard_build: bool = False) -> CompilationSelection:
    """Compile a prior fixed match; dashboard mode retains its existing model output path."""
    plan = _compile_fixed_match(match) if match.matched and not dashboard_build else None
    return CompilationSelection(
        compiler=match.compiler,
        plan=plan,
        metric_names=match.metric_names,
        promotion_metric=match.promotion_metric,
        direct_contract=match.direct_contract,
        explicit_order_item_formula=match.explicit_order_item_formula,
    )


def compile_inventory_mapping(
    mapping: MetricMapping,
    inventory_compiler: Callable[[MetricMapping], tuple[str, tuple[Any, ...]]] = compile_inventory_query,
) -> CompilationSelection:
    """Adapt a validated inventory interpretation at the later, specialized stage."""
    if mapping.domain != "inventory":
        return CompilationSelection()
    sql, parameters = inventory_compiler(mapping)
    plan = QueryPlan(sql=sql, parameters=parameters,
                     explanation="Compiled from the validated inventory interpretation.")
    return CompilationSelection(
        compiler=CompilerKind.INVENTORY_MAPPING,
        plan=plan,
        metric_names=frozenset(mapping.metrics),
    )


# Compatibility wrappers for existing focused callers that assert the legacy plans.
def _annual_revenue_plan(question: str, metric_names: set[str], today: date | None = None):
    parameters = _annual_revenue_match(question, frozenset(metric_names), today)
    if parameters is None:
        return None
    return _compile_fixed_match(FixedQueryMatch(CompilerKind.ANNUAL_REVENUE,
                                                metric_names=frozenset(metric_names), parameters=parameters))


def _completed_months_revenue_plan(question: str, metric_names: set[str], today: date | None = None):
    parameters = _completed_months_revenue_match(question, frozenset(metric_names), today)
    if parameters is None:
        return None
    return _compile_fixed_match(FixedQueryMatch(CompilerKind.COMPLETED_MONTHS_REVENUE,
                                                metric_names=frozenset(metric_names), parameters=parameters))


def _explicit_month_revenue_plan(question: str, metric_names: set[str], today: date | None = None):
    parameters = _explicit_month_revenue_match(question, frozenset(metric_names), today)
    if parameters is None:
        return None
    return _compile_fixed_match(FixedQueryMatch(CompilerKind.EXPLICIT_MONTH_REVENUE,
                                                metric_names=frozenset(metric_names), parameters=parameters))


def _month_over_month_revenue_plan(question: str, metric_names: set[str], today: date | None = None):
    parameters = _month_over_month_revenue_match(question, frozenset(metric_names), today)
    if parameters is None:
        return None
    return _compile_fixed_match(FixedQueryMatch(CompilerKind.MONTH_OVER_MONTH_REVENUE,
                                                metric_names=frozenset(metric_names), parameters=parameters))


def _promotion_query_plan(question: str, today: date | None = None):
    match = _promotion_match(question, today)
    if match is None:
        return None, None
    return _compile_fixed_match(match), match.promotion_metric
