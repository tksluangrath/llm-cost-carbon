"""Normalizes each pinned ccusage source's `daily --json` output into a
list of UsageRecord, one per (date, model) pair -- a day's aggregate
fields (totalCost, top-level inputTokens) are never parsed into a record,
since they sum across models and don't belong to any single one.
"""
import json
import subprocess
from dataclasses import dataclass
from datetime import date as _date, timedelta
from functools import partial

from llm_cost_carbon.calc.constants import CCUSAGE_VERSION


class AmbiguousCostAttributionError(ValueError):
    """Raised when a day reports >1 model but only a day-level cost --
    there's no per-model field to split by, so this refuses to guess an
    allocation rather than return an invented number."""


# Plain dataclass, not pydantic: internal adapter type built from
# already-parsed JSON, not agent input; pydantic validates the MCP tool
# surface in server.py instead.
@dataclass
class UsageRecord:
    model: str
    input_tokens: int
    output_tokens: int
    cache_creation_tokens: int | None  # None = not reported by this source
    cache_read_tokens: int | None      # 0 = reported and genuinely zero
    usd_cost: float
    source: str
    window_start: str  # ISO-8601 UTC, inclusive
    window_end: str    # ISO-8601 UTC, exclusive


def _window(date_str: str) -> tuple[str, str]:
    """ccusage's daily report only gives a bare date (e.g. "2026-07-29");
    this manufactures a [start, end) UTC range at midnight boundaries since
    nothing finer-grained exists in the source -- documented assumption,
    not observed precision (decided 2026-07-30)."""
    d = _date.fromisoformat(date_str)
    return f"{d.isoformat()}T00:00:00Z", f"{(d + timedelta(days=1)).isoformat()}T00:00:00Z"


def parse_claude_daily(data: dict) -> list[UsageRecord]:
    """claude's real, verified shape: modelBreakdowns is a list, each entry
    carries its own cost and cache fields (always present in every
    observed row, sometimes 0)."""
    records = []
    for day in data.get("daily", []):
        start, end = _window(day["date"])
        for mb in day["modelBreakdowns"]:
            records.append(UsageRecord(
                model=mb["modelName"],
                input_tokens=mb["inputTokens"],
                output_tokens=mb["outputTokens"],
                cache_creation_tokens=mb["cacheCreationTokens"],
                cache_read_tokens=mb["cacheReadTokens"],
                usd_cost=mb["cost"],
                source="claude",
                window_start=start,
                window_end=end,
            ))
    return records


def _parse_dict_shaped_daily(data: dict, source: str) -> list[UsageRecord]:
    """codex's real, verified shape: `models` is a dict keyed by model
    name, with cost only reported at the day level (`costUSD`), never per
    model. A single-model day can attribute that cost unambiguously; a
    multi-model day can't without guessing a split, so it raises.

    opencode/pi/amp reuse this same shape and rule as a documented
    ASSUMPTION, not a verified observation -- their real fixtures have
    zero non-empty rows, so this path has never run against real data
    from those three sources (see tests/test_ccusage_adapter.py's
    UNVERIFIED test). Cache fields use .get() (None if absent) since
    they're documented as optionally-reported; every other field is
    required and raises loudly (KeyError) if missing.
    """
    records = []
    for day in data.get("daily", []):
        start, end = _window(day["date"])
        models = day["models"]
        if len(models) > 1:
            raise AmbiguousCostAttributionError(
                f"{source} {day['date']}: {len(models)} models "
                f"({sorted(models)}) but cost is only reported at the day "
                "level -- cannot attribute per-model cost without guessing"
            )
        day_cost = day["costUSD"]
        for model_name, m in models.items():
            records.append(UsageRecord(
                model=model_name,
                input_tokens=m["inputTokens"],
                output_tokens=m["outputTokens"],
                cache_creation_tokens=m.get("cacheCreationTokens"),
                cache_read_tokens=m.get("cacheReadTokens"),
                usd_cost=day_cost,
                source=source,
                window_start=start,
                window_end=end,
            ))
    return records


parse_codex_daily = partial(_parse_dict_shaped_daily, source="codex")
parse_opencode_daily = partial(_parse_dict_shaped_daily, source="opencode")
parse_pi_daily = partial(_parse_dict_shaped_daily, source="pi")
parse_amp_daily = partial(_parse_dict_shaped_daily, source="amp")


def fetch_daily(source: str, version: str = CCUSAGE_VERSION, timeout: int = 60) -> dict:
    """Subprocess wrapper around the pinned ccusage binary's `daily --json`
    output. Raises on non-zero exit (CalledProcessError), invalid JSON
    (JSONDecodeError), or a hung process (TimeoutExpired) -- doesn't catch
    or degrade internally, since the caller (server.py's estimate()) is the
    one that knows whether to fall through to the estimated path.
    """
    result = subprocess.run(
        ["npx", "--yes", f"ccusage@{version}", source, "daily", "--json"],
        shell=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, result.args, result.stdout, result.stderr)
    return json.loads(result.stdout)


def _select_window(records: list[UsageRecord], model: str, host: str, window: str) -> UsageRecord:
    """Filters to the requested window, summing across days for "all".
    Never returns None -- a captured result with no matching usage is a
    legitimate zero-cost record, not an absence. Cache-token fields on the
    returned record are irrelevant here (reconcile() never reads them) and
    are set to None rather than aggregated."""
    matches = [r for r in records if r.model == model]
    if window != "all":
        target_date = _date.today().isoformat() if window == "today" else window
        matches = [r for r in matches if r.window_start.startswith(target_date)]

    if not matches:
        today = f"{_date.today().isoformat()}T00:00:00Z"
        return UsageRecord(model=model, input_tokens=0, output_tokens=0,
                            cache_creation_tokens=None, cache_read_tokens=None,
                            usd_cost=0.0, source=host,
                            window_start=today, window_end=today)
    return UsageRecord(
        model=model,
        input_tokens=sum(r.input_tokens for r in matches),
        output_tokens=sum(r.output_tokens for r in matches),
        cache_creation_tokens=None, cache_read_tokens=None,
        usd_cost=sum(r.usd_cost for r in matches),
        source=host,
        window_start=min(r.window_start for r in matches),
        window_end=max(r.window_end for r in matches),
    )
