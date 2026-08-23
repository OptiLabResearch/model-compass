"""Public Artificial Analysis coding-agent page adapter.

The page exposes a small JSON-LD Dataset payload to ordinary visitors. This
adapter preserves the displayed agent/harness label and separates it from base
model observations; it does not infer a canonical model slug from free text.
"""
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
PARSER_VERSION = "0.1.0"


def parse_datasets(page: str, *, fetched_at: str) -> list[dict]:
    datasets = []
    payloads = []
    for raw in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S):
        try:
            payloads.append(json.loads(html.unescape(raw)))
        except json.JSONDecodeError:
            continue
    page_version = next((match.group(1) for payload in payloads
                         for match in [re.search(r"\bv(\d+(?:\.\d+)*)\b", payload.get("description") or "", re.I)]
                         if match), None)
    for payload in payloads:
        name = payload.get("name")
        description = payload.get("description") or ""
        if name not in {"Coding Agent Index", "Time per Task", "Cost per Task"}:
            continue
        metric = {"Coding Agent Index": "codingAgentsIndex",
                  "Time per Task": "codingAgentsMeanAgentWallTimeSec",
                  "Cost per Task": "codingAgentsMeanCostUsd"}[name]
        for row in payload.get("data") or []:
            label = row.get("label")
            if not label or metric not in row:
                continue
            version_match = re.search(r"\bv(\d+(?:\.\d+)*)\b", description, re.I)
            item = {"agent_id": label, "agent_name": label,
                    "benchmark_suite": name, "benchmark_version": version_match.group(1) if version_match else page_version,
                    "scores": {"coding_agent_index": row.get("codingAgentsIndex")},
                    "execution_time_seconds": row.get("codingAgentsMeanAgentWallTimeSec"),
                    "cost_per_task_usd": row.get("codingAgentsMeanCostUsd"),
                    "raw_label": label, "methodology_description": description}
            datasets.append(normalize_coding_agent_observation(item, fetched_at=fetched_at, source="artificial_analysis_coding_agents"))
    return datasets


def fetch(*, timeout: int = 30) -> dict:
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    req = Request(URL, headers={"User-Agent": "ModelCompass/2.0"})
    with urlopen(req, timeout=timeout) as response:
        page = response.read(5 * 1024 * 1024).decode("utf-8", "replace")
    observations = parse_datasets(page, fetched_at=fetched_at)
    labels = sorted({o.get("agent_id") for o in observations if o.get("agent_id")})
    suites = sorted({o.get("benchmark_suite") for o in observations})
    return {"version": 1, "parser_version": PARSER_VERSION, "generated_at": fetched_at,
            "source": "artificial_analysis_coding_agents", "source_url": URL,
            "methodology": "public JSON-LD datasets; agent/harness labels preserved verbatim",
            "coverage": {"scope": "partial_public_jsonld", "complete_public_dataset": False,
                         "agent_labels": len(labels), "dataset_names": suites,
                         "note": "JSON-LD is a partial structured view; richer page/network datasets may exist."},
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
