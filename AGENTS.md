# Repository Guidelines

## Purpose and boundaries

Model Compass is a durable, Codex-first model-intelligence project with a
dependency-free static comparison site and deterministic data pipelines.

- `public/` is the complete Cloudflare Pages deployment output. Never deploy
  the repository root.
- `scripts/` contains source adapters, exports, validators, and the CLI.
- `data/` contains committed generated/private artifacts; ignored raw payloads
  live under `data/aa_cache/`.

## Authoritative project documents

- `docs/PROJECT.md` — stable scope and non-goals.
- `docs/ARCHITECTURE.md` — data flow, source authority, and identity boundaries.
- `docs/STATUS.md` — current phase, branch, blockers, and next action.
- `docs/ROADMAP.md` — phase order and acceptance outcomes.
- `docs/plans/active/` — active implementation plans.
- `docs/reports/` — accepted evidence; historical reports are archived.
- `scripts/aa/README.md` — detailed source and pipeline operation.

Read `docs/STATUS.md` and its active plan before roadmap work.

## Architecture and data sources

`scripts.aa.orchestrate` builds `data/aa_models_v2.json` from:

1. AA leaderboard RSC payload (primary rich source).
2. Official AA Free API (optional `AA_API_KEY`, baseline/IDs/validation).
3. Oolong snapshot (fallback/cross-check).

`data/enrichment_cache.json` is a transitional backfill input still read by
the orchestrator; it is not a canonical source. `scripts/build_site_from_aa.py`
derives `public/data/models.json` and `scripts/export_benchmarks_json.py`
derives `public/data/benchmarks.json`.

OpenRouter, Endpoint Accuracy, and coding-agent results are separate
observation domains. Identity-aware recommendations consume only explicit
`verified` or audited `manual` exact mappings; preserve provider endpoint
variants and treat candidates, ambiguities, and unresolved joins as diagnostic
only.

## Refresh and deployment

The weekly refresh is defined by `.github/workflows/refresh.yml`: build rich
data, derive public data, export history and benchmarks, refresh provider and
agent observations, regenerate Phase 3 artifacts, then commit changed generated
outputs. Cloudflare Pages publishes only `public/`.

The RSC payload is an upstream frontend contract. If it drifts, inspect ignored
raw data under `data/aa_cache/` and update the adapter. Source failures and
artifact invariant failures must remain visible; do not publish empty or
ambiguous data.

## Commands

Python 3.12+ and Node.js 20+ are used by CI.

- `python3 -m http.server 8000 --directory public`
- `python3 scripts/validate_site.py`
- `node scripts/test_browser_security.mjs`
- `python3 -m scripts.aa.orchestrate [--offline|--no-api|--no-snapshot|--refresh]`
- `python3 scripts/build_site_from_aa.py [--as-of YYYY-MM-DD]`
- `python3 scripts/export_history_csv.py [--date YYYY-MM-DD]`
- `python3 scripts/export_benchmarks_json.py`
- `python3 -m scripts.aa.phase3_artifacts`
- `python3 scripts/model_compass.py recommend coding --limit 10`
- `python3 scripts/aa/tests/test_pipeline.py`
- `python3 scripts/aa/crossvalidate.py`
- `python3 scripts/prune_aa_cache.py --max-age-days 30` (dry run)

The full validation command set is in `.github/workflows/ci.yml`. Build/export
commands write generated artifacts; use temporary output paths for replay tests.

## Credentials and conventions

Use an ignored repository-root `.env` with mode `0600` for the optional
`AA_API_KEY`. Never read, print, commit, paste, or deploy credential values.
Keep Python at four-space indentation and JavaScript at two spaces. Missing
metrics remain unknown, not zero. Preserve strict CSP, public output
allowlists, outbound URL allowlists, atomic writes, and formula-safe CSV
export.

Keep commits focused with imperative subjects. Generated refreshes use
`data: weekly refresh YYYY-MM-DD`. Do not weaken tests or source-authority
rules; review generated-artifact reproducibility and run an independent
correctness review for substantive phases.
