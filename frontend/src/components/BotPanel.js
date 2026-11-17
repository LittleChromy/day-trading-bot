import React, { useState, useEffect, useCallback } from 'react';
import { botAPI, errorMessage } from '../api/client';
import { useAccess } from '../access';

const money = (v) => (v == null ? '—' : `${v < 0 ? '-' : ''}$${Math.abs(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`);

const BotPanel = () => {
  const { canControl, isAdmin } = useAccess();
  const [status, setStatus] = useState(null);
  const [account, setAccount] = useState(null);
  const [events, setEvents] = useState([]);
  const [models, setModels] = useState([]);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);

  const refresh = useCallback(async () => {
    try {
      const [s, a, e, m] = await Promise.all([botAPI.status(), botAPI.account(), botAPI.events(30), botAPI.models()]);
      setStatus(s.data.bot);
      setAccount(a.data.account);
      setEvents(e.data.events);
      setModels(m.data.models);
      setError(null);
    } catch (err) {
      setError(`Cannot reach the bot API: ${errorMessage(err)}`);
    }
  }, []);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 30000);
    return () => clearInterval(interval);
  }, [refresh]);

  const act = async (name, fn, describe) => {
    setBusy(name);
    setNotice(null);
    try {
      const res = await fn();
      setNotice(describe ? describe(res.data) : 'Done');
      setError(null);
      await refresh();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  const toggleAuto = () => {
    const enable = !status.auto_trade;
    if (enable && !window.confirm(
      `Enable automated trading?\n\nThe bot will open and close positions on its own in ` +
      `"${status.execution_mode}" mode using your risk settings.`)) return;
    act('auto', () => botAPI.setAutoTrade(enable), (d) => `Auto-trading ${d.auto_trade ? 'enabled' : 'disabled'}`);
  };

  const flatten = () => {
    if (!window.confirm('Close ALL open positions now?')) return;
    act('flatten', botAPI.flatten, (d) => `Closed ${d.closed.length} position(s)`);
  };

  if (!status) {
    return error ? <div className="error-message">{error}</div> : <div className="loading">Loading bot status…</div>;
  }

  const r = status.risk || {};
  const scanner = status.scanner || {};
  const picks = scanner.scanned || [];

  return (
    <div className="bot-panel">
      <div className="panel-header">
        <h2>Trading Bot</h2>
        {canControl && (
        <div className="row-gap wrap">
          <button className={`btn ${status.auto_trade ? 'btn-danger' : 'btn-success'}`} onClick={toggleAuto} disabled={!!busy}>
            {status.auto_trade ? 'Stop auto-trading' : 'Start auto-trading'}
          </button>
          {isAdmin && (
            <button className="btn btn-primary" disabled={!!busy}
                    onClick={() => act('run', botAPI.run, (d) =>
                      `Cycle done for all accounts: ${d.summary.signals} signal(s), ${d.summary.entries.length} entr(ies), ${d.summary.exits.length} exit(s)`)}>
              {busy === 'run' ? 'Running…' : 'Run cycle now'}
            </button>
          )}
          <button className="btn btn-warning" onClick={flatten} disabled={!!busy}>Flatten all</button>
        </div>
        )}
      </div>

      {error && <div className="error-message">{error}</div>}
      {notice && <div className="info-message">{notice}</div>}
      {!status.alpaca_configured && isAdmin && (
        <div className="warning-message">
          Alpaca API keys are not configured. Add them to <code>.env</code> to get market data and signals.
        </div>
      )}
      {status.last_error && <div className="error-message">Last cycle error: {status.last_error}</div>}

      <div className="metrics-grid">
        <Stat label="Auto-trading" value={status.auto_trade ? 'ON' : 'OFF'} cls={status.auto_trade ? 'text-green' : 'muted'} />
        <Stat label="Execution" value={status.execution_mode} sub={status.paper_account ? 'paper' : 'LIVE'} />
        <Stat label="Market" value={status.market_open ? 'Open' : 'Closed'} cls={status.market_open ? 'text-green' : 'text-red'}
              sub={status.market_clock_estimated ? 'estimated' : null} />
        <Stat label="Open positions" value={`${status.open_positions} / ${r.MAX_OPEN_POSITIONS}`} />
        {account && <Stat label="Equity" value={money(account.equity)} />}
        {account && <Stat label="Today's P&L" value={money(account.daily_pnl)}
                          cls={account.daily_pnl >= 0 ? 'text-green' : 'text-red'} />}
      </div>

      <div className="two-col">
        <div className="card">
          <h3>Risk settings</h3>
          <dl className="kv">
            <dt>Confidence threshold</dt><dd>{Math.round(r.CONFIDENCE_THRESHOLD * 100)}%</dd>
            <dt>Risk per trade</dt><dd>{r.RISK_PER_TRADE_PCT}% of equity</dd>
            <dt>Max position size</dt><dd>{r.MAX_POSITION_PCT}% of equity</dd>
            <dt>Stop loss / take profit</dt><dd>{r.STOP_LOSS_PCT}% / {r.TAKE_PROFIT_PCT}%</dd>
            <dt>Daily loss limit</dt><dd>{r.MAX_DAILY_LOSS_PCT}%</dd>
            <dt>Short selling</dt><dd>{r.ALLOW_SHORTING ? 'allowed' : 'off'}</dd>
            <dt>Flatten before close</dt><dd>{r.FLATTEN_AT_CLOSE ? 'yes' : 'no'}</dd>
          </dl>
          <p className="muted small">Change these in the <b>Settings</b> tab.</p>
        </div>

        <div className="card">
          <div className="row-between">
            <h3>ML models</h3>
            {isAdmin && <button className="btn btn-sm btn-secondary" disabled={!!busy}
                    onClick={() => act('retrain', botAPI.retrain, (d) =>
                      `Retrained: random forest ${d.trained.random_forest ? '✓' : '—'}, neural net ${d.trained.neural_network ? '✓' : '—'}`)}>
              {busy === 'retrain' ? 'Training…' : 'Retrain now'}
            </button>}
          </div>
          {models.length ? (
            <table className="data-table compact">
              <thead><tr><th>Model</th><th className="num">Ver</th><th className="num">Accuracy</th><th className="num">Samples</th></tr></thead>
              <tbody>
                {models.slice(0, 6).map((m) => (
                  <tr key={m.id} className={m.is_active ? '' : 'muted'}>
                    <td>{m.model_type}</td>
                    <td className="num">v{m.version}</td>
                    <td className="num">{m.accuracy != null ? `${(m.accuracy * 100).toFixed(1)}%` : '—'}</td>
                    <td className="num">{m.training_samples}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="muted small">No models yet. They train automatically once at least 10 signal-based trades have closed with both wins and losses.</p>
          )}
        </div>
      </div>

      <div className="two-col">
        <div className="card">
          <div className="row-between">
            <h3>Stocks being analyzed ({(status.symbols || []).length})</h3>
            {scanner.enabled && isAdmin && (
              <button className="btn btn-sm btn-secondary" disabled={!!busy}
                      onClick={() => act('rescan', botAPI.rescan, (d) => `Scanner picked ${d.scanner.scanned.length} stock(s)`)}>
                {busy === 'rescan' ? 'Scanning…' : 'Rescan now'}
              </button>
            )}
          </div>
          {scanner.enabled ? (
            <>
              {scanner.last_error && (
                <p className="error-inline">Scanner unavailable ({scanner.last_error}); using the fixed watchlist.</p>
              )}
              {picks.length > 0 && (
                <table className="data-table compact">
                  <thead><tr><th>Scanner pick</th><th>Why</th><th className="num">Price</th><th className="num">Today</th></tr></thead>
                  <tbody>
                    {picks.map((p) => (
                      <tr key={p.symbol}>
                        <td className="bold">{p.symbol}</td>
                        <td className="muted">{p.source}</td>
                        <td className="num">${p.price.toFixed(2)}</td>
                        <td className={`num ${p.change_pct > 0 ? 'text-green' : p.change_pct < 0 ? 'text-red' : ''}`}>
                          {p.change_pct == null ? '—' : `${p.change_pct > 0 ? '+' : ''}${p.change_pct.toFixed(1)}%`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {!picks.length && !scanner.last_error && <p className="muted small">No scanner picks yet (the market may be closed).</p>}
              {scanner.include_watchlist && (
                <p className="muted small">Plus your watchlist: {(scanner.watchlist || []).join(', ') || '—'}</p>
              )}
            </>
          ) : (
            <p className="muted small">
              Fixed watchlist: {(status.symbols || []).join(', ')}. Set <code>AUTO_SCAN=true</code> to let the bot pick
              the day's most active stocks.
            </p>
          )}
        </div>

        <div className="card">
          <div className="row-between">
            <h3>Discord notifications</h3>
            {canControl && <button className="btn btn-sm btn-secondary" disabled={!!busy || !status.notifications}
                    onClick={() => act('notify', botAPI.notifyTest, (d) => d.message)}>
              {busy === 'notify' ? 'Sending…' : 'Send test'}
            </button>}
          </div>
          {status.notifications ? (
            <p className="small">
              <span className="pill pill-green">ON</span> You'll get a message when your trades open and close, and
              a summary at the market close.
            </p>
          ) : (
            <p className="muted small">
              <span className="pill pill-gray">OFF</span> Add your Discord webhook link in the <b>Settings</b> tab.
            </p>
          )}
        </div>
      </div>

      <div className="card">
        <h3>Activity log</h3>
        {events.length ? (
          <ul className="event-log">
            {events.map((e) => (
              <li key={e.id} className={e.level === 'ERROR' ? 'text-red' : ''}>
                <span className="muted small">{new Date(e.timestamp + 'Z').toLocaleString()}</span>
                <span className="pill pill-gray">{e.event_type}</span>
                <span>{e.message}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted small">No bot activity yet.</p>
        )}
      </div>
    </div>
  );
};

const Stat = ({ label, value, sub, cls = '' }) => (
  <div className="metric-card">
    <p className="metric-label">{label}</p>
    <p className={`metric-value ${cls}`}>{value}</p>
    {sub && <p className="muted small">{sub}</p>}
  </div>
);

export default BotPanel;
