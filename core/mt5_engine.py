"""
MetaTrader 5 Engine Adapter Layer.

This module acts as a strict Facade isolating the C++ MetaTrader5 Python library
from the REST API. It handles all broker communication, normalizes proprietary
data structures (like numpy structured arrays and broker-local timestamps) into
standard Python types, and manages trade execution lifecycles.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import MetaTrader5 as mt5

from core.config import settings
from core.logger import logger


class MT5Engine:
    """
    Singleton-style engine for managing MT5 terminal interactions.

    Attributes:
        broker_tz (ZoneInfo): The broker's specific timezone, used to accurately
            convert MT5's naive local timestamps into strict UTC.
    """

    def __init__(self):
        self.broker_tz = ZoneInfo(settings.MT5_TIMEZONE)

    def start(self) -> bool:
        """
        Initializes the terminal and authenticates with the broker.

        Returns:
            bool: True if connection and authorization succeed, False otherwise.
        """
        logger.info(f"Initializing MT5 from: {settings.TERMINAL_PATH}")
        init_success = mt5.initialize(
            path=settings.TERMINAL_PATH, timeout=300000, portable=True
        )

        if not init_success:
            logger.critical(f"MT5 init failed: {mt5.last_error()}")
            return False

        if settings.MT5_LOGIN != 0 and settings.MT5_PASSWORD:
            logger.info(f"Logging into {settings.MT5_SERVER} as {settings.MT5_LOGIN}")
            authorized = mt5.login(
                settings.MT5_LOGIN,
                password=settings.MT5_PASSWORD,
                server=settings.MT5_SERVER,
                timeout=300000,
            )
            if not authorized:
                logger.error(f"MT5 login failed: {mt5.last_error()}")
                return False

        logger.info("MT5 Engine successfully connected and authorized.")
        return True

    def stop(self):
        """Clean shutdown of the terminal IPC connection."""
        mt5.shutdown()
        logger.info("MT5 Engine shutdown complete.")

    def get_timeframes(self) -> dict:
        """Returns a mapping of string timeframes to MT5 C++ constants."""
        return {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
            "W1": mt5.TIMEFRAME_W1,
            "MN1": mt5.TIMEFRAME_MN1,
        }

    def _parse_array(self, array_data) -> list[dict]:
        """
        Converts MT5 numpy structured arrays to standard Python dictionaries.

        MT5 returns data as complex C-struct arrays which are not JSON serializable
        by FastAPI. This safely flattens them into standard key-value dicts.

        Args:
            array_data (numpy.ndarray): The raw data array from MT5.

        Returns:
            list[dict]: A list of parsed dictionary records.
        """
        if array_data is None or len(array_data) == 0:
            return []
        columns = array_data.dtype.names
        return [dict(zip(columns, row)) for row in array_data.tolist()]

    def _normalize_time(self, raw_timestamp: int) -> tuple[int, str]:
        """
        Converts raw MT5 broker time to a true UTC timestamp and ISO 8601 string.

        MT5 returns timestamps as naive integers representing the broker's local time.
        This attaches the broker's timezone and strictly shifts it to UTC to ensure
        frontend clients receive standardized temporal data.

        Args:
            raw_timestamp (int): Naive epoch timestamp from MT5.

        Returns:
            tuple[int, str]: Normalized UTC epoch integer and ISO format string.
        """
        naive_dt = datetime.fromtimestamp(raw_timestamp, tz=timezone.utc).replace(
            tzinfo=None
        )
        broker_aware_dt = naive_dt.replace(tzinfo=self.broker_tz)
        utc_dt = broker_aware_dt.astimezone(timezone.utc)
        return int(utc_dt.timestamp()), utc_dt.isoformat()

    def get_rates_from_pos(
        self, symbol: str, timeframe: int, start_pos: int, count: int
    ) -> list[dict]:
        """Fetches OHLCV candlestick data starting from the most recent bar."""
        mt5.symbol_select(symbol, True)
        rates = mt5.copy_rates_from_pos(symbol, timeframe, start_pos, count)
        if rates is None or len(rates) == 0:
            return []

        parsed = self._parse_array(rates)
        for ohlc in parsed:
            utc_ts, iso_str = self._normalize_time(ohlc["time"])
            ohlc["time"] = utc_ts
            ohlc["iso_time"] = iso_str
        return parsed

    def get_rates_range(
        self, symbol: str, timeframe: int, date_from: datetime, date_to: datetime
    ) -> list[dict]:
        """Fetches OHLCV candlestick data for a strict historical date range."""
        mt5.symbol_select(symbol, True)
        rates = mt5.copy_rates_range(symbol, timeframe, date_from, date_to)
        if rates is None or len(rates) == 0:
            return []

        parsed = self._parse_array(rates)
        for ohlc in parsed:
            utc_ts, iso_str = self._normalize_time(ohlc["time"])
            ohlc["time"] = utc_ts
            ohlc["iso_time"] = iso_str
        return parsed

    def get_positions_total(self) -> int:
        """Returns the total number of active open positions."""
        total = mt5.positions_total()
        return total if total is not None else 0

    def get_orders_total(self) -> int:
        """Returns the total number of resting pending orders."""
        total = mt5.orders_total()
        return total if total is not None else 0

    def get_all_symbols(self) -> list[dict]:
        """Retrieves system metadata and trading specifications for all broker symbols."""
        symbols = mt5.symbols_get()
        if not symbols:
            raise ValueError("Failed to retrieve symbols from MT5.")
        return [sym._asdict() for sym in symbols]

    def get_open_positions(self, symbol: str = None) -> list[dict]:
        """Retrieves active positions and appends real-time margin/nominal valuations."""
        positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
        if not positions:
            return []

        pos_list = []
        for pos in positions:
            p_dict = pos._asdict()
            sym_info = mt5.symbol_info(p_dict["symbol"])
            contract_size = sym_info.trade_contract_size if sym_info else 100000.0

            p_dict["nominal_value"] = (
                p_dict["volume"] * contract_size * p_dict["price_current"]
            )
            margin = mt5.order_calc_margin(
                p_dict["type"], p_dict["symbol"], p_dict["volume"], p_dict["price_open"]
            )
            p_dict["margin"] = margin if margin is not None else 0.0
            pos_list.append(p_dict)
        return pos_list

    def get_active_orders(self, symbol: str = None) -> list[dict]:
        """Retrieves all resting pending orders."""
        orders = mt5.orders_get(symbol=symbol) if symbol else mt5.orders_get()
        if not orders:
            return []
        return [o._asdict() for o in orders]

    def get_recent_ticks(self, symbol: str, count: int = 100) -> list[dict]:
        """Fetches high-resolution Level 1 Bid/Ask tick streams."""
        mt5.symbol_select(symbol, True)
        ticks = mt5.copy_ticks_from(
            symbol, datetime.now(timezone.utc), count, mt5.COPY_TICKS_ALL
        )

        if ticks is None or len(ticks) == 0:
            return []

        parsed_ticks = self._parse_array(ticks)
        for tick in parsed_ticks:
            utc_ts, iso_str = self._normalize_time(tick["time"])
            tick["time"] = utc_ts
            tick["iso_time"] = iso_str

        return parsed_ticks

    def get_order_book(self, symbol: str) -> dict:
        """
        Retrieves a snapshot of Level 2 Depth of Market (DOM).

        Raises:
            ValueError: If the broker does not supply Level 2 data for the asset.
        """
        mt5.symbol_select(symbol, True)

        if not mt5.market_book_add(symbol):
            raise ValueError(
                f"Broker does not support Level 2 (DOM) data for {symbol}."
            )

        book_items = mt5.market_book_get(symbol)
        mt5.market_book_release(symbol)

        if not book_items:
            return {"bids": [], "asks": []}

        bids, asks = [], []
        for item in book_items:
            entry = {
                "type": item.type,
                "price": item.price,
                "volume": item.volume,
                "volume_real": item.volume_real,
            }
            if item.type == mt5.BOOK_TYPE_SELL:
                asks.append(entry)
            elif item.type == mt5.BOOK_TYPE_BUY:
                bids.append(entry)

        return {"bids": bids, "asks": asks}

    def get_trade_history(self, date_from: datetime, date_to: datetime) -> list[dict]:
        """Retrieves closed deals from the broker history for a given timeframe."""
        deals = mt5.history_deals_get(date_from, date_to)
        if not deals:
            return []
        history = [
            d._asdict()
            for d in deals
            if d.entry in [mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_INOUT]
        ]
        history.sort(key=lambda x: x["time"], reverse=True)
        return history

    def _get_filling_mode(self, symbol: str) -> int:
        """
        Dynamically detects the broker's permitted execution filling mode.

        Prevents order rejection by checking if the broker requires Fill-or-Kill (FOK)
        or Immediate-or-Cancel (IOC) flags for a specific asset.
        """
        symbol_info = mt5.symbol_info(symbol)
        if not symbol_info:
            raise ValueError(f"Symbol {symbol} info unavailable.")

        allowed_modes = symbol_info.filling_mode
        if allowed_modes & 2:
            return mt5.ORDER_FILLING_IOC
        elif allowed_modes & 1:
            return mt5.ORDER_FILLING_FOK
        return mt5.ORDER_FILLING_RETURN

    def simulate_trade(
        self,
        symbol: str,
        volume: float,
        order_type_str: str,
        price_open: float,
        price_close: float,
    ) -> dict:
        """
        Calculates required margin and expected profit for a theoretical position
        before committing it to the live market.
        """
        type_map = {"BUY": mt5.ORDER_TYPE_BUY, "SELL": mt5.ORDER_TYPE_SELL}
        order_type = type_map.get(order_type_str.upper())
        if order_type is None:
            raise ValueError(
                f"Simulation requires a basic BUY or SELL type. Got: {order_type_str}"
            )

        mt5.symbol_select(symbol, True)
        margin = mt5.order_calc_margin(order_type, symbol, volume, price_open)
        profit = mt5.order_calc_profit(
            order_type, symbol, volume, price_open, price_close
        )

        return {"margin_required": margin, "expected_profit": profit}

    def execute_order(
        self,
        symbol: str,
        volume: float,
        order_type_str: str,
        target_price: float = 0.0,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
    ):
        """Constructs and fires a trade execution request to the broker."""
        mt5.symbol_select(symbol, True)
        symbol_info = mt5.symbol_info(symbol)
        if not symbol_info:
            raise ValueError(f"Symbol {symbol} not found or not visible.")

        if float(volume) < symbol_info.volume_min:
            raise ValueError(
                f"Minimum volume for {symbol} is {symbol_info.volume_min}."
            )

        normalized_volume = (
            round(float(volume) / symbol_info.volume_step) * symbol_info.volume_step
        )
        filling_mode = self._get_filling_mode(symbol)

        type_map = {
            "BUY": mt5.ORDER_TYPE_BUY,
            "SELL": mt5.ORDER_TYPE_SELL,
            "BUY_LIMIT": mt5.ORDER_TYPE_BUY_LIMIT,
            "SELL_LIMIT": mt5.ORDER_TYPE_SELL_LIMIT,
            "BUY_STOP": mt5.ORDER_TYPE_BUY_STOP,
            "SELL_STOP": mt5.ORDER_TYPE_SELL_STOP,
        }

        order_type_str = order_type_str.upper()
        if order_type_str not in type_map:
            raise ValueError(f"Unsupported order type: {order_type_str}")

        order_type = type_map[order_type_str]

        if order_type == mt5.ORDER_TYPE_BUY:
            price = mt5.symbol_info_tick(symbol).ask
        elif order_type == mt5.ORDER_TYPE_SELL:
            price = mt5.symbol_info_tick(symbol).bid
        else:
            if target_price <= 0:
                raise ValueError("Limit and Stop orders require a valid target price.")
            price = target_price

        request = {
            "action": mt5.TRADE_ACTION_PENDING
            if "LIMIT" in order_type_str or "STOP" in order_type_str
            else mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(normalized_volume),
            "type": order_type,
            "price": price,
            "sl": float(stop_loss),
            "tp": float(take_profit),
            "deviation": 20,
            "magic": 1000,
            "comment": "MDServer API",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling_mode,
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            error_comment = result.comment if result else mt5.last_error()
            raise RuntimeError(f"Order rejected: {error_comment}")

        return result._asdict()

    def close_position(self, ticket: int):
        """Flattens a specific open position by crossing the spread."""
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            raise ValueError(f"Position with ticket #{ticket} not found.")

        pos = positions[0]._asdict()
        symbol, volume, pos_type = pos["symbol"], pos["volume"], pos["type"]

        mt5.symbol_select(symbol, True)
        close_type = (
            mt5.ORDER_TYPE_SELL
            if pos_type == mt5.POSITION_TYPE_BUY
            else mt5.ORDER_TYPE_BUY
        )
        price = (
            mt5.symbol_info_tick(symbol).bid
            if close_type == mt5.ORDER_TYPE_SELL
            else mt5.symbol_info_tick(symbol).ask
        )

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": close_type,
            "position": ticket,
            "price": price,
            "deviation": 20,
            "magic": 1000,
            "comment": "MDServer Close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._get_filling_mode(symbol),
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            error_comment = result.comment if result else mt5.last_error()
            raise RuntimeError(f"Close rejected: {error_comment}")
        return result._asdict()

    def cancel_order(self, ticket: int) -> dict:
        """Removes a resting pending order from the market."""
        request = {
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": ticket,
        }
        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            error_comment = result.comment if result else mt5.last_error()
            raise RuntimeError(f"Order cancel rejected: {error_comment}")
        return result._asdict()

    def get_account_info(self) -> dict:
        info = mt5.account_info()
        if not info:
            raise ValueError("Failed to retrieve MT5 account info.")
        return info._asdict()

    def get_terminal_info(self) -> dict:
        info = mt5.terminal_info()
        if not info:
            raise ValueError("Failed to retrieve MT5 terminal info.")
        return info._asdict()


# Instantiate a global engine object for the FastAPI app to use
engine = MT5Engine()
