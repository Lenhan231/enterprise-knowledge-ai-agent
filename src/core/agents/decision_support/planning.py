"""Context-aware task decomposition; rules are only a narrow outage fallback."""
import json
import re
from datetime import date

from core.agents.runtime import generate, generate_with_local_codex
from core.models.agent_plan import AgentPlan
from core.prompts.agents import PLANNING_PROMPT, PLANNING_REPAIR_PROMPT


async def plan_request(request, provider, *, history=(), previous=None, report_headings=None, sql_schema=None):
    from core.agents.intent_classifier import IntentClassifier, is_product_profit_recommendation
    intent = IntentClassifier.fallback(request.question)
    if not history and previous is None and report_headings is None:
        unresolved_reference = bool(re.search(
            r'\b(that|the other one|this one|those|them)\b|cái đó|cái còn lại|cái kia',
            request.question, re.I,
        ))
        if (intent.intent == 'analytics' and intent.needs_sql and not intent.needs_knowledge
                and not unresolved_reference):
            return AgentPlan(objective=request.question, fallback=True, tasks=[{
                'id': 'fallback', 'agent': 'sql', 'question': request.question}])
    from core.analytics.text_to_sql import APPROVED_COLUMNS
    latest_turn = history[-1] if history else {}
    latest_metrics = next((turn.get('metrics') for turn in reversed(history) if turn.get('metrics')), '')
    data = {'question': request.question, 'current_date': date.today().isoformat(),
            'history': history, 'previous': previous,
            'follow_up_context': {
                'prior_resolved_scope': latest_turn.get('scope') or latest_turn.get('question'),
                'prior_confirmed_sql_metrics': latest_metrics,
            },
            'available_sql_schema': {table: sorted(columns) for table, columns in (APPROVED_COLUMNS if sql_schema is None else sql_schema).items()}}
    if report_headings is not None:
        data['report_headings'] = report_headings
    prompt = PLANNING_PROMPT.format(workflow='report_sources' if report_headings is not None else 'chat',
                                    data=json.dumps(data, ensure_ascii=False, default=str))
    for attempt in range(2):
        try:
            try:
                raw = await generate(provider, prompt)
            except Exception as provider_error:
                raw = await generate_with_local_codex(prompt, provider_error)
            if not isinstance(raw, str) or len(raw) > 24_000:
                raise ValueError('Invalid plan size')
            payload = json.loads(raw.strip().removeprefix('```json').removesuffix('```').strip())
            if isinstance(payload, dict) and payload.get('clarification'):
                payload.setdefault('objective', latest_turn.get('scope') or request.question)
                payload.setdefault('tasks', [])
            if previous and not payload.get('clarification'):
                completed = {outcome['id'] for outcome in previous['outcomes'] if outcome['status'] == 'complete'}
                trusted = AgentPlan.model_validate(previous['plan'])
                payload['tasks'] = [task.model_dump() for task in trusted.tasks if task.id in completed] + [
                    task for task in payload.get('tasks', []) if task.get('id') not in completed]
            result = AgentPlan.model_validate(payload)
            if is_product_profit_recommendation(request.question) and not result.clarification:
                present = {task.agent for task in result.tasks}
                tasks = [task.model_dump() for task in result.tasks]
                for agent, prefix in (('knowledge', 'k'), ('sql', 's')):
                    if agent not in present:
                        task_id = prefix
                        suffix = 2
                        while any(task['id'] == task_id for task in tasks):
                            task_id = f'{prefix}{suffix}'
                            suffix += 1
                        tasks.append({'id': task_id, 'agent': agent, 'question': request.question})
                result = AgentPlan(objective=result.objective, fallback=result.fallback, tasks=tasks)
            return result
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
