import React, { useState, useEffect } from 'react';
import SignalsPanel from './components/SignalsPanel';
import TradesPanel from './components/TradesPanel';
import AnalyticsPanel from './components/AnalyticsPanel';
import BotPanel from './components/BotPanel';
import BacktestPanel from './components/BacktestPanel';
import { healthAPI } from './api/client';
import './App.css';

const TABS = [
  { id: 'bot', label: 'Bot', Component: BotPanel },
  { id: 'signals', label: 'Signals', Component: SignalsPanel },
  { id: 'trades', label: 'Trades', Component: TradesPanel },
  { id: 'analytics', label: 'Analytics', Component: AnalyticsPanel },
  { id: 'backtest', label: 'Backtest', Component: BacktestPanel },
];

function App() {
  const [activeTab, setActiveTab] = useState('bot');
  const [health, setHealth] = useState(null);

  useEffect(() => {
    const check = () =>
      healthAPI.checkStatus().then((r) => setHealth(r.data)).catch(() => setHealth({ status: 'offline' }));
    check();
    const interval = setInterval(check, 60000);
    return () => clearInterval(interval);
  }, []);

  const Active = TABS.find((t) => t.id === activeTab).Component;

  return (
    <div className="App">
      <header className="app-header">
        <h1>📈 Day Trading Bot</h1>
        <p>Strategy signals, automated paper trading &amp; performance analytics</p>
        {health && (
          <span className={`health-badge ${health.status === 'healthy' ? 'ok' : 'bad'}`}>
            API {health.status}
            {health.execution_mode ? ` · ${health.execution_mode}` : ''}
            {health.auto_trade ? ' · auto-trading ON' : ''}
          </span>
        )}
      </header>

      <nav className="app-nav">
        {TABS.map((t) => (
          <button key={t.id} className={`nav-button ${activeTab === t.id ? 'active' : ''}`} onClick={() => setActiveTab(t.id)}>
            {t.label}
          </button>
        ))}
      </nav>

      <main className="app-content">
        <Active />
      </main>

      <footer className="app-footer">
        Decision-support tool. Not financial advice. No strategy wins every trade. Paper trade first.
      </footer>
    </div>
  );
}

export default App;
