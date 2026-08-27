# Phase 4 Source-Contract Report

Status: implementation evidence recorded; Phase 4 acceptance remains open.

This report records the source-authority and identity decisions that govern the
current implementation. It is the durable evidence companion to
[`docs/plans/active/phase-4-source-contracts.md`](../plans/active/phase-4-source-contracts.md).

## Source contracts

| Domain | Access tier | Configured role | Authority boundary | Stability risk |
|---|---|---|---|---|
| AA leaderboard RSC | Public | Primary rich model source | Authoritative for fields present in the payload | Undocumented frontend payload; parser drift is fail-visible |
| AA Free API | Optional `AA_API_KEY` | Baseline IDs, headline fields, and index validation | Authoritative for those fields when supplied | Tier/field availability can change; no paid endpoint is assumed |
| Oolong snapshot | Public | Fallback and cross-check | Candidate evidence and coverage support; does not override AA fields | Third-party schema and freshness |
| OpenRouter API | Public | Endpoint operations | Authoritative only for OpenRouter endpoint availability, pricing, performance, and capabilities | Catalog and endpoint details change over time |
| AA Endpoint Accuracy pages | Public | Bounded Gate-D observations | Authoritative for captured point-in-time measurements | Page/JSON-LD structure and cohort coverage can drift |
| AA coding-agent pages | Public | Harness/model/configuration observations | Not canonical base-model facts | Page schema and benchmark variants can change |

The documented AA `openrouter_api_id` field is Pro-only and provider detail is
Commercial-only. No paid source was enabled. The public RSC and snapshot
adapters therefore preserve source-qualified evidence without promoting it to
authoritative identity.

## Identity decisions

- Exact snapshot `openrouter_api_id` matches against observed OpenRouter IDs are
  recorded as third-party candidate evidence.
- A candidate match never enables identity-aware provider recommendations.
- One-to-many matches enumerate every possible AA model variant and remain
  ambiguous; conflicting evidence is not coerced into a verified mapping.
- Official-AA identity evidence, if an explicitly approved future Pro payload
  supplies it, must remain separately sourced and must not be conflated with
  snapshot evidence.
- Provider identity retains endpoint variants whenever variants can carry
  different accuracy evidence.
- Only explicit `verified` or audited `manual` mappings are authoritative for
  recommendation joins. Candidates, ambiguities, conflicts, and unresolved
  joins are diagnostics.

## Implemented safeguards

- `scripts/public_contract.py` centralizes public slug/URL rules, featured
  coverage, numeric bounds, and model-count-drop protection.
- The rich builder, compatibility builder, and public validator use the same
  contract.
- `scripts/build_site_from_aa.py --as-of YYYY-MM-DD` makes release-window
  selection and output metadata reproducible from a fixed rich input.
- CI replays the checked-in rich dataset through the public builder, validates
  the resulting model count/timestamp/date, and exercises cache-pruning safety.
- Raw timestamped debug dumps remain ignored and can be pruned only through the
  dry-run-first `scripts/prune_aa_cache.py` utility; reusable keyed/latest caches
  are outside its deletion pattern.

## Verification state

The current branch retains the previously generated Phase 3 identity artifacts
and adds the shared public contract, deterministic builder replay, archive
hygiene, and workflow date pinning. Full CI, final diff review, synchronization
with current `origin/main`, and independent Sol review are still required before
Phase 4 can be marked accepted.
