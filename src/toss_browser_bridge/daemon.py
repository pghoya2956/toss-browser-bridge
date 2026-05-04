from __future__ import annotations

import argparse
import json
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

from toss_browser_bridge.bridge_lib import (
    HOST,
    LOG_FILE,
    MUTATION_JOURNAL_FILE,
    PID_FILE,
    PORT,
    PROFILE_DIR,
    SOURCE,
    clear_runtime_markers,
    ensure_runtime_dirs,
    masked_account_id,
    now_kst,
    rotate_token,
    sanitize_endpoint_entry,
    write_pid,
)
from toss_browser_bridge.preview import (
    PreviewDomainError,
    build_preview_fingerprint,
    make_preview_id,
    preview_state_from_blockers,
)
from toss_browser_bridge.submit import (
    MutationDomainError,
    MutationValidationError,
    append_mutation_journal,
    build_prepare_drift_issues,
    build_order_confirm_phrase,
    build_order_prepare_payload,
    build_order_preview_fingerprint_payload,
    build_order_preview_receipt,
    find_recent_mutation_by_id,
    find_recent_mutation_by_preview_fingerprint,
    make_mutation_id,
    mutation_journal_is_writable,
    validate_place_order_params,
    validate_verify_order_params,
)

ACCOUNT_URL = "https://www.tossinvest.com/account"
KST = ZoneInfo("Asia/Seoul")
FINAL_SUBMIT_ENABLE_ENV = "TOSS_BRIDGE_ENABLE_FINAL_SUBMIT"
FINAL_SUBMIT_TEST_BYPASS_ENV = "TOSS_BRIDGE_ALLOW_TEST_FINAL_SUBMIT"

BROKER_ACK_OK = "OK"
BROKER_REJECTED_INSUFFICIENT_BALANCE = "BROKER_REJECTED_INSUFFICIENT_BALANCE"
BROKER_REJECTED_INSUFFICIENT_QUANTITY = "BROKER_REJECTED_INSUFFICIENT_QUANTITY"
BROKER_REJECTED_INVALID_PRICE = "BROKER_REJECTED_INVALID_PRICE"
BROKER_REJECTED_MARKET_CLOSED = "BROKER_REJECTED_MARKET_CLOSED"
BROKER_REJECTED_AUTH_REQUIRED = "BROKER_REJECTED_AUTH_REQUIRED"
BROKER_REJECTED_DUPLICATE_ORDER = "BROKER_REJECTED_DUPLICATE_ORDER"
BROKER_REJECTED_TIMEOUT = "BROKER_REJECTED_TIMEOUT"
BROKER_REJECTED_HTTP_ERROR = "BROKER_REJECTED_HTTP_ERROR"
BROKER_REJECTED_UNKNOWN = "BROKER_REJECTED_UNKNOWN"

BROKER_ACK_REJECT_CODES = frozenset({
    BROKER_REJECTED_INSUFFICIENT_BALANCE,
    BROKER_REJECTED_INSUFFICIENT_QUANTITY,
    BROKER_REJECTED_INVALID_PRICE,
    BROKER_REJECTED_MARKET_CLOSED,
    BROKER_REJECTED_AUTH_REQUIRED,
    BROKER_REJECTED_DUPLICATE_ORDER,
    BROKER_REJECTED_TIMEOUT,
    BROKER_REJECTED_HTTP_ERROR,
    BROKER_REJECTED_UNKNOWN,
})


def classify_broker_reject(message: str | None, status_code: int, error: str | None) -> str:
    """Map broker create error response to BROKER_REJECTED_* enum.

    Skeleton implementation — Phase 0 P0-02 capture had no reject responses.
    Concrete Korean message → enum mappings will be appended as supervised
    Phase 6 captures surface real reject payloads (P0-03 backlog).
    """
    if error:
        return BROKER_REJECTED_TIMEOUT
    if status_code in (408, 504):
        return BROKER_REJECTED_TIMEOUT
    if status_code in (401, 403):
        return BROKER_REJECTED_AUTH_REQUIRED
    if status_code >= 500:
        return BROKER_REJECTED_HTTP_ERROR
    return BROKER_REJECTED_UNKNOWN
SUMMARY_ENDPOINTS = [
    {
        "name": "account_overview",
        "method": "GET",
        "url": "https://wts-cert-api.tossinvest.com/api/v3/my-assets/summaries/markets/all/overview",
        "path": "/api/v3/my-assets/summaries/markets/all/overview",
    },
    {
        "name": "cached_orderable_amount",
        "method": "GET",
        "url": "https://wts-cert-api.tossinvest.com/api/v1/dashboard/common/cached-orderable-amount",
        "path": "/api/v1/dashboard/common/cached-orderable-amount",
    },
    {
        "name": "withdrawable_kr",
        "method": "GET",
        "url": "https://wts-api.tossinvest.com/api/v1/my-assets/summaries/markets/kr/withdrawable-amount",
        "path": "/api/v1/my-assets/summaries/markets/kr/withdrawable-amount",
    },
    {
        "name": "withdrawable_us",
        "method": "GET",
        "url": "https://wts-api.tossinvest.com/api/v1/my-assets/summaries/markets/us/withdrawable-amount",
        "path": "/api/v1/my-assets/summaries/markets/us/withdrawable-amount",
    },
]
POSITIONS_ENDPOINT = {
    "name": "asset_sections_v2",
    "method": "POST",
    "url": "https://wts-cert-api.tossinvest.com/api/v2/dashboard/asset/sections/all",
    "path": "/api/v2/dashboard/asset/sections/all",
    "body": {},
}
QUOTE_PROBE_ENDPOINT = {
    "name": "quote_probe",
    "method": "GET",
    "url": "https://wts-info-api.tossinvest.com/api/v1/product/stock-prices?meta=true&productCodes=US19990122001",
    "path": "/api/v1/product/stock-prices",
}
FX_RATE_ENDPOINT = {
    "name": "fx_rate_probe",
    "method": "GET",
    "url": "https://wts-info-api.tossinvest.com/api/v1/product/exchange-rate?buyCurrency=USD&sellCurrency=KRW",
    "path": "/api/v1/product/exchange-rate",
}
FX_BUY_QUOTE_ENDPOINT = {
    "name": "fx_quote_for_buy_probe",
    "method": "GET",
    "url": "https://wts-api.tossinvest.com/api/v1/exchange/current-quote/for-buy",
    "path": "/api/v1/exchange/current-quote/for-buy",
}
FX_SELL_QUOTE_ENDPOINT = {
    "name": "fx_quote_for_sell_probe",
    "method": "GET",
    "url": "https://wts-api.tossinvest.com/api/v1/exchange/current-quote/for-sell",
    "path": "/api/v1/exchange/current-quote/for-sell",
}
TRADE_WITHOUT_CONFIRM_ENDPOINT = {
    "name": "trade_without_confirm_toggle",
    "method": "GET",
    "url": "https://wts-api.tossinvest.com/api/v1/trading/settings/toggle/find?categoryName=TRADE_WITHOUT_CONFIRM",
    "path": "/api/v1/trading/settings/toggle/find",
}
ACCOUNT_LIST_ENDPOINT = {
    "name": "account_list",
    "method": "GET",
    "url": "https://wts-api.tossinvest.com/api/v1/account/list",
    "path": "/api/v1/account/list",
}
PREVIEW_MARKETS = {"kr", "us"}
ORDER_SIDES = {"buy", "sell"}
ORDER_TYPES = {"market", "limit"}
FX_SIDES = {"buy", "sell"}
MUTATION_CAPABILITIES = (
    "order_preview_ready",
    "order_submit_ready",
    "post_submit_verify_ready",
    "fx_preview_ready",
    "fx_submit_ready",
    "cancel_order_ready",
)


class PreviewValidationError(ValueError):
    pass


def normalize_product_code(symbol: str) -> str:
    trimmed = symbol.strip().upper()
    if len(trimmed) == 6 and trimmed.isdigit():
        return f"A{trimmed}"
    return trimmed


def looks_like_product_code(value: str) -> bool:
    if len(value) == 7 and value.startswith("A") and value[1:].isdigit():
        return True
    if len(value) >= 8 and value[:2].isalpha() and value[2:].isdigit():
        return True
    return False


def validate_order_preview_params(params: dict[str, Any]) -> dict[str, Any]:
    market = str(params.get("market") or "us").strip().lower()
    if market not in PREVIEW_MARKETS:
        raise PreviewValidationError(f"market must be one of: {', '.join(sorted(PREVIEW_MARKETS))}")

    side = str(params.get("side") or "").strip().lower()
    if side not in ORDER_SIDES:
        raise PreviewValidationError(f"side must be one of: {', '.join(sorted(ORDER_SIDES))}")

    symbol = normalize_product_code(str(params.get("symbol") or ""))
    if not symbol:
        raise PreviewValidationError("symbol is required")

    order_type_raw = params.get("order_type")
    if order_type_raw in (None, ""):
        raise PreviewValidationError("order_type is required")
    order_type = str(order_type_raw).strip().lower()
    if order_type not in ORDER_TYPES:
        raise PreviewValidationError(f"order_type must be one of: {', '.join(sorted(ORDER_TYPES))}")

    quantity = _parse_positive_int(params.get("quantity"), "quantity")
    limit_price_raw = params.get("limit_price")
    limit_price = None
    if order_type == "limit":
        if limit_price_raw in (None, ""):
            raise PreviewValidationError("limit_price is required for limit orders")
        limit_price = _parse_positive_number(limit_price_raw, "limit_price")
    elif limit_price_raw not in (None, ""):
        raise PreviewValidationError("limit_price is only allowed for limit orders")

    return {
        "market": market,
        "side": side,
        "symbol": symbol,
        "order_type": order_type,
        "quantity": quantity,
        "limit_price": limit_price,
    }


def validate_fx_preview_params(params: dict[str, Any]) -> dict[str, Any]:
    side = str(params.get("side") or "").strip().lower()
    if side not in FX_SIDES:
        raise PreviewValidationError(f"side must be one of: {', '.join(sorted(FX_SIDES))}")

    provided_amounts = [
        (field, value)
        for field, value in (
            ("amount_krw", params.get("amount_krw")),
            ("amount_usd", params.get("amount_usd")),
        )
        if value not in (None, "")
    ]
    if not provided_amounts:
        raise PreviewValidationError("exactly one of amount_krw or amount_usd is required")
    if len(provided_amounts) > 1:
        raise PreviewValidationError("amount_krw and amount_usd cannot be provided together")

    amount_field, raw_value = provided_amounts[0]
    return {
        "side": side,
        "amount_field": amount_field,
        "amount": _parse_positive_number(raw_value, amount_field),
    }


def _parse_positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise PreviewValidationError(f"{field} must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise PreviewValidationError(f"{field} must be a positive integer") from exc
    if parsed <= 0 or str(parsed) != str(value).strip():
        raise PreviewValidationError(f"{field} must be a positive integer")
    return parsed


def _parse_positive_number(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise PreviewValidationError(f"{field} must be a positive number")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise PreviewValidationError(f"{field} must be a positive number") from exc
    if parsed <= 0:
        raise PreviewValidationError(f"{field} must be a positive number")
    return parsed


def classify_health_payload(
    results: list[dict[str, Any]],
    current_url: str | None,
    attached: bool,
    mutation_runtime_state: dict[str, bool] | None = None,
) -> tuple[str, dict[str, Any]]:
    logged_out = is_logged_out(current_url)
    account_list_ok = _endpoint_ok(results, "account_list")
    overview_ok = _endpoint_ok(results, "account_overview")
    positions_ok = _endpoint_ok(results, "asset_sections_v2")
    completed_orders_ok = _endpoint_ok(results, "completed_orders_us_probe")
    quote_ok = _endpoint_ok(results, "quote_probe")
    fx_rate_ok = _endpoint_ok(results, "fx_rate_probe")
    fx_buy_quote_ok = _endpoint_ok(results, "fx_quote_for_buy_probe")
    fx_sell_quote_ok = _endpoint_ok(results, "fx_quote_for_sell_probe")
    web_ready = (account_list_ok or overview_ok or positions_ok) and not logged_out
    order_preview_ready = overview_ok and quote_ok and not logged_out
    fx_preview_ready = overview_ok and fx_rate_ok and fx_buy_quote_ok and fx_sell_quote_ok and not logged_out
    runtime_state = mutation_runtime_state or {}
    post_submit_verify_ready = (
        overview_ok
        and positions_ok
        and completed_orders_ok
        and not logged_out
        and runtime_state.get("verify_path_discovered", False)
    )
    order_submit_ready = (
        order_preview_ready
        and post_submit_verify_ready
        and runtime_state.get("submit_path_discovered", False)
        and runtime_state.get("final_submit_enabled", False)
        and runtime_state.get("journal_writable", False)
        and runtime_state.get("inflight_available", False)
    )

    capabilities = {
        "browser_attached": attached,
        "web_session_ready": web_ready,
        "wts_api_ready": account_list_ok and not logged_out,
        "wts_cert_api_ready": (overview_ok or positions_ok) and not logged_out,
        "account_summary_ready": overview_ok and not logged_out,
        "positions_ready": positions_ok and not logged_out,
        "completed_orders_ready": completed_orders_ok and not logged_out,
        "quote_ready": quote_ok,
        "order_preview_ready": order_preview_ready,
        "order_submit_ready": order_submit_ready,
        "post_submit_verify_ready": post_submit_verify_ready,
        "fx_preview_ready": fx_preview_ready,
    }
    for capability_name in MUTATION_CAPABILITIES:
        capabilities.setdefault(capability_name, False)
    payload = {
        "attached": attached,
        "current_url": current_url,
        "profile_name": "toss-bridge",
        "session_state": "attached_but_logged_out" if logged_out else "attached",
        "capabilities": capabilities,
    }
    capability = "attached_but_logged_out" if logged_out else "browser_attached"
    return capability, payload


def _endpoint_ok(results: list[dict[str, Any]], name: str) -> bool:
    return next((bool(item.get("ok")) for item in results if item.get("name") == name), False)


def is_logged_out(url: str | None) -> bool:
    if not url:
        return True
    return "/signin" in url


def _env_flag(name: str) -> bool:
    return str(os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def resolve_final_submit_state() -> tuple[bool, str]:
    requested = _env_flag(FINAL_SUBMIT_ENABLE_ENV)
    under_pytest = bool(os.environ.get("PYTEST_CURRENT_TEST"))
    allow_test = _env_flag(FINAL_SUBMIT_TEST_BYPASS_ENV)
    if not requested:
        return False, "disabled_by_default"
    if under_pytest and not allow_test:
        return False, "blocked_in_pytest"
    return True, "enabled_by_env"


@dataclass
class QueryContext:
    checked_at: str
    endpoint_matrix: list[dict[str, Any]]
    last_errors: list[str]


class TossBridgeRuntime:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._shutdown_server: HTTPServer | None = None
        self._playwright = None
        self._context = None
        self._page: Page | None = None
        self._last_errors: list[str] = []
        self._last_endpoint_matrix: list[dict[str, Any]] = []
        self._mutation_inflight = False
        self._submit_path_discovered = True
        self._verify_path_discovered = True
        self._final_submit_enabled, self._final_submit_guard_reason = resolve_final_submit_state()
        self._verify_poll_attempts = 3
        self._verify_poll_delay_seconds = 1.0

    def bind_server(self, server: HTTPServer) -> None:
        self._shutdown_server = server

    def start_browser(self) -> None:
        with self._lock:
            if self._context is not None:
                return
            ensure_runtime_dirs()
            self._playwright = sync_playwright().start()
            self._context = self._playwright.chromium.launch_persistent_context(
                str(PROFILE_DIR),
                channel="chrome",
                headless=False,
                viewport={"width": 1440, "height": 960},
                args=["--window-size=1440,960"],
            )
            if self._context.pages:
                self._page = self._context.pages[0]
            else:
                self._page = self._context.new_page()
            self._page.goto(ACCOUNT_URL, wait_until="domcontentloaded")

    def stop_browser(self) -> None:
        with self._lock:
            if self._context is not None:
                self._context.close()
                self._context = None
                self._page = None
            if self._playwright is not None:
                self._playwright.stop()
                self._playwright = None

    def ensure_page(self) -> Page:
        self.start_browser()
        assert self._context is not None
        if self._page is None or self._page.is_closed():
            self._page = self._context.new_page()
        if not self._page.url.startswith("https://www.tossinvest.com"):
            self._page.goto(ACCOUNT_URL, wait_until="domcontentloaded")
        return self._page

    def execute(self, kind: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            if kind == "health":
                return self.health()
            if kind == "open_login":
                return self.open_login()
            if kind == "reconnect":
                return self.reconnect()
            if kind == "shutdown":
                return self.shutdown()
            if kind == "account_summary":
                return self.account_summary()
            if kind == "positions":
                return self.positions()
            if kind == "completed_orders":
                return self.completed_orders(params or {})
            if kind == "quote":
                return self.quote(params or {})
            if kind == "order_preview":
                return self.order_preview(params or {})
            if kind == "fx_preview":
                return self.fx_preview(params or {})
            if kind == "place_order":
                return self.place_order(params or {})
            if kind == "verify_order":
                return self.verify_order(params or {})
            raise ValueError(f"unsupported kind: {kind}")

    def open_login(self) -> dict[str, Any]:
        page = self.ensure_page()
        page.bring_to_front()
        page.goto(ACCOUNT_URL, wait_until="domcontentloaded")
        return {
            "ok": True,
            "kind": "open_login",
            "source": SOURCE,
            "checked_at": now_kst(),
            "capability": "browser_attached",
            "data": {"current_url": page.url, "profile_path": str(PROFILE_DIR)},
            "diagnostics": {"endpoint_matrix": [], "last_errors": list(self._last_errors)},
        }

    def reconnect(self) -> dict[str, Any]:
        self.stop_browser()
        self.start_browser()
        return self.health()

    def shutdown(self) -> dict[str, Any]:
        self.stop_browser()
        if self._shutdown_server is not None:
            threading.Thread(target=self._shutdown_server.shutdown, daemon=True).start()
        return {
            "ok": True,
            "kind": "shutdown",
            "source": SOURCE,
            "checked_at": now_kst(),
            "capability": "browser_attached",
            "data": {"message": "daemon shutting down"},
            "diagnostics": {"endpoint_matrix": [], "last_errors": list(self._last_errors)},
        }

    def _fetch_many(self, requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        page = self.ensure_page()
        try:
            results = page.evaluate(
                r"""
                async (requests) => {
                  const xsrfPattern = new RegExp("(?:^|; )" + "XSRF" + "-TOKEN=([^;]+)");
                  const xsrf = decodeURIComponent((document.cookie.match(xsrfPattern) || [])[1] || "");
                  const browserTabId =
                    sessionStorage.getItem("WTS-BROWSER-TAB-ID") ||
                    localStorage.getItem("qr-tabId") ||
                    "";
                  const needsAppVersion = requests.some((req) => !!req.include_app_version);
                  let appVersion = "";
                  if (needsAppVersion) {
                    const mainScript = [...document.querySelectorAll("script[src]")]
                      .map((node) => node.src)
                      .find((src) => src.includes("/_next/static/chunks/main-"));
                    if (mainScript) {
                      try {
                        const js = await fetch(mainScript, {credentials: "include"}).then((resp) => resp.text());
                        const match = js.match(/v\d{6}\.\d{4}/);
                        if (match) appVersion = match[0];
                      } catch (error) {}
                    }
                  }
                  const baseHeaders = {"Accept": "application/json"};
                  if (xsrf) baseHeaders["X-XSRF-TOKEN"] = xsrf;
                  if (browserTabId) baseHeaders["Browser-Tab-Id"] = browserTabId;
                  const output = [];
                  for (const req of requests) {
                    const headers = {...baseHeaders, ...(req.headers || {})};
                    if (req.include_app_version && appVersion) {
                      headers["App-Version"] = appVersion;
                    }
                    const init = {
                      method: req.method,
                      credentials: "include",
                      headers,
                    };
                    if (req.body !== undefined) {
                      init.body = JSON.stringify(req.body);
                      init.headers["Content-Type"] = "application/json";
                    }
                    try {
                      const resp = await fetch(req.url, init);
                      const text = await resp.text();
                      let json = null;
                      try { json = JSON.parse(text); } catch (e) {}
                      output.push({
                        name: req.name,
                        method: req.method,
                        path: req.path,
                        status_code: resp.status,
                        ok: resp.ok,
                        json,
                        text,
                        error: null
                      });
                    } catch (error) {
                      output.push({
                        name: req.name,
                        method: req.method,
                        path: req.path,
                        status_code: 0,
                        ok: false,
                        json: null,
                        text: "",
                        error: String(error)
                      });
                    }
                  }
                  return output;
                }
                """,
                requests,
            )
        except PlaywrightTimeoutError as exc:
            raise RuntimeError(f"browser request timed out: {exc}") from exc

        self._last_endpoint_matrix = [sanitize_endpoint_entry(item) for item in results]
        self._last_errors = [
            f"{item['name']}: {item['status_code'] or item['error']}"
            for item in results
            if not item.get("ok")
        ]
        return results

    def _make_context(self, results: list[dict[str, Any]]) -> QueryContext:
        checked_at = now_kst()
        return QueryContext(
            checked_at=checked_at,
            endpoint_matrix=[sanitize_endpoint_entry(item) for item in results],
            last_errors=list(self._last_errors),
        )

    def health(self) -> dict[str, Any]:
        page = self.ensure_page()
        probes = [
            ACCOUNT_LIST_ENDPOINT,
            SUMMARY_ENDPOINTS[0],
            POSITIONS_ENDPOINT,
            {
                "name": "completed_orders_us_probe",
                "method": "GET",
                "url": f"https://wts-cert-api.tossinvest.com/api/v2/trading/my-orders/markets/us/by-date/completed?range.from={datetime.now(KST).replace(day=1).strftime('%Y-%m-%d')}&range.to={datetime.now(KST).strftime('%Y-%m-%d')}&size=1&number=1",
                "path": "/api/v2/trading/my-orders/markets/us/by-date/completed",
                "include_app_version": True,
            },
            QUOTE_PROBE_ENDPOINT,
            FX_RATE_ENDPOINT,
            FX_BUY_QUOTE_ENDPOINT,
            FX_SELL_QUOTE_ENDPOINT,
        ]
        results = self._fetch_many(probes)
        context = self._make_context(results)
        capability, payload = classify_health_payload(
            results,
            current_url=page.url,
            attached=True,
            mutation_runtime_state=self._mutation_runtime_state(),
        )
        return {
            "ok": True,
            "kind": "health",
            "source": SOURCE,
            "checked_at": context.checked_at,
            "capability": capability,
            "data": payload,
            "diagnostics": {
                "endpoint_matrix": context.endpoint_matrix,
                "last_errors": context.last_errors,
            },
        }

    def account_summary(self) -> dict[str, Any]:
        page = self.ensure_page()
        if is_logged_out(page.url):
            context = self._make_context([])
            return self._error_response(
                "account_summary",
                "account_summary_ready",
                "browser attached but logged out",
                context,
                code="logged_out",
            )
        results = self._fetch_many(SUMMARY_ENDPOINTS)
        context = self._make_context(results)
        by_name = {item["name"]: item for item in results}
        required_ok = all(by_name[name]["ok"] for name in ["account_overview", "cached_orderable_amount"])
        if not required_ok:
            return self._error_response(
                "account_summary",
                "account_summary_ready",
                "account summary fetch failed",
                context,
            )

        overview = by_name["account_overview"]["json"]["result"]
        cached = by_name["cached_orderable_amount"]["json"]["result"]
        account_id = masked_account_id(overview.get("accountNo"))
        orderable_krw = max(
            ((cached.get("orderableAmountKr") or {}).get("krw")) or 0,
            ((cached.get("orderableAmountUs") or {}).get("krw")) or 0,
        )
        orderable_usd = max(
            ((cached.get("orderableAmountKr") or {}).get("usd")) or 0,
            ((cached.get("orderableAmountUs") or {}).get("usd")) or 0,
        )
        data = {
            "account_id": account_id,
            "label": "토스증권_위탁",
            "total_asset_krw": overview.get("totalAssetAmount"),
            "orderable_krw": orderable_krw,
            "orderable_usd": orderable_usd,
            "markets": self._sanitize_markets(overview.get("overviewByMarket", {})),
            "sync_status": "ok",
            "last_verified_at": context.checked_at,
        }
        return {
            "ok": True,
            "kind": "account_summary",
            "source": SOURCE,
            "checked_at": context.checked_at,
            "capability": "account_summary_ready",
            "data": data,
            "diagnostics": {
                "endpoint_matrix": context.endpoint_matrix,
                "last_errors": context.last_errors,
            },
        }

    def positions(self) -> dict[str, Any]:
        page = self.ensure_page()
        if is_logged_out(page.url):
            context = self._make_context([])
            return self._error_response(
                "positions",
                "positions_ready",
                "browser attached but logged out",
                context,
                code="logged_out",
            )
        results = self._fetch_many([POSITIONS_ENDPOINT])
        context = self._make_context(results)
        sections_response = results[0]
        if not sections_response["ok"]:
            return self._error_response(
                "positions",
                "positions_ready",
                "positions fetch failed",
                context,
            )
        result = sections_response["json"]["result"]
        sections = result.get("sections", [])
        overview = next((section for section in sections if section.get("type") == "SORTED_OVERVIEW"), None)
        if overview is None:
            return self._error_response(
                "positions",
                "positions_ready",
                "SORTED_OVERVIEW section not found",
                context,
            )
        products = (overview.get("data") or {}).get("products", [])
        positions: list[dict[str, Any]] = []
        for product in products:
            market_type = product.get("marketType")
            for item in product.get("items", []):
                symbol = item.get("stockSymbol") or item.get("stockCode")
                native_currency = self._native_currency(product.get("marketType"), item.get("currentPrice"))
                current_price = self._money(item.get("currentPrice"), native_currency)
                average_price = self._money(item.get("purchasePrice"), native_currency)
                market_value = self._money(item.get("evaluatedAmount"), native_currency)
                pnl = self._money(item.get("profitLossAmount"), native_currency)
                positions.append(
                    {
                        "account_id": "toss:primary",
                        "ticker": symbol,
                        "name": item.get("stockName"),
                        "quantity": item.get("quantity"),
                        "currency": native_currency,
                        "market_type": market_type,
                        "market_code": item.get("marketCode"),
                        "cost_basis": {
                            "avg_native": average_price,
                        },
                        "market_data": {
                            "current_price_native": current_price,
                            "market_value_native": market_value,
                            "unrealized_pnl_native": pnl,
                            "unrealized_pnl_rate_pct": self._money(item.get("profitLossRate"), native_currency),
                        },
                    }
                )
        return {
            "ok": True,
            "kind": "positions",
            "source": SOURCE,
            "checked_at": context.checked_at,
            "capability": "positions_ready",
            "data": {
                "account_id": "toss:primary",
                "positions": positions,
            },
            "diagnostics": {
                "endpoint_matrix": context.endpoint_matrix,
                "last_errors": context.last_errors,
            },
        }

    def completed_orders(self, params: dict[str, Any]) -> dict[str, Any]:
        page = self.ensure_page()
        if is_logged_out(page.url):
            context = self._make_context([])
            return self._error_response(
                "completed_orders",
                "completed_orders_ready",
                "browser attached but logged out",
                context,
                code="logged_out",
            )
        market = str(params.get("market") or "all").lower()
        limit = int(params.get("limit") or 50)
        today = datetime.now(KST)
        from_date = today.replace(day=1).strftime("%Y-%m-%d")
        to_date = today.strftime("%Y-%m-%d")
        markets = ["us", "kr"] if market == "all" else [market]
        requests = []
        for entry in markets:
            requests.append(
                {
                    "name": f"completed_orders_{entry}",
                    "method": "GET",
                    "url": f"https://wts-cert-api.tossinvest.com/api/v2/trading/my-orders/markets/{entry}/by-date/completed?range.from={from_date}&range.to={to_date}&size={limit}&number=1",
                    "path": f"/api/v2/trading/my-orders/markets/{entry}/by-date/completed",
                    "include_app_version": True,
                }
            )
        results = self._fetch_many(requests)
        context = self._make_context(results)
        if not all(item["ok"] for item in results):
            return self._error_response(
                "completed_orders",
                "completed_orders_ready",
                "completed orders fetch failed",
                context,
            )
        items: list[dict[str, Any]] = []
        for result in results:
            entry_market = result["name"].split("_")[-1]
            body = ((result["json"] or {}).get("result") or {}).get("body") or []
            for raw in body:
                executed_quantity = raw.get("executedQuantity") or 0
                price_krw = self._extract_money(raw.get("averageExecutionPrice"), "krw")
                price_usd = self._extract_money(raw.get("averageExecutionPrice"), "usd")
                if not price_krw:
                    price_krw = self._extract_money(raw.get("orderPrice"), "krw")
                if not price_usd:
                    price_usd = self._extract_money(raw.get("orderPrice"), "usd")
                items.append(
                    {
                        "market": entry_market,
                        "symbol": raw.get("symbol") or raw.get("stockCode"),
                        "name": raw.get("stockName"),
                        "side": raw.get("tradeType"),
                        "shares": executed_quantity or raw.get("orderQuantity"),
                        "price_krw": price_krw,
                        "price_usd": price_usd,
                        "total_krw": (price_krw or 0) * (executed_quantity or 0),
                        "total_usd": (price_usd or 0) * (executed_quantity or 0),
                        "executed_at": raw.get("lastExecutedAt") or raw.get("orderedAt"),
                        "order_type": raw.get("orderMethodType") or raw.get("orderType") or "unknown",
                        "status": raw.get("status"),
                    }
                )
        return {
            "ok": True,
            "kind": "completed_orders",
            "source": SOURCE,
            "checked_at": context.checked_at,
            "capability": "completed_orders_ready",
            "data": {
                "market": market,
                "items": items,
            },
            "diagnostics": {
                "endpoint_matrix": context.endpoint_matrix,
                "last_errors": context.last_errors,
            },
        }

    def quote(self, params: dict[str, Any]) -> dict[str, Any]:
        symbol = str(params.get("symbol") or "").strip()
        if not symbol:
            context = self._make_context([])
            return self._error_response(
                "quote",
                "quote_ready",
                "symbol is required",
                context,
                code="invalid_request",
            )
        product_code = normalize_product_code(symbol)
        requests: list[dict[str, Any]] = []
        if not looks_like_product_code(product_code):
            requests.append(
                {
                    "name": "search_stocks",
                    "method": "POST",
                    "url": "https://wts-info-api.tossinvest.com/api/v2/search/stocks",
                    "path": "/api/v2/search/stocks",
                    "body": {"query": product_code},
                }
            )
        search_results = self._fetch_many(requests) if requests else []
        if search_results:
            context = self._make_context(search_results)
            result = ((search_results[0]["json"] or {}).get("result") or {}).get("stocks") or []
            if not search_results[0]["ok"] or not result:
                return self._error_response(
                    "quote",
                    "quote_ready",
                    f"no product code found for {symbol}",
                    context,
                    code="invalid_request",
                )
            product_code = result[0]["stockCode"]
        info_requests = [
            {
                "name": "stock_info",
                "method": "GET",
                "url": f"https://wts-info-api.tossinvest.com/api/v2/stock-infos/{product_code}",
                "path": f"/api/v2/stock-infos/{product_code}",
            },
            {
                "name": "stock_detail_common",
                "method": "GET",
                "url": f"https://wts-info-api.tossinvest.com/api/v1/stock-detail/ui/{product_code}/common",
                "path": f"/api/v1/stock-detail/ui/{product_code}/common",
            },
            {
                "name": "stock_prices",
                "method": "GET",
                "url": f"https://wts-info-api.tossinvest.com/api/v1/product/stock-prices?meta=true&productCodes={product_code}",
                "path": "/api/v1/product/stock-prices",
            },
        ]
        results = self._fetch_many(info_requests)
        context = self._make_context(results)
        if not all(item["ok"] for item in (results[0], results[2])):
            return self._error_response("quote", "quote_ready", "quote fetch failed", context)
        by_name = {item["name"]: item for item in results}
        info = ((by_name["stock_info"]["json"] or {}).get("result")) or {}
        detail = ((by_name["stock_detail_common"]["json"] or {}).get("result")) or {}
        prices = ((by_name["stock_prices"]["json"] or {}).get("result")) or []
        if not prices:
            return self._error_response("quote", "quote_ready", "no price result returned", context)
        price = prices[0]
        base = price.get("base") or 0
        close = price.get("close") or 0
        change = close - base
        change_rate = (change / base) if base else 0
        return {
            "ok": True,
            "kind": "quote",
            "source": SOURCE,
            "checked_at": context.checked_at,
            "capability": "quote_ready",
            "data": {
                "product_code": price.get("productCode"),
                "symbol": info.get("symbol") or symbol.upper(),
                "name": info.get("name"),
                "market": ((info.get("market") or {}).get("displayName")),
                "market_code": ((info.get("market") or {}).get("code")),
                "currency": price.get("currency") or info.get("currency"),
                "current_price": close,
                "reference_price": base,
                "price_change": change,
                "change_rate_pct": change_rate * 100,
                "volume": price.get("volume"),
                "status": info.get("status"),
                "badge_count": len(detail.get("badges") or []),
                "notice_count": len(detail.get("notices") or []),
                "as_of": context.checked_at,
            },
            "diagnostics": {
                "endpoint_matrix": context.endpoint_matrix,
                "last_errors": context.last_errors,
            },
        }

    def order_preview(self, params: dict[str, Any]) -> dict[str, Any]:
        try:
            normalized = validate_order_preview_params(params)
        except PreviewValidationError as exc:
            raise self._preview_error(
                "order_preview",
                "order_preview_ready",
                "invalid_request",
                str(exc),
            ) from exc

        page = self.ensure_page()
        if is_logged_out(page.url):
            raise self._preview_error(
                "order_preview",
                "order_preview_ready",
                "logged_out",
                "browser attached but logged out",
            )

        summary = self.account_summary()
        self._ensure_preview_dependency("order_preview", "order_preview_ready", summary)

        quote = self.quote({"symbol": normalized["symbol"], "market": normalized["market"]})
        self._ensure_preview_dependency("order_preview", "order_preview_ready", quote)

        positions = None
        if normalized["side"] == "sell":
            positions = self.positions()
            self._ensure_preview_dependency("order_preview", "order_preview_ready", positions)

        context = self._context_from_responses(*(item for item in (summary, quote, positions) if item is not None))

        summary_data = summary["data"]
        quote_data = quote["data"]
        account_id = summary_data["account_id"]
        currency = quote_data.get("currency") or ("USD" if normalized["market"] == "us" else "KRW")
        orderable_cash = summary_data["orderable_usd"] if normalized["market"] == "us" else summary_data["orderable_krw"]
        estimated_unit_price = normalized["limit_price"] if normalized["order_type"] == "limit" else quote_data["current_price"]
        estimated_total_amount = round(float(estimated_unit_price) * normalized["quantity"], 4)
        inferred_market = self._infer_market_bucket(
            quote_data.get("market_code"),
            currency,
            quote_data.get("product_code"),
        )

        warnings: list[dict[str, Any]] = []
        blocking_issues: list[dict[str, Any]] = []
        if normalized["order_type"] == "market":
            warnings.append(
                {
                    "code": "market_order_uses_last_price",
                    "message": "market order preview uses the latest displayed price and can change at submit time",
                }
            )
        if inferred_market and inferred_market != normalized["market"]:
            blocking_issues.append(
                {
                    "code": "market_mismatch",
                    "message": f"resolved product belongs to {inferred_market} market, not {normalized['market']}",
                }
            )

        status_issue = self._market_status_issue(quote_data.get("status"))
        if status_issue is not None:
            target = blocking_issues if status_issue["blocking"] else warnings
            target.append(
                {
                    "code": status_issue["code"],
                    "message": status_issue["message"],
                }
            )

        available_quantity = None
        if normalized["side"] == "buy":
            if orderable_cash < estimated_total_amount:
                blocking_issues.append(
                    {
                        "code": "insufficient_buying_power",
                        "message": f"estimated total {estimated_total_amount} exceeds orderable cash {orderable_cash}",
                    }
                )
        else:
            available_quantity = self._available_position_quantity(positions["data"]["positions"], quote_data)
            if available_quantity < normalized["quantity"]:
                blocking_issues.append(
                    {
                        "code": "insufficient_position_quantity",
                        "message": f"requested quantity {normalized['quantity']} exceeds available position {available_quantity}",
                    }
                )

        preview_state = preview_state_from_blockers(blocking_issues)
        inputs = {
            "market": normalized["market"],
            "side": normalized["side"],
            "symbol": normalized["symbol"],
            "order_type": normalized["order_type"],
            "quantity": normalized["quantity"],
            "limit_price": normalized["limit_price"],
        }
        derived = {
            "product_code": quote_data["product_code"],
            "market_code": quote_data.get("market_code"),
            "currency": currency,
            "market_status": quote_data.get("status"),
            "current_price": quote_data["current_price"],
            "reference_price": quote_data["reference_price"],
            "estimated_unit_price": estimated_unit_price,
            "estimated_total_amount": estimated_total_amount,
            "orderable_cash": orderable_cash,
            "available_quantity": available_quantity,
        }
        submit_candidate = {
            "market": normalized["market"],
            "side": normalized["side"],
            "product_code": quote_data["product_code"],
            "symbol": quote_data["symbol"],
            "order_type": normalized["order_type"],
            "quantity": normalized["quantity"],
            "limit_price": normalized["limit_price"],
            "currency": currency,
            "estimated_total_amount": estimated_total_amount,
        }
        verification_plan = {
            "queries": ["completed_orders", "positions", "account_summary"],
            "expectations": [
                "completed order should appear in recent order history",
                "positions should reflect the requested symbol quantity delta",
                "account summary should reflect cash and orderable amount movement",
            ],
        }
        fingerprint_payload = build_order_preview_fingerprint_payload(
            account_id=account_id,
            inputs=inputs,
            submit_candidate=submit_candidate,
            derived=derived,
        )
        preview_id = make_preview_id()
        preview_fingerprint = build_preview_fingerprint(fingerprint_payload)
        preview_receipt = build_order_preview_receipt(
            preview_id=preview_id,
            preview_fingerprint=preview_fingerprint,
            account_id=account_id,
            inputs=inputs,
            submit_candidate=submit_candidate,
            derived=derived,
            verification_plan=verification_plan,
        )
        confirm_phrase = build_order_confirm_phrase(preview_receipt)

        return {
            "ok": True,
            "kind": "order_preview",
            "source": SOURCE,
            "checked_at": context.checked_at,
            "capability": "order_preview_ready",
            "data": {
                "preview_id": preview_id,
                "preview_fingerprint": preview_fingerprint,
                "preview_state": preview_state,
                "account_id": account_id,
                "market": normalized["market"],
                "warnings": warnings,
                "blocking_issues": blocking_issues,
                "inputs": inputs,
                "derived": derived,
                "submit_candidate": submit_candidate,
                "preview_receipt": preview_receipt,
                "confirm_phrase": confirm_phrase,
                "verification_plan": verification_plan,
            },
            "diagnostics": {
                "endpoint_matrix": context.endpoint_matrix,
                "last_errors": context.last_errors,
            },
        }

    def place_order(self, params: dict[str, Any]) -> dict[str, Any]:
        try:
            normalized = validate_place_order_params(params)
        except MutationValidationError as exc:
            raise self._mutation_error(
                "place_order",
                "order_submit_ready",
                exc.code,
                str(exc),
            ) from exc

        page = self.ensure_page()
        if is_logged_out(page.url):
            raise self._mutation_error(
                "place_order",
                "order_submit_ready",
                "logged_out",
                "browser attached but logged out",
            )
        if self._mutation_inflight:
            raise self._mutation_error(
                "place_order",
                "order_submit_ready",
                "submit_blocked",
                "another mutation is already in flight",
            )
        if not mutation_journal_is_writable(MUTATION_JOURNAL_FILE):
            raise self._mutation_error(
                "place_order",
                "order_submit_ready",
                "capability_not_ready",
                "mutation journal is not writable",
            )
        duplicate = find_recent_mutation_by_preview_fingerprint(
            MUTATION_JOURNAL_FILE,
            normalized["preview_fingerprint"],
        )
        if duplicate is not None:
            raise self._mutation_error(
                "place_order",
                "order_submit_ready",
                "submit_blocked",
                "preview_fingerprint already exists in mutation journal; request a fresh preview before retrying",
            )

        mutation_id = make_mutation_id()
        self._mutation_inflight = True
        try:
            try:
                recheck = self.order_preview(dict(normalized["preview_receipt"]["inputs"]))
            except PreviewDomainError as exc:
                raise self._mutation_error(
                    "place_order",
                    "order_submit_ready",
                    "capability_not_ready" if exc.code == "capability_not_ready" else exc.code,
                    f"request-time preview recheck failed: {exc.message}",
                ) from exc
            recheck_data = recheck["data"]
            if recheck_data["preview_state"] != "preview_ready":
                self._append_place_order_journal(
                    mutation_id=mutation_id,
                    normalized=normalized,
                    submit_state="submit_blocked",
                    verification_state="pending",
                    broker_ack={
                        "status": "preview_recheck_blocked",
                        "message": "request-time preview recheck returned blocking issues",
                        "market": normalized["preview_receipt"]["inputs"]["market"],
                        "symbol": normalized["preview_receipt"]["inputs"]["symbol"],
                        "side": normalized["preview_receipt"]["inputs"]["side"],
                        "quantity": normalized["preview_receipt"]["inputs"]["quantity"],
                        "order_type": normalized["preview_receipt"]["inputs"]["order_type"],
                    },
                )
                raise self._mutation_error(
                    "place_order",
                    "order_submit_ready",
                    "submit_blocked",
                    "request-time preview recheck returned blocking issues",
                    extra_diagnostics={"mutation_id": mutation_id},
                )
            if recheck_data["preview_fingerprint"] != normalized["preview_fingerprint"]:
                self._append_place_order_journal(
                    mutation_id=mutation_id,
                    normalized=normalized,
                    submit_state="submit_blocked",
                    verification_state="pending",
                    broker_ack={
                        "status": "preview_recheck_mismatch",
                        "message": "request-time preview fingerprint drifted from preview_receipt",
                        "market": normalized["preview_receipt"]["inputs"]["market"],
                        "symbol": normalized["preview_receipt"]["inputs"]["symbol"],
                        "side": normalized["preview_receipt"]["inputs"]["side"],
                        "quantity": normalized["preview_receipt"]["inputs"]["quantity"],
                        "order_type": normalized["preview_receipt"]["inputs"]["order_type"],
                    },
                )
                raise self._mutation_error(
                    "place_order",
                    "order_submit_ready",
                    "submit_blocked",
                    "request-time preview fingerprint drifted from preview_receipt",
                    extra_diagnostics={"mutation_id": mutation_id},
                )
            if not self._submit_path_discovered:
                self._append_place_order_journal(
                    mutation_id=mutation_id,
                    normalized=normalized,
                    submit_state="submit_blocked",
                    verification_state="pending",
                    broker_ack={
                        "status": "not_attempted",
                        "message": "submit path discovery not completed",
                        "market": normalized["preview_receipt"]["inputs"]["market"],
                        "symbol": normalized["preview_receipt"]["inputs"]["symbol"],
                        "side": normalized["preview_receipt"]["inputs"]["side"],
                        "quantity": normalized["preview_receipt"]["inputs"]["quantity"],
                        "order_type": normalized["preview_receipt"]["inputs"]["order_type"],
                    },
                )
                raise self._mutation_error(
                    "place_order",
                    "order_submit_ready",
                    "capability_not_ready",
                    "order submit path discovery is not completed yet",
                    extra_diagnostics={"mutation_id": mutation_id},
                )

            preflight = self._run_prepare_preflight(normalized)

            if not self._final_submit_enabled:
                self._append_place_order_journal(
                    mutation_id=mutation_id,
                    normalized=normalized,
                    submit_state="submit_blocked",
                    verification_state="pending",
                    broker_ack={
                        "status": "prepared",
                        "code": "PREPARED",
                        "message": preflight["message"],
                        "guard_reason": self._final_submit_guard_reason,
                        "market": normalized["preview_receipt"]["inputs"]["market"],
                        "symbol": normalized["preview_receipt"]["inputs"]["symbol"],
                        "side": normalized["preview_receipt"]["inputs"]["side"],
                        "quantity": normalized["preview_receipt"]["inputs"]["quantity"],
                        "order_type": normalized["preview_receipt"]["inputs"]["order_type"],
                    },
                )
                raise self._mutation_error(
                    "place_order",
                    "order_submit_ready",
                    "capability_not_ready",
                    f"final submit is disabled ({self._final_submit_guard_reason}); prepare preflight succeeded",
                    preflight["context"],
                    extra_diagnostics={"mutation_id": mutation_id},
                )

            broker_ack, broker_context = self._run_broker_create(normalized, preflight)
            submit_state = "submitted" if broker_ack.get("status") == "submitted" else "broker_rejected"
            self._append_place_order_journal(
                mutation_id=mutation_id,
                normalized=normalized,
                submit_state=submit_state,
                verification_state="pending",
                broker_ack=broker_ack,
            )

            data: dict[str, Any] = {
                "mutation_id": mutation_id,
                "submit_state": submit_state,
                "verification_state": "pending",
                "broker_ack": broker_ack,
            }
            if normalized.get("auto_verify") and submit_state == "submitted":
                try:
                    verify_payload = self.verify_order({"mutation_id": mutation_id})
                except MutationDomainError as exc:
                    data["auto_verify_error"] = {"code": exc.code, "message": exc.message}
                else:
                    verify_data = verify_payload.get("data") or {}
                    data["verification_state"] = verify_data.get("verification_state") or "pending"
                    if "verify_snapshot" in verify_data:
                        data["verify_snapshot"] = verify_data["verify_snapshot"]
            return {
                "ok": True,
                "kind": "place_order",
                "source": SOURCE,
                "checked_at": broker_context.checked_at,
                "capability": "order_submit_ready",
                "data": data,
                "diagnostics": {
                    "endpoint_matrix": broker_context.endpoint_matrix,
                    "last_errors": broker_context.last_errors,
                },
            }
        finally:
            self._mutation_inflight = False

    def verify_order(self, params: dict[str, Any]) -> dict[str, Any]:
        try:
            normalized = validate_verify_order_params(params)
        except MutationValidationError as exc:
            raise self._mutation_error(
                "verify_order",
                "post_submit_verify_ready",
                exc.code,
                str(exc),
            ) from exc

        page = self.ensure_page()
        if is_logged_out(page.url):
            raise self._mutation_error(
                "verify_order",
                "post_submit_verify_ready",
                "logged_out",
                "browser attached but logged out",
            )
        entry = find_recent_mutation_by_id(MUTATION_JOURNAL_FILE, normalized["mutation_id"])
        if entry is None:
            raise self._mutation_error(
                "verify_order",
                "post_submit_verify_ready",
                "invalid_request",
                f"mutation_id was not found in mutation journal: {normalized['mutation_id']}",
            )
        if not self._verify_path_discovered:
            raise self._mutation_error(
                "verify_order",
                "post_submit_verify_ready",
                "capability_not_ready",
                f"verify path is not ready for {normalized['mutation_id']}",
                extra_diagnostics={"mutation_id": normalized["mutation_id"]},
            )

        snapshot, context = self._verify_mutation_entry_with_window(entry)
        self._append_verify_order_journal(entry, snapshot)
        return {
            "ok": True,
            "kind": "verify_order",
            "source": SOURCE,
            "checked_at": context.checked_at,
            "capability": "post_submit_verify_ready",
            "data": {
                "mutation_id": entry["mutation_id"],
                "submit_state": entry.get("submit_state"),
                "verification_state": snapshot["status"],
                "broker_ack": entry.get("broker_ack") or {},
                "verify_snapshot": snapshot,
            },
            "diagnostics": {
                "endpoint_matrix": context.endpoint_matrix,
                "last_errors": context.last_errors,
            },
        }

    def fx_preview(self, params: dict[str, Any]) -> dict[str, Any]:
        try:
            normalized = validate_fx_preview_params(params)
        except PreviewValidationError as exc:
            raise self._preview_error(
                "fx_preview",
                "fx_preview_ready",
                "invalid_request",
                str(exc),
            ) from exc

        page = self.ensure_page()
        if is_logged_out(page.url):
            raise self._preview_error(
                "fx_preview",
                "fx_preview_ready",
                "logged_out",
                "browser attached but logged out",
            )

        summary = self.account_summary()
        self._ensure_preview_dependency("fx_preview", "fx_preview_ready", summary)

        fx_results = self._fetch_many([FX_RATE_ENDPOINT, FX_BUY_QUOTE_ENDPOINT, FX_SELL_QUOTE_ENDPOINT])
        fx_context = self._make_context(fx_results)
        if not all(item.get("ok") for item in fx_results):
            raise self._preview_error(
                "fx_preview",
                "fx_preview_ready",
                "capability_not_ready",
                "fx quote fetch failed",
                fx_context,
            )

        context = self._context_from_responses(summary, {"diagnostics": fx_context.__dict__})
        by_name = {item["name"]: item for item in fx_results}
        market_rate = ((by_name["fx_rate_probe"].get("json") or {}).get("result")) or {}
        buy_quote = ((by_name["fx_quote_for_buy_probe"].get("json") or {}).get("result")) or {}
        sell_quote = ((by_name["fx_quote_for_sell_probe"].get("json") or {}).get("result")) or {}
        if not market_rate or not buy_quote or not sell_quote:
            raise self._preview_error(
                "fx_preview",
                "fx_preview_ready",
                "preview_failed",
                "fx quote response was missing required fields",
                context,
            )

        summary_data = summary["data"]
        account_id = summary_data["account_id"]
        source_currency = "KRW" if normalized["side"] == "buy" else "USD"
        target_currency = "USD" if normalized["side"] == "buy" else "KRW"
        source_balance = summary_data["orderable_krw"] if source_currency == "KRW" else summary_data["orderable_usd"]
        selected_quote = buy_quote if normalized["side"] == "buy" else sell_quote
        selected_rate = float(selected_quote["usdRate"])
        reference_rate = float(market_rate.get("close") or selected_quote.get("displayUsdRate") or selected_rate)

        if normalized["amount_field"] == "amount_krw":
            source_amount = float(normalized["amount"]) if source_currency == "KRW" else float(normalized["amount"]) / selected_rate
            target_amount = float(normalized["amount"]) / selected_rate if target_currency == "USD" else float(normalized["amount"])
        else:
            source_amount = float(normalized["amount"]) * selected_rate if source_currency == "KRW" else float(normalized["amount"])
            target_amount = float(normalized["amount"]) if target_currency == "USD" else float(normalized["amount"]) * selected_rate

        spread_amount = abs(float(buy_quote["usdRate"]) - float(sell_quote["usdRate"]))
        spread_pct = (spread_amount / reference_rate * 100) if reference_rate else 0.0
        warnings: list[dict[str, Any]] = []
        blocking_issues: list[dict[str, Any]] = []

        if source_amount > float(source_balance):
            blocking_issues.append(
                {
                    "code": "insufficient_fx_balance",
                    "message": f"required {source_currency} amount {round(source_amount, 4)} exceeds available balance {source_balance}",
                }
            )
        valid_till = selected_quote.get("validTill")
        if valid_till:
            warnings.append(
                {
                    "code": "quote_expires_soon",
                    "message": f"fx quote is only valid until {valid_till}",
                }
            )
        if spread_pct > 0:
            warnings.append(
                {
                    "code": "fx_spread_applied",
                    "message": f"buy/sell quote spread is {round(spread_pct, 4)}%",
                }
            )

        preview_state = preview_state_from_blockers(blocking_issues)
        amount_krw = round(source_amount if source_currency == "KRW" else target_amount, 4)
        amount_usd = round(target_amount if target_currency == "USD" else source_amount, 8)
        inputs = {
            "side": normalized["side"],
            "amount_field": normalized["amount_field"],
            "amount": float(normalized["amount"]),
        }
        derived = {
            "source_currency": source_currency,
            "target_currency": target_currency,
            "source_balance": source_balance,
            "source_amount": round(source_amount, 4),
            "target_amount": round(target_amount, 8 if target_currency == "USD" else 4),
            "market_reference_rate": reference_rate,
            "applied_rate": selected_rate,
            "buy_rate": float(buy_quote["usdRate"]),
            "sell_rate": float(sell_quote["usdRate"]),
            "spread_amount": round(spread_amount, 8),
            "spread_pct": round(spread_pct, 6),
            "favorable_percent": selected_quote.get("favorablePercent"),
            "round": selected_quote.get("round"),
            "valid_from": selected_quote.get("validFrom"),
            "valid_till": valid_till,
        }
        submit_candidate = {
            "side": normalized["side"],
            "buy_currency": selected_quote.get("buyCurrency"),
            "sell_currency": selected_quote.get("sellCurrency"),
            "rate_quote_id": selected_quote.get("rateQuoteId"),
            "usd_rate": selected_rate,
            "amount_krw": amount_krw,
            "amount_usd": amount_usd,
        }
        verification_plan = {
            "queries": ["account_summary"],
            "expectations": [
                "account summary should reflect KRW and USD orderable balance movement after exchange submit",
            ],
        }
        fingerprint_payload = {
            "kind": "fx_preview",
            "inputs": inputs,
            "account_id": account_id,
            "submit_candidate": submit_candidate,
            "derived": {
                "source_currency": derived["source_currency"],
                "target_currency": derived["target_currency"],
                "source_amount": derived["source_amount"],
                "target_amount": derived["target_amount"],
                "applied_rate": derived["applied_rate"],
                "market_reference_rate": derived["market_reference_rate"],
                "favorable_percent": derived["favorable_percent"],
                "round": derived["round"],
            },
        }

        return {
            "ok": True,
            "kind": "fx_preview",
            "source": SOURCE,
            "checked_at": context.checked_at,
            "capability": "fx_preview_ready",
            "data": {
                "preview_id": make_preview_id(),
                "preview_fingerprint": build_preview_fingerprint(fingerprint_payload),
                "preview_state": preview_state,
                "account_id": account_id,
                "warnings": warnings,
                "blocking_issues": blocking_issues,
                "inputs": inputs,
                "derived": derived,
                "submit_candidate": submit_candidate,
                "verification_plan": verification_plan,
            },
            "diagnostics": {
                "endpoint_matrix": context.endpoint_matrix,
                "last_errors": context.last_errors,
            },
        }

    def diagnostics(self) -> dict[str, Any]:
        return {
            "ok": True,
            "kind": "diagnostics",
            "source": SOURCE,
            "checked_at": now_kst(),
            "capability": "browser_attached",
            "data": {},
            "diagnostics": {
                "endpoint_matrix": list(self._last_endpoint_matrix),
                "last_errors": list(self._last_errors),
                "runtime": {
                    "profile_dir": str(PROFILE_DIR),
                    "log_file": str(LOG_FILE),
                    "pid_file": str(PID_FILE),
                    "mutation_journal_file": str(MUTATION_JOURNAL_FILE),
                    **self._mutation_runtime_state(),
                },
            },
        }

    @staticmethod
    def _money(payload: dict[str, Any] | None, currency: str = "KRW") -> float:
        if not payload:
            return 0.0
        preferred = "usd" if currency == "USD" else "krw"
        fallback = "krw" if preferred == "usd" else "usd"
        if payload.get(preferred) is not None:
            return payload[preferred]
        if payload.get(fallback) is not None:
            return payload[fallback]
        return 0.0

    @staticmethod
    def _native_currency(market_type: str | None, current_price: dict[str, Any] | None) -> str:
        if market_type and market_type.startswith("US"):
            return "USD"
        if current_price and current_price.get("usd") is not None and current_price.get("krw") is None:
            return "USD"
        return "KRW"

    @staticmethod
    def _sanitize_markets(markets: dict[str, Any]) -> dict[str, Any]:
        sanitized: dict[str, Any] = {}
        for key, item in markets.items():
            sanitized[key] = {
                "market": item.get("market"),
                "orderable_amount": item.get("orderableAmount"),
                "pending_buy_order_amount": item.get("pendingBuyOrderAmount"),
                "evaluated_amount": item.get("evaluatedAmount"),
                "principal_amount": item.get("principalAmount"),
                "evaluated_profit_amount": item.get("evaluatedProfitAmount"),
                "profit_rate": item.get("profitRate"),
                "total_asset_amount": item.get("totalAssetAmount"),
            }
        return sanitized

    @staticmethod
    def _extract_money(payload: dict[str, Any] | None, key: str) -> float | None:
        if not payload:
            return None
        value = payload.get(key)
        return value if value is not None else None

    def _preview_error(
        self,
        kind: str,
        capability: str,
        code: str,
        message: str,
        context: QueryContext | None = None,
    ) -> PreviewDomainError:
        active_context = context or self._make_context([])
        return PreviewDomainError(
            kind=kind,
            capability=capability,
            code=code,
            message=message,
            diagnostics={
                "endpoint_matrix": active_context.endpoint_matrix,
                "last_errors": active_context.last_errors,
            },
        )

    def _mutation_error(
        self,
        kind: str,
        capability: str,
        code: str,
        message: str,
        context: QueryContext | None = None,
        extra_diagnostics: dict[str, Any] | None = None,
    ) -> MutationDomainError:
        active_context = context or self._make_context([])
        diagnostics = {
            "endpoint_matrix": active_context.endpoint_matrix,
            "last_errors": active_context.last_errors,
        }
        if extra_diagnostics:
            diagnostics.update(extra_diagnostics)
        return MutationDomainError(
            kind=kind,
            capability=capability,
            code=code,
            message=message,
            diagnostics=diagnostics,
        )

    def _ensure_preview_dependency(self, kind: str, capability: str, payload: dict[str, Any]) -> None:
        if payload.get("ok"):
            return
        error = payload.get("error") or {}
        code = error.get("code") or "capability_not_ready"
        if code not in {"invalid_request", "logged_out", "capability_not_ready", "preview_failed"}:
            code = "capability_not_ready"
        raise PreviewDomainError(
            kind=kind,
            capability=capability,
            code=code,
            message=error.get("message") or f"{kind} dependency failed",
            diagnostics=payload.get("diagnostics") or {"endpoint_matrix": [], "last_errors": []},
        )

    def _context_from_responses(self, *responses: dict[str, Any]) -> QueryContext:
        checked_at = now_kst()
        endpoint_matrix: list[dict[str, Any]] = []
        last_errors: list[str] = []
        for payload in responses:
            diagnostics = payload.get("diagnostics") or {}
            endpoint_matrix.extend(diagnostics.get("endpoint_matrix") or [])
            for item in diagnostics.get("last_errors") or []:
                if item not in last_errors:
                    last_errors.append(item)
        self._last_endpoint_matrix = list(endpoint_matrix)
        self._last_errors = list(last_errors)
        return QueryContext(
            checked_at=checked_at,
            endpoint_matrix=endpoint_matrix,
            last_errors=last_errors,
        )

    @staticmethod
    def _infer_market_bucket(market_code: str | None, currency: str | None, product_code: str | None) -> str | None:
        market_code_value = (market_code or "").upper()
        if market_code_value.startswith("US") or "NASDAQ" in market_code_value or "NYSE" in market_code_value:
            return "us"
        if market_code_value.startswith("KR") or "KOSPI" in market_code_value or "KOSDAQ" in market_code_value:
            return "kr"
        currency_value = (currency or "").upper()
        if currency_value == "USD":
            return "us"
        if currency_value == "KRW":
            return "kr"
        if product_code and str(product_code).startswith("A"):
            return "kr"
        return None

    @staticmethod
    def _market_status_issue(status: str | None) -> dict[str, Any] | None:
        normalized = (status or "").strip().upper()
        if not normalized:
            return None
        if any(token in normalized for token in ("HALT", "SUSPEND", "DELIST", "STOP")):
            return {
                "blocking": True,
                "code": "market_not_tradeable",
                "message": f"market status {status} indicates trading is blocked",
            }
        if normalized not in {"ACTIVE", "NORMAL", "OPEN", "TRADING", "N"}:
            return {
                "blocking": False,
                "code": "market_status_requires_review",
                "message": f"market status {status} requires manual review before submit",
            }
        return None

    @staticmethod
    def _available_position_quantity(positions: list[dict[str, Any]], quote_data: dict[str, Any]) -> int:
        product_code = quote_data.get("product_code")
        symbol = str(quote_data.get("symbol") or "").upper()
        for item in positions:
            ticker = str(item.get("ticker") or "").upper()
            if ticker == symbol or ticker == str(product_code or "").upper():
                return int(item.get("quantity") or 0)
        return 0

    def _error_response(
        self,
        kind: str,
        capability: str,
        message: str,
        context: QueryContext,
        code: str = "capability_not_ready",
    ) -> dict[str, Any]:
        return {
            "ok": False,
            "kind": kind,
            "source": SOURCE,
            "checked_at": context.checked_at,
            "capability": capability,
            "error": {
                "code": code,
                "message": message,
            },
            "diagnostics": {
                "endpoint_matrix": context.endpoint_matrix,
                "last_errors": context.last_errors,
            },
        }

    def _mutation_runtime_state(self) -> dict[str, Any]:
        return {
            "journal_writable": mutation_journal_is_writable(MUTATION_JOURNAL_FILE),
            "submit_path_discovered": self._submit_path_discovered,
            "verify_path_discovered": self._verify_path_discovered,
            "final_submit_enabled": self._final_submit_enabled,
            "final_submit_guard_reason": self._final_submit_guard_reason,
            "inflight_available": not self._mutation_inflight,
            "verify_window_attempts": self._verify_poll_attempts,
        }

    def _append_place_order_journal(
        self,
        *,
        mutation_id: str,
        normalized: dict[str, Any],
        submit_state: str,
        verification_state: str,
        broker_ack: dict[str, Any],
        verify_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        entry = {
            "mutation_id": mutation_id,
            "kind": "place_order",
            "requested_at": now_kst(),
            "preview_fingerprint": normalized["preview_fingerprint"],
            "confirm_phrase_hash": normalized["confirm_phrase_hash"],
            "submit_state": submit_state,
            "verification_state": verification_state,
            "broker_ack": broker_ack,
        }
        if verify_snapshot is not None:
            entry["verify_snapshot"] = verify_snapshot
        return append_mutation_journal(MUTATION_JOURNAL_FILE, entry)

    def _append_verify_order_journal(self, entry: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
        return append_mutation_journal(
            MUTATION_JOURNAL_FILE,
            {
                "mutation_id": entry["mutation_id"],
                "kind": "verify_order",
                "requested_at": now_kst(),
                "preview_fingerprint": entry.get("preview_fingerprint"),
                "confirm_phrase_hash": entry.get("confirm_phrase_hash"),
                "submit_state": entry.get("submit_state"),
                "verification_state": snapshot["status"],
                "broker_ack": entry.get("broker_ack") or {},
                "verify_snapshot": snapshot,
            },
        )

    def _verify_mutation_entry_with_window(self, entry: dict[str, Any]) -> tuple[dict[str, Any], QueryContext]:
        submit_state = str(entry.get("submit_state") or "")
        if submit_state in {"submit_blocked", "broker_rejected", "submit_cancelled"}:
            return self._verify_mutation_entry(entry)

        attempts = max(int(self._verify_poll_attempts), 1)
        delay_seconds = max(float(self._verify_poll_delay_seconds), 0.0)
        last_snapshot: dict[str, Any] | None = None
        last_context: QueryContext | None = None
        for attempt in range(1, attempts + 1):
            snapshot, context = self._verify_mutation_entry(entry)
            if snapshot["status"] != "unknown":
                return snapshot, context
            last_snapshot = snapshot
            last_context = context
            if attempt < attempts and delay_seconds > 0:
                time.sleep(delay_seconds)
        assert last_snapshot is not None
        assert last_context is not None
        last_snapshot = dict(last_snapshot)
        last_snapshot["message"] = (
            f"no matching completed order was found after {attempts} verify attempt(s); "
            "manual follow-up is still required"
        )
        return last_snapshot, last_context

    def _verify_mutation_entry(self, entry: dict[str, Any]) -> tuple[dict[str, Any], QueryContext]:
        submit_state = str(entry.get("submit_state") or "")
        broker_ack = entry.get("broker_ack") or {}
        checked_at = now_kst()
        if submit_state in {"submit_blocked", "broker_rejected", "submit_cancelled"}:
            context = self._make_context([])
            return (
                {
                    "status": "verified_failed",
                    "message": str(broker_ack.get("message") or "mutation did not reach final submit"),
                    "matched_order": None,
                    "position_delta": None,
                    "cash_delta": None,
                    "verified_at": checked_at,
                },
                context,
            )

        market = str(broker_ack.get("market") or "all").lower()
        completed_orders = self.completed_orders({"market": market, "limit": 20})
        positions = self.positions()
        account_summary = self.account_summary()
        context = self._context_from_responses(completed_orders, positions, account_summary)
        for payload in (completed_orders, positions, account_summary):
            if not payload.get("ok"):
                error = payload.get("error") or {}
                raise self._mutation_error(
                    "verify_order",
                    "post_submit_verify_ready",
                    error.get("code") or "capability_not_ready",
                    error.get("message") or "verify dependency failed",
                    context,
                    extra_diagnostics={"mutation_id": entry["mutation_id"]},
                )

        matched_order = self._match_completed_order(entry, completed_orders["data"]["items"])
        symbol = str(broker_ack.get("symbol") or "").upper()
        position_delta = self._build_position_snapshot(symbol, positions["data"]["positions"])
        cash_delta = self._build_cash_snapshot(market, account_summary["data"])
        if matched_order is not None:
            return (
                {
                    "status": "verified_success",
                    "message": "matched completed order in recent order history",
                    "matched_order": matched_order,
                    "position_delta": position_delta,
                    "cash_delta": cash_delta,
                    "verified_at": checked_at,
                },
                context,
            )
        return (
            {
                "status": "unknown",
                "message": "no matching completed order was found in the current verify window",
                "matched_order": None,
                "position_delta": position_delta,
                "cash_delta": cash_delta,
                "verified_at": checked_at,
            },
            context,
        )

    @staticmethod
    def _match_completed_order(entry: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any] | None:
        broker_ack = entry.get("broker_ack") or {}
        target_market = str(broker_ack.get("market") or "").lower()
        target_symbol = str(broker_ack.get("symbol") or "").upper()
        target_side = str(broker_ack.get("side") or "").lower()
        target_quantity = int(broker_ack.get("quantity") or 0)
        for item in items:
            if str(item.get("market") or "").lower() != target_market:
                continue
            if str(item.get("symbol") or "").upper() != target_symbol:
                continue
            if str(item.get("side") or "").lower() != target_side:
                continue
            if int(item.get("shares") or 0) != target_quantity:
                continue
            return {
                "market": item.get("market"),
                "symbol": item.get("symbol"),
                "side": item.get("side"),
                "shares": item.get("shares"),
                "executed_at": item.get("executed_at"),
                "status": item.get("status"),
            }
        return None

    @staticmethod
    def _build_position_snapshot(symbol: str, positions: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not symbol:
            return None
        for item in positions:
            if str(item.get("ticker") or "").upper() == symbol:
                return {
                    "symbol": symbol,
                    "current_quantity": item.get("quantity"),
                }
        return {
            "symbol": symbol,
            "current_quantity": 0,
        }

    @staticmethod
    def _build_cash_snapshot(market: str, account_summary: dict[str, Any]) -> dict[str, Any]:
        if market == "us":
            return {
                "currency": "USD",
                "current_orderable_cash": account_summary.get("orderable_usd"),
            }
        return {
            "currency": "KRW",
            "current_orderable_cash": account_summary.get("orderable_krw"),
        }

    def _run_prepare_preflight(self, normalized: dict[str, Any]) -> dict[str, Any]:
        receipt = normalized["preview_receipt"]
        product_code = str(receipt["submit_candidate"]["product_code"])
        overview_results = self._fetch_many([SUMMARY_ENDPOINTS[0]])
        overview_context = self._make_context(overview_results)
        if not overview_results[0]["ok"]:
            raise self._mutation_error(
                "place_order",
                "order_submit_ready",
                "capability_not_ready",
                "account overview fetch failed during prepare preflight",
                overview_context,
            )
        account_no = str((((overview_results[0]["json"] or {}).get("result")) or {}).get("accountNo") or "").strip()
        if not account_no:
            raise self._mutation_error(
                "place_order",
                "order_submit_ready",
                "capability_not_ready",
                "account overview did not return accountNo for prepare preflight",
                overview_context,
            )

        submit_market = self._resolve_prepare_market(receipt)
        currency_mode, allow_auto_exchange = self._resolve_prepare_cash_mode(receipt)
        prepare_payload = build_order_prepare_payload(
            receipt,
            submit_market=submit_market,
            currency_mode=currency_mode,
            allow_auto_exchange=allow_auto_exchange,
        )
        prepare_requests = [
            {
                "name": "order_prerequisite",
                "method": "GET",
                "url": f"https://wts-cert-api.tossinvest.com/api/v2/trading/order/{product_code}/prerequisite",
                "path": f"/api/v2/trading/order/{product_code}/prerequisite",
                "headers": {"X-Tossinvest-Account": account_no},
                "include_app_version": True,
            },
            {
                **TRADE_WITHOUT_CONFIRM_ENDPOINT,
                "headers": {"X-Tossinvest-Account": account_no},
            },
            {
                "name": "order_prepare",
                "method": "POST",
                "url": "https://wts-cert-api.tossinvest.com/api/v2/wts/trading/order/prepare",
                "path": "/api/v2/wts/trading/order/prepare",
                "headers": {"X-Tossinvest-Account": account_no},
                "include_app_version": True,
                "body": prepare_payload,
            },
        ]
        results = self._fetch_many(prepare_requests)
        context = self._make_context(results)
        by_name = {item["name"]: item for item in results}
        prerequisite = by_name["order_prerequisite"]
        if not prerequisite["ok"]:
            raise self._mutation_error(
                "place_order",
                "order_submit_ready",
                "capability_not_ready",
                "order prerequisite fetch failed during prepare preflight",
                context,
            )
        prepare_result = by_name["order_prepare"]
        if not prepare_result["ok"]:
            prepare_message = self._extract_prepare_error_message(prepare_result)
            raise self._mutation_error(
                "place_order",
                "order_submit_ready",
                "submit_blocked",
                prepare_message,
                context,
            )
        prepare_body = ((prepare_result.get("json") or {}).get("result")) or {}
        prepared_order_info = prepare_body.get("preparedOrderInfo") or {}
        if not prepared_order_info:
            raise self._mutation_error(
                "place_order",
                "order_submit_ready",
                "submit_blocked",
                "order prepare response was missing preparedOrderInfo",
                context,
            )

        auth_required = prepare_body.get("authRequired") or {}
        if auth_required.get("required") is True:
            raise self._mutation_error(
                "place_order",
                "order_submit_ready",
                "submit_blocked",
                "order prepare requires additional authentication before final submit",
                context,
            )
        verifier = str(auth_required.get("verifier") or "").upper()
        if verifier in {"REQUIRED", "AGAIN_REQUIRED"}:
            raise self._mutation_error(
                "place_order",
                "order_submit_ready",
                "submit_blocked",
                f"order prepare verifier state {verifier} is outside the current guarded scope",
                context,
            )

        drift_issues = build_prepare_drift_issues(
            receipt,
            prepared_order_info,
            compare_price=not allow_auto_exchange,
        )
        if drift_issues:
            raise self._mutation_error(
                "place_order",
                "order_submit_ready",
                "submit_blocked",
                drift_issues[0]["message"],
                context,
            )

        buying_red_flags = prepare_body.get("buyingRedFlags") or []
        if buying_red_flags:
            raise self._mutation_error(
                "place_order",
                "order_submit_ready",
                "submit_blocked",
                "order prepare returned buying red flags that require manual review",
                context,
            )
        if not str(prepare_body.get("orderKey") or "").strip():
            raise self._mutation_error(
                "place_order",
                "order_submit_ready",
                "submit_blocked",
                "order prepare response was missing orderKey",
                context,
            )

        return {
            "message": "prepare preflight succeeded",
            "context": context,
            "account_no": account_no,
            "submit_market": submit_market,
            "currency_mode": currency_mode,
            "allow_auto_exchange": allow_auto_exchange,
            "prepare_payload": prepare_payload,
            "prepare_body": prepare_body,
            "prepared_order_info": prepared_order_info,
        }

    def _run_broker_create(
        self,
        normalized: dict[str, Any],
        preflight: dict[str, Any],
    ) -> tuple[dict[str, Any], QueryContext]:
        """Call POST /api/v2/wts/trading/order/create after prepare preflight succeeded.

        Endpoint URL/body schema captured in Phase 0 P0-02 (HAR diff against
        simulation baseline). Body = prepare_payload minus the ``withOrderKey``
        key; ``orderKey`` is tracked server-side via session cookie.
        """
        prepare_payload = preflight["prepare_payload"]
        create_payload = {key: value for key, value in prepare_payload.items() if key != "withOrderKey"}
        account_no = preflight["account_no"]
        inputs = normalized["preview_receipt"]["inputs"]
        market_label = str(inputs.get("market") or "")
        symbol_label = str(inputs.get("symbol") or "")
        side_label = str(inputs.get("side") or "")
        quantity_label = inputs.get("quantity")
        order_type_label = str(inputs.get("order_type") or "")

        create_request = {
            "name": "order_create",
            "method": "POST",
            "url": "https://wts-cert-api.tossinvest.com/api/v2/wts/trading/order/create",
            "path": "/api/v2/wts/trading/order/create",
            "headers": {"X-Tossinvest-Account": account_no},
            "include_app_version": True,
            "body": create_payload,
        }

        ordered_at = now_kst()
        base_ack = {
            "market": market_label,
            "symbol": symbol_label,
            "side": side_label,
            "quantity": quantity_label,
            "order_type": order_type_label,
        }

        try:
            results = self._fetch_many([create_request])
        except RuntimeError as exc:
            return (
                {
                    **base_ack,
                    "status": "broker_rejected",
                    "code": BROKER_REJECTED_TIMEOUT,
                    "message": str(exc),
                    "ordered_at": ordered_at,
                    "http_status": 0,
                },
                self._make_context([]),
            )

        context = self._make_context(results)
        result = results[0]
        status_code = int(result.get("status_code") or 0)
        body = result.get("json") or {}
        broker_result = body.get("result") or {}

        if not result.get("ok"):
            fetch_error = result.get("error")
            response_message = (
                broker_result.get("message")
                or body.get("message")
                or fetch_error
                or "broker create request failed"
            )
            code = classify_broker_reject(
                message=str(response_message),
                status_code=status_code,
                error=fetch_error,
            )
            return (
                {
                    **base_ack,
                    "status": "broker_rejected",
                    "code": code,
                    "message": str(response_message),
                    "ordered_at": ordered_at,
                    "http_status": status_code,
                },
                context,
            )

        order_id = str(broker_result.get("orderId") or "").strip()
        if not order_id:
            response_message = (
                broker_result.get("message")
                or body.get("message")
                or "broker create response missing orderId"
            )
            code = classify_broker_reject(
                message=str(response_message),
                status_code=status_code,
                error=None,
            )
            return (
                {
                    **base_ack,
                    "status": "broker_rejected",
                    "code": code,
                    "message": str(response_message),
                    "ordered_at": ordered_at,
                    "http_status": status_code,
                },
                context,
            )

        return (
            {
                **base_ack,
                "status": "submitted",
                "code": BROKER_ACK_OK,
                "message": str(broker_result.get("message") or ""),
                "broker_order_id": order_id,
                "order_no": broker_result.get("orderNo"),
                "order_date": broker_result.get("orderDate"),
                "is_reserved": bool(broker_result.get("isReserved") or False),
                "ordered_at": ordered_at,
                "http_status": status_code,
            },
            context,
        )

    @staticmethod
    def _resolve_prepare_market(receipt: dict[str, Any]) -> str:
        market_code = str(((receipt.get("derived") or {}).get("market_code")) or "").upper()
        if "NASDAQ" in market_code:
            return "NSQ"
        if "NYSE" in market_code:
            return "NYS"
        if "AMEX" in market_code or "ARCA" in market_code:
            return "AMX"
        if "KOSPI" in market_code:
            return "KSP"
        if "KOSDAQ" in market_code:
            return "KSQ"
        market = str(((receipt.get("inputs") or {}).get("market")) or "").lower()
        if market == "us":
            return "US_ETC"
        return "KR_ETC"

    @staticmethod
    def _resolve_prepare_cash_mode(receipt: dict[str, Any]) -> tuple[str, bool]:
        market = str(((receipt.get("inputs") or {}).get("market")) or "").lower()
        side = str(((receipt.get("inputs") or {}).get("side")) or "").lower()
        derived_currency = str(((receipt.get("derived") or {}).get("currency")) or "").upper()
        if market == "kr":
            return "KRW", False
        if market == "us" and side == "buy":
            return "KRW", True
        if derived_currency in {"KRW", "USD"}:
            return derived_currency, False
        return "USD", False

    @staticmethod
    def _extract_prepare_error_message(result: dict[str, Any]) -> str:
        payload = result.get("json") or {}
        candidates = [
            ((payload.get("error") or {}).get("message")),
            ((payload.get("error") or {}).get("reason")),
            payload.get("message"),
            (((payload.get("result") or {}).get("message"))),
        ]
        for candidate in candidates:
            if candidate:
                return f"order prepare preflight request failed: {candidate}"
        raw_text = str(result.get("text") or "").strip()
        if raw_text:
            compact = " ".join(raw_text.split())
            return f"order prepare preflight request failed: {compact[:200]}"
        return "order prepare preflight request failed"

class BridgeHandler(BaseHTTPRequestHandler):
    runtime = TossBridgeRuntime()
    bearer_token = ""

    def do_GET(self) -> None:
        if not self._authorize():
            return
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._write_json(self.runtime.health())
            return
        if parsed.path == "/diagnostics":
            self._write_json(self.runtime.diagnostics())
            return
        self._write_error(HTTPStatus.NOT_FOUND, "not_found", "unknown path")

    def do_POST(self) -> None:
        if not self._authorize():
            return
        parsed = urlparse(self.path)
        if parsed.path != "/bridge/query":
            self._write_error(HTTPStatus.NOT_FOUND, "not_found", "unknown path")
            return
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length).decode("utf-8") if content_length else "{}"
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            self._write_error(HTTPStatus.BAD_REQUEST, "invalid_json", "invalid JSON body")
            return
        kind = payload.get("kind")
        params = payload.get("params") or {}
        if not kind:
            self._write_error(HTTPStatus.BAD_REQUEST, "missing_kind", "kind is required")
            return
        try:
            result = self.runtime.execute(kind, params)
        except (PreviewDomainError, MutationDomainError) as exc:
            self._write_json(exc.to_payload(source=SOURCE, checked_at=now_kst()))
            return
        except Exception as exc:  # noqa: BLE001
            self._write_json(
                {
                    "ok": False,
                    "kind": kind,
                    "source": SOURCE,
                    "checked_at": now_kst(),
                    "capability": f"{kind}_ready",
                    "error": {"code": "runtime_error", "message": str(exc)},
                    "diagnostics": {
                        "endpoint_matrix": list(self.runtime._last_endpoint_matrix),
                        "last_errors": list(self.runtime._last_errors),
                    },
                },
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return
        self._write_json(result)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        ensure_runtime_dirs()
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(f"[{now_kst()}] {self.address_string()} {format % args}\n")

    def _authorize(self) -> bool:
        expected = f"Bearer {self.bearer_token}"
        provided = self.headers.get("Authorization", "")
        if provided != expected:
            self._write_error(HTTPStatus.UNAUTHORIZED, "unauthorized", "missing or invalid bearer token")
            return False
        return True

    def _write_error(self, status: HTTPStatus, code: str, message: str) -> None:
        self._write_json(
            {
                "ok": False,
                "source": SOURCE,
                "checked_at": now_kst(),
                "error": {"code": code, "message": message},
            },
            status=status,
        )

    def _write_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_server(port: int = PORT) -> None:
    ensure_runtime_dirs()
    server = HTTPServer((HOST, port), BridgeHandler)
    token = rotate_token()
    BridgeHandler.bearer_token = token
    BridgeHandler.runtime.bind_server(server)
    write_pid(os.getpid())
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        BridgeHandler.runtime.stop_browser()
        clear_runtime_markers()


def main() -> None:
    parser = argparse.ArgumentParser(description="Toss Browser Bridge daemon")
    parser.add_argument("command", choices=["run"], nargs="?", default="run")
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()
    run_server(port=args.port)


if __name__ == "__main__":
    main()
