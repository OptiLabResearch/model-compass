# Phase 5 Decision-Profile Report

Status: implementation and review repairs complete 2026-08-27; acceptance
pending final independent Luna Max review. The implementation is committed as
`20023c6`, with repairs in `b511b11`, on `feat/model-compass-phase5`.

This report records the durable implementation and verification evidence for
the three explainable recommendation profiles. The active execution plan is
[`docs/plans/active/phase-5-decision-profiles.md`](../plans/active/phase-5-decision-profiles.md).

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
- Focused tests cover profile selection, access filtering and overlays,
  marginal details, unknown values, finite output, stable ties, and CLI
  exposure.

## Verification state

`python3 scripts/check.py --scope all` passed on 2026-08-27 at repair commit
`b511b11`, including Python syntax, CLI, public build/site contracts, pipeline,
decision, history, observation, identity, deterministic replay, and generated
artifact comparison checks. `git diff --check origin/main...HEAD` also passed.
The final documentation-only verification is recorded in the active plan.

Luna Max’s initial independent review found three findings covering non-finite
constraint values, non-finite recommendation fields, and negative prices. The
repairs and regression tests are in `b511b11`. A final independent Luna Max
review has been requested but has not yet issued a verdict, so this report
intentionally does not mark Phase 5 accepted; the remaining action is to
record that verdict, address any further findings, and then close the plan and
update `docs/STATUS.md`.
