import pytest

from toss_browser_bridge.daemon import (
    PreviewValidationError,
    validate_fx_preview_params,
    validate_order_preview_params,
)


def test_validate_order_preview_params_normalizes_limit_order() -> None:
    payload = validate_order_preview_params(
        {
            "market": "kr",
            "side": "buy",
            "symbol": "005930",
            "order_type": "limit",
            "quantity": "3",
            "limit_price": "71200",
        }
    )

    assert payload == {
        "market": "kr",
        "side": "buy",
        "symbol": "A005930",
        "order_type": "limit",
        "quantity": 3,
        "limit_price": 71200.0,
    }


@pytest.mark.parametrize(
    ("params", "message"),
    [
        (
            {
                "market": "us",
                "side": "buy",
                "symbol": "TSLA",
                "order_type": "market",
                "quantity": 2,
                "limit_price": 300,
            },
            "limit_price is only allowed for limit orders",
        ),
        (
            {
                "market": "us",
                "side": "buy",
                "symbol": "TSLA",
                "order_type": "limit",
                "quantity": 2,
            },
            "limit_price is required for limit orders",
        ),
        (
            {
                "market": "us",
                "side": "buy",
                "symbol": "TSLA",
                "order_type": "market",
                "quantity": 0,
            },
            "quantity must be a positive integer",
        ),
    ],
)
def test_validate_order_preview_params_rejects_invalid_payloads(params: dict, message: str) -> None:
    with pytest.raises(PreviewValidationError, match=message):
        validate_order_preview_params(params)


def test_validate_fx_preview_params_accepts_single_amount() -> None:
    payload = validate_fx_preview_params({"side": "sell", "amount_usd": "150.5"})

    assert payload == {
        "side": "sell",
        "amount_field": "amount_usd",
        "amount": 150.5,
    }


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({}, "side must be one of: buy, sell"),
        (
            {"side": "buy"},
            "exactly one of amount_krw or amount_usd is required",
        ),
        (
            {"side": "buy", "amount_krw": 1000, "amount_usd": 10},
            "amount_krw and amount_usd cannot be provided together",
        ),
    ],
)
def test_validate_fx_preview_params_rejects_invalid_payloads(params: dict, message: str) -> None:
    with pytest.raises(PreviewValidationError, match=message):
        validate_fx_preview_params(params)
