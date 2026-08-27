# AI Models Compass

AI Models Compass is a dependency-free static site for comparing recent language models using benchmark, pricing, speed, and latency data from [Artificial Analysis](https://artificialanalysis.ai/models).

Live site: [models.optiqo.dev](https://models.optiqo.dev)

## Clone and run locally

You need Python 3.12 or newer. The site itself has no package install or build step.

```bash
git clone https://github.com/OptiLabResearch/model-compass.git
cd model-compass
python3 -m http.server 8000 --directory public
```

Open [http://localhost:8000](http://localhost:8000). Opening `public/index.html` directly with `file://` will not work because the page fetches `data/models.json`.

Run the bounded repository check before submitting changes:

```bash
python3 scripts/check.py --scope auto
```

Use `python3 scripts/check.py --scope site` for a UI-only check and read
[`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) for the task matrix and other
focused scopes.

## Repository layout

- `public/` is the complete deployable site and the only directory that should be published.
- `public/data/models.json` is the browser's data source.
- `scripts/` contains dependency-free refresh, export, validation, and security checks.
- `data/enrichment_cache.json` is a transitional backfill input used by the orchestrator; it is not a canonical source.
- `data/history/` contains dated public CSV snapshots and bounded rich-dataset delta files.
- `data/openrouter_observations.json` contains bounded provider-endpoint observations.
- `data/coding_agent_observations.json` contains separate model+harness coding-agent observations.
- `data/endpoint_accuracy_observations.json` contains point-in-time Artificial Analysis endpoint measurements.
- `data/identity_mappings.json` contains generated cross-source mapping health; `data/identity_aliases.json` contains the small audited manual mapping set used to generate it.
- `.github/workflows/` contains read-only pull-request checks and the scheduled refresh.

## Project documentation

- [Project scope](docs/PROJECT.md)
- [Architecture and source authority](docs/ARCHITECTURE.md)
- [Current status](docs/STATUS.md)
- [Roadmap](docs/ROADMAP.md)
- [Development workflow and validation](docs/DEVELOPMENT.md)
- [Active plans and accepted reports](docs/plans/active/ and docs/reports/)
- [Pipeline operations](scripts/aa/README.md)

## Data refresh (maintainer-only)

The weekly workflow builds the rich dataset from the Artificial Analysis leaderboard RSC payload, the official Free API when `AA_API_KEY` is available, and the Oolong-Tea snapshot adapter. It validates the merged result, derives the public site JSON, writes dated public CSV/rich delta history, and commits only when data changed. Malformed payloads, duplicate slugs, unexpected URLs, implausible model-count drops, index-version changes, out-of-range values, and missing featured models fail closed. A fallback to an older dataset is explicitly reported as stale.

Refreshing locally is writeful and may use the network and an API key. Copy
`.env.example` to `.env`, add your own `AA_API_KEY`, restrict the file to your
user, and follow the operational commands in
[`scripts/aa/README.md`](scripts/aa/README.md). Do not run this sequence for a
normal code or documentation task.

```bash
chmod 600 .env
set -a; source .env; set +a
python3 -m scripts.aa.orchestrate
python3 scripts/build_site_from_aa.py
python3 scripts/export_history_csv.py
python3 scripts/export_benchmarks_json.py
python3 scripts/aa/openrouter_source.py --max-endpoints 25
python3 -m scripts.aa.endpoint_accuracy gpt-oss-120b
python3 -m scripts.aa.coding_agent_source
python3 -m scripts.aa.phase3_artifacts
python3 scripts/check.py --scope all
```

For deterministic parser work, use `python3 -m scripts.aa.orchestrate --offline` with cached payloads; it never attempts a network request. The retained `scripts/fetch_aa_models.py` is a compatibility path for reference/tests; the rich pipeline is the active site refresh path. Use `--as-of YYYY-MM-DD` on the public builder when replaying a historical rich dataset.

Never commit `.env` or paste API keys into issues, logs, screenshots, or pull requests.

The private decision interface also supports provider and coding-agent queries.
Agent-facing output is bounded by default; add `--full` only when complete
records are required and use `--compact` when piping JSON:

```bash
python3 scripts/model_compass.py recommend coding --limit 10 --compact
python3 scripts/model_compass.py providers openai/gpt-5
python3 scripts/model_compass.py recommend-provider openai/gpt-5 --profile interactive
python3 scripts/model_compass.py agents
python3 scripts/model_compass.py recommend-agent cost
python3 scripts/model_compass.py access
python3 scripts/model_compass.py endpoint-accuracy glm-5-2
python3 scripts/model_compass.py recommend-provider glm-5-2 --profile accuracy-first --require-accuracy-evidence
python3 scripts/model_compass.py identity-health
python3 scripts/model_compass.py unresolved-identities --limit 20
```

Use `python3 scripts/model_compass.py recommend coding --full` or
`unresolved-identities --full` only for an explicit record-level investigation.

Provider observations are operational facts from OpenRouter and do not overwrite Artificial Analysis benchmark fields. Coding-agent observations retain the public agent/harness label and are not flattened into base-model records.
Endpoint Accuracy observations are separate point-in-time measurements. Their source confidence intervals and classification are preserved; missing coverage is reported as `not_measured`, not as an accuracy failure. The public JSON-LD adapter is intentionally bounded to the audited Gate-D cohort in the weekly process. Endpoint Accuracy failures preserve the prior input artifact; any required-source or identity failure stops derived artifacts from being published.

Identity-aware recommendations require audited model and exact provider-endpoint mappings. Provider namespaces and display names are never fallback joins; variants such as DeepInfra Base and Turbo remain distinct.

## Deployment

Cloudflare Pages is configured by `wrangler.toml` to publish only `public/`. The repository root must never be used as a direct-upload directory because it can contain local credentials and maintenance files.

## Contributing and security

Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request. Report vulnerabilities privately according to [SECURITY.md](SECURITY.md), not in a public issue.

## License

The project source is available under the [MIT License](LICENSE). Artificial Analysis remains the source and owner of its benchmark data; review its terms before redistributing the dataset outside this project.
