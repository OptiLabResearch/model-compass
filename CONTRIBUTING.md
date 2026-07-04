# Contributing

Thanks for your interest in contributing to model-compass! Here's how to get started.

## Running Locally

The site is a static HTML + JSON project with no build step:

```bash
git clone https://github.com/your-username/model-compass.git
cd model-compass
python3 -m http.server 8000
# Visit http://localhost:8000
```

## Running the Scraper

The weekly model data refresh is automated via GitHub Actions, but you can run it manually:

```bash
python3 scripts/scrape_aa_models.py
# Outputs: data/models.json and a dated CSV in data/history/
```

The scraper fetches data from the Artificial Analysis free API (no auth required).

## Making Changes

- Open an issue first for big ideas or breaking changes
- Small fixes (typos, styling, data corrections) can be PRs directly
- Pages import data from `data/models.json` at load time — if you edit this file, changes are live immediately on a static server
- Test your changes locally before opening a PR

## Questions?

Check existing issues, or open a new one with your question. We're here to help.
