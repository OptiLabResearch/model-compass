"""Common normalized schema for AA model records + validation bounds.

Every source adapter normalizes its raw records into THIS schema (per-model,
keyed by slug downstream). Unknown raw fields are preserved under
``raw_fields`` rather than dropped, per the "don't throw unknown fields away"
requirement.

Conventions (mirrors existing public/data/models.json where sensible so the
legacy site builder can keep working):
- benchmarks stored 0..100 (RSC/site report 0..1; convert with *100)
- pricing per 1M tokens, USD
- performance ``_seconds``/per-second units
- ``None`` means "not measured", never zero.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Sanity bounds for stale/empty detection (private realism, tuned to AA scale).
# ---------------------------------------------------------------------------
EXPECTED_INDEX_VERSION = "4.1"
MIN_MODELS_RSC = 250           # the RSC source should always exceed this
MIN_MODELS_API = 100
MIN_MODELS_SNAPSHOT = 200
MAX_MODELS = 8000
MIN_RICH_BENCHMARK_RATIO = 0.35  # share of models with intelligenceIndex ≥ this


def model_record_template() -> dict:
    """A blank record with every normalized field None/empty."""
    return {
        "slug": None,             # normalized AA url-slug (identity)
        "orig_id": None,          # source's original model id (uuid or hostApiId)
        "orig_slug": None,        # source's original slug before normalization
        "source": None,           # which adapter produced this record
        "name": None,
        "short_name": None,
        "creator": None,
        "creator_slug": None,
        "released": None,         # ISO date
        "knowledge_cutoff": None,
        "is_reasoning": None,
        "deprecated": None,
        "is_open_weights": None,
        "license": None,
        "license_url": None,
        "commercial_allowed": None,
        "size_class": None,
        "parameters_billions": None,
        "active_params_billions": None,
        "context_tokens": None,
        "input_modalities": None,   # dict[str,bool]
        "output_modalities": None,  # dict[str,bool]
        # composite indices (0..100 scale)
        "intelligence_index": None,
        "intelligence_index_estimated": None,
        "intelligence_index_version": None,
        "coding_index": None,
        "math_index": None,
        "agentic_index": None,
        "omniscience_index": None,
        # benchmarks 0..100
        "benchmarks": {
            "gpqa": None, "gpqa_diamond": None, "hle": None,
            "scicode": None, "ifbench": None, "lcr": None,
            "tau2": None, "tau_banking": None,
            "terminalbench_hard": None, "terminalbench_v21": None,
            "mmlu_pro": None, "livecodebench": None, "math_500": None,
            "aime": None, "aime25": None,
            "gdpval": None, "critpt": None, "mmmu_pro": None,
            "apex_agents": None, "it_bench_sre": None,
            "omniscience": None, "omniscience_accuracy": None,
            "omniscience_hallucination_rate": None,
            "omniscience_non_halluc": None,
        },
        # pricing per 1M tokens USD
        "pricing": {
            "input": None, "output": None,
            "blended_3_1": None, "blended_7_2_1": None, "blended_1_1": None,
            "cache_hit": None, "cache_write": None,
        },
        # cost to evaluate / cost per task
        "intelligence_eval_total_cost_usd": None,
        "cost_per_intelligence_task_usd": None,   # dict or scalar
        "output_tokens_per_task": None,           # dict(answer/reasoning/total)
        "time_per_task_seconds": None,
        # performance
        "performance": {
            "median_output_speed_tps": None,
            "median_ttft_seconds": None,
            "median_ttfa_seconds": None,
            "median_e2e_500tok_seconds": None,
            "percentiles": None,       # reserved: dict of percentile arrays
            "by_prompt_length": [],    # list of dicts
        },
        "hosts": [],             # list of provider/host info dicts
        "identity_evidence": [], # source-qualified external identity claims
        "raw_fields": {},        # preserved unknown/extra raw fields
    }


# Required fields for a record to be considered "not corrupt". If a source
# record fails all of these we treat it as a parse failure, not a valid record.
REQUIRED_IDENTITY_FIELDS = ("slug", "name")


def require_identity(record: dict) -> bool:
    """A record is minimally valid if it has a slug and a name."""
    return bool(record.get("slug") and record.get("name"))
