import logging
import json
from datetime import datetime
from .technical_indicators import (
    calculate_rsi,
    calculate_macd,
    calculate_bollinger_bands,
    calculate_moving_averages,
    calculate_stochastic,
    calculate_volume_signal,
    calculate_momentum
)
from config import Config

logger = logging.getLogger(__name__)

class StrategyEngine:
    """
    Combines multiple trading strategies and generates signals
    with confidence scores based on strategy agreement
    """
    
    def __init__(self):
        self.strategy_weights = {
            'rsi': 0.15,
            'macd': 0.20,
            'bollinger_bands': 0.15,
            'moving_average': 0.20,
            'stochastic': 0.10,
            'volume': 0.10,
            'momentum': 0.10
        }
    
    def analyze(self, symbol, bars_data):
        """
        Run all strategies on the given data and generate a combined signal
        Returns: (signal_type, confidence_score, strategy_details)
        """
        if bars_data is None or bars_data.empty or len(bars_data) < 50:
            return None, 0.0, {}
        
        close_prices = bars_data['close']
        volume_data = bars_data['volume'] if 'volume' in bars_data.columns else None
        
        strategy_results = {}
        buy_votes = 0
        sell_votes = 0
        total_weight = 0
        buy_weight = 0
        sell_weight = 0
        
        # RSI Strategy
        try:
            rsi, rsi_signal = calculate_rsi(close_prices)
            if rsi_signal:
                strategy_results['rsi'] = {
                    'value': round(rsi, 2),
                    'signal': rsi_signal,
                    'weight': self.strategy_weights['rsi']
                }
                if rsi_signal == 'BUY':
                    buy_votes += 1
                    buy_weight += self.strategy_weights['rsi']
                else:
                    sell_votes += 1
                    sell_weight += self.strategy_weights['rsi']
                total_weight += self.strategy_weights['rsi']
        except Exception as e:
            logger.warning(f"RSI calculation failed for {symbol}: {str(e)}")
        
        # MACD Strategy
        try:
            macd, signal, histogram, macd_signal = calculate_macd(close_prices)
            if macd_signal:
                strategy_results['macd'] = {
                    'macd': round(macd, 4),
                    'signal_line': round(signal, 4),
                    'histogram': round(histogram, 4),
                    'signal': macd_signal,
                    'weight': self.strategy_weights['macd']
                }
                if macd_signal == 'BUY':
                    buy_votes += 1
                    buy_weight += self.strategy_weights['macd']
                else:
                    sell_votes += 1
                    sell_weight += self.strategy_weights['macd']
                total_weight += self.strategy_weights['macd']
        except Exception as e:
            logger.warning(f"MACD calculation failed for {symbol}: {str(e)}")
        
        # Bollinger Bands Strategy
        try:
            upper, middle, lower, bb_signal = calculate_bollinger_bands(close_prices)
            if bb_signal:
                strategy_results['bollinger_bands'] = {
                    'upper': round(upper, 2),
                    'middle': round(middle, 2),
                    'lower': round(lower, 2),
                    'signal': bb_signal,
                    'weight': self.strategy_weights['bollinger_bands']
                }
                if bb_signal == 'BUY':
                    buy_votes += 1
                    buy_weight += self.strategy_weights['bollinger_bands']
                else:
                    sell_votes += 1
                    sell_weight += self.strategy_weights['bollinger_bands']
                total_weight += self.strategy_weights['bollinger_bands']
        except Exception as e:
            logger.warning(f"Bollinger Bands calculation failed for {symbol}: {str(e)}")
        
        # Moving Average Strategy
        try:
            ma_short, ma_long, ma_signal = calculate_moving_averages(close_prices)
            if ma_signal:
                strategy_results['moving_average'] = {
                    'short_ma': round(ma_short, 2),
                    'long_ma': round(ma_long, 2),
                    'signal': ma_signal,
                    'weight': self.strategy_weights['moving_average']
                }
                if ma_signal == 'BUY':
                    buy_votes += 1
                    buy_weight += self.strategy_weights['moving_average']
                else:
                    sell_votes += 1
                    sell_weight += self.strategy_weights['moving_average']
                total_weight += self.strategy_weights['moving_average']
        except Exception as e:
            logger.warning(f"Moving Average calculation failed for {symbol}: {str(e)}")
        
        # Stochastic Strategy
        try:
            k_percent, d_percent, stoch_signal = calculate_stochastic(close_prices)
            if stoch_signal:
                strategy_results['stochastic'] = {
                    'k_percent': round(k_percent, 2),
                    'd_percent': round(d_percent, 2),
                    'signal': stoch_signal,
                    'weight': self.strategy_weights['stochastic']
                }
                if stoch_signal == 'BUY':
                    buy_votes += 1
                    buy_weight += self.strategy_weights['stochastic']
                else:
                    sell_votes += 1
                    sell_weight += self.strategy_weights['stochastic']
                total_weight += self.strategy_weights['stochastic']
        except Exception as e:
            logger.warning(f"Stochastic calculation failed for {symbol}: {str(e)}")
        
        # Volume Strategy
        if volume_data is not None:
            try:
                volume_ratio, volume_signal = calculate_volume_signal(close_prices, volume_data)
                if volume_signal:
                    strategy_results['volume'] = {
                        'ratio': round(volume_ratio, 2),
                        'signal': volume_signal,
                        'weight': self.strategy_weights['volume']
                    }
                    if volume_signal == 'BUY':
                        buy_votes += 1
                        buy_weight += self.strategy_weights['volume']
                    else:
                        sell_votes += 1
                        sell_weight += self.strategy_weights['volume']
                    total_weight += self.strategy_weights['volume']
            except Exception as e:
                logger.warning(f"Volume calculation failed for {symbol}: {str(e)}")
        
        # Momentum Strategy
        try:
            momentum, momentum_signal = calculate_momentum(close_prices)
            if momentum_signal:
                strategy_results['momentum'] = {
                    'value': round(momentum, 4),
                    'signal': momentum_signal,
                    'weight': self.strategy_weights['momentum']
                }
                if momentum_signal == 'BUY':
                    buy_votes += 1
                    buy_weight += self.strategy_weights['momentum']
                else:
                    sell_votes += 1
                    sell_weight += self.strategy_weights['momentum']
                total_weight += self.strategy_weights['momentum']
        except Exception as e:
            logger.warning(f"Momentum calculation failed for {symbol}: {str(e)}")
        
        # Generate final signal
        final_signal = None
        confidence = 0.0
        
        if total_weight > 0:
            if buy_weight > sell_weight:
                final_signal = 'BUY'
                confidence = buy_weight / total_weight
            elif sell_weight > buy_weight:
                final_signal = 'SELL'
                confidence = sell_weight / total_weight
            else:
                confidence = 0.5  # Neutral
        
        return final_signal, confidence, strategy_results
