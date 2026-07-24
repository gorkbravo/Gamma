from __future__ import annotations

from ib_insync import Stock

from src.services.ibkr_client import IBKRClient


def _client() -> IBKRClient:
    return IBKRClient(host="127.0.0.1", port=7497, client_id=991, mock=True)


def test_duplicate_contract_definition_errors_are_deduplicated_in_user_summary():
    client = _client()
    contract = Stock("LMT", "SMART", "USD")

    client._on_ib_error(41, 200, "No security definition has been found for the request", contract)
    client._on_ib_error(41, 200, "No security definition has been found for the request", contract)
    client._on_ib_error(42, 200, "No security definition has been found for the request", contract)

    assert client.drain_errors() == ["LMT: IBKR could not resolve the security definition."]


def test_definition_errors_for_distinct_symbols_remain_distinct():
    client = _client()

    client._on_ib_error(41, 200, "No security definition has been found for the request", Stock("LMT", "SMART", "USD"))
    client._on_ib_error(42, 200, "No security definition has been found for the request", Stock("FOUR", "SMART", "USD"))

    assert client.drain_errors() == [
        "LMT: IBKR could not resolve the security definition.",
        "FOUR: IBKR could not resolve the security definition.",
    ]


def test_unknown_request_ids_are_concise_and_deduplicated():
    client = _client()

    client._on_ib_error(-1, 200, "No security definition has been found for the request", None)
    client._on_ib_error(77, 200, "No security definition has been found for the request", None)

    assert client.drain_errors() == [
        "IBKR could not resolve a security definition for an unattributed request."
    ]


def test_diagnostics_preserve_raw_request_ids_codes_and_contract_attribution():
    client = _client()
    raw_message = "No security definition has been found for the request"

    client._on_ib_error(41, 200, raw_message, Stock("LMT", "SMART", "USD"))
    client._on_ib_error(42, 200, raw_message, Stock("LMT", "SMART", "USD"))

    assert client.drain_errors() == ["LMT: IBKR could not resolve the security definition."]
    diagnostics = client.format_error_records()
    assert len(diagnostics) == 2
    assert "reqId=41 code=200 symbol=LMT" in diagnostics[0]
    assert raw_message in diagnostics[0]
    assert "reqId=42 code=200 symbol=LMT" in diagnostics[1]
