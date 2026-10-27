import pytest
import tempfile
import sqlite3
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

# 1. Create a temporary database path for the entire test session
@pytest.fixture(scope="session")
def test_db_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test_mdserver.sqlite3"

# 2. Patch the settings and lifespan dependencies BEFORE importing the app
@pytest.fixture(scope="module")
def client(test_db_path):
    with patch("core.config.settings.DB_PATH", test_db_path), \
         patch("core.mt5_engine.MT5Engine.start", return_value=True), \
         patch("core.mt5_engine.MT5Engine.stop", return_value=None), \
         patch("subprocess.run"):
        
        # Import inside the patched context to ensure overridden variables are used
        from main import app
        from core.security import init_db
        
        # Initialize the temporary SQLite tables
        init_db()
        
        with TestClient(app) as c:
            yield c