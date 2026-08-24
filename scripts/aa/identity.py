"""Explicit, auditable model and provider identity resolution.

Observations are deduplicated into entities before health is calculated. Only
verified/manual mappings may be consumed by recommendation code.
"""
from __future__ import annotations
from datetime import datetime, timezone
import json
from pathlib import Path
import re

STATES = {"verified", "candidate", "unresolved", "ambiguous", "conflict", "manual"}


def normalize_name(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")


def load_aliases(path: str | Path | None) -> list[dict]:
    if not path or not Path(path).exists():
        return []
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data.get("mappings", []) if isinstance(data, dict) else []


def _model_evidence(source_id: str, row: dict, aa_models: list[dict]) -> list[dict]:
    namespace, _, portion = source_id.partition("/")
    portion_n = normalize_name(portion or source_id)
    source_name = row.get("model_name") or row.get("name") or portion
    source_name_n = normalize_name(source_name)
    out = []
    for model in aa_models:
        slug, name = model.get("slug"), model.get("name")
        creator = normalize_name(model.get("creator_slug") or model.get("creator"))
        slug_n, name_n = normalize_name(slug), normalize_name(name)
        score, reasons = 0, []
        if portion_n == slug_n:
            score += 4; reasons.append("OpenRouter model portion equals AA slug")
        if portion_n == name_n or source_name_n in {slug_n, name_n}:
            score += 3; reasons.append("normalized model name/version equality")
        if creator and namespace and creator == normalize_name(namespace):
            score += 2; reasons.append("OpenRouter namespace agrees with AA creator")
        if score:
            out.append({"target_entity_id": slug, "score": score, "evidence": reasons})
    return sorted(out, key=lambda x: (-x["score"], x["target_entity_id"]))


def _entity_rows(rows: list[dict], key: str) -> dict[str, dict]:
    entities = {}
    for row in rows:
        value = row.get(key)
        if value and value not in entities:
            entities[value] = row
    return entities


def openrouter_endpoint_entity_id(row: dict) -> str | None:
    """Return a fail-closed operational endpoint identity including its variant."""
    model_id, provider_id, endpoint_id = row.get("model_id"), row.get("provider_id"), row.get("endpoint_id")
    if not model_id or not provider_id or not endpoint_id:
        return None
    return ":".join((str(model_id), str(provider_id), str(endpoint_id)))


def _alias_for(aliases: list[dict], relation: str, source_id: str) -> dict | None:
    return next((a for a in aliases if a.get("relation", "model_to_model") == relation
                 and a.get("source_entity_id") == source_id), None)


def resolve(aa_models: list[dict], openrouter: list[dict], endpoint_accuracy: list[dict] | None = None,
            aliases: list[dict] | None = None, *, verified_at: str | None = None) -> dict:
    verified_at = verified_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    aliases = aliases or []
    aa_by_slug = _entity_rows(aa_models, "slug")
    or_models = _entity_rows(openrouter, "model_id")
    aa_endpoints = {o.get("identity_key"): o for o in endpoint_accuracy or [] if o.get("identity_key")}
    or_endpoints = {openrouter_endpoint_entity_id(o): o for o in openrouter if openrouter_endpoint_entity_id(o)}
    aa_providers = {o.get("provider_namespace") or (o.get("provider_id") or "").split("/", 1)[0] for o in endpoint_accuracy or [] if o.get("provider_id")}
    or_providers = {(o.get("provider_id") or "").split("/", 1)[0] for o in openrouter if o.get("provider_id")}
    mappings, unresolved, ambiguous, conflicts = [], [], [], []

    for source_id, row in sorted(or_models.items()):
        explicit = _alias_for(aliases, "model_to_model", source_id)
        if explicit:
            target = explicit.get("target_entity_id")
            if target not in aa_by_slug:
                conflicts.append({"relation": "model_to_model", "source_entity_id": source_id, "target_entity_id": target, "reason": "manual target does not exist"})
            else:
                mappings.append({"relation": "model_to_model", "source": "openrouter", "source_entity_id": source_id,
                                 "target": "artificial_analysis", "target_entity_id": target, "state": "manual", "confidence": 1.0,
                                 "evidence": explicit.get("evidence", "audited manual alias"),
                                 "last_verified": explicit.get("last_verified") or explicit.get("first_verified") or verified_at})
            continue
        evidence = _model_evidence(source_id, row, aa_models)
        if len(evidence) == 1 and evidence[0]["score"] >= 4:
            mappings.append({"relation": "model_to_model", "source": "openrouter", "source_entity_id": source_id,
                             "target": "artificial_analysis", "target_entity_id": evidence[0]["target_entity_id"],
                             "state": "candidate", "confidence": min(.95, .45 + evidence[0]["score"] / 10),
                             "evidence": "; ".join(evidence[0]["evidence"]) + "; non-authoritative", "last_verified": verified_at})
        elif len(evidence) > 1 and evidence[0]["score"] == evidence[1]["score"]:
            ambiguous.append({"relation": "model_to_model", "source_entity_id": source_id, "candidates": [x["target_entity_id"] for x in evidence]})
        else:
            unresolved.append({"relation": "model_to_model", "source_entity_id": source_id})

    for source_id, row in sorted(or_endpoints.items()):
        explicit = _alias_for(aliases, "provider_endpoint_to_endpoint", source_id)
        if explicit:
            target = explicit.get("target_entity_id")
            if target not in aa_endpoints:
                conflicts.append({"relation": "provider_endpoint_to_endpoint", "source_entity_id": source_id, "target_entity_id": target, "reason": "manual target does not exist"})
            else:
                mappings.append({"relation": "provider_endpoint_to_endpoint", "source": "openrouter", "source_entity_id": source_id,
                                 "target": "artificial_analysis", "target_entity_id": target, "state": "manual", "confidence": 1.0,
                                 "evidence": explicit.get("evidence", "audited manual provider alias"),
                                 "last_verified": explicit.get("last_verified") or explicit.get("first_verified") or verified_at})
        else:
            unresolved.append({"relation": "provider_endpoint_to_endpoint", "source_entity_id": source_id})

    for slug in sorted({r.get("model_slug") for r in endpoint_accuracy or [] if r.get("model_slug") and r.get("model_slug") in aa_by_slug}):
        mappings.append({"relation": "endpoint_model_to_model", "source": "artificial_analysis_endpoint_accuracy",
                         "source_entity_id": slug, "target": "artificial_analysis", "target_entity_id": slug,
                         "state": "verified", "confidence": 1.0, "evidence": "same Artificial Analysis stable slug", "last_verified": verified_at})

    model_maps = [m for m in mappings if m["relation"] == "model_to_model"]
    endpoint_maps = [m for m in mappings if m["relation"] == "provider_endpoint_to_endpoint"]
    health = {
        "aa_model_count": len(aa_by_slug), "openrouter_model_count": len(or_models),
        "openrouter_endpoint_count": len(openrouter), "aa_endpoint_count": len(aa_endpoints), "aa_provider_count": len(aa_providers),
        "openrouter_provider_count": len(or_providers), "unique_unresolved_model_ids": sorted({x["source_entity_id"] for x in unresolved if x["relation"] == "model_to_model"}),
        "model_mappings": {s: sum(m["state"] == s for m in model_maps) for s in ("verified", "manual", "candidate")},
        "endpoint_mappings": {s: sum(m["state"] == s for m in endpoint_maps) for s in ("verified", "manual", "candidate")},
        "unresolved_models": sum(x["relation"] == "model_to_model" for x in unresolved),
        "unresolved_endpoints": sum(x["relation"] == "provider_endpoint_to_endpoint" for x in unresolved),
        "ambiguous": len(ambiguous), "conflict": len(conflicts),
    }
    return {"version": 3, "generated_at": verified_at, "mappings": mappings,
            "unresolved": unresolved, "ambiguous": ambiguous, "conflicts": conflicts, "health": health}
