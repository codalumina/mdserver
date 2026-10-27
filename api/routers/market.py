"""
Market Data Routing Module.

This module exposes read-only HTTP endpoints for extracting market data from the 
MT5 terminal. It handles single-asset OHLCV histories, high-resolution tick streams, 
Depth of Market (DOM) snapshots, and bulk concurrent matrix fetches. It ensures 
graceful degradation when queried assets lack specific broker feeds (e.g., CFDs 
missing Level 2 DOM).
"""

from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query, status

from core.mt5_engine import engine
from core.logger import logger
from schemas.mt5 import PriceActionResponse, BulkPriceActionResponse, MarketMoversResponse, TickDataResponse, OrderBookResponse

router = APIRouter()

@router.get("/recent/", response_model=PriceActionResponse)
def recent_price_action(
    symbol: str = Query(..., description="Target symbol (e.g., EURUSD)"),
    timeframe: str = Query(..., description="Chart timeframe (e.g., H1, D1)"),
    count: int = Query(100, description="Number of candles to retrieve")
):
    """
    Retrieve the most recent OHLCV price action data for a single asset.
    
    Args:
        symbol (str): The target trading asset (e.g., 'EURUSD').
        timeframe (str): The chart resolution (e.g., 'H1', 'M15').
        count (int): The number of recent candles to fetch.
        
    Returns:
        PriceActionResponse: A structured payload containing parsed OHLCV dictionaries.
        
    Raises:
        HTTPException: 400 if the timeframe is invalid, 404 if no data exists.
    """
    tf_map = engine.get_timeframes()
    tf_constant = tf_map.get(timeframe.upper())

    if tf_constant is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid timeframe. Valid options: {list(tf_map.keys())}"
        )

    parsed_rates = engine.get_rates_from_pos(symbol, tf_constant, 0, count)

    if not parsed_rates:
        logger.warning(f"No price action found for {symbol} on {timeframe}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No data available for symbol: {symbol}"
        )

    return PriceActionResponse(
        symbol=symbol,
        timeframe=timeframe.upper(),
        count=len(parsed_rates),
        price_action=parsed_rates,
        timestamp=datetime.now(timezone.utc).isoformat()
    )

@router.get("/ticks/recent/", response_model=TickDataResponse)
def recent_ticks(
    symbol: str = Query(..., description="Target symbol (e.g., EURUSD)"),
    count: int = Query(100, le=5000, description="Number of ticks to retrieve (max 5000)")
):
    """
    Retrieve the most recent Level 1 tick data (Bid/Ask).
    
    Fetches raw, unaggregated price changes. Useful for order flow analysis 
    or building custom lower-timeframe charts.
    """
    ticks = engine.get_recent_ticks(symbol, count)
    
    if not ticks:
        logger.warning(f"No tick data found for {symbol}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No tick data available for symbol: {symbol}"
        )

    return TickDataResponse(
        symbol=symbol,
        count=len(ticks),
        ticks=ticks,
        timestamp=datetime.now(timezone.utc).isoformat()
    )

@router.get("/book/", response_model=OrderBookResponse)
def order_book(symbol: str = Query(..., description="Target symbol (e.g., EURUSD)")):
    """
    Retrieve a snapshot of the Level 2 Depth of Market (Order Book).
    
    CFD and Forex brokers often restrict Level 2 DOM data. This endpoint traps 
    the MT5 subscription failure and degrades gracefully to a 404 Not Found 
    rather than crashing the server.
    """
    try:
        book_data = engine.get_order_book(symbol)
        return OrderBookResponse(
            symbol=symbol,
            bids=book_data["bids"],
            asks=book_data["asks"],
            timestamp=datetime.now(timezone.utc).isoformat()
        )
    except ValueError as ve:
        logger.warning(str(ve))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as e:
        logger.error(f"Failed to fetch order book for {symbol}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/historical/", response_model=PriceActionResponse)
def historical_price_range(
    symbol: str = Query(...),
    timeframe: str = Query(...),
    start_date: str = Query(...),
    end_date: str = Query(...)
):
    """
    Retrieve historical OHLC data bounded by a strict UTC date range.
    
    Note on timezones: The frontend requests exact UTC boundaries. This route 
    shifts those UTC datetimes into the broker's local naive timezone before 
    querying MT5, ensuring the returned dataset strictly matches the requested window.
    """
    tf_map = engine.get_timeframes()
    tf_constant = tf_map.get(timeframe.upper())
    if tf_constant is None:
        raise HTTPException(status_code=400, detail="Invalid timeframe.")

    start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))

    # Convert true UTC request into the broker's local timezone for the MT5 query
    broker_start = start_dt.astimezone(engine.broker_tz).replace(tzinfo=None)
    broker_end = end_dt.astimezone(engine.broker_tz).replace(tzinfo=None)

    parsed_rates = engine.get_rates_range(symbol, tf_constant, broker_start, broker_end)
    
    if not parsed_rates:
        raise HTTPException(status_code=404, detail="No historical data found.")

    return PriceActionResponse(
        symbol=symbol, timeframe=timeframe.upper(),
        count=len(parsed_rates), price_action=parsed_rates,
        timestamp=datetime.now(timezone.utc).isoformat()
    )

@router.get("/recent/bulk/", response_model=BulkPriceActionResponse)
def bulk_recent_price_action(
    symbols: str = Query(...),
    timeframes: str = Query("H1,H4,D1,W1,MN1"),
    count: int = Query(80)
):
    """
    Retrieve OHLC candles concurrently for multiple symbols and timeframes.
    
    Note: To prevent the MT5 terminal from freezing while aggregating deep 
    historical data, queries for Weekly (W1) and Monthly (MN1) timeframes 
    are strictly clamped to 5 periods.
    """
    target_symbols = [s.strip() for s in symbols.split(",") if s.strip()]
    target_tfs = [tf.strip().upper() for tf in timeframes.split(",") if tf.strip()]
    
    tf_map = engine.get_timeframes()
    data_matrix = {}
    
    for sym in target_symbols:
        data_matrix[sym] = {}
        
        for tf_str in target_tfs:
            tf_constant = tf_map.get(tf_str)
            if tf_constant is None:
                continue
                
            # Prevent freezing on deep W1/MN1 history
            tf_count = 5 if tf_str in ["W1", "MN1"] else count
            parsed_rates = engine.get_rates_from_pos(sym, tf_constant, 0, tf_count)
            data_matrix[sym][tf_str] = parsed_rates
            
    return BulkPriceActionResponse(
        count_requested=count, symbols=target_symbols,
        timeframes=target_tfs, data=data_matrix,
        timestamp=datetime.now(timezone.utc).isoformat()
    )

@router.get("/movers/", response_model=MarketMoversResponse)
def market_movers(symbols: str = Query(None)):
    """
    Fetch the most recent daily (D1) open and close prices to calculate market movers.
    If no specific symbols are passed, it scans all broker-provided assets.
    """
    if symbols:
        target_symbols = [s.strip() for s in symbols.split(",") if s.strip()]
    else:
        all_syms = engine.get_all_symbols()
        target_symbols = [s.get("name") for s in all_syms if s.get("name")]
        
    movers = []
    tf_constant = engine.get_timeframes().get("D1")
    for sym in target_symbols:
        rates = engine.get_rates_from_pos(sym, tf_constant, 0, 1)
        if rates:
            movers.append({
                "symbol": sym,
                "open": float(rates[0]["open"]),
                "close": float(rates[0]["close"])
            })
            
    return MarketMoversResponse(
        status="success", 
        movers=movers,
        timestamp=datetime.now(timezone.utc).isoformat()
    )