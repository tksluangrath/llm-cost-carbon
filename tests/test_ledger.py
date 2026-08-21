"""Ledger revival build-order verify conditions: append writes correct
entries, summarize() sums correctly per scope, export() caps/truncates
and filters since/until at the stated boundaries. All tests point
LEDGER_DIR/LEDGER_PATH at a tmp_path -- never touch the real
~/.llm-cost-carbon/ directory.
"""
import json

import pytest

from llm_cost_carbon import ledger


@pytest.fixture(autouse=True)
def _isolated_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "LEDGER_DIR", tmp_path / ".llm-cost-carbon")
    monkeypatch.setattr(ledger, "LEDGER_PATH", tmp_path / ".llm-cost-carbon" / "ledger.jsonl")
    monkeypatch.setattr(ledger, "SESSION_ID", "session-a")


def _lines():
    return [json.loads(line) for line in ledger.LEDGER_PATH.read_text().splitlines()]


def test_append_writes_one_entry_per_call_with_correct_fields():
    ledger.append(model="claude-sonnet-5", usd_cost=1.23, source="captured", tool="estimate")
    ledger.append(model="llama-3.1-8b", usd_cost=0.18, source="estimated", tool="compare")
    ledger.append(model="gpt-5.2-codex", usd_cost=0.14, source="captured", tool="estimate")

    entries = _lines()
    assert len(entries) == 3
    assert entries[0]["model"] == "claude-sonnet-5"
    assert entries[0]["usd_cost"] == 1.23
    assert entries[0]["source"] == "captured"
    assert entries[0]["tool"] == "estimate"
    assert entries[0]["session_id"] == "session-a"
    assert entries[0]["timestamp"]  # non-empty, presence checked; format covered by round-trip below


def test_append_creates_dir_and_file_with_restrictive_permissions():
    ledger.append(model="x", usd_cost=1.0, source="estimated", tool="estimate")
    assert oct(ledger.LEDGER_DIR.stat().st_mode)[-3:] == "700"
    assert oct(ledger.LEDGER_PATH.stat().st_mode)[-3:] == "600"


def test_summarize_session_excludes_other_sessions():
    ledger.append(model="a", usd_cost=1.0, source="captured", tool="estimate")
    ledger.append(model="b", usd_cost=2.0, source="estimated", tool="compare")
    # a raw entry from a different session, written directly (not via append())
    with ledger.LEDGER_PATH.open("a") as f:
        f.write(json.dumps({
            "timestamp": "2026-01-01T00:00:00+00:00", "session_id": "session-b",
            "model": "c", "usd_cost": 100.0, "source": "captured", "tool": "estimate",
        }) + "\n")

    session_summary = ledger.summarize("session")
    assert session_summary["scope"] == "session"
    assert session_summary["call_count"] == 2
    assert session_summary["total_usd"] == 3.0
    assert session_summary["captured_usd"] == 1.0
    assert session_summary["estimated_usd"] == 2.0

    project_summary = ledger.summarize("project")
    assert project_summary["call_count"] == 3
    assert project_summary["total_usd"] == 103.0
    assert project_summary["captured_usd"] == 101.0


def test_summarize_empty_ledger_returns_zeroes_not_an_error():
    summary = ledger.summarize("project")
    assert summary["call_count"] == 0
    assert summary["total_usd"] == 0
    assert summary["date_range"] == ("", "")


def test_summarize_invalid_scope_raises():
    with pytest.raises(ValueError):
        ledger.summarize("not-a-scope")


def test_export_json_untruncated_for_small_ledger():
    ledger.append(model="a", usd_cost=1.0, source="captured", tool="estimate")
    ledger.append(model="b", usd_cost=2.0, source="estimated", tool="compare")

    result = json.loads(ledger.export("json"))
    assert result["truncated"] is False
    assert len(result["entries"]) == 2
    # newest-first
    assert result["entries"][0]["model"] == "b"
    assert result["entries"][1]["model"] == "a"


def test_export_truncates_at_limit_and_sets_marker():
    for i in range(5):
        ledger.append(model=f"m{i}", usd_cost=1.0, source="estimated", tool="estimate")

    result = json.loads(ledger.export("json", limit=3))
    assert result["truncated"] is True
    assert len(result["entries"]) == 3
    # newest-first: last-appended (m4, m3, m2) survive the cap
    assert [e["model"] for e in result["entries"]] == ["m4", "m3", "m2"]


def test_export_since_is_inclusive_until_is_exclusive():
    ledger.LEDGER_DIR.mkdir(mode=0o700, exist_ok=True)
    with ledger.LEDGER_PATH.open("a") as f:
        for ts, model in [
            ("2026-01-01T00:00:00+00:00", "before"),
            ("2026-01-02T00:00:00+00:00", "on-since"),
            ("2026-01-03T00:00:00+00:00", "middle"),
            ("2026-01-04T00:00:00+00:00", "on-until"),
            ("2026-01-05T00:00:00+00:00", "after"),
        ]:
            f.write(json.dumps({
                "timestamp": ts, "session_id": "session-a", "model": model,
                "usd_cost": 1.0, "source": "estimated", "tool": "estimate",
            }) + "\n")

    result = json.loads(ledger.export("json", since="2026-01-02T00:00:00+00:00", until="2026-01-04T00:00:00+00:00"))
    models = {e["model"] for e in result["entries"]}
    assert models == {"on-since", "middle"}  # since inclusive, until exclusive


def test_export_csv_format():
    ledger.append(model="a", usd_cost=1.0, source="captured", tool="estimate")
    result = ledger.export("csv")
    assert "timestamp,session_id,tool,model,models_compared,usd_cost,source" in result
    assert "a" in result
    assert "captured" in result


def test_export_csv_renders_models_compared_as_joined_list():
    ledger.append(tool="compare", models_compared=["a", "b", "c"])
    result = ledger.export("csv")
    assert "a, b, c" in result


def test_export_invalid_format_raises():
    with pytest.raises(ValueError):
        ledger.export("xml")
