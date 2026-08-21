#!/usr/bin/env python3.12
"""Demonstrate and verify the query layer against the merged dataset."""
import sys
from pathlib import Path
if sys.path and Path(sys.path[0]).resolve() == Path(__file__).resolve().parent:
    sys.path.pop(0)  # avoid aa/http.py shadowing stdlib http when run as a script
sys.path.insert(0, 'scripts')
from aa.query import AADB

db = AADB('data/aa_models_v2.json')
print("Loaded", len(db.models), "models | generated", db.generated_at)

print("\nBest coding models:")
for v, m in db.best_coding(5):
    print("  %7.2f  %-38s %s" % (v, m['name'][:38], m['creator']))

print("\nBest agentic models:")
for v, m in db.best_agentic(5):
    print("  %7.2f  %-38s %s" % (v, m['name'][:38], m['creator']))

print("\nBest value (IQ/$ blended 3:1):")
for ratio, m, iq, cost in db.value_intelligence_per_dollar(5):
    print("  %8.1f IQ/$ | IQ %6.2f | $%s/1M | %s" % (ratio, iq, cost, m['name'][:40]))

print("\nBest value (IQ/$ per AA eval task):")
for ratio, m, iq, cost in db.value_intelligence_per_task(5):
    print("  %8.1f IQ/$ | IQ %6.2f | $%s/task | %s" % (ratio, iq, cost, m['name'][:40]))

print("\nBest speed (tokens/s):")
for sp, m in db.fastest(5):
    print("  %8.1f tps  %s" % (sp, m['name'][:40]))

print("\nCheapest 1M in/out:")
for inp, m, i, o in db.cheapest_1m(blind=True, limit=5):
    print("  $%s/$%s  %s" % (i, o, m['name'][:40]))

print("\nBackup candidates within 5 IQ of best:")
for v, m in db.backup_candidates(require_open_weights=False, gap=5.0, limit=6):
    print("  %7.2f  %-38s %s" % (v, m['name'][:38], m['creator']))