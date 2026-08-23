"""Explicit, auditable cross-source identity resolution.

Only exact stable IDs and explicit aliases become verified mappings. Display-name
matches are candidates at most; they never silently join recommendation inputs.
"""
from __future__ import annotations
from datetime import datetime, timezone
import json
from pathlib import Path
import re

STATES = {"verified", "high-confidence", "candidate", "unresolved", "conflict", "manual"}


def normalize_name(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")


def load_aliases(path: str | Path | None) -> list[dict]:
    if not path or not Path(path).exists():
        return []
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data.get("mappings", []) if isinstance(data, dict) else []


def resolve(aa_models: list[dict], openrouter: list[dict], endpoint_accuracy: list[dict] | None = None,
            aliases: list[dict] | None = None, *, verified_at: str | None = None) -> dict:
    verified_at = verified_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    mappings, unresolved, ambiguous, conflicts = [], [], [], []
    aliases = aliases or []
    aa_by_slug = {m.get("slug"): m for m in aa_models if m.get("slug")}
    alias_map = {(a.get("source_entity_id"), a.get("target_entity_id")): a for a in aliases
                 if a.get("source_entity_id") and a.get("target_entity_id")}
    for row in openrouter:
        source_id = row.get("model_id")
        if not source_id:
            continue
        explicit = next((a for a in aliases if a.get("source_entity_id") == source_id), None)
        if explicit:
            target = explicit.get("target_entity_id")
            if target not in aa_by_slug:
                conflicts.append({"source_entity_id": source_id, "target_entity_id": target,
                                  "reason": "manual target does not exist"})
                continue
            mappings.append({"relation": "model_to_model", "source": "openrouter", "source_entity_id": source_id,
                             "target": "artificial_analysis", "target_entity_id": target,
                             "state": "manual", "confidence": 1.0, "evidence": explicit.get("evidence", "manual alias"),
                             "first_verified": explicit.get("first_verified", verified_at), "last_verified": verified_at})
            continue
        candidates = [slug for slug, model in aa_by_slug.items()
                      if normalize_name(model.get("slug")) == normalize_name(source_id)
                      or normalize_name(model.get("name")) == normalize_name(source_id)]
        if len(candidates) == 1:
            mappings.append({"relation": "model_to_model", "source": "openrouter", "source_entity_id": source_id,
                             "target": "artificial_analysis", "target_entity_id": candidates[0],
                             "state": "candidate", "confidence": 0.6,
                             "evidence": "normalized display/name equality; not authoritative", "last_verified": verified_at})
        elif len(candidates) > 1:
            ambiguous.append({"source": "openrouter", "source_entity_id": source_id, "candidates": sorted(candidates)})
        else:
            unresolved.append({"source": "openrouter", "source_entity_id": source_id})
    for row in endpoint_accuracy or []:
        if row.get("model_slug") in aa_by_slug:
            mappings.append({"relation": "endpoint_model_to_model", "source": "artificial_analysis_endpoint_accuracy",
                             "source_entity_id": row.get("model_slug"), "target": "artificial_analysis",
                             "target_entity_id": row.get("model_slug"), "state": "verified", "confidence": 1.0,
                             "evidence": "same Artificial Analysis stable slug", "last_verified": verified_at})
    counts = {"verified": sum(m["state"] == "verified" for m in mappings),
              "manual": sum(m["state"] == "manual" for m in mappings),
              "candidate": sum(m["state"] == "candidate" for m in mappings),
              "unresolved": len(unresolved), "ambiguous": len(ambiguous), "conflict": len(conflicts)}
    return {"version": 1, "generated_at": verified_at, "mappings": mappings,
            "unresolved": unresolved, "ambiguous": ambiguous, "conflicts": conflicts,
            "health": {"aa_models": len(aa_by_slug), "openrouter_models": len(openrouter), **counts}}
