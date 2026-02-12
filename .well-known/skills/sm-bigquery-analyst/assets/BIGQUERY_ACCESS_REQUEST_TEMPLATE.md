# BigQuery Access Request Template

Use this when a user cannot query data and needs their internal admin to grant access.

## Minimum access model (least privilege)

Grant the user (or group) these roles:

1. **Project level** (required to run query jobs):
   - `roles/bigquery.jobUser`
2. **Dataset level** (required to read/query data):
   - `roles/bigquery.dataViewer` on `sm_transformed_v2`
   - `roles/bigquery.dataViewer` on `sm_metadata`

Optional dataset access based on use case:

1. `roles/bigquery.dataViewer` on `sm_experimental` (MTA/experimental tables)
2. `roles/bigquery.dataViewer` on any tenant custom datasets

Notes:

1. `roles/bigquery.jobUser` must be granted on a project/folder/org resource.
2. `roles/bigquery.dataViewer` can be granted at project, dataset, table, or view scope.
3. If you prefer simplicity over least privilege, project-level `bigquery.dataViewer` works but is broader.

## Copy/paste message for internal admin

```text
Subject: BigQuery access request for SourceMedium analysis

Hi Admin Team,

Please grant BigQuery access for:
- Principal: <user-or-group-email>
- Project: <PROJECT_ID>

Required permissions:
1) Project-level role:
   - roles/bigquery.jobUser

2) Dataset-level roles:
   - roles/bigquery.dataViewer on <PROJECT_ID>.sm_transformed_v2
   - roles/bigquery.dataViewer on <PROJECT_ID>.sm_metadata

Optional (if needed for MTA/experimental analysis):
- roles/bigquery.dataViewer on <PROJECT_ID>.sm_experimental

Success criteria after grant:
- bq query --use_legacy_sql=false --dry_run 'SELECT 1 AS ok' succeeds
- bq query --use_legacy_sql=false "SELECT 1 FROM \`<PROJECT_ID>.sm_transformed_v2.obt_orders\` LIMIT 1" succeeds

Thanks.
```

## Official Google docs

1. BigQuery roles and permissions:
   - https://cloud.google.com/bigquery/docs/access-control
2. Grant dataset/table/view access in BigQuery:
   - https://cloud.google.com/bigquery/docs/control-access-to-resources-iam
3. Grant project-level IAM roles:
   - https://cloud.google.com/iam/docs/granting-changing-revoking-access
