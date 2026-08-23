# Model Compass Phase 2 Report

**Date:** 2026-08-23 UTC
**Repository:** `/srv/projects/shared/model-compass`
**Validation branch:** `phase2-validation`
**Draft PR:** `#6`
**Phase 2 refresh commit:** `92612ed`
**Phase 2 refresh run:** GitHub Actions run `32622159112`

## 1. Executive summary

Phase 2 was executed against the live repository and live upstream services. The new implementation was pushed to a linear validation branch, a real authenticated GitHub Actions refresh was run with the configured `AA_API_KEY` secret, the generated artifacts were pulled back and inspected, and the actual CI workflow was exercised through draft PR #6.

The live Phase 2 refresh passed all active refresh steps:

- RSC: **416 records, healthy**
- Official Artificial Analysis API: **609 records, healthy**
- Oolong snapshot: **570 records, healthy**
- Merged rich dataset: **618 models**
- Derived public dataset: **204 models**
- Public benchmark export: **204 models**
- OpenRouter catalog: **422 models**
- OpenRouter provider observations: **63 endpoint observations**, zero endpoint errors, bounded to 25 model-detail requests
- Artificial Analysis coding-agent observations: **27 observations** across Coding Agent Index, Time per Task, and Cost per Task
- Refresh workflow: **success in 23 seconds**
- CI workflow on draft PR #6: **success**
- Cloudflare Pages preview check on the draft PR: **pass**

The previous foundation now works with a real authenticated refresh. The generated rich records contain per-record source provenance and freshness metadata. The new provider and coding-agent layers remain separate from canonical model benchmark records.

The production hostname diagnosis is also clearer: `models.optiqo.dev` resolves to Cloudflare Anycast IPs and returns Cloudflare **error code 1010** before the origin is reached (`cfOrigin;dur=0`). `/robots.txt` is served successfully. This points to a Cloudflare access/security rule affecting the audit source IP or request class, not a static-site schema or origin build failure. No CSP/WAF weakening was performed.

## 2. Starting evidence and repository state

Before implementation, the following were read and verified:

- `REPOSITORY_REVIEW_DOSSIER.md`
- `MODEL_COMPASS_IMPROVEMENT_REPORT.md`
- `README.md`
- `AGENTS.md`
- `scripts/aa/README.md`
- current source, tests, CI, and refresh workflow

The repository had already passed the Phase 1 implementation commits:

- `fc17fb6` — pipeline hardening and decision engine
- `eb4b446` — provider-variant preservation during source merge
- `4a2b781` — honest cached-data freshness reporting

The local host did not contain `.env`, and `AA_API_KEY` was not present in the local environment. The GitHub repository secret list confirmed an `AA_API_KEY` secret exists without exposing its value. Therefore the real authenticated refresh was run through GitHub Actions rather than by copying or printing a secret locally.

## 3. Live refresh acceptance

### 3.1 First live refresh against remote main

A manual refresh was dispatched against the then-current protected `main` revision. It completed successfully as run `32621379393` and produced:

| Measure | Result |
|---|---:|
| RSC records | 416 |
| Official API records | 610 |
| Snapshot records | 570 |
| Merged rich models | 619 |
| Public models | 205 |
| Public benchmark rows | 205 |

The workflow committed generated data as `0b6fffa`.

This run proved the upstream sources and original refresh path were live, but it ran the pre-Phase-2 remote code. It was therefore not treated as proof of the new provenance/provider/coding-agent implementation.

### 3.2 Phase 2 live refresh with new code

Because direct push to protected `main` was rejected for containing a merge commit, a linear `phase2-validation` branch was created from the refreshed remote main and the reviewed implementation commits were cherry-picked. The branch was pushed and the same refresh workflow was dispatched as run `32622159112`.

The complete job passed:

```text
Set up job                                      PASS
Build private AA dataset                        PASS
Build public site models.json                   PASS
Export dated history CSV                        PASS
Export static benchmarks JSON                   PASS
Refresh provider observations                   PASS
Refresh coding-agent observations              PASS
Commit and push if changed                      PASS
```

Live results from the workflow log:

| Measure | Phase 1 baseline | Phase 2 live result | Assessment |
|---|---:|---:|---|
| RSC records | ~411 | 416 | legitimate upstream growth |
| Official API records | ~610 | 609 | one-record upstream movement |
| Snapshot records | ~570 | 570 | stable |
| Rich merged models | 614 | 618 | no collapse; +4 net |
| Public models | 201 | 204 | consistent with new/recent models |
| Intelligence coverage | 601/614 | 605/618 | slightly improved |
| Coding index coverage | 223/614 | 224/618 | essentially stable |
| Agentic index coverage | 186/614 | 188/618 | slightly improved |
| Context coverage | 609/614 | 614/618 | improved |
| GPQA coverage | 576 | 581 | improved |
| HLE coverage | 570 | 575 | improved |
| SciCode coverage | 568 | 573 | improved |
| Terminal-Bench Hard | 438 | 438 | stable |

The changes are consistent with upstream model additions/updates, not an extraction collapse. The workflow also committed the generated refresh as `92612ed` on `phase2-validation`.

## 4. Provenance and freshness verification

The pulled Phase 2 rich output was inspected after the successful workflow run.

Top-level report:

```json
{
  "total_models": 618,
  "status": "fresh",
  "stale": false,
  "sources": {
    "rsc": {"healthy": true, "records": 416},
    "official_api": {"healthy": true, "records": 609},
    "snapshot": {"healthy": true, "records": 570}
  }
}
```

A representative rich record contained:

```json
{
  "source": "rsc",
  "intelligence_index_version": 4.1,
  "merged": {
    "primary": "rsc",
    "also_from": ["official_api", "snapshot"]
  },
  "provenance": {
    "sources": ["rsc", "official_api", "snapshot"],
    "primary_source": "rsc",
    "parser_version": "0.2.0",
    "fetched_at": "2026-08-23T06:08:54Z",
    "cached": false
  }
}
```

The live-generated data therefore verifies:

- primary/contributing sources;
- parser version;
- source fetch timestamp;
- cache indicator;
- AA index-version provenance;
- top-level freshness/status;
- source-level health and counts.

The provider and coding-agent artifacts carry their own source timestamps and parser/source metadata rather than being inserted into the base model record.

## 5. First real rich-history delta

The Phase 2 workflow generated `data/history/rich/2026-08-23.delta.json` against the previous rich snapshot.

The committed real delta contains:

```json
{
  "previous": 619,
  "current": 618,
  "added": 0,
  "removed": 1,
  "changed": 3
}
```

The one removal and three material changes are represented as explicit raw before/after values. The history implementation applies materiality thresholds to avoid recording trivial float noise:

- composite indices: 0.1 normalized units;
- prices: 1% relative movement;
- speed: 5% relative movement;
- booleans, dates, context, and presence changes: exact changes.

Retention remains bounded to 104 rich delta files. The current real delta is committed on the validation branch and was produced by the active workflow, not a synthetic test.

## 6. Production 403 diagnosis

Read-only checks from the VPS:

- `models.optiqo.dev` resolves to Cloudflare Anycast addresses `188.114.96.1`, `188.114.97.1`, and IPv6 Cloudflare addresses.
- HTTPS `/` returns HTTP 403 with body `error code: 1010`.
- `/data/models.json` returns the same HTTP 403/1010.
- `/robots.txt` returns HTTP 200.
- Response headers identify Cloudflare and include `Server-Timing: cfEdge;dur=...,cfOrigin;dur=0`.
- A Cloudflare Pages preview check on draft PR #6 passed.

Interpretation: the request is reaching Cloudflare, but the main site request is denied by a Cloudflare access/security rule before the origin is contacted. This is consistent with an IP, bot, browser-integrity, hostname, or WAF policy. It is not evidence that the static artifact or Cloudflare Pages build is malformed. The remediation belongs in Cloudflare rules/access policy, using a controlled browser or allowlisted diagnostic path; security controls were not weakened.

## 7. Decision-engine changes

### Confidence is now separate from ranking

Each recommendation still has a deterministic profile-specific ranking score, but its explanation now includes an independent evidence assessment:

```json
{
  "score": 0.91,
  "confidence": {
    "level": "medium",
    "evidence_coverage": 0.667,
    "missing_metrics": ["speed"],
    "source_count": 2,
    "source_agreement": "unknown",
    "freshness_days": 0.1,
    "fresh": true
  }
}
```

Confidence is a qualitative evidence label, not a fabricated statistical interval. It considers:

- required profile metric presence;
- presence of optional cost/speed metrics that have nonzero profile weights;
- freshness when a timestamp exists;
- number of contributing sources;
- explicit source agreement/disagreement when available;
- missing evidence.

The levels are:

- **high:** at least 80% evidence coverage, fresh/unknown age, at least two sources, and no recorded disagreement;
- **medium:** at least 50% evidence coverage without recorded disagreement;
- **low:** sparse evidence or explicit disagreement.

Unknown source agreement remains `unknown`; it is not silently treated as corroboration.

### Profile versioning

Named profiles now expose `profile_version: "1.0"` in recommendation output. Custom profiles receive a `custom-1` version unless they provide an explicit version. The profile version, selected metric, constraints, and explanations are therefore auditable from machine-readable output.

### Pareto behavior

The contract is explicit:

- `cost` is minimized;
- dimensions prefixed with `-` are minimized;
- all other dimensions are maximized;
- missing dimensions exclude a model from that frontier rather than becoming zero.

## 8. Provider observation schema and identity rules

Provider data is now first-class in a separate observation artifact. The canonical model dataset remains backward-compatible and is not overwritten by OpenRouter fields.

A provider observation contains:

- `observation_type: "provider_endpoint"`;
- `model_id` and `model_slug` using the provider’s endpoint identifier;
- `provider_id`, `provider_name`, and `endpoint_id`;
- provider-specific context length;
- input/output price per million tokens plus raw pricing;
- provider latency and throughput when exposed;
- uptime/status over the available windows;
- quantization;
- supported parameters/capabilities;
- privacy placeholder for only legitimately exposed properties;
- source, fetched timestamp, and source authority.

Identity rules:

1. The OpenRouter model/endpoint identifier is not assumed to equal the Artificial Analysis canonical slug.
2. Provider observations remain keyed by `(source, model_id, provider_id, endpoint_id)`.
3. OpenRouter is authoritative for its provider availability, routing, endpoint pricing, uptime, and provider operational fields.
4. Artificial Analysis remains authoritative for its benchmark/index fields.
5. Context and capability fields remain source-specific unless an explicit reconciliation rule is later added.
6. A provider observation cannot overwrite canonical benchmark truth.

The current committed live artifact is `data/openrouter_observations.json` with 422 catalog models and 387 retained detailed endpoint observations from bounded rotating cohorts (114 catalog models, 27.01% coverage).

Supported queries:

```bash
python3 scripts/model_compass.py providers meta/muse-spark-1.2-contributor
python3 scripts/model_compass.py recommend-provider meta/muse-spark-1.2-contributor --profile interactive
```

The live smoke query returned the Meta endpoint with 1,048,576 context tokens, 0.10/0.20 USD per million input/output pricing, availability status, and source timestamp.

## 9. OpenRouter integration status and fields

OpenRouter was tested directly during implementation:

- `GET https://openrouter.ai/api/v1/models` returned HTTP 200;
- payload contained 422 catalog models;
- per-model endpoint details returned provider name, tag, pricing, context, quantization, supported parameters, status, uptime, latency, and throughput fields;
- two-model and 25-model bounded adapter runs succeeded with zero endpoint errors.

The adapter is `scripts/aa/openrouter_source.py`. It uses the public API without credentials and is now part of the weekly refresh workflow with `--max-endpoints 25`.

OpenRouter does not overwrite AA benchmark values. Provider query output carries provenance and timestamp.

External documentation checked:

- <https://openrouter.ai/docs/guides/overview/models>
- <https://openrouter.ai/docs/guides/routing/provider-selection>

Those documents describe the public models API, capability filters, provider routing, pricing/context/throughput/latency-oriented model information, and provider selection concepts. The implementation uses only the public API path verified in this environment.

## 10. Coding-agent/harness integration status and fields

The Artificial Analysis coding-agent page was publicly reachable without authentication:

- <https://artificialanalysis.ai/agents/coding-agents>

The page includes JSON-LD Dataset payloads for:

- Coding Agent Index;
- Time per Task;
- Cost per Task.

The live page reported Coding Agent Index methodology/version information and 9 agent/harness labels in each dataset. The adapter produced 27 observations, preserving each displayed agent/harness label verbatim.

The artifact is `data/coding_agent_observations.json`. Each observation contains:

- `observation_type: "coding_agent"`;
- agent/harness label;
- model ID when explicitly available, otherwise null rather than guessed;
- benchmark suite and version;
- component score map;
- execution time when supplied;
- cost per task when supplied;
- source and fetched timestamp;
- methodology description where available.

The implementation intentionally does not flatten an agent row into the base model record. The same underlying model can appear under different agent/harness labels without losing that distinction.

Supported queries:

```bash
python3 scripts/model_compass.py agents --limit 10
python3 scripts/model_compass.py recommend-agent coding_agent_index --limit 10
python3 scripts/model_compass.py recommend-agent cost --limit 10
python3 scripts/model_compass.py recommend-agent time --limit 10
```

Current limitations: the public page exposes labels rather than a complete stable canonical model/harness join and the captured public page currently provides aggregate score/time/cost datasets rather than full per-benchmark component rows. The adapter preserves that limitation instead of inventing model IDs.

External references checked:

- <https://artificialanalysis.ai/agents/coding-agents>
- <https://artificialanalysis.ai/agents/coding-agents/comparisons>
- <https://artificialanalysis.ai/methodology/coding-agents-benchmarking>

## 11. Private access overlay status

A gitignored `.model-compass-access.json` was populated from non-secret local availability checks. It contains channel-level facts only:

| Channel | Status | Evidence |
|---|---|---|
| Codex | available | `/home/hermes/.local/bin/codex` exists |
| Antigravity/AGY | available | `/home/hermes/.local/bin/agy` exists |
| OpenCode | unavailable locally | `opencode` executable not found |
| OpenRouter | operational source available | public catalog returned HTTP 200; private credential was not inspected |

No credentials, cookies, OAuth tokens, API keys, aliases, or model secrets were written. The overlay supports future model/channel entries but currently contains no model-specific availability claims. `python3 scripts/model_compass.py access` prints channel status without secrets.

This deliberately distinguishes “the source/catalog is reachable” from “a private credential is configured.”

## 12. Agent-facing interface

The stable JSON CLI now includes:

```bash
python3 scripts/model_compass.py list [query]
python3 scripts/model_compass.py recommend PROFILE
python3 scripts/model_compass.py pareto DIMENSION...
python3 scripts/model_compass.py backup MODEL
python3 scripts/model_compass.py explain MODEL
python3 scripts/model_compass.py providers MODEL_ID
python3 scripts/model_compass.py recommend-provider MODEL_ID --profile interactive|batch
python3 scripts/model_compass.py agents
python3 scripts/model_compass.py recommend-agent coding_agent_index|cost|time
python3 scripts/model_compass.py access
python3 scripts/model_compass.py changes --previous SNAPSHOT
python3 scripts/model_compass.py health
```

The Python API exposes corresponding `AADB`, `DecisionEngine`, `ProviderDB`, and `CodingAgentDB` surfaces. Human-oriented UI scraping is not required.

Recommendation responses expose profile/version, constraints, source list, timestamps/provenance, missing metrics, evidence coverage, qualitative confidence, and access filtering when requested.

## 13. Exact tests and results

Executed locally after pulling the real Phase 2 refresh artifacts:

```text
python3 -m compileall -q scripts                         PASS
python3 scripts/test_fetch_aa_models.py                  6 tests PASS
python3 scripts/aa/tests/test_pipeline.py                9 tests PASS
python3 scripts/aa/tests/test_decision_engine.py          4 tests PASS
python3 scripts/aa/tests/test_history.py                 2 tests PASS
python3 scripts/aa/tests/test_observations.py             5 tests PASS
python3 scripts/validate_site.py                          PASS (204 models)
node scripts/test_browser_security.mjs                    PASS
python3 scripts/model_compass.py access                   PASS
python3 scripts/model_compass.py recommend-provider ...   PASS
```

The real Phase 2 GitHub refresh passed all workflow steps. Draft PR #6’s actual `Security and integrity checks` CI job completed successfully. The Cloudflare Pages preview check also passed.

Deterministic fixtures cover:

- RSC parsing and cached acquisition timestamps;
- provider endpoint normalization;
- source authority separation;
- coding-agent observation identity;
- confidence/missing evidence;
- provider and coding-agent query ordering;
- provider variant merge;
- material rich-history deltas;
- stale/offline behavior;
- existing public output/security contracts.

## 14. CI and workflow changes

`.github/workflows/ci.yml` now runs the observation tests in addition to the previous rich pipeline, decision, history, validation, syntax, and browser-security checks.

`.github/workflows/refresh.yml` now refreshes, after public exports:

1. bounded OpenRouter observations (`--max-endpoints 25`);
2. public Artificial Analysis coding-agent observations;
3. commits both artifacts with the normal generated-data commit.

The real Phase 2 branch workflow exercised these new steps successfully. Direct push to protected `main` was rejected because the local history contained a merge commit; no branch-protection bypass was attempted. The work is available in draft PR #6 for review.

## 15. Files and commits changed

Phase 2 implementation commit:

- `40555ad feat: add provider and coding agent intelligence`

The validation branch also contains the previously reviewed Phase 1 commits, linearly cherry-picked from the protected-main baseline:

- `d2a0e35` — pipeline hardening and decision engine
- `16480f3` — provider-variant preservation
- `63740a3` — prior improvement/audit reports
- `aecb519` — report formatting
- `8601b64` — honest cached freshness
- `40555ad` — provider and coding-agent intelligence

Live generated refresh commit on the validation branch:

- `92612ed data: weekly refresh 2026-08-23`

New/changed implementation files include:

- `scripts/aa/observations.py`
- `scripts/aa/openrouter_source.py`
- `scripts/aa/provider_query.py`
- `scripts/aa/coding_agent_source.py`
- `scripts/aa/decision.py`
- `scripts/aa/history.py`
- `scripts/model_compass.py`
- `scripts/aa/tests/test_observations.py`
- `scripts/aa/tests/fixtures/coding_agents_minimal.html`
- `.github/workflows/ci.yml`
- `.github/workflows/refresh.yml`
- `data/openrouter_observations.json`
- `data/coding_agent_observations.json`
- `data/history/rich/2026-08-23.delta.json`
- `README.md`
- `scripts/aa/README.md`

## Pre-Merge Corrections

The focused pre-merge review identified and corrected several issues without changing the Phase 2 architecture:

- **Coding-agent version:** `coding_agent_source.py` no longer hard-codes `1.4`. It derives the version from public methodology/description text and returns `null` when unavailable. The checked-in fixture proves that a page stating v1.3 produces `benchmark_version: "1.3"`. The current live page at refresh time stated v1.4, which is now captured as a derived value rather than an assumption.
- **Recommendation freshness:** the decision engine now centralizes freshness into `fresh`, `stale`, or `unknown`. Recommendation explanations and confidence use the same timestamp policy. Missing or malformed timestamps are `unknown`, not fresh.
- **Provider ranking:** interactive recommendations prioritize availability and latency; batch recommendations prioritize availability, throughput, then cost. Zero-valued prices and measurements remain valid values. Missing metrics and deterministic ties have explicit tests.
- **Provider identity:** observations now include a stable `(model_id, provider_id, endpoint_id)` identity key. OpenRouter's stable `tag` is preferred for provider identity, with normalized provider name as fallback.
- **OpenRouter sampling:** the adapter now sorts the catalog deterministically, rotates a persisted cursor cohort, retains recent observations for 14 days, records selected IDs/cursor/coverage, and commits the small sampling state. It no longer repeatedly queries the upstream catalog prefix.
- **Coding-agent coverage:** the artifact now explicitly reports `scope: partial_public_jsonld`, `complete_public_dataset: false`, dataset names, label coverage, and a note that richer page/network data may exist. The 27 observations are not presented as the complete public Coding Agent dataset.

The correction pass was committed as `142cf76 fix: correct phase 2 provider and freshness semantics`.

## 16. Current limitations

- Local access to `AA_API_KEY` was intentionally not created; authenticated validation was performed through GitHub Actions, where the configured secret remained hidden.
- OpenRouter endpoint expansion is bounded to 25 catalog models per refresh, yielding 63 endpoint observations in this run rather than a complete provider census.
- OpenRouter provider observations currently cover operational fields exposed by the endpoint API; privacy/retention fields are empty when not provided.
- The provider observation artifact is not yet joined automatically to canonical AA slugs because provider model IDs and AA slugs do not have a verified universal identity mapping.
- Coding-agent observations preserve public labels but cannot infer a stable base-model ID when the source does not expose one.
- The public coding-agent page currently supplies aggregate datasets; full per-task/per-benchmark/harness configuration data was not publicly present in the captured JSON-LD payload.
- Confidence is an evidence heuristic, not a statistical confidence interval.
- Source agreement remains `unknown` unless explicitly computed or supplied; the system does not pretend multiple sources agree merely because they contributed records.
- The current private access overlay has channel-level availability but no model-specific aliases or quota classifications.
- The production 403/Cloudflare 1010 remains an access-policy issue requiring Cloudflare-owner action.
- No new UI was added, intentionally.

## 17. Deferred ideas

- Complete OpenRouter endpoint census or adaptive endpoint sampling based on model importance.
- Formal cross-source identity mapping between AA model slugs, OpenRouter model IDs, and coding-agent labels.
- Provider-specific historical deltas and materiality rules beyond the current rich model delta.
- Full coding-agent component benchmark rows and model/harness joins if a legitimately public structured source exposes them.
- Uncertainty estimation using repeated measurements or source-level numeric agreement; current data does not justify fabricated intervals.
- Model-specific private access aliases and quota/marginal-cost classes after explicit local configuration is supplied.
- Provider and coding-agent UI views after the observation/query contracts have accumulated more real refreshes.
- Migration to SQLite/Parquet; current bounded JSON artifacts remain simpler and sufficient.

## 18. User action required

1. Review draft PR <https://github.com/OptiLabResearch/model-compass/pull/6>. It was created to exercise CI and was not merged automatically.
2. Decide whether the bounded 25-model OpenRouter endpoint sample is sufficient or whether a larger, rate-budgeted sample is desired.
3. If model-specific “available to me” recommendations are wanted, provide/maintain the private model/channel entries in `.model-compass-access.json`; do not add credentials.
4. Ask the Cloudflare owner to inspect the rule producing error 1010 for the VPS/source IP while preserving the current security controls.

## Final assessment

Phase 2’s core acceptance gate passed: the new code ran through a real authenticated refresh, generated fresh provenance-bearing model data, created a real rich-history delta, refreshed provider observations from OpenRouter, ingested public coding-agent observations, exposed structured queries, and passed the actual CI gate through a draft PR. The remaining work is primarily depth and identity quality—complete provider coverage, stable cross-source joins, richer coding-agent fields, and user-specific model aliases—not evidence that the foundation is untested.
