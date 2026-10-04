"""Canonical metric names and decision domains supported by the Vinamilk public corpus."""

BUSINESS_METRIC_CATALOG = {
    "farmer_raw_milk_purchased": {
        "label": "Raw fresh milk purchased from farming households",
        "domain": "milk_supply",
        "definition": "Annual raw fresh milk purchased from contracted or partner farming households.",
        "unit_guidance": "tonnes",
        "aliases": ("milk purchased from farmers", "fresh raw milk purchased", "sữa thu mua từ nông hộ"),
    },
    "total_raw_milk_supply": {
        "label": "Total raw fresh milk supplied for production",
        "domain": "milk_supply",
        "definition": "Annual fresh raw milk supply reported for production; preserve approximate/management scope in evidence.",
        "unit_guidance": "tonnes",
        "aliases": ("raw milk supplied for production", "raw fresh milk volume", "raw milk supply", "sữa tươi nguyên liệu cung cấp cho sản xuất"),
    },
    "managed_farm_raw_milk": {
        "label": "Raw milk produced by managed farms",
        "domain": "milk_supply",
        "definition": "Annual fresh raw milk produced by Vinamilk and Mộc Châu managed farm systems.",
        "unit_guidance": "tonnes",
        "aliases": ("farm system produces", "raw milk from managed farms", "milk produced by farms"),
    },
    "dairy_cattle_herd_size": {
        "label": "Dairy cattle managed across the group",
        "domain": "milk_supply",
        "definition": "Year-end or reported dairy cattle herd under Vinamilk and Mộc Châu management; retain report scope and approximate wording.",
        "unit_guidance": "cows",
        "aliases": ("dairy cattle managed", "herd", "đàn bò sữa"),
    },
    "partner_farm_households": {
        "label": "Partner farming households",
        "domain": "milk_supply",
        "definition": "Number of households linked to the fresh-milk supply chain; retain approximate scope.",
        "unit_guidance": "households",
        "aliases": ("farming households", "farmer households", "nông hộ"),
    },
    "contracted_household_training_coverage": {
        "label": "Contracted households receiving annual technical training",
        "domain": "milk_supply",
        "definition": "Share of contracted farming households receiving annual technical training.",
        "unit_guidance": "%",
        "aliases": ("households receive annual technical training", "trained contracted households", "hộ chăn nuôi được đào tạo"),
    },
    "farmer_support_coverage": {
        "label": "Technical support coverage for substandard-milk households",
        "domain": "milk_supply",
        "definition": "Share of farming households with substandard milk that receive technical consultation/support.",
        "unit_guidance": "%",
        "aliases": ("households with substandard milk receive technical support", "substandard milk households", "hộ có sữa không đạt chuẩn"),
    },
    "milk_collection_points": {
        "label": "Milk collection hubs and stations",
        "domain": "milk_supply",
        "definition": "Collection network count; encode operator and any combined total in the scope.",
        "unit_guidance": "stations",
        "aliases": ("collection hubs", "collection stations", "milk collection network", "trạm thu mua"),
    },
    "biomass_corn_procured_from_farmers": {
        "label": "Biomass corn purchased from farming households",
        "domain": "milk_supply",
        "definition": "Annual biomass corn procurement from farming households as cattle-feed input; preserve reporting period and scope.",
        "unit_guidance": "tonnes",
        "aliases": ("biomass corn purchased", "corn procured from farmers"),
    },
    "silage_corn_procured_from_farmers": {
        "label": "Silage corn procured from local households",
        "domain": "milk_supply",
        "definition": "Annual silage-corn procurement from local households; keep distinct from biomass corn and preserve report scope.",
        "unit_guidance": "tonnes",
        "aliases": ("silage corn from local households", "silage corn procurement"),
    },
    "fertilizer_support_volume": {
        "label": "Fertilizer supplied to support farming households",
        "domain": "milk_supply",
        "definition": "Reported fertilizer volume supplied to support farming households; do not infer a per-household amount.",
        "unit_guidance": "tonnes",
        "aliases": ("fertilizer supplied to households", "fertilizer support"),
    },
    "globalgap_certified_farm_share": {
        "label": "Farms certified to GLOBALG.A.P. standards",
        "domain": "milk_supply",
        "definition": "Share of reported farms certified to GLOBALG.A.P.; retain the report's farm-system scope.",
        "unit_guidance": "%",
        "aliases": ("farms certified", "globalgap", "global gap"),
    },
    "supply_chain_customer_satisfaction": {
        "label": "Supply-chain customer satisfaction",
        "domain": "manufacturing_efficiency",
        "definition": "Reported customer satisfaction for supply-chain execution; retain upper-bound wording and population scope.",
        "unit_guidance": "%",
        "aliases": ("customer satisfaction", "supply chain satisfaction"),
    },
    "purchasing_cost_savings": {
        "label": "Savings from purchasing activities",
        "domain": "manufacturing_efficiency",
        "definition": "Reported annual savings attributed to purchasing activities; preserve approximate wording and currency.",
        "unit_guidance": "VND billion",
        "aliases": ("savings in purchasing", "purchasing savings", "purchasing activities", "purchasing cost"),
    },
    "production_cost_savings": {
        "label": "Estimated production cost savings",
        "domain": "manufacturing_efficiency",
        "definition": "Estimated annual bill-of-materials savings from production operations.",
        "unit_guidance": "VND billion",
        "aliases": ("production cost savings", "production savings", "bill of materials savings"),
    },
    "raw_material_cost_savings": {
        "label": "Raw material cost savings",
        "domain": "manufacturing_efficiency",
        "definition": "Reported savings from raw materials in production; preserve the report's organizational scope and currency.",
        "unit_guidance": "VND billion",
        "aliases": ("raw material savings", "savings from raw materials", "nguyên vật liệu tiết kiệm"),
    },
    "production_overhead_budget_utilization": {
        "label": "General production overhead as share of budget",
        "domain": "manufacturing_efficiency",
        "definition": "Reported general production overhead as a percentage of its approved budget for the year.",
        "unit_guidance": "% of budget",
        "aliases": ("production overhead as a share of budget", "production overhead maintained at", "chi phí sản xuất chung so với ngân sách"),
    },
    "production_lines_meeting_oee_target": {
        "label": "Production lines meeting OEE target",
        "domain": "manufacturing_efficiency",
        "definition": "Share of production lines reported as meeting their target Overall Equipment Effectiveness (OEE).",
        "unit_guidance": "%",
        "aliases": ("oee", "production lines meeting", "production line efficiency"),
    },
    "domestic_revenue_growth": {
        "label": "Domestic business revenue growth",
        "domain": "market_performance",
        "definition": "Year-over-year growth rate of domestic business revenue.",
        "unit_guidance": "%",
        "aliases": ("domestic business revenue growth", "domestic business growth", "tăng trưởng doanh thu nội địa"),
    },
    "domestic_segment_gross_profit": {
        "label": "Domestic segment gross profit",
        "domain": "market_performance",
        "definition": "Gross profit reported for customers located in Vietnam; geographic segment scope, before unallocated selling and administration costs.",
        "unit_guidance": "VND billion",
        "aliases": ("domestic gross profit", "domestic segment gross profit", "segment gross profit", "gross profit",
                    "lợi nhuận gộp trong nước"),
    },
    "overseas_segment_gross_profit": {
        "label": "Overseas segment gross profit",
        "domain": "market_performance",
        "definition": "Gross profit reported for customers located outside Vietnam; geographic segment scope, before unallocated selling and administration costs.",
        "unit_guidance": "VND billion",
        "aliases": ("overseas gross profit", "overseas segment gross profit", "segment gross profit", "gross profit",
                    "lợi nhuận gộp nước ngoài"),
    },
    "brand_innovation_perception": {
        "label": "Brand innovation and creativity perception",
        "domain": "product_portfolio",
        "definition": "Reported consumer-perception index for brand innovation and creativity.",
        "unit_guidance": "%",
        "aliases": ("brand innovation", "innovation and creativity", "đổi mới sáng tạo"),
    },
    "green_farm_urban_purchase_consideration": {
        "label": "Green Farm purchase consideration in urban areas",
        "domain": "product_portfolio",
        "definition": "Share of urban consumers considering Green Farm; preserve survey period (including H1 where applicable).",
        "unit_guidance": "%",
        "aliases": ("purchase consideration", "considering green farm", "cân nhắc mua green farm"),
    },
    "plant_based_milk_sales_growth": {
        "label": "Plant-based milk sales growth",
        "domain": "product_portfolio",
        "definition": "Year-over-year sales growth reported for the plant-based milk category; approximate values remain qualified.",
        "unit_guidance": "%",
        "aliases": ("plant based milk", "plant-based", "sữa thực vật"),
    },
    "green_farm_sales_growth": {
        "label": "Green Farm sales growth",
        "domain": "product_portfolio",
        "definition": "Year-over-year Green Farm sales growth; preserve lower-bound wording where reported.",
        "unit_guidance": "%",
        "aliases": ("green farm growth", "green farm sales"),
    },
    "green_farm_brand_awareness": {
        "label": "Green Farm brand awareness",
        "domain": "product_portfolio",
        "definition": "Reported consumer awareness of the Green Farm brand.",
        "unit_guidance": "%",
        "aliases": ("green farm awareness", "brand awareness", "nhận biết green farm"),
    },
    "green_farm_customer_loyalty": {
        "label": "Green Farm consumer loyalty",
        "domain": "product_portfolio",
        "definition": "Reported share of Green Farm consumers identified as loyal customers.",
        "unit_guidance": "%",
        "aliases": ("green farm loyalty", "loyal customers", "khách hàng trung thành"),
    },
    "new_or_relaunched_products": {
        "label": "New and relaunched products",
        "domain": "product_portfolio",
        "definition": "Count of new or relaunched products reported for the year; not a count of launches alone.",
        "unit_guidance": "products",
        "aliases": ("products launched", "new and relaunched", "sản phẩm mới được tái tung"),
    },
    "new_products_count": {
        "label": "Completely new products introduced",
        "domain": "product_portfolio",
        "definition": "Products reported as completely new during the fiscal year; distinct from products relaunched or refreshed.",
        "unit_guidance": "products",
        "aliases": ("completely new products", "entirely new products", "sản phẩm hoàn toàn mới"),
    },
    "employee_headcount": {
        "label": "Group employee headcount",
        "domain": "human_resources",
        "definition": "Employee total reported for the group; preserve the report's date and organizational scope.",
        "unit_guidance": "employees",
        "aliases": ("employee headcount", "number of employees", "staffing level", "nhân sự", "số nhân viên"),
    },
    "employee_headcount_change": {
        "label": "Net employee headcount change",
        "domain": "human_resources",
        "definition": "Net change in group employee count reported for the fiscal year; not gross hires or turnover.",
        "unit_guidance": "employees",
        "aliases": ("headcount change", "net hiring", "employee increase", "tăng nhân viên", "tăng thêm nhân viên"),
    },
    "employee_training_hours": {
        "label": "Employee training hours",
        "domain": "human_resources",
        "definition": "Total employee training hours reported for the fiscal year; preserve any lower-bound wording.",
        "unit_guidance": "hours",
        "aliases": ("training hours", "employee training hours", "giờ đào tạo nhân viên"),
    },
    "market_share_lead_over_runner_up": {
        "label": "Approximate market-share lead over the second player",
        "domain": "market_performance",
        "definition": "Reported lead over the second-largest manufacturer in the cited sector; preserve approximate wording and sector scope.",
        "unit_guidance": "percentage points",
        "aliases": (
            "market share lead", "market share gap", "market leader gap",
            "điểm phần trăm so với nhà sản xuất thứ 2", "khoảng cách thị phần",
            "chênh lệch thị phần với đối thủ đứng thứ hai",
        ),
    },
    "domestic_consolidated_net_revenue": {
        "label": "Domestic consolidated net revenue",
        "domain": "market_performance",
        "definition": "Consolidated net revenue generated in the domestic market.",
        "unit_guidance": "VND billion",
        "aliases": ("domestic consolidated net revenue", "domestic and overseas segment net revenue",
                    "domestic net revenue", "domestic revenue", "doanh thu nội địa",
                    "doanh thu thuần hợp nhất trong nước"),
    },
    "parent_domestic_net_revenue": {
        "label": "Parent-company domestic net revenue",
        "domain": "market_performance",
        "definition": "Net revenue of the parent company in the domestic market; distinct from consolidated domestic revenue.",
        "unit_guidance": "VND billion",
        "aliases": ("parent company domestic net revenue", "doanh thu thuần trong nước công ty mẹ"),
    },
    "domestic_consolidated_net_revenue_growth": {
        "label": "Domestic consolidated net revenue growth",
        "domain": "market_performance",
        "definition": "Year-over-year growth in consolidated domestic net revenue; distinct from parent-company growth.",
        "unit_guidance": "%",
        "aliases": ("domestic consolidated revenue growth", "domestic market revenue growth",
                    "domestic and overseas market revenue growth",
                    "tăng trưởng doanh thu hợp nhất trong nước"),
    },
    "parent_domestic_net_revenue_growth": {
        "label": "Parent-company domestic net revenue growth",
        "domain": "market_performance",
        "definition": "Year-over-year growth in parent-company domestic net revenue; distinct from consolidated domestic growth.",
        "unit_guidance": "%",
        "aliases": ("parent company domestic growth",),
    },
    "export_net_revenue": {
        "label": "Export net revenue",
        "domain": "market_performance",
        "definition": "Annual net revenue from export activity.",
        "unit_guidance": "VND billion",
        "aliases": ("export net revenue", "export revenue", "doanh thu thuần xuất khẩu"),
    },
    "export_net_revenue_growth": {
        "label": "Export net revenue growth",
        "domain": "market_performance",
        "definition": "Year-over-year growth of export net revenue.",
        "unit_guidance": "%",
        "aliases": ("export revenue growth", "export net revenue growth", "tăng trưởng xuất khẩu"),
    },
    "commercial_export_revenue": {
        "label": "Commercial export revenue",
        "domain": "market_performance",
        "definition": "Commercial export revenue reported as a component of total export net revenue; do not add it to the total.",
        "unit_guidance": "VND billion",
        "aliases": ("commercial export revenue", "commercial exports", "doanh thu xuất khẩu thương mại"),
    },
    "commercial_export_revenue_growth": {
        "label": "Commercial export revenue growth",
        "domain": "market_performance",
        "definition": "Year-over-year growth in commercial export revenue, a component of total export net revenue.",
        "unit_guidance": "%",
        "aliases": ("commercial export growth", "commercial export revenue increase"),
    },
    "export_volume_teu": {
        "label": "Export volume",
        "domain": "market_performance",
        "definition": "Reported annual export shipping volume in twenty-foot equivalent units (TEUs); not a revenue or market-share measure.",
        "unit_guidance": "TEUs",
        "aliases": ("export volume", "export shipping volume", "xuất khẩu TEU"),
    },
    "guinea_export_revenue_growth": {
        "label": "Guinea export-market revenue growth",
        "domain": "market_performance",
        "definition": "Year-over-year export-market revenue growth reported for Guinea; the report does not disclose its absolute revenue or margin.",
        "unit_guidance": "%",
        "aliases": ("Guinea export growth", "Guinea market growth", "Guinea grew", "tăng trưởng Guinea"),
    },
    "hong_kong_export_revenue_growth": {
        "label": "Hong Kong export-market revenue growth",
        "domain": "market_performance",
        "definition": "Year-over-year export-market revenue growth reported for Hong Kong; the report does not disclose its absolute revenue or margin.",
        "unit_guidance": "%",
        "aliases": ("Hong Kong export growth", "Hong Kong market growth", "Hong Kong grew", "tăng trưởng Hong Kong"),
    },
    "japan_export_revenue_growth": {
        "label": "Japan export-market revenue growth",
        "domain": "market_performance",
        "definition": "Year-over-year export-market revenue growth reported for Japan; the report does not disclose its absolute revenue or margin.",
        "unit_guidance": "%",
        "aliases": ("Japan export growth", "Japan market growth", "Japan grew", "tăng trưởng Nhật Bản"),
    },
    "overseas_market_net_revenue": {
        "label": "Overseas market net revenue",
        "domain": "market_performance",
        "definition": "Net revenue generated in overseas markets; reported separately from export revenue.",
        "unit_guidance": "VND billion",
        "aliases": ("overseas market net revenue", "domestic and overseas segment net revenue",
                    "overseas segment net revenue", "overseas net revenue", "doanh thu thuần thị trường nước ngoài"),
    },
    "overseas_market_net_revenue_growth": {
        "label": "Overseas market net revenue growth",
        "domain": "market_performance",
        "definition": "Year-over-year growth of overseas market net revenue.",
        "unit_guidance": "%",
        "aliases": ("overseas market revenue growth", "overseas market net revenue growth",
                    "overseas revenue growth", "tăng trưởng thị trường nước ngoài"),
    },
    "domestic_revenue_share": {
        "label": "Domestic share of consolidated net revenue",
        "domain": "market_performance",
        "definition": "Domestic contribution share of consolidated net revenue, as reported.",
        "unit_guidance": "%",
        "aliases": ("domestic share of consolidated revenue", "đóng góp 82% doanh thu thuần hợp nhất"),
    },
    "overseas_revenue_share": {
        "label": "Overseas share of consolidated net revenue",
        "domain": "market_performance",
        "definition": "Overseas contribution share of consolidated net revenue, as reported.",
        "unit_guidance": "%",
        "aliases": ("overseas share of consolidated revenue", "đóng góp 18% doanh thu thuần hợp nhất"),
    },
    "foreign_subsidiary_revenue": {
        "label": "Foreign subsidiaries' revenue",
        "domain": "market_performance",
        "definition": "Revenue reported for foreign subsidiaries; distinct from overseas-market net revenue and exports.",
        "unit_guidance": "VND billion",
        "aliases": ("foreign subsidiaries revenue", "doanh thu các chi nhánh nước ngoài"),
    },
    "foreign_subsidiary_revenue_growth": {
        "label": "Foreign subsidiaries' revenue growth",
        "domain": "market_performance",
        "definition": "Year-over-year revenue growth reported for foreign subsidiaries.",
        "unit_guidance": "%",
        "aliases": ("foreign subsidiaries revenue growth", "tăng trưởng doanh thu các chi nhánh nước ngoài"),
    },
    "export_markets_count": {
        "label": "Countries and territories reached by exports",
        "domain": "market_performance",
        "definition": "Cumulative number of export destinations reached; not a yearly addition.",
        "unit_guidance": "markets",
        "aliases": ("exported to countries and territories", "xuất khẩu đến quốc gia và vùng lãnh thổ"),
    },
    "new_export_markets_entered": {
        "label": "New export countries entered",
        "domain": "market_performance",
        "definition": "Number of new export countries entered during the fiscal year.",
        "unit_guidance": "countries",
        "aliases": ("expanded exports to new countries", "mở rộng xuất khẩu sang quốc gia mới"),
    },
    "export_trade_promotion_programs": {
        "label": "Export trade-promotion programs",
        "domain": "market_performance",
        "definition": "Number of trade-promotion programs reported for the year.",
        "unit_guidance": "programs",
        "aliases": ("trade promotion programs", "chương trình xúc tiến thương mại"),
    },
    "double_digit_growth_product_categories": {
        "label": "Product categories with double-digit growth contributions",
        "domain": "product_portfolio",
        "definition": "Count of product categories named as contributing positively with double-digit growth; category names remain in evidence scope.",
        "unit_guidance": "categories",
        "aliases": ("product categories with double digit growth", "sản phẩm với mức tăng 2 chữ số"),
    },
    "tpm_energy_cost_reduction": {
        "label": "TPM energy cost reduction",
        "domain": "manufacturing_efficiency",
        "definition": "Reduction in energy costs after five years of TPM commitment (2019–2023).",
        "unit_guidance": "%",
        "aliases": ("energy costs decreased by", "energy cost reduction", "energy savings"),
    },
    "tpm_productivity_increase": {
        "label": "TPM productivity increase",
        "domain": "manufacturing_efficiency",
        "definition": "Productivity increase after five years of TPM commitment (2019–2023).",
        "unit_guidance": "%",
        "aliases": ("productivity increased by", "productivity improvement", "productivity increase"),
    },
    "tpm_oee_increase_line_a1": {
        "label": "TPM OEE increase on production line A1",
        "domain": "manufacturing_efficiency",
        "definition": "OEE increase on production line A1 after five years of TPM commitment (2019–2023).",
        "unit_guidance": "%",
        "aliases": ("oee production line a1 increased by", "production line a1 oee improvement",
                    "oee improvement on production line a1"),
    },
    "tpm_water_intensity_reduction": {
        "label": "TPM water intensity reduction",
        "domain": "manufacturing_efficiency",
        "definition": "Reduction in water use per tonne of product after five years of TPM; the report states both volume and percent reduction.",
        "unit_guidance": "m³/tonne of product",
        "aliases": ("water down by", "water intensity reduction"),
    },
    "tpm_power_consumption_reduction": {
        "label": "TPM power consumption reduction",
        "domain": "manufacturing_efficiency",
        "definition": "Power consumption reduction after five years of TPM commitment (2019–2023).",
        "unit_guidance": "%",
        "aliases": ("power down by",),
    },
    "tpm_steam_consumption_reduction": {
        "label": "TPM steam consumption reduction",
        "domain": "manufacturing_efficiency",
        "definition": "Steam consumption reduction after five years of TPM commitment (2019–2023).",
        "unit_guidance": "%",
        "aliases": ("steam down by", "steam consumption reduction", "steam reduction"),
    },
    "tpm_initiative_savings": {
        "label": "Savings from TPM initiatives",
        "domain": "manufacturing_efficiency",
        "definition": "Savings attributed to 316 initiatives after five years of TPM commitment (2019–2023).",
        "unit_guidance": "VND billion",
        "aliases": ("316 initiatives saving vnd",),
    },
    "tpm_rework_rate_reduction": {
        "label": "TPM rework rate reduction",
        "domain": "manufacturing_efficiency",
        "definition": "Reported rework reduction after five years of TPM; preserve the report's percent wording without assuming percentage points.",
        "unit_guidance": "%",
        "aliases": ("rework down by",),
    },
    "tpm_quality_index_increase": {
        "label": "TPM quality index increase",
        "domain": "manufacturing_efficiency",
        "definition": "Increase in the quality index (Q) after five years of TPM commitment (2019–2023).",
        "unit_guidance": "%",
        "aliases": ("quality index q rose by",),
    },
    "tpm_raw_material_cost_savings": {
        "label": "TPM raw material cost savings",
        "domain": "manufacturing_efficiency",
        "definition": "Reported raw material cost savings after five years of TPM commitment (2019–2023).",
        "unit_guidance": "VND billion",
        "aliases": ("raw material costs saving vnd", "raw material cost savings", "raw material savings"),
    },
    "tpm_waste_reduction": {
        "label": "TPM waste reduction",
        "domain": "manufacturing_efficiency",
        "definition": "Waste reduction after five years of TPM commitment (2019–2023).",
        "unit_guidance": "%",
        "aliases": ("waste reduced by",),
    },
    "tpm_improvement_initiatives": {
        "label": "TPM improvement initiatives",
        "domain": "manufacturing_efficiency",
        "definition": "Number of initiatives reported alongside TPM savings after five years of commitment (2019–2023).",
        "unit_guidance": "initiatives",
        "aliases": ("initiatives saving vnd",),
    },
    "tpm_satisfaction_increase": {
        "label": "TPM satisfaction increase",
        "domain": "manufacturing_efficiency",
        "definition": "Satisfaction increase reported in the five-year TPM results; the report excerpt does not define the survey population.",
        "unit_guidance": "%",
        "aliases": ("satisfaction up by",),
    },
    "tpm_defect_free_streak_years": {
        "label": "Consecutive years without product defects",
        "domain": "manufacturing_efficiency",
        "definition": "Consecutive years with no reported product defect occurrences in the five-year TPM results.",
        "unit_guidance": "years",
        "aliases": ("product defects no occurrences", "defect-free years"),
    },
    "total_raw_water_intake": {
        "label": "Total raw water intake",
        "domain": "environmental_performance",
        "definition": "Annual consolidated raw water intake as disclosed in the 2025 sustainability report, in its stated reporting boundary.",
        "unit_guidance": "m³",
        "aliases": ("raw water intake",),
    },
    "recycled_reused_water": {
        "label": "Recycled or reused water",
        "domain": "environmental_performance",
        "definition": "Annual recycled or reused water volume in the 2025 sustainability report.",
        "unit_guidance": "m³",
        "aliases": ("reused water", "recycled water"),
    },
    "total_water_consumption": {
        "label": "Total water consumption",
        "domain": "environmental_performance",
        "definition": "Annual total water consumption as disclosed in the 2025 sustainability report.",
        "unit_guidance": "m³",
        "aliases": ("water consumption",),
    },
    "wastewater_discharge": {
        "label": "Total wastewater discharge",
        "domain": "environmental_performance",
        "definition": "Annual total wastewater discharge as disclosed in the 2025 sustainability report.",
        "unit_guidance": "m³",
        "aliases": ("wastewater discharge",),
    },
    "scope_1_ghg_emissions": {
        "label": "Scope 1 greenhouse-gas emissions",
        "domain": "environmental_performance",
        "definition": "Annual Scope 1 greenhouse-gas emissions in the report's stated operational control boundary.",
        "unit_guidance": "kg CO₂e",
        "aliases": ("scope 1 emissions",),
    },
    "scope_2_ghg_emissions": {
        "label": "Scope 2 greenhouse-gas emissions",
        "domain": "environmental_performance",
        "definition": "Annual Scope 2 greenhouse-gas emissions in the report's stated operational control boundary.",
        "unit_guidance": "kg CO₂e",
        "aliases": ("scope 2 emissions",),
    },
    "scope_1_2_ghg_emissions": {
        "label": "Scope 1 and 2 greenhouse-gas emissions",
        "domain": "environmental_performance",
        "definition": "Combined annual Scope 1 and Scope 2 emissions as disclosed in the report.",
        "unit_guidance": "kg CO₂e",
        "aliases": ("scope 1 and 2 emissions", "total scope 1 2"),
    },
    "dairy_product_ghg_intensity": {
        "label": "Scope 1 and 2 emissions per tonne of dairy products",
        "domain": "environmental_performance",
        "definition": "Reported average Scope 1 and 2 emissions per tonne of dairy products; preserve the report's operational boundary and unit.",
        "unit_guidance": "kg CO₂e/tonne product",
        "aliases": ("emissions per tonne of dairy products", "dairy product emissions intensity", "dairy emissions intensity"),
    },
    "sugar_product_ghg_intensity": {
        "label": "Scope 1 and 2 emissions per tonne of sugar products",
        "domain": "environmental_performance",
        "definition": "Reported average Scope 1 and 2 emissions per tonne of sugar products; preserve the report's operational boundary and unit.",
        "unit_guidance": "kg CO₂e/tonne product",
        "aliases": ("emissions per tonne of sugar products", "sugar product emissions intensity", "sugar emissions intensity"),
    },
    "total_waste_generated": {
        "label": "Total waste generated",
        "domain": "environmental_performance",
        "definition": "Annual total waste by type as reported; the report notes a changed assurance boundary in 2025 and revised 2023–2024 comparison data.",
        "unit_guidance": "kg",
        "aliases": ("total waste generated",),
    },
    "waste_recovered_recycled": {
        "label": "Waste reused, recycled, or otherwise recovered",
        "domain": "environmental_performance",
        "definition": "Annual waste reused, recycled, or otherwise recovered; interpret with the report's disclosed boundary notes.",
        "unit_guidance": "kg",
        "aliases": ("waste reused recycled recovered",),
    },
    "waste_treated_disposed": {
        "label": "Waste treated or disposed",
        "domain": "environmental_performance",
        "definition": "Annual waste treated by methods such as incineration or landfill; interpret with the report's disclosed boundary notes.",
        "unit_guidance": "kg",
        "aliases": ("waste treated landfill incineration",),
    },
    "farm_count": {
        "label": "Dairy farms",
        "domain": "farm_operations",
        "definition": "Number of domestic dairy farms stated in the 2024 sustainability report.",
        "unit_guidance": "farms",
        "aliases": ("number of dairy farms", "vinamilk farms"),
    },
    "managed_milk_cow_count": {
        "label": "Managed dairy cows",
        "domain": "farm_operations",
        "definition": "Number of dairy cows managed by the company as stated in the 2024 sustainability report.",
        "unit_guidance": "cows",
        "aliases": ("milk cows", "dairy cows", "managed dairy cows", "how many dairy cows", "đàn bò sữa"),
    },
    "raw_milk_collection_station_count": {
        "label": "Raw milk collection stations",
        "domain": "farm_operations",
        "definition": "Reported count of raw-milk collection stations; preserve operator coverage and distinguish reported totals from sums of operators.",
        "unit_guidance": "stations",
        "aliases": ("raw milk collection stations",),
    },
    "green_energy_share_manufacturing": {
        "label": "Green energy share in manufacturing",
        "domain": "environmental_performance",
        "definition": "Reported share of green energy use in manufacturing in 2024.",
        "unit_guidance": "%",
        "aliases": ("green energy usage in manufacturing", "renewable energy share"),
    },
    "electricity_saved": {
        "label": "Electricity saved",
        "domain": "environmental_performance",
        "definition": "Electricity savings reported for 2024; preserve the report's stated unit and scope.",
        "unit_guidance": "kWh",
        "aliases": ("saved electricity", "electricity saved"),
    },
    "farm_global_slp_coverage": {
        "label": "Farms meeting Global S.L.P. standards",
        "domain": "farm_operations",
        "definition": "Share of farms reported to meet Global S.L.P. standards in 2024.",
        "unit_guidance": "%",
        "aliases": ("farms meet global slp",),
    },
    "farms_using_biogas": {
        "label": "Farms using biogas systems",
        "domain": "farm_operations",
        "definition": "Share of Vinamilk farms reported to use biogas systems in 2024.",
        "unit_guidance": "%",
        "aliases": ("farms utilize the biogas system",),
    },
    "farm_ghg_inventory_coverage": {
        "label": "Farms with greenhouse-gas inventories",
        "domain": "farm_operations",
        "definition": "Share of farms covered by greenhouse-gas inventories following ISO 14064 as reported in 2024.",
        "unit_guidance": "%",
        "aliases": ("farms inventory for greenhouse gases",),
    },
    "retail_points_of_sale": {
        "label": "Supermarket and convenience-store points of sale",
        "domain": "market_performance",
        "definition": "Reported supermarket and convenience-store point-of-sale network; retain each report's estimate and scope.",
        "unit_guidance": "points of sale",
        "aliases": ("points of sale", "retail distribution points"),
    },
    "vinamilk_stores": {
        "label": "Vinamilk stores",
        "domain": "market_performance",
        "definition": "Reported count of Vinamilk-branded stores; retain each report's estimate and scope.",
        "unit_guidance": "stores",
        "aliases": ("vinamilk stores",),
    },
}

# Automatic extraction is intentionally narrower than the full analytics
# catalog. These are the few decision-driving measures worth discovering from
# public reports; supporting indicators remain available for admin entry and
# later, explicitly scoped extraction runs.
BUSINESS_DECISION_PROFILES = {
    "milk_supply": {
        "label": "Milk sourcing resilience",
        "management_question": "Is the mix of farmer-sourced and managed-farm milk keeping raw-material supply dependable?",
        "primary_metrics": (
            "farmer_raw_milk_purchased", "total_raw_milk_supply",
            "managed_farm_raw_milk", "dairy_cattle_herd_size",
            "farmer_support_coverage",
        ),
    },
    "market_performance": {
        "label": "Market performance and route-to-market reach",
        "management_question": "Which markets merit commercial diligence based on revenue scale, growth and reported route-to-market reach, and what evidence is still needed before reallocating investment?",
        "primary_metrics": (
            "domestic_consolidated_net_revenue", "domestic_consolidated_net_revenue_growth",
            "overseas_market_net_revenue", "overseas_market_net_revenue_growth",
            "market_share_lead_over_runner_up", "retail_points_of_sale", "vinamilk_stores",
        ),
    },
    "product_portfolio": {
        "label": "Product portfolio investment signals",
        "management_question": "Which product lines show reported demand or growth signals worth further investment review?",
        "primary_metrics": (
            "plant_based_milk_sales_growth", "green_farm_sales_growth",
            "green_farm_urban_purchase_consideration", "new_or_relaunched_products",
            "brand_innovation_perception",
        ),
    },
    "manufacturing_efficiency": {
        "label": "Factory productivity, cost and quality",
        "management_question": "Are production efficiency, controllable costs and reported product-quality signals improving enough to prioritize factory improvement?",
        "primary_metrics": (
            "production_lines_meeting_oee_target", "production_overhead_budget_utilization",
            "raw_material_cost_savings", "production_cost_savings",
            "tpm_productivity_increase", "tpm_defect_free_streak_years",
        ),
    },
    "human_resources": {
        "label": "Workforce capacity and capability",
        "management_question": "Is workforce scale and training keeping pace with business needs?",
        "primary_metrics": (
            "employee_headcount", "employee_headcount_change", "employee_training_hours",
        ),
    },
    "environmental_performance": {
        "label": "Environmental intensity and resource use",
        "management_question": "Are emissions intensity and key resource-use indicators moving in the right direction?",
        "primary_metrics": (
            "dairy_product_ghg_intensity", "sugar_product_ghg_intensity",
            "scope_1_2_ghg_emissions", "total_water_consumption",
            "waste_recovered_recycled",
        ),
    },
    "farm_operations": {
        "label": "Farm capacity and operating footprint",
        "management_question": "What scale and operating practices characterize Vinamilk's managed-farm network?",
        "primary_metrics": (
            "farm_count", "managed_milk_cow_count", "raw_milk_collection_station_count",
            "farms_using_biogas",
        ),
    },
}
SUPPORTED_BUSINESS_DECISION_DOMAINS = tuple(BUSINESS_DECISION_PROFILES)
BUSINESS_METRIC_DECISION_PROFILE = {
    metric_name: domain
    for domain, profile in BUSINESS_DECISION_PROFILES.items()
    for metric_name in profile["primary_metrics"]
}

# Qualifiers and period labels already live in extraction_config JSONB; expose
# them consistently to dashboard and SQL paths instead of flattening to a number.
BUSINESS_VALUE_QUALIFIER_SQL = """CASE
    WHEN extraction_config->>'value_qualifier' IN ('exact', 'approximately', 'more_than', 'at_least', 'less_than', 'at_most')
      THEN extraction_config->>'value_qualifier'
    WHEN lower(concat_ws(' ', source_quote, scope)) ~ '(at least|no fewer than|ít nhất)' THEN 'at_least'
    WHEN lower(concat_ws(' ', source_quote, scope)) ~ '(up to|at most|no more than|lên đến|tối đa)' THEN 'at_most'
    WHEN lower(concat_ws(' ', source_quote, scope)) ~ '(more than|(^|[[:space:]])over[[:space:]]|exceed(ed|s)?|greater than|hơn|trên)' THEN 'more_than'
    WHEN lower(concat_ws(' ', source_quote, scope)) ~ '(less than|under|below|dưới)' THEN 'less_than'
    WHEN lower(concat_ws(' ', source_quote, scope)) ~ '(approximately|approx\\.?|estimated?|ước tính|nearly|around|about|gần|khoảng|xấp xỉ|~)' THEN 'approximately'
    ELSE 'exact'
END"""
BUSINESS_REPORTING_PERIOD_SQL = "COALESCE(NULLIF(extraction_config->>'period', ''), 'FY')"


def resolve_business_metric_names(question: str) -> set[str]:
    """Match catalog labels/codes in a question for deterministic analytics routing."""
    text = " ".join(question.casefold().replace("_", " ").split())
    matches = set()
    for name, definition in BUSINESS_METRIC_CATALOG.items():
        aliases = {name.replace("_", " "), definition["label"], *definition.get("aliases", ())}
        if any(" ".join(alias.casefold().split()) in text for alias in aliases):
            matches.add(name)
    if (any(term in text for term in ("domestic", "local market", "nội địa"))
            and any(term in text for term in ("overseas", "international", "foreign market", "nước ngoài"))
            and any(term in text for term in ("growth", "grew", "tăng trưởng"))):
        matches.update({"domestic_consolidated_net_revenue_growth",
                        "overseas_market_net_revenue_growth"})
    if "emissions per tonne of dairy products and sugar products" in text:
        matches.update({"dairy_product_ghg_intensity", "sugar_product_ghg_intensity"})
    if (any(term in text for term in ("export market", "export country", "export markets", "thị trường xuất khẩu"))
            and any(term in text for term in ("which", "priorit", "invest", "nên", "ưu tiên", "đầu tư"))):
        matches.update({"guinea_export_revenue_growth", "hong_kong_export_revenue_growth",
                        "japan_export_revenue_growth"})
    if matches:
        return matches
    domain_terms = {
        "milk_supply": ("raw milk", "fresh milk", "farmer", "supply chain", "milk sourcing", "sữa tươi", "nông hộ", "nguồn sữa", "milk collection", "globalgap", "fertilizer", "biomass corn"),
        "manufacturing_efficiency": ("oee", "production line", "purchasing savings", "production cost", "hiệu suất dây chuyền", "tiết kiệm chi phí", "customer satisfaction", "satisfaction", "product defect", "defect-free", "quality index", "lỗi sản phẩm", "chất lượng sản phẩm"),
        "product_portfolio": ("green farm", "plant-based", "plant based", "độ nhận biết", "mức độ cân nhắc", "sữa thực vật", "new products", "brand innovation"),
        "market_performance": ("domestic revenue", "export revenue", "overseas revenue", "market share", "international market", "xuất khẩu", "tăng trưởng nội địa", "doanh thu nội địa", "thị trường trong nước", "thị trường nước ngoài", "points of sale", "vinamilk stores", "retail", "distribution reach", "điểm bán", "cửa hàng"),
        "environmental_performance": ("water", "waste", "emission", "greenhouse gas", "carbon", "energy", "nước thải", "nước sạch", "nước tiêu thụ", "nước đầu vào", "nước tái chế", "nước tái sử dụng", "nguồn nước", "chất thải", "phát thải", "khí nhà kính", "năng lượng xanh"),
        "farm_operations": ("dairy farm", "milk cow", "herd", "biogas", "global s.l.p", "trang trại", "đàn bò", "trạm thu gom sữa"),
        "human_resources": ("headcount", "staffing", "workforce", "nhân viên", "nhân sự", "lao động", "tuyển dụng"),
    }
    mentioned_domains = {
        domain for domain, terms in domain_terms.items()
        if any(term in text for term in terms)
    }
    if "environmental_performance" in mentioned_domains:
        environmental_topics = {
            "water": ("total_raw_water_intake", "recycled_reused_water", "total_water_consumption", "wastewater_discharge"),
            "waste": ("total_waste_generated", "waste_recovered_recycled", "waste_treated_disposed"),
            "emissions": ("scope_1_ghg_emissions", "scope_2_ghg_emissions", "scope_1_2_ghg_emissions",
                          "dairy_product_ghg_intensity", "sugar_product_ghg_intensity"),
            "energy": ("green_energy_share_manufacturing", "electricity_saved"),
        }
        topic_terms = {
            "water": ("water", "nước thải", "nước sạch", "nước tiêu thụ", "nước đầu vào", "nước tái chế", "nước tái sử dụng", "nguồn nước"),
            "waste": ("waste", "chất thải"),
            "emissions": ("emission", "greenhouse gas", "carbon", "phát thải", "khí nhà kính"),
            "energy": ("energy", "năng lượng"),
        }
        for topic, terms in topic_terms.items():
            if any(term in text for term in terms):
                matches.update(environmental_topics[topic])
    for name, definition in BUSINESS_METRIC_CATALOG.items():
        if definition["domain"] in mentioned_domains and definition["domain"] != "environmental_performance":
            matches.add(name)
    return matches


def resolve_business_metric_domain(question: str) -> str | None:
    """Return a domain only when metric resolution points to one unambiguous domain."""
    text = " ".join(question.casefold().split())
    if (any(term in text for term in ("domestic", "local market", "overseas", "thị trường trong nước", "nước ngoài"))
            and any(term in text for term in ("market", "thị trường", "đầu tư", "ưu tiên"))):
        return "market_performance"
    domains = {
        BUSINESS_METRIC_CATALOG[name]["domain"]
        for name in resolve_business_metric_names(question)
        if name in BUSINESS_METRIC_CATALOG
    }
    return next(iter(domains)) if len(domains) == 1 else None
