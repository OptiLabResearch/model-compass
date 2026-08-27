"""Small dependency-free selector for the script-style test modules."""
from __future__ import annotations

import argparse


def run_tests(namespace, title):
    parser = argparse.ArgumentParser(description=f"Run {title.lower()}")
    parser.add_argument("--test", action="append", dest="selected",
                        help="run one named test; repeat for multiple tests")
    parser.add_argument("--list", action="store_true",
                        help="list available test names and exit")
    args = parser.parse_args()
    tests = {
        name: function for name, function in namespace.items()
        if name.startswith("test_") and callable(function)
    }
    if args.list:
        for name in sorted(tests):
            print(name)
        return
    selected = set(args.selected or tests)
    unknown = sorted(selected - tests.keys())
    if unknown:
        parser.error("unknown test(s): " + ", ".join(unknown))
    for name in sorted(tests):
        if name in selected:
            tests[name]()
            print(f"PASS {name}")
    print(title)
