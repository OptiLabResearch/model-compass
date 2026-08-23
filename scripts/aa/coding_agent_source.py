"""Public Artificial Analysis coding-agent structured adapter."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen

from .http import atomic_write_json
from .observations import normalize_coding_agent_observation

URL = "https://artificialanalysis.ai/agents/coding-agents"
PARSER_VERSION = "0.2.0"
MAX_BYTES = 8 * 1024 * 1024


def parse_datasets_rich(page: str, *, fetched_at: str) -> list[dict]:
    payloads = []
    for raw in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S):
        try:
            payloads.append(json.loads(html.unescape(raw)))
        except json.JSONDecodeError:
            continue
    rows, versions = {}, []
    for payload in payloads:
        name = payload.get("name")
        description = payload.get("description") or ""
        version_match = re.search(r"\bv(\d+(?:\.\d+)*)\b", description, re.I)
        if version_match:
            versions.append(version_match.group(1))
        for row in payload.get("data") or []:
            label = (row.get("label") or "").strip()
            if not label:
                continue
            # Cost/time views append the lab/provider on a second line; that
            # suffix is source metadata, not a different harness variant.
            variant_label = re.sub(r"\s*\n\s*\([^()]*\)\s*$", "", label).strip()
            item = rows.setdefault(variant_label, {"label": variant_label, "source_labels": [], "scores": {}, "tokens": {}})
            item["source_labels"].append(label)
            item["benchmark_version"] = version_match.group(1) if version_match else None
            if name == "Coding Agent Index" and "codingAgentsIndex" in row:
                item["scores"]["coding_agent_index"] = row["codingAgentsIndex"]
            elif name == "Time per Task" and "codingAgentsMeanAgentWallTimeSec" in row:
                item["execution_time_seconds"] = row["codingAgentsMeanAgentWallTimeSec"]
            elif name == "Cost per Task" and "codingAgentsMeanCostUsd" in row:
                item["cost_per_task_usd"] = row["codingAgentsMeanCostUsd"]
            for key in ("totalTokens", "inputTokens", "cachedInputTokens", "outputTokens", "turns"):
                if key in row:
                    item["tokens"][key] = row[key]
            if "cacheHitRate" in row:
                item["cache_hit_rate"] = row["cacheHitRate"]
    result = []
    for label, item in rows.items():
        left, _, right = label.partition(" - ")
        model = right.split("\n", 1)[0].strip() if right else None
        config_match = re.search(r"\(([^()]*)\)", label)
        item.update({"variant_id": label, "source_labels": sorted(set(item.get("source_labels", []))), "agent_id": left.strip() or None,
                     "agent_name": left.strip() or None, "harness": left.strip() or None,
                     "model_name": model, "configuration": config_match.group(1) if config_match else None,
                     "benchmark_suite": "Artificial Analysis Coding Agent Index",
                     "benchmark_version": item.get("benchmark_version") or max(versions, default=None),
                     "parser_version": PARSER_VERSION})
        result.append(normalize_coding_agent_observation(item, fetched_at=fetched_at, source="artificial_analysis_coding_agents"))
    return result


def parse_datasets(page: str, *, fetched_at: str) -> list[dict]:
    """Backward-compatible one-row-per-JSON-LD-dataset parser."""
    payloads = []
    for raw in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S):
        try:
            payloads.append(json.loads(html.unescape(raw)))
        except json.JSONDecodeError:
            continue
    out = []
    page_version = next((m.group(1) for p in payloads for m in [re.search(r"\bv(\d+(?:\.\d+)*)\b", p.get("description") or "", re.I)] if m), None)
    for payload in payloads:
        name, desc = payload.get("name"), payload.get("description") or ""
        if name not in {"Coding Agent Index", "Time per Task", "Cost per Task"}:
            continue
        version = re.search(r"\bv(\d+(?:\.\d+)*)\b", desc, re.I)
        metric = {"Coding Agent Index": "codingAgentsIndex", "Time per Task": "codingAgentsMeanAgentWallTimeSec", "Cost per Task": "codingAgentsMeanCostUsd"}[name]
        for row in payload.get("data") or []:
            if not row.get("label") or metric not in row: continue
            raw = {"label": row["label"], "agent_id": row["label"], "agent_name": row["label"], "benchmark_suite": name,
                   "benchmark_version": version.group(1) if version else page_version, "scores": {"coding_agent_index": row.get("codingAgentsIndex")},
                   "execution_time_seconds": row.get("codingAgentsMeanAgentWallTimeSec"), "cost_per_task_usd": row.get("codingAgentsMeanCostUsd"), "parser_version": PARSER_VERSION}
            out.append(normalize_coding_agent_observation(raw, fetched_at=fetched_at, source="artificial_analysis_coding_agents"))
    return out


def fetch(*, timeout: int = 30) -> dict:
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    req = Request(URL, headers={"User-Agent": "ModelCompass/3.0"})
    with urlopen(req, timeout=timeout) as response:
        page = response.read(MAX_BYTES + 1)
    if len(page) > MAX_BYTES:
        raise ValueError("coding-agent page exceeded bounded payload size")
    observations = parse_datasets_rich(page.decode("utf-8", "replace"), fetched_at=fetched_at)
    return {"version": 1, "parser_version": PARSER_VERSION, "generated_at": fetched_at,
            "source": "artificial_analysis_coding_agents", "source_url": URL,
            "methodology": "public JSON-LD metric views merged by source-declared variant label",
            "coverage": {"scope": "partial_public_jsonld", "complete_public_dataset": False,
                         "variants": len(observations),
                         "benchmark_version": max((o.get("benchmark_version") or "" for o in observations), default=None),
                         "note": "Public JSON-LD is bounded and may omit rendered/network-only rows."},
            "observation_count": len(observations), "observations": observations}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Fetch public coding-agent observations")
    parser.add_argument("--output", type=Path, default=Path("data/coding_agent_observations.json"))
    args = parser.parse_args(argv)
    result = fetch()
    atomic_write_json(args.output, result)
    print(f"Coding-agent observations={result['observation_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
