"""First-class provider and coding-agent observation contracts.

Observations are source-specific facts. They do not overwrite canonical model
benchmark fields. JSON is used because the current weekly dataset is small,
portable, and easy to replay.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any


def _float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _provider_id(value: str | None) -> str | None:
    if not value:
        return None
    return "-".join(str(value).lower().replace("|", " ").split())


def source_authority(field: str) -> str:
    if field in {"intelligence_index", "coding_index", "agentic_index", "benchmarks"}:
        return "artificial_analysis"
    if field.startswith("provider_") or field in {"uptime", "quantization", "supported_parameters"}:
        return "openrouter"
    return "source_specific"


def normalize_openrouter_endpoint(raw: dict, *, fetched_at: str | None = None) -> dict:
    pricing = raw.get("pricing") or {}
    input_price = _float(pricing.get("prompt"))
    output_price = _float(pricing.get("completion"))
    status = raw.get("status")
    return {
        "observation_type": "provider_endpoint",
        "model_id": raw.get("model_id"),
        "model_slug": raw.get("model_id"),
        "provider_id": _provider_id(raw.get("tag") or raw.get("provider_name")),
        "provider_name": raw.get("provider_name"),
        "endpoint_id": raw.get("name") or raw.get("model_id"),
        "context_tokens": raw.get("context_length"),
        "pricing": {
            "input_per_million": input_price * 1_000_000 if input_price is not None else None,
            "output_per_million": output_price * 1_000_000 if output_price is not None else None,
            "raw": pricing,
        },
        "performance": {
            "latency_seconds": _float(raw.get("latency_last_30m")),
            "throughput_tps": _float(raw.get("throughput_last_30m")),
        },
        "availability": {
            "status": "available" if status == 0 else "unavailable" if status is not None else "unknown",
            "uptime_5m": _float(raw.get("uptime_last_5m")),
            "uptime_30m": _float(raw.get("uptime_last_30m")),
            "uptime_1d": _float(raw.get("uptime_last_1d")),
        },
        "quantization": raw.get("quantization"),
        "capabilities": {"supported_parameters": sorted(raw.get("supported_parameters") or [])},
        "privacy": {},
        "provenance": {"source": "openrouter", "fetched_at": fetched_at,
                        "source_authority": "openrouter", "raw_endpoint": raw.get("model_id")},
    }


def normalize_coding_agent_observation(raw: dict, *, fetched_at: str, source: str) -> dict:
    """Normalize a harness/model row without pretending it is a base-model fact."""
    return {
        "observation_type": "coding_agent",
        "agent_id": raw.get("agent_id") or raw.get("harness"),
        "agent_name": raw.get("agent_name") or raw.get("harness"),
        "model_id": raw.get("model_id") or raw.get("model"),
        "configuration": raw.get("configuration") or raw.get("reasoning_level"),
        "benchmark_suite": raw.get("benchmark_suite"),
        "benchmark_version": raw.get("benchmark_version"),
        "scores": raw.get("scores") or {},
        "cost_per_task_usd": _float(raw.get("cost_per_task_usd")),
        "execution_time_seconds": _float(raw.get("execution_time_seconds")),
        "tokens": raw.get("tokens"),
        "turns": raw.get("turns"),
        "provenance": {"source": source, "fetched_at": fetched_at,
                        "source_authority": source},
    }
