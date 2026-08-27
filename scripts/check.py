#!/usr/bin/env python3
"""Bounded, dependency-free validation entrypoint for local work and CI."""
from __future__ import annotations

import argparse
import ast
import os
from pathlib import Path
import subprocess
import sys
import tempfile


REPO = Path(__file__).resolve().parent.parent
MAX_FAILURE_OUTPUT = 12000
PYTHON = sys.executable


class CheckFailure(RuntimeError):
    pass


def _trim_output(output: str) -> str:
    output = output.strip()
    if len(output) <= MAX_FAILURE_OUTPUT:
        return output
    head = MAX_FAILURE_OUTPUT // 2
    tail = MAX_FAILURE_OUTPUT - head
    return output[:head] + "\n... output truncated ...\n" + output[-tail:]


def _run(label, command, *, verbose=False, env=None):
    result = subprocess.run(
        command,
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        errors="replace",
    )
    if result.returncode:
        details = "\n".join(part for part in (result.stdout, result.stderr) if part.strip())
        raise CheckFailure(
            f"{label} failed with exit code {result.returncode}\n{_trim_output(details)}"
        )
    if verbose:
        details = "\n".join(part for part in (result.stdout, result.stderr) if part.strip())
        if details:
            print(details)
    print(f"[check] PASS {label}")
    return result


def _environment():
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _python(*parts):
    return [PYTHON, *map(str, parts)]


def _node(*parts):
    return ["node", *map(str, parts)]


def _script(path, *parts):
    return _python(REPO / path, *parts)


def _syntax_check(*, verbose=False):
    for path in sorted((REPO / "scripts").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError) as exc:
            raise CheckFailure(f"Python syntax check failed for {path}: {exc}") from exc
    print("[check] PASS Python syntax")


def _node_version(*, verbose=False):
    result = _run("Node.js version", _node("--version"), verbose=verbose)
    version = result.stdout.strip().removeprefix("v")
    try:
        major = int(version.split(".", 1)[0])
    except (ValueError, IndexError) as exc:
        raise CheckFailure(f"Could not parse Node.js version: {version!r}") from exc
    if major < 20:
        raise CheckFailure(f"Node.js 20+ required; found {version}")


def _git_paths(command):
    result = subprocess.run(command, cwd=REPO, capture_output=True, text=True, errors="replace")
    if result.returncode:
        return None
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def changed_paths():
    """Return local changes, then the current commit's changes in CI."""
    status = _git_paths(["git", "status", "--porcelain=v1"])
    if status is None:
        return None
    paths = set()
    for line in status:
        if len(line) >= 4:
            path = line[3:]
            if " -> " in path:
                path = path.rsplit(" -> ", 1)[-1]
            paths.add(path)
    if paths:
        return paths
    staged = _git_paths(["git", "diff", "--cached", "--name-only"])
    unstaged = _git_paths(["git", "diff", "--name-only"])
    paths.update(staged or set())
    paths.update(unstaged or set())
    if paths:
        return paths
    return _git_paths(["git", "diff", "--name-only", "HEAD^", "HEAD"])


def auto_scope(paths):
    if not paths:
        return "all"
    documentation = {
        "README.md", "CONTRIBUTING.md", "SECURITY.md", "LICENSE",
    }
    if all(path.startswith("docs/") or path in documentation for path in paths):
        return "quick"
    if all(path.startswith("public/") and not path.startswith("public/data/")
           for path in paths):
        return "site"
    return "all"


def run_quick(*, verbose=False, env=None):
    _run("site validation", _script("scripts/validate_site.py"), verbose=verbose, env=env)
    for asset in ("nav.js", "models.js", "theme-init.js"):
        _run(f"JavaScript syntax ({asset})", _node("--check", REPO / "public/assets" / asset),
             verbose=verbose, env=env)
    _run("browser security", _node("scripts/test_browser_security.mjs"),
         verbose=verbose, env=env)


def run_site(*, verbose=False, env=None):
    _run("public build contract", _script("scripts/test_public_build.py"),
         verbose=verbose, env=env)
    run_quick(verbose=verbose, env=env)


def run_legacy(*, verbose=False, env=None):
    _run("legacy adapter compatibility", _script("scripts/test_fetch_aa_models.py"),
         verbose=verbose, env=env)


def run_cache(*, verbose=False, env=None):
    _run("cache pruning", _script("scripts/test_prune_aa_cache.py"),
         verbose=verbose, env=env)


def run_pipeline(*, verbose=False, env=None):
    _run("pipeline tests", _script("scripts/aa/tests/test_pipeline.py"),
         verbose=verbose, env=env)


def run_decision(*, verbose=False, env=None):
    _run("decision tests", _script("scripts/aa/tests/test_decision_engine.py"),
         verbose=verbose, env=env)


def run_history(*, verbose=False, env=None):
    _run("history tests", _script("scripts/aa/tests/test_history.py"),
         verbose=verbose, env=env)


def run_observations(*, verbose=False, env=None):
    _run("observation tests", _script("scripts/aa/tests/test_observations.py"),
         verbose=verbose, env=env)
    _run("phase-3 observation tests", _script("scripts/aa/tests/test_phase3_observations.py"),
         verbose=verbose, env=env)


def run_identity(*, verbose=False, env=None):
    _run("identity contract tests", _script("scripts/aa/tests/test_identity_contracts.py"),
         verbose=verbose, env=env)


def run_cli(*, verbose=False, env=None):
    _run("check-runner tests", _script("scripts/test_check.py"),
         verbose=verbose, env=env)
    _run("CLI tests", _script("scripts/test_model_compass.py"),
         verbose=verbose, env=env)


def run_phase3_replay(*, verbose=False, env=None):
    with tempfile.TemporaryDirectory(prefix="model-compass-check-") as directory:
        output_dir = Path(directory)
        identity_output = output_dir / "identity_mappings.json"
        summary_output = output_dir / "phase3_summary.json"
        _run(
            "phase-3 deterministic replay",
            _python("-m", "scripts.aa.phase3_artifacts",
                    "--identity-output", identity_output,
                    "--summary-output", summary_output),
            verbose=verbose,
            env=env,
        )
        for generated, checked_in in (
            (identity_output, REPO / "data/identity_mappings.json"),
            (summary_output, REPO / "data/phase3_summary.json"),
        ):
            if generated.read_bytes() != checked_in.read_bytes():
                raise CheckFailure(f"phase-3 replay differs from {checked_in.relative_to(REPO)}")
    print("[check] PASS phase-3 artifact comparison")


def run_all(*, verbose=False, env=None):
    _syntax_check(verbose=verbose)
    _node_version(verbose=verbose)
    run_cli(verbose=verbose, env=env)
    run_legacy(verbose=verbose, env=env)
    run_cache(verbose=verbose, env=env)
    run_site(verbose=verbose, env=env)
    run_pipeline(verbose=verbose, env=env)
    run_decision(verbose=verbose, env=env)
    run_history(verbose=verbose, env=env)
    run_observations(verbose=verbose, env=env)
    run_identity(verbose=verbose, env=env)
    run_phase3_replay(verbose=verbose, env=env)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run bounded Model Compass validation")
    parser.add_argument("--scope", choices=(
        "auto", "quick", "site", "legacy", "cache", "pipeline", "decision",
        "history", "observations", "identity", "all",
    ), default="auto")
    parser.add_argument("--verbose", action="store_true",
                        help="show successful command output")
    args = parser.parse_args(argv)
    scope = args.scope
    if scope == "auto":
        scope = auto_scope(changed_paths())
        print(f"[check] auto scope: {scope}")
    env = _environment()
    try:
        if scope == "quick":
            run_quick(verbose=args.verbose, env=env)
        elif scope == "site":
            run_site(verbose=args.verbose, env=env)
        elif scope == "legacy":
            run_legacy(verbose=args.verbose, env=env)
        elif scope == "cache":
            run_cache(verbose=args.verbose, env=env)
        elif scope == "pipeline":
            run_pipeline(verbose=args.verbose, env=env)
        elif scope == "decision":
            run_decision(verbose=args.verbose, env=env)
        elif scope == "history":
            run_history(verbose=args.verbose, env=env)
        elif scope == "observations":
            run_observations(verbose=args.verbose, env=env)
        elif scope == "identity":
            run_identity(verbose=args.verbose, env=env)
        else:
            run_all(verbose=args.verbose, env=env)
    except CheckFailure as exc:
        print(f"[check] FAIL {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
