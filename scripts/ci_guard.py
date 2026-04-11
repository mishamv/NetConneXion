"""CI Guard -- quick repository context check.

Run as the first CI/pre-commit step to catch:
  - wrong clone / branch / path
  - critical lint errors (F, E4, E7 -- no E501)
  - failing tests in tests/

Usage:
    python scripts/ci_guard.py              # full check
    python scripts/ci_guard.py --lint-only  # lint only
    python scripts/ci_guard.py --ctx-only   # context only
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXPECTED_PACKAGE = "quickip"
PYTHON = sys.executable


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT, **kwargs)


def _section(title: str) -> None:
    print(f"\n-- {title} {'-' * (50 - len(title))}")


def check_context() -> list[str]:
    errors: list[str] = []

    if not (REPO_ROOT / EXPECTED_PACKAGE).is_dir():
        errors.append(f"Package '{EXPECTED_PACKAGE}/' not found in {REPO_ROOT}")

    r = _run(["git", "rev-parse", "--show-toplevel"])
    if r.returncode != 0:
        errors.append("Not inside a git repository")
    else:
        toplevel = Path(r.stdout.strip())
        if toplevel != REPO_ROOT:
            errors.append(f"Git root mismatch: expected {REPO_ROOT}, got {toplevel}")

    sha = _run(["git", "rev-parse", "--short", "HEAD"]).stdout.strip() or "unknown"
    branch = _run(["git", "branch", "--show-current"]).stdout.strip() or "unknown"

    print(f"  repo   : {REPO_ROOT}")
    print(f"  branch : {branch}")
    print(f"  commit : {sha}")
    return errors


def check_lint() -> list[str]:
    errors: list[str] = []
    r = _run([
        PYTHON, "-m", "ruff", "check", EXPECTED_PACKAGE,
        "--select", "F,E4,E7",
        "--output-format=concise",
    ])
    if r.returncode != 0:
        errors.append("Lint errors found:\n" + r.stdout.strip())
    else:
        print("  lint   : OK (0 critical errors)")
    return errors


def check_tests() -> list[str]:
    errors: list[str] = []
    tests_dir = REPO_ROOT / "tests"
    if not tests_dir.exists():
        print("  tests  : skipped (no tests/ directory)")
        return errors

    r = _run([PYTHON, "-m", "pytest", "tests/", "-q", "--tb=short"])
    if r.returncode != 0:
        out = (r.stdout + r.stderr).strip()
        errors.append("Tests failed:\n" + out)
    else:
        summary = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "passed"
        print(f"  tests  : {summary}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="NetConneXion CI guard")
    parser.add_argument("--lint-only", action="store_true")
    parser.add_argument("--ctx-only", action="store_true")
    args = parser.parse_args()

    all_errors: list[str] = []

    _section("Context")
    if not args.lint_only:
        all_errors.extend(check_context())

    _section("Lint")
    if not args.ctx_only:
        all_errors.extend(check_lint())

    if not args.lint_only and not args.ctx_only:
        _section("Tests")
        all_errors.extend(check_tests())

    if all_errors:
        _section("FAILED")
        for err in all_errors:
            print(f"  FAIL: {err}")
        return 1

    print("\n-- All checks passed " + "-" * 31)
    return 0


if __name__ == "__main__":
    sys.exit(main())
