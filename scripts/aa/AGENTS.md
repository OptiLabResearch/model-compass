# Artificial Analysis pipeline scope

The RSC-rich pipeline in this directory is active; `../fetch_aa_models.py` is
legacy compatibility code. Read `scripts/aa/README.md`, the relevant adapter,
and its focused tests before changing acquisition or normalization behavior.

Prefer offline fixtures, checked-in artifacts, and targeted test selectors.
Live acquisition can use credentials, network calls, caches, and generated
outputs; run it only when explicitly required and never print credentials or
raw payloads. Preserve fail-visible source drift, atomic writes, provenance,
identity authority, and unknown metrics.
