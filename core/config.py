"""
Application Configuration and Environment Management.

This module leverages Pydantic's BaseSettings to automatically load and validate 
environment variables from a `.env` file. It establishes the global paths, 
server bindings, and MetaTrader 5 C++ terminal credentials used across the system.
"""

import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Global configuration schema. Attributes are overridden by `.env` variables 
    if they exist, ensuring sensitive credentials are not hardcoded.
    """

    # Server Binding
    HOST: str = "0.0.0.0"
    PORT: int = 14234
    API_V1_STR: str = "/marketserver/api"

    # MT5 Credentials
    MT5_LOGIN: int = 0
    MT5_PASSWORD: str = ""
    MT5_SERVER: str = ""
    MT5_TIMEZONE: str = "Europe/Athens"
    TERMINAL_PATH: str = "C:\\Program Files\\MetaTrader 5\\terminal64.exe"

    # Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    LOG_DIR: Path = DATA_DIR / "logs"
    DB_PATH: Path = DATA_DIR / "mdserver.sqlite3"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

settings = Settings()