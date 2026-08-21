"""MCP server (cost-only v1): registers list_models, estimate, compare.

Built against `mcp==2.0.0`'s installed API, which renamed the plan's
"FastMCP" to `mcp.server.mcpserver.MCPServer` -- same role (function ->
tool registration, pydantic-validated request/response at the wire
boundary), different class name. Flagged in the Step 3/4 status report.
"""
import json
from dataclasses import dataclass
from datetime import date
from subprocess import CalledProcessError, TimeoutExpired

from mcp.server.mcpserver import MCPServer

from llm_cost_carbon.adapters import parser
from llm_cost_carbon.adapters.parser import (
    _select_window,
    parse_amp_daily,
    parse_claude_daily,
    parse_codex_daily,
    parse_opencode_daily,
    parse_pi_daily,
)
from llm_cost_carbon.calc.reconcile import MODELS, ReconciledResult, reconcile

KNOWN_CCUSAGE_SOURCES = ("claude", "codex", "opencode", "pi", "amp")
PARSERS = {
    "claude": parse_claude_daily,
    "codex": parse_codex_daily,
    "opencode": parse_opencode_daily,
    "pi": parse_pi_daily,
    "amp": parse_amp_daily,
}

mcp = MCPServer("llm-cost-carbon")


@dataclass
class ModelRow:
    model: str
    usd_price_per_million_output_tokens: float
    price_source: str
    last_verified: str


@dataclass
class ModelTable:
    models: list[ModelRow]


@dataclass
class EstimateResult:
    model: str
    usd_cost: float
    source: str             # "captured" | "estimated"
    capture_status: str
    capture_reason: str | None
    citations: list[str]
    last_verified: str
    stale: bool


@dataclass
class ComparisonTable:
    results: list[EstimateResult]


def _to_estimate_result(result: ReconciledResult) -> EstimateResult:
    return EstimateResult(
        model=result.model,
        usd_cost=result.usd_cost,
        source=result.source,
        capture_status=result.capture_status,
        capture_reason=result.capture_reason,
        citations=result.citations,
        last_verified=MODELS[result.model]["last_verified"],
        stale=result.stale,
    )


@mcp.tool()
def list_models() -> ModelTable:
    """Table of covered models: pricing, source, and freshness. No energy/carbon columns."""
    return ModelTable(models=[
        ModelRow(
            model=row["model"],
            usd_price_per_million_output_tokens=row["usd_price_per_million_output_tokens"],
            price_source=row["price_source"],
            last_verified=row["last_verified"],
        )
        for row in MODELS.values()
    ])


@mcp.tool()
def estimate(
    model: str,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    host: str | None = None,
    window: str = "today",
) -> EstimateResult:
    """$ cost, tagged 'captured' (real ccusage usage) or 'estimated' (manual tokens)."""
    if window not in ("today", "all"):
        try:
            date.fromisoformat(window)
        except ValueError:
            raise ValueError(f"invalid window: {window!r}")

    capture_reason = None
    if host is None or host not in KNOWN_CCUSAGE_SOURCES:  # whitelist before fetch_daily()
        capture_status, usage = "not_covered", None
    else:
        try:
            data = parser.fetch_daily(host)
            records = PARSERS[host](data)
            usage = _select_window(records, model, host, window)
            capture_status = "captured"  # zero matching rows -> captured, usd_cost 0, not an error
        except (TimeoutExpired, json.JSONDecodeError, CalledProcessError, KeyError, ValueError) as e:
            usage, capture_status, capture_reason = None, "unavailable", str(e)

    if capture_status != "captured" and (input_tokens is None or output_tokens is None):
        raise ValueError("input_tokens/output_tokens required when capture unavailable")

    result = reconcile(usage, model, input_tokens, output_tokens, capture_status, capture_reason)
    return _to_estimate_result(result)


@mcp.tool()
def compare(models: list[str], input_tokens: int, output_tokens: int) -> ComparisonTable:
    """Ranked $ cost table across models, always 'estimated' mode."""
    results = [
        _to_estimate_result(reconcile(None, m, input_tokens, output_tokens, "not_covered", None))
        for m in models
    ]
    results.sort(key=lambda r: r.usd_cost)
    return ComparisonTable(results=results)


if __name__ == "__main__":
    mcp.run()
