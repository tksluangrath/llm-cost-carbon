---
name: llm-cost
description: Answer an LLM cost/pricing or cumulative-spend question using the llm-cost-carbon MCP server's tools (list_models, estimate, compare, ledger_summary, export_ledger) directly in this chat, not from memory.
---

# llm-cost

Answer the user's cost question by calling the llm-cost-carbon MCP
server's tools -- `list_models`, `estimate`, `compare`, `ledger_summary`,
`export_ledger` -- directly in this chat. Never answer a cost/pricing
question from memory or by reading `data/models.json` yourself when this
server is available; always call the tool, so the answer reflects what
the server actually has loaded.

For "how much have I spent" / cumulative-spend questions, use
`ledger_summary(scope="session"|"project")` rather than adding up
individual `estimate()`/`compare()` results yourself -- every
`estimate()`/`compare()` call already writes to the local ledger, so the
summary tool has the real running total. Use `export_ledger` when the
user wants the raw entries (e.g. for auditing or a CSV), not just totals.

If a call fails with a "ModelNotFoundError"-shaped error for a model you'd
expect to be priced, or `list_models()` is missing entries you know were
added recently (check `data/models.json` on disk if unsure), this
session's server connection is stale -- it loads the pricing table once
at process start, so edits since then aren't visible until the connection
restarts. Say so plainly and tell the user to run `/mcp` to reconnect,
rather than silently falling back to a guessed price or answering from
memory.
