from types import MethodType
from typing import Any

import pytest

from toss_browser_bridge.daemon import TossBridgeRuntime
from toss_browser_bridge.preview import PreviewDomainError


class FakePage:
    def __init__(self, url: str) -> None:
        self.url = url


def _summary_response() -> dict[str, Any]:
    return {
        "ok": True,
        "kind": "account_summary",
        "source": "toss_browser_bridge",
        "checked_at": "2026-04-17T12:00:00+09:00",
        "capability": "account_summary_ready",
        "data": {
            "account_id": "toss:***1234",
            "orderable_krw": 1_000_000,
            "orderable_usd": 1000.0,
        },
        "diagnostics": {
            "endpoint_matrix": [
                {
                    "name": "account_overview",
                    "method": "GET",
                    "path": "/api/v3/my-assets/summaries/markets/all/overview",
                    "status_code": 200,
                    "ok": True,
                }
            ],
            "last_errors": [],
        },
    }


def _runtime(page_url: str = "https://www.tossinvest.com/account") -> TossBridgeRuntime:
    runtime = TossBridgeRuntime()
    runtime.ensure_page = MethodType(lambda self: FakePage(page_url), runtime)
    runtime.account_summary = MethodType(lambda self: _summary_response(), runtime)
    return runtime


def _fx_fetch_many_success(self: TossBridgeRuntime, requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payloads = {
        "fx_rate_probe": {
            "result": {"code": "EXCHANGE_RATE", "base": 1472.6, "close": 1479.65},
        },
        "fx_quote_for_buy_probe": {
            "result": {
                "rateQuoteId": "buy-quote",
                "buyCurrency": "USD",
                "sellCurrency": "KRW",
                "validFrom": "2026-04-17T03:46:39Z",
                "validTill": "2026-04-17T03:51:35Z",
                "roundDate": "2026-04-17",
                "round": 453,
                "usdRate": 1480.389825,
                "favorablePercent": 95,
                "displayUsdRate": 1480.39,
            }
        },
        "fx_quote_for_sell_probe": {
            "result": {
                "rateQuoteId": "sell-quote",
                "buyCurrency": "KRW",
                "sellCurrency": "USD",
                "validFrom": "2026-04-17T03:46:39Z",
                "validTill": "2026-04-17T03:51:35Z",
                "roundDate": "2026-04-17",
                "round": 453,
                "usdRate": 1478.91054473,
                "favorablePercent": 95,
                "displayUsdRate": 1478.91,
            }
        },
    }
    results = []
    for request in requests:
        results.append(
            {
                "name": request["name"],
                "method": request["method"],
                "path": request["path"],
                "status_code": 200,
                "ok": True,
                "json": payloads[request["name"]],
                "error": None,
            }
        )
    self._last_endpoint_matrix = results
    self._last_errors = []
    return results


def test_fx_preview_builds_buy_preview_response() -> None:
    runtime = _runtime()
    runtime._fetch_many = MethodType(_fx_fetch_many_success, runtime)

    payload = runtime.fx_preview({"side": "buy", "amount_krw": 150000})

    assert payload["ok"] is True
    assert payload["kind"] == "fx_preview"
    assert payload["data"]["preview_state"] == "preview_ready"
    assert payload["data"]["derived"]["source_currency"] == "KRW"
    assert payload["data"]["derived"]["target_currency"] == "USD"
    assert payload["data"]["submit_candidate"]["rate_quote_id"] == "buy-quote"
    assert payload["data"]["preview_fingerprint"].startswith("sha256:")


def test_fx_preview_blocks_when_amount_exceeds_available_balance() -> None:
    runtime = _runtime()
    runtime._fetch_many = MethodType(_fx_fetch_many_success, runtime)

    payload = runtime.fx_preview({"side": "sell", "amount_usd": 1500})

    assert payload["ok"] is True
    assert payload["data"]["preview_state"] == "blocked"
    assert payload["data"]["blocking_issues"][0]["code"] == "insufficient_fx_balance"


def test_fx_preview_returns_logged_out_before_quote_fetch() -> None:
    runtime = _runtime("https://www.tossinvest.com/signin?redirectUrl=%2Faccount")

    with pytest.raises(PreviewDomainError, match="logged out") as excinfo:
        runtime.fx_preview({"side": "buy", "amount_krw": 100000})

    assert excinfo.value.code == "logged_out"


def test_fx_preview_returns_capability_not_ready_on_quote_fetch_failure() -> None:
    runtime = _runtime()

    def _fetch_many_failure(self: TossBridgeRuntime, requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "name": requests[0]["name"],
                "method": requests[0]["method"],
                "path": requests[0]["path"],
                "status_code": 500,
                "ok": False,
                "json": None,
                "error": "upstream failed",
            }
        ] + [
            {
                "name": request["name"],
                "method": request["method"],
                "path": request["path"],
                "status_code": 200,
                "ok": True,
                "json": {"result": {}},
                "error": None,
            }
            for request in requests[1:]
        ]

    runtime._fetch_many = MethodType(_fetch_many_failure, runtime)

    with pytest.raises(PreviewDomainError, match="fx quote fetch failed") as excinfo:
        runtime.fx_preview({"side": "buy", "amount_krw": 100000})

    assert excinfo.value.code == "capability_not_ready"
