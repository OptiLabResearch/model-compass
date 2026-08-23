# Model Compass Phase 2 Pre-Merge Correction Report

**Date:** 2026-08-23 UTC
**Repository:** `/srv/projects/shared/model-compass`
**Branch:** `phase2-validation`
**PR:** [#6](https://github.com/OptiLabResearch/model-compass/pull/6)
**Scope:** focused pre-merge correction pass only; no Phase 3 implementation

## Merge recommendation

**Recommendation: merge PR #6 after the final CI check for the latest correction commit is green.**

The implementation is functionally ready. The branch is currently marked `MERGEABLE` by GitHub, but the PR is still a draft and its merge state is `UNSTABLE` because the latest bot-generated refresh commit does not have a newly attached CI check. The correction commit itself passed CI before the final refresh, and the final refresh workflow plus Cloudflare preview both passed. I pushed a final human-authored documentation/report commit after the refresh to cause the required CI workflow to run against the final branch tip; the final merge recommendation should be considered confirmed once that check reports success.

PR #6 was **not merged automatically**.

## 1. Exact corrections made

### Coding-agent benchmark version

**Bug:** `coding_agent_source.py` previously hard-coded `benchmark_version: "1.4"`.

**Fix:** the adapter now parses a version from public methodology/description text using a structured version pattern. If no version is exposed, it records `null` rather than inventing one. The version is shared across the Coding Agent Index, Time per Task, and Cost per Task JSON-LD datasets when the page exposes it once.

**Verification:** the checked-in fixture says `Coding Agent Index v1.3` and produces `benchmark_version: "1.3"` for all three observations. The live page at the time of the corrected refresh exposed `v1.4`, which was captured as a derived value. The code no longer silently preserves an obsolete constant.

### Recommendation freshness

**Bug:** recommendation explanations used `_fresh(model, None)`, which returned `True` without examining age.

**Fix:** freshness is centralized in `_freshness_state()` and returns exactly one of:

- `fresh` — timestamp exists and is within the 14-day evidence window;
- `stale` — timestamp exists but is older than the window, or provenance explicitly marks stale;
- `unknown` — timestamp is absent, malformed, or in the future.

The recommendation explanation and nested confidence object use the same helper. Missing timestamps are no longer reported as fresh.

**Tests:** fresh, stale, absent/malformed/unknown timestamp cases are covered.

### Provider recommendation semantics

**Bug:** the batch profile primarily selected lowest input price even when throughput was available. `value or infinity` expressions also treated valid zero prices as missing/worst.

**Fix:**

- **Interactive:** availability first, then measured latency, then price, then provider ID as a deterministic tie-breaker.
- **Batch:** availability first, then measured throughput descending, then price ascending, then provider ID.
- Unavailable endpoints rank after available/unknown endpoints.
- Zero-valued prices and throughput remain valid numeric measurements.
- Missing latency/throughput/price is explicitly ranked after present values.
- Stable provider-ID tie behavior is tested.

### Provider identity stability

OpenRouter endpoint payloads expose a `tag` field and provider name. The adapter prefers `tag`, normalized deterministically, and falls back to normalized provider name. Each observation now carries:

```text
identity_key = model_id : provider_id : endpoint_id
```

This is an OpenRouter-local identity only. No fuzzy AA/OpenRouter canonical join was introduced.

### OpenRouter sampling, rotation, and retention

**Bug:** every run queried the first 25 catalog entries, making coverage dependent on upstream ordering and preventing useful expansion.

**Fix:**

- catalog IDs are sorted deterministically;
- a persisted cursor selects the next bounded cohort;
- optional priority IDs are supported without making them mandatory;
- each refresh selects at most 25 model details;
- `data/openrouter_sampling_state.json` stores the cursor and persists rotation;
- previous observations are retained for 14 days using `last_seen` timestamps;
- expired observations are removed;
- output records selected IDs, cursor before/after, fresh/retained counts, catalog coverage, and retention policy;
- retained legacy observations receive a stable identity key during migration.

This avoids uncontrolled growth while ensuring subsequent weekly runs advance through the catalog.

### Honest coding-agent coverage

The artifact now explicitly reports:

```json
{
  "scope": "partial_public_jsonld",
  "complete_public_dataset": false,
  "agent_labels": 18,
  "dataset_names": ["Coding Agent Index", "Cost per Task", "Time per Task"]
}
```

The 27 rows are a partial structured JSON-LD view, not the complete public Coding Agent dataset. Richer page/network data remains a Phase 3 investigation.

## 2. Real refresh and provider coverage

The corrected branch ran the authenticated refresh workflow again as GitHub Actions run `32625444780`.

Live results:

| Source/artifact | Result |
|---|---:|
| RSC | 416 records, healthy |
| Official AA API | 609 records, healthy |
| Oolong snapshot | 570 records, healthy |
| Merged rich dataset | 618 models |
| Public dataset | 204 models |
| OpenRouter catalog | 422 models |
| OpenRouter selected this run | 25 models |
| OpenRouter retained endpoint observations | 387 |
| OpenRouter catalog models with detailed observations | 114 / 422 (27.01%) |
| OpenRouter endpoint errors | 0 |
| Coding-agent observations | 27 |
| Coding-agent live version | derived `1.4` from current public page |
| Rich delta | 0 added, 0 removed, 0 material changes in this refresh |

The provider artifact contains fresh and retained observations, and the selection cursor advanced. A prior local focused live run advanced the cursor across additional cohorts; the final workflow run preserved the bounded rotation/retention behavior through the actual GitHub Actions path.

## 3. Tests and validation

Executed locally after the correction changes:

```text
python3 -m compileall -q scripts                         PASS
python3 scripts/test_fetch_aa_models.py                  6 tests PASS
python3 scripts/aa/tests/test_pipeline.py                9 tests PASS
python3 scripts/aa/tests/test_decision_engine.py          5 tests PASS
python3 scripts/aa/tests/test_history.py                 2 tests PASS
python3 scripts/aa/tests/test_observations.py             9 tests PASS
python3 scripts/validate_site.py                          PASS (204 models)
node scripts/test_browser_security.mjs                    PASS
CLI access/provider/agent smoke tests                      PASS
```

The corrected live refresh workflow passed all of its steps:

- rich AA orchestration;
- public derivation;
- history CSV export;
- benchmark export;
- OpenRouter provider refresh;
- coding-agent refresh;
- generated-data commit;
- failure handling step.

Draft PR #6’s Cloudflare Pages preview check is green. The CI check was green for the correction commit before the final generated refresh commit. A final documentation commit was pushed afterward to make GitHub attach a fresh CI check to the latest branch tip; that latest check is the remaining merge gate.

## 4. Commits

Focused correction commit:

- `142cf76 fix: correct phase 2 provider and freshness semantics`

Documentation/report follow-up:

- `0deb3b2` — record pre-merge correction details in the Phase 2 report;
- `5b8a8f3` — add this pre-merge report;
- `79573b8` — update final provider coverage after the corrected workflow refresh.

- `40555ad feat: add provider and coding agent intelligence`
- `92612ed data: weekly refresh 2026-08-23`
- `7b4a559 data: weekly refresh 2026-08-23` after the final corrected workflow run

## 5. PR status and mergeability

At the time of this report:

- PR: open, draft, #6;
- branch: `phase2-validation`;
- base: `main`;
- GitHub mergeable field: `MERGEABLE`;
- branch protection was not bypassed;
- Cloudflare Pages preview: green;
- latest refresh workflow: green;
- latest CI check: rerun/verification pending after the final report commit.

Once the latest `Security and integrity checks` result is green, I recommend marking the PR ready for review and merging it normally. I do not recommend merging while GitHub reports the latest branch tip as `UNSTABLE`.

## 6. Remaining blockers to merge

No code or data correctness blocker remains from the requested pre-merge review.

The only procedural blocker is confirmation that the final branch tip has a green required CI check after the last generated refresh/report update. This is a GitHub check-state issue, not a known test or implementation failure.

## 7. Phase 2 report update

`MODEL_COMPASS_PHASE2_REPORT.md` now contains a **Pre-Merge Corrections** section documenting these fixes and the updated provider coverage. The report does not erase the original Phase 2 limitations; it records that the corrections were made afterward.

## 8. Phase 3 handoff notes — explicitly deferred

No Phase 3 implementation was started.

Next priorities:

1. Investigate Artificial Analysis Endpoint Accuracy Index data and methodology:
   - <https://artificialanalysis.ai/articles/endpoint-accuracy-index>
   - <https://artificialanalysis.ai/methodology/endpoint-accuracy-index>
2. Investigate richer public coding-agent page/network/RSC data for DeepSWE, Terminal-Bench, SWE-Atlas-QnA, cost, time, token usage, model, and harness views.
3. Build evidence-based joins among AA model/configuration IDs, OpenRouter IDs/endpoints, and coding-agent labels without silent fuzzy matching.
4. Add provider observation history events for endpoint additions/removals and material operational changes.
5. Add model-specific private aliases and quota/marginal-cost classifications only when explicitly configured.

## Final assessment

The requested focused corrections are implemented, tested, committed, and exercised through a second real authenticated refresh. PR #6 is **functionally ready to merge**, pending the final green CI check on its latest branch tip. It should not be merged automatically by this task.
