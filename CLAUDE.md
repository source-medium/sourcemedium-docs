# CLAUDE.md

This file provides guidance to Claude Code when working with the SourceMedium documentation repository.

## Project Overview

This is a **Mintlify documentation site** for SourceMedium, a data analytics platform for e-commerce brands. The docs cover:
- Platform integrations (Shopify, Meta, Google Ads, Klaviyo, etc.)
- Data transformation and activation
- Dashboard/BI usage guides
- Attribution and analytics concepts

**Tech Stack:** Mintlify (MDX-based docs framework), GitHub Actions for CI/CD

## Essential Commands

```bash
# Local development
mintlify dev                    # Start local dev server (requires npm install -g mintlify)

# Validation (run before committing)
python3 -m json.tool docs.json  # Validate JSON syntax

# Navigation validation script (from CI workflow)
python3 << 'EOF'
import json, os, sys
def extract_refs(obj, refs=[]):
    if isinstance(obj, str) and not obj.startswith('http'): refs.append(obj)
    elif isinstance(obj, list): [extract_refs(i, refs) for i in obj]
    elif isinstance(obj, dict): [extract_refs(v, refs) for k,v in obj.items() if k in ('tabs','pages','navigation','groups')]
    return refs
refs = extract_refs(json.load(open('docs.json')))
missing = [f"{r}.mdx" for r in refs if not os.path.exists(f"{r}.mdx")]
if missing: print(f"Missing: {missing[:10]}"); sys.exit(1)
print(f"✅ All {len(refs)} nav refs valid")
EOF
```

## Directory Structure

```
sourcemedium-docs/
├── docs.json                 # Main navigation config (Mintlify)
├── help-center/              # FAQs, guides, troubleshooting
│   ├── faq/
│   │   ├── account-management-faqs/
│   │   ├── dashboard-functionality-faqs/
│   │   ├── data-faqs/
│   │   └── configuration-sheet-faqs/
│   └── core-concepts/
├── data-inputs/              # Integration guides
│   ├── platform-integration-instructions/   # Setup guides per platform
│   ├── platform-supporting-resources/       # Platform-specific deep dives
│   ├── configuration-sheet/                 # Config sheet docs
│   └── attribution-health/                  # Attribution improvement guides
├── data-transformations/     # How SM transforms data
│   └── naming-conventions/   # Column/table naming standards
├── data-activation/          # Using SM data
│   ├── managed-data-warehouse/
│   ├── managed-bi-v1/modules/
│   ├── data-tables/          # Table documentation
│   └── template-resources/   # Looker Studio templates
├── onboarding/               # Getting started content
│   ├── getting-started/
│   └── analytics-tools/
├── mta/                      # Multi-Touch Attribution docs
├── snippets/                 # Reusable MDX snippets
├── images/                   # All images (article-imgs/, platform-logos/)
└── .github/workflows/        # CI/CD (docs-quality.yml)
```

## docs.json Navigation Structure

The navigation uses a `tabs > groups > pages` hierarchy:

```json
{
  "navigation": {
    "tabs": [
      {
        "tab": "Tab Name",
        "groups": [
          {
            "group": "Group Name",
            "pages": [
              "path/to/page",           // Simple page reference
              {                          // Nested group
                "group": "Nested Group",
                "pages": ["path/to/nested-page"]
              }
            ]
          }
        ]
      }
    ]
  }
}
```

**Current Tabs:**
- What Is SourceMedium (help-center)
- Onboarding
- Data Integrations & Inputs
- Data Transformation
- Data Activation
- MTA

**Important:** Page references are paths WITHOUT `.mdx` extension. They must match actual file paths.

## MDX Components

Mintlify provides these components (use them for consistent formatting):

### Callouts
```mdx
<Info>Informational note</Info>
<Tip>Helpful suggestion</Tip>
<Note>Important callout</Note>
<Warning>Caution or gotcha</Warning>
```

### Cards & Groups
```mdx
<CardGroup cols={2}>
  <Card title="Card Title" icon="icon-name" href="/path/to/page">
    Card description
  </Card>
</CardGroup>
```

### Tabs
```mdx
<Tabs>
  <Tab title="First Tab">Content for first tab</Tab>
  <Tab title="Second Tab">Content for second tab</Tab>
</Tabs>
```

### Accordions
```mdx
<Accordion title="Expandable Section">
  Hidden content revealed on click
</Accordion>

<AccordionGroup>
  <Accordion title="Item 1">Content 1</Accordion>
  <Accordion title="Item 2">Content 2</Accordion>
</AccordionGroup>
```

### Steps
```mdx
<Steps>
  <Step title="Step 1">First step content</Step>
  <Step title="Step 2">Second step content</Step>
</Steps>
```

### Tooltips & Snippets
```mdx
<Tooltip tip="Explanation text">Term</Tooltip>

{/* Include reusable snippet */}
<Snippet file="snippet-name.mdx" />
```

## Frontmatter

Every `.mdx` file needs frontmatter:

```yaml
---
title: "Page Title"                    # Required
sidebarTitle: "Short Nav Title"        # Optional - shorter title for sidebar
description: "SEO description"         # Optional but recommended
icon: 'icon-name'                      # Optional - Font Awesome icon
---
```

Common icons: `plug`, `chart-line`, `question-mark`, `book`, `gear`, `heart-pulse`, `tags`

## CI/CD Quality Checks

PRs trigger `.github/workflows/docs-quality.yml` which validates:

1. **Spell Check** (codespell) - Catches typos
2. **Link Check** (lychee) - Validates internal/external URLs
3. **JSON Validation** - Ensures docs.json is valid
4. **Navigation Validation** - All page refs point to existing files

**Ignored terms** (add to workflow if needed): smcid, sourcemedium, hdyhau, utm, cogs, ltv, roas, aov, klaviyo, shopify, etc.

## Writing Guidelines

### Terminology
- **SMCID** - SourceMedium Customer ID (unique identifier)
- **HDYHAU** - "How Did You Hear About Us?" (post-purchase survey)
- **MTA** - Multi-Touch Attribution
- **LTV** - Lifetime Value
- **ROAS** - Return on Ad Spend
- **AOV** - Average Order Value
- **Zero-party data** - Customer-provided info (surveys)
- **First-party data** - Tracking-based data (UTMs, GA4)

### Style
- Use sentence case for headings
- Prefer active voice
- Keep paragraphs short (3-4 sentences max)
- Use tables for comparisons and reference info
- Use CardGroups for related links/resources
- Use Tabs for alternative approaches or platform-specific content

### Links
- **Internal:** Use relative paths `/data-inputs/platform-integration-instructions/shopify-integration`
- **External:** Full URLs `https://example.com`
- **Never:** Use old `help.sourcemedium.com` URLs (these are deprecated)

## Common Tasks

### Adding a new integration guide
1. Create file: `data-inputs/platform-integration-instructions/<platform>-integration.mdx`
2. Add to `docs.json` navigation under appropriate group
3. Optionally create supporting resources in `data-inputs/platform-supporting-resources/<platform>/`

### Adding a new FAQ
1. Create file in appropriate `help-center/faq/<category>/` folder
2. Add to `docs.json` under "What Is SourceMedium" tab > FAQs group

### Adding images
1. Place in `images/article-imgs/` (or `platform-logos/` for logos)
2. Reference as `/images/article-imgs/filename.png`

### Creating reusable content
1. Create snippet in `snippets/snippet-name.mdx`
2. Use with `<Snippet file="snippet-name.mdx" />`

## Troubleshooting

### "Page not found" in local dev
- Check file path matches docs.json reference exactly
- Ensure `.mdx` extension exists on file but NOT in docs.json

### CI failing on spell check
- Add legitimate terms to `ignore_words_list` in `.github/workflows/docs-quality.yml`

### CI failing on link check
- Fix broken internal links (check file exists)
- For flaky external links, add to `--exclude` in lychee args

### Navigation not updating
- Ensure valid JSON in docs.json (run `python3 -m json.tool docs.json`)
- Check page path exists as `.mdx` file
