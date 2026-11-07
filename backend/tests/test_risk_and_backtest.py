import pytest

from risk_manager import stop_and_target, position_size, check_trade_allowed, exit_hit
from backtester import run_backtest
from conftest import make_bars

SETTINGS = {
    'STARTING_CAPITAL': 100000.0, 'CONFIDENCE_THRESHOLD': 0.6, 'ALLOW_SHORTING': False,
    'STOP_LOSS_PCT': 1.0, 'TAKE_PROFIT_PCT': 2.0, 'RISK_PER_TRADE_PCT': 1.0,
    'MAX_POSITION_PCT': 10.0, 'MAX_OPEN_POSITIONS': 2, 'MAX_DAILY_LOSS_PCT': 3.0,
}


def test_stop_and_target():
    assert stop_and_target(100, 'BUY', 1.5, 3) == (98.5, 103.0)
    assert stop_and_target(100, 'SELL', 1.5, 3) == (101.5, 97.0)


def test_position_size_respects_risk_and_caps():
    # risk 1% of 100k = 1000; $2 risk/share -> 500 shares, but 10% cap = 100 shares at $100
    assert position_size(100000, 100, 98, 1.0, 10.0) == 100
    assert position_size(100000, 100, 98, 1.0, 100.0) == 500
    assert position_size(100000, 100, 98, 1.0, 100.0, buying_power=5000) == 50
    assert position_size(0, 100, 98, 1, 10) == 0
    assert position_size(100000, 100, 100, 1, 10) == 0


def test_trade_checks():
    ok, _ = check_trade_allowed('BUY', 'AAPL', set(), 0, 0, 100000, SETTINGS)
    assert ok
    assert not check_trade_allowed('SELL', 'AAPL', set(), 0, 0, 100000, SETTINGS)[0]
    assert not check_trade_allowed('BUY', 'AAPL', {'AAPL'}, 1, 0, 100000, SETTINGS)[0]
    assert not check_trade_allowed('BUY', 'MSFT', {'A', 'B'}, 2, 0, 100000, SETTINGS)[0]
    assert not check_trade_allowed('BUY', 'MSFT', set(), 0, -3000, 100000, SETTINGS)[0]


def test_exit_hit_prefers_stop_when_both_touched():
    assert exit_hit('BUY', 99, 102, 103, 98) == ('STOP_LOSS', 99)
    assert exit_hit('BUY', 99, 102, 102.5, 100) == ('TAKE_PROFIT', 102)
    assert exit_hit('SELL', 101, 98, 100.5, 97) == ('TAKE_PROFIT', 98)
    assert exit_hit('BUY', 99, 102, 101, 100) == (None, None)


def test_backtest_runs_and_is_consistent():
    bars = make_bars(n=78 * 6, drift=0.0003, vol=0.003, seed=7)
    result = run_backtest(bars, SETTINGS, symbol='TEST')
    m = result['metrics']
    assert m['total_trades'] == len(result['trades'])
    assert m['winning_trades'] + m['losing_trades'] == m['total_trades']
    pnl = sum(t['profit_loss'] for t in result['trades'])
    assert m['final_equity'] == pytest.approx(SETTINGS['STARTING_CAPITAL'] + pnl, abs=0.05)
    # positions never carry overnight
    for t in result['trades']:
        assert t['entry_time'][:10] == t['exit_time'][:10]
        assert t['side'] == 'BUY'
    assert m['max_drawdown_pct'] <= 0


def test_backtest_rejects_short_history():
    with pytest.raises(ValueError):
        run_backtest(make_bars(n=20), SETTINGS)
