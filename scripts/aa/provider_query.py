"""Queries over provider endpoint and coding-agent observation artifacts."""
from __future__ import annotations
from pathlib import Path
import json


def _number(value):
    return value if isinstance(value, (int, float)) else None


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
            rows = [r for r in rows if _number((r.get("performance") or {}).get("throughput_tps")) is not None] or rows
            key = lambda r: ((r.get("pricing") or {}).get("input_per_million") or float("inf"), r.get("provider_id", ""))
        else:
            rows = [r for r in rows if _number((r.get("performance") or {}).get("latency_seconds")) is not None] or rows
            key = lambda r: ((r.get("performance") or {}).get("latency_seconds") or float("inf"), r.get("provider_id", ""))
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
