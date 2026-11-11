"""Normalize reviewed invoice.v1 values before publishing them for SQL."""

import re
from datetime import date
from decimal import Decimal


def is_invoice_question(question):
    return bool(re.search(r'\binvoices?\b|h[oó]a\s+đơn|hoá\s+đơn|\binvoice_|\btax_amount\b', question, re.I))


def validate_invoice_currency(tree, error_type):
    """Keep currency visible at each invoice monetary aggregation boundary."""
    from sqlglot import exp
    from sqlglot.optimizer.scope import Scope, traverse_scope
    from core.analytics.join_validation import column_origin

    currency = ('commerce.invoices', 'currency')
    monetary = {('commerce.invoices', name) for name in ('subtotal', 'tax_amount', 'total_amount')}
    monetary |= {('commerce.invoice_items', name) for name in ('amount', 'unit_price')}

    def uses_money(column, scope, visited=()):
        if id(scope) in visited:
            return False
        if column_origin(scope, column) in monetary:
            return True
        source = scope.sources.get(column.table)
        if isinstance(source, Scope):
            projections = [p for p in source.expression.selects if p.alias_or_name == column.name]
            return any(uses_money(c, source, (*visited, id(scope)))
                       for p in projections for c in p.find_all(exp.Column))
        return False

    for scope in traverse_scope(tree):
        aggregates = [node for node in scope.expression.find_all(exp.AggFunc)
                      if node.find_ancestor(exp.Select) is scope.expression
                      and not isinstance(node, exp.Count)]
        if not any(uses_money(col, scope)
                   for agg in aggregates for col in agg.find_all(exp.Column)):
            continue
        group = scope.expression.args.get('group')
        grouped = []
        for node in group.expressions if group else ():
            if isinstance(node, exp.Literal) and node.is_int:
                index = int(node.this) - 1
                node = scope.expression.selects[index].unalias() if 0 <= index < len(scope.expression.selects) else node
            grouped.append(node)
        projected = [node.unalias() for node in scope.expression.selects]
        if not all(any(isinstance(node, exp.Column) and column_origin(scope, node) == currency for node in nodes)
                   for nodes in (grouped, projected)):
            raise error_type('Invoice monetary aggregates must select and GROUP BY invoices.currency.')


def _text(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError('Invoice text fields must be strings or null')
    return value.strip() or None


def _number(value):
    if value is None or value == '':
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError('Invoice numbers must be numeric values or Vietnamese-formatted strings')
    if isinstance(value, str):
        value = value.strip()
        # shortcut: extracted strings use Vietnamese separators; add a format contract for other locales.
        if not re.fullmatch(r'(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?', value):
            raise ValueError('Expected Vietnamese number formatting (1.234,56)')
        value = value.replace('.', '').replace(',', '.')
    number = Decimal(str(value))
    if not number.is_finite() or number < 0:
        raise ValueError('Invoice numbers must be finite and nonnegative')
    return number


def normalize_invoice(data):
    """Return typed header/items; never infer absent amounts, quantities or currency."""
    if not isinstance(data, dict):
        raise ValueError('invoice_data must be an object')
    raw_date = _text(data.get('date'))
    invoice_date = None
    if raw_date:
        match = re.fullmatch(r'(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})', raw_date, re.I)
        match = match or re.fullmatch(r'(\d{1,2})/(\d{1,2})/(\d{4})', raw_date)
        invoice_date = date(int(match[3]), int(match[2]), int(match[1])) if match else date.fromisoformat(raw_date)
    header = {name: _text(data.get(name)) for name in ('invoice_no', 'buyer', 'seller', 'currency')}
    if header['currency']:
        if not re.fullmatch(r'[A-Za-z]{3}', header['currency']):
            raise ValueError('Currency must be a three-letter code or null')
        header['currency'] = header['currency'].upper()
    header.update(invoice_date=invoice_date,
                  **{name: _number(data.get(name)) for name in ('subtotal', 'tax_amount', 'total_amount')})
    raw_items = data.get('items', [])
    if not isinstance(raw_items, list) or any(not isinstance(item, dict) for item in raw_items):
        raise ValueError('Invoice items must be a list of objects')
    items = [dict(line_no=index,
                  **{name: _text(item.get(name)) for name in ('description', 'unit')},
                  **{name: _number(item.get(name)) for name in ('quantity', 'unit_price', 'amount')})
             for index, item in enumerate(raw_items, 1)]
    return header, items
