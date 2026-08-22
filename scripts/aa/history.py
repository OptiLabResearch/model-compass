"""Deterministic rich snapshot deltas with bounded retention."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json


TRACKED_FIELDS = (
    "intelligence_index", "coding_index", "agentic_index", "omniscience_index",
    "context_tokens", "released", "deprecated", "is_open_weights",
)


def _value(model: dict, field: str):
    if field.startswith("pricing."):
        return (model.get("pricing") or {}).get(field.split(".", 1)[1])
    if field.startswith("performance."):
        return (model.get("performance") or {}).get(field.split(".", 1)[1])
    return model.get(field)


def _record(model: dict) -> dict:
    return {"slug": model.get("slug"), "name": model.get("name"),
            "creator": model.get("creator"),
            "fields": {field: _value(model, field) for field in TRACKED_FIELDS},
            "price_input": _value(model, "pricing.input"),
            "price_output": _value(model, "pricing.output"),
            "speed_tps": _value(model, "performance.median_output_speed_tps")}


def snapshot_index(snapshot: dict) -> dict[str, dict]:
    return {m["slug"]: m for m in snapshot.get("models", []) if isinstance(m, dict) and m.get("slug")}


def diff_snapshots(previous: dict | None, current: dict, *, generated_at: str | None = None) -> dict:
    old = snapshot_index(previous or {})
    new = snapshot_index(current)
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = []
    for slug in sorted(set(old) & set(new)):
        before, after = _record(old[slug]), _record(new[slug])
        changes = {}
        for field in (*TRACKED_FIELDS, "price_input", "price_output", "speed_tps"):
            if before.get("fields", {}).get(field, before.get(field)) != after.get("fields", {}).get(field, after.get(field)):
                changes[field] = {"before": before.get("fields", {}).get(field, before.get(field)),
                                  "after": after.get("fields", {}).get(field, after.get(field))}
        if changes:
            changed.append({"slug": slug, "name": after["name"], "changes": changes})
    stamp = generated_at or current.get("generated_at") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"version": 1, "generated_at": stamp,
            "previous_generated_at": (previous or {}).get("generated_at"),
            "counts": {"previous": len(old), "current": len(new), "added": len(added),
                       "removed": len(removed), "changed": len(changed)},
            "added": added, "removed": removed, "changed": changed}


def write_delta(path: Path, delta: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(delta, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def prune_deltas(directory: Path, *, keep: int = 104) -> list[str]:
    """Delete oldest delta JSON files, retaining at most ``keep``."""
    files = sorted(directory.glob("*.delta.json"), key=lambda p: p.name)
    removed = files[:-keep] if keep >= 0 else files
    for path in removed:
        path.unlink()
    return [p.name for p in removed]
