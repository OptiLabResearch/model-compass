#!/usr/bin/env python3
"""Deterministic replay and public-contract tests for the rich site builder."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RICH_PATH = REPO / "data" / "aa_models_v2.json"
BUILDER_PATH = REPO / "scripts" / "build_site_from_aa.py"


def load_builder():
    spec = importlib.util.spec_from_file_location("build_site_from_aa", BUILDER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PublicBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builder = load_builder()
        cls.rich = json.loads(RICH_PATH.read_text(encoding="utf-8"))

    def test_selection_is_stable_for_an_explicit_as_of_date(self):
        records = self.rich["models"]
        first = self.builder.select_models(records, 183, date(2026, 8, 23))
        second = self.builder.select_models(records, 183, date(2026, 8, 23))
        self.assertEqual([row["slug"] for row in first], [row["slug"] for row in second])
        self.assertGreaterEqual(len(first), len(self.builder.FEATURED_SLUGS))

    def test_builder_replay_writes_source_timestamp_and_as_of(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "models.json"
            import sys
            previous = sys.argv
            try:
                sys.argv = [str(BUILDER_PATH), "--as-of", "2026-08-23", "--output", str(output)]
                self.assertEqual(self.builder.main(), 0)
            finally:
                sys.argv = previous
            data = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(data["as_of"], "2026-08-23")
            self.assertEqual(data["scraped_at"], self.rich["generated_at"])
            expected = self.builder.select_models(
                self.rich["models"], 183, date(2026, 8, 23)
            )
            self.assertEqual(len(data["models"]), len(expected))
            self.assertEqual(data["coverage"]["total"], len(data["models"]))


if __name__ == "__main__":
    unittest.main()
