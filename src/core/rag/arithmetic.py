"""Bounded exact checks for literal arithmetic equalities, never general Python eval."""

import ast
import operator
import re
from fractions import Fraction

from core.reports.grounding import numeric_value

_OPERATORS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
_NUMBER = re.compile(r"(?:\d+(?:[.,]\d+)*|[.,]\d+)")
_RUN = re.compile(r"(?:(?!,\s)[0-9\s.,()+*/×÷=^%−-])+")


def _expression(text):
    if len(text) > 200:
        raise ValueError("arithmetic_budget")
    values = {}

    def replace(match):
        value = numeric_value(match.group())
        if value is None or value[1] or len(values) >= 16:
            raise ValueError("ambiguous_arithmetic_number")
        name = f"n{len(values)}"
        values[name] = Fraction(value[0])
        return name

    normalized = text.translate(str.maketrans({"×": "*", "÷": "/", "−": "-"}))
    tree = ast.parse(_NUMBER.sub(replace, normalized), mode="eval")
    if sum(1 for _ in ast.walk(tree)) > 64:
        raise ValueError("arithmetic_budget")
    return tree, values


def _evaluate(node, values):
    if isinstance(node, ast.Expression):
        return _evaluate(node.body, values)
    if isinstance(node, ast.Name) and node.id in values:
        return values[node.id]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _evaluate(node.operand, values)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_evaluate(node.left, values), _evaluate(node.right, values))
    raise ValueError("unsupported_arithmetic")


def check_equalities(text):
    """Return (number checked, issue); skip comparisons/assignments without arithmetic."""
    checked = 0
    for match in _RUN.finditer(text):
        expression = match.group().strip().rstrip(",.").strip()
        expression = re.sub(r"^[.,]+(?=\s)", "", expression).strip()
        expression = re.sub(r"^\d+[.)]\s+", "", expression)
        if "=" not in expression or not re.search(r"[\d)]\s*[-+*/×÷^%−]", expression):
            continue
        if match.start() and not match.group()[0].isspace() and text[match.start() - 1].isalpha():
            continue
        line_start = text.rfind("\n", 0, match.start()) + 1
        line_end = text.find("\n", match.end())
        line = text[line_start:line_end if line_end >= 0 else len(text)]
        if re.search(r"làm tròn|xấp xỉ|rounded|approximately", line, flags=re.IGNORECASE):
            return checked, "unverified_arithmetic"
        parts = expression.split("=")
        if any(not part.strip() for part in parts):
            return checked, "unsupported_arithmetic"
        try:
            parsed = [_expression(part.strip()) for part in parts]
            if not any(isinstance(node, ast.BinOp) for tree, _ in parsed for node in ast.walk(tree)):
                continue
            values = [_evaluate(tree, numbers) for tree, numbers in parsed]
        except ZeroDivisionError:
            return checked, "invalid_arithmetic"
        except (ValueError, SyntaxError, RecursionError):
            return checked, "unverified_arithmetic"
        checked += 1
        if any(value != values[0] for value in values[1:]):
            return checked, "arithmetic_mismatch"
    return checked, None
