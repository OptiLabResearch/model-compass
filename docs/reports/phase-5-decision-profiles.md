# Phase 5 Decision-Profile Report

Status: accepted 2026-08-27. The implementation is committed as `20023c6`,
with review repairs in `b511b11` and final numeric hardening in `6c8aab9`, on
`feat/model-compass-phase5`.

This report records the durable implementation and verification evidence for
the three explainable recommendation profiles. The completed execution plan is
[`docs/plans/completed/phase-5-decision-profiles.md`](../plans/completed/phase-5-decision-profiles.md).

## Profile contract

| Profile | Selection rule | Safety boundary |
|---|---|---|
| `best-overall` | Intelligence-index ranking with documented quality, speed, and blended-cost weights | Known metrics are weighted and missing metrics remain unknown; explanations retain provenance, freshness, and confidence |
| `available-to-me` | The `best-overall` ranking restricted to an ignored local overlay with explicit boolean `available: true` | Missing or non-boolean access is unknown and excluded; access evidence is returned in each explanation |
| `marginal-cost-aware` | Quality gained per additional dollar over the best cheaper candidate, using known blended 3:1 token cost | Missing costs are excluded; zero/equal-cost and tie cases remain finite and deterministic with baseline and delta details |

The profiles expose stable version and strategy metadata through the decision
engine, `AADB`, and the CLI. The implementation does not add a dependency,
network call, paid source, gateway, or router.

## Implemented safeguards

- The profile registry uses an explicit rich profile version and preserves the
  existing profile behavior and version contract.
- Availability is modeled as `available`, `unavailable`, or `unknown`; only
  explicit booleans can affect admission.
- Marginal scoring reports baseline slug/metrics, quality gain, cost delta, and
  quality per cost delta. Non-finite values cannot enter the result JSON.
- Weighted scoring renormalizes over known metrics rather than treating a
  missing cost or speed value as a factual zero.
- Numeric inputs are fail-closed for oversized integers, non-finite/overflowed
  derived costs, negative prices, non-positive performance values, and
  out-of-domain index values; direct explanations are JSON-safe as well.
- Focused tests cover profile selection, access filtering and overlays,
  marginal details, unknown values, finite output, stable ties, and CLI
  exposure.

## Verification state

`python3 scripts/check.py --scope all` passed on 2026-08-27 at final repair
commit `6c8aab9`, including Python syntax, CLI, public build/site contracts,
pipeline, decision, history, observation, identity, deterministic replay, and
generated artifact comparison checks. `git diff --check origin/main...HEAD`
also passed.

Luna Max’s initial independent review found three findings covering non-finite
constraint values, non-finite recommendation fields, and negative prices. The
repairs and regression tests are in `b511b11`. The final independent review
identified four additional numeric-boundary cases; they are repaired with
regression tests in `6c8aab9`. The final Luna Max re-review returned PASS with
no remaining Phase 5 acceptance blockers.
