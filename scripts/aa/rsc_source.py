"""RSC source adapter — extract full AA model dataset from the site's public
Next.js React Server Components payload, with NO API key required.

Why RSC? AA's public leaderboard page ships the complete dataset (host-model
pairs) in a single `text/x-component` ~2.5 MB response. It carries the richest
metric set: all composite indices, per-benchmark scores (omniscience, GDPval,
CritPt, MMMU-Pro, terminalbench...), median AND percentile performance,
cost-per-task, full pricing blends, context window, modalities flag, and
provider/host metadata. This is strictly more than the Free API exposes (which
drops blending, percentiles, many benchmarks, and metadata).

Structure (verified 2026-08-21): the payload is a Next.js flight stream whose
model table appears as ``{rows:[ {id, label, hostApiId, footnotes, host:{...},
model:{...}, features:{contextWindowTokens,...}, pricing:{...},
performance:{...}}, ...]}``. The wrapper key that carried this historically
(``hostsModels``) is GONE, and keys are camelCase (not the reference parser's
snake_case). Rather than hardcode a single key, we search for the ``rows``
array and validate that entries look like host-model pairs; MALFORMED PARSING IS
A HARD FAILURE (see the `search` strategy), not a silent empty dataset.

Responsible crawling: the endpoint is a public cache (x-vercel-cache: HIT). We
fetch at most once per run, cache the raw bytes to disk, and never hammer it.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from . import schema
from .http import atomic_write_json, fetch_bytes, read_json, FetchResult
from .source_base import RSC_PARSER_VERSION, SourceResult

log = logging.getLogger("aa.pipeline")

# The _rsc query token drifts; the base URL + a valid token + the RSC headers
# are the contract. We try a list of known tokens, then fall back to scraping
# the HTML page for the current token if all fail.
RSC_URLS = [
    "https://artificialanalysis.ai/leaderboards/providers?_rsc=hgvan",
    "https://artificialanalysis.ai/leaderboards/providers?_rsc=xv7gf",
    "https://artificialanalysis.ai/leaderboards/providers?_rsc=abc12",
]

RSC_HEADERS = {
    "rsc": "1",
    "next-router-prefetch": "1",
    "next-router-state-tree": (
        '[["","pages",["leaderboards",["models",["__PAGE__",{},'
        '"/leaderboards/models","refresh"]]]],null,null,true]'
    ),
    "next-url": "/leaderboards/models",
    "accept": "*/*",
}

# The leaderboard page URL used only to discover the current _rsc token.
PROVIDERS_PAGE = "https://artificialanalysis.ai/leaderboards/providers"
MAX_ROWS = 4000

# camelCase -> normalized schema field helpers. The RSC payload stores many
# values as 0..1 fractions; schema stores 0..100. We convert.
def _pct(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return round(v * 100.0, 2)
    return None


def _num(v, digits=2):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return round(v, digits)
    return None


def _perf(v, digits=2):
    """0-means-not-measured handling (AA uses 0 for unmeasured speed/latency)."""
    if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
        return round(v, digits)
    return None


def _b(v):
    return bool(v) if v is not None else None


def _extract_rows(payload_text: str):
    """Locate and json-parse the ``rows:[...]`` array in the flight payload.

    Returns (rows_list, end_index) or (None, None) if absent. We walk the text
    for the LAST occurrence of ``"rows":[`` and bracket-match its array so we
    are robust to other ``rows`` keys occurring earlier in unrelated markup.
    """
    marker = '"rows":['
    last = payload_text.rfind(marker)
    if last < 0:
        return None, None
    start = payload_text.index("[", last)
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(payload_text)):
        c = payload_text[i]
        if esc:
            esc = False
        elif c == "\\":
            esc = True
        elif c == '"':
            in_str = not in_str
        elif not in_str:
            if c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    end = i
                    text = payload_text[start:end + 1]
                    try:
                        return json.loads(text), end
                    except json.JSONDecodeError as e:
                        log.error("RSC rows JSON parse failed at byte %s", e.pos)
                        return None, None
    return None, None


def _looks_like_row(entry) -> bool:
    """A row entry must reference a model and its host in the expected shape."""
    return (
        isinstance(entry, dict)
        and isinstance(entry.get("model"), dict)
        and isinstance(entry.get("host"), dict)
        and entry["model"].get("slug")
    )


def _extract_array(payload_text: str, key: str):
    """Locate and json-parse the array for *any* ``"<key>":[`` occurrence,
    scanning from the end and returning the first one that parses as a list
    of dicts. Returns (list, end_index) or (None, None)."""
    search_from = len(payload_text)
    while True:
        last = payload_text.rfind(f'"{key}":[', 0, search_from)
        if last < 0:
            return None, None
        start = payload_text.index("[", last)
        depth = 0
        in_str = False
        esc = False
        end = -1
        for i in range(start, len(payload_text)):
            c = payload_text[i]
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = not in_str
            elif not in_str:
                if c == "[":
                    depth += 1
                elif c == "]":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
        if end < 0:
            return None, None
        text = payload_text[start:end + 1]
        try:
            arr = json.loads(text)
        except json.JSONDecodeError:
            search_from = last  # try an earlier occurrence
            continue
        # only accept arrays that look like the RSC models metadata table
        if isinstance(arr, list) and arr and all(isinstance(x, dict) for x in arr):
            return arr, end
        search_from = last


def _extract_models_meta(payload_text: str) -> dict:
    """Return {slug: entry} for the RSC ``models`` metadata table, which carries
    releaseDate / creator / isReasoning / deprecated / effort that the ``rows``
    table omits. Best-effort: {} if not found."""
    arr, _ = _extract_array(payload_text, "models")
    if not arr:
        return {}
    out = {}
    for entry in arr:
        slug = (entry or {}).get("slug")
        if slug:
            out[slug] = entry
    return out


def normalize_row(row: dict, source_meta: dict) -> dict:
    """Map one RSC row (host+model+pricing+performance) onto the schema."""
    rec = schema.model_record_template()
    model = row.get("model") or {}
    feat = row.get("features") or {}
    perf = row.get("performance") or {}
    price = row.get("pricing") or {}
    host = row.get("host") or {}
    # malformed sub-objects (some rows carry strings/None here) -> coerce
    if not isinstance(model, dict): model = {}
    if not isinstance(feat, dict): feat = {}
    if not isinstance(perf, dict): perf = {}
    if not isinstance(price, dict): price = {}
    if not isinstance(host, dict): host = {}

    slug = str(model.get("slug") or row.get("hostApiId") or "").strip().lower()
    rec["slug"] = slug or None
    rec["orig_id"] = row.get("id")
    rec["orig_slug"] = model.get("slug") or row.get("hostApiId")
    rec["source"] = source_meta.get("source")
    rec["name"] = (model.get("name") or row.get("label") or slug) or None
    rec["short_name"] = row.get("label") or model.get("name")
    creator = model.get("creator") or {}
    rec["creator"] = creator.get("name") or host.get("name")
    rec["creator_slug"] = creator.get("slug") if isinstance(creator, dict) else None
    rec["released"] = model.get("releaseDate") or model.get("release_date")
    rec["knowledge_cutoff"] = model.get("knowledgeCutoffDate")
    rec["is_reasoning"] = _b(model.get("reasoningModel"))
    rec["deprecated"] = _b(model.get("deprecated"))
    rec["is_open_weights"] = _b(model.get("isOpenWeights"))
    rec["license"] = model.get("licenseName")
    rec["commercial_allowed"] = model.get("commercialAllowed")
    rec["size_class"] = model.get("sizeClass") or price.get("priceClass")
    rec["parameters_billions"] = _num(model.get("parameters"))
    rec["active_params_billions"] = _num(model.get("inferenceParametersActiveBillions"))
    rec["context_tokens"] = feat.get("contextWindowTokens") or model.get("contextWindowTokens")

    rec["input_modalities"] = {
        "text": _b(mk.get("text")),
        "image": _b(mk.get("image")),
        "audio": _b(mk.get("speech")),
        "video": _b(mk.get("video")),
    } if (mk := model.get("inputModality")) else None
    rec["output_modalities"] = {
        "text": _b(mk.get("text")),
        "image": _b(mk.get("image")),
        "audio": _b(mk.get("speech")),
        "video": _b(mk.get("video")),
    } if (mk := model.get("outputModality")) else None

    # composite indices
    rec["intelligence_index"] = _num(model.get("intelligenceIndex"), 2)
    rec["intelligence_index_estimated"] = _b(model.get("intelligenceIndexIsEstimated"))
    rec["intelligence_index_version"] = source_meta.get("intelligence_index_version")
    rec["coding_index"] = _num(model.get("codingIndex"), 2)
    rec["math_index"] = _num(model.get("mathIndex"), 2)
    rec["agentic_index"] = _num(model.get("agenticIndex"), 2)
    rec["omniscience_index"] = _num(model.get("omniscience"), 1)

    b = rec["benchmarks"]
    b["gpqa"] = _pct(model.get("gpqa") or model.get("gpqaDiamond"))
    b["hle"] = _pct(model.get("hle"))
    b["scicode"] = _pct(model.get("scicode"))
    b["ifbench"] = _pct(model.get("ifbench"))
    b["lcr"] = _pct(model.get("lcr"))
    b["tau2"] = _pct(model.get("tau2"))
    b["tau_banking"] = _pct(model.get("tauBanking"))
    b["terminalbench_hard"] = _pct(model.get("terminalbenchHard"))
    b["terminalbench_v21"] = _pct(model.get("terminalbenchV21"))
    b["mmlu_pro"] = _pct(model.get("mmlu_pro") if "mmlu_pro" in model else model.get("mmluPro"))
    b["livecodebench"] = _pct(model.get("livecodebench"))
    b["math_500"] = _pct(model.get("math500") if "math500" in model else model.get("math_500"))
    b["aime25"] = _pct(model.get("aime25"))
    b["gdpval"] = _pct(model.get("gdpvalNormalized"))
    b["critpt"] = _pct(model.get("critpt"))
    b["mmmu_pro"] = _pct(model.get("mmmuPro"))
    b["apex_agents"] = _pct(model.get("apexAgents"))
    b["it_bench_sre"] = _pct(model.get("itBenchSre"))
    b["omniscience"] = _num(model.get("omniscience"), 2)
    b["omniscience_accuracy"] = _pct(model.get("omniscienceAccuracy"))
    b["omniscience_hallucination_rate"] = _pct(model.get("omniscienceHallucinationRate"))
    if isinstance(model.get("omniscienceNonHallucination"), (int, float)):
        b["omniscience_non_halluc"] = _pct(model["omniscienceNonHallucination"])

    p = rec["pricing"]
    p["input"] = _num(price.get("price1mInputTokens"), 4)
    p["output"] = _num(price.get("price1mOutputTokens"), 4)
    p["blended_3_1"] = _num(price.get("price1mBlended3To1") or price.get("price1mBlended0To3To1"), 4)
    p["blended_7_2_1"] = _num(price.get("price1mBlended7To2To1"), 4)
    p["blended_1_1"] = _num(price.get("price1mBlended1To1"), 4)
    p["cache_hit"] = _num(price.get("cacheHitPrice"), 4)
    p["cache_write"] = _num(price.get("cacheWritePrice"), 4)

    rec["cost_per_intelligence_task_usd"] = _num(price.get("costPerTask"), 4)
    rec["output_tokens_per_task"] = {
        "answer": _num(model.get("intelligenceIndexAnswerOutputTokens")),
        "reasoning": _num(model.get("intelligenceIndexReasoningOutputTokens")),
        "total": _num(model.get("intelligenceIndexOutputTokensPerTask")),
    } if any(k in model for k in (
        "intelligenceIndexAnswerOutputTokens",
        "intelligenceIndexReasoningOutputTokens",
        "intelligenceIndexOutputTokensPerTask",
    )) else None
    rec["time_per_task_seconds"] = _num(model.get("intelligenceIndexTimePerTask"), 1)

    rec["performance"]["median_output_speed_tps"] = _perf(
        perf.get("medianOutputTokensPerSecond"),
    )
    rec["performance"]["median_ttft_seconds"] = _perf(
        perf.get("medianTimeToFirstTokenSeconds"),
    )
    rec["performance"]["median_ttfa_seconds"] = _perf(
        perf.get("medianTimeToFirstAnswerTokenSeconds"),
    )
    rec["performance"]["median_e2e_500tok_seconds"] = _perf(
        perf.get("medianEndToEndResponseTimeSeconds"),
    )
    # percentile performance when available
    percentiles = {}
    for base, key in (
        ("output_speed", "OutputTokensPerSecond"),
        ("ttft", "TimeToFirstTokenSeconds"),
    ):
        for q in ("percentile05", "quartile25", "quartile75", "percentile95"):
            v = _perf(perf.get(q + key))
            if v is not None:
                percentiles.setdefault(base, {})[q] = v
    if percentiles:
        rec["performance"]["percentiles"] = percentiles

    rec["hosts"] = [{
        "name": host.get("name"),
        "slug": host.get("slug"),
        "logo": host.get("logo"),
        "hostApiId": row.get("hostApiId"),
    }]
    _collect_raw_fields(rec, row)
    return rec


def _collect_raw_fields(rec: dict, row: dict) -> None:
    """Preserve any unknown/extra raw fields instead of dropping them."""
    known = {
        "slug", "name", "releaseDate", "isOpenWeights", "deprecated",
        "reasoningModel", "intelligenceIndex", "intelligenceIndexIsEstimated",
        "omniscience", "omniscienceAccuracy", "omniscienceNonHallucination",
        "gdpvalNormalized", "terminalbenchHard", "terminalbenchV21",
        "tau2", "tauBanking", "lcr", "hle", "gpqa", "scicode",
        "livecodebench", "aime25", "ifbench", "critpt", "apexAgents",
        "itBenchSre", "mmmuPro", "sizeClass", "creator", "codingIndex",
        "mathIndex", "agenticIndex",
    }
    for key, val in (row.get("model") or {}).items():
        if key not in known and val is not None:
            rec.setdefault("raw_fields", {})["model:" + str(key)] = val
    # host-level extras (rare) preserved too
    for key, val in (row.get("host") or {}).items():
        if key not in ("name", "slug", "logo", "functionCallingUrl", "jsonModeUrl",
                       "color") and val is not None:
            rec.setdefault("raw_fields", {})["host:" + str(key)] = val
    for key in ("id", "label", "hostApiId", "footnotes"):
        if key not in ("id", "label") and row.get(key) is not None:
            rec.setdefault("raw_fields", {})["row:" + key] = row[key]


def _discover_token() -> str | None:
    """Find the current _rsc token from the providers page HTML if configured
    URLs fail. Returns a _rsc token or None. Best-effort."""
    try:
        from .http import build_request
        from urllib.request import urlopen
        req = build_request(PROVIDERS_PAGE)
        with urlopen(req, timeout=60) as r:
            html = r.read(600 * 1024).decode("utf-8", errors="replace")
        m = re.search(r'([?_&])(_rsc|_rsc=)([a-zA-Z0-9]+)', html)
        if m:
            return m.group(3)
        for tok in re.findall(r'_rsc=([a-zA-Z0-9]+)', html):
            return tok
    except Exception as e:  # noqa: BLE001
        log.warning("RSC token discovery failed: %s", e)
    return None


class RSCSource:
    """Fetch + normalize the AA RSC payload. ``use_cache`` lets tests reuse a
    dumped payload; ``cache_dir`` stores the raw bytes for reproducibility."""

    name = "rsc"

    def __init__(self, use_cache: bool = True, cache_dir: Path | None = None,
                 force_refresh: bool = False, offline: bool = False):
        self.use_cache = use_cache
        self.cache_dir = cache_dir or Path("data/aa_cache")
        self.force_refresh = force_refresh
        self.offline = offline

    def fetch(self) -> SourceResult:
        now = datetime.now(timezone.utc)
        result = SourceResult(
            source=self.name, parser_version=RSC_PARSER_VERSION,
            fetched_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            fetched_at_ts=now.timestamp(), records=[], meta={},
            healthy=False,
        )
        raw_bytes, raw_meta = self._get_raw()
        if raw_bytes is None:
            result.errors.append("RSC payload unavailable")
            return result
        # persist raw bytes for reproducibility
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        raw_path = self.cache_dir / f"rsc_raw_{now.strftime('%Y%m%d_%H%M%S')}.bin"
        raw_path.write_bytes(raw_bytes)
        result.raw_path = str(raw_path)
        try:
            text = raw_bytes.decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            result.errors.append("RSC payload not valid UTF-8")
            return result

        rows, _end = _extract_rows(text)
        if rows is None:
            result.errors.append(
                "Could not locate 'rows' array in RSC payload — AA structure has "
                "changed. Inspect raw payload and update normalize_row / _extract_rows."
            )
            return result
        if not any(_looks_like_row(r) for r in rows[:50]):
            result.errors.append(
                "RSC 'rows' entries do not look like host-model pairs — schema drift. "
                "Inspect raw payload."
            )
            return result
        if len(rows) > MAX_ROWS:
            result.warnings.append(f"unexpectedly large rows array: {len(rows)}")
        if len(rows) == 0:
            result.errors.append("RSC rows array is empty — likely drift or empty fetch")
            return result

        models = {}
        # The `rows` table omits releaseDate/creator/effort; the `models`
        # metadata table in the same payload carries them. Merge so records
        # keep full identity even for models AA's rows table under-specifies.
        meta = _extract_models_meta(text)
        for r in rows:
            if not _looks_like_row(r):
                continue
            rec = normalize_row(r, {"source": self.name, "intelligence_index_version": schema.EXPECTED_INDEX_VERSION})
            if not schema.require_identity(rec):
                continue
            slug = rec["slug"]
            mmeta = meta.get(slug)
            if mmeta:
                if rec.get("released") is None:
                    rec["released"] = mmeta.get("releaseDate") or mmeta.get("release_date")
                if rec.get("creator") is None:
                    cr = mmeta.get("creator")
                    if isinstance(cr, dict):
                        rec["creator"] = cr.get("name") or cr.get("slug")
                if rec.get("is_reasoning") is None and mmeta.get("isReasoning") is not None:
                    rec["is_reasoning"] = bool(mmeta["isReasoning"])
                if rec.get("deprecated") is None and mmeta.get("deprecated") is not None:
                    rec["deprecated"] = bool(mmeta["deprecated"])
            models[slug] = rec  # dedup by slug, last wins for richness
        result.meta = {
            "raw_rows": len(rows),
            "unique_models": len(models),
            "models_meta": len(meta),
            "payload_bytes": len(raw_bytes),
            "intelligence_index_version": "4.1",
            **(raw_meta or {}),
        }
        result.records = list(models.values())
        result.healthy = len(result.records) >= schema.MIN_MODELS_RSC
        if not result.healthy:
            result.errors.append(f"only {len(result.records)} models from RSC (min {schema.MIN_MODELS_RSC})")
        return result

    def _get_raw(self):
        """Return (bytes, meta) for the RSC payload, honouring disk cache."""
        cache_path = self.cache_dir / "rsc_raw_latest.bin" if self.use_cache else None
        if not self.force_refresh and self.use_cache and cache_path and cache_path.exists():
            log.info("Using cached RSC bytes (%d)", cache_path.stat().st_size)
            return cache_path.read_bytes(), {"cached": True}
        if self.offline:
            return None, {"error": "offline mode has no cached RSC payload"}
        last_err = None
        for url in RSC_URLS:
            try:
                res: FetchResult = fetch_bytes(
                    url, headers=RSC_HEADERS, retries=2,
                    # these URLs may 404 if token drifts -> treat as retryable
                    error_http_codes=frozenset({400, 401, 403, 404, 410}),
                )
                if res.status == 200 and b'"rows":[' in res.body:
                    if self.use_cache and cache_path:
                        cache_path.write_bytes(res.body)
                        log.info("Cached RSC bytes (%d)", len(res.body))
                    return res.body, {"cached": False, "url": url, "status": 200}
                last_err = f"{url} returned status {res.status} without rows payload"
            except RuntimeError as e:
                last_err = f"{url}: {e}"
                log.warning("RSC fetch attempt failed: %s", last_err)
        # try token discovery last
        tok = _discover_token()
        if tok:
            url = f"{PROVIDERS_PAGE}?_rsc={tok}"
            try:
                res = fetch_bytes(url, headers=RSC_HEADERS, retries=1,
                                  error_http_codes=frozenset({400, 401, 403}))
                if res.status == 200 and b'"rows":[' in res.body:
                    if self.use_cache and cache_path:
                        cache_path.write_bytes(res.body)
                    return res.body, {"cached": False, "url": url, "status": 200}
            except RuntimeError as e:
                last_err = f"{url}: {e}"
        log.error("RSC extraction failed after all attempts: %s", last_err)
        return None, {"error": last_err}


# CLI smoke test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    src = RSCSource(use_cache=False)
    res = src.fetch()
    print("healthy:", res.healthy)
    print("records:", len(res.records))
    print("errors:", res.errors[:5])
    print("warnings:", res.warnings[:5])
    from collections import Counter
    if res.records:
        c = Counter()
        for r in res.records:
            for k in ("intelligence_index", "omniscience_index", "context_tokens"):
                if r.get(k) is not None:
                    c[k] += 1
        print("field counts:", dict(c))