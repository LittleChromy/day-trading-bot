import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def make_bars(n=300, start=100.0, drift=0.0, vol=0.002, seed=0, freq='5min', start_ts='2026-03-02 14:30'):
    """Synthetic OHLCV bars during regular hours (UTC index)"""
    rng = np.random.default_rng(seed)
    rets = rng.normal(drift, vol, n)
    close = start * np.exp(np.cumsum(rets))
    open_ = np.concatenate([[start], close[:-1]])
    spread = np.abs(rng.normal(0, vol, n)) * close
    high = np.maximum(open_, close) + spread
    low = np.minimum(open_, close) - spread
    volume = rng.integers(1_000, 10_000, n).astype(float)
    # 78 five-minute bars per session; jump to the next day's open after each session
    idx, ts, day_bars = [], pd.Timestamp(start_ts, tz='UTC'), 0
    for _ in range(n):
        idx.append(ts)
        day_bars += 1
        if day_bars == 78:
            ts = ts.normalize() + pd.Timedelta(days=1, hours=14, minutes=30)
            day_bars = 0
        else:
            ts += pd.Timedelta(freq)
    return pd.DataFrame({'open': open_, 'high': high, 'low': low, 'close': close, 'volume': volume},
                        index=pd.DatetimeIndex(idx))


class FakeOrder:
    def __init__(self, id_, price):
        self.id = id_
        self.filled_avg_price = price
        self.status = 'filled'
        self.legs = []


class FakeDataHandler:
    """Stands in for AlpacaDataHandler: deterministic bars and prices, no network"""

    def __init__(self, bars_by_symbol=None, prices=None, market_open=True, configured=True):
        self.bars = bars_by_symbol or {}
        self.prices = prices or {}
        self.market_open = market_open
        self._configured = configured
        self.is_paper = True
        self.orders = []
        self.closed = []
        self.clock_time = '2026-03-02 15:00'
        self.most_actives = []
        self.movers = {'gainers': [], 'losers': []}
        self.quotes = {}
        self.untradable = set()
        self.screener_error = None

    @property
    def configured(self):
        return self._configured

    def get_bars(self, symbol, timeframe=None, limit=None):
        df = self.bars.get(symbol)
        return None if df is None else df.tail(limit or len(df))

    def get_historical_bars(self, symbol, timeframe, start, end=None):
        return self.bars.get(symbol)

    def get_latest_price(self, symbol):
        if symbol in self.prices:
            return self.prices[symbol]
        df = self.bars.get(symbol)
        return float(df['close'].iloc[-1]) if df is not None else None

    def get_clock(self):
        now = pd.Timestamp(self.clock_time, tz='America/New_York').to_pydatetime()
        close = pd.Timestamp('2026-03-02 16:00', tz='America/New_York').to_pydatetime()
        return {'is_open': self.market_open, 'timestamp': now, 'next_open': now, 'next_close': close}

    def get_account_info(self):
        return None

    def get_most_actives(self, top=50):
        if self.screener_error:
            raise RuntimeError(self.screener_error)
        return self.most_actives

    def get_movers(self, top=25):
        if self.screener_error:
            raise RuntimeError(self.screener_error)
        return self.movers

    def get_snapshot_quotes(self, symbols):
        return {s: self.quotes[s] for s in symbols if s in self.quotes}

    def is_tradable_stock(self, symbol):
        return symbol not in self.untradable

    def get_position(self, symbol):
        return object()

    def close_position(self, symbol):
        self.closed.append(symbol)

    def submit_bracket_order(self, symbol, qty, side, take_profit, stop_loss):
        order = FakeOrder(f'order-{len(self.orders) + 1}', self.get_latest_price(symbol))
        self.orders.append((symbol, qty, side, take_profit, stop_loss))
        return order

    def get_order(self, order_id):
        return None


@pytest.fixture
def fake_data():
    return FakeDataHandler()


@pytest.fixture
def app(fake_data, tmp_path):
    from app import create_app
    application = create_app('testing', data_handler=fake_data, start_scheduler=False)
    application.config['MODEL_PATH'] = str(tmp_path) + '/'
    application.config['CONFIDENCE_THRESHOLD'] = 0.5
    yield application
    from models import db
    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()
