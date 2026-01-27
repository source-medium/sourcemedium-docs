# Query Library (AI Analyst) — Spec (Codex)

Status: Draft  
Owner: TBD (Docs + AI Analyst)  
Last updated: 2026-01-27

## Background

We want a **high-quality, highly relevant query library** that:

1) Improves the AI Analyst’s SQL generation (better patterns + fewer mistakes).  
2) Improves customer self-serve docs (“how to query SourceMedium tables”).  
3) Creates a testable, versioned set of “gold” SQL templates we can QA/validate in batches.

We already have three strong sources of truth:

- **Uni2 SQL rules** (authoritative): `src/agent_core/agents/prompts.py` + `src/agent_core/domain_tables.py`.  
- **QA patterns + SQL guidelines** (useful but secondary when conflicting): `uni-training/.claude/shared/*`.  
- **Semi-vetted eval dataset** (seed set): `uni-training/evaluation/training_simplified.json` (136 Qs, with SQL strings + insights; requires validation).

Important conflict resolution rule:
- If `uni-training/.claude` guidance conflicts with **uni2** logic, **prefer uni2**.

## Goals

- Establish a **repeatable batching workflow** (5–10 queries per batch) to: prioritize → normalize → QA → validate → publish.
- Build an initial “gold” set focused on **core tables** and **high-frequency questions** (revenue/orders/AOV, products, new vs repeat, basic marketing/ad performance, cohorts).
- Ensure every published query is:
  - safe to copy/paste (uses placeholders like `your_project.sm_transformed_v2.<table>`),
  - schema-correct (columns exist),
  - aligned with uni2 business logic conventions (filters, attribution semantics, channel semantics).

## Non-goals (for v0)

- Exhaustive coverage of every table and edge-case.
- Complex multi-touch/MTA journey analysis (only include when explicit intent; later batches).
- Highly tenant-specific enumerations (UTM/campaign value lists) embedded directly in docs.

## Guiding Principles (Hard Requirements)

### SQL correctness + safety

- **No invented columns**: only reference documented columns for the table.
- **Always use valid-order filters** on order tables:
  - `WHERE is_order_sm_valid = TRUE` (and only use `order_cancelled_at` when it exists on the selected table).
- **No LIKE/REGEXP on low-cardinality categorical columns** (uni2 rule):
  - For dimensions like `sm_channel`, `source_system`, `sm_utm_source`, `sm_utm_medium`, `sm_utm_source_medium`, etc. use `=` / `IN` with normalized comparisons (e.g., `LOWER(TRIM(col)) = 'meta'`).
  - If the query needs “contains”-style matching, prefer a **discovery-first** step that enumerates actual values, then exact-match in the final query.
- **Assumptions header** at top of every “gold” query:
  - `-- Assumptions: timeframe=<...> | metric=<...> | grain=<...> | scope=<...>`
- **Channel semantics must be correct** (uni2 rule):
  - `source_system` = system/platform of origin (ads platform vs commerce platform depends on table domain).
  - `sm_channel` = normalized sales channel (`online_dtc`, `amazon`, `tiktok_shop`, etc.). Do not substitute one for the other.
- **Default timeframe**:
  - If query is an operational metric and the question lacks a timeframe, default to **last 30 days**.

### Docs compatibility

- SQL in docs should use:
  - `your_project.sm_transformed_v2.<table>` (and `your_project.sm_experimental.<table>` only for explicitly experimental/MTA examples).
- Keep examples compact and scannable:
  - Prefer “one query per example” (or a clearly labeled 2-step pattern when discovery is required).

## Where the Query Library Lives (Docs)

We publish in two places (with the same underlying “gold” queries):

1) **AI Analyst Query Library pages** (domain-oriented, question-first)
   - Proposed location: `sourcemedium-docs/ai-analyst/query-library/`
   - Pages per domain (mirrors “What You Can Ask”):
     - Orders & Revenue
     - Customers
     - Products
     - Marketing & Ads
     - Email & SMS
     - Cohorts & LTV
     - Web Analytics / Funnel
     - Refunds & Support (optional early)
   - Each page: 8–20 queries over time, with “gold” badge and clear tags.

2) **Per-table “Example Queries” sections** (table-oriented, schema-first)
   - Add a small curated set (2–5) to high-traffic tables under:
     - `sourcemedium-docs/data-activation/data-tables/sm_transformed_v2/*.mdx`
   - Start with:
     - `obt_orders`, `dim_orders`, `obt_order_lines`, `rpt_executive_summary_daily`, `rpt_ad_performance_daily`, `rpt_cohort_ltv_*`, `rpt_outbound_message_performance_daily`, `obt_funnel_event_history`.

## Query Entry Format (Canonical Metadata)

Each query should have consistent metadata so it can be searched, deduped, and QA’d.

Minimum fields:
- `id`: stable identifier (e.g., `QL-ORD-001`)
- `title`: human-readable
- `domain`: one of the doc domains above
- `primary_table`: canonical table name (e.g., `sm_transformed_v2.obt_orders`)
- `tables_used`: list (keep small)
- `archetype`: `trend` | `breakdown` | `ranking` | `cohort_curve` | `funnel` | `diagnostic` | `exploration`
- `time_grain`: `day` | `week` | `month` | `none`
- `default_timeframe`: e.g., `last_30_days`
- `tags`: e.g., `["sm_channel", "new_vs_repeat", "pop_comparison"]`
- `assumptions`: the literal assumptions header values
- `sql`: the final SQL (docs-ready placeholders)
- `notes`: pitfalls + how to adapt (optional)

Optional but recommended:
- `example_questions`: 2–5 natural language phrasings that this query answers.
- `validation_checks`: a short checklist (expected ranges, sanity checks).

## Archetypes (Reusable Building Blocks)

We standardize common shapes to maximize reuse:

- `trend`: metric over time + optional period-over-period (PoP) comparison
- `breakdown`: metric by dimension (`sm_channel`, `source_system`, `sm_store_id`)
- `ranking`: top-N entities (products, campaigns, customers) with thresholds
- `cohort_curve`: retention/LTV over months since acquisition
- `funnel`: session/event funnel steps with conversion rates (when available)
- `diagnostic`: data freshness / attribution health / null-coverage checks
- `exploration`: distinct-value discovery query used before exact matches

## Prioritization (How We Pick the Next Batch)

We prioritize with a scoring rubric per candidate query:

1) **User value / frequency**: how often this comes up (use eval dataset + support intuition)
2) **Template reusability**: can it answer multiple phrasings with small parameter tweaks?
3) **Low QA risk**: minimal joins, stable columns, clear semantics
4) **Docs placement value**: would a customer actually copy/paste this from a table page?

Practical batch selection rule:
- Each batch should cover **2–3 archetypes** and **1–2 primary tables** max.
- First batches should skew heavily toward:
  - `obt_orders` / `dim_orders` / `obt_order_lines`
  - plus one “adjacent” table when needed (e.g., `rpt_executive_summary_daily`).

Seed evidence we already have:
- `training_simplified.json` usage is concentrated in Orders/Order Lines/Order Dims and then cohort + MTA.
- It includes deprecated `sm_experimental.rpt_mta_models_v4` references; those should not be promoted to “gold”.

## QA + Validation Workflow (Batch-Based)

### Step 0 — Candidate selection
- Pick 5–10 candidates using the rubric.
- Decide publication targets:
  - AI Analyst Query Library domain page(s)
  - Specific table pages (if applicable)

### Step 1 — Normalize to docs conventions
- Replace literal project IDs with `your_project`.
- Ensure tables are `sm_transformed_v2` unless explicitly experimental.
- Add assumptions header.
- Ensure `is_order_sm_valid = TRUE` is present where required.
- Remove/avoid deprecated tables (e.g., `sm_experimental.rpt_mta_models_v4`).

### Step 2 — Static validation (CI-friendly)
We can validate without warehouse access:

- **Schema/column validation**:
  - Use existing script: `sourcemedium-docs/scripts/docs_column_accuracy.py` (extend or reuse) to validate SQL blocks reference real columns for referenced tables.
- **Style + rule linting** (new checks; should mirror uni2 constraints):
  - enforce assumptions header
  - ban LIKE/REGEXP on categorical columns (or require a “discovery query” pattern first)
  - enforce dataset naming (`your_project.sm_transformed_v2`)
  - enforce required filters for orders tables (`is_order_sm_valid = TRUE`)

### Step 3 — Live validation (engineer-run gate)
- Run BigQuery dry-run for each query example (per docs repo guidance):
  - `bq query --dry_run --use_legacy_sql=false "<sql>"`
- When feasible, run the query with a constrained timeframe and `LIMIT` to verify it returns plausible results.

### Step 4 — Human QA checklist
- Semantics:
  - `source_system` vs `sm_channel` usage correct
  - revenue definition consistent (prefer `order_net_revenue` unless explicitly otherwise)
  - time bucket derivations correct (BigQuery GoogleSQL)
- Safety:
  - no invented columns
  - no categorical LIKE/REGEXP
  - required validity filters present
- UX:
  - query answers a real question and is easily adaptable
  - notes mention how to scope by store/channel safely

### Step 5 — Publish
- Add to:
  - domain query library page(s)
  - relevant table pages (“Example Queries” section)
- Keep each page scannable with consistent formatting:
  - “When to use”
  - “SQL”
  - “How to adapt” (optional)
  - “Common pitfalls” (optional)

## Batch 1 Recommendation (Initial “Gold” Set)

Target: high ROI, low risk, core tables. Primarily `obt_orders` + `dim_orders` + `obt_order_lines`.

Suggested batch contents (example; final selection should follow rubric):

1) Revenue / Orders / AOV trend (daily) + PoP comparison  
2) Revenue / Orders by `sm_channel` (include `sm_store_id`)  
3) New vs repeat customers (use `sm_valid_order_index = 1`)  
4) Top SKUs/products by net revenue (with non-product filters as needed)  
5) Discount + refund contribution rates (safe use of negative fields)  
6) (Optional) Attribution completeness summary using `sm_utm_source_medium` with exact-match hygiene (no LIKE/REGEXP)

## Handling “Discovery-First” Without Breaking uni2 Rules

Some analyses (especially UTMs) are high-entropy in practice. To stay aligned with uni2’s “no categorical LIKE/REGEXP” rule, doc examples should prefer:

- A small **exploration query** to enumerate actual distinct values (recent window, top by frequency).
- A final query that uses **exact matches / IN** with normalized comparisons.

This also avoids embedding tenant-specific value assumptions in docs.

## Success Metrics (What “Good” Looks Like)

- We can consistently ship 5–10 “gold” queries per batch with low churn.
- Docs examples pass static schema checks and dry-run checks.
- The AI Analyst produces fewer SQL retries / QA failures on the same archetypes.
- Coverage improves against the eval set (e.g., % of eval questions matched to a “gold” archetype).

## Open Questions

1) Source of truth:
   - Should canonical query metadata live in `uni2/` and sync into docs, or live directly in `sourcemedium-docs/`?
2) “Gold” vs “Draft”:
   - Do we publish drafts in docs (clearly marked), or keep drafts internal until validated?
3) MTA sequencing:
   - When do we start including MTA examples (explicit intent only), and how do we label experimental limitations?

