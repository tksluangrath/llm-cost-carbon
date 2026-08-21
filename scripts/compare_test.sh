#!/usr/bin/env bash
# Live end-to-end check: asks a fresh Claude Code session to actually use the
# llm-cost-carbon MCP tools (list_models/estimate/compare/ledger_summary/
# export_ledger), not just run pytest. Requires the server already
# registered via `claude mcp add` (see README.md's install section).
#
# ponytail: one prompt, one tool-allowlist, no framework -- this mirrors the
# exact `claude -p` invocations used by hand throughout Step 5 and later
# live checks; add more prompts here if this needs to cover more than one
# scenario later.
set -euo pipefail

PROMPT="${1:-Using the llm-cost-carbon MCP server: compare the cost per 1,000 output tokens for llama-3.1-8b, llama-3.1-70b, and llama-3.1-405b, then call ledger_summary with scope=session and export_ledger with format=json, and report what each returned.}"

claude -p "$PROMPT" \
  --allowedTools "mcp__llm-cost-carbon__compare mcp__llm-cost-carbon__list_models mcp__llm-cost-carbon__estimate mcp__llm-cost-carbon__ledger_summary mcp__llm-cost-carbon__export_ledger"
