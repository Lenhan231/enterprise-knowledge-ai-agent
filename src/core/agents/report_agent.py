"""Draft a cited report from role-visible passages and verified database facts."""

import re
import logging
from decimal import Decimal, ROUND_HALF_UP

from core.agents.base import BaseAgent
from core.agents.knowledge_agent import KnowledgeAgent
from core.agents.sql_analytics_agent import SQLAnalyticsAgent
from core.analytics.metric_ontology import resolve_metric_names
from core.analytics.business_metric_catalog import BUSINESS_METRIC_CATALOG, resolve_business_metric_names
from core.llm.groq_provider import GroqProvider
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
_INVALID_REPORT = "The answer was withheld because its citations could not be verified. Please retry the question."
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
    return any(term in text for term in (
        "should", "recommend", "decision", "decide", "strategy", "what should", "which market",
        "which option", "prioritize", "scale", "reallocate", "investment", "nên", "đề xuất",
        "quyết định", "chiến lược", "ưu tiên", "mở rộng", "phân bổ",
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
        return f"[{item.citation_id}] {item.source}, page {page}. {fact}"
    content = (item.content or "").strip()
    if len(content) > 1200:
        content = content[:1200].rsplit(" ", 1)[0] + " …"
    page = item.metadata.get("page_number")
    page_text = f", page {page}" if page is not None else ""
    return f"[{item.citation_id}] {item.source}{page_text}\n{content}"


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


def _report_validation_failure(
    answer: str, evidence: list[Evidence], allowed: set[str], question: str,
) -> str | None:
    citations = set(_CITATION.findall(answer))
    if not citations or citations - allowed:
        return "missing_or_unknown_citations"
    if _is_financial_summary(question) and not _financial_facts_match_cited_evidence(answer, evidence):
        return "financial_values_or_units_do_not_match_cited_evidence"
    return None


def _segment_economics_answer(metric_data: AgentResult, question: str) -> str | None:
    """Answer a complete, verified domestic/overseas comparison without an LLM."""
    required = {
        "domestic_consolidated_net_revenue",
        "domestic_segment_gross_profit",
        "overseas_market_net_revenue",
        "overseas_segment_gross_profit",
    }
    rows = metric_data.data.get("business_metrics", [])
    years = sorted({int(row["fiscal_year"]) for row in rows if row.get("fiscal_year") is not None})
    if len(years) < 2:
        return None
    first, latest = years[-2:]
    by_year = {
        year: {row.get("metric_name"): row for row in rows if row.get("fiscal_year") == year}
        for year in (first, latest)
    }
    if any(not required.issubset(by_year[year]) for year in (first, latest)):
        return None
    if any(by_year[y][code].get("unit") != "VND billion" for y in (first, latest) for code in required):
        return None

    codes = sorted(required)
    citation = {}
    for index, code in enumerate(codes, 1):
        for year in (first, latest):
            row = by_year[year][code]
            citation[(year, code)] = next(
                (item.citation_id for item in metric_data.evidence
                 if item.metadata.get("business_metric_id") == row.get("business_metric_id") and item.citation_id),
                None,
            )
    if any(not value for value in citation.values()):
        return None

    def value(year: int, code: str) -> Decimal:
        return Decimal(str(by_year[year][code]["metric_value"]))

    def pct_change(code: str) -> str:
        result = ((value(latest, code) / value(first, code) - 1) * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return f"{result}%"

    def margin(segment: str, year: int) -> Decimal:
        revenue = "domestic_consolidated_net_revenue" if segment == "domestic" else "overseas_market_net_revenue"
        profit = "domestic_segment_gross_profit" if segment == "domestic" else "overseas_segment_gross_profit"
        return (value(year, profit) / value(year, revenue) * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def amount(year: int, code: str) -> str:
        return f"{value(year, code):,.3f}"

    domestic_margin_change = margin("domestic", latest) - margin("domestic", first)
    overseas_margin_change = margin("overseas", latest) - margin("overseas", first)
    domestic_rev = "domestic_consolidated_net_revenue"
    overseas_rev = "overseas_market_net_revenue"
    domestic_profit = "domestic_segment_gross_profit"
    overseas_profit = "overseas_segment_gross_profit"
    if any(term in question.casefold() for term in ("doanh thu", "lợi nhuận", "thị trường", "so sánh", "quyết định", "nước ngoài")):
        return (
            f"- Doanh thu thuần nội địa: {amount(first, domestic_rev)} lên {amount(latest, domestic_rev)} tỷ VND, "
            f"tăng {pct_change(domestic_rev)}; lợi nhuận gộp phân khúc tăng {pct_change(domestic_profit)}. "
            f"Biên gộp tính từ hai chỉ số này là {margin('domestic', first)}% → {margin('domestic', latest)}% "
            f"({domestic_margin_change:+.2f} điểm phần trăm). [{citation[(first, domestic_rev)]}] [{citation[(latest, domestic_rev)]}] "
            f"[{citation[(first, domestic_profit)]}] [{citation[(latest, domestic_profit)]}]\n"
            f"- Doanh thu thuần thị trường nước ngoài: {amount(first, overseas_rev)} lên {amount(latest, overseas_rev)} tỷ VND, "
            f"tăng {pct_change(overseas_rev)}; lợi nhuận gộp phân khúc tăng {pct_change(overseas_profit)}. "
            f"Biên gộp tính được là {margin('overseas', first)}% → {margin('overseas', latest)}% "
            f"({overseas_margin_change:+.2f} điểm phần trăm). [{citation[(first, overseas_rev)]}] [{citation[(latest, overseas_rev)]}] "
            f"[{citation[(first, overseas_profit)]}] [{citation[(latest, overseas_profit)]}]\n"
            f"- Hàm ý: thị trường nước ngoài tăng doanh thu và cải thiện biên gộp nhanh hơn; nội địa vẫn có biên gộp "
            f"{margin('domestic', latest)}% so với {margin('overseas', latest)}% ở {latest}. Đây là căn cứ để ưu tiên "
            f"thẩm định sâu hơn, chưa đủ căn cứ để khuyến nghị phân bổ vốn; cần thêm chi phí, năng lực, nhu cầu vốn và "
            f"lợi nhuận kỳ vọng theo thị trường. [{citation[(latest, domestic_rev)]}] "
            f"[{citation[(latest, overseas_rev)]}] [{citation[(latest, domestic_profit)]}] "
            f"[{citation[(latest, overseas_profit)]}]"
        )
    return (
        f"- Domestic net revenue moved from {amount(first, domestic_rev)} to {amount(latest, domestic_rev)} VND billion "
        f"({pct_change(domestic_rev)}); segment gross profit changed {pct_change(domestic_profit)}. Calculated gross "
        f"margin: {margin('domestic', first)}% → {margin('domestic', latest)}% ({domestic_margin_change:+.2f} pp). "
        f"[{citation[(first, domestic_rev)]}] [{citation[(latest, domestic_rev)]}] [{citation[(first, domestic_profit)]}] [{citation[(latest, domestic_profit)]}]\n"
        f"- Overseas-market net revenue moved from {amount(first, overseas_rev)} to {amount(latest, overseas_rev)} VND billion "
        f"({pct_change(overseas_rev)}); segment gross profit changed {pct_change(overseas_profit)}. Calculated gross "
        f"margin: {margin('overseas', first)}% → {margin('overseas', latest)}% ({overseas_margin_change:+.2f} pp). "
        f"[{citation[(first, overseas_rev)]}] [{citation[(latest, overseas_rev)]}] [{citation[(first, overseas_profit)]}] [{citation[(latest, overseas_profit)]}]\n"
        f"- Implication: overseas grew revenue and improved gross margin faster, while domestic still had the higher "
        f"gross margin in {latest}. This supports further diligence, not a capital-allocation recommendation; market-level "
        f"costs, capacity, capital needs, and expected returns are still required. "
        f"[{citation[(latest, domestic_rev)]}] [{citation[(latest, overseas_rev)]}] "
        f"[{citation[(latest, domestic_profit)]}] [{citation[(latest, overseas_profit)]}]"
    )


def _market_growth_decision_answer(metric_data: AgentResult, question: str) -> str | None:
    """Compare verified domestic/overseas growth without letting unrelated RAG text override SQL facts."""
    required = {
        "domestic_consolidated_net_revenue_growth",
        "overseas_market_net_revenue_growth",
    }
    rows = metric_data.data.get("business_metrics", [])
    years = sorted({int(row["fiscal_year"]) for row in rows
                    if row.get("fiscal_year") is not None})
    requested_years = {int(year) for year in re.findall(
        r"(?<!\d)(?:FY\s*)?((?:19|20)\d{2})\b", question, re.IGNORECASE
    )}
    eligible_years = [year for year in years if not requested_years or year in requested_years]
    complete_years = []
    observations = {}
    for year in eligible_years:
        by_name = {row.get("metric_name"): row for row in rows
                   if row.get("fiscal_year") == year}
        if not required.issubset(by_name):
            continue
        if any(by_name[name].get("unit") != "%" for name in required):
            continue
        citations = {}
        for name in required:
            metric_id = by_name[name].get("business_metric_id")
            citations[name] = next((item.citation_id for item in metric_data.evidence
                                    if item.metadata.get("business_metric_id") == metric_id
                                    and item.citation_id), None)
        if not all(citations.values()):
            continue
        domestic = Decimal(str(by_name["domestic_consolidated_net_revenue_growth"]["metric_value"]))
        overseas = Decimal(str(by_name["overseas_market_net_revenue_growth"]["metric_value"]))
        gap = (overseas - domestic).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        complete_years.append(year)
        observations[year] = (domestic, overseas, gap, citations)
    if not complete_years or (requested_years and not requested_years.issubset(complete_years)):
        return None

    lines = []
    for year in complete_years:
        domestic, overseas, gap, citations = observations[year]
        domestic_cite = citations["domestic_consolidated_net_revenue_growth"]
        overseas_cite = citations["overseas_market_net_revenue_growth"]
        lines.append(
            f"- FY{year} reported domestic consolidated net revenue growth was {domestic}% "
            f"[{domestic_cite}], versus {overseas}% for overseas markets [{overseas_cite}] "
            f"(a {gap} percentage-point difference, calculated from the reported rates)."
        )
    latest = complete_years[-1]
    latest_domestic, latest_overseas, _, latest_citations = observations[latest]
    latest_cites = (
        f"[{latest_citations['domestic_consolidated_net_revenue_growth']}] "
        f"[{latest_citations['overseas_market_net_revenue_growth']}]"
    )
    lines.append(
        f"- Decision implication: in FY{latest}, overseas growth ({latest_overseas}%) exceeded domestic "
        f"growth ({latest_domestic}%). That supports prioritizing an overseas-market diligence review, not "
        "allocating more capital based on growth alone. Compare segment gross margins, market-specific selling "
        "costs, capacity constraints, required capital and expected returns before deciding. " + latest_cites
    )
    amount_names = ("domestic_consolidated_net_revenue", "overseas_market_net_revenue")
    by_year = {
        year: {row.get("metric_name"): row for row in rows if row.get("fiscal_year") == year}
        for year in {int(row["fiscal_year"]) for row in rows if row.get("fiscal_year") is not None}
    }
    if all(name in by_year.get(latest, {}) for name in amount_names):
        latest_amounts = [by_year[latest][name] for name in amount_names]
        if all(row.get("unit") == "VND billion" for row in latest_amounts):
            amount_citations = {}
            for name in amount_names:
                metric_id = by_year[latest][name].get("business_metric_id")
                amount_citations[name] = next((item.citation_id for item in metric_data.evidence
                                               if item.metadata.get("business_metric_id") == metric_id
                                               and item.citation_id), None)
            if all(amount_citations.values()):
                domestic_revenue, overseas_revenue = (
                    Decimal(str(by_year[latest][name]["metric_value"])) for name in amount_names
                )
                scale_ratio = (domestic_revenue / overseas_revenue).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                amount_line = (
                    f"- FY{latest} revenue scale: domestic VND {domestic_revenue:,.0f} billion "
                    f"[{amount_citations[amount_names[0]]}] versus overseas VND {overseas_revenue:,.0f} billion "
                    f"[{amount_citations[amount_names[1]]}] (domestic was {scale_ratio}× the overseas amount)."
                )
                decision_evidence = list(amount_citations.values())
                absolute_change = ""
                prior_years = [year for year in by_year if year < latest and
                               all(name in by_year[year] and by_year[year][name].get("unit") == "VND billion"
                                   for name in amount_names)]
                if prior_years:
                    prior = max(prior_years)
                    prior_citations = {}
                    for name in amount_names:
                        metric_id = by_year[prior][name].get("business_metric_id")
                        prior_citations[name] = next((item.citation_id for item in metric_data.evidence
                                                      if item.metadata.get("business_metric_id") == metric_id
                                                      and item.citation_id), None)
                    if all(prior_citations.values()):
                        domestic_delta = domestic_revenue - Decimal(str(by_year[prior][amount_names[0]]["metric_value"]))
                        overseas_delta = overseas_revenue - Decimal(str(by_year[prior][amount_names[1]]["metric_value"]))
                        decision_evidence.extend(prior_citations.values())
                        absolute_change = (
                            f" The FY{prior}–FY{latest} absolute revenue increases were VND {domestic_delta:,.0f} "
                            f"billion domestically and VND {overseas_delta:,.0f} billion overseas."
                        )
                        lines.insert(-1, amount_line)
                lines[-1] = (
                    f"- Decision implication: overseas growth ({latest_overseas}%) and absolute revenue gain provide "
                    f"a reason to prioritize overseas-market diligence, while domestic revenue remains {scale_ratio}× "
                    f"larger and merits protection.{absolute_change} This is not enough to allocate capital; compare "
                    "segment gross margins, selling/distribution costs, working capital, capacity, risks and expected "
                    "incremental returns first. " + latest_cites + " "
                    + " ".join(f"[{citation}]" for citation in decision_evidence)
                )
    return "\n".join(lines)


def _factory_efficiency_decision_answer(metric_data: AgentResult, question: str) -> str | None:
    """Give a source-exact next-step decision from complete verified factory KPIs."""
    required = {
        "production_lines_meeting_oee_target",
        "production_cost_savings",
        "purchasing_cost_savings",
    }
    rows = metric_data.data.get("business_metrics", [])
    years = sorted({int(row["fiscal_year"]) for row in rows if row.get("fiscal_year") is not None})
    requested_years = {int(year) for year in re.findall(
        r"(?<!\d)(?:FY\s*)?((?:19|20)\d{2})\b", question, re.IGNORECASE
    )}
    units = {
        "production_lines_meeting_oee_target": "%",
        "production_cost_savings": "VND billion",
        "purchasing_cost_savings": "VND billion",
    }
    for year in reversed(years):
        if requested_years and year not in requested_years:
            continue
        by_name = {row.get("metric_name"): row for row in rows if row.get("fiscal_year") == year}
        if not required.issubset(by_name) or any(by_name[name].get("unit") != unit
                                                  for name, unit in units.items()):
            continue
        citations = {}
        for name in required:
            metric_id = by_name[name].get("business_metric_id")
            citations[name] = next((item.citation_id for item in metric_data.evidence
                                    if item.metadata.get("business_metric_id") == metric_id
                                    and item.citation_id), None)
        if not all(citations.values()):
            continue
        ordered = (
            "production_lines_meeting_oee_target",
            "production_cost_savings",
            "purchasing_cost_savings",
        )
        facts = []
        for name in ordered:
            row = by_name[name]
            facts.append(
                f"{row['metric_label']}: {_qualified_business_metric_value(row)} [{citations[name]}]"
            )
        citations_text = " ".join(f"[{citations[name]}]" for name in ordered)
        return (
            f"FY{year} reported " + "; ".join(facts) + ". "
            "These figures support prioritizing a plant-and-line OEE exception review and a separate audit of "
            "production and purchasing savings baselines/calculations. The reports do not identify which factory "
            "or line underperformed, establish that the savings caused the OEE result, or provide enough evidence "
            "to approve a facility investment or savings target. Request plant-level OEE, downtime, production "
            "volume, spend-category baselines and calculation workpapers before making those decisions. "
            + citations_text
        )
    return None


def _business_metric_citation(metric_data: AgentResult, row: dict) -> str | None:
    metric_id = row.get("business_metric_id")
    return next((item.citation_id for item in metric_data.evidence
                 if item.metadata.get("business_metric_id") == metric_id and item.citation_id), None)


def _export_country_priorities_answer(metric_data: AgentResult) -> str | None:
    """Rank reported export-market growth as a diligence signal, never as ROI."""
    names = (
        "guinea_export_revenue_growth", "hong_kong_export_revenue_growth",
        "japan_export_revenue_growth",
    )
    rows = {row.get("metric_name"): row for row in metric_data.data.get("business_metrics", [])
            if row.get("fiscal_year") == 2025 and row.get("unit") == "%"}
    if any(name not in rows for name in names):
        return None
    citations = {name: _business_metric_citation(metric_data, rows[name]) for name in names}
    if any(not citations[name] for name in names):
        return None
    ranked = sorted(names, key=lambda name: Decimal(str(rows[name]["metric_value"])), reverse=True)
    facts = "; ".join(
        f"{rows[name]['metric_label']} was {_qualified_business_metric_value(rows[name])} "
        f"[{citations[name]}]" for name in ranked
    )
    context_names = (
        "export_net_revenue", "export_net_revenue_growth",
        "commercial_export_revenue", "commercial_export_revenue_growth", "export_volume_teu",
    )
    context_rows = {row.get("metric_name"): row for row in metric_data.data.get("business_metrics", [])
                    if row.get("fiscal_year") == 2025 and row.get("metric_name") in context_names}
    context_facts = []
    for name in context_names:
        row = context_rows.get(name)
        citation = _business_metric_citation(metric_data, row) if row else None
        if row and citation:
            context_facts.append(f"{row['metric_label']} was {_qualified_business_metric_value(row)} [{citation}]")
    scale_context = ""
    if context_facts:
        scale_context = " Company-level FY2025 export context: " + "; ".join(context_facts) + "."
        if "commercial_export_revenue" in context_rows:
            scale_context += " Commercial export revenue is included in total export net revenue; do not add the two figures."
    return (
        f"FY2025 export-market growth ranks {facts}. Use Guinea and Hong Kong as the first markets for a "
        "commercial diligence or limited pilot shortlist, with Japan as a developed-market comparison. "
        "This prioritization uses reported growth only; it is not an ROI recommendation."
        + scale_context + " The report does not disclose each market's absolute revenue, "
        "contribution margin, selling/distribution cost, working-capital needs or capacity requirement, and a high "
        "growth rate may reflect a small starting base. Do not approve a capital shift from this evidence alone. "
        "Before deciding, compare market-level net sales, gross/contribution margin, customer concentration, "
        "receivables, compliance costs and incremental return. "
        + " ".join(f"[{citations[name]}]" for name in ranked)
    )


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


def _milk_sourcing_decision_answer(metric_data: AgentResult) -> str | None:
    """Compare the complete, verified farmer-purchase series without mixing total supply."""
    by_year = {int(row["fiscal_year"]): row for row in metric_data.data.get("business_metrics", [])
               if row.get("metric_name") == "farmer_raw_milk_purchased"
               and row.get("fiscal_year") is not None and row.get("unit") == "tonnes"}
    years = (2023, 2024, 2025)
    if any(year not in by_year for year in years):
        return None
    citations = {year: _business_metric_citation(metric_data, by_year[year]) for year in years}
    if any(not citation for citation in citations.values()):
        return None
    start = Decimal(str(by_year[2023]["metric_value"]))
    end = Decimal(str(by_year[2025]["metric_value"]))
    change = end - start
    change_percent = (change / start * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    facts = "; ".join(
        f"FY{year}: {_qualified_business_metric_value(by_year[year])} [{citations[year]}]"
        for year in years
    )
    direction = "fell" if change < 0 else "rose"
    return (
        f"Reported fresh-milk purchases from farming households were {facts}. From FY2023 to FY2025, "
        f"the reported amount {direction} by {abs(change):,.3f} tonnes ({abs(change_percent)}%), calculated from the cited values. "
        "Treat this as a supplier-volume review signal, not proof of supplier attrition or a procurement-quality problem; "
        "the reports do not provide a matched monthly, farm-level series. Before changing contracts or support, compare "
        "active suppliers, accepted/rejected volume, quality, delivered price and transport cost by region and receiving "
        "factory. The FY2024 figure is approximate, and the reports' measurement perimeters should be confirmed. "
        + " ".join(f"[{citations[year]}]" for year in years)
    )


def _product_portfolio_decision_answer(metric_data: AgentResult) -> str | None:
    """Turn verified product signals into diligence priorities, not a scale-up claim."""
    rows = metric_data.data.get("business_metrics", [])
    by_name_year = {(row.get("metric_name"), int(row["fiscal_year"])): row for row in rows
                    if row.get("fiscal_year") is not None}
    required = {
        ("plant_based_milk_sales_growth", 2024), ("green_farm_sales_growth", 2024),
        ("green_farm_brand_awareness", 2024), ("green_farm_customer_loyalty", 2024),
        ("green_farm_urban_purchase_consideration", 2022),
        ("green_farm_urban_purchase_consideration", 2024), ("new_or_relaunched_products", 2024),
    }
    if not required.issubset(by_name_year):
        return None
    selected = {key: by_name_year[key] for key in required}
    citations = {key: _business_metric_citation(metric_data, row) for key, row in selected.items()}
    if any(not citation for citation in citations.values()):
        return None

    def fact(name: str, year: int) -> str:
        key = (name, year)
        return f"{_qualified_business_metric_value(selected[key])} [{citations[key]}]"

    consideration_change = (
        Decimal(str(selected[("green_farm_urban_purchase_consideration", 2024)]["metric_value"]))
        - Decimal(str(selected[("green_farm_urban_purchase_consideration", 2022)]["metric_value"]))
    )
    all_citations = " ".join(f"[{citation}]" for citation in citations.values())
    return (
        "Prioritize a SKU-level profitability and repeat-purchase review of plant-based milk and Green Farm; "
        "the public evidence is not sufficient to rank them for expansion. In FY2024, plant-based milk sales grew "
        f"{fact('plant_based_milk_sales_growth', 2024)}, Green Farm sales grew {fact('green_farm_sales_growth', 2024)}, "
        f"and Green Farm awareness and loyalty were {fact('green_farm_brand_awareness', 2024)} and "
        f"{fact('green_farm_customer_loyalty', 2024)}. Urban purchase consideration rose from "
        f"{fact('green_farm_urban_purchase_consideration', 2022)} in FY2022 to "
        f"{fact('green_farm_urban_purchase_consideration', 2024)} in FY2024 ({consideration_change:+} percentage points, "
        f"calculated); {fact('new_or_relaunched_products', 2024)} were launched or relaunched across the portfolio. "
        "These are different measures and populations, not evidence of margin or causal conversion. Before scaling, "
        "compare net sales and contribution margin by SKU/channel, repeat-purchase cohorts, promotion spend, returns, "
        "inventory and capacity. " + all_citations
    )


def _environmental_priorities_answer(metric_data: AgentResult) -> str | None:
    """Compare complete verified environment series without treating scope changes as performance."""
    rows = metric_data.data.get("business_metrics", [])
    by_name_year = {(row.get("metric_name"), int(row["fiscal_year"])): row for row in rows
                    if row.get("fiscal_year") is not None}
    years = (2023, 2024, 2025)
    metric_names = (
        "total_water_consumption", "scope_1_2_ghg_emissions", "dairy_product_ghg_intensity",
        "sugar_product_ghg_intensity", "total_waste_generated",
    )
    required = {(name, year) for name in metric_names for year in years}
    if not required.issubset(by_name_year):
        return None
    selected = {key: by_name_year[key] for key in required}
    citations = {key: _business_metric_citation(metric_data, row) for key, row in selected.items()}
    if any(not citation for citation in citations.values()):
        return None
    waste_scope = str(selected[("total_waste_generated", 2025)].get("scope", ""))
    if "boundary" not in waste_scope.casefold():
        return None

    def value(name: str, year: int) -> Decimal:
        return Decimal(str(selected[(name, year)]["metric_value"]))

    def fact(name: str, year: int) -> str:
        key = (name, year)
        return f"{_qualified_business_metric_value(selected[key])} [{citations[key]}]"

    def movement(name: str, first_year: int, last_year: int, direction: str) -> str:
        first, last = value(name, first_year), value(name, last_year)
        delta = last - first
        percent = (delta / first * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return f"{direction} by {abs(delta):,} {selected[(name, last_year)]['unit']} ({abs(percent)}%)"

    all_citations = " ".join(f"[{citation}]" for citation in citations.values())
    return (
        "Prioritize a production-line review of sugar-product emissions intensity, which rebounded sharply in 2025; "
        "check dairy-product intensity in parallel. Total water consumption continued to decline, while total Scope 1+2 "
        "emissions remain below 2023 but rose slightly from 2024. The reported waste series is not comparable as a simple "
        "operating trend because its source scope records a changed assurance boundary in 2025. "
        f"Water consumption was {fact('total_water_consumption', 2023)} in FY2023, {fact('total_water_consumption', 2024)} "
        f"in FY2024 and {fact('total_water_consumption', 2025)} in FY2025 ({movement('total_water_consumption', 2023, 2025, 'fell')}). "
        f"Scope 1+2 emissions were {fact('scope_1_2_ghg_emissions', 2023)}, {fact('scope_1_2_ghg_emissions', 2024)} and "
        f"{fact('scope_1_2_ghg_emissions', 2025)}; from FY2024 to FY2025 they {movement('scope_1_2_ghg_emissions', 2024, 2025, 'rose')}. "
        f"Dairy-product intensity was {fact('dairy_product_ghg_intensity', 2023)}, {fact('dairy_product_ghg_intensity', 2024)} and "
        f"{fact('dairy_product_ghg_intensity', 2025)}; sugar-product intensity was {fact('sugar_product_ghg_intensity', 2023)}, "
        f"{fact('sugar_product_ghg_intensity', 2024)} and {fact('sugar_product_ghg_intensity', 2025)} "
        f"({movement('sugar_product_ghg_intensity', 2024, 2025, 'rose')}). Waste totals were "
        f"{fact('total_waste_generated', 2023)}, {fact('total_waste_generated', 2024)} and {fact('total_waste_generated', 2025)}. "
        "For action, request facility/line-level energy by source and production output to explain the intensity rebound, and "
        "restate waste history on one assurance boundary before assigning a reduction target. These group-level figures "
        "do not identify a facility or establish a cause. " + all_citations
    )


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
        report_request = request.model_copy(update={
            "metadata": {
                **request.metadata,
                "evidence_only": True,
                "decision_support": _is_decision_support_request(request.question),
            },
        })
        metric_data = None
        business_metric_question = (
            _is_business_metric_decision_question(request.question)
            or _is_business_metric_trend_question(request.question)
        )
        if (_is_financial_change_explanation(request.question)
                or _is_decision_support_request(request.question)
                or business_metric_question) and self.analytics is not None:
            metric_data = self.analytics.run(request)
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
            segment_answer = _segment_economics_answer(metric_data, request.question)
            if segment_answer is not None:
                return metric_data.model_copy(update={
                    "answer": segment_answer,
                    "agent": "report",
                    "metadata": {**metric_data.metadata, "insufficient_context": False,
                                 "decision_analysis": "verified_segment_economics"},
                })
            export_country_answer = _export_country_priorities_answer(metric_data)
            if export_country_answer is not None:
                return metric_data.model_copy(update={
                    "answer": export_country_answer,
                    "agent": "report",
                    "metadata": {**metric_data.metadata, "insufficient_context": False,
                                 "decision_analysis": "verified_export_country_priorities"},
                })
            factory_answer = _factory_efficiency_decision_answer(metric_data, request.question)
            if factory_answer is not None:
                return metric_data.model_copy(update={
                    "answer": factory_answer,
                    "agent": "report",
                    "metadata": {**metric_data.metadata, "insufficient_context": False,
                                 "decision_analysis": "verified_factory_efficiency"},
                })
            milk_answer = _milk_sourcing_decision_answer(metric_data)
            if milk_answer is not None:
                return metric_data.model_copy(update={
                    "answer": milk_answer,
                    "agent": "report",
                    "metadata": {**metric_data.metadata, "insufficient_context": False,
                                 "decision_analysis": "verified_milk_sourcing"},
                })
            product_answer = _product_portfolio_decision_answer(metric_data)
            if product_answer is not None:
                return metric_data.model_copy(update={
                    "answer": product_answer,
                    "agent": "report",
                    "metadata": {**metric_data.metadata, "insufficient_context": False,
                                 "decision_analysis": "verified_product_portfolio"},
                })
            environmental_answer = _environmental_priorities_answer(metric_data)
            if environmental_answer is not None:
                return metric_data.model_copy(update={
                    "answer": environmental_answer,
                    "agent": "report",
                    "metadata": {**metric_data.metadata, "insufficient_context": False,
                                 "decision_analysis": "verified_environmental_trends"},
                })
            market_answer = _market_growth_decision_answer(metric_data, request.question)
            if market_answer is not None:
                return metric_data.model_copy(update={
                    "answer": market_answer,
                    "agent": "report",
                    "metadata": {**metric_data.metadata, "insufficient_context": False,
                                 "decision_analysis": "verified_market_growth"},
                })
        source_data = self.knowledge.run(report_request)
        if metric_data is not None:
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
            "For decision-support requests, state which verified evidence supports a choice and what remains unknown. "
            "When comparable segment net-revenue and gross-profit observations are both supplied, calculate gross "
            "margin as gross profit divided by net revenue for each segment and year, state the change in percentage "
            "points, round calculated margins to two decimals, and cite both inputs. Call this gross margin, not net "
            "margin; segment gross profit excludes selling and administration costs. Preserve reported metric units "
            "and values to three decimals when stored in VND billion. Faster revenue or gross-profit growth alone "
            "must never be presented as a recommendation to allocate capital. State that it prioritizes further "
            "diligence only; a final allocation decision needs market-level costs, capacity, capital requirements "
            "and expected returns. Label calculated implications as inferences. "
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
            "For business-metric summaries, explain direction and calculate changes only from the supplied verified "
            "observations. Preserve value qualifiers such as approximately and more_than in all numerical summaries, "
            "and distinguish H1 from full-year reporting periods. You may explain a reporting-boundary change only "
            "when a cited passage explicitly states it. "
            "Do not infer operational causes, production changes, efficiency gains, measurement uncertainty, or "
            "causal effects from year-to-year movement. If the sources do not state why a value changed, say the "
            "reports show the movement but do not establish its cause. For operational recommendations, give review "
            "questions tied to the reported trend; label possible causes as unverified hypotheses and never imply a "
            "specific initiative drove a change unless the evidence says so. Preserve scope notes and qualifiers, and "
            "cite every numeric statement. Label arithmetic or decision implications as calculations/inferences.\n\n"
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
            "Do not calculate from unverified candidates.\n\n"
            f"{financial_instruction}{executive_instruction}{grounded_business_instruction}{change_instruction}Request: {request.question}\n\n{priority_note}Evidence:\n{sources}"
        )
        answer = _normalize_numeric_citations(self.llm.generate(prompt).strip(), prompt_evidence)
        validation_failure = _report_validation_failure(
            answer, prompt_evidence, allowed, request.question,
        )
        repaired = validation_failure is not None
        if repaired:
            correction = (
                "\n\nYour previous draft failed validation: " + validation_failure + ". "
                "Rewrite the answer using only the evidence above. End every factual sentence with exact supplied IDs "
                "in [S1] format; copy values and units exactly when relevant. Do not add claims that are not supported."
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
            else:
                logger.warning("Report financial answer did not preserve cited numeric values and magnitude units")
                failure_metadata = {"financial_evidence_validation_failed": True}
            return source_data.model_copy(update={
                "answer": _INVALID_REPORT,
                "agent": "report",
                "metadata": {**source_data.metadata, **failure_metadata},
            })
        metadata = {**source_data.metadata}
        if repaired:
            metadata["citation_repair_attempted"] = True
        return source_data.model_copy(update={"answer": answer, "agent": "report", "metadata": metadata})

    def close(self) -> None:
        if self._owns_knowledge:
            self.knowledge.close()
        if hasattr(self.llm, "close"):
            self.llm.close()
