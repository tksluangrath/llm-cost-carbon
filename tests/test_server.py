"""Step 4 verify: in-process MCP client round-trips all 3 tools.

Uses `mcp.client.Client`, which connects to an `MCPServer` in-process (no
stdio/subprocess) -- the in-process client boundary claude-plan.md's Testing
Approach calls for, built on this installed mcp version's own testing
helper rather than a hand-rolled transport.
"""
import json
import subprocess
from datetime import date
from pathlib import Path

import pytest
from mcp.client import Client

from llm_cost_carbon import server as server_module
from llm_cost_carbon.adapters import parser
from llm_cost_carbon.adapters.parser import _select_window, parse_claude_daily

MODEL = "llama-3.1-8b"  # models.json: $0.18 / million output tokens

FIXTURES = Path(__file__).parent / "fixtures"
CLAUDE_FIXTURE = json.loads((FIXTURES / "ccusage_claude_daily.json").read_text())


class _FrozenDate(date):
    """Stands in for `_date` in adapters.parser so "today" resolves to the
    fixture's most recent day (2026-07-29) regardless of the real clock --
    `fromisoformat` still works normally since this subclasses `date`."""

    @classmethod
    def today(cls):
        return date(2026, 7, 29)


@pytest.mark.anyio
async def test_list_models_round_trips():
    async with Client(server_module.mcp) as client:
        result = await client.call_tool("list_models", {})
    assert result.is_error is False
    names = {m["model"] for m in result.structured_content["models"]}
    assert MODEL in names


@pytest.mark.anyio
async def test_estimate_matches_hand_computed_example_to_6_decimals():
    async with Client(server_module.mcp) as client:
        result = await client.call_tool(
            "estimate", {"model": MODEL, "input_tokens": 500_000, "output_tokens": 500_000}
        )
    assert result.is_error is False
    # 500,000 output tokens * $0.18 / 1,000,000 = $0.09
    assert round(result.structured_content["usd_cost"], 6) == 0.09
    assert result.structured_content["source"] == "estimated"
    assert result.structured_content["capture_status"] == "not_covered"


@pytest.mark.anyio
async def test_compare_ranks_by_cost():
    async with Client(server_module.mcp) as client:
        result = await client.call_tool(
            "compare",
            {"models": ["llama-3.1-405b", "llama-3.1-8b"], "input_tokens": 1_000_000, "output_tokens": 1_000_000},
        )
    assert result.is_error is False
    ranked = [r["model"] for r in result.structured_content["results"]]
    assert ranked == ["llama-3.1-8b", "llama-3.1-405b"]


@pytest.mark.anyio
async def test_capture_failure_returns_valid_result_not_an_exception(monkeypatch):
    def raise_timeout(source, version=None, timeout=60):
        raise subprocess.TimeoutExpired(cmd=["npx", "ccusage"], timeout=60)

    monkeypatch.setattr("llm_cost_carbon.adapters.parser.fetch_daily", raise_timeout)

    async with Client(server_module.mcp) as client:
        result = await client.call_tool(
            "estimate",
            {"model": MODEL, "input_tokens": 10, "output_tokens": 20, "host": "claude"},
        )
    assert result.is_error is False
    assert result.structured_content["capture_status"] == "unavailable"
    assert result.structured_content["capture_reason"] is not None


@pytest.mark.anyio
async def test_unknown_model_becomes_tool_error_not_a_crash():
    async with Client(server_module.mcp) as client:
        result = await client.call_tool(
            "estimate", {"model": "not-a-real-model", "input_tokens": 1, "output_tokens": 1}
        )
    assert result.is_error is True


@pytest.fixture
def anyio_backend():
    return "asyncio"


# --- Step 4b: _select_window() window filtering ---
#
# claude-sonnet-5 (the fixture's real multi-day model) isn't in
# models.json's pricing table -- that's models.json's own pre-existing,
# flagged-out-of-scope gap (see claude-plan.md's "open finding"), not
# something this step touches. reconcile() raises ModelNotFoundError for
# any model it doesn't price, so conditions 1-3 (which need claude-sonnet-5's
# real multi-day numbers) exercise _select_window() directly rather than the
# full estimate() tool. Condition 4 (zero-match handling) and condition 5
# (window validation) don't need a priced Claude model, so those go through
# the real estimate() tool end to end.


def test_window_today_selects_most_recent_day(monkeypatch):
    monkeypatch.setattr(parser, "_date", _FrozenDate)
    records = parse_claude_daily(CLAUDE_FIXTURE)
    result = _select_window(records, "claude-sonnet-5", "claude", "today")
    assert round(result.usd_cost, 6) == 20.798729


def test_window_explicit_date_selects_that_day_not_today(monkeypatch):
    monkeypatch.setattr(parser, "_date", _FrozenDate)
    records = parse_claude_daily(CLAUDE_FIXTURE)
    result = _select_window(records, "claude-sonnet-5", "claude", "2026-07-09")
    assert round(result.usd_cost, 6) == 10.543412


def test_window_all_sums_every_matching_day():
    records = parse_claude_daily(CLAUDE_FIXTURE)
    result = _select_window(records, "claude-sonnet-5", "claude", "all")
    assert round(result.usd_cost, 6) == round(214.11233100000004, 6)


@pytest.mark.anyio
async def test_zero_matching_rows_is_captured_zero_cost_not_estimated(monkeypatch):
    monkeypatch.setattr(parser, "_date", _FrozenDate)
    monkeypatch.setattr(parser, "fetch_daily", lambda source, version=None, timeout=60: CLAUDE_FIXTURE)

    async with Client(server_module.mcp) as client:
        result = await client.call_tool(
            "estimate", {"model": MODEL, "host": "claude", "window": "today"}
        )
    assert result.is_error is False
    assert result.structured_content["usd_cost"] == 0.0
    assert result.structured_content["capture_status"] == "captured"
    assert result.structured_content["source"] == "captured"


@pytest.mark.anyio
async def test_invalid_window_raises_before_any_subprocess_call(monkeypatch):
    def fail_if_called(*a, **k):
        raise AssertionError("fetch_daily must not be called for an invalid window")

    monkeypatch.setattr(parser, "fetch_daily", fail_if_called)

    async with Client(server_module.mcp) as client:
        result = await client.call_tool(
            "estimate",
            {"model": MODEL, "host": "claude", "window": "yesterday", "input_tokens": 1, "output_tokens": 1},
        )
    assert result.is_error is True
