"""Shared deterministic calendar report scope parsing."""
from datetime import date, datetime
from zoneinfo import ZoneInfo
import calendar
import re

_FILTER = re.compile(r'\b(category|region|product|order[_ ]source)\s+["\']([^"\']{1,100})["\']', re.I)
_MONTH_NUMBERS = {name.lower(): month for month in range(1, 13)
                  for name in (calendar.month_name[month], calendar.month_abbr[month])}
_MONTH_TOKEN = '(?:' + '|'.join(_MONTH_NUMBERS) + r')\b'
_MONTH_RANGE = re.compile(
    r'\b(?:(?P<prefix>from|between)\s+)?(?P<start>' + _MONTH_TOKEN + r')\.?(?:\s+(?P<start_year>(?:19|20)\d{2}))?'
    r'\s*(?P<link>to|through|until|and|[-–—])\s*(?P<end>' + _MONTH_TOKEN + r')\.?(?:\s+(?P<end_year>(?:19|20)\d{2}))?')

FINANCIAL_OVERVIEW = r'\b(?:báo cáo tài chính|bao cao tai chinh)\b'
_VI_MONTH = re.compile(r'\b(?:tháng|thang)\s+(0?[1-9]|1[0-2])\b(?:\s+(?:năm|nam)\s+(?=(?:19|20)\d{2}\b))?')
_VI_SCOPE = {
    'tháng này': 'this month', 'tháng trước': 'last month',
    'quý này': 'this quarter', 'quý trước': 'last quarter',
    'năm nay': 'this year', 'năm trước': 'last year', 'năm ngoái': 'last year',
    'mới nhất': 'latest', 'theo tháng': 'monthly', 'theo quý': 'quarterly', 'theo năm': 'yearly',
}


def calendar_text(text):
    text = re.sub(r'\b(?:' + '|'.join(_VI_SCOPE) + r')\b', lambda match: _VI_SCOPE[match[0]], text)
    text = re.sub(r'\b(từ|tu|đến|den|tới|toi)\s+(?=(?:(?:tháng|thang)\s+\d|(?:(?:năm|nam)\s+)?(?:19|20)\d{2}\b))',
                  lambda match: 'from ' if match[1] in {'từ', 'tu'} else 'to ', text)
    text = re.sub(r'\b(from|to)\s+(?:năm|nam)\s+(?=(?:19|20)\d{2}\b)', r'\1 ', text)
    return _VI_MONTH.sub(lambda match: calendar.month_name[int(match[1])].lower() + ' ', text)


def named_month_range(text, today, years, months, quarters):
    match = _MONTH_RANGE.search(text)
    if match is None or match['link'] == 'and' and match['prefix'] != 'between':
        return None
    year = next(iter(years)) if len(years) == 1 else str(today.year)
    start = date(int(match['start_year'] or match['end_year'] or year), _MONTH_NUMBERS[match['start']], 1)
    last = date(int(match['end_year'] or match['start_year'] or year), _MONTH_NUMBERS[match['end']], 1)
    if last < start:
        raise ValueError('The end month must follow the start month; include both years for a cross-year range.')
    if quarters or months - {start.month, last.month} or years - {str(start.year), str(last.year)}:
        raise ValueError('Specify one continuous month range without conflicting periods.')
    return start, month_start(last.year, last.month + 1)


def named_year_range(text, months, quarters):
    match = re.search(r'\b(?:(?P<prefix>from|between)\s+)?(?P<start>(?:19|20)\d{2})\s*'
                      r'(?P<link>to|through|until|and|[-\u2013\u2014])\s*(?P<end>(?:19|20)\d{2})\b', text)
    if match is None or match['link'] == 'and' and match['prefix'] != 'between':
        return None
    if months or quarters or re.findall(r'\b(?:19|20)\d{2}\b', text) != [match['start'], match['end']]:
        raise ValueError('Specify one continuous year range without conflicting periods.')
    if int(match['end']) < int(match['start']):
        raise ValueError('The end year must follow the start year.')
    return date(int(match['start']), 1, 1), date(int(match['end'])+1, 1, 1)


def scope_text(question, *, dimensions=None):
    pattern = _FILTER if dimensions is None else re.compile(r'\b(' + '|'.join(dimensions) + r')\s+["\']([^"\']{1,100})["\']', re.I)
    return calendar_text(pattern.sub(lambda match: match.group(1), question).casefold())


def has_sales_period(question):
    text = scope_text(question)
    months = '|'.join([*calendar.month_name[1:], *calendar.month_abbr[1:]])
    return bool(re.search(r'\b(?:19|20)\d{2}\b|monthly|quarterly|annual|yearly|latest|\bq[1-4]\b|quarter\s+[1-4]|this month|last month|this quarter|last quarter|this year|last year|tháng|quý|\b(?:' + months + r')\b', text, re.I))


def month_start(year, month):
    index = year * 12 + month - 1
    return date(index // 12, index % 12 + 1, 1)


def parse_request(question, *, today=None, latest=None, topic=r'sales?|revenue|doanh thu|bán hàng|' + FINANCIAL_OVERVIEW, dimensions=('category', 'region', 'product', 'order_source')):
    today = today or datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date()
    dimension_pattern = '|'.join(dimensions).replace('order_source', 'order[_ ]source')
    filter_pattern = re.compile(r'\b(' + dimension_pattern + r')\s+["\']([^"\']{1,100})["\']', re.I)
    text = calendar_text(filter_pattern.sub(lambda match: match.group(1), question).casefold())
    if not 3 <= len(text) <= 2000 or not re.search(topic, text):
        raise ValueError('Request a report for the supported topic.')
    years = set(re.findall(r'\b(?:19|20)\d{2}\b', text))
    months = {i for i in range(1, 13) if re.search(r'\b(?:' + calendar.month_name[i].lower() + '|' + calendar.month_abbr[i].lower() + r')\b', text)}
    months.update(int(m) for m in re.findall(r'\btháng\s+(0?[1-9]|1[0-2])\b', text))
    if re.search(r'\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b|\b\d{1,2}[-/]\d{1,2}[-/]\d{4}\b', text):
        raise ValueError('Use a calendar month, quarter, or year rather than a single date.')
    months.update(int(m) for m in re.findall(r'\b(?:19|20)\d{2}[-/](0?[1-9]|1[0-2])\b', text))
    quarters = set(re.findall(r'\b(?:q|quarter\s*|quý\s*)([1-4])\b', text))
    period_range = named_month_range(text, today, years, months, quarters) or named_year_range(text, months, quarters)
    if re.search(r'\b(?:this|last) (?:month|quarter|year)\b', text) and (years or months or quarters):
        raise ValueError('Use either a relative period or an explicit calendar period.')
    if period_range is None and (len(years) > 1 or len(months) > 1 or len(quarters) > 1 or (months and quarters)):
        raise ValueError('Specify one calendar month, quarter, or year.')
    if re.search(r'\b(?:weekly|daily)\b', text) or period_range is None and re.search(r'\b(?:between|from|until|through)\b', text):
        raise ValueError('Use a calendar month, quarter, year, or explicit month or year range with monthly, quarterly, or yearly granularity.')
    grain = ('month' if 'monthly' in text else 'quarter' if re.search(r'quarter|\bq[1-4]\b|quý', text)
             else 'year' if re.search(r'annual|yearly|year report|năm', text) and not months else 'month')
    if 'latest' in text:
        if years or months or quarters:
            raise ValueError('Use either latest or an explicit calendar period.')
        if latest is None:
            raise ValueError('No observed sales date is available for the latest period.')
        today = latest
    year = int(next(iter(years))) if years else today.year
    if not (years or months or quarters or re.search(r'latest|this month|last month|this year|last year|this quarter|last quarter', text)):
        raise ValueError('Include a reporting period, for example May 2026 or 2026.')
    if period_range is not None:
        start, end = period_range
    elif months:
        start = date(year, next(iter(months)), 1)
        end = month_start(start.year, start.month + 1)
    elif quarters:
        start = date(year, (int(next(iter(quarters))) - 1) * 3 + 1, 1)
        end = month_start(start.year, start.month + 3)
    elif re.search(r'\b(?:this|last) quarter\b', text):
        month = (today.month - 1) // 3 * 3 + 1
        start = month_start(today.year, month - (3 if 'last quarter' in text else 0))
        end = month_start(start.year, start.month + 3)
    elif re.search(r'\b(?:this|last) month\b', text):
        start = month_start(today.year, today.month - (1 if 'last month' in text else 0))
        end = month_start(start.year, start.month + 1)
    elif years or 'year' in text or grain == 'year':
        start = date(year - ('last year' in text), 1, 1)
        end = date(start.year + 1, 1, 1)
    else:
        month = (today.month - 1) // 3 * 3 + 1 if grain == 'quarter' else today.month
        start = month_start(today.year, month - (3 if 'last quarter' in text else 1 if 'last month' in text else 0))
        end = month_start(start.year, start.month + (3 if grain == 'quarter' else 1))
    dimensions = re.findall(r'\bby\s+(' + dimension_pattern + r')\b', text)
    if len(set(dimensions)) > 1:
        raise ValueError('Choose one breakdown dimension.')
    if re.search(r'\bby\b', text) and not dimensions:
        raise ValueError('Supported breakdowns: ' + ', '.join(dimensions))
    # shortcut: dimension filters require an explicit quoted value, extend when a reviewed entity resolver is available.
    filters = list(filter_pattern.finditer(question))
    if len(filters) > 1 or re.search(r'\bby\s+(?:' + dimension_pattern + r')\s*(?:and\b|,)' , text):
        raise ValueError('Choose one supported breakdown or quoted dimension filter.')
    unquoted = re.search(r'\b(?:for|in|by)\s+(?:' + dimension_pattern + r')\s+(\w+)' , text)
    if unquoted and unquoted.group(1) not in {'in', 'for', 'during'}:
        raise ValueError('Quote the dimension filter value, for example region "North".')
    filtered = filters[0] if filters else None
    dimension = filtered.group(1).lower().replace(' ', '_') if filtered else dimensions[0].replace(' ', '_') if dimensions else 'all'
    if filtered and dimensions and dimension != dimensions[0].replace(' ', '_'):
        raise ValueError('Choose one dimension for the report.')
    return {'period': {'start': start.isoformat(), 'end_exclusive': end.isoformat()},
            'granularity': grain, 'dimension': dimension,
            'dimension_value': filtered.group(2) if filtered else None}
