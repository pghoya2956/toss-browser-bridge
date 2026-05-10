from __future__ import annotations

import hashlib
import json
import secrets
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from toss_browser_bridge.bridge_lib import ensure_runtime_dirs
from toss_browser_bridge.preview import build_preview_fingerprint, canonical_json_dumps

MUTATION_DOMAIN_ERROR_CODES = {
    "invalid_request",
    "logged_out",
    "capability_not_ready",
    "submit_blocked",
    "submit_cancelled",
    "broker_rejected",
    "unknown",
    "verification_failed",
}

ORDER_PREVIEW_RECEIPT_KIND = "order_preview_receipt"
MUTATION_JOURNAL_SCHEMA_VERSION = 1
MUTATION_JOURNAL_ALLOWED_FIELDS = {
    "schema_version",
    "mutation_id",
    "kind",
    "requested_at",
    "preview_fingerprint",
    "confirm_phrase_hash",
    "submit_state",
    "verification_state",
    "broker_ack",
    "verify_snapshot",
}
BROKER_ACK_ALLOWED_FIELDS = {
    "status",
    "code",
    "message",
    "market",
    "symbol",
    "side",
    "quantity",
    "order_type",
    "ordered_at",
    "broker_order_id",
    "order_no",
    "order_date",
    "is_reserved",
    "http_status",
    "guard_reason",
}
VERIFY_SNAPSHOT_ALLOWED_FIELDS = {
    "status",
    "message",
    "matched_order",
    "position_delta",
    "cash_delta",
    "verified_at",
}
ORDER_PRICE_TYPE_CODES = {
    "limit": "00",
    "market": "03",
}

ORDER_TYPES_SUPPORTED = frozenset({"limit", "market"})

# Per-market override for orderPriceType. Phase 0 P0-02 supervised capture
# (toss web app, NVDA 5주 "시장가") confirmed that the US client maps
# order_type="market" to API ``orderPriceType="00"`` and fills price with
# the NBBO quote — i.e. the broker only ever sees a limit order on US.
# KR market orders are unverified at this stage; the legacy "03" mapping
# is preserved as a placeholder until Phase 6 supervised capture.
US_MARKET_ORDER_PRICE_TYPE = "00"
SUBMIT_MARKETS = {"KSP", "KSQ", "KR_ETC", "NYS", "NSQ", "AMX", "US_ETC"}
SUBMIT_CURRENCY_MODES = {"KRW", "USD"}


def make_mutation_id() -> str:
    return f"mut_{secrets.token_hex(8)}"


class MutationValidationError(ValueError):
    def __init__(self, message: str, *, code: str = "invalid_request") -> None:
        super().__init__(message)
        self.code = code


class MutationDomainError(Exception):
    def __init__(
        self,
        *,
        kind: str,
        capability: str,
        code: str,
        message: str,
        diagnostics: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        if code not in MUTATION_DOMAIN_ERROR_CODES:
            raise ValueError(f"unsupported mutation domain error code: {code}")
        self.kind = kind
        self.capability = capability
        self.code = code
        self.message = message
        self.diagnostics = diagnostics or {"endpoint_matrix": [], "last_errors": []}

    def to_payload(self, *, source: str, checked_at: str) -> dict[str, Any]:
        diagnostics = dict(self.diagnostics)
        diagnostics["endpoint_matrix"] = list(self.diagnostics.get("endpoint_matrix") or [])
        diagnostics["last_errors"] = list(self.diagnostics.get("last_errors") or [])
        return {
            "ok": False,
            "kind": self.kind,
            "source": source,
            "checked_at": checked_at,
            "capability": self.capability,
            "error": {
                "code": self.code,
                "message": self.message,
            },
            "diagnostics": diagnostics,
        }


def build_order_preview_fingerprint_payload(
    *,
    account_id: str,
    inputs: dict[str, Any],
    submit_candidate: dict[str, Any],
    derived: dict[str, Any],
) -> dict[str, Any]:
    return {
        "kind": "order_preview",
        "inputs": {
            "market": inputs["market"],
            "side": inputs["side"],
            "symbol": inputs["symbol"],
            "order_type": inputs["order_type"],
            "quantity": inputs["quantity"],
            "limit_price": inputs.get("limit_price"),
        },
        "account_id": account_id,
        "submit_candidate": {
            "market": submit_candidate["market"],
            "side": submit_candidate["side"],
            "product_code": submit_candidate["product_code"],
            "symbol": submit_candidate["symbol"],
            "order_type": submit_candidate["order_type"],
            "quantity": submit_candidate["quantity"],
            "limit_price": submit_candidate.get("limit_price"),
            "currency": submit_candidate["currency"],
            "estimated_total_amount": submit_candidate["estimated_total_amount"],
        },
        "derived": {
            "product_code": derived["product_code"],
            "currency": derived["currency"],
            "estimated_unit_price": derived["estimated_unit_price"],
            "estimated_total_amount": derived["estimated_total_amount"],
            "orderable_cash": derived["orderable_cash"],
            "available_quantity": derived.get("available_quantity"),
            "market_status": derived.get("market_status"),
        },
    }


def build_order_preview_receipt(
    *,
    preview_id: str,
    preview_fingerprint: str,
    account_id: str,
    inputs: dict[str, Any],
    submit_candidate: dict[str, Any],
    derived: dict[str, Any],
    verification_plan: dict[str, Any],
) -> dict[str, Any]:
    return {
        "receipt_kind": ORDER_PREVIEW_RECEIPT_KIND,
        "schema_version": 1,
        "preview_id": preview_id,
        "preview_fingerprint": preview_fingerprint,
        "account_id": account_id,
        "inputs": {
            "market": inputs["market"],
            "side": inputs["side"],
            "symbol": inputs["symbol"],
            "order_type": inputs["order_type"],
            "quantity": inputs["quantity"],
            "limit_price": inputs.get("limit_price"),
        },
        "submit_candidate": {
            "market": submit_candidate["market"],
            "side": submit_candidate["side"],
            "product_code": submit_candidate["product_code"],
            "symbol": submit_candidate["symbol"],
            "order_type": submit_candidate["order_type"],
            "quantity": submit_candidate["quantity"],
            "limit_price": submit_candidate.get("limit_price"),
            "currency": submit_candidate["currency"],
            "estimated_total_amount": submit_candidate["estimated_total_amount"],
        },
        "derived": {
            "product_code": derived["product_code"],
            "market_code": derived.get("market_code"),
            "currency": derived["currency"],
            "estimated_unit_price": derived["estimated_unit_price"],
            "estimated_total_amount": derived["estimated_total_amount"],
            "orderable_cash": derived["orderable_cash"],
            "available_quantity": derived.get("available_quantity"),
            "market_status": derived.get("market_status"),
        },
        "verification_plan": verification_plan,
    }


def validate_order_preview_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(receipt, dict):
        raise MutationValidationError("preview_receipt must be a JSON object")
    if receipt.get("receipt_kind") != ORDER_PREVIEW_RECEIPT_KIND:
        raise MutationValidationError("preview_receipt receipt_kind must be order_preview_receipt")
    if receipt.get("schema_version") != 1:
        raise MutationValidationError("preview_receipt schema_version must be 1")

    for field in ("preview_id", "preview_fingerprint", "account_id", "inputs", "submit_candidate", "derived"):
        if field not in receipt:
            raise MutationValidationError(f"preview_receipt missing {field}")

    inputs = receipt["inputs"]
    submit_candidate = receipt["submit_candidate"]
    derived = receipt["derived"]
    try:
        expected = build_preview_fingerprint(
            build_order_preview_fingerprint_payload(
                account_id=str(receipt["account_id"]),
                inputs=inputs,
                submit_candidate=submit_candidate,
                derived=derived,
            )
        )
    except (KeyError, TypeError) as exc:
        raise MutationValidationError("preview_receipt is missing required canonical fields") from exc
    if receipt["preview_fingerprint"] != expected:
        raise MutationValidationError("preview_receipt fingerprint does not match receipt contents")
    return receipt


def build_order_confirm_phrase(receipt: dict[str, Any]) -> str:
    validated = validate_order_preview_receipt(receipt)
    inputs = validated["inputs"]
    market = str(inputs["market"]).strip().upper()
    side = str(inputs["side"]).strip().upper()
    symbol = str(inputs["symbol"]).strip().upper()
    order_type = str(inputs["order_type"]).strip().upper()
    quantity = str(inputs["quantity"]).strip()
    if order_type == "LIMIT":
        price = _format_limit_price(validated)
        return f"{side} {quantity} {symbol} {order_type} {price} {market}"
    return f"{side} {quantity} {symbol} {order_type} {market}"


def build_confirm_phrase_hash(confirm_phrase: str) -> str:
    digest = hashlib.sha256(confirm_phrase.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def validate_place_order_params(params: dict[str, Any]) -> dict[str, Any]:
    receipt = validate_order_preview_receipt(params.get("preview_receipt"))
    inputs_order_type = receipt["inputs"].get("order_type")
    if inputs_order_type not in ORDER_TYPES_SUPPORTED:
        raise MutationValidationError(f"unsupported order_type: {inputs_order_type}")
    if receipt["submit_candidate"].get("order_type") != inputs_order_type:
        raise MutationValidationError("preview_receipt submit_candidate.order_type must match inputs.order_type")

    preview_fingerprint = str(params.get("preview_fingerprint") or "").strip()
    if not preview_fingerprint:
        raise MutationValidationError("preview_fingerprint is required")
    if preview_fingerprint != receipt["preview_fingerprint"]:
        raise MutationValidationError("preview_fingerprint does not match preview_receipt")

    if params.get("confirm") is not True:
        raise MutationValidationError("confirm must be true to submit an order")

    confirm_text = str(params.get("confirm_text") or "").strip()
    if not confirm_text:
        raise MutationValidationError("confirm_text is required")

    confirm_phrase = build_order_confirm_phrase(receipt)
    if confirm_text != confirm_phrase:
        raise MutationValidationError("confirm_text does not match the canonical confirm phrase", code="submit_blocked")

    auto_verify = bool(params.get("auto_verify") or False)

    is_reservation_order_raw = params.get("is_reservation_order")
    if is_reservation_order_raw is None:
        is_reservation_order: bool | None = None
    elif isinstance(is_reservation_order_raw, bool):
        is_reservation_order = is_reservation_order_raw
    else:
        raise MutationValidationError(
            "is_reservation_order must be bool or None — "
            "policy enums (auto/on/off) are converted in the wrapper layer"
        )

    return {
        "preview_receipt": receipt,
        "preview_fingerprint": preview_fingerprint,
        "confirm_phrase": confirm_phrase,
        "confirm_phrase_hash": build_confirm_phrase_hash(confirm_phrase),
        "auto_verify": auto_verify,
        "is_reservation_order": is_reservation_order,
    }


def validate_verify_order_params(params: dict[str, Any]) -> dict[str, Any]:
    mutation_id = str(params.get("mutation_id") or "").strip()
    if not mutation_id:
        raise MutationValidationError("mutation_id is required")
    return {"mutation_id": mutation_id}


def sanitize_mutation_journal_entry(entry: dict[str, Any]) -> dict[str, Any]:
    sanitized = {key: entry[key] for key in MUTATION_JOURNAL_ALLOWED_FIELDS if key in entry}
    sanitized.setdefault("schema_version", MUTATION_JOURNAL_SCHEMA_VERSION)

    broker_ack = sanitized.get("broker_ack")
    if isinstance(broker_ack, dict):
        sanitized["broker_ack"] = {
            key: broker_ack[key]
            for key in BROKER_ACK_ALLOWED_FIELDS
            if key in broker_ack
        }

    verify_snapshot = sanitized.get("verify_snapshot")
    if isinstance(verify_snapshot, dict):
        sanitized["verify_snapshot"] = {
            key: verify_snapshot[key]
            for key in VERIFY_SNAPSHOT_ALLOWED_FIELDS
            if key in verify_snapshot
        }

    return sanitized


def append_mutation_journal(path: Path, entry: dict[str, Any]) -> dict[str, Any]:
    ensure_runtime_dirs()
    path.parent.mkdir(parents=True, exist_ok=True)
    sanitized = sanitize_mutation_journal_entry(entry)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(canonical_json_dumps(sanitized))
        handle.write("\n")
    return sanitized


def mutation_journal_is_writable(path: Path) -> bool:
    try:
        ensure_runtime_dirs()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8"):
            pass
    except OSError:
        return False
    return True


def mutation_journal_line_preview(entry: dict[str, Any]) -> str:
    return canonical_json_dumps(sanitize_mutation_journal_entry(entry))


def find_recent_mutation_by_preview_fingerprint(path: Path, preview_fingerprint: str) -> dict[str, Any] | None:
    """Idempotency 검사: 같은 preview_fingerprint 의 *실 broker 시도* 가 있는지 확인.

    submit_state="submit_blocked" 는 broker create 호출 0 + 실주문 0 이므로 idempotency 무관.
    재시도 안전 (예: TOSS_BRIDGE_ENABLE_FINAL_SUBMIT off→on 토글 후 동일 preview retry).
    """
    if not path.exists():
        return None
    for raw_line in reversed(path.read_text(encoding="utf-8").splitlines()):
        line = raw_line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("preview_fingerprint") != preview_fingerprint:
            continue
        if entry.get("submit_state") == "submit_blocked":
            continue
        return sanitize_mutation_journal_entry(entry)
    return None


def find_recent_mutation_by_id(path: Path, mutation_id: str) -> dict[str, Any] | None:
    if not path.exists():
        return None
    for raw_line in reversed(path.read_text(encoding="utf-8").splitlines()):
        line = raw_line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("mutation_id") == mutation_id:
            return sanitize_mutation_journal_entry(entry)
    return None


def collect_enum_candidates(payload: Any, allowed_values: set[str]) -> list[str]:
    found: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for nested in value.values():
                walk(nested)
            return
        if isinstance(value, list):
            for nested in value:
                walk(nested)
            return
        if isinstance(value, str) and value in allowed_values and value not in found:
            found.append(value)

    walk(payload)
    return found


def resolve_order_price_type(market_bucket: str, order_type: str) -> str:
    """Map (market_bucket, order_type) to broker orderPriceType code.

    P0-02 found that toss web app maps US market orders to
    ``orderPriceType="00"`` (limit) at the API layer, with the client
    filling the price field from the NBBO quote. KR market orders are
    not yet verified — Phase 6 supervised capture will replace the
    "03" placeholder if it diverges.
    """
    if order_type not in ORDER_PRICE_TYPE_CODES:
        raise MutationValidationError(f"unsupported order_type for prepare payload: {order_type}")
    if order_type == "market" and (market_bucket or "").lower() == "us":
        return US_MARKET_ORDER_PRICE_TYPE
    return ORDER_PRICE_TYPE_CODES[order_type]


def build_order_prepare_payload(
    receipt: dict[str, Any],
    *,
    submit_market: str,
    currency_mode: str,
    allow_auto_exchange: bool,
    is_reservation_order: bool | None = None,
) -> dict[str, Any]:
    validated = validate_order_preview_receipt(receipt)
    inputs = validated["inputs"]
    submit_candidate = validated["submit_candidate"]
    order_type = str(inputs["order_type"])
    market_bucket = str(inputs.get("market") or "").lower()
    order_price_type = resolve_order_price_type(market_bucket, order_type)
    quantity = int(inputs["quantity"])
    price = float(submit_candidate.get("limit_price") or 0)
    if price <= 0:
        raise MutationValidationError(
            "preview_receipt submit_candidate.limit_price must be positive "
            "(market orders use NBBO-quoted price; preview must populate it)"
        )
    reservation_flag = False if is_reservation_order is None else bool(is_reservation_order)
    return {
        "stockCode": submit_candidate["product_code"],
        "market": submit_market,
        "currencyMode": currency_mode,
        "tradeType": inputs["side"],
        "price": price,
        "quantity": quantity,
        "orderAmount": 0,
        "orderPriceType": order_price_type,
        "agreedOver100Million": False,
        "marginTrading": False,
        "max": False,
        "isReservationOrder": reservation_flag,
        "openPriceSinglePriceYn": False,
        "withOrderKey": True,
    }


def build_prepare_drift_issues(
    receipt: dict[str, Any],
    prepared_order_info: dict[str, Any],
    *,
    compare_price: bool = True,
) -> list[dict[str, str]]:
    validated = validate_order_preview_receipt(receipt)
    inputs = validated["inputs"]
    expected_order_price_type = resolve_order_price_type(
        str(inputs.get("market") or "").lower(),
        str(inputs["order_type"]),
    )
    issues: list[dict[str, str]] = []

    if str(prepared_order_info.get("tradeType") or "") != str(inputs["side"]):
        issues.append(
            {
                "code": "prepare_trade_type_mismatch",
                "message": "preparedOrderInfo.tradeType drifted from preview_receipt",
            }
        )
    if str(prepared_order_info.get("orderPriceType") or "") != expected_order_price_type:
        issues.append(
            {
                "code": "prepare_order_price_type_mismatch",
                "message": "preparedOrderInfo.orderPriceType drifted from preview_receipt",
            }
        )
    if int(prepared_order_info.get("quantity") or 0) != int(inputs["quantity"]):
        issues.append(
            {
                "code": "prepare_quantity_mismatch",
                "message": "preparedOrderInfo.quantity drifted from preview_receipt",
            }
        )
    if compare_price:
        currency = str(((validated.get("derived") or {}).get("currency")) or "").upper()
        price_quant = Decimal("0.01") if currency == "USD" else Decimal("1")
        expected_price = Decimal(str(validated["submit_candidate"]["limit_price"])).quantize(
            price_quant,
            rounding=ROUND_HALF_UP,
        )
        actual_price = Decimal(str(prepared_order_info.get("price") or 0)).quantize(
            price_quant,
            rounding=ROUND_HALF_UP,
        )
        if actual_price != expected_price:
            issues.append(
                {
                    "code": "prepare_price_mismatch",
                    "message": "preparedOrderInfo.price drifted from preview_receipt",
                }
            )
    return issues


def _format_limit_price(receipt: dict[str, Any]) -> str:
    currency = str(((receipt.get("derived") or {}).get("currency")) or "").upper()
    limit_price = ((receipt.get("submit_candidate") or {}).get("limit_price"))
    if limit_price in (None, ""):
        raise MutationValidationError("preview_receipt submit_candidate.limit_price is required for limit orders")
    quant = Decimal("0.01") if currency == "USD" else Decimal("1")
    amount = Decimal(str(limit_price)).quantize(quant, rounding=ROUND_HALF_UP)
    return format(amount, "f")
