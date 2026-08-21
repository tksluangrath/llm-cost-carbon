"""Append-only local ledger of every estimate()/compare() call, so
cumulative spend can be answered without re-deriving it from memory or
storing anything beyond what estimate()/compare() already computed.
Cost-only: never stores carbon/energy fields, only usd_cost.

LEDGER_DIR/LEDGER_PATH are module-level so tests can monkeypatch them to
a tmp_path rather than touching the real ~/.llm-cost-carbon/ directory.
"""
import csv
import io
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

LEDGER_DIR = Path.home() / ".llm-cost-carbon"
LEDGER_PATH = LEDGER_DIR / "ledger.jsonl"

DEFAULT_EXPORT_LIMIT = 1000

# One id per server process -- the MCP server process corresponds to one
# Claude Code session. A server restart mid-conversation starts a new
# session_id; accepted for v1 (see build prompt's open question 3).
SESSION_ID = str(uuid.uuid4())


@dataclass
class LedgerEntry:
    timestamp: str          # ISO-8601 UTC, when this entry was written
    session_id: str
    tool: str                        # "estimate" | "compare"
    model: str | None                # single model; set for "estimate", None for "compare"
    models_compared: list[str] | None  # set for "compare", None for "estimate"
    usd_cost: float | None           # real dollar figure; None for "compare" -- a
                                      # comparison is exploratory, not actual spend,
                                      # so it must never be summed into totals
    source: str | None               # "captured" | "estimated" | None


def append(
    tool: str,
    model: str | None = None,
    models_compared: list[str] | None = None,
    usd_cost: float | None = None,
    source: str | None = None,
) -> None:
    """One entry per estimate() call, one entry per compare() call
    regardless of how many models it compares -- a compare() call is one
    logical query even though it touches N models internally; splitting it
    into N entries would make export_ledger's output look like N separate
    actions that never happened (this exact rule existed in the ledger's
    original pre-cut design)."""
    LEDGER_DIR.mkdir(mode=0o700, exist_ok=True)
    if not LEDGER_PATH.exists():
        LEDGER_PATH.touch(mode=0o600)
    entry = LedgerEntry(
        timestamp=datetime.now(timezone.utc).isoformat(),
        session_id=SESSION_ID,
        tool=tool,
        model=model,
        models_compared=models_compared,
        usd_cost=usd_cost,
        source=source,
    )
    with LEDGER_PATH.open("a") as f:
        f.write(json.dumps(asdict(entry)) + "\n")


def _read_all() -> list[dict]:
    if not LEDGER_PATH.exists():
        return []
    with LEDGER_PATH.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def summarize(scope: str) -> dict:
    """call_count reflects every logged call (estimate() and compare()
    alike -- each is a real query). The dollar totals only sum entries
    with a real usd_cost -- compare()'s entries never have one, since
    comparing hypothetical costs isn't spend."""
    if scope not in ("session", "project"):
        raise ValueError(f"invalid scope: {scope!r}")
    entries = _read_all()
    if scope == "session":
        entries = [e for e in entries if e["session_id"] == SESSION_ID]
    cost_entries = [e for e in entries if e["usd_cost"] is not None]
    total = sum(e["usd_cost"] for e in cost_entries)
    captured = sum(e["usd_cost"] for e in cost_entries if e["source"] == "captured")
    estimated = sum(e["usd_cost"] for e in cost_entries if e["source"] == "estimated")
    timestamps = [e["timestamp"] for e in entries]
    date_range = (min(timestamps), max(timestamps)) if timestamps else ("", "")
    return {
        "scope": scope,
        "total_usd": total,
        "captured_usd": captured,
        "estimated_usd": estimated,
        "call_count": len(entries),
        "date_range": date_range,
    }


def export(format: str, since: str | None = None, until: str | None = None,
           limit: int = DEFAULT_EXPORT_LIMIT) -> str:
    """`since` is inclusive, `until` is exclusive -- both compared as
    ISO-8601 strings against each entry's timestamp. Newest-first;
    truncated to `limit` rows with a `truncated: true` marker if exceeded."""
    if format not in ("json", "csv"):
        raise ValueError(f"invalid format: {format!r}")
    entries = _read_all()
    if since is not None:
        entries = [e for e in entries if e["timestamp"] >= since]
    if until is not None:
        entries = [e for e in entries if e["timestamp"] < until]
    entries.sort(key=lambda e: e["timestamp"], reverse=True)
    truncated = len(entries) > limit
    entries = entries[:limit]

    if format == "json":
        return json.dumps({"entries": entries, "truncated": truncated})

    buf = io.StringIO()
    fieldnames = ["timestamp", "session_id", "tool", "model", "models_compared", "usd_cost", "source"]
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for e in entries:
        row = dict(e)
        models = row.get("models_compared")
        row["models_compared"] = ", ".join(models) if models else ""
        writer.writerow(row)
    if truncated:
        buf.write("# truncated: true\n")
    return buf.getvalue()
