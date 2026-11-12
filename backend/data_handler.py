import logging
import re
from datetime import datetime, timedelta, timezone

import pandas as pd

from config import Config

logger = logging.getLogger(__name__)

_TIMEFRAME_RE = re.compile(r'^(\d+)\s*(min|minute|m|h|hour|d|day)$', re.IGNORECASE)


def parse_timeframe(timeframe):
    """
    Turn strings like '1Min', '5min', '15Min', '1H', '1D' into (amount, unit)
    where unit is 'Minute', 'Hour' or 'Day'.
    """
    match = _TIMEFRAME_RE.match(str(timeframe).strip())
    if not match:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    amount = int(match.group(1))
    unit = match.group(2).lower()
    if unit in ('min', 'minute', 'm'):
        return amount, 'Minute'
    if unit in ('h', 'hour'):
        return amount, 'Hour'
    return amount, 'Day'


def _lookback(amount, unit, limit):
    """Calendar lookback that comfortably covers `limit` bars of regular-hours data."""
    if unit == 'Minute':
        trading_days = (amount * limit) / 390.0  # 390 minutes in a regular session
    elif unit == 'Hour':
        trading_days = (amount * limit) / 6.5
    else:
        trading_days = amount * limit
    calendar_days = int(trading_days * 7 / 5) + 4  # weekends + holidays buffer
    return timedelta(days=max(calendar_days, 3))


class AlpacaDataHandler:
    """Handles market data and order routing through the Alpaca API"""

    def __init__(self, api_key=None, secret_key=None, base_url=None, feed=None):
        self.api_key = api_key or Config.ALPACA_API_KEY
        self.secret_key = secret_key or Config.ALPACA_SECRET_KEY
        self.base_url = base_url or Config.ALPACA_BASE_URL
        self.feed = feed or Config.ALPACA_DATA_FEED
        self._api = None

    # ------------------------------------------------------------------ client
    @property
    def configured(self):
        return bool(self.api_key and self.secret_key
                    and 'your_api_key' not in str(self.api_key))

    @property
    def is_paper(self):
        return 'paper' in str(self.base_url).lower()

    @property
    def api(self):
        if self._api is None:
            if not self.configured:
                raise RuntimeError("Alpaca API keys are not configured")
            import alpaca_trade_api as tradeapi
            self._api = tradeapi.REST(self.api_key, self.secret_key, self.base_url, api_version='v2')
        return self._api

    # ------------------------------------------------------------- market data
    def get_bars(self, symbol, timeframe=None, limit=None):
        """
        Get recent OHLCV bars for a symbol as a DataFrame indexed by timestamp
        with columns open, high, low, close, volume.
        """
        timeframe = timeframe or Config.BAR_TIMEFRAME
        limit = limit or Config.BAR_LIMIT
        try:
            from alpaca_trade_api.rest import TimeFrame, TimeFrameUnit
            amount, unit = parse_timeframe(timeframe)
            tf = TimeFrame(amount, getattr(TimeFrameUnit, unit))
            end = datetime.now(timezone.utc)
            start = end - _lookback(amount, unit, limit)
            bars = self.api.get_bars(
                symbol, tf,
                start=start.isoformat(),
                end=end.isoformat(),
                adjustment='raw',
                feed=self.feed,
            )
            df = bars.df
            if df is None or df.empty:
                return None
            return self.prepare_data(df).tail(limit)
        except Exception as e:
            logger.error(f"Error fetching bars for {symbol}: {e}")
            return None

    def get_latest_price(self, symbol):
        """Latest trade price (falls back to the quote midpoint)"""
        try:
            trade = self.api.get_latest_trade(symbol, feed=self.feed)
            if trade and getattr(trade, 'price', None):
                return float(trade.price)
        except Exception as e:
            logger.warning(f"Latest trade unavailable for {symbol}: {e}")
        try:
            quote = self.api.get_latest_quote(symbol, feed=self.feed)
            bid, ask = float(quote.bid_price or 0), float(quote.ask_price or 0)
            if bid and ask:
                return (bid + ask) / 2
            return ask or bid or None
        except Exception as e:
            logger.error(f"Error fetching latest price for {symbol}: {e}")
            return None

    def get_latest_trades(self, symbol):
        try:
            return self.api.get_latest_trade(symbol, feed=self.feed)
        except Exception as e:
            logger.error(f"Error fetching latest trade for {symbol}: {e}")
            return None

    def get_multiple_bars(self, symbols, timeframe=None, limit=None):
        data = {}
        for symbol in symbols:
            bars = self.get_bars(symbol, timeframe, limit)
            if bars is not None:
                data[symbol] = bars
        return data

    def get_historical_bars(self, symbol, timeframe, start, end=None):
        """Bars between two dates, used by the backtester"""
        try:
            from alpaca_trade_api.rest import TimeFrame, TimeFrameUnit
            amount, unit = parse_timeframe(timeframe)
            tf = TimeFrame(amount, getattr(TimeFrameUnit, unit))
            end = end or datetime.now(timezone.utc)
            bars = self.api.get_bars(
                symbol, tf,
                start=pd.Timestamp(start).isoformat(),
                end=pd.Timestamp(end).isoformat(),
                adjustment='raw',
                feed=self.feed,
            )
            return self.prepare_data(bars.df)
        except Exception as e:
            logger.error(f"Error fetching historical bars for {symbol}: {e}")
            return None

    @staticmethod
    def prepare_data(df):
        """Sort, de-duplicate and keep only the OHLCV columns"""
        if df is None or df.empty:
            return None
        df = df.copy()
        df.columns = [str(c).lower() for c in df.columns]
        df = df[~df.index.duplicated(keep='last')].sort_index()
        keep = [c for c in ('open', 'high', 'low', 'close', 'volume') if c in df.columns]
        return df[keep].astype(float)

    # ----------------------------------------------------------------- account
    def get_account_info(self):
        try:
            return self.api.get_account()
        except Exception as e:
            logger.error(f"Error fetching account info: {e}")
            return None

    def get_positions(self):
        try:
            return self.api.list_positions()
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return []

    def get_clock(self):
        """Returns dict(is_open, next_open, next_close) or None"""
        try:
            clock = self.api.get_clock()
            return {
                'is_open': bool(clock.is_open),
                'timestamp': pd.Timestamp(clock.timestamp).to_pydatetime(),
                'next_open': pd.Timestamp(clock.next_open).to_pydatetime(),
                'next_close': pd.Timestamp(clock.next_close).to_pydatetime(),
            }
        except Exception as e:
            logger.error(f"Error fetching market clock: {e}")
            return None

    # ------------------------------------------------------------------ orders
    def submit_bracket_order(self, symbol, qty, side, take_profit, stop_loss):
        """Market entry with attached take-profit and stop-loss legs"""
        return self.api.submit_order(
            symbol=symbol,
            qty=qty,
            side=side,
            type='market',
            time_in_force='day',
            order_class='bracket',
            take_profit={'limit_price': round(take_profit, 2)},
            stop_loss={'stop_price': round(stop_loss, 2)},
        )

    def get_order(self, order_id):
        try:
            return self.api.get_order(order_id, nested=True)
        except Exception as e:
            logger.error(f"Error fetching order {order_id}: {e}")
            return None

    def get_position(self, symbol):
        try:
            return self.api.get_position(symbol)
        except Exception:
            return None

    def close_position(self, symbol):
        """Cancel open orders for the symbol (bracket legs) and flatten the position"""
        try:
            for order in self.api.list_orders(status='open', symbols=[symbol]):
                self.api.cancel_order(order.id)
        except Exception as e:
            logger.warning(f"Could not cancel open orders for {symbol}: {e}")
        return self.api.close_position(symbol)

    # ---------------------------------------------------------------- screener
    DATA_URL = 'https://data.alpaca.markets'

    def _data_get(self, path, params=None):
        """GET a market-data endpoint that alpaca-trade-api has no wrapper for"""
        import requests
        response = requests.get(
            f'{self.DATA_URL}{path}', params=params or {}, timeout=15,
            headers={'APCA-API-KEY-ID': self.api_key, 'APCA-API-SECRET-KEY': self.secret_key},
        )
        response.raise_for_status()
        return response.json()

    def get_most_actives(self, top=50):
        """Today's most traded stocks by volume: [{'symbol', 'volume', 'trade_count'}]"""
        data = self._data_get('/v1beta1/screener/stocks/most-actives', {'by': 'volume', 'top': min(top, 100)})
        return data.get('most_actives') or []

    def get_movers(self, top=25):
        """Today's biggest gainers and losers: {'gainers': [...], 'losers': [...]} with percent_change and price"""
        data = self._data_get('/v1beta1/screener/stocks/movers', {'top': min(top, 50)})
        return {'gainers': data.get('gainers') or [], 'losers': data.get('losers') or []}

    def get_snapshot_quotes(self, symbols):
        """
        {symbol: {'price', 'change_pct'}} from snapshots (latest trade vs previous close).
        Symbols without a usable price are left out.
        """
        result = {}
        if not symbols:
            return result
        snapshots = self.api.get_snapshots(list(symbols), feed=self.feed)
        for symbol, snap in (snapshots or {}).items():
            if snap is None:
                continue
            price = getattr(getattr(snap, 'latest_trade', None), 'price', None) \
                or getattr(getattr(snap, 'daily_bar', None), 'close', None)
            prev = getattr(getattr(snap, 'prev_daily_bar', None), 'close', None)
            if not price:
                continue
            change = (float(price) - float(prev)) / float(prev) * 100 if prev else None
            result[symbol] = {'price': float(price), 'change_pct': change}
        return result

    def is_tradable_stock(self, symbol):
        """Active, tradable US equity on a major exchange (cached)"""
        cache = self.__dict__.setdefault('_asset_cache', {})
        if symbol not in cache:
            try:
                asset = self.api.get_asset(symbol)
                cache[symbol] = bool(
                    getattr(asset, 'tradable', False)
                    and getattr(asset, 'status', '') == 'active'
                    and getattr(asset, 'exchange', '') in ('NYSE', 'NASDAQ', 'ARCA', 'AMEX', 'BATS')
                )
            except Exception:
                cache[symbol] = False
        return cache[symbol]
