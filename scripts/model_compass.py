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


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def engine(args) -> DecisionEngine:
    data = load_json(Path(args.data))
    access = {}
    if args.access and Path(args.access).exists():
        access = load_json(Path(args.access)).get("models", {})
    return DecisionEngine(data.get("models", []), access=access)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Model Compass model-intelligence CLI")
    p.add_argument("--data", default=str(REPO / "data/aa_models_v2.json"))
    p.add_argument("--access", default=str(REPO / ".model-compass-access.json"),
                   help="optional gitignored access overlay")
    sub = p.add_subparsers(dest="command", required=True)
    ls = sub.add_parser("list"); ls.add_argument("query", nargs="?"); ls.add_argument("--limit", type=int, default=20)
    rec = sub.add_parser("recommend"); rec.add_argument("profile", choices=sorted(PROFILES)); rec.add_argument("--limit", type=int, default=10); rec.add_argument("--available-only", action="store_true")
    par = sub.add_parser("pareto"); par.add_argument("dimensions", nargs="+", help="e.g. intelligence_index cost"); par.add_argument("--limit", type=int, default=50)
    bak = sub.add_parser("backup"); bak.add_argument("primary"); bak.add_argument("--limit", type=int, default=10); bak.add_argument("--allow-same-provider", action="store_true")
    ex = sub.add_parser("explain"); ex.add_argument("slug")
    ch = sub.add_parser("changes"); ch.add_argument("--previous", type=Path, required=True); ch.add_argument("--current", type=Path, default=Path("data/aa_models_v2.json"))
    health = sub.add_parser("health")
    args = p.parse_args(argv)
    if args.command == "changes":
        print(json.dumps(diff_snapshots(load_json(args.previous), load_json(args.current)), indent=2, sort_keys=True)); return 0
    db = engine(args)
    if args.command == "list":
        rows = [m for m in db.models if not args.query or args.query.lower() in json.dumps(m).lower()]
        print(json.dumps([{k: m.get(k) for k in ("slug", "name", "creator", "intelligence_index", "coding_index")} for m in rows[:args.limit]], indent=2)); return 0
    if args.command == "recommend":
        result = db.recommend(args.profile, limit=args.limit, available_only=args.available_only)
        print(json.dumps(result, indent=2, sort_keys=True)); return 0
    if args.command == "pareto":
        print(json.dumps(db.pareto(args.dimensions)[:args.limit], indent=2, sort_keys=True)); return 0
    if args.command == "backup":
        print(json.dumps(db.backups(args.primary, providers=not args.allow_same_provider, limit=args.limit), indent=2, sort_keys=True)); return 0
    if args.command == "explain":
        m = db.get(args.slug)
        if not m: print(json.dumps({"error": "model not found", "slug": args.slug})); return 1
        print(json.dumps(db.explain(m), indent=2, sort_keys=True)); return 0
    if args.command == "health":
        report = load_json(REPO / "data/aa_pipeline_report.json")
        print(json.dumps({"status": report.get("status", "unknown"), "stale": report.get("stale", True), "generated_at": report.get("generated_at"), "sources": report.get("sources", {}), "total_models": report.get("total_models")}, indent=2, sort_keys=True)); return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
