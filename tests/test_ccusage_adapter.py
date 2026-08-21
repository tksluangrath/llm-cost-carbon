"""Step 2 verify: contract tests per tested ccusage source subcommand.

claude and codex are tested against real, non-empty checked-in fixtures --
every assertion there is a verified observation. opencode/pi/amp's real
fixtures are genuinely empty (no local usage history for these hosts on
this machine), so their None-defaulting behavior is tested against a
hand-built synthetic row instead -- see the test docstring below for why
that's flagged as unverified rather than presented with the same
confidence as the claude/codex tests.
"""
import json
from pathlib import Path

import pytest

from llm_cost_carbon.adapters.parser import (
    parse_amp_daily,
    parse_claude_daily,
    parse_codex_daily,
    parse_opencode_daily,
    parse_pi_daily,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name):
    return json.loads((FIXTURES / name).read_text())


# --- claude: real, verified shape (modelBreakdowns list) ---


def test_parse_claude_daily_explodes_multi_model_day_into_separate_records():
    """2026-07-29 has 2 models in modelBreakdowns -- must produce 2 records,
    each with that model's own fields, not the day-level aggregate."""
    records = parse_claude_daily(_load("ccusage_claude_daily.json"))
    day_records = [r for r in records if r.window_start == "2026-07-29T00:00:00Z"]
    assert len(day_records) == 2

    by_model = {r.model: r for r in day_records}
    sonnet = by_model["claude-sonnet-5"]
    assert sonnet.input_tokens == 12203
    assert sonnet.output_tokens == 177996
    assert sonnet.cache_creation_tokens == 1120913
    assert sonnet.cache_read_tokens == 73149473
    assert sonnet.usd_cost == 20.798728600000018
    assert sonnet.source == "claude"
    assert sonnet.window_start == "2026-07-29T00:00:00Z"
    assert sonnet.window_end == "2026-07-30T00:00:00Z"

    opus = by_model["claude-opus-5"]
    assert opus.input_tokens == 6
    assert opus.output_tokens == 7980
    assert opus.cache_creation_tokens == 15997
    assert opus.cache_read_tokens == 29974
    assert opus.usd_cost == 0.31449825


def test_parse_claude_daily_cache_fields_are_real_ints_never_none():
    """Every row in the real fixture reports cache fields (sometimes 0,
    never absent) -- claude never hits the None branch."""
    records = parse_claude_daily(_load("ccusage_claude_daily.json"))
    assert records
    assert all(r.cache_creation_tokens is not None for r in records)
    assert all(r.cache_read_tokens is not None for r in records)


def test_parse_claude_daily_total_record_count_matches_modelbreakdown_count():
    data = _load("ccusage_claude_daily.json")
    expected = sum(len(day["modelBreakdowns"]) for day in data["daily"])
    assert len(parse_claude_daily(data)) == expected


def test_parse_claude_daily_missing_required_field_raises_loudly():
    data = {"daily": [{"date": "2026-01-01", "modelBreakdowns": [{"modelName": "x"}]}]}
    with pytest.raises(KeyError):
        parse_claude_daily(data)


# --- codex: real, verified shape (models dict, day-level cost only) ---


def test_parse_codex_daily_single_model_days_match_fixture_exactly():
    records = parse_codex_daily(_load("ccusage_codex_daily.json"))
    assert len(records) == 2

    r0 = records[0]
    assert r0.model == "gpt-5.2-codex"
    assert r0.input_tokens == 20368
    assert r0.output_tokens == 3671
    assert r0.cache_creation_tokens == 0
    assert r0.cache_read_tokens == 130688
    assert r0.usd_cost == 0.1099084
    assert r0.source == "codex"
    assert r0.window_start == "2026-01-05T00:00:00Z"
    assert r0.window_end == "2026-01-06T00:00:00Z"

    r1 = records[1]
    assert r1.cache_creation_tokens == 0
    assert r1.cache_read_tokens == 39424
    assert r1.usd_cost == 0.030191700000000002


def test_parse_codex_daily_multi_model_day_raises_instead_of_guessing_cost_split():
    """codex only reports cost at the day level, never per model -- a day
    with 2+ models has no way to attribute cost to either one without
    inventing a split. Fail loudly (per the same rule as claude's missing
    field), don't guess."""
    data = {
        "daily": [
            {
                "date": "2026-01-05",
                "costUSD": 1.0,
                "models": {
                    "gpt-5.2-codex": {
                        "inputTokens": 1,
                        "outputTokens": 1,
                        "cacheCreationTokens": 0,
                        "cacheReadTokens": 0,
                    },
                    "gpt-5.2-codex-mini": {
                        "inputTokens": 1,
                        "outputTokens": 1,
                        "cacheCreationTokens": 0,
                        "cacheReadTokens": 0,
                    },
                },
            }
        ]
    }
    with pytest.raises(ValueError):
        parse_codex_daily(data)


def test_parse_codex_daily_missing_required_field_raises_loudly():
    data = {"daily": [{"date": "2026-01-01", "costUSD": 1.0, "models": {"x": {}}}]}
    with pytest.raises(KeyError):
        parse_codex_daily(data)


# --- opencode/pi/amp: real fixtures are genuinely empty on this machine ---


@pytest.mark.parametrize(
    "fixture_name,parser",
    [
        ("ccusage_opencode_daily.json", parse_opencode_daily),
        ("ccusage_pi_daily.json", parse_pi_daily),
        ("ccusage_amp_daily.json", parse_amp_daily),
    ],
)
def test_parse_returns_empty_list_for_sources_with_no_local_usage(fixture_name, parser):
    """Real, verified: these checked-in fixtures' `daily` arrays are
    genuinely empty (no local usage history for these hosts on this
    machine) -- this is the one thing about these 3 sources we actually
    know from real data."""
    assert parser(_load(fixture_name)) == []


def test_opencode_pi_amp_cache_fields_default_to_none_when_absent_UNVERIFIED():
    """UNVERIFIED AGAINST REAL DATA. opencode/pi/amp have zero non-empty
    rows in their checked-in fixtures -- there is no real observation of
    what these three sources emit for a day with actual usage. This test
    exercises the parser's None-default behavior against a hand-built
    synthetic row (assumed to share codex's dict-of-models shape), not a
    captured fixture. This is a deliberate, flagged risk accepted in the
    Phase-1 checkpoint ruling, not a silent guess -- revisit and replace
    with a real fixture-based test if/when actual usage data becomes
    available for any of these three sources.
    """
    synthetic_day_with_no_cache_fields_reported = {
        "daily": [
            {
                "date": "2026-01-01",
                "costUSD": 1.23,
                "models": {
                    "some-model": {
                        "inputTokens": 10,
                        "outputTokens": 20,
                        # deliberately no cacheCreationTokens/cacheReadTokens keys
                    },
                },
            }
        ]
    }
    for parser in (parse_opencode_daily, parse_pi_daily, parse_amp_daily):
        records = parser(synthetic_day_with_no_cache_fields_reported)
        assert len(records) == 1
        assert records[0].cache_creation_tokens is None
        assert records[0].cache_read_tokens is None
        assert records[0].input_tokens == 10
        assert records[0].usd_cost == 1.23
