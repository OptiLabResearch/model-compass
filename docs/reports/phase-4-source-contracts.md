# Phase 4 Source-Contract Report

Status: accepted 2026-08-27. The implementation was synchronized with
`origin/main`, passed the full local matrix, and received an independent Sol
re-review with no remaining findings. The focused repair is committed as
`2f35ee4`.

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

## Final identity repairs

- A verified OpenRouter model mapping requires the exact
  `official_api`/`openrouter_api_id`/`authoritative` evidence tuple. Snapshot,
  RSC, malformed, and otherwise candidate-labeled evidence cannot promote a
  mapping.
- Official evidence that conflicts with candidate metadata produces an
  explicit conflict and no model mapping, preserving the recommendation
  fail-closed boundary.
- Identity health now reports mapping, ambiguity, and combined resolution
  method counts. The generated artifact records 56 unique metadata mappings and
  24 metadata ambiguities, reconciling to 80 exact metadata matches.

## Verification state

The Phase 4 branch is based on current `origin/main` (the remote main tip is an
ancestor), and the final diff is whitespace-clean. `python3 scripts/check.py
--scope all` passed on 2026-08-27, including identity contracts, variant-safe
observation checks, deterministic Phase 3 replay, and byte-for-byte generated
artifact comparison. The first independent Sol review found the authority and
health gaps above; after repair, a fresh Sol re-review accepted commit
`2f35ee4` with no Critical, High, Medium, or Low findings.
