"""
Data Validation and Serialization Schemas.

This module defines the Pydantic models used across the API to strictly enforce 
JSON request/response contracts. These schemas ensure that all C++ MetaTrader 5 
data structures are safely serialized for frontend consumption and automatically 
generate the interactive OpenAPI/Swagger documentation.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union
from datetime import datetime

class OHLCV(BaseModel):
    time: int
    iso_time: str
    open: float
    high: float
    low: float
    close: float
    tick_volume: int
    real_volume: int  # Added for future exchange volume support
    spread: int       # Added to catch the full MT5 array output

class PriceActionResponse(BaseModel):
    symbol: str
    timeframe: str
    count: int
    price_action: List[OHLCV]
    timestamp: str

class Tick(BaseModel):
    time: int
    iso_time: str
    bid: float
    ask: float
    last: float
    volume: int
    time_msc: int
    flags: int
    volume_real: float

class TickDataResponse(BaseModel):
    symbol: str
    count: int
    ticks: List[Tick]
    timestamp: str

class BookEntry(BaseModel):
    type: int
    price: float
    volume: int
    volume_real: float

class OrderBookResponse(BaseModel):
    symbol: str
    bids: List[BookEntry]
    asks: List[BookEntry]
    timestamp: str

class Position(BaseModel):
    ticket: int
    time: int
    time_msc: int
    time_update: int
    time_update_msc: int
    type: int
    magic: int
    identifier: int
    reason: int
    volume: float
    price_open: float
    sl: float
    tp: float
    price_current: float
    swap: float
    profit: float
    symbol: str
    comment: str
    external_id: str
    nominal_value: float
    margin: float

class OpenPositionsResponse(BaseModel):
    count: int
    positions: List[Position]
    timestamp: str

class ActiveOrder(BaseModel):
    ticket: int
    time_setup: int
    type: int
    state: int
    volume_initial: float
    volume_current: float
    price_open: float
    sl: float
    tp: float
    price_current: float
    symbol: str
    comment: str

class ActiveOrdersResponse(BaseModel):
    count: int
    orders: List[ActiveOrder]
    timestamp: str

class CancelOrderRequest(BaseModel):
    ticket: int

class TradeDeal(BaseModel):
    ticket: int
    order: int
    time: int
    time_msc: int
    type: int
    entry: int
    magic: int
    position_id: int
    reason: int
    volume: float
    price: float
    commission: float
    swap: float
    profit: float
    fee: float
    symbol: str
    comment: str
    external_id: str

class TradeHistoryResponse(BaseModel):
    count: int
    net_pnl: float
    total_commission: float
    deals: List[TradeDeal]
    timestamp: str

class ExecuteTradeRequest(BaseModel):
    symbol: str
    volume: float
    type: str  # BUY, SELL, BUY_LIMIT, SELL_LIMIT, etc.
    target_price: Optional[float] = 0.0
    stop_loss: Optional[float] = 0.0
    take_profit: Optional[float] = 0.0
    client_timestamp: Optional[str] = None

class SimulateTradeRequest(BaseModel):
    symbol: str
    volume: float
    type: str  # BUY, SELL
    price_open: float
    price_close: float

class TradeSimulationResponse(BaseModel):
    status: str
    margin_required: Optional[float]
    expected_profit: Optional[float]
    timestamp: str

class ClosePositionRequest(BaseModel):
    ticket: int
    client_timestamp: Optional[str] = None

class TradeExecutionResponse(BaseModel):
    status: str
    ticket: Optional[int] = None
    details: Dict[str, Any]
    timestamp: str

class SymbolInfo(BaseModel):
    name: str
    description: Optional[str] = None
    exchange: Optional[str] = None
    isin: Optional[str] = None
    digits: Optional[int] = None
    point: Optional[float] = None
    volume_min: Optional[float] = None
    volume_step: Optional[float] = None
    volume_max: Optional[float] = None
    trade_contract_size: Optional[float] = None
    asset_class: str = Field(alias="class", default="Unknown")
    group: str = "Unknown"

class AllSymbolsResponse(BaseModel):
    count: int
    symbols: List[SymbolInfo]
    timestamp: str

class CalendarEvent(BaseModel):
    time: int
    iso_time: str
    event_id: str
    event_name: str
    currency: str
    country: str
    importance: int
    actual: Optional[float] = None
    forecast: Optional[float] = None
    previous: Optional[float] = None

class CalendarResponse(BaseModel):
    count: int
    events: List[CalendarEvent]
    timestamp: str

class Mover(BaseModel):
    symbol: str
    open: float
    close: float

class MarketMoversResponse(BaseModel):
    status: str
    movers: List[Mover]
    timestamp: str  

class BulkPriceActionResponse(BaseModel):
    count_requested: int
    symbols: List[str]
    timeframes: List[str]
    data: Dict[str, Dict[str, List[OHLCV]]]
    timestamp: str

class MT5Stats(BaseModel):
    connected: bool
    broker: str
    server: str
    account_name_initials: str
    leverage: int
    ping: float
    build: int
    account_currency: str
    balance: float
    equity: float
    floating_profit: float
    margin_free: float
    margin_level_pct: float
    trade_allowed_by_broker: bool
    algo_trading_allowed: bool
    open_positions_count: int
    pending_orders_count: int

class OSStats(BaseModel):
    python_architecture: str
    wine_version: str
    ram_total_mb: Union[float, str] = "N/A"
    ram_available_mb: Union[float, str] = "N/A"
    ram_used_mb: Union[float, str] = "N/A"
    cpu_load_avg: Union[List[str], str] = "N/A"
    uptime_days: Union[float, str] = "N/A"
    uptime_hours: Union[float, str] = "N/A"
    cpu_cores: Union[int, str] = "N/A"
    cpu_model: str = "N/A"
    disk_total_gb: Union[float, str] = "N/A"
    disk_free_gb: Union[float, str] = "N/A"
    linux_read_error: str = "N/A"

class ServerStatResponse(BaseModel):
    status: str
    timestamp: str
    mt5: MT5Stats
    server: OSStats