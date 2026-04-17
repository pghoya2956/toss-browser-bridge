from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_LIVE_E2E = os.environ.get("TOSS_BRIDGE_LIVE_E2E") == "1"


pytestmark = pytest.mark.skipif(not RUN_LIVE_E2E, reason="set TOSS_BRIDGE_LIVE_E2E=1 to run live bridge E2E")


def _run_cli(*args: str) -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, "-m", "toss_browser_bridge.cli", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(completed.stdout)


def test_live_logged_in_read_and_guarded_submit_flow(tmp_path) -> None:
    health = _run_cli("health")
    assert health["ok"] is True
    assert health["capability"] == "browser_attached"
    assert health["data"]["capabilities"]["order_preview_ready"] is True
    assert health["data"]["capabilities"]["post_submit_verify_ready"] is True
    assert health["data"]["capabilities"]["order_submit_ready"] is False
    assert health["data"]["capabilities"]["fx_preview_ready"] is True

    account_summary = _run_cli("account-summary")
    assert account_summary["ok"] is True
    assert account_summary["data"]["account_id"].startswith("toss:")

    positions = _run_cli("positions")
    assert positions["ok"] is True
    assert isinstance(positions["data"]["positions"], list)

    completed_orders = _run_cli("completed-orders", "--limit", "3")
    assert completed_orders["ok"] is True
    assert isinstance(completed_orders["data"]["items"], list)

    quote = _run_cli("quote", "--symbol", "AAPL")
    assert quote["ok"] is True
    assert quote["data"]["symbol"] == "AAPL"
    cents_bump = ((time.time_ns() % 17) + 1) / 100
    limit_price = f"{float(quote['data']['current_price']) + cents_bump:.2f}"

    preview = _run_cli(
        "order-preview",
        "--market",
        "us",
        "--side",
        "buy",
        "--symbol",
        "AAPL",
        "--order-type",
        "limit",
        "--quantity",
        "1",
        "--limit-price",
        limit_price,
    )
    assert preview["ok"] is True
    assert preview["kind"] == "order_preview"
    assert preview["data"]["preview_state"] == "preview_ready"
    assert preview["data"]["preview_fingerprint"].startswith("sha256:")
    assert isinstance(preview["diagnostics"]["endpoint_matrix"], list)
    receipt_file = tmp_path / "preview-receipt.json"
    receipt_file.write_text(json.dumps(preview["data"]["preview_receipt"]), encoding="utf-8")

    place_order = _run_cli(
        "place-order",
        "--preview-receipt-file",
        str(receipt_file),
        "--preview-fingerprint",
        preview["data"]["preview_fingerprint"],
        "--confirm",
        "--confirm-text",
        preview["data"]["confirm_phrase"],
    )
    assert place_order["ok"] is False
    assert place_order["kind"] == "place_order"
    assert place_order["error"]["code"] == "capability_not_ready"
    assert "prepare preflight succeeded" in place_order["error"]["message"]
    assert place_order["diagnostics"]["mutation_id"].startswith("mut_")

    verify_order = _run_cli("verify-order", "--mutation-id", place_order["diagnostics"]["mutation_id"])
    assert verify_order["ok"] is True
    assert verify_order["kind"] == "verify_order"
    assert verify_order["data"]["mutation_id"] == place_order["diagnostics"]["mutation_id"]
    assert verify_order["data"]["submit_state"] == "submit_blocked"
    assert verify_order["data"]["verification_state"] == "verified_failed"
    assert verify_order["data"]["verify_snapshot"]["matched_order"] is None

    fx_preview = _run_cli("fx-preview", "--side", "buy", "--amount-krw", "100000")
    assert fx_preview["ok"] is True
    assert fx_preview["kind"] == "fx_preview"
    assert fx_preview["data"]["preview_state"] in {"preview_ready", "blocked"}
    assert fx_preview["data"]["preview_fingerprint"].startswith("sha256:")
