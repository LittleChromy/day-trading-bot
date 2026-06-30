import React, { useState, useEffect } from 'react';
import { tradesAPI } from '../api/client';
import TradeTable from './TradeTable';

const TradesPanel = () => {
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState('OPEN');
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchTrades();
  }, [filter]);

  const fetchTrades = async () => {
    setLoading(true);
    try {
      const response = await tradesAPI.getAll(filter, null, 50);
      setTrades(response.data.trades);
      setError(null);
    } catch (err) {
      setError('Failed to fetch trades');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="trades-panel">
      <div className="panel-header">
        <h2>Trade History</h2>
        <div className="filter-buttons">
          {['OPEN', 'CLOSED', 'CANCELLED'].map((status) => (
            <button
              key={status}
              className={`btn ${filter === status ? 'btn-active' : 'btn-secondary'}`}
              onClick={() => setFilter(status)}
            >
              {status}
            </button>
          ))}
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}

      {loading ? (
        <div className="loading">Loading trades...</div>
      ) : (
        <TradeTable trades={trades} onClose={fetchTrades} />
      )}
    </div>
  );
};

export default TradesPanel;
