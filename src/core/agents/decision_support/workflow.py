"""LangGraph state machine for planning and running specialist tasks."""
from __future__ import annotations

import re
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from core.agents.decision_support.execution import Execution, authorize
from core.agents.decision_support.intent_classifier import IntentClassifier
from core.agents.decision_support.response import assemble_response
from core.agents.runtime import remaining
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


class AgentWorkflow:
    def __init__(self, route_selector, *, sql_schema, analytics_agent, route_classifier,
                 plan_requester, planner_provider, response_provider):
        self.route_selector = route_selector
        self.sql_schema = sql_schema
        self.analytics_agent = analytics_agent
        self.route_classifier = route_classifier
        self.plan_requester = plan_requester
        self.planner_provider = planner_provider
        self.response_provider = response_provider

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

    async def run(self, state, *, config=None):
        return await self.graph.ainvoke(state, config=config)

    async def partial_result(self, request, execution, report_headings, forced_plan):
        result = (execution.collected_sources(execution.plan) if report_headings is not None
                  else await assemble_response(request, execution.plan, execution, None))
        result.metadata.update(ok=False, status='partial' if result.evidence else 'failed')
        result.metadata['limitations'].append('Request deadline exhausted.')
        result.answer += '\n\nRequest deadline exhausted; remaining tasks were stopped.'
        if forced_plan is not None:
            result = result.model_copy(update={'agent': 'decision_support', 'metadata': {
                **result.metadata, 'selected_route': 'decision_support'}})
        return result

    async def _plan(self, state):
        with measure('routing'):
            request = state['request']
            plan = state.get('forced_plan')
            route_selection = None
            jev_routed = False
            resumed_clarification = False
            if plan is None:
                from core.agents.decision_support.conversation_context import resolve_clarification_choice

                choice = resolve_clarification_choice(
                    request.metadata.get('clarification_choice'), state['history'])
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
                    route_selection = await self.route_selector.select(
                        request.question, state['history'], self.sql_schema,
                        allow_direct=state.get('report_headings') is None,
                        classifier=self.route_classifier,
                    )
                    if route_selection.agent:
                        task_id = 'k' if route_selection.agent == 'knowledge' else 's'
                        plan = AgentPlan(objective=request.question, fallback=True, tasks=[{
                            'id': task_id, 'agent': route_selection.agent, 'question': request.question}])
                        jev_routed = True
                    else:
                        plan = await self.plan_requester(
                            request, self.planner_provider(), history=state['history'],
                            report_headings=state.get('report_headings'), sql_schema=self.sql_schema,
                            selected_tools=route_selection.selected_tools)
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
                        # Discovery only improves planner context; SQL returns source errors.
                        schema = None
                    live_schema = schema.get('tables') if isinstance(schema, dict) else None
                    if live_schema and live_schema != self.sql_schema and not jev_routed:
                        plan = await self.plan_requester(
                            request, self.planner_provider(), history=state['history'],
                            report_headings=state.get('report_headings'), sql_schema=live_schema,
                            selected_tools=route_selection.selected_tools if route_selection else None)
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
        failed = [execution.outcomes[t.id] for t in state['plan'].tasks if t.id in execution.outcomes
                  and execution.outcomes[t.id].status in {'failed', 'empty'}]
        return {'revise': bool(failed and state['revisions'] < 1 and execution.invocations < 6
                               and remaining() > 5)}

    async def _revise(self, state):
        execution = state['execution']
        try:
            plan = await self.plan_requester(
                state['request'], self.planner_provider(), history=state['history'],
                previous=execution.revision_context(state['plan']),
                report_headings=state.get('report_headings'), sql_schema=self.sql_schema)
            if plan.clarification:
                return {'revisions': 1}
            completed = {key: o for key, o in execution.outcomes.items() if o.status == 'complete'}
            by_id = {task.id: task for task in plan.tasks}
            if any(key not in by_id or by_id[key] != outcome.task for key, outcome in completed.items()):
                return {'revisions': 1}
            if not {task.agent for task in state['plan'].tasks} <= {task.agent for task in plan.tasks}:
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
                                                       self.response_provider()))
        result.metadata['revisions'] = state['revisions']
        if state.get('forced_plan') is not None:
            result = result.model_copy(update={'agent': 'decision_support', 'metadata': {
                **result.metadata, 'selected_route': 'decision_support'}})
        return {'result': result}
