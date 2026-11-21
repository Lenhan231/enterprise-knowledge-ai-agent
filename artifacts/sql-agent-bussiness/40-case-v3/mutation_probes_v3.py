"""Controlled one-change SQL variants for the v3 discriminative probes."""

from __future__ import annotations

from copy import deepcopy


MUTATIONS = [
    {
        "id": "M002-01-missing-time-scope", "case_id": "B40-002", "category": "missing_time_restriction",
        "description": "Replace the 2025 ship-date range with a non-null parameter tautology.",
        "sql_replacements": [("WHERE s.ship_date >= $1 AND s.ship_date < $2", "WHERE $1::date IS NOT NULL AND $2::date IS NOT NULL")],
        "parameter_updates": {}, "validator_oracle": None,
    },
    {
        "id": "M002-02-wrong-date-boundary", "case_id": "B40-002", "category": "incorrect_date_boundary",
        "description": "Move the exclusive end boundary one day earlier, omitting 2025-12-31.",
        "sql_replacements": [], "parameter_updates": {1: "2025-12-31"}, "validator_oracle": None,
    },
    {
        "id": "M002-03-wrong-null-aggregate", "case_id": "B40-002", "category": "incorrect_null_handling",
        "description": "Count non-NULL delivery dates under the missing-date predicate.",
        "sql_replacements": [(
            "COUNT(*) FILTER (WHERE s.delivery_date IS NULL) AS missing_delivery_date_count",
            "COUNT(s.delivery_date) FILTER (WHERE s.delivery_date IS NULL) AS missing_delivery_date_count",
        )],
        "parameter_updates": {}, "validator_oracle": None,
    },
    {
        "id": "M006-01-missing-city-filter", "case_id": "B40-006", "category": "missing_required_filter",
        "description": "Remove the Hai Phong constraint while keeping the bound parameter valid.",
        "sql_replacements": [(
            "WHERE g.city = $1 AND c.age_group = $2 AND c.signup_date >= $3 AND c.signup_date < $4",
            "WHERE c.age_group = $1 AND c.signup_date >= $2 AND c.signup_date < $3",
        )],
        "parameter_replacement": ["25-34", "2024-01-01", "2025-01-01"],
        "parameter_updates": {}, "validator_oracle": None,
    },
    {
        "id": "M006-02-wrong-age-value", "case_id": "B40-006", "category": "wrong_filter_value",
        "description": "Use age group 35-44 instead of the requested 25-34.",
        "sql_replacements": [], "parameter_updates": {1: "35-44"}, "validator_oracle": None,
    },
    {
        "id": "M006-03-wrong-join-key", "case_id": "B40-006", "category": "incorrect_join_key",
        "description": "Join geography ZIP to customer_id instead of customers.zip.",
        "sql_replacements": [("g.zip = c.zip", "g.zip = c.customer_id")],
        "parameter_updates": {}, "validator_oracle": "approved_join_relationship",
    },
    {
        "id": "M008-01-missing-nonnull-filter", "case_id": "B40-008", "category": "missing_null_filter",
        "description": "Remove the return_reason IS NOT NULL constraint.",
        "sql_replacements": [(" AND r.return_reason IS NOT NULL", "")],
        "parameter_updates": {}, "validator_oracle": None,
    },
    {
        "id": "M008-02-inverted-null-filter", "case_id": "B40-008", "category": "incorrect_null_handling",
        "description": "Select NULL reasons instead of non-NULL reasons.",
        "sql_replacements": [("r.return_reason IS NOT NULL", "r.return_reason IS NULL")],
        "parameter_updates": {}, "validator_oracle": None,
    },
    {
        "id": "M015-01-wrong-ranking-direction", "case_id": "B40-015", "category": "wrong_ranking_direction",
        "description": "Rank net revenue ascending rather than descending.",
        "sql_replacements": [("net_revenue DESC", "net_revenue ASC")],
        "parameter_updates": {}, "validator_oracle": None,
    },
    {
        "id": "M015-02-incorrect-limit", "case_id": "B40-015", "category": "incorrect_limit",
        "description": "Use TOP 5 instead of the requested TOP 3.",
        "sql_replacements": [("LIMIT 3", "LIMIT 5")],
        "parameter_updates": {}, "validator_oracle": None,
    },
    {
        "id": "M015-03-missing-limit", "case_id": "B40-015", "category": "missing_limit",
        "description": "Remove the business TOP 3 and retain only the executor's safe maximum cap (200 rows).",
        "sql_replacements": [(" LIMIT 3", " LIMIT 200")],
        "parameter_updates": {}, "validator_oracle": None,
    },
    {
        "id": "M017-01-wrong-aggregation", "case_id": "B40-017", "category": "wrong_aggregation",
        "description": "Use MAX(return_quantity) instead of SUM(return_quantity).",
        "sql_replacements": [("SUM(r.return_quantity)", "MAX(r.return_quantity)")],
        "parameter_updates": {}, "validator_oracle": None,
    },
    {
        "id": "M017-02-wrong-grouping-grain", "case_id": "B40-017", "category": "missing_required_grouping",
        "description": "Aggregate all return rows together without grouping by product_id.",
        "sql_replacements": [
            ("SELECT r.product_id, SUM(r.return_quantity)", "SELECT SUM(r.return_quantity)"),
            (" GROUP BY r.product_id ORDER BY returned_units DESC, r.product_id ASC", " ORDER BY returned_units DESC"),
        ],
        "parameter_updates": {}, "validator_oracle": None,
    },
    {
        "id": "M021-01-nonnull-instead-of-true", "case_id": "B40-021", "category": "wrong_boolean_population",
        "description": "Count every non-NULL stockout flag, including FALSE rows.",
        "sql_replacements": [("i.stockout_flag = TRUE", "i.stockout_flag IS NOT NULL")],
        "parameter_updates": {}, "validator_oracle": None,
    },
    {
        "id": "M023-01-reversed-snapshot-delta", "case_id": "B40-023", "category": "wrong_comparison_direction",
        "description": "Compute before minus after instead of after minus before.",
        "sql_replacements": [(
            "MAX(i.stock_on_hand) FILTER (WHERE i.snapshot_date = $2) - MAX(i.stock_on_hand) FILTER (WHERE i.snapshot_date = $1) AS stock_delta",
            "MAX(i.stock_on_hand) FILTER (WHERE i.snapshot_date = $1) - MAX(i.stock_on_hand) FILTER (WHERE i.snapshot_date = $2) AS stock_delta",
        )],
        "parameter_updates": {}, "validator_oracle": None,
    },
    {
        "id": "M023-02-wrong-after-snapshot", "case_id": "B40-023", "category": "wrong_inventory_snapshot",
        "description": "Compare against 2025-11-30 instead of the requested 2025-10-31 snapshot.",
        "sql_replacements": [], "parameter_updates": {1: "2025-11-30"}, "validator_oracle": None,
    },
    {
        "id": "M023-03-missing-common-product-condition", "case_id": "B40-023", "category": "missing_snapshot_membership_condition",
        "description": "Remove the requirement that each product be present in both snapshots.",
        "sql_replacements": [(" HAVING COUNT(DISTINCT i.snapshot_date) = 2", "")],
        "parameter_updates": {}, "validator_oracle": None,
    },
    {
        "id": "M026-01-wrong-inherited-year", "case_id": "B40-026", "category": "wrong_followup_time_scope",
        "description": "Use 2025 instead of the inherited 2024 year for the monthly COGS follow-up.",
        "sql_replacements": [], "parameter_updates": {0: "2025-01-01", 1: "2026-01-01"}, "validator_oracle": None,
    },
    {
        "id": "M027-01-missing-delivered-filter", "case_id": "B40-027", "category": "missing_population_filter",
        "description": "Count all statuses rather than only delivered orders in inherited 2025 scope.",
        "sql_replacements": [(
            "WHERE o.order_status = $1 AND o.order_date >= $2 AND o.order_date < $3",
            "WHERE o.order_date >= $1 AND o.order_date < $2",
        )],
        "parameter_replacement": ["2025-01-01", "2026-01-01"],
        "parameter_updates": {}, "validator_oracle": None,
        "semantic_validator_oracle": "required_order_status_population",
    },
    {
        "id": "M027-02-wrong-inherited-year", "case_id": "B40-027", "category": "wrong_followup_time_scope",
        "description": "Use 2024 instead of inherited 2025 for the delivered-order follow-up.",
        "sql_replacements": [], "parameter_updates": {1: "2024-01-01", 2: "2025-01-01"}, "validator_oracle": None,
    },
    {
        "id": "M028-01-misaligned-comparison-month", "case_id": "B40-028", "category": "misaligned_month_grouping",
        "description": "Shift 2023 gross-profit rows one month later before aligning them to 2024.",
        "sql_replacements": [
            ("EXTRACT(MONTH FROM s.date) AS month, SUM", "EXTRACT(MONTH FROM s.date) + CASE WHEN EXTRACT(YEAR FROM s.date) = 2023 THEN 1 ELSE 0 END AS month, SUM"),
            ("GROUP BY EXTRACT(YEAR FROM s.date), EXTRACT(MONTH FROM s.date)", "GROUP BY EXTRACT(YEAR FROM s.date), EXTRACT(MONTH FROM s.date) + CASE WHEN EXTRACT(YEAR FROM s.date) = 2023 THEN 1 ELSE 0 END"),
        ],
        "parameter_updates": {}, "validator_oracle": None,
    },
    {
        "id": "M028-02-wrong-gross-profit-formula", "case_id": "B40-028", "category": "wrong_aggregation_formula",
        "description": "Use gross revenue alone instead of SUM(revenue)-SUM(cogs).",
        "sql_replacements": [("SUM(s.revenue) - SUM(s.cogs) AS gross_profit", "SUM(s.revenue) AS gross_profit")],
        "parameter_updates": {}, "validator_oracle": None,
    },
    {
        "id": "M028-03-wrong-inherited-period", "case_id": "B40-028", "category": "wrong_followup_time_scope",
        "description": "Drop 2024 from the inherited year-over-year comparison window.",
        "sql_replacements": [], "parameter_updates": {0: "2022-01-01", 1: "2024-01-01"}, "validator_oracle": None,
    },
    {
        "id": "M029-01-missing-top-two-limit", "case_id": "B40-029", "category": "missing_limit",
        "description": "Remove the business TOP 2 and retain only the executor's safe maximum cap (200 rows).",
        "sql_replacements": [(" LIMIT 2", " LIMIT 200")],
        "parameter_updates": {}, "validator_oracle": None,
    },
    {
        "id": "M029-02-wrong-ranking-direction", "case_id": "B40-029", "category": "wrong_ranking_direction",
        "description": "Rank return quantity ascending rather than descending.",
        "sql_replacements": [("returned_units DESC", "returned_units ASC")],
        "parameter_updates": {}, "validator_oracle": None,
    },
    {
        "id": "M029-03-wrong-tie-break-direction", "case_id": "B40-029", "category": "wrong_tie_break_direction",
        "description": "Use reverse alphabetical order for equal return quantities instead of ascending reason names.",
        "sql_replacements": [("r.return_reason ASC NULLS LAST", "r.return_reason DESC NULLS FIRST")],
        "parameter_updates": {}, "validator_oracle": None,
    },
    {
        "id": "M030-01-wrong-inventory-snapshot", "case_id": "B40-030", "category": "wrong_inventory_snapshot",
        "description": "Use the 2025-09-30 snapshot instead of inherited 2025-10-31.",
        "sql_replacements": [], "parameter_updates": {0: "2025-09-30"}, "validator_oracle": None,
    },
    {
        "id": "M004-01-join-fanout-denominator", "case_id": "B40-004", "category": "join_fanout_aggregation",
        "description": "Divide line-item revenue by joined order rows rather than distinct orders.",
        "sql_replacements": [("COUNT(DISTINCT o.order_id)", "COUNT(o.order_id)")],
        "parameter_updates": {}, "validator_oracle": "join_fanout_aggregation",
    },
]


def construct_mutation(gold_by_id: dict[str, dict], spec: dict) -> dict:
    """Apply exactly the declared semantic change and prove its target changed."""
    gold = gold_by_id[spec["case_id"]]
    sql = gold["sql"]
    for before, after in spec["sql_replacements"]:
        if sql.count(before) != 1:
            raise ValueError(f"{spec['id']}: expected one occurrence of mutation target {before!r}")
        sql = sql.replace(before, after, 1)
    parameters = deepcopy(spec.get("parameter_replacement", gold["parameters"]))
    for index, value in spec["parameter_updates"].items():
        if parameters[index] == value:
            raise ValueError(f"{spec['id']}: parameter update did not change position {index}")
        parameters[index] = value
    parameters_changed = parameters != gold["parameters"]
    if not spec["sql_replacements"] and not parameters_changed:
        raise ValueError(f"{spec['id']}: mutation made no change")
    for _before, after in spec["sql_replacements"]:
        if after and after not in sql:
            raise ValueError(f"{spec['id']}: declared semantic change is absent from constructed SQL")
    return {"sql": sql, "parameters": parameters, "construction_verified": True}


def mutation_catalog() -> list[dict]:
    return deepcopy(MUTATIONS)
