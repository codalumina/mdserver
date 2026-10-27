"""
MDServer Entry Point and Application Factory.

This module initializes the FastAPI application, mounts the security dependencies,
and registers all API routing modules. It also manages the critical lifespan 
events required to safely boot and terminate the WINE-encapsulated MetaTrader 5 
terminal alongside the web server.
"""

import subprocess
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from core.config import settings
from core.logger import logger
from core.mt5_engine import engine
from core.security import verify_api_key, init_db
from api.routers import market, trade, symbols, calendar, stat

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages the startup and shutdown lifecycle of the application.
    
    Startup:
        - Initializes the SQLite security database.
        - Boots the MT5 Engine (establishes the IPC connection to the terminal).
    
    Shutdown:
        - Gracefully closes the MT5 Engine connection.
        - Executes a defensive OS-level taskkill. Under WINE, the MT5 GUI 
          (terminal64.exe) often becomes a zombie process after the Python 
          script terminates. This guarantees a clean teardown to prevent 
          memory leaks across server reboots.
    """
    logger.info("Booting MDServer FastAPI application...")
    init_db()
    
    if not engine.start():
        logger.critical("Failed to start MT5 Engine. Data routes will fail.")
        
    yield
    
    logger.info("Shutting down MDServer...")
    engine.stop()
    
    # Defensive Teardown: Force-kill the MT5 GUI to prevent WINE zombies
    logger.info("Executing taskkill on terminal64.exe to guarantee clean teardown...")
    subprocess.run(["taskkill", "/F", "/IM", "terminal64.exe"], check=False, capture_output=True)

app = FastAPI(
    title="MDServer",
    description="Decoupled MT5 REST API for MarketDash",
    version="1.0.0",
    lifespan=lifespan,
    dependencies=[Depends(verify_api_key)]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(market.router, prefix=settings.API_V1_STR, tags=["Market Data"])
app.include_router(trade.router, prefix=f"{settings.API_V1_STR}/trade", tags=["Trade Execution"])
app.include_router(symbols.router, prefix=f"{settings.API_V1_STR}/symbols", tags=["Market Symbols"])
app.include_router(calendar.router, prefix=f"{settings.API_V1_STR}/calendar", tags=["Economic Calendar"])
app.include_router(stat.router, prefix=f"{settings.API_V1_STR}/stat", tags=["System Statistics"])

if __name__ == "__main__":
    logger.info(f"Starting Uvicorn server on {settings.HOST}:{settings.PORT}")
    # log_config=None forces Uvicorn to use our custom forensic logging pipeline
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=False, log_config=None)