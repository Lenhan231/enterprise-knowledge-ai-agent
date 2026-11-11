-- Revenue, market growth and export-reach observations have their own
-- decision domain; product_portfolio remains focused on product outcomes.
UPDATE public.business_metric_evidence
SET domain = 'market_performance'
WHERE domain = 'product_portfolio'
  AND metric_name = ANY (ARRAY[
      'domestic_revenue_growth',
      'market_share_lead_over_runner_up',
      'domestic_consolidated_net_revenue',
      'parent_domestic_net_revenue',
      'domestic_consolidated_net_revenue_growth',
      'parent_domestic_net_revenue_growth',
      'export_net_revenue',
      'export_net_revenue_growth',
      'overseas_market_net_revenue',
      'overseas_market_net_revenue_growth',
      'domestic_revenue_share',
      'overseas_revenue_share',
      'foreign_subsidiary_revenue',
      'foreign_subsidiary_revenue_growth',
      'export_markets_count',
      'new_export_markets_entered',
      'export_trade_promotion_programs'
  ]::text[]);
