import logging

from .technical_indicators import (
    calculate_rsi,
    calculate_macd,
    calculate_bollinger_bands,
    calculate_moving_averages,
    calculate_stochastic,
    calculate_volume_signal,
    calculate_momentum,
)
from config import Config

logger = logging.getLogger(__name__)

MIN_BARS = 60


def _r(value, digits):
    return round(value, digits) if value is not None else None


class StrategyEngine:
    """
    Combines multiple trading strategies and generates signals with a
    confidence score based on how many (weighted) strategies agree.
    """

    DEFAULT_WEIGHTS = {
        'rsi': 0.15,
        'macd': 0.20,
        'bollinger_bands': 0.15,
        'moving_average': 0.20,
        'stochastic': 0.10,
        'volume': 0.10,
        'momentum': 0.10,
    }

    def __init__(self, weights=None, min_agreeing=None):
        self.strategy_weights = dict(weights or self.DEFAULT_WEIGHTS)
        self.min_agreeing = Config.MIN_AGREEING_STRATEGIES if min_agreeing is None else min_agreeing

    def _run_strategies(self, bars):
        close = bars['close']
        high = bars['high'] if 'high' in bars.columns else None
        low = bars['low'] if 'low' in bars.columns else None
        volume = bars['volume'] if 'volume' in bars.columns else None

        def rsi():
            value, sig = calculate_rsi(close)
            return sig, {'value': _r(value, 2)}

        def macd():
            m, s, h, sig = calculate_macd(close)
            return sig, {'macd': _r(m, 4), 'signal_line': _r(s, 4), 'histogram': _r(h, 4)}

        def bollinger():
            upper, middle, lower, sig = calculate_bollinger_bands(close)
            return sig, {'upper': _r(upper, 2), 'middle': _r(middle, 2), 'lower': _r(lower, 2)}

        def moving_average():
            short, long_, sig = calculate_moving_averages(close)
            return sig, {'short_ma': _r(short, 2), 'long_ma': _r(long_, 2)}

        def stochastic():
            k, d, sig = calculate_stochastic(close, high=high, low=low)
            return sig, {'k_percent': _r(k, 2), 'd_percent': _r(d, 2)}

        def volume_strategy():
            if volume is None:
                return None, {}
            ratio, sig = calculate_volume_signal(close, volume)
            return sig, {'ratio': _r(ratio, 2)}

        def momentum():
            value, sig = calculate_momentum(close)
            return sig, {'value': _r(value, 4)}

        return {
            'rsi': rsi,
            'macd': macd,
            'bollinger_bands': bollinger,
            'moving_average': moving_average,
            'stochastic': stochastic,
            'volume': volume_strategy,
            'momentum': momentum,
        }

    def analyze(self, symbol, bars_data):
        """
        Run all strategies on the bars and combine them.
        Returns: (signal_type or None, confidence 0-1, strategy_details dict)
        strategy_details only contains strategies that voted BUY or SELL.
        """
        if bars_data is None or bars_data.empty or len(bars_data) < MIN_BARS:
            return None, 0.0, {}

        strategy_results = {}
        weights = {'BUY': 0.0, 'SELL': 0.0}
        votes = {'BUY': 0, 'SELL': 0}

        for name, fn in self._run_strategies(bars_data).items():
            weight = self.strategy_weights.get(name, 0)
            if weight <= 0:
                continue
            try:
                vote, values = fn()
            except Exception as e:
                logger.warning(f"{name} calculation failed for {symbol}: {e}")
                continue
            if vote not in ('BUY', 'SELL'):
                continue
            strategy_results[name] = {**values, 'signal': vote, 'weight': weight}
            weights[vote] += weight
            votes[vote] += 1

        voting_weight = weights['BUY'] + weights['SELL']
        total_weight = sum(w for w in self.strategy_weights.values() if w > 0)
        if voting_weight == 0 or weights['BUY'] == weights['SELL']:
            return None, 0.5 if voting_weight else 0.0, strategy_results

        side = 'BUY' if weights['BUY'] > weights['SELL'] else 'SELL'
        agreement = weights[side] / voting_weight              # how one-sided the vote is
        participation = voting_weight / total_weight           # how many strategies had an opinion
        confidence = round(agreement * (0.5 + 0.5 * participation), 4)

        if votes[side] < self.min_agreeing:
            return None, confidence, strategy_results
        return side, confidence, strategy_results
