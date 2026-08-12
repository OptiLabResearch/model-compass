# Repository Guidelines

## Project structure

Model Compass is a dependency-free static site. `public/` is the complete deployment output: HTML lives at its root, shared browser code and styles are in `public/assets/`, and `public/data/models.json` is the UI data source. Never deploy the repository root.

Refresh and validation utilities live in `scripts/`. `data/enrichment_cache.json` preserves metrics unavailable from the API, and dated snapshots live in `data/history/`. CI and scheduled refresh configuration live in `.github/`.

## Data pipeline and deployment

The weekly refresh (`.github/workflows/refresh.yml`, Sundays 19:00 UTC) fetches the documented AA Free API (`/api/v2/language/models/free`), enriches it from AA's `/models` page, validates, exports a dated CSV, and commits `public/data/models.json` + `data/enrichment_cache.json` + `data/history/` to `main` only when data changed. Cloudflare Pages auto-deploys from `main` (there is no deploy Action), so a merged refresh is live within minutes — no manual deploy step.

The refresh fails closed and opens a `data-refresh` labeled GitHub issue on failure. If a refresh fails, check in order: the `AA_API_KEY` secret (HTTP 401 = auth/key), the run log (HTTP 410 = a retired `/api/v2/data/*` endpoint — AA retires those 2026-11-04; do not reintroduce them), a `FEATURED_SLUGS` entry renamed upstream, or an AA `/models` page change. The Pro endpoint `/api/v2/language/models` is the only upgrade path for more fields and needs a paid key. `fetch_aa_models.py` also hard-fails if `EXPECTED_INDEX_VERSION` (4.1) changes — update that constant rather than weakening the check.

## Local commands

On Windows use `py -3` in place of `python3`. `validate_site.py`, `test_fetch_aa_models.py`, and `test_browser_security.mjs` need no `AA_API_KEY` — run them freely; only `fetch_aa_models.py` needs it. On Windows, `git status` may flag CRLF-only changes with empty diffs — check `git diff` for real content before committing.

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
