"""
Walk-forward backtester for the strategy engine.

For each bar the engine only sees data up to and including that bar. A signal
enters at the next bar's open; stops and targets are checked against each
following bar's high/low (stop first when both are touched). Open positions
are closed at the last bar of each trading day and at the end of the data.
"""
import math

import numpy as np
import pandas as pd

from risk_manager import stop_and_target, position_size, exit_hit
from strategies.strategy_engine import StrategyEngine, MIN_BARS

WINDOW = 200  # bars handed to the engine at each step (bounds run time)


def _day(ts):
    try:
        return pd.Timestamp(ts).tz_convert('America/New_York').date()
    except (TypeError, ValueError):
        return pd.Timestamp(ts).date()


def run_backtest(bars, settings, engine=None, symbol='SYMBOL'):
    """
    bars: DataFrame indexed by timestamp with open/high/low/close/volume.
    settings: mapping with the risk keys from config (STARTING_CAPITAL, STOP_LOSS_PCT, ...).
    Returns a dict of metrics, the trade list and an equity curve.
    """
    engine = engine or StrategyEngine()
    bars = bars.sort_index()
    if len(bars) < MIN_BARS + 2:
        raise ValueError(f'Need at least {MIN_BARS + 2} bars to backtest, got {len(bars)}')

    capital = float(settings.get('STARTING_CAPITAL', 100000.0))
    threshold = float(settings.get('CONFIDENCE_THRESHOLD', 0.6))
    allow_short = bool(settings.get('ALLOW_SHORTING', False))
    stop_pct = float(settings.get('STOP_LOSS_PCT', 1.5))
    target_pct = float(settings.get('TAKE_PROFIT_PCT', 3.0))
    risk_pct = float(settings.get('RISK_PER_TRADE_PCT', 1.0))
    max_pos_pct = float(settings.get('MAX_POSITION_PCT', 10.0))
    commission = float(settings.get('COMMISSION_PER_SHARE', 0.0))

    days = [_day(ts) for ts in bars.index]
    opens, highs, lows, closes = (bars[c].to_numpy(dtype=float) for c in ('open', 'high', 'low', 'close'))

    equity = capital
    position = None
    trades = []
    curve = []

    def close_position(i, price, reason):
        nonlocal equity, position
        side, qty, entry = position['side'], position['qty'], position['entry']
        pnl = ((price - entry) if side == 'BUY' else (entry - price)) * qty - commission * qty * 2
        equity += pnl
        trades.append({
            'symbol': symbol,
            'side': side,
            'entry_time': pd.Timestamp(position['time']).isoformat(),
            'exit_time': pd.Timestamp(bars.index[i]).isoformat(),
            'entry_price': round(entry, 4),
            'exit_price': round(price, 4),
            'quantity': qty,
            'profit_loss': round(pnl, 2),
            'profit_loss_percent': round(((price - entry) if side == 'BUY' else (entry - price)) / entry * 100, 3),
            'exit_reason': reason,
            'confidence': position['confidence'],
        })
        position = None

    pending = None  # signal from the previous bar, filled at this bar's open
    for i in range(len(bars)):
        # 1) fill a pending entry at this bar's open
        if pending and position is None:
            entry = opens[i]
            stop, target = stop_and_target(entry, pending['side'], stop_pct, target_pct)
            qty = position_size(equity, entry, stop, risk_pct, max_pos_pct)
            if qty > 0:
                position = {'side': pending['side'], 'qty': qty, 'entry': entry, 'stop': stop,
                            'target': target, 'time': bars.index[i], 'confidence': pending['confidence']}
        pending = None

        # 2) manage the open position on this bar
        if position is not None:
            reason, price = exit_hit(position['side'], position['stop'], position['target'], highs[i], lows[i])
            if reason:
                close_position(i, price, reason)
            elif i == len(bars) - 1:
                close_position(i, closes[i], 'END_OF_DATA')
            elif days[i + 1] != days[i]:
                close_position(i, closes[i], 'EOD')

        # mark-to-market equity
        mtm = equity
        if position is not None:
            diff = (closes[i] - position['entry']) if position['side'] == 'BUY' else (position['entry'] - closes[i])
            mtm += diff * position['qty']
        curve.append((bars.index[i], mtm))

        # 3) look for a new signal (no entries on the last bar of a day or of the data)
        last_of_day = i == len(bars) - 1 or days[i + 1] != days[i]
        if position is None and not last_of_day and i + 1 >= MIN_BARS:
            window = bars.iloc[max(0, i + 1 - WINDOW): i + 1]
            side, confidence, _ = engine.analyze(symbol, window)
            if side and confidence >= threshold and (side == 'BUY' or allow_short):
                pending = {'side': side, 'confidence': round(confidence, 4)}

    return {
        'symbol': symbol,
        'metrics': _metrics(trades, curve, capital, bars),
        'trades': trades,
        'equity_curve': _downsample([{'time': pd.Timestamp(t).isoformat(), 'equity': round(v, 2)}
                                     for t, v in curve]),
    }


def _metrics(trades, curve, capital, bars):
    values = np.array([v for _, v in curve]) if curve else np.array([capital])
    peak = np.maximum.accumulate(values)
    drawdowns = (values - peak) / peak
    final = float(values[-1])

    wins = [t['profit_loss'] for t in trades if t['profit_loss'] > 0]
    losses = [t['profit_loss'] for t in trades if t['profit_loss'] <= 0]
    gross_win, gross_loss = sum(wins), abs(sum(losses))

    # Sharpe on daily returns of the equity curve
    daily = pd.Series(values, index=pd.DatetimeIndex([t for t, _ in curve])).resample('1D').last().dropna()
    daily_ret = daily.pct_change().dropna()
    sharpe = (float(daily_ret.mean() / daily_ret.std() * math.sqrt(252))
              if len(daily_ret) > 1 and daily_ret.std() > 0 else 0.0)

    first, last = float(bars['close'].iloc[0]), float(bars['close'].iloc[-1])
    return {
        'starting_capital': round(capital, 2),
        'final_equity': round(final, 2),
        'total_return_pct': round((final - capital) / capital * 100, 3),
        'buy_and_hold_return_pct': round((last - first) / first * 100, 3) if first else 0.0,
        'total_trades': len(trades),
        'winning_trades': len(wins),
        'losing_trades': len(losses),
        'win_rate': round(len(wins) / len(trades) * 100, 2) if trades else 0.0,
        'avg_win': round(gross_win / len(wins), 2) if wins else 0.0,
        'avg_loss': round(-gross_loss / len(losses), 2) if losses else 0.0,
        'profit_factor': round(float(gross_win / gross_loss), 3) if gross_loss else None,  # None = no losing trades
        'max_drawdown_pct': round(float(drawdowns.min()) * 100, 3),
        'sharpe_ratio': round(sharpe, 3),
        'bars': len(bars),
        'start': pd.Timestamp(bars.index[0]).isoformat(),
        'end': pd.Timestamp(bars.index[-1]).isoformat(),
    }


def _downsample(points, max_points=500):
    if len(points) <= max_points:
        return points
    step = math.ceil(len(points) / max_points)
    return points[::step] + ([points[-1]] if (len(points) - 1) % step else [])
