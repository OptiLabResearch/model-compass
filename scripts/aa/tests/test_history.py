"""History delta and retention tests."""
from __future__ import annotations
import sys
from pathlib import Path
import tempfile

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
from aa.history import diff_snapshots, prune_deltas  # noqa: E402
try:
    from _runner import run_tests  # noqa: E402
except ModuleNotFoundError:  # pytest imports this module from the repository root
    from scripts.aa.tests._runner import run_tests  # noqa: E402


def snap(score, *, generated="2026-08-22T00:00:00Z"):
    return {"generated_at": generated, "models": [{
        "slug": "a", "name": "A", "creator": "C",
        "intelligence_index": score, "pricing": {"input": 1, "output": 2},
        "performance": {"median_output_speed_tps": 10},
    }]}


def test_delta_captures_added_removed_and_field_changes():
    old = snap(50, generated="2026-08-15T00:00:00Z")
    new = {"generated_at": "2026-08-22T00:00:00Z", "models": snap(60)["models"] + [{
        "slug": "b", "name": "B", "creator": "D"}]}
    new["models"].append({"slug": "c", "name": "C", "creator": "E"})
    delta = diff_snapshots(old, new)
    assert delta["counts"] == {"previous": 1, "current": 3, "added": 2, "removed": 0, "changed": 1}
    assert delta["changed"][0]["changes"]["intelligence_index"] == {"before": 50, "after": 60}


def test_retention_keeps_newest_files():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        for name in ("2026-01-01.delta.json", "2026-01-02.delta.json", "2026-01-03.delta.json"):
            (root / name).write_text("{}")
        assert prune_deltas(root, keep=2) == ["2026-01-01.delta.json"]
        assert sorted(p.name for p in root.glob("*.delta.json")) == ["2026-01-02.delta.json", "2026-01-03.delta.json"]


if __name__ == "__main__":
    run_tests(globals(), "All history tests passed.")
