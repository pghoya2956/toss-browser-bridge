from __future__ import annotations

from types import MethodType

import pytest

import toss_browser_bridge.daemon as daemon_module
from toss_browser_bridge.daemon import TossBridgeRuntime
from toss_browser_bridge.preview import build_preview_fingerprint
from toss_browser_bridge.submit import (
    MutationDomainError,
    MutationValidationError,
    append_mutation_journal,
    build_prepare_drift_issues,
    build_order_prepare_payload,
    build_order_preview_fingerprint_payload,
    build_order_preview_receipt,
    find_recent_mutation_by_id,
    validate_place_order_params,
)
from toss_browser_bridge.daemon import classify_broker_reject


class FakePage:
    def __init__(self, url: str) -> None:
        self.url = url


def _runtime(page_url: str = "https://www.tossinvest.com/account") -> TossBridgeRuntime:
    runtime = TossBridgeRuntime()
    runtime.ensure_page = MethodType(lambda self: FakePage(page_url), runtime)
    return runtime


def _receipt(preview_fingerprint: str | None = None) -> dict[str, object]:
    inputs = {
        "market": "us",
        "side": "buy",
        "symbol": "AAPL",
        "order_type": "limit",
        "quantity": 1,
        "limit_price": 200.0,
    }
    submit_candidate = {
        "market": "us",
        "side": "buy",
        "product_code": "US0378331005",
        "symbol": "AAPL",
        "order_type": "limit",
        "quantity": 1,
        "limit_price": 200.0,
        "currency": "USD",
        "estimated_total_amount": 200.0,
    }
    derived = {
        "product_code": "US0378331005",
        "currency": "USD",
        "estimated_unit_price": 200.0,
        "estimated_total_amount": 200.0,
        "orderable_cash": 1000.0,
        "available_quantity": None,
        "market_status": "ACTIVE",
    }
    actual_fingerprint = preview_fingerprint or build_preview_fingerprint(
        build_order_preview_fingerprint_payload(
            account_id="toss:***1234",
            inputs=inputs,
            submit_candidate=submit_candidate,
            derived=derived,
        )
    )
    return build_order_preview_receipt(
        preview_id="pvw_test1234",
        preview_fingerprint=actual_fingerprint,
        account_id="toss:***1234",
        inputs=inputs,
        submit_candidate=submit_candidate,
        derived=derived,
        verification_plan={"queries": ["completed_orders", "positions", "account_summary"]},
    )


def test_place_order_returns_capability_not_ready_until_verify_is_implemented(tmp_path, monkeypatch) -> None:
    runtime = _runtime()
    runtime.account_summary = MethodType(
        lambda self: {
            "ok": True,
            "kind": "account_summary",
            "checked_at": "2026-04-17T15:00:00+09:00",
            "diagnostics": {"endpoint_matrix": [], "last_errors": []},
            "data": {"account_id": "toss:***1234", "orderable_krw": 1_000_000, "orderable_usd": 1_000},
        },
        runtime,
    )
    runtime.quote = MethodType(
        lambda self, params: {
            "ok": True,
            "kind": "quote",
            "checked_at": "2026-04-17T15:00:00+09:00",
            "diagnostics": {"endpoint_matrix": [], "last_errors": []},
            "data": {
                "product_code": "US0378331005",
                "symbol": "AAPL",
                "market_code": "US_NASDAQ",
                "currency": "USD",
                "current_price": 200.0,
                "reference_price": 199.0,
                "status": "ACTIVE",
            },
        },
        runtime,
    )
    monkeypatch.setattr(daemon_module, "MUTATION_JOURNAL_FILE", tmp_path / "mutation-journal.jsonl")
    runtime._run_prepare_preflight = MethodType(
        lambda self, normalized: {
            "message": "prepare preflight succeeded",
            "context": None,
            "account_no": "44258118-01",
            "submit_market": "NSQ",
            "currency_mode": "USD",
            "allow_auto_exchange": False,
            "prepare_payload": {},
            "prepare_body": {},
            "prepared_order_info": {},
        },
        runtime,
    )
    receipt = runtime.order_preview(
        {
            "market": "us",
            "side": "buy",
            "symbol": "AAPL",
            "order_type": "limit",
            "quantity": 1,
            "limit_price": 200.0,
        }
    )["data"]["preview_receipt"]

    with pytest.raises(
        MutationDomainError,
        match=r"final submit is disabled \(disabled_by_default\); prepare preflight succeeded",
    ) as excinfo:
        runtime.place_order(
            {
                "preview_receipt": receipt,
                "preview_fingerprint": receipt["preview_fingerprint"],
                "confirm": True,
                "confirm_text": "BUY 1 AAPL LIMIT 200.00 US",
            }
        )

    assert excinfo.value.code == "capability_not_ready"


def test_build_order_prepare_payload_uses_limit_code_and_receipt_fields() -> None:
    receipt = _receipt()

    payload = build_order_prepare_payload(
        receipt,
        submit_market="NSQ",
        currency_mode="USD",
        allow_auto_exchange=False,
    )

    assert payload["stockCode"] == "US0378331005"
    assert payload["tradeType"] == "buy"
    assert payload["market"] == "NSQ"
    assert payload["currencyMode"] == "USD"
    assert payload["orderPriceType"] == "00"
    assert payload["quantity"] == 1
    assert payload["withOrderKey"] is True


def test_build_prepare_drift_issues_detects_price_change() -> None:
    receipt = _receipt()

    issues = build_prepare_drift_issues(
        receipt,
        {
            "tradeType": "buy",
            "orderPriceType": "00",
            "quantity": 1,
            "price": 201.0,
        },
    )

    assert issues == [
        {
            "code": "prepare_price_mismatch",
            "message": "preparedOrderInfo.price drifted from preview_receipt",
        }
    ]


def test_resolve_order_price_type_us_market_uses_limit_code_per_p0_02() -> None:
    from toss_browser_bridge.submit import resolve_order_price_type

    assert resolve_order_price_type("us", "limit") == "00"
    assert resolve_order_price_type("us", "market") == "00"


def test_resolve_order_price_type_kr_market_uses_placeholder_until_supervised() -> None:
    from toss_browser_bridge.submit import resolve_order_price_type

    assert resolve_order_price_type("kr", "limit") == "00"
    assert resolve_order_price_type("kr", "market") == "03"


def test_build_order_prepare_payload_us_market_uses_orderPriceType_00() -> None:
    from toss_browser_bridge.preview import build_preview_fingerprint
    from toss_browser_bridge.submit import build_order_preview_fingerprint_payload, build_order_preview_receipt

    inputs = {
        "market": "us",
        "side": "sell",
        "symbol": "NVDA",
        "order_type": "market",
        "quantity": 5,
        "limit_price": 198.27,
    }
    submit_candidate = {
        "market": "us",
        "side": "sell",
        "product_code": "US67066G1040",
        "symbol": "NVDA",
        "order_type": "market",
        "quantity": 5,
        "limit_price": 198.27,
        "currency": "USD",
        "estimated_total_amount": 991.35,
    }
    derived = {
        "product_code": "US67066G1040",
        "currency": "USD",
        "estimated_unit_price": 198.27,
        "estimated_total_amount": 991.35,
        "orderable_cash": 1000.0,
        "available_quantity": 5,
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
    receipt = build_order_preview_receipt(
        preview_id="pvw_market",
        preview_fingerprint=fingerprint,
        account_id="toss:***1234",
        inputs=inputs,
        submit_candidate=submit_candidate,
        derived=derived,
        verification_plan={"queries": ["completed_orders", "positions", "account_summary"]},
    )

    payload = build_order_prepare_payload(
        receipt,
        submit_market="NSQ",
        currency_mode="USD",
        allow_auto_exchange=False,
    )

    assert payload["orderPriceType"] == "00"
    assert payload["price"] == 198.27
    assert payload["quantity"] == 5


def test_place_order_blocks_when_request_time_preview_fingerprint_drifts(tmp_path, monkeypatch) -> None:
    runtime = _runtime()
    monkeypatch.setattr(daemon_module, "MUTATION_JOURNAL_FILE", tmp_path / "mutation-journal.jsonl")
    receipt = _receipt()
    runtime.order_preview = MethodType(
        lambda self, params: {
            "ok": True,
            "kind": "order_preview",
            "checked_at": "2026-04-17T15:00:00+09:00",
            "diagnostics": {"endpoint_matrix": [], "last_errors": []},
            "data": {
                "preview_state": "preview_ready",
                "preview_fingerprint": "sha256:drifted",
            },
        },
        runtime,
    )

    with pytest.raises(
        MutationDomainError,
        match="request-time preview fingerprint drifted from preview_receipt",
    ) as excinfo:
        runtime.place_order(
            {
                "preview_receipt": receipt,
                "preview_fingerprint": receipt["preview_fingerprint"],
                "confirm": True,
                "confirm_text": "BUY 1 AAPL LIMIT 200.00 US",
            }
        )

    assert excinfo.value.code == "submit_blocked"


def test_place_order_blocks_duplicate_preview_fingerprint(tmp_path, monkeypatch) -> None:
    runtime = _runtime()
    journal_path = tmp_path / "mutation-journal.jsonl"
    monkeypatch.setattr(daemon_module, "MUTATION_JOURNAL_FILE", journal_path)
    receipt = _receipt()
    append_mutation_journal(
        journal_path,
        {
            "mutation_id": "mut_existing",
            "kind": "place_order",
            "requested_at": "2026-04-17T15:10:00+09:00",
            "preview_fingerprint": receipt["preview_fingerprint"],
            "confirm_phrase_hash": "sha256:phrase",
            "submit_state": "submit_blocked",
            "verification_state": "pending",
            "broker_ack": {
                "status": "not_attempted",
                "message": "already used",
                "market": "us",
                "symbol": "AAPL",
                "side": "buy",
                "quantity": 1,
                "order_type": "limit",
            },
        },
    )

    with pytest.raises(
        MutationDomainError,
        match="preview_fingerprint already exists in mutation journal",
    ) as excinfo:
        runtime.place_order(
            {
                "preview_receipt": receipt,
                "preview_fingerprint": receipt["preview_fingerprint"],
                "confirm": True,
                "confirm_text": "BUY 1 AAPL LIMIT 200.00 US",
            }
        )

    assert excinfo.value.code == "submit_blocked"


def test_verify_order_requires_mutation_id() -> None:
    runtime = _runtime()

    with pytest.raises(MutationDomainError, match="mutation_id is required") as excinfo:
        runtime.verify_order({})

    assert excinfo.value.code == "invalid_request"


def test_verify_order_marks_blocked_mutation_as_verified_failed(tmp_path, monkeypatch) -> None:
    runtime = _runtime()
    journal_path = tmp_path / "mutation-journal.jsonl"
    monkeypatch.setattr(daemon_module, "MUTATION_JOURNAL_FILE", journal_path)
    append_mutation_journal(
        journal_path,
        {
            "mutation_id": "mut_blocked",
            "kind": "place_order",
            "requested_at": "2026-04-17T15:10:00+09:00",
            "preview_fingerprint": "sha256:test",
            "confirm_phrase_hash": "sha256:phrase",
            "submit_state": "submit_blocked",
            "verification_state": "pending",
            "broker_ack": {
                "status": "prepared",
                "message": "final create remains blocked",
                "market": "us",
                "symbol": "AAPL",
                "side": "buy",
                "quantity": 1,
                "order_type": "limit",
            },
        },
    )

    payload = runtime.verify_order({"mutation_id": "mut_blocked"})

    assert payload["ok"] is True
    assert payload["data"]["mutation_id"] == "mut_blocked"
    assert payload["data"]["submit_state"] == "submit_blocked"
    assert payload["data"]["verification_state"] == "verified_failed"
    assert payload["data"]["verify_snapshot"]["message"] == "final create remains blocked"
    saved = find_recent_mutation_by_id(journal_path, "mut_blocked")
    assert saved["kind"] == "verify_order"
    assert saved["verification_state"] == "verified_failed"


def test_verify_order_returns_verified_success_when_completed_order_matches(tmp_path, monkeypatch) -> None:
    runtime = _runtime()
    journal_path = tmp_path / "mutation-journal.jsonl"
    monkeypatch.setattr(daemon_module, "MUTATION_JOURNAL_FILE", journal_path)
    append_mutation_journal(
        journal_path,
        {
            "mutation_id": "mut_submitted",
            "kind": "place_order",
            "requested_at": "2026-04-17T15:10:00+09:00",
            "preview_fingerprint": "sha256:test",
            "confirm_phrase_hash": "sha256:phrase",
            "submit_state": "submitted",
            "verification_state": "pending",
            "broker_ack": {
                "status": "accepted",
                "message": "submitted",
                "market": "us",
                "symbol": "AAPL",
                "side": "buy",
                "quantity": 1,
                "order_type": "limit",
            },
        },
    )
    runtime.completed_orders = MethodType(
        lambda self, params: {
            "ok": True,
            "kind": "completed_orders",
            "checked_at": "2026-04-17T15:12:00+09:00",
            "diagnostics": {"endpoint_matrix": [{"name": "completed_orders_us"}], "last_errors": []},
            "data": {
                "market": params["market"],
                "items": [
                    {
                        "market": "us",
                        "symbol": "AAPL",
                        "side": "buy",
                        "shares": 1,
                        "executed_at": "2026-04-17T15:11:30+09:00",
                        "status": "completed",
                    }
                ],
            },
        },
        runtime,
    )
    runtime.positions = MethodType(
        lambda self: {
            "ok": True,
            "kind": "positions",
            "checked_at": "2026-04-17T15:12:00+09:00",
            "diagnostics": {"endpoint_matrix": [{"name": "positions"}], "last_errors": []},
            "data": {"account_id": "toss:primary", "positions": [{"ticker": "AAPL", "quantity": 7}]},
        },
        runtime,
    )
    runtime.account_summary = MethodType(
        lambda self: {
            "ok": True,
            "kind": "account_summary",
            "checked_at": "2026-04-17T15:12:00+09:00",
            "diagnostics": {"endpoint_matrix": [{"name": "account_summary"}], "last_errors": []},
            "data": {"account_id": "toss:***1234", "orderable_krw": 1_000_000, "orderable_usd": 800.0},
        },
        runtime,
    )

    payload = runtime.verify_order({"mutation_id": "mut_submitted"})

    assert payload["ok"] is True
    assert payload["data"]["verification_state"] == "verified_success"
    assert payload["data"]["verify_snapshot"]["matched_order"]["symbol"] == "AAPL"
    assert payload["data"]["verify_snapshot"]["position_delta"]["current_quantity"] == 7
    assert payload["data"]["verify_snapshot"]["cash_delta"]["currency"] == "USD"
    saved = find_recent_mutation_by_id(journal_path, "mut_submitted")
    assert saved["kind"] == "verify_order"
    assert saved["verification_state"] == "verified_success"


def test_verify_order_returns_unknown_when_verify_window_has_no_match(tmp_path, monkeypatch) -> None:
    runtime = _runtime()
    runtime._verify_poll_attempts = 2
    runtime._verify_poll_delay_seconds = 0.0
    journal_path = tmp_path / "mutation-journal.jsonl"
    monkeypatch.setattr(daemon_module, "MUTATION_JOURNAL_FILE", journal_path)
    append_mutation_journal(
        journal_path,
        {
            "mutation_id": "mut_unknown",
            "kind": "place_order",
            "requested_at": "2026-04-17T15:10:00+09:00",
            "preview_fingerprint": "sha256:test",
            "confirm_phrase_hash": "sha256:phrase",
            "submit_state": "submitted",
            "verification_state": "pending",
            "broker_ack": {
                "status": "accepted",
                "message": "submitted",
                "market": "us",
                "symbol": "AAPL",
                "side": "buy",
                "quantity": 1,
                "order_type": "limit",
            },
        },
    )
    runtime.completed_orders = MethodType(
        lambda self, params: {
            "ok": True,
            "kind": "completed_orders",
            "checked_at": "2026-04-17T15:12:00+09:00",
            "diagnostics": {"endpoint_matrix": [{"name": "completed_orders_us"}], "last_errors": []},
            "data": {"market": params["market"], "items": []},
        },
        runtime,
    )
    runtime.positions = MethodType(
        lambda self: {
            "ok": True,
            "kind": "positions",
            "checked_at": "2026-04-17T15:12:00+09:00",
            "diagnostics": {"endpoint_matrix": [{"name": "positions"}], "last_errors": []},
            "data": {"account_id": "toss:primary", "positions": [{"ticker": "AAPL", "quantity": 6}]},
        },
        runtime,
    )
    runtime.account_summary = MethodType(
        lambda self: {
            "ok": True,
            "kind": "account_summary",
            "checked_at": "2026-04-17T15:12:00+09:00",
            "diagnostics": {"endpoint_matrix": [{"name": "account_summary"}], "last_errors": []},
            "data": {"account_id": "toss:***1234", "orderable_krw": 1_000_000, "orderable_usd": 800.0},
        },
        runtime,
    )

    payload = runtime.verify_order({"mutation_id": "mut_unknown"})

    assert payload["ok"] is True
    assert payload["data"]["verification_state"] == "unknown"
    assert payload["data"]["verify_snapshot"]["matched_order"] is None
    assert "after 2 verify attempt(s)" in payload["data"]["verify_snapshot"]["message"]
    assert payload["data"]["verify_snapshot"]["position_delta"]["current_quantity"] == 6


def test_verify_order_retries_within_bounded_window_until_match(tmp_path, monkeypatch) -> None:
    runtime = _runtime()
    runtime._verify_poll_attempts = 3
    runtime._verify_poll_delay_seconds = 0.0
    journal_path = tmp_path / "mutation-journal.jsonl"
    monkeypatch.setattr(daemon_module, "MUTATION_JOURNAL_FILE", journal_path)
    append_mutation_journal(
        journal_path,
        {
            "mutation_id": "mut_retry",
            "kind": "place_order",
            "requested_at": "2026-04-17T15:10:00+09:00",
            "preview_fingerprint": "sha256:test",
            "confirm_phrase_hash": "sha256:phrase",
            "submit_state": "submitted",
            "verification_state": "pending",
            "broker_ack": {
                "status": "accepted",
                "message": "submitted",
                "market": "us",
                "symbol": "AAPL",
                "side": "buy",
                "quantity": 1,
                "order_type": "limit",
            },
        },
    )
    state = {"calls": 0}

    def _completed_orders(self, params):
        state["calls"] += 1
        items = []
        if state["calls"] >= 2:
            items = [
                {
                    "market": "us",
                    "symbol": "AAPL",
                    "side": "buy",
                    "shares": 1,
                    "executed_at": "2026-04-17T15:11:30+09:00",
                    "status": "completed",
                }
            ]
        return {
            "ok": True,
            "kind": "completed_orders",
            "checked_at": "2026-04-17T15:12:00+09:00",
            "diagnostics": {"endpoint_matrix": [{"name": "completed_orders_us"}], "last_errors": []},
            "data": {"market": params["market"], "items": items},
        }

    runtime.completed_orders = MethodType(_completed_orders, runtime)
    runtime.positions = MethodType(
        lambda self: {
            "ok": True,
            "kind": "positions",
            "checked_at": "2026-04-17T15:12:00+09:00",
            "diagnostics": {"endpoint_matrix": [{"name": "positions"}], "last_errors": []},
            "data": {"account_id": "toss:primary", "positions": [{"ticker": "AAPL", "quantity": 7}]},
        },
        runtime,
    )
    runtime.account_summary = MethodType(
        lambda self: {
            "ok": True,
            "kind": "account_summary",
            "checked_at": "2026-04-17T15:12:00+09:00",
            "diagnostics": {"endpoint_matrix": [{"name": "account_summary"}], "last_errors": []},
            "data": {"account_id": "toss:***1234", "orderable_krw": 1_000_000, "orderable_usd": 800.0},
        },
        runtime,
    )

    payload = runtime.verify_order({"mutation_id": "mut_retry"})

    assert payload["ok"] is True
    assert payload["data"]["verification_state"] == "verified_success"
    assert state["calls"] == 2


def test_final_submit_stays_blocked_under_pytest_even_if_env_requests_enable(monkeypatch) -> None:
    monkeypatch.setenv("TOSS_BRIDGE_ENABLE_FINAL_SUBMIT", "1")
    monkeypatch.delenv("TOSS_BRIDGE_ALLOW_TEST_FINAL_SUBMIT", raising=False)

    runtime = _runtime()

    assert runtime._final_submit_enabled is False
    assert runtime._mutation_runtime_state()["final_submit_guard_reason"] == "blocked_in_pytest"


def test_final_submit_can_be_explicitly_unblocked_for_manual_non_pytest_runtime(monkeypatch) -> None:
    monkeypatch.setenv("TOSS_BRIDGE_ENABLE_FINAL_SUBMIT", "1")
    monkeypatch.setenv("TOSS_BRIDGE_ALLOW_TEST_FINAL_SUBMIT", "1")

    runtime = _runtime()

    assert runtime._final_submit_enabled is True
    assert runtime._mutation_runtime_state()["final_submit_guard_reason"] == "enabled_by_env"


def test_classify_broker_reject_maps_status_codes_to_enum() -> None:
    assert classify_broker_reject(message=None, status_code=0, error="EAI_AGAIN") == "BROKER_REJECTED_TIMEOUT"
    assert classify_broker_reject(message="gateway timeout", status_code=504, error=None) == "BROKER_REJECTED_TIMEOUT"
    assert classify_broker_reject(message="forbidden", status_code=403, error=None) == "BROKER_REJECTED_AUTH_REQUIRED"
    assert classify_broker_reject(message="unauthorized", status_code=401, error=None) == "BROKER_REJECTED_AUTH_REQUIRED"
    assert classify_broker_reject(message="server error", status_code=500, error=None) == "BROKER_REJECTED_HTTP_ERROR"
    assert classify_broker_reject(message="unknown", status_code=200, error=None) == "BROKER_REJECTED_UNKNOWN"
    assert classify_broker_reject(message=None, status_code=400, error=None) == "BROKER_REJECTED_UNKNOWN"


def _enable_final_submit(monkeypatch) -> None:
    monkeypatch.setenv("TOSS_BRIDGE_ENABLE_FINAL_SUBMIT", "1")
    monkeypatch.setenv("TOSS_BRIDGE_ALLOW_TEST_FINAL_SUBMIT", "1")


def _stub_place_order_dependencies(runtime, monkeypatch, tmp_path, fingerprint) -> None:
    monkeypatch.setattr(daemon_module, "MUTATION_JOURNAL_FILE", tmp_path / "mutation-journal.jsonl")
    runtime.order_preview = MethodType(
        lambda self, params: {
            "ok": True,
            "kind": "order_preview",
            "checked_at": "2026-05-04T23:40:00+09:00",
            "diagnostics": {"endpoint_matrix": [], "last_errors": []},
            "data": {
                "preview_state": "preview_ready",
                "preview_fingerprint": fingerprint,
            },
        },
        runtime,
    )
    runtime._run_prepare_preflight = MethodType(
        lambda self, normalized: {
            "message": "prepare preflight succeeded",
            "context": self._make_context([]),
            "account_no": "44258118-01",
            "submit_market": "NSQ",
            "currency_mode": "USD",
            "allow_auto_exchange": False,
            "prepare_payload": {
                "stockCode": "US0378331005",
                "tradeType": "buy",
                "market": "NSQ",
                "currencyMode": "USD",
                "price": 200.0,
                "quantity": 1,
                "orderAmount": 0,
                "orderPriceType": "00",
                "agreedOver100Million": False,
                "marginTrading": False,
                "max": False,
                "isReservationOrder": False,
                "openPriceSinglePriceYn": False,
                "withOrderKey": True,
            },
            "prepare_body": {"orderKey": "trade::session::stub"},
            "prepared_order_info": {"price": 200.0, "quantity": 1},
        },
        runtime,
    )


def test_place_order_submits_when_broker_create_returns_order_id(tmp_path, monkeypatch) -> None:
    _enable_final_submit(monkeypatch)
    runtime = _runtime()
    receipt = _receipt()
    _stub_place_order_dependencies(runtime, monkeypatch, tmp_path, receipt["preview_fingerprint"])
    runtime._fetch_many = MethodType(
        lambda self, requests: [
            {
                "name": "order_create",
                "method": "POST",
                "path": "/api/v2/wts/trading/order/create",
                "status_code": 200,
                "ok": True,
                "json": {
                    "result": {
                        "message": "AAPL 매수 주문 완료",
                        "orderDate": "2026-05-04",
                        "orderNo": 3,
                        "isReserved": False,
                        "orderId": "V56qyv7r",
                    }
                },
                "text": "",
                "error": None,
            }
        ],
        runtime,
    )

    response = runtime.place_order(
        {
            "preview_receipt": receipt,
            "preview_fingerprint": receipt["preview_fingerprint"],
            "confirm": True,
            "confirm_text": "BUY 1 AAPL LIMIT 200.00 US",
        }
    )

    assert response["ok"] is True
    data = response["data"]
    assert data["submit_state"] == "submitted"
    assert data["broker_ack"]["status"] == "submitted"
    assert data["broker_ack"]["code"] == "OK"
    assert data["broker_ack"]["broker_order_id"] == "V56qyv7r"
    assert data["broker_ack"]["order_no"] == 3
    assert data["broker_ack"]["order_date"] == "2026-05-04"
    assert data["broker_ack"]["http_status"] == 200


def test_place_order_marks_broker_rejected_when_orderid_missing(tmp_path, monkeypatch) -> None:
    _enable_final_submit(monkeypatch)
    runtime = _runtime()
    receipt = _receipt()
    _stub_place_order_dependencies(runtime, monkeypatch, tmp_path, receipt["preview_fingerprint"])
    runtime._fetch_many = MethodType(
        lambda self, requests: [
            {
                "name": "order_create",
                "method": "POST",
                "path": "/api/v2/wts/trading/order/create",
                "status_code": 200,
                "ok": True,
                "json": {"result": {"message": "주문 거절"}},
                "text": "",
                "error": None,
            }
        ],
        runtime,
    )

    response = runtime.place_order(
        {
            "preview_receipt": receipt,
            "preview_fingerprint": receipt["preview_fingerprint"],
            "confirm": True,
            "confirm_text": "BUY 1 AAPL LIMIT 200.00 US",
        }
    )

    data = response["data"]
    assert data["submit_state"] == "broker_rejected"
    assert data["broker_ack"]["code"] == "BROKER_REJECTED_UNKNOWN"
    assert "broker_order_id" not in data["broker_ack"]


def test_place_order_marks_broker_rejected_with_timeout_on_runtime_error(tmp_path, monkeypatch) -> None:
    _enable_final_submit(monkeypatch)
    runtime = _runtime()
    receipt = _receipt()
    _stub_place_order_dependencies(runtime, monkeypatch, tmp_path, receipt["preview_fingerprint"])

    def _raise_timeout(self, requests):
        raise RuntimeError("browser request timed out: 30000ms")

    runtime._fetch_many = MethodType(_raise_timeout, runtime)

    response = runtime.place_order(
        {
            "preview_receipt": receipt,
            "preview_fingerprint": receipt["preview_fingerprint"],
            "confirm": True,
            "confirm_text": "BUY 1 AAPL LIMIT 200.00 US",
        }
    )

    data = response["data"]
    assert data["submit_state"] == "broker_rejected"
    assert data["broker_ack"]["code"] == "BROKER_REJECTED_TIMEOUT"
    assert data["broker_ack"]["http_status"] == 0


def test_place_order_auto_verify_attaches_verify_snapshot_when_submitted(tmp_path, monkeypatch) -> None:
    _enable_final_submit(monkeypatch)
    runtime = _runtime()
    receipt = _receipt()
    _stub_place_order_dependencies(runtime, monkeypatch, tmp_path, receipt["preview_fingerprint"])
    runtime._fetch_many = MethodType(
        lambda self, requests: [
            {
                "name": "order_create",
                "method": "POST",
                "path": "/api/v2/wts/trading/order/create",
                "status_code": 200,
                "ok": True,
                "json": {
                    "result": {
                        "message": "AAPL 매수 주문 완료",
                        "orderDate": "2026-05-04",
                        "orderNo": 3,
                        "isReserved": False,
                        "orderId": "V56qyv7r",
                    }
                },
                "text": "",
                "error": None,
            }
        ],
        runtime,
    )
    verify_calls: list[dict] = []

    def _fake_verify_order(self, params):
        verify_calls.append(params)
        return {
            "ok": True,
            "kind": "verify_order",
            "data": {
                "verification_state": "verified_success",
                "verify_snapshot": {
                    "status": "verified_success",
                    "matched_order": {"order_no": 3},
                    "verified_at": "2026-05-04T23:41:00+09:00",
                },
            },
        }

    runtime.verify_order = MethodType(_fake_verify_order, runtime)

    response = runtime.place_order(
        {
            "preview_receipt": receipt,
            "preview_fingerprint": receipt["preview_fingerprint"],
            "confirm": True,
            "confirm_text": "BUY 1 AAPL LIMIT 200.00 US",
            "auto_verify": True,
        }
    )

    data = response["data"]
    assert len(verify_calls) == 1
    assert data["verification_state"] == "verified_success"
    assert data["verify_snapshot"]["matched_order"]["order_no"] == 3


# ---------------------------------------------------------------------------
# Phase 1 P1-07: payload pass-through (isReservationOrder) 회귀 + 신규 테스트
# ---------------------------------------------------------------------------


def _build_prepare_payload_with_flag(reservation: bool | None) -> dict[str, object]:
    return build_order_prepare_payload(
        _receipt(),
        submit_market="NSQ",
        currency_mode="USD",
        allow_auto_exchange=False,
        is_reservation_order=reservation,
    )


def test_build_order_prepare_payload_default_none_keeps_reservation_false() -> None:
    payload = _build_prepare_payload_with_flag(None)
    assert payload["isReservationOrder"] is False


def test_build_order_prepare_payload_explicit_true_serializes_reservation_true() -> None:
    payload = _build_prepare_payload_with_flag(True)
    assert payload["isReservationOrder"] is True


def test_build_order_prepare_payload_explicit_false_serializes_reservation_false() -> None:
    payload = _build_prepare_payload_with_flag(False)
    assert payload["isReservationOrder"] is False


def _valid_place_params(extra: dict[str, object] | None = None) -> dict[str, object]:
    receipt = _receipt()
    base = {
        "preview_receipt": receipt,
        "preview_fingerprint": receipt["preview_fingerprint"],
        "confirm": True,
        "confirm_text": "BUY 1 AAPL LIMIT 200.00 US",
    }
    if extra:
        base.update(extra)
    return base


def test_validate_place_order_params_omits_reservation_when_unset() -> None:
    normalized = validate_place_order_params(_valid_place_params())
    assert normalized["is_reservation_order"] is None


def test_validate_place_order_params_passes_through_true() -> None:
    normalized = validate_place_order_params(_valid_place_params({"is_reservation_order": True}))
    assert normalized["is_reservation_order"] is True


def test_validate_place_order_params_passes_through_false() -> None:
    normalized = validate_place_order_params(_valid_place_params({"is_reservation_order": False}))
    assert normalized["is_reservation_order"] is False


def test_validate_place_order_params_rejects_string_enum() -> None:
    with pytest.raises(MutationValidationError) as excinfo:
        validate_place_order_params(_valid_place_params({"is_reservation_order": "on"}))
    assert "is_reservation_order" in str(excinfo.value)


def test_market_status_issue_n_classifies_as_review_not_normal() -> None:
    issue = TossBridgeRuntime._market_status_issue("N")
    assert issue is not None
    assert issue["blocking"] is False
    assert issue["code"] == "market_status_requires_review"


def test_market_status_issue_active_returns_none() -> None:
    assert TossBridgeRuntime._market_status_issue("ACTIVE") is None


def test_market_status_issue_halt_blocks() -> None:
    issue = TossBridgeRuntime._market_status_issue("HALT")
    assert issue is not None
    assert issue["blocking"] is True
    assert issue["code"] == "market_not_tradeable"
