"""SQL follow-up state stored alongside a chat conversation."""
import json

from core.agents.sql.metric_mapping import SQLConversationState
from core.agents.sql.query_intent import PendingClarification


def context_from_history(history):
    for turn in reversed(history):
        raw = turn.get('sql_context')
        if raw is None:
            continue
        if not raw:
            return None
        try:
            return SQLConversationState.model_validate_json(raw).model_dump()
        except ValueError:
            return None
    return None


def serialize_context(interpretation):
    if not isinstance(interpretation, dict):
        return ''
    try:
        return SQLConversationState.model_validate(
            {'accepted': interpretation, 'pending': None}).model_dump_json()
    except ValueError:
        return ''


def context_after_execution(execution, history):
    context = next((turn['sql_context'] for turn in reversed(history) if 'sql_context' in turn), '')
    for task in execution.plan.tasks if execution.plan else ():
        outcome = execution.outcomes.get(task.id)
        result = outcome.result if outcome and task.agent == 'sql' else None
        if result and result.data.get('query_status') == 'executed':
            context = serialize_context(result.metadata.get('semantic_interpretation'))
    return context


def pending_from_history(history):
    for turn in reversed(history):
        raw = turn.get('pending_clarification')
        if raw:
            try:
                return PendingClarification.model_validate_json(raw)
            except (TypeError, ValueError):
                return None
    return None


def pending_from_result(result):
    raw = result.metadata.get('pending_clarification')
    if not raw:
        return None
    try:
        if isinstance(raw, dict):
            return PendingClarification.model_validate_json(json.dumps(raw, ensure_ascii=False), strict=True)
        return PendingClarification.model_validate_json(raw, strict=True)
    except (TypeError, ValueError):
        return None


def pending_after_execution(execution):
    for task in execution.plan.tasks if execution.plan else ():
        outcome = execution.outcomes.get(task.id)
        if outcome and outcome.result and task.agent == 'sql':
            pending = pending_from_result(outcome.result)
            if pending is not None:
                return pending
    return None


def record_pending_reply(history, reply, pending):
    history.append({
        'question': reply[:2000], 'scope': pending.original_question[:2000],
        'clarification': pending.clarification_question[:2000],
        'pending_clarification': pending.model_dump_json(),
    })


def clear_pending_history(history):
    for turn in history:
        turn.pop('pending_clarification', None)


def without_pending_metadata(result):
    if 'pending_clarification' not in result.metadata:
        return result
    metadata = dict(result.metadata)
    metadata.pop('pending_clarification', None)
    return result.model_copy(update={'metadata': metadata})


def append_debug_turn(history, request, result):
    status = result.metadata.get('status')
    pending = pending_from_result(result)
    if status in {'failed', 'unsupported'} or (result.metadata.get('ok') is False and pending is None
                                                and status != 'clarification_required'):
        return
    context = next((turn['sql_context'] for turn in reversed(history) if 'sql_context' in turn), '')
    if result.data.get('query_status') == 'executed':
        context = serialize_context(result.metadata.get('semantic_interpretation'))
    turn = {'question': request.question[:2000], 'scope': request.question[:2000],
            'clarification': result.answer[:2000] if status == 'clarification_required' else '',
            'sql_context': context}
    if pending is not None:
        turn['pending_clarification'] = pending.model_dump_json()
        turn['clarification'] = pending.clarification_question[:2000]
    options = result.metadata.get('clarification_options')
    if status == 'clarification_required' and isinstance(options, list):
        turn['clarification_options'] = options[:3]
    metrics = result.metadata.get('metrics')
    if result.data.get('query_status') == 'executed' and isinstance(metrics, dict):
        turn['metrics'] = ', '.join(sorted(name for name in metrics if isinstance(name, str)))
    history.append(turn)
