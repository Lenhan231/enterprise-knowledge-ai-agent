"""Context-aware task decomposition; rules are only a narrow outage fallback."""
import json
import re

from core.agents.runtime import generate
from core.models.agent_plan import AgentPlan
from core.prompts.agents import PLANNING_PROMPT, PLANNING_REPAIR_PROMPT


async def plan_request(request, provider, *, history=(), previous=None, report_headings=None):
    from core.analytics.text_to_sql import APPROVED_COLUMNS
    data = {'question': request.question, 'history': history, 'previous': previous,
            'available_sql_schema': {table: sorted(columns) for table, columns in APPROVED_COLUMNS.items()}}
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
        sql_only = intent.intent == 'analytics' and any(
            term in text for term in ('how many orders', 'list products', 'bao nhiêu đơn hàng'))
        if policy_only or sql_only:
            return AgentPlan(objective=request.question, fallback=True, tasks=[{
                'id': 'fallback', 'agent': 'knowledge' if policy_only else 'sql', 'question': request.question}])
    raise ValueError('Automatic task planning is temporarily unavailable; please retry or select a specialist mode.')
