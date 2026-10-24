"""Fixed Inventory Control dashboard backed by the read-only commerce source."""

from __future__ import annotations

import asyncio

from core.agents.sql_analytics_agent import SQLAnalyticsAgent
from core.models.agents import AgentResult, Evidence


class InventoryDashboardAgent:
    def __init__(self, repository) -> None:
        self.repository = repository

    async def run(self, request) -> AgentResult:
        SQLAnalyticsAgent._authorize(request)
        category = request.metadata.get("category")
        if category is not None:
            if not isinstance(category, str) or len(category) > 100:
                raise ValueError("category must be a string of at most 100 characters")
            category = category.strip() or None

        latest = await self.repository.execute_approved_query(
            "SELECT MAX(i.snapshot_date) AS snapshot_date FROM commerce.inventory AS i LIMIT 1"
        )
        if not latest or latest[0]["snapshot_date"] is None:
            return AgentResult(
                answer="No inventory snapshot is available in the approved data source.",
                agent="dashboard", metadata={"ok": False},
                data={"dashboard": {"outline_id": "inventory_control", "sections": []}},
            )
        snapshot = latest[0]["snapshot_date"]
        filters = "i.snapshot_date = $1 AND i.category IS NOT DISTINCT FROM COALESCE($2, i.category)"
        queries = (
            "SELECT COUNT(i.product_id) AS sku_count, "
            "COUNT(*) FILTER (WHERE i.stockout_flag) * 100.0 / NULLIF(COUNT(*), 0) AS stockout_rate, "
            "COUNT(*) FILTER (WHERE i.overstock_flag) * 100.0 / NULLIF(COUNT(*), 0) AS overstock_rate, "
            "AVG(i.fill_rate) AS mean_fill_rate, "
            "COUNT(*) FILTER (WHERE i.overstock_flag AND i.days_of_supply IS NOT NULL) "
            f"AS high_days_of_supply_count FROM commerce.inventory AS i WHERE {filters} LIMIT 1",
            "SELECT i.category AS category, "
            "COUNT(*) FILTER (WHERE i.stockout_flag) * 100.0 / NULLIF(COUNT(*), 0) AS stockout_rate "
            f"FROM commerce.inventory AS i WHERE {filters} GROUP BY i.snapshot_date, i.category "
            "ORDER BY 2 DESC LIMIT 20",
            "SELECT i.category AS category, "
            "COUNT(*) FILTER (WHERE i.stockout_flag) AS stockout_flag_count, "
            "COUNT(*) FILTER (WHERE i.overstock_flag) AS overstock_flag_count, "
            "COUNT(*) FILTER (WHERE i.stockout_flag AND i.overstock_flag) AS both_flags_count "
            f"FROM commerce.inventory AS i WHERE {filters} GROUP BY i.snapshot_date, i.category LIMIT 20",
            "SELECT i.product_id AS product_id, i.product_name AS product_name, "
            "i.category AS category, i.stock_on_hand AS stock_on_hand, "
            "i.days_of_supply AS days_of_supply, i.stockout_flag AS stockout_flag, "
            "i.overstock_flag AS overstock_flag, i.reorder_flag AS reorder_flag "
            f"FROM commerce.inventory AS i WHERE {filters} AND "
            "(i.stockout_flag OR i.overstock_flag OR i.reorder_flag) "
            "ORDER BY i.days_of_supply DESC NULLS LAST LIMIT 25",
        )
        kpis, stockout, flags, exceptions = await asyncio.gather(*(
            self.repository.execute_approved_query(sql, snapshot, category) for sql in queries
        ))
        values = kpis[0] if kpis else {}
        dashboard = {
            "outline_id": "inventory_control",
            "title": "Inventory Control & Exceptions",
            "snapshot_date": snapshot.isoformat() if hasattr(snapshot, "isoformat") else str(snapshot),
            "category": category,
            "kpis": values,
            "stockout_by_category": stockout,
            "inventory_flags": flags,
            "exceptions": exceptions,
        }
        return AgentResult(
            answer=(f"Inventory snapshot as of {dashboard['snapshot_date']}: "
                    f"{values.get('sku_count', 0)} SKUs. Policy flags are simulated draft indicators."),
            agent="dashboard", data={"dashboard": dashboard},
            evidence=[Evidence(
                citation_id="S1", source_type="database", source="commerce.inventory",
                content=f"Inventory snapshot date: {dashboard['snapshot_date']}",
                metadata={"snapshot_date": dashboard["snapshot_date"]},
            )],
            metadata={"ok": True, "limitations": [
                "The latest available inventory snapshot is dated " + dashboard["snapshot_date"] + ".",
                "Inventory policy thresholds are simulated drafts and require business-owner approval.",
                "High days of supply is represented by the source overstock_flag; no new threshold is applied.",
            ]},
        )
