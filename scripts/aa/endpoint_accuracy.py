"""Bounded public Artificial Analysis Endpoint Accuracy adapter."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from collections import Counter
import html
import json
from pathlib import Path
import re
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .http import atomic_write_json

BASE = "https://artificialanalysis.ai"
PARSER_VERSION = "0.4.0"
MAX_BYTES = 8 * 1024 * 1024
DEFAULT_RETENTION_DAYS = 14


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


def _variant_provider_ids(rows: list[dict]) -> list[str]:
    """Qualify labels when one provider URL represents multiple variants."""
    bases = [_provider_id(row["label"], row.get("detailsUrl")) for row in rows]
    counts = Counter((base, row.get("detailsUrl") or "") for base, row in zip(bases, rows))
    result = []
    for base, row in zip(bases, rows):
        if counts[(base, row.get("detailsUrl") or "")] == 1:
            result.append(base)
            continue
        label_id = re.sub(r"[^a-z0-9]+", "-", row["label"].lower()).strip("-")
        suffix = label_id.removeprefix(base).strip("-") or "base"
        result.append(f"{base}/{suffix}")
    return result


def _derived_classification(scores: dict) -> str:
    lower, upper = scores.get("lower"), scores.get("upper")
    if lower is not None and upper is not None:
        if lower <= 100 <= upper:
            return "reference_consistent"
        if upper < 100:
            return "below_reference"
        if lower > 100:
            return "above_reference"
    return "unknown"


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
    source_rows = [row for row in accuracy.get("data") or [] if row.get("label") and _values(row.get("endpointAccuracyIndex"))]
    provider_ids = _variant_provider_ids(source_rows)
    for row, provider_id in zip(source_rows, provider_ids):
        label = row.get("label")
        scores = _values(row.get("endpointAccuracyIndex"))
        details = row.get("detailsUrl")
        source_classification = row.get("classification") or row.get("referenceClassification")
        observations.append({
            "observation_type": "endpoint_accuracy", "source_model_id": model_slug,
            "model_slug": model_slug,
            "model_name": (accuracy.get("name") or "").split(":", 1)[-1].strip() or model_slug,
            "provider_id": provider_id, "provider_namespace": provider_id.split("/", 1)[0], "provider_name": label,
            "endpoint_id": details or label,
            "identity_key": ":".join(str(x or "") for x in (model_slug, provider_id, details or label)),
            "index_version": version.group(1) if version else None,
            "accuracy": {"mid": scores.get("mid"), "as_reference_percent": scores.get("mid"),
                         "lower": scores.get("lower"), "upper": scores.get("upper")},
            "classification": source_classification or "unknown",
            "derived_classification": _derived_classification(scores) if not source_classification else None,
            "components": row.get("components") or {}, "output_tokens_per_task": row.get("outputTokensPerTask"),
            "repeat_counts": row.get("repeatCounts") or {},
            "measurement_date": row.get("measurementDate") or row.get("measuredAt"),
            "reference": row.get("reference") or {}, "notes": row.get("notes"),
            "provenance": {"source": "artificial_analysis_endpoint_accuracy", "source_url": source_url,
                           "fetched_at": fetched_at, "parser_version": PARSER_VERSION,
                           "point_in_time": True},
        })
    return {"version": 1, "parser_version": PARSER_VERSION, "generated_at": fetched_at,
            "source": "artificial_analysis_endpoint_accuracy", "source_url": source_url,
            "index_version": version.group(1) if version else None,
            "coverage": {"scope": "public_jsonld", "models": 1 if observations else 0,
                         "endpoints": len(observations),
                         "measurement_dates": sorted({o["measurement_date"] for o in observations if o["measurement_date"]}),
                         "classification_values": sorted({o["classification"] for o in observations}),
                         "derived_classification_values": sorted({o["derived_classification"] for o in observations if o["derived_classification"]})},
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


def merge_models(previous: dict | None, fresh: list[dict], errors: list[dict], *, now: str,
                 retention_days: int = DEFAULT_RETENTION_DAYS) -> dict:
    """Merge bounded model results, retaining recent successful observations only."""
    now_dt = datetime.fromisoformat(now.replace("Z", "+00:00"))
    normalized_fresh = []
    for result in fresh:
        if result.get("model_slug"):
            normalized_fresh.append(result)
            continue
        grouped = {}
        for observation in result.get("observations", []):
            grouped.setdefault(observation.get("model_slug"), []).append(observation)
        for slug, observations in grouped.items():
            normalized_fresh.append({"model_slug": slug, "fetched_at": result.get("fetched_at") or result.get("generated_at"), "observations": observations, "coverage": {"endpoints": len(observations)}})
    fresh = normalized_fresh
    by_model = {r.get("model_slug"): r for r in fresh if r.get("model_slug")}
    retained = {}
    for row in (previous or {}).get("model_results", []):
        slug = row.get("model_slug")
        if not slug or slug in by_model:
            continue
        stamp = row.get("fetched_at") or row.get("provenance", {}).get("fetched_at")
        try:
            age = (now_dt - datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))).total_seconds() / 86400
        except (TypeError, ValueError):
            continue
        if 0 <= age <= retention_days:
            copy = dict(row)
            copy["retained"] = True
            copy["stale_after_days"] = retention_days
            retained[slug] = copy
    all_results = {**retained, **{r["model_slug"]: r for r in fresh}}
    observations = [o for r in all_results.values() for o in r.get("observations", [])]
    identities = [o.get("identity_key") for o in observations if o.get("identity_key")]
    if len(identities) != len(set(identities)):
        raise ValueError("Endpoint Accuracy observations contain duplicate identity keys")
    index_versions = sorted({o.get("index_version") for o in observations if o.get("index_version")})
    return {"version": 2, "parser_version": PARSER_VERSION, "generated_at": now,
            "source": "artificial_analysis_endpoint_accuracy", "model_results": [all_results[k] for k in sorted(all_results)],
            "errors": sorted(errors, key=lambda x: x.get("model_slug", "")),
            "index_version": index_versions[0] if len(index_versions) == 1 else None,
            "coverage": {"scope": "bounded_public_jsonld", "requested_models": len(set(by_model) | {e.get("model_slug") for e in errors}),
                         "successful_models": len(fresh), "retained_stale_models": len(retained),
                         "models": len({o.get("model_slug") for o in observations}), "endpoints": len(observations),
                         "index_versions": index_versions,
                         "retention_days": retention_days, "partial": bool(errors or retained)},
            "observation_count": len(observations), "observations": observations}


def fetch_many(model_slugs: list[str], *, timeout: int = 30, previous: dict | None = None,
               retention_days: int = DEFAULT_RETENTION_DAYS) -> dict:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    fresh, errors = [], []
    for slug in list(dict.fromkeys(model_slugs)):
        try:
            result = fetch(slug, timeout=timeout)
            result["fetched_at"] = now
            fresh.append(result)
        except Exception as exc:
            errors.append({"model_slug": slug, "error_type": type(exc).__name__, "error": str(exc), "attempted_at": now})
    return merge_models(previous, fresh, errors, now=now, retention_days=retention_days)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Fetch bounded public Endpoint Accuracy observations")
    parser.add_argument("model_slugs", nargs="+", help="bounded list of AA model slugs")
    parser.add_argument("--output", type=Path, default=Path("data/endpoint_accuracy_observations.json"))
    parser.add_argument("--retention-days", type=int, default=DEFAULT_RETENTION_DAYS)
    args = parser.parse_args(argv)
    previous = json.loads(args.output.read_text(encoding="utf-8")) if args.output.exists() else None
    result = fetch_many(args.model_slugs, previous=previous, retention_days=max(1, args.retention_days))
    if result["errors"] or result["coverage"]["successful_models"] != result["coverage"]["requested_models"]:
        print(f"Endpoint Accuracy acquisition failed closed: errors={len(result['errors'])} successful={result['coverage']['successful_models']} requested={result['coverage']['requested_models']}")
        return 1
    atomic_write_json(args.output, result)
    print(f"Endpoint Accuracy models={result['coverage']['models']} observations={result['observation_count']} errors={len(result['errors'])} retained={result['coverage']['retained_stale_models']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
