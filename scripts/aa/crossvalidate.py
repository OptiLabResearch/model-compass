#!/usr/bin/env python3.12
"""Cross-validation of AA sources against each other.

Validates that our extraction is correct by comparing independent sources for
the SAME model:
  - RSC (primary) vs Oolong snapshot (independent third party)
  - RSC vs official Free API  (when AA_API_KEY is set)

For each overlapping model we compare intelligence_index, input/output price,
and speed. Discrepancy thresholds are generous because the sources are
sampled at different times / have different precision. Large mismatches on a
meaningful fraction of models => a schema/scale bug, which we surface loudly.

Usage:
    python3.12 scripts/aa/crossvalidate.py
    AA_API_KEY=... python3.12 scripts/aa/crossvalidate.py --api
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
# When run as `python3.12 scripts/aa/crossvalidate.py`, Python puts scripts/aa
# on sys.path[0], which makes our aa/http.py shadow stdlib http -> circular
# import. Remove scripts/aa from the front.
if sys.path and Path(sys.path[0]).resolve() == Path(__file__).resolve().parent:
    sys.path.pop(0)
sys.path.insert(0, str(REPO / "scripts"))

logging.basicConfig(level=logging.WARNING)

log = logging.getLogger("aa.pipeline")


def _val(rec, path):
    node = rec
    for k in path:
        if not isinstance(node, dict):
            return None
        node = node.get(k)
    return node if node is not None else None


def compare_pair(a: dict, b: dict, paths, tol) -> dict:
    """Compare records a and b over the given value paths. Returns
    {label: (A_val, B_val, ok)} for fields present in both."""
    out = {}
    for label, path, atol in paths:
        va, vb = _val(a, path), _val(b, path)
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
            diff = abs(va - vb)
            ok = diff <= atol or (atol > 0 and diff / max(abs(va), 1e-9) <= 0.10)
            out[label] = (round(float(va), 3), round(float(vb), 3), ok)
    return out


def load_dataset(path: str) -> dict:
    import json
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=str(REPO / "data" / "aa_models_v2.json"))
    ap.add_argument("--api", action="store_true", help="also validate against official API")
    args = ap.parse_args()

    merged = {m["slug"]: m for m in load_dataset(args.models)["models"]}

    # 1) Independent snapshot cross-check
    from aa.http import fetch_json
    from aa.snapshot_source import DEFAULT_BASE_URL, _llms_url, _snapshot_array, _normalize
    latest, _ = fetch_json(DEFAULT_BASE_URL)
    llms_url = _llms_url(DEFAULT_BASE_URL, latest)
    payload, _ = fetch_json(llms_url)
    _k, entries = _snapshot_array(payload)
    if entries is None:
        print("Could not parse snapshot entries.")
        return
    snap = {}
    for e in entries:
        r = _normalize(e)
        if r.get("slug"):
            snap[r["slug"]] = r
    print(f"Snapshot has {len(snap)} models for cross-check.")

    paths = [
        ("intelligence_index", ["intelligence_index"], 3.0),
        ("input_price", ["pricing", "input"], 0.5),
        ("output_price", ["pricing", "output"], 1.0),
        ("speed_tps", ["performance", "median_output_speed_tps"], 15.0),
        ("context", ["context_tokens"], 100_000),
    ]
    overlap = set(merged) & set(snap)
    mismatch_buckets = {}
    compared = {p[0]: 0 for p in paths}
    for slug in overlap:
        a, b = merged[slug], snap[slug]
        res = compare_pair(a, b, paths, 0)
        for label, (va, vb, ok) in res.items():
            compared[label] += 1
            if not ok:
                mismatch_buckets.setdefault(label, []).append((slug, va, vb))

    print(f"\nOverlap: {len(overlap)} models matched by slug.")
    print("=== RSC(primary) vs Snapshot ===")
    for label in compared:
        n_comp = compared[label]
        bad = len(mismatch_buckets.get(label, []))
        pct_bad = (bad / n_comp * 100) if n_comp else 0
        flag = "OK" if pct_bad <= 8 else "DRIFT?"
        print(f"  {label:20} compared={n_comp:4d} mismatched={bad:4d} ({pct_bad:.0f}%)  {flag}")
        if mismatch_buckets.get(label):
            print("     e.g.", mismatch_buckets[label][:3])

    if args.api:
        import os
        if not os.environ.get("AA_API_KEY"):
            print("\nAA_API_KEY not set; skipping API cross-check.")
        else:
            from aa.official_api_source import OfficialAPISource
            api = OfficialAPISource()
            api_res = api.fetch()
            print(f"\n=== RSC vs Official API ({len(api_res.records)} API models) ===")
            api_by = {r["slug"]: r for r in api_res.records}
            overlap2 = set(merged) & set(api_by)
            mb2 = {}
            comp2 = {p[0]: 0 for p in paths}
            for slug in overlap2:
                res = compare_pair(merged[slug], api_by[slug], paths, 0)
                for label, (va, vb, ok) in res.items():
                    comp2[label] += 1
                    if not ok:
                        mb2.setdefault(label, []).append((slug, va, vb))
            for label in comp2:
                n = comp2[label]; bad = len(mb2.get(label, []))
                print(f"  {label:20} compared={n:4d} mismatched={bad:4d} ({bad/n*100 if n else 0:.0f}%)")


if __name__ == "__main__":
    main()