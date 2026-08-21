---
noteId: "66a42bb08c3011f1918a15090ec10702"
tags: []

---

# llm-cost-carbon

An MCP (Model Context Protocol) server that answers one question about LLM
inference: "what did this cost in dollars" — reconciling real, captured
usage (via the `ccusage` CLI) with manual token-count estimates, in one
place. It ships as an MCP tool layer only: a local Python process, stdio
transport, no proxy, no daemon, no paid APIs, no cloud infrastructure. An
agent (e.g. Claude Code) calls tools (`list_models`, `estimate`, `compare`,
`ledger_summary`, `export_ledger`) on demand.

v1 scope is cost-only — no carbon/energy modeling. See "Why this is
cost-only" below.

## Setup

```bash
uv sync
```

Requires Python 3.11+ and `npx` on PATH (`ccusage` runs via `npx`, pinned to
a specific version in `src/llm_cost_carbon/calc/constants.py`) — `npx` is
only invoked when `estimate()` is called with a `host`; a plain token-count
estimate needs neither `npx` nor a network connection.

Quick check that it's working, no Claude Code required:

```bash
uv run python -c "
from llm_cost_carbon.server import estimate
print(estimate(model='llama-3.1-8b', input_tokens=1000, output_tokens=1000))
"
```

To use it from Claude Code, register it as an MCP server:

```bash
claude mcp add llm-cost-carbon -e PYTHONPATH=/path/to/llm-cost-carbon/src -- /path/to/llm-cost-carbon/.venv/bin/python3 -m llm_cost_carbon.server
```

Replace `/path/to/llm-cost-carbon` with the absolute path to your clone
(`pwd` from the repo root gives it to you). This form runs the venv's
Python directly instead of going through `uv run`. `uv run` depends on an
editable-install `.pth` file that `uv` writes as a hidden file on macOS,
and Python 3.13's `site.py` skips hidden `.pth` files, so `uv run python -m
llm_cost_carbon.server` fails with "Connection closed" when Claude Code
tries to start it.

If you're using Claude Code, `.claude/skills/llm-cost/SKILL.md` ships a
`/llm-cost` skill that calls these tools directly in chat instead of
answering pricing/spend questions from memory.

## Test

```bash
uv run pytest
```

CI (`.github/workflows/tests.yml`) runs the same suite via `uv` on every
push and PR to `main`.

## Project layout

- `src/llm_cost_carbon/adapters/` — normalizes ccusage output into usage records
- `src/llm_cost_carbon/calc/` — pricing constants and cost calculations
- `src/llm_cost_carbon/data/` — model pricing data
- `src/llm_cost_carbon/ledger.py` — local append-only spend ledger (`~/.llm-cost-carbon/ledger.jsonl`)
- `scripts/smoke_ccusage.py` — live smoke check against the real ccusage binary
- `scripts/compare_test.sh` — live end-to-end check: drives a real `claude -p` session against all 5 MCP tools
- `planning/` — design docs and revision history

## ccusage attribution

Real usage capture delegates entirely to
[ccusage](https://github.com/ccusage/ccusage) (MIT license), which parses
local session logs for supported hosts (Claude Code, Codex, OpenCode,
pi-agent, Amp) and exposes `--json` output. This project normalizes that
output into one schema; it doesn't reimplement usage capture.

## Data handling

- **Read locally:** only local `ccusage` session log files, via the pinned
  `ccusage` CLI — nothing else on disk is read.
- **Write locally:** every `estimate()`/`compare()` call appends one line
  to a local ledger at `~/.llm-cost-carbon/ledger.jsonl` (directory `0700`,
  file `0600`) — model, cost, source, and timestamp only, nothing else.
  This is what `ledger_summary`/`export_ledger` read back. Delete it
  anytime with `rm -rf ~/.llm-cost-carbon/`; nothing depends on it existing.
- **Network:** `npx ccusage@<pinned version>` performs an npm registry
  lookup on each invocation — a real network call, made only when
  `estimate()` is called with a `host` argument. Token-count-only estimates
  make no network call at all. The ledger is local-only; nothing about it
  ever goes over the network.
- **Telemetry:** none. This project sends nothing anywhere.

## Why this is cost-only, not cost-and-carbon

The original scope included carbon/energy modeling: FLOP-based Wh/gCO2
estimates layered on top of cost. It's cut from v1. A physically grounded
carbon model needs public parameter counts, and the models people
actually ask about cost for, closed ones like Claude and GPT, don't
publish those. A carbon number built on a guessed parameter count would
be worse than no carbon number at all, so it stays out until that
changes.
