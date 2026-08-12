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

Run the repository checks before submitting changes:

```bash
python3 scripts/validate_site.py
node scripts/test_browser_security.mjs
```

## Repository layout

- `public/` is the complete deployable site and the only directory that should be published.
- `public/data/models.json` is the browser's data source.
- `scripts/` contains dependency-free refresh, export, validation, and security checks.
- `data/enrichment_cache.json` retains metrics unavailable through the official API.
- `data/history/` contains dated CSV snapshots for reproducibility.
- `.github/workflows/` contains read-only pull-request checks and the scheduled refresh.

## Data refresh

The weekly workflow fetches the documented Artificial Analysis Free API, enriches it from the public models page, validates the result, exports a dated CSV, and commits only when data changed. Malformed payloads, duplicate slugs, unexpected URLs, implausible model-count drops, index-version changes, out-of-range values, and missing featured models fail closed.

To refresh locally, copy `.env.example` to `.env`, add your own `AA_API_KEY`, restrict the file to your user, and run:

```bash
chmod 600 .env
set -a; source .env; set +a
python3 scripts/fetch_aa_models.py
python3 scripts/export_history_csv.py
python3 scripts/validate_site.py
```

Never commit `.env` or paste API keys into issues, logs, screenshots, or pull requests.

## Deployment

Cloudflare Pages is configured by `wrangler.toml` to publish only `public/`. The repository root must never be used as a direct-upload directory because it can contain local credentials and maintenance files.

## Contributing and security

Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request. Report vulnerabilities privately according to [SECURITY.md](SECURITY.md), not in a public issue.

## License

The project source is available under the [MIT License](LICENSE). Artificial Analysis remains the source and owner of its benchmark data; review its terms before redistributing the dataset outside this project.
