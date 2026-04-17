from __future__ import annotations

import json

import pytest

from toss_browser_bridge.preview import build_preview_fingerprint
from toss_browser_bridge.submit import (
    MutationDomainError,
    append_mutation_journal,
    build_order_confirm_phrase,
    build_order_preview_fingerprint_payload,
    build_order_preview_receipt,
    find_recent_mutation_by_id,
    mutation_journal_line_preview,
    sanitize_mutation_journal_entry,
    validate_order_preview_receipt,
    validate_place_order_params,
    validate_verify_order_params,
)


def _receipt(order_type: str = "limit") -> dict[str, object]:
    inputs = {
        "market": "us",
        "side": "buy",
        "symbol": "AAPL",
        "order_type": order_type,
        "quantity": 3,
        "limit_price": 201.5 if order_type == "limit" else None,
    }
    submit_candidate = {
        "market": "us",
        "side": "buy",
        "product_code": "US0378331005",
        "symbol": "AAPL",
        "order_type": order_type,
        "quantity": 3,
        "limit_price": 201.5 if order_type == "limit" else None,
        "currency": "USD",
        "estimated_total_amount": 604.5,
    }
    derived = {
        "product_code": "US0378331005",
        "currency": "USD",
        "estimated_unit_price": 201.5,
        "estimated_total_amount": 604.5,
        "orderable_cash": 1000.0,
        "available_quantity": None,
        "market_status": "ACTIVE",
    }
    fingerprint = build_preview_fingerprint(
        build_order_preview_fingerprint_payload(
            account_id="toss:***1234",
            inputs=inputs,
            submit_candidate=submit_candidate,
            derived=derived,
        )
    )
    return build_order_preview_receipt(
        preview_id="pvw_test1234",
        preview_fingerprint=fingerprint,
        account_id="toss:***1234",
        inputs=inputs,
        submit_candidate=submit_candidate,
        derived=derived,
        verification_plan={"queries": ["completed_orders", "positions", "account_summary"]},
    )


def test_build_order_confirm_phrase_is_ascii_and_deterministic() -> None:
    receipt = validate_order_preview_receipt(_receipt())

    phrase = build_order_confirm_phrase(receipt)

    assert phrase == "BUY 3 AAPL LIMIT 201.50 US"
    assert phrase.isascii()


def test_validate_place_order_params_requires_matching_confirm_text() -> None:
    receipt = validate_order_preview_receipt(_receipt())

    with pytest.raises(Exception, match="confirm_text does not match the canonical confirm phrase"):
        validate_place_order_params(
            {
                "preview_receipt": receipt,
                "preview_fingerprint": receipt["preview_fingerprint"],
                "confirm": True,
                "confirm_text": "BUY 99 AAPL LIMIT 999.99 US",
            }
        )


def test_validate_place_order_params_rejects_market_receipt() -> None:
    receipt = validate_order_preview_receipt(_receipt(order_type="market"))

    with pytest.raises(Exception, match="limit preview receipts only"):
        validate_place_order_params(
            {
                "preview_receipt": receipt,
                "preview_fingerprint": receipt["preview_fingerprint"],
                "confirm": True,
                "confirm_text": "BUY 3 AAPL MARKET US",
            }
        )


def test_mutation_domain_error_renders_json_payload() -> None:
    error = MutationDomainError(
        kind="place_order",
        capability="order_submit_ready",
        code="capability_not_ready",
        message="order submit path discovery is not completed yet",
        diagnostics={"endpoint_matrix": [], "last_errors": []},
    )

    payload = error.to_payload(source="toss_browser_bridge", checked_at="2026-04-17T15:00:00+09:00")

    assert payload["error"]["code"] == "capability_not_ready"
    assert payload["kind"] == "place_order"
    assert payload["capability"] == "order_submit_ready"


def test_mutation_domain_error_preserves_extra_diagnostics() -> None:
    error = MutationDomainError(
        kind="place_order",
        capability="order_submit_ready",
        code="capability_not_ready",
        message="blocked",
        diagnostics={"endpoint_matrix": [], "last_errors": [], "mutation_id": "mut_1234"},
    )

    payload = error.to_payload(source="toss_browser_bridge", checked_at="2026-04-17T15:00:00+09:00")

    assert payload["diagnostics"]["mutation_id"] == "mut_1234"


def test_mutation_journal_sanitizes_forbidden_fields(tmp_path) -> None:
    path = tmp_path / "mutation-journal.jsonl"
    entry = append_mutation_journal(
        path,
        {
            "mutation_id": "mut_1234",
            "kind": "place_order",
            "requested_at": "2026-04-17T15:10:00+09:00",
            "preview_fingerprint": "sha256:test",
            "confirm_phrase_hash": "sha256:phrase",
            "submit_state": "submitted",
            "verification_state": "pending",
            "broker_ack": {
                "status": "accepted",
                "code": "ACK",
                "message": "accepted",
                "market": "us",
                "symbol": "AAPL",
                "side": "buy",
                "quantity": 1,
                "order_type": "limit",
                "ordered_at": "2026-04-17T15:10:02+09:00",
                "accountNo": "12345678",
                "headers": {"Authorization": "Bearer secret"},
            },
            "verify_snapshot": {
                "status": "pending",
                "verified_at": "2026-04-17T15:10:03+09:00",
                "raw_response": {"secret": True},
            },
            "raw_body": {"token": "secret"},
        },
    )

    assert entry["schema_version"] == 1
    assert "raw_body" not in entry
    assert "accountNo" not in entry["broker_ack"]
    assert "headers" not in entry["broker_ack"]
    assert "raw_response" not in entry["verify_snapshot"]
    saved = json.loads(path.read_text(encoding="utf-8").strip())
    assert saved == sanitize_mutation_journal_entry(entry)


def test_mutation_journal_line_preview_is_sanitized() -> None:
    line = mutation_journal_line_preview(
        {
            "mutation_id": "mut_1234",
            "kind": "place_order",
            "requested_at": "2026-04-17T15:10:00+09:00",
            "preview_fingerprint": "sha256:test",
            "confirm_phrase_hash": "sha256:phrase",
            "submit_state": "submit_blocked",
            "verification_state": "pending",
            "Authorization": "Bearer secret",
        }
    )

    assert "Authorization" not in line
    assert '"mutation_id":"mut_1234"' in line


def test_find_recent_mutation_by_id_returns_latest_sanitized_entry(tmp_path) -> None:
    path = tmp_path / "mutation-journal.jsonl"
    append_mutation_journal(
        path,
        {
            "mutation_id": "mut_1234",
            "kind": "place_order",
            "requested_at": "2026-04-17T15:10:00+09:00",
            "preview_fingerprint": "sha256:test",
            "confirm_phrase_hash": "sha256:phrase",
            "submit_state": "submitted",
            "verification_state": "pending",
            "broker_ack": {"status": "accepted", "message": "first"},
        },
    )
    append_mutation_journal(
        path,
        {
            "mutation_id": "mut_1234",
            "kind": "verify_order",
            "requested_at": "2026-04-17T15:11:00+09:00",
            "preview_fingerprint": "sha256:test",
            "confirm_phrase_hash": "sha256:phrase",
            "submit_state": "submitted",
            "verification_state": "unknown",
            "broker_ack": {"status": "accepted", "message": "second"},
            "verify_snapshot": {"status": "unknown", "verified_at": "2026-04-17T15:11:00+09:00"},
        },
    )

    entry = find_recent_mutation_by_id(path, "mut_1234")

    assert entry["kind"] == "verify_order"
    assert entry["verification_state"] == "unknown"
    assert entry["verify_snapshot"]["status"] == "unknown"


def test_validate_verify_order_params_requires_mutation_id() -> None:
    with pytest.raises(Exception, match="mutation_id is required"):
        validate_verify_order_params({})
