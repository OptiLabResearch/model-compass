"""Shared invariants for the public Model Compass data contract.

The rich pipeline and the retired Free-API pipeline both emit the same public
site schema. Keeping the curation, URL, slug, and output validation rules here
prevents the two paths from drifting while the legacy path is still retained
for compatibility and tests.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path


FEATURED_SLUGS = {
    "claude-fable-5", "claude-opus-4-8", "claude-sonnet-5",
    "gpt-5-6-sol", "gpt-5-6-terra", "gpt-5-6-luna",
    "kimi-k3", "grok-4-5",
    "glm-5-2", "muse-spark-1-1",
    "gemini-3-6-flash", "gemini-3-1-pro-preview",
    "qwen3-7-max",
    "minimax-m3", "qwen3-7-plus",
    "mimo-v2-5-pro", "mimo-v2-5-0424",
    "deepseek-v4-pro", "deepseek-v4-flash",
}

OPENROUTER_SLUGS = {
    "deepseek-v4-pro": "deepseek/deepseek-v4-pro",
    "minimax-m3": "minimax/minimax-m3",
    "kimi-k3": "moonshotai/kimi-k3",
    "mimo-v2-5-pro": "xiaomi/mimo-v2.5-pro",
    "mimo-v2-5-0424": "xiaomi/mimo-v2.5",
    "glm-5-2": "z-ai/glm-5.2",
    "qwen3-7-max": "qwen/qwen3.7-max",
    "qwen3-7-plus": "qwen/qwen3.7-plus",
    "muse-spark-1-1": "meta-llama/muse-spark-1.1",
    "grok-4-5": "x-ai/grok-4.5",
}

RELEASE_WINDOW_DAYS = 183
MAX_PUBLIC_MODELS = 8000
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,199}$")


def _check_finite_numbers(value, path: str = "root") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise RuntimeError(f"Output contains non-finite number at {path}")
    if isinstance(value, dict):
        for key, child in value.items():
            _check_finite_numbers(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _check_finite_numbers(child, f"{path}[{index}]")


def validate_output_models(
    models: list,
    previous_path: Path,
    *,
    max_models: int = MAX_PUBLIC_MODELS,
) -> None:
    """Enforce invariants that protect the published dataset and browser UI."""
    if not len(FEATURED_SLUGS) <= len(models) <= max_models:
        raise RuntimeError(f"Output model count {len(models)} is implausible")

    seen = set()
    for model in models:
        if not isinstance(model, dict):
            raise RuntimeError("Output contains a non-object model")
        slug = model.get("slug")
        if not isinstance(slug, str) or not SLUG_RE.fullmatch(slug):
            raise RuntimeError(f"Output contains an invalid slug: {slug}")
        if slug in seen:
            raise RuntimeError(f"Output contains duplicate slug: {slug}")
        seen.add(slug)
        if model.get("aa_url") != f"https://artificialanalysis.ai/models/{slug}":
            raise RuntimeError(f"Output contains unexpected AA URL for {slug}")
        name = model.get("name")
        creator = model.get("creator")
        if not isinstance(name, str) or not name or len(name) > 500:
            raise RuntimeError(f"Output contains invalid name for {slug}")
        if creator is not None and (not isinstance(creator, str) or len(creator) > 200):
            raise RuntimeError(f"Output contains invalid creator for {slug}")
        _check_finite_numbers(model, f"models.{slug}")

        for value in (model.get("benchmarks") or {}).values():
            if value is not None and (
                not isinstance(value, (int, float)) or not 0 <= value <= 100
            ):
                raise RuntimeError(f"Output contains out-of-range benchmark for {slug}")
        for value in (model.get("pricing_per_m_tokens") or {}).values():
            if value is not None and (
                not isinstance(value, (int, float)) or not 0 <= value <= 1_000_000
            ):
                raise RuntimeError(f"Output contains invalid pricing for {slug}")

    missing_featured = FEATURED_SLUGS - seen
    if missing_featured:
        raise RuntimeError(
            "Output is missing featured slugs: " + ", ".join(sorted(missing_featured))
        )

    if previous_path.exists():
        try:
            previous = json.loads(previous_path.read_text(encoding="utf-8"))
            previous_count = len(previous.get("models") or [])
        except (OSError, json.JSONDecodeError, TypeError):
            previous_count = 0
        if previous_count and len(models) < math.floor(previous_count * 0.6):
            raise RuntimeError(
                f"Output model count dropped from {previous_count} to {len(models)}; "
                "refusing an automatic destructive refresh"
            )
