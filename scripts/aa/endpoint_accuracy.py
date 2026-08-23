"""Public Artificial Analysis Endpoint Accuracy observation adapter.

The provider page publishes a bounded JSON-LD Dataset to ordinary visitors. The
adapter keeps endpoint measurements separate from canonical model records and
preserves source uncertainty/classification instead of deriving significance.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from .http import atomic_write_json

BASE = "https://artificialanalysis.ai"
PARSER_VERSION = "0.2.0"
MAX_BYTES = 8 * 1024 * 1024


def _jsonld(page: str) -> list[dict]:
    out = []
    for raw in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S):
        try:
            value = json.loads(html.unescape(raw))
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            out.append(value)
    return out


def _values(values) -> dict:
    result = {}
    for item in values or []:
        if isinstance(item, dict) and item.get("name") in {"mid", "lower", "upper"}:
            try:
                result[item["name"]] = float(item.get("value"))
            except (TypeError, ValueError):
                pass
    return result


def _provider_id(label: str, details_url: str | None) -> str:
    if details_url:
        path = urlparse(details_url).path.rstrip("/").split("/")
        if path and path[-1]:
            return path[-1].lower()
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")


def parse_page(page: str, *, source_url: str, fetched_at: str) -> dict:
    payloads = _jsonld(page)
    model_match = re.search(r"/models/([^/]+)/providers", source_url)
    model_slug = model_match.group(1) if model_match else None
    accuracy = next((p for p in payloads if "endpoint accuracy index" in str(p.get("name", "")).lower()
                    and any("endpointAccuracyIndex" in row for row in p.get("data") or [])), None)
    if not accuracy:
        raise ValueError("Endpoint Accuracy JSON-LD dataset not found")
    description = accuracy.get("description") or ""
    version = re.search(r"\bv(\d+(?:\.\d+)*)\b", description, re.I)
    observations = []
    for row in accuracy.get("data") or []:
        label = row.get("label")
        scores = _values(row.get("endpointAccuracyIndex"))
        if not label or not scores:
            continue
        details = row.get("detailsUrl")
        observations.append({
            "observation_type": "endpoint_accuracy",
            "source_model_id": model_slug,
            "model_slug": model_slug,
            "model_name": (accuracy.get("name") or "").split(":", 1)[-1].strip() or model_slug,
            "provider_id": _provider_id(label, details),
            "provider_name": label,
            "endpoint_id": details or label,
            "identity_key": ":".join(str(x or "") for x in (model_slug, _provider_id(label, details), details or label)),
            "index_version": version.group(1) if version else None,
            "accuracy": {"mid": scores.get("mid"), "as_reference_percent": scores.get("mid"),
                         "lower": scores.get("lower"), "upper": scores.get("upper")},
            "classification": row.get("classification") or row.get("referenceClassification") or "unknown",
            "components": row.get("components") or {},
            "output_tokens_per_task": row.get("outputTokensPerTask"),
            "repeat_counts": row.get("repeatCounts") or {},
            "measurement_date": row.get("measurementDate") or row.get("measuredAt"),
            "reference": row.get("reference") or {},
            "notes": row.get("notes"),
            "provenance": {"source": "artificial_analysis_endpoint_accuracy",
                           "source_url": source_url, "fetched_at": fetched_at,
                           "parser_version": PARSER_VERSION, "point_in_time": True},
        })
    return {"version": 1, "parser_version": PARSER_VERSION,
            "generated_at": fetched_at, "source": "artificial_analysis_endpoint_accuracy",
            "source_url": source_url, "index_version": version.group(1) if version else None,
            "coverage": {"scope": "public_jsonld", "models": 1 if observations else 0,
                         "endpoints": len(observations),
                         "measurement_dates": sorted({o["measurement_date"] for o in observations if o["measurement_date"]}),
                         "classification_values": sorted({o["classification"] for o in observations})},
            "observation_count": len(observations), "observations": observations}


def fetch(model_slug: str, *, timeout: int = 30) -> dict:
    url = f"{BASE}/models/{model_slug}/providers"
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    req = Request(url, headers={"User-Agent": "ModelCompass/3.0"})
    with urlopen(req, timeout=timeout) as response:
        page = response.read(MAX_BYTES + 1)
    if len(page) > MAX_BYTES:
        raise ValueError("Endpoint Accuracy page exceeded bounded payload size")
    return parse_page(page.decode("utf-8", "replace"), source_url=url, fetched_at=stamp)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Fetch public Endpoint Accuracy observations")
    parser.add_argument("model_slug")
    parser.add_argument("--output", type=Path, default=Path("data/endpoint_accuracy_observations.json"))
    args = parser.parse_args(argv)
    result = fetch(args.model_slug)
    atomic_write_json(args.output, result)
    print(f"Endpoint Accuracy observations={result['observation_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
