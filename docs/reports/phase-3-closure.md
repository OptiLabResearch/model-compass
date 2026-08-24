# Phase 3 Closure Report

Status: independent engineering gate passed on `8cb0105`; final remote PR checks are pending.

## Outcome

Phase 3 now has a reproducible weekly vertical slice joining OpenRouter operational evidence to Artificial Analysis Endpoint Accuracy through audited exact identities. Model mappings and provider-endpoint mappings must be `verified` or `manual`; raw IDs, provider namespaces, display names, and candidates are never authoritative fallbacks.

The Endpoint Accuracy parser gives DeepInfra Base and Turbo distinct identities. The audited Turbo mapping resolves only to its actual 84.4 below-reference observation. The strict accuracy-first Gate-D result is CoreWeave `coreweave/fp4`, backed by the AA 97.63 observation and both mapping records. Removing the CoreWeave endpoint mapping returns no recommendation.

## Reproduction

The normal acquisition/build sequence is:

```text
python3 scripts/aa/openrouter_source.py --max-endpoints 25
python3 -m scripts.aa.endpoint_accuracy gpt-oss-120b
python3 -m scripts.aa.coding_agent_source
python3 -m scripts.aa.phase3_artifacts
python3 scripts/model_compass.py recommend-provider gpt-oss-120b --profile accuracy-first --require-accuracy-evidence
```

The weekly workflow runs this sequence after the canonical AA/site build. Gate-model acquisition must be current and error-free; otherwise generation fails without publishing a misleading derived artifact. CI regenerates identity/summary artifacts and rejects a diff.

## Candidate artifact evidence

- 618 canonical AA models.
- 621 OpenRouter endpoint observations across 185 model IDs.
- 30 Endpoint Accuracy observations with 30 unique identities across two retained models, index v1.0.
- 2 audited exact endpoint mappings; 619 unmapped operational endpoints remain explicitly unresolved.
- Coding Agent Index v1.4: 9 distinct harness/model/configuration variants.
- Gate D: `gpt-oss-120b` → `openai/gpt-oss-120b` → `coreweave/fp4`; Endpoint Accuracy 97.63, 95% interval 90.53–104.73, `reference_consistent`.

## Verification

The synchronized candidate tip is based on `origin/main` `1fbd925`. The complete repository CI command set passed locally after live acquisition and deterministic regeneration. Regression coverage includes missing model/endpoint mappings, candidate rejection, Base/Turbo collision, Turbo evidence, CoreWeave removal, both source acquisition failures, artifact reproduction/count/version invariants, mixed-version history, and the checked-in real Gate-D explanation.

An independent Sol review of the first synchronized tip found workflow ordering, retained OpenRouter Gate evidence, mixed-version history, stale documentation, and a timestamp-boundary freshness bug. Two repair/review cycles followed. The final immutable `8cb0105` review passed with no substantive correctness blocker; pushed PR checks remain before formal acceptance.
