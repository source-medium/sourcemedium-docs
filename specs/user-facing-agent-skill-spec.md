# User-Facing Agent Skill Spec (SourceMedium BigQuery)

Status: Proposed (finalized v1 decisions)  
Owner: Docs + AI Analyst + Data Platform  
Last updated: 2026-02-08

## 1) Goal

Define one public, user-facing skill that helps tenants/end users:

1. Set up BigQuery CLI access.
2. Verify project and dataset/table access.
3. Ask analytical questions with auditable SQL receipts.
4. Ground explanations in SourceMedium docs and real schema/runtime constraints.

The skill must work across **Codex** and **Claude Code**.

## 2) Final v1 Decisions

1. **Single skill first**: ship `sm-bigquery-analyst`.
2. **Canonical host is not the docs site**:
   - Canonical machine-readable artifact lives in a dedicated/public GitHub skills repo.
   - Docs site hosts human-facing pages and install instructions only.
3. **Agent Skills spec compliance is mandatory**:
   - Required frontmatter fields and naming constraints must pass validation.
4. **skills.sh publication path**:
   - Publish from GitHub repo.
   - Provide install commands in docs.
   - Leaderboard listing is automatic based on `npx skills add` telemetry.

## 3) Scope

### In scope

1. User setup flow (`gcloud`/`bq`, auth, project selection, access checks).
2. Querying and analysis workflow with strict output contract.
3. Docs-first guidance using canonical SourceMedium pages.
4. Access-escalation workflow with exact copy/paste admin request template.
5. Internal grounding via generated references from `reporting_queries` and `uni`.
6. Packaging for Codex + Claude compatibility.

### Out of scope (v1)

1. IAM provisioning automation.
2. Production table mutation by default.
3. Replacing `uni` tool orchestration.
4. Multi-skill public taxonomy.

## 4) Convention: Where This Lives

### 4.1 Canonical machine-readable location

Use a skill repo structure:

```text
<skills-repo>/
└── skills/
    └── sm-bigquery-analyst/
        ├── SKILL.md
        ├── references/
        ├── scripts/
        ├── assets/           # optional
        └── agents/openai.yaml # optional, Codex-facing metadata
```

This is the source for installation and distribution.

### 4.2 Docs-site location (human-facing)

Add docs pages under a dedicated section (for example `AI Analyst -> Agent Skills`):

1. `ai-analyst/agent-skills/index.mdx` (overview + skill catalog)
2. `ai-analyst/agent-skills/sm-bigquery-analyst.mdx` (what it does + install commands + examples)

Docs pages are explanatory. They should not be treated as canonical SKILL source.

## 5) Agent Skills Spec Compliance Requirements

`SKILL.md` must include YAML frontmatter with:

1. Required:
   - `name`
   - `description`
2. Optional:
   - `license`
   - `compatibility`
   - `metadata`
   - `allowed-tools` (experimental)

Hard constraints:

1. `name`:
   - 1-64 chars
   - lowercase alphanumeric + hyphens
   - no leading/trailing hyphen
   - no consecutive hyphens
   - must match parent directory name
2. `description`:
   - 1-1024 chars
   - must describe what it does and when to use it

Structure guidance:

1. Keep main `SKILL.md` concise (recommended under 500 lines).
2. Use progressive disclosure with `references/` and `scripts/`.
3. Keep file references one level deep from `SKILL.md`.

Validation gate:

1. `skills-ref validate ./skills/sm-bigquery-analyst`

## 6) skills.sh Publishing Convention

Distribution model:

1. Skills are hosted in GitHub repos.
2. Install via CLI using one of:
   - `npx skills add <owner/repo>` (collection/repo install)
   - `npx skills add https://github.com/<owner>/<repo> --skill <skill-name>` (single-skill install)

Leaderboard/listing convention:

1. No manual listing flow required.
2. Skills appear via anonymous install telemetry from `npx skills add`.

Docs requirement for adoption:

1. Publish copy/paste install commands on docs page.
2. Include repo link and version/change notes.

## 7) Verified SourceMedium System Constraints (Grounding)

### 7.1 `reporting_queries` (dbt source of truth)

1. Canonical dataset/model group definitions are in `dbt_project.yml`.
2. Customer-facing rename map is in `mdw_schema_config.rename_column_map_all` (for example `smcid -> sm_store_id`).
3. Customer-facing exclusions are in `mdw_schema_config.excluded_columns_all_tables`.
4. Tenant metadata dictionary generation is tenant-table based.

### 7.2 `uni` (runtime source of truth)

1. Startup requires metadata from `{BIGQUERY_PROJECT_ID}.sm_metadata.dim_data_dictionary`.
2. Table availability and schema context are metadata-gated.
3. SQL flow is identify tables -> generate SQL -> normalize/cleanup -> dry-run -> execute.
4. Docs context can be injected from Mintlify retrieval.

### 7.3 `sourcemedium-docs` (canonical user docs routes)

1. `/onboarding/analytics-tools/bigquery-essentials`
2. `/data-activation/template-resources/sql-query-library`
3. `/data-activation/data-tables/sm_transformed_v2/index`
4. `/data-activation/data-tables/sm_metadata/dim_data_dictionary`
5. `/help-center/core-concepts/data-definitions/is-order-sm-valid`
6. `/onboarding/getting-started/how-to-manage-user-access`
7. `/ai-analyst/agent-skills/bigquery-access-request-template`

## 8) Skill UX Contract (Non-Negotiable)

For analytical questions, always output:

1. **Answer** (plain English).
2. **SQL receipt** (copy/paste runnable BigQuery SQL).
3. **Notes/assumptions** (time window, metric definition, grain, scope, timezone, attribution lens).
4. **Verify command** (`bq query --use_legacy_sql=false '<SQL>'`).

If blocked by setup/access:

1. State exact failing step.
2. State exact permissions ask (project/dataset + role-level guidance).
3. Include copy/paste request text the user can send to their internal admin.
4. Never fabricate numbers.

## 9) Query Guardrails (SourceMedium conventions)

1. Fully qualify tables: `` `project.dataset.table` ``.
2. Use `is_order_sm_valid = TRUE` for order analyses unless explicitly justified.
3. Use `sm_store_id` (not `smcid`) in user-facing SQL.
4. Use `SAFE_DIVIDE` for ratio metrics.
5. Handle DATE/TIMESTAMP types explicitly.
6. Avoid `LIKE`/`REGEXP` on low-cardinality categoricals; discover values first.
7. Bound exploratory queries with `LIMIT` and time filters.

## 10) Cross-Agent Packaging and Sync

Canonical source:

1. Dedicated/public skills repo (`skills/sm-bigquery-analyst`).

Compatibility mirrors:

1. Codex: `agents/openai.yaml` metadata in skill folder.
2. Claude: mirrored copy under `.claude/skills/sm-bigquery-analyst/` in repos that need local invocation.

Sync method (v1):

1. Scripted one-way sync from canonical skill folder to mirror targets.
2. Prevent manual drift by CI check (hash or diff check on `SKILL.md` and `references/`).

## 11) Internal Insight Integration (Generated References)

The user-facing `SKILL.md` stays concise. Internal depth lives in generated reference files:

1. `references/generated/dbt-contract.md`
   - Dataset defaults, model lists, rename map, exclusions.
2. `references/generated/uni-execution-contract.md`
   - Metadata prerequisites, table gating behavior, SQL validation lifecycle, docs-context behavior.

Refresh mechanism:

1. `scripts/refresh_references.sh` reads local sibling repos (`reporting_queries`, `uni`) and regenerates these files.

## 12) Rollout Plan

### Phase 1: Scaffold and compliance

1. Create canonical skill folder.
2. Implement spec-compliant frontmatter and structure.
3. Add validation command in CI.

### Phase 2: Content and grounding

1. Draft SKILL workflow (setup -> verify -> analyze).
2. Add generated internal references.
3. Add docs map and troubleshooting references.

### Phase 3: Publication

1. Publish in GitHub skills repo.
2. Add docs pages with install commands and examples.
3. Validate install path via `npx skills add ...`.

### Phase 4: Cross-agent QA

Run prompt matrix in Codex and Claude:

1. Missing CLI.
2. Wrong project.
3. Permission denied.
4. Standard metric query.
5. Ambiguous definition query.
6. Suspicious data-quality query (must do discovery-first diagnostics).

## 13) Acceptance Criteria (v1)

1. One skill installs and runs via skills CLI from GitHub.
2. Docs site contains human-facing skill page(s) with working install commands.
3. `SKILL.md` passes Agent Skills validation requirements.
4. Every analytical response includes SQL receipt + assumptions + verification command.
5. SQL output follows SourceMedium naming/filter conventions.
6. Internal grounding references are generated from both `reporting_queries` and `uni`.
7. Dedicated docs article exists with minimum roles + admin request template.
8. No fabricated outputs when setup/access fails.

## 14) References

Internal:

1. `reporting_queries/dbt_project.yml`
2. `reporting_queries/macros/distro/copy_data_mdw/dda_column_aliases.sql`
3. `reporting_queries/macros/distro/mdw/utils/generate_tenant_data_dictionary.sql`
4. `uni/src/platforms/slack/app.py`
5. `uni/src/agent_core/async_utils.py`
6. `uni/src/agent_core/agents/tools.py`
7. `uni/src/integrations/mintlify.py`
8. `sourcemedium-docs/onboarding/analytics-tools/bigquery-essentials.mdx`
9. `sourcemedium-docs/data-activation/template-resources/sql-query-library.mdx`
10. `sourcemedium-docs/data-activation/data-tables/sm_transformed_v2/index.mdx`
11. `sourcemedium-docs/data-activation/data-tables/sm_metadata/dim_data_dictionary.mdx`
12. `sourcemedium-docs/help-center/core-concepts/data-definitions/is-order-sm-valid.mdx`
13. `sourcemedium-docs/onboarding/getting-started/how-to-manage-user-access.mdx`
14. `sourcemedium-docs/ai-analyst/agent-skills/bigquery-access-request-template.mdx`

External:

1. https://agentskills.io/specification
2. https://agentskills.io/integrate-skills
3. https://agentskills.io/home
4. https://skills.sh/docs/cli
5. https://skills.sh/docs/faq
6. https://cloud.google.com/bigquery/docs/access-control
7. https://cloud.google.com/bigquery/docs/control-access-to-resources-iam
8. https://cloud.google.com/iam/docs/granting-changing-revoking-access
