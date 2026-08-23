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
    def __init__(self, observations=None, accuracy=None, identity=None):
        self.observations = list(observations or [])
        self.accuracy = list(accuracy or [])
        self.identity = identity or {}
        self.mappings = [m for m in self.identity.get("mappings", []) if m.get("state") in {"verified", "manual"}]

    @classmethod
    def from_file(cls, path: str | Path, accuracy_path: str | Path | None = None,
                  identity_path: str | Path | None = None):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        accuracy = []
        if accuracy_path and Path(accuracy_path).exists():
            accuracy = json.loads(Path(accuracy_path).read_text(encoding="utf-8")).get("observations", [])
        identity = {}
        if identity_path and Path(identity_path).exists():
            identity = json.loads(Path(identity_path).read_text(encoding="utf-8"))
        return cls(data.get("observations", []), accuracy, identity)

    def _model_mapping(self, aa_model_id: str) -> dict | None:
        return next((m for m in self.mappings if m.get("relation") == "model_to_model"
                     and m.get("target_entity_id") == aa_model_id), None)

    def providers(self, model_id: str) -> list[dict]:
        mapped = self._model_mapping(model_id)
        operational_id = mapped.get("source_entity_id") if mapped else model_id
        return [o for o in self.observations if o.get("model_id") == operational_id]

    def _accuracy_for(self, row: dict, aa_model_id: str | None = None) -> tuple[dict | None, dict | None]:
        provider = row.get("provider_id") or ""
        provider_namespace = provider.split("/", 1)[0]
        model_map = self._model_mapping(aa_model_id or row.get("model_id", ""))
        if self.identity and not model_map:
            return None, None
        provider_map = next((m for m in self.mappings if m.get("relation") == "provider_to_provider"
                             and m.get("source_entity_id") == provider_namespace), None)
        allowed_providers = {provider, provider_namespace}
        if provider_map:
            allowed_providers.add(provider_map.get("target_entity_id"))
        for a in self.accuracy:
            if aa_model_id and a.get("model_slug") != aa_model_id:
                continue
            if not aa_model_id and a.get("model_slug") not in {None, row.get("model_id")}:
                continue
            if a.get("provider_id") in allowed_providers or (a.get("provider_name") or "").lower() == (row.get("provider_name") or "").lower():
                return a, provider_map
        return None, provider_map

    def _quality(self, row: dict, aa_model_id: str | None = None) -> dict:
        obs, provider_map = self._accuracy_for(row, aa_model_id)
        if not obs:
            return {"status": "not_measured", "observation": None, "mapping_evidence": {"model": self._model_mapping(aa_model_id or row.get("model_id", "")), "provider": provider_map}}
        classification = obs.get("classification") or obs.get("derived_classification") or "unknown"
        interval = obs.get("accuracy") or {}
        if classification == "unknown":
            if interval.get("lower") is not None and interval.get("upper") is not None:
                classification = "reference_consistent" if interval["lower"] <= 100 <= interval["upper"] else "below_reference" if interval["upper"] < 100 else "above_reference"
        status = "measured_good" if classification in {"within_reference", "reference_consistent", "at_reference"} else "measured_degraded" if classification in {"below_reference", "significantly_below", "outside_reference", "above_reference"} else "measured_uncertain"
        return {"status": status, "classification": classification, "observation": obs,
                "mapping_evidence": {"model": self._model_mapping(aa_model_id or row.get("model_id", "")), "provider": provider_map}}

    def best_provider(self, model_id: str, profile: str = "interactive", *, require_accuracy_evidence: bool = False,
                      min_accuracy: float | None = None, allow_unknown: bool = True) -> dict | None:
        rows = self.providers(model_id)
        ranked = []
        for row in rows:
            quality = self._quality(row, model_id)
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
                key = (_availability_rank(row), quality_rank, _value(row, "performance", "throughput_tps") is None, -(_value(row, "performance", "throughput_tps") or 0), _value(row, "pricing", "input_per_million") is None, _value(row, "pricing", "input_per_million") if _value(row, "pricing", "input_per_million") is not None else float("inf"), row.get("provider_id", ""))
            else:
                key = (_availability_rank(row), quality_rank, _value(row, "performance", "latency_seconds") is None, _value(row, "performance", "latency_seconds") if _value(row, "performance", "latency_seconds") is not None else float("inf"), _value(row, "pricing", "input_per_million") is None, _value(row, "pricing", "input_per_million") if _value(row, "pricing", "input_per_million") is not None else float("inf"), row.get("provider_id", ""))
            ranked.append((key, row, quality))
        if not ranked:
            return None
        _, row, quality = min(ranked, key=lambda x: x[0])
        result = dict(row); result["endpoint_quality"] = quality
        result["decision"] = {"profile": profile, "require_accuracy_evidence": require_accuracy_evidence, "min_accuracy": min_accuracy, "allow_unknown": allow_unknown, "missing_evidence": quality["status"] == "not_measured", "identity_policy": "verified_or_manual_only" if self.identity else "direct_fixture_identity"}
        return result

    def independent_fallbacks(self, model_id: str, primary_provider: str, limit: int = 10) -> list[dict]:
        rows = [r for r in self.providers(model_id) if r.get("provider_id") != primary_provider]
        rows.sort(key=lambda r: (-((_value(r, "availability", "uptime_1d") or 0)), r.get("provider_id", "")))
        return rows[:limit]


class CodingAgentDB:
    def __init__(self, observations=None): self.observations = list(observations or [])
    @classmethod
    def from_file(cls, path: str | Path): return cls(json.loads(Path(path).read_text(encoding="utf-8")).get("observations", []))
    def best(self, metric: str = "coding_agent_index", limit: int = 10):
        rows = [o for o in self.observations if _number((o.get("scores") or {}).get(metric)) is not None]
        return sorted(rows, key=lambda o: (-((o.get("scores") or {}).get(metric) or 0), o.get("variant_id") or o.get("agent_id", "")))[:limit]
    def cheapest(self, limit: int = 10):
        rows = [o for o in self.observations if _number(o.get("cost_per_task_usd")) is not None]
        return sorted(rows, key=lambda o: (o["cost_per_task_usd"], o.get("variant_id") or o.get("agent_id", "")))[:limit]
    def fastest(self, limit: int = 10):
        rows = [o for o in self.observations if _number(o.get("execution_time_seconds")) is not None]
        return sorted(rows, key=lambda o: (o["execution_time_seconds"], o.get("variant_id") or o.get("agent_id", "")))[:limit]
    def pareto(self, quality="coding_agent_index", efficiency="cost_per_task_usd"):
        rows = [o for o in self.observations if _number((o.get("scores") or {}).get(quality)) is not None and _number(o.get(efficiency)) is not None]
        out = [r for r in rows if not any(other is not r and other["scores"][quality] >= r["scores"][quality] and other[efficiency] <= r[efficiency] and (other["scores"][quality] > r["scores"][quality] or other[efficiency] < r[efficiency]) for other in rows)]
        return sorted(out, key=lambda o: (-(o["scores"][quality]), o[efficiency], o.get("variant_id", "")))
