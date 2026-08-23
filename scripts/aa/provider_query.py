"""Queries over provider, endpoint-accuracy, and coding-agent observations."""
from __future__ import annotations
from pathlib import Path
import json


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _availability_rank(row: dict) -> int:
    status = (row.get("availability") or {}).get("status")
    return 0 if status == "available" else 1 if status == "unknown" else 2


def _value(row: dict, *path):
    node = row
    for key in path:
        node = node.get(key) if isinstance(node, dict) else None
    return _number(node)


class ProviderDB:
    def __init__(self, observations=None, accuracy=None):
        self.observations = list(observations or [])
        self.accuracy = list(accuracy or [])

    @classmethod
    def from_file(cls, path: str | Path, accuracy_path: str | Path | None = None):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        accuracy = []
        if accuracy_path and Path(accuracy_path).exists():
            accuracy = json.loads(Path(accuracy_path).read_text(encoding="utf-8")).get("observations", [])
        return cls(data.get("observations", []), accuracy)

    def providers(self, model_id: str) -> list[dict]:
        return [o for o in self.observations if o.get("model_id") == model_id]

    def _accuracy_for(self, row: dict) -> dict | None:
        provider = row.get("provider_id") or ""
        label = (row.get("provider_name") or "").lower()
        model_id = row.get("model_id")
        for a in self.accuracy:
            if a.get("model_slug") not in {None, model_id}:
                continue
            if a.get("provider_id") == provider or (a.get("provider_name") or "").lower() == label:
                return a
        return None

    def _quality(self, row: dict) -> dict:
        obs = self._accuracy_for(row)
        if not obs:
            return {"status": "not_measured", "observation": None}
        classification = obs.get("classification") or "unknown"
        interval = (obs.get("accuracy") or {})
        if classification == "unknown" and interval.get("lower") is not None and interval.get("upper") is not None:
            classification = "reference_consistent" if interval["lower"] <= 100 <= interval["upper"] else "below_reference"
        status = "measured_good" if classification in {"within_reference", "reference_consistent", "at_reference"} else "measured_degraded" if classification in {"below_reference", "significantly_below", "outside_reference"} else "measured_uncertain"
        return {"status": status, "classification": classification, "observation": obs}

    def best_provider(self, model_id: str, profile: str = "interactive", *, require_accuracy_evidence: bool = False,
                      min_accuracy: float | None = None, allow_unknown: bool = True) -> dict | None:
        rows = self.providers(model_id)
        ranked = []
        for row in rows:
            quality = self._quality(row)
            if require_accuracy_evidence and quality["status"] == "not_measured":
                continue
            if not allow_unknown and quality["status"] in {"not_measured", "measured_uncertain"}:
                continue
            mid = _value(quality.get("observation") or {}, "accuracy", "mid")
            if min_accuracy is not None and (mid is None or mid < min_accuracy):
                continue
            if profile == "accuracy-first" and quality["status"] == "measured_degraded":
                continue
            quality_rank = {"measured_good": 0, "measured_uncertain": 1, "not_measured": 2, "measured_degraded": 3}.get(quality["status"], 4)
            if profile == "batch":
                key = (_availability_rank(row), quality_rank,
                       _value(row, "performance", "throughput_tps") is None,
                       -(_value(row, "performance", "throughput_tps") or 0),
                       _value(row, "pricing", "input_per_million") is None,
                       _value(row, "pricing", "input_per_million") if _value(row, "pricing", "input_per_million") is not None else float("inf"),
                       row.get("provider_id", ""))
            else:
                key = (_availability_rank(row), quality_rank,
                       _value(row, "performance", "latency_seconds") is None,
                       _value(row, "performance", "latency_seconds") if _value(row, "performance", "latency_seconds") is not None else float("inf"),
                       _value(row, "pricing", "input_per_million") is None,
                       _value(row, "pricing", "input_per_million") if _value(row, "pricing", "input_per_million") is not None else float("inf"),
                       row.get("provider_id", ""))
            ranked.append((key, row, quality))
        if not ranked:
            return None
        _, row, quality = min(ranked, key=lambda x: x[0])
        result = dict(row)
        result["endpoint_quality"] = quality
        result["decision"] = {"profile": profile, "require_accuracy_evidence": require_accuracy_evidence,
                              "min_accuracy": min_accuracy, "allow_unknown": allow_unknown,
                              "missing_evidence": quality["status"] == "not_measured"}
        return result

    def independent_fallbacks(self, model_id: str, primary_provider: str, limit: int = 10) -> list[dict]:
        rows = [r for r in self.providers(model_id) if r.get("provider_id") != primary_provider]
        rows.sort(key=lambda r: (-((_value(r, "availability", "uptime_1d") or 0)), r.get("provider_id", "")))
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
        rows.sort(key=lambda o: (-((o.get("scores") or {}).get(metric) or 0), o.get("variant_id") or o.get("agent_id", "")))
        return rows[:limit]

    def cheapest(self, limit: int = 10) -> list[dict]:
        rows = [o for o in self.observations if _number(o.get("cost_per_task_usd")) is not None]
        rows.sort(key=lambda o: (o["cost_per_task_usd"], o.get("variant_id") or o.get("agent_id", "")))
        return rows[:limit]

    def fastest(self, limit: int = 10) -> list[dict]:
        rows = [o for o in self.observations if _number(o.get("execution_time_seconds")) is not None]
        rows.sort(key=lambda o: (o["execution_time_seconds"], o.get("variant_id") or o.get("agent_id", "")))
        return rows[:limit]

    def pareto(self, quality="coding_agent_index", efficiency="cost_per_task_usd") -> list[dict]:
        rows = [o for o in self.observations if _number((o.get("scores") or {}).get(quality)) is not None and _number(o.get(efficiency)) is not None]
        out = []
        for row in rows:
            q, cost = row["scores"][quality], row[efficiency]
            if any(other is not row and other["scores"][quality] >= q and other[efficiency] <= cost and
                   (other["scores"][quality] > q or other[efficiency] < cost) for other in rows):
                continue
            out.append(row)
        return sorted(out, key=lambda o: (-(o["scores"][quality]), o[efficiency], o.get("variant_id", "")))
