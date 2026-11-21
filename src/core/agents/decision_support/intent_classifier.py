import json
import math
import os
import re
import urllib.request

from core.agents.sql.metric_ontology import resolve_metric_names
from core.agents.sql.invoices import is_invoice_question
from core.llm.groq_provider import GroqProvider
from core.models.intent import IntentResult
from core.prompts.intent import INTENT_CLASSIFIER_PROMPT


JEV_ROUTE_THRESHOLD = 0.5
JEV_HISTORY_THRESHOLD = 0.8
JEV_ROUTES = {'knowledge', 'sql', 'plan_required'}
JEV_TABLE_LIMIT = 5
SQL_SCHEMA_SELECTION_MODEL = 'perplexity/pplx-decider-flash-v1.3:free'


def classify_jev_route(question: str, approved_schema=None, history=()):
    """Classify tool routing with Jev; callers may fall back to planner on service errors."""
    api_key = os.getenv('OPENROUTER_API_KEY', '').strip()
    if not api_key:
        raise RuntimeError('OPENROUTER_API_KEY is not configured')
    schema = {table: sorted(columns) for table, columns in (approved_schema or {}).items()}
    request_body = json.dumps({
        'model': 'typesafe/jev-1.14',
        'state': {
            'question': question,
            'history': list(history)[-5:],
            'available_tools': {
                'knowledge': 'Search authorized enterprise documents for policies and factual explanations.',
                'sql': 'Run read-only queries against the approved structured commerce schema.',
            },
            'approved_schema': schema,
        },
        'questions': {
            'knowledge_required': {
                'type': 'choice',
                'instructions': ('Decide independently whether searching authorized enterprise documents is needed '
                                 'to answer the current request. Select yes when policy, operating guidance, or '
                                 'document evidence would improve or ground the answer, including a request for a '
                                 'business recommendation or action based on measured results. In those cases, SQL '
                                 'may establish what happened while Knowledge supplies applicable constraints or '
                                 'guidance. Examples include asking which products need replenishment review, which '
                                 'promotion candidate to consider, or what action to take based on sales, margin, '
                                 'inventory, returns or delivery evidence. Select no for a purely descriptive ranking '
                                 'that requests no action, policy or operating guidance. Do not suppress this tool '
                                 'because SQL may also be needed.'),
                'criteria': {
                    'yes': ('Knowledge evidence is needed or useful, especially to ground a requested business '
                            'recommendation, action, or policy-constrained decision; use it alongside SQL when the '
                            'question asks what the business should prioritize or review.'),
                    'no': ('Knowledge evidence is not needed for a purely descriptive calculation, ranking or '
                           'comparison with no requested action or policy interpretation.'),
                },
            },
            'sql_required': {
                'type': 'choice',
                'instructions': ('Decide independently whether querying the approved structured commerce data is '
                                 'needed to answer the current request. Select yes when the user asks about measured '
                                 'business data, comparisons, rankings, counts, or trends. Do not suppress this tool '
                                 'because Knowledge may also be needed.'),
                'criteria': {
                    'yes': 'Read-only SQL evidence is needed or useful for the current request.',
                    'no': 'Structured data evidence is not needed for the current request.',
                },
            },
            'history_required': {
                'type': 'choice',
                'instructions': 'Does the current question need earlier turns to form a complete standalone specialist question?',
                'criteria': {
                    'yes': 'The question is a follow-up whose metric, entity, time scope, or referent depends on history.',
                    'no': 'The current question is self-contained without earlier turns.',
                },
            },
        },
    }, ensure_ascii=False, default=str).encode()
    request = urllib.request.Request(
        'https://openrouter.ai/api/alpha/decisions', data=request_body,
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}, method='POST',
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.loads(response.read())
    answers = payload.get('answers', {})
    knowledge_answer = answers.get('knowledge_required', {})
    sql_answer = answers.get('sql_required', {})
    history_answer = answers.get('history_required', {})
    tool_probabilities = {}
    for tool, answer in (('knowledge', knowledge_answer), ('sql', sql_answer)):
        if not isinstance(answer, dict):
            raise ValueError('Jev returned an invalid tool-routing decision')
        try:
            probability = float(answer.get('probabilities', {}).get('yes', -1))
        except (AttributeError, TypeError, ValueError):
            probability = -1
        if answer.get('type') != 'choice' or not 0 <= probability <= 1:
            raise ValueError('Jev returned an invalid tool-routing decision')
        tool_probabilities[tool] = probability
    selected_tools = [tool for tool, probability in tool_probabilities.items()
                      if probability > JEV_ROUTE_THRESHOLD]
    route = selected_tools[0] if len(selected_tools) == 1 else 'plan_required'
    confidence = tool_probabilities[selected_tools[0]] if len(selected_tools) == 1 else 0.0
    if not isinstance(history_answer, dict):
        raise ValueError('Jev returned an invalid tool-routing decision')
    history_choice = history_answer.get('choice')
    try:
        history_probability = float(history_answer.get('probabilities', {}).get(history_choice, -1))
    except (AttributeError, TypeError, ValueError):
        history_probability = -1
    if (not isinstance(history_answer, dict) or history_answer.get('type') != 'choice'
            or history_choice not in {'yes', 'no'} or not 0 <= history_probability <= 1):
        raise ValueError('Jev returned an invalid tool-routing decision')
    return {'route': route, 'selected_tools': selected_tools, 'confidence': confidence,
            'history_required': not (history_choice == 'no' and history_probability >= JEV_HISTORY_THRESHOLD),
            'model': payload.get('model')}


def select_jev_schema_tables(question, table_columns, metric_definitions=None, *, primary_keys=None,
                             approved_joins=(), limit=JEV_TABLE_LIMIT):
    """Rank schema tables with Jev and add metric sources and approved join bridges."""
    tables = {name: sorted(columns) for name, columns in table_columns.items()}
    if not tables:
        raise ValueError('Cannot select tables from an empty schema')
    api_key = os.getenv('OPENROUTER_API_KEY', '').strip()
    if not api_key:
        raise RuntimeError('OPENROUTER_API_KEY is not configured')
    keys = primary_keys or {}
    joins_by_table = {name: [] for name in tables}
    graph = {name: set() for name in tables}
    for edge in approved_joins:
        (left_table, left_column), (right_table, right_column) = sorted(edge)
        if left_table in tables and right_table in tables:
            joins_by_table[left_table].append(f'{left_table}.{left_column} = {right_table}.{right_column}')
            joins_by_table[right_table].append(f'{right_table}.{right_column} = {left_table}.{left_column}')
            graph[left_table].add(right_table)
            graph[right_table].add(left_table)
    descriptions = {
        name: {'columns': columns, 'primary_key': sorted(keys.get(name, ())),
               'approved_joins': sorted(joins_by_table[name])}
        for name, columns in tables.items()
    }
    metric_context = {
        name: {key: definition.get(key) for key in ('aliases', 'source', 'formula', 'grain', 'unit', 'dimensions')
               if definition.get(key) is not None}
        for name, definition in (metric_definitions or {}).items()
    }
    question_ids = {name: f'table_{index}' for index, name in enumerate(sorted(tables))}
    criteria = [
        'Not relevant to the requested data or a valid join path.',
        'May provide a requested dimension or an approved bridge to a relevant table.',
        'Contains a requested measure or entity and is needed to answer the question.',
    ]
    model = os.getenv('SQL_SCHEMA_SELECTION_MODEL', SQL_SCHEMA_SELECTION_MODEL).strip() or SQL_SCHEMA_SELECTION_MODEL
    request_body = json.dumps({
        'model': model,
        'state': {'question': question, 'canonical_metrics': metric_context, 'schema_tables': descriptions},
        'questions': {
            question_id: {
                'type': 'score',
                'instructions': (f'How relevant is {table} to answering the user question? Consider its columns, '
                                'the requested measure and dimensions, time scope, and approved join relationships. '
                                'Score each table independently; do not assume that a table absent from this schema exists.'),
                'criteria': criteria,
            }
            for table, question_id in question_ids.items()
        },
    }, ensure_ascii=False).encode()
    request = urllib.request.Request(
        'https://openrouter.ai/api/alpha/decisions', data=request_body,
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}, method='POST',
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.loads(response.read())
    answers = payload.get('answers', {})
    ranked = []
    for table, question_id in question_ids.items():
        answer = answers.get(question_id, {})
        score = answer.get('score')
        confidence = answer.get('confidence')
        if (answer.get('type') != 'score' or isinstance(score, bool) or not isinstance(score, (int, float))
                or not math.isfinite(score) or not 0 <= score <= len(criteria) - 1
                or isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(confidence)
                or not 0 <= confidence <= 1):
            raise ValueError('Jev returned an invalid schema-table score')
        ranked.append((float(score), table))
    top_tables = sorted(ranked, key=lambda item: (-item[0], item[1]))[:limit]
    if not top_tables or top_tables[0][0] <= 0:
        raise ValueError('Jev did not identify a relevant schema table')
    candidates = {table for _, table in top_tables}
    required_tables = {table for score, table in top_tables if score > 1}
    metric_sources = {table for definition in (metric_definitions or {}).values()
                      for table in re.findall(r'commerce\.\w+', definition.get('source', ''))
                      if table in tables}
    required_tables.update(metric_sources)
    if not required_tables:
        raise ValueError('Jev did not identify a required schema table')
    selected = set(required_tables)

    # Add the shortest approved bridge for each connected pair; bridge closure can exceed the top-five cap.
    required = sorted(selected)
    for index, start in enumerate(required):
        for target in required[index + 1:]:
            pending = [(start, [start])]
            visited = {start}
            path = None
            while pending:
                current, route = pending.pop(0)
                if current == target:
                    path = route
                    break
                for neighbor in sorted(graph[current] - visited):
                    visited.add(neighbor)
                    pending.append((neighbor, route + [neighbor]))
            if path:
                selected.update(path)
    return {'tables': selected, 'required_tables': required_tables,
            'candidate_tables': candidates}


def _is_document_count_request(text: str) -> bool:
    explicit_count = any(term in text for term in (
        "document count", "document counts", "count of document", "number of document",
        "count documents", "counts by domain", "documents by domain",
        "documents by business domain", "how many reports", "number of reports",
        "count of reports", "reports by year", "annual reports by year",
        "số lượng tài liệu", "thống kê tài liệu", "tài liệu theo lĩnh vực",
        "bao nhiêu báo cáo", "số báo cáo", "báo cáo theo năm",
    ))
    report_count = "report" in text and any(
        term in text for term in ("how many", "number of", "count of", "count the", "bao nhiêu", "số lượng")
    )
    return explicit_count or report_count


def is_product_profit_recommendation(question: str) -> bool:
    text = question.casefold()
    return (
        any(term in text for term in ("product", "products", "sản phẩm"))
        and any(term in text for term in (
            "replenish", "reorder", "promote", "discontinue", "stop selling",
            "nhập thêm", "bổ sung", "quảng bá", "ngừng bán",
        ))
        and any(term in text for term in ("profit", "profitable", "margin", "lợi nhuận", "sinh lời"))
    )


class IntentClassifier:
    def __init__(self, llm: GroqProvider | None = None):
        self.llm = llm or GroqProvider()

    def classify(self, question: str) -> IntentResult:
        fallback = self.fallback(question)
        if fallback.intent == "report" and any(
            term in question.casefold()
            for term in ("why", "reason", "cause", "tại sao", "vì sao", "nguyên nhân")
        ):
            return fallback
        prompt = INTENT_CLASSIFIER_PROMPT.format(
            question=question,
        )

        try:
            raw = self.llm.generate(prompt)
            payload = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
            return self._normalize_data_intent(question, IntentResult.model_validate(payload))
        except Exception:
            return fallback

    @staticmethod
    def fallback(question: str) -> IntentResult:
        text = question.casefold()
        commerce_metrics = resolve_metric_names(text)
        metadata_counts = _is_document_count_request(text)
        structured_lookup = bool(re.search(
            r"(?:sản phẩm|product)\s*(?:mã|id)\s*#?\s*\d+",
            text,
            re.I,
        ))
        years = set(re.findall(r"\b(?:19|20)\d{2}\b", text))
        commerce_summary = (
            {"revenue", "cogs"}.issubset(commerce_metrics)
            and len(years) <= 1
            and not any(term in text for term in (
                "trend", "growth", "compare", "comparison", "versus", " vs ",
                "between", "across years", "by year", "tăng trưởng", "so sánh",
                "qua các năm", "theo năm", "chart", "dashboard", "biểu đồ",
            ))
        )
        why_metric_changed = (
            any(term in text for term in ("why", "reason", "cause", "tại sao", "vì sao", "nguyên nhân"))
            and bool(commerce_metrics)
            and len(years) >= 2
        )
        product_profit_recommendation = is_product_profit_recommendation(question)
        analytics = product_profit_recommendation or is_invoice_question(text) or metadata_counts or structured_lookup or bool(commerce_metrics) or any(
            term in text for term in ("trend", "compare", "growth", "tăng trưởng", "so sánh", "thống kê")
        )
        dashboard = any(term in text for term in (
            "dashboard", "chart", "visualize", "bảng điều khiển", "biểu đồ", "đồ thị",
        ))
        report = not metadata_counts and (
            commerce_summary
            or why_metric_changed
            or any(term in text for term in (
                "summarize", "summarise", "summary of", "tóm tắt", "write a report",
                "draft a report", "generate a report", "prepare a report", "create a report",
                "viết báo cáo", "lập báo cáo", "tạo báo cáo",
            ))
        )
        requires_knowledge = product_profit_recommendation or why_metric_changed or any(term in text for term in (
            "policy", "procedure", "document", "chính sách", "quy trình", "tài liệu",
        ))
        intent = (
            "dashboard" if dashboard else "report" if report else
            "hybrid" if analytics and requires_knowledge else
            "analytics" if analytics else "knowledge"
        )
        return IntentResult(
            intent=intent,
            needs_knowledge=intent in {"knowledge", "hybrid"} or (intent == "report" and requires_knowledge),
            needs_sql=intent in {"analytics", "hybrid", "report"},
            output_mode="dashboard" if dashboard else "answer",
            confidence=0.35,
            reason="Phân loại dự phòng theo quy tắc",
            fallback=True,
        )

    @classmethod
    def _normalize_data_intent(cls, question: str, result: IntentResult) -> IntentResult:
        if _is_document_count_request(question.casefold()) and result.output_mode != "dashboard":
            return result.model_copy(update={
                "intent": "analytics",
                "needs_knowledge": False,
                "needs_sql": True,
                "output_mode": "answer",
            })
        fallback = cls.fallback(question)
        if fallback.intent == "report" and result.output_mode != "dashboard":
            return fallback
        if fallback.intent == "analytics" and result.output_mode != "dashboard":
            return fallback
        if fallback.needs_knowledge and fallback.needs_sql and result.output_mode != "dashboard":
            return result.model_copy(update={"intent": "hybrid", "needs_knowledge": True, "needs_sql": True})
        return result

    def close(self) -> None:
        if hasattr(self.llm, "close"):
            self.llm.close()

if __name__ == "__main__":
    intent_classifier = IntentClassifier()
    question = "Cho tôi xem xu hướng doanh thu trong 5 quý gần nhất"
    print(intent_classifier.classify(question))
    intent_classifier.close()
