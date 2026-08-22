"""AA pipeline orchestrator — run all sources, merge, validate, emit output.

This is the NEW private data pipeline for model-compass. It is the source of
truth for Hermes / our tools when making model-selection decisions.

Design (adapter/source pattern so the AA extraction mechanism is replaceable):

    RSCSource (rich, no key, ~412 models, full metrics)   <-- primary
    OfficialAPISource (stable baseline/IDs, needs AA_API_KEY)
    SnapshotSource (Oolong third-party, fallback/cross-check)
            |  each -> SourceResult (raw + normalized records + provenance)
            v
    merge_records()   dedup by slug, priority RSC > API > Snapshot,
                      fill blanks from richer sources, preserve raw_fields
    run_sanity()      fail-visible checks (count, fields, dupes, NaN)
            v
    emit: data/aa_models_v2.json      (normalized, all models, all fields)
          data/aa_pipeline_report.json (coverage + source + errors for debugging)

The single-file legacy pipeline (scripts/fetch_aa_models.py) that builds the
public static site continues to work independently on the public/data/models.json
subset; this orchestrator feeds the private dataset and can also serve the
legacy builder later.

Usage:
    AA_API_KEY=... python3.12 scripts/aa/orchestrate.py            # full
    python3.12 scripts/aa/orchestrate.py --no-api --no-snapshot    # RSC only
    python3.12 scripts/aa/orchestrate.py --offline                 # stale cache only
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from aa import schema          # noqa: E402
from aa.http import atomic_write_json, read_json          # noqa: E402
from aa.source_base import SourceResult                    # noqa: E402
from aa.rsc_source import RSCSource                        # noqa: E402
from aa.validate import run_sanity, check_schema_drift, KNOWN_FIELDS  # noqa: E402
from aa.history import diff_snapshots, write_delta, prune_deltas  # noqa: E402


def load_all_sources(args, cache_dir: Path) -> list[SourceResult]:
    results: list[SourceResult] = []

    rsc = RSCSource(use_cache=True, cache_dir=cache_dir, force_refresh=args.refresh,
                    offline=args.offline)
    results.append(rsc.fetch())

    if args.api:
        try:
            from aa.official_api_source import OfficialAPISource
            api = OfficialAPISource(cache_dir=cache_dir, force_refresh=args.refresh,
                                    offline=args.offline)
            results.append(api.fetch())
        except ImportError:
            logging.getLogger("aa.pipeline").warning(
                "official_api_source not present; skipping API"
            )
            results.append(SourceResult(
                source="official_api", parser_version="0.0.0",
                fetched_at="", fetched_at_ts=0, records=[], healthy=False,
                errors=["module not available"],
            ))

    if args.snapshot:
        try:
            from aa.snapshot_source import SnapshotSource
            snap = SnapshotSource(cache_dir=cache_dir, force_refresh=args.refresh,
                                  offline=args.offline)
            results.append(snap.fetch())
        except ImportError:
            logging.getLogger("aa.pipeline").warning(
                "snapshot_source not present; skipping snapshot"
            )
            results.append(SourceResult(
                source="snapshot", parser_version="0.0.0",
                fetched_at="", fetched_at_ts=0, records=[], healthy=False,
                errors=["module not available"],
            ))
    return results


def validate_source_results(results: list[SourceResult]) -> None:
    """Crash loudly if the PRIMARY (RSC) source looks corrupt — fail visible."""
    primary = next((r for r in results if r.source == "rsc"), None)
    if primary is None:
        raise RuntimeError("RSC source did not run")
    rep = run_sanity(primary.records, "rsc", schema.MIN_MODELS_RSC)
    if not rep.passed:
        raise RuntimeError("RSC sanity check FAILED: " + "; ".join(rep.failures[:5]))
    return None


def _fill(dst, key, value):
    """Fill dst[key] only if present (and non-emptiness) so richer source wins."""
    if value is None:
        return
    if isinstance(value, dict) and not value:
        return
    dst[key] = value


def merge_records(results: list[SourceResult]) -> list[dict]:
    """Merge all source records into one per-slug dict. Priority rich-over-thin.

    Records with a slug; a later source (RSC added first = highest priority when
    deduping within a slug) provides primary values. For fields where the higher
    priority record is None, fill from the next source. raw_fields unions.
    """
    merged: dict[str, dict] = {}
    # Order by priority: RSC first, then API, then snapshot.
    priority = {"rsc": 3, "official_api": 2, "snapshot": 1}
    ordered = []
    for r in results:
        for rec in r.records:
            if not rec.get("slug") or not rec.get("name"):
                continue
            ordered.append((priority.get(r.source, 0), r.source, rec))
    # highest priority first
    ordered.sort(key=lambda tup: -tup[0])
    for _prio, src_name, rec in ordered:
        slug = rec["slug"]
        if slug not in merged:
            merged[slug] = dict(rec)
            merged[slug]["source"] = src_name
            merged[slug]["provenance"] = {
                "sources": [src_name], "primary_source": src_name,
                "parser_version": next((r.parser_version for r in results if r.source == src_name), None),
                "fetched_at": next((r.fetched_at for r in results if r.source == src_name), None),
                "cached": bool(next((r.meta.get("cached") for r in results if r.source == src_name), False)),
            }
            merged[slug]["merged"] = {"primary": src_name, "also_from": []}
            continue
        dst = merged[slug]
        # fill blanks in dst from this (lower/equal priority) record
        for k, v in rec.items():
            if k == "hosts" and isinstance(v, list):
                existing = dst.setdefault("hosts", [])
                if not isinstance(existing, list):
                    existing = dst["hosts"] = []
                seen_hosts = {str(h.get("slug") or h.get("name")) for h in existing if isinstance(h, dict)}
                for host in v:
                    if not isinstance(host, dict):
                        continue
                    key = str(host.get("slug") or host.get("name"))
                    if key not in seen_hosts:
                        existing.append(host)
                        seen_hosts.add(key)
            elif isinstance(v, dict):
                if k not in dst or not isinstance(dst[k], dict):
                    dst[k] = {}
                for kk, vv in v.items():
                    if (dst[k].get(kk) is None) and vv is not None:
                        dst[k][kk] = vv
            elif k == "raw_fields":
                if not isinstance(dst.get("raw_fields"), dict):
                    dst["raw_fields"] = {}
                dst["raw_fields"].update(v or {})
            else:
                if dst.get(k) is None and v is not None:
                    dst[k] = v
        # record that this source contributed
        contrib = dst.setdefault("merged", {})
        srcset = contrib.setdefault("also_from", [])
        if src_name not in srcset:
            srcset.append(src_name)
        prov = dst.setdefault("provenance", {})
        sources = prov.setdefault("sources", [])
        if src_name not in sources:
            sources.append(src_name)
    return list(merged.values())


def apply_enrichment_cache(models: list[dict], cache_path: Path) -> int:
    """Backfill page/API-only fields from the legacy enrichment cache if the
    new RSC source lacks them (e.g. omniscience metrics for a model that
    dropped off AA's front page). Returns count of filled models."""
    if not cache_path.exists():
        return 0
    cache = read_json(cache_path) or {}
    cache_models = cache.get("models") or {}
    if not cache_models:
        return 0
    filled = 0
    for m in models:
        cached = cache_models.get(m.get("slug"))
        if not cached:
            continue
        # map legacy cache keys onto our schema
        gap_b = m.get("benchmarks") or {}
        keymap = {
            "gdpval_v2": "gdpval", "critpt": "critpt", "mmmu_pro": "mmmu_pro",
            "apex_agents_aa": "apex_agents", "it_bench_sre": "it_bench_sre",
            "omniscience_non_halluc": "omniscience_non_halluc",
        }
        for legacy_key, our_key in keymap.items():
            if gap_b.get(our_key) is None:
                v = (cached.get("benchmarks") or {}).get(legacy_key)
                if v is not None:
                    if not isinstance(m.get("benchmarks"), dict):
                        m["benchmarks"] = {}
                    m["benchmarks"][our_key] = v
        if m.get("agentic_index") is None:
            v = (cached.get("composite") or {}).get("agentic_index")
            if v is not None:
                m["agentic_index"] = v
        filled += 1
    return filled


def coverage_report(models: list[dict], results: list[SourceResult]) -> dict:
    """Summarize field coverage for the debugging report."""
    fields = [
        "intelligence_index", "coding_index", "math_index", "agentic_index",
        "omniscience_index", "context_tokens", "parameters_billions",
        "is_reasoning", "is_open_weights", "license", "size_class",
        "released", "creator",
    ]
    coverage = {
        f: sum(1 for m in models if m.get(f) is not None) for f in fields
    }
    bench_fields = set()
    for m in models:
        bench_fields.update((m.get("benchmarks") or {}).keys())
    bench_coverage = {
        f: sum(1 for m in models if (m.get("benchmarks") or {}).get(f) is not None)
        for f in sorted(bench_fields)
    }
    src_stats = {}
    for r in results:
        src_stats[r.source] = {
            "healthy": r.healthy, "records": len(r.records),
            "fetched_at": r.fetched_at, "errors": r.errors[:10],
        }
    return {
        "total_models": len(models),
        "field_coverage": coverage,
        "benchmark_coverage": bench_coverage,
        "sources": src_stats,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="AA private data pipeline")
    ap.add_argument("--no-api", action="store_true", help="skip official API source")
    ap.add_argument("--no-snapshot", action="store_true", help="skip snapshot source")
    ap.add_argument("--offline", action="store_true", help="use only cached/stale data")
    ap.add_argument("--refresh", action="store_true", help="force bypass of disk caches")
    ap.add_argument("--output", default=str(REPO_ROOT / "data" / "aa_models_v2.json"))
    ap.add_argument("--report", default=str(REPO_ROOT / "data" / "aa_pipeline_report.json"))
    ap.add_argument("--history-dir", default=str(REPO_ROOT / "data" / "history" / "rich"))
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    log = logging.getLogger("aa.pipeline")

    cache_dir = REPO_ROOT / "data" / "aa_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    results = load_all_sources(
        argparse.Namespace(
            api=not args.no_api, snapshot=not args.no_snapshot,
            refresh=args.refresh,
            offline=args.offline,
        ),
        cache_dir,
    )
    # report what each source produced
    for r in results:
        status = "OK" if r.healthy else "FAILED"
        log.info("[%s] %s: %d records (%s)", r.source, status, len(r.records),
                 ", ".join(r.errors[:3]) if r.errors else "no errors")

    # offline: if no live source is healthy, refuse to overwrite the last good
    # dataset rather than silently emitting empty data.
    any_healthy = any(r.healthy for r in results)
    previous = read_json(Path(args.output))
    if not any_healthy:
        if previous and previous.get("models"):
            log.warning("No live source healthy; keeping previous dataset "
                        "(%d models) as stale fallback.", len(previous["models"]))
            stale_report = {
                "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "status": "stale_fallback", "stale": True,
                "stale_reason": "no healthy source; previous dataset retained",
                "previous_generated_at": previous.get("generated_at"),
                "sources": {r.source: {"healthy": r.healthy, "records": len(r.records), "errors": r.errors[:10]} for r in results},
            }
            atomic_write_json(Path(args.report), stale_report)
            return 0
        log.error("No live AA source healthy and no previous dataset; aborting.")
        return 1

    validate_source_results(results)

    models = merge_records(results)
    n_filled = apply_enrichment_cache(models, REPO_ROOT / "data" / "enrichment_cache.json")

    # drift check on normalized schema (informational)
    drift = check_schema_drift(models, "merged", KNOWN_FIELDS)
    for d in drift:
        log.warning(d)

    # final dataset-level sanity
    all_rep = run_sanity(models, "merged", schema.MIN_MODELS_RSC)
    if not all_rep.passed:
        log.error("Final merged sanity FAILED: %s", "; ".join(all_rep.failures[:5]))
        return 1

    out = {
        "version": schema.EXPECTED_INDEX_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "models": sorted(models, key=lambda m: (m.get("intelligence_index") is not None, -(m.get("intelligence_index") or 0))),
        "coverage": coverage_report(models, results),
        "notes": [f"backfilled {n_filled} models from legacy enrichment cache"],
        "freshness": {"stale": False, "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "source_fetched_at": {r.source: r.fetched_at for r in results}},
    }
    atomic_write_json(Path(args.output), {
        "version": out["version"], "generated_at": out["generated_at"],
        "coverage": out["coverage"], "models": out["models"],
        "freshness": out["freshness"],
    })
    history_dir = Path(args.history_dir)
    if previous and previous.get("models"):
        stamp = out["generated_at"][:10]
        write_delta(history_dir / f"{stamp}.delta.json", diff_snapshots(previous, out, generated_at=out["generated_at"]))
        prune_deltas(history_dir, keep=104)
    atomic_write_json(Path(args.report), {
        "generated_at": out["generated_at"],
        "sources": coverage_report(models, results)["sources"],
        "field_coverage": coverage_report(models, results)["field_coverage"],
        "benchmark_coverage": coverage_report(models, results)["benchmark_coverage"],
        "total_models": len(models),
        "parser_versions": {
            "rsc": "0.2.0", "official_api": "0.1.0", "snapshot": "0.1.0",
        },
        "status": "fresh", "stale": False, "total_models": len(models),
        "freshness": out["freshness"],
    })
    log.info("Wrote %d models -> %s", len(models), args.output)
    log.info("Report -> %s", args.report)
    return 0


if __name__ == "__main__":
    sys.exit(main())