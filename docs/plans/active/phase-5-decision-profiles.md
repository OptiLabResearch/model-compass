# Phase 5 Decision Profiles Plan

Status: active — implementation complete on 2026-08-27; acceptance is pending
independent Sol review on `feat/model-compass-phase5`.

## Durable scope

Phase 5 adds three explicit, explainable model recommendation profiles to the
dependency-free decision engine. It builds on the accepted Phase 4 source and
identity boundaries; it does not add providers, paid data, a gateway, or a
production routing service.

## Decision contract

- `best-overall` ranks models using the intelligence index with documented
  quality, speed, and blended 3:1 cost weights, while retaining metric,
  provenance, freshness, and confidence explanations.
- `available-to-me` uses the same evidence-backed ranking but admits a model
  only when the ignored local access overlay explicitly records boolean
  `available: true`. Missing or non-boolean availability remains unknown and
  is excluded.
- `marginal-cost-aware` requires a known blended 3:1 token cost and ranks each
  candidate by quality gained per additional dollar over the best cheaper
  candidate. The cheapest candidate uses a zero-quality baseline; equal and
  zero-cost cases remain finite and deterministic. Missing cost is excluded,
  never treated as zero.

All three profiles return stable profile/version metadata and expose the
calculation inputs in their explanations. Existing profiles retain their
current behavior unless a shared correctness fix is required.

## Acceptance criteria

1. The three named profiles are available through `DecisionEngine`, `AADB`, and
   the stable CLI without a new dependency or network call.
2. Availability filtering is explicit and fail-closed; access evidence is
   visible in the recommendation explanation.
3. Marginal-cost ranking uses only known numeric costs, handles free/equal-cost
   candidates without non-finite output, and reports baseline, quality gain,
   and cost delta.
4. Missing quality, cost, speed, provenance, and access values remain unknown;
   no score silently substitutes a missing metric with a factual zero.
5. Deterministic tests cover profile selection, access filtering, marginal
   ranking, tie behavior, missing values, explanation fields, and CLI exposure.
6. Documentation records the profile semantics and the full validation matrix
   passes before Phase 5 acceptance and independent review.

## Execution

1. Extend the profile registry and preserve profile-version metadata.
2. Add explicit access-state and marginal-cost scoring helpers with bounded
   explanations.
3. Add focused decision/CLI tests and update the public decision documentation.
4. Run full validation, review the final diff, obtain independent Sol review,
   and update this plan and `docs/STATUS.md` with accepted evidence.

## Implementation evidence

- Commit `20023c6` adds the three profiles to `DecisionEngine`, carries the
  contract through `AADB` and the stable CLI, and documents the access overlay
  and scoring semantics.
- Focused decision tests, CLI tests, Python compilation, and
  `python3 scripts/check.py --scope all` passed on 2026-08-27. The full matrix
  included pipeline, decision, observation, identity, deterministic replay,
  and generated-artifact comparison checks.
- `git diff --check origin/main...HEAD` passed, and bounded CLI smoke checks
  exercised all three profiles. Missing access remains fail-closed for
  `available-to-me`; missing marginal cost is excluded.
- Primary implementation review found no remaining local issue. An
  independent Sol review was attempted but the reviewer returned a platform
  usage-limit error before producing a verdict, so this plan remains active
  and Phase 5 is not yet marked accepted.
