import pytest
from unittest.mock import patch
from core.mt5_engine import MT5Engine

@pytest.fixture
def engine():
    """Returns a fresh instance of the MT5Engine for testing."""
    return MT5Engine()

def test_normalize_time(engine):
    """Verifies broker time is successfully parsed into UTC timestamps and ISO strings."""
    # Mock timestamp: 1700000000 (roughly Nov 2023)
    raw_mt5_time = 1700000000
    utc_ts, iso_str = engine._normalize_time(raw_mt5_time)
    
    assert isinstance(utc_ts, int)
    assert isinstance(iso_str, str)
    assert "T" in iso_str
    assert "+00:00" in iso_str

@patch("core.mt5_engine.mt5")
def test_simulate_trade_engine(mock_mt5, engine):
    """Verifies engine calculates trade metrics using MT5 native functions."""
    # Setup mocks for MT5 constants and function returns
    mock_mt5.ORDER_TYPE_BUY = 0
    mock_mt5.order_calc_margin.return_value = 100.50
    mock_mt5.order_calc_profit.return_value = 25.0
    
    result = engine.simulate_trade(
        symbol="EURUSD",
        volume=1.0,
        order_type_str="BUY",
        price_open=1.05,
        price_close=1.06
    )
    
    assert result["margin_required"] == 100.50
    assert result["expected_profit"] == 25.0
    
    # Ensure MT5 was interacted with correctly under the hood
    mock_mt5.symbol_select.assert_called_once_with("EURUSD", True)
    mock_mt5.order_calc_margin.assert_called_once_with(0, "EURUSD", 1.0, 1.05)
    mock_mt5.order_calc_profit.assert_called_once_with(0, "EURUSD", 1.0, 1.05, 1.06)

@patch("core.mt5_engine.mt5")
def test_simulate_trade_engine_invalid_type(mock_mt5, engine):
    """Verifies engine correctly traps and rejects unsupported order types during simulation."""
    with pytest.raises(ValueError, match="Simulation requires a basic BUY or SELL type"):
        engine.simulate_trade(
            symbol="EURUSD",
            volume=1.0,
            order_type_str="INVALID_TYPE",
            price_open=1.05,
            price_close=1.06
        )