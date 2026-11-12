"""
Stock scanner: builds the list of symbols the bot analyzes each cycle.

Candidates come from Alpaca's screener (today's most active stocks and biggest
movers) and are filtered down to liquid, reasonably priced, tradable stocks.
"Best" here means "active and liquid right now" - it is a way to find stocks
worth analyzing, not a prediction of which will go up.

If the screener is unavailable (keys, plan or network), the bot falls back to
the fixed STOCK_SYMBOLS watchlist and keeps working.
"""
import logging
import re
import threading
import time

logger = logging.getLogger(__name__)

_PLAIN_SYMBOL = re.compile(r'^[A-Z]{1,5}$')  # skips warrants, units, preferred shares (e.g. ABC.WS, XYZ+)


class StockScanner:
    def __init__(self, app):
        self.app = app
        self.cfg = app.config
        self._lock = threading.Lock()
        self._symbols = []
        self._details = []
        self._scanned_at = 0.0
        self.last_error = None

    @property
    def enabled(self):
        return bool(self.cfg.get('AUTO_SCAN', False))

    @property
    def watchlist(self):
        return list(self.cfg.get('STOCK_SYMBOLS') or [])

    # ------------------------------------------------------------------ scan
    def _candidates(self, data):
        """Candidates {symbol: {'source', 'rank', ...}}; actives and movers are interleaved by rank"""
        candidates = {}
        try:
            for rank, row in enumerate(data.get_most_actives(self.cfg.get('SCAN_CANDIDATES', 50))):
                symbol = str(row.get('symbol', '')).upper()
                candidates.setdefault(symbol, {'source': 'most active', 'rank': rank * 2, 'volume': row.get('volume')})
        except Exception as e:
            logger.warning(f"Most-actives screener failed: {e}")
        try:
            movers = data.get_movers(25)
            for kind in ('gainers', 'losers'):
                for rank, row in enumerate(movers.get(kind, [])):
                    symbol = str(row.get('symbol', '')).upper()
                    info = candidates.setdefault(symbol, {'source': kind[:-1], 'rank': rank * 2 + 1})
                    info.setdefault('change_pct', row.get('percent_change'))
        except Exception as e:
            logger.warning(f"Movers screener failed: {e}")
        return {s: i for s, i in candidates.items() if _PLAIN_SYMBOL.match(s)}

    def scan(self):
        """Run the screener now. Returns the selected symbols (may be empty)."""
        data = self.app.data_handler
        cfg = self.cfg
        candidates = self._candidates(data)
        if not candidates:
            raise RuntimeError('Screener returned no candidates')

        quotes = data.get_snapshot_quotes(list(candidates))
        min_price, max_price = cfg.get('SCAN_MIN_PRICE', 5.0), cfg.get('SCAN_MAX_PRICE', 1000.0)
        max_move = cfg.get('SCAN_MAX_MOVE_PCT', 25.0)
        limit = cfg.get('SCAN_MAX_SYMBOLS', 15)
        allow_short = cfg.get('ALLOW_SHORTING', False)

        selected = []
        for symbol, info in sorted(candidates.items(), key=lambda kv: kv[1]['rank']):
            quote = quotes.get(symbol)
            if not quote:
                continue
            price = quote['price']
            change = quote['change_pct'] if quote['change_pct'] is not None else info.get('change_pct')
            if not (min_price <= price <= max_price):
                continue
            if change is not None and abs(change) > max_move:
                continue  # too wild for a percentage stop to mean anything
            if info['source'] == 'loser' and not allow_short:
                continue  # long-only: falling knives are not candidates
            if not data.is_tradable_stock(symbol):
                continue
            selected.append({'symbol': symbol, 'price': round(price, 2), 'source': info['source'],
                             'change_pct': round(change, 2) if change is not None else None})
            if len(selected) >= limit:
                break
        return selected

    # ----------------------------------------------------------------- public
    def symbols(self, force=False):
        """
        Symbols to analyze this cycle: scanner picks (refreshed every
        SCAN_REFRESH_MINUTES) plus the fixed watchlist when SCAN_INCLUDE_WATCHLIST is on.
        """
        if not self.enabled or not self.app.data_handler.configured:
            return self.watchlist

        with self._lock:
            max_age = self.cfg.get('SCAN_REFRESH_MINUTES', 15) * 60
            if force or not self._scanned_at or time.time() - self._scanned_at > max_age:
                try:
                    self._details = self.scan()
                    self._symbols = [d['symbol'] for d in self._details]
                    self.last_error = None
                    logger.info(f"Scanner selected {len(self._symbols)} symbol(s): {', '.join(self._symbols) or '-'}")
                except Exception as e:
                    self.last_error = str(e)
                    logger.warning(f"Stock scan failed, using the fixed watchlist: {e}")
                    self._details, self._symbols = [], []
                self._scanned_at = time.time()

            combined = list(self._symbols)
            if self.cfg.get('SCAN_INCLUDE_WATCHLIST', True) or not combined:
                combined += [s for s in self.watchlist if s not in combined]
            return combined

    def status(self):
        return {
            'enabled': self.enabled,
            'scanned': list(self._details),
            'watchlist': self.watchlist,
            'include_watchlist': bool(self.cfg.get('SCAN_INCLUDE_WATCHLIST', True)),
            'last_scan': self._scanned_at or None,
            'last_error': self.last_error,
        }
