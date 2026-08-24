"""Deterministic snapshot deltas with bounded retention."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import json

TRACKED_FIELDS = ("intelligence_index", "coding_index", "agentic_index", "omniscience_index", "context_tokens", "released", "deprecated", "is_open_weights")
MATERIALITY = {"intelligence_index": 0.1, "coding_index": 0.1, "agentic_index": 0.1, "omniscience_index": 0.1, "price_input": 0.01, "price_output": 0.01, "speed_tps": 0.05}


def _value(model: dict, field: str):
    node = model
    for part in field.split("."):
        node = node.get(part) if isinstance(node, dict) else None
    return node


def _material_change(field: str, before, after) -> bool:
    if before == after: return False
    threshold = MATERIALITY.get(field)
    if threshold is None or not isinstance(before, (int, float)) or not isinstance(after, (int, float)): return True
    return abs(after - before) / max(abs(before), abs(after), 1.0) >= threshold


def _record(model: dict) -> dict:
    fields = {field: _value(model, field) for field in TRACKED_FIELDS}
    fields.update({"price_input": _value(model, "pricing.input"), "price_output": _value(model, "pricing.output"), "speed_tps": _value(model, "performance.median_output_speed_tps")})
    return {"slug": model.get("slug"), "name": model.get("name"), "fields": fields}


def snapshot_index(snapshot: dict) -> dict[str, dict]:
    return {m["slug"]: m for m in snapshot.get("models", []) if isinstance(m, dict) and m.get("slug")}


def diff_snapshots(previous: dict | None, current: dict, *, generated_at: str | None = None) -> dict:
    old, new = snapshot_index(previous or {}), snapshot_index(current)
    added, removed, changed = sorted(set(new) - set(old)), sorted(set(old) - set(new)), []
    for slug in sorted(set(old) & set(new)):
        before, after = _record(old[slug]), _record(new[slug]); changes = {}
        for field in (*TRACKED_FIELDS, "price_input", "price_output", "speed_tps"):
            b, a = before["fields"].get(field), after["fields"].get(field)
            if _material_change(field, b, a): changes[field] = {"before": b, "after": a}
        if changes: changed.append({"slug": slug, "name": after["name"], "changes": changes})
    stamp = generated_at or current.get("generated_at") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"version": 1, "generated_at": stamp, "previous_generated_at": (previous or {}).get("generated_at"),
            "counts": {"previous": len(old), "current": len(new), "added": len(added), "removed": len(removed), "changed": len(changed)},
            "added": added, "removed": removed, "changed": changed}


def diff_observations(previous: dict | None, current: dict, *, key="identity_key", fields=(), generated_at=None) -> dict:
    """Diff endpoint/agent observations without comparing incompatible versions as scores."""
    def observation_index(artifact):
        rows = [o for o in (artifact or {}).get("observations", []) if o.get(key)]
        index = {o[key]: o for o in rows}
        if len(index) != len(rows):
            raise ValueError(f"duplicate observation key: {key}")
        return index
    old = observation_index(previous)
    new = observation_index(current)
    added, removed, changed = sorted(set(new) - set(old)), sorted(set(old) - set(new)), []
    def row_version(row):
        value = row.get("benchmark_version") or row.get("index_version")
        return str(value) if value is not None else None
    def artifact_versions(artifact):
        artifact = artifact or {}
        coverage = artifact.get("coverage") or {}
        values = {row_version(row) for row in artifact.get("observations", []) if row_version(row)}
        if values:
            return tuple(sorted(values))
        direct = artifact.get("benchmark_version") or artifact.get("index_version") or coverage.get("benchmark_version")
        return (str(direct),) if direct else ()
    def display_versions(values):
        return values[0] if len(values) == 1 else list(values) if values else None
    old_versions, new_versions = artifact_versions(previous), artifact_versions(current)
    if old_versions == new_versions:
        for ident in sorted(set(old) & set(new)):
            before_version, after_version = row_version(old[ident]), row_version(new[ident])
            if before_version != after_version:
                changed.append({"identity_key": ident, "changes": {"benchmark_version": {"before": before_version, "after": after_version}, "comparability": "not directly comparable across versions"}})
                continue
            changes = {}
            for field in fields:
                before, after = _value(old[ident], field), _value(new[ident], field)
                if _material_change(field, before, after): changes[field] = {"before": before, "after": after}
            if changes: changed.append({"identity_key": ident, "changes": changes})
    else:
        changed.append({"identity_key": "__metadata__", "changes": {"benchmark_version": {"before": display_versions(old_versions), "after": display_versions(new_versions)}, "comparability": "not directly comparable across versions"}})
    return {"version": 1, "generated_at": generated_at or current.get("generated_at"), "counts": {"previous": len(old), "current": len(new), "added": len(added), "removed": len(removed), "changed": len(changed)}, "added": added, "removed": removed, "changed": changed}


def write_delta(path: Path, delta: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(delta, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def prune_deltas(directory: Path, *, keep: int = 104) -> list[str]:
    files = sorted(directory.glob("*.delta.json"), key=lambda p: p.name); removed = files[:-keep] if keep >= 0 else files
    for path in removed: path.unlink()
    return [p.name for p in removed]
