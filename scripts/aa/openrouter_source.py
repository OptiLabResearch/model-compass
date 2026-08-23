"""Public OpenRouter operational source adapter.

The model list is public and requires no credential. Endpoint expansion is
bounded because one endpoint request is needed per model and provider detail is
not present in the list response. This source never supplies benchmark fields.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.parse import quote

try:
    from .http import fetch_json, atomic_write_json
    from .observations import normalize_openrouter_endpoint
except ImportError:
    import sys
    aa_dir = Path(__file__).resolve().parent
    if sys.path and Path(sys.path[0]).resolve() == aa_dir:
        sys.path.pop(0)
    sys.path.insert(0, str(aa_dir.parent))
    from aa.http import fetch_json, atomic_write_json
    from aa.observations import normalize_openrouter_endpoint

MODELS_URL = "https://openrouter.ai/api/v1/models"
ENDPOINT_URL = "https://openrouter.ai/api/v1/models/{model}/endpoints"
PARSER_VERSION = "0.1.0"


def select_cohort(catalog: list[dict], *, limit: int, cursor: int = 0,
                  priority_ids: list[str] | None = None) -> list[str]:
    """Select a deterministic rotating cohort, never depending on API order."""
    ids = sorted({str(item.get("id")) for item in catalog if item.get("id")})
    priority = [x for x in (priority_ids or []) if x in ids]
    priority = list(dict.fromkeys(priority))[:limit]
    remainder = [x for x in ids if x not in priority]
    if not remainder or len(priority) >= limit:
        return priority[:limit]
    start = cursor % len(remainder)
    rotated = remainder[start:] + remainder[:start]
    return priority + rotated[:limit - len(priority)]


def _observation_key(row: dict) -> tuple:
    return (row.get("model_id"), row.get("provider_id"), row.get("endpoint_id"))


def merge_retained_observations(previous: list[dict], fresh: list[dict], *, now: str,
                                retention_days: int = 14) -> list[dict]:
    now_dt = datetime.fromisoformat(now.replace("Z", "+00:00"))
    fresh_unique = {_observation_key(row): row for row in fresh}
    merged = dict(fresh_unique)
    for row in fresh_unique.values():
        row.setdefault("provenance", {})["last_seen"] = now
    for row in previous:
        row.setdefault("identity_key", ":".join(str(x or "") for x in _observation_key(row)))
        key = _observation_key(row)
        if key in merged:
            continue
        stamp = (row.get("provenance") or {}).get("last_seen") or (row.get("provenance") or {}).get("fetched_at")
        if not stamp:
            continue
        try:
            age = (now_dt - datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))).total_seconds() / 86400
        except ValueError:
            continue
        if 0 <= age <= retention_days:
            merged[key] = row
    return sorted(merged.values(), key=lambda row: tuple(str(x or "") for x in _observation_key(row)))


def fetch_observations(*, max_endpoints: int = 25, timeout: int = 30,
                       previous: dict | None = None, state: dict | None = None,
                       retention_days: int = 14) -> dict:
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload, response = fetch_json(MODELS_URL, timeout=timeout, retries=2)
    models = payload.get("data") or []
    state = state or {}
    cursor = int(state.get("cursor", 0))
    selected_ids = select_cohort(models, limit=max_endpoints, cursor=cursor,
                                 priority_ids=state.get("priority_ids"))
    by_id = {item.get("id"): item for item in models}
    observations = []
    endpoint_errors = []
    for model_id in selected_ids:
        if not model_id:
            continue
        try:
            ep_payload, _ = fetch_json(ENDPOINT_URL.format(model=quote(model_id, safe="/")), timeout=timeout, retries=1)
            for endpoint in (ep_payload.get("data") or {}).get("endpoints", []):
                observations.append(normalize_openrouter_endpoint(endpoint, fetched_at=fetched_at))
        except Exception as exc:  # source boundary: retain partial success
            endpoint_errors.append({"model_id": model_id, "error": str(exc)})
    retained = merge_retained_observations((previous or {}).get("observations", []), observations,
                                           now=fetched_at, retention_days=retention_days)
    remainder_count = max(len(models) - len(state.get("priority_ids", [])), 1)
    next_cursor = (cursor + max(0, len(selected_ids) - len(state.get("priority_ids", [])))) % remainder_count
    fresh_count = len({_observation_key(row) for row in observations})
    retained_count = len(retained) - fresh_count
    return {
        "version": 1, "parser_version": PARSER_VERSION, "generated_at": fetched_at,
        "source": "openrouter", "source_url": MODELS_URL,
        "model_catalog_count": len(models), "endpoint_models_requested": len(selected_ids),
        "endpoint_observation_count": len(retained), "endpoint_errors": endpoint_errors,
        "observations": retained,
        "coverage": {"catalog_models": len(models),
                     "models_with_observations": len({row.get("model_id") for row in retained}),
                     "proportion": round(len({row.get("model_id") for row in retained}) / len(models), 4) if models else 0,
                     "fresh_observations": fresh_count, "retained_observations": retained_count,
                     "retention_days": retention_days},
        "selection": {"cursor_before": cursor, "cursor_after": next_cursor,
                      "selected_model_ids": selected_ids},
        "next_state": {"cursor": next_cursor, "priority_ids": state.get("priority_ids", [])},
        "response_headers": response.headers,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Fetch bounded OpenRouter provider observations")
    parser.add_argument("--max-endpoints", type=int, default=25)
    parser.add_argument("--output", type=Path, default=Path("data/openrouter_observations.json"))
    parser.add_argument("--state", type=Path, default=Path("data/openrouter_sampling_state.json"))
    parser.add_argument("--retention-days", type=int, default=14)
    args = parser.parse_args(argv)
    previous = json.loads(args.output.read_text(encoding="utf-8")) if args.output.exists() else None
    state = json.loads(args.state.read_text(encoding="utf-8")) if args.state.exists() else None
    result = fetch_observations(max_endpoints=max(0, min(args.max_endpoints, 100)),
                                previous=previous, state=state,
                                retention_days=max(1, args.retention_days))
    atomic_write_json(args.output, result)
    atomic_write_json(args.state, result["next_state"])
    print(f"OpenRouter models={result['model_catalog_count']} selected={result['endpoint_models_requested']} endpoint_observations={result['endpoint_observation_count']} errors={len(result['endpoint_errors'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
