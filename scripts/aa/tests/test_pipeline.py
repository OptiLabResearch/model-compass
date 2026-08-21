"""Unit tests for the aa package pipeline (RSC parser, merge, sanity).

Run:   python3.12 -m pytest scripts/aa/tests  -v
   or: python3.12 scripts/aa/tests/test_pipeline.py

Uses a minimal synthetic RSC flight payload so tests are deterministic and
offline (no network, no API key). Verifies the core guarantees we care about:
structural drift detection, 0..1->0..100 conversion, dedup, NaN/dupe-checking,
and the merge priority.
"""

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
if sys.path and Path(sys.path[0]).resolve() == Path(__file__).resolve().parent.parent:
    sys.path.pop(0)  # avoid aa/http.py shadowing stdlib http when run as a script
sys.path.insert(0, str(REPO / "scripts"))

from aa import rsc_source
from aa import schema
from aa import validate
from aa.http import atomic_write_json


def build_flight(rows, extra_after=""):
    """Wrap a rows array in a minimal Next.js flight-style payload.

    The real RSC payload carries the model table as *literal* JSON on the wire
    (the `"rows":[ ... ]` marker must appear verbatim), so we do the same here.
    """
    return ('<div>...prefix ' + json.dumps({"rows": rows}, separators=(",", ":"))
            + ' suffix ' + extra_after + '</div>')


def make_row(slug="gpt-x", name="GPT-X", ii=50.0, price_in=1.0, is_reasoning=True,
             open_weights=False, context=128000, omni=90.0, host="Acme"):
    """ii/omni are ALREADY on AA's 0..100 scale (verified from live dump);
    benchmarks below are 0..1 fractions converted by the parser to 0..100."""
    return {
        "id": "uuid-" + slug,
        "label": name,
        "hostApiId": slug,
        "host": {"name": host, "slug": host.lower(), "logo": "x.svg"},
        "model": {
            "slug": slug, "name": name, "reasoningModel": is_reasoning,
            "isOpenWeights": open_weights, "intelligenceIndex": ii,
            "omniscience": omni, "omniscienceNonHallucination": 0.8,
            "gpqa": 0.9, "sizeClass": "medium",
            "creator": {"name": host},
        },
        "features": {"contextWindowTokens": context},
        "pricing": {"price1mInputTokens": price_in, "price1mOutputTokens": 4.0},
        "performance": {"medianOutputTokensPerSecond": 150.0,
                        "medianTimeToFirstTokenSeconds": 1.0},
    }


def build_models(rows):
    payload = build_flight([make_row(*r) for r in rows])
    return rows


def test_rsc_extract_normalize_roundtrip():
    # ii/omni are on AA's 0..100 scale; gpqa/omniscience_non_halluc are 0..1.
    rows = [make_row("gpt-a", "A", ii=50.0), make_row("gpt-b", "B", ii=70.0)]
    payload = build_flight(rows)
    out, _ = rsc_source._extract_rows(payload)
    assert out is not None and len(out) == 2
    rec = rsc_source.normalize_row(out[0], {"source": "rsc"})
    assert rec["slug"] == "gpt-a"
    assert rec["intelligence_index"] == 50.0          # already 0..100
    assert rec["omniscience_index"] == 90.0           # already 0..100
    assert rec["benchmarks"]["gpqa"] == 90.0          # 0..1 -> 0..100
    assert rec["benchmarks"]["omniscience_non_halluc"] == 80.0
    assert rec["context_tokens"] == 128000
    assert rec["pricing"]["input"] == 1.0
    assert validate.run_sanity([rec], "rsc", 1).passed


def test_drift_detect_missing_rows():
    payload = '<div>no rows here at all' + '</div>'
    assert rsc_source._extract_rows(payload) == (None, None)


def test_drift_detect_not_model_rows():
    # rows present but entries aren't host-model pairs -> not looks_like_row
    rows = [{"foo": 1}]
    payload = build_flight(rows)
    out, _ = rsc_source._extract_rows(payload)
    assert out is not None
    assert not any(rsc_source._looks_like_row(r) for r in out)


def test_duplicate_slug_detection():
    recs = [
        {**schema.model_record_template(), "slug": "dup", "name": "A"},
        {**schema.model_record_template(), "slug": "dup", "name": "B"},
    ]
    rep = validate.run_sanity(recs, "rsc", 1)
    assert any("duplicate" in f for f in rep.failures)


def test_nonfinite_detection():
    rec = schema.model_record_template()
    rec.update({"slug": "x", "name": "X", "intelligence_index": float("nan")})
    rep = validate.run_sanity([rec], "rsc", 0)
    assert any("non-finite" in f for f in rep.failures)


def test_merge_priority_rich_over_thin():
    from aa.orchestrate import merge_records
    from aa.source_base import SourceResult
    rich = SourceResult(source="rsc", parser_version="0", fetched_at="t",
                        fetched_at_ts=0, records=[{
                            **schema.model_record_template(),
                            "slug": "m", "name": "M", "intelligence_index": 60.0,
                            "pricing": {"input": 1.0, "output": 2.0,
                                        "blended_3_1": None, "blended_7_2_1": None,
                                        "blended_1_1": None, "cache_hit": None,
                                        "cache_write": None},
                            "benchmarks": {**schema.model_record_template()["benchmarks"]},
                        }], healthy=True)
    thin = SourceResult(source="official_api", parser_version="0", fetched_at="t",
                        fetched_at_ts=0, records=[{
                            **schema.model_record_template(),
                            "slug": "m", "name": "M", "intelligence_index": None,
                            "pricing": {"input": None, "output": None,
                                        "blended_3_1": 3.5, "blended_7_2_1": None,
                                        "blended_1_1": None, "cache_hit": None,
                                        "cache_write": None},
                            "benchmarks": {**schema.model_record_template()["benchmarks"]},
                        }], healthy=True)
    merged = merge_records([rich, thin])
    assert len(merged) == 1
    m = merged[0]
    assert m["intelligence_index"] == 60.0       # rich wins
    assert m["pricing"]["blended_3_1"] == 3.5    # thin fills rich's gap
    assert m["source"] == "rsc"                  # primary provenance
    assert "official_api" in m["merged"].get("also_from", [])


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("All tests passed.")