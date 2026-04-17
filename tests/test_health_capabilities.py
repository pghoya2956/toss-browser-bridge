import json
from pathlib import Path

from toss_browser_bridge.daemon import MUTATION_CAPABILITIES, classify_health_payload


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def test_logged_out_fixture_classifies_readiness() -> None:
    fixture = _load_fixture("health-logged-out.json")

    capability, payload = classify_health_payload(
        fixture["results"],
        current_url=fixture["current_url"],
        attached=fixture["attached"],
    )

    assert capability == "attached_but_logged_out"
    assert payload["session_state"] == "attached_but_logged_out"
    assert payload["capabilities"]["browser_attached"] is True
    assert payload["capabilities"]["web_session_ready"] is False
    assert payload["capabilities"]["wts_api_ready"] is False
    assert payload["capabilities"]["wts_cert_api_ready"] is False
    assert payload["capabilities"]["account_summary_ready"] is False
    assert payload["capabilities"]["positions_ready"] is False
    assert payload["capabilities"]["completed_orders_ready"] is False
    assert payload["capabilities"]["quote_ready"] is True
    assert all(payload["capabilities"][name] is False for name in MUTATION_CAPABILITIES)


def test_logged_in_fixture_classifies_readiness() -> None:
    fixture = _load_fixture("health-logged-in.json")

    capability, payload = classify_health_payload(
        fixture["results"],
        current_url=fixture["current_url"],
        attached=fixture["attached"],
    )

    assert capability == "browser_attached"
    assert payload["session_state"] == "attached"
    assert payload["capabilities"]["browser_attached"] is True
    assert payload["capabilities"]["web_session_ready"] is True
    assert payload["capabilities"]["wts_api_ready"] is True
    assert payload["capabilities"]["wts_cert_api_ready"] is True
    assert payload["capabilities"]["account_summary_ready"] is True
    assert payload["capabilities"]["positions_ready"] is True
    assert payload["capabilities"]["completed_orders_ready"] is True
    assert payload["capabilities"]["quote_ready"] is True
    assert all(payload["capabilities"][name] is False for name in MUTATION_CAPABILITIES)
