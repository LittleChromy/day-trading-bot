"""
Technical indicators. Each function takes pandas Series and returns the latest
indicator value(s) plus a 'BUY' / 'SELL' / None vote. Values are plain floats
(or None when there is not enough data) so they serialise cleanly to JSON.
"""
import math

import numpy as np
import pandas as pd

from config import Config


def _f(value):
    """Convert to float, mapping NaN/inf/None to None"""
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def calculate_rsi(data, period=None):
    """
    Relative Strength Index (Wilder's smoothing)
    RSI > overbought: SELL, RSI < oversold: BUY
    """
    period = period or Config.RSI_PERIOD
    if len(data) <= period:
        return None, None

    delta = data.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    last_gain, last_loss = avg_gain.iloc[-1], avg_loss.iloc[-1]
    if pd.isna(last_gain) or pd.isna(last_loss):
        return None, None
    if last_loss == 0:
        current_rsi = 100.0 if last_gain > 0 else 50.0
    else:
        current_rsi = 100 - (100 / (1 + last_gain / last_loss))

    signal = None
    if current_rsi > Config.RSI_OVERBOUGHT:
        signal = 'SELL'
    elif current_rsi < Config.RSI_OVERSOLD:
        signal = 'BUY'
    return _f(current_rsi), signal


def calculate_macd(data, fast=None, slow=None, signal_period=None):
    """
    MACD: MACD above signal line with positive histogram: BUY, below: SELL
    """
    fast = fast or Config.MACD_FAST
    slow = slow or Config.MACD_SLOW
    signal_period = signal_period or Config.MACD_SIGNAL
    if len(data) < slow + signal_period:
        return None, None, None, None

    ema_fast = data.ewm(span=fast, adjust=False).mean()
    ema_slow = data.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    histogram = macd_line - signal_line

    current_macd = _f(macd_line.iloc[-1])
    current_signal = _f(signal_line.iloc[-1])
    current_histogram = _f(histogram.iloc[-1])
    if None in (current_macd, current_signal, current_histogram):
        return None, None, None, None

    signal = None
    if current_histogram > 0:
        signal = 'BUY'
    elif current_histogram < 0:
        signal = 'SELL'
    return current_macd, current_signal, current_histogram, signal


def calculate_bollinger_bands(data, period=None, std_dev=None):
    """
    Bollinger Bands: price at/below lower band: BUY, at/above upper band: SELL
    """
    period = period or Config.BB_PERIOD
    std_dev = std_dev or Config.BB_STD_DEV
    if len(data) < period:
        return None, None, None, None

    sma = data.rolling(window=period).mean()
    std = data.rolling(window=period).std()
    upper_band = sma + std * std_dev
    lower_band = sma - std * std_dev

    current_price = _f(data.iloc[-1])
    current_middle = _f(sma.iloc[-1])
    current_upper = _f(upper_band.iloc[-1])
    current_lower = _f(lower_band.iloc[-1])
    if None in (current_price, current_middle, current_upper, current_lower):
        return None, None, None, None

    signal = None
    if current_price <= current_lower:
        signal = 'BUY'
    elif current_price >= current_upper:
        signal = 'SELL'
    return current_upper, current_middle, current_lower, signal


def calculate_moving_averages(data, short_period=None, long_period=None):
    """
    Moving average trend: short MA above long MA: BUY, below: SELL
    """
    short_period = short_period or Config.MA_SHORT
    long_period = long_period or Config.MA_LONG
    if len(data) < long_period:
        return None, None, None

    current_short = _f(data.rolling(window=short_period).mean().iloc[-1])
    current_long = _f(data.rolling(window=long_period).mean().iloc[-1])
    if current_short is None or current_long is None:
        return None, None, None

    signal = None
    if current_short > current_long:
        signal = 'BUY'
    elif current_short < current_long:
        signal = 'SELL'
    return current_short, current_long, signal


def calculate_stochastic(data, period=14, d_period=3, high=None, low=None):
    """
    Stochastic oscillator: %K < 20: BUY, %K > 80: SELL.
    Uses bar highs/lows when given, otherwise closes.
    """
    if len(data) < period + d_period:
        return None, None, None

    high = data if high is None else high
    low = data if low is None else low
    low_min = low.rolling(window=period).min()
    high_max = high.rolling(window=period).max()
    price_range = (high_max - low_min).replace(0, np.nan)

    k_percent = 100 * (data - low_min) / price_range
    d_percent = k_percent.rolling(window=d_period).mean()

    current_k = _f(k_percent.iloc[-1])
    current_d = _f(d_percent.iloc[-1])
    if current_k is None:
        return None, None, None

    signal = None
    if current_k < 20:
        signal = 'BUY'
    elif current_k > 80:
        signal = 'SELL'
    return current_k, current_d, signal


def calculate_volume_signal(price_data, volume_data, period=20, threshold=1.5):
    """
    Volume confirmation: unusually high volume on an up bar: BUY, on a down bar: SELL
    """
    if len(price_data) <= period or len(volume_data) <= period:
        return None, None

    avg_volume = _f(volume_data.rolling(window=period).mean().iloc[-1])
    current_volume = _f(volume_data.iloc[-1])
    current_price_change = _f(price_data.diff().iloc[-1])
    if not avg_volume or current_volume is None or current_price_change is None:
        return None, None

    volume_ratio = current_volume / avg_volume
    signal = None
    if volume_ratio > threshold:
        if current_price_change > 0:
            signal = 'BUY'
        elif current_price_change < 0:
            signal = 'SELL'
    return volume_ratio, signal


def calculate_momentum(data, period=10):
    """
    Rate of change over `period` bars (percent): positive: BUY, negative: SELL
    """
    if len(data) <= period:
        return None, None

    past = _f(data.iloc[-period - 1])
    current = _f(data.iloc[-1])
    if not past or current is None:
        return None, None
    momentum = (current - past) / past * 100

    signal = None
    if momentum > 0:
        signal = 'BUY'
    elif momentum < 0:
        signal = 'SELL'
    return momentum, signal

