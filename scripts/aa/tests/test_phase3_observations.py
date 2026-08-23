#!/usr/bin/env python3
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from aa.endpoint_accuracy import parse_page, merge_models
from aa.coding_agent_source import parse_datasets_rich
from aa.identity import resolve
from aa.provider_query import ProviderDB
from aa.history import diff_observations

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

providers = [
 {"model_id":"model-a","provider_id":"good","provider_name":"Good Provider","availability":{"status":"available"},"performance":{"latency_seconds":2},"pricing":{"input_per_million":1}},
 {"model_id":"model-a","provider_id":"bad","provider_name":"Degraded Provider","availability":{"status":"available"},"performance":{"latency_seconds":1},"pricing":{"input_per_million":0.1}},
]
acc = endpoint["observations"]
db = ProviderDB(providers, acc)
assert db.best_provider("model-a", "accuracy-first")["provider_id"] == "good"
assert db.best_provider("model-a", require_accuracy_evidence=True)["provider_id"] == "good"
ok("provider accuracy-aware selection and strict evidence")

old = {"benchmark_version":"1.0","observations":[{"identity_key":"x","score":1}]}
new = {"benchmark_version":"1.1","observations":[{"identity_key":"x","score":2}]}
delta = diff_observations(old,new,fields=["score"])
assert delta["counts"]["changed"] == 2
ok("observation history and incompatible-version marker")
print("All phase3 observation tests passed.")
