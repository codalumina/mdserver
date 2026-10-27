"""
Trade Execution and Risk Management Routing Module.

This module exposes state-changing HTTP endpoints for interacting with live 
broker accounts. It handles order entry, trade simulation (margin/profit checks), 
active position management, and emergency bulk-flattening.
"""

from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, status, Query

from core.mt5_engine import engine
from core.logger import logger
from schemas.mt5 import (
    OpenPositionsResponse, ActiveOrdersResponse, CancelOrderRequest,
    ExecuteTradeRequest, TradeExecutionResponse,
    ClosePositionRequest, TradeHistoryResponse,
    SimulateTradeRequest, TradeSimulationResponse
)

router = APIRouter()

@router.get("/positions/", response_model=OpenPositionsResponse)
def open_positions(symbol: str = Query(None, description="Optional symbol filter")):
    """
    Retrieve all currently open positions in the market.
    
    Optionally filters by a specific symbol. The underlying engine automatically 
    enriches the raw MT5 data with real-time nominal valuations and margin 
    requirements before returning it.
    """
    try:
        positions = engine.get_open_positions(symbol)
        return OpenPositionsResponse(
            count=len(positions),
            positions=positions,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
    except Exception as e:
        logger.error(f"Failed to fetch positions: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/orders/", response_model=ActiveOrdersResponse)
def active_orders(symbol: str = Query(None, description="Optional symbol filter")):
    """
    Retrieve all currently active pending orders.
    
    Returns resting limit and stop orders that have not yet been triggered 
    or filled by the live market. Can be optionally filtered by symbol.
    """
    try:
        orders = engine.get_active_orders(symbol)
        return ActiveOrdersResponse(
            count=len(orders),
            orders=orders,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
    except Exception as e:
        logger.error(f"Failed to fetch active orders: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.post("/simulate/", response_model=TradeSimulationResponse)
def simulate_trade_endpoint(request: SimulateTradeRequest):
    """
    Calculate required margin and expected monetary profit before execution.
    
    Leverages MT5's internal calculator to evaluate risk using the broker's 
    current leverage and contract specifications without exposing capital.
    
    Args:
        request (SimulateTradeRequest): The theoretical trade parameters.
        
    Returns:
        TradeSimulationResponse: Margins and expected profits in the account's base currency.
    """
    try:
        result = engine.simulate_trade(
            symbol=request.symbol,
            volume=request.volume,
            order_type_str=request.type,
            price_open=request.price_open,
            price_close=request.price_close
        )
        return TradeSimulationResponse(
            status="success",
            margin_required=result["margin_required"],
            expected_profit=result["expected_profit"],
            timestamp=datetime.now(timezone.utc).isoformat()
        )
    except Exception as e:
        logger.warning(f"Trade simulation failed: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/execute/", response_model=TradeExecutionResponse)
def execute_trade(request: ExecuteTradeRequest):
    """
    Executes a market or pending order.
    
    Optional parameters like target_price, stop_loss, and take_profit default 
    to 0.0 at the schema level if omitted by the client.
    """
    try:
        result = engine.execute_order(
            symbol=request.symbol,
            volume=request.volume,
            order_type_str=request.type,
            target_price=request.target_price,
            stop_loss=request.stop_loss,
            take_profit=request.take_profit
        )
        return TradeExecutionResponse(
            status="success",
            ticket=result.get("order"),
            details=result,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
    except Exception as e:
        logger.warning(f"Trade execution rejected: {e}")
        raise HTTPException(status_code=status.HTTP_406_NOT_ACCEPTABLE, detail=str(e))

@router.post("/close/", response_model=TradeExecutionResponse)
def close_position(request: ClosePositionRequest):
    """
    Close a specific open position by crossing the spread.
    
    Args:
        request (ClosePositionRequest): Payload containing the exact integer ticket ID.
    """
    try:
        result = engine.close_position(request.ticket)
        return TradeExecutionResponse(
            status="success",
            ticket=result.get("order"),
            details=result,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
    except Exception as e:
        logger.warning(f"Position close rejected for #{request.ticket}: {e}")
        raise HTTPException(status_code=status.HTTP_406_NOT_ACCEPTABLE, detail=str(e))

@router.post("/orders/cancel/", response_model=TradeExecutionResponse)
def cancel_order(request: CancelOrderRequest):
    """
    Cancel a specific resting pending order from the market.
    
    Args:
        request (CancelOrderRequest): Payload containing the exact integer ticket ID of the order to remove.
    """
    try:
        result = engine.cancel_order(request.ticket)
        return TradeExecutionResponse(
            status="success",
            ticket=result.get("order"),
            details=result,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
    except Exception as e:
        logger.warning(f"Order cancel rejected for #{request.ticket}: {e}")
        raise HTTPException(status_code=status.HTTP_406_NOT_ACCEPTABLE, detail=str(e))

@router.post("/flatten/")
def flatten_positions():
    """
    Emergency Panic Button: Iterates through and closes all open positions.
    
    Designed for fault tolerance: if one position fails to close (e.g., due to 
    a sudden requote), the loop catches the exception, logs it, and continues 
    attempting to close the remaining positions.
    """
    try:
        positions = engine.get_open_positions()
        results, errors = [], []
        
        for pos in positions:
            try:
                res = engine.close_position(pos["ticket"])
                results.append(res)
            except Exception as e:
                errors.append({"ticket": pos["ticket"], "error": str(e)})
                
        return {"status": "executed", "summary": {"closed": results, "failed": errors}}
    except Exception as e:
        logger.error(f"Panic flatten failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/history/", response_model=TradeHistoryResponse)
def trade_history(days: int = Query(30, description="Lookback window in days")):
    """
    Retrieve closed trades history and aggregate net performance.
    
    Dynamically calculates a rolling lookback window and computes total net 
    PnL (Profit + Swap + Commission) across all closed deals.
    """
    try:
        date_to = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1)
        date_from = date_to - timedelta(days=days + 1)
        
        history = engine.get_trade_history(date_from, date_to)
        
        net_pnl = sum(d.get("profit", 0.0) + d.get("swap", 0.0) + d.get("commission", 0.0) for d in history)
        total_comm = sum(d.get("commission", 0.0) for d in history)
        
        return TradeHistoryResponse(
            count=len(history),
            net_pnl=net_pnl,
            total_commission=total_comm,
            deals=history,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
    except Exception as e:
        logger.error(f"History fetch failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))