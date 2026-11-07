import React, { useState } from 'react';
import { Line } from 'react-chartjs-2';
import { backtestAPI, errorMessage } from '../api/client';

const BacktestPanel = () => {
  const [form, setForm] = useState({
    symbol: 'AAPL', days: 30, timeframe: '5Min',
    STOP_LOSS_PCT: 1.5, TAKE_PROFIT_PCT: 3.0, CONFIDENCE_THRESHOLD: 0.6,
  });
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  const run = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await backtestAPI.run({
        symbol: form.symbol.trim().toUpperCase(),
        days: parseInt(form.days, 10),
        timeframe: form.timeframe,
        overrides: {
          STOP_LOSS_PCT: parseFloat(form.STOP_LOSS_PCT),
          TAKE_PROFIT_PCT: parseFloat(form.TAKE_PROFIT_PCT),
          CONFIDENCE_THRESHOLD: parseFloat(form.CONFIDENCE_THRESHOLD),
        },
      });
      setResult(res.data.backtest);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const m = result?.metrics;
  const chartData = result && {
    labels: result.equity_curve.map((p) => new Date(p.time).toLocaleDateString()),
    datasets: [{
      label: 'Equity ($)',
      data: result.equity_curve.map((p) => p.equity),
      borderColor: '#667eea',
      backgroundColor: 'rgba(102,126,234,0.1)',
      pointRadius: 0,
      borderWidth: 2,
      fill: true,
    }],
  };

  return (
    <div className="backtest-panel">
      <div className="panel-header">
        <h2>Backtest</h2>
      </div>

      <form className="card form-grid" onSubmit={run}>
        <label className="form-field"><span>Symbol</span>
          <input className="input" value={form.symbol} onChange={set('symbol')} required maxLength={10} /></label>
        <label className="form-field"><span>Days of history</span>
          <input className="input" type="number" min="1" max="365" value={form.days} onChange={set('days')} /></label>
        <label className="form-field"><span>Bar size</span>
          <select className="input" value={form.timeframe} onChange={set('timeframe')}>
            {['1Min', '5Min', '15Min', '1Hour'].map((t) => <option key={t} value={t}>{t}</option>)}
          </select></label>
        <label className="form-field"><span>Stop loss %</span>
          <input className="input" type="number" step="0.1" min="0.1" value={form.STOP_LOSS_PCT} onChange={set('STOP_LOSS_PCT')} /></label>
        <label className="form-field"><span>Take profit %</span>
          <input className="input" type="number" step="0.1" min="0.1" value={form.TAKE_PROFIT_PCT} onChange={set('TAKE_PROFIT_PCT')} /></label>
        <label className="form-field"><span>Min confidence</span>
          <input className="input" type="number" step="0.05" min="0" max="1" value={form.CONFIDENCE_THRESHOLD} onChange={set('CONFIDENCE_THRESHOLD')} /></label>
        <div className="form-actions">
          <button className="btn btn-primary" type="submit" disabled={loading}>{loading ? 'Running…' : 'Run backtest'}</button>
          <span className="muted small">Long-only unless ALLOW_SHORTING is on. Positions are closed at end of day.</span>
        </div>
      </form>

      {error && <div className="error-message">{error}</div>}

      {m && (
        <>
          <div className="metrics-grid">
            <Stat label="Total return" value={`${m.total_return_pct.toFixed(2)}%`} good={m.total_return_pct >= 0} />
            <Stat label="Buy & hold" value={`${m.buy_and_hold_return_pct.toFixed(2)}%`} />
            <Stat label="Trades" value={m.total_trades} />
            <Stat label="Win rate" value={`${m.win_rate.toFixed(1)}%`} good={m.win_rate >= 50} />
            <Stat label="Profit factor" value={m.profit_factor == null ? '—' : m.profit_factor.toFixed(2)} good={m.profit_factor == null || m.profit_factor >= 1} />
            <Stat label="Max drawdown" value={`${m.max_drawdown_pct.toFixed(2)}%`} />
            <Stat label="Sharpe" value={m.sharpe_ratio.toFixed(2)} />
            <Stat label="Final equity" value={`$${m.final_equity.toLocaleString()}`} />
          </div>

          <div className="chart-container">
            <h3>Equity curve — {result.symbol} ({result.timeframe}, {m.bars} bars)</h3>
            <div className="chart-box"><Line data={chartData} options={{ maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { ticks: { maxTicksLimit: 10 } } } }} /></div>
          </div>

          {result.trades.length > 0 && (
            <div className="card">
              <h3>Trades ({result.trades.length})</h3>
              <div className="table-wrap">
                <table className="data-table compact">
                  <thead><tr><th>Entry</th><th>Side</th><th className="num">Qty</th><th className="num">Entry $</th><th className="num">Exit $</th><th className="num">P&amp;L</th><th>Exit reason</th></tr></thead>
                  <tbody>
                    {result.trades.slice(-100).reverse().map((t, i) => (
                      <tr key={i}>
                        <td className="small">{new Date(t.entry_time).toLocaleString()}</td>
                        <td>{t.side}</td>
                        <td className="num">{t.quantity}</td>
                        <td className="num">{t.entry_price.toFixed(2)}</td>
                        <td className="num">{t.exit_price.toFixed(2)}</td>
                        <td className={`num bold ${t.profit_loss >= 0 ? 'text-green' : 'text-red'}`}>{t.profit_loss.toFixed(2)}</td>
                        <td className="small muted">{t.exit_reason.replace(/_/g, ' ').toLowerCase()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
};

const Stat = ({ label, value, good }) => (
  <div className="metric-card">
    <p className="metric-label">{label}</p>
    <p className={`metric-value ${good === undefined ? '' : good ? 'text-green' : 'text-red'}`}>{value}</p>
  </div>
);

export default BacktestPanel;
