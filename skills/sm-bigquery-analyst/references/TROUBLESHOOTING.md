# Troubleshooting

Common failures and how to resolve them.

## CLI Tool Issues

### gcloud or bq not found

```bash
# Check if installed
gcloud --version
bq --version

# If not installed, install Google Cloud SDK
# macOS: brew install google-cloud-sdk
# Or visit: https://cloud.google.com/sdk/docs/install
```

### Wrong project

```bash
# Check current project
gcloud config get-value project

# Set correct project
gcloud config set project <PROJECT_ID>
```

## Authentication Issues

### Not authenticated

```bash
# Check authenticated accounts
gcloud auth list

# If empty or wrong account, authenticate
gcloud auth login

# Re-authenticate application default credentials
gcloud auth application-default login
```

### BigQuery API disabled

**Error message:** "BigQuery API has not been used in project..."

**Solution:** Enable BigQuery API in target project:
1. Go to Google Cloud Console
2. Navigate to APIs & Services > Library
3. Search for "BigQuery API"
4. Click Enable

## Permission Issues

### Access Denied: bigquery.jobs.create

**What it means:** Cannot run query jobs in this project.

**Solution:** Request `roles/bigquery.jobUser` on the project.

### Access Denied: bigquery.tables.getData

**What it means:** Cannot read data from the table.

**Solution:** Request `roles/bigquery.dataViewer` on the dataset.

### Table not found

**What it means:** Either the table doesn't exist, or you don't have permission to see it.

**Debug steps:**
1. Verify the project ID is correct
2. Verify the dataset name (e.g., `sm_transformed_v2`)
3. Verify the table name
4. If all names are correct, you may lack `roles/bigquery.dataViewer` on the dataset

## Query Errors

### Column not found: smcid

**Fix:** Use `sm_store_id` instead. The column `smcid` is an internal name that does not exist in customer tables.

### Column not found: sm_marketing_channel

**Fix:** Use `sm_channel` instead.

### Type mismatch in WHERE clause

**Problem:** Comparing TIMESTAMP to DATE directly.

```sql
-- Wrong
WHERE order_processed_at_local_datetime >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)

-- Correct
WHERE DATE(order_processed_at_local_datetime) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
```

### Division by zero

**Fix:** Always use `SAFE_DIVIDE(numerator, denominator)` instead of `numerator / denominator`.

## Cost / Performance Issues

### Query too expensive

**Warning signs:**
- "This query will process X GB"
- Query takes longer than 30 seconds for simple aggregations

**Solutions:**
1. Add date filters: `WHERE DATE(column) >= '2024-01-01'`
2. Add `LIMIT` clause
3. Use partition filters if available
4. Run with `--dry_run` first to check cost

### Resources exceeded

**Problem:** Query uses too much memory.

**Solutions:**
1. Reduce date range
2. Use `GROUP BY` on fewer columns
3. Break into multiple smaller queries

## Getting Help

If issues persist:

1. Run the setup verification commands from SKILL.md
2. Copy the exact error message
3. Share with your SourceMedium support contact
