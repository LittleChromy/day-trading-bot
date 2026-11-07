import numpy as np
import pandas as pd

from strategies import (calculate_rsi, calculate_macd, calculate_bollinger_bands,
                        calculate_moving_averages, calculate_stochastic,
                        calculate_volume_signal, calculate_momentum, StrategyEngine)
from conftest import make_bars


def test_rsi_extremes():
    up = pd.Series(np.linspace(100, 150, 60))
    down = pd.Series(np.linspace(150, 100, 60))
    assert calculate_rsi(up) == (100.0, 'SELL')
    value, sig = calculate_rsi(down)
    assert value < 1 and sig == 'BUY'


def test_rsi_flat_series_is_neutral():
    value, sig = calculate_rsi(pd.Series([100.0] * 40))
    assert value == 50.0 and sig is None


def test_insufficient_data_returns_none():
    short = pd.Series([1.0, 2.0, 3.0])
    assert calculate_rsi(short) == (None, None)
    assert calculate_macd(short) == (None, None, None, None)
    assert calculate_moving_averages(short) == (None, None, None)
    assert calculate_stochastic(short) == (None, None, None)


def test_trend_indicators_follow_direction():
    up = pd.Series(np.linspace(100, 130, 120))
    assert calculate_macd(up)[3] == 'BUY'
    assert calculate_moving_averages(up)[2] == 'BUY'
    assert calculate_momentum(up)[1] == 'BUY'
    down = up[::-1].reset_index(drop=True)
    assert calculate_moving_averages(down)[2] == 'SELL'
    assert calculate_momentum(down)[1] == 'SELL'


def test_bollinger_breakout():
    data = pd.Series([100.0] * 30 + [100.5, 99.5] * 5 + [110.0])
    assert calculate_bollinger_bands(data)[3] == 'SELL'


def test_stochastic_uses_high_low():
    close = pd.Series([100.0] * 30)
    high = pd.Series([110.0] * 30)
    low = pd.Series([95.0] * 30)
    k, _, sig = calculate_stochastic(close, high=high, low=low)
    assert round(k, 2) == 33.33 and sig is None


def test_volume_spike():
    price = pd.Series([100.0] * 25 + [101.0])
    volume = pd.Series([1000.0] * 25 + [5000.0])
    ratio, sig = calculate_volume_signal(price, volume)
    assert ratio > 1.5 and sig == 'BUY'


def test_engine_strong_uptrend_signals_buy():
    bars = make_bars(n=150, drift=0.002, vol=0.0005, seed=1)
    side, confidence, details = StrategyEngine(min_agreeing=3).analyze('TEST', bars)
    assert side == 'BUY'
    assert 0 < confidence <= 1
    assert 'moving_average' in details and details['moving_average']['signal'] == 'BUY'


def test_engine_requires_enough_bars_and_agreement():
    assert StrategyEngine().analyze('X', make_bars(n=30)) == (None, 0.0, {})
    bars = make_bars(n=150, drift=0.002, vol=0.0005, seed=1)
    side, _, _ = StrategyEngine(min_agreeing=8).analyze('X', bars)
    assert side is None
