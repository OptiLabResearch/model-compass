# Repository Guidelines

## Project structure

Model Compass is a dependency-free static site. `public/` is the complete deployment output: HTML lives at its root, shared browser code and styles are in `public/assets/`, and `public/data/models.json` is the UI data source. Never deploy the repository root.

Refresh and validation utilities live in `scripts/`. `data/enrichment_cache.json` preserves metrics unavailable from the API, and dated snapshots live in `data/history/`. CI and scheduled refresh configuration live in `.github/`.

## Local commands

- `python3 -m http.server 8000 --directory public` serves the site.
- `python3 scripts/validate_site.py` checks the public boundary, CSP, HTML, data, fonts, and history.
- `node scripts/test_browser_security.mjs` checks URL and HTML-sanitization regressions.
- `AA_API_KEY=... python3 scripts/fetch_aa_models.py` refreshes model data.
- `python3 scripts/export_history_csv.py` writes today's CSV snapshot.

## Credentials

Use the ignored repository-root `.env` for local credentials and keep it mode `0600`. The only project credential is `AA_API_KEY`. Never read, print, commit, paste, or deploy secret values. GitHub and deployment credentials are managed outside repository files.

## Style and testing

Use four spaces for Python and two for JavaScript. Prefer small, dependency-free changes. Treat missing benchmark values as unknown, not zero. Preserve the strict CSP, output allowlist, outbound URL allowlist, data validation, atomic writes, and formula-safe CSV export.

Before submitting, run the repository validation and browser-security tests. For UI work, exercise search, filters, presets, comparison, sorting, hash links, responsive layouts, and both themes.

## Commits and pull requests

Use concise imperative subjects; reserve `data: weekly refresh YYYY-MM-DD` for generated refreshes. Keep commits focused. PRs should describe user-visible effects, checks performed, data changes, and screenshots for UI work. Follow `SECURITY.md` for vulnerability reports.
