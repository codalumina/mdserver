"""
Forensic Logging and Telemetry Pipeline.

This module unifies the application's logging output. It strips FastAPI/Uvicorn's 
default unformatted loggers and routes all traffic through a custom formatter. 
Output is dual-routed to an ANSI-colored console stream and a daily-rotating 
forensic file for long-term auditing.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from core.config import settings

# Ensure log directory exists
settings.LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = settings.LOG_DIR / "system.log"

logger = logging.getLogger("MDServer")
logger.setLevel(logging.DEBUG)

formatter = logging.Formatter(
    fmt="%(asctime)s | %(levelname)-8s | %(module)s:%(funcName)s:%(lineno)d | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

class ColoredConsoleFormatter(logging.Formatter):
    """
    Injects ANSI escape codes into the console output to color-code log levels, 
    improving visual parsing during live debugging.
    """
    
    COLORS = {
        logging.DEBUG: "\033[36m",      # Cyan
        logging.INFO: "\033[32m",       # Green
        logging.WARNING: "\033[33m",    # Yellow
        logging.ERROR: "\033[31m",      # Red
        logging.CRITICAL: "\033[1;31m"  # Bold Red
    }
    RESET = "\033[0m"

    def format(self, record):
        formatted_message = super().format(record)
        color = self.COLORS.get(record.levelno, self.RESET)
        return f"{color}{formatted_message}{self.RESET}"

console_formatter = ColoredConsoleFormatter(
    fmt="%(asctime)s | %(levelname)-8s | %(module)s:%(funcName)s:%(lineno)d | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# File Handler (10MB per file, keep last 5 backups)
file_handler = RotatingFileHandler(
    LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
)
file_handler.setFormatter(formatter)
file_handler.setLevel(logging.DEBUG)

# Console Handler (Stdout)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(console_formatter)
console_handler.setLevel(logging.INFO)

logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Intercept Uvicorn's internal loggers to unify formatting and write to system.log
for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
    u_logger = logging.getLogger(logger_name)
    u_logger.handlers = []  # Strip Uvicorn's default unformatted handlers
    u_logger.setLevel(logging.INFO)
    u_logger.addHandler(file_handler)
    u_logger.addHandler(console_handler)
    u_logger.propagate = False