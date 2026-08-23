"""Behavioral contract tests for recommendations and the stable CLI helpers."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))

from aa.decision import DecisionEngine, Profile  # noqa: E402
from aa import schema  # noqa: E402


def model(slug, creator, score, cost, speed, *, context=128000,
          reasoning=True, open_weights=False, provider="p1", fresh=True):
    row = schema.model_record_template()
    row.update({
        "slug": slug, "name": slug, "creator": creator,
        "creator_slug": creator.lower(), "intelligence_index": score,
        "coding_index": score, "agentic_index": score,
        "is_reasoning": reasoning, "is_open_weights": open_weights,
        "context_tokens": context,
        "pricing": {"input": cost, "output": cost * 4,
                    "blended_3_1": cost * 1.75, "blended_7_2_1": None,
                    "blended_1_1": None, "cache_hit": None, "cache_write": None},
        "performance": {"median_output_speed_tps": speed,
                         "median_ttft_seconds": 1.0,
                         "median_ttfa_seconds": 1.0,
                         "median_e2e_500tok_seconds": None,
                         "percentiles": None, "by_prompt_length": []},
        "hosts": [{"name": provider, "slug": provider}],
        "provenance": {"fresh": fresh, "fetched_at": "2026-08-22T00:00:00Z",
                       "sources": ["fixture"]},
    })
    return row


def engine():
    return DecisionEngine([
        model("alpha", "A", 90, 1, 100, provider="pa"),
        model("beta", "B", 85, 0.5, 80, provider="pb", context=64000),
        model("gamma", "C", 70, 0.2, 200, provider="pc", open_weights=True),
        model("delta", "A", 60, 0.4, 20, provider="pa", fresh=False),
    ])


def test_constraints_and_explanations_are_deterministic():
    result = engine().recommend({"min_intelligence": 80, "max_cost": 2.0,
                                 "min_context_tokens": 100000,
                                 "fresh_within_days": 30}, limit=10)
    assert [r["slug"] for r in result["recommendations"]] == ["alpha"]
    assert result["recommendations"][0]["explanation"]["metrics_used"]
    assert result["recommendations"][0]["explanation"]["sources"] == ["fixture"]


def test_pareto_frontier_excludes_dominated_models():
    rows = engine().pareto(["intelligence_index", "cost"])
    slugs = [r["slug"] for r in rows]
    assert "delta" not in slugs
    assert set(slugs) == {"alpha", "beta", "gamma"}


def test_backup_requires_independence():
    result = engine().backups("alpha", creators=True, providers=True, limit=10)
    assert [r["slug"] for r in result] == ["beta", "gamma"]


def test_profiles_are_configuration_not_scattered_logic():
    profile = Profile.from_dict("cheap", {"max_cost": 1.0, "min_intelligence": 65})
    result = engine().recommend(profile, limit=10)
    assert [r["slug"] for r in result["recommendations"]] == ["beta", "gamma"]


def test_freshness_is_fresh_stale_or_unknown_not_always_true():
    fresh = model("fresh", "F", 90, 1, 100)
    fresh["provenance"]["fetched_at"] = "2026-08-23T00:00:00Z"
    stale = model("stale", "S", 89, 1, 100)
    stale["provenance"]["fetched_at"] = "2026-07-01T00:00:00Z"
    unknown = model("unknown", "U", 88, 1, 100)
    unknown["provenance"].pop("fetched_at")
    rows = engine()
    rows.models.extend([fresh, stale, unknown])
    result = rows.recommend("premium", limit=10)
    states = {r["slug"]: r["explanation"]["fresh"] for r in result["recommendations"]}
    assert states["fresh"] == "fresh"
    assert states["stale"] == "stale"
    assert states["unknown"] == "unknown"


def test_naive_timestamp_is_interpreted_as_utc():
    row = model("naive", "N", 87, 1, 100)
    row["provenance"]["fetched_at"] = "2026-08-23T00:00:00"
    result = DecisionEngine([row]).recommend("premium")
    assert result["recommendations"][0]["explanation"]["fresh"] == "fresh"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("All decision tests passed.")
