"""Focused tests for the agent-facing CLI output and loading boundaries."""
from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import model_compass  # noqa: E402


class ModelCompassCliTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.data_path = root / "models.json"
        self.identity_path = root / "identity.json"
        self.data_path.write_text(json.dumps({"models": [
            {
                "slug": "fixture/model",
                "name": "Fixture Model",
                "creator": "Fixture",
                "source": "fixture",
                "intelligence_index": 90,
                "coding_index": 80,
                "agentic_index": 70,
                "context_tokens": 128000,
                "is_reasoning": True,
                "is_open_weights": False,
                "pricing": {"input": 1.0, "output": 2.0, "blended_3_1": 1.3},
                "performance": {"median_output_speed_tps": 100.0,
                                "median_ttft_seconds": 1.0},
                "hosts": [{"slug": "fixture-provider", "name": "Fixture Provider",
                           "raw_provider_payload": "omitted"}],
                "provenance": {"sources": ["fixture"], "fetched_at": "2026-08-27T00:00:00Z"},
                "raw_fields": {"fixture_payload": "large acquisition payload"},
            },
        ]}), encoding="utf-8")
        self.identity_path.write_text(json.dumps({
            "health": {"status": "needs_review"},
            "unresolved": [{"id": index} for index in range(3)],
            "ambiguous": [{"id": "ambiguous"}],
            "conflicts": [],
        }), encoding="utf-8")

    def tearDown(self):
        self.tempdir.cleanup()

    def invoke(self, *args):
        output = io.StringIO()
        with redirect_stdout(output):
            result = model_compass.main(list(args))
        self.assertEqual(result, 0)
        return json.loads(output.getvalue())

    def test_default_model_view_omits_raw_payload_and_full_restores_it(self):
        summary = self.invoke("--data", str(self.data_path), "list", "--limit", "1")
        self.assertNotIn("raw_fields", summary[0])
        self.assertNotIn("raw_provider_payload", json.dumps(summary))

        full = self.invoke("--data", str(self.data_path), "list", "--limit", "1", "--full")
        self.assertIn("raw_fields", full[0])

    def test_compact_output_is_single_line_json(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(model_compass.main([
                "--data", str(self.data_path), "list", "--limit", "1", "--compact",
            ]), 0)
        self.assertEqual(len(output.getvalue().splitlines()), 1)
        self.assertEqual(json.loads(output.getvalue())[0]["slug"], "fixture/model")

    def test_phase5_profiles_are_cli_exposed_and_access_filtered(self):
        best = self.invoke(
            "--data", str(self.data_path), "recommend", "best-overall", "--limit", "1",
        )
        self.assertEqual(best["profile"], "best-overall")
        self.assertEqual(best["strategy"], "weighted")

        access_path = Path(self.tempdir.name) / "access.json"
        access_path.write_text(json.dumps({
            "models": {"fixture/model": {"available": True, "source": "fixture"}},
        }), encoding="utf-8")
        available = self.invoke(
            "--data", str(self.data_path), "--access", str(access_path),
            "recommend", "available-to-me", "--limit", "1",
        )
        self.assertEqual(available["profile"], "available-to-me")
        self.assertEqual(available["recommendations"][0]["explanation"]["availability"]["status"], "available")

        marginal = self.invoke(
            "--data", str(self.data_path), "recommend", "marginal-cost-aware", "--limit", "1",
        )
        self.assertEqual(marginal["profile"], "marginal-cost-aware")
        self.assertEqual(marginal["strategy"], "marginal_cost")

    def test_nonfinite_recommendation_fields_are_emitted_as_unknown_json(self):
        data = json.loads(self.data_path.read_text(encoding="utf-8"))
        data["models"][0]["performance"]["median_output_speed_tps"] = float("nan")
        data["models"][0]["provenance"]["fetched_at"] = float("inf")
        self.data_path.write_text(json.dumps(data), encoding="utf-8")

        result = self.invoke(
            "--data", str(self.data_path), "recommend", "best-overall", "--limit", "1",
        )
        row = result["recommendations"][0]
        self.assertIsNone(row["performance"]["median_output_speed_tps"])
        self.assertIsNone(row["provenance"]["fetched_at"])

    def test_nonfinite_explain_fields_are_emitted_as_unknown_json(self):
        data = json.loads(self.data_path.read_text(encoding="utf-8"))
        data["models"][0]["provenance"]["fetched_at"] = float("nan")
        self.data_path.write_text(json.dumps(data), encoding="utf-8")

        result = self.invoke(
            "--data", str(self.data_path), "explain", "fixture/model",
        )
        self.assertIsNone(result["provenance"]["fetched_at"])

    def test_identity_diagnostics_are_bounded_and_do_not_load_model_data(self):
        missing_data = Path(self.tempdir.name) / "missing-model-data.json"
        summary = self.invoke(
            "--data", str(missing_data), "--identity-data", str(self.identity_path),
            "unresolved-identities", "--limit", "1",
        )
        self.assertEqual(summary["counts"], {"ambiguous": 1, "conflicts": 0, "unresolved": 3})
        self.assertEqual(len(summary["samples"]["unresolved"]), 1)

        full = self.invoke(
            "--data", str(missing_data), "--identity-data", str(self.identity_path),
            "unresolved-identities", "--full",
        )
        self.assertEqual(len(full["unresolved"]), 3)


if __name__ == "__main__":
    unittest.main()
