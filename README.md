# Model Compass

Compare, shortlist, and pick LLMs — benchmark data from [Artificial Analysis](https://artificialanalysis.ai/models), updated weekly.

Three pages:
- **Picker** ([index.html](index.html)) — describe a task in plain language, get a model recommendation
- **Shortlist** ([shortlist.html](shortlist.html)) — a curated, filterable table of tracked models
- **All Models** ([models.html](models.html)) — the full benchmark table across every model tracked in the last 6 months

> Real README, screenshots, self-hosting instructions, and data-source attribution
> land in a later phase. This is a stub.

## Run locally

```
python3 -m http.server
```

Then open `http://localhost:8000/index.html`. Opening the files directly via
`file://` will not work — the pages `fetch()` their data, which requires a
same-origin HTTP server.
