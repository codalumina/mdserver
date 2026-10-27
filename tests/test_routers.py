import os
import pytest
import builtins
from unittest.mock import patch, mock_open
import sqlite3

@pytest.fixture
def auth_headers(test_db_path):
    """Injects a valid test key and returns the HTTP authorization header."""
    valid_key = "router_test_key_123"
    with sqlite3.connect(test_db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO api_keys (key_value, client_name) VALUES (?, ?)",
            (valid_key, "Pytest_Routers")
        )
        conn.commit()
    return {"Authorization": f"Bearer {valid_key}"}

@patch("core.mt5_engine.MT5Engine.simulate_trade")
def test_simulate_trade_route(mock_simulate, client, auth_headers):
    """Verifies the /simulate/ endpoint correctly parses payloads and returns expected schema."""
    # Mock the engine's return dictionary
    mock_simulate.return_value = {"margin_required": 50.0, "expected_profit": 15.0}
    
    payload = {
        "symbol": "EURUSD",
        "volume": 0.1,
        "type": "BUY",
        "price_open": 1.05,
        "price_close": 1.06
    }
    
    response = client.post("/marketserver/api/trade/simulate/", json=payload, headers=auth_headers)
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["margin_required"] == 50.0
    assert data["expected_profit"] == 15.0
    
    # Ensure the router passed the variables to the engine exactly as received
    mock_simulate.assert_called_once_with(
        symbol="EURUSD", volume=0.1, order_type_str="BUY", price_open=1.05, price_close=1.06
    )

@patch("core.mt5_engine.MT5Engine.execute_order")
def test_execute_trade_route(mock_execute, client, auth_headers):
    """Verifies the /execute/ endpoint handles market orders successfully."""
    # Mock the MT5 order return dictionary
    mock_execute.return_value = {"order": 99999, "retcode": 10009}
    
    payload = {
        "symbol": "EURUSD",
        "volume": 0.1,
        "type": "BUY"
    }
    
    response = client.post("/marketserver/api/trade/execute/", json=payload, headers=auth_headers)
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["ticket"] == 99999
    
    # Verify optional fields default to 0.0 as defined in the schema
    mock_execute.assert_called_once_with(
        symbol="EURUSD", volume=0.1, order_type_str="BUY", 
        target_price=0.0, stop_loss=0.0, take_profit=0.0
    )

@patch("core.mt5_engine.MT5Engine.get_terminal_info")
@patch("core.mt5_engine.MT5Engine.get_account_info")
@patch("core.mt5_engine.MT5Engine.get_positions_total", return_value=2)
@patch("core.mt5_engine.MT5Engine.get_orders_total", return_value=1)
def test_stat_route(mock_orders, mock_pos, mock_acc, mock_term, client, auth_headers):
    """Verifies the /stat/ endpoint aggregates MT5 and OS metrics."""
    mock_term.return_value = {"connected": True, "build": 4150, "ping_last": 45.2, "trade_allowed": True}
    mock_acc.return_value = {"name": "Test User", "company": "TestBroker", "server": "Test-Server", "balance": 10000.0, "currency": "USD"}

    response = client.get("/marketserver/api/stat/", headers=auth_headers)
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["mt5"]["broker"] == "TestBroker"
    assert data["mt5"]["open_positions_count"] == 2
    assert "ram_total_mb" in data["server"]

@patch("core.mt5_engine.MT5Engine.get_all_symbols")
def test_symbols_route(mock_symbols, client, auth_headers):
    """Verifies the /symbols/all/ endpoint formats raw MT5 tuples into the API schema."""
    mock_symbols.return_value = [{
        "name": "EURUSD", "path": "Forex\\Majors\\EURUSD", "description": "Euro vs US Dollar",
        "digits": 5, "trade_contract_size": 100000.0
    }]
    
    response = client.get("/marketserver/api/symbols/all/", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["symbols"][0]["name"] == "EURUSD"
    assert data["symbols"][0]["class"] == "Majors"

@patch("core.mt5_engine.MT5Engine.get_rates_from_pos")
def test_recent_market_data(mock_rates, client, auth_headers):
    """Verifies the /recent/ endpoint formats OHLCV data."""
    mock_rates.return_value = [{
        "time": 1700000000, "iso_time": "2023-11-14T22:13:20+00:00",
        "open": 1.05, "high": 1.06, "low": 1.04, "close": 1.055,
        "tick_volume": 100, "real_volume": 0, "spread": 2
    }]
    
    response = client.get("/marketserver/api/recent/?symbol=EURUSD&timeframe=H1&count=1", headers=auth_headers)
    
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "EURUSD"
    assert len(data["price_action"]) == 1
    assert data["price_action"][0]["close"] == 1.055

@patch("core.mt5_engine.MT5Engine.get_order_book")
def test_order_book_success(mock_book, client, auth_headers):
    """Verifies the /book/ endpoint handles successful DOM snapshots."""
    mock_book.return_value = {
        "bids": [{"type": 2, "price": 1.05, "volume": 10, "volume_real": 10.0}],
        "asks": [{"type": 1, "price": 1.051, "volume": 15, "volume_real": 15.0}]
    }
    
    response = client.get("/marketserver/api/book/?symbol=EURUSD", headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()["bids"]) == 1

@patch("core.mt5_engine.MT5Engine.get_order_book")
def test_order_book_unsupported(mock_book, client, auth_headers):
    """Verifies the /book/ endpoint correctly traps brokers failing to provide Level 2 data."""
    mock_book.side_effect = ValueError("Broker does not support Level 2 (DOM) data for SpotBrent.")
    
    response = client.get("/marketserver/api/book/?symbol=SpotBrent", headers=auth_headers)
    assert response.status_code == 404
    assert "does not support Level 2" in response.json()["detail"]

@patch("core.mt5_engine.MT5Engine.get_terminal_info")
@patch("os.path.exists")
@patch("builtins.open", new_callable=mock_open, read_data="time,event_id,event_name,currency,importance,actual_value,forecast_value,prev_value\n1700000000,999,Test Rate Decision,USD,3,5250000,5000000,5000000\n")
def test_calendar_route(mock_file, mock_exists, mock_term, client, auth_headers):
    """Verifies the /calendar/ endpoint parses MQL5 CSV exports safely."""
    # Mock MT5 returning a fake Windows directory path
    mock_term.return_value = {"data_path": "C:\\Mock\\MT5\\Data"}
    mock_exists.return_value = True # Pretend the CSV exists
    
    # We must patch the normalizer so it doesn't crash on the fake timestamp
    with patch("core.mt5_engine.MT5Engine._normalize_time", return_value=(1700000000, "2023-11-14T22:13:20+00:00")):
        response = client.get("/marketserver/api/calendar/?importance=3&currency=USD", headers=auth_headers)
        
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["events"][0]["event_name"] == "Test Rate Decision"
    # Ensure the string division by 1,000,000 for MT5 values worked
    assert data["events"][0]["actual"] == 5.25

# --- Trade Management Tests ---

@patch("core.mt5_engine.MT5Engine.close_position")
def test_close_position_route(mock_close, client, auth_headers):
    """Verifies the /close/ endpoint correctly maps the ticket ID to the engine."""
    mock_close.return_value = {"order": 123456, "retcode": 10009}
    
    response = client.post("/marketserver/api/trade/close/", json={"ticket": 123456}, headers=auth_headers)
    
    assert response.status_code == 200
    assert response.json()["ticket"] == 123456
    mock_close.assert_called_once_with(123456)

@patch("core.mt5_engine.MT5Engine.get_open_positions")
@patch("core.mt5_engine.MT5Engine.close_position")
def test_flatten_positions_route(mock_close, mock_get_pos, client, auth_headers):
    """Verifies the emergency flatten button closes all fetched tickets."""
    mock_get_pos.return_value = [{"ticket": 111}, {"ticket": 222}]
    mock_close.return_value = {"retcode": 10009}
    
    response = client.post("/marketserver/api/trade/flatten/", headers=auth_headers)
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "executed"
    assert len(data["summary"]["closed"]) == 2
    assert mock_close.call_count == 2

@patch("core.mt5_engine.MT5Engine.get_trade_history")
def test_trade_history_route(mock_history, client, auth_headers):
    """Verifies history fetches and correctly sums net PnL and commissions."""
    # We must provide all fields required by the TradeDeal schema to pass Pydantic validation
    base_deal = {
        "order": 1, "time": 1700000000, "time_msc": 1700000000000, 
        "type": 0, "entry": 1, "magic": 0, "position_id": 1, 
        "reason": 0, "volume": 1.0, "price": 1.05, "fee": 0.0, 
        "symbol": "EURUSD", "comment": "test", "external_id": ""
    }
    
    mock_history.return_value = [
        {**base_deal, "ticket": 1, "profit": 50.0, "swap": -2.0, "commission": -1.0},
        {**base_deal, "ticket": 2, "profit": -10.0, "swap": 0.0, "commission": -1.0}
    ]
    
    response = client.get("/marketserver/api/trade/history/?days=7", headers=auth_headers)
    
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    assert data["net_pnl"] == 36.0  # (50 - 2 - 1) + (-10 - 1) = 36.0
    assert data["total_commission"] == -2.0

# --- Advanced Market Data Tests ---

@patch("core.mt5_engine.MT5Engine.get_rates_from_pos")
def test_market_movers_route(mock_rates, client, auth_headers):
    """Verifies the /movers/ endpoint accurately fetches daily open/close differences."""
    mock_rates.return_value = [{"open": 1.0500, "close": 1.0600}]
    
    # Corrected the URL path from /recent/movers/ to /movers/
    response = client.get("/marketserver/api/movers/?symbols=EURUSD", headers=auth_headers)
    
    assert response.status_code == 200
    data = response.json()
    assert data["movers"][0]["symbol"] == "EURUSD"
    assert data["movers"][0]["close"] == 1.0600

@patch("core.mt5_engine.MT5Engine.get_recent_ticks")
def test_recent_ticks_route(mock_ticks, client, auth_headers):
    """Verifies the /ticks/recent/ endpoint returns high-resolution Level 1 data."""
    mock_ticks.return_value = [{
        "time": 1700000000, "iso_time": "2023-11-14T22:13:20+00:00",
        "bid": 1.0500, "ask": 1.0501, "last": 1.0500,
        "volume": 0, "time_msc": 1700000000123, "flags": 4, "volume_real": 0.0
    }]
    
    response = client.get("/marketserver/api/ticks/recent/?symbol=EURUSD&count=1", headers=auth_headers)
    
    assert response.status_code == 200
    assert response.json()["ticks"][0]["bid"] == 1.0500