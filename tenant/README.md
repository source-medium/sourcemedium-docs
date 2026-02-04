# Tenant-Specific Documentation

This folder contains hidden documentation pages for individual tenants. These pages are **not** included in the public navigation and are only accessible via direct URL.

## Structure

```
tenant/
├── README.md                    # This file
├── {tenant_id}/
│   ├── index.mdx               # Tenant overview page
│   └── custom-objects.mdx      # Custom objects inventory
```

## Access URLs

Documentation is accessible at:
- Overview: `https://docs.sourcemedium.com/tenant/{tenant_id}`
- Custom Objects: `https://docs.sourcemedium.com/tenant/{tenant_id}/custom-objects`

### Current Tenants

| Tenant | Custom Objects | URL |
|--------|---------------|-----|
| avenuez | 5 | `/tenant/avenuez/custom-objects` |
| catalinacrunch | 7 | `/tenant/catalinacrunch/custom-objects` |
| catchco | 15 | `/tenant/catchco/custom-objects` |
| cpap | 54 | `/tenant/cpap/custom-objects` |
| elixhealing | 1 | `/tenant/elixhealing/custom-objects` |
| fluencyfirm | 10 | `/tenant/fluencyfirm/custom-objects` |
| guardianbikes | 32 | `/tenant/guardianbikes/custom-objects` |
| idyl | 14 | `/tenant/idyl/custom-objects` |
| irestore4 | 25 | `/tenant/irestore4/custom-objects` |
| neurogum | 46 | `/tenant/neurogum/custom-objects` |
| peoplebrandco | 8 | `/tenant/peoplebrandco/custom-objects` |
| pillar3cx | 8 | `/tenant/pillar3cx/custom-objects` |
| piquetea | 61 | `/tenant/piquetea/custom-objects` |
| theperfectjean | 9 | `/tenant/theperfectjean/custom-objects` |
| xcvi | 100 | `/tenant/xcvi/custom-objects` |
| zbiotics | 100+ | `/tenant/zbiotics/custom-objects` |

## Data Source

Documentation is generated from `sm-{tenant}.sm_metadata.dim_tenant_custom_objects` tables, which are populated by the `generate_dim_tenant_custom_objects` macro.

### Regenerating Documentation

To regenerate documentation for all tenants:

```bash
# 1. First, refresh the source data
dbt run-operation generate_dim_tenant_custom_objects

# 2. Then regenerate docs (use the Python script in /tmp or create a new one)
python3 /tmp/generate_tenant_docs.py
python3 /tmp/generate_tenant_index.py
```

### Adding a New Tenant

1. Ensure the tenant has `dim_tenant_custom_objects` populated
2. Add tenant to the generation scripts
3. Run the generation scripts
4. Commit the new MDX files

## Security Model

These pages use **security through obscurity**:
- Not listed in public navigation (`docs.json`)
- No authentication required
- Accessible to anyone with the direct URL

This is intentional - the data is metadata about table structures, not sensitive business data. For truly sensitive documentation, consider upgrading to Mintlify Pro for password protection.

## Maintenance

- **Automated updates**: Consider setting up a scheduled job to regenerate these docs weekly
- **New tenants**: Add to generation scripts when onboarding
- **Tenant offboarding**: Remove directory when tenant churns
