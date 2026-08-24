#!/usr/bin/env python3
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from aa import endpoint_accuracy as endpoint_module
from aa.endpoint_accuracy import parse_page, merge_models
from aa.coding_agent_source import parse_datasets_rich
from aa.identity import resolve
from aa.provider_query import ProviderDB
from aa.history import diff_observations
from aa.phase3_artifacts import build_artifacts

FIX = Path(__file__).parent / "fixtures"

def ok(name): print("PASS", name)

endpoint = parse_page((FIX / "endpoint_accuracy_minimal.html").read_text(), source_url="https://artificialanalysis.ai/models/model-a/providers", fetched_at="2026-08-23T00:00:00Z")
assert endpoint["observation_count"] == 2
assert endpoint["observations"][0]["accuracy"]["lower"] == 97
assert endpoint["observations"][1]["classification"] == "significantly_below"
assert endpoint["observations"][1]["derived_classification"] is None
no_source_class = parse_page('<script type="application/ld+json">{"name":"Endpoint Accuracy Index","description":"v1.0","data":[{"label":"Above","endpointAccuracyIndex":[{"name":"mid","value":105},{"name":"lower","value":102},{"name":"upper","value":108}]}]}</script>', source_url="https://artificialanalysis.ai/models/model-a/providers", fetched_at="2026-08-23T00:00:00Z")
assert no_source_class["observations"][0]["classification"] == "unknown" and no_source_class["observations"][0]["derived_classification"] == "above_reference"
ok("endpoint fixture, interval, classification, point-in-time fields")

merged = merge_models({"model_results": [{"model_slug": "old", "fetched_at": "2026-08-20T00:00:00Z", "observations": [{"model_slug": "old"}]}]}, [endpoint], [{"model_slug": "missing", "error": "no dataset"}], now="2026-08-23T00:00:00Z", retention_days=14)
assert merged["coverage"]["retained_stale_models"] == 1 and merged["errors"][0]["model_slug"] == "missing"
assert merged["coverage"]["models"] == 2
ok("bounded multi-model merge, per-model errors, and retention")

agents = parse_datasets_rich((FIX / "coding_agents_rich.html").read_text(), fetched_at="2026-08-23T00:00:00Z")
assert len(agents) == 1 and agents[0]["scores"]["coding_agent_index"] == 0.8
assert agents[0]["cost_per_task_usd"] == 0.12 and agents[0]["configuration"] == "xhigh"
ok("coding-agent metric merge and variant/configuration")

models = [{"slug": "model-a", "name": "Model A"}, {"slug": "model-b", "name": "Model B"}]
router = [{"model_id": "model-a"}, {"model_id": "unknown/model"}]
health = resolve(models, router)["health"]
assert health["model_mappings"]["candidate"] == 1 and health["unresolved_models"] == 1
assert health["openrouter_model_count"] == 2 and health["openrouter_endpoint_count"] == 2
ok("deduplicated model/provider identity health without silent join")

candidate_only = {"mappings": [{"relation": "model_to_model", "source_entity_id": "model-a", "target_entity_id": "model-a", "state": "candidate"}]}
assert ProviderDB([{"model_id": "model-a"}], [], candidate_only).providers("model-a") == []
assert ProviderDB([{"model_id": "model-a"}], [], {}).providers("model-a") == []
ok("candidate and raw-id model fallbacks are rejected when identity is configured")

providers = [
 {"model_id":"model-a","provider_id":"good","provider_name":"Good Provider","availability":{"status":"available"},"performance":{"latency_seconds":2},"pricing":{"input_per_million":1}},
 {"model_id":"model-a","provider_id":"bad","provider_name":"Degraded Provider","availability":{"status":"available"},"performance":{"latency_seconds":1},"pricing":{"input_per_million":0.1}},
]
acc = endpoint["observations"]
db = ProviderDB(providers, acc)
assert db.best_provider("model-a", "accuracy-first")["provider_id"] == "good"
assert db.best_provider("model-a", require_accuracy_evidence=True)["provider_id"] == "good"
ok("provider accuracy-aware selection and strict evidence")

old = {"coverage":{"benchmark_version":"1.0"},"observations":[{"variant_id":"x","score":1}]}
new = {"coverage":{"benchmark_version":"1.1"},"observations":[{"variant_id":"x","score":2}]}
delta = diff_observations(old,new,key="variant_id",fields=["score"])
assert delta["counts"]["changed"] == 1 and delta["changed"][0]["identity_key"] == "__metadata__"
ok("observation history and incompatible-version marker")

variant_payload = {"name": "Endpoint Accuracy Index", "description": "v1.0", "data": [
    {"label": "CoreWeave", "detailsUrl": "/providers/coreweave", "endpointAccuracyIndex": [{"name": "mid", "value": 100}, {"name": "lower", "value": 95}, {"name": "upper", "value": 105}]},
    {"label": "DeepInfra", "detailsUrl": "/providers/deepinfra", "endpointAccuracyIndex": [{"name": "mid", "value": 97.01}, {"name": "lower", "value": 86.74}, {"name": "upper", "value": 107.28}]},
    {"label": "DeepInfra (Turbo)", "detailsUrl": "/providers/deepinfra", "endpointAccuracyIndex": [{"name": "mid", "value": 84.4}, {"name": "lower", "value": 75.59}, {"name": "upper", "value": 93.21}]},
]}
variant_page = f'<script type="application/ld+json">{json.dumps(variant_payload)}</script>'
variant_result = parse_page(variant_page, source_url="https://artificialanalysis.ai/models/gpt-oss-120b/providers", fetched_at="2026-08-23T00:00:00Z")
variant_rows = {row["provider_id"]: row for row in variant_result["observations"]}
assert {"deepinfra/base", "deepinfra/turbo"} <= set(variant_rows)
assert variant_rows["deepinfra/base"]["identity_key"] != variant_rows["deepinfra/turbo"]["identity_key"]
assert variant_rows["deepinfra/turbo"]["derived_classification"] == "below_reference"
ok("DeepInfra Base and Turbo have distinct endpoint identities")

operational = [
    {"model_id": "openai/gpt-oss-120b", "provider_id": "coreweave/fp4", "provider_name": "CoreWeave", "endpoint_id": "CoreWeave | openai/gpt-oss-120b", "availability": {"status": "available"}, "performance": {"latency_seconds": 1}, "pricing": {"input_per_million": 0.03}},
    {"model_id": "openai/gpt-oss-120b", "provider_id": "deepinfra/bf16", "provider_name": "DeepInfra", "endpoint_id": "DeepInfra | openai/gpt-oss-120b", "availability": {"status": "available"}, "performance": {"latency_seconds": 0.5}, "pricing": {"input_per_million": 0.02}},
    {"model_id": "openai/gpt-oss-120b", "provider_id": "deepinfra/turbo", "provider_name": "DeepInfra", "endpoint_id": "DeepInfra | openai/gpt-oss-120b", "availability": {"status": "available"}, "performance": {"latency_seconds": 0.25}, "pricing": {"input_per_million": 0.15}},
]
aliases = {"mappings": [
    {"relation": "model_to_model", "source_entity_id": "openai/gpt-oss-120b", "target_entity_id": "gpt-oss-120b", "evidence": "fixture model mapping"},
    {"relation": "provider_endpoint_to_endpoint", "source_entity_id": "openai/gpt-oss-120b:coreweave/fp4:CoreWeave | openai/gpt-oss-120b", "target_entity_id": variant_rows["coreweave"]["identity_key"], "evidence": "fixture exact CoreWeave mapping"},
    {"relation": "provider_endpoint_to_endpoint", "source_entity_id": "openai/gpt-oss-120b:deepinfra/turbo:DeepInfra | openai/gpt-oss-120b", "target_entity_id": variant_rows["deepinfra/turbo"]["identity_key"], "evidence": "fixture exact Turbo mapping"},
]}
aa = {"generated_at": "2026-08-23T00:00:00Z", "models": [{"slug": "gpt-oss-120b", "name": "gpt-oss-120b"}]}
openrouter_artifact = {"generated_at": "2026-08-23T00:00:00Z", "endpoint_observation_count": len(operational), "observations": operational}
accuracy_artifact = merge_models(None, [variant_result], [], now="2026-08-23T00:00:00Z")
identity, summary = build_artifacts(aa, openrouter_artifact, accuracy_artifact, aliases)
identity_again, summary_again = build_artifacts(aa, openrouter_artifact, accuracy_artifact, aliases)
assert (identity, summary) == (identity_again, summary_again)
gate_db = ProviderDB(operational, accuracy_artifact["observations"], identity)
gate = gate_db.best_provider("gpt-oss-120b", "accuracy-first", require_accuracy_evidence=True)
assert gate["provider_id"] == "coreweave/fp4"
turbo = next(row for row in operational if row["provider_id"] == "deepinfra/turbo")
assert gate_db._quality(turbo, "gpt-oss-120b")["classification"] == "below_reference"
without_coreweave = {**identity, "mappings": [m for m in identity["mappings"] if m.get("source_entity_id") != "openai/gpt-oss-120b:coreweave/fp4:CoreWeave | openai/gpt-oss-120b"]}
assert ProviderDB(operational, accuracy_artifact["observations"], without_coreweave).best_provider("gpt-oss-120b", "accuracy-first", require_accuracy_evidence=True) is None
ok("exact Gate-D mappings, Turbo evidence, and missing-CoreWeave fail closure")

with tempfile.TemporaryDirectory() as directory:
    output = Path(directory) / "accuracy.json"
    output.write_text('{"sentinel": true}\n', encoding="utf-8")
    original_fetch_many = endpoint_module.fetch_many
    endpoint_module.fetch_many = lambda *args, **kwargs: {"errors": [{"model_slug": "gpt-oss-120b"}], "coverage": {"successful_models": 0, "requested_models": 1}}
    try:
        assert endpoint_module.main(["gpt-oss-120b", "--output", str(output)]) == 1
        assert json.loads(output.read_text(encoding="utf-8")) == {"sentinel": True}
    finally:
        endpoint_module.fetch_many = original_fetch_many
ok("acquisition failure does not overwrite the last good artifact")
print("All phase3 observation tests passed.")
