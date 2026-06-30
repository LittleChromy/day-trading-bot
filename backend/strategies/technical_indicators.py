import pandas as pd
import numpy as np
from config import Config

def calculate_rsi(data, period=None):
    """
    Calculate Relative Strength Index (RSI)
    RSI > 70: Overbought (potential SELL)
    RSI < 30: Oversold (potential BUY)
    """
    if period is None:
        period = Config.RSI_PERIOD
    
    if len(data) < period:
        return None, None
    
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    current_rsi = rsi.iloc[-1]
    signal = None
    
    if current_rsi > Config.RSI_OVERBOUGHT:
        signal = 'SELL'
    elif current_rsi < Config.RSI_OVERSOLD:
        signal = 'BUY'
    
    return current_rsi, signal

def calculate_macd(data, fast=None, slow=None, signal_period=None):
    """
    Calculate MACD (Moving Average Convergence Divergence)
    MACD > Signal Line & increasing: BUY
    MACD < Signal Line & decreasing: SELL
    """
    if fast is None:
        fast = Config.MACD_FAST
    if slow is None:
        slow = Config.MACD_SLOW
    if signal_period is None:
        signal_period = Config.MACD_SIGNAL
    
    if len(data) < slow:
        return None, None, None, None
    
    ema_fast = data.ewm(span=fast).mean()
    ema_slow = data.ewm(span=slow).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_period).mean()
    histogram = macd_line - signal_line
    
    current_macd = macd_line.iloc[-1]
    current_signal = signal_line.iloc[-1]
    current_histogram = histogram.iloc[-1]
    
    signal = None
    if current_macd > current_signal and current_histogram > 0:
        signal = 'BUY'
    elif current_macd < current_signal and current_histogram < 0:
        signal = 'SELL'
    
    return current_macd, current_signal, current_histogram, signal

def calculate_bollinger_bands(data, period=None, std_dev=None):
    """
    Calculate Bollinger Bands
    Price touches lower band: BUY
    Price touches upper band: SELL
    """
    if period is None:
        period = Config.BB_PERIOD
    if std_dev is None:
        std_dev = Config.BB_STD_DEV
    
    if len(data) < period:
        return None, None, None, None
    
    sma = data.rolling(window=period).mean()
    std = data.rolling(window=period).std()
    
    upper_band = sma + (std * std_dev)
    lower_band = sma - (std * std_dev)
    
    current_price = data.iloc[-1]
    current_middle = sma.iloc[-1]
    current_upper = upper_band.iloc[-1]
    current_lower = lower_band.iloc[-1]
    
    signal = None
    if current_price <= current_lower:
        signal = 'BUY'
    elif current_price >= current_upper:
        signal = 'SELL'
    
    return current_upper, current_middle, current_lower, signal

def calculate_moving_averages(data, short_period=None, long_period=None):
    """
    Calculate Moving Average Crossover
    Short MA > Long MA: BUY
    Short MA < Long MA: SELL
    """
    if short_period is None:
        short_period = Config.MA_SHORT
    if long_period is None:
        long_period = Config.MA_LONG
    
    if len(data) < long_period:
        return None, None, None
    
    ma_short = data.rolling(window=short_period).mean()
    ma_long = data.rolling(window=long_period).mean()
    
    current_short = ma_short.iloc[-1]
    current_long = ma_long.iloc[-1]
    
    signal = None
    if current_short > current_long:
        signal = 'BUY'
    elif current_short < current_long:
        signal = 'SELL'
    
    return current_short, current_long, signal

def calculate_stochastic(data, period=14, k_period=3, d_period=3):
    """
    Calculate Stochastic Oscillator
    %K > 80: Overbought (potential SELL)
    %K < 20: Oversold (potential BUY)
    """
    if len(data) < period:
        return None, None, None
    
    low_min = data.rolling(window=period).min()
    high_max = data.rolling(window=period).max()
    
    k_percent = 100 * (data - low_min) / (high_max - low_min)
    d_percent = k_percent.rolling(window=d_period).mean()
    
    current_k = k_percent.iloc[-1]
    current_d = d_percent.iloc[-1]
    
    signal = None
    if current_k < 20:
        signal = 'BUY'
    elif current_k > 80:
        signal = 'SELL'
    
    return current_k, current_d, signal

def calculate_volume_signal(price_data, volume_data, period=20):
    """
    Volume-based trading signal
    High volume on price increase: BUY
    High volume on price decrease: SELL
    """
    if len(price_data) < period or len(volume_data) < period:
        return None, None
    
    price_change = price_data.diff()
    avg_volume = volume_data.rolling(window=period).mean()
    current_volume = volume_data.iloc[-1]
    current_price_change = price_change.iloc[-1]
    
    signal = None
    volume_ratio = current_volume / avg_volume.iloc[-1] if avg_volume.iloc[-1] > 0 else 1
    
    if volume_ratio > 1.5:
        if current_price_change > 0:
            signal = 'BUY'
        elif current_price_change < 0:
            signal = 'SELL'
    
    return volume_ratio, signal

def calculate_momentum(data, period=10):
    """
    Calculate Momentum indicator
    Positive momentum: BUY
    Negative momentum: SELL
    """
    if len(data) < period:
        return None, None
    
    momentum = data.diff(period)
    current_momentum = momentum.iloc[-1]
    
    signal = None
    if current_momentum > 0:
        signal = 'BUY'
    elif current_momentum < 0:
        signal = 'SELL'
    
    return current_momentum, signal
