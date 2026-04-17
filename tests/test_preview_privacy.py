from toss_browser_bridge.bridge_lib import sanitize_endpoint_entry


def test_sanitize_endpoint_entry_drops_sensitive_transport_fields() -> None:
    payload = sanitize_endpoint_entry(
        {
            "name": "fx_quote_for_buy_probe",
            "method": "GET",
            "path": "/api/v1/exchange/current-quote/for-buy",
            "status_code": 200,
            "ok": True,
            "error": None,
            "url": "https://wts-api.tossinvest.com/api/v1/exchange/current-quote/for-buy",
            "headers": {"Authorization": "Bearer secret", "X-XSRF-TOKEN": "token"},
            "body": {"accountNo": "18401036018"},
        }
    )

    assert payload == {
        "name": "fx_quote_for_buy_probe",
        "method": "GET",
        "path": "/api/v1/exchange/current-quote/for-buy",
        "status_code": 200,
        "ok": True,
        "error": None,
    }
