from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from toss_browser_bridge.bridge_lib import (
    HOST,
    PORT,
    TOKEN_FILE,
    ensure_runtime_dirs,
    read_text_if_exists,
    request_json,
    wait_for_port,
)

def resolve_python_executable() -> str:
    executable = sys.executable.strip()
    if not executable:
        raise RuntimeError(
            "current Python interpreter is unavailable; "
            "reinstall toss-browser-bridge or run toss-bridge-daemon manually"
        )
    if not Path(executable).exists():
        raise RuntimeError(
            f"current Python interpreter does not exist: {executable}; "
            "reinstall toss-browser-bridge or run toss-bridge-daemon manually"
        )
    return executable


def build_daemon_command() -> list[str]:
    return [
        resolve_python_executable(),
        "-m",
        "toss_browser_bridge.daemon",
        "run",
        "--port",
        str(PORT),
    ]


def ensure_daemon_running() -> str:
    ensure_runtime_dirs()
    token = read_text_if_exists(TOKEN_FILE)
    if token and wait_for_port(timeout=0.75):
        return token

    if not token and wait_for_port(timeout=0.75):
        raise RuntimeError(
            f"port {PORT} is already in use by another process; "
            "set TOSS_BRIDGE_PORT or stop the conflicting daemon"
        )

    cmd = build_daemon_command()
    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        raise RuntimeError(
            "bridge daemon failed to launch with the installed Python environment; "
            "reinstall toss-browser-bridge or run toss-bridge-daemon manually"
        ) from exc
    if not wait_for_port(timeout=20.0):
        raise RuntimeError(
            f"bridge daemon did not start on {HOST}:{PORT}; "
            "check Chrome/Playwright prerequisites or run toss-bridge-daemon manually"
        )
    token = read_text_if_exists(TOKEN_FILE)
    if not token:
        raise RuntimeError(
            "bridge token file was not created; "
            "check daemon startup logs or run toss-bridge-daemon manually"
        )
    return token


def invoke(kind: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    token = ensure_daemon_running()
    method = "GET" if kind in {"health", "diagnostics"} else "POST"
    path = "/health" if kind == "health" else "/diagnostics" if kind == "diagnostics" else "/bridge/query"
    payload = None if method == "GET" else {"kind": kind, "params": params or {}}
    try:
        return request_json(method, path, payload, token=token)
    except RuntimeError as exc:
        refreshed = read_text_if_exists(TOKEN_FILE)
        if refreshed and refreshed != token and "bridge http 401" in str(exc):
            return request_json(method, path, payload, token=refreshed)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Toss Browser Bridge client")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("health")
    sub.add_parser("diagnostics")
    sub.add_parser("open-login")
    sub.add_parser("reconnect")
    sub.add_parser("shutdown")
    sub.add_parser("account-summary")
    sub.add_parser("positions")
    completed = sub.add_parser("completed-orders")
    completed.add_argument("--market", default="all")
    completed.add_argument("--limit", type=int, default=50)
    quote = sub.add_parser("quote")
    quote.add_argument("--symbol", required=True)
    quote.add_argument("--market", default="us")
    order_preview = sub.add_parser("order-preview")
    order_preview.add_argument("--market", required=True, choices=["kr", "us"])
    order_preview.add_argument("--side", required=True, choices=["buy", "sell"])
    order_preview.add_argument("--symbol", required=True)
    order_preview.add_argument("--order-type", required=True, choices=["market", "limit"])
    order_preview.add_argument("--quantity", required=True, type=int)
    order_preview.add_argument("--limit-price", type=float)
    fx_preview = sub.add_parser("fx-preview")
    fx_preview.add_argument("--side", required=True, choices=["buy", "sell"])
    fx_preview.add_argument("--amount-krw", type=float)
    fx_preview.add_argument("--amount-usd", type=float)
    place_order = sub.add_parser("place-order")
    place_order.add_argument("--preview-receipt-file", required=True)
    place_order.add_argument("--preview-fingerprint", required=True)
    place_order.add_argument("--confirm", action="store_true")
    place_order.add_argument("--confirm-text", required=True)
    verify_order = sub.add_parser("verify-order")
    verify_order.add_argument("--mutation-id", required=True)

    args = parser.parse_args()
    command_map = {
        "health": "health",
        "diagnostics": "diagnostics",
        "open-login": "open_login",
        "reconnect": "reconnect",
        "shutdown": "shutdown",
        "account-summary": "account_summary",
        "positions": "positions",
        "completed-orders": "completed_orders",
        "quote": "quote",
        "order-preview": "order_preview",
        "fx-preview": "fx_preview",
        "place-order": "place_order",
        "verify-order": "verify_order",
    }
    params = {}
    if args.command == "completed-orders":
        params = {"market": args.market, "limit": args.limit}
    elif args.command == "quote":
        params = {"symbol": args.symbol, "market": args.market}
    elif args.command == "order-preview":
        params = {
            "market": args.market,
            "side": args.side,
            "symbol": args.symbol,
            "order_type": args.order_type,
            "quantity": args.quantity,
            "limit_price": args.limit_price,
        }
    elif args.command == "fx-preview":
        params = {
            "side": args.side,
            "amount_krw": args.amount_krw,
            "amount_usd": args.amount_usd,
        }
    elif args.command == "place-order":
        receipt_path = Path(args.preview_receipt_file)
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            parser.error(f"preview receipt file not found: {receipt_path}")
        except json.JSONDecodeError as exc:
            parser.error(f"invalid JSON in preview receipt file: {receipt_path} ({exc})")
        params = {
            "preview_receipt": receipt,
            "preview_fingerprint": args.preview_fingerprint,
            "confirm": args.confirm,
            "confirm_text": args.confirm_text,
        }
    elif args.command == "verify-order":
        params = {"mutation_id": args.mutation_id}
    payload = invoke(command_map[args.command], params=params)
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
