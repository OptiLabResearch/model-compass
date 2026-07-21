# Model Compass

Compare, shortlist, and pick LLMs — benchmark data from [Artificial Analysis](https://artificialanalysis.ai/models), refreshed weekly.

Three pages:
- **Picker** ([index.html](index.html)) — describe a task in plain language; an LLM reads the benchmark table and recommends a model, citing the numbers
- **Shortlist** ([shortlist.html](shortlist.html)) — a curated, filterable table of tracked models
- **All Models** ([models.html](models.html)) — the full benchmark table across every model tracked in the last 6 months

Live at [models.optiqo.dev](https://models.optiqo.dev).

## How the picker works

Three stages, and the order matters:

1. **An LLM classifies the task and picks a model.** The page POSTs your task plus the
   shortlist (with each model's benchmark row) to `/api/recommend`, a Cloudflare Pages
   Function that calls Groq. The LLM reads the actual numbers, so it can weigh tradeoffs
   the fixed formula can't express — "this one is 1 point better and 20x the price".
2. **Hard gates are re-applied in code.** Unattended work requires ≥70% non-hallucination;
   high-stakes requires ≥80% and ≥45 intelligence; real-time/voice requires ≤5s to first
   token. These run *after* the LLM answers, against the scenarios it itself reported. A
   pick that fails a gate is thrown out and the page says so. **The LLM advises; the gates
   decide.**
3. **A weighted formula ranks everything** (`TASK_WEIGHTS` in `index.html`) and provides the
   score breakdown, the candidate table, and the fallback pick.

If the recommender is rate-limited or unreachable, the page degrades to the formula and
tells you. It never silently pretends an LLM was involved.

## Data

`data/models.json` is the single source of truth; all three pages fetch it.
`scripts/fetch_aa_models.py` builds it from two sources:

| Source | Coverage | Provides |
| --- | --- | --- |
| AA official API (`AA_API_KEY`) | every tracked model | intelligence/coding indices, GPQA, HLE, SciCode, IFBench, LCR, τ², τ³-Banking, Terminal-Bench, pricing, speed, TTFT |
| AA `/models` page payload | the ~28 models AA renders | **AA-Omniscience / non-hallucination**, agentic index, GDPval, CritPt, MMMU-Pro, context window, modalities |

The API does not expose non-hallucination, which the picker's gates depend on — hence the
hybrid. AA now ships its full dataset encrypted, so the page half is best-effort and may
break; when it does, the build still succeeds on API data alone and says loudly what was lost.

`data/enrichment_cache.json` remembers the page-only metrics per model, so a model dropping
off AA's front page doesn't strip the picker of its gates. Cached values are stamped with the
date observed and are always overridden by fresh data. Benchmarks of a released model don't
drift much, but AA does re-run evals — that's the tradeoff being made.

Scores that AA has retired (MMLU-Pro, LiveCodeBench, AIME, MATH-500) are null for every
model in the current window and are not displayed.

## Refresh

`.github/workflows/refresh.yml` runs Sundays at 19:00 UTC: fetch → export CSV snapshot to
`data/history/` → commit → Cloudflare Pages auto-deploys. The job **fails loudly** (and opens
an issue) if the API is unreachable or a curated model has vanished upstream, rather than
committing a quietly degraded dataset.

Curation lives in `FEATURED_SLUGS` in `scripts/fetch_aa_models.py`. Featured models are
exempt from the 6-month release-window cutoff — curation decides the shortlist, not age.

## Setup

Two secrets:

| Secret | Where | Why |
| --- | --- | --- |
| `AA_API_KEY` | GitHub Actions repo secret | the weekly data refresh |
| `GROQ_API_KEY` | Cloudflare Pages project (production + preview) | the `/api/recommend` function |

## Run locally

The ignored local `.env` path is already connected to the Hermes credential store on the development machine. Do not overwrite it with `.env.example`; on another machine, create `.env` from that example and fill it locally.

Load the environment in the shell before running commands that need credentials:

The picker's recommender is a Pages Function, so it needs the Functions runtime:

```
set -a; source .env; set +a
npx wrangler pages dev . --binding GROQ_API_KEY="$GROQ_API_KEY"
```

`python3 -m http.server` also works, but without `/api/recommend` the picker detects this and
presents itself as the keyword-classifier build.

Refresh the data by hand with:

```
set -a; source .env; set +a
python3 scripts/fetch_aa_models.py
python3 scripts/export_history_csv.py
```

Opening the files via `file://` will not work — the pages `fetch()` their data, which needs a
same-origin HTTP server.
