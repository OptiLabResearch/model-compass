#!/usr/bin/env python3
"""Stable, deterministic CLI for Model Compass intelligence queries."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
from aa.decision import DecisionEngine, PROFILES  # noqa: E402
from aa.history import diff_snapshots  # noqa: E402
from aa.provider_query import ProviderDB, CodingAgentDB  # noqa: E402
from aa.identity import load_aliases, resolve  # noqa: E402


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def engine(args) -> DecisionEngine:
    data = load_json(Path(args.data))
    access = {}
    if args.access and Path(args.access).exists():
        access = load_json(Path(args.access)).get("models", {})
    return DecisionEngine(data.get("models", []), access=access)


def _nonnegative_limit(value):
    value = int(value)
    if value < 0:
        raise argparse.ArgumentTypeError("limit must be non-negative")
    return value


def _add_output_options(parser, *, limit=None):
    parser.add_argument("--full", action="store_true",
                        help="include complete records; default output is bounded")
    parser.add_argument("--compact", action="store_true",
                        help="emit one-line JSON")
    if limit is not None:
        parser.add_argument("--limit", type=_nonnegative_limit, default=limit)
    return parser


def _emit(payload, args) -> None:
    if args.compact:
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True,
                         allow_nan=False))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True,
                         allow_nan=False))


def _model_summary(model):
    """Return decision-relevant fields without raw acquisition payloads."""
    summary = {}
    for key in ("slug", "name", "creator", "source", "intelligence_index",
                "coding_index", "agentic_index", "context_tokens",
                "is_reasoning", "is_open_weights"):
        if key in model:
            summary[key] = model[key]
    for parent, keys in {
        "pricing": ("input", "output", "blended_3_1"),
        "performance": ("median_output_speed_tps", "median_ttft_seconds",
                        "median_ttfa_seconds"),
    }.items():
        values = model.get(parent)
        if isinstance(values, dict):
            summary[parent] = {key: values[key] for key in keys if key in values}
    hosts = model.get("hosts")
    if isinstance(hosts, list):
        summary["host_count"] = len(hosts)
        summary["hosts"] = [
            {key: host[key] for key in ("slug", "name") if key in host}
            for host in hosts[:20] if isinstance(host, dict)
        ]
        if len(hosts) > 20:
            summary["hosts_truncated"] = True
    provenance = model.get("provenance")
    if isinstance(provenance, dict):
        summary["provenance"] = {
            key: provenance[key]
            for key in ("sources", "primary_source", "source_agreement", "fetched_at",
                        "cached", "fresh")
            if key in provenance
        }
    merged = model.get("merged")
    if isinstance(merged, dict):
        summary["merged"] = {
            key: merged[key] for key in ("also_from", "primary_source") if key in merged
        }
    return summary


def _recommendation_view(result, full):
    if full:
        return result
    recommendations = []
    for model in result.get("recommendations", []):
        row = _model_summary(model)
        for key in ("recommendation_score", "explanation"):
            if key in model:
                row[key] = model[key]
        recommendations.append(row)
    return {
        key: result[key]
        for key in ("profile", "profile_version", "strategy", "metric", "candidate_count")
        if key in result
    } | {"recommendations": recommendations}


def _model_list_view(rows, full):
    return rows if full else [_model_summary(row) for row in rows]


def _identity_view(data, *, full, limit):
    groups = {
        "unresolved": data.get("unresolved", []),
        "ambiguous": data.get("ambiguous", []),
        "conflicts": data.get("conflicts", []),
    }
    if full:
        return {"health": data.get("health", {}), **groups}
    return {
        "health": data.get("health", {}),
        "counts": {key: len(rows) for key, rows in groups.items()},
        "limit": limit,
        "samples": {key: rows[:limit] for key, rows in groups.items()},
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Model Compass model-intelligence CLI")
    p.add_argument("--data", default=str(REPO / "data/aa_models_v2.json"))
    p.add_argument("--access", default=str(REPO / ".model-compass-access.json"),
                   help="optional gitignored access overlay")
    p.add_argument("--providers-data", default=str(REPO / "data/openrouter_observations.json"))
    p.add_argument("--agents-data", default=str(REPO / "data/coding_agent_observations.json"))
    p.add_argument("--accuracy-data", default=str(REPO / "data/endpoint_accuracy_observations.json"))
    p.add_argument("--identity-data", default=str(REPO / "data/identity_mappings.json"))
    sub = p.add_subparsers(dest="command", required=True)
    ls = sub.add_parser("list"); ls.add_argument("query", nargs="?"); _add_output_options(ls, limit=20)
    rec = sub.add_parser("recommend"); rec.add_argument("profile", choices=sorted(PROFILES)); rec.add_argument("--available-only", action="store_true"); _add_output_options(rec, limit=10)
    par = sub.add_parser("pareto"); par.add_argument("dimensions", nargs="+", help="e.g. intelligence_index cost"); _add_output_options(par, limit=50)
    bak = sub.add_parser("backup"); bak.add_argument("primary"); bak.add_argument("--allow-same-provider", action="store_true"); _add_output_options(bak, limit=10)
    ex = sub.add_parser("explain"); ex.add_argument("slug"); _add_output_options(ex)
    providers = sub.add_parser("providers"); providers.add_argument("model_id"); _add_output_options(providers)
    rp = sub.add_parser("recommend-provider"); rp.add_argument("model_id"); rp.add_argument("--profile", choices=["interactive", "batch", "accuracy-first"], default="interactive"); rp.add_argument("--require-accuracy-evidence", action="store_true"); rp.add_argument("--min-accuracy", type=float); rp.add_argument("--disallow-unknown", action="store_true"); _add_output_options(rp)
    ea = sub.add_parser("endpoint-accuracy"); ea.add_argument("model_id"); _add_output_options(ea, limit=20)
    agents = sub.add_parser("agents"); _add_output_options(agents, limit=10)
    ra = sub.add_parser("recommend-agent"); ra.add_argument("metric", choices=["coding_agent_index", "cost", "time"], default="coding_agent_index"); _add_output_options(ra, limit=10)
    access = sub.add_parser("access"); _add_output_options(access)
    ch = sub.add_parser("changes"); ch.add_argument("--previous", type=Path, required=True); ch.add_argument("--current", type=Path, default=Path("data/aa_models_v2.json")); _add_output_options(ch)
    health = sub.add_parser("health"); _add_output_options(health)
    identity_health = sub.add_parser("identity-health"); _add_output_options(identity_health)
    unresolved = sub.add_parser("unresolved-identities"); _add_output_options(unresolved, limit=20)
    args = p.parse_args(argv)
    if args.command == "changes":
        _emit(diff_snapshots(load_json(args.previous), load_json(args.current)), args); return 0
    model_commands = {"list", "recommend", "pareto", "backup", "explain"}
    db = engine(args) if args.command in model_commands else None
    if args.command == "list":
        rows = [m for m in db.models if not args.query or args.query.lower() in json.dumps(m).lower()]
        _emit(_model_list_view(rows[:args.limit], args.full), args); return 0
    if args.command == "recommend":
        result = db.recommend(args.profile, limit=args.limit, available_only=args.available_only)
        _emit(_recommendation_view(result, args.full), args); return 0
    if args.command == "pareto":
        _emit(_model_list_view(db.pareto(args.dimensions)[:args.limit], args.full), args); return 0
    if args.command == "backup":
        _emit(_model_list_view(db.backups(args.primary, providers=not args.allow_same_provider, limit=args.limit), args.full), args); return 0
    if args.command == "explain":
        m = db.get(args.slug)
        if not m: _emit({"error": "model not found", "slug": args.slug}, args); return 1
        _emit(db.explain(m), args); return 0
    if args.command == "health":
        report = load_json(REPO / "data/aa_pipeline_report.json")
        identity = load_json(Path(args.identity_data)) if Path(args.identity_data).exists() else {}
        accuracy = load_json(Path(args.accuracy_data)) if Path(args.accuracy_data).exists() else {}
        _emit({"status": report.get("status", "unknown"), "stale": report.get("stale", True), "generated_at": report.get("generated_at"), "sources": report.get("sources", {}), "total_models": report.get("total_models"), "endpoint_accuracy": {"status": "fresh" if accuracy else "not_present", "coverage": accuracy.get("coverage", {})}, "identity": identity.get("health", {})}, args); return 0
    if args.command == "providers":
        _emit(ProviderDB.from_file(args.providers_data, args.accuracy_data, args.identity_data).providers(args.model_id), args); return 0
    if args.command == "recommend-provider":
        result = ProviderDB.from_file(args.providers_data, args.accuracy_data, args.identity_data).best_provider(args.model_id, args.profile, require_accuracy_evidence=args.require_accuracy_evidence, min_accuracy=args.min_accuracy, allow_unknown=not args.disallow_unknown)
        _emit(result or {"error": "model/provider not found", "model_id": args.model_id}, args); return 0 if result else 1
    if args.command == "endpoint-accuracy":
        data = load_json(Path(args.accuracy_data)) if Path(args.accuracy_data).exists() else {"observations": []}
        rows = [o for o in data.get("observations", []) if o.get("model_slug") == args.model_id]
        observations = rows if args.full else rows[:args.limit]
        _emit({"model_id": args.model_id, "coverage": data.get("coverage", {}),
               "observation_count": len(rows), "returned": len(observations),
               "limit": None if args.full else args.limit,
               "observations": observations}, args); return 0
    if args.command == "agents":
        _emit(CodingAgentDB.from_file(args.agents_data).best(limit=args.limit), args); return 0
    if args.command == "recommend-agent":
        db = CodingAgentDB.from_file(args.agents_data)
        rows = db.best(limit=args.limit) if args.metric == "coding_agent_index" else db.cheapest(limit=args.limit) if args.metric == "cost" else db.fastest(limit=args.limit)
        _emit(rows, args); return 0
    if args.command == "access":
        overlay = load_json(Path(args.access)) if args.access and Path(args.access).exists() else {"models": {}}
        _emit({"channels": overlay.get("channels", {}), "models": sorted(overlay.get("models", {})), "count": len(overlay.get("models", {}))}, args); return 0
    if args.command in {"identity-health", "unresolved-identities"}:
        data = load_json(Path(args.identity_data)) if Path(args.identity_data).exists() else {"health": {}, "unresolved": [], "ambiguous": [], "conflicts": []}
        if args.command == "identity-health":
            _emit(data.get("health", {}), args)
        else:
            _emit(_identity_view(data, full=args.full, limit=args.limit), args)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
