"""Transparent model decision engine built on normalized rich records.

This module deliberately keeps recommendation policy explicit: constraints are
applied first, then a documented weighted score ranks survivors. Missing values
are excluded from a metric rather than treated as zero. Results include an
explanation so callers can distinguish evidence from policy.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable


PROFILES: dict[str, dict[str, Any]] = {
    "coding": {"metric": "coding_index", "min_intelligence": 45,
               "weights": {"quality": 0.65, "cost": 0.15, "speed": 0.20}},
    "code-review": {"metric": "coding_index", "min_intelligence": 50,
                    "weights": {"quality": 0.70, "cost": 0.10, "speed": 0.20}},
    "reasoning": {"metric": "intelligence_index", "require_reasoning": True,
                   "weights": {"quality": 0.75, "cost": 0.10, "speed": 0.15}},
    "agentic": {"metric": "agentic_index", "weights": {"quality": 0.65,
                                                            "cost": 0.10,
                                                            "speed": 0.25}},
    "long-context": {"metric": "intelligence_index", "min_context_tokens": 100000,
                      "weights": {"quality": 0.75, "cost": 0.10, "speed": 0.15}},
    "fast": {"metric": "intelligence_index", "min_speed": 80,
              "weights": {"quality": 0.55, "cost": 0.15, "speed": 0.30}},
    "cheap": {"metric": "intelligence_index", "max_cost": 1.0,
              "weights": {"quality": 0.55, "cost": 0.35, "speed": 0.10}},
    "premium": {"metric": "intelligence_index",
                 "weights": {"quality": 0.85, "cost": 0.05, "speed": 0.10}},
}


def _num(value: Any) -> float | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _cost(model: dict) -> float | None:
    p = model.get("pricing") or {}
    b = _num(p.get("blended_3_1"))
    if b is not None:
        return b
    i, o = _num(p.get("input")), _num(p.get("output"))
    return round((3 * i + o) / 4, 6) if i is not None and o is not None else None


def _speed(model: dict) -> float | None:
    return _num((model.get("performance") or {}).get("median_output_speed_tps"))


def _sources(model: dict) -> list[str]:
    prov = model.get("provenance") or {}
    values = prov.get("sources") or []
    if values:
        return sorted({str(v) for v in values})
    merged = model.get("merged") or {}
    return sorted({str(v) for v in [model.get("source"), *merged.get("also_from", [])] if v})


@dataclass(frozen=True)
class Profile:
    name: str
    constraints: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, name: str, values: dict[str, Any]) -> "Profile":
        return cls(name=name, constraints=dict(values))

    @classmethod
    def named(cls, name: str) -> "Profile":
        if name not in PROFILES:
            raise ValueError(f"Unknown profile: {name}; choose from {sorted(PROFILES)}")
        return cls(name=name, constraints=dict(PROFILES[name]))


class DecisionEngine:
    def __init__(self, models: Iterable[dict], access: dict[str, dict] | None = None):
        self.models = [m for m in models if isinstance(m, dict) and m.get("slug")]
        self._by_slug = {m["slug"]: m for m in self.models}
        self.access = access or {}

    def get(self, slug: str) -> dict | None:
        return self._by_slug.get(slug)

    def explain(self, model: dict) -> dict:
        return {"slug": model.get("slug"), "name": model.get("name"),
                "sources": _sources(model), "provenance": model.get("provenance", {}),
                "coverage": {"intelligence_index": model.get("intelligence_index") is not None,
                             "coding_index": model.get("coding_index") is not None,
                             "agentic_index": model.get("agentic_index") is not None,
                             "cost": _cost(model) is not None,
                             "speed": _speed(model) is not None},
                "access": self.access.get(model.get("slug"))}

    def _fresh(self, model: dict, days: int | None) -> bool:
        if days is None:
            return True
        prov = model.get("provenance") or {}
        if prov.get("fresh") is False:
            return False
        stamp = prov.get("fetched_at") or model.get("fetched_at")
        if not stamp:
            return False
        try:
            when = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - when).total_seconds() / 86400
            return 0 <= age <= days
        except ValueError:
            return False

    def _matches(self, model: dict, c: dict[str, Any]) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        checks = {
            "min_intelligence": (model.get("intelligence_index"), ">="),
            "min_coding": (model.get("coding_index"), ">="),
            "min_agentic": (model.get("agentic_index"), ">="),
            "min_context_tokens": (model.get("context_tokens"), ">="),
            "min_speed": (_speed(model), ">="),
            "max_cost": (_cost(model), "<="),
            "max_ttft": ((model.get("performance") or {}).get("median_ttft_seconds"), "<="),
        }
        for key, (actual, op) in checks.items():
            expected = _num(c.get(key))
            if expected is None:
                continue
            if actual is None or (op == ">=" and actual < expected) or (op == "<=" and actual > expected):
                return False, reasons
            reasons.append(f"{key} {op} {expected:g}")
        if c.get("require_reasoning") is True and model.get("is_reasoning") is not True:
            return False, reasons
        if c.get("open_weights") is True and model.get("is_open_weights") is not True:
            return False, reasons
        if c.get("provider") and c["provider"] not in {h.get("slug") or h.get("name") for h in model.get("hosts", [])}:
            return False, reasons
        if c.get("creator") and model.get("creator") != c["creator"]:
            return False, reasons
        if c.get("available_only") and not self.access.get(model.get("slug"), {}).get("available"):
            return False, reasons
        modalities = c.get("modalities") or []
        available = set((model.get("input_modalities") or {}).keys()) | set((model.get("output_modalities") or {}).keys())
        if any(m not in available for m in modalities):
            return False, reasons
        if not self._fresh(model, c.get("fresh_within_days")):
            return False, reasons
        return True, reasons

    def _metric_score(self, model: dict, metric: str) -> float | None:
        return _num(model.get(metric))

    def recommend(self, profile: str | Profile | dict[str, Any] | None = None, *, limit: int = 10,
                  available_only: bool = False) -> dict[str, Any]:
        if profile is None:
            p = Profile.named("premium")
        elif isinstance(profile, str):
            p = Profile.named(profile)
        elif isinstance(profile, Profile):
            p = profile
        else:
            p = Profile.from_dict("custom", profile)
        c = dict(p.constraints)
        c["available_only"] = available_only or c.get("available_only", False)
        metric = c.pop("metric", "intelligence_index")
        weights = c.pop("weights", {"quality": 1.0, "cost": 0.0, "speed": 0.0})
        candidates = []
        for m in self.models:
            ok, constraint_reasons = self._matches(m, c)
            quality = self._metric_score(m, metric)
            cost, speed = _cost(m), _speed(m)
            if not ok or quality is None:
                continue
            candidates.append((m, quality, cost, speed, constraint_reasons))
        max_quality = max((x[1] for x in candidates), default=1.0)
        max_speed = max((x[3] or 0 for x in candidates), default=1.0)
        min_cost = min((x[2] for x in candidates if x[2] is not None), default=0.0)
        max_cost = max((x[2] for x in candidates if x[2] is not None), default=1.0)
        ranked = []
        for m, quality, cost, speed, reasons in candidates:
            q = quality / max_quality if max_quality else 0
            s = (speed or 0) / max_speed if max_speed else 0
            cscore = (max_cost - cost) / (max_cost - min_cost) if cost is not None and max_cost > min_cost else (1.0 if cost is not None else 0.0)
            score = weights.get("quality", 0) * q + weights.get("speed", 0) * s + weights.get("cost", 0) * cscore
            metrics_used = [metric]
            if speed is not None: metrics_used.append("performance.median_output_speed_tps")
            if cost is not None: metrics_used.append("pricing.blended_3_1")
            ranked.append((score, m, {"score": round(score, 6), "metrics_used": metrics_used,
                                      "constraints_satisfied": reasons, "missing_metrics": [x for x, v in [("cost", cost), ("speed", speed)] if v is None],
                                      "sources": _sources(m), "fresh": self._fresh(m, None)}))
        ranked.sort(key=lambda x: (-x[0], x[1].get("slug", "")))
        output = []
        for score, m, explanation in ranked[:limit]:
            row = dict(m)
            row["recommendation_score"] = explanation["score"]
            row["explanation"] = explanation
            output.append(row)
        return {"profile": p.name, "metric": metric, "candidate_count": len(ranked), "recommendations": output}

    def pareto(self, dimensions: list[str]) -> list[dict]:
        """Return non-dominated models; dimensions prefixed ``-`` are minimized.
        Known cost dimensions are minimized, all others are maximized."""
        values = []
        for m in self.models:
            row = []
            valid = True
            for dim in dimensions:
                name = dim.lstrip("-")
                value = _cost(m) if name == "cost" else self._metric_score(m, name)
                if value is None:
                    valid = False
                    break
                maximize = not (name == "cost" or dim.startswith("-"))
                row.append((value, maximize))
            if valid:
                values.append((m, row))
        frontier = []
        for candidate, cvals in values:
            dominated = False
            for other, ovals in values:
                if other is candidate:
                    continue
                no_worse = all((ov >= cv if maximize else ov <= cv) for (ov, maximize), (cv, _) in zip(ovals, cvals))
                strictly = any((ov > cv if maximize else ov < cv) for (ov, maximize), (cv, _) in zip(ovals, cvals))
                if no_worse and strictly:
                    dominated = True
                    break
            if not dominated:
                frontier.append(candidate)
        return sorted(frontier, key=lambda m: m.get("slug", ""))

    def backups(self, primary_slug: str, *, creators: bool = True, providers: bool = True,
                families: bool = False, limit: int = 10) -> list[dict]:
        primary = self._by_slug.get(primary_slug)
        if not primary:
            return []
        p_hosts = {h.get("slug") or h.get("name") for h in primary.get("hosts", [])}
        p_creator = primary.get("creator")
        p_family = str(primary.get("slug", "")).split("-")[0]
        out = []
        for m in self.models:
            if m is primary:
                continue
            if creators and m.get("creator") == p_creator:
                continue
            hosts = {h.get("slug") or h.get("name") for h in m.get("hosts", [])}
            if providers and p_hosts & hosts:
                continue
            if families and str(m.get("slug", "")).split("-")[0] == p_family:
                continue
            if _num(m.get("intelligence_index")) is not None:
                out.append(m)
        out.sort(key=lambda m: (-m.get("intelligence_index", 0), m.get("slug", "")))
        return out[:limit]
