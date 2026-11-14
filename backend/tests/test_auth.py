from conftest import make_bars

REMOTE = {'Host': 'quiet-river-1234.trycloudflare.com'}
MUTATIONS = [
    ('post', '/api/bot/auto-trade', {'enabled': True}),
    ('post', '/api/bot/run', None),
    ('post', '/api/bot/flatten', None),
    ('post', '/api/bot/retrain', None),
    ('post', '/api/bot/universe', None),
    ('post', '/api/bot/notify-test', None),
    ('post', '/api/signals/generate', {}),
    ('post', '/api/signals/1/execute', {}),
    ('post', '/api/trades/create', {'symbol': 'AAPL', 'trade_type': 'BUY', 'entry_price': 1, 'quantity': 1}),
    ('put', '/api/trades/close/1', {'exit_price': 1}),
    ('put', '/api/trades/cancel/1', None),
]
READS = ['/api/health/status', '/api/bot/status', '/api/bot/account', '/api/bot/events', '/api/bot/models',
         '/api/bot/universe', '/api/signals/recent', '/api/trades/all', '/api/analytics/performance',
         '/api/analytics/strategies', '/api/auth/status']


def _call(client, method, path, body, headers=None):
    return getattr(client, method)(path, json=body, headers=headers or {})


def test_local_requests_keep_full_control_without_a_password(client):
    assert client.get('/api/auth/status').get_json() == {'status': 'success', 'password_set': False, 'control': True}
    assert client.post('/api/bot/auto-trade', json={'enabled': True}).status_code == 200


def test_shared_link_is_view_only_without_a_password(app, client):
    for method, path, body in MUTATIONS:
        res = _call(client, method, path, body, REMOTE)
        assert res.status_code == 403, (path, res.status_code)
        assert res.get_json()['code'] == 'view_only'
    assert app.trading_bot.auto_trade is False
    for path in READS:
        assert client.get(path, headers=REMOTE).status_code == 200, path
    assert client.get('/api/auth/status', headers=REMOTE).get_json()['control'] is False


def test_forwarded_host_counts_as_remote(client):
    headers = {'X-Forwarded-Host': 'example.ngrok.app'}
    assert client.post('/api/bot/run', headers=headers).status_code == 403


def test_password_is_required_everywhere_once_set(app, client):
    app.config['ADMIN_PASSWORD'] = 'correct horse battery'
    good = {'X-Admin-Token': 'correct horse battery'}
    for extra in ({}, REMOTE):
        for method, path, body in MUTATIONS:
            res = _call(client, method, path, body, dict(extra))
            assert res.status_code == 401 and res.get_json()['code'] == 'locked', path
            assert _call(client, method, path, body, {**extra, 'X-Admin-Token': 'wrong'}).status_code == 401
        for path in READS:
            assert client.get(path, headers=dict(extra)).status_code == 200
    assert app.trading_bot.auto_trade is False

    assert client.get('/api/auth/status', headers={**REMOTE, **good}).get_json()['control'] is True
    res = client.post('/api/bot/auto-trade', json={'enabled': True}, headers={**REMOTE, **good})
    assert res.status_code == 200 and app.trading_bot.auto_trade is True


def test_unlock_endpoint(app, client, monkeypatch):
    monkeypatch.setattr('auth.time.sleep', lambda s: None)
    assert client.post('/api/auth/unlock', json={'password': 'x'}).status_code == 400  # none configured
    app.config['ADMIN_PASSWORD'] = 'correct horse battery'
    assert client.post('/api/auth/unlock', json={'password': 'nope'}, headers=REMOTE).status_code == 401
    assert client.post('/api/auth/unlock', json={}, headers=REMOTE).status_code == 401
    assert client.post('/api/auth/unlock', json={'password': 'correct horse battery'}, headers=REMOTE).status_code == 200


def test_viewers_can_run_backtests(client, fake_data):
    fake_data.bars['AAPL'] = make_bars(n=78 * 4, drift=0.0003, vol=0.003, seed=3)
    assert client.post('/api/backtest/run', json={'symbol': 'AAPL'}, headers=REMOTE).status_code == 200


def test_secrets_are_never_returned(app, client):
    app.config.update(ADMIN_PASSWORD='correct horse battery', DISCORD_WEBHOOK_URL='https://discord.test/hook/SECRET')
    for path in READS:
        body = client.get(path, headers=REMOTE).get_data(as_text=True)
        assert 'correct horse' not in body and 'SECRET' not in body, path
