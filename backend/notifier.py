"""
Discord notifications.

Set DISCORD_WEBHOOK_URL to a channel webhook and the bot posts a message for
new signals, trade entries/exits, problems and an end-of-day summary.
Messages are sent from a background thread so a slow or failing Discord never
blocks trading. The webhook URL is a secret: it is never logged.
"""
import logging
import queue
import threading
import time

import requests

logger = logging.getLogger(__name__)

_ICONS = {
    'SIGNAL_BUY': '🟢', 'SIGNAL_SELL': '🔴', 'ENTRY': '📥', 'EXIT_WIN': '✅', 'EXIT_LOSS': '❌',
    'CANCELLED': '⚪', 'ERROR': '⚠️', 'HALT': '🛑', 'SUMMARY': '📊', 'CONFIG': '⚙️', 'TEST': '🔔',
}


def _money(value):
    return f"{'-' if value < 0 else '+'}${abs(value):,.2f}"


class DiscordNotifier:
    def __init__(self, webhook_url=None, notify_signals=True, notify_trades=True, post=None):
        self.webhook_url = (webhook_url or '').strip()
        self.notify_signals = notify_signals
        self.notify_trades = notify_trades
        self._post = post or requests.post      # injectable for tests
        self._queue = queue.Queue(maxsize=200)
        self._worker = None
        self.last_error = None

    @property
    def enabled(self):
        return self.webhook_url.startswith('https://')

    # ------------------------------------------------------------ transport
    def _deliver(self, content):
        """Send one message now. Returns True on success."""
        try:
            response = self._post(self.webhook_url, json={'username': 'Day Trading Bot', 'content': content[:1900]},
                                  timeout=10)
            status = getattr(response, 'status_code', 204)
            if status == 429:  # rate limited: wait once and retry
                try:
                    wait = float(response.json().get('retry_after', 1))
                except Exception:
                    wait = 1.0
                time.sleep(min(wait, 10))
                response = self._post(self.webhook_url, json={'username': 'Day Trading Bot', 'content': content[:1900]},
                                      timeout=10)
                status = getattr(response, 'status_code', 204)
            if status >= 300:
                self.last_error = f'Discord returned HTTP {status}'
                logger.warning(self.last_error)
                return False
            self.last_error = None
            return True
        except Exception as e:
            self.last_error = f'Could not reach Discord: {type(e).__name__}'
            logger.warning(self.last_error)
            return False

    def _run(self):
        while True:
            content = self._queue.get()
            self._deliver(content)
            time.sleep(0.5)  # stay well under Discord's webhook rate limit
            self._queue.task_done()

    def send(self, content):
        """Queue a message. Never raises and never blocks."""
        if not self.enabled:
            return False
        if self._worker is None or not self._worker.is_alive():
            self._worker = threading.Thread(target=self._run, daemon=True, name='discord-notifier')
            self._worker.start()
        try:
            self._queue.put_nowait(content)
            return True
        except queue.Full:
            logger.warning('Notification queue is full; dropping message')
            return False

    def send_now(self, content):
        """Send synchronously and report the result (used by the test button)."""
        if not self.enabled:
            self.last_error = 'DISCORD_WEBHOOK_URL is not set'
            return False
        return self._deliver(content)

    def flush(self, timeout=5):
        """Wait for queued messages (tests)."""
        deadline = time.time() + timeout
        while self._queue.unfinished_tasks and time.time() < deadline:
            time.sleep(0.02)

    # ------------------------------------------------------------- messages
    def signal(self, signal):
        if not self.notify_signals:
            return
        icon = _ICONS['SIGNAL_BUY' if signal.signal_type == 'BUY' else 'SIGNAL_SELL']
        votes = [name.replace('_', ' ') for name, info in signal.get_strategy_details().items()
                 if isinstance(info, dict) and info.get('signal') == signal.signal_type]
        self.send(f"{icon} **{signal.signal_type} signal: {signal.symbol}** at ${signal.current_price:,.2f}\n"
                  f"Confidence {signal.confidence_score:.0%}" + (f" · agreeing: {', '.join(votes)}" if votes else ''))

    def entry(self, trade):
        if not self.notify_trades:
            return
        side = 'LONG' if trade.trade_type == 'BUY' else 'SHORT'
        self.send(f"{_ICONS['ENTRY']} **Opened {side} {trade.quantity} {trade.symbol}** at ${trade.entry_price:,.2f} "
                  f"({trade.source}, {trade.execution_mode})\n"
                  f"Stop ${trade.stop_loss:,.2f} · Target ${trade.take_profit:,.2f} · "
                  f"Size ${trade.entry_price * trade.quantity:,.0f}")

    def exit(self, trade):
        if not self.notify_trades:
            return
        pnl = trade.profit_loss or 0
        icon = _ICONS['EXIT_WIN' if pnl > 0 else 'EXIT_LOSS']
        reason = (trade.exit_reason or 'closed').replace('_', ' ').lower()
        self.send(f"{icon} **Closed {trade.quantity} {trade.symbol}** at ${trade.exit_price:,.2f} ({reason})\n"
                  f"P&L **{_money(pnl)}** ({trade.profit_loss_percent or 0:+.2f}%)")

    def problem(self, message, halt=False):
        self.send(f"{_ICONS['HALT' if halt else 'ERROR']} **{'Trading halted' if halt else 'Problem'}**: {message}")

    def info(self, message):
        self.send(f"{_ICONS['CONFIG']} {message}")

    def daily_summary(self, closed_trades, account, open_positions):
        pnl = sum(t.profit_loss or 0 for t in closed_trades)
        wins = sum(1 for t in closed_trades if (t.profit_loss or 0) > 0)
        lines = [f"{_ICONS['SUMMARY']} **Daily summary**"]
        if closed_trades:
            lines.append(f"{len(closed_trades)} trade(s) closed · {wins} win(s) / {len(closed_trades) - wins} loss(es) "
                         f"· P&L **{_money(pnl)}**")
            best = max(closed_trades, key=lambda t: t.profit_loss or 0)
            worst = min(closed_trades, key=lambda t: t.profit_loss or 0)
            if len(closed_trades) > 1:
                lines.append(f"Best {best.symbol} {_money(best.profit_loss or 0)} · "
                             f"Worst {worst.symbol} {_money(worst.profit_loss or 0)}")
        else:
            lines.append('No trades closed today.')
        lines.append(f"Equity ${account.get('equity', 0):,.2f} · open positions: {open_positions} "
                     f"· mode: {account.get('mode')}")
        self.send('\n'.join(lines))
