# Development workflow and agent context

This is the canonical task-routing and validation guide. Start with the
smallest row that covers the task, then expand only when a check or source
failure requires it.

## Task routing

| Task | Read first | Normal validation | Avoid by default |
|---|---|---|---|
| UI, browser, or CSP | root `AGENTS.md`, the touched asset, relevant public contract | `python3 scripts/check.py --scope site` | all of `public/data/` |
| CLI or recommendation behavior | `scripts/AGENTS.md`, `scripts/model_compass.py`, focused tests | `python3 scripts/check.py --scope decision` and `python3 scripts/test_model_compass.py` | full rich model JSON and raw fields |
| RSC, source, or normalization code | `scripts/aa/AGENTS.md`, `scripts/aa/README.md`, touched adapter/test | `python3 scripts/check.py --scope pipeline` or `--scope all` | live acquisition and `data/aa_cache/` |
| Provider, agent, endpoint, or identity observations | `scripts/aa/AGENTS.md`, relevant observation/query module, focused contract test | `python3 scripts/check.py --scope observations` or `--scope identity` | unrelated observation domains |
| Generated data or refresh | `data/AGENTS.md`, `docs/STATUS.md`, active plan, pipeline README | `python3 scripts/check.py --scope all` after generation | editing generated output by hand |
| Documentation or workflow | `docs/AGENTS.md`, `docs/PROJECT.md`, relevant current document | `python3 scripts/check.py --scope auto` | archived reports and duplicated command catalogs |

For roadmap work, read `docs/STATUS.md` and the applicable file in
`docs/plans/active/` before the roadmap. Read the nearest `AGENTS.md`; nested
guidance narrows the root agreements.

## Validation scopes

The dependency-free `scripts/check.py` captures child output and prints one
line per successful check. It never performs network acquisition and uses
temporary paths for deterministic Phase 3 replay.

| Scope | Use for |
|---|---|
| `quick` | site validation, JavaScript syntax, browser security |
| `site` | public build plus `quick` |
| `legacy` | compatibility adapter tests |
| `cache` | cache-pruning tests |
| `pipeline` | RSC/parser/merge tests |
| `decision` | decision-engine tests |
| `history` | history delta/retention tests |
| `observations` | provider/agent observations and Phase 3 observation tests |
| `identity` | source-qualified identity contract tests |
| `all` | syntax, CLI, compatibility, site, data, and all focused tests |
| `auto` | conservative selection based on changed paths |

Use `python3 scripts/check.py --scope auto` for normal work. `auto` selects
`quick` for documentation-only changes, `site` for non-data public changes,
and `all` for source, data, workflow, unknown, or no detected changes. CI uses
the same entrypoint. Use `--verbose` only when a failing or surprising check
needs its captured output.

The script-style tests support bounded selection without installing pytest:

```bash
python3 scripts/aa/tests/test_pipeline.py --list
python3 scripts/aa/tests/test_pipeline.py --test test_rsc_extract_normalize_roundtrip
python3 scripts/aa/tests/test_identity_contracts.py --test test_merge_preserves_source_qualified_evidence
```

## Output and command safety

`model_compass.py` returns decision-relevant summaries by default. Use
`--limit N` and `--compact` for agent-facing output; use `--full` only when a
complete record is needed. Identity diagnostics return counts and samples by
default. Missing metrics and unresolved mappings remain explicit.

Read-only checks include `validate_site.py`, the query CLI, and the bounded
check scopes. Builders, exporters, Phase 3 generation, pruning, and refresh
commands can write artifacts. The orchestrator, cross-validator, OpenRouter,
Endpoint Accuracy, and coding-agent commands can also use the network or
credentials. Run those only for an explicitly requested refresh or source
investigation. For replay work, pass output paths under a temporary directory
where the command supports them; never make a no-op generated refresh just to
inspect a file.

Do not paste raw payloads, `.env` content, credentials, or unbounded command
logs into agent context. Summarize failures and retain only the relevant
head/tail when a complete log is required for diagnosis.

## Efficiency measurement

The repository has no agent token, reasoning, latency, cost, or prompt-cache
telemetry. Treat those values as unknown until the agent platform records them.
For before/after comparisons, use the same task fixtures and record per task:

- input, output, and reasoning tokens, plus cache hits, from the agent platform;
- tool-call count, command count, repeated reads/searches, and wall-clock latency;
- check scope, pass/fail result, retries, and task completion rate; and
- estimated cost from the platform's model pricing and actual token counts.

Compare medians and failure-adjusted completion rate across multiple equivalent
tasks. The local check runner is intentionally quiet so its output bytes and
elapsed time can be measured without mixing raw child logs into the agent
conversation. Do not turn an observed reduction in repository bytes into a
token-savings claim without agent traces.
