"""Policy context and bounded request contracts; database permissions remain separate."""
from functools import lru_cache
import copy
from pathlib import Path

import yaml
from sqlglot import exp, parse_one


ROOT = Path(__file__).resolve().parents[3]


@lru_cache(maxsize=1)
def _ontology():
    data = yaml.safe_load((ROOT / 'data/semantic/vietstyle_business_ontology_v1.yaml').read_text(encoding='utf-8'))
    return data


def policy_context(available_sources):
    """Supply only policy entities available to this authorized SQL runtime."""
    data = _ontology()
    available = set(available_sources)
    return copy.deepcopy({
        'policy': data['policy'],
        'entities': {name: entity for name, entity in data['entities'].items() if name in available},
        'relationships': [relation for relation in data['relationships']
                          if relation['from'].rsplit('.', 1)[0] in available
                          and relation['to'].rsplit('.', 1)[0] in available],
        'rules': [{**rule, 'sources': [name for name in rule['sources'] if name in available]}
                  for rule in data['rules'] if not rule['sources'] or available.intersection(rule['sources'])],
        'metric_authority': 'Use the executable metric catalog for formulas and approval status; policy supplies business constraints.'})


def validate_request_contract(sql, contract, parameters=()):
    """A planner contract can constrain output but cannot authorize SQL or new metrics."""
    from core.analytics.text_to_sql import SQLValidationError

    def reject():
        raise SQLValidationError('SQL does not match the requested output contract. Preserve only requested columns and independent measure filters.')

    if (not isinstance(contract, dict) or set(contract) - {'columns', 'dimensions', 'chart_type', 'measure_filters'}):
        reject()
    columns = contract.get('columns')
    if (not isinstance(columns, list) or not 1 <= len(columns) <= 24
            or any(not isinstance(name, str) or not name or len(name) > 128 for name in columns)
            or len(set(columns)) != len(columns)):
        reject()
    dimensions = contract.get('dimensions', [])
    chart_type = contract.get('chart_type')
    if (not isinstance(dimensions, list) or any(not isinstance(name, str) or name not in columns for name in dimensions)
            or chart_type is not None and (not isinstance(chart_type, str) or chart_type not in {'line', 'bar', 'donut', 'table'})):
        reject()
    tree = parse_one(sql, read='postgres')
    projections = {item.alias_or_name: item.unalias() for item in tree.selects}
    if [item.alias_or_name for item in tree.selects] != columns:
        reject()
    filters = contract.get('measure_filters', {})
    if not isinstance(filters, dict) or len(filters) > 24:
        reject()
    for alias, predicate in filters.items():
        if (alias not in projections or not isinstance(predicate, dict)
                or set(predicate) != {'column', 'equals'} or not isinstance(predicate['column'], str)
                or type(predicate['equals']) is not bool):
            reject()
        projection = projections[alias]
        if not isinstance(projection, exp.Filter):
            reject()
        condition = projection.expression
        condition = condition.this if isinstance(condition, exp.Where) else condition
        if isinstance(condition, exp.Column):
            column, value = condition, True
        elif isinstance(condition, (exp.EQ, exp.Is)):
            column, right = condition.this, condition.expression
            value = right.this if isinstance(right, exp.Boolean) else None
            if isinstance(right, exp.Parameter):
                try:
                    index = int(right.this.this)
                    value = parameters[index - 1] if 1 <= index <= len(parameters) else None
                except (ValueError, TypeError, AttributeError):
                    reject()
        else:
            reject()
        if (not isinstance(column, exp.Column) or column.name != predicate['column']
                or type(value) is not bool or value is not predicate['equals']):
            reject()
        where = tree.args.get('where')
        if where and any(column.name == predicate['column'] for column in where.find_all(exp.Column)):
            reject()
