import json

from conftest import make_bars
from models import db, Signal, Trade, BotEvent


def _seed_uptrend(fake_data, symbol='AAPL'):
    bars = make_bars(n=150, drift=0.002, vol=0.0005, seed=1)
    fake_data.bars[symbol] = bars
    return bars


def test_health(client):
    res = client.get('/api/health/status')
    assert res.status_code == 200
    assert res.get_json()['database'] == 'ok'


def test_generate_signals_and_cooldown(client, fake_data):
    _seed_uptrend(fake_data)
    res = client.post('/api/signals/generate', json={'symbols': ['AAPL']})
    body = res.get_json()
    assert res.status_code == 200, body
    assert body['count'] == 1
    sig = body['signals'][0]
    assert sig['signal'] == 'BUY' and sig['id'] and isinstance(sig['strategies'], dict)
    # Same signal again inside the cooldown window is suppressed
    assert client.post('/api/signals/generate', json={'symbols': ['AAPL']}).get_json()['count'] == 0
    recent = client.get('/api/signals/recent').get_json()
    assert recent['count'] == 1 and recent['signals'][0]['strategies']


def test_generate_without_keys_returns_503(app, client, fake_data):
    fake_data._configured = False
    assert client.post('/api/signals/generate', json={}).status_code == 503


def test_execute_signal_simulated_and_close(client, fake_data):
    bars = _seed_uptrend(fake_data)
    sig_id = client.post('/api/signals/generate', json={'symbols': ['AAPL']}).get_json()['signals'][0]['id']

    res = client.post(f'/api/signals/{sig_id}/execute', json={})
    body = res.get_json()
    assert res.status_code == 201, body
    trade = body['trade']
    price = float(bars['close'].iloc[-1])
    assert trade['execution_mode'] == 'simulated' and trade['quantity'] > 0
    assert trade['stop_loss'] < price < trade['take_profit']

    # second execution of the same signal is refused
    assert client.post(f'/api/signals/{sig_id}/execute', json={}).status_code == 400

    fake_data.prices['AAPL'] = price * 1.01
    res = client.put(f"/api/trades/close/{trade['id']}", json={})
    closed = res.get_json()
    assert res.status_code == 200, closed
    assert closed['profit_loss'] > 0

    perf = client.get('/api/analytics/performance?days=7').get_json()['metrics']
    assert perf['total_trades'] == 1 and perf['winning_trades'] == 1
    acc = client.get('/api/analytics/signal-accuracy').get_json()['accuracy_metrics']
    assert acc['total_signals'] == 1 and acc['accuracy_rate'] == 100
    strategies = client.get('/api/analytics/strategies').get_json()['strategies']
    assert strategies and all(s['winning_signals'] == 1 for s in strategies)
    assert client.get('/api/analytics/equity-curve').get_json()['points']


def test_manual_trade_journal(client):
    res = client.post('/api/trades/create', json={'symbol': 'msft', 'trade_type': 'sell',
                                                  'entry_price': 400, 'quantity': 5})
    assert res.status_code == 201
    tid = res.get_json()['trade_id']
    assert client.put(f'/api/trades/close/{tid}', json={}).status_code == 400  # needs exit price
    body = client.put(f'/api/trades/close/{tid}', json={'exit_price': 390}).get_json()
    assert body['profit_loss'] == 50.0
    assert client.post('/api/trades/create', json={'symbol': 'X'}).status_code == 400
    assert client.post('/api/trades/create', json={'symbol': 'X', 'trade_type': 'HOLD',
                                                   'entry_price': 1, 'quantity': 1}).status_code == 400


def test_bot_cycle_auto_trades_and_stops_out(app, client, fake_data):
    bars = _seed_uptrend(fake_data)
    assert client.post('/api/bot/auto-trade', json={'enabled': True}).get_json()['auto_trade'] is True

    summary = client.post('/api/bot/run').get_json()['summary']
    assert summary['signals'] == 1 and len(summary['entries']) == 1

    with app.app_context():
        trade = db.session.get(Trade, summary['entries'][0])
        assert trade.source == 'BOT' and trade.status == 'OPEN'
        stop = trade.stop_loss

    # price collapses through the stop -> monitor closes it
    fake_data.prices['AAPL'] = stop - 1
    summary = client.post('/api/bot/run').get_json()['summary']
    assert summary['exits'] == [trade.id]
    with app.app_context():
        trade = db.session.get(Trade, trade.id)
        assert trade.status == 'CLOSED' and trade.exit_reason == 'STOP_LOSS' and trade.profit_loss < 0
        assert BotEvent.query.filter_by(event_type='EXIT').count() == 1

    events = client.get('/api/bot/events').get_json()['events']
    assert any(e['event_type'] == 'ENTRY' for e in events)
    status = client.get('/api/bot/status').get_json()['bot']
    assert status['auto_trade'] is True and status['open_positions'] == 0


def test_bot_does_not_trade_when_market_closed(client, fake_data):
    _seed_uptrend(fake_data)
    fake_data.market_open = False
    client.post('/api/bot/auto-trade', json={'enabled': True})
    summary = client.post('/api/bot/run').get_json()['summary']
    assert summary['market_open'] is False and summary['entries'] == []


def test_alpaca_mode_sends_bracket_order_and_flatten(app, client, fake_data):
    _seed_uptrend(fake_data)
    app.trading_bot.mode = 'alpaca'
    sig_id = client.post('/api/signals/generate', json={'symbols': ['AAPL']}).get_json()['signals'][0]['id']
    trade = client.post(f'/api/signals/{sig_id}/execute', json={'quantity': 3}).get_json()['trade']
    assert trade['broker_order_id'] == 'order-1' and trade['quantity'] == 3
    symbol, qty, side, tp, sl = fake_data.orders[0]
    assert (symbol, qty, side) == ('AAPL', 3, 'buy') and sl < tp

    closed = client.post('/api/bot/flatten').get_json()['closed']
    assert len(closed) == 1 and fake_data.closed == ['AAPL']


def test_live_account_refused(app, client, fake_data):
    app.trading_bot.mode = 'alpaca'
    fake_data.is_paper = False
    res = client.post('/api/bot/auto-trade', json={'enabled': True})
    assert res.status_code == 400 and 'live' in res.get_json()['message']


def test_backtest_endpoint(client, fake_data):
    fake_data.bars['AAPL'] = make_bars(n=78 * 4, drift=0.0003, vol=0.003, seed=3)
    res = client.post('/api/backtest/run', json={'symbol': 'AAPL', 'days': 10,
                                                 'overrides': {'STOP_LOSS_PCT': 0.5}})
    body = res.get_json()
    assert res.status_code == 200, body
    assert body['backtest']['settings']['STOP_LOSS_PCT'] == 0.5
    json.dumps(body)  # strictly serialisable
    assert client.post('/api/backtest/run', json={}).status_code == 400


def test_retrain_with_closed_trades(app, client):
    with app.app_context():
        for i in range(24):
            win = i % 2 == 0
            details = {'rsi': {'value': 25 if win else 60, 'signal': 'BUY'},
                       'macd': {'histogram': 0.1 if win else -0.1, 'signal': 'BUY'}}
            sig = Signal(symbol='AAPL', signal_type='BUY', confidence_score=0.7, current_price=100,
                         strategy_details=json.dumps(details))
            db.session.add(sig)
            db.session.flush()
            t = Trade(symbol='AAPL', trade_type='BUY', entry_price=100, exit_price=101 if win else 99,
                      quantity=10, status='CLOSED', execution_mode='simulated', signal_id=sig.id)
            t.calculate_pnl()
            db.session.add(t)
        db.session.commit()
    res = client.post('/api/bot/retrain').get_json()
    assert res['trained']['random_forest'] is True
    models = client.get('/api/bot/models').get_json()['models']
    assert models[0]['model_type'] == 'Random Forest' and models[0]['version'] == 1
