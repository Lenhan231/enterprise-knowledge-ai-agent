"""Vietnamese display formatting; source values and SQL remain unchanged."""
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
import re
from zoneinfo import ZoneInfo

VIETNAM = ZoneInfo('Asia/Ho_Chi_Minh')


def format_number(value, *, unit=None, currency=None):
    if value is None or isinstance(value, bool):
        return '—'
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount.adjusted() > 308:
            return '—'
        unit = (unit or '').lower()
        percentage = unit == 'percent' or unit.startswith('fraction')
        if unit.startswith('fraction'):
            amount *= 100
        money = unit.startswith(('currency', 'unknown_currency')) or currency is not None or unit in {'vnd', 'usd', 'eur'}
        digits = 1 if percentage else 0 if money or unit in {'count', 'products', 'orders', 'units', 'sessions', 'rows'} else 2
        with localcontext() as context:
            context.prec = max(28, amount.adjusted() + digits + 3)
            amount = amount.quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)
        if amount == 0:
            amount = abs(amount)
        integer, _, fraction = f'{amount:,.{digits}f}'.partition('.')
        shown = integer.replace(',', '.') + (',' + fraction.rstrip('0') if fraction.rstrip('0') else '')
        return shown + ('%' if percentage else ' ₫' if currency == 'VND' else ' ' + currency if currency else '')
    except (InvalidOperation, ValueError, TypeError, OverflowError):
        return '—'


def format_datetime(value):
    try:
        instant = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=timezone.utc)
        return instant.astimezone(VIETNAM).strftime('%d/%m/%Y %H:%M')
    except (ValueError, TypeError, OverflowError):
        return '—'


def format_value(value, *, unit=None, currency=None):
    if value is None:
        return '—'
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    if isinstance(value, datetime) or isinstance(value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}[T ].+', value):
        return format_datetime(value)
    if isinstance(value, date) or isinstance(value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        try:
            return (value if isinstance(value, date) else date.fromisoformat(value)).strftime('%d/%m/%Y')
        except ValueError:
            return str(value)
    if isinstance(value, (int, float, Decimal)) or isinstance(value, str) and re.fullmatch(r'-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?', value):
        return format_number(value, unit=unit, currency=currency)
    return str(value)


def axis_date(value, granularity):
    try:
        day = date.fromisoformat(str(value)[:10])
        if granularity == 'year':
            return day.strftime('%Y')
        if granularity == 'quarter':
            return f'Q{(day.month-1)//3+1}/{day.year}'
        return day.strftime('%m/%Y' if granularity == 'month' else '%d/%m')
    except ValueError:
        return str(value)
