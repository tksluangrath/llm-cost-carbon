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

from llm_cost_carbon import ledger, server as server_module
from llm_cost_carbon.adapters import parser
from llm_cost_carbon.adapters.parser import _select_window, parse_claude_daily

MODEL = "llama-3.1-8b"  # models.json: $0.18 / million output tokens


@pytest.fixture(autouse=True)
def _isolated_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "LEDGER_DIR", tmp_path / ".llm-cost-carbon")
    monkeypatch.setattr(ledger, "LEDGER_PATH", tmp_path / ".llm-cost-carbon" / "ledger.jsonl")

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
async def test_estimate_writes_one_ledger_entry():
    async with Client(server_module.mcp) as client:
        await client.call_tool("estimate", {"model": MODEL, "input_tokens": 1000, "output_tokens": 1000})
    entries = json.loads(ledger.export("json"))["entries"]
    assert len(entries) == 1
    assert entries[0]["model"] == MODEL
    assert entries[0]["tool"] == "estimate"
    assert entries[0]["source"] == "estimated"


@pytest.mark.anyio
async def test_compare_writes_one_ledger_entry_regardless_of_model_count():
    """compare() is one logical query even though it touches N models
    internally -- matches the ledger's original pre-cut design ("compare
    writes 1 entry regardless of model count"). Splitting it into N
    entries would make export_ledger's output look like N separate
    actions that never happened, and would inflate ledger_summary()'s
    totals for a single exploratory query."""
    async with Client(server_module.mcp) as client:
        await client.call_tool(
            "compare",
            {"models": ["llama-3.1-8b", "llama-3.1-70b", "llama-3.1-405b"], "input_tokens": 1000, "output_tokens": 1000},
        )
    entries = json.loads(ledger.export("json"))["entries"]
    assert len(entries) == 1
    assert entries[0]["tool"] == "compare"
    assert entries[0]["models_compared"] == ["llama-3.1-8b", "llama-3.1-70b", "llama-3.1-405b"]
    assert entries[0]["model"] is None
    assert entries[0]["usd_cost"] is None  # no real spend occurred


@pytest.mark.anyio
async def test_compare_does_not_inflate_ledger_summary_totals():
    async with Client(server_module.mcp) as client:
        await client.call_tool("estimate", {"model": MODEL, "input_tokens": 1_000_000, "output_tokens": 1_000_000})
        await client.call_tool(
            "compare",
            {"models": ["llama-3.1-8b", "llama-3.1-70b", "llama-3.1-405b"], "input_tokens": 1_000_000, "output_tokens": 1_000_000},
        )
        result = await client.call_tool("ledger_summary", {"scope": "session"})
    assert result.is_error is False
    # 1 estimate() call + 1 compare() call = 2 logical queries...
    assert result.structured_content["call_count"] == 2
    # ...but total_usd reflects only the single estimate() call's real
    # cost -- compare()'s 3 hypothetical model costs are never summed in.
    assert round(result.structured_content["total_usd"], 6) == 0.18


@pytest.mark.anyio
async def test_list_models_does_not_write_a_ledger_entry():
    async with Client(server_module.mcp) as client:
        await client.call_tool("list_models", {})
    assert json.loads(ledger.export("json"))["entries"] == []


@pytest.mark.anyio
async def test_ledger_summary_round_trips_through_mcp_tool():
    async with Client(server_module.mcp) as client:
        await client.call_tool("estimate", {"model": MODEL, "input_tokens": 1_000_000, "output_tokens": 1_000_000})
        result = await client.call_tool("ledger_summary", {"scope": "session"})
    assert result.is_error is False
    assert result.structured_content["call_count"] == 1
    assert round(result.structured_content["total_usd"], 6) == 0.18
    assert result.structured_content["estimated_usd"] == result.structured_content["total_usd"]
    assert result.structured_content["captured_usd"] == 0


@pytest.mark.anyio
async def test_export_ledger_round_trips_through_mcp_tool():
    async with Client(server_module.mcp) as client:
        await client.call_tool("estimate", {"model": MODEL, "input_tokens": 1000, "output_tokens": 1000})
        result = await client.call_tool("export_ledger", {"format": "json"})
    assert result.is_error is False
    # export_ledger returns a plain str, so the SDK wraps it as
    # structured_content = {"result": "<json string>"} (non-object return
    # values can't be structured content directly per the MCP spec).
    parsed = json.loads(result.structured_content["result"])
    assert parsed["truncated"] is False
    assert len(parsed["entries"]) == 1
    assert parsed["entries"][0]["model"] == MODEL


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
    assert "timed out after 60 seconds" in result.structured_content["capture_reason"]


@pytest.mark.anyio
async def test_ambiguous_multi_model_day_degrades_to_estimated_not_a_tool_error(monkeypatch):
    """A real multi-model day for a dict-shaped source (codex/opencode/pi/
    amp) raises AmbiguousCostAttributionError from the parser -- a genuine
    parse-time capture failure, which the design says should degrade to
    the estimated path (like a timeout or bad JSON), not surface as an
    unhandled tool error."""
    ambiguous_day = {
        "daily": [
            {
                "date": "2026-01-05",
                "costUSD": 1.0,
                "models": {
                    "gpt-5.2-codex": {"inputTokens": 1, "outputTokens": 1},
                    "gpt-5.2-codex-mini": {"inputTokens": 1, "outputTokens": 1},
                },
            }
        ]
    }
    monkeypatch.setattr(parser, "fetch_daily", lambda source, version=None, timeout=60: ambiguous_day)

    async with Client(server_module.mcp) as client:
        result = await client.call_tool(
            "estimate",
            {"model": MODEL, "host": "codex", "input_tokens": 10, "output_tokens": 20},
        )
    assert result.is_error is False
    assert result.structured_content["capture_status"] == "unavailable"
    assert "cannot attribute per-model cost" in result.structured_content["capture_reason"]
    assert result.structured_content["source"] == "estimated"


@pytest.mark.anyio
async def test_missing_required_field_degrades_to_estimated_not_a_tool_error(monkeypatch):
    """A malformed/incomplete real response (missing a required field) is
    also a parse-time capture failure per the same rule -- KeyError from
    the parser must degrade, not crash the tool call."""
    malformed_day = {
        "daily": [
            {"date": "2026-01-05", "modelBreakdowns": [{"modelName": "x"}]}  # missing required fields
        ]
    }
    monkeypatch.setattr(parser, "fetch_daily", lambda source, version=None, timeout=60: malformed_day)

    async with Client(server_module.mcp) as client:
        result = await client.call_tool(
            "estimate",
            {"model": MODEL, "host": "claude", "input_tokens": 10, "output_tokens": 20},
        )
    assert result.is_error is False
    assert result.structured_content["capture_status"] == "unavailable"
    assert "inputTokens" in result.structured_content["capture_reason"]
    assert result.structured_content["source"] == "estimated"


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
