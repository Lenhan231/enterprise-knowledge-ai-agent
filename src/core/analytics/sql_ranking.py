"""Resolve explicit ranking intent and verify the final SQL ordering by AST."""

from __future__ import annotations

import re
import unicodedata
import math
from dataclasses import dataclass, replace

from sqlglot import exp, parse_one
from sqlglot.optimizer.scope import Scope, traverse_scope

from core.analytics.join_validation import PRIMARY_KEYS
from core.analytics.metric_ontology import get_metric_definition, resolve_metric_names
from core.analytics.sql_validation import SQLValidationError


@dataclass(frozen=True)
class RankingMeasure:
    """Server-resolved metric reference; custom measures never contain SQL text."""

    identity: str
    metric_id: str | None
    source: str | None
    column: str | None
    calculation: str
    approval_status: str
    expression: exp.Expression | None = None


@dataclass(frozen=True)
class RankingIntent:
    entity: str | None
    entity_columns: tuple[tuple[str, str], ...]
    measure: RankingMeasure | None
    direction: str | None
    limit: int | None
    issue: str | None = None
    partition_columns: tuple[tuple[str, str], ...] = ()
    partition_expressions: tuple[exp.Expression, ...] = ()
    partition_entities: tuple[str, ...] = ()
    partition_grains: tuple[str, ...] = ()

    @property
    def resolved(self) -> bool:
        return self.issue is None and self.measure is not None and self.entity is not None

    @property
    def measure_contract_eligible(self) -> bool:
        return self.issue is None and self.measure is None and self.entity is not None and self.direction is not None


_ENTITIES = {
    "customer": {
        "dimension": "customer_id",
        "terms": ("customer", "customers", "customer id", "khách hàng", "người mua"),
        "columns": (("commerce.orders", "customer_id"), ("commerce.customers", "customer_id")),
    },
    "product": {
        "dimension": "product_id",
        "terms": ("product", "products", "product id", "sản phẩm", "mặt hàng"),
        "columns": (("commerce.products", "product_id"), ("commerce.order_items", "product_id"),
                    ("commerce.inventory", "product_id"), ("commerce.returns", "product_id")),
    },
    "order": {
        "dimension": "order_id",
        "terms": ("order", "orders", "order id", "đơn hàng"),
        "columns": (("commerce.orders", "order_id"),),
    },
    "promotion": {
        "dimension": "promo_id",
        "terms": ("promotion", "promotions", "promo", "promo code", "discount code", "discount codes",
                  "mã khuyến mãi", "mã giảm giá"),
        "columns": (("commerce.promotions", "promo_id"), ("commerce.order_items", "promo_id")),
    },
    "category": {
        "dimension": "category",
        "terms": ("category", "categories", "danh mục", "ngành hàng"),
        "columns": (("commerce.products", "category"), ("commerce.inventory", "category")),
    },
    "region": {
        "dimension": "region",
        "terms": ("region", "regions", "khu vực", "vùng"),
        "columns": (("commerce.geography", "region"),),
    },
    "acquisition_channel": {
        "dimension": "acquisition_channel",
        "terms": ("acquisition channel", "customer acquisition channel", "kênh thu hút khách hàng"),
        "columns": (("commerce.customers", "acquisition_channel"),),
    },
    # A recognized but absent entity must fail closed instead of being treated as an ID.
    "dealer": {
        "dimension": "dealer_id",
        "terms": ("dealer", "dealers", "đại lý", "nhà phân phối"),
        "columns": (),
    },
}

_DESCENDING = ("highest", "greatest", "largest", "longest", "most", "maximum", "max", "best",
               "nhiều nhất", "cao nhất", "lớn nhất", "tốt nhất", "đứng đầu")
_ASCENDING = ("lowest", "fewest", "smallest", "shortest", "least", "minimum", "min",
              "ít nhất", "thấp nhất", "nhỏ nhất", "ngắn nhất")
_RANK_MARKERS = ("rank", "ranking", "ranked", "xếp hạng", "sắp xếp theo")
_NUMBER_WORDS = dict(zip(
    "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
    "seventeen eighteen nineteen twenty mot hai ba bon nam sau bay tam chin muoi".split(),
    (*range(1, 21), 1, 2, 3, 4, 5, 6, 7, 8, 9, 10),
))
_NUMBER_PATTERN = r"(?:\d+|" + "|".join(_NUMBER_WORDS) + r")"


def _text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def _has_term(text: str, terms: tuple[str, ...]) -> bool:
    return any(re.search(r"(?<![\w])" + re.escape(term) + r"(?![\w])", text) for term in terms)


def _explicit_limit(text: str, entity: str | None = None) -> int | None:
    number = r"(" + _NUMBER_PATTERN + r")"
    match = re.search(r"\b(?:top|bottom|first|last)\s+" + number + r"\b", text)
    if not match:
        entity_terms = sorted(_ENTITIES[entity]["terms"] if entity else
                              (term for spec in _ENTITIES.values() for term in spec["terms"]),
                              key=len, reverse=True)
        leading_entity = "|".join(re.escape(term) for term in entity_terms)
        match = re.search(
            r"(?<![\w])(?:(?:find|show|list|tìm|lấy|chọn|give|return)\s+)?"
            + number + r"\s+(?:" + leading_entity + r")\b",
            text,
        )
    if not match:
        return None
    value = match[1]
    result = _NUMBER_WORDS.get(value, int(value) if value.isdigit() else 0)
    return result if 1 <= result <= 200 else None


def _has_entity_count(text: str, entity: str) -> bool:
    terms = sorted(_ENTITIES[entity]["terms"], key=len, reverse=True)
    pattern = r"(?<![\w])" + _NUMBER_PATTERN + r"\s+(?:"
    return bool(re.search(pattern + "|".join(re.escape(term) for term in terms) + r")\b", text))


def _directions(text: str) -> tuple[bool, bool]:
    descending_terms = tuple(term for term in _DESCENDING if term != "max")
    ascending_terms = tuple(term for term in _ASCENDING if term != "min")
    value_descending = (_has_term(text, descending_terms)
                        or bool(re.search(r"\bmax\b(?!\s*\()", text))
                        or bool(re.search(r"\bnhiều(?:\s+\w+){0,2}\s+nhất\b", text)))
    value_ascending = (_has_term(text, ascending_terms)
                       or bool(re.search(r"\bmin\b(?!\s*\()", text))
                       or bool(re.search(r"\bít(?:\s+\w+){0,2}\s+nhất\b", text)))
    top = _has_term(text, ("top", "first"))
    bottom = _has_term(text, ("bottom", "last"))
    descending = value_descending or (top and not value_ascending)
    ascending = value_ascending or (bottom and not value_descending)
    return ascending, descending


def _measure_for(text: str, entity: str, metrics: set[str]) -> RankingMeasure | None:
    quantity_ratio = _has_term(text, ("ratio", "rate", "percentage", "percent", "tỷ lệ", "tỉ lệ", "phần trăm"))
    if entity == "promotion" and _has_term(text, ("revenue", "sales", "doanh thu")):
        return RankingMeasure(
            identity="promotion_net_item_revenue", metric_id=None, source="commerce.order_items",
            column=None, calculation="sum_order_item_net", approval_status="unverified",
        )

    if (not metrics and not quantity_ratio and _has_term(text, ("unit", "units", "quantity", "số lượng"))
            and _has_term(text, ("return", "returned", "refund", "trả hàng", "hoàn hàng", "bị trả"))):
        return RankingMeasure(
            identity="sum:commerce.returns.return_quantity", metric_id=None,
            source="commerce.returns", column="return_quantity", calculation="sum_column",
            approval_status="unverified",
        )

    if (not metrics and not quantity_ratio and _has_term(text, ("unit", "units", "quantity", "số lượng"))
            and _has_term(text, ("buy", "buys", "bought", "purchase", "purchased", "mua", "sell", "sold", "bán"))):
        return RankingMeasure(
            identity="sum:commerce.order_items.quantity", metric_id=None,
            source="commerce.order_items", column="quantity", calculation="sum_column",
            approval_status="unverified",
        )

    if len(metrics) == 1:
        metric_id = next(iter(metrics))
        definition = get_metric_definition(metric_id)
        approved_for_dimension = _ENTITIES[entity]["dimension"] in definition.get("dimensions", ())
        return RankingMeasure(
            identity=metric_id, metric_id=metric_id, source=None, column=None,
            calculation="catalog_metric",
            approval_status=(str(definition.get("approval_status", "catalogued"))
                             if approved_for_dimension else "unverified"),
        )
    if metrics:
        return None

    return None


def _ranking_metric(text: str, metrics: set[str]) -> tuple[str | None, int | None]:
    """Pick the metric named nearest the ranking direction when a request has several metrics."""
    if len(metrics) == 1:
        metric_id = next(iter(metrics))
        definition = get_metric_definition(metric_id)
        terms = (*definition.get("aliases", ()), metric_id.replace("_", " "))
        positions = [
            match.start()
            for term in terms
            for match in re.finditer(r"(?<![\w])" + re.escape(term) + r"(?![\w])", text)
        ]
        return metric_id, min(positions) if positions else None
    if not metrics:
        return None, None
    ranked_by = re.search(r"\b(?:by|according\s+to|ranked\s+by|theo)\s+(.+?)(?:[,.;!?]|$)", text)
    if ranked_by:
        clause = ranked_by.group(1)
        clause_hits = []
        for metric_id in metrics:
            definition = get_metric_definition(metric_id)
            terms = (*definition.get("aliases", ()), metric_id.replace("_", " "))
            if any(re.search(r"(?<![\w])" + re.escape(term) + r"(?![\w])", clause) for term in terms):
                clause_hits.append(metric_id)
        if len(clause_hits) == 1:
            metric_id = clause_hits[0]
            return metric_id, ranked_by.start(1)
        if clause_hits:
            return None, None
    direction_terms = (*_DESCENDING, *_ASCENDING)
    direction_positions = [
        match.start()
        for term in direction_terms
        for match in re.finditer(r"(?<![\w])" + re.escape(term) + r"(?![\w])", text)
        if not (term in {"max", "min"} and re.match(r"\s*\(", text[match.end():]))
    ]
    if not direction_positions:
        return None, None
    direction_pos = min(direction_positions)
    hits = []
    for metric_id in metrics:
        definition = get_metric_definition(metric_id)
        terms = (*definition.get("aliases", ()), metric_id.replace("_", " "))
        for term in terms:
            match = re.search(r"(?<![\w])" + re.escape(term) + r"(?![\w])", text)
            if match and match.start() < direction_pos:
                hits.append((match.start(), len(term), metric_id))
    if not hits:
        return None, None
    position, length = max((position, length) for position, length, _ in hits)
    best_metrics = {metric_id for hit_position, hit_length, metric_id in hits
                    if (hit_position, hit_length) == (position, length)}
    if len(best_metrics) != 1:
        return None, None
    metric_id = next(iter(best_metrics))
    return metric_id, position


def _entity_mentions(text: str) -> list[tuple[int, int, str]]:
    mentions = []
    for name, spec in _ENTITIES.items():
        positions = [
            (match.start(), match.end())
            for term in spec["terms"]
            for match in re.finditer(r"(?<![\w])" + re.escape(term) + r"(?![\w])", text)
        ]
        mentions.extend((start, end, name) for start, end in positions)
    return sorted(mentions)


def _target_entity(text: str, mentions: list[tuple[int, int, str]], metric_pos: int | None) -> str | None:
    selector = re.compile(
        r"^\s*(?:(?:find|show|list|tìm|lấy|cho tôi)\s+)?"
        r"(?:(?:top|bottom|first|last)\s+)?(?:" + _NUMBER_PATTERN + r"\s+)?$"
    )
    subjects = []
    for start, end, entity in mentions:
        prefix = text[:start]
        suffix = text[end:]
        count_before = re.search(_NUMBER_PATTERN + r"\s+$", prefix)
        if (selector.fullmatch(prefix) or count_before
                or re.match(r"^\s*(?:\([^)]*\)\s*)?(?:nào|who|which|with|that|có|has|have)\b", suffix)):
            subjects.append((start, entity))
    if subjects:
        return min(subjects)[1]

    before_measure = [mention for mention in mentions if metric_pos is not None and mention[0] < metric_pos]
    if before_measure:
        return max(before_measure)[2]
    return mentions[0][2] if len({mention[2] for mention in mentions}) == 1 and mentions else None


def _partition_columns(text: str, mentions: list[tuple[int, int, str]], entity: str):
    columns = []
    for mentioned_entity in _partition_entities(text, mentions, entity):
        columns.extend(_ENTITIES[mentioned_entity]["columns"])
    return tuple(dict.fromkeys(columns))


def _partition_entities(text: str, mentions: list[tuple[int, int, str]], entity: str) -> tuple[str, ...]:
    entities = []
    for start, _, mentioned_entity in mentions:
        if mentioned_entity == entity:
            continue
        prefix = text[:start]
        each_group = re.search(r"\b(?:in|within|for|per)\s+(?:each|every)\s+$", prefix)
        each_group_vi = re.search(r"(?:ở|trong|theo)\s+(?:từng|mỗi)\s+$", prefix)
        if each_group or each_group_vi:
            entities.append(mentioned_entity)
    return tuple(dict.fromkeys(entities))


_TIME_PARTITION_PATTERNS = {
    "day": r"(?:per|each|every|in each|within each|for each)\s+(?:calendar\s+)?days?|(?:từng|mỗi)\s+ngày",
    "week": r"(?:per|each|every|in each|within each|for each)\s+(?:calendar\s+)?weeks?|(?:từng|mỗi)\s+tuần",
    "month": r"(?:per|each|every|in each|within each|for each)\s+(?:calendar\s+)?months?|(?:từng|mỗi)\s+tháng|monthly\s+(?:top|bottom|rank)",
    "quarter": r"(?:per|each|every|in each|within each|for each)\s+(?:calendar\s+)?quarters?|(?:từng|mỗi)\s+quý",
    "year": r"(?:per|each|every|in each|within each|for each)\s+(?:calendar\s+)?years?|(?:từng|mỗi)\s+năm",
}


def _partition_grains(text: str) -> tuple[str, ...]:
    return tuple(grain for grain, pattern in _TIME_PARTITION_PATTERNS.items()
                 if re.search(r"(?<![\w])(?:" + pattern + r")(?![\w])", text))


def _has_explicit_measure_request(text: str) -> bool:
    """Require a measure cue before a model contract can fill an unknown ranking metric."""
    if re.search(r"\b(?:ratio|rate|percentage|percent|share)\b|(?:tỷ lệ|tỉ lệ|phần trăm)", text):
        return True
    if re.search(
        r"\b(?:most|least|highest|lowest|greatest|smallest)\s+(?:[\w-]+\s+){0,3}"
        r"(?:units?|quantity|volume|amount|value|margin|rate|score|profitability)\b",
        text,
    ):
        return True
    if re.search(
        r"\b(?:paid|pay(?:s|ing)?|payment|spent|spend(?:s|ing)?)\b.*\b(?:money|amount|value)\b|"
        r"\b(?:money|amount|value)\b.*\b(?:paid|pay(?:s|ing)?|payment|spent|spend(?:s|ing)?)\b|"
        r"\b(?:trả|thanh toán|chi tiêu)\b.*\b(?:tiền|giá trị|số tiền)\b|"
        r"\b(?:tiền|giá trị|số tiền)\b.*\b(?:trả|thanh toán|chi tiêu)\b",
        text,
    ):
        return True

    clause = re.search(r"\b(?:by|theo)\s+(.+?)(?:[,.;!?]|$)", text)
    if not clause:
        return False
    requested = clause.group(1).strip()
    dimensions = tuple(term for spec in _ENTITIES.values() for term in spec["terms"])
    time_terms = (
        "day", "days", "daily", "week", "weeks", "weekly", "month", "months", "monthly",
        "quarter", "quarters", "year", "years", "yearly", "ngày", "tuần", "tháng", "quý", "năm",
    )
    grouping_prefixes = tuple(sorted((*dimensions, *time_terms), key=len, reverse=True))
    excluded = r"(?:each|every|per|từng|mỗi)\s+|" + "|".join(re.escape(term) for term in grouping_prefixes)
    return not re.match(r"^(?:" + excluded + r")\b", requested)


def _ranking_request(question: str) -> tuple[str, bool, bool, bool]:
    text = _text(question)
    # "most recent" describes a date request, not the greatest entity value.
    text = text.replace("most recent", " ").replace("most recently", " ")
    ascending, descending = _directions(text)
    return text, ascending, descending, ascending or descending or _has_term(text, _RANK_MARKERS)


def has_ranking_request(question: str) -> bool:
    """Retain the generic ranking cue when structured intent extraction cannot resolve it."""
    return _ranking_request(question)[3]


def resolve_ranking_intent(question: str) -> RankingIntent | None:
    """Resolve simple explicit top/bottom requests; preserve unknown intent as unresolved."""
    text, ascending, descending, ranking = _ranking_request(question)
    if not ranking:
        return None

    metrics = resolve_metric_names(question)
    entity_mentions = _entity_mentions(text)
    ranking_metric, metric_pos = _ranking_metric(text, metrics)

    direction = "asc" if ascending else "desc" if descending else None
    explicit_limit = _explicit_limit(text)
    limit = explicit_limit if explicit_limit is not None else 1
    if ascending and descending:
        return RankingIntent(None, (), None, None, limit, "The request contains conflicting ranking directions.")
    entity = _target_entity(text, entity_mentions, metric_pos)
    if entity is None:
        return RankingIntent(None, (), None, direction, limit,
                             "Specify one supported entity to rank.")
    explicit_limit = _explicit_limit(text, entity)
    limit = explicit_limit if explicit_limit is not None else 1
    partition_columns = _partition_columns(text, entity_mentions, entity)
    partition_entities = _partition_entities(text, entity_mentions, entity)
    partition_grains = _partition_grains(text)
    measure_metrics = {ranking_metric} if ranking_metric else metrics
    measure = _measure_for(text, entity, measure_metrics)
    if not _ENTITIES[entity]["columns"]:
        issue = f"The schema has no approved identity column for {entity}."
    elif direction is None:
        issue = "Specify whether the ranking should be highest or lowest."
    elif explicit_limit is None and (
            re.search(r"\b(?:top|bottom|first|last)\b", text)
            or _has_entity_count(text, entity)):
        issue = "The requested ranking limit must be between 1 and 200."
    elif len(metrics) > 1 and ranking_metric is None:
        issue = "Specify one business measure for the ranking."
    elif measure is None and not _has_explicit_measure_request(text):
        issue = "Specify the business measure to rank."
    else:
        issue = None
    return RankingIntent(entity, _ENTITIES[entity]["columns"], measure, direction, limit, issue,
                         partition_columns, (), partition_entities, partition_grains)


def complete_ranking_intent(intent: RankingIntent | None, contract, table_columns) -> RankingIntent:
    """Decode a model-supplied ranking description using only catalog IDs and schema fields."""
    if (not isinstance(contract, dict)
            or set(contract) != {"entity", "measure", "direction", "limit", "partition_by"}):
        _raise_sql_validation("A ranking query needs a complete typed ranking_contract.")

    entity = contract["entity"]
    if not isinstance(entity, str) or entity not in _ENTITIES or not _ENTITIES[entity]["columns"]:
        _raise_sql_validation("The ranking contract names an unsupported entity identity.")
    direction = contract["direction"]
    if not isinstance(direction, str) or direction not in {"asc", "desc"}:
        _raise_sql_validation("The ranking contract direction must be asc or desc.")
    limit = contract["limit"]
    if type(limit) is not int or not 1 <= limit <= 200:
        _raise_sql_validation("The ranking contract limit must be between 1 and 200.")

    partition_names = contract["partition_by"]
    if not isinstance(partition_names, list) or len(partition_names) > 5:
        _raise_sql_validation("The ranking contract partition dimensions are invalid.")
    partition_columns = []
    partition_expressions = []
    partition_tokens = set()
    contract_partition_entities = []
    contract_partition_grains = []
    contract_field_columns = []
    for dimension in partition_names:
        if isinstance(dimension, str) and dimension in _ENTITIES:
            if dimension == entity:
                _raise_sql_validation("The ranking contract partition cannot repeat its ranked entity.")
            columns = _ENTITIES[dimension]["columns"]
            if not columns:
                _raise_sql_validation("The ranking contract partition dimension has no approved identity.")
            tokens = {(table, column, None) for table, column in columns}
            if partition_tokens & tokens:
                _raise_sql_validation("The ranking contract partition dimensions must be unique.")
            partition_tokens.update(tokens)
            contract_partition_entities.append(dimension)
            for table, column in columns:
                partition_columns.append((table, column))
                partition_expressions.append(exp.column(column, table=table.rsplit(".", 1)[-1], db="commerce"))
        elif isinstance(dimension, dict) and set(dimension) in (
                {"source", "column"}, {"source", "column", "date_part"}):
            source, column = dimension["source"], dimension["column"]
            date_part = dimension.get("date_part")
            if (not isinstance(source, str) or source not in table_columns
                    or not isinstance(column, str) or column not in table_columns[source]
                    or (date_part is not None and (
                        not isinstance(date_part, str)
                        or date_part not in {"day", "week", "month", "quarter", "year"}
                    ))):
                _raise_sql_validation("The ranking partition must use an approved schema dimension.")
            token = (source, column, date_part)
            if token in partition_tokens:
                _raise_sql_validation("The ranking contract partition dimensions must be unique.")
            if date_part is None and any(existing[:2] == token[:2] for existing in partition_tokens):
                _raise_sql_validation("The ranking contract partition dimensions must be unique.")
            partition_tokens.add(token)
            partition_columns.append((source, column))
            schema, table = source.split(".", 1)
            reference = exp.column(column, table=table, db=schema)
            if date_part is None:
                partition_expressions.append(reference)
                matching_entities = [
                    name for name, spec in _ENTITIES.items()
                    if (source, column) in spec["columns"]
                ]
                if matching_entities:
                    contract_partition_entities.extend(matching_entities)
                else:
                    contract_field_columns.append((source, column))
            else:
                contract_partition_grains.append(date_part)
                partition_expressions.append(exp.Cast(
                    this=exp.TimestampTrunc(this=reference, unit=exp.Var(this=date_part.upper())),
                    to=exp.DataType.build("DATE"),
                ))
        else:
            _raise_sql_validation("The ranking contract partition dimensions are invalid.")
    partition_columns = tuple(dict.fromkeys(partition_columns))
    if set(partition_columns) & set(_ENTITIES[entity]["columns"]):
        _raise_sql_validation("The ranking contract partition cannot repeat the ranked entity.")
    for table, column in (*_ENTITIES[entity]["columns"], *partition_columns):
        if table not in table_columns or column not in table_columns[table]:
            _raise_sql_validation(f"The ranking identity {table}.{column} is unavailable in the approved schema.")

    measure_contract = contract["measure"]
    if not isinstance(measure_contract, dict):
        _raise_sql_validation("The ranking contract measure must be a typed object.")
    if set(measure_contract) == {"metric_id"}:
        metric_id = measure_contract["metric_id"]
        try:
            definition = get_metric_definition(metric_id)
        except (KeyError, TypeError, ValueError) as error:
            _raise_sql_validation("The ranking contract references an unknown canonical metric.")
        approved = _ENTITIES[entity]["dimension"] in definition.get("dimensions", ())
        measure = RankingMeasure(
            identity=metric_id, metric_id=metric_id, source=None, column=None,
            calculation="catalog_metric",
            approval_status=str(definition.get("approval_status", "catalogued")) if approved else "unverified",
        )
    elif set(measure_contract) == {"source", "column", "aggregation"}:
        source, column, aggregation = (
            measure_contract["source"], measure_contract["column"], measure_contract["aggregation"]
        )
        calculations = {
            "sum": "sum_column", "avg": "avg_column", "min": "min_column", "max": "max_column",
            "count": "count_column", "count_distinct": "count_distinct_column",
        }
        if (not isinstance(source, str) or source not in table_columns
                or not isinstance(column, str) or column not in table_columns[source]
                or not isinstance(aggregation, str)
                or aggregation not in calculations):
            _raise_sql_validation("The ranking measure must use an approved source column and aggregation.")
        measure = RankingMeasure(
            identity=f"{aggregation}:{source}.{column}", metric_id=None,
            source=source, column=column, calculation=calculations[aggregation],
            approval_status="unverified",
        )
    elif set(measure_contract) == {"aggregation", "expression"}:
        aggregation = measure_contract["aggregation"]
        calculations = {
            "sum": "formula_sum", "avg": "formula_avg", "min": "formula_min",
            "max": "formula_max", "count": "formula_count",
            "count_distinct": "formula_count_distinct",
        }
        if not isinstance(aggregation, str) or aggregation not in calculations:
            _raise_sql_validation("The ranking formula aggregation is unsupported.")
        expression = _decode_measure_expression(measure_contract["expression"], table_columns)
        identity = f"{aggregation}:{expression.sql(dialect='postgres', normalize=True)}"
        measure = RankingMeasure(
            identity=identity, metric_id=None, source=None, column=None,
            calculation=calculations[aggregation], approval_status="unverified",
            expression=expression,
        )
    else:
        _raise_sql_validation("The ranking measure contract contains unsupported fields.")

    if intent is not None:
        if intent.entity and entity != intent.entity:
            _raise_sql_validation("The ranking contract changed the requested entity.")
        if intent.direction and direction != intent.direction:
            _raise_sql_validation("The ranking contract changed the requested direction.")
        if intent.limit and limit != intent.limit:
            _raise_sql_validation("The ranking contract changed the requested TOP-N limit.")
        if set(contract_partition_entities) != set(intent.partition_entities):
            _raise_sql_validation("The ranking contract changed the requested per-group partition.")
        if set(contract_partition_grains) != set(intent.partition_grains):
            _raise_sql_validation("The ranking contract changed the requested time partition.")
        if contract_field_columns:
            _raise_sql_validation("The ranking contract contains a partition dimension not resolved from the request.")
        if intent.measure and measure.identity != intent.measure.identity:
            _raise_sql_validation("The ranking contract changed the requested business measure.")
        return replace(intent, measure=measure, partition_columns=partition_columns,
                       partition_expressions=tuple(partition_expressions))

    return RankingIntent(
        entity=entity, entity_columns=_ENTITIES[entity]["columns"], measure=measure,
        direction=direction, limit=limit, issue=None, partition_columns=partition_columns,
        partition_expressions=tuple(partition_expressions),
    )


def _raise_sql_validation(message: str):
    from core.analytics.text_to_sql import SQLValidationError
    raise SQLValidationError(message)


def _decode_measure_expression(node, table_columns, *, depth=0, budget=None) -> exp.Expression:
    """Build a small arithmetic AST from schema-bound references, never from SQL text."""
    if budget is None:
        budget = [0]
    budget[0] += 1
    if budget[0] > 31 or depth > 8 or not isinstance(node, dict):
        _raise_sql_validation("The ranking formula is malformed or exceeds its size limit.")
    if set(node) == {"source", "column"}:
        source, column = node["source"], node["column"]
        if (not isinstance(source, str) or source not in table_columns
                or not isinstance(column, str) or column not in table_columns[source]):
            _raise_sql_validation("The ranking formula must reference only approved schema columns.")
        schema, table = source.split(".", 1)
        return exp.column(column, table=table, db=schema)
    if set(node) == {"value"}:
        value = node["value"]
        if (type(value) not in {int, float} or len(str(value)) > 32
                or (isinstance(value, float) and not math.isfinite(value))):
            _raise_sql_validation("The ranking formula numeric operand is invalid.")
        return exp.Literal.number(str(value))
    if (set(node) != {"op", "left", "right"}
            or not isinstance(node["op"], str)
            or node["op"] not in {"add", "sub", "mul", "div"}):
        _raise_sql_validation("The ranking formula supports only typed columns and binary arithmetic.")
    left = _decode_measure_expression(node["left"], table_columns, depth=depth + 1, budget=budget)
    right = _decode_measure_expression(node["right"], table_columns, depth=depth + 1, budget=budget)
    operators = {"add": exp.Add, "sub": exp.Sub, "mul": exp.Mul, "div": exp.Div}
    return operators[node["op"]](this=left, expression=right)


def _unaliased(expression: exp.Expression) -> exp.Expression:
    return expression.this if isinstance(expression, exp.Alias) else expression


def _projected_order_expression(ordered: exp.Ordered, select: exp.Select) -> exp.Expression:
    expression = ordered.this
    if isinstance(expression, exp.Literal) and expression.is_int:
        index = int(expression.this) - 1
        if not 0 <= index < len(select.selects):
            _raise_sql_validation("Ranking ORDER BY position is outside the final SELECT list.")
        return _unaliased(select.selects[index])
    if isinstance(expression, exp.Column) and not expression.table and not expression.db:
        matches = [item for item in select.selects if item.alias_or_name.casefold() == expression.name.casefold()]
        if len(matches) == 1:
            return _unaliased(matches[0])
    return _unaliased(expression)


def _canonical(expression: exp.Expression, scope, table_columns):
    from core.analytics.metric_validation import _canonical as canonicalize

    def resolve_unqualified(node):
        if not isinstance(node, exp.Column) or node.table or node.db:
            return node
        candidates = {}
        for alias, (_, source) in scope.selected_sources.items():
            if isinstance(source, Scope):
                exposed = any(
                    projection.alias_or_name.casefold() == node.name.casefold()
                    for projection in source.expression.selects
                )
            elif isinstance(source, exp.Table) and source.db:
                exposed = node.name.casefold() in table_columns.get(
                    f"{source.db.casefold()}.{source.name.casefold()}", ()
                )
            else:
                exposed = False
            if exposed:
                candidates[id(source)] = alias
        if len(candidates) != 1:
            _raise_sql_validation(
                f"Ranking semantics are inconclusive for ambiguous unqualified column {node.name}."
            )
        return exp.column(node.name, table=next(iter(candidates.values())))

    try:
        qualified = _unaliased(expression).copy().transform(resolve_unqualified)
        return canonicalize(qualified, scope, (), {})
    except Exception as error:
        _raise_sql_validation("Ranking semantics are inconclusive for this SQL scope: " + str(error)[:240])


def _canonical_partition(expression: exp.Expression, scope, table_columns):
    try:
        value = _canonical(expression, scope, table_columns)
    except Exception:
        # A schema-bound expected partition may sit outside a CTE's visible aliases.
        # Keep its fully qualified expression; the SQL-side expression still must
        # resolve through its actual scope and compare equal to it.
        if not all(column.db and column.table for column in expression.find_all(exp.Column)):
            raise
        value = expression.copy()
    # DATE_TRUNC buckets remain equivalent when SQL casts their timestamp to DATE.
    if (isinstance(value, exp.Cast) and isinstance(value.this, exp.TimestampTrunc)
            and value.args.get("to") and value.args["to"].this == exp.DataType.Type.DATE):
        return value.this
    return value


def _expected_partitions(intent: RankingIntent, scope, table_columns):
    expressions = intent.partition_expressions or tuple(
        exp.column(column, table=table.rsplit(".", 1)[-1], db="commerce")
        for table, column in intent.partition_columns
    )
    return {_canonical_partition(expression, scope, table_columns) for expression in expressions}


def _expected_expression(intent: RankingIntent, table_columns) -> exp.Expression:
    measure = intent.measure
    if measure.metric_id:
        from core.analytics.metric_validation import _formula
        try:
            return _formula(get_metric_definition(measure.metric_id), table_columns)
        except Exception as error:
            _raise_sql_validation("Ranking metric formula could not be established: " + str(error)[:240])
    if measure.calculation.endswith("_column"):
        table = measure.source.rsplit(".", 1)[-1]
        column = exp.column(measure.column, table=table, db="commerce")
        if measure.calculation == "sum_column":
            return exp.Sum(this=column)
        if measure.calculation == "avg_column":
            return exp.Avg(this=column)
        if measure.calculation == "min_column":
            return exp.Min(this=column)
        if measure.calculation == "max_column":
            return exp.Max(this=column)
        if measure.calculation == "count_column":
            return exp.Count(this=column, big_int=True)
        if measure.calculation == "count_distinct_column":
            return exp.Count(this=exp.Distinct(expressions=[column]), big_int=True)
    if measure.calculation.startswith("formula_") and measure.expression is not None:
        expression = measure.expression.copy()
        aggregation = measure.calculation.removeprefix("formula_")
        if aggregation == "sum":
            return exp.Sum(this=expression)
        if aggregation == "avg":
            return exp.Avg(this=expression)
        if aggregation == "min":
            return exp.Min(this=expression)
        if aggregation == "max":
            return exp.Max(this=expression)
        if aggregation == "count":
            return exp.Count(this=expression, big_int=True)
        if aggregation == "count_distinct":
            return exp.Count(this=exp.Distinct(expressions=[expression]), big_int=True)
    if measure.calculation == "sum_order_item_net":
        table = "order_items"
        return exp.Sum(this=exp.Sub(
            this=exp.Mul(this=exp.column("quantity", table=table, db="commerce"),
                         expression=exp.column("unit_price", table=table, db="commerce")),
            expression=exp.column("discount_amount", table=table, db="commerce"),
        ))
    _raise_sql_validation("Ranking measure has no verifiable expression.")


def _scope_projection(scope: Scope, name: str):
    projections = [projection for projection in scope.expression.selects
                   if projection.alias_or_name.casefold() == name.casefold()]
    return projections[0] if len(projections) == 1 else None


def _column_flows_through(column: exp.Column, scope: Scope, target: Scope, seen=None) -> bool:
    """Resolve a projected column through CTEs to a specific ranking result scope."""
    if seen is None:
        seen = set()
    marker = (id(scope.expression), column.table.casefold(), column.name.casefold())
    if marker in seen:
        return False
    seen.add(marker)

    if column.table:
        source = scope.sources.get(column.table.casefold())
    else:
        sources = {
            id(source): source
            for _, source in scope.selected_sources.values()
            if isinstance(source, Scope) and _scope_projection(source, column.name) is not None
        }
        source = next(iter(sources.values())) if len(sources) == 1 else None

    if source is target:
        return _scope_projection(target, column.name) is not None
    if not isinstance(source, Scope):
        return False
    projection = _scope_projection(source, column.name)
    if projection is None:
        return False
    projected_expression = _unaliased(projection)
    columns = list(projected_expression.find_all(exp.Column))
    return bool(columns) and all(_column_flows_through(item, source, target, seen.copy()) for item in columns)


def _expression_flows_through(expression: exp.Expression, scope: Scope, target: Scope) -> bool:
    columns = list(expression.find_all(exp.Column))
    return bool(columns) and all(_column_flows_through(column, scope, target) for column in columns)


def _window_rank_alias(tree, final_scope, reachable, intent, expected, table_columns) -> str | None:
    candidates = []
    for scope in reachable:
        select = scope.expression
        for projection in select.selects:
            alias = projection.alias_or_name
            if not alias:
                continue
            for window in _unaliased(projection).find_all(exp.Window):
                if not isinstance(window.this, (exp.Rank, exp.DenseRank, exp.RowNumber)):
                    continue
                order = window.args.get("order")
                if not order or not order.expressions:
                    continue
                primary = order.expressions[0]
                if bool(primary.args.get("desc")) != (intent.direction == "desc"):
                    continue
                actual = _canonical(_projected_order_expression(primary, select), scope, table_columns)
                try:
                    expected_in_scope = _canonical(expected, scope, table_columns)
                except SQLValidationError:
                    # A downstream CTE can expose the complete canonical measure
                    # even when its underlying fact tables are no longer in scope.
                    expected_in_scope = expected
                actual_partition = {
                    _canonical_partition(item, scope, table_columns)
                    for item in (window.args.get("partition_by") or ())
                }
                expected_partition = _expected_partitions(intent, scope, table_columns)
                if actual_partition != expected_partition:
                    _raise_sql_validation(
                        "The window ranking partition does not match the requested grouping."
                    )
                if actual == expected_in_scope:
                    candidates.append((alias.casefold(), scope))

    if not candidates:
        return None
    entity_expressions = [
        exp.column(column, table=table.rsplit(".", 1)[-1], db="commerce")
        for table, column in intent.entity_columns
    ]
    final_entity_projections = []
    final_measure_projections = []
    for projection in tree.selects:
        try:
            canonical = _canonical(_unaliased(projection), final_scope, table_columns)
        except Exception:
            continue
        if canonical in entity_expressions:
            final_entity_projections.append(projection)
        if canonical == expected:
            final_measure_projections.append(projection)

    for alias, window_scope in candidates:
        for scope in reachable:
            for predicate in scope.expression.find_all(exp.EQ, exp.LTE, exp.LT):
                left, right = predicate.this, predicate.expression
                if (not isinstance(left, exp.Column) or left.name.casefold() != alias
                        or not _column_flows_through(left, scope, window_scope)):
                    continue
                if not isinstance(right, exp.Literal) or not right.is_int:
                    continue
                actual_limit = int(right.this) - (1 if isinstance(predicate, exp.LT) else 0)
                if actual_limit != intent.limit:
                    _raise_sql_validation(
                        f"Window ranking must retain exactly the top {intent.limit} rows per partition."
                    )
                output_scope = window_scope if scope is final_scope else scope
                if not any(_expression_flows_through(projection, final_scope, output_scope)
                           for projection in final_entity_projections):
                    continue
                if final_measure_projections and not any(
                        _expression_flows_through(projection, final_scope, output_scope)
                        for projection in final_measure_projections):
                    continue
                return alias
    return None


def validate_ranking_semantics(sql: str, intent: RankingIntent, table_columns) -> dict[str, str | int]:
    """Verify final rank key, direction, limit, entity output and grouped measure lineage."""
    if not intent.resolved:
        _raise_sql_validation(intent.issue or "Ranking intent is unresolved.")
    if intent.partition_grains and not intent.partition_expressions:
        _raise_sql_validation("A time-partitioned ranking needs a complete typed ranking_contract.")
    tree = parse_one(sql, read="postgres")
    if not isinstance(tree, exp.Select):
        _raise_sql_validation("Ranking must finish in one result-producing SELECT.")
    scopes = list(traverse_scope(tree))
    final_scope = next((scope for scope in scopes if scope.expression is tree), scopes[-1] if scopes else None)
    if final_scope is None:
        _raise_sql_validation("Ranking scope could not be resolved.")

    expected = _expected_expression(intent, table_columns)

    reachable: list[Scope] = []
    seen: set[int] = set()

    def visit(scope):
        if id(scope.expression) in seen:
            return
        seen.add(id(scope.expression))
        reachable.append(scope)
        for _, source in scope.selected_sources.values():
            if isinstance(source, Scope):
                visit(source)

    visit(final_scope)

    offset = tree.args.get("offset")
    if offset is not None:
        offset_expression = getattr(offset, "expression", None)
        offset_value = getattr(offset_expression, "this", None)
        if (not isinstance(offset_expression, exp.Literal) or not offset_expression.is_int
                or int(offset_value) != 0):
            _raise_sql_validation("Ranking cannot skip leading rows with a nonzero or unverified OFFSET.")

    limit = tree.args.get("limit")
    limit_value = getattr(getattr(limit, "expression", None), "this", None)
    if not str(limit_value).isdigit():
        _raise_sql_validation("Ranking must have a bounded final result.")
    final_limit = int(limit_value)
    window_rank = _window_rank_alias(tree, final_scope, reachable, intent, expected, table_columns)
    if window_rank:
        if final_limit < intent.limit:
            _raise_sql_validation("The final LIMIT truncates the requested per-partition ranking.")
    else:
        if intent.partition_columns or intent.partition_expressions:
            _raise_sql_validation("The requested per-group ranking needs a matching window partition.")
        if final_limit != intent.limit:
            _raise_sql_validation(f"Ranking must preserve LIMIT {intent.limit} exactly.")
        order = tree.args.get("order")
        if not order or not order.expressions:
            _raise_sql_validation("The top/bottom request needs ORDER BY the requested business measure before LIMIT.")
        primary = order.expressions[0]
        if bool(primary.args.get("desc")) != (intent.direction == "desc"):
            _raise_sql_validation("The ranking direction must be " + intent.direction.upper() + ".")
        actual = _canonical(_projected_order_expression(primary, tree), final_scope, table_columns)
        if actual != expected:
            _raise_sql_validation(
                f"The first ranking key does not match the requested measure {intent.measure.identity}; "
                f"rank by that measure {intent.direction.upper()} before any entity tie-breaker."
            )

    entity_expressions = [exp.column(column, table=table.rsplit(".", 1)[-1], db="commerce")
                          for table, column in intent.entity_columns]
    final_entity = any(
        _canonical(_unaliased(projection), final_scope, table_columns) == entity
        for projection in tree.selects for entity in entity_expressions
    )
    if not final_entity:
        _raise_sql_validation(f"The final result must retain the {intent.entity} identity.")

    grouped_measure = False
    for scope in reachable:
        select = scope.expression
        group = select.args.get("group")
        if group is None:
            continue
        measures = any(_canonical(_unaliased(projection), scope, table_columns) == expected for projection in select.selects)
        groups = []
        for item in group.expressions:
            if isinstance(item, exp.Literal) and item.is_int:
                index = int(item.this) - 1
                if 0 <= index < len(select.selects):
                    item = _unaliased(select.selects[index])
            elif isinstance(item, exp.Column) and not item.table and not item.db:
                aliases = [projection for projection in select.selects
                           if projection.alias_or_name.casefold() == item.name.casefold()]
                if len(aliases) == 1:
                    item = _unaliased(aliases[0])
            groups.append(_canonical_partition(_unaliased(item), scope, table_columns))
        expected_partition = _expected_partitions(intent, scope, table_columns)
        group_set = set(groups)
        group_entities = group_set & set(entity_expressions)
        extra_groups = group_set - expected_partition - group_entities

        def dependent_on_ranked_entity(extra):
            if not isinstance(extra, exp.Column):
                return False
            return any(
                isinstance(entity, exp.Column)
                and entity.table == extra.table
                and entity.db == extra.db == "commerce"
                and entity.name in PRIMARY_KEYS.get(entity.table, set())
                for entity in group_entities
            )

        partition_source_columns = {
            column for partition in expected_partition for column in partition.find_all(exp.Column)
        }

        def dependent_on_partition(extra):
            return isinstance(extra, exp.Column) and extra in partition_source_columns

        if (measures and group_entities and expected_partition <= group_set
                and len(group_set - group_entities) >= len(expected_partition)
                and all(dependent_on_ranked_entity(extra) or dependent_on_partition(extra)
                        for extra in extra_groups)):
            grouped_measure = True
            break
    if not grouped_measure:
        _raise_sql_validation(
            f"The requested measure must be aggregated and grouped at the {intent.entity} identity grain."
        )

    return {
        "status": "verified",
        "entity": intent.entity,
        "measure": intent.measure.identity,
        "measure_approval": intent.measure.approval_status,
        "direction": intent.direction,
        "limit": intent.limit,
    }
