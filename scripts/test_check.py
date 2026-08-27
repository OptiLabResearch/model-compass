"""Focused tests for conservative validation-scope selection."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from check import auto_scope, changed_paths


class AutoScopeTests(unittest.TestCase):
    def test_documentation_changes_use_quick_scope(self):
        self.assertEqual(auto_scope({"docs/DEVELOPMENT.md", "README.md"}), "quick")

    def test_public_source_changes_use_site_scope(self):
        self.assertEqual(auto_scope({"public/index.html", "public/assets/nav.js"}), "site")

    def test_generated_public_data_requires_full_scope(self):
        self.assertEqual(auto_scope({"public/data/models.json"}), "all")

    def test_unknown_or_missing_changes_use_full_scope(self):
        self.assertEqual(auto_scope({"scripts/model_compass.py"}), "all")
        self.assertEqual(auto_scope(None), "all")

    def test_unstaged_status_keeps_the_first_path_character(self):
        with patch("check._git_paths", return_value={" M docs/STATUS.md"}):
            self.assertEqual(changed_paths(), {"docs/STATUS.md"})


if __name__ == "__main__":
    unittest.main()
