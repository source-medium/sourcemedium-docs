# Repository Guidelines

## Project Structure & Module Organization
- Content lives in `.mdx` under topical folders: `onboarding/`, `data-activation/`, `mta/`, `advanced-insights-and-strategy/`, `internal/`.
- Assets live in `images/` (logos, article images, gifs, videos). Reference with root-relative paths (e.g., `/images/article-gifs/eznav.gif`).
- Site configuration: `docs.json` (branding, navigation, tabs, analytics).

## Build, Test, and Development Commands
- Install Mintlify CLI (once): `npm i -g mintlify`
- Run local preview with hot-reload: `mintlify dev`
- Build static site (CI does this): `mintlify build`
- Deploy to Mintlify (requires API key): `mintlify deploy` with `MINTLIFY_API_KEY` set.
- CI/CD: `.github/workflows/mintlify-docs-update.yml` builds and deploys on `master` using Node 16.

## Coding Style & Naming Conventions
- Files: kebab-case filenames ending in `.mdx` (e.g., `how-to-manage-user-access.mdx`).
- Frontmatter is required:
  ```md
  ---
  title: "Page Title"
  description: "Short summary"
  # optional: sidebarTitle, icon
  ---
  ```
- Markdown: use sentence case headings, ordered lists for procedures, and root-relative asset links. Keep lines concise and use code fences for commands.

## Validation Guidelines
- Preview locally via `mintlify dev`; ensure pages render, links resolve, and images load.
- Check frontmatter completeness (title, description) and navigation presence in `docs.json` if adding new pages/sections.
- Keep images optimized; place new media in `images/article-imgs/` or `images/article-videos/` as appropriate.

## Commit & Pull Request Guidelines
- Commits: short, imperative summaries (scope optional). Example: `Update MTA docs with dedup logic`.
- PRs: include a clear description, related issue/linear ticket, and screenshots or screen capture of the rendered page. Note any `docs.json` navigation changes.
- Before requesting review: run `mintlify dev` locally and verify no console errors.

## Security & Configuration Tips
- Never commit secrets. CI uses `MINTLIFY_API_KEY` and `SLACK_WEBHOOK_URL` GitHub Secrets.
- Local deploys require exporting `MINTLIFY_API_KEY` in your shell for `mintlify deploy`.
