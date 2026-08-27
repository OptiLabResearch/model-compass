# Scripts scope

`scripts/` contains dependency-free adapters, exports, validators, tests, and
the agent-facing CLI. Read only the entrypoint and directly imported module
needed for the task; use `docs/DEVELOPMENT.md` for the check scope.

`model_compass.py` is a diagnostic interface: default output is bounded and
`--full` is an explicit opt-in to complete records. Prefer `--limit` and
`--compact` when sending results to an agent. `check.py` captures child output,
uses temporary paths for deterministic replay, and is the canonical validation
entrypoint.

The rich pipeline under `scripts/aa/` is active. `fetch_aa_models.py` is a
compatibility path and should be changed only when its compatibility tests or
the legacy workflow require it. Do not invoke live/network adapters merely to
answer a source or code question; use offline fixtures and checked-in outputs.
