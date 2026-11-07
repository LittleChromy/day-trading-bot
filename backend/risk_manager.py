"""
Position sizing and pre-trade risk checks. Pure functions with no I/O so they
are shared by the live bot and the backtester.
"""
import math


def stop_and_target(entry_price, side, stop_loss_pct, take_profit_pct):
    """Stop-loss and take-profit prices for a long (BUY) or short (SELL) entry"""
    if side == 'BUY':
        stop = entry_price * (1 - stop_loss_pct / 100)
        target = entry_price * (1 + take_profit_pct / 100)
    else:
        stop = entry_price * (1 + stop_loss_pct / 100)
        target = entry_price * (1 - take_profit_pct / 100)
    return round(stop, 2), round(target, 2)


def position_size(equity, entry_price, stop_price, risk_per_trade_pct, max_position_pct, buying_power=None):
    """
    Shares to buy so that hitting the stop loses at most `risk_per_trade_pct` of
    equity, capped so the position is at most `max_position_pct` of equity and
    never more than available buying power.
    """
    if not equity or equity <= 0 or not entry_price or entry_price <= 0:
        return 0
    risk_per_share = abs(entry_price - stop_price)
    if risk_per_share <= 0:
        return 0

    by_risk = (equity * risk_per_trade_pct / 100) / risk_per_share
    by_size = (equity * max_position_pct / 100) / entry_price
    qty = min(by_risk, by_size)
    if buying_power is not None:
        qty = min(qty, max(buying_power, 0) / entry_price)
    return max(int(math.floor(qty)), 0)


def check_trade_allowed(side, symbol, open_symbols, open_count, daily_pnl, equity, settings):
    """
    Returns (allowed: bool, reason: str). `settings` is any mapping with the
    risk keys from config.Config.
    """
    if side == 'SELL' and not settings.get('ALLOW_SHORTING', False):
        return False, 'Short selling is disabled (ALLOW_SHORTING=false)'
    if symbol in open_symbols:
        return False, f'Already holding an open position in {symbol}'
    if open_count >= settings.get('MAX_OPEN_POSITIONS', 5):
        return False, 'Maximum number of open positions reached'
    max_loss = equity * settings.get('MAX_DAILY_LOSS_PCT', 3.0) / 100
    if daily_pnl <= -max_loss:
        return False, f'Daily loss limit hit ({daily_pnl:.2f} <= -{max_loss:.2f}); trading halted for today'
    return True, 'ok'


def exit_hit(side, stop_price, target_price, bar_high, bar_low):
    """
    Checks a bar against stop/target. Returns ('STOP_LOSS'|'TAKE_PROFIT', price) or (None, None).
    If both are touched in the same bar the stop is assumed to fill first (conservative).
    """
    if side == 'BUY':
        if stop_price is not None and bar_low <= stop_price:
            return 'STOP_LOSS', stop_price
        if target_price is not None and bar_high >= target_price:
            return 'TAKE_PROFIT', target_price
    else:
        if stop_price is not None and bar_high >= stop_price:
            return 'STOP_LOSS', stop_price
        if target_price is not None and bar_low <= target_price:
            return 'TAKE_PROFIT', target_price
    return None, None
