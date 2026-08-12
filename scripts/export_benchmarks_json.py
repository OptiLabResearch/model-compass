#!/usr/bin/env python3
"""
export_benchmarks_json.py — Expose normalized benchmark dataset as static JSON.

Usage:
    python3 scripts/export_benchmarks_json.py [--output public/data/benchmarks.json]

Transforms public/data/models.json into public/data/benchmarks.json matching the
format consumed by external agents / GPT integrations.
"""

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODELS_JSON = REPO_ROOT / "public" / "data" / "models.json"
DEFAULT_BENCHMARKS_JSON = REPO_ROOT / "public" / "data" / "benchmarks.json"


def model_to_benchmark(m: dict) -> dict:
    pricing = m.get("pricing_per_m_tokens") or {}
    composite = m.get("composite") or {}
    bench = m.get("benchmarks") or {}
    perf = m.get("performance") or {}

    return {
        "slug": m.get("slug"),
        "name": m.get("name"),
        "creator": m.get("creator"),
        "released": m.get("released"),
        "input_price": pricing.get("input"),
        "output_price": pricing.get("output"),
        "blended_price": pricing.get("blended_3_1"),
        "intelligence": composite.get("intelligence_index_v4_1"),
        "coding": composite.get("coding_index"),
        "agentic": composite.get("agentic_index"),
        "omniscience": composite.get("omniscience_index"),
        "gpqa": bench.get("gpqa_diamond"),
        "hle": bench.get("hle"),
        "critpt": bench.get("critpt"),
        "non_hallucination": bench.get("omniscience_non_halluc"),
        "ifbench": bench.get("ifbench"),
        "lcr": bench.get("lcr"),
        "tau2_bench": bench.get("tau2_bench"),
        "tau3_banking": bench.get("tau3_banking"),
        "gdpval": bench.get("gdpval_v2"),
        "terminalbench_hard": bench.get("terminalbench_hard"),
        "terminalbench_2_1": bench.get("terminalbench_v2_1"),
        "scicode": bench.get("scicode"),
        "mmmu_pro": bench.get("mmmu_pro"),
        "speed_tps": perf.get("output_speed_tps"),
        "ttft_seconds": perf.get("ttft_seconds_total"),
        "ttfa_seconds": perf.get("ttft_seconds_answer"),
    }


def build_benchmarks_payload(data: dict) -> dict:
    scraped_at = data.get("scraped_at") or ""
    if len(scraped_at) >= 10 and scraped_at[4] == "-" and scraped_at[7] == "-":
        updated_at = scraped_at[:10]
    else:
        updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    raw_models = data.get("models") or []
    benchmarks_models = [model_to_benchmark(m) for m in raw_models]

    return {
        "updated_at": updated_at,
        "source": "Artificial Analysis via Model Compass",
        "models": benchmarks_models,
    }


def export_benchmarks(data: dict, out_path: Path) -> None:
    payload = build_benchmarks_payload(data)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=out_path.parent,
            prefix=".benchmarks.", suffix=".tmp", delete=False,
        ) as f:
            tmp_name = f.name
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, out_path)
    finally:
        if tmp_name and os.path.exists(tmp_name):
            os.unlink(tmp_name)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument(
        "--models-json", type=Path, default=DEFAULT_MODELS_JSON,
        help="Path to models.json input",
    )
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_BENCHMARKS_JSON,
        help="Path to benchmarks.json output",
    )
    args = parser.parse_args()

    if not args.models_json.exists():
        print(f"ERROR: input file {args.models_json} does not exist", file=sys.stderr)
        return 1

    try:
        data = json.loads(args.models_json.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: invalid JSON in {args.models_json}: {exc}", file=sys.stderr)
        return 1

    export_benchmarks(data, args.output)
    count = len(data.get("models") or [])
    print(f"Wrote {args.output} ({count} models)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
