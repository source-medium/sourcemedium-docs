# Source Medium Documentation

This repository contains the Mintlify documentation for the Source Medium dbt repository.

## Documentation Workflows

### Updating Docs from Parent Repository

Documentation can be updated from the parent dbt repository (`reporting_queries`) using the following steps:

1. Navigate to the parent repository root:
   ```bash
   cd /path/to/reporting_queries
   ```

2. Run the documentation generation script:
   ```bash
   ./bin/generate_mintlify_docs.sh
   ```

3. The script will:
   - Extract information from dbt's manifest and catalog files
   - Convert it to Markdown files in the appropriate directories
   - Commit and push changes to this repository

4. After the script finishes, update the submodule reference in the parent repository:
   ```bash
   git add mintlify
   git commit -m "Update mintlify docs"
   git push
   ```

### Direct Documentation Editing

For making direct changes to documentation files (not generated from dbt), follow this workflow:

1. Create a new branch for your changes:
   ```bash
   git checkout -b your-branch-name
   ```

2. Make your changes to the documentation files

3. Preview your changes locally (requires Mintlify CLI):
   ```bash
   npm i -g mintlify  # Install if not already installed
   mintlify dev
   ```

4. Commit and push your changes:
   ```bash
   git add .
   git commit -m "Description of your changes"
   git push -u origin your-branch-name
   ```

5. Create a pull request using GitHub CLI:
   ```bash
   gh pr create --title "Your PR title" --body "Description of your changes"
   ```

6. Merge the pull request:
   ```bash
   gh pr merge <PR-NUMBER> --merge
   ```

7. After merging, don't forget to update the main repository to point to the latest version of this submodule.

8. When sending Slack notifications about documentation updates, include a link to the PR diffs:
   ```
   📚 *Documentation Update*: <description>

   *View the updated documentation here*: <link>

   *See PR & Diffs*: <PR-URL>/files
   ```
   This allows team members to easily view the changes made to the documentation.

## Content Structure

- `models/`: Documentation for dbt models
- `macros/`: Documentation for dbt macros
- `seeds/`: Documentation for dbt seeds
- `snapshots/`: Documentation for dbt snapshots
- `analyses/`: Documentation for dbt analyses
- `data-inputs/`: Documentation for data input platforms
- `data-transformations/`: Documentation for data transformation processes
- `data-activation/`: Documentation for data activation platforms

## Adding New Content

Add new content with MDX files using this template:

```md
---
title: "Page Title"
sidebarTitle: "Sidebar title (optional - if different from page title)"
description: "Subtitle (optional)"
---

Content goes here...
```

## Customizing Branding

Brand settings are configured in the `v2-mint.json` file, including:
- Company name
- Logo
- Favicon
- Color scheme
- Navigation structure

## Deployment

Documentation is automatically deployed to the Mintlify site when changes are pushed to the master branch of this repository via the GitHub workflow in `.github/workflows/mintlify-docs-update.yml`.

If the GitHub workflow fails, you can manually deploy through the Mintlify dashboard.

## Documentation URL

Our documentation is available at: https://docs.sourcemedium.com/

## Last Updated

This documentation was last tested on: `March 5, 2024`
