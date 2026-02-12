---
name: sourcemedium
description: SourceMedium AI Analyst capabilities for BigQuery analysis. Install the full skill package for your coding agent.
---

# SourceMedium AI Analyst

Install the full skill package for your coding agent:

```bash
npx skills add source-medium/skills@v1.0.0
```

## Quick Start (Copy/Paste)

Copy this prompt and give it to your coding agent:

```
Install the SourceMedium BigQuery analyst skill and help me verify my setup:

1. Run: npx skills add source-medium/skills@v1.0.0
2. Run the setup verification commands from the skill
3. Confirm my BigQuery access is working

My BigQuery project ID is: [YOUR_PROJECT_ID]
```

## What you get

| Skill | Description |
|-------|-------------|
| `sm-bigquery-analyst` | Query SourceMedium BigQuery safely. Emits SQL receipts. SELECT-only, cost-guarded. |
| `sm-bigquery-analyst-manual` | Manual-only version. Requires explicit invocation. |

## Features

- **Setup verification** — validates gcloud/bq CLI, authentication, and table access
- **Safe queries** — SELECT-only, dry-run first, cost-guarded
- **SQL receipts** — every answer includes copy/paste SQL + verification command
- **No fabrication** — if access fails, returns exact error and access request template

## Documentation

See [docs.sourcemedium.com/ai-analyst/agent-skills](https://docs.sourcemedium.com/ai-analyst/agent-skills) for full documentation.
