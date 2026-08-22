# Repository Guidelines

## Project structure

Model Compass is a dependency-free static site. `public/` is the complete deployment output: HTML lives at its root, shared browser code and styles are in `public/assets/`, and `public/data/models.json` is the UI data source. Never deploy the repository root.

Refresh and validation utilities live in `scripts/`. `data/enrichment_cache.json` and `data/history/` are legacy artifacts of the old Free-API pipeline (see below). CI and scheduled refresh configuration live in `.github/`.

There are two data pipelines:

1. **Private rich dataset** (`scripts/aa/`) builds `data/aa_models_v2.json` from three sources: the AA leaderboard RSC payload (primary, no key, ~411 models with the full benchmark set), the official AA Free API (`AA_API_KEY`, baseline/IDs/validation), and a third-party daily snapshot (Oolong-Tea, fallback/cross-check). This is the master dataset for model-selection queries.
2. **Public site data** (`scripts/build_site_from_aa.py`) derives `public/data/models.json` + `public/data/benchmarks.json` from that rich dataset.

## Data pipeline and deployment

The weekly refresh (`.github/workflows/refresh.yml`, Sundays 19:00 UTC) runs: (1) `python3 -m scripts.aa.orchestrate` to merge the three AA sources into `data/aa_models_v2.json`, (2) `python3 scripts/build_site_from_aa.py` to produce the site's `public/data/models.json`, (3) exports the dated history CSV and `public/data/benchmarks.json`, then commits only when data changed. Cloudflare Pages auto-deploys from `main` (there is no deploy Action), so a merged refresh is live within minutes — no manual deploy step.

The pipeline fails closed and opens a `data-refresh` labeled GitHub issue on failure. If a refresh fails, check in order: the `AA_API_KEY` secret (HTTP 401 = auth/key), a retired/renamed AA endpoint (HTTP 410 — AA retires legacy `/api/v2/data/*` endpoints 2026-11-04; do not reintroduce them), an RSC leaderboard payload change (the `roles`/`models` tables drift — inspect the raw payload in `data/aa_cache/` and update `rsc_source.py`), a `FEATURED_SLUGS` entry renamed upstream, or a stale third-party snapshot. The Pro endpoint `/api/v2/language/models` is the only upgrade path for more fields and needs a paid key. `scripts/aa/orchestrate.py` hard-fails if the index version (4.1) changes — update the constant rather than weakening the check.

**Legacy script:** `scripts/fetch_aa_models.py` (Free API + `/models` page scrape) is retained for reference but **no longer feeds the site**, because AA's Free API now omits per-benchmark scores (Pro-only), which left most models without benchmarks.

## Local commands

On Windows use `py -3` in place of `python3`. `validate_site.py`, `test_fetch_aa_models.py`, and `test_browser_security.mjs` need no `AA_API_KEY` — run them freely; only the private pipeline's API source needs it (and the pipeline skips it gracefully when unset). On Windows, `git status` may flag CRLF-only changes with empty diffs — check `git diff` for real content before committing.

- `python3 -m http.server 8000 --directory public` serves the site.
- `python3 scripts/validate_site.py` checks the public boundary, CSP, HTML, data, fonts, and history.
- `node scripts/test_browser_security.mjs` checks URL and HTML-sanitization regressions.
- `python3 -m scripts.aa.orchestrate` builds the private rich dataset (`data/aa_models_v2.json`); `--no-api`/`--no-snapshot`/`--offline`/`--refresh` flags available; optional `AA_API_KEY`.
- `python3 scripts/model_compass.py recommend coding --limit 10` provides deterministic recommendation/explanation JSON; `pareto`, `backup`, `explain`, `changes`, `health`, and `list` are also available. `.model-compass-access.json` is an optional gitignored availability overlay.
- `python3 scripts/build_site_from_aa.py` builds the site's `public/data/models.json` from the rich dataset.
- `python3 scripts/export_history_csv.py` writes today's CSV snapshot.
- `python3 scripts/export_benchmarks_json.py` writes `public/data/benchmarks.json`.
- `python3 scripts/aa/tests/test_pipeline.py` and `python3 scripts/aa/crossvalidate.py` test and cross-validate the pipeline.
- `python3 -c "import sys;sys.path.insert(0,'scripts');from aa.query import AADB;db=AADB()"` queries the dataset (best coding/value/backup etc.).
- Rich snapshot deltas are written under `data/history/rich/` and retained for 104 files; `--offline` is cache-only and never attempts a network request.

## Credentials

Use the ignored repository-root `.env` for local credentials and keep it mode `0600`. The only project credential is `AA_API_KEY`. Never read, print, commit, paste, or deploy secret values. GitHub and deployment credentials are managed outside repository files.

## Style and testing

Use four spaces for Python and two for JavaScript. Prefer small, dependency-free changes. Treat missing benchmark values as unknown, not zero. Preserve the strict CSP, output allowlist, outbound URL allowlist, data validation, atomic writes, and formula-safe CSV export.

Before submitting, run the repository validation and browser-security tests. For UI work, exercise search, filters, presets, comparison, sorting, hash links, responsive layouts, and both themes.

## Commits and pull requests

Use concise imperative subjects; reserve `data: weekly refresh YYYY-MM-DD` for generated refreshes. Keep commits focused. PRs should describe user-visible effects, checks performed, data changes, and screenshots for UI work. Follow `SECURITY.md` for vulnerability reports.
