# Phase 4 Source Contracts Plan

Status: completed and accepted 2026-08-27. The final focused repair is
`2f35ee4`; see the durable report for review evidence.

## Durable report

See [`docs/reports/phase-4-source-contracts.md`](../../reports/phase-4-source-contracts.md) for the current source-contract and implementation evidence record.

## Objective

Strengthen upstream source boundaries and increase auditable identity diagnostics without weakening Phase 3's fail-closed recommendation policy or requiring a paid service tier.

## Verified evidence

- The documented AA Free endpoint `/api/v2/language/models/free` is already used. It provides stable AA identity and headline metrics but omits `openrouter_api_id` and provider detail.
- AA documents `openrouter_api_id` as Pro-only and per-provider model data/provider endpoints as Commercial-only. Replacing the rich RSC or provider extraction with those contracts would require paid access.
- OpenRouter documents `/api/v1/models`, permanent `canonical_slug`, variant-aware model lookup, provider listing, and per-model endpoint links; the existing adapter uses that public operational contract.
- The current AA merged artifact has 309 third-party snapshot `openrouter_api_id` values (231 distinct). Against the observed OpenRouter cohort, 80 IDs match: 57 identify one AA slug and 23 collide across variants (105 AA rows total).
- `hostApiId` is provider/runtime metadata, not an OpenRouter identifier. Its exact overlap is corroborating candidate evidence only.

## Acceptance criteria

1. Durable architecture/reporting states the access tier, authority, stability, and configured role of each upstream contract.
2. Identity resolution records exact third-party snapshot/OpenRouter ID matches as source-qualified candidates only.
3. One-to-many metadata matches are ambiguous and enumerate every AA variant; conflicting metadata cannot become verified truth.
4. Official-AA `openrouter_api_id`, if a future approved Pro payload supplies it, is preserved as separately sourced evidence; no paid endpoint is enabled in this phase.
5. Candidate metadata never enables identity-aware provider recommendations.
6. Identity artifact health exposes evidence-method counts and agrees with mappings/ambiguities.
7. Deterministic tests cover unique metadata, variant collision, missing/conflicting evidence, source provenance, candidate rejection, and artifact reproduction.
8. Full CI, final diff review, `origin/main` synchronization, and independent Sol review pass before acceptance.

## Execution

1. Preserve normalized source-qualified identity evidence through adapter merge.
2. Teach identity resolution to distinguish authoritative official evidence from third-party/provider-host candidates and collisions.
3. Add health/report invariants and deterministic tests; regenerate derived artifacts.
4. Record the upstream contract evaluation and paid-tier conclusion.
5. Run full verification and independent review, repair findings, update durable state, and archive this plan after acceptance.
