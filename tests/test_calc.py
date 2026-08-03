"""Step 3 verify: reconcile() unit tests, no I/O."""
import pytest

from llm_cost_carbon.adapters.ccusage import UsageRecord
from llm_cost_carbon.calc.reconcile import ModelNotFoundError, reconcile

MODEL = "llama-3.1-8b"  # models.json: $0.18 / million output tokens


def _usage(**overrides):
    defaults = dict(
        model=MODEL,
        input_tokens=100,
        output_tokens=200,
        cache_creation_tokens=0,
        cache_read_tokens=0,
        usd_cost=1.23,
        source="claude",
        window_start="2026-01-01T00:00:00Z",
        window_end="2026-01-02T00:00:00Z",
    )
    defaults.update(overrides)
    return UsageRecord(**defaults)


def test_zero_token_estimated_path_returns_zero_cost():
    result = reconcile(None, MODEL, 0, 0, "not_covered", None)
    assert result.usd_cost == 0.0


def test_unknown_model_raises_model_not_found_not_none():
    with pytest.raises(ModelNotFoundError):
        reconcile(None, "not-a-real-model", 10, 10, "not_covered", None)


@pytest.mark.parametrize("capture_status", ["not_covered", "unavailable"])
def test_not_covered_and_unavailable_route_through_estimated_math(capture_status):
    result = reconcile(None, MODEL, 1_000_000, 1_000_000, capture_status, "some reason")
    assert result.usd_cost == pytest.approx(0.18)
    assert result.source == "estimated"
    assert result.capture_status == capture_status


def test_usage_present_uses_ccusage_cost_directly_not_recomputed():
    usage = _usage(usd_cost=20.798728600000018, output_tokens=177996)
    result = reconcile(usage, MODEL, None, None, "captured", None)
    assert result.usd_cost == 20.798728600000018
    assert result.source == "captured"


def test_citations_and_stale_populate_from_model_row():
    result = reconcile(None, MODEL, 0, 0, "not_covered", None)
    assert result.citations == ["Together.ai, https://www.together.ai/models/llama-3-1-8b, accessed 2026-07-29"]
    assert result.stale is False  # last_verified 2026-07-29, well under 90 days as of any 2026 run
