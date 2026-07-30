---
noteId: "66a42bb08c3011f1918a15090ec10702"
tags: []

---

# llm-cost-carbon

An MCP server for reconciling real LLM inference cost, using
[ccusage](https://github.com/ryoppippi/ccusage) to read local usage logs
from Claude Code, Codex, OpenCode, Amp, and other CLI tools.

v1 scope is cost-only — no carbon/energy modeling (see `planning/` for the
history behind that cut).

## Setup

```bash
uv sync
```

Requires Python 3.11+ and `npx` on PATH (ccusage runs via `npx`, pinned to a
specific version in `src/llm_cost_carbon/calc/constants.py`).

## Test

```bash
uv run pytest
```

## Project layout

- `src/llm_cost_carbon/adapters/` — normalizes ccusage output into usage records
- `src/llm_cost_carbon/calc/` — pricing constants and cost calculations
- `src/llm_cost_carbon/data/` — model pricing data
- `scripts/smoke_ccusage.py` — live smoke check against the real ccusage binary
- `planning/` — design docs and revision history
