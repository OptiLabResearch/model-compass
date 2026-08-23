# Model Compass Phase 3 Report

**Verified commit:** `b022d5188801203a78d56966b95c122037578754` on `feat/model-compass-phase3`.

**Status:** COMPLETE AS A BOUNDED PHASE 3 FOUNDATION — implementation correctness blockers from the independent review are resolved. Endpoint Accuracy and Coding Agents remain explicitly experimental/manual because public coverage is partial and rotating. PR #7 is **safe to merge as a Phase 3 foundation after the final PR checks pass**; it must not be merged until those checks are re-run on the final commit. Phase 4 was not started.

## Scope and decision

This phase covers bounded public observation adapters, auditable model/provider identity, identity-aware provider recommendation, history/health reporting, deterministic fixtures, and one audited live Gate-D join. It does not promote partial sources into the weekly refresh, scrape rendered charts, bypass access controls, or infer verified identity from names.

## 1. Endpoint Accuracy ingestion

`scripts/aa/endpoint_accuracy.py` now supports a bounded list of model slugs (`model_slug [model_slug ...]`) instead of overwriting the output for one model.

The merge artifact records:

- requested, successful, and retained-stale model counts;
- endpoint and model coverage;
- per-model error type, message, and attempt time;
- source/parser provenance for each observation;
- bounded retention of recent successful model results (`--retention-days`, default 14);
- `partial` status when errors or retained stale data exist;
- source classification separately from `derived_classification`.

The current checked-in live artifact requested three models: `glm-5-2`, `gpt-oss-120b`, and `deepseek-v4-pro`. Two succeeded, one returned the explicit error `Endpoint Accuracy JSON-LD dataset not found`, and the artifact contains 30 endpoint observations across two models. No failed model silently erased prior data.

When source classification is absent, derived interpretation is now:

- interval spanning 100: `reference_consistent`;
- upper bound below 100: `below_reference`;
- lower bound above 100: `above_reference`.

The derived value is never substituted for the source-supplied classification.

## 2. Public structured-source investigation

I rechecked ordinary public HTML plus Next.js Flight/RSC payload markers for:

- `https://artificialanalysis.ai/models/gpt-oss-120b/providers`;
- `https://artificialanalysis.ai/agents/coding-agents`.

The provider page contains public Flight/RSC payloads and `endpointAccuracyIndex` data, but the stable, directly parseable Endpoint Accuracy dataset remains the JSON-LD adapter used here. The coding-agent page also contains Flight/RSC markers and rendered metric labels, including `Coding Agent Index` and agent wall-time fields, but no sufficiently stable, documented public structured contract was found that would justify a new brittle parser in this phase. No access controls were bypassed and no chart/HTML scraping was added. The adapters therefore remain manual/experimental with the limitation explicitly reported.

## 3. Identity health semantics

`identity.py` now deduplicates OpenRouter observations into unique model and provider entities before resolution. Health separates:

- AA model count;
- OpenRouter unique model count and endpoint observation count;
- AA and OpenRouter provider counts;
- unique unresolved model IDs;
- model mappings by verified/manual/candidate;
- provider mappings by verified/manual/candidate;
- unresolved model/provider counts;
- ambiguity and conflicts.

Current artifact counts:

- AA models: 618;
- OpenRouter unique models: 139;
- OpenRouter endpoint observations: 465;
- AA providers represented by Endpoint Accuracy: 21;
- OpenRouter provider namespaces: 63;
- model mappings: 0 verified, 1 manual, 9 candidate;
- provider mappings: 0 verified, 2 manual;
- unresolved model entities: 56;
- unresolved provider entities: 61;
- ambiguous mappings: 73;
- conflicts: 0.

Candidate generation uses structured evidence (namespace/creator agreement, model portion after `/`, normalized version/name equality, and source-exposed IDs). Candidates are explicitly non-authoritative and are rejected by identity-aware recommendation paths.

## 4. Provider identity and ProviderDB/CLI wiring

Provider relationships use the same explicit manual/candidate/unresolved/conflict model as model relationships. Provider namespaces are separated from endpoint variants such as `coreweave/fp4` and `deepinfra/turbo`; no silent fuzzy provider join is performed.

`ProviderDB` now consumes only verified/manual model and provider mappings when an identity artifact is supplied. Candidate and unresolved mappings are treated as missing evidence. Recommendation explanations expose both mapping records and their evidence, as well as the Endpoint Accuracy observation and derived classification.

The CLI now wires `--identity-data` into both `providers` and `recommend-provider`.

## 5. Gate-D live evidence

A real audited join is recorded for:

- AA model `gpt-oss-120b`;
- OpenRouter model `openai/gpt-oss-120b`;
- AA provider `coreweave`;
- OpenRouter provider namespace `coreweave`.

Evidence is preserved in `data/identity_aliases.json`: the AA rich model record exposes `raw_fields.openrouter_api_id: openai/gpt-oss-120b`, the public OpenRouter catalog exposes the same model ID, and the public endpoint/provider names agree for CoreWeave. These are manual audited aliases, not fabricated automatic certainty.

The real CLI acceptance command was:

```text
python3 scripts/model_compass.py recommend-provider gpt-oss-120b --profile accuracy-first --require-accuracy-evidence
```

It returned the OpenRouter `openai/gpt-oss-120b` CoreWeave endpoint and combined it with the AA Endpoint Accuracy observation (`mid 97.63`, interval `90.53–104.73`, derived `reference_consistent`, status `measured_good`). The explanation included both the model and provider alias evidence. This is a real Gate-D provider recommendation combining OpenRouter operational data with AA Endpoint Accuracy.

## 6. Deterministic tests and acceptance

Added/updated deterministic coverage for bounded multi-model merge, per-model errors, retention, absent-source interval classification, entity deduplication, provider identity, candidate evidence, strict mapping consumption, and Gate-D explanation evidence.

Executed successfully:

```text
python3 -m compileall -q scripts
python3 scripts/aa/tests/test_phase3_observations.py
python3 scripts/aa/tests/test_observations.py
python3 scripts/aa/tests/test_history.py
python3 scripts/aa/tests/test_decision_engine.py
python3 scripts/aa/tests/test_pipeline.py
python3 scripts/validate_site.py
node scripts/test_browser_security.mjs
python3 scripts/model_compass.py identity-health
python3 scripts/model_compass.py recommend-provider gpt-oss-120b --profile accuracy-first --require-accuracy-evidence
```

All returned exit code 0. The public validator reported 204 models and the browser security helpers passed.

## 7. Gate summary

- **Gate A — Endpoint Accuracy:** PASS for bounded reproducible multi-model ingestion, explicit partial coverage, errors, retention, provenance, and interval interpretation. Source coverage remains partial/manual.
- **Gate B — Coding Agents:** ACCEPTED WITH SOURCE LIMITATION. Existing rich structured adapter remains separate and deterministic; no stable richer public contract justified a brittle expansion.
- **Gate C — Identity health:** PASS. Model/provider counts and states are separated; candidates never become verified truth automatically.
- **Gate D — Unified recommendation:** PASS for the audited `gpt-oss-120b`/`openai/gpt-oss-120b` + CoreWeave join. Recommendation is fail-closed for candidate/unresolved identities.

## 8. Limitations and future expansion

Acceptable source limitations for this experimental phase:

- public JSON-LD exposes fewer Endpoint Accuracy rows than some rendered pages;
- coverage rotates and one requested model currently lacks the expected dataset;
- Coding-Agent public Flight/RSC data is richer than the stable adapter contract, but not sufficiently stable/documented for a new parser;
- component values, dates, repeat counts, and token telemetry remain absent where the source does not expose them.

Deferred opportunities, not current blockers:

- expand the bounded model cohort;
- add a stable public structured contract if Artificial Analysis documents or exposes one;
- grow the audited alias set through independent public evidence;
- consider weekly refresh promotion only after source stability and coverage policy are approved.

## 9. Merge decision

**PR #7 is now safe to merge as a Phase 3 foundation, assuming the final pushed commit has green required checks and remains mergeable.** The remaining partial upstream source coverage is documented and intentionally fail-closed; it is not an implementation correctness blocker. Do not merge automatically in this task.
