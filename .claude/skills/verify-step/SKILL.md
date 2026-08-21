---
name: verify-step
description: Research -> Test(red) -> Implement(green) -> Review -> Sign-off workflow for a llm-cost-carbon build-order step, per planning/claude-plan.md.
---

# verify-step

The workflow this project has hand-run across Steps 3, 4, 4b, and 5 of
`planning/claude-plan.md`'s build order. It caught a real bug once (Step
4b: `estimate()`'s `window` param was specified but never implemented,
silently returning the wrong day's cost — the Test phase's fixture-based
check is what surfaced it). Use this for any future step in this
project's build order, or any similarly-scoped change to a shipped part
of the codebase.

## Phase 1 — Research

Read the relevant section of `planning/claude-plan.md` (the step's own
entry, plus any "Corrections" section covering it) and the current state
of the file(s) it touches. State explicitly: does the plan's assumption
still match what's actually in the codebase? (`FastMCP` not existing in
the installed `mcp` package is the standing example of why this matters —
check before building on an assumption, don't inherit it.)

**Exit criterion:** any mismatch between the plan and reality is named
before Phase 2 starts, not discovered mid-implementation.

## Phase 2 — Test (red)

Write the test(s) for the step's stated verify condition(s) *before* the
implementation exists.

**Exit criterion:** run the new test(s) against the pre-implementation
code and confirm they fail for the *expected* reason — an `ImportError`
or `AttributeError` on the not-yet-written function, not a typo in the
test itself. A test that already passes before implementation exists is
invalid and must be rewritten.

## Phase 3 — Implement (green)

Write the minimum code to pass Phase 2's test(s).

**Exit criterion:** the full suite passes (`uv run pytest -q` — this
repo's `.claude/settings.json` PostToolUse hook already runs this
automatically after any edit to `src/**/*.py` or `tests/**/*.py`, so this
step is often already done by the time you check).

## Phase 4 — Review

Check the implementation against the step's stated verify condition(s)
and against `claude-plan.md`'s anti-overengineering constraints (no new
dependencies, no speculative abstractions, minimum code that satisfies the
verify condition).

**Exit criterion:** one pass/fail line per verify condition. Any fail
returns to Phase 3, not forward to Phase 5.

## Phase 5 — Sign-off

Trace every new/changed line to `claude-plan.md`'s Build Order, an
appended design section, or a stated verify condition.

**Exit criterion:** anything that doesn't trace to one of those three
sources is cut or named explicitly to the user — never silently kept.
