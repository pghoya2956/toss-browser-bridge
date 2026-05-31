import json
from pathlib import Path

from toss_browser_bridge.daemon import MUTATION_CAPABILITIES, POSITIONS_ENDPOINT, classify_health_payload


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
    assert payload["capabilities"]["order_preview_ready"] is False
    assert payload["capabilities"]["post_submit_verify_ready"] is False
    assert payload["capabilities"]["fx_preview_ready"] is False
    assert payload["capabilities"]["order_submit_ready"] is False
    assert payload["capabilities"]["fx_submit_ready"] is False
    assert payload["capabilities"]["cancel_order_ready"] is False
    assert all(name in payload["capabilities"] for name in MUTATION_CAPABILITIES)


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
    assert payload["capabilities"]["order_preview_ready"] is True
    assert payload["capabilities"]["post_submit_verify_ready"] is False
    assert payload["capabilities"]["fx_preview_ready"] is True
    assert payload["capabilities"]["order_submit_ready"] is False
    assert payload["capabilities"]["fx_submit_ready"] is False
    assert payload["capabilities"]["cancel_order_ready"] is False
    assert all(name in payload["capabilities"] for name in MUTATION_CAPABILITIES)


def test_logged_in_fixture_enables_submit_readiness_only_with_runtime_state() -> None:
    fixture = _load_fixture("health-logged-in.json")

    capability, payload = classify_health_payload(
        fixture["results"],
        current_url=fixture["current_url"],
        attached=fixture["attached"],
        mutation_runtime_state={
            "submit_path_discovered": True,
            "verify_path_discovered": True,
            "final_submit_enabled": True,
            "journal_writable": True,
            "inflight_available": True,
        },
    )

    assert capability == "browser_attached"
    assert payload["capabilities"]["post_submit_verify_ready"] is True
    assert payload["capabilities"]["order_submit_ready"] is True


def test_positions_endpoint_requests_sorted_overview_section() -> None:
    assert POSITIONS_ENDPOINT["body"] == {"types": ["SORTED_OVERVIEW"]}


def test_health_does_not_mark_positions_ready_for_empty_sections() -> None:
    fixture = _load_fixture("health-logged-in.json")
    results = []
    for item in fixture["results"]:
        cloned = dict(item)
        if cloned["name"] == "asset_sections_v2":
            cloned["json"] = {"result": {"sections": []}}
        results.append(cloned)

    capability, payload = classify_health_payload(
        results,
        current_url=fixture["current_url"],
        attached=fixture["attached"],
    )

    assert capability == "browser_attached"
    assert payload["capabilities"]["web_session_ready"] is True
    assert payload["capabilities"]["positions_ready"] is False
    assert payload["capabilities"]["post_submit_verify_ready"] is False
