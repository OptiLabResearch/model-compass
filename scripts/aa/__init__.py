""".. package for the Artificial Analysis data pipeline.

This package replaces the monolithic single-script fetch in
``scripts/fetch_aa_models.py`` with a multi-source, adapter-based design:

    sources  (rsc, official api, third-party snapshot)
        |   each produces a :class:`SourceResult` (raw + normalized records)
        v
    orchestrate.py   merges, dedups, validates, writes outputs

Every source emits a common envelope so the extraction mechanism is swappable
(see ``source_base.py``). The goal is a reliable, private, local dataset for
model-selection decisions, robust to Artificial Analysis changing its site.
"""

__version__ = "0.1.0"