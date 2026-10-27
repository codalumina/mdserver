import sqlite3
from unittest.mock import patch

def test_no_api_key(client):
    """Ensure requests without an Authorization header are rejected."""
    response = client.get("/marketserver/api/stat/")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"

def test_invalid_api_key(client):
    """Ensure requests with fabricated or revoked keys are rejected."""
    response = client.get(
        "/marketserver/api/stat/", 
        headers={"Authorization": "Bearer fabricated_key_123"}
    )
    assert response.status_code == 403
    assert "Could not validate credentials" in response.json()["detail"]

def test_valid_api_key(client, test_db_path):
    """Ensure a valid key grants access to the system."""
    valid_key = "mdserver_test_key_999"
    
    # Manually inject a known valid key into our temporary test database
    with sqlite3.connect(test_db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO api_keys (key_value, client_name) VALUES (?, ?)",
            (valid_key, "Pytest_Runner")
        )
        conn.commit()

    # We must mock the MT5 Engine methods the /stat/ endpoint relies on
    with patch("core.mt5_engine.MT5Engine.get_terminal_info", return_value={"connected": True, "build": 4150, "ping_last": 45.2}), \
         patch("core.mt5_engine.MT5Engine.get_account_info", return_value={"name": "Test User", "balance": 10000.0, "currency": "USD"}), \
         patch("core.mt5_engine.MT5Engine.get_positions_total", return_value=0), \
         patch("core.mt5_engine.MT5Engine.get_orders_total", return_value=0):
        
        response = client.get(
            "/marketserver/api/stat/", 
            headers={"Authorization": f"Bearer {valid_key}"}
        )
        
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
        assert response.json()["mt5"]["connected"] is True