"""Public OpenRouter operational source adapter.

The model list is public and requires no credential. Endpoint expansion is
bounded because one endpoint request is needed per model and provider detail is
not present in the list response. This source never supplies benchmark fields.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
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


def fetch_observations(*, max_endpoints: int = 25, timeout: int = 30) -> dict:
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload, response = fetch_json(MODELS_URL, timeout=timeout, retries=2)
    models = payload.get("data") or []
    observations = []
    endpoint_errors = []
    for item in models[:max_endpoints]:
        model_id = item.get("id")
        if not model_id:
            continue
        try:
            ep_payload, _ = fetch_json(ENDPOINT_URL.format(model=quote(model_id, safe="/")), timeout=timeout, retries=1)
            for endpoint in (ep_payload.get("data") or {}).get("endpoints", []):
                observations.append(normalize_openrouter_endpoint(endpoint, fetched_at=fetched_at))
        except Exception as exc:  # source boundary: retain partial success
            endpoint_errors.append({"model_id": model_id, "error": str(exc)})
    return {
        "version": 1, "parser_version": PARSER_VERSION, "generated_at": fetched_at,
        "source": "openrouter", "source_url": MODELS_URL,
        "model_catalog_count": len(models), "endpoint_models_requested": min(max_endpoints, len(models)),
        "endpoint_observation_count": len(observations), "endpoint_errors": endpoint_errors,
        "observations": observations,
        "response_headers": response.headers,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Fetch bounded OpenRouter provider observations")
    parser.add_argument("--max-endpoints", type=int, default=25)
    parser.add_argument("--output", type=Path, default=Path("data/openrouter_observations.json"))
    args = parser.parse_args(argv)
    result = fetch_observations(max_endpoints=max(0, min(args.max_endpoints, 100)))
    atomic_write_json(args.output, result)
    print(f"OpenRouter models={result['model_catalog_count']} endpoint_observations={result['endpoint_observation_count']} errors={len(result['endpoint_errors'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
