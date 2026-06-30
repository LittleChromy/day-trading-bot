import React, { useState } from 'react';
import SignalsPanel from './components/SignalsPanel';
import TradesPanel from './components/TradesPanel';
import AnalyticsPanel from './components/AnalyticsPanel';
import './App.css';

function App() {
  const [activeTab, setActiveTab] = useState('signals');

  return (
    <div className="App">
      <header className="app-header">
        <h1>📈 Day Trading Bot</h1>
        <p>AI-Powered Trading Signals & Performance Analytics</p>
      </header>

      <nav className="app-nav">
        <button 
          className={`nav-button ${activeTab === 'signals' ? 'active' : ''}`}
          onClick={() => setActiveTab('signals')}
        >
          Signals
        </button>
        <button 
          className={`nav-button ${activeTab === 'trades' ? 'active' : ''}`}
          onClick={() => setActiveTab('trades')}
        >
          Trades
        </button>
        <button 
          className={`nav-button ${activeTab === 'analytics' ? 'active' : ''}`}
          onClick={() => setActiveTab('analytics')}
        >
          Analytics
        </button>
      </nav>

      <main className="app-content">
        {activeTab === 'signals' && <SignalsPanel />}
        {activeTab === 'trades' && <TradesPanel />}
        {activeTab === 'analytics' && <AnalyticsPanel />}
      </main>
    </div>
  );
}

export default App;
