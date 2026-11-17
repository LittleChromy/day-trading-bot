import React, { useCallback, useEffect, useState } from 'react';
import { adminAPI, botAPI, errorMessage } from '../api/client';
import { useAccess } from '../access';

const money = (v) => (v == null ? '—' : `${v < 0 ? '-' : ''}$${Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}`);
const when = (iso) => (iso ? new Date(iso + 'Z').toLocaleString() : 'never');

const AdminPanel = () => {
  const { user: me } = useAccess();
  const [users, setUsers] = useState([]);
  const [signup, setSignup] = useState(true);
  const [events, setEvents] = useState([]);
  const [form, setForm] = useState({ username: '', password: '', role: 'user' });
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [u, e] = await Promise.all([adminAPI.users(), botAPI.events(40, true)]);
      setUsers(u.data.users);
      setSignup(u.data.signup_allowed);
      setEvents(e.data.events);
      setErr(null);
    } catch (e) {
      setErr(errorMessage(e));
    }
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, 60000);
    return () => clearInterval(interval);
  }, [load]);

  const act = async (fn, success) => {
    setBusy(true);
    setMsg(null);
    setErr(null);
    try {
      await fn();
      setMsg(success);
      await load();
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const create = (e) => {
    e.preventDefault();
    act(() => adminAPI.createUser(form.username.trim(), form.password, form.role),
      `Created ${form.role} account "${form.username.trim()}"`).then(() =>
      setForm({ username: '', password: '', role: 'user' }));
  };

  const resetPassword = (u) => {
    const password = window.prompt(`New password for ${u.username} (8+ characters):`);
    if (!password) return;
    act(() => adminAPI.updateUser(u.id, { password }), `Password for ${u.username} changed. They have been logged out.`);
  };

  const remove = (u) => {
    if (!window.confirm(`Delete ${u.username} and all their trades? This cannot be undone.`)) return;
    act(() => adminAPI.deleteUser(u.id), `Deleted ${u.username}`);
  };

  const active = users.filter((u) => u.is_active);
  const trading = active.filter((u) => u.auto_trade).length;

  return (
    <div className="admin-panel">
      <div className="panel-header">
        <h2>Admin</h2>
        <label className="row-gap small">
          <input type="checkbox" checked={signup} disabled={busy}
                 onChange={(e) => act(() => adminAPI.setSignup(e.target.checked),
                   e.target.checked ? 'Anyone with the link can now create an account' : 'Sign-up closed')} />
          Anyone with the link can sign up
        </label>
      </div>

      {err && <div className="error-message">{err}</div>}
      {msg && <div className="info-message">{msg}</div>}

      <div className="metrics-grid">
        <div className="metric-card"><p className="metric-label">Accounts</p><p className="metric-value">{users.length}</p></div>
        <div className="metric-card"><p className="metric-label">Active</p><p className="metric-value">{active.length}</p></div>
        <div className="metric-card"><p className="metric-label">Auto-trading</p><p className="metric-value">{trading}</p></div>
      </div>

      <div className="card">
        <h3>Accounts</h3>
        <div className="table-wrap">
          <table className="data-table compact">
            <thead>
              <tr>
                <th>User</th><th>Role</th><th>Auto</th><th className="num">Equity</th><th className="num">Today</th>
                <th className="num">Total P&amp;L</th><th className="num">Trades</th><th className="num">Win rate</th>
                <th className="num">Open</th><th>Last login</th><th />
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className={u.is_active ? '' : 'muted'}>
                  <td className="bold">
                    {u.username}{u.id === me?.id ? ' (you)' : ''}
                    {!u.is_active && <span className="pill pill-gray" style={{ marginLeft: 6 }}>disabled</span>}
                  </td>
                  <td><span className={`pill ${u.role === 'admin' ? 'pill-blue' : 'pill-gray'}`}>{u.role}</span></td>
                  <td>{u.auto_trade ? <span className="text-green">ON</span> : 'off'}</td>
                  <td className="num">{money(u.equity)}</td>
                  <td className={`num ${u.daily_pnl > 0 ? 'text-green' : u.daily_pnl < 0 ? 'text-red' : ''}`}>{money(u.daily_pnl)}</td>
                  <td className={`num ${u.total_pnl > 0 ? 'text-green' : u.total_pnl < 0 ? 'text-red' : ''}`}>{money(u.total_pnl)}</td>
                  <td className="num">{u.closed_trades}</td>
                  <td className="num">{u.win_rate == null ? '—' : `${u.win_rate}%`}</td>
                  <td className="num">{u.open_positions}</td>
                  <td className="small muted">{when(u.last_login)}</td>
                  <td>
                    {u.id !== me?.id && (
                      <div className="actions">
                        <button className="btn btn-sm btn-secondary" disabled={busy}
                                onClick={() => act(() => adminAPI.updateUser(u.id, { role: u.role === 'admin' ? 'user' : 'admin' }),
                                  `${u.username} is now ${u.role === 'admin' ? 'a normal user' : 'an admin'}`)}>
                          {u.role === 'admin' ? 'Make user' : 'Make admin'}
                        </button>
                        <button className="btn btn-sm btn-secondary" disabled={busy} onClick={() => resetPassword(u)}>Password</button>
                        <button className="btn btn-sm btn-secondary" disabled={busy}
                                onClick={() => act(() => adminAPI.updateUser(u.id, { is_active: !u.is_active }),
                                  `${u.username} ${u.is_active ? 'disabled' : 'enabled'}`)}>
                          {u.is_active ? 'Disable' : 'Enable'}
                        </button>
                        <button className="btn btn-sm btn-danger" disabled={busy} onClick={() => remove(u)}>Delete</button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted small">
          Normal accounts trade with pretend money only. Admins can see everyone's results here; each user sees only
          their own.
        </p>
      </div>

      <div className="two-col">
        <form className="card" onSubmit={create}>
          <h3>Add an account</h3>
          <label className="form-field"><span>Username</span>
            <input className="input" required minLength={3} maxLength={30} value={form.username}
                   onChange={(e) => setForm({ ...form, username: e.target.value })} /></label>
          <label className="form-field"><span>Password (8+ characters)</span>
            <input className="input" type="text" required minLength={8} value={form.password} autoComplete="off"
                   onChange={(e) => setForm({ ...form, password: e.target.value })} /></label>
          <label className="form-field"><span>Role</span>
            <select className="input" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              <option value="user">Normal user</option>
              <option value="admin">Admin</option>
            </select></label>
          <div className="form-actions">
            <button className="btn btn-primary" type="submit" disabled={busy}>Create</button>
          </div>
        </form>

        <div className="card">
          <h3>Everyone's activity</h3>
          {events.length ? (
            <ul className="event-log">
              {events.map((e) => (
                <li key={e.id} className={e.level === 'ERROR' ? 'text-red' : ''}>
                  <span className="muted small">{new Date(e.timestamp + 'Z').toLocaleString()}</span>
                  <span className="pill pill-gray">{e.username || 'system'}</span>
                  <span>{e.message}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted small">No activity yet.</p>
          )}
        </div>
      </div>
    </div>
  );
};

export default AdminPanel;
