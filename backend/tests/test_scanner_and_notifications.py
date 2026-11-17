from conftest import make_bars
from notifier import DiscordNotifier


class FakeResponse:
    def __init__(self, status_code=204):
        self.status_code = status_code


class Outbox:
    """Captures what would be posted to Discord"""

    def __init__(self, status_code=204):
        self.messages = []
        self.urls = []
        self.status_code = status_code

    def __call__(self, url, json=None, timeout=None):
        self.urls.append(url)
        self.messages.append(json['content'])
        return FakeResponse(self.status_code)


def _wire_notifier(app):
    outbox = Outbox()
    app.notifier = DiscordNotifier('https://discord.test/api/webhooks/1/abc', post=outbox)
    return outbox


def _uptrend(fake_data, symbol='AAPL'):
    fake_data.bars[symbol] = make_bars(n=150, drift=0.002, vol=0.0005, seed=1)


# ------------------------------------------------------------- notifications
def test_notifications_for_signal_entry_and_exit(app, client, fake_data):
    outbox = _wire_notifier(app)
    _uptrend(fake_data)
    client.post('/api/bot/auto-trade', json={'enabled': True})
    summary = client.post('/api/bot/run').get_json()['summary']
    assert len(summary['entries']) == 1

    fake_data.prices['AAPL'] = 1.0  # crash through the stop
    client.post('/api/bot/run')
    app.notifier.flush()

    text = '\n'.join(outbox.messages)
    assert 'Auto-trading **enabled**' in text
    assert 'BUY signal: AAPL' in text
    assert 'Opened LONG' in text and 'Stop $' in text
    assert 'Closed' in text and 'stop loss' in text and 'P&L **-$' in text
    assert all(u == 'https://discord.test/api/webhooks/1/abc' for u in outbox.urls)


def test_disabled_notifier_sends_nothing(app, client, fake_data):
    assert app.notifier.enabled is False
    _uptrend(fake_data)
    client.post('/api/bot/auto-trade', json={'enabled': True})
    assert client.post('/api/bot/run').status_code == 200
    res = client.post('/api/bot/notify-test')
    assert res.status_code == 400 and 'No Discord webhook' in res.get_json()['message']
    assert client.get('/api/bot/status').get_json()['bot']['notifications'] is False


def test_notify_test_endpoint_reports_discord_failure(app, client):
    outbox = _wire_notifier(app)
    assert client.post('/api/bot/notify-test').status_code == 200
    assert 'Test notification' in outbox.messages[0]
    outbox.status_code = 404
    res = client.post('/api/bot/notify-test')
    assert res.status_code == 400 and '404' in res.get_json()['message']


def test_discord_outage_never_breaks_trading(app, client, fake_data):
    def broken(url, json=None, timeout=None):
        raise ConnectionError('discord down')
    app.notifier = DiscordNotifier('https://discord.test/hook', post=broken)
    _uptrend(fake_data)
    client.post('/api/bot/auto-trade', json={'enabled': True})
    summary = client.post('/api/bot/run').get_json()['summary']
    app.notifier.flush()
    assert len(summary['entries']) == 1
    assert 'discord.test' not in (app.notifier.last_error or '')  # webhook URL is never echoed


def test_daily_summary_sent_once_at_the_close(app, client, fake_data):
    outbox = _wire_notifier(app)
    _uptrend(fake_data)
    client.post('/api/bot/auto-trade', json={'enabled': True})
    client.post('/api/bot/run')                     # opens a position at 15:00

    fake_data.clock_time = '2026-03-02 15:55'       # inside the flatten window
    fake_data.prices['AAPL'] = fake_data.get_latest_price('AAPL') * 1.01
    summary = client.post('/api/bot/run').get_json()['summary']
    assert len(summary['exits']) == 1
    client.post('/api/bot/run')
    app.notifier.flush()

    summaries = [m for m in outbox.messages if 'Daily summary' in m]
    assert len(summaries) == 1
    assert '1 trade(s) closed' in summaries[0] and '1 win(s)' in summaries[0]


def test_alert_when_no_market_data_is_throttled(app, client, fake_data):
    outbox = _wire_notifier(app)
    app.config['STOCK_SYMBOLS'] = ['AAPL', 'MSFT']  # no bars for either
    client.post('/api/bot/run')
    client.post('/api/bot/run')
    app.notifier.flush()
    assert sum('No market data' in m for m in outbox.messages) == 1
    body = client.post('/api/signals/generate', json={}).get_json()
    assert body['no_data'] == ['AAPL', 'MSFT'] and body['scanned'] == 2


# ------------------------------------------------------------------- scanner
def _screener(fake_data):
    fake_data.most_actives = [{'symbol': s, 'volume': 1} for s in ['NVDA', 'PENNY', 'TSLA', 'ABC.WS', 'DELIST', 'AMD']]
    fake_data.movers = {'gainers': [{'symbol': 'ROCKET', 'percent_change': 80.0}, {'symbol': 'GOOD', 'percent_change': 6.0}],
                        'losers': [{'symbol': 'DROP', 'percent_change': -9.0}]}
    fake_data.quotes = {
        'NVDA': {'price': 140.0, 'change_pct': 2.0}, 'PENNY': {'price': 0.8, 'change_pct': 5.0},
        'TSLA': {'price': 300.0, 'change_pct': -1.0}, 'DELIST': {'price': 20.0, 'change_pct': 0.0},
        'AMD': {'price': 150.0, 'change_pct': 1.0}, 'ROCKET': {'price': 12.0, 'change_pct': 80.0},
        'GOOD': {'price': 45.0, 'change_pct': 6.0}, 'DROP': {'price': 30.0, 'change_pct': -9.0},
    }
    fake_data.untradable = {'DELIST'}


def test_scanner_filters_and_merges_watchlist(app, fake_data):
    _screener(fake_data)
    app.config.update(AUTO_SCAN=True, STOCK_SYMBOLS=['AAPL', 'NVDA'], SCAN_MAX_SYMBOLS=10)
    symbols = app.scanner.symbols()
    # penny stock, warrant, untradable, +80% rocket and (long-only) loser are all excluded
    assert symbols == ['NVDA', 'GOOD', 'TSLA', 'AMD', 'AAPL']
    status = app.scanner.status()
    assert status['enabled'] and status['last_error'] is None
    assert {d['symbol']: d['source'] for d in status['scanned']}['GOOD'] == 'gainer'

    app.config['SCAN_INCLUDE_WATCHLIST'] = False
    assert app.scanner.symbols() == ['NVDA', 'GOOD', 'TSLA', 'AMD']


def test_scanner_respects_limit_and_shorting(app, fake_data):
    _screener(fake_data)
    app.config.update(AUTO_SCAN=True, STOCK_SYMBOLS=[], SCAN_MAX_SYMBOLS=2)
    assert app.scanner.symbols() == ['NVDA', 'GOOD']
    app.config.update(SCAN_MAX_SYMBOLS=10, ALLOW_SHORTING=True)
    assert 'DROP' in app.scanner.symbols(force=True)


def test_scanner_falls_back_to_watchlist(app, client, fake_data):
    fake_data.screener_error = '403 Forbidden'
    app.config.update(AUTO_SCAN=True, STOCK_SYMBOLS=['AAPL', 'MSFT'])
    assert app.scanner.symbols() == ['AAPL', 'MSFT']
    assert app.scanner.status()['last_error']
    body = client.get('/api/bot/universe').get_json()
    assert body['symbols'] == ['AAPL', 'MSFT'] and body['scanner']['scanned'] == []


def test_scanner_results_are_cached_and_drive_signal_generation(app, client, fake_data):
    _screener(fake_data)
    fake_data.bars['GOOD'] = make_bars(n=150, drift=0.002, vol=0.0005, seed=1)
    app.config.update(AUTO_SCAN=True, STOCK_SYMBOLS=[])
    body = client.post('/api/signals/generate', json={}).get_json()
    assert [s['symbol'] for s in body['signals']] == ['GOOD']

    fake_data.most_actives = [{'symbol': 'AMD', 'volume': 1}]
    assert 'NVDA' in app.scanner.symbols()                   # cached
    assert client.post('/api/bot/universe').get_json()['symbols'][0] == 'AMD'  # forced refresh
