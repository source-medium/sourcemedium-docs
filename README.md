# Source Medium Documentation

This repository contains the Mintlify documentation for the Source Medium dbt repository.

## Documentation Workflows

### Automatic Documentation Generation

Documentation is automatically generated from the dbt repository using a custom script that:

1. Extracts information from dbt's manifest and catalog files
2. Converts it to Markdown files in the appropriate directories
3. Commits and pushes changes to this repository

### Direct Documentation Editing

For making direct changes to documentation files (not generated from dbt), follow this workflow:

1. Create a new branch for your changes:
   ```bash
   git checkout -b your-branch-name
   ```

2. Make your changes to the documentation files

3. Commit and push your changes:
   ```bash
   git add .
   git commit -m "Description of your changes"
   git push -u origin your-branch-name
   ```

4. Create a pull request using GitHub CLI:
   ```bash
   gh pr create --title "Your PR title" --body "Description of your changes"
   ```

5. Merge the pull request:
   ```bash
   gh pr merge <PR-NUMBER> --merge
   ```

6. After merging, don't forget to update the main repository to point to the latest version of this submodule.

## File Structure

- `models/`: Documentation for dbt models
- `macros/`: Documentation for dbt macros
- `seeds/`: Documentation for dbt seeds
- `snapshots/`: Documentation for dbt snapshots
- `analyses/`: Documentation for dbt analyses
- `data-inputs/`: Documentation for data input platforms
- `data-transformations/`: Documentation for data transformation processes
- `data-activation/`: Documentation for data activation platforms

## Deployment

Documentation is automatically deployed to the Mintlify site when changes are pushed to the main branch of this repository.

## Documentation URL

Our documentation is available at: https://docs.sourcemedium.com/

## Last Updated

This documentation was last tested on: `March 4, 2024 at 3:00 PM PST`
