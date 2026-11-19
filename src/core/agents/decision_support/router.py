"""Bounded LangGraph orchestration for Knowledge, SQL and decision-support modes."""
from __future__ import annotations

import asyncio
import inspect
import json
import os
import re
import secrets
import time
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from core.agents.decision_support.conversation_context import ConversationStore
from core.agents.decision_support.execution import Execution, authorize
from core.agents.intent_classifier import (
    JEV_ROUTE_THRESHOLD, classify_jev_route, IntentClassifier, is_product_profit_recommendation,
)
from core.agents.decision_support.planning import plan_request
from core.agents.decision_support.response import assemble_response
from core.agents.runtime import deadline, remaining, run_sync
from core.agents.sql.intent_resolution import apply_pending_choice, resolve_pending_clarification
from core.agents.sql.query_intent import (
    ClarificationChoice,
    PendingClarification,
    QueryIntent,
)
from core.latency import measure
from core.models.agents import AgentRequest, AgentResult
from core.models.agent_plan import AgentPlan


class _State(TypedDict, total=False):
    request: AgentRequest
    history: list
    plan: AgentPlan
    forced_plan: AgentPlan
    execution: Execution
    revisions: int
    revise: bool
    result: AgentResult
    report_headings: list[str] | None


def _resolve_clarification_choice(selection, history: list):
    if not isinstance(selection, dict) or not history:
        return None
    for turn in reversed(history):
        state = turn.get('clarification_state')
        if not isinstance(state, dict) or state.get('active') is not True:
            continue
        scope = state.get('scope')
        choices = state.get('choices')
        if not isinstance(scope, str) or not scope.strip() or not isinstance(choices, list):
            return None
        if ('clarification_id' in selection or 'choice_id' in selection):
            if (selection.get('clarification_id') != state.get('id')
                    or type(selection.get('version')) is not int
                    or selection.get('version') != state.get('version')):
                continue
            match = next((choice for choice in choices
                          if isinstance(choice, dict) and choice.get('id') == selection.get('choice_id')),
                         None)
            if match is not None:
                index = choices.index(match)
                return scope.strip(), index + 1, match.get('label'), turn
            continue
        # Older clients submit the original question and an option index. Resolve only
        # against the one active server-owned choice set; never search historical turns.
        index, question = selection.get('index'), selection.get('question')
        if (type(index) is int and 0 <= index < len(choices)
                and isinstance(question, str)
                and question in {turn.get('question'), state.get('question')}):
            return scope.strip(), index + 1, choices[index].get('label'), turn
    return None


class AgentRouter:
    def __init__(self, classifier, knowledge_agent, analytics_agent, dashboard_agent=None,
                 report_agent=None, *, llm=None, request_timeout=120):
        self.classifier = classifier
        from core.agents.sql.analytics_agent import AnalyticsAgent
        self.sql_mode_agent = analytics_agent if isinstance(analytics_agent, AnalyticsAgent) else None
        sql_runtime = analytics_agent.sql_agent if self.sql_mode_agent else analytics_agent
        self.knowledge_agent, self.analytics_agent = knowledge_agent, sql_runtime
        schema = getattr(sql_runtime, 'table_columns', None)
        self.sql_schema = schema if isinstance(schema, dict) else None
        self.dashboard_agent, self.report_agent = dashboard_agent, report_agent
        self.llm, self._owns_llm = llm, False
        self._injected_llm = llm is not None
        self.response_llm, self._owns_response_llm = None, False
        self.request_timeout = min(120, request_timeout)
        self.conversations = ConversationStore()
        self.report_conversations = ConversationStore()
        self.last_destination = 'unrouted'  # Compatibility only; results carry request-local routing.
        graph = StateGraph(_State)
        for name in ('plan', 'execute', 'inspect', 'revise', 'combine'):
            graph.add_node(name, getattr(self, '_' + name))
        graph.add_edge(START, 'plan')
        graph.add_conditional_edges('plan', lambda state: 'done' if state.get('result') else 'execute',
                                    {'done': END, 'execute': 'execute'})
        graph.add_edge('execute', 'inspect')
        graph.add_conditional_edges('inspect', lambda state: 'revise' if state['revise'] else 'combine',
                                    {'revise': 'revise', 'combine': 'combine'})
        graph.add_edge('revise', 'execute')
        graph.add_edge('combine', END)
        self.graph = graph.compile()

    async def run(self, request, *, config=None):
        return await self._run(request, config=config)

    async def collect_sources(self, request, headings, *, config=None):
        if request.conversation_id:
            request = request.model_copy(update={'conversation_id': 'report:' + request.conversation_id})
        return await self._run(request, report_headings=list(headings), config=config)

    async def _run(self, request, *, report_headings=None, config=None, forced_plan=None):
        execution = Execution(request, {'knowledge': self.knowledge_agent, 'sql': self.analytics_agent},
                              auto_mode=report_headings is None and forced_plan is None)
        token = deadline.set(time.monotonic() + self.request_timeout)
        try:
            with measure('agent_workflow'):
                async with asyncio.timeout(self.request_timeout):
                    store = self.report_conversations if report_headings is not None else self.conversations
                    async with store.session(request) as history:
                        user_question = request.question
                        pending_resumed = False
                        if report_headings is None and forced_plan is None:
                            request, reply_plan, reply_resumed, early_result = (
                                await self._prepare_clarification_reply(request, history))
                            if early_result is not None:
                                return early_result
                            if reply_plan is not None:
                                forced_plan = reply_plan
                                pending_resumed = reply_resumed
                                execution.request = request
                        pending = self._pending_from_history(history)
                        if pending is not None and report_headings is None and forced_plan is None:
                            try:
                                authorize(request, 'sql')
                                resolved = await resolve_pending_clarification(
                                    pending, request.question, self._intent_provider(), self._intent_schema())
                            except (AssertionError, AttributeError, IndexError, KeyError, NameError,
                                    PermissionError, TypeError, ZeroDivisionError):
                                raise
                            except Exception:
                                resolved = pending
                            if isinstance(resolved, PendingClarification):
                                self._clear_pending_history(history)
                                return self._pending_result(resolved, history, reply=request.question)
                            self._clear_pending_history(history)
                            if isinstance(resolved, QueryIntent):
                                request = request.model_copy(update={
                                    'question': resolved.original_question,
                                    'metadata': {**request.metadata,
                                                 '_query_intent': resolved.model_dump(mode='json'),
                                                 '_original_question': resolved.original_question},
                                })
                                forced_plan = AgentPlan(objective=resolved.original_question, tasks=[{
                                    'id': 'sql', 'agent': 'sql', 'question': resolved.original_question,
                                }])
                                pending_resumed = True
                                execution.request = request
                        execution.sql_context = self._sql_context_from_history(history)
                        if pending_resumed:
                            execution.auto_mode = True
                        # Reports build their own section questions, so only chat turns get the user's wording.
                        execution.standalone = not history and report_headings is None and forced_plan is None
                        graph_input = {'request': request, 'history': list(history),
                            'execution': execution, 'revisions': 0, 'report_headings': report_headings}
                        if forced_plan is not None:
                            graph_input['forced_plan'] = forced_plan
                        state = await self.graph.ainvoke(graph_input, config=config)
                        result = AgentResult.model_validate(state['result'])
                        pending_state = self._pending_after_execution(execution)
                        status = result.metadata.get('status')
                        history_request = state.get('request') or request
                        if status == 'clarification_required':
                            result.metadata['clarification_question'] = history_request.question[:2000]
                        record_context = (status in {'complete', 'partial', 'clarification_required'}
                                          or (status is None and result.metadata.get('ok') is True)
                                          or pending_state is not None)
                        if record_context:
                            scope = state['plan'].objective if state.get('plan') else history_request.question
                            clarification_state = (self._present_clarification(
                                result, history, scope, pending_state)
                                if status == 'clarification_required' else None)
                            turn = {'question': history_request.question[:2000], 'scope': scope[:2000],
                                    'clarification': result.answer[:2000] if result.metadata.get('status') == 'clarification_required' else ''}
                            options = result.metadata.get('clarification_options')
                            if status == 'clarification_required' and isinstance(options, list):
                                turn['clarification_options'] = options[:3]
                            if pending_state is not None:
                                turn['pending_clarification'] = pending_state.model_dump_json()
                                turn['clarification'] = pending_state.clarification_question[:2000]
                            if clarification_state is not None:
                                turn['clarification_state'] = clarification_state
                            if result.metadata.get('status') == 'clarification_required' and state.get('plan'):
                                tasks = state['plan'].tasks
                                pending = [execution.outcomes.get(task.id) for task in tasks]
                                if (len(tasks) == 1 and not tasks[0].depends_on and not tasks[0].inputs
                                        and pending[0] and pending[0].status == 'clarification_required'):
                                    turn['clarification_plan'] = AgentPlan(
                                        objective=scope, tasks=tasks,
                                        fallback=state['plan'].fallback,
                                        uses_context=state['plan'].uses_context,
                                    ).model_dump_json()
                            if report_headings is None:
                                turn['sql_context'] = self._sql_context_after_execution(execution, history)
                                metrics = next((outcome.result.metadata.get('metrics')
                                    for outcome in execution.outcomes.values()
                                    if outcome.result and outcome.result.data.get('query_status') == 'executed'
                                    and isinstance(outcome.result.metadata.get('metrics'), dict)), None)
                                if metrics:
                                    turn['metrics'] = ', '.join(sorted(name for name in metrics if isinstance(name, str)))
                            history.append(turn)
                        self.last_destination = result.metadata.get('selected_route', 'unrouted')
                        return self._without_pending_metadata(result)
        except PermissionError:
            raise
        except TimeoutError:
            if getattr(execution, 'plan', None) and execution.outcomes:
                result = (execution.collected_sources(execution.plan) if report_headings is not None
                          else await assemble_response(request, execution.plan, execution, None))
                result.metadata.update(ok=False, status='partial' if result.evidence else 'failed')
                result.metadata['limitations'].append('Request deadline exhausted.')
                result.answer += '\n\nRequest deadline exhausted; remaining tasks were stopped.'
                if forced_plan is not None:
                    result = result.model_copy(update={'agent': 'decision_support', 'metadata': {
                        **result.metadata, 'selected_route': 'decision_support'}})
                return result
            return self._failure('Request deadline exhausted before a supported answer could be completed.',
                                 trace=execution.trace)
        except (ValueError, RuntimeError) as error:
            return self._failure('Automatic planning is unavailable or could not safely complete this request. '
                                 'Please retry or select Knowledge or SQL.', trace=execution.trace,
                                 error_type=type(error).__name__)
        finally:
            deadline.reset(token)

    async def route(self, request):
        return await self.run(request)

    async def run_mode(self, request, mode, *, config=None):
        if mode in {'auto', 'agentic'}:
            return await self.run(request, config=config)
        if mode == 'decision_support':
            plan = AgentPlan(objective=request.question, tasks=[
                {'id': 'knowledge', 'agent': 'knowledge', 'question': request.question},
                {'id': 'sql', 'agent': 'sql', 'question': request.question},
            ])
            return await self._run(request, config=config, forced_plan=plan)
        agents = {'knowledge': self.knowledge_agent, 'sql': self.analytics_agent,
                  'dashboard': self.dashboard_agent, 'report': self.report_agent}
        if mode not in agents:
            raise ValueError('Unsupported agent mode')
        if mode in {'knowledge', 'sql'}:
            authorize(request, mode)
        agent = agents[mode]
        if agent is None:
            return self._failure('This standalone request type is not supported.')
        if mode == 'sql':
            if self.sql_mode_agent is not None:
                agent = self.sql_mode_agent
            else:
                from core.agents.sql.agent import SQLAnalyticsAgent
                if isinstance(agent, SQLAnalyticsAgent):
                    from core.agents.sql.analytics_agent import AnalyticsAgent
                    agent = AnalyticsAgent(agent)
        if mode == 'sql':
            authorize(request, 'sql')
            async with self.conversations.session(request) as history:
                request, _, _, early_result = await self._prepare_clarification_reply(request, history)
                if early_result is not None:
                    return early_result
                marker = request.metadata.get('_validated_clarification_choice')
                if marker:
                    choice = _resolve_clarification_choice(marker, list(history))
                    if choice is None:
                        return self._invalid_clarification_reply()
                    scope, _, option, turn = choice
                    turn['clarification_state']['active'] = False
                    self._clear_pending_history(history)
                    metadata = dict(request.metadata)
                    metadata.pop('_validated_clarification_choice', None)
                    request = request.model_copy(update={
                        'question': f"{scope}\n\nUser clarification: {option}",
                        'metadata': metadata,
                    })
                pending = self._pending_from_history(history)
                if pending is not None:
                    try:
                        resolved = await resolve_pending_clarification(
                            pending, request.question, self._intent_provider(), self._intent_schema())
                    except (AssertionError, AttributeError, IndexError, KeyError, NameError,
                            PermissionError, TypeError, ZeroDivisionError):
                        raise
                    except Exception:
                        resolved = pending
                    if isinstance(resolved, PendingClarification):
                        self._clear_pending_history(history)
                        return self._pending_result(resolved, history, reply=request.question)
                    self._clear_pending_history(history)
                    if isinstance(resolved, QueryIntent):
                        request = request.model_copy(update={
                            'question': resolved.original_question,
                            'metadata': {**request.metadata,
                                         '_query_intent': resolved.model_dump(mode='json'),
                                         '_original_question': resolved.original_question},
                        })
                with measure('agent_workflow'):
                    result = agent.run(request)
                    if inspect.isawaitable(result):
                        result = await result
                result = AgentResult.model_validate(result)
                if result.metadata.get('status') == 'clarification_required':
                    result.metadata['clarification_question'] = request.question[:2000]
                await self._record_sql_debug_turn(request, result, history=history)
                result = self._without_pending_metadata(result)
        else:
            with measure('agent_workflow'):
                result = agent.run(request)
                if inspect.isawaitable(result):
                    result = await result
            result = AgentResult.model_validate(result)
        route = 'analytics' if mode == 'sql' else mode
        self.last_destination = route
        return result.model_copy(update={'metadata': {**result.metadata, 'selected_route': route}})

    @staticmethod
    def _sql_context_from_history(history):
        from core.analytics.metric_mapping import SQLConversationState
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

    @staticmethod
    def _serialize_sql_context(interpretation):
        if not isinstance(interpretation, dict):
            return ''
        from core.analytics.metric_mapping import SQLConversationState
        try:
            return SQLConversationState.model_validate(
                {'accepted': interpretation, 'pending': None}).model_dump_json()
        except ValueError:
            return ''

    @classmethod
    def _sql_context_after_execution(cls, execution, history):
        context = next((turn['sql_context'] for turn in reversed(history) if 'sql_context' in turn), '')
        for task in execution.plan.tasks if execution.plan else ():
            outcome = execution.outcomes.get(task.id)
            result = outcome.result if outcome and task.agent == 'sql' else None
            if result and result.data.get('query_status') == 'executed':
                context = cls._serialize_sql_context(result.metadata.get('semantic_interpretation'))
        return context

    async def _record_sql_debug_turn(self, request, result, *, history=None):
        if history is None:
            if not request.conversation_id or not request.identity:
                return
            async with self.conversations.session(request) as session:
                await self._record_sql_debug_turn(request, result, history=session)
            return
        status = result.metadata.get('status')
        pending = self._pending_from_result(result)
        if status in {'failed', 'unsupported'} or (result.metadata.get('ok') is False and pending is None
                                                    and status != 'clarification_required'):
            return
        context = next((turn['sql_context'] for turn in reversed(history) if 'sql_context' in turn), '')
        if result.data.get('query_status') == 'executed':
            context = self._serialize_sql_context(result.metadata.get('semantic_interpretation'))
        turn = {'question': request.question[:2000], 'scope': request.question[:2000],
                'clarification': result.answer[:2000] if status == 'clarification_required' else '',
                'sql_context': context}
        if pending is not None:
            turn['pending_clarification'] = pending.model_dump_json()
            turn['clarification'] = pending.clarification_question[:2000]
        options = result.metadata.get('clarification_options')
        if status == 'clarification_required' and isinstance(options, list):
            turn['clarification_options'] = options[:3]
        if status == 'clarification_required':
            turn['clarification_state'] = self._present_clarification(
                result, history, request.question, pending)
        metrics = result.metadata.get('metrics')
        if result.data.get('query_status') == 'executed' and isinstance(metrics, dict):
            turn['metrics'] = ', '.join(sorted(name for name in metrics if isinstance(name, str)))
        history.append(turn)

    def _intent_provider(self):
        provider_factory = getattr(self.analytics_agent, '_provider', None)
        return provider_factory() if provider_factory else self._provider()

    def _intent_schema(self):
        if self.sql_schema:
            return self.sql_schema
        from core.analytics.text_to_sql import APPROVED_COLUMNS
        return APPROVED_COLUMNS

    @staticmethod
    def _pending_from_history(history):
        for turn in reversed(history):
            state = turn.get('clarification_state')
            if isinstance(state, dict) and state.get('active') is not True:
                continue
            raw = turn.get('pending_clarification')
            if raw:
                try:
                    return PendingClarification.model_validate_json(raw)
                except (TypeError, ValueError):
                    return None
        return None

    @staticmethod
    def _pending_from_result(result):
        raw = result.metadata.get('_pending_clarification', result.metadata.get('pending_clarification'))
        if not raw:
            return None
        try:
            if isinstance(raw, dict):
                return PendingClarification.model_validate_json(json.dumps(raw, ensure_ascii=False), strict=True)
            return PendingClarification.model_validate_json(raw, strict=True)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _pending_after_execution(cls, execution):
        for task in execution.plan.tasks if execution.plan else ():
            outcome = execution.outcomes.get(task.id)
            if outcome and outcome.result and task.agent == 'sql':
                pending = cls._pending_from_result(outcome.result)
                if pending is not None:
                    return pending
        return None

    @staticmethod
    def _active_clarification_state(history):
        for turn in reversed(history):
            state = turn.get('clarification_state')
            if isinstance(state, dict) and state.get('active') is True:
                return state, turn
        return None, None

    @classmethod
    def _validate_clarification_reply(cls, reply, history):
        if (not isinstance(reply, dict) or set(reply) - {'clarification_id', 'version', 'choice_id'}
                or not isinstance(reply.get('clarification_id'), str)
                or type(reply.get('version')) is not int or reply['version'] < 1
                or ('choice_id' in reply and not isinstance(reply['choice_id'], str))):
            return None
        state, turn = cls._active_clarification_state(history)
        if (state is None or state.get('id') != reply['clarification_id']
                or state.get('version') != reply['version']):
            return None
        if 'choice_id' not in reply:
            return (state, turn, None) if state.get('allow_custom') is True else None
        match = next((choice for choice in state.get('choices', [])
                      if isinstance(choice, dict) and choice.get('id') == reply['choice_id']), None)
        return (state, turn, match) if match is not None else None

    @classmethod
    def _legacy_choice_marker(cls, selection, history):
        resolved = _resolve_clarification_choice(selection, history)
        if resolved is None:
            return None
        _, number, _, turn = resolved
        state = turn.get('clarification_state')
        if not isinstance(state, dict) or not 1 <= number <= len(state.get('choices', [])):
            return None
        choice = state['choices'][number - 1]
        return {'clarification_id': state['id'], 'version': state['version'],
                'choice_id': choice['id']}

    async def _prepare_clarification_reply(self, request, history):
        """Validate a click under the conversation lock and translate it to server-owned state."""
        metadata = dict(request.metadata)
        has_structured = 'clarification_reply' in metadata
        has_legacy = 'clarification_choice' in metadata
        if not has_structured and not has_legacy:
            return request, None, False, None

        if has_structured:
            reply = metadata.pop('clarification_reply')
            validated = self._validate_clarification_reply(reply, history)
            if validated is None:
                return request, None, False, self._invalid_clarification_reply()
            state, turn, record = validated
        else:
            legacy = metadata.pop('clarification_choice')
            marker = self._legacy_choice_marker(legacy, history)
            validated = self._validate_clarification_reply(marker, history) if marker else None
            if validated is None:
                return request, None, False, self._invalid_clarification_reply()
            state, turn, record = validated

        pending = self._pending_from_history(history)
        scope = state['scope']
        if pending is not None:
            if record is None:
                try:
                    resolved = await resolve_pending_clarification(
                        pending, request.question, self._intent_provider(), self._intent_schema())
                except Exception:
                    # Keep the live state so a client can retry after a transient provider failure.
                    raise
            else:
                if record.get('kind') != 'intent':
                    return request, None, False, self._invalid_clarification_reply()
                selected = ClarificationChoice.model_validate_json(
                    json.dumps(record.get('intent_choice'), ensure_ascii=False), strict=True)
                resolved = apply_pending_choice(pending, selected, self._intent_schema())

            state['active'] = False
            self._clear_pending_history(history)
            if isinstance(resolved, PendingClarification):
                return request, None, False, self._pending_result(
                    resolved, history, reply=request.question)
            if isinstance(resolved, QueryIntent):
                request = request.model_copy(update={
                    'question': resolved.original_question,
                    'metadata': {**metadata, '_query_intent': resolved.model_dump(mode='json'),
                                 '_original_question': resolved.original_question},
                })
                from core.models.agent_plan import AgentPlan
                plan = AgentPlan(objective=resolved.original_question, tasks=[{
                    'id': 'sql', 'agent': 'sql', 'question': resolved.original_question,
                }])
                return request, plan, True, None
            return request.model_copy(update={'metadata': metadata}), None, False, None

        if record is None:
            if not request.question.strip():
                return request, None, False, self._invalid_clarification_reply()
            state['active'] = False
            self._clear_pending_history(history)
            return request.model_copy(update={
                'question': f"{scope}\n\nUser clarification: {request.question.strip()}",
                'metadata': metadata,
            }), None, False, None

        if record.get('kind') != 'plan':
            return request, None, False, self._invalid_clarification_reply()
        marker = {'clarification_id': state['id'], 'version': state['version'],
                  'choice_id': record['id']}
        return request.model_copy(update={
            'metadata': {**metadata, '_validated_clarification_choice': marker},
        }), None, False, None

    @staticmethod
    def _present_clarification(result, history, scope, pending=None):
        """Attach the sole public choice contract and retain opaque resolution data in history."""
        records = []
        if pending is not None:
            for choice in pending.allowed_choices[:3]:
                records.append({
                    'id': secrets.token_urlsafe(18), 'label': choice.label,
                    'kind': 'intent', 'intent_choice': choice.model_dump(mode='json'),
                })
        else:
            options = result.metadata.get('clarification_options')
            if isinstance(options, list):
                for index, label in enumerate(options[:3]):
                    if isinstance(label, str) and label.strip():
                        records.append({
                            'id': secrets.token_urlsafe(18), 'label': label,
                            'kind': 'plan', 'index': index,
                        })
        prior_versions = [
            turn['clarification_state'].get('version', 0)
            for turn in history if isinstance(turn.get('clarification_state'), dict)
        ]
        state = {
            'id': secrets.token_urlsafe(24),
            'version': max(prior_versions, default=0) + 1,
            'scope': str(scope)[:2000],
            'question': result.answer[:2000],
            'choices': records,
            'allow_custom': True,
            'active': True,
        }
        result.metadata['clarification_ui'] = {
            'id': state['id'], 'version': state['version'],
            'question': state['question'],
            'choices': [{'id': choice['id'], 'label': choice['label']} for choice in records],
            'allow_custom': state['allow_custom'],
        }
        return state

    @staticmethod
    def _invalid_clarification_reply():
        return AgentResult(
            answer='This clarification is no longer active. Please ask the question again.',
            agent='sql_analytics', data={'query_status': 'clarification_required'},
            metadata={'ok': False, 'status': 'clarification_required',
                      'clarification_required': True,
                      'clarification_reply_error': 'stale_or_invalid', 'selected_route': 'analytics'},
        )

    @classmethod
    def _pending_result(cls, pending, history, *, reply=None):
        result = AgentResult(
            answer=pending.clarification_question, agent='sql_analytics',
            data={'query_status': 'clarification_required'},
            metadata={'ok': False, 'status': 'clarification_required',
                      'clarification_required': True, 'selected_route': 'analytics'},
        )
        state = cls._present_clarification(result, history, pending.original_question, pending)
        history.append({
            'question': (reply or pending.original_question)[:2000],
            'scope': pending.original_question[:2000],
            'clarification': pending.clarification_question[:2000],
            'pending_clarification': pending.model_dump_json(),
            'clarification_state': state,
        })
        return result

    @staticmethod
    def _record_pending_reply(history, reply, pending):
        history.append({
            'question': reply[:2000], 'scope': pending.original_question[:2000],
            'clarification': pending.clarification_question[:2000],
            'pending_clarification': pending.model_dump_json(),
        })

    @staticmethod
    def _clear_pending_history(history):
        for turn in history:
            turn.pop('pending_clarification', None)
            state = turn.get('clarification_state')
            if isinstance(state, dict):
                state['active'] = False

    @staticmethod
    def _without_pending_metadata(result):
        if not ({'pending_clarification', '_pending_clarification', '_query_intent',
                 '_original_question'} & result.metadata.keys()):
            return result
        metadata = dict(result.metadata)
        metadata.pop('pending_clarification', None)
        metadata.pop('_pending_clarification', None)
        metadata.pop('_query_intent', None)
        metadata.pop('_original_question', None)
        return result.model_copy(update={'metadata': metadata})

    async def _plan(self, state):
        with measure('routing'):
            request = state['request']
            plan = state.get('forced_plan')
            jev_routed = False
            resumed_clarification = False
            if plan is None:
                choice = _resolve_clarification_choice(
                    request.metadata.get('_validated_clarification_choice')
                    or request.metadata.get('clarification_choice'), state['history'])
                if choice:
                    scope, _, option, turn = choice
                    turn['clarification_state']['active'] = False
                    request = request.model_copy(update={
                        'question': f"{scope}\n\nUser clarification: {option}"
                    })
                    state['request'] = request
                    state['execution'].request = request
                    raw_plan = turn.get('clarification_plan')
                    if isinstance(raw_plan, str):
                        try:
                            previous_plan = AgentPlan.model_validate_json(raw_plan)
                            if (len(previous_plan.tasks) == 1 and not previous_plan.tasks[0].depends_on
                                    and not previous_plan.tasks[0].inputs):
                                task = previous_plan.tasks[0]
                                task_question = f"{task.question}\n\nUser clarification: {option}"
                                if len(task_question) <= 2000:
                                    plan = previous_plan.model_copy(update={
                                        'objective': scope,
                                        'tasks': [task.model_copy(update={'question': task_question})],
                                    })
                                    resumed_clarification = True
                        except ValueError:
                            pass
                if plan is None:
                    latest_turn = state['history'][-1] if state['history'] else {}
                    short_followup = bool(state['history'] and len(request.question.split()) <= 8)
                    pending_clarification = bool(
                        isinstance(latest_turn.get('clarification'), str)
                        and latest_turn['clarification'].strip()
                    )
                    try:
                        route = await run_sync(classify_jev_route, request.question, self.sql_schema,
                                               state['history'], _timeout=12)
                    except Exception:
                        route = None
                    if (route and route['route'] in {'knowledge', 'sql'}
                            and not is_product_profit_recommendation(request.question)
                            and route['confidence'] >= JEV_ROUTE_THRESHOLD and not route['history_required']
                            and not short_followup
                            and state.get('report_headings') is None and not pending_clarification):
                        agent = route['route']
                        task_id = 'k' if agent == 'knowledge' else 's'
                        plan = AgentPlan(objective=request.question, fallback=True, tasks=[{
                            'id': task_id, 'agent': agent, 'question': request.question}])
                        jev_routed = True
                    else:
                        plan = await plan_request(request, self._provider(), history=state['history'],
                                                  report_headings=state.get('report_headings'), sql_schema=self.sql_schema,
                                                  selected_tools=route.get('selected_tools', []) if route else None)
            explicit_sql = bool(re.search(
                r'\b(select|sql|query|table|database|schema|from)\b|(?:truy vấn|bảng)',
                request.question, re.I))
            analytics_intent = IntentClassifier.fallback(request.question).needs_sql
            if state.get('forced_plan') is None and not resumed_clarification and (any(task.agent == 'sql' for task in plan.tasks) or (
                    plan.clarification and (explicit_sql or analytics_intent))):
                sql_agent = getattr(self.analytics_agent, 'sql_agent', self.analytics_agent)
                repository = getattr(sql_agent, 'repository', None)
                discover = getattr(repository, 'get_schema', None)
                if discover is not None:
                    try:
                        schema = await discover()
                    except Exception:
                        # Let the SQL agent return its structured source error.
                        # Discovery here is only for improving the planner context.
                        schema = None
                    live_schema = schema.get('tables') if isinstance(schema, dict) else None
                    if live_schema and live_schema != self.sql_schema and not jev_routed:
                        plan = await plan_request(request, self._provider(), history=state['history'],
                            report_headings=state.get('report_headings'), sql_schema=live_schema,
                            selected_tools=route.get('selected_tools', []) if route else None)
        state['execution'].plan = plan
        if plan.clarification:
            return {'request': request, 'plan': plan,
                    'result': AgentResult(answer=plan.clarification, agent='agentic', metadata={
                'ok': False, 'status': 'clarification_required', 'clarification_required': True,
                'selected_route': 'clarification', 'task_trace': []})}
        return {'request': request, 'plan': plan}

    async def _execute(self, state):
        await state['execution'].run(state['plan'])
        return {}

    async def _inspect(self, state):
        execution = state['execution']
        # A clarification is a request for user input, not a recoverable execution failure.
        # Replanning it adds another model call without changing the information available.
        failed = [execution.outcomes[t.id] for t in state['plan'].tasks if t.id in execution.outcomes
                  and execution.outcomes[t.id].status in {'failed', 'empty'}]
        return {'revise': bool(failed and state['revisions'] < 1 and execution.invocations < 6
                               and remaining() > 5)}

    async def _revise(self, state):
        execution = state['execution']
        try:
            plan = await plan_request(state['request'], self._provider(), history=state['history'],
                previous=execution.revision_context(state['plan']), report_headings=state.get('report_headings'), sql_schema=self.sql_schema)
            if plan.clarification:
                return {'revisions': 1}
            completed = {key: o for key, o in execution.outcomes.items() if o.status == 'complete'}
            by_id = {t.id: t for t in plan.tasks}
            if any(key not in by_id or by_id[key] != o.task for key, o in completed.items()):
                return {'revisions': 1}
            if not {t.agent for t in state['plan'].tasks} <= {t.agent for t in plan.tasks}:
                return {'revisions': 1}
            for task in plan.tasks:
                authorize(state['request'], task.agent)
            execution.plan = plan
            return {'plan': plan, 'revisions': 1}
        except PermissionError:
            raise
        except Exception:
            return {'revisions': 1}

    async def _combine(self, state):
        plan, execution = state['plan'], state['execution']
        direct_fallback = None
        if plan.fallback and len(plan.tasks) == 1:
            outcome = execution.outcomes.get(plan.tasks[0].id)
            if outcome and outcome.status == 'complete' and outcome.result:
                direct_fallback = outcome.result
        if (direct_fallback is not None and state.get('report_headings') is None
                and plan.tasks[0].agent != 'sql'):
            selected_route = 'analytics' if plan.tasks[0].agent == 'sql' else plan.tasks[0].agent
            result = direct_fallback.model_copy(update={'metadata': {
                **direct_fallback.metadata,
                'selected_route': selected_route,
                'planning_fallback': True,
                'task_trace': execution.trace,
                'specialist_invocations': execution.invocations,
            }})
        else:
            with measure('answer_synthesis'):
                result = (execution.collected_sources(plan) if state.get('report_headings') is not None
                          else await assemble_response(state['request'], plan, execution,
                                                       self._response_provider()))
        result.metadata['revisions'] = state['revisions']
        if state.get('forced_plan') is not None:
            result = result.model_copy(update={'agent': 'decision_support', 'metadata': {
                **result.metadata, 'selected_route': 'decision_support'}})
        return {'result': result}

    @staticmethod
    def _failure(answer, *, trace=None, error_type=None):
        return AgentResult(answer=answer, agent='agentic', metadata={'ok': False, 'status': 'failed',
            'selected_route': 'unrouted', 'task_trace': trace or [], 'error_type': error_type})

    def _provider(self):
        if self.llm is None:
            provider = os.getenv('DECISION_PLANNER_LLM_PROVIDER', 'auto').strip().casefold()
            cloudflare_ready = bool(os.getenv('CLOUDFLARE_ACCOUNT_ID') and
                                    (os.getenv('CLOUDFLARE_API_TOKEN') or os.getenv('CLOUDFLARE_WORKERS_API')))
            if provider not in {'auto', 'cloudflare', 'groq', 'codex_cli'}:
                raise ValueError('DECISION_PLANNER_LLM_PROVIDER must be auto, cloudflare, groq or codex_cli')
            if provider == 'codex_cli':
                from core.agents.runtime import CodexCLIProvider
                self.llm = CodexCLIProvider(timeout=60)
            elif provider == 'cloudflare' or (provider == 'auto' and cloudflare_ready):
                from core.llm.Cloudflare_provider import CloudflareProvider
                self.llm = CloudflareProvider(
                    model=os.getenv('DECISION_PLANNER_CLOUDFLARE_MODEL', '@cf/openai/gpt-oss-20b'))
            else:
                from core.llm.groq_provider import GroqProvider
                self.llm = GroqProvider(model=os.getenv('DECISION_PLANNER_GROQ_MODEL') or None)
            self._owns_llm = True
        return self.llm

    def _response_provider(self):
        # Explicitly injected providers remain a single-model override for tests and callers.
        if self._injected_llm:
            return self.llm
        if self.response_llm is not None:
            return self.response_llm
        provider = os.getenv('DECISION_RESPONSE_LLM_PROVIDER', 'auto').strip().casefold()
        if provider == 'codex_cli':
            self.response_llm = 'codex_cli'
            return self.response_llm
        has_cloudflare = bool(os.getenv('CLOUDFLARE_ACCOUNT_ID') and
                              (os.getenv('CLOUDFLARE_API_TOKEN') or os.getenv('CLOUDFLARE_WORKERS_API')))
        if provider not in {'auto', 'cloudflare', 'groq'}:
            raise ValueError('DECISION_RESPONSE_LLM_PROVIDER must be auto, cloudflare, groq or codex_cli')
        use_cloudflare = provider == 'cloudflare' or (provider == 'auto' and has_cloudflare)
        if use_cloudflare:
            from core.llm.Cloudflare_provider import CloudflareProvider
            self.response_llm = CloudflareProvider(
                model=os.getenv('DECISION_RESPONSE_CLOUDFLARE_MODEL', '@cf/openai/gpt-oss-20b'))
        else:
            from core.llm.groq_provider import GroqProvider
            self.response_llm = GroqProvider(model=os.getenv('DECISION_RESPONSE_GROQ_MODEL') or None)
        self._owns_response_llm = True
        return self.response_llm

    async def close(self):
        seen = set()
        for agent in (self.knowledge_agent, self.analytics_agent, self.dashboard_agent, self.report_agent):
            if agent is None or id(agent) in seen:
                continue
            seen.add(id(agent))
            close = getattr(agent, 'close', None)
            if close:
                result = close()
                if inspect.isawaitable(result):
                    await result
        if self.classifier is not None and hasattr(self.classifier, 'close'):
            self.classifier.close()
        owned = [(self.llm, self._owns_llm), (self.response_llm, self._owns_response_llm)]
        closed = set()
        for provider, is_owned in owned:
            if is_owned and provider is not None and id(provider) not in closed and hasattr(provider, 'close'):
                provider.close()
                closed.add(id(provider))
