"""Tests for provider observations, confidence, and source identity."""
from __future__ import annotations
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
from aa.observations import normalize_openrouter_endpoint, source_authority  # noqa: E402
from aa.coding_agent_source import parse_datasets  # noqa: E402
from aa.provider_query import ProviderDB, CodingAgentDB  # noqa: E402
from aa.openrouter_source import select_cohort, merge_retained_observations  # noqa: E402
from aa.decision import DecisionEngine  # noqa: E402


def test_openrouter_endpoint_preserves_provider_specific_fields():
    raw = {
        "model_id": "openai/gpt-x", "provider_name": "Provider A", "tag": "provider-a",
        "context_length": 128000, "pricing": {"prompt": "0.000001", "completion": "0.000004"},
        "quantization": "int4", "supported_parameters": ["tools"],
        "uptime_last_1d": 99.5, "latency_last_30m": 1.2, "throughput_last_30m": 80,
        "status": 0,
    }
    out = normalize_openrouter_endpoint(raw, fetched_at="2026-08-23T00:00:00Z")
    assert out["model_id"] == "openai/gpt-x"
    assert out["provider_id"] == "provider-a"
    assert out["identity_key"] == "openai/gpt-x:provider-a:openai/gpt-x"
    assert out["pricing"]["input_per_million"] == 1.0
    assert out["pricing"]["output_per_million"] == 4.0
    assert out["availability"]["status"] == "available"
    assert out["provenance"]["source"] == "openrouter"


def test_source_authority_does_not_overwrite_benchmark_truth():
    assert source_authority("intelligence_index") == "artificial_analysis"
    assert source_authority("provider_latency") == "openrouter"
    assert source_authority("context_tokens") == "source_specific"


def test_confidence_separates_coverage_from_rank():
    model = {"slug": "m", "name": "M", "intelligence_index": 90,
             "creator": "C", "source": "rsc", "provenance": {
                 "sources": ["rsc"], "fetched_at": "2026-08-23T00:00:00Z"},
             "pricing": {}, "performance": {}}
    result = DecisionEngine([model]).recommend("premium")
    explanation = result["recommendations"][0]["explanation"]
    assert explanation["confidence"]["level"] in {"low", "medium", "high"}
    assert "cost" in explanation["confidence"]["missing_metrics"]


def test_coding_agent_fixture_remains_separate_observation():
    page = (Path(__file__).parent / "fixtures" / "coding_agents_minimal.html").read_text()
    rows = parse_datasets(page, fetched_at="2026-08-23T00:00:00Z")
    assert len(rows) == 3
    assert {r["observation_type"] for r in rows} == {"coding_agent"}
    assert {r["benchmark_suite"] for r in rows} == {"Coding Agent Index", "Time per Task", "Cost per Task"}
    assert {r["benchmark_version"] for r in rows} == {"1.3"}


def test_coding_agent_version_is_order_independent():
    lines = (Path(__file__).parent / "fixtures" / "coding_agents_minimal.html").read_text().splitlines()
    rows = parse_datasets("\n".join(lines[1:] + lines[:1]), fetched_at="2026-08-23T00:00:00Z")
    assert {r["benchmark_version"] for r in rows} == {"1.3"}


def test_provider_and_agent_queries_are_source_specific():
    endpoint = normalize_openrouter_endpoint({"model_id": "m", "provider_name": "A", "tag": "a", "latency_last_30m": 1.0, "status": 0}, fetched_at="t")
    endpoint2 = normalize_openrouter_endpoint({"model_id": "m", "provider_name": "B", "tag": "b", "latency_last_30m": 2.0, "status": 0}, fetched_at="t")
    db = ProviderDB([endpoint, endpoint2])
    assert db.best_provider("m")["provider_id"] == "a"
    agents = CodingAgentDB([{"agent_id": "a", "scores": {"coding_agent_index": 0.5}}, {"agent_id": "b", "scores": {"coding_agent_index": 0.7}}])
    assert agents.best()[0]["agent_id"] == "b"


def test_provider_profiles_use_latency_vs_throughput_and_keep_zero_prices():
    def endpoint(provider, latency, throughput, price, status=0):
        return normalize_openrouter_endpoint({"model_id": "m2", "provider_name": provider,
            "tag": provider.lower(), "latency_last_30m": latency,
            "throughput_last_30m": throughput, "status": status,
            "pricing": {"prompt": str(price), "completion": "0.000001"}}, fetched_at="t")
    db = ProviderDB([endpoint("FreeFastBatch", 5, 100, 0),
                    endpoint("PaidInteractive", 1, 10, 0.00001),
                    endpoint("Unavailable", 0, 1000, 0, status=1)])
    assert db.best_provider("m2", "interactive")["provider_id"] == "paidinteractive"
    assert db.best_provider("m2", "batch")["provider_id"] == "freefastbatch"


def test_provider_missing_metrics_and_ties_are_deterministic():
    def endpoint(provider, **kwargs):
        return normalize_openrouter_endpoint({"model_id": "m3", "provider_name": provider,
            "tag": provider.lower(), "status": 0, **kwargs}, fetched_at="t")
    db = ProviderDB([endpoint("Zed", pricing={"prompt": "0.000001"}),
                    endpoint("Alpha", pricing={"prompt": "0.000001"})])
    assert db.best_provider("m3")["provider_id"] == "alpha"


def test_rotating_cohort_is_deterministic_and_not_catalog_prefix():
    catalog = [{"id": f"vendor/model-{i}"} for i in range(10)]
    first = select_cohort(catalog, limit=3, cursor=0)
    second = select_cohort(catalog, limit=3, cursor=3)
    assert first == ["vendor/model-0", "vendor/model-1", "vendor/model-2"]
    assert second == ["vendor/model-3", "vendor/model-4", "vendor/model-5"]
    assert select_cohort(catalog, limit=3, cursor=0) == first


def test_retention_preserves_recent_observations_and_expires_old():
    previous = [{"model_id": "m", "provider_id": "p", "endpoint_id": "e",
                 "provenance": {"last_seen": "2026-08-20T00:00:00Z"}}]
    kept = merge_retained_observations(previous, [], now="2026-08-23T00:00:00Z", retention_days=7)
    expired = merge_retained_observations(previous, [], now="2026-08-30T00:00:00Z", retention_days=7)
    assert len(kept) == 1
    assert expired == []
    duplicate = merge_retained_observations(previous, previous + previous, now="2026-08-23T00:00:00Z", retention_days=7)
    assert len(duplicate) == 1


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("All observation/confidence tests passed.")
