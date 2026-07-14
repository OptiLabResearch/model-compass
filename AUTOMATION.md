# Automation plan

What runs by itself today, what still needs a human, and what to build next — ordered
by (impact ÷ effort), not by how interesting it is.

## Where things stand

| Concern | Status |
| --- | --- |
| Weekly data refresh | Automated (`.github/workflows/refresh.yml`, Sundays 19:00 UTC) |
| Refresh failure is visible | Automated — job fails loudly and opens a `data-refresh` issue |
| Deploy | Automated — Cloudflare Pages builds on push to `main` |
| Stale-data warning in the UI | Automated — banner after 8 days (`assets/nav.js`) |
| Rich-metric loss when AA drops a model | Automated — `data/enrichment_cache.json` carries values forward |
| Featured model renamed upstream | Automated — hard build failure, not a silent drop |
| Picker recommendations | Automated — `/api/recommend` (Groq), with formula fallback |
| **Shortlist curation** | **Manual** — `FEATURED_SLUGS` is hand-edited |
| **Recommendation quality** | **Unverified** — no tests; a prompt regression ships silently |
| **Page-scrape breakage** | **Semi-manual** — degrades gracefully but nobody is told |
| **Cache staleness** | **Unbounded** — a cached value can age forever |

The honest summary: the *pipeline* is now well automated, the *judgment* is not. Everything
below is about closing that gap.

---

## 1. Tell someone when the enrichment scrape breaks — 30 min

The single most likely future failure. AA now ships its full dataset encrypted and is
actively locking the page down; the `initialModels` payload we parse will disappear. When it
does, the build **still succeeds** on API data alone — by design — but the picker quietly
loses non-hallucination on new models and nobody finds out for months.

`fetch_aa_models.py` already prints a warning and tracks `coverage.with_rich_metrics`. Make
the workflow act on it:

- Fail the job (or open an issue) if `with_rich_metrics` drops below, say, 20 models, or if
  it falls by more than 25% week over week.
- Same treatment if `featured_without_rich_metrics` grows.

This is a few lines in the workflow reading `data/models.json`. Do this first.

## 2. A regression suite for the recommender — half a day

Right now a prompt edit, a Groq model swap, or an AA schema change can silently make the
picker worse, and the only detection mechanism is you noticing a bad answer. Two layers:

**Golden tasks (no LLM, runs on every PR).** A JSON file of ~20 tasks with assertions about
the *gates*, not the pick — those are deterministic and must never regress:

```
{ "task": "nightly cron, nobody reviews it",
  "expect_scenarios": ["unattended"],
  "expect_all_candidates_pass": { "non_halluc": 70 } }
```

Assert on the outputs of `classifyTask` / `pickForTask` (extract them from `index.html`
into a small `assets/picker-core.js` first — a prerequisite worth doing anyway, since it also
lets the Function and the page share one definition of the gates instead of two).

Both bugs found while building this — the `0`-means-unmeasured TTFT sentinel and the dead
`scenarios.voice` gate — would have been caught by this suite on day one.

**LLM smoke test (nightly, not per-PR).** Fire ~10 real tasks at `/api/recommend`, assert the
response validates, the pick is in-shortlist, and the gates hold. Costs pennies; catches
"Groq deprecated the model" before a user does.

## 3. Auto-propose shortlist changes — half a day

`FEATURED_SLUGS` is the last hand-maintained thing in the data path, and it decays: a strong
new model isn't picked up until you notice it, and there's no prompt to reconsider.

Don't auto-curate — *auto-nominate*. A weekly job (right after the refresh) that opens a PR
when any non-featured model would rank top-3 for a task type under `TASK_WEIGHTS`, or beats a
featured model on the metric that model was presumably featured *for*:

> **Shortlist suggestions — 2026-07-19**
> - `+ qwen3-8-max` — would rank #2 for `coding` (terminalbench 81.2 vs featured median 68.4)
> - `− mimo-v2-5-0424` — now #14 of 18 on every task type; superseded by `mimo-v2-5-pro`
> - `! claude-sonnet-4-6-adaptive` — no longer rendered by AA; running on cached metrics
>   from 2026-07-05 (10 weeks old)

You review and merge. Keeps editorial control, removes the "I forgot to look" failure mode.

## 4. Bound the cache staleness — 1 hour

`enrichment_cache.json` will happily serve a value observed a year ago. Benchmark scores for a
frozen checkpoint mostly don't drift, but AA *does* re-run evals and revise numbers.

- Add `rich_as_of` (already written per-entry) to the UI: any model whose gate-relevant
  metrics come from cache older than ~60 days gets a small "metrics from {date}" note in the
  shortlist and picker.
- Warn in the refresh job when a **featured** model's cached data passes 90 days.
- Never expire silently. A stale number that's labelled is fine; an unlabelled one is not.

## 5. Recommender capacity — 1 hour (or $0)

Groq's free tier meters ~8k tokens/minute *per model* and one recommendation costs 5–6k, so
the site supports roughly one pick per minute per model. The function already walks a chain
(`gpt-oss-120b` → `gpt-oss-20b` → `llama-3.3-70b`), giving ~3/min, and degrades to the
formula beyond that.

That's fine for personal use and thin for public traffic. Options, cheapest first:

- **Cache identical tasks** in Workers KV, keyed by `hash(task + models.json scraped_at)`.
  Free, and the example-chip tasks (which are what most visitors click) become instant.
- **Trim the prompt further** — the system prompt is ~1.1k tokens and could halve.
- **Upgrade the Groq tier** — removes the ceiling entirely; the real fix if the site gets
  traffic.

## 6. Trend tracking — 1 day, high user value

`data/history/*.csv` has been accumulating weekly snapshots since June and **nothing reads
it**. That's a whole product sitting unused. A diff job could generate, automatically:

- price cuts and hikes ("DeepSeek V4 Pro output: $1.20 → $0.80")
- new entrants to the shortlist, models newly gated out
- score movements when AA re-runs an eval
- a "What changed this week" section on the homepage, written from the diff

This is the highest-value *new* thing on the list. Everything else protects what exists; this
adds something. It's last only because nothing breaks without it.

---

## Suggested order

1. Scrape-break alerting (30 min) — protects the thing most likely to break
2. Cache staleness bounds (1 hr) — protects correctness of what's already shipped
3. Golden-task suite (half day) — prerequisite: extract `picker-core.js`
4. Shortlist auto-nomination (half day) — removes the last manual step
5. KV cache for recommendations (1 hr) — only when traffic justifies it
6. Trend tracking (1 day) — the fun one

## Things deliberately NOT automated

- **Merging shortlist changes.** Curation is editorial judgment; a bot proposes, you decide.
- **Bypassing the hard gates.** They're the product. Nothing may be allowed to route around
  a non-hallucination floor, including a very confident LLM.
- **Un-gating `models.optiqo.dev`.** The domain sits behind Cloudflare Access; that's a
  deliberate access decision and not the automation layer's business.
