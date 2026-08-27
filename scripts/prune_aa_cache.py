#!/usr/bin/env python3
"""Prune aged timestamped AA debug payloads without touching reusable caches.

The command is dry-run by default. Pass ``--apply`` to remove only files whose
names match the timestamped raw/normalized debug-cache convention and whose
modification time is older than the requested retention window.
"""

from __future__ import annotations

import argparse
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CACHE_DIR = REPO_ROOT / "data" / "aa_cache"
DEBUG_CACHE_RE = re.compile(
    r"^(?:rsc_raw|snapshot_raw|snapshot_normalized)_\d{8}_\d{6}\.(?:bin|json)$"
)


def cache_candidates(cache_dir: Path, cutoff: datetime) -> list[Path]:
    """Return only recognized timestamped debug files older than ``cutoff``."""
    if not cache_dir.is_dir():
        return []
    cutoff_timestamp = cutoff.timestamp()
    candidates = []
    for path in sorted(cache_dir.iterdir()):
        if not path.is_file() or not DEBUG_CACHE_RE.fullmatch(path.name):
            continue
        if path.stat().st_mtime < cutoff_timestamp:
            candidates.append(path)
    return candidates


def prune_cache(
    cache_dir: Path,
    max_age_days: int,
    *,
    apply: bool = False,
    now: datetime | None = None,
) -> list[Path]:
    """Find and optionally remove aged timestamped debug payloads."""
    if max_age_days <= 0:
        raise ValueError("max_age_days must be positive")
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    paths = cache_candidates(cache_dir, reference - timedelta(days=max_age_days))
    if apply:
        for path in paths:
            path.unlink()
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--max-age-days", type=int, default=30)
    parser.add_argument(
        "--apply", action="store_true",
        help="remove matching files; without this flag the command is a dry run",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="print only the number of matching files, not every path",
    )
    args = parser.parse_args()
    try:
        paths = prune_cache(args.cache_dir, args.max_age_days, apply=args.apply)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    action = "Removed" if args.apply else "Would remove"
    if args.quiet:
        print(f"{action.lower()} {len(paths)} aged timestamped debug cache file(s).")
    else:
        for path in paths:
            print(f"{action} {path}")
    if not paths and not args.quiet:
        print("No aged timestamped debug cache files found.")
    if not args.apply and paths:
        print("Dry run only; pass --apply to remove these files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
