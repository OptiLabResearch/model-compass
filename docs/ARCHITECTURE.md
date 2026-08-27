# Architecture

## Product boundary

Model Compass is a dependency-free static comparison site plus a private,
deterministic decision dataset. Only `public/` is deployable. Private data,
source caches, provider observations, identity evidence, and pipeline reports
remain outside that boundary.

## Batch data flow

```text
AA leaderboard RSC ─┐
AA Free API (optional) ├─> scripts.aa.orchestrate
Oolong snapshot ─────┘             │
                                   v
                         data/aa_models_v2.json
                                   │
                                   ├─> public/data/models.json
                                   ├─> public/data/benchmarks.json
                                   └─> data/history/rich/*.delta.json

OpenRouter ───────────────> provider observations
AA Endpoint Accuracy ────> bounded accuracy observations
AA coding-agent pages ───> coding-agent observations
                                   │
                                   v
                         identity and Phase 3 artifacts
```

The weekly workflow builds the rich dataset first, derives public artifacts,
exports history, refreshes the separate observation domains, and regenerates
deterministic identity/summary artifacts. `public/` is the only Cloudflare
Pages upload boundary.

## Source authority and access

| Domain | Source | Access tier | Role | Authority |
|---|---|---|---|---|
| Core model metrics | AA leaderboard RSC payload | Public | Rich primary model table | Primary for fields it exposes |
| Baseline IDs and validation | AA Free API | Optional key | Stable IDs, baseline fields, index checks | Primary for those fields when present |
| Cross-check/fallback | Oolong daily snapshot | Public | Coverage fallback and discrepancy signal | Not authoritative over AA fields |
| Provider operations | OpenRouter API | Public | Endpoint availability, pricing, latency, capabilities | Authoritative only for OpenRouter observations |
| Endpoint Accuracy | AA bounded JSON-LD pages | Public | Point-in-time endpoint evidence | Authoritative for captured measurements |
| Coding-agent results | AA public coding-agent pages | Public | Harness/model/configuration observations | Not base-model facts |

The RSC payload is an upstream frontend contract and may drift independently
from the documented API. The adapters fail visibly on structural drift and the
orchestrator refuses to replace a good dataset when no source is healthy.
Paid-tier data is not assumed or silently substituted for missing public data.

## Public contract

`scripts/public_contract.py` owns shared featured slugs, OpenRouter endpoint
routing, release-window policy, slug/URL rules, numeric bounds, and destructive
model-count-drop protection. Both the active rich builder and the retained
Free-API compatibility path use it; `scripts/validate_site.py` validates the
same contract directly.

The builder accepts `--as-of YYYY-MM-DD`. If omitted, it uses the rich dataset's
`generated_at` date, so replaying the same rich input produces the same release
window and metadata rather than depending on the machine clock.

Missing benchmark or pricing values remain unknown, not zero. Public output
must preserve strict CSP, allowlisted outbound URLs, atomic writes, and the
frontend's established schema.

## Identity and recommendation boundary

Cross-source joins pass through versioned identity artifacts. Only explicit
`verified` or audited `manual` exact mappings are authoritative for
identity-aware recommendations. Metadata candidates, heuristic candidates,
ambiguities, conflicts, and unresolved joins are diagnostic and fail closed.
Provider identity includes the endpoint variant whenever variants can carry
different accuracy evidence; provider namespaces and display names are never
fallback joins.

## Storage and reproducibility

Committed JSON remains the storage/interchange format while current scale
permits deterministic review and replay. Ignored raw payloads under
`data/aa_cache/` support debugging and offline parsing; timestamped debug dumps
can be pruned with the dry-run-first `scripts/prune_aa_cache.py` utility.
Committed generated artifacts must have a documented producer, internally
consistent counts and metadata, deterministic fixtures or replay inputs, and
fail-closed acquisition behavior. Accepted evidence belongs in `docs/reports/`;
current status and decisions belong in `docs/STATUS.md` and the active plan.
