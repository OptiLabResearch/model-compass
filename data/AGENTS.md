# Data scope

`data/` contains committed generated/private artifacts. Read metadata,
coverage, or bounded records first; do not dump complete datasets into agent
context. `data/aa_cache/` is ignored raw acquisition data for targeted parser
debugging only, not a normal orientation input.

Treat generated files as outputs of the documented pipeline. Preserve source
authority, unknown metrics, identity ambiguity, and provider variants. Never
read, print, or expose `.env` or credential values. Use temporary output paths
for replay checks and regenerate committed artifacts only for an authorized
refresh.
