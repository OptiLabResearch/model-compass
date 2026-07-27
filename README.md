# Model Compass

Compare and evaluate LLMs — benchmark data from [Artificial Analysis](https://artificialanalysis.ai/models), refreshed weekly.

**All Models** ([index.html](index.html)) — full benchmark table across every model tracked in the last 6 months.

Live at [models.optiqo.dev](https://models.optiqo.dev).

## Data

`data/models.json` is the single source of truth; fetched by `index.html`.
`scripts/fetch_aa_models.py` builds it from two sources:

| Source | Coverage | Provides |
| --- | --- | --- |
| AA official API (`AA_API_KEY`) | every tracked model | intelligence/coding indices, GPQA, HLE, SciCode, IFBench, LCR, τ², τ³-Banking, Terminal-Bench, pricing, speed, TTFT |
| AA `/models` page payload | the ~28 models AA renders | **AA-Omniscience / non-hallucination**, agentic index, GDPval, CritPt, MMMU-Pro, context window, modalities |

`data/enrichment_cache.json` remembers the page-only metrics per model. Cached values are stamped with the date observed and are always overridden by fresh data.

Scores that AA has retired (MMLU-Pro, LiveCodeBench, AIME, MATH-500) are null for every model in the current window and are not displayed.

## Refresh

`.github/workflows/refresh.yml` runs Sundays at 19:00 UTC: fetch → export CSV snapshot to `data/history/` → commit → Cloudflare Pages auto-deploys. The job **fails loudly** (and opens an issue) if the API is unreachable or a curated model has vanished upstream, rather than committing a quietly degraded dataset.

## Setup

One secret for data refreshes:

| Secret | Where | Why |
| --- | --- | --- |
| `AA_API_KEY` | GitHub Actions repo secret | the weekly data refresh |

## Run locally

The ignored local `.env` path is already connected to the Hermes credential store on the development machine. Do not overwrite it with `.env.example`; on another machine, create `.env` from that example and fill it locally.

Serve the static page with Python:

```
python3 -m http.server 8000
```

Refresh the data by hand with:

```
set -a; source .env; set +a
python3 scripts/fetch_aa_models.py
python3 scripts/export_history_csv.py
```

Opening the files via `file://` will not work — the page fetches `data/models.json`, which needs an HTTP server.
