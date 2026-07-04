#!/usr/bin/env python3
"""
scrape_aa_models.py — Scrape Artificial Analysis model data into a JSON source-of-truth.

Fetches the AA comparison URL and extracts the full model data embedded in the
Next.js RSC payload. No API key or browser required.

Usage:
    python3 scrape_aa_models.py                 # scrape all models released in the last 6 months
    python3 scrape_aa_models.py --output other.json

Writes data/models.json (relative to the repo root) by default. All three
pages (index.html, shortlist.html, models.html) fetch this single file.
"""

import re
import json
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

SOURCE_URL = "https://artificialanalysis.ai/models"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = REPO_ROOT / "data" / "models.json"

# Models highlighted on the Picker and Shortlist pages (a curated subset of
# whatever AA is currently tracking). Everything else still appears on the
# All Models page. Add/remove slugs here to change the curated set.
FEATURED_SLUGS = {
    'gpt-5-5', 'gpt-5-5-pro', 'gemini-3-1-pro-preview', 'gemini-3-5-flash',
    'claude-sonnet-4-6-adaptive', 'claude-opus-4-8', 'claude-fable-5',
    'deepseek-v4-pro', 'deepseek-v4-flash', 'grok-4-3', 'minimax-m3',
    'kimi-k2-6', 'kimi-k2-7-code', 'mimo-v2-5-pro', 'mimo-v2-5-0424',
    'glm-5-2', 'qwen3-7-max', 'qwen3-7-plus',
}

# OpenRouter routing slug for models that are available through it (i.e. not
# a proprietary API you'd call directly). Used only to power the "available
# via OpenRouter" filter in the UI — optional, purely informational.
OPENROUTER_SLUGS = {
    'deepseek-v4-pro': 'deepseek/deepseek-v4-pro',
    'deepseek-v4-flash': 'deepseek/deepseek-v4-flash',
    'minimax-m3': 'minimax/minimax-m3',
    'kimi-k2-6': 'moonshotai/kimi-k2.6',
    'kimi-k2-7-code': 'moonshotai/kimi-k2.7-code',
    'mimo-v2-5-pro': 'xiaomi/mimo-v2.5-pro',
    'mimo-v2-5-0424': 'xiaomi/mimo-v2-5',
    'glm-5-2': 'z-ai/glm-5.2',
    'qwen3-7-max': 'qwen/qwen3.7-max',
    'qwen3-7-plus': 'qwen/qwen3.7-plus',
}

NOTES = {
    'mimo-v2-5-0424': 'Non-reasoning budget pick',
}

RELEASE_WINDOW_DAYS = 183  # ~6 months


def fetch_page(url: str) -> str:
    req = Request(url, headers={'User-Agent': USER_AGENT})
    with urlopen(req, timeout=60) as r:
        return r.read().decode('utf-8', errors='replace')


def find_matching_bracket(s: str, start_pos: int, open_char='[', close_char=']') -> int:
    """Find the matching closing bracket from start_pos (which must point to open_char)."""
    depth = 0
    i = start_pos
    in_string = False
    escape = False
    while i < len(s):
        c = s[i]
        if escape:
            escape = False
            i += 1
            continue
        if c == '\\':
            escape = True
            i += 1
            continue
        if c == '"':
            in_string = not in_string
        if not in_string:
            if c == open_char:
                depth += 1
            elif c == close_char:
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return -1


def find_models_array_bounds(html: str):
    """Find the start and end of the escaped JSON model array in the RSC payload."""
    positions = [m.start() for m in re.finditer(r'\\"show_host_model_evals\\"', html)]
    if not positions:
        raise RuntimeError("No model data found in page (show_host_model_evals marker missing)")

    first_pos = positions[0]
    arr_start = html.rfind('[{', 0, first_pos + 1)
    if arr_start < 0:
        raise RuntimeError("Could not find array start")

    arr_end_idx = find_matching_bracket(html, arr_start)
    if arr_end_idx < 0:
        raise RuntimeError("Could not find matching closing bracket for model array")

    return arr_start, arr_end_idx + 1


def parse_models_array(html: str) -> list:
    """Extract and parse the escaped JSON model array."""
    arr_start, arr_end = find_models_array_bounds(html)
    chunk = html[arr_start:arr_end]
    unescaped = chunk.replace('\\"', '"')
    return json.loads(unescaped)


def extract_leaderboards(html: str) -> dict:
    """Extract all section leaderboards (top-N entries per metric)."""
    label_array_starts = [m.start() for m in re.finditer(r'\[\{"label":"', html)]
    leaderboards = {}
    for start in label_array_starts:
        end = find_matching_bracket(html, start)
        if end <= 0:
            continue
        chunk = html[start:end + 1]
        try:
            arr = json.loads(chunk.replace('\\"', '"'))
        except json.JSONDecodeError:
            continue
        if not arr or not isinstance(arr, list) or len(arr) < 3:
            continue
        skip_keys = {'label', 'id', 'color', 'logo', 'reasoning', 'detailsUrl',
                     'url', 'pattern', 'displayValue', 'value', 'labelKey'}
        metric_keys = [k for k in arr[0].keys() if k not in skip_keys]
        if not metric_keys:
            continue
        metric = metric_keys[0]
        entries = []
        for item in arr:
            label = item.get('label', '')
            val = item.get(metric)
            url = item.get('detailsUrl', '')
            if isinstance(val, (int, float)):
                entries.append({"label": label, "value": val, "url": url})
            else:
                entries.append({"label": label, "value": None, "url": url})
        leaderboards[metric] = entries
    return leaderboards


def pct(v, digits=1):
    if v is None or v == '$undefined':
        return None
    if isinstance(v, (int, float)):
        return round(v * 100, digits)
    return v


def num(v, digits=2):
    if v is None or v == '$undefined':
        return None
    if isinstance(v, (int, float)):
        return round(v, digits)
    return v


def build_model_entry(m: dict) -> dict:
    """Convert a raw AA model object into our normalized schema."""
    creator_obj = m.get('model_creators', {})
    creator = creator_obj.get('name') if isinstance(creator_obj, dict) else None

    ob = m.get('omniscience_breakdown', {})
    ob_total = ob.get('total', {}) if isinstance(ob, dict) else {}

    cpt = m.get('intelligenceIndexCostPerTask', {})
    cpt_cost = cpt.get('cost', {}) if isinstance(cpt, dict) else {}

    otpt = m.get('intelligenceIndexOutputTokensPerTask', {})

    eval_costs = {}
    if isinstance(cpt, dict):
        for ev in cpt.get('evaluations', []):
            eval_costs[ev.get('slug')] = num(ev.get('weightedCostPerTask'), 4)

    slug = m.get('slug', '')

    entry = {
        "name": m.get('name'),
        "short_name": m.get('short_name'),
        "slug": slug,
        "aa_url": f"https://artificialanalysis.ai/models/{slug}" if slug else None,
        "openrouter_slug": OPENROUTER_SLUGS.get(slug),
        "creator": creator,
        "released": m.get('release_date'),
        "knowledge_cutoff": m.get('knowledge_cutoff_date'),
        "is_reasoning": m.get('reasoning_model', False),
        "is_frontier": m.get('frontier_model', False),
        "context_tokens": m.get('context_window_tokens'),
        "is_open_weights": m.get('is_open_weights', False),
        "license": m.get('license_name'),
        "license_url": m.get('license_url'),
        "commercial_allowed": m.get('commercial_allowed'),
        "size_class": m.get('size_class'),
        "parameters_billions": m.get('parameters'),
        "active_params_billions": m.get('activeParams'),
        "inference_active_params_billions": m.get('inference_parameters_active_billions'),
        "output_tokens_max": m.get('output_tokens'),
        "input_modalities": {
            "text": m.get('input_modality_text'),
            "image": m.get('input_modality_image'),
            "audio": m.get('input_modality_speech'),
            "video": m.get('input_modality_video'),
        },
        "output_modalities": {
            "text": m.get('output_modality_text'),
            "image": m.get('output_modality_image'),
            "audio": m.get('output_modality_speech'),
            "video": m.get('output_modality_video'),
        },
        "featured": slug in FEATURED_SLUGS,
        "note": NOTES.get(slug),
        "composite": {
            "intelligence_index_v4_1": num(m.get('intelligence_index_v4_1') or m.get('intelligence_index')),
            "intelligence_index_estimated": num(m.get('estimated_intelligence_index_v4_1')),
            "coding_index": num(m.get('coding_index')),
            "agentic_index": num(m.get('agentic_index')),
            "math_index": num(m.get('math_index')),
            "omniscience_index": num(m.get('omniscience'), digits=1),
        },
        "benchmarks": {
            "gdpval_v2": pct(m.get('gdpval_normalized')),
            "terminalbench_v2_1": pct(m.get('terminalbench_v2_1')),
            "terminalbench_hard": pct(m.get('terminalbench_hard')),
            "tau3_banking": pct(m.get('tau_banking')),
            "tau2_bench": pct(m.get('tau2')),
            "lcr": pct(m.get('lcr')),
            "omniscience_accuracy": pct(ob_total.get('accuracy')),
            "omniscience_non_halluc": pct(ob_total.get('non_hallucination_rate')),
            "omniscience_hallucination_rate": pct(ob_total.get('hallucination_rate')),
            "hle": pct(m.get('hle')),
            "gpqa_diamond": pct(m.get('gpqa')),
            "scicode": pct(m.get('scicode')),
            "ifbench": pct(m.get('ifbench')),
            "critpt": pct(m.get('critpt')),
            "apex_agents_aa": pct(m.get('apex_agents')),
            "it_bench_sre": pct(m.get('it_bench_sre')),
            "mmmu_pro": pct(m.get('mmmu_pro')),
            "aime25": pct(m.get('aime25')),
            "aime": pct(m.get('aime')),
            "humaneval": pct(m.get('humaneval')),
            "livecodebench": pct(m.get('livecodebench')),
            "mmlu_pro": pct(m.get('mmlu_pro')),
        },
        "pricing_per_m_tokens": {
            "cache_hit": num(m.get('cache_hit_price')),
            "cache_write": num(m.get('cacheWritePrice')),
            "input": num(m.get('price_1m_input_tokens')),
            "output": num(m.get('price_1m_output_tokens')),
            "blended_7_2_1": num(m.get('price_1m_blended_7_2_1')),
            "blended_3_1": num(m.get('price_1m_blended_0_3_1')),
            "blended_1_1": num(m.get('price_1m_blended_0_1_1')),
        },
        "cost_per_intelligence_task_usd": {
            "total": num(cpt_cost.get('total'), 3),
            "input": num(cpt_cost.get('input'), 4),
            "output": num(cpt_cost.get('output'), 4),
            "cache_read": num(cpt_cost.get('cacheRead'), 4),
            "cache_write": num(cpt_cost.get('cacheWrite'), 4),
            "non_cache_input": num(cpt_cost.get('nonCacheInput'), 4),
            "reasoning": num(cpt_cost.get('reasoning'), 4),
            "answer": num(cpt_cost.get('answer'), 4),
        },
        "cost_per_eval_breakdown_usd": eval_costs,
        "time_per_task_seconds": num(m.get('intelligenceIndexTimePerTask'), 1),
        "output_tokens_per_task": {
            "total": num(otpt.get('output')) if isinstance(otpt, dict) else None,
            "answer": num(otpt.get('answer')) if isinstance(otpt, dict) else None,
            "reasoning": num(otpt.get('reasoning')) if isinstance(otpt, dict) else None,
        },
        "performance": {
            "output_speed_tps": num(m.get('timescaleData', {}).get('median_output_speed')),
            "output_speed_p05": num(m.get('timescaleData', {}).get('percentile_05_output_speed')),
            "output_speed_p95": num(m.get('timescaleData', {}).get('percentile_95_output_speed')),
            "ttft_seconds_total": num(m.get('timescaleData', {}).get('median_time_to_first_chunk')),
            "ttft_seconds_thinking": num(m.get('timescaleData', {}).get('median_time_to_first_reasoning_chunk')),
            "ttft_seconds_answer": num(m.get('time_to_first_answer_token_metrics', {}).get('total_time')),
            "end_to_end_500tok": {
                "total": num(m.get('end_to_end_response_time_metrics', {}).get('total_time')),
                "input": num(m.get('end_to_end_response_time_metrics', {}).get('input_time')),
                "reasoning": num(m.get('end_to_end_response_time_metrics', {}).get('reasoning_time')),
                "answer": num(m.get('end_to_end_response_time_metrics', {}).get('answer_time')),
            }
        },
        "output_speed_by_prompt_length": []
    }

    for p in m.get('performanceByPromptLength', []):
        if p.get('prompt_length_type') in ('short', 'medium', 'long'):
            entry['output_speed_by_prompt_length'].append({
                "prompt_length_type": p.get('prompt_length_type'),
                "median_output_speed_tps": num(p.get('median_output_speed')),
                "median_ttft_seconds": num(p.get('median_time_to_first_chunk')),
                "median_ttft_answer_seconds": num(p.get('median_time_to_first_answer_token')),
            })

    # Derived metrics — computed at scrape time so the picker doesn't have to.
    intel = entry['composite']['intelligence_index_v4_1']
    blend = entry['pricing_per_m_tokens']['blended_7_2_1']
    cpt_total = entry['cost_per_intelligence_task_usd']['total']
    nh = entry['benchmarks']['omniscience_non_halluc']
    speed = entry['performance']['output_speed_tps']
    ttft_a = entry['performance']['ttft_seconds_answer']

    derived = {}
    if intel and blend and blend > 0:
        derived['value_intelligence_per_dollar_blend'] = round(intel / blend, 1)
    if intel and cpt_total and cpt_total > 0:
        derived['value_intelligence_per_dollar_task'] = round(intel / cpt_total, 1)
    if intel and nh:
        derived['safety_composite'] = round(intel * 0.4 + nh * 0.6, 1)
    if speed:
        derived['throughput_tps'] = speed
    if ttft_a is not None:
        derived['latency_ttft_seconds'] = ttft_a
    if speed:
        if speed >= 100: derived['speed_tier'] = 2
        elif speed >= 50: derived['speed_tier'] = 1
        else: derived['speed_tier'] = 0
    if ttft_a is not None:
        if ttft_a <= 5: derived['latency_tier'] = 2
        elif ttft_a <= 20: derived['latency_tier'] = 1
        else: derived['latency_tier'] = 0

    entry['derived'] = derived

    return entry


def main():
    parser = argparse.ArgumentParser(description="Scrape AA model data to a single JSON source of truth")
    parser.add_argument("--url", default=SOURCE_URL, help="AA URL to scrape")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output JSON path")
    parser.add_argument("--days", type=int, default=RELEASE_WINDOW_DAYS,
                         help="Only keep models released within this many days")
    args = parser.parse_args()

    print(f"Fetching {args.url}...")
    html = fetch_page(args.url)
    print(f"  Got {len(html)} bytes")

    print("Parsing models array...")
    all_models = parse_models_array(html)
    print(f"  Found {len(all_models)} models in RSC payload")

    print("Extracting leaderboards...")
    leaderboards = extract_leaderboards(html)
    print(f"  Found {len(leaderboards)} leaderboards")

    cutoff = (datetime.now(timezone.utc) - timedelta(days=args.days)).date()
    recent = []
    for m in all_models:
        rd = m.get('release_date')
        if not rd:
            continue
        try:
            d = datetime.fromisoformat(rd).date()
        except ValueError:
            continue
        if d >= cutoff:
            recent.append(m)
    print(f"  {len(recent)} models released in the last {args.days} days")

    print(f"Building JSON ({len(recent)} models)...")
    out = {
        "version": "4.1",
        "scraped_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_url": args.url,
        "scrape_method": "curl + RSC payload extraction (no browser or API key required)",
        "intelligence_index_methodology": (
            "AA Intelligence Index v4.1 = composite of 9 evaluations: "
            "GDPval-AA v2, τ³-Banking, Terminal-Bench v2.1, SciCode, HLE, "
            "GPQA Diamond, CritPt, AA-Omniscience, AA-LCR"
        ),
        "models": [build_model_entry(m) for m in recent],
        "leaderboards": leaderboards,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, 'w') as f:
        json.dump(out, f, indent=2)
    print(f"  Saved {args.output} ({args.output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
