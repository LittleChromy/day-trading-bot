import pytest

from conftest import ADMIN_PASSWORD, login_client, make_bars, make_user
from models import db, BotEvent, Trade, User

REMOTE = {'Host': 'quiet-river-1234.trycloudflare.com', 'CF-Connecting-IP': '203.0.113.9'}


def _uptrend(fake_data, symbol='AAPL'):
    fake_data.bars[symbol] = make_bars(n=150, drift=0.002, vol=0.0005, seed=1)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr('auth.time.sleep', lambda s: None)


# --------------------------------------------------------------- login wall
def test_everything_private_needs_login(anon):
    assert anon.get('/api/health/status').status_code == 200
    assert anon.get('/api/auth/config').status_code == 200
    for path in ('/api/bot/status', '/api/trades/all', '/api/signals/recent', '/api/analytics/performance',
                 '/api/account/settings', '/api/admin/users', '/api/auth/me'):
        res = anon.get(path)
        assert res.status_code == 401 and res.get_json()['code'] == 'login_required', path
    assert anon.post('/api/bot/auto-trade', json={'enabled': True}).status_code == 401


def test_bad_and_forged_tokens_are_rejected(app, client, anon):
    for token in ('garbage', client.environ_base['HTTP_AUTHORIZATION'][7:] + 'x'):
        assert anon.get('/api/auth/me', headers={'Authorization': f'Bearer {token}'}).status_code == 401
    from itsdangerous import URLSafeTimedSerializer
    forged = URLSafeTimedSerializer('wrong-secret', salt='dtb-auth').dumps({'u': 1, 'v': 1})
    assert anon.get('/api/auth/me', headers={'Authorization': f'Bearer {forged}'}).status_code == 401


# --------------------------------------------------------- first admin setup
def test_first_account_from_this_computer_becomes_admin(anon):
    assert anon.get('/api/auth/config').get_json()['can_create_admin'] is True
    res = anon.post('/api/auth/register', json={'username': 'owner', 'password': 'owner-password'})
    assert res.status_code == 201 and res.get_json()['user']['role'] == 'admin'
    res = anon.post('/api/auth/register', json={'username': 'second', 'password': 'second-password'})
    assert res.get_json()['user']['role'] == 'user'


def test_first_account_through_a_shared_link_is_not_admin(anon, app):
    cfg = anon.get('/api/auth/config', headers=REMOTE).get_json()
    assert cfg['needs_admin_setup'] is True and cfg['can_create_admin'] is False
    res = anon.post('/api/auth/register', json={'username': 'stranger', 'password': 'stranger-pass'}, headers=REMOTE)
    assert res.status_code == 201 and res.get_json()['user']['role'] == 'user'
    with app.app_context():
        assert User.query.filter_by(role='admin').count() == 0


def test_admin_created_from_env_and_legacy_trades_assigned(fake_data):
    from app import create_app
    import config as config_module

    class Cfg(config_module.TestingConfig):
        ADMIN_USERNAME = 'boss'
        ADMIN_PASSWORD = 'boss-password-1'
        AUTO_TRADE = True

    config_module.config['envtest'] = Cfg
    try:
        app = create_app('envtest', data_handler=fake_data, start_scheduler=False)
        with app.app_context():
            boss = User.query.filter_by(username='boss').one()
            assert boss.is_admin and boss.auto_trade is True
            db.session.add(Trade(symbol='OLD', trade_type='BUY', entry_price=1, quantity=1, status='OPEN'))
            db.session.commit()
            from models import assign_legacy_data
            assign_legacy_data(boss)
            assert Trade.query.filter_by(symbol='OLD').one().user_id == boss.id
        login_client(app, 'boss', 'boss-password-1')
        with app.app_context():
            db.drop_all()
    finally:
        config_module.config.pop('envtest')


# ------------------------------------------------------------- registration
def test_register_validation_and_duplicates(anon, admin_id):
    for body, msg in (({'username': 'ab', 'password': 'long-enough'}, 'Username'),
                      ({'username': 'bad name!', 'password': 'long-enough'}, 'Username'),
                      ({'username': 'carol', 'password': 'short'}, 'at least 8')):
        res = anon.post('/api/auth/register', json=body)
        assert res.status_code == 400 and msg in res.get_json()['message']
    assert anon.post('/api/auth/register', json={'username': 'Carol', 'password': 'carol-pass1'}).status_code == 201
    res = anon.post('/api/auth/register', json={'username': 'carol', 'password': 'carol-pass1'})
    assert res.status_code == 409


def test_admin_can_close_signup(client, anon):
    assert client.put('/api/admin/signup', json={'allowed': False}).get_json()['signup_allowed'] is False
    res = anon.post('/api/auth/register', json={'username': 'late', 'password': 'late-password'}, headers=REMOTE)
    assert res.status_code == 403 and res.get_json()['code'] == 'signup_closed'
    # the admin can still create accounts
    assert client.post('/api/admin/users', json={'username': 'late', 'password': 'late-password'}).status_code == 201


# --------------------------------------------------------------------- login
def test_login_errors_and_throttling(app, admin_id, anon):
    res = anon.post('/api/auth/login', json={'username': 'admin', 'password': 'nope'})
    assert res.status_code == 401
    assert anon.post('/api/auth/login', json={'username': 'nobody', 'password': 'nope'}).status_code == 401
    for _ in range(10):
        anon.post('/api/auth/login', json={'username': 'admin', 'password': 'nope'}, headers=REMOTE)
    res = anon.post('/api/auth/login', json={'username': 'admin', 'password': ADMIN_PASSWORD}, headers=REMOTE)
    assert res.status_code == 429
    # someone else's attempts don't lock the real owner out from another address
    assert anon.post('/api/auth/login', json={'username': 'ADMIN', 'password': ADMIN_PASSWORD}).status_code == 200


def test_password_change_logs_out_old_sessions(app, client):
    old = client.environ_base['HTTP_AUTHORIZATION']
    res = client.put('/api/auth/password', json={'current_password': 'wrong', 'new_password': 'new-password-1'})
    assert res.status_code == 401
    res = client.put('/api/auth/password', json={'current_password': ADMIN_PASSWORD, 'new_password': 'new-password-1'})
    assert res.status_code == 200
    assert client.get('/api/auth/me').status_code == 401          # old token is dead
    client.environ_base['HTTP_AUTHORIZATION'] = 'Bearer ' + res.get_json()['token']
    assert client.get('/api/auth/me').status_code == 200
    assert old != client.environ_base['HTTP_AUTHORIZATION']


# --------------------------------------------------------------- isolation
def test_users_only_see_and_touch_their_own_trades(app, client, user_client, fake_data):
    _uptrend(fake_data)
    sig = client.post('/api/signals/generate', json={'symbols': ['AAPL']}).get_json()['signals'][0]
    admin_trade = client.post(f"/api/signals/{sig['id']}/execute", json={}).get_json()['trade']

    # alice sees the shared signal as not traded by her, and can trade it herself
    mine = user_client.get('/api/signals/recent').get_json()['signals'][0]
    assert mine['id'] == sig['id'] and mine['acted_upon'] is False
    alice_trade = user_client.post(f"/api/signals/{sig['id']}/execute", json={}).get_json()['trade']
    assert alice_trade['execution_mode'] == 'simulated' and alice_trade['id'] != admin_trade['id']
    assert user_client.post(f"/api/signals/{sig['id']}/execute", json={}).status_code == 400

    assert [t['id'] for t in user_client.get('/api/trades/all').get_json()['trades']] == [alice_trade['id']]
    assert [t['id'] for t in client.get('/api/trades/all').get_json()['trades']] == [admin_trade['id']]
    # alice cannot read, close or cancel the admin's trade, or list it via user_id
    assert user_client.get(f"/api/trades/{admin_trade['id']}").status_code == 404
    assert user_client.put(f"/api/trades/close/{admin_trade['id']}", json={}).status_code == 404
    assert user_client.put(f"/api/trades/cancel/{admin_trade['id']}").status_code == 404
    assert user_client.get(f"/api/trades/all?user_id={admin_trade['user_id']}").get_json()['count'] == 1
    # the admin can look at alice's trades
    alice_id = alice_trade['user_id']
    assert client.get(f'/api/trades/all?user_id={alice_id}').get_json()['trades'][0]['id'] == alice_trade['id']

    # flatten only closes your own positions
    closed = user_client.post('/api/bot/flatten').get_json()['closed']
    assert [t['id'] for t in closed] == [alice_trade['id']]
    with app.app_context():
        assert db.session.get(Trade, admin_trade['id']).status == 'OPEN'

    # analytics and events are per user
    assert user_client.get('/api/analytics/performance').get_json()['metrics']['total_trades'] == 1
    assert client.get('/api/analytics/performance').get_json()['metrics']['total_trades'] == 0
    assert all(e['user_id'] == alice_id for e in user_client.get('/api/bot/events').get_json()['events'])


def test_each_account_has_its_own_balance(client, user_client, fake_data):
    user_client.put('/api/account/settings', json={'starting_capital': 25000})
    assert user_client.get('/api/bot/account').get_json()['account']['equity'] == 25000
    assert client.get('/api/bot/account').get_json()['account']['equity'] == 100000


def test_normal_users_cannot_use_admin_powers(user_client, client):
    for method, path in (('get', '/api/admin/users'), ('post', '/api/admin/users'), ('put', '/api/admin/users/1'),
                         ('delete', '/api/admin/users/1'), ('put', '/api/admin/signup'), ('post', '/api/bot/run'),
                         ('post', '/api/bot/retrain'), ('post', '/api/bot/universe'),
                         ('post', '/api/signals/generate')):
        res = getattr(user_client, method)(path, json={})
        assert res.status_code == 403 and res.get_json()['code'] == 'admin_only', path
    # but they can read the shared universe and models, and backtest
    assert user_client.get('/api/bot/universe').status_code == 200
    assert user_client.get('/api/bot/models').status_code == 200


def test_normal_users_are_always_simulated(app, user_client, fake_data):
    app.trading_bot.mode = 'alpaca'  # the admin trades through Alpaca
    _uptrend(fake_data)
    with app.app_context():
        from signal_service import generate_signals
        sig_id = generate_signals(app, ['AAPL'])[0].id
    trade = user_client.post(f'/api/signals/{sig_id}/execute', json={}).get_json()['trade']
    assert trade['execution_mode'] == 'simulated' and fake_data.orders == []
    assert user_client.get('/api/bot/status').get_json()['bot']['execution_mode'] == 'simulated'


# --------------------------------------------------------- per-user auto trading
def test_auto_trading_is_per_user_with_own_settings(app, client, fake_data):
    make_user(app, 'bob')
    make_user(app, 'cara')
    bob = login_client(app, 'bob', 'user-password-123')
    cara = login_client(app, 'cara', 'user-password-123')
    bob.post('/api/bot/auto-trade', json={'enabled': True})
    cara.post('/api/bot/auto-trade', json={'enabled': True})
    # cara demands more confidence than this signal has
    res = cara.put('/api/account/settings', json={'settings': {'CONFIDENCE_THRESHOLD': 0.95}})
    assert res.status_code == 200
    bob.put('/api/account/settings', json={'settings': {'STOP_LOSS_PCT': 0.5}})
    _uptrend(fake_data)

    summary = client.post('/api/bot/run').get_json()['summary']
    assert len(summary['entries']) == 1                             # admin's auto-trade is off; only bob
    assert any(s['user'] == 'cara' and 'threshold' in s['reason'] for s in summary['skipped'])
    trade = bob.get('/api/trades/all').get_json()['trades'][0]
    assert trade['stop_loss'] == pytest.approx(trade['entry_price'] * 0.995, abs=0.01)
    assert cara.get('/api/trades/all').get_json()['count'] == 0

    # the switch is stored, so it survives a restart
    with app.app_context():
        assert User.query.filter_by(username='bob').one().auto_trade is True


# ----------------------------------------------------------- account settings
def test_settings_validation(app, user_client):
    body = user_client.get('/api/account/settings').get_json()
    assert body['settings']['STOP_LOSS_PCT'] == app.config['STOP_LOSS_PCT']
    for bad in ({'settings': {'STOP_LOSS_PCT': 50}}, {'settings': {'NOPE': 1}}, {'settings': {'RISK_PER_TRADE_PCT': 'x'}},
                {'settings': {'CONFIDENCE_THRESHOLD': 0.2}}, {'starting_capital': 5},
                {'discord_webhook_url': 'http://169.254.169.254/latest'},
                {'discord_webhook_url': 'https://evil.example/api/webhooks/1/abc'}):
        assert user_client.put('/api/account/settings', json=bad).status_code == 400, bad
    ok = user_client.put('/api/account/settings', json={
        'settings': {'TAKE_PROFIT_PCT': 4.5, 'NOTIFY_SIGNALS': False},
        'discord_webhook_url': 'https://discord.com/api/webhooks/123/abc_DEF-9'}).get_json()
    assert ok['settings']['TAKE_PROFIT_PCT'] == 4.5 and ok['discord_configured'] is True
    reset = user_client.put('/api/account/settings', json={'settings': {'TAKE_PROFIT_PCT': None}}).get_json()
    assert reset['settings']['TAKE_PROFIT_PCT'] == app.config['TAKE_PROFIT_PCT']
    assert 'discord.com' not in user_client.get('/api/account/settings').get_data(as_text=True)


def test_account_reset(app, user_client, fake_data):
    _uptrend(fake_data)
    with app.app_context():
        from signal_service import generate_signals
        sig_id = generate_signals(app, ['AAPL'])[0].id
    user_client.post(f'/api/signals/{sig_id}/execute', json={})
    assert user_client.post('/api/account/reset', json={'confirm': 'RESET'}).status_code == 400  # open position
    user_client.post('/api/bot/flatten')
    assert user_client.post('/api/account/reset', json={}).status_code == 400
    assert user_client.post('/api/account/reset', json={'confirm': 'RESET'}).get_json()['deleted_trades'] == 1
    assert user_client.get('/api/trades/all?status=CLOSED').get_json()['count'] == 0


# ------------------------------------------------------------ admin panel
def test_admin_manages_users(app, client, user_client):
    users = client.get('/api/admin/users').get_json()['users']
    alice = next(u for u in users if u['username'] == 'alice')
    assert alice['equity'] == 100000 and alice['role'] == 'user'

    # promote and demote
    assert client.put(f"/api/admin/users/{alice['id']}", json={'role': 'admin'}).get_json()['user']['role'] == 'admin'
    assert client.put(f"/api/admin/users/{alice['id']}", json={'role': 'user'}).status_code == 200

    # reset her password: her session ends and the new password works
    assert client.put(f"/api/admin/users/{alice['id']}", json={'password': 'fresh-password'}).status_code == 200
    assert user_client.get('/api/auth/me').status_code == 401
    alice_client = login_client(app, 'alice', 'fresh-password')

    # disable: logged out, cannot log back in, auto-trade off
    alice_client.post('/api/bot/auto-trade', json={'enabled': True})
    client.put(f"/api/admin/users/{alice['id']}", json={'is_active': False})
    assert alice_client.get('/api/auth/me').status_code == 401
    assert app.test_client().post('/api/auth/login', json={'username': 'alice', 'password': 'fresh-password'}).status_code == 403
    with app.app_context():
        assert db.session.get(User, alice['id']).auto_trade is False

    # delete removes her data
    with app.app_context():
        db.session.add(Trade(symbol='X', trade_type='BUY', entry_price=1, quantity=1, status='CLOSED',
                             exit_price=2, user_id=alice['id']))
        db.session.add(BotEvent(event_type='ENTRY', message='x', user_id=alice['id']))
        db.session.commit()
    assert client.delete(f"/api/admin/users/{alice['id']}").status_code == 200
    with app.app_context():
        assert Trade.query.filter_by(user_id=alice['id']).count() == 0
        assert db.session.get(User, alice['id']) is None


def test_admin_cannot_lock_themselves_out(client, admin_id):
    assert client.put(f'/api/admin/users/{admin_id}', json={'role': 'user'}).status_code == 400
    assert client.put(f'/api/admin/users/{admin_id}', json={'is_active': False}).status_code == 400
    assert client.delete(f'/api/admin/users/{admin_id}').status_code == 400
    assert client.put('/api/admin/users/9999', json={'role': 'user'}).status_code == 404


def test_secrets_never_leave_the_server(app, client, user_client):
    user_client.put('/api/account/settings', json={'discord_webhook_url': 'https://discord.com/api/webhooks/1/SECRET'})
    for c in (client, user_client):
        for path in ('/api/admin/users', '/api/auth/me', '/api/account/settings', '/api/bot/status'):
            body = c.get(path).get_data(as_text=True)
            assert 'SECRET' not in body and 'password_hash' not in body and 'pbkdf2' not in body, path
