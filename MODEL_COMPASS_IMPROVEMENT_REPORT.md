# Model Compass Improvement Report

**Date:** 2026-08-22 UTC  
**Repository:** `/srv/projects/shared/model-compass`  
**Starting point:** `6dd03afb1f17e727abf5a0fcc4a1857e9e31372b`  
**Implementation commits:**

- `fc17fb6 feat: harden pipeline and add decision engine`
- `eb4b446 fix: preserve provider variants during source merge`

This iteration followed the repository review dossier and preserved the working static site. It focused on correctness, deterministic replay, provenance, history, recommendation quality, and a stable agent-facing interface. It did **not** turn Model Compass into a first-party benchmark runner.

## 1. What changed

### Pipeline reliability

- Made `--offline` genuinely cache-only.
  - RSC uses the cached raw payload or fails without network access.
  - Official API uses cached pages and does not require `AA_API_KEY` in offline mode.
  - Snapshot source uses cached JSON and does not fetch when offline.
  - Fixed the orchestrator argument propagation bug discovered during verification.
- Added explicit freshness/status information to newly generated rich output and pipeline reports.
  - Fresh output includes `freshness.stale: false`, generation time, and per-source fetch timestamps.
  - Reports include `status: "fresh"`, `stale: false`, and `total_models`.
- Made stale fallback explicit.
  - If no source is healthy but a previous dataset exists, the report is replaced with a `stale_fallback` report containing the reason, previous generation time, source errors, and `stale: true`.
  - The previous good model data is not overwritten.
- Added per-record provenance during source merge:
  - contributing source list,
  - primary source,
  - parser version,
  - fetched timestamp,
  - cache indicator.
- Added the AA index version to RSC-normalized records instead of retaining it only at dataset level.
- Added `provenance` to the known normalized schema fields so valid provenance does not trigger schema-drift warnings.
- Preserved distinct provider/host variants when records from different sources resolve to the same model slug. Host entries are now unioned rather than discarded when the higher-priority record already has a host list.

### Testing and CI

- Added a checked-in sanitized RSC replay fixture at `scripts/aa/tests/fixtures/rsc_minimal.txt`.
- Added fixture replay and per-record index-version assertions to `test_pipeline.py`.
- Added behavioral tests for constraints, explanations, Pareto frontiers, profiles, backup independence, and history deltas.
- CI now runs:
  - recursive Python compilation,
  - the existing legacy tests,
  - the rich pipeline tests,
  - decision-engine tests,
  - history tests,
  - public validation,
  - JavaScript syntax checks,
  - browser-security tests.
- The new tests remain dependency-free standalone scripts. `pytest` was checked but is not installed on the host; no new pytest dependency was introduced.

### Decision engine

Added `scripts/aa/decision.py`, a transparent recommendation layer with:

- constraint filtering for:
  - minimum intelligence/coding/agentic scores,
  - maximum blended cost,
  - minimum context,
  - minimum throughput,
  - maximum TTFT,
  - reasoning requirement,
  - open-weights requirement,
  - creator/provider restrictions,
  - modality requirements,
  - freshness requirements,
  - private access availability;
- configurable named profiles:
  - `coding`,
  - `code-review`,
  - `reasoning`,
  - `agentic`,
  - `long-context`,
  - `fast`,
  - `cheap`,
  - `premium`;
- deterministic weighted ranking after constraints;
- explicit explanations containing:
  - metrics used,
  - satisfied constraints,
  - missing metrics,
  - source list,
  - freshness flag,
  - recommendation score;
- Pareto frontier analysis across quality/cost/speed-like dimensions;
- independent backups with optional creator, provider, and family independence;
- model explanation output with coverage/provenance/access information.

Missing metrics are not converted to zero. A model must have the selected quality metric to enter a recommendation result. Cost and speed contribute only when present, and their absence is exposed in the explanation.

### Stable CLI and private access overlay

Added `scripts/model_compass.py`, a deterministic JSON CLI:

```bash
python3 scripts/model_compass.py list --limit 20
python3 scripts/model_compass.py list gemini --limit 10
python3 scripts/model_compass.py recommend coding --limit 10
python3 scripts/model_compass.py recommend cheap --available-only
python3 scripts/model_compass.py pareto intelligence_index cost
python3 scripts/model_compass.py backup claude-opus-5
python3 scripts/model_compass.py explain claude-opus-5
python3 scripts/model_compass.py changes --previous data/aa_models_v2.json
python3 scripts/model_compass.py health
```

An optional `.model-compass-access.json` file is ignored by Git and can contain local availability facts without credentials, for example:

```json
{
  "models": {
    "some-model": {
      "available": true,
      "channel": "openrouter",
      "preferred": true,
      "cost_class": "subscription"
    }
  }
}
```

The overlay is intentionally separate from upstream benchmark truth. No credential, OAuth token, or API key is stored in this file or repository.

### Rich history/change intelligence

Added `scripts/aa/history.py` with deterministic snapshot deltas covering:

- added models,
- removed models,
- tracked index changes,
- release/deprecation/open-weight changes,
- input/output price changes,
- throughput changes.

The orchestrator writes rich deltas under `data/history/rich/YYYY-MM-DD.delta.json` when a previous rich dataset exists and retains at most 104 files. The existing public dated CSV history remains intact. This gives approximately two years of weekly rich deltas without retaining an uncontrolled full 6 MB snapshot every week.

## 2. Architecture decisions

### Keep JSON and avoid a database for now

The current rich dataset is approximately 6 MB and the public output is much smaller. JSON remains easy to inspect, replay, consume from Python, and commit through the existing GitHub Actions workflow. The new delta history avoids immediate repository growth pressure. SQLite becomes justified when history queries, provider-level measurements, or time-series volume exceed what bounded JSON deltas can handle; this iteration does not cross that threshold.

### Keep one canonical model record, preserve endpoint variants

A full model/release/provider relational redesign was deferred because current AA sources do not expose a stable, uniform provider identity contract across all adapters. The existing `hosts` list is now preserved across merges, while the top-level record continues to be backward-compatible with the static site and `AADB`. A future provider-specific schema can promote host entries into first-class observations once source coverage and identity rules are verified.

### Make recommendation policy configuration-driven

Named profiles live in `decision.py` as data-like dictionaries rather than scattered methods. The public Python surface is exposed through `AADB` wrappers, while the CLI is independent of Hermes internals. Recommendations are deliberately explainable rather than presented as an opaque “best model” scalar.

### Preserve the public site boundary

No browser schema or deployment directory was changed. The static site still consumes `public/data/models.json`; rich private records remain separate. No UI expansion was attempted before the data and recommendation layer became more defensible.

## 3. Bugs and correctness gaps fixed

- Fixed documented-but-broken offline semantics.
- Fixed stale fallback opacity by writing an explicit stale report.
- Fixed missing RSC per-record index-version provenance.
- Fixed provider/host variant loss during same-slug merge.
- Fixed `AADB.backup_candidates()` so same-creator and same-provider candidates are excluded by default.
- Added a real decision-engine backup path with optional family independence.
- Replaced the obsolete README refresh instructions with the active rich pipeline.
- Updated rich-pipeline documentation from the stale 609-model count to the current 614-model report and directed readers to the generated coverage report.
- Added the new pipeline tests to the CI gate instead of testing primarily the legacy path.

## 4. Schema and data impact

### Rich output additions

Newly generated `data/aa_models_v2.json` files include:

```json
{
  "freshness": {
    "stale": false,
    "generated_at": "...",
    "source_fetched_at": {
      "rsc": "...",
      "official_api": "...",
      "snapshot": "..."
    }
  }
}
```

Newly merged records include a `provenance` object. Existing consumers can ignore these additive fields. Existing normalized fields and public output mapping remain compatible.

### Pipeline report additions

Newly generated reports include `status`, `stale`, `total_models`, and `freshness`. A stale fallback report intentionally contains status/error information instead of pretending to be a fresh coverage report.

### History additions

Rich deltas are additive files in `data/history/rich/`; public CSV history is unchanged. Retention is bounded to 104 delta files.

### Migration/backward compatibility

No migration is required for existing data. The decision layer tolerates old records without provenance and derives sources from existing `source`/`merged` fields. Existing `AADB` methods remain available, with new methods added rather than replacing the original public methods. The public site schema is unchanged.

## 5. Tests and exact results

Executed successfully after the implementation:

```text
python3 -m compileall -q scripts
python3 scripts/test_fetch_aa_models.py
python3 scripts/aa/tests/test_pipeline.py
python3 scripts/aa/tests/test_decision_engine.py
python3 scripts/aa/tests/test_history.py
python3 scripts/validate_site.py
node --check public/assets/nav.js
node --check public/assets/models.js
node --check public/assets/theme-init.js
node scripts/test_browser_security.mjs
```

Results:

- Recursive Python compilation: passed.
- Legacy unittest: 6 tests passed.
- Rich pipeline tests: 8 tests passed, including checked-in RSC replay and provider-variant preservation.
- Decision engine tests: 4 tests passed.
- History tests: 2 tests passed.
- Public validation: passed, 201 models.
- JavaScript syntax checks: passed.
- Browser security helpers: passed.

A deterministic offline end-to-end replay was also run with the cached RSC and snapshot payloads:

```text
python3 -m scripts.aa.orchestrate --offline ...
python3 scripts/build_site_from_aa.py --rich <offline-output> ...
python3 scripts/export_benchmarks_json.py --models-json <offline-public-output> ...
```

Observed result:

- RSC cache: 411 records, healthy.
- Snapshot cache: 570 records, healthy.
- Official API: explicitly unavailable because no cached API page existed; no network request was attempted.
- Merged offline dataset: 609 records.
- Derived public fixture output: 196 records.
- Derived public benchmarks export: 196 records.
- No source or application files were modified by this replay; outputs were written under `/tmp`.

## 6. CI changes

`.github/workflows/ci.yml` now runs the active rich pipeline tests and recursive compilation. Actions remain pinned to full commit SHAs, and the CI job retains read-only repository contents permissions.

The refresh workflow remains responsible for generated data commits and issue alerts. It will pick up rich history deltas because it already stages `data/history/`.

## 7. Current source/data coverage

The checked-in pre-implementation dataset remains the latest committed snapshot unless a real refresh is run:

- rich models: 614;
- public models: 201;
- last committed source report: RSC/API/snapshot all healthy;
- intelligence index: 601/614;
- coding index: 223/614;
- agentic index: 186/614;
- context tokens: 609/614;
- `math_index`: 0 coverage;
- public non-hallucination coverage: 193/201 according to the independent audit.

The new provenance/freshness fields are generated on the next orchestrated refresh; the committed historical JSON predates this implementation and was intentionally not rewritten merely to create a data diff.

## 8. Current history/freshness behavior

- Fresh runs write explicit freshness and source timestamps.
- Offline runs are cache-only and can be replayed without network access.
- No-healthy-source runs preserve the previous dataset but produce a stale report with `status: "stale_fallback"`.
- Successful runs compare the previous rich dataset and write a compact delta.
- Rich delta retention is capped at 104 files.
- Raw payload cache retention remains outside Git and is still not automatically pruned; this is documented as a remaining operational limitation.

## 9. Decision-engine capabilities and examples

Python API:

```python
from aa.query import AADB

db = AADB("data/aa_models_v2.json")
db.recommend("coding", limit=10)
db.pareto(["intelligence_index", "cost"])
db.backups("claude-opus-5", limit=10)
db.explain("claude-opus-5")
```

The `cost` Pareto dimension means lower blended 3:1 cost is better. Other dimensions are maximized unless prefixed with `-`. Results with missing required dimensions are excluded from the frontier rather than filled with zero.

The recommendation score is not a universal truth claim. It is a transparent profile-specific ranking among candidates that passed the stated constraints. The returned explanation identifies source, missing metrics, and the metrics used.

## 10. External source assessment

### Artificial Analysis

The official documentation was rechecked during this iteration at:

- <https://artificialanalysis.ai/data-api/docs>

The documentation describes the v2 API at `https://artificialanalysis.ai/api/v2`, `x-api-key` authentication, structured model/benchmark/pricing/performance data, pagination, response tiers, and rate-limit headers. It also states that provider-level and historical performance fields depend on higher tiers. Those boundaries support keeping the current Free API/RSC pipeline and deferring provider/time-series ingestion until the available account tier and licensing are explicitly verified.

The repository continues to use the public leaderboard RSC only as data legitimately delivered to ordinary visitors. No access controls, CAPTCHA, paywall, or private endpoint was bypassed.

### OpenRouter

The public documentation was checked at:

- <https://openrouter.ai/docs/guides/overview/models>
- <https://openrouter.ai/docs/guides/routing/provider-selection>

The documentation exposes a public models API and describes model/provider browsing, capability filters, pricing/context/throughput/latency-oriented sorting, and provider routing behavior. This is a useful orthogonal operational source, particularly for availability and endpoint choices. It was **not integrated in this iteration** because doing so correctly requires a provider-variant schema, explicit source authority rules, and a verified access/terms decision. Adding a second broad model table before those identity rules are settled would increase “benchmark soup” and merge risk rather than improve recommendation quality.

### Coding-agent/harness data

No separate coding-agent/harness adapter was added. The current rich dataset already carries some agentic/coding-related metrics, but a genuine harness dataset needs model + harness + task/version + execution/cost metadata. It belongs in a separate normalized observation layer rather than being flattened into the base model row. This is deferred until a concrete legitimately accessible source and schema are selected.

## 11. Unresolved limitations

- The checked-in historical rich JSON has not been regenerated, so its records do not yet contain the new provenance/freshness additions. The next real refresh will create the new shape.
- Provider variants are preserved as host entries, but provider-specific price/performance observations are not yet modeled as fully independent records.
- RSC parsing still depends on an undocumented upstream frontend payload; replay fixtures reduce regression risk but do not remove upstream coupling.
- Schema drift detection still warns for unknown normalized fields rather than failing every semantic change.
- The official API was not live-called during validation; no secret was available or read. Offline behavior was tested with cached RSC/snapshot data.
- Raw cache retention remains undefined.
- The public production URL was previously observed returning HTTP 403 from the audit host; this iteration did not weaken security controls or establish whether that response is intentional WAF/access policy.
- The UI does not yet expose recommendations, Pareto views, history, provider comparisons, or explanations. The stable private layer was prioritized first.
- The decision engine uses simple normalized weighted scoring and does not yet model uncertainty intervals, benchmark correlation, or statistical confidence.
- The private access overlay is supported by the CLI but no user-specific overlay was created because that would require user-provided availability facts.
- No local HTTP service was introduced; the CLI/Python API is the stable boundary for Hermes.

## 12. Deferred ideas and rationale

- **OpenRouter adapter:** deferred until provider identity, authority, and access/terms policy are explicit.
- **Full relational/SQLite schema:** deferred while bounded JSON deltas remain adequate and easier to inspect/replay.
- **Coding-agent/harness ingestion:** deferred until a concrete source and observation schema are available.
- **Historical UI charts and detail pages:** deferred until the history and recommendation contracts have more real refreshes.
- **Live cross-validation in every PR:** deferred because it would make CI network-dependent and rate-limit-sensitive. Deterministic fixtures are now the normal gate; live checks remain an operational/manual path.
- **First-party benchmark execution:** explicitly out of scope for this repository; a separate benchmark project should feed results through an adapter.
- **Automatic raw-cache pruning:** deferred because raw payloads are valuable for diagnosing parser drift and require a deliberate retention/backup policy.

## 13. Files changed

Committed in `fc17fb6`:

- `.github/workflows/ci.yml`
- `.gitignore`
- `AGENTS.md`
- `README.md`
- `scripts/aa/README.md`
- `scripts/aa/decision.py`
- `scripts/aa/history.py`
- `scripts/aa/official_api_source.py`
- `scripts/aa/orchestrate.py`
- `scripts/aa/query.py`
- `scripts/aa/rsc_source.py`
- `scripts/aa/snapshot_source.py`
- `scripts/aa/tests/fixtures/rsc_minimal.txt`
- `scripts/aa/tests/test_decision_engine.py`
- `scripts/aa/tests/test_history.py`
- `scripts/aa/tests/test_pipeline.py`
- `scripts/aa/validate.py`
- `scripts/model_compass.py`

Committed in `eb4b446`:

- `scripts/aa/orchestrate.py`
- `scripts/aa/tests/test_pipeline.py`

The previously created `REPOSITORY_REVIEW_DOSSIER.md` is retained in the repository as the audit artifact alongside this report. No credentials or private access overlay were created.

## 14. User action required

No immediate user action is required to use the new local decision layer. Optional future actions:

1. Provide a private availability profile if recommendations should be limited to the user’s actual channels.
2. Confirm whether OpenRouter integration is desired and what account/terms boundary applies.
3. Confirm the desired retention policy for ignored raw payload caches.
4. Run the next real scheduled or manually triggered refresh so the committed rich dataset receives provenance/freshness fields and the first rich delta file is generated.
5. Investigate the production 403 through the Cloudflare/access-control owner without weakening CSP or deployment boundaries.

## Final assessment

This iteration establishes a stronger foundation rather than claiming that Model Compass is already a complete model-intelligence platform. The active pipeline now has deterministic replay protection, honest offline behavior, explicit stale reporting, richer provenance, provider-variant preservation, bounded history deltas, CI coverage for the active code, and a transparent Hermes-friendly decision interface. The next highest-value work is to observe several real refreshes, validate the new history/provenance in production, then promote provider observations and access-aware recommendations only after identity and source-authority rules are settled.
