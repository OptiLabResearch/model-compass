#!/usr/bin/env python3.12
"""Build the public site's models.json from the rich private AA dataset.

WHY: the AA Free API no longer returns per-benchmark scores (they are now
Pro-only), and the retained legacy /models page scrape only enriches a
small default subset. The old pipeline therefore left most models without
benchmarks and could miss the latest models. The RSC dataset built by
scripts/aa/ carries full benchmarks + pricing + performance, so we source the
site from it.

This script maps each rich record onto the public site schema consumed by the
frontend (public/assets/models.js). The shared public contract is defined in
scripts/public_contract.py.

Usage:
    python3 -m scripts.aa.orchestrate            # first, build rich dataset
    python3 scripts/build_site_from_aa.py            # then, build site models.json
    python3 scripts/build_site_from_aa.py --output public/data/models.json \
        --as-of 2026-08-23

Exits non-zero if the rich dataset is missing/stale, or if the output fails the
public contract validator.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from public_contract import (  # noqa: E402
    FEATURED_SLUGS,
    OPENROUTER_SLUGS,
    RELEASE_WINDOW_DAYS,
    validate_output_models,
)

DEFAULT_RICH = REPO_ROOT / "data" / "aa_models_v2.json"
DEFAULT_OUTPUT = REPO_ROOT / "public" / "data" / "models.json"
MIN_RICH_MODELS = 250

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


def select_models(records: list, days: int, as_of: date) -> list:
    cutoff = as_of - timedelta(days=days)
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
    ap.add_argument('--as-of', type=date.fromisoformat, default=None,
                    help='UTC selection date (YYYY-MM-DD); defaults to rich dataset date')
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

    generated_at = data.get('generated_at')
    default_as_of = generated_at[:10] if isinstance(generated_at, str) and len(generated_at) >= 10 else None
    as_of = args.as_of or (date.fromisoformat(default_as_of) if default_as_of else date.today())

    # Sticky featured-first ordering by intelligence, with an explicit cutoff.
    kept = select_models(records, args.days, as_of)
    models = [to_site_model(r) for r in kept]
    models.sort(key=lambda m: (not m['featured'],
                               -(m['composite']['intelligence_index_v4_1'] or 0)))

    validate_output_models(models, args.output)

    out = {
        "version": data.get('version', '4.1'),
        "intelligence_index_version": "4.1",
        "scraped_at": generated_at or f"{as_of.isoformat()}T00:00:00Z",
        "as_of": as_of.isoformat(),
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