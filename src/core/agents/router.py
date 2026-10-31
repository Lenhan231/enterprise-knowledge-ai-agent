"""Bounded LangGraph orchestration for Knowledge/SQL and standalone modes."""
from __future__ import annotations

import asyncio
import inspect
import time
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from core.agents.conversation_context import ConversationStore
from core.agents.execution import Execution, authorize
from core.agents.planning import plan_request
from core.agents.response import assemble_response
from core.agents.runtime import deadline, remaining
from core.latency import measure
from core.models.agents import AgentRequest, AgentResult
from core.models.agent_plan import AgentPlan


class _State(TypedDict, total=False):
    request: AgentRequest
    history: list
    plan: AgentPlan
    execution: Execution
    revisions: int
    revise: bool
    result: AgentResult
    report_headings: list[str] | None


class AgentRouter:
    def __init__(self, classifier, knowledge_agent, analytics_agent, dashboard_agent=None,
                 report_agent=None, *, llm=None, request_timeout=120):
        self.classifier = classifier
        self.knowledge_agent, self.analytics_agent = knowledge_agent, analytics_agent
        self.dashboard_agent, self.report_agent = dashboard_agent, report_agent
        self.llm, self._owns_llm = llm, False
        self.request_timeout = min(120, request_timeout)
        self.conversations = ConversationStore()
        self.report_conversations = ConversationStore()
        self.sql_conversations = ConversationStore()
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

    async def _run(self, request, *, report_headings=None, config=None):
        execution = Execution(request, {'knowledge': self.knowledge_agent, 'sql': self.analytics_agent})
        token = deadline.set(time.monotonic() + self.request_timeout)
        try:
            with measure('agent_workflow'):
                async with asyncio.timeout(self.request_timeout):
                    store = self.report_conversations if report_headings is not None else self.conversations
                    async with store.session(request) as history:
                        state = await self.graph.ainvoke({'request': request, 'history': list(history),
                            'execution': execution, 'revisions': 0, 'report_headings': report_headings}, config=config)
                        result = AgentResult.model_validate(state['result'])
                        if result.metadata.get('status') in {'complete', 'partial', 'clarification_required'}:
                            scope = state['plan'].objective if state.get('plan') else request.question
                            history.append({'question': request.question[:2000], 'scope': scope[:2000],
                                            'clarification': result.answer[:500] if result.metadata.get('status') == 'clarification_required' else ''})
                        self.last_destination = result.metadata.get('selected_route', 'unrouted')
                        return result
        except PermissionError:
            raise
        except TimeoutError:
            if getattr(execution, 'plan', None) and execution.outcomes:
                result = (execution.collected_sources(execution.plan) if report_headings is not None
                          else await assemble_response(request, execution.plan, execution, None))
                result.metadata.update(ok=False, status='partial' if result.evidence else 'failed')
                result.metadata['limitations'].append('Request deadline exhausted.')
                result.answer += '\n\nRequest deadline exhausted; remaining tasks were stopped.'
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
        agents = {'knowledge': self.knowledge_agent, 'sql': self.analytics_agent,
                  'dashboard': self.dashboard_agent, 'report': self.report_agent}
        if mode not in agents:
            raise ValueError('Unsupported agent mode')
        if mode in {'knowledge', 'sql'}:
            authorize(request, mode)
        agent = agents[mode]
        if agent is None:
            return self._failure('This standalone request type is not supported.')
        if mode == 'sql' and request.conversation_id:
            return await self._run_sql_conversation(request,agent)
        with measure('agent_workflow'):
            result = agent.run(request)
            if inspect.isawaitable(result):
                result = await result
        result = AgentResult.model_validate(result)
        route = 'analytics' if mode == 'sql' else mode
        self.last_destination = route
        return result.model_copy(update={'metadata': {**result.metadata, 'selected_route': route}})

    async def _run_sql_conversation(self, request, agent):
        from core.analytics.metric_mapping import SQLConversationState, PendingSQLQuestion
        token = deadline.set(time.monotonic()+remaining(self.request_timeout))
        try:
            async with asyncio.timeout(remaining()):
                async with self.sql_conversations.session(request) as history:
                    state = SQLConversationState.model_validate_json(history[-1]['sql_state']) if history else SQLConversationState()
                    scoped = request.model_copy(update={'metadata':{**request.metadata,'_sql_context':state.model_dump()}})
                    with measure('agent_workflow'):
                        result = AgentResult.model_validate(await agent.run(scoped))
                    action = result.metadata.pop('_sql_context_action','new')
                    if result.data.get('query_status') == 'executed':
                        state = SQLConversationState.model_validate({'accepted':result.metadata.get('semantic_interpretation')})
                    elif state.pending and action != 'new':
                        combined = state.pending.question+'\nClarification reply: '+request.question
                        if len(combined) <= 2000:
                            state.pending.question = combined
                        state.pending.clarification = result.answer[:1000]
                    else:
                        state.pending = PendingSQLQuestion(question=request.question[:2000],clarification=result.answer[:1000],
                                                           base=state.accepted if action == 'followup' else None)
                    history[:] = [{'sql_state':state.model_dump_json()}]
                self.last_destination = 'analytics'
                return result.model_copy(update={'metadata':{**result.metadata,'selected_route':'analytics'}})
        except TimeoutError:
            return self._failure('The SQL conversation request timed out. Please retry or restate the complete scope.')
        finally:
            deadline.reset(token)

    async def _plan(self, state):
        with measure('routing'):
            plan = await plan_request(state['request'], self._provider(), history=state['history'],
                                      report_headings=state.get('report_headings'))
        state['execution'].plan = plan
        if plan.clarification:
            return {'plan': plan, 'result': AgentResult(answer=plan.clarification, agent='agentic', metadata={
                'ok': False, 'status': 'clarification_required', 'clarification_required': True,
                'selected_route': 'clarification', 'task_trace': []})}
        return {'plan': plan}

    async def _execute(self, state):
        await state['execution'].run(state['plan'])
        return {}

    async def _inspect(self, state):
        execution = state['execution']
        failed = [execution.outcomes[t.id] for t in state['plan'].tasks if t.id in execution.outcomes
                  and execution.outcomes[t.id].status in {'failed', 'empty', 'clarification_required'}]
        return {'revise': bool(failed and state['revisions'] < 1 and execution.invocations < 6
                               and remaining() > 5)}

    async def _revise(self, state):
        execution = state['execution']
        try:
            plan = await plan_request(state['request'], self._provider(), history=state['history'],
                previous=execution.revision_context(state['plan']), report_headings=state.get('report_headings'))
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
        with measure('answer_synthesis'):
            result = (state['execution'].collected_sources(state['plan']) if state.get('report_headings') is not None
                      else await assemble_response(state['request'], state['plan'], state['execution'], self._provider()))
        result.metadata['revisions'] = state['revisions']
        return {'result': result}

    @staticmethod
    def _failure(answer, *, trace=None, error_type=None):
        return AgentResult(answer=answer, agent='agentic', metadata={'ok': False, 'status': 'failed',
            'selected_route': 'unrouted', 'task_trace': trace or [], 'error_type': error_type})

    def _provider(self):
        if self.llm is None:
            sql_agent = getattr(self.analytics_agent, 'sql_agent', None)
            if sql_agent is not None and hasattr(sql_agent, '_provider'):
                return sql_agent._provider()
            from core.llm.groq_provider import GroqProvider
            self.llm = GroqProvider()
            self._owns_llm = True
        return self.llm

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
        if self._owns_llm and self.llm is not None and hasattr(self.llm, 'close'):
            self.llm.close()
