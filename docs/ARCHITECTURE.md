# Architecture

`public/` is the complete static deployment. `data/aa_models_v2.json` is the private rich canonical-model dataset; `scripts/build_site_from_aa.py` derives the public JSON artifacts. The AA RSC leaderboard is the primary rich source, the AA Free API supplies baseline identity/validation when configured, and the Oolong snapshot is a fallback/cross-check.

Provider operations, Endpoint Accuracy, and coding-agent results are separate observation domains. OpenRouter is authoritative only for its endpoint availability, price, performance, and capability observations. Artificial Analysis is authoritative for its model benchmarks and Endpoint Accuracy measurements. Coding-agent observations describe a harness/model/configuration variant and do not become base-model facts.

Cross-source joins pass through versioned identity artifacts. Candidate, ambiguous, unresolved, and conflicting relationships are diagnostic only. Recommendation code consumes only verified or audited manual mappings. Provider identity includes the endpoint variant when variants can carry different accuracy evidence; source-specific observations never overwrite unrelated canonical facts.

JSON remains the storage and interchange format while current scale permits deterministic review and replay. Generated artifacts must have a documented command, deterministic fixtures, internally consistent counts/metadata, and fail-closed acquisition behavior. Missing values remain unknown. Confidence/evidence strength is reported separately from ranking.
