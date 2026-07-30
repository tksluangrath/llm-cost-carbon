"""Step 1 verify (cost-only v1, scope-reduced 2026-07-29): data/models.json
has 5-10 entries, each with pricing + a source reference + last_verified.

Trimmed from the pre-reduction version: params, params_provenance,
precision, wh_per_1k_output_tokens, gco2_per_1k_output_tokens and their
assertions are gone along with FLOP-based energy modeling. What's left
below still applies unchanged to a cost-only tool.
"""
import json
import re
from datetime import date, datetime
from pathlib import Path

MODELS_PATH = Path(__file__).parent.parent / "src" / "llm_cost_carbon" / "data" / "models.json"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
REQUIRED_FIELDS = {
    "model",
    "usd_price_per_million_output_tokens",
    "price_source",
    "last_verified",
}


def load_models():
    return json.loads(MODELS_PATH.read_text())["models"]


def test_model_count_between_5_and_10():
    models = load_models()
    assert 5 <= len(models) <= 10


def test_every_model_has_required_fields():
    for m in load_models():
        missing = REQUIRED_FIELDS - m.keys()
        assert not missing, f"{m.get('model')} missing fields: {missing}"


def test_last_verified_is_a_valid_iso_date_not_in_the_future():
    today = date.today()
    for m in load_models():
        assert DATE_RE.match(m["last_verified"]), m["model"]
        parsed = datetime.strptime(m["last_verified"], "%Y-%m-%d").date()
        assert parsed <= today, f"{m['model']} last_verified is in the future"


def test_model_names_are_unique():
    models = load_models()
    names = [m["model"] for m in models]
    assert len(names) == len(set(names))


def test_price_is_positive():
    for m in load_models():
        assert m["usd_price_per_million_output_tokens"] > 0
