import React, { useState, useEffect, useCallback } from 'react';
import SignalsPanel from './components/SignalsPanel';
import TradesPanel from './components/TradesPanel';
import AnalyticsPanel from './components/AnalyticsPanel';
import BotPanel from './components/BotPanel';
import BacktestPanel from './components/BacktestPanel';
import SettingsPanel from './components/SettingsPanel';
import AdminPanel from './components/AdminPanel';
import LoginPage from './components/LoginPage';
import { healthAPI, authAPI, getSessionToken, setSessionToken, setLoggedOutHandler } from './api/client';
import { AccessContext } from './access';
import './App.css';

const TABS = [
  { id: 'bot', label: 'Bot', Component: BotPanel },
  { id: 'signals', label: 'Signals', Component: SignalsPanel },
  { id: 'trades', label: 'Trades', Component: TradesPanel },
  { id: 'analytics', label: 'Analytics', Component: AnalyticsPanel },
  { id: 'backtest', label: 'Backtest', Component: BacktestPanel },
  { id: 'settings', label: 'Settings', Component: SettingsPanel },
  { id: 'admin', label: 'Admin', Component: AdminPanel, adminOnly: true },
];

function App() {
  const [activeTab, setActiveTab] = useState('bot');
  const [health, setHealth] = useState(null);
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(!!getSessionToken());

  const logout = useCallback(() => {
    setSessionToken('');
    setUser(null);
    setActiveTab('bot');
  }, []);

  useEffect(() => {
    setLoggedOutHandler(logout);
    if (!getSessionToken()) return;
    authAPI
      .me()
      .then((r) => setUser(r.data.user))
      .catch(() => setSessionToken(''))
      .finally(() => setChecking(false));
  }, [logout]);

  useEffect(() => {
    const check = () =>
      healthAPI.checkStatus().then((r) => setHealth(r.data)).catch(() => setHealth({ status: 'offline' }));
    check();
    const interval = setInterval(check, 60000);
    return () => clearInterval(interval);
  }, []);

  const onLoggedIn = (token, loggedIn) => {
    setSessionToken(token);
    setUser(loggedIn);
    setActiveTab('bot');
  };

  if (checking) return <div className="loading">Loading…</div>;
  if (!user) return <LoginPage onLoggedIn={onLoggedIn} />;

  const isAdmin = user.role === 'admin';
  const tabs = TABS.filter((t) => !t.adminOnly || isAdmin);
  const Active = (tabs.find((t) => t.id === activeTab) || tabs[0]).Component;

  return (
    <div className="App">
      <header className="app-header">
        <div className="user-bar">
          <span>
            👤 {user.username}
            {isAdmin && <span className="role-badge">admin</span>}
          </span>
          <button className="link-button" onClick={logout}>Log out</button>
        </div>
        <h1>📈 Day Trading Bot</h1>
        <p>Strategy signals, automated paper trading &amp; performance analytics</p>
        {health && health.status !== 'healthy' && (
          <span className="health-badge bad">API {health.status}</span>
        )}
      </header>

      <nav className="app-nav">
        {tabs.map((t) => (
          <button key={t.id} className={`nav-button ${activeTab === t.id ? 'active' : ''}`} onClick={() => setActiveTab(t.id)}>
            {t.label}
          </button>
        ))}
      </nav>

      <main className="app-content">
        <AccessContext.Provider value={{ user, isAdmin, canControl: true }}>
          <Active key={user.id} />
        </AccessContext.Provider>
      </main>

      <footer className="app-footer">
        Decision-support tool. Not financial advice. No strategy wins every trade. Paper trade first.
      </footer>
    </div>
  );
}

export default App;
