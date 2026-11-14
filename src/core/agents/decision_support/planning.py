"""Context-aware task decomposition; rules are only a narrow outage fallback."""
import json
import re
from datetime import date

from core.agents.runtime import generate
from core.models.agent_plan import AgentPlan, AgentTask
from core.prompts.agents import PLANNING_PROMPT, PLANNING_REPAIR_PROMPT


def _revenue_month_followup(question, history):
    if not re.fullmatch(r'\s*(?:(?:vậy|còn)\s+)?(?:tháng trước(?: thì sao)?|last month|previous month)\s*[?!.]*\s*',
                        question, re.I):
        return None
    from core.analytics.metric_ontology import resolve_metric_names

    for turn in reversed(history):
        scope = turn.get('scope') or turn.get('question') or ''
        if resolve_metric_names(scope) != {'revenue'}:
            continue
        match = re.search(r'\btháng\s+(0?[1-9]|1[0-2])(?:\s+năm\s+((?:19|20)\d{2}))?\b', scope, re.I)
        if not match:
            return None
        year, month = int(match.group(2) or date.today().year), int(match.group(1))
        month -= 1
        if month == 0:
            month, year = 12, year - 1
        return f'doanh thu tháng {month} năm {year}'
    return None


async def plan_request(request, provider, *, history=(), previous=None, report_headings=None, sql_schema=None):
    resolved_followup = (_revenue_month_followup(request.question, history)
                         if previous is None and report_headings is None else None)
    if resolved_followup:
        return AgentPlan(objective=resolved_followup, tasks=[
            AgentTask(id='sql', agent='sql', question=resolved_followup)])
    if not history and previous is None and report_headings is None:
        from core.agents.intent_classifier import IntentClassifier
        intent = IntentClassifier.fallback(request.question)
        if intent.intent == 'analytics' and intent.needs_sql and not intent.needs_knowledge:
            return AgentPlan(objective=request.question, fallback=True, tasks=[{
                'id': 'fallback', 'agent': 'sql', 'question': request.question}])
    from core.analytics.text_to_sql import APPROVED_COLUMNS
    data = {'question': request.question, 'history': history, 'previous': previous,
            'available_sql_schema': {table: sorted(columns) for table, columns in (APPROVED_COLUMNS if sql_schema is None else sql_schema).items()}}
    if report_headings is not None:
        data['report_headings'] = report_headings
    prompt = PLANNING_PROMPT.format(workflow='report_sources' if report_headings is not None else 'chat',
                                    data=json.dumps(data, ensure_ascii=False, default=str))
    for attempt in range(2):
        try:
            raw = await generate(provider, prompt)
            if not isinstance(raw, str) or len(raw) > 24_000:
                raise ValueError('Invalid plan size')
            payload = json.loads(raw.strip().removeprefix('```json').removesuffix('```').strip())
            if previous and not payload.get('clarification'):
                completed = {outcome['id'] for outcome in previous['outcomes'] if outcome['status'] == 'complete'}
                trusted = AgentPlan.model_validate(previous['plan'])
                payload['tasks'] = [task.model_dump() for task in trusted.tasks if task.id in completed] + [
                    task for task in payload.get('tasks', []) if task.get('id') not in completed]
            return AgentPlan.model_validate(payload)
        except PermissionError:
            raise
        except Exception:
            if attempt == 0:
                prompt += PLANNING_REPAIR_PROMPT
    if not history and previous is None:
        from core.agents.intent_classifier import IntentClassifier
        intent = IntentClassifier.fallback(request.question)
        # Broad analytics/comparison and mixed keywords do not prove safe decomposition.
        text = request.question.casefold()
        mixed_cues = re.search(r'\b(count|compare|sales|revenue|orders|total|average|trend|how many|number of)\b', text)
        mixed_cues = mixed_cues or any(term in text for term in ('so sánh', 'đếm', 'bao nhiêu', 'doanh thu', 'đơn hàng'))
        policy_only = not mixed_cues and intent.intent == 'knowledge' and any(
            term in text for term in ('policy', 'procedure', 'chính sách', 'quy trình'))
        # A single analytics request needs no task decomposition. Let the SQL
        # agent apply its own ambiguity and metric safeguards during an outage.
        if policy_only:
            return AgentPlan(objective=request.question, fallback=True, tasks=[{
                'id': 'fallback', 'agent': 'knowledge', 'question': request.question}])
    raise ValueError('Automatic task planning is temporarily unavailable; please retry or select a specialist mode.')
