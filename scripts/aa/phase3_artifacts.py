"""Deterministically validate and build Phase 3 identity/acceptance artifacts."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from .http import atomic_write_json
from .identity import load_aliases, resolve
from .provider_query import ProviderDB

REPO = Path(__file__).resolve().parents[2]
GATE_MODEL = "gpt-oss-120b"
GATE_PROVIDER = "coreweave/fp4"


def _count_matches(artifact: dict, count_field: str, rows_field: str) -> None:
    expected, actual = artifact.get(count_field), len(artifact.get(rows_field, []))
    if expected != actual:
        raise ValueError(f"{count_field}={expected!r} does not match {rows_field} count {actual}")


def validate_inputs(aa: dict, openrouter: dict, accuracy: dict) -> None:
    _count_matches(openrouter, "endpoint_observation_count", "observations")
    _count_matches(accuracy, "observation_count", "observations")
    if accuracy.get("errors"):
        raise ValueError("Endpoint Accuracy artifact contains acquisition errors")
    observations = accuracy.get("observations", [])
    identities = [row.get("identity_key") for row in observations]
    if not identities or any(not value for value in identities) or len(identities) != len(set(identities)):
        raise ValueError("Endpoint Accuracy identity keys must be present and unique")
    coverage = accuracy.get("coverage") or {}
    if coverage.get("endpoints") != len(observations):
        raise ValueError("Endpoint Accuracy coverage endpoint count is inconsistent")
    model_count = len({row.get("model_slug") for row in observations if row.get("model_slug")})
    if coverage.get("models") != model_count:
        raise ValueError("Endpoint Accuracy coverage model count is inconsistent")
    versions = sorted({row.get("index_version") for row in observations if row.get("index_version")})
    if coverage.get("index_versions") != versions or accuracy.get("index_version") != (versions[0] if len(versions) == 1 else None):
        raise ValueError("Endpoint Accuracy index-version metadata is inconsistent")
    if not aa.get("models"):
        raise ValueError("AA canonical model artifact is empty")


def build_artifacts(aa: dict, openrouter: dict, accuracy: dict, aliases: dict) -> tuple[dict, dict]:
    validate_inputs(aa, openrouter, accuracy)
    stamps = [value for value in (aa.get("generated_at"), openrouter.get("generated_at"), accuracy.get("generated_at")) if value]
    generated_at = max(stamps) if stamps else "unknown"
    identity = resolve(aa["models"], openrouter.get("observations", []), accuracy.get("observations", []),
                       aliases.get("mappings", []), verified_at=generated_at)
    if identity.get("conflicts"):
        raise ValueError(f"Identity aliases conflict with source artifacts: {identity['conflicts']}")
    gate = ProviderDB(openrouter.get("observations", []), accuracy.get("observations", []), identity).best_provider(
        GATE_MODEL, "accuracy-first", require_accuracy_evidence=True)
    if not gate or gate.get("provider_id") != GATE_PROVIDER:
        raise ValueError("Gate D did not produce the audited CoreWeave recommendation")
    quality = gate["endpoint_quality"]
    mappings = quality["mapping_evidence"]
    if not mappings.get("model") or not mappings.get("provider_endpoint"):
        raise ValueError("Gate D explanation lacks authoritative identity mappings")
    summary = {
        "version": 2,
        "phase": 3,
        "generated_at": generated_at,
        "sources": {
            "aa_models": len(aa["models"]),
            "openrouter_observations": len(openrouter.get("observations", [])),
            "endpoint_accuracy_observations": len(accuracy.get("observations", [])),
            "endpoint_accuracy_models": (accuracy.get("coverage") or {}).get("models"),
            "endpoint_accuracy_index_versions": (accuracy.get("coverage") or {}).get("index_versions", []),
        },
        "identity": identity["health"],
        "gate_d": {
            "model_id": GATE_MODEL,
            "provider_id": gate["provider_id"],
            "endpoint_quality_status": quality["status"],
            "classification": quality.get("classification"),
            "accuracy": (quality.get("observation") or {}).get("accuracy"),
            "accuracy_identity_key": (quality.get("observation") or {}).get("identity_key"),
            "model_mapping": mappings["model"],
            "provider_endpoint_mapping": mappings["provider_endpoint"],
            "identity_policy": gate["decision"]["identity_policy"],
        },
    }
    return identity, summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build deterministic Phase 3 derived artifacts")
    parser.add_argument("--aa", type=Path, default=REPO / "data/aa_models_v2.json")
    parser.add_argument("--openrouter", type=Path, default=REPO / "data/openrouter_observations.json")
    parser.add_argument("--accuracy", type=Path, default=REPO / "data/endpoint_accuracy_observations.json")
    parser.add_argument("--aliases", type=Path, default=REPO / "data/identity_aliases.json")
    parser.add_argument("--identity-output", type=Path, default=REPO / "data/identity_mappings.json")
    parser.add_argument("--summary-output", type=Path, default=REPO / "data/phase3_summary.json")
    args = parser.parse_args(argv)
    load = lambda path: json.loads(path.read_text(encoding="utf-8"))
    identity, summary = build_artifacts(load(args.aa), load(args.openrouter), load(args.accuracy),
                                        {"mappings": load_aliases(args.aliases)})
    atomic_write_json(args.identity_output, identity)
    atomic_write_json(args.summary_output, summary)
    print(f"Phase 3 artifacts: mappings={len(identity['mappings'])} conflicts=0 gate_d={summary['gate_d']['provider_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
