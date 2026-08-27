"""Behavioral contract tests for recommendations and the stable CLI helpers."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))

from aa.decision import DecisionEngine, Profile, PROFILES  # noqa: E402
from aa import schema  # noqa: E402
from aa.query import AADB  # noqa: E402
try:
    from _runner import run_tests  # noqa: E402
except ModuleNotFoundError:  # pytest imports this module from the repository root
    from scripts.aa.tests._runner import run_tests  # noqa: E402


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


def test_phase5_named_profiles_expose_version_and_strategy():
    assert {"best-overall", "available-to-me", "marginal-cost-aware"} <= set(PROFILES)
    best = engine().recommend("best-overall", limit=1)
    assert best["profile_version"] == "2.0"
    assert best["strategy"] == "weighted"
    assert best["recommendations"][0]["explanation"]["strategy"] == "weighted"


def test_weighted_profiles_renormalize_around_unknown_metrics():
    complete = model("complete", "C", 90, 1.0, 100)
    partial = model("partial", "P", 88, 1.0, 100)
    partial["pricing"] = {key: None for key in partial["pricing"]}
    partial["performance"]["median_output_speed_tps"] = None
    result = DecisionEngine([complete, partial]).recommend("best-overall", limit=10)
    row = next(item for item in result["recommendations"] if item["slug"] == "partial")
    assert row["explanation"]["metrics_used"] == ["intelligence_index"]
    assert row["explanation"]["missing_metrics"] == ["cost", "speed"]
    assert row["recommendation_score"] > 0.9


def test_nonfinite_constraint_metrics_fail_closed():
    bad_context = model("bad-context", "B", 90, 1.0, 100)
    bad_context["context_tokens"] = float("nan")
    bad_ttft = model("bad-ttft", "T", 90, 1.0, 100)
    bad_ttft["performance"]["median_ttft_seconds"] = float("nan")
    bad_index = model("bad-index", "I", 90, 1.0, 100)
    bad_index["intelligence_index"] = float("inf")

    context_result = DecisionEngine([bad_context]).recommend(
        {"min_context_tokens": 100000}, limit=10)
    ttft_result = DecisionEngine([bad_ttft]).recommend(
        {"max_ttft": 2.0}, limit=10)
    index_result = DecisionEngine([bad_index]).recommend(
        {"min_intelligence": 80}, limit=10)
    assert context_result["candidate_count"] == 0
    assert ttft_result["candidate_count"] == 0
    assert index_result["candidate_count"] == 0


def test_nonfinite_model_fields_are_unknown_in_recommendation_json():
    row = model("nonfinite", "N", 90, 1.0, 100)
    row["performance"]["median_output_speed_tps"] = float("nan")
    row["provenance"]["extra_metric"] = float("inf")
    result = DecisionEngine([row]).recommend("best-overall", limit=1)
    json.dumps(result, allow_nan=False)
    output = result["recommendations"][0]
    assert output["performance"]["median_output_speed_tps"] is None
    assert output["provenance"]["extra_metric"] is None


def test_oversized_numeric_inputs_are_unknown_and_derived_cost_overflow_is_excluded():
    huge_index = model("huge-index", "H", 90, 1.0, 100)
    huge_index["intelligence_index"] = 10 ** 1000
    assert DecisionEngine([huge_index]).recommend(
        {"min_intelligence": 80}, limit=10)["candidate_count"] == 0

    overflowed_cost = model("overflowed-cost", "O", 90, 1.0, 100)
    overflowed_cost["pricing"] = {key: None for key in overflowed_cost["pricing"]}
    overflowed_cost["pricing"].update({"input": 1e308, "output": 1e308})
    valid = model("valid", "V", 70, 0.0, 100)
    result = DecisionEngine([overflowed_cost, valid]).recommend(
        "marginal-cost-aware", limit=10)
    assert [row["slug"] for row in result["recommendations"]] == ["valid"]


def test_invalid_performance_and_index_values_remain_unknown():
    bad_speed = model("bad-speed", "S", 90, 1.0, 0.0)
    bad_ttft = model("bad-ttft", "T", 90, 1.0, 100)
    bad_ttft["performance"]["median_ttft_seconds"] = -1.0
    bad_index = model("bad-index", "I", 101, 1.0, 100)

    speed_result = DecisionEngine([bad_speed]).recommend("best-overall", limit=1)
    assert speed_result["candidate_count"] == 1
    assert speed_result["recommendations"][0]["explanation"]["missing_metrics"] == ["speed"]
    assert DecisionEngine([bad_ttft]).recommend(
        {"max_ttft": 2.0}, limit=10)["candidate_count"] == 0
    assert DecisionEngine([bad_index]).recommend(
        {"min_intelligence": 80}, limit=10)["candidate_count"] == 0


def test_negative_prices_are_unknown_and_never_cost_baselines():
    negative = model("negative", "N", 99, 1.0, 100)
    negative["pricing"]["blended_3_1"] = -1.0
    valid = model("valid", "V", 70, 0.0, 100)
    result = DecisionEngine([negative, valid]).recommend(
        "marginal-cost-aware", limit=10)
    assert [row["slug"] for row in result["recommendations"]] == ["valid"]


def test_available_to_me_requires_explicit_boolean_access_evidence():
    access = {
        "alpha": {"available": False, "source": "fixture"},
        "beta": {"available": True, "source": "fixture"},
        "gamma": {"available": "true", "source": "fixture"},
        "delta": {"available": True, "source": "fixture"},
    }
    result = DecisionEngine(engine().models, access=access).recommend("available-to-me", limit=10)
    assert {r["slug"] for r in result["recommendations"]} == {"beta", "delta"}
    assert all(r["explanation"]["availability"]["status"] == "available"
               for r in result["recommendations"])


def test_aadb_accepts_access_overlay_for_available_profile():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "models.json"
        path.write_text(json.dumps({"models": [model("local", "L", 80, 1, 100)]}),
                        encoding="utf-8")
        result = AADB(path, access={"local": {"available": True}}).recommend(
            "available-to-me", limit=1)
    assert [row["slug"] for row in result["recommendations"]] == ["local"]


def test_marginal_cost_profile_explains_gain_and_excludes_unknown_cost():
    entry = model("entry", "E", 70, 0.1, 100)
    middle = model("middle", "M", 85, 0.5, 100)
    top = model("top", "T", 90, 5.0, 100)
    free = model("free", "F", 75, 0.0, 100)
    unknown = model("unknown-cost", "U", 95, 1.0, 100)
    unknown["pricing"] = {key: None for key in unknown["pricing"]}

    result = DecisionEngine([entry, middle, top, free, unknown]).recommend(
        "marginal-cost-aware", limit=10)
    rows = {row["slug"]: row for row in result["recommendations"]}
    assert result["strategy"] == "marginal_cost"
    assert "unknown-cost" not in rows
    assert result["recommendations"][0]["slug"] == "free"
    assert rows["top"]["explanation"]["marginal_cost"]["baseline_slug"] == "middle"
    assert rows["top"]["explanation"]["marginal_cost"]["quality_gain"] == 5.0
    assert rows["free"]["explanation"]["marginal_cost"]["cost_delta"] == 0.0
    json.dumps(result, allow_nan=False)


def test_marginal_cost_equal_scores_use_stable_slug_order():
    first = model("alpha", "A", 75, 0.0, 100)
    second = model("beta", "B", 75, 0.0, 100)
    result = DecisionEngine([second, first]).recommend("marginal-cost-aware", limit=10)
    assert [row["slug"] for row in result["recommendations"]] == ["alpha", "beta"]


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


def test_stale_complete_evidence_is_not_high_confidence():
    row = model("stale-complete", "S", 87, 1, 100)
    row["provenance"].update({"fetched_at": "2026-07-01T00:00:00Z", "sources": ["rsc", "api"]})
    result = DecisionEngine([row]).recommend("premium")
    assert result["recommendations"][0]["explanation"]["confidence"]["level"] != "high"


if __name__ == "__main__":
    run_tests(globals(), "All decision tests passed.")
