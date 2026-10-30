"""
Market Metadata Routing Module.

This module exposes the broker's asset specifications, including margin requirements,
minimum volume steps, and trade contract sizes. This is critical for frontends
to build accurate order entry forms and calculate pip values.
"""

from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, status

from core.mt5_engine import engine
from core.logger import logger
from schemas.mt5 import AllSymbolsResponse

router = APIRouter()


@router.get("/all/", response_model=AllSymbolsResponse)
def all_symbols():
    """
    Retrieve detailed metadata for all available trading symbols.

    Brokers frequently group symbols using an internal directory-style path
    (e.g., 'Forex\\Majors\\EURUSD'). This function splits that raw path to
    dynamically infer the asset class and group, allowing the frontend to
    build categorized dropdown menus automatically.
    """

    try:
        symbols = engine.get_all_symbols()
        data = []

        for sym in symbols:
            sym_meta = sym.get("path", "").split("\\")
            asset_class = sym_meta[1] if len(sym_meta) > 1 else "Unknown"
            group = sym_meta[2] if len(sym_meta) > 2 else "Unknown"

            data.append(
                {
                    "name": sym.get("name", ""),
                    "description": sym.get("description"),
                    "exchange": sym.get("exchange"),
                    "isin": sym.get("isin"),
                    "digits": sym.get("digits"),
                    "point": sym.get("point"),
                    "volume_min": sym.get("volume_min"),
                    "volume_step": sym.get("volume_step"),
                    "volume_max": sym.get("volume_max"),
                    "trade_contract_size": sym.get("trade_contract_size"),
                    "trade_tick_size": sym.get("trade_tick_size"),
                    "trade_tick_value": sym.get("trade_tick_value"),
                    "class": asset_class,
                    "group": group,
                }
            )

        return AllSymbolsResponse(
            count=len(data),
            symbols=data,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as e:
        logger.error(f"Failed to fetch symbols: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
