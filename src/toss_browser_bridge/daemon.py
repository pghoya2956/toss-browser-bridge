from __future__ import annotations

import argparse
import json
import os
import threading
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

ACCOUNT_URL = "https://www.tossinvest.com/account"
KST = ZoneInfo("Asia/Seoul")
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
ACCOUNT_LIST_ENDPOINT = {
    "name": "account_list",
    "method": "GET",
    "url": "https://wts-api.tossinvest.com/api/v1/account/list",
    "path": "/api/v1/account/list",
}


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
                  const xsrf = decodeURIComponent((document.cookie.match(/(?:^|; )XSRF-TOKEN=([^;]+)/) || [])[1] || "");
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

    def _base_capabilities(self) -> dict[str, Any]:
        current_url = self._page.url if self._page and not self._page.is_closed() else None
        attached = self._context is not None and self._page is not None and not self._page.is_closed()
        return {
            "attached": attached,
            "current_url": current_url,
            "profile_name": "toss-bridge",
            "capabilities": {
                "browser_attached": attached,
                "web_session_ready": False,
                "wts_api_ready": False,
                "wts_cert_api_ready": False,
                "account_summary_ready": False,
                "positions_ready": False,
                "completed_orders_ready": False,
                "quote_ready": False,
            },
        }

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
        ]
        results = self._fetch_many(probes)
        context = self._make_context(results)
        payload = self._base_capabilities()
        payload["current_url"] = page.url
        logged_out = self._is_logged_out(page.url)
        payload["session_state"] = "attached_but_logged_out" if logged_out else "attached"

        account_list_ok = next((item["ok"] for item in results if item["name"] == "account_list"), False)
        overview_ok = next((item["ok"] for item in results if item["name"] == "account_overview"), False)
        positions_ok = next((item["ok"] for item in results if item["name"] == "asset_sections_v2"), False)
        completed_orders_ok = next((item["ok"] for item in results if item["name"] == "completed_orders_us_probe"), False)
        quote_ok = next((item["ok"] for item in results if item["name"] == "quote_probe"), False)
        web_ready = (account_list_ok or overview_ok or positions_ok) and not logged_out
        payload["capabilities"].update(
            {
                "web_session_ready": web_ready,
                "wts_api_ready": account_list_ok and not logged_out,
                "wts_cert_api_ready": (overview_ok or positions_ok) and not logged_out,
                "account_summary_ready": overview_ok and not logged_out,
                "positions_ready": positions_ok and not logged_out,
                "completed_orders_ready": completed_orders_ok and not logged_out,
                "quote_ready": quote_ok,
            }
        )
        return {
            "ok": True,
            "kind": "health",
            "source": SOURCE,
            "checked_at": context.checked_at,
            "capability": "attached_but_logged_out" if logged_out else "browser_attached",
            "data": payload,
            "diagnostics": {
                "endpoint_matrix": context.endpoint_matrix,
                "last_errors": context.last_errors,
            },
        }

    def account_summary(self) -> dict[str, Any]:
        page = self.ensure_page()
        if self._is_logged_out(page.url):
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
        if self._is_logged_out(page.url):
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
        if self._is_logged_out(page.url):
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
        product_code = self._normalize_product_code(symbol)
        requests: list[dict[str, Any]] = []
        if not self._looks_like_product_code(product_code):
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

    @staticmethod
    def _normalize_product_code(symbol: str) -> str:
        trimmed = symbol.strip().upper()
        if len(trimmed) == 6 and trimmed.isdigit():
            return f"A{trimmed}"
        return trimmed

    @staticmethod
    def _looks_like_product_code(value: str) -> bool:
        if len(value) == 7 and value.startswith("A") and value[1:].isdigit():
            return True
        if len(value) >= 8 and value[:2].isalpha() and value[2:].isdigit():
            return True
        return False

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

    @staticmethod
    def _is_logged_out(url: str | None) -> bool:
        if not url:
            return True
        return "/signin" in url


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
