from __future__ import annotations

from typing import Any

import pytest

from tests.conftest import RestTestContext, XtTestRuntime


REST_TESTED_ENDPOINTS = {
    "/api/v1/data/kline-history",
    "/api/v1/data/tick-history",
    "/api/v1/data/full-tick",
    "/api/v1/data/financial",
    "/api/v1/data/instrument/{symbol}",
    "/api/v1/data/trading-calendar",
    "/api/v1/data/index-weight",
    "/api/v1/data/sectors",
    "/api/v1/data/l2/quote",
    "/api/v1/data/l2/order",
    "/api/v1/data/l2/transaction",
    "/api/v1/data/subscriptions/quote",
    "/api/v1/data/subscriptions/whole-quote",
    "/api/v1/data/subscriptions",
    "/api/v1/data/subscriptions/{subscription_id}",
    "/api/v1/trading/sessions",
    "/api/v1/trading/sessions/{session_id}",
    "/api/v1/trading/sessions/{session_id}/asset",
    "/api/v1/trading/sessions/{session_id}/positions",
    "/api/v1/trading/sessions/{session_id}/orders",
    "/api/v1/trading/sessions/{session_id}/trades",
    "/api/v1/trading/sessions/{session_id}/cancel",
    "/api/v1/akshare/kline",
}


def _skip_if_live_streams_disabled(runtime: XtTestRuntime) -> None:
    if runtime.is_real and not runtime.enable_live_streams:
        pytest.skip("real streaming tests require --xt-enable-live-streams or QMT_TEST_ENABLE_LIVE_STREAMS=1")


def _open_rest_session(ctx: RestTestContext, account_id: str, account_type: str) -> str:
    response = ctx.client.post(
        "/api/v1/trading/sessions",
        json={"account_id": account_id, "account_type": account_type},
        headers=ctx.headers,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["success"] is True
    session = payload["data"]
    assert session["environment"] == ctx.runtime.mode
    assert session["account_kind"] == ctx.runtime.account_kind
    assert session["orders_enabled"] is ctx.runtime.orders_enabled
    return session["session_id"]


def _request_json(ctx: RestTestContext, method: str, path: str, body: dict[str, Any] | None = None):
    request = getattr(ctx.client, method)
    if body is None:
        response = request(path, headers=ctx.headers)
    else:
        response = request(path, json=body, headers=ctx.headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["success"] is True
    assert "data" in payload
    return payload["data"]


REST_DATA_CASES = [
    ("kline-history", "post", "/api/v1/data/kline-history"),
    ("tick-history", "post", "/api/v1/data/tick-history"),
    ("full-tick", "post", "/api/v1/data/full-tick"),
    ("financial", "post", "/api/v1/data/financial"),
    ("instrument", "get", "/api/v1/data/instrument/{symbol}?complete=false"),
    ("trading-calendar", "post", "/api/v1/data/trading-calendar"),
    ("index-weight", "post", "/api/v1/data/index-weight"),
    ("sectors", "get", "/api/v1/data/sectors"),
    ("l2-quote", "post", "/api/v1/data/l2/quote"),
    ("l2-order", "post", "/api/v1/data/l2/order"),
    ("l2-transaction", "post", "/api/v1/data/l2/transaction"),
]


def _build_rest_data_body(case_id: str, symbols: list[str], index_code: str, market: str) -> dict[str, Any] | None:
    if case_id == "kline-history":
        return {"symbols": symbols, "period": "1d", "start_time": "20240101", "end_time": "20240131"}
    if case_id == "tick-history":
        return {"symbols": [symbols[0]], "start_time": "20240101093000", "end_time": "20240101150000"}
    if case_id == "full-tick":
        return {"symbols": [symbols[0]]}
    if case_id == "financial":
        return {"symbols": [symbols[0]], "table_names": ["Balance"]}
    if case_id == "instrument":
        return None
    if case_id == "trading-calendar":
        return {"market": market, "start_time": "20240101", "end_time": "20240131"}
    if case_id == "index-weight":
        return {"index_code": index_code}
    if case_id == "sectors":
        return None
    if case_id in {"l2-quote", "l2-order", "l2-transaction"}:
        return {"symbols": [symbols[0]], "start_time": "", "end_time": ""}
    raise AssertionError(f"unknown case: {case_id}")


def _assert_rest_data_shape(case_id: str, data: dict[str, Any], symbols: list[str], index_code: str, market: str) -> None:
    if case_id in {"kline-history", "tick-history", "full-tick", "financial", "l2-quote", "l2-order", "l2-transaction", "sectors"}:
        assert "items" in data
        assert isinstance(data["items"], list)
        return
    if case_id == "instrument":
        assert data["symbol"] == symbols[0]
        assert "fields" in data
        return
    if case_id == "trading-calendar":
        assert data["market"] == market
        assert isinstance(data["dates"], list)
        return
    if case_id == "index-weight":
        assert data["index_code"] == index_code
        assert isinstance(data["components"], list)
        return
    raise AssertionError(f"unknown case: {case_id}")


@pytest.mark.parametrize(("case_id", "method", "path_template"), REST_DATA_CASES, ids=[case[0] for case in REST_DATA_CASES])
def test_rest_data_interfaces(
    rest_test_context: RestTestContext,
    xt_default_symbols: list[str],
    xt_default_index_code: str,
    xt_default_market: str,
    case_id: str,
    method: str,
    path_template: str,
):
    path = path_template.format(symbol=xt_default_symbols[0])
    body = _build_rest_data_body(case_id, xt_default_symbols, xt_default_index_code, xt_default_market)
    if rest_test_context.runtime.is_real and case_id == "trading-calendar":
        request = getattr(rest_test_context.client, method)
        if body is None:
            response = request(path, headers=rest_test_context.headers)
        else:
            response = request(path, json=body, headers=rest_test_context.headers)
        if response.status_code == 501:
            payload = response.json()
            assert payload["data"]["error_code"] == "FEATURE_NOT_SUPPORTED"
            return
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["success"] is True
        data = payload["data"]
    else:
        data = _request_json(rest_test_context, method, path, body)
    _assert_rest_data_shape(case_id, data, xt_default_symbols, xt_default_index_code, xt_default_market)


def test_rest_quote_subscription_crud_interfaces(rest_test_context: RestTestContext, xt_default_symbols: list[str]):
    create_data = _request_json(
        rest_test_context,
        "post",
        "/api/v1/data/subscriptions/quote",
        {"symbols": [xt_default_symbols[0]], "period": "tick", "adjust_type": "none", "count": 0},
    )
    subscription_id = create_data["subscription_id"]
    assert create_data["subscription_type"] == "quote"
    assert create_data["count"] == 0

    list_data = _request_json(rest_test_context, "get", "/api/v1/data/subscriptions")
    assert any(item["subscription_id"] == subscription_id for item in list_data["items"])

    get_data = _request_json(rest_test_context, "get", f"/api/v1/data/subscriptions/{subscription_id}")
    assert get_data["subscription_id"] == subscription_id

    delete_data = _request_json(rest_test_context, "delete", f"/api/v1/data/subscriptions/{subscription_id}")
    assert delete_data["success"] is True


def test_rest_quote_subscription_rejects_tick_full_history_replay(
    rest_test_context: RestTestContext,
    xt_default_symbols: list[str],
):
    response = rest_test_context.client.post(
        "/api/v1/data/subscriptions/quote",
        json={"symbols": [xt_default_symbols[0]], "period": "tick", "count": -1},
        headers=rest_test_context.headers,
    )

    assert response.status_code == 422, response.text
    payload = response.json()
    assert payload["data"]["error_code"] == "INVALID_SUBSCRIPTION_COUNT"


def test_rest_whole_quote_subscription_crud_interfaces(rest_test_context: RestTestContext):
    create_data = _request_json(
        rest_test_context,
        "post",
        "/api/v1/data/subscriptions/whole-quote",
        {"markets": ["SH", "SZ"]},
    )
    subscription_id = create_data["subscription_id"]
    assert create_data["subscription_type"] == "whole_quote"

    get_data = _request_json(rest_test_context, "get", f"/api/v1/data/subscriptions/{subscription_id}")
    assert get_data["subscription_id"] == subscription_id

    delete_data = _request_json(rest_test_context, "delete", f"/api/v1/data/subscriptions/{subscription_id}")
    assert delete_data["success"] is True


def test_rest_trading_session_interfaces(
    rest_test_context: RestTestContext,
    xt_trading_account_id: str,
):
    session_id = _open_rest_session(rest_test_context, xt_trading_account_id, rest_test_context.runtime.account_type)

    session_data = _request_json(rest_test_context, "get", f"/api/v1/trading/sessions/{session_id}")
    assert session_data["session_id"] == session_id
    assert session_data["environment"] == rest_test_context.runtime.mode
    assert session_data["account_kind"] == rest_test_context.runtime.account_kind
    assert session_data["orders_enabled"] is rest_test_context.runtime.orders_enabled

    asset_data = _request_json(rest_test_context, "get", f"/api/v1/trading/sessions/{session_id}/asset")
    assert "account_id" in asset_data

    positions_data = _request_json(rest_test_context, "get", f"/api/v1/trading/sessions/{session_id}/positions")
    assert isinstance(positions_data["items"], list)

    orders_data = _request_json(rest_test_context, "get", f"/api/v1/trading/sessions/{session_id}/orders")
    assert isinstance(orders_data["items"], list)

    trades_data = _request_json(rest_test_context, "get", f"/api/v1/trading/sessions/{session_id}/trades")
    assert isinstance(trades_data["items"], list)

    close_data = _request_json(rest_test_context, "delete", f"/api/v1/trading/sessions/{session_id}")
    assert close_data["success"] is True


def test_rest_trading_order_and_cancel_interfaces(
    rest_test_context: RestTestContext,
    xt_default_symbols: list[str],
    xt_trading_account_id: str,
):
    session_id = _open_rest_session(rest_test_context, xt_trading_account_id, rest_test_context.runtime.account_type)

    order_response = rest_test_context.client.post(
        f"/api/v1/trading/sessions/{session_id}/orders",
        json={
            "stock_code": xt_default_symbols[0],
            "side": "BUY",
            "price_type": 11,
            "volume": 100,
            "price": 12.3,
            "strategy_name": "pytest",
            "order_remark": "rest-order",
        },
        headers=rest_test_context.headers,
    )

    if rest_test_context.runtime.orders_enabled:
        assert order_response.status_code == 200, order_response.text
        order_payload = order_response.json()
        assert order_payload["success"] is True
        order_data = order_payload["data"]
        assert order_data["stock_code"] == xt_default_symbols[0]
        assert order_data["order_id"]

        cancel_by_order_data = _request_json(
            rest_test_context,
            "post",
            f"/api/v1/trading/sessions/{session_id}/cancel",
            {"order_id": order_data["order_id"]},
        )
        assert cancel_by_order_data["success"] is True

        cancel_by_sysid_data = _request_json(
            rest_test_context,
            "post",
            f"/api/v1/trading/sessions/{session_id}/cancel",
            {"market": "SH", "order_sysid": "SYSID-TEST"},
        )
        assert cancel_by_sysid_data["success"] is True
    else:
        assert order_response.status_code == 403, order_response.text
        payload = order_response.json()
        assert payload["success"] is False
        assert payload["data"]["error_code"] == "ORDERS_DISABLED"

        cancel_response = rest_test_context.client.post(
            f"/api/v1/trading/sessions/{session_id}/cancel",
            json={"order_id": "blocked-order"},
            headers=rest_test_context.headers,
        )
        assert cancel_response.status_code == 403, cancel_response.text
        cancel_payload = cancel_response.json()
        assert cancel_payload["success"] is False
        assert cancel_payload["data"]["error_code"] == "ORDERS_DISABLED"

    _request_json(rest_test_context, "delete", f"/api/v1/trading/sessions/{session_id}")


def test_rest_missing_subscription_returns_404(rest_test_context: RestTestContext):
    response = rest_test_context.client.get(
        "/api/v1/data/subscriptions/missing-subscription",
        headers=rest_test_context.headers,
    )
    assert response.status_code == 404
    payload = response.json()
    assert payload["success"] is False


def test_websocket_quote_stream_interface(
    rest_test_context: RestTestContext,
    xt_default_symbols: list[str],
):
    _skip_if_live_streams_disabled(rest_test_context.runtime)

    create_data = _request_json(
        rest_test_context,
        "post",
        "/api/v1/data/subscriptions/quote",
        {"symbols": [xt_default_symbols[0]], "period": "tick"},
    )
    subscription_id = create_data["subscription_id"]

    with rest_test_context.client.websocket_connect(
        f"/ws/quote/{subscription_id}?token={rest_test_context.runtime.api_key}"
    ) as websocket:
        connected = websocket.receive_json()
        message = websocket.receive_json()

    assert connected["type"] == "connected"
    if rest_test_context.runtime.is_real:
        assert message["type"] in {"quote", "heartbeat"}
        if message["type"] == "quote":
            assert message["data"]["symbol"] == xt_default_symbols[0]
        else:
            assert message["subscription_id"] == subscription_id
    else:
        assert message["type"] == "quote"
        assert message["data"]["symbol"] == xt_default_symbols[0]


def test_rest_akshare_kline_interface(rest_test_context: RestTestContext):
    response = rest_test_context.client.post(
        "/api/v1/akshare/kline",
        json={"symbol": "000001", "asset_type": "index", "period": "daily", "start_date": "20250101", "end_date": "20250110"},
        headers=rest_test_context.headers,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["success"] is True
    assert "items" in payload["data"]
