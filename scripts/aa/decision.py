"""Transparent model decision engine built on normalized rich records.

This module deliberately keeps recommendation policy explicit: constraints are
applied first, then a documented weighted score ranks survivors. Missing values
are excluded from a metric rather than treated as zero. Results include an
explanation so callers can distinguish evidence from policy.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
from typing import Any, Iterable


PROFILE_VERSION = "1.0"
PROFILE_RICH_VERSION = "2.0"


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
    "best-overall": {"version": PROFILE_RICH_VERSION, "metric": "intelligence_index",
                     "weights": {"quality": 0.85, "cost": 0.05, "speed": 0.10}},
    "available-to-me": {"version": PROFILE_RICH_VERSION, "metric": "intelligence_index",
                        "available_only": True,
                        "weights": {"quality": 0.85, "cost": 0.05, "speed": 0.10}},
    "marginal-cost-aware": {"version": PROFILE_RICH_VERSION, "metric": "intelligence_index",
                             "strategy": "marginal_cost"},
}


def _num(value: Any) -> float | None:
    return value if (isinstance(value, (int, float)) and not isinstance(value, bool)
                     and math.isfinite(value)) else None


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
    version: str = PROFILE_VERSION

    @classmethod
    def from_dict(cls, name: str, values: dict[str, Any]) -> "Profile":
        values = dict(values)
        version = str(values.pop("version", "custom-1"))
        return cls(name=name, constraints=values, version=version)

    @classmethod
    def named(cls, name: str) -> "Profile":
        if name not in PROFILES:
            raise ValueError(f"Unknown profile: {name}; choose from {sorted(PROFILES)}")
        values = dict(PROFILES[name])
        version = str(values.pop("version", PROFILE_VERSION))
        return cls(name=name, constraints=values, version=version)


class DecisionEngine:
    def __init__(self, models: Iterable[dict], access: dict[str, dict] | None = None):
        self.models = [m for m in models if isinstance(m, dict) and m.get("slug")]
        self._by_slug = {m["slug"]: m for m in self.models}
        self.access = access or {}

    def get(self, slug: str) -> dict | None:
        return self._by_slug.get(slug)

    def _availability_state(self, model: dict) -> dict[str, Any]:
        """Return only explicit boolean availability evidence from the local overlay."""
        record = self.access.get(model.get("slug"))
        if not isinstance(record, dict):
            return {"status": "unknown", "available": None}
        available = record.get("available")
        status = "available" if available is True else "unavailable" if available is False else "unknown"
        state = {"status": status, "available": available if isinstance(available, bool) else None}
        for key in ("source", "checked_at", "expires_at", "reason"):
            if key in record:
                state[key] = record[key]
        return state

    def explain(self, model: dict) -> dict:
        return {"slug": model.get("slug"), "name": model.get("name"),
                "sources": _sources(model), "provenance": model.get("provenance", {}),
                "coverage": {"intelligence_index": model.get("intelligence_index") is not None,
                             "coding_index": model.get("coding_index") is not None,
                             "agentic_index": model.get("agentic_index") is not None,
                             "cost": _cost(model) is not None,
                             "speed": _speed(model) is not None},
                "access": self.access.get(model.get("slug"))}

    def _freshness_state(self, model: dict, max_days: int = 14) -> tuple[str, float | None]:
        prov = model.get("provenance") or {}
        if prov.get("fresh") is False:
            return "stale", None
        stamp = prov.get("fetched_at") or model.get("fetched_at")
        if not stamp:
            return "unknown", None
        try:
            when = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - when).total_seconds() / 86400
            if age < 0:
                return "unknown", age
            return ("fresh" if age <= max_days else "stale"), age
        except ValueError:
            return "unknown", None

    def _fresh(self, model: dict, days: int | None) -> bool:
        if days is None:
            return True
        state, _ = self._freshness_state(model, days)
        return state == "fresh"

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
        if c.get("available_only") and self._availability_state(model)["status"] != "available":
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

    def _confidence(self, model: dict, metric: str, weights: dict[str, float]) -> dict[str, Any]:
        metric_fields = [metric]
        if weights.get("cost", 0) > 0:
            metric_fields.append("cost")
        if weights.get("speed", 0) > 0:
            metric_fields.append("speed")
        values = {metric: self._metric_score(model, metric), "cost": _cost(model), "speed": _speed(model)}
        missing = [name for name in metric_fields if values.get(name) is None]
        coverage = round((len(metric_fields) - len(missing)) / len(metric_fields), 3)
        prov = model.get("provenance") or {}
        source_count = len(_sources(model))
        agreement = prov.get("source_agreement", "unknown")
        freshness, age_days = self._freshness_state(model)
        fresh = freshness == "fresh"
        if coverage >= 0.8 and freshness == "fresh" and source_count >= 2 and agreement != "disagree":
            level = "high"
        elif coverage >= 0.5 and agreement != "disagree":
            level = "medium"
        else:
            level = "low"
        return {"level": level, "evidence_coverage": coverage, "missing_metrics": missing,
                "source_count": source_count, "source_agreement": agreement,
                "freshness_days": round(age_days, 2) if age_days is not None else None,
                "fresh": freshness}

    def _marginal_cost_details(self, candidates: list[tuple]) -> dict[str, dict[str, Any]]:
        """Calculate quality gained per extra blended-cost dollar.

        Each model is compared with the highest-quality strictly cheaper
        candidate. The cheapest cost tier uses a zero-quality/zero-cost
        baseline. Equal-cost candidates therefore remain comparable and all
        divisions stay finite, including a zero-cost tier.
        """
        priced = [candidate for candidate in candidates
                  if candidate[2] is not None and math.isfinite(candidate[1])
                  and math.isfinite(candidate[2])]
        details: dict[str, dict[str, Any]] = {}
        for model, quality, cost, _speed_value, _reasons in priced:
            cheaper = [candidate for candidate in priced if candidate[2] < cost]
            baseline = min(cheaper, key=lambda candidate: (
                -candidate[1], candidate[2], candidate[0].get("slug", "")
            )) if cheaper else None
            baseline_quality = baseline[1] if baseline else 0.0
            baseline_cost = baseline[2] if baseline else 0.0
            quality_gain = max(0.0, quality - baseline_quality)
            cost_delta = cost - baseline_cost
            if cost_delta > 0:
                raw_score = quality_gain / cost_delta
                score = raw_score if math.isfinite(raw_score) else 1e12
            else:
                score = quality_gain
            details[model.get("slug", "")] = {
                "baseline_slug": baseline[0].get("slug") if baseline else None,
                "baseline_quality": round(baseline_quality, 6),
                "baseline_cost": round(baseline_cost, 6),
                "quality_gain": round(quality_gain, 6),
                "cost_delta": round(max(0.0, cost_delta), 6),
                "quality_per_cost_delta": round(score, 6),
            }
        return details

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
        strategy = c.pop("strategy", "weighted")
        if strategy not in {"weighted", "marginal_cost"}:
            raise ValueError(f"Unknown recommendation strategy: {strategy}")
        candidates = []
        for m in self.models:
            ok, constraint_reasons = self._matches(m, c)
            quality = self._metric_score(m, metric)
            cost, speed = _cost(m), _speed(m)
            if not ok or quality is None or (strategy == "marginal_cost" and cost is None):
                continue
            candidates.append((m, quality, cost, speed, constraint_reasons))
        max_quality = max((x[1] for x in candidates), default=1.0)
        max_speed = max((x[3] or 0 for x in candidates), default=1.0)
        min_cost = min((x[2] for x in candidates if x[2] is not None), default=0.0)
        max_cost = max((x[2] for x in candidates if x[2] is not None), default=1.0)
        marginal_details = self._marginal_cost_details(candidates) if strategy == "marginal_cost" else {}
        ranked = []
        for m, quality, cost, speed, reasons in candidates:
            marginal = marginal_details.get(m.get("slug"))
            if strategy == "marginal_cost":
                score = marginal["quality_per_cost_delta"]
                metrics_used = [metric, "pricing.blended_3_1", "marginal_quality_gain_per_cost_delta"]
            else:
                q = quality / max_quality if max_quality else 0
                s = (speed or 0) / max_speed if max_speed else 0
                cscore = (max_cost - cost) / (max_cost - min_cost) if cost is not None and max_cost > min_cost else (1.0 if cost is not None else 0.0)
                components = [(weights.get("quality", 0), q)]
                if speed is not None:
                    components.append((weights.get("speed", 0), s))
                if cost is not None:
                    components.append((weights.get("cost", 0), cscore))
                weight_total = sum(weight for weight, _value in components if weight > 0)
                score = (sum(weight * value for weight, value in components if weight > 0)
                         / weight_total if weight_total else 0.0)
                metrics_used = [metric]
                if speed is not None: metrics_used.append("performance.median_output_speed_tps")
                if cost is not None: metrics_used.append("pricing.blended_3_1")
            explanation = {"score": round(score, 6), "strategy": strategy, "metrics_used": metrics_used,
                           "constraints_satisfied": reasons,
                           "missing_metrics": [x for x, v in [("cost", cost), ("speed", speed)] if v is None],
                           "sources": _sources(m), "fresh": self._freshness_state(m)[0],
                           "availability": self._availability_state(m),
                           "confidence": self._confidence(m, metric, weights)}
            if marginal is not None:
                explanation["marginal_cost"] = marginal
            ranked.append((score, m, explanation))
        ranked.sort(key=lambda x: (-x[0], x[1].get("slug", "")))
        output = []
        for score, m, explanation in ranked[:limit]:
            row = dict(m)
            row["recommendation_score"] = explanation["score"]
            row["explanation"] = explanation
            output.append(row)
        return {"profile": p.name, "profile_version": p.version, "strategy": strategy, "metric": metric,
                "candidate_count": len(ranked), "recommendations": output}

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
