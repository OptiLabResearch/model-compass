"""Source-adapter contract.

Every Artificial Analysis data source (RSC web payload, official API,
third-party snapshot) is wrapped in an :class:`SourceAdapter` that returns a
single :class:`SourceResult`:

- the raw payload (or raw snapshot) — preserved, not just normalized
- normalized per-model records on the common schema
- provenance metadata: source name, fetch timestamp, parser version,
  per-record original id/slug, and errors/warnings

The orchestrator merges ``SourceResult.records`` keyed by normalized model
slug, so any source's extraction mechanism can be swapped in or out without
touching downstream logic.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

log = logging.getLogger("aa.pipeline")

# Parser versions: bump when the extraction routine changes so stale artifacts
# can be distinguished from fresh ones.
RSC_PARSER_VERSION = "0.2.0"
API_PARSER_VERSION = "0.1.0"
SNAPSHOT_PARSER_VERSION = "0.1.0"


@dataclass
class SourceResult:
    """Envelope returned by every source adapter."""

    source: str                      # e.g. "rsc", "official_api", "snapshot"
    parser_version: str
    fetched_at: str                  # ISO UTC timestamp
    fetched_at_ts: float             # unix epoch for staleness math
    records: list[dict]              # normalized records (common schema)
    raw: Any = None                  # raw payload/snapshot (preserved)
    raw_path: str | None = None      # where raw was persisted, if applicable
    meta: dict = field(default_factory=dict)     # free-form source metadata
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    healthy: bool = False            # whether this fetch is trustworthy


class SourceAdapter(Protocol):
    name: str

    def fetch(self) -> SourceResult:
        """Fetch and normalize. Must not raise for a merely-empty result."""
        ...