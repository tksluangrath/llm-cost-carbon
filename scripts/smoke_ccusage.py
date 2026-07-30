#!/usr/bin/env python3
"""Step 1 verify: runs the pinned ccusage binary with --json against each
tested source subcommand and asserts the output parses as JSON with the
expected top-level keys. Zero rows for a source is a pass (no local usage
history for that host) -- the bar is valid shape, not non-empty data.

ponytail: no test framework here on purpose -- this is the actual smoke
check the plan's Step 1 verify condition names, run standalone against a
live subprocess. Shape assertions on captured fixtures live in
tests/test_models_data.py and (Step 2) tests/test_ccusage_adapter.py.
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from llm_cost_carbon.calc.constants import CCUSAGE_VERSION  # noqa: E402

SOURCES = ["claude", "codex", "opencode", "pi", "amp"]
EXPECTED_TOP_LEVEL_KEYS = {"daily", "totals"}


def check_source(source: str) -> None:
    result = subprocess.run(
        ["npx", "--yes", f"ccusage@{CCUSAGE_VERSION}", source, "daily", "--json"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise SystemExit(f"{source}: ccusage exited {result.returncode}: {result.stderr}")
    data = json.loads(result.stdout)
    missing = EXPECTED_TOP_LEVEL_KEYS - data.keys()
    if missing:
        raise SystemExit(f"{source}: missing expected top-level keys {missing}, got {list(data.keys())}")
    print(f"{source}: OK ({len(data.get('daily') or [])} day rows)")


def main() -> None:
    for source in SOURCES:
        check_source(source)
    print(f"All {len(SOURCES)} sources OK against ccusage@{CCUSAGE_VERSION}.")


if __name__ == "__main__":
    main()
