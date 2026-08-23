# Private Artificial Analysis pipeline (scripts/aa/)

Adapters that collect Artificial Analysis model data into a single private
normalized dataset for model-selection decisions. Built 2026-08-21.

## Why this exists

The legacy pipeline (`scripts/fetch_aa_models.py`) builds the static-site
`public/data/models.json` from the Free API + a brittle `/models` page scrape.
For internal model-selection/orchestration we wanted the **richest practical
dataset** AA exposes publicly, not the narrow Free-API subset, and we wanted it
robust to AA changing its site.

Live investigation (2026-08-21) found that AA's own leaderboard page ships the
**complete** model table via a Next.js React Server Components payload — far
richer than the Free API (which drops blending, percentiles, many benchmarks,
metadata) and than the legacy page scrape. The RSC structure had already
drifted again (camelCase `rows[]`, not the reference parser's snake_case
`hostsModels`), confirming a robust adapter is needed.

## Sources

| Source | File | Role | Key? | Notes |
|---|---|---|---|---|
| RSC leaderboard | `rsc_source.py` | **primary** | No | ~412 unique models, full metric set |
| Official Free API | `official_api_source.py` | baseline / IDs / validation | `AA_API_KEY` | ~195 models, public subset only |
| Oolong snapshot | `snapshot_source.py` | fallback / cross-check | No | MIT, daily, ~570 models |

Shared contract: `source_base.py` (`SourceResult`), `schema.py` (normalized
fields + bounds), `http.py` (retries/backoff/rate-limit/atomic/cache),
`validate.py` (fail-visible sanity + drift detection).

## Outputs

- `data/aa_models_v2.json` — merged normalized dataset (614 models as of
  2026-08-21), each record includes source provenance (`merged.primary`,
  `merged.also_from`), original ids/slugs, normalized values, and preserved
  unknown raw fields.
- `data/aa_pipeline_report.json` — per-source health + field/benchmark coverage.
- `data/history/rich/*.delta.json` — bounded rich-dataset change deltas (104 files retained).
- `data/openrouter_observations.json` — bounded provider endpoint observations from the public OpenRouter API.
- `data/coding_agent_observations.json` — separate public Artificial Analysis coding-agent/harness observations.
- `data/aa_cache/` — raw payloads (git-ignored), for reproducibility/debugging.

## Commands

```bash
# Build the dataset (RSC + snapshot; API used if AA_API_KEY set)
python3.12 -m scripts.aa.orchestrate
# Flags: --no-api --no-snapshot --offline (stale-only) --refresh (bypass cache)

# Cross-validate RSC vs snapshot (and vs API with AA_API_KEY)
python3.12 scripts/aa/crossvalidate.py --api

# Query layer demo (best coding/value/agentic/speed/backup)
python3.12 scripts/aa/demo_query.py

# Stable decision CLI (JSON output)
python3 scripts/model_compass.py recommend coding
python3 scripts/model_compass.py pareto intelligence_index cost
python3 scripts/model_compass.py backup <slug>
python3 scripts/model_compass.py agents
python3 scripts/model_compass.py recommend-agent coding_agent_index

# Offline unit tests (drift detection, scaling, dedup, merge, NaN)
python3.12 scripts/aa/tests/test_pipeline.py
```

## Using the query layer

```python
import sys; sys.path.insert(0, 'scripts')
from aa.query import AADB
db = AADB('data/aa_models_v2.json')

db.best_coding(10)                       # best coding models
db.best_agentic(10)                      # best agentic models
db.best_for_benchmark('mmlu_pro', 10)    # best for a specific benchmark
db.value_intelligence_per_dollar(10)     # IQ per $ (3:1 blend)
db.value_intelligence_per_task(10)       # IQ per $ of running AA's eval
db.quality_vs_speed(10)                  # quality with throughput
db.backup_candidates(gap=5)              # close-to-best, cross-vendor
db.fastest(10); db.cheapest_1m(10)       # speed / cost rankings
db.get('gpt-5-6-luna-low')               # fetch one record by slug
```

## Refresh / update

Runs in the weekly GitHub workflow (`.github/workflows/refresh.yml`, Sundays
19:00 UTC) right after the legacy site pipeline; `data/aa_models_v2.json` and
`data/aa_pipeline_report.json` are committed when changed. Local refresh is the
`orchestrate` command above.

## Field / benchmark coverage (2026-08-21)

614 merged models. Field coverage varies by source and is recorded in
`data/aa_pipeline_report.json` on every refresh:

- intelligence_index 601/614, omniscience_index 480, context_tokens 609,
  creator 614, is_open_weights 609, parameters 338, license 328
- benchmarks: gpqa 576, hle 570, scicode 568, lcr 502, critpt 483,
  omniscience_accuracy/non_halluc 480, ifbench 456, tau2 446,
  terminalbench_hard 438, omniscience 371, mmmu_pro 240, gdpval 197,
  aime25 189, livecodebench 216, tau_banking 166, apex_agents 30,
  it_bench_sre 29
- codding_index 166, agentic_index 146 (largely from the snapshot; the RSC
  payload does not carry these two sub-indices for most rows)
- performance: speed 366, percentile distributions 329
- pricing: input 439

**Not available from any public source:** `math_index` (AA does not expose it).
The official Free API also omits blending, percentile performance, context
window, parameters, and licensing — the RSC/snapshot sources fill those. To get
everything the Free API hides (blended pricing, percentiles, provider-level,
time-series) you would need a **Pro** or **Commercial** key.

## Fail-visible behaviour if AA changes its site

- Extraction fails loudly (no silent empty JSON) when the RSC `rows[]` table
  disappears or entries stop looking like host-model pairs.
- `validate.run_sanity` guards: model count below bounds, required fields
  missing everywhere, duplicate slugs, and non-finite numbers.
- The orchestrator refuses to overwrite a good dataset when no source is
  healthy, and reports per-source errors in `data/aa_pipeline_report.json`.
- Drift of unexpected normalized fields is logged as a warning.
- Raw payloads are preserved under `data/aa_cache/` so a structure change can
  be inspected directly.

To adapt to an AA change: fetch the current leaderboard RSC, inspect the raw
payload in `data/aa_cache/`, then update `_extract_rows` / `normalize_row` in
`rsc_source.py` and bump `RSC_PARSER_VERSION` in `source_base.py`.

## Licensing note

The RSC extraction approach is informed by the GPL-3.0 reference
(MaurerAnton/artificialanalysis-ai-parser). Our `rsc_source.py` is an
independent implementation sharing no code, and the adapter interface means it
can be swapped if licensing constraints change. AA benchmark data is AA's; API
use requires attribution to artificialanalysis.ai.