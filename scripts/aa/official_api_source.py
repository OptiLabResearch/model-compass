"""Official Artificial Analysis v2 Free language-model API source adapter.

The Free endpoint intentionally exposes a smaller public subset than the
leaderboard/RSC source.  Missing fields are therefore kept as ``None`` rather
than treated as schema errors.  Raw page responses are cached individually so
normal refreshes do not spend the API's limited request budget.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

try:
    from . import schema
    from .http import FetchResult, atomic_write_json, disk_cache_key, fetch_bytes, read_json
    from .source_base import API_PARSER_VERSION, SourceResult
except ImportError:  # Support ``python scripts/aa/official_api_source.py``.
    import sys
    # Remove scripts/aa from the front so aa/http.py cannot shadow stdlib http.
    if sys.path and Path(sys.path[0]).resolve() == Path(__file__).resolve().parent:
        sys.path.pop(0)
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.aa import schema
    from scripts.aa.http import FetchResult, atomic_write_json, disk_cache_key, fetch_bytes, read_json
    from scripts.aa.source_base import API_PARSER_VERSION, SourceResult

log = logging.getLogger("aa.pipeline")

BASE_URL = "https://artificialanalysis.ai/api/v2"
FREE_PATH = "/language/models/free"
MAX_PAGES = 25


def _num(value: Any, digits: int = 2):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return round(value, digits)
    return None


def _pct(value: Any):
    """Convert an API fraction to the schema's 0..100 benchmark scale."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return round(value * 100.0, 2)
    return None


def _perf(value: Any, digits: int = 2):
    """AA uses zero for unmeasured performance values."""
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
        return round(value, digits)
    return None


def _text(value: Any):
    return value.strip() if isinstance(value, str) and value.strip() else None


def _creator_parts(value: Any) -> tuple[Any, Any]:
    if isinstance(value, dict):
        return value.get("name") or value.get("slug"), value.get("slug")
    return value, None


def normalize_model(item: dict, intelligence_index_version: Any = None) -> dict:
    """Map one snake_case Free API model object to the common schema."""
    rec = schema.model_record_template()
    slug = _text(item.get("slug") or item.get("model_slug") or item.get("id"))
    rec["slug"] = slug.lower() if slug else None
    rec["orig_id"] = item.get("id")
    rec["orig_slug"] = item.get("slug") or item.get("model_slug")
    rec["source"] = "official_api"
    rec["name"] = _text(item.get("name") or item.get("model_name") or slug)
    rec["short_name"] = _text(item.get("short_name"))
    creator, creator_slug = _creator_parts(item.get("model_creator") or item.get("creator"))
    rec["creator"] = creator
    rec["creator_slug"] = creator_slug
    rec["released"] = item.get("release_date")

    # The Free API reports composite indices on the SAME 0..100 scale as the
    # RSC source (verified: docs example 62.9; legacy parser uses no ×100;
    # RSC GPT-5.6 Luna = 33.85). Indices live INSIDE `evaluations` as
    # artificial_analysis_*_index. Do NOT multiply by 100 here.
    evaluations = item.get("evaluations") if isinstance(item.get("evaluations"), dict) else {}
    def idx(*keys) -> Any:
        for key in keys:
            v = item.get(key)
            if v is None:
                v = evaluations.get(key)
            if v is not None:
                return _num(v, 2)
        return None

    rec["intelligence_index"] = idx("artificial_analysis_intelligence_index")
    rec["intelligence_index_version"] = intelligence_index_version
    rec["coding_index"] = idx("artificial_analysis_coding_index", "coding_index")
    rec["math_index"] = idx("artificial_analysis_math_index", "math_index")
    rec["agentic_index"] = idx("artificial_analysis_agentic_index", "agentic_index")
    rec["omniscience_index"] = idx("artificial_analysis_omniscience_index", "omniscience_index")

    benchmarks = rec["benchmarks"]
    if evaluations:
        # Benchmarks inside evaluations ARE fractions (mmlu_pro 0.791 -> 79.1).
        benchmark_keys = {
            "gpqa": ("gpqa", "gpqa_diamond"), "gpqa_diamond": ("gpqa_diamond",),
            "hle": ("hle",), "scicode": ("scicode",), "ifbench": ("ifbench",),
            "lcr": ("lcr",), "tau2": ("tau2",), "tau_banking": ("tau_banking",),
            "terminalbench_hard": ("terminalbench_hard",), "terminalbench_v21": ("terminalbench_v21",),
            "mmlu_pro": ("mmlu_pro",), "livecodebench": ("livecodebench",),
            "math_500": ("math_500",), "aime": ("aime",), "aime25": ("aime25",),
            "gdpval": ("gdpval",), "critpt": ("critpt",), "mmmu_pro": ("mmmu_pro",),
            "apex_agents": ("apex_agents",), "it_bench_sre": ("it_bench_sre",),
        }
        for target, keys in benchmark_keys.items():
            for key in keys:
                if key in evaluations:
                    benchmarks[target] = _pct(evaluations[key])
                    break
        # cost to run the intelligence evaluation (may be present on API)
        cost = item.get("artificial_analysis_intelligence_index_cost")
        if isinstance(cost, dict):
            rec["intelligence_eval_total_cost_usd"] = _num(cost.get("total_cost"), 2)
            cost_per_task = cost.get("cost_per_task")
            if isinstance(cost_per_task, dict):
                rec["cost_per_intelligence_task_usd"] = _num(
                    cost_per_task.get("total_cost"), 4)

    pricing = rec["pricing"]
    pricing["input"] = _num(item.get("price_1m_input_tokens"), 4)
    pricing["output"] = _num(item.get("price_1m_output_tokens"), 4)
    # These are documented as excluded from Free, but map them if upstream adds them.
    pricing["blended_3_1"] = _num(item.get("price_1m_blended_3_to_1"), 4)
    pricing["blended_7_2_1"] = _num(item.get("price_1m_blended_7_to_2_to_1"), 4)
    pricing["blended_1_1"] = _num(item.get("price_1m_blended_1_to_1"), 4)

    rec["performance"]["median_output_speed_tps"] = _perf(item.get("median_output_tokens_per_second"))
    rec["performance"]["median_ttft_seconds"] = _perf(item.get("median_time_to_first_token_seconds"))
    rec["performance"]["median_ttfa_seconds"] = _perf(item.get("median_time_to_first_answer_token_seconds"))
    rec["performance"]["median_e2e_500tok_seconds"] = _perf(item.get("median_end_to_end_response_time_seconds"))

    known = {
        "id", "slug", "model_slug", "name", "model_name", "short_name", "model_creator", "creator",
        "release_date", "artificial_analysis_intelligence_index", "coding_index", "math_index",
        "agentic_index", "omniscience_index", "evaluations", "price_1m_input_tokens", "price_1m_output_tokens",
        "price_1m_blended_3_to_1", "price_1m_blended_7_to_2_to_1", "price_1m_blended_1_to_1",
        "median_output_tokens_per_second", "median_time_to_first_token_seconds",
        "median_time_to_first_answer_token_seconds", "median_end_to_end_response_time_seconds",
    }
    rec["raw_fields"] = {k: v for k, v in item.items() if k not in known and v is not None}
    return rec


class OfficialAPISource:
    """Fetch and normalize the paged Artificial Analysis Free API endpoint."""

    name = "official_api"

    def __init__(self, api_key: str | None = None, cache_dir: Path | None = None,
                 force_refresh: bool = False, offline: bool = False):
        self.api_key = api_key if api_key is not None else os.environ.get("AA_API_KEY")
        self.cache_dir = cache_dir or Path("data/aa_cache")
        self.force_refresh = force_refresh
        self.offline = offline
        self._cache_times: list[float] = []

    def _page_url(self, page: int) -> str:
        return f"{BASE_URL}{FREE_PATH}?{urlencode({'page': page})}"

    def _load_page(self, page: int) -> tuple[dict, dict, bool]:
        url = self._page_url(page)
        cache_path = self.cache_dir / f"official_api_{disk_cache_key(url)}.json"
        if not self.force_refresh:
            cached = read_json(cache_path)
            if isinstance(cached, dict) and isinstance(cached.get("payload"), dict):
                self._cache_times.append(cache_path.stat().st_mtime)
                return cached["payload"], cached.get("headers") or {}, True
        if self.offline:
            raise RuntimeError(f"offline mode has no cached API page {page}")
        result: FetchResult = fetch_bytes(
            url, headers={"x-api-key": self.api_key or "", "User-Agent": "Mozilla/5.0 (compatible; ModelCompass/1.0)"},
            retries=3,
        )
        try:
            payload = json.loads(result.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Invalid JSON from {url}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError(f"JSON payload from {url} is not an object")
        atomic_write_json(cache_path, {"payload": payload, "headers": result.headers, "url": url})
        return payload, result.headers, False

    def fetch(self) -> SourceResult:
        now = datetime.now(timezone.utc)
        result = SourceResult(self.name, API_PARSER_VERSION, now.strftime("%Y-%m-%dT%H:%M:%SZ"), now.timestamp(), [])
        if not self.api_key and not self.offline:
            result.errors.append("AA_API_KEY is not set; official API fetch skipped")
            return result
        all_items: list[dict] = []
        pages: list[dict] = []
        headers_seen: dict[str, Any] = {}
        cache_hits = 0
        try:
            for page in range(1, MAX_PAGES + 1):
                payload, headers, cached = self._load_page(page)
                cache_hits += int(cached)
                pages.append(payload)
                headers_seen.update(headers)
                items = payload.get("data", [])
                if not isinstance(items, list):
                    raise RuntimeError(f"API page {page} has non-list data")
                all_items.extend(x for x in items if isinstance(x, dict))
                pagination = payload.get("pagination") or {}
                if not pagination.get("has_more"):
                    break
            else:
                result.warnings.append(f"stopped after safety cap of {MAX_PAGES} pages")
        except RuntimeError as exc:
            result.errors.append(str(exc))
            return result

        version = next((p.get("intelligence_index_version") for p in pages if p.get("intelligence_index_version") is not None), None)
        models = {}
        for item in all_items:
            rec = normalize_model(item, version)
            if schema.require_identity(rec):
                models[rec["slug"]] = rec
        result.records = list(models.values())
        result.raw = pages
        if cache_hits and self._cache_times:
            cached_ts = min(self._cache_times)
            result.fetched_at_ts = cached_ts
            result.fetched_at = datetime.fromtimestamp(cached_ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        result.meta = {"pages": len(pages), "raw_records": len(all_items), "cached_pages": cache_hits,
                       "cached": cache_hits == len(pages), "intelligence_index_version": version, **headers_seen}
        result.healthy = len(result.records) >= schema.MIN_MODELS_API
        if not result.records:
            result.errors.append("official API returned 0 valid records")
        elif not result.healthy:
            result.errors.append(f"only {len(result.records)} models from official API (min {schema.MIN_MODELS_API})")
        return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if not os.environ.get("AA_API_KEY"):
        print("AA_API_KEY is not set; official API smoke test skipped (exit 0).")
    else:
        res = OfficialAPISource().fetch()
        fields = ("name", "intelligence_index", "creator", "pricing", "performance")
        coverage = {f: sum(1 for r in res.records if (r.get(f) if f not in ("pricing", "performance") else any(v is not None for v in r[f].values()))) for f in fields}
        print("healthy:", res.healthy)
        print("records:", len(res.records))
        print("field coverage:", coverage)
        print("errors:", res.errors)
