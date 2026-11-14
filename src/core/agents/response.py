"""Combine authorized evidence with stable citations and explicit coverage gaps."""
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from core.agents.runtime import generate
from core.models.agents import AgentResult
from core.prompts.agents import SYNTHESIS_PROMPT
from core.rag.arithmetic import verified_results


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


_MULTIPLIERS = {'tỷ': 10**9, 'tỉ': 10**9, 'triệu': 10**6, 'tr': 10**6, 'nghìn': 10**3, 'ngàn': 10**3, 'k': 10**3}
_SHORTHAND = re.compile(r'(?<![\w.,])(\d+(?:[.,]\d+)?)\s*(tỷ|tỉ|triệu|tr|nghìn|ngàn|k)(\d)?(?!\w)', re.IGNORECASE)
# A unit between operands ('4.000.000 VND + 1.500.000 VND = ...') would otherwise hide the equality.
_UNITS = re.compile(r'(?<=\d)\s*(?:VNĐ|VND|đồng|USD)(?!\w)', re.IGNORECASE)


def _shorthand_amounts(text):
    """'18 triệu' -> 18000000, '4tr5' -> 4500000, so a full amount in the answer matches a shorthand source."""
    amounts = set()
    for number, unit, tail in _SHORTHAND.findall(text):
        scale = _MULTIPLIERS[unit.lower()]
        for options in _number_options(number):
            amounts.update(value * scale + (int(tail) * scale // 10 if tail else 0) for value in options)
    return amounts


def _supported_numbers(answer, inputs, question):
    # Generated specialist prose is not an authority for facts in final synthesis.
    facts = [{'rows': item['data'].get('rows', []),
              'content': [e.get('content') for e in item['evidence']]} for item in inputs]
    source = json.dumps(facts, ensure_ascii=False, default=str) + question
    # Results of equalities that check exactly are derived, not invented; their operands must still be sourced.
    plain = _UNITS.sub('', answer)
    source_numbers = _number_options(source + ' ' + ' '.join(verified_results(plain)))
    allowed = set().union(*source_numbers, _shorthand_amounts(source)) if source_numbers else _shorthand_amounts(source)
    return all(options & allowed for options in _number_options(re.sub(r'\[S\d+\]', '', answer)))


def _null_sql_findings(inputs, question):
    """Explain aggregate NULLs without claiming that they mean zero or no matching rows."""
    sql_items = [item for item in inputs if item['agent'] == 'sql']
    null_columns = set()
    citations = []
    for item in sql_items:
        rows = item['data'].get('rows', [])
        if not rows:
            continue
        citations.extend(e['citation_id'] for e in item['evidence'])
        for column in rows[0]:
            if all(row.get(column) is None for row in rows):
                null_columns.add(column)
    if not null_columns or not citations:
        return None
    refs = ' '.join(f'[{citation}]' for citation in dict.fromkeys(citations))
    columns = ', '.join(sorted(null_columns))
    if re.search(r'[ăâđêôơưáàảãạấầẩẫậắằẳẵặếềểễệốồổỗộớờởỡựứừửữýỳỷỹỵ]', question, re.I):
        return (f"Truy vấn đã chạy nhưng kết quả {columns} là NULL {refs}. "
                "Điều này không đồng nghĩa với doanh thu bằng không; kết quả hiện tại chưa cho biết "
                "không có bản ghi phù hợp hay các bản ghi đều thiếu giá trị này.")
    return (f"The query completed, but {columns} is NULL {refs}. "
            "This does not mean the value is zero; the result does not distinguish "
            "between no matching rows and matching rows with missing values.")


def _scalar_sql_finding(item, question):
    rows = item['data'].get('rows', [])
    if len(rows) != 1:
        return None
    values = [(name, value) for name, value in rows[0].items()
              if value is not None and isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)]
    citations = [e['citation_id'] for e in item['evidence'] if e.get('citation_id')]
    if len(values) != 1 or not citations:
        return None
    column, value = values[0]
    try:
        rendered = format(Decimal(str(value)), ',f')
    except InvalidOperation:
        return None
    refs = ' '.join(f'[{citation}]' for citation in citations)
    parameters = item['data'].get('parameters') or []
    period = ''
    if len(parameters) >= 2:
        try:
            start = date.fromisoformat(str(parameters[0])[:10])
            end = date.fromisoformat(str(parameters[1])[:10])
            if start.day == end.day == 1 and (end.year, end.month) == (
                    start.year + (start.month == 12), start.month % 12 + 1):
                period = f' tháng {start.month} năm {start.year}'
        except ValueError:
            pass
    vietnamese = bool(re.search(r'[ăâđêôơưáàảãạấầẩẫậắằẳẵặếềễệốồổỗộớờởỡứừửữựýỳỷỹỵ]', question, re.I))
    if vietnamese:
        label = {'revenue': 'Doanh thu', 'cogs': 'Giá vốn'}.get(column.casefold(), column)
        return f'{label}{period}: {rendered} {refs}.'
    label = {'revenue': 'Revenue', 'cogs': 'COGS'}.get(column.casefold(), column)
    return f'{label}{period}: {rendered} {refs}.'


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
        scalar_answer = (_scalar_sql_finding(inputs[0], request.question)
                         if inputs[0]['agent'] == 'sql' else None)
        answer = scalar_answer or inputs[0]['answer']
        fallback = False if scalar_answer else bool(usable[0].result.metadata.get('fallback', False))
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
    null_answer = _null_sql_findings(inputs, request.question)
    if null_answer:
        answer, fallback = null_answer, False
    if answer and (not re.search(r'\[S\d+\]', answer)
                   or not set(re.findall(r'\[(S\d+)\]', answer)) <= allowed or '[UNKNOWN]' in answer
                   or not _supported_numbers(answer, inputs, request.question)):
        answer, fallback = '', True
    if not answer:
        blocks = []
        scalar_answer = None
        answer = _null_sql_findings(inputs, plan.objective or request.question)
        for item in inputs:
            refs = ' '.join(f'[{e["citation_id"]}]' for e in item['evidence'])
            if item['agent'] == 'sql':
                if answer:
                    continue
                rows = item['data'].get('rows', [])
                scalar = _scalar_sql_finding(item, request.question)
                if scalar:
                    scalar_answer = scalar
                    blocks.append(scalar)
                    continue
                blocks.append(f'SQL findings {refs}:\n' + json.dumps(rows[:10], ensure_ascii=False, default=str))
                if len(rows) > 10:
                    limitations.append('Answer preview shows the first 10 rows; full returned rows remain in Results.')
            else:
                for source in item['evidence']:
                    excerpt = (source.get('content') or 'See the cited source.')[:1600]
                    blocks.append(f'Document evidence [{source["citation_id"]}]:\n> ' + excerpt.replace('\n', '\n> '))
        if scalar_answer and len(blocks) == 1:
            answer, fallback = scalar_answer, False
        elif blocks:
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
