import React, { useEffect, useState } from 'react';
import { authAPI, errorMessage } from '../api/client';

const LoginPage = ({ onLoggedIn }) => {
  const [config, setConfig] = useState(null);
  const [mode, setMode] = useState('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    authAPI
      .config()
      .then((r) => {
        setConfig(r.data);
        if (r.data.can_create_admin) setMode('register');
      })
      .catch((err) => setError(`Cannot reach the server: ${errorMessage(err)}`));
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    if (mode === 'register' && password !== confirm) {
      setError('The passwords do not match');
      return;
    }
    setBusy(true);
    try {
      const res = mode === 'login' ? await authAPI.login(username, password) : await authAPI.register(username, password);
      onLoggedIn(res.data.token, res.data.user);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const creatingAdmin = mode === 'register' && config?.can_create_admin;
  const canRegister = config?.signup_allowed;

  return (
    <div className="App">
      <header className="app-header">
        <h1>📈 Day Trading Bot</h1>
        <p>Strategy signals, automated paper trading &amp; performance analytics</p>
      </header>

      <main className="login-wrap">
        <form className="card login-card" onSubmit={submit}>
          <h2>{mode === 'login' ? 'Log in' : creatingAdmin ? 'Create the admin account' : 'Create an account'}</h2>

          {creatingAdmin && (
            <p className="info-message small">
              No admin exists yet. The first account created on this computer becomes the admin.
            </p>
          )}
          {mode === 'register' && !creatingAdmin && (
            <p className="muted small">
              You get your own bot with a simulated $100,000 account. No real money is involved.
            </p>
          )}

          <label className="form-field">
            <span>Username</span>
            <input className="input" value={username} onChange={(e) => setUsername(e.target.value)}
                   autoComplete="username" required minLength={3} maxLength={30} autoFocus />
          </label>
          <label className="form-field">
            <span>Password</span>
            <input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                   autoComplete={mode === 'login' ? 'current-password' : 'new-password'} required
                   minLength={mode === 'login' ? 1 : 8} />
          </label>
          {mode === 'register' && (
            <label className="form-field">
              <span>Repeat password</span>
              <input className="input" type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)}
                     autoComplete="new-password" required minLength={8} />
            </label>
          )}

          {error && <p className="error-inline">{error}</p>}

          <button className="btn btn-primary full" type="submit" disabled={busy || !config}>
            {busy ? 'Please wait…' : mode === 'login' ? 'Log in' : 'Create account'}
          </button>

          {mode === 'login' && canRegister && (
            <p className="center small">
              New here?{' '}
              <button type="button" className="link-button link-dark" onClick={() => { setMode('register'); setError(null); }}>
                Create an account
              </button>
            </p>
          )}
          {mode === 'login' && config && !canRegister && (
            <p className="center muted small">Sign-up is closed. Ask the admin for an account.</p>
          )}
          {mode === 'register' && !creatingAdmin && (
            <p className="center small">
              Already have an account?{' '}
              <button type="button" className="link-button link-dark" onClick={() => { setMode('login'); setError(null); }}>
                Log in
              </button>
            </p>
          )}
        </form>
      </main>

      <footer className="app-footer">
        Decision-support tool. Not financial advice. No strategy wins every trade.
      </footer>
    </div>
  );
};

export default LoginPage;
