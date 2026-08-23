# Model Compass Phase 3 Report

**Status:** PARTIALLY COMPLETE — the deterministic Phase 3 observation, identity, query, history, and health layers are implemented and tested, but the public Endpoint Accuracy JSON-LD source is still partial/manual and current OpenRouter observations do not provide verified cross-source IDs for the representative AA models. The PR is therefore not ready to merge as a fully accepted Phase 3.

## 1. Starting baseline

- Repository: `/srv/projects/shared/model-compass`
- Baseline branch: `main`
- Baseline commit: `47b074b66aaaa27068e4c32e0af5f8c8cc0a4c34`
- Phase 3 branch: `feat/model-compass-phase3`
- Baseline was verified clean and matched `origin/main` before branching.
- Phase 2 deterministic tests and public validators passed before implementation.
- Baseline checked-in counts: 618 rich models, 204 public models, 445 OpenRouter provider observations, and 27 partial coding-agent observations.

## 2. Source discovery

Live read-only retrieval was performed against the current public pages. Artificial Analysis currently publishes Endpoint Accuracy Index v1.0 as a point-in-time percentage of a self-hosted reference, with a 95% confidence interval and reference-parity classification semantics.[1] The methodology describes BFCL v4-500, HLE-250, and AA-LCR-25 as equally weighted components and says the covered model set rotates.[1]

The current GLM-5.2 provider page exposes an Endpoint Accuracy JSON-LD Dataset with provider labels, mid/lower/upper values, and provider detail URLs. Its visible page showed 21 provider rows, while the public JSON-LD payload exposed 14 endpoint rows; this difference is intentionally reported as partial coverage rather than silently filled.[2] The gpt-oss-120b page exposed 16 JSON-LD endpoint rows.[3] The DeepSeek V4 Pro page did not expose the expected Endpoint Accuracy JSON-LD dataset during this run, so it was not ingested.

The coding-agent page exposes JSON-LD metric datasets for Coding Agent Index, Time per Task, and Cost per Task. The live page describes the current index as DeepSWE, Terminal-Bench v2.1, and SWE-Atlas-QnA, and exposes harness/model variants plus quality, cost, time, and token-usage sections.[4][5] The public JSON-LD payload available to an ordinary visitor did not include all rendered/network-only rows or all token fields.

OpenRouter documents model/provider routing as separate decisions and exposes provider sorting by price, throughput, and latency.[6] The existing OpenRouter adapter remains separate and was not replaced.

## 3. Endpoint Accuracy ingestion

Implemented `scripts/aa/endpoint_accuracy.py`.

- Access method: ordinary public HTTPS provider page; no authentication or bypass.
- Payload: bounded public JSON-LD extraction, maximum 8 MiB.
- Parser version: `0.2.0`.
- Output: `data/endpoint_accuracy_observations.json`.
- Current live result: 30 observations across 2 models (`glm-5-2`, `gpt-oss-120b`), index version `1.0`.
- DeepSeek V4 Pro was explicitly not published as a successful empty result because the expected structured dataset was absent.
- The adapter remains manual/experimental and is not added to the weekly refresh workflow.

### Preserved schema

Each observation preserves:

- `observation_type: endpoint_accuracy`;
- AA model slug/name;
- provider and endpoint IDs/labels;
- index version;
- `accuracy.mid`, `accuracy.lower`, `accuracy.upper`, and reference percentage;
- source classification when present, otherwise `unknown`;
- component, repeat-count, output-token, measurement-date, reference, and notes fields when exposed;
- source URL, fetch timestamp, parser version, and `point_in_time: true` provenance.

The source confidence interval is never recomputed. If a source classification is absent, the provider query layer may derive only a clearly labeled `reference_consistent`/`below_reference` state from whether the supplied interval contains 100; it does not invent a confidence interval or a significance test.

## 4. Coding-agent ingestion

Implemented a richer structured path in `scripts/aa/coding_agent_source.py` while retaining the old `parse_datasets()` JSON-LD fallback contract for compatibility.

The new `parse_datasets_rich()` path merges metric views by the source-declared variant label and preserves:

- variant ID and original source labels;
- harness/agent name;
- model display name without asserting a canonical model ID;
- configuration/reasoning text where present;
- dynamic benchmark/index version;
- Coding Agent Index;
- cost per task;
- agent wall time per task;
- token container and cache-hit fields when exposed;
- source/parser/fetch provenance.

Coverage comparison:

| Measure | Phase 2 | Phase 3 live structured artifact |
|---|---:|---:|
| Partial observations/rows | 27 | 9 merged variants |
| Coding Agent Index values | 9 views | 9 variants |
| Cost per task | present in partial views | 9 variants |
| Agent wall time | present in partial views | 9 variants |
| Model/harness/configuration distinction | mostly label-only | explicit fields plus original labels |
| Benchmark version | dynamic JSON-LD extraction | dynamic `1.4` |

The improvement is structure and cross-metric alignment, not row count. No model ID is inferred from free text.

## 5. Cross-source identity

Implemented `scripts/aa/identity.py` and `data/identity_aliases.json`.

Mapping states are explicit: `verified`, `manual`, `candidate`, `unresolved`, `ambiguous`, and `conflict`. Strong same-source AA slugs are verified. Normalized display-name equality can produce only a `candidate`; it is not used as an authoritative join. Manual mappings are versioned, auditable, reversible, and separate from credentials.

Current health artifact: `data/identity_mappings.json`.

- AA models: 618
- OpenRouter observations: 445
- Verified same-source endpoint/model mappings: 30
- Candidate AA↔OpenRouter mappings: 0
- Unresolved OpenRouter model IDs: 445
- Ambiguous mappings: 0
- Conflicts: 0
- Manual overrides: 0

This is an honest coverage result: current OpenRouter IDs did not provide enough evidence for automatic AA↔OpenRouter joins. It prevents false provider recommendations rather than pretending the names are equivalent.

## 6. Provider decision changes

`ProviderDB` now accepts Endpoint Accuracy observations and returns an explanation containing:

- `measured_good`, `measured_degraded`, `measured_uncertain`, or `not_measured`;
- source observation and provenance;
- profile, minimum accuracy, evidence requirement, and unknown-evidence policy;
- missing-evidence flag.

Supported modes include `interactive`, `batch`, and `accuracy-first`, plus `--require-accuracy-evidence`, `--min-accuracy`, and `--disallow-unknown` in the CLI. Missing Endpoint Accuracy is not treated as failure unless the caller explicitly requires evidence. Strict accuracy-first behavior excludes measured-degraded endpoints in the tested fixture.

A real unified `recommend-provider glm-5-2` result could not be demonstrated from the current OpenRouter artifact because no verified mapping connects that AA slug to an OpenRouter model ID. The implementation therefore refuses the join instead of emitting a plausible but unsupported recommendation. Fixture tests cover parity, degradation, unknown evidence, strict evidence, and deterministic selection.

## 7. Coding-agent queries

Added/retained machine-readable CLI surfaces:

```text
endpoint-accuracy MODEL
recommend-provider MODEL --profile accuracy-first
recommend-provider MODEL --require-accuracy-evidence
agents
recommend-agent coding_agent_index|cost|time
identity-health
unresolved-identities
health
```

`CodingAgentDB.pareto()` now provides a quality/cost frontier for compatible same-version observations. Benchmark version remains part of every observation, and history marks version changes as not directly comparable.

## 8. History/change intelligence

Extended `scripts/aa/history.py` with `diff_observations()` for endpoint and agent observations. It records added, removed, and materially changed observations. Accuracy mid/interval/classification fields remain source values; no significance is inferred from small point-estimate movement. Coding-agent benchmark-version changes generate an explicit comparability marker.

Existing canonical model history behavior and bounded 104-file retention remain intact.

## 9. Private access overlay

No new private access facts were added. The existing gitignored overlay remains separate from external benchmark truth and contains no keys, cookies, or tokens. Because the identity layer currently leaves OpenRouter joins unresolved, no unverified access-aware provider result was exposed.

## 10. Source health and workflow

`health` now reports Endpoint Accuracy artifact presence/coverage and identity health alongside the existing AA source report. The Phase 3 adapters are deliberately manual/experimental rather than promoted to weekly refresh because:

1. public JSON-LD coverage is smaller than visible page coverage;
2. the DeepSeek page lacked the expected structured dataset;
3. the source coverage rotates;
4. the current identity coverage is insufficient for unified provider recommendations.

This is a bounded failure mode: a missing optional source cannot overwrite canonical model or public site artifacts.

## 11. Deterministic fixtures and tests

Added:

- `endpoint_accuracy_minimal.html`;
- `coding_agents_rich.html`;
- `test_phase3_observations.py`.

The new tests cover interval parsing, classification preservation, point-in-time metadata, richer metric merge, variant/configuration extraction, unresolved/candidate identity health, strict accuracy evidence, degraded-provider exclusion, and incompatible benchmark-version history.

Exact commands and results:

```text
python3 -m compileall -q scripts                         PASS
python3 scripts/test_fetch_aa_models.py                  PASS (6 tests)
python3 scripts/aa/tests/test_pipeline.py                PASS
python3 scripts/aa/tests/test_decision_engine.py         PASS
python3 scripts/aa/tests/test_history.py                 PASS
python3 scripts/aa/tests/test_observations.py            PASS
python3 scripts/aa/tests/test_phase3_observations.py     PASS
python3 scripts/validate_site.py                         PASS (204 models)
node --check public/assets/nav.js                        PASS
node --check public/assets/models.js                     PASS
node --check public/assets/theme-init.js                 PASS
node scripts/test_browser_security.mjs                   PASS
```

## 12. Live acceptance

- **Gate A:** PASS for legitimate structured ingestion on GLM-5.2 and gpt-oss-120b: current version `1.0`, 30 observations, provider IDs, scores, and intervals parsed. Page-vs-JSON-LD coverage difference and missing DeepSeek structured payload are recorded.
- **Gate B:** PARTIAL PASS: richer observations align the public Coding Agent Index, cost, and wall-time views into 9 variants with explicit harness/model/configuration fields. Public JSON-LD does not expose the complete rendered dataset or token telemetry.
- **Gate C:** PASS as a health report, but coverage is intentionally low: 30 verified same-source endpoint mappings and 445 unresolved OpenRouter model IDs; no silent fuzzy joins.
- **Gate D:** PARTIAL: fixture demonstrations pass. Live unified provider recommendations for the named AA models are blocked by absent verified AA↔OpenRouter identity mappings, so no unsupported live recommendation is claimed.

## 13. Files and commits

Commits on the Phase 3 branch:

- `9893a92 feat: add endpoint and identity intelligence`
- `0b7963e feat: expose phase 3 queries and health`

Key files:

- `scripts/aa/endpoint_accuracy.py`
- `scripts/aa/coding_agent_source.py`
- `scripts/aa/identity.py`
- `scripts/aa/provider_query.py`
- `scripts/aa/history.py`
- `scripts/model_compass.py`
- `scripts/aa/tests/test_phase3_observations.py`
- `data/endpoint_accuracy_observations.json`
- `data/coding_agent_observations.json`
- `data/identity_mappings.json`
- `data/identity_aliases.json`
- `data/phase3_summary.json`
- `MODEL_COMPASS_PHASE3_REPORT.md`

## 14. Artifact/repository size impact

The Endpoint Accuracy artifact is approximately 30 KB; the identity health artifact is approximately 55 KB; the coding-agent artifact is approximately 16 KB. The repository remains JSON-based; no SQLite migration was justified because the bounded observation volumes and fixture replay needs remain manageable.

## 15. Known limitations and deferred Phase 4 work

- Endpoint Accuracy component-level values, repeat counts, dates, and classifications are null/unknown when the public JSON-LD does not expose them.
- Visible provider-page rows exceed JSON-LD rows on the sampled page; no HTML chart scraping or private/network endpoint bypass was attempted.
- DeepSeek V4 Pro had no expected public JSON-LD accuracy dataset in this run.
- Coding-agent token fields were not exposed in the available JSON-LD payload.
- Automatic AA↔OpenRouter identity resolution remains unresolved for current catalog observations.
- No automatic model routing or production-agent configuration was changed.
- Endpoint and coding-agent sources are not in weekly refresh CI yet.
- A future phase should add a legitimate stable structured source or authenticated configured source where permitted, expand identity evidence, add provider-page artifact adapters where terms permit, and complete live unified recommendation acceptance.

## 16. User action and merge recommendation

No user action is required to run the deterministic tests. Human review is required before merging. If the user wants weekly automation, they must decide whether the partial public JSON-LD coverage is acceptable or provide an approved stable source/access contract; this implementation intentionally does not promote a fragile adapter automatically.

**Merge recommendation: NOT READY TO MERGE as a complete Phase 3.** The branch is suitable for review as a partial implementation, but Gate D is incomplete and the new sources should remain manual/experimental until identity coverage and stable structured coverage improve.

## Sources

[1] https://artificialanalysis.ai/methodology/endpoint-accuracy-index  
[2] https://artificialanalysis.ai/models/glm-5-2/providers  
[3] https://artificialanalysis.ai/models/gpt-oss-120b/providers  
[4] https://artificialanalysis.ai/agents/coding-agents  
[5] https://artificialanalysis.ai/methodology/coding-agents-benchmarking  
[6] https://openrouter.ai/docs/guides/routing/provider-selection
