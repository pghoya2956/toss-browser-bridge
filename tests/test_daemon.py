from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import HTTPServer
from typing import Any

import pytest

from toss_browser_bridge.daemon import BridgeHandler
from toss_browser_bridge.preview import PreviewDomainError
from toss_browser_bridge.submit import MutationDomainError


class FakeRuntime:
    def __init__(self) -> None:
        self._last_endpoint_matrix = [
            {"name": "account_overview", "method": "GET", "path": "/api/account", "status_code": 500, "ok": False}
        ]
        self._last_errors = ["account_overview: 500"]

    def health(self) -> dict[str, Any]:
        return {"ok": True, "kind": "health"}

    def diagnostics(self) -> dict[str, Any]:
        return {"ok": True, "kind": "diagnostics"}

    def execute(self, kind: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if kind == "explode":
            raise RuntimeError("boom")
        if kind == "preview_invalid":
            raise PreviewDomainError(
                kind="order_preview",
                capability="order_preview_ready",
                code="invalid_request",
                message="order_type is required",
                diagnostics={"endpoint_matrix": [], "last_errors": []},
            )
        if kind == "mutation_blocked":
            raise MutationDomainError(
                kind="place_order",
                capability="order_submit_ready",
                code="capability_not_ready",
                message="order submit path discovery is not completed yet",
                diagnostics={"endpoint_matrix": [], "last_errors": []},
            )
        return {"ok": True, "kind": kind, "params": params or {}}


@pytest.fixture
def daemon_server() -> str:
    original_runtime = BridgeHandler.runtime
    original_token = BridgeHandler.bearer_token
    BridgeHandler.runtime = FakeRuntime()
    BridgeHandler.bearer_token = "test-token"

    server = HTTPServer(("127.0.0.1", 0), BridgeHandler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
        BridgeHandler.runtime = original_runtime
        BridgeHandler.bearer_token = original_token


def _request(
    base_url: str,
    method: str,
    path: str,
    *,
    token: str | None = "test-token",
    body: dict[str, Any] | bytes | None = None,
) -> tuple[int, dict[str, Any]]:
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"

    data = None
    if isinstance(body, dict):
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    elif isinstance(body, bytes):
        headers["Content-Type"] = "application/json"
        data = body

    request = urllib.request.Request(f"{base_url}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_rejects_missing_or_invalid_bearer_token(daemon_server: str) -> None:
    status, payload = _request(daemon_server, "GET", "/health", token="wrong-token")

    assert status == 401
    assert payload["error"] == {
        "code": "unauthorized",
        "message": "missing or invalid bearer token",
    }


def test_rejects_invalid_json_body(daemon_server: str) -> None:
    status, payload = _request(daemon_server, "POST", "/bridge/query", body=b"{not-json")

    assert status == 400
    assert payload["error"] == {
        "code": "invalid_json",
        "message": "invalid JSON body",
    }


def test_rejects_missing_kind(daemon_server: str) -> None:
    status, payload = _request(daemon_server, "POST", "/bridge/query", body={"params": {}})

    assert status == 400
    assert payload["error"] == {
        "code": "missing_kind",
        "message": "kind is required",
    }


def test_returns_runtime_errors_with_diagnostics(daemon_server: str) -> None:
    status, payload = _request(daemon_server, "POST", "/bridge/query", body={"kind": "explode", "params": {}})

    assert status == 500
    assert payload["error"] == {
        "code": "runtime_error",
        "message": "boom",
    }
    assert payload["diagnostics"]["endpoint_matrix"] == [
        {"name": "account_overview", "method": "GET", "path": "/api/account", "status_code": 500, "ok": False}
    ]
    assert payload["diagnostics"]["last_errors"] == ["account_overview: 500"]


def test_returns_preview_domain_errors_with_http_200(daemon_server: str) -> None:
    status, payload = _request(daemon_server, "POST", "/bridge/query", body={"kind": "preview_invalid", "params": {}})

    assert status == 200
    assert payload["error"] == {
        "code": "invalid_request",
        "message": "order_type is required",
    }
    assert payload["capability"] == "order_preview_ready"


def test_returns_mutation_domain_errors_with_http_200(daemon_server: str) -> None:
    status, payload = _request(daemon_server, "POST", "/bridge/query", body={"kind": "mutation_blocked", "params": {}})

    assert status == 200
    assert payload["error"] == {
        "code": "capability_not_ready",
        "message": "order submit path discovery is not completed yet",
    }
    assert payload["capability"] == "order_submit_ready"
