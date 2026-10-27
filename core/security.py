"""
Zero-Trust Boundary and Authentication Layer.

This module enforces a strict Bearer token authentication schema across all 
FastAPI routes. It relies on a local SQLite database to store and validate 
hashed or raw API keys, ensuring that no unauthorized client can interact 
with the live MT5 terminal.
"""

import sqlite3
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader
from core.config import settings
from core.logger import logger

API_KEY_NAME = "Authorization"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=True)

import sqlite3
from core.config import settings
from core.logger import logger

def init_db():
    """
    Initializes the SQLite database for API keys.
    
    Creates the required data directories if they do not exist and provisions 
    the schema. Alerts the administrator via standard output if the system 
    boots without any active access tokens.
    """

    try:
        settings.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(settings.DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key_value TEXT UNIQUE NOT NULL,
                    client_name TEXT NOT NULL,
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Security Check: Warn the user if no keys exist
            cursor.execute("SELECT COUNT(*) FROM api_keys")
            if cursor.fetchone()[0] == 0:
                logger.warning(
                    "SECURITY ALERT: No API keys found! "
                    "You must run `WINEPREFIX=~/.mdserver wine python cli.py create-key --client Admin` to generate a secure access token."
                )
            conn.commit()
    except Exception as e:
        logger.critical(f"Failed to initialize security database: {e}")
        raise

def verify_api_key(api_key_header: str = Security(api_key_header)):
    """
    Validates the Bearer token against the SQLite database.
    
    Automatically strips the 'Bearer ' prefix if present and queries the active 
    keys table. If the key is missing, fabricated, or revoked, it halts the 
    request and raises a 403 Forbidden exception before the router is accessed.
    
    Args:
        api_key_header (str): The raw authorization header injected by FastAPI.
        
    Returns:
        str: The validated token string.
    """
    
    token = api_key_header.replace("Bearer ", "") if "Bearer " in api_key_header else api_key_header
    
    try:
        with sqlite3.connect(settings.DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT is_active, client_name FROM api_keys WHERE key_value = ?", 
                (token,)
            )
            result = cursor.fetchone()
            
            if not result or not result[0]:
                logger.warning(f"Unauthorized access attempt with token: {token[:4]}***")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, 
                    detail="Could not validate credentials or key is revoked."
                )
            return token
    except sqlite3.Error as e:
        logger.error(f"Database error during token validation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Internal security error."
        )