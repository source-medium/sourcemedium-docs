# Query Patterns

Common SQL patterns for SourceMedium BigQuery analysis.

## Daily Revenue by Channel

```sql
SELECT
  DATE(order_processed_at_local_datetime) AS order_date,
  sm_channel,
  COUNT(sm_order_key) AS order_count,
  SUM(order_net_revenue) AS revenue
FROM `your_project.sm_transformed_v2.obt_orders`
WHERE is_order_sm_valid = TRUE
  AND DATE(order_processed_at_local_datetime) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
GROUP BY 1, 2
ORDER BY 1 DESC
```

## New Customer Acquisition by Source

```sql
SELECT
  DATE(order_processed_at_local_datetime) AS order_date,
  sm_utm_source_medium,
  COUNT(DISTINCT sm_customer_key) AS new_customers,
  SUM(order_net_revenue) AS revenue,
  SAFE_DIVIDE(SUM(order_net_revenue), COUNT(DISTINCT sm_customer_key)) AS avg_first_order_value
FROM `your_project.sm_transformed_v2.obt_orders`
WHERE is_order_sm_valid = TRUE
  AND is_first_purchase_order = TRUE
GROUP BY 1, 2
ORDER BY 1 DESC
```

## Product Performance with Margins

```sql
SELECT
  product_title,
  sku,
  SUM(order_line_quantity) AS units_sold,
  SUM(order_line_net_revenue) AS revenue,
  SUM(order_line_product_cost) AS cogs,
  SUM(order_line_gross_profit) AS profit,
  SAFE_DIVIDE(SUM(order_line_gross_profit), SUM(order_line_net_revenue)) AS profit_margin
FROM `your_project.sm_transformed_v2.obt_order_lines`
WHERE is_order_sm_valid = TRUE
GROUP BY 1, 2
ORDER BY revenue DESC
LIMIT 20
```

## Ad Performance Summary

```sql
SELECT
  ad_platform,
  SUM(ad_spend) AS spend,
  SUM(ad_impressions) AS impressions,
  SUM(ad_clicks) AS clicks,
  SAFE_DIVIDE(SUM(ad_clicks), SUM(ad_impressions)) AS ctr,
  SAFE_DIVIDE(SUM(ad_spend), SUM(ad_clicks)) AS cpc
FROM `your_project.sm_transformed_v2.rpt_ad_performance_daily`
WHERE report_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
GROUP BY 1
ORDER BY spend DESC
```

## LTV Cohort Analysis (CRITICAL)

Queries against `rpt_cohort_ltv_*` tables have strict requirements:

### Rules

1. **Filter `sm_order_line_type` to exactly ONE value** — the table has 3 rows per cohort. Without this filter, all metrics inflate 3x.
   - Valid values: `'all_orders'`, `'subscription_orders_only'`, `'one_time_orders_only'`
   - Valid: `WHERE sm_order_line_type = 'all_orders'`
   - Valid: `GROUP BY sm_order_line_type` (when comparing order types)
   - Invalid: no filter at all, or `IN ('all_orders', 'subscription_orders_only')`

2. **`months_since_first_order` is 0-indexed** — 0 = cohort month, 12 = 12-month mark.

3. **Aggregation** — use `AVG(SAFE_DIVIDE(metric, cohort_size))`, not `SAFE_DIVIDE(SUM(metric), SUM(cohort_size))`.

4. **Dimension** — use `acquisition_order_filter_dimension = 'source/medium'` for marketing analysis.

5. **Revenue column** — use `cumulative_order_net_revenue` (not `cumulative_gross_profit`).

### Example Query

```sql
SELECT
  first_order_month,
  months_since_first_order,
  AVG(SAFE_DIVIDE(cumulative_order_net_revenue, cohort_size)) AS avg_ltv
FROM `your_project.sm_transformed_v2.rpt_cohort_ltv_by_first_valid_purchase_attribute_no_product_filters`
WHERE sm_order_line_type = 'all_orders'
  AND acquisition_order_filter_dimension = 'source/medium'
  AND months_since_first_order <= 12
GROUP BY 1, 2
ORDER BY 1, 2
```

## Discover Categorical Values (Before Filtering)

Always discover values before using `LIKE` or `IN` on categorical columns:

```sql
-- See what channel values exist
SELECT sm_channel, COUNT(*) AS n
FROM `your_project.sm_transformed_v2.obt_orders`
WHERE is_order_sm_valid = TRUE
GROUP BY 1 ORDER BY 2 DESC

-- See what order sequence values exist
SELECT subscription_order_sequence, COUNT(*) AS n
FROM `your_project.sm_transformed_v2.obt_orders`
WHERE is_order_sm_valid = TRUE
GROUP BY 1 ORDER BY 2 DESC
```

## Check Data Freshness

```sql
SELECT
  table_id,
  TIMESTAMP_MILLIS(last_modified_time) AS last_modified
FROM `your_project.sm_transformed_v2.__TABLES__`
WHERE table_id IN ('obt_orders', 'obt_customers', 'obt_order_lines')
ORDER BY last_modified DESC
```

## MTA / Attribution Queries

If the question involves multi-touch attribution, use the experimental dataset:

```sql
FROM `your_project.sm_experimental.obt_purchase_journeys_with_mta_models`
```

For standard order/revenue analysis, use `sm_transformed_v2` tables.
