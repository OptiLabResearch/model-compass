#!/usr/bin/env python3.12
"""build_site_from_aa.py — Build the public site's models.json from the rich
private AA dataset (data/aa_models_v2.json) instead of the degraded Free-API
scrape.

WHY: the AA Free API no longer returns per-benchmark scores (they are now
Pro-only), and the legacy /models page scrape only enriches the ~28 top models.
So the old pipeline produced a models.json where ~175 of ~201 models had no
benchmarks and the latest models were missing. The RSC dataset built by
scripts/aa/ carries full benchmarks + pricing + performance + the newest models
for 600+ models, so we source the site from it.

This script maps each rich record onto the EXACT legacy site schema that the
frontend (public/assets/models.js) and the existing validator consume, so no
UI change is needed.

Usage:
    python3.12 -m scripts.aa.orchestrate            # first, build rich dataset
    python3.12 scripts/build_site_from_aa.py        # then, build site models.json
    python3.12 scripts/build_site_from_aa.py --output public/data/models.json

Exits non-zero if the rich dataset is missing/stale, or if the output fails the
same validator the old pipeline used.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RICH = REPO_ROOT / "data" / "aa_models_v2.json"
DEFAULT_OUTPUT = REPO_ROOT / "public" / "data" / "models.json"
MIN_RICH_MODELS = 250
MAX_SITE_MODELS = 8000

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,199}$")

# Featured + routing + notes shipped alongside the old pipeline. Kept here so
# this script is self-contained; mirror any edits made to fetch_aa_models.py.
FEATURED_SLUGS = {
    'claude-fable-5', 'claude-opus-4-8', 'claude-sonnet-5',
    'gpt-5-6-sol', 'gpt-5-6-terra', 'gpt-5-6-luna',
    'kimi-k3', 'grok-4-5',
    'glm-5-2', 'muse-spark-1-1',
    'gemini-3-6-flash', 'gemini-3-1-pro-preview',
    'qwen3-7-max',
    'minimax-m3', 'qwen3-7-plus',
    'mimo-v2-5-pro', 'mimo-v2-5-0424',
    'deepseek-v4-pro', 'deepseek-v4-flash',
}
OPENROUTER_SLUGS = {
    'deepseek-v4-pro': 'deepseek/deepseek-v4-pro',
    'minimax-m3': 'minimax/minimax-m3',
    'kimi-k3': 'moonshotai/kimi-k3',
    'mimo-v2-5-pro': 'xiaomi/mimo-v2.5-pro',
    'mimo-v2-5-0424': 'xiaomi/mimo-v2-5',
    'glm-5-2': 'z-ai/glm-5.2',
    'qwen3-7-max': 'qwen/qwen3.7-max',
    'qwen3-7-plus': 'qwen/qwen3.7-plus',
    'muse-spark-1-1': 'meta-llama/muse-spark-1.1',
    'grok-4-5': 'x-ai/grok-4.5',
}
RELEASE_WINDOW_DAYS = 183


def _num(v, d=2):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return round(v, d)
    return None


def _blend3(m):
    p = m.get('pricing') or {}
    b = p.get('blended_3_1')
    if isinstance(b, (int, float)):
        return round(b, 2)
    i, o = p.get('input'), p.get('output')
    if isinstance(i, (int, float)) and isinstance(o, (int, float)):
        return round((3 * i + o) / 4.0, 2)
    return None


def _blend721(m):
    p = m.get('pricing') or {}
    b = p.get('blended_7_2_1')
    if isinstance(b, (int, float)):
        return round(b, 2)
    i, o = p.get('input'), p.get('output')
    if isinstance(i, (int, float)) and isinstance(o, (int, float)):
        return round((7 * i + 2 * o) / 10.0, 2)
    return None


def map_benchmarks(rich: dict) -> dict:
    b = rich.get('benchmarks') or {}
    out = {
        "gpqa_diamond": _num(b.get('gpqa'), 1),
        "hle": _num(b.get('hle'), 1),
        "scicode": _num(b.get('scicode'), 1),
        "ifbench": _num(b.get('ifbench'), 1),
        "lcr": _num(b.get('lcr'), 1),
        "tau2_bench": _num(b.get('tau2'), 1),
        "tau3_banking": _num(b.get('tau_banking'), 1),
        "terminalbench_hard": _num(b.get('terminalbench_hard'), 1),
        "terminalbench_v2_1": _num(b.get('terminalbench_v21'), 1),
        "mmlu_pro": _num(b.get('mmlu_pro'), 1),
        "livecodebench": _num(b.get('livecodebench'), 1),
        "math_500": _num(b.get('math_500'), 1),
        "aime": _num(b.get('aime'), 1),
        "aime25": _num(b.get('aime25'), 1),
        "gdpval_v2": _num(b.get('gdpval'), 1),
        "critpt": _num(b.get('critpt'), 1),
        "mmmu_pro": _num(b.get('mmmu_pro'), 1),
        "apex_agents_aa": _num(b.get('apex_agents'), 1),
        "it_bench_sre": _num(b.get('it_bench_sre'), 1),
        "omniscience_accuracy": _num(b.get('omniscience_accuracy'), 1),
        "omniscience_hallucination_rate": _num(b.get('omniscience_hallucination_rate'), 1),
        "omniscience_non_halluc": _num(b.get('omniscience_non_halluc'), 1),
    }
    # sanity: omniscience raw must be bounded to 0..100 per site validator;
    # AA's raw omniscience score can be negative/large, so clamp like legacy did.
    o = _num(b.get('omniscience'), 1)
    if o is not None:
        out['omniscience'] = max(0, min(100, o))
    return out


def map_performance(rich: dict) -> dict:
    p = rich.get('performance') or {}
    e2e = None
    total_e2e = _num(p.get('median_e2e_500tok_seconds'), 2)
    if total_e2e is not None:
        e2e = {"total": total_e2e, "input": None, "reasoning": 0, "answer": None}
    return {
        "output_speed_tps": _num(p.get('median_output_speed_tps'), 2),
        "ttft_seconds_total": _num(p.get('median_ttft_seconds'), 2),
        "ttft_seconds_answer": _num(p.get('median_ttfa_seconds'), 2),
        "end_to_end_500tok": e2e,
    }


def to_site_model(rich: dict) -> dict:
    slug = (rich.get('slug') or '').strip()
    name = rich.get('name') or slug
    b = map_benchmarks(rich)
    perf = map_performance(rich)
    p = rich.get('pricing') or {}
    im = rich.get('input_modalities') or {}
    om = rich.get('output_modalities') or {}

    def mod(d):
        return {"text": bool(d.get('text')), "image": bool(d.get('image')),
                "audio": bool(d.get('audio')), "video": bool(d.get('video'))} if d else None

    cpt = rich.get('cost_per_intelligence_task_usd')
    cpt_out: dict = {"total": None, "input": None, "output": None,
                     "cacheRead": None, "cacheWrite": None,
                     "nonCacheInput": None, "reasoning": None, "answer": None}
    if isinstance(cpt, (int, float)):
        cpt_out["total"] = _num(cpt, 4)

    intel = _num(rich.get('intelligence_index'), 2)
    intel = max(0, min(100, intel)) if intel is not None else None

    model = {
        "name": name,
        "slug": slug,
        "aa_url": f"https://artificialanalysis.ai/models/{slug}" if slug else None,
        "creator": rich.get('creator'),
        "released": rich.get('released'),
        "knowledge_cutoff": rich.get('knowledge_cutoff'),
        "is_reasoning": bool(rich.get('is_reasoning')),
        "is_open_weights": bool(rich.get('is_open_weights')),
        "deprecated": bool(rich.get('deprecated')),
        "commercial_allowed": rich.get('commercial_allowed'),
        "license": rich.get('license'),
        "license_url": rich.get('license_url'),
        "size_class": rich.get('size_class'),
        "context_tokens": _num(rich.get('context_tokens'), 0),
        "parameters_billions": _num(rich.get('parameters_billions'), 2),
        "active_params_billions": _num(rich.get('active_params_billions'), 2),
        "input_modalities": mod(im),
        "output_modalities": mod(om),
        "composite": {
            "intelligence_index_v4_1": intel,
            "coding_index": _num(rich.get('coding_index'), 2),
            "math_index": _num(rich.get('math_index'), 2),
            "agentic_index": _num(rich.get('agentic_index'), 2),
            "omniscience_index": _num(rich.get('omniscience_index'), 1),
        },
        "benchmarks": b,
        "pricing_per_m_tokens": {
            "input": _num(p.get('input'), 4),
            "output": _num(p.get('output'), 4),
            "blended_3_1": _blend3(rich),
            "blended_7_2_1": _blend721(rich),
            "blended_1_1": None,
            "cache_hit": _num(p.get('cache_hit'), 4),
            "cache_write": _num(p.get('cache_write'), 4),
        },
        "intelligence_evaluation_total_cost_usd": _num(
            rich.get('intelligence_eval_total_cost_usd'), 2),
        "cost_per_intelligence_task_usd": cpt_out,
        "cost_per_eval_breakdown_usd": {},
        "time_per_task_seconds": _num(rich.get('time_per_task_seconds'), 1),
        "output_tokens_per_task": rich.get('output_tokens_per_task'),
        "performance": perf,
        "output_speed_by_prompt_length": [],
        "featured": slug in FEATURED_SLUGS,
        "openrouter_slug": OPENROUTER_SLUGS.get(slug),
        "note": None,
        "has_rich_data": b.get('omniscience_non_halluc') is not None or b.get('gpqa_diamond') is not None,
        "data_sources": {
            "documented_free_api": rich.get('source') == 'official_api',
            "page_enrichment": False,
            "aa_pipeline": True,
        },
        "short_name": rich.get('short_name') or name,
    }
    model['derived'] = build_derived(model)
    return model


def build_derived(m: dict) -> dict:
    """Same derived metrics the old pipeline computed (kept for the UI)."""
    intel = m['composite'].get('intelligence_index_v4_1')
    blend = m['pricing_per_m_tokens'].get('blended_3_1')
    cpt = m['cost_per_intelligence_task_usd'].get('total') if isinstance(
        m['cost_per_intelligence_task_usd'], dict) else m['cost_per_intelligence_task_usd']
    nh = m['benchmarks'].get('omniscience_non_halluc')
    speed = m['performance'].get('output_speed_tps')
    ttft_a = m['performance'].get('ttft_seconds_answer')
    d = {}
    if intel and blend and blend > 0:
        d['value_intelligence_per_dollar_blend'] = round(intel / blend, 1)
    if intel and cpt and cpt > 0:
        d['value_intelligence_per_dollar_task'] = round(intel / cpt, 1)
    if intel and nh:
        d['safety_composite'] = round(intel * 0.4 + nh * 0.6, 1)
    if speed:
        d['throughput_tps'] = speed
        d['speed_tier'] = 2 if speed >= 100 else 1 if speed >= 50 else 0
    if ttft_a is not None:
        d['latency_ttft_seconds'] = ttft_a
        d['latency_tier'] = 2 if ttft_a <= 5 else 1 if ttft_a <= 20 else 0
    return d


def validate_output(models: list, prev_path: Path) -> None:
    """Mirror of fetch_aa_models.validate_output_models (kept self-contained)."""
    if not len(FEATURED_SLUGS) <= len(models) <= MAX_SITE_MODELS:
        raise RuntimeError(f"Output model count {len(models)} is implausible")
    seen = set()
    for model in models:
        slug = model.get('slug')
        if not isinstance(slug, str) or not SLUG_RE.fullmatch(slug) or slug in seen:
            raise RuntimeError(f"Output contains invalid/duplicate slug: {slug}")
        seen.add(slug)
        if model.get('aa_url') != f"https://artificialanalysis.ai/models/{slug}":
            raise RuntimeError(f"Output contains unexpected AA URL for {slug}")
        if not model.get('name'):
            raise RuntimeError(f"Output contains missing name for {slug}")
        for value in (model.get('benchmarks') or {}).values():
            if value is not None and (not isinstance(value, (int, float))
                                      or not 0 <= value <= 100):
                raise RuntimeError(f"Out-of-range benchmark for {slug}: {value}")
        for value in (model.get('pricing_per_m_tokens') or {}).values():
            if value is not None and (not isinstance(value, (int, float))
                                      or not 0 <= value <= 1_000_000):
                raise RuntimeError(f"Invalid pricing for {slug}: {value}")
    missing = FEATURED_SLUGS - seen
    if missing:
        raise RuntimeError("Missing featured slugs: " + ", ".join(sorted(missing)))
    if prev_path.exists():
        try:
            prev = json.loads(prev_path.read_text(encoding='utf-8'))
            prev_count = len(prev.get('models') or [])
        except (OSError, json.JSONDecodeError, TypeError):
            prev_count = 0
        if prev_count and len(models) < math.floor(prev_count * 0.6):
            raise RuntimeError(
                f"Model count dropped from {prev_count} to {len(models)}; "
                "refusing a destructive refresh")


def select_models(records: list, days: int) -> list:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date()
    kept = []
    for r in records:
        if r.get('slug') in FEATURED_SLUGS:
            kept.append(r)
            continue
        rd = r.get('released')
        if not rd:
            continue
        try:
            if datetime.fromisoformat(rd).date() >= cutoff:
                kept.append(r)
        except ValueError:
            continue
    return kept


def atomic_write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix=f'.{path.name}.', suffix='.tmp',
                                         delete=False) as f:
            tmp = f.name
            json.dump(obj, f, indent=2, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split('\n')[2] or "")
    ap.add_argument('--rich', type=Path, default=DEFAULT_RICH)
    ap.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument('--days', type=int, default=RELEASE_WINDOW_DAYS)
    args = ap.parse_args()

    if not args.rich.exists():
        print(f"ERROR: rich dataset {args.rich} missing. "
              "Run `python3.12 -m scripts.aa.orchestrate` first.", file=sys.stderr)
        return 1
    data = json.loads(args.rich.read_text(encoding='utf-8'))
    records = data.get('models') or []
    if len(records) < MIN_RICH_MODELS:
        print(f"ERROR: rich dataset has only {len(records)} models "
              f"(min {MIN_RICH_MODELS}).", file=sys.stderr)
        return 1

    # sticky featured-first ordering by intelligence, like the old pipeline
    kept = select_models(records, args.days)
    models = [to_site_model(r) for r in kept]
    models.sort(key=lambda m: (not m['featured'],
                               -(m['composite']['intelligence_index_v4_1'] or 0)))

    validate_output(models, args.output)

    out = {
        "version": data.get('version', '4.1'),
        "intelligence_index_version": "4.1",
        "scraped_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_url": "https://artificialanalysis.ai/leaderboards/providers",
        "scrape_method": "AA RSC leaderboard payload via scripts/aa pipeline",
        "intelligence_index_methodology": (
            "AA Intelligence Index v4.1 = composite of 9 evaluations: "
            "GDPval-AA v2, τ³-Banking, Terminal-Bench v2.1, SciCode, HLE, "
            "GPQA Diamond, CritPt, AA-Omniscience, AA-LCR"),
        "models": models,
        "coverage": {
            "total": len(models),
            "featured": sum(1 for m in models if m['featured']),
            "with_rich_metrics": sum(1 for m in models
                                     if m['benchmarks'].get('omniscience_non_halluc') is not None),
            "with_documented_free_api": sum(1 for m in models
                                           if m['data_sources']['documented_free_api']),
            "featured_without_rich_metrics": sorted(
                m['slug'] for m in models
                if m['featured'] and m['benchmarks'].get('omniscience_non_halluc') is None),
        },
    }

    atomic_write_json(args.output, out)
    print(f"  Saved {args.output} ({args.output.stat().st_size} bytes, "
          f"{len(models)} models)")
    n_rich = out['coverage']['with_rich_metrics']
    print(f"  {n_rich}/{len(models)} models with rich (non-hallucination) metrics")
    return 0


if __name__ == "__main__":
    sys.exit(main())