"""Oolong-Tea Artificial Analysis snapshot source adapter.

This is a dependency-free fallback for the richer RSC/API sources.  The
snapshot format is intentionally discovered at runtime because its model-list
key is not part of the source contract.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from . import schema
from .http import atomic_write_json, disk_cache_key, fetch_json, read_json
from .source_base import SNAPSHOT_PARSER_VERSION, SourceResult

log = logging.getLogger("aa.pipeline")

DEFAULT_BASE_URL = (
    "https://raw.githubusercontent.com/oolong-tea-2026/"
    "artificial-analysis-leaderboards/main/data/latest.json"
)
PREFERRED_ARRAY_KEYS = ("models", "data", "records", "items")


def _key(value: object) -> str:
    """Compare camelCase/snake_case/source spellings uniformly."""
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _num(value, digits: int = 2):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return round(value, digits)
    return None


def _pct(value, digits: int = 2):
    """Normalize fractions to the schema's 0..100 benchmark scale."""
    number = _num(value, digits)
    if number is None:
        return None
    if 0 <= number <= 1:
        return round(number * 100.0, digits)
    return number


def _perf(value, digits: int = 2):
    """Treat zero/non-numeric speed and latency values as unavailable."""
    number = _num(value, digits)
    return number if number is not None and number > 0 else None


def _find_value(obj: object, names: tuple[str, ...]):
    """Find a positively named field through an entry's nested objects."""
    wanted = {_key(name) for name in names}
    if isinstance(obj, dict):
        # Exact matches win over recursive traversal (important for generic
        # keys such as ``name`` and ``id``).
        for field, value in obj.items():
            if _key(field) in wanted and value is not None:
                return value
        for value in obj.values():
            found = _find_value(value, names)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = _find_value(value, names)
            if found is not None:
                return found
    return None


def _find_key_value(obj: object, names: tuple[str, ...]):
    """Return both the matched source key and its value for modality maps."""
    wanted = {_key(name) for name in names}
    if isinstance(obj, dict):
        for field, value in obj.items():
            if _key(field) in wanted and value is not None:
                return field, value
        for value in obj.values():
            found = _find_key_value(value, names)
            if found is not None:
                return found
    return None


def _slug(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


def _snapshot_array(payload: dict) -> tuple[str | None, list[dict] | None]:
    """Find the first preferred, otherwise first, list of dictionaries."""
    candidates = []
    for field, value in payload.items():
        if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
            candidates.append((field, value))
    for preferred in PREFERRED_ARRAY_KEYS:
        for field, value in candidates:
            if _key(field) == _key(preferred):
                return str(field), value
    return candidates[0] if candidates else (None, None)


def _llms_url(base_url: str, latest: dict) -> str:
    path = latest.get("path")
    date = latest.get("date")
    parsed = urlparse(base_url)
    base_dir = parsed.path.rsplit("/", 1)[0] + "/"
    if path:
        relative = str(path).strip("/")
        # ``path`` is repository-relative (normally ``data/YYYY-MM-DD``),
        # while latest.json itself lives inside the data directory.
        if relative.startswith("data/") and base_dir.rstrip("/").endswith("/data"):
            base_dir = base_dir.rsplit("data/", 1)[0]
        target = base_dir + relative + "/llms.json"
        return parsed._replace(path=target, query="", fragment="").geturl()
    if date:
        target = base_dir + str(date).strip("/") + "/llms.json"
        return parsed._replace(path=target, query="", fragment="").geturl()
    raise RuntimeError("latest.json has neither a snapshot path nor date")


def _normalize(entry: dict) -> dict:
    rec = schema.model_record_template()
    slug = _slug(_find_value(entry, ("slug", "model_slug", "modelSlug", "model_id", "modelId")))
    name = _find_value(entry, ("name", "model_name", "modelName", "label"))
    rec["slug"] = slug
    rec["orig_slug"] = slug
    rec["orig_id"] = _find_value(entry, ("id", "model_id", "modelId", "uuid"))
    rec["source"] = "snapshot"
    rec["name"] = str(name).strip() if name is not None else slug
    rec["short_name"] = _find_value(entry, ("short_name", "shortName")) or rec["name"]
    creator = _find_value(entry, ("creator", "creator_name", "creatorName",
                                  "provider", "organization", "company"))
    if isinstance(creator, dict):
        rec["creator"] = creator.get("name") or creator.get("slug")
        rec["creator_slug"] = creator.get("slug")
    else:
        rec["creator"] = creator
        rec["creator_slug"] = _find_value(entry, ("creator_slug", "creatorSlug",
                                                  "provider_slug", "providerSlug"))
    rec["released"] = _find_value(entry, ("released", "release_date", "releaseDate"))
    rec["deprecated"] = _bool(_find_value(entry, ("deprecated",)))
    rec["is_reasoning"] = _bool(_find_value(entry, ("reasoning_model", "reasoningModel",
                                                    "is_reasoning", "reasoning")))
    # open_weights is a nested dict in this snapshot (is_open_weights, license...)
    ow = entry.get("open_weights")
    if isinstance(ow, dict):
        rec["is_open_weights"] = _bool(ow.get("is_open_weights"))
        rec["commercial_allowed"] = _bool(ow.get("commercial_allowed"))
        rec["license"] = ow.get("license_name")
        rec["license_url"] = ow.get("license_url")
    else:
        rec["is_open_weights"] = _bool(_find_value(entry, ("open_weights", "openWeights",
                                                           "is_open_weights")))

    # The snapshot nests the metric groups (mirrors the site schema):
    #   evaluations  -> indices on 0..100 (artificial_analysis_*_index) + benchmarks 0..1
    #   pricing      -> price_1m_*  (and intelligence_index_cost_*)
    #   speed        -> median_* + percentile_*
    #   capabilities -> context window / params / modalities / size class
    ev = entry.get("evaluations") if isinstance(entry.get("evaluations"), dict) else {}
    pricing = entry.get("pricing") if isinstance(entry.get("pricing"), dict) else {}
    speed = entry.get("speed") if isinstance(entry.get("speed"), dict) else {}
    cap = entry.get("capabilities") if isinstance(entry.get("capabilities"), dict) else {}
    # flat fallbacks too (older snapshots)
    def val(*keys):
        for k in keys:
            if k in ev: return ev[k]
            if k in pricing: return pricing[k]
            if k in speed: return speed[k]
            if k in cap: return cap[k]
            v = entry.get(k)
            if v is not None: return v
        return None

    # Indices: on the SAME 0..100 scale as RSC (verified: 33.26 > 0..1). Use _num, NOT _pct.
    rec["intelligence_index"] = _num(val("artificial_analysis_intelligence_index",
                                         "intelligence_index", "intelligenceIndex", "IQ"), 2)
    rec["intelligence_index_estimated"] = _bool(val("artificial_analysis_intelligence_index_is_estimated"))
    rec["coding_index"] = _num(val("artificial_analysis_coding_index", "coding_index",
                                   "codingIndex", "coding"), 2)
    rec["agentic_index"] = _num(val("artificial_analysis_agentic_index", "agentic_index",
                                    "agenticIndex", "agentic"), 2)
    rec["omniscience_index"] = _num(val("aa_omniscience", "omniscience_index",
                                        "omniscienceIndex", "omniscience"), 1)

    b = rec["benchmarks"]
    bench_map = {
        "gpqa": ("gpqa", "gpqa_diamond", "gpqaDiamond"),
        "hle": ("hle",),
        "scicode": ("scicode",),
        "ifbench": ("ifbench",),
        "lcr": ("aa_lcr", "lcr"),
        "tau2": ("tau2_bench", "tau2"),
        "tau_banking": ("tau_banking", "tau3_banking", "tau_banking_bench"),
        "terminalbench_hard": ("terminal_bench_hard", "terminalbench_hard"),
        "terminalbench_v21": ("terminal_bench_v21", "terminalbench_v2_1"),
        "mmlu_pro": ("mmlu_pro", "mmluPro"),
        "gdpval": ("gdpval_aa_normalized", "gdpval_normalized", "gdpval"),
        "critpt": ("critpt",),
        "mmmu_pro": ("mmmu_pro", "mmmuPro"),
        "apex_agents": ("apex_agents",),
        "omniscience_accuracy": ("aa_omniscience_accuracy", "omniscience_accuracy"),
        "omniscience_hallucination_rate": ("aa_omniscience_hallucination_rate",
                                           "omniscience_hallucination_rate"),
        "omniscience_non_halluc": ("aa_omniscience_non_hallucination",
                                   "omniscience_non_hallucination"),
    }
    for target, aliases in bench_map.items():
        v = _find_value(ev, aliases)
        if v is None:
            v = _find_value(entry, aliases)
        if v is not None:
            b[target] = _pct(v)

    rec["context_tokens"] = _num(val("context_window_tokens", "contextWindowTokens",
                                     "context_window", "contextWindow"), 0)
    rec["size_class"] = val("size_class", "sizeClass")
    rec["parameters_billions"] = _num(val("total_parameters", "parameters",
                                          "parameters_billions", "param_billions"), 2)
    rec["active_params_billions"] = _num(val("active_parameters", "active_params_billions",
                                             "inference_parameters_active_billions"), 2)
    # modalities: snapshot exposes per-modality booleans in `capabilities`
    in_mods = val("input_modalities", "inputModalities")
    if isinstance(in_mods, dict):
        rec["input_modalities"] = {("audio" if k == "speech" else k): v
                                   for k, v in in_mods.items()}
    elif isinstance(in_mods, list):
        rec["input_modalities"] = {str(m): True for m in in_mods}
    elif cap:
        rec["input_modalities"] = {
            "text": _bool(cap.get("input_modality_text")),
            "image": _bool(cap.get("input_modality_image")),
            "audio": _bool(cap.get("input_modality_speech")),
            "video": _bool(cap.get("input_modality_video")),
        }
        rec["output_modalities"] = {
            "text": _bool(cap.get("output_modality_text")),
            "image": _bool(cap.get("output_modality_image")),
            "audio": _bool(cap.get("output_modality_speech")),
            "video": _bool(cap.get("output_modality_video")),
        }

    p = rec["pricing"]
    p["input"] = _num(val("price_1m_input_tokens", "input_price", "inputPrice"), 4)
    p["output"] = _num(val("price_1m_output_tokens", "output_price", "outputPrice"), 4)
    p["blended_3_1"] = _num(val("price_1m_blended_3_to_1", "blended_price_3_1"), 4)
    p["cache_hit"] = _num(val("cache_hit_price", "cacheHitPrice", "cache_hit"), 4)
    p["cache_write"] = _num(val("cache_write_price", "cacheWritePrice", "cache_write"), 4)
    rec["intelligence_eval_total_cost_usd"] = _num(
        val("intelligence_index_cost_total"), 2)

    perf = rec["performance"]
    perf["median_output_speed_tps"] = _perf(val("output_tokens_per_second",
                                                "median_output_tokens_per_second",
                                                "median_output_speed_tps"))
    perf["median_ttft_seconds"] = _perf(val("time_to_first_token_seconds",
                                            "median_time_to_first_token_seconds",
                                            "median_ttft_seconds"))
    perf["median_ttfa_seconds"] = _perf(val("time_to_first_answer_token_seconds",
                                            "median_time_to_first_answer_token_seconds"))
    perf["median_e2e_500tok_seconds"] = _perf(val("end_to_end_response_time_seconds",
                                                  "median_end_to_end_response_time_seconds"))
    percentiles = {}
    for base, pfx in (("output_speed", "output_tokens_per_second"),
                      ("ttft", "time_to_first_token_seconds")):
        for q in ("percentile05", "quartile25", "quartile75", "percentile95"):
            v = speed.get(q + "_" + pfx) if isinstance(speed, dict) else None
            if v is not None and isinstance(v, (int, float)):
                percentiles.setdefault(base, {})[q] = round(v, 2)
    if percentiles:
        perf["percentiles"] = percentiles

    rec["raw_fields"] = {"snapshot_entry": entry}
    return rec


def _bool(v):
    if isinstance(v, bool):
        return v
    if v in (1, "1", "true", "True", "yes"):
        return True
    if v in (0, "0", "false", "False", "no"):
        return False
    return None


class SnapshotSource:
    name = "snapshot"

    def __init__(self, base_url: str = DEFAULT_BASE_URL,
                 cache_dir: Path = Path("data/aa_cache"), force_refresh: bool = False):
        self.base_url = base_url
        self.cache_dir = Path(cache_dir)
        self.force_refresh = force_refresh

    def _fetch_cached(self, url: str) -> dict:
        cache_path = self.cache_dir / f"snapshot_{disk_cache_key(url)}.json"
        if not self.force_refresh:
            cached = read_json(cache_path)
            if isinstance(cached, dict):
                log.info("Using cached snapshot JSON for %s", url)
                return cached
        payload, _response = fetch_json(url)
        atomic_write_json(cache_path, payload)
        return payload

    def fetch(self) -> SourceResult:
        now = datetime.now(timezone.utc)
        result = SourceResult(
            source=self.name, parser_version=SNAPSHOT_PARSER_VERSION,
            fetched_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            fetched_at_ts=now.timestamp(), records=[], raw=None, meta={}, healthy=False,
        )
        try:
            latest = self._fetch_cached(self.base_url)
            llms_url = _llms_url(self.base_url, latest)
            payload = self._fetch_cached(llms_url)
            result.raw = payload
            array_key, entries = _snapshot_array(payload)
            if entries is None:
                raise RuntimeError("could not detect a list of model dictionaries in llms.json")

            models = {}
            skipped = 0
            for entry in entries:
                rec = _normalize(entry)
                if not schema.require_identity(rec):
                    skipped += 1
                    continue
                models[rec["slug"]] = rec
            result.records = list(models.values())
            result.meta = {
                "source_url": llms_url,
                "fetched_at": result.fetched_at,
                "model_count": len(result.records),
                "parser_version": SNAPSHOT_PARSER_VERSION,
                "array_key": array_key,
                "snapshot_date": latest.get("date"),
                "skipped_entries": skipped,
            }
            raw_path = self.cache_dir / f"snapshot_raw_{now.strftime('%Y%m%d_%H%M%S')}.json"
            normalized_path = self.cache_dir / f"snapshot_normalized_{now.strftime('%Y%m%d_%H%M%S')}.json"
            atomic_write_json(raw_path, payload)
            atomic_write_json(normalized_path, result.records)
            result.raw_path = str(raw_path)
            result.healthy = len(result.records) >= schema.MIN_MODELS_SNAPSHOT
            if not result.healthy:
                result.errors.append(f"only {len(result.records)} models from snapshot (min {schema.MIN_MODELS_SNAPSHOT})")
            log.info("[%s] detected model array key %s (%d records)", self.name, array_key, len(result.records))
        except Exception as exc:  # adapter boundary must never raise
            result.errors.append(str(exc) or exc.__class__.__name__)
            log.error("[%s] snapshot fetch failed: %s", self.name, exc)
        return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    fetched = SnapshotSource(force_refresh=True).fetch()
    print("healthy:", fetched.healthy)
    print("models:", len(fetched.records))
    print("errors:", fetched.errors)
    print("array_key:", fetched.meta.get("array_key"))
