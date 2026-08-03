"""reconcile() -- pure reconciliation of captured usage or manual token
estimates against the model pricing table. No subprocess/MCP imports:
capture_status is decided by the caller (server.py's estimate()), not here.
"""
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from llm_cost_carbon.adapters.ccusage import UsageRecord
from llm_cost_carbon.calc.constants import STALENESS_THRESHOLD_DAYS

MODELS_PATH = Path(__file__).parent.parent / "data" / "models.json"


class ModelNotFoundError(Exception):
    """Raised when `model` isn't a row in models.json's pricing table."""


@dataclass
class ReconciledResult:
    model: str
    usd_cost: float
    source: str            # "captured" (from ccusage) | "estimated" (manual tokens)
    capture_status: str    # "captured" | "unavailable" | "not_covered"
    capture_reason: str | None
    citations: list[str]
    stale: bool            # true if the model row's last_verified > 90 days


def _load_models() -> dict[str, dict]:
    data = json.loads(MODELS_PATH.read_text())
    return {row["model"]: row for row in data["models"]}


MODELS = _load_models()


def reconcile(
    usage: UsageRecord | None,
    model: str,
    input_tokens: int | None,
    output_tokens: int | None,
    capture_status: str,
    capture_reason: str | None,
) -> ReconciledResult:
    row = MODELS.get(model)
    if row is None:
        raise ModelNotFoundError(model)

    if usage is not None:
        usd_cost = usage.usd_cost
        source = "captured"
    else:
        # ponytail: models.json only prices output tokens (see its
        # per-row price_source notes) -- input_tokens plays no part in
        # the estimated-path math, by design of the pricing table.
        usd_cost = (output_tokens or 0) * row["usd_price_per_million_output_tokens"] / 1_000_000
        source = "estimated"

    last_verified = datetime.strptime(row["last_verified"], "%Y-%m-%d").date()
    stale = (date.today() - last_verified).days > STALENESS_THRESHOLD_DAYS

    return ReconciledResult(
        model=model,
        usd_cost=usd_cost,
        source=source,
        capture_status=capture_status,
        capture_reason=capture_reason,
        citations=[row["price_source"]],
        stale=stale,
    )
