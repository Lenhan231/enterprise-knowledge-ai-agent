"""Bounded LangGraph orchestration for Knowledge, SQL and decision-support modes."""
from __future__ import annotations

import asyncio
import inspect
import os
import time

from core.agents.decision_support.conversation_context import ConversationStore
from core.agents.decision_support.conversation_context import (
    resolve_clarification_choice as _resolve_clarification_choice,
)
from core.agents.decision_support.execution import Execution, authorize
from core.agents.decision_support.route_selector import AgentRouter as RouteSelector
from core.agents.decision_support.planning import plan_request
from core.agents.decision_support.workflow import AgentWorkflow
from core.agents.runtime import deadline
from core.agents.sql.intent_resolution import resolve_pending_clarification
from core.agents.sql.query_intent import PendingClarification, QueryIntent
from core.agents.sql.conversation import (
    append_debug_turn,
    clear_pending_history,
    context_after_execution,
    context_from_history,
    pending_after_execution,
    pending_from_history,
    record_pending_reply,
    without_pending_metadata,
)
from core.agents.decision_support.intent_classifier import classify_jev_route
from core.latency import measure
from core.models.agents import AgentRequest, AgentResult
from core.models.agent_plan import AgentPlan


class AgentOrchestrator:
    def __init__(self, classifier, knowledge_agent, analytics_agent, dashboard_agent=None,
                 report_agent=None, *, llm=None, request_timeout=120):
        self.classifier = classifier
        self.route_selector = RouteSelector()
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
        self.workflow = AgentWorkflow(
            self.route_selector,
            sql_schema=self.sql_schema,
            analytics_agent=self.analytics_agent,
            route_classifier=lambda *args, **kwargs: classify_jev_route(*args, **kwargs),
            plan_requester=lambda *args, **kwargs: plan_request(*args, **kwargs),
            planner_provider=lambda: self._provider(),
            response_provider=lambda: self._response_provider(),
        )
        self.graph = self.workflow.graph  # Compatibility for existing integrations.

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
                        pending = pending_from_history(history)
                        pending_resumed = False
                        if pending is not None and report_headings is None and forced_plan is None:
                            try:
                                authorize(request, 'sql')
                                resolved = await resolve_pending_clarification(
                                    pending, request.question, self._intent_provider(), self._intent_schema())
                            except Exception:
                                resolved = pending
                            if isinstance(resolved, PendingClarification):
                                record_pending_reply(history, request.question, resolved)
                                return AgentResult(
                                    answer=resolved.clarification_question, agent='sql_analytics',
                                    data={'query_status': 'clarification_required'},
                                    metadata={'ok': False, 'status': 'clarification_required',
                                              'clarification_required': True, 'selected_route': 'analytics'},
                                )
                            clear_pending_history(history)
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
                        execution.sql_context = context_from_history(history)
                        execution.conversation_context = [] if report_headings is not None else list(history)
                        if pending_resumed:
                            execution.auto_mode = True
                        # Reports build their own section questions, so only chat turns get the user's wording.
                        execution.standalone = not history and report_headings is None and forced_plan is None
                        graph_input = {'request': request, 'history': list(history),
                            'execution': execution, 'revisions': 0, 'report_headings': report_headings}
                        if forced_plan is not None:
                            graph_input['forced_plan'] = forced_plan
                        state = await self.workflow.run(graph_input, config=config)
                        result = AgentResult.model_validate(state['result'])
                        pending_state = pending_after_execution(execution)
                        status = result.metadata.get('status')
                        history_request = state.get('request') or request
                        if status == 'clarification_required':
                            result.metadata['clarification_question'] = history_request.question[:2000]
                        record_context = (status in {'complete', 'partial', 'clarification_required'}
                                          or (status is None and result.metadata.get('ok') is True)
                                          or pending_state is not None)
                        if record_context:
                            scope = state['plan'].objective if state.get('plan') else history_request.question
                            turn = {'question': history_request.question[:2000], 'scope': scope[:2000],
                                    'clarification': result.answer[:2000] if result.metadata.get('status') == 'clarification_required' else ''}
                            options = result.metadata.get('clarification_options')
                            if status == 'clarification_required' and isinstance(options, list):
                                turn['clarification_options'] = options[:3]
                            if pending_state is not None:
                                turn['pending_clarification'] = pending_state.model_dump_json()
                                turn['clarification'] = pending_state.clarification_question[:2000]
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
                                turn['sql_context'] = context_after_execution(execution, history)
                                metrics = next((outcome.result.metadata.get('metrics')
                                    for outcome in execution.outcomes.values()
                                    if outcome.result and outcome.result.data.get('query_status') == 'executed'
                                    and isinstance(outcome.result.metadata.get('metrics'), dict)), None)
                                if metrics:
                                    turn['metrics'] = ', '.join(sorted(name for name in metrics if isinstance(name, str)))
                            history.append(turn)
                        self.last_destination = result.metadata.get('selected_route', 'unrouted')
                        return without_pending_metadata(result)
        except PermissionError:
            raise
        except TimeoutError:
            if getattr(execution, 'plan', None) and execution.outcomes:
                return await self.workflow.partial_result(request, execution, report_headings, forced_plan)
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
                pending = pending_from_history(history)
                if pending is None:
                    choice = _resolve_clarification_choice(
                        request.metadata.get('clarification_choice'), list(history))
                    if choice:
                        scope, _, option, turn = choice
                        clarification = turn.get('clarification')
                        request = request.model_copy(update={
                            'question': f"{scope}\n\nUser clarification: {option}",
                            'metadata': {**request.metadata, '_resolved_clarification': {
                                'original_question': scope,
                                'clarification_question': clarification if isinstance(clarification, str) else '',
                                'answer': option,
                            }},
                        })
                if pending is not None:
                    try:
                        resolved = await resolve_pending_clarification(
                            pending, request.question, self._intent_provider(), self._intent_schema())
                    except Exception:
                        resolved = pending
                    if isinstance(resolved, PendingClarification):
                        record_pending_reply(history, request.question, resolved)
                        return AgentResult(
                            answer=resolved.clarification_question, agent='sql_analytics',
                            data={'query_status': 'clarification_required'},
                            metadata={'ok': False, 'status': 'clarification_required',
                                      'clarification_required': True, 'selected_route': 'analytics'},
                        )
                    clear_pending_history(history)
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
                append_debug_turn(history, request, result)
                result = without_pending_metadata(result)
        else:
            with measure('agent_workflow'):
                result = agent.run(request)
                if inspect.isawaitable(result):
                    result = await result
            result = AgentResult.model_validate(result)
        route = 'analytics' if mode == 'sql' else mode
        self.last_destination = route
        return result.model_copy(update={'metadata': {**result.metadata, 'selected_route': route}})

    def _intent_provider(self):
        provider_factory = getattr(self.analytics_agent, '_provider', None)
        return provider_factory() if provider_factory else self._provider()

    def _intent_schema(self):
        if self.sql_schema:
            return self.sql_schema
        from core.agents.sql.text_to_sql import APPROVED_COLUMNS
        return APPROVED_COLUMNS

    async def _plan(self, state):
        return await self.workflow._plan(state)

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


# Backwards-compatible name for existing integrations; new code should use AgentOrchestrator.
AgentRouter = AgentOrchestrator
