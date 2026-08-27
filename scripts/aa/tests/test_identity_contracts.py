#!/usr/bin/env python3
"""Phase 4 tests for source-qualified identity evidence and authority."""
from __future__ import annotations
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))

from aa.identity import model_identity_evidence, resolve  # noqa: E402
from aa.official_api_source import normalize_model  # noqa: E402
from aa.orchestrate import merge_records  # noqa: E402
from aa.provider_query import ProviderDB  # noqa: E402
from aa.schema import model_record_template  # noqa: E402
from aa.snapshot_source import _normalize as normalize_snapshot  # noqa: E402
from aa.source_base import SourceResult  # noqa: E402
try:
    from _runner import run_tests  # noqa: E402
except ModuleNotFoundError:  # pytest imports this module from the repository root
    from scripts.aa.tests._runner import run_tests  # noqa: E402


def model(slug, evidence):
    return {"slug": slug, "name": slug, "identity_evidence": evidence}


def endpoint(model_id):
    return {"model_id": model_id, "provider_id": "provider/variant", "endpoint_id": "Endpoint"}


def test_adapters_label_external_ids_by_source_authority():
    official = normalize_model({"id": "aa-1", "slug": "model-a", "name": "Model A",
                                "openrouter_api_id": "author/model-a"})
    snapshot = normalize_snapshot({"id": "snap-1", "slug": "model-a", "name": "Model A",
                                   "open_weights": {"openrouter_api_id": "author/model-a"}})
    assert official["identity_evidence"] == [{
        "kind": "openrouter_model_id", "entity_id": "author/model-a",
        "source": "official_api", "source_field": "openrouter_api_id",
        "authority": "authoritative",
    }]
    assert snapshot["identity_evidence"] == [{
        "kind": "openrouter_model_id", "entity_id": "author/model-a",
        "source": "snapshot", "source_field": "open_weights.openrouter_api_id",
        "authority": "candidate",
    }]


def test_merge_preserves_source_qualified_evidence():
    rsc = model_record_template(); rsc.update({"slug": "model-a", "name": "Model A"})
    api = model_record_template(); api.update({"slug": "model-a", "name": "Model A", "identity_evidence": [{
        "kind": "openrouter_model_id", "entity_id": "author/model-a", "source": "official_api",
        "source_field": "openrouter_api_id", "authority": "authoritative"}]})
    snapshot = model_record_template(); snapshot.update({"slug": "model-a", "name": "Model A", "identity_evidence": [{
        "kind": "openrouter_model_id", "entity_id": "author/model-a", "source": "snapshot",
        "source_field": "open_weights.openrouter_api_id", "authority": "candidate"}]})
    results = [SourceResult("rsc", "1", "t", 0, [rsc], healthy=True),
               SourceResult("official_api", "1", "t", 0, [api], healthy=True),
               SourceResult("snapshot", "1", "t", 0, [snapshot], healthy=True)]
    evidence = merge_records(results)[0]["identity_evidence"]
    assert [(row["source"], row["authority"]) for row in evidence] == [
        ("official_api", "authoritative"), ("snapshot", "candidate")]


def test_official_exact_id_verifies_but_snapshot_exact_id_is_candidate():
    official = model("model-a", [{"kind": "openrouter_model_id", "entity_id": "author/model-a",
                                   "source": "official_api", "source_field": "openrouter_api_id",
                                   "authority": "authoritative"}])
    verified = resolve([official], [endpoint("author/model-a")], verified_at="2026-08-24T00:00:00Z")
    mapping = next(row for row in verified["mappings"] if row["relation"] == "model_to_model")
    assert mapping["state"] == "verified" and mapping["method"] == "official_openrouter_id"

    snapshot = model("model-b", [{"kind": "openrouter_model_id", "entity_id": "author/model-b",
                                   "source": "snapshot", "source_field": "open_weights.openrouter_api_id",
                                   "authority": "candidate"}])
    candidate = resolve([snapshot], [endpoint("author/model-b")], verified_at="2026-08-24T00:00:00Z")
    mapping = next(row for row in candidate["mappings"] if row["relation"] == "model_to_model")
    assert mapping["state"] == "candidate" and mapping["method"] == "source_metadata_exact"
    assert ProviderDB([endpoint("author/model-b")], [], candidate).providers("model-b") == []


def test_variant_collision_is_ambiguous_and_authoritative_collision_conflicts():
    candidate_evidence = lambda: [{"kind": "openrouter_model_id", "entity_id": "author/shared",
                                    "source": "snapshot", "source_field": "open_weights.openrouter_api_id",
                                    "authority": "candidate"}]
    ambiguous = resolve([model("base", candidate_evidence()), model("high", candidate_evidence())],
                        [endpoint("author/shared")], verified_at="2026-08-24T00:00:00Z")
    assert not [row for row in ambiguous["mappings"] if row["relation"] == "model_to_model"]
    assert ambiguous["ambiguous"] == [{"relation": "model_to_model", "source_entity_id": "author/shared",
                                        "method": "source_metadata_exact", "candidates": ["base", "high"],
                                        "evidence": ["snapshot open_weights.openrouter_api_id exactly equals OpenRouter model ID"]}]

    authoritative_evidence = lambda: [{"kind": "openrouter_model_id", "entity_id": "author/shared",
                                        "source": "official_api", "source_field": "openrouter_api_id",
                                        "authority": "authoritative"}]
    conflict = resolve([model("base", authoritative_evidence()), model("high", authoritative_evidence())],
                       [endpoint("author/shared")], verified_at="2026-08-24T00:00:00Z")
    assert conflict["conflicts"][0]["reason"] == "authoritative external ID maps to multiple AA variants"


def test_legacy_evidence_is_source_qualified_and_missing_is_empty():
    legacy = {"raw_fields": {"snapshot_entry": {"open_weights": {"openrouter_api_id": "author/model"}}},
              "hosts": [{"hostApiId": "provider-model"}]}
    evidence = model_identity_evidence(legacy)
    assert {(row["source"], row["kind"], row["authority"]) for row in evidence} == {
        ("snapshot", "openrouter_model_id", "candidate"),
        ("rsc", "provider_host_api_id", "candidate"),
    }
    assert model_identity_evidence({}) == []


if __name__ == "__main__":
    run_tests(globals(), "All identity contract tests passed.")
