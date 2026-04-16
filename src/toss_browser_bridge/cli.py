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

REPO_ROOT = Path(__file__).resolve().parents[2]


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

    cmd = [
        "uv",
        "run",
        "--project",
        str(REPO_ROOT),
        "python",
        "-m",
        "toss_browser_bridge.daemon",
        "run",
    ]
    subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    if not wait_for_port(timeout=20.0):
        raise RuntimeError(f"bridge daemon did not start on {HOST}:{PORT}")
    token = read_text_if_exists(TOKEN_FILE)
    if not token:
        raise RuntimeError("bridge token file was not created")
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
    }
    params = {}
    if args.command == "completed-orders":
        params = {"market": args.market, "limit": args.limit}
    elif args.command == "quote":
        params = {"symbol": args.symbol, "market": args.market}
    payload = invoke(command_map[args.command], params=params)
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
