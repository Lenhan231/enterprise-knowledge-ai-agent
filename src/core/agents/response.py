"""Combine authorized evidence with stable citations and explicit coverage gaps."""
import json
import re
from decimal import Decimal, InvalidOperation

from core.agents.runtime import generate
from core.models.agents import AgentResult
from core.prompts.agents import SYNTHESIS_PROMPT


def _number_options(text):
    numbers = []
    for token in re.findall(r'(?<!\w)[+-]?\d+(?:[.,]\d+)*(?:[eE][+-]?\d+)?%?', text):
        token = token.rstrip('%')
        options = set()
        if '.' in token and ',' in token:
            decimal = '.' if token.rfind('.') > token.rfind(',') else ','
            token = token.replace(',' if decimal == '.' else '.', '').replace(decimal, '.')
        elif re.fullmatch(r'[+-]?\d{1,3}(?:[.,]\d{3})+', token):
            options.add(Decimal(token.replace('.', '').replace(',', '')))
        try:
            options.add(Decimal(token.replace(',', '.')))
        except InvalidOperation:
            pass
        numbers.append(options)
    return numbers


def _supported_numbers(answer, inputs, question):
    # Generated specialist prose is not an authority for facts in final synthesis.
    facts = [{'rows': item['data'].get('rows', []),
              'content': [e.get('content') for e in item['evidence']]} for item in inputs]
    source = json.dumps(facts, ensure_ascii=False, default=str) + question
    source_numbers = _number_options(source)
    allowed = set().union(*source_numbers) if source_numbers else set()
    return all(options & allowed for options in _number_options(re.sub(r'\[S\d+\]', '', answer)))


async def assemble_response(request, plan, execution, provider):
    active = [execution.outcomes[t.id] for t in plan.tasks if t.id in execution.outcomes]
    usable = [o for o in active if o.result and o.result.evidence and o.status in {'complete', 'partial'}]
    missing = [o for o in active if o.status != 'complete']
    status = 'complete' if len(active) == len(plan.tasks) and not missing else ('partial' if usable else 'failed')
    if not usable and any(o.status == 'clarification_required' for o in active):
        status = 'clarification_required'
    evidence, inputs, data, limitations = [], [], {}, []
    for task in plan.tasks:
        if task.id not in execution.outcomes:
            limitations.append(f'{task.agent} task {task.id}: incomplete.')
    for outcome in active:
        if outcome.result:
            limitations.extend(outcome.result.metadata.get('limitations', []))
        if outcome.status != 'complete':
            limitations.append(f'{outcome.task.agent} task {outcome.task.id}: {outcome.status}.')
            if outcome.result:
                diagnostic = {key: value for key, value in outcome.result.data.items()
                              if key in {'sql', 'attempted_sql', 'parameters', 'query_status'}}
                if diagnostic:
                    data[outcome.task.agent] = diagnostic
    for outcome in usable:
        result = outcome.result
        mapping, local = {}, []
        for item in result.evidence:
            new_id = f'S{len(evidence) + 1}'
            if item.citation_id:
                mapping[item.citation_id] = new_id
            source = item.model_copy(update={'citation_id': new_id})
            evidence.append(source)
            local.append(source)
        answer = re.sub(r'\[(S\d+)\]', lambda m: f'[{mapping.get(m[1], "UNKNOWN")}]', result.answer)
        inputs.append({'task_id': outcome.task.id, 'agent': outcome.task.agent, 'answer': answer,
                       'data': result.data, 'evidence': [e.model_dump() for e in local]})
        key = outcome.task.agent
        if key in data:
            key = 'task:' + outcome.task.id
        data[key] = result.data
    fallback = True
    answer = ''
    if len(usable) == 1 and len(plan.tasks) == 1 and status == 'complete':
        answer = inputs[0]['answer']
        fallback = bool(usable[0].result.metadata.get('fallback', False))
    elif usable:
        serialized = json.dumps(inputs, ensure_ascii=False, default=str)
        if len(serialized) <= 32_000:
            prompt = SYNTHESIS_PROMPT.format(
                question=request.question,
                objective=plan.objective,
                limitations=json.dumps(limitations, ensure_ascii=False),
                results=serialized,
            )
            try:
                raw = await generate(provider, prompt, timeout=20)
                draft = json.loads(raw.strip().removeprefix('```json').removesuffix('```').strip())
                candidate = draft['answer']
                if not isinstance(candidate, str) or not candidate.strip() or len(candidate) > 8000:
                    raise ValueError('Invalid synthesis')
                cited = set(re.findall(r'\[(S\d+)\]', candidate))
                allowed = {e.citation_id for e in evidence}
                if not cited or not cited <= allowed or set(draft['used_tasks']) != {o.task.id for o in usable}:
                    raise ValueError('Invalid citations or missing task coverage')
                for item in inputs:
                    if not cited.intersection(e['citation_id'] for e in item['evidence']):
                        raise ValueError('Uncited task')
                # This detects invented numeric tokens, not all possible semantic errors.
                if not _supported_numbers(candidate, inputs, request.question):
                    raise ValueError('Unsupported numeric value')
                answer, fallback = candidate.strip(), False
            except Exception:
                pass
    allowed = {e.citation_id for e in evidence}
    if answer and (not re.search(r'\[S\d+\]', answer)
                   or not set(re.findall(r'\[(S\d+)\]', answer)) <= allowed or '[UNKNOWN]' in answer
                   or not _supported_numbers(answer, inputs, request.question)):
        answer, fallback = '', True
    if not answer:
        blocks = []
        for item in inputs:
            refs = ' '.join(f'[{e["citation_id"]}]' for e in item['evidence'])
            if item['agent'] == 'sql':
                rows = item['data'].get('rows', [])
                blocks.append(f'SQL findings {refs}:\n' + json.dumps(rows[:10], ensure_ascii=False, default=str))
                if len(rows) > 10:
                    limitations.append('Answer preview shows the first 10 rows; full returned rows remain in Results.')
            else:
                for source in item['evidence']:
                    excerpt = (source.get('content') or 'See the cited source.')[:1600]
                    blocks.append(f'Document evidence [{source["citation_id"]}]:\n> ' + excerpt.replace('\n', '\n> '))
        if blocks:
            answer = 'Evidence fallback — review the supported findings and gaps below.\n\n' + '\n\n'.join(blocks)
        elif status == 'clarification_required':
            answer = next(o.result.answer for o in active if o.status == 'clarification_required')
        else:
            answer = 'No supported answer could be completed. A task failed or its deadline/evidence budget was exhausted.'
    if limitations:
        answer += '\n\nLimitations: ' + ' '.join(dict.fromkeys(limitations))
    agent_names = {task.agent for task in plan.tasks}
    route = 'hybrid' if len(agent_names) > 1 else ('analytics' if 'sql' in agent_names else 'knowledge')
    return AgentResult(answer=answer, agent=route, evidence=evidence, data=data,
                       metadata={'ok': status == 'complete', 'status': status, 'fallback': fallback,
                                 'limitations': list(dict.fromkeys(limitations)), 'selected_route': route,
                                 'task_trace': execution.trace, 'specialist_invocations': execution.invocations,
                                 'planning_fallback': plan.fallback})
