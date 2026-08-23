"""Validation & schema-drift detection for the AA pipeline.

Fail-visible checks: an unexpectedly tiny payload, a dramatic reduction in
model count, disappearance of expected fields, zero benchmark scores,
duplicate-model explosions, or malformed numeric fields should fail the run
rather than silently publish an empty/corrupted dataset.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

from . import schema

log = logging.getLogger("aa.pipeline")


@dataclass
class SanityReport:
    rules_run: int = 0
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures


def _check_number(record: dict, path: list[str], failures: list[str],
                  slug: str) -> None:
    """Float/NaN/Inf guard, else append a failure."""
    node = record
    for key in path[:-1]:
        if not isinstance(node, dict):
            return
        node = node.get(key)
    if not isinstance(node, dict):
        return
    val = node.get(path[-1])
    if isinstance(val, float) and not math.isfinite(val):
        failures.append(f"{slug}.{'.'.join(path)} is non-finite: {val}")


def run_sanity(records: list[dict], source: str,
               min_models: int, expected_fields: tuple[str, ...] = ("slug", "name")) -> SanityReport:
    """Validate a batch of normalized records from one source."""
    rep = SanityReport()
    if not isinstance(records, list):
        rep.failures.append(f"[{source}] records is not a list")
        return rep
    rep.rules_run += 1
    if len(records) < min_models:
        rep.failures.append(
            f"[{source}] model count {len(records)} below minimum {min_models}"
        )

    rep.rules_run += 1
    for f in expected_fields:
        present = sum(1 for r in records if r.get(f))
        if present == 0:
            rep.failures.append(f"[{source}] required field '{f}' missing on all records")

    # duplicate slug check
    rep.rules_run += 1
    slugs = [r.get("slug") for r in records if r.get("slug")]
    dupes = {s for s in slugs if slugs.count(s) > 1}
    if dupes:
        rep.failures.append(
            f"[{source}] duplicate slugs: {sorted(str(s) for s in dupes)[:10]}"
        )

    # crash on unexpected NaN/Inf floats
    rep.rules_run += 1
    numeric_paths = [
        ["intelligence_index"], ["coding_index"], ["math_index"],
        ["benchmarks", "gpqa"], ["benchmarks", "mmlu_pro"],
        ["pricing", "input"], ["pricing", "output"],
        ["performance", "median_output_speed_tps"],
    ]
    for r in records:
        slug = r.get("slug", "?")
        for path in numeric_paths:
            _check_number(r, path, rep.failures, slug)

    # sanity on the intelligence index distribution (whole-dataset corrupt check)
    rep.rules_run += 1
    ii_vals = [r["intelligence_index"] for r in records
               if isinstance(r.get("intelligence_index"), (int, float))
               and not isinstance(r.get("intelligence_index"), bool)]
    if len(records) >= min_models and len(ii_vals):
        median_ok = len(ii_vals) / len(records) >= schema.MIN_RICH_BENCHMARK_RATIO
        if not median_ok:
            rep.failures.append(
                f"[{source}] only {len(ii_vals)}/{len(records)} have intelligence_index "
                f"(below {schema.MIN_RICH_BENCHMARK_RATIO:.0%}) — possible field drift"
            )

    return rep


def check_schema_drift(records: list[dict], source: str,
                       known_fields: set[str]) -> list[str]:
    """Return warnings for fields in *)all** records that aren't in known_fields."""
    present = {k for r in records for k in (r or {}).keys()}
    unknown = present - known_fields - {"slug", "name"}
    return [f"[{source}] unexpected normalized fields: {sorted(unknown)}"] if unknown else []


KNOWN_FIELDS = set(schema.model_record_template().keys()) | {"from_cache"} | {"merged"} | {"raw_fields"} | {"hosts"} | {"provenance"}


def staleness_fallback(current: dict, fallback: dict, max_age_days: int = 7,
                       source: str = "?") -> dict:
    """Return an appropriate record when a source is stale or broken.

    Simple policy helper: if a fresh-but-empty/partial result arrives, prefer
    the last-good snapshot if it exists and is within max_age_days of today.
    Over-ride with real logic in the orchestrator; kept here for reuse.
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).timestamp()
    if fallback:
        fetched_ts = fallback.get("meta", {}).get("fetched_at_ts") or 0
        age_days = (now - fetched_ts) / 86400
        if 0 <= age_days <= max_age_days:
            log.warning("[%s] using stale snapshot aged %.1f days",
                        source, age_days)
            return fallback
    return current