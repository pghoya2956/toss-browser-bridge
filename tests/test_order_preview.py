from types import MethodType
from typing import Any

import pytest

from toss_browser_bridge.daemon import TossBridgeRuntime
from toss_browser_bridge.preview import PreviewDomainError
from toss_browser_bridge.submit import build_order_confirm_phrase, validate_order_preview_receipt


class FakePage:
    def __init__(self, url: str) -> None:
        self.url = url


def _response(
    *,
    ok: bool,
    kind: str,
    data: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
    endpoint_name: str = "dependency",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": ok,
        "kind": kind,
        "source": "toss_browser_bridge",
        "checked_at": "2026-04-17T12:00:00+09:00",
        "capability": f"{kind}_ready",
        "diagnostics": {
            "endpoint_matrix": [
                {
                    "name": endpoint_name,
                    "method": "GET",
                    "path": f"/api/{endpoint_name}",
                    "status_code": 200 if ok else 500,
                    "ok": ok,
                }
            ],
            "last_errors": [] if ok else [f"{endpoint_name}: 500"],
        },
    }
    if ok:
        payload["data"] = data or {}
    else:
        payload["error"] = error or {"code": "capability_not_ready", "message": "dependency failed"}
    return payload


def _runtime(page_url: str = "https://www.tossinvest.com/account") -> TossBridgeRuntime:
    runtime = TossBridgeRuntime()
    runtime.ensure_page = MethodType(lambda self: FakePage(page_url), runtime)
    return runtime


def test_order_preview_rejects_missing_order_type() -> None:
    runtime = _runtime()

    with pytest.raises(PreviewDomainError, match="order_type is required") as excinfo:
        runtime.order_preview(
            {
                "market": "us",
                "side": "buy",
                "symbol": "AAPL",
                "quantity": 1,
            }
        )

    assert excinfo.value.code == "invalid_request"


def test_order_preview_builds_buy_preview_response() -> None:
    runtime = _runtime()
    runtime.account_summary = MethodType(
        lambda self: _response(
            ok=True,
            kind="account_summary",
            endpoint_name="account_overview",
            data={
                "account_id": "toss:***1234",
                "orderable_krw": 1_000_000,
                "orderable_usd": 1_000,
            },
        ),
        runtime,
    )
    runtime.quote = MethodType(
        lambda self, params: _response(
            ok=True,
            kind="quote",
            endpoint_name="stock_prices",
            data={
                "product_code": "US0378331005",
                "symbol": "AAPL",
                "market_code": "US_NASDAQ",
                "currency": "USD",
                "current_price": 210.5,
                "reference_price": 205.0,
                "status": "ACTIVE",
            },
        ),
        runtime,
    )

    payload = runtime.order_preview(
        {
            "market": "us",
            "side": "buy",
            "symbol": "AAPL",
            "order_type": "market",
            "quantity": 2,
        }
    )

    assert payload["ok"] is True
    assert payload["data"]["preview_state"] == "preview_ready"
    assert payload["data"]["submit_candidate"]["estimated_total_amount"] == 421.0
    assert payload["data"]["submit_candidate"]["limit_price"] == 210.5
    assert payload["data"]["inputs"]["limit_price"] is None
    assert payload["data"]["warnings"][0]["code"] == "market_order_uses_last_price"
    assert payload["data"]["blocking_issues"] == []
    assert payload["data"]["preview_fingerprint"].startswith("sha256:")
    assert payload["data"]["preview_receipt"]["preview_fingerprint"] == payload["data"]["preview_fingerprint"]
    assert payload["data"]["confirm_phrase"] == build_order_confirm_phrase(payload["data"]["preview_receipt"])


def test_order_preview_marks_sell_preview_blocked_when_quantity_exceeds_position() -> None:
    runtime = _runtime()
    runtime.account_summary = MethodType(
        lambda self: _response(
            ok=True,
            kind="account_summary",
            endpoint_name="account_overview",
            data={
                "account_id": "toss:***1234",
                "orderable_krw": 1_000_000,
                "orderable_usd": 1_000,
            },
        ),
        runtime,
    )
    runtime.quote = MethodType(
        lambda self, params: _response(
            ok=True,
            kind="quote",
            endpoint_name="stock_prices",
            data={
                "product_code": "US0378331005",
                "symbol": "AAPL",
                "market_code": "US_NASDAQ",
                "currency": "USD",
                "current_price": 210.5,
                "reference_price": 205.0,
                "status": "ACTIVE",
            },
        ),
        runtime,
    )
    runtime.positions = MethodType(
        lambda self: _response(
            ok=True,
            kind="positions",
            endpoint_name="asset_sections_v2",
            data={
                "account_id": "toss:primary",
                "positions": [{"ticker": "AAPL", "quantity": 1}],
            },
        ),
        runtime,
    )

    payload = runtime.order_preview(
        {
            "market": "us",
            "side": "sell",
            "symbol": "AAPL",
            "order_type": "limit",
            "quantity": 3,
            "limit_price": 215,
        }
    )

    assert payload["ok"] is True
    assert payload["data"]["preview_state"] == "blocked"
    assert payload["data"]["blocking_issues"][0]["code"] == "insufficient_position_quantity"
    assert payload["data"]["derived"]["available_quantity"] == 1
    assert validate_order_preview_receipt(payload["data"]["preview_receipt"]) == payload["data"]["preview_receipt"]


def test_order_preview_raises_domain_error_when_sell_dependency_fails() -> None:
    runtime = _runtime()
    runtime.account_summary = MethodType(
        lambda self: _response(
            ok=True,
            kind="account_summary",
            endpoint_name="account_overview",
            data={
                "account_id": "toss:***1234",
                "orderable_krw": 1_000_000,
                "orderable_usd": 1_000,
            },
        ),
        runtime,
    )
    runtime.quote = MethodType(
        lambda self, params: _response(
            ok=True,
            kind="quote",
            endpoint_name="stock_prices",
            data={
                "product_code": "US0378331005",
                "symbol": "AAPL",
                "market_code": "US_NASDAQ",
                "currency": "USD",
                "current_price": 210.5,
                "reference_price": 205.0,
                "status": "ACTIVE",
            },
        ),
        runtime,
    )
    runtime.positions = MethodType(
        lambda self: _response(
            ok=False,
            kind="positions",
            endpoint_name="asset_sections_v2",
            error={"code": "capability_not_ready", "message": "positions fetch failed"},
        ),
        runtime,
    )

    with pytest.raises(PreviewDomainError, match="positions fetch failed") as excinfo:
        runtime.order_preview(
            {
                "market": "us",
                "side": "sell",
                "symbol": "AAPL",
                "order_type": "market",
                "quantity": 1,
            }
        )

    assert excinfo.value.code == "capability_not_ready"
