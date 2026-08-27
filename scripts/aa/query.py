"""Programmatic query layer over the AA normalized dataset.

Purpose: answer model-selection / orchestration questions easily, e.g.
  - best coding model
  - best planning/reasoning model    (AA doesn't expose a planning index; use
    intelligence + reasoning flag + agentic as proxies)
  - best agentic model
  - best model for a benchmark profile
  - quality vs cost
  - quality vs speed
  - coding quality vs price
  - appropriate backup model
  - models improving / getting cheaper

Load once:   db = AADB('data/aa_models_v2.json')
Then use the helpers below. Every helper filters to models that *have* the
relevant metric (no silent zero-fill), and returns records head-first ordered
by the score you asked for.
"""

from __future__ import annotations

import json
from pathlib import Path
from .decision import DecisionEngine, Profile, PROFILES


class AADB:
    def __init__(self, path: str | Path = "data/aa_models_v2.json",
                 access: dict[str, dict] | None = None):
        self.path = Path(path)
        blob = json.loads(self.path.read_text(encoding="utf-8"))
        self.models = blob.get("models", [])
        self.generated_at = blob.get("generated_at")
        self.coverage = blob.get("coverage", {})
        self._by_slug = {m.get("slug"): m for m in self.models}
        self.engine = DecisionEngine(self.models, access=access)

    # -- index lookup ------------------------------------------------------
    def get(self, slug: str) -> dict | None:
        return self._by_slug.get(slug)

    def top_by_index(self, metric: str = "intelligence_index", limit: int = 10,
                     min_value: float | None = None,
                     require_reasoning: bool | None = None,
                     require_agentic: bool = False):
        """Return top-N by a 0..100 index. ``metric`` is one of
        intelligence_index/coding_index/agentic_index/omniscience_index."""
        rows = []
        for m in self.models:
            v = m.get(metric)
            if not isinstance(v, (int, float)) or v is None:
                continue
            if min_value is not None and v < min_value:
                continue
            if require_reasoning is True and not m.get("is_reasoning"):
                continue
            if require_reasoning is False and m.get("is_reasoning"):
                continue
            if require_agentic and m.get("agentic_index") is None:
                continue
            rows.append((v, m))
        rows.sort(key=lambda t: t[0], reverse=True)
        return [(v, m) for v, m in rows[:limit]]

    # -- value helpers -----------------------------------------------------
    @staticmethod
    def _blend3(m):
        """Blended 1M cost at 3:1 input:output (AA's default). Falls back to a
        3:1 blend computed from input/output when the source omits it."""
        p = m.get('pricing') or {}
        b = p.get('blended_3_1')
        if isinstance(b, (int, float)):
            return b
        d = p.get('blended_7_2_1')
        if isinstance(d, (int, float)):
            return d
        i, o = p.get('input'), p.get('output')
        if isinstance(i, (int, float)) and isinstance(o, (int, float)):
            return round((3 * i + o) / 4.0, 4)
        return None

    def best_coding(self, limit: int = 10):
        return self.top_by_index("coding_index", limit)

    def best_agentic(self, limit: int = 10):
        return self.top_by_index("agentic_index", limit)

    def best_intelligence(self, limit: int = 10):
        return self.top_by_index("intelligence_index", limit)

    def best_omniscience(self, limit: int = 10):
        return self.top_by_index("omniscience_index", limit)

    def best_for_benchmark(self, benchmark: str, limit: int = 10):
        """Top by a specific benchmark score (0..100)."""
        rows = []
        for m in self.models:
            v = (m.get("benchmarks") or {}).get(benchmark)
            if isinstance(v, (int, float)) and v is not None:
                rows.append((v, m))
        rows.sort(key=lambda t: t[0], reverse=True)
        return rows[:limit]

    def value_intelligence_per_dollar(self, limit: int = 10):
        """IQ per $ of a blended 1M-token pass (3:1 blend, computed if absent)."""
        rows = []
        for m in self.models:
            iq = m.get("intelligence_index")
            cost = self._blend3(m)
            if isinstance(iq, (int, float)) and isinstance(cost, (int, float)) \
                    and cost > 0:
                rows.append((iq / cost, m, iq, cost))
        rows.sort(key=lambda t: t[0], reverse=True)
        return rows[:limit]

    def value_intelligence_per_task(self, limit: int = 10):
        """IQ per $ of running AA's Intelligence Index eval (cost-per-task basis)."""
        rows = []
        for m in self.models:
            iq = m.get("intelligence_index")
            cpt = m.get("cost_per_intelligence_task_usd")
            if isinstance(iq, (int, float)) and isinstance(cpt, (int, float)) \
                    and cpt > 0:
                rows.append((iq / cpt, m, iq, cpt))
        rows.sort(key=lambda t: t[0], reverse=True)
        return rows[:limit]

    def value_coding_per_dollar(self, limit: int = 10):
        rows = []
        for m in self.models:
            cd = m.get("coding_index")
            cost = self._blend3(m)
            if isinstance(cd, (int, float)) and isinstance(cost, (int, float)) \
                    and cost > 0:
                rows.append((cd / cost, m, cd, cost))
        rows.sort(key=lambda t: t[0], reverse=True)
        return rows[:limit]

    def quality_vs_speed(self, metric: str = "intelligence_index", limit: int = 10):
        """Score/iq vs throughput (tokens/s). Returns models with both metrics."""
        rows = []
        for m in self.models:
            q = m.get(metric)
            sp = (m.get("performance") or {}).get("median_output_speed_tps")
            if isinstance(q, (int, float)) and isinstance(sp, (int, float)) and sp > 0:
                rows.append((q, m, sp))
        rows.sort(key=lambda t: t[0], reverse=True)
        return rows[:limit]

    def fastest(self, limit: int = 10):
        rows = []
        for m in self.models:
            sp = (m.get("performance") or {}).get("median_output_speed_tps")
            if isinstance(sp, (int, float)) and sp > 0:
                rows.append((sp, m))
        rows.sort(key=lambda t: t[0], reverse=True)
        return rows[:limit]

    def cheapest_1m(self, blind: bool = False, limit: int = 10):
        rows = []
        for m in self.models:
            inp = (m.get("pricing") or {}).get("input")
            out = (m.get("pricing") or {}).get("output")
            if isinstance(inp, (int, float)) and isinstance(out, (int, float)) \
                    and not (blind and not m.get("is_open_weights")):
                rows.append((inp, m, inp, out))
        rows.sort(key=lambda t: t[0])
        return rows[:limit]

    def backup_candidates(self, primary_metric: str = "intelligence_index",
                          gap: float = 5.0, require_open_weights: bool = False,
                          limit: int = 10):
        """Backup-model candidates: close in quality to the best, with a
        different creator (avoid single-vendor dependency)."""
        best = self.top_by_index(primary_metric, 1)
        if not best:
            return []
        top_score = best[0][0]
        primary_creator = best[0][1].get("creator")
        primary_hosts = {h.get("slug") or h.get("name") for h in best[0][1].get("hosts", [])}
        rows = []
        for m in self.models:
            v = m.get(primary_metric)
            if not isinstance(v, (int, float)):
                continue
            if top_score - v > gap:
                continue
            if require_open_weights and not m.get("is_open_weights"):
                continue
            if m.get("creator") == primary_creator:
                continue
            hosts = {h.get("slug") or h.get("name") for h in m.get("hosts", [])}
            if primary_hosts and hosts & primary_hosts:
                continue
            rows.append((v, m))
        rows.sort(key=lambda t: t[0], reverse=True)
        return rows[:limit]

    def recommend(self, profile: str | dict | Profile = "premium", limit: int = 10,
                  available_only: bool = False) -> dict:
        return self.engine.recommend(profile, limit=limit, available_only=available_only)

    def pareto(self, dimensions: list[str]) -> list[dict]:
        return self.engine.pareto(dimensions)

    def backups(self, primary_slug: str, limit: int = 10) -> list[dict]:
        return self.engine.backups(primary_slug, limit=limit)

    def explain(self, slug: str) -> dict | None:
        model = self.get(slug)
        return self.engine.explain(model) if model else None

    @staticmethod
    def profiles() -> list[str]:
        return sorted(PROFILES)
