#!/usr/bin/env python3
"""Deterministic tests for AA Free API pagination and normalization."""

import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("fetch_aa_models.py")
SPEC = importlib.util.spec_from_file_location("fetch_aa_models", MODULE_PATH)
fetch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fetch)


class FetchAAModelsTests(unittest.TestCase):
    def test_free_mixed_case_slug_is_canonicalized(self):
        models = fetch.normalize_api_slugs([{"slug": "QwQ-32B-Preview"}])
        self.assertEqual(models[0]["slug"], "qwq-32b-preview")

    def test_free_api_paginates_and_preserves_metadata(self):
        requested = []
        original = fetch._fetch_json

        def fake_fetch(req):
            requested.append(req.full_url)
            page = int(req.full_url.rsplit("=", 1)[1])
            return {
                "tier": "free",
                "intelligence_index_version": 4.1,
                "pagination": {
                    "page": page,
                    "page_size": 1,
                    "total_pages": 2,
                    "has_more": page == 1,
                },
                "data": [{
                    "id": f"id-{page}",
                    "name": f"Model {page}",
                    "slug": f"model-{page}",
                    "release_date": "2026-01-01",
                    "model_creator": {"id": "creator-id", "name": "Creator"},
                    "evaluations": {},
                    "pricing": {},
                }],
            }, {"X-RateLimit-Remaining": str(100 - page)}

        fetch._fetch_json = fake_fetch
        try:
            models, meta = fetch.fetch_free_api_models("not-a-real-key")
        finally:
            fetch._fetch_json = original

        self.assertEqual([m["slug"] for m in models], ["model-1", "model-2"])
        self.assertEqual(meta["tier"], "free")
        self.assertEqual(meta["intelligence_index_version"], 4.1)
        self.assertEqual(meta["headers"]["X-RateLimit-Remaining"], "98")
        self.assertEqual(requested, [
            f"{fetch.FREE_API_URL}?page=1",
            f"{fetch.FREE_API_URL}?page=2",
        ])

    def test_free_fields_build_model_entry(self):
        free = {
            "id": "model-id",
            "name": "Example",
            "slug": "example",
            "release_date": "2026-01-01",
            "model_creator": {"id": "creator-id", "name": "Creator"},
            "evaluations": {"artificial_analysis_agentic_index": 42.5},
            "pricing": {
                "price_1m_input_tokens": 1,
                "price_1m_cache_hit_tokens": 0.25,
                "price_1m_cache_write_tokens": 1.25,
            },
            "artificial_analysis_intelligence_index_cost": {
                "total_cost": 20.69,
                "cost_per_task": {"total_cost": 0.1678},
            },
            "performance": {
                "median_output_tokens_per_second": 99.5,
                "median_time_to_first_token_seconds": 0.4,
                "median_time_to_first_answer_token_seconds": 3.2,
                "median_end_to_end_response_time_seconds": 8.7,
            },
            "_has_free_api_data": True,
        }

        model = fetch.build_model_entry(free, None)

        self.assertEqual(model["aa_id"], "model-id")
        self.assertEqual(model["creator_aa_id"], "creator-id")
        self.assertEqual(model["composite"]["agentic_index"], 42.5)
        self.assertEqual(model["pricing_per_m_tokens"]["cache_hit"], 0.25)
        self.assertEqual(model["pricing_per_m_tokens"]["cache_write"], 1.25)
        self.assertEqual(model["intelligence_evaluation_total_cost_usd"], 20.69)
        self.assertEqual(model["cost_per_intelligence_task_usd"]["total"], 0.1678)
        self.assertEqual(model["performance"]["output_speed_tps"], 99.5)
        self.assertEqual(model["performance"]["ttft_seconds_total"], 0.4)
        self.assertEqual(model["performance"]["ttft_seconds_answer"], 3.2)
        self.assertEqual(model["performance"]["end_to_end_500tok"]["total"], 8.7)
        self.assertTrue(model["data_sources"]["documented_free_api"])


    def test_free_api_ignores_identical_duplicate_across_pages(self):
        original = fetch._fetch_json
        model = {
            "id": "stable-id",
            "name": "Example",
            "slug": "Example",
            "release_date": "2026-01-01",
            "model_creator": {"id": "creator-id", "name": "Creator"},
            "evaluations": {},
            "pricing": {},
        }

        def fake_fetch(req):
            page = int(req.full_url.rsplit("=", 1)[1])
            return {
                "tier": "free",
                "intelligence_index_version": 4.1,
                "pagination": {
                    "page": page,
                    "page_size": 1,
                    "total_pages": 2,
                    "has_more": page == 1,
                },
                "data": [dict(model)],
            }, {}

        fetch._fetch_json = fake_fetch
        try:
            models, meta = fetch.fetch_free_api_models("not-a-real-key")
        finally:
            fetch._fetch_json = original

        self.assertEqual([item["slug"] for item in models], ["example"])
        self.assertEqual(meta["duplicate_slugs"], ["example"])

    def test_free_api_rejects_conflicting_duplicate_slug(self):
        original = fetch._fetch_json

        def fake_fetch(req):
            page = int(req.full_url.rsplit("=", 1)[1])
            return {
                "tier": "free",
                "intelligence_index_version": 4.1,
                "pagination": {
                    "page": page,
                    "page_size": 1,
                    "total_pages": 2,
                    "has_more": page == 1,
                },
                "data": [{
                    "id": f"id-{page}",
                    "name": f"Model {page}",
                    "slug": "duplicate",
                    "release_date": "2026-01-01",
                    "model_creator": {"id": "creator-id", "name": "Creator"},
                    "evaluations": {},
                    "pricing": {},
                }],
            }, {}

        fetch._fetch_json = fake_fetch
        try:
            with self.assertRaisesRegex(RuntimeError, "conflicting duplicate slug"):
                fetch.fetch_free_api_models("not-a-real-key")
        finally:
            fetch._fetch_json = original


if __name__ == "__main__":
    unittest.main()
