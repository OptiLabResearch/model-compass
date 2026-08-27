#!/usr/bin/env python3
"""
export_history_csv.py — Flatten public/data/models.json into a dated CSV snapshot
under data/history/, matching the column layout of the existing history files.

Usage:
    python3 scripts/export_history_csv.py [--date YYYY-MM-DD]

Writes data/history/<date>.csv (UTC today by default). Intended to run after
scripts/build_site_from_aa.py in the weekly refresh workflow.
"""

import csv
import json
import os
import argparse
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS_JSON = REPO_ROOT / "public" / "data" / "models.json"
HISTORY_DIR = REPO_ROOT / "data" / "history"

# Mirrors the All Models table column order. AA stopped publishing MMLU-Pro,
# LiveCodeBench, MATH-500, AIME and the math index — those columns were all "—"
# and were dropped in favour of metrics AA does still report. Snapshots written
# before 2026-07-14 use the older, wider header.
HEADER = [
    "name", "creator", "release_date", "in_$/M", "out_$/M", "blend_3to1_$/M",
    "intelligence", "coding", "agentic", "omniscience", "gpqa_%", "hle_%",
    "critpt_%", "non_halluc_%", "ifbench_%", "lcr_%", "tau2_%", "tau_banking_%",
    "gdpval_%", "terminalbench_hard_%", "terminalbench_v2_1_%", "scicode_%",
    "mmmu_pro_%", "speed_tps", "ttft_s", "ttfa_s", "slug",
]


def fmt(value):
    if value is None:
        return "—"
    if isinstance(value, str) and value.lstrip('\t\r').startswith(('=', '+', '-', '@')):
        return "'" + value
    return value


def to_row(m):
    pricing = m.get("pricing_per_m_tokens") or {}
    composite = m.get("composite") or {}
    bench = m.get("benchmarks") or {}
    perf = m.get("performance") or {}
    return [
        m.get("name"),
        m.get("creator"),
        m.get("released"),
        fmt(pricing.get("input")),
        fmt(pricing.get("output")),
        fmt(pricing.get("blended_3_1")),
        fmt(composite.get("intelligence_index_v4_1")),
        fmt(composite.get("coding_index")),
        fmt(composite.get("agentic_index")),
        fmt(composite.get("omniscience_index")),
        fmt(bench.get("gpqa_diamond")),
        fmt(bench.get("hle")),
        fmt(bench.get("critpt")),
        fmt(bench.get("omniscience_non_halluc")),
        fmt(bench.get("ifbench")),
        fmt(bench.get("lcr")),
        fmt(bench.get("tau2_bench")),
        fmt(bench.get("tau3_banking")),
        fmt(bench.get("gdpval_v2")),
        fmt(bench.get("terminalbench_hard")),
        fmt(bench.get("terminalbench_v2_1")),
        fmt(bench.get("scicode")),
        fmt(bench.get("mmmu_pro")),
        fmt(perf.get("output_speed_tps")),
        # AA no longer reports a separate time-to-first-reasoning-chunk, so this
        # is time to first chunk of any kind, matching the All Models table.
        fmt(perf.get("ttft_seconds_total")),
        fmt(perf.get("ttft_seconds_answer")),
        m.get("slug"),
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="Override date (YYYY-MM-DD), defaults to today (UTC)")
    args = parser.parse_args()

    date_str = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as exc:
        raise SystemExit("--date must use YYYY-MM-DD") from exc

    data = json.loads(MODELS_JSON.read_text(encoding="utf-8"))
    if not isinstance(data.get("models"), list):
        raise SystemExit(f"Invalid models payload in {MODELS_JSON}")

    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    out_path = HISTORY_DIR / f"{date_str}.csv"
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", dir=HISTORY_DIR,
            prefix=f".{date_str}.", suffix=".tmp", delete=False,
        ) as f:
            tmp_name = f.name
            w = csv.writer(f, lineterminator="\n")
            w.writerow(HEADER)
            for m in data["models"]:
                w.writerow(to_row(m))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, out_path)
    finally:
        if tmp_name and os.path.exists(tmp_name):
            os.unlink(tmp_name)

    print(f"Wrote {out_path} ({len(data['models'])} models)")


if __name__ == "__main__":
    main()
