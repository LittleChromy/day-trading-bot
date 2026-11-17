import React, { useCallback, useEffect, useState } from 'react';
import { accountAPI, authAPI, botAPI, errorMessage, setSessionToken } from '../api/client';
import { useAccess } from '../access';

const FIELDS = [
  { key: 'CONFIDENCE_THRESHOLD', label: 'Minimum signal confidence', unit: '%', scale: 100, step: 1,
    help: 'Only trade signals at least this confident. Higher means fewer trades.' },
  { key: 'RISK_PER_TRADE_PCT', label: 'Risk per trade', unit: '% of equity', step: 0.1,
    help: 'How much you lose if a trade hits its stop. Sets the position size.' },
  { key: 'MAX_POSITION_PCT', label: 'Max position size', unit: '% of equity', step: 1 },
  { key: 'STOP_LOSS_PCT', label: 'Stop loss', unit: '%', step: 0.1 },
  { key: 'TAKE_PROFIT_PCT', label: 'Take profit', unit: '%', step: 0.1 },
  { key: 'MAX_OPEN_POSITIONS', label: 'Max open positions', unit: '', step: 1 },
  { key: 'MAX_DAILY_LOSS_PCT', label: 'Daily loss limit', unit: '% of equity', step: 0.5,
    help: 'No new trades for the rest of the day once you are down this much.' },
];

const SettingsPanel = ({ onTokenChange }) => {
  const { user } = useAccess();
  const [data, setData] = useState(null);
  const [form, setForm] = useState({});
  const [capital, setCapital] = useState('');
  const [webhook, setWebhook] = useState('');
  const [pw, setPw] = useState({ current: '', next: '', repeat: '' });
  const [msg, setMsg] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(null);

  const load = useCallback(async () => {
    try {
      const res = await accountAPI.settings();
      setData(res.data);
      const f = {};
      FIELDS.forEach(({ key, scale = 1 }) => {
        f[key] = String(+(res.data.settings[key] * scale).toFixed(2));
      });
      f.NOTIFY_SIGNALS = !!res.data.settings.NOTIFY_SIGNALS;
      f.NOTIFY_TRADES = !!res.data.settings.NOTIFY_TRADES;
      setForm(f);
      setCapital(String(res.data.starting_capital));
    } catch (e) {
      setErr(errorMessage(e));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const run = async (name, fn, success) => {
    setBusy(name);
    setMsg(null);
    setErr(null);
    try {
      const res = await fn();
      setMsg(typeof success === 'function' ? success(res.data) : success);
      return res;
    } catch (e) {
      setErr(errorMessage(e));
      return null;
    } finally {
      setBusy(null);
    }
  };

  const saveRisk = async (e) => {
    e.preventDefault();
    const settings = {};
    FIELDS.forEach(({ key, scale = 1 }) => {
      settings[key] = parseFloat(form[key]) / scale;
    });
    settings.NOTIFY_SIGNALS = form.NOTIFY_SIGNALS;
    settings.NOTIFY_TRADES = form.NOTIFY_TRADES;
    const body = { settings };
    if (!data.alpaca_account) body.starting_capital = parseFloat(capital);
    const res = await run('risk', () => accountAPI.update(body), 'Settings saved');
    if (res) load();
  };

  const resetDefaults = async () => {
    const settings = {};
    FIELDS.forEach(({ key }) => {
      settings[key] = null;
    });
    const res = await run('defaults', () => accountAPI.update({ settings }), 'Back to the default settings');
    if (res) load();
  };

  const saveWebhook = async (url) => {
    const res = await run('discord', () => accountAPI.update({ discord_webhook_url: url }),
      url ? 'Discord link saved' : 'Discord notifications turned off');
    if (res) {
      setWebhook('');
      load();
    }
  };

  const changePassword = async (e) => {
    e.preventDefault();
    if (pw.next !== pw.repeat) {
      setErr('The new passwords do not match');
      return;
    }
    const res = await run('password', () => authAPI.changePassword(pw.current, pw.next),
      'Password changed. Other devices have been logged out.');
    if (res) {
      setSessionToken(res.data.token);
      if (onTokenChange) onTokenChange(res.data.token);
      setPw({ current: '', next: '', repeat: '' });
    }
  };

  const resetAccount = () => {
    if (!window.confirm('Start your simulated account over? All your trades and activity will be deleted. '
      + 'This cannot be undone.')) return;
    run('reset', accountAPI.reset, (d) => `Account reset (${d.deleted_trades} trade(s) removed)`);
  };

  if (!data) return err ? <div className="error-message">{err}</div> : <div className="loading">Loading settings…</div>;

  const [minCap, maxCap] = data.capital_limits;
  const isSimulated = !user?.is_admin || !data.alpaca_account;

  return (
    <div className="settings-panel">
      <div className="panel-header">
        <h2>Settings</h2>
        <span className="muted">Signed in as <b>{user?.username}</b> ({user?.role})</span>
      </div>

      {err && <div className="error-message">{err}</div>}
      {msg && <div className="info-message">{msg}</div>}

      <form className="card" onSubmit={saveRisk}>
        <div className="row-between">
          <h3>Your trading rules</h3>
          <button type="button" className="btn btn-sm btn-secondary" onClick={resetDefaults} disabled={!!busy}>
            Use defaults
          </button>
        </div>
        <p className="muted small">These apply to your account only, for auto-trading and for trades you open yourself.</p>
        <div className="form-grid">
          {FIELDS.map(({ key, label, unit, scale = 1, step, help }) => {
            const [lo, hi] = data.limits[key];
            return (
              <label key={key} className="form-field" title={help || ''}>
                <span>{label}{unit ? ` (${unit})` : ''}</span>
                <input className="input" type="number" step={step} min={+(lo * scale).toFixed(2)} max={+(hi * scale).toFixed(2)}
                       value={form[key] ?? ''} onChange={(e) => setForm({ ...form, [key]: e.target.value })} required />
                <span className="muted small">default {+(data.defaults[key] * scale).toFixed(2)}{unit === '%' ? '%' : ''}</span>
              </label>
            );
          })}
          {isSimulated && (
            <label className="form-field">
              <span>Starting balance ($)</span>
              <input className="input" type="number" min={minCap} max={maxCap} step="1000"
                     value={capital} onChange={(e) => setCapital(e.target.value)} required />
              <span className="muted small">pretend money for your simulated account</span>
            </label>
          )}
        </div>
        <div className="form-actions">
          <button className="btn btn-primary" type="submit" disabled={!!busy}>
            {busy === 'risk' ? 'Saving…' : 'Save'}
          </button>
          <span className="muted small">
            Short selling: {data.server_wide.ALLOW_SHORTING ? 'allowed' : 'off'} · close everything before the bell:{' '}
            {data.server_wide.FLATTEN_AT_CLOSE ? 'yes' : 'no'} (set by the admin)
          </span>
        </div>
      </form>

      <div className="two-col">
        <div className="card">
          <h3>Discord notifications</h3>
          <p className="small">
            {data.discord_configured ? <span className="pill pill-green">ON</span> : <span className="pill pill-gray">OFF</span>}{' '}
            Get a message on your phone when your bot opens or closes a trade.
          </p>
          <p className="muted small">
            In Discord: channel settings (gear) → Integrations → Webhooks → New Webhook → Copy Webhook URL, then
            paste it here. Treat the link like a password.
          </p>
          <div className="row-gap wrap">
            <input className="input grow" type="url" placeholder="https://discord.com/api/webhooks/…"
                   value={webhook} onChange={(e) => setWebhook(e.target.value)} />
            <button className="btn btn-primary" disabled={!webhook || !!busy} onClick={() => saveWebhook(webhook.trim())}>
              Save
            </button>
          </div>
          <div className="row-gap wrap" style={{ marginTop: '0.75rem' }}>
            <label className="small"><input type="checkbox" checked={!!form.NOTIFY_TRADES}
              onChange={(e) => setForm({ ...form, NOTIFY_TRADES: e.target.checked })} /> trades</label>
            <label className="small"><input type="checkbox" checked={!!form.NOTIFY_SIGNALS}
              onChange={(e) => setForm({ ...form, NOTIFY_SIGNALS: e.target.checked })} /> every new signal</label>
            <span className="muted small">(saved with Save above)</span>
          </div>
          {data.discord_configured && (
            <div className="row-gap" style={{ marginTop: '0.75rem' }}>
              <button className="btn btn-sm btn-secondary" disabled={!!busy}
                      onClick={() => run('test', botAPI.notifyTest, (d) => d.message)}>Send test</button>
              <button className="btn btn-sm btn-secondary" disabled={!!busy} onClick={() => saveWebhook('')}>Turn off</button>
            </div>
          )}
        </div>

        <form className="card" onSubmit={changePassword}>
          <h3>Change password</h3>
          <label className="form-field"><span>Current password</span>
            <input className="input" type="password" autoComplete="current-password" required
                   value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} /></label>
          <label className="form-field"><span>New password (8+ characters)</span>
            <input className="input" type="password" autoComplete="new-password" minLength={8} required
                   value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} /></label>
          <label className="form-field"><span>Repeat new password</span>
            <input className="input" type="password" autoComplete="new-password" minLength={8} required
                   value={pw.repeat} onChange={(e) => setPw({ ...pw, repeat: e.target.value })} /></label>
          <div className="form-actions">
            <button className="btn btn-primary" type="submit" disabled={!!busy}>Change password</button>
          </div>
        </form>
      </div>

      {isSimulated && (
        <div className="card">
          <h3>Start over</h3>
          <p className="muted small">
            Deletes all your trades and activity and puts your simulated balance back to the starting amount.
            Close your open positions first.
          </p>
          <button className="btn btn-danger" onClick={resetAccount} disabled={!!busy}>Reset my account</button>
        </div>
      )}
    </div>
  );
};

export default SettingsPanel;
