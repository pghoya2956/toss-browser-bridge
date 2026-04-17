from toss_browser_bridge.preview import (
    PreviewDomainError,
    build_preview_fingerprint,
    canonical_json_dumps,
    preview_state_from_blockers,
)


def test_canonical_json_dumps_sorts_keys() -> None:
    payload = {"b": 2, "a": {"d": 4, "c": 3}}

    assert canonical_json_dumps(payload) == '{"a":{"c":3,"d":4},"b":2}'


def test_preview_fingerprint_is_stable_for_equivalent_payloads() -> None:
    left = {
        "kind": "order_preview",
        "inputs": {"side": "buy", "market": "us"},
        "account_id": "toss:***1234",
        "submit_candidate": {"quantity": 1, "symbol": "AAPL"},
        "derived": {"currency": "USD", "estimated_total_amount": 210.5},
    }
    right = {
        "submit_candidate": {"symbol": "AAPL", "quantity": 1},
        "derived": {"estimated_total_amount": 210.5, "currency": "USD"},
        "account_id": "toss:***1234",
        "inputs": {"market": "us", "side": "buy"},
        "kind": "order_preview",
    }

    assert build_preview_fingerprint(left) == build_preview_fingerprint(right)


def test_preview_state_from_blockers_reflects_blocked_state() -> None:
    assert preview_state_from_blockers([]) == "preview_ready"
    assert preview_state_from_blockers([{"code": "insufficient_buying_power"}]) == "blocked"


def test_preview_domain_error_renders_json_payload() -> None:
    error = PreviewDomainError(
        kind="order_preview",
        capability="order_preview_ready",
        code="invalid_request",
        message="order_type is required",
        diagnostics={"endpoint_matrix": [], "last_errors": []},
    )

    payload = error.to_payload(source="toss_browser_bridge", checked_at="2026-04-17T12:34:56+09:00")

    assert payload == {
        "ok": False,
        "kind": "order_preview",
        "source": "toss_browser_bridge",
        "checked_at": "2026-04-17T12:34:56+09:00",
        "capability": "order_preview_ready",
        "error": {
            "code": "invalid_request",
            "message": "order_type is required",
        },
        "diagnostics": {
            "endpoint_matrix": [],
            "last_errors": [],
        },
    }
