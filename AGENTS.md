# Repository Guidelines

## Project Structure & Module Organization

Model Compass is a static, three-page site with no application build step. `index.html` contains the model picker, `shortlist.html` the curated view, and `models.html` the full benchmark table. Shared browser code and styling live in `assets/nav.js` and `assets/style.css`; keep page-specific scripts and styles with their HTML page unless they are reused.

`data/models.json` is the UI's source of truth. `data/enrichment_cache.json` preserves metrics unavailable from the API, while dated snapshots live in `data/history/`. Python utilities in `scripts/` fetch and export this data. The Groq-backed Cloudflare Pages endpoint is `functions/api/recommend.js`. Deployment and scheduled refresh configuration live in `wrangler.toml` and `.github/workflows/refresh.yml`.

## Build, Test, and Development Commands

- `python3 -m http.server 8000` serves the static pages at `http://localhost:8000`; the LLM recommender falls back locally.
- `npx wrangler pages dev . --binding GROQ_API_KEY="$GROQ_API_KEY"` runs the site with the Pages Function enabled.
- `AA_API_KEY=... python3 scripts/fetch_aa_models.py` rebuilds `data/models.json` and updates the enrichment cache.
- `python3 scripts/export_history_csv.py` writes today's CSV snapshot; use `--date YYYY-MM-DD` for reproducible output.

## Credentials and Environment

For local work, use the ignored repository-root `.env` path. On this machine it is a symlink to `/root/.hermes/.env`, so the project reuses Hermes's protected credentials without duplicating them. Do not replace or overwrite that symlink. On another machine, create `.env` from `.env.example` and fill it locally. The project uses:

- `AA_API_KEY` for local Artificial Analysis data refreshes
- `GROQ_API_KEY` for local Pages Function development

Hermes-wide credentials may already be present in the agent's environment. Do not read, print, commit, or paste secret values. If a command reports a missing credential, report only the missing variable name. For shell commands that need the project file, load it in that shell with `set -a; source .env; set +a`.

GitHub and Cloudflare credentials are handled separately from this repository's `.env`. GitHub Actions supplies its built-in `GITHUB_TOKEN`, while `AA_API_KEY` is a GitHub repository secret. Production uses the Cloudflare Pages `GROQ_API_KEY` secret. For local Wrangler/deployment administration, `CLOUDFLARE_API_TOKEN` is stored in `/root/.hermes/.env` and loaded by Hermes; use the environment variable and never open, print, copy, or commit the credential file.

There is no compile or bundle command.

## Coding Style & Naming Conventions

Follow existing formatting: four spaces for Python and two spaces for JavaScript. Use `snake_case` for Python functions and variables, `camelCase` for JavaScript, `UPPER_SNAKE_CASE` for constants, and kebab-case for CSS classes and web filenames. Prefer small dependency-free changes. Reuse shared CSS variables from `assets/style.css`, and treat missing benchmark values as unknown—not zero. No formatter or linter is configured, so review diffs for consistency.

## Testing Guidelines

No automated test framework or coverage target exists yet. Before submitting, serve the repository over HTTP and exercise Picker, Shortlist, All Models, theme switching, filters, and stale-data messaging in both light and dark modes. For endpoint changes, test successful requests plus missing-key, invalid-body, and rate-limit fallback paths. For data changes, run both scripts and inspect JSON/CSV diffs for dropped featured models or metrics.

## Commit & Pull Request Guidelines

Use concise, imperative commit subjects, matching history such as `Add automation plan`; reserve `data: weekly refresh YYYY-MM-DD` for generated refreshes. Keep commits focused. Open an issue before large or breaking work. Pull requests should explain the user-visible effect, list manual checks, link relevant issues, and include before/after screenshots for UI changes. Call out generated data updates and any required `AA_API_KEY` or `GROQ_API_KEY` configuration; never commit secret values.
