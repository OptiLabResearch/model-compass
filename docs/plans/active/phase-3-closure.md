# Phase 3 Closure Plan

## Objective

Repair draft PR #7 so a normal documented process produces a reproducible, fail-closed Gate-D vertical slice without provider-variant collisions.

## Verified starting evidence

- `origin/main` is `1fbd925`; PR head `5c02936` is one commit behind and GitHub reports conflicts.
- Baseline CI commands pass on the PR head.
- AA Endpoint Accuracy contains separate `DeepInfra` and `DeepInfra (Turbo)` rows but the parser assigns both `gpt-oss-120b:deepinfra:/providers/deepinfra`.
- OpenRouter retains separate `deepinfra/bf16` and `deepinfra/turbo` endpoint variants.
- `ProviderDB.providers()` falls back to the requested raw model ID when an identity document exists but lacks an authoritative model mapping.
- Identity and summary artifacts have no single repository generation command, and `data/phase3_summary.json` disagrees with `data/identity_mappings.json`.
- Observation history reads top-level `benchmark_version`, while Endpoint Accuracy artifacts expose per-observation `index_version` and a null top-level value after merge.

## Acceptance criteria

1. Endpoint identities distinguish evidence-bearing provider variants; DeepInfra Base and Turbo cannot collide or inherit one another's observations.
2. With identity data enabled, model and provider joins require verified/manual mappings at the exact required granularity; candidates and raw ID/name fallback are rejected.
3. Removing the required CoreWeave mapping makes strict Gate-D recommendation return no result.
4. DeepInfra Turbo receives its actual below-reference observation only through an explicit audited variant mapping, or remains unmapped.
5. One documented deterministic command regenerates Phase 3 derived artifacts from checked-in inputs; acquisition errors fail closed and do not publish misleading artifacts.
6. Artifact versions, counts, coverage, identity health, and summaries agree and are validated by tests.
7. History detects actual benchmark/index version changes in generated artifacts and does not compare incompatible scores as ordinary changes.
8. Deterministic tests cover missing mappings, candidate rejection, variant collisions, acquisition failure, artifact reproducibility, and the checked-in Gate-D explanation.
9. Full CI, phase-specific integration checks, and a bounded live acquisition smoke pass on a tip synchronized with `origin/main`.
10. An independent Sol review finds no substantive correctness blocker; final status/report/PR claims match the implementation.

## Execution

1. Add failing regression tests around exact identity granularity, strict joins, artifact invariants, acquisition failure, history metadata, and Gate D.
2. Refine Endpoint Accuracy identity extraction and the identity mapping schema without broad rewrites.
3. Make `ProviderDB` fail closed whenever an identity artifact is configured and join only through exact authoritative mappings.
4. Add one deterministic Phase 3 artifact builder/validator and wire the documented acquisition/build path.
5. Regenerate artifacts, run deterministic and live checks, then synchronize with `origin/main`.
6. Obtain independent review, repair findings, repeat checks, align durable status/reporting, and archive this plan only after acceptance.
