#!/usr/bin/env python3
"""Standalone tests for the safe AA cache-pruning utility."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from prune_aa_cache import prune_cache


class PruneCacheTests(unittest.TestCase):
    def test_dry_run_is_bounded_and_non_destructive(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            old = cache / "rsc_raw_20260101_000000.bin"
            current = cache / "rsc_raw_20260827_000000.bin"
            keyed = cache / "rsc_raw_latest.bin"
            unrelated = cache / "notes.txt"
            for path in (old, current, keyed, unrelated):
                path.write_text("fixture", encoding="utf-8")
            old_timestamp = (datetime.now(timezone.utc) - timedelta(days=45)).timestamp()
            os.utime(old, (old_timestamp, old_timestamp))
            found = prune_cache(cache, 30, now=datetime.now(timezone.utc))
            self.assertEqual(found, [old])
            self.assertTrue(old.exists())
            self.assertTrue(keyed.exists())
            self.assertTrue(unrelated.exists())

    def test_apply_removes_only_matching_aged_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            old = cache / "snapshot_normalized_20260101_000000.json"
            retained = cache / "snapshot_normalized_20260827_000000.json"
            old.write_text("fixture", encoding="utf-8")
            retained.write_text("fixture", encoding="utf-8")
            reference = datetime(2026, 8, 27, tzinfo=timezone.utc)
            old_timestamp = (reference - timedelta(days=31)).timestamp()
            os.utime(old, (old_timestamp, old_timestamp))
            found = prune_cache(cache, 30, apply=True, now=reference)
            self.assertEqual(found, [old])
            self.assertFalse(old.exists())
            self.assertTrue(retained.exists())


if __name__ == "__main__":
    unittest.main()
