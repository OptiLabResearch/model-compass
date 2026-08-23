"""Queries over provider endpoint and coding-agent observation artifacts."""
from __future__ import annotations
from pathlib import Path
import json


def _number(value):
    return value if isinstance(value, (int, float)) else None


def _availability_rank(row: dict) -> int:
    status = (row.get("availability") or {}).get("status")
    return 0 if status == "available" else 1 if status == "unknown" else 2


def _value(row: dict, *path):
    node = row
    for key in path:
        node = node.get(key) if isinstance(node, dict) else None
    return _number(node)


class ProviderDB:
    def __init__(self, observations=None):
        self.observations = list(observations or [])

    @classmethod
    def from_file(cls, path: str | Path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(data.get("observations", []))

    def providers(self, model_id: str) -> list[dict]:
        return [o for o in self.observations if o.get("model_id") == model_id]

    def best_provider(self, model_id: str, profile: str = "interactive") -> dict | None:
        rows = self.providers(model_id)
        if profile == "batch":
            key = lambda r: (_availability_rank(r),
                             _value(r, "performance", "throughput_tps") is None,
                             -(_value(r, "performance", "throughput_tps") or 0),
                             _value(r, "pricing", "input_per_million") is None,
                             _value(r, "pricing", "input_per_million") if _value(r, "pricing", "input_per_million") is not None else float("inf"),
                             r.get("provider_id", ""))
        else:
            key = lambda r: (_availability_rank(r),
                             _value(r, "performance", "latency_seconds") is None,
                             _value(r, "performance", "latency_seconds") if _value(r, "performance", "latency_seconds") is not None else float("inf"),
                             _value(r, "pricing", "input_per_million") is None,
                             _value(r, "pricing", "input_per_million") if _value(r, "pricing", "input_per_million") is not None else float("inf"),
                             r.get("provider_id", ""))
        return min(rows, key=key) if rows else None

    def independent_fallbacks(self, model_id: str, primary_provider: str, limit: int = 10) -> list[dict]:
        rows = [r for r in self.providers(model_id) if r.get("provider_id") != primary_provider]
        rows.sort(key=lambda r: (-((r.get("availability") or {}).get("uptime_1d") or 0), r.get("provider_id", "")))
        return rows[:limit]


class CodingAgentDB:
    def __init__(self, observations=None):
        self.observations = list(observations or [])

    @classmethod
    def from_file(cls, path: str | Path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(data.get("observations", []))

    def best(self, metric: str = "coding_agent_index", limit: int = 10) -> list[dict]:
        rows = [o for o in self.observations if _number((o.get("scores") or {}).get(metric)) is not None]
        rows.sort(key=lambda o: (-((o.get("scores") or {}).get(metric) or 0), o.get("agent_id", "")))
        return rows[:limit]

    def cheapest(self, limit: int = 10) -> list[dict]:
        rows = [o for o in self.observations if _number(o.get("cost_per_task_usd")) is not None]
        rows.sort(key=lambda o: (o["cost_per_task_usd"], o.get("agent_id", "")))
        return rows[:limit]

    def fastest(self, limit: int = 10) -> list[dict]:
        rows = [o for o in self.observations if _number(o.get("execution_time_seconds")) is not None]
        rows.sort(key=lambda o: (o["execution_time_seconds"], o.get("agent_id", "")))
        return rows[:limit]
