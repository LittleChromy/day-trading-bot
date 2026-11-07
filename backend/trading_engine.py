"""
The trading bot: turns signals into trades, manages stops/targets, enforces
risk limits and flattens positions before the close.

Execution modes
  simulated : trades are recorded in the local database and filled at the
              latest market price. No orders leave this app. (default)
  alpaca    : bracket orders are sent to Alpaca. Refuses to run against a
              live (non-paper) account unless ALLOW_LIVE_TRADING=true.
"""
import logging
import threading
from datetime import datetime, time, timezone

from models import db, Trade, Signal, BotEvent
from risk_manager import stop_and_target, position_size, check_trade_allowed, exit_hit
from signal_service import generate_signals, record_trade_outcome

logger = logging.getLogger(__name__)

try:
    from zoneinfo import ZoneInfo
    NY = ZoneInfo('America/New_York')
except Exception:  # pragma: no cover
    NY = None


class TradingError(Exception):
    pass


class TradingBot:
    def __init__(self, app):
        self.app = app
        self.cfg = app.config
        self.data = app.data_handler
        self.auto_trade = bool(self.cfg.get('AUTO_TRADE', False))
        self.mode = self.cfg.get('EXECUTION_MODE', 'simulated')
        self.last_cycle = None
        self.last_error = None
        self._lock = threading.RLock()

    # ------------------------------------------------------------ helpers
    def log_event(self, event_type, message, symbol=None, level='INFO'):
        getattr(logger, level.lower(), logger.info)(f"[{event_type}] {message}")
        try:
            db.session.add(BotEvent(event_type=event_type, message=message, symbol=symbol, level=level))
            db.session.commit()
        except Exception:
            db.session.rollback()

    def validate_mode(self):
        if self.mode not in ('simulated', 'alpaca'):
            raise TradingError(f"Unknown EXECUTION_MODE '{self.mode}' (use 'simulated' or 'alpaca')")
        if self.mode == 'alpaca':
            if not self.data.configured:
                raise TradingError('EXECUTION_MODE=alpaca requires ALPACA_API_KEY and ALPACA_SECRET_KEY')
            if not self.data.is_paper and not self.cfg.get('ALLOW_LIVE_TRADING', False):
                raise TradingError('Refusing to trade a live account. Use the paper URL or set ALLOW_LIVE_TRADING=true')

    def market_clock(self):
        """dict(is_open, next_close) from Alpaca, or a regular-hours estimate when unavailable"""
        clock = self.data.get_clock() if self.data.configured else None
        if clock:
            return clock
        now = datetime.now(NY) if NY else datetime.utcnow()
        is_open = now.weekday() < 5 and time(9, 30) <= now.time() < time(16, 0)
        close = now.replace(hour=16, minute=0, second=0, microsecond=0)
        return {'is_open': is_open, 'next_close': close, 'timestamp': now, 'estimated': True}

    def latest_price(self, symbol):
        try:
            return self.data.get_latest_price(symbol)
        except Exception as e:
            logger.warning(f"No price for {symbol}: {e}")
            return None

    def open_trades(self):
        return Trade.query.filter_by(status='OPEN').all()

    def realized_pnl_since(self, since):
        trades = Trade.query.filter(Trade.status == 'CLOSED', Trade.exit_time >= since).all()
        return sum(t.profit_loss or 0 for t in trades)

    @staticmethod
    def _start_of_trading_day_utc():
        """Midnight New York time, as a naive UTC datetime (matches DB timestamps)"""
        if NY:
            midnight = datetime.now(NY).replace(hour=0, minute=0, second=0, microsecond=0)
            return midnight.astimezone(timezone.utc).replace(tzinfo=None)
        return datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    def account_snapshot(self):
        """Equity, cash/buying power and today's P&L"""
        today_realized = self.realized_pnl_since(self._start_of_trading_day_utc())
        if self.mode == 'alpaca' and self.data.configured:
            acct = self.data.get_account_info()
            if acct is not None:
                equity = float(acct.equity)
                last_equity = float(getattr(acct, 'last_equity', equity) or equity)
                return {
                    'mode': 'alpaca',
                    'paper': self.data.is_paper,
                    'equity': equity,
                    'cash': float(acct.cash),
                    'buying_power': float(acct.buying_power),
                    'daily_pnl': round(equity - last_equity, 2),
                    'realized_today': round(today_realized, 2),
                }
        realized_total = sum(t.profit_loss or 0 for t in Trade.query.filter_by(status='CLOSED').all())
        unrealized, exposure = 0.0, 0.0
        for t in self.open_trades():
            price = self.latest_price(t.symbol) or t.entry_price
            unrealized += t.unrealized_pnl(price) or 0
            exposure += t.entry_price * t.quantity
        equity = self.cfg.get('STARTING_CAPITAL', 100000.0) + realized_total + unrealized
        return {
            'mode': 'simulated',
            'paper': True,
            'equity': round(equity, 2),
            'cash': round(equity - exposure - unrealized, 2),
            'buying_power': round(max(equity - exposure, 0), 2),
            'daily_pnl': round(today_realized + unrealized, 2),
            'realized_today': round(today_realized, 2),
            'unrealized': round(unrealized, 2),
        }

    # -------------------------------------------------------------- entries
    def execute_signal(self, signal, quantity=None, source='BOT', enforce_market_hours=True):
        """
        Open a trade from a Signal. Applies the risk checks, sizes the position,
        attaches stop-loss/take-profit, and sends the order in alpaca mode.
        Returns the Trade; raises TradingError when the trade is not allowed.
        """
        with self._lock:
            self.validate_mode()
            if signal.acted_upon:
                raise TradingError('Signal has already been acted upon')

            if enforce_market_hours and not self.market_clock()['is_open']:
                raise TradingError('Market is closed')

            snapshot = self.account_snapshot()
            open_trades = self.open_trades()
            allowed, reason = check_trade_allowed(
                signal.signal_type, signal.symbol,
                {t.symbol for t in open_trades}, len(open_trades),
                snapshot['daily_pnl'], snapshot['equity'], self.cfg,
            )
            if not allowed:
                raise TradingError(reason)

            price = self.latest_price(signal.symbol) or signal.current_price
            stop, target = stop_and_target(price, signal.signal_type,
                                           self.cfg['STOP_LOSS_PCT'], self.cfg['TAKE_PROFIT_PCT'])
            qty = int(quantity) if quantity else position_size(
                snapshot['equity'], price, stop,
                self.cfg['RISK_PER_TRADE_PCT'], self.cfg['MAX_POSITION_PCT'], snapshot.get('buying_power'))
            if qty <= 0:
                raise TradingError('Position size works out to 0 shares (check equity and risk settings)')

            order_id = None
            if self.mode == 'alpaca':
                side = 'buy' if signal.signal_type == 'BUY' else 'sell'
                try:
                    order = self.data.submit_bracket_order(signal.symbol, qty, side, target, stop)
                    order_id = order.id
                    filled = getattr(order, 'filled_avg_price', None)
                    if filled:
                        price = float(filled)
                except Exception as e:
                    raise TradingError(f'Order rejected by Alpaca: {e}')

            trade = Trade(
                symbol=signal.symbol,
                trade_type=signal.signal_type,
                entry_price=round(float(price), 4),
                quantity=qty,
                entry_time=datetime.utcnow(),
                status='OPEN',
                stop_loss=stop,
                take_profit=target,
                source=source,
                execution_mode=self.mode,
                broker_order_id=order_id,
                notes=f'From signal #{signal.id} ({signal.confidence_score:.0%} confidence)',
            )
            db.session.add(trade)
            db.session.flush()
            signal.trade_id = trade.id
            signal.acted_upon = True
            db.session.commit()

            self.log_event('ENTRY', f"{source} {signal.signal_type} {qty} {signal.symbol} @ {price:.2f} "
                                    f"(stop {stop:.2f}, target {target:.2f}, {self.mode})", signal.symbol)
            return trade

    # ---------------------------------------------------------------- exits
    def close_trade(self, trade, exit_price=None, reason='MANUAL', send_order=True):
        """
        Close an open trade. In alpaca mode the position is flattened at the broker
        unless send_order=False (used when the broker already closed it).
        """
        with self._lock:
            if trade.status != 'OPEN':
                raise TradingError('Trade is not open')
            if send_order and trade.execution_mode == 'alpaca' and self.data.configured:
                try:
                    if self.data.get_position(trade.symbol) is not None:
                        self.data.close_position(trade.symbol)
                except Exception as e:
                    raise TradingError(f'Failed to close position at Alpaca: {e}')
            if exit_price is None:
                exit_price = self.latest_price(trade.symbol)
            if exit_price is None:
                raise TradingError(f'No exit price available for {trade.symbol}')

            trade.exit_price = round(float(exit_price), 4)
            trade.exit_time = datetime.utcnow()
            trade.status = 'CLOSED'
            trade.exit_reason = reason
            trade.calculate_pnl()
            record_trade_outcome(trade)
            db.session.commit()
            self.log_event('EXIT', f"Closed {trade.trade_type} {trade.quantity} {trade.symbol} @ "
                                   f"{trade.exit_price:.2f} ({trade.exit_reason}) P&L {trade.profit_loss:+.2f}",
                           trade.symbol)
            return trade

    def _broker_exit(self, trade):
        """For alpaca trades: detect a filled stop/target leg. Returns (reason, price) or (None, None)."""
        order = self.data.get_order(trade.broker_order_id) if trade.broker_order_id else None
        if order is None:
            return None, None
        if trade.entry_price and getattr(order, 'filled_avg_price', None):
            fill = float(order.filled_avg_price)
            if abs(fill - trade.entry_price) > 1e-6:
                trade.entry_price = fill
                db.session.commit()
        for leg in getattr(order, 'legs', None) or []:
            if getattr(leg, 'status', '') == 'filled':
                reason = 'TAKE_PROFIT' if getattr(leg, 'type', '') == 'limit' else 'STOP_LOSS'
                return reason, float(leg.filled_avg_price)
        if getattr(order, 'status', '') in ('canceled', 'expired', 'rejected') and not getattr(order, 'filled_qty', 0):
            return 'CANCELLED', None
        return None, None

    def monitor_positions(self):
        """Check every open trade against its stop/target and sync broker fills"""
        closed = []
        for trade in self.open_trades():
            try:
                if trade.execution_mode == 'alpaca' and self.data.configured:
                    reason, price = self._broker_exit(trade)
                    if reason == 'CANCELLED':
                        trade.status = 'CANCELLED'
                        trade.exit_reason = 'ORDER_CANCELLED'
                        db.session.commit()
                        self.log_event('CANCELLED', f"Entry order for {trade.symbol} was not filled", trade.symbol)
                        continue
                    if reason:
                        closed.append(self.close_trade(trade, price, reason=reason, send_order=False))
                    continue

                price = self.latest_price(trade.symbol)
                if price is None:
                    continue
                reason, _ = exit_hit(trade.trade_type, trade.stop_loss, trade.take_profit, price, price)
                if reason:
                    closed.append(self.close_trade(trade, price, reason=reason))
            except Exception as e:
                db.session.rollback()
                self.log_event('ERROR', f"Monitoring {trade.symbol} failed: {e}", trade.symbol, 'ERROR')
        return closed

    def flatten_all(self, reason='EOD'):
        closed = []
        for trade in self.open_trades():
            try:
                closed.append(self.close_trade(trade, reason=reason))
            except Exception as e:
                db.session.rollback()
                self.log_event('ERROR', f"Could not flatten {trade.symbol}: {e}", trade.symbol, 'ERROR')
        return closed

    def near_close(self, clock=None):
        clock = clock or self.market_clock()
        if not clock.get('is_open') or not clock.get('next_close'):
            return False
        now = clock.get('timestamp') or datetime.now(clock['next_close'].tzinfo)
        minutes_left = (clock['next_close'] - now).total_seconds() / 60
        return minutes_left <= self.cfg.get('FLATTEN_MINUTES_BEFORE_CLOSE', 10)

    # ---------------------------------------------------------------- cycle
    def run_cycle(self, generate=True):
        """
        One full bot iteration: manage open positions, flatten before the close,
        scan for signals and (if auto-trading is on) act on them.
        Must be called inside an app context.
        """
        summary = {'signals': 0, 'entries': [], 'exits': [], 'skipped': [], 'market_open': None}
        try:
            clock = self.market_clock()
            summary['market_open'] = clock['is_open']

            summary['exits'] += [t.id for t in self.monitor_positions()]

            if self.cfg.get('FLATTEN_AT_CLOSE', True) and self.near_close(clock):
                summary['exits'] += [t.id for t in self.flatten_all('EOD')]
                self.last_cycle = datetime.utcnow()
                return summary

            if not generate:
                return summary
            new_signals = generate_signals(self.app)
            summary['signals'] = len(new_signals)

            if self.auto_trade and clock['is_open']:
                for signal in sorted(new_signals, key=lambda s: s.confidence_score, reverse=True):
                    try:
                        trade = self.execute_signal(signal, source='BOT')
                        summary['entries'].append(trade.id)
                    except TradingError as e:
                        summary['skipped'].append({'signal_id': signal.id, 'symbol': signal.symbol,
                                                   'reason': str(e)})
                        logger.info(f"Skipped {signal.signal_type} {signal.symbol}: {e}")
            self.last_error = None
        except Exception as e:
            db.session.rollback()
            self.last_error = str(e)
            self.log_event('ERROR', f"Bot cycle failed: {e}", level='ERROR')
        self.last_cycle = datetime.utcnow()
        return summary

    def status(self):
        clock = self.market_clock()
        return {
            'auto_trade': self.auto_trade,
            'execution_mode': self.mode,
            'alpaca_configured': self.data.configured,
            'paper_account': self.data.is_paper,
            'market_open': clock.get('is_open'),
            'market_clock_estimated': bool(clock.get('estimated')),
            'next_close': clock['next_close'].isoformat() if clock.get('next_close') else None,
            'last_cycle': self.last_cycle.isoformat() if self.last_cycle else None,
            'last_error': self.last_error,
            'open_positions': len(self.open_trades()),
            'symbols': self.cfg['STOCK_SYMBOLS'],
            'risk': {k: self.cfg.get(k) for k in (
                'CONFIDENCE_THRESHOLD', 'RISK_PER_TRADE_PCT', 'MAX_POSITION_PCT', 'STOP_LOSS_PCT',
                'TAKE_PROFIT_PCT', 'MAX_OPEN_POSITIONS', 'MAX_DAILY_LOSS_PCT', 'ALLOW_SHORTING',
                'FLATTEN_AT_CLOSE')},
        }
