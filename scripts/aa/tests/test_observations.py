"""Tests for provider observations, confidence, and source identity."""
from __future__ import annotations
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
from aa.observations import normalize_openrouter_endpoint, source_authority  # noqa: E402
from aa.coding_agent_source import parse_datasets  # noqa: E402
from aa.provider_query import ProviderDB, CodingAgentDB  # noqa: E402
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


def test_provider_and_agent_queries_are_source_specific():
    endpoint = normalize_openrouter_endpoint({"model_id": "m", "provider_name": "A", "tag": "a", "latency_last_30m": 1.0, "status": 0}, fetched_at="t")
    endpoint2 = normalize_openrouter_endpoint({"model_id": "m", "provider_name": "B", "tag": "b", "latency_last_30m": 2.0, "status": 0}, fetched_at="t")
    db = ProviderDB([endpoint, endpoint2])
    assert db.best_provider("m")["provider_id"] == "a"
    agents = CodingAgentDB([{"agent_id": "a", "scores": {"coding_agent_index": 0.5}}, {"agent_id": "b", "scores": {"coding_agent_index": 0.7}}])
    assert agents.best()[0]["agent_id"] == "b"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("All observation/confidence tests passed.")
