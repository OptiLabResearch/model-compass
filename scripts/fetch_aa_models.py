#!/usr/bin/env python3
"""
fetch_aa_models.py — Build public/data/models.json from Artificial Analysis.

Two sources, merged:

  1. The official AA API (requires AA_API_KEY). Authoritative and supported.
     Covers every tracked model (~574) but only 17 evaluations — notably it does
     NOT expose AA-Omniscience, the agentic index, GDPval, CritPt, MMMU-Pro or
     the context window.

  2. The /models page's server-rendered payload. Best-effort. Carries the full
     metric set, but only for the ~28 models AA renders by default. This is the
     only public source for omniscience / non-hallucination.

The API is the base; the page enriches it where it can. If the page scrape
breaks (AA has been actively restructuring it), the site still builds from the
API alone, and this script says so loudly.

Usage:
    AA_API_KEY=... python3 scripts/fetch_aa_models.py
    python3 scripts/fetch_aa_models.py --no-enrich     # API only
    python3 scripts/fetch_aa_models.py --output x.json

Exits non-zero if AA_API_KEY is unset, if the API call fails, or if a
FEATURED_SLUGS entry has no match upstream (a silent rename would otherwise
empty the dataset with no error at all).
"""

import os
import re
import sys
import json
import math
import argparse
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

API_URL = "https://artificialanalysis.ai/api/v2/data/llms/models"
PAGE_URL = "https://artificialanalysis.ai/models"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = REPO_ROOT / "public" / "data" / "models.json"

# Last-known-good store for the metrics only the page can provide. AA renders
# ~28 models richly; everything else it has ever rendered is remembered here, so
# a model dropping off AA's front page doesn't silently strip the non-hallucination
# metrics.
#
# Safe because these are properties of a *released* model: a frozen checkpoint's
# GPQA score doesn't drift. It is not free, though — AA does re-run evals and
# revise numbers, so every cached value carries the date it was observed, and
# fresh page data always wins over the cache.
ENRICHMENT_CACHE = REPO_ROOT / "data" / "enrichment_cache.json"

# The fields the API cannot provide, and which the cache therefore preserves.
CACHED_PATHS = [
    ("composite", "agentic_index"),
    ("composite", "omniscience_index"),
    ("benchmarks", "gdpval_v2"),
    ("benchmarks", "critpt"),
    ("benchmarks", "mmmu_pro"),
    ("benchmarks", "apex_agents_aa"),
    ("benchmarks", "it_bench_sre"),
    ("benchmarks", "omniscience_accuracy"),
    ("benchmarks", "omniscience_hallucination_rate"),
    ("benchmarks", "omniscience_non_halluc"),
]
CACHED_TOP_LEVEL = [
    "context_tokens", "knowledge_cutoff", "is_reasoning", "is_open_weights",
    "license", "license_url", "commercial_allowed", "size_class",
    "parameters_billions", "active_params_billions",
    "input_modalities", "output_modalities",
]

# Featured models (a curated subset of whatever AA is currently tracking).
# Everything else still appears on the All Models page. Add/remove slugs here
# to change the curated set.
#
# Featured models are exempt from the RELEASE_WINDOW_DAYS cutoff: curation, not
# age, decides exemption. A featured slug that vanishes upstream is a hard
# error, not a silent drop — see check_featured_slugs().
# Curated 2026-07-21 from AA intel/coding/non-hallucination + value.
# Swaps: gpt-5-5→gpt-5-6-{sol,terra,luna}, sonnet-4-6→sonnet-5, k2→k3,
# grok-4-3→4-5, gemini-3-5-flash→3-6-flash; add muse-spark-1-1; drop
# gpt-5-5-pro (no scores) and deepseek-v4-flash (nh≈4%, gates always fail).
FEATURED_SLUGS = {
    # Frontier
    'claude-fable-5', 'claude-opus-4-8', 'claude-sonnet-5',
    'gpt-5-6-sol', 'gpt-5-6-terra', 'gpt-5-6-luna',
    'kimi-k3', 'grok-4-5',
    # Strong mid / reliability
    'glm-5-2', 'muse-spark-1-1',
    'gemini-3-6-flash', 'gemini-3-1-pro-preview',
    'qwen3-7-max',
    # Budget / specialized
    'minimax-m3', 'qwen3-7-plus',
    'mimo-v2-5-pro', 'mimo-v2-5-0424',
    'deepseek-v4-pro', 'deepseek-v4-flash',
}

# OpenRouter routing slug for models that are available through it (i.e. not
# a proprietary API you'd call directly). Used only to power the "available
# via OpenRouter" filter in the UI — optional, purely informational.
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

NOTES = {
    'mimo-v2-5-0424': 'Non-reasoning budget pick',
    'gpt-5-6-luna': 'OpenAI value tier (cheapest of the 5.6 line)',
    'deepseek-v4-pro': 'Cheap coding; fails unattended/high-stakes nh gates',
    'minimax-m3': 'Best non-hallucination per dollar on the shortlist',
}

RELEASE_WINDOW_DAYS = 183  # ~6 months


# ---------------------------------------------------------------------------
# Source 1 — the official API
# ---------------------------------------------------------------------------

MAX_RESPONSE_BYTES = 25 * 1024 * 1024  # 25 MB hard cap on upstream bodies
MIN_API_MODELS = 100
MAX_API_MODELS = 5000
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,199}$")


class _NoRedirectHandler(HTTPRedirectHandler):
    """Fail closed instead of forwarding credentials across redirects."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open_no_redirect(req: Request, timeout: int = 90):
    return build_opener(_NoRedirectHandler).open(req, timeout=timeout)


def _read_limited(resp, limit: int = MAX_RESPONSE_BYTES) -> bytes:
    chunks = []
    total = 0
    while True:
        chunk = resp.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise RuntimeError(f"Upstream response exceeded {limit} bytes")
        chunks.append(chunk)
    return b''.join(chunks)


def _atomic_write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', encoding='utf-8', dir=path.parent,
            prefix=f'.{path.name}.', suffix='.tmp', delete=False,
        ) as f:
            tmp_name = f.name
            json.dump(obj, f, indent=2, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    finally:
        if tmp_name and os.path.exists(tmp_name):
            os.unlink(tmp_name)


def fetch_api_models(api_key: str) -> list:
    req = Request(API_URL, headers={'x-api-key': api_key, 'User-Agent': USER_AGENT})
    try:
        with _open_no_redirect(req, timeout=90) as r:
            payload = json.loads(_read_limited(r).decode('utf-8'))
    except HTTPError as e:
        raise RuntimeError(f"AA API returned HTTP {e.code}") from e
    except URLError as e:
        raise RuntimeError(f"AA API unreachable: {e.reason}") from e

    models = payload.get('data')
    if not models:
        raise RuntimeError(f"AA API returned no models (status={payload.get('status')})")
    return models


def validate_api_models(models: list) -> None:
    """Reject malformed or implausible upstream payloads before normalization."""
    if not isinstance(models, list):
        raise RuntimeError("AA API data is not a list")
    if not MIN_API_MODELS <= len(models) <= MAX_API_MODELS:
        raise RuntimeError(
            f"AA API model count {len(models)} is outside the safe range "
            f"{MIN_API_MODELS}..{MAX_API_MODELS}"
        )

    seen = set()
    for index, model in enumerate(models):
        if not isinstance(model, dict):
            raise RuntimeError(f"AA API model {index} is not an object")
        slug = model.get('slug')
        if not isinstance(slug, str) or not SLUG_RE.fullmatch(slug):
            raise RuntimeError(f"AA API model {index} has an invalid slug")
        if slug in seen:
            raise RuntimeError(f"AA API returned duplicate slug: {slug}")
        seen.add(slug)

        name = model.get('name')
        if name is not None and (not isinstance(name, str) or len(name) > 500):
            raise RuntimeError(f"AA API model {slug} has an invalid name")
        for key in ('evaluations', 'pricing'):
            value = model.get(key)
            if value is not None and not isinstance(value, dict):
                raise RuntimeError(f"AA API model {slug} has invalid {key}")
        creator = model.get('model_creator')
        if creator is not None and not isinstance(creator, dict):
            raise RuntimeError(f"AA API model {slug} has an invalid creator")
        release_date = model.get('release_date')
        if release_date:
            try:
                datetime.fromisoformat(release_date).date()
            except (TypeError, ValueError) as exc:
                raise RuntimeError(
                    f"AA API model {slug} has invalid release_date"
                ) from exc


def _check_finite_numbers(value, path: str = 'root') -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise RuntimeError(f"Non-finite number at {path}")
    if isinstance(value, dict):
        for key, child in value.items():
            _check_finite_numbers(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _check_finite_numbers(child, f"{path}[{index}]")


def validate_output_models(models: list, previous_path: Path) -> None:
    """Enforce invariants that protect the published dataset and browser UI."""
    if not len(FEATURED_SLUGS) <= len(models) <= MAX_API_MODELS:
        raise RuntimeError(f"Output model count {len(models)} is implausible")

    seen = set()
    for model in models:
        slug = model.get('slug')
        if not isinstance(slug, str) or not SLUG_RE.fullmatch(slug):
            raise RuntimeError("Output contains an invalid slug")
        if slug in seen:
            raise RuntimeError(f"Output contains duplicate slug: {slug}")
        seen.add(slug)
        if model.get('aa_url') != f"https://artificialanalysis.ai/models/{slug}":
            raise RuntimeError(f"Output contains unexpected AA URL for {slug}")
        name = model.get('name')
        creator = model.get('creator')
        if not isinstance(name, str) or not name or len(name) > 500:
            raise RuntimeError(f"Output contains invalid name for {slug}")
        if creator is not None and (not isinstance(creator, str) or len(creator) > 200):
            raise RuntimeError(f"Output contains invalid creator for {slug}")
        _check_finite_numbers(model, f"models.{slug}")

        for value in (model.get('benchmarks') or {}).values():
            if value is not None and (not isinstance(value, (int, float)) or not 0 <= value <= 100):
                raise RuntimeError(f"Output contains out-of-range benchmark for {slug}")
        for value in (model.get('pricing_per_m_tokens') or {}).values():
            if value is not None and (not isinstance(value, (int, float)) or not 0 <= value <= 1_000_000):
                raise RuntimeError(f"Output contains invalid pricing for {slug}")

    missing_featured = FEATURED_SLUGS - seen
    if missing_featured:
        raise RuntimeError(
            "Output is missing featured slugs: " + ", ".join(sorted(missing_featured))
        )

    if previous_path.exists():
        try:
            previous = json.loads(previous_path.read_text(encoding='utf-8'))
            previous_count = len(previous.get('models') or [])
        except (OSError, json.JSONDecodeError, TypeError):
            previous_count = 0
        if previous_count and len(models) < math.floor(previous_count * 0.6):
            raise RuntimeError(
                f"Output model count dropped from {previous_count} to {len(models)}; "
                "refusing an automatic destructive refresh"
            )


# ---------------------------------------------------------------------------
# Source 2 — the page payload (best effort)
# ---------------------------------------------------------------------------

def _matching_bracket(s: str, start: int) -> int:
    """Index of the ']' matching the '[' at `start`, ignoring brackets in strings."""
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(s)):
        c = s[i]
        if escape:
            escape = False
        elif c == '\\':
            escape = True
        elif c == '"':
            in_string = not in_string
        elif not in_string:
            if c == '[':
                depth += 1
            elif c == ']':
                depth -= 1
                if depth == 0:
                    return i
    return -1


def _rsc_blob(html: str) -> str:
    """Reassemble the Next.js RSC payload from its self.__next_f.push() chunks."""
    pushes = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', html, re.S)
    joined = ''.join(pushes)
    # The payload is a JS string literal: \\" -> \" and \" -> ", \n -> newline.
    return joined.encode('utf-8', 'replace').decode('unicode_escape', errors='replace')


def _grab_array(blob: str, key: str):
    marker = f'"{key}":['
    i = blob.find(marker)
    if i < 0:
        return None
    start = blob.index('[', i)
    end = _matching_bracket(blob, start)
    if end < 0:
        return None
    try:
        return json.loads(blob[start:end + 1])
    except json.JSONDecodeError:
        return None


def fetch_page_enrichment() -> dict:
    """Return {slug: rich_model_dict} scraped from the /models page payload.

    Best effort by design: AA is actively restructuring this page (the full
    dataset is now shipped encrypted), so any failure here is a warning, not a
    build break. Returns {} if the page can't be parsed.
    """
    req = Request(PAGE_URL, headers={'User-Agent': USER_AGENT})
    try:
        with _open_no_redirect(req, timeout=90) as r:
            html = _read_limited(r).decode('utf-8', errors='replace')
    except (HTTPError, URLError, RuntimeError) as e:
        print(f"  WARNING: could not fetch {PAGE_URL}: {e}", file=sys.stderr)
        return {}

    blob = _rsc_blob(html)
    rich = _grab_array(blob, 'initialModels')
    if not rich:
        print("  WARNING: 'initialModels' not found in the page payload — AA has "
              "changed the page again. Falling back to API-only data.",
              file=sys.stderr)
        return {}
    return {m['slug']: m for m in rich if m.get('slug')}


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def pct(v, digits=1):
    """0–1 fraction -> 0–100 percentage."""
    if isinstance(v, (int, float)):
        return round(v * 100, digits)
    return None


def num(v, digits=2):
    if isinstance(v, (int, float)):
        return round(v, digits)
    return None


def perf(v, digits=2):
    """Like num(), but treats a non-positive value as 'not measured'.

    The AA API reports 0 — not null — for models it has never benchmarked for
    speed (50 of them at time of writing, including gpt-5-5-pro). A 0s time to
    first token is not instant, it is missing.
    """
    if isinstance(v, (int, float)) and v > 0:
        return round(v, digits)
    return None


def _first(*vals):
    """First non-None value."""
    for v in vals:
        if v is not None:
            return v
    return None


def shorten_model_name(name: str | None) -> str | None:
    if not name:
        return name

    def _repl(match: re.Match) -> str:
        txt = match.group(0)
        if re.search(r'max', txt, re.I):
            return '(Max)'
        if re.search(r'xhigh', txt, re.I):
            return '(Xhigh)'
        if re.search(r'high', txt, re.I):
            return '(High)'
        if re.search(r'medium', txt, re.I):
            return '(Medium)'
        if re.search(r'low', txt, re.I):
            return '(Low)'
        return txt

    n = re.sub(
        r'\((?:Adaptive\s+)?Reasoning,\s*(?:Max|High|Medium|Low|Xhigh)\s*Effort(?:,\s*Opus\s*[\d.]+\s*Fallback)?\)',
        _repl,
        name,
        flags=re.I,
    )
    n = re.sub(r'\(Non-reasoning,\s*(High|Low|Medium|Max)\s*Effort\)', r'(\1)', n, flags=re.I)
    return n.strip()


def build_model_entry(api_m: dict, rich: dict | None) -> dict:
    """Merge an API model with its (optional) page-scraped rich counterpart."""
    rich = rich or {}
    slug = api_m.get('slug', '')
    ev = api_m.get('evaluations') or {}
    pricing = api_m.get('pricing') or {}

    creator = (api_m.get('model_creator') or {}).get('name') \
        or (rich.get('creator') or {}).get('name')

    ob = rich.get('omniscienceBreakdown') or {}
    halluc = ob.get('hallucinationRate')

    cpt = rich.get('intelligenceIndexCostPerTask') or {}
    cpt_cost = cpt.get('cost') or {}
    otpt = rich.get('intelligenceIndexOutputTokensPerTask') or {}
    e2e = rich.get('endToEndResponseTime') or {}
    ts = rich.get('timescaleData') or {}
    ttfa = rich.get('timeToFirstAnswerToken') or {}

    eval_costs = {
        e.get('slug'): num(e.get('weightedCostPerTask'), 4)
        for e in (cpt.get('evaluations') or [])
    }

    raw_name = _first(rich.get('name'), api_m.get('name'))
    raw_short = _first(rich.get('shortName'), api_m.get('name'))
    clean_name = shorten_model_name(raw_name)
    clean_short = shorten_model_name(raw_short)

    entry = {
        "name": clean_name,
        "short_name": clean_short,
        "slug": slug,
        "aa_url": f"https://artificialanalysis.ai/models/{slug}" if slug else None,
        "openrouter_slug": OPENROUTER_SLUGS.get(slug),
        "creator": creator,
        "released": api_m.get('release_date') or rich.get('releaseDate'),
        "knowledge_cutoff": rich.get('knowledgeCutoffDate'),
        "is_reasoning": bool(rich.get('isReasoning', False)),
        "deprecated": bool(rich.get('deprecated', False)),
        "context_tokens": rich.get('contextWindowTokens'),
        "is_open_weights": bool(rich.get('isOpenWeights', False)),
        "license": rich.get('licenseName'),
        "license_url": rich.get('licenseUrl'),
        "commercial_allowed": rich.get('commercialAllowed'),
        "size_class": rich.get('sizeClass'),
        "parameters_billions": rich.get('parameters'),
        "active_params_billions": rich.get('inferenceParametersActiveBillions'),
        "input_modalities": {
            "text": rich.get('inputModalityText'),
            "image": rich.get('inputModalityImage'),
            "audio": rich.get('inputModalitySpeech'),
            "video": rich.get('inputModalityVideo'),
        },
        "output_modalities": {
            "text": rich.get('outputModalityText'),
            "image": rich.get('outputModalityImage'),
            "audio": rich.get('outputModalitySpeech'),
            "video": rich.get('outputModalityVideo'),
        },
        "featured": slug in FEATURED_SLUGS,
        "note": NOTES.get(slug),
        "has_rich_data": bool(rich),

        "composite": {
            # Both sources are AA Intelligence Index v4.1 on the same scale; the
            # API rounds to 1dp, the page carries full precision, so prefer the page.
            "intelligence_index_v4_1": _first(
                num(rich.get('intelligenceIndex')),
                num(ev.get('artificial_analysis_intelligence_index')),
            ),
            "coding_index": _first(
                num(rich.get('codingIndex')),
                num(ev.get('artificial_analysis_coding_index')),
            ),
            "math_index": num(ev.get('artificial_analysis_math_index')),
            # Page-only.
            "agentic_index": num(rich.get('agenticIndex')),
            "omniscience_index": num(rich.get('omniscience'), digits=1),
        },

        "benchmarks": {
            # Available from the API for most models.
            "gpqa_diamond": _first(pct(rich.get('gpqa')), pct(ev.get('gpqa'))),
            "hle": _first(pct(rich.get('hle')), pct(ev.get('hle'))),
            "scicode": _first(pct(rich.get('scicode')), pct(ev.get('scicode'))),
            "ifbench": _first(pct(rich.get('ifbench')), pct(ev.get('ifbench'))),
            "lcr": _first(pct(rich.get('lcr')), pct(ev.get('lcr'))),
            "tau2_bench": _first(pct(rich.get('tau2')), pct(ev.get('tau2'))),
            "tau3_banking": _first(pct(rich.get('tauBanking')), pct(ev.get('tau_banking'))),
            "terminalbench_hard": _first(
                pct(rich.get('terminalbenchHard')), pct(ev.get('terminalbench_hard'))),
            "terminalbench_v2_1": _first(
                pct(rich.get('terminalbenchV21')), pct(ev.get('terminalbench_v2_1'))),
            "mmlu_pro": pct(ev.get('mmlu_pro')),
            "livecodebench": _first(pct(rich.get('livecodebench')), pct(ev.get('livecodebench'))),
            "math_500": pct(ev.get('math_500')),
            "aime": pct(ev.get('aime')),
            "aime25": _first(pct(rich.get('aime25')), pct(ev.get('aime_25'))),

            # Page-only — the API does not expose these at all.
            "gdpval_v2": pct(rich.get('gdpvalNormalized')),
            "critpt": pct(rich.get('critpt')),
            "mmmu_pro": pct(rich.get('mmmuPro')),
            "apex_agents_aa": pct(rich.get('apexAgents')),
            "it_bench_sre": pct(rich.get('itBenchSre')),
            "omniscience_accuracy": pct(ob.get('accuracy')),
            "omniscience_hallucination_rate": pct(halluc),
            # AA reports the hallucination rate; models store non_halluc as its complement.
            "omniscience_non_halluc": (
                round(100 - halluc * 100, 1) if isinstance(halluc, (int, float)) else None
            ),
        },

        "pricing_per_m_tokens": {
            "input": _first(num(rich.get('price1mInputTokens')),
                            num(pricing.get('price_1m_input_tokens'))),
            "output": _first(num(rich.get('price1mOutputTokens')),
                             num(pricing.get('price_1m_output_tokens'))),
            "blended_3_1": _first(num(rich.get('price1mBlended0To3To1')),
                                  num(pricing.get('price_1m_blended_3_to_1'))),
            "blended_7_2_1": num(rich.get('price1mBlended7To2To1')),
            "blended_1_1": num(rich.get('price1mBlended0To1To1')),
            "cache_hit": num(rich.get('cacheHitPrice')),
            "cache_write": num(rich.get('cacheWritePrice')),
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
        "time_per_task_seconds": num(rich.get('intelligenceIndexTimePerTask'), 1),
        "output_tokens_per_task": {
            "total": num(otpt.get('output')),
            "answer": num(otpt.get('answer')),
            "reasoning": num(otpt.get('reasoning')),
        },

        "performance": {
            # The API reports these for every model; the page only for its 28.
            # perf() maps AA's 0-means-unmeasured sentinel to null.
            "output_speed_tps": _first(
                perf(ts.get('medianOutputSpeed')),
                perf(api_m.get('median_output_tokens_per_second')),
            ),
            "ttft_seconds_total": _first(
                perf(ts.get('medianTimeToFirstChunk')),
                perf(api_m.get('median_time_to_first_token_seconds')),
            ),
            "ttft_seconds_answer": _first(
                perf(ttfa.get('total')),
                perf(api_m.get('median_time_to_first_answer_token')),
            ),
            "end_to_end_500tok": {
                "total": num(e2e.get('total')),
                "input": num(e2e.get('input')),
                "reasoning": num(e2e.get('reasoning')),
                "answer": num(e2e.get('answer')),
            },
        },
        "output_speed_by_prompt_length": [
            {
                "prompt_length_type": k,
                "median_output_speed_tps": num(v.get('medianOutputSpeed')),
                "median_ttft_seconds": num(v.get('medianTimeToFirstChunk')),
                "median_ttft_answer_seconds": num(v.get('medianTimeToFirstAnswerToken')),
            }
            for k, v in (rich.get('performanceByPromptType') or {}).items()
            if isinstance(v, dict)
        ],
    }

    entry['derived'] = build_derived(entry)
    return entry


def build_derived(entry: dict) -> dict:
    """Metrics precomputed for table display efficiency."""
    intel = entry['composite']['intelligence_index_v4_1']
    # Prefer the 3:1 blend (matches table column / real-world mix); fall back to 7:2:1.
    blend = entry['pricing_per_m_tokens']['blended_3_1'] \
        or entry['pricing_per_m_tokens']['blended_7_2_1']
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
        derived['speed_tier'] = 2 if speed >= 100 else 1 if speed >= 50 else 0
    if ttft_a is not None:
        derived['latency_ttft_seconds'] = ttft_a
        derived['latency_tier'] = 2 if ttft_a <= 5 else 1 if ttft_a <= 20 else 0
    return derived


# ---------------------------------------------------------------------------

def load_cache() -> dict:
    if not ENRICHMENT_CACHE.exists():
        return {}
    try:
        return json.loads(ENRICHMENT_CACHE.read_text()).get('models', {})
    except (json.JSONDecodeError, OSError) as e:
        print(f"  WARNING: could not read {ENRICHMENT_CACHE.name} ({e}); starting fresh",
              file=sys.stderr)
        return {}


def _extract_rich(entry: dict) -> dict:
    """Pull the page-only fields out of a built entry, for storing in the cache."""
    snap = {}
    for section, key in CACHED_PATHS:
        v = entry[section].get(key)
        if v is not None:
            snap.setdefault(section, {})[key] = v
    for key in CACHED_TOP_LEVEL:
        v = entry.get(key)
        if v is not None:
            snap[key] = v
    return snap


def apply_cache(entry: dict, cache: dict) -> bool:
    """Backfill page-only fields from the cache. Returns True if anything was filled.

    Fresh data always wins: a field is only filled when it is currently None.
    """
    cached = cache.get(entry['slug'])
    if not cached:
        return False

    filled = False
    for section, key in CACHED_PATHS:
        if entry[section].get(key) is None:
            v = (cached.get(section) or {}).get(key)
            if v is not None:
                entry[section][key] = v
                filled = True
    for key in CACHED_TOP_LEVEL:
        if entry.get(key) in (None, False, {}) and cached.get(key) is not None:
            # Don't let a cached False overwrite a fresh False — only fill real gaps.
            if entry.get(key) is None or (key in ('is_reasoning', 'is_open_weights')
                                          and not entry.get(key)):
                entry[key] = cached[key]
                filled = True

    if filled:
        entry['rich_as_of'] = cached.get('_as_of')
        entry['derived'] = build_derived(entry)
    return filled


def save_cache(cache: dict, entries: list, today: str) -> None:
    """Fold today's fresh page data into the cache and write it back."""
    for e in entries:
        if not e.get('has_rich_data'):
            continue
        snap = _extract_rich(e)
        if not snap:
            continue
        snap['_as_of'] = today
        snap['_name'] = e.get('name')
        cache[e['slug']] = snap

    _atomic_write_json(ENRICHMENT_CACHE, {
        "description": (
            "Last-known-good values for metrics the AA API does not expose "
            "(omniscience/non-hallucination, agentic index, GDPval, CritPt, "
            "MMMU-Pro, context window). Written by scripts/fetch_aa_models.py. "
            "Each entry records the date it was observed; fresh page data "
            "always overrides these."
        ),
        "updated_at": today,
        "models": dict(sorted(cache.items())),
    })


def check_featured_slugs(api_models: list) -> list:
    """FEATURED_SLUGS entries with no match upstream. Non-empty means fail the build."""
    present = {m.get('slug') for m in api_models}
    return sorted(FEATURED_SLUGS - present)


def select_models(api_models: list, days: int) -> list:
    """Featured models always; everything else only if released within `days`."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date()
    kept = []
    for m in api_models:
        if m.get('slug') in FEATURED_SLUGS:
            kept.append(m)
            continue
        rd = m.get('release_date')
        if not rd:
            continue
        try:
            if datetime.fromisoformat(rd).date() >= cutoff:
                kept.append(m)
        except ValueError:
            continue
    return kept


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--days", type=int, default=RELEASE_WINDOW_DAYS,
                        help="Keep non-featured models released within this many days")
    parser.add_argument("--no-enrich", action="store_true",
                        help="Skip the page scrape; build from the API alone")
    args = parser.parse_args()

    api_key = os.environ.get('AA_API_KEY')
    if not api_key:
        print("ERROR: AA_API_KEY is not set. Get a key at "
              "https://artificialanalysis.ai/ and export it, or add it to the "
              "repo's GitHub Actions secrets.", file=sys.stderr)
        return 1

    print(f"Fetching {API_URL} ...")
    try:
        api_models = fetch_api_models(api_key)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    validate_api_models(api_models)
    print(f"  {len(api_models)} models from the API (validated)")

    missing = check_featured_slugs(api_models)
    if missing:
        print(
            "\nERROR: featured slugs missing from the AA API:\n"
            + "\n".join(f"  - {s}" for s in missing)
            + "\n\nAA has most likely renamed or retired them. Update FEATURED_SLUGS "
              "(and OPENROUTER_SLUGS / NOTES) in this script. Refusing to write a "
              "models.json that would silently drop them.",
            file=sys.stderr,
        )
        return 1

    enrichment = {}
    if not args.no_enrich:
        print(f"Enriching from {PAGE_URL} ...")
        enrichment = fetch_page_enrichment()
        print(f"  {len(enrichment)} models carry full metrics "
              f"(omniscience, agentic index, GDPval, CritPt, MMMU-Pro, context window)")

    kept = select_models(api_models, args.days)
    models = [build_model_entry(m, enrichment.get(m.get('slug'))) for m in kept]

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cache = load_cache()
    n_from_cache = sum(1 for m in models if not m['has_rich_data'] and apply_cache(m, cache))
    validate_output_models(models, args.output)
    save_cache(cache, models, today)
    if cache:
        print(f"  {n_from_cache} models backfilled from the enrichment cache "
              f"({len(cache)} slugs remembered)")

    n_featured = sum(1 for m in models if m['featured'])
    n_rich = sum(1 for m in models
                 if m['benchmarks'].get('omniscience_non_halluc') is not None)
    featured_no_rich = sorted(
        m['slug'] for m in models
        if m['featured'] and m['benchmarks'].get('omniscience_non_halluc') is None)
    print(f"  {len(models)} models kept ({n_featured} featured, rest released "
          f"in the last {args.days} days); {n_rich} with non-hallucination data")

    if featured_no_rich:
        print("\n  NOTE: these featured models have no omniscience/non-hallucination "
              "data:\n" + "\n".join(f"    - {s}" for s in featured_no_rich))

    out = {
        "version": "4.1",
        "scraped_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_url": PAGE_URL,
        "scrape_method": (
            "AA official API (all models, 17 evaluations) + /models page payload "
            "(full metric set, top models only)"
        ),
        "intelligence_index_methodology": (
            "AA Intelligence Index v4.1 = composite of 9 evaluations: "
            "GDPval-AA v2, τ³-Banking, Terminal-Bench v2.1, SciCode, HLE, "
            "GPQA Diamond, CritPt, AA-Omniscience, AA-LCR"
        ),
        "models": models,
        "coverage": {
            "total": len(models),
            "featured": n_featured,
            "with_rich_metrics": n_rich,
            "featured_without_rich_metrics": featured_no_rich,
        },
    }

    _atomic_write_json(args.output, out)
    print(f"  Saved {args.output} ({args.output.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
