import React, { useState, useEffect, useCallback } from 'react';
import { tradesAPI, errorMessage } from '../api/client';
import TradeTable from './TradeTable';

const EMPTY_FORM = { symbol: '', trade_type: 'BUY', entry_price: '', quantity: '', stop_loss: '', take_profit: '' };

const TradesPanel = () => {
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState('OPEN');
  const [error, setError] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);

  const fetchTrades = useCallback(async () => {
    setLoading(true);
    try {
      const response = await tradesAPI.getAll(filter === 'ALL' ? null : filter, null, 100);
      setTrades(response.data.trades);
      setError(null);
    } catch (err) {
      setError(`Failed to fetch trades: ${errorMessage(err)}`);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    fetchTrades();
    if (filter !== 'OPEN') return undefined;
    const interval = setInterval(fetchTrades, 30000);
    return () => clearInterval(interval);
  }, [fetchTrades, filter]);

  const submit = async (e) => {
    e.preventDefault();
    try {
      await tradesAPI.create({
        ...form,
        entry_price: parseFloat(form.entry_price),
        quantity: parseInt(form.quantity, 10),
        stop_loss: form.stop_loss ? parseFloat(form.stop_loss) : null,
        take_profit: form.take_profit ? parseFloat(form.take_profit) : null,
      });
      setForm(EMPTY_FORM);
      setShowForm(false);
      fetchTrades();
    } catch (err) {
      setError(`Failed to record trade: ${errorMessage(err)}`);
    }
  };

  const field = (name, label, type = 'text', extra = {}) => (
    <label className="form-field">
      <span>{label}</span>
      <input
        className="input"
        type={type}
        value={form[name]}
        onChange={(e) => setForm({ ...form, [name]: e.target.value })}
        {...extra}
      />
    </label>
  );

  return (
    <div className="trades-panel">
      <div className="panel-header">
        <h2>Trades</h2>
        <div className="row-gap wrap">
          {['OPEN', 'CLOSED', 'CANCELLED', 'ALL'].map((status) => (
            <button
              key={status}
              className={`btn ${filter === status ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setFilter(status)}
            >
              {status}
            </button>
          ))}
          <button className="btn btn-success" onClick={() => setShowForm((v) => !v)}>
            {showForm ? 'Hide form' : '+ Log trade'}
          </button>
        </div>
      </div>

      {showForm && (
        <form className="card form-grid" onSubmit={submit}>
          {field('symbol', 'Symbol', 'text', { required: true, maxLength: 10 })}
          <label className="form-field">
            <span>Side</span>
            <select className="input" value={form.trade_type}
                    onChange={(e) => setForm({ ...form, trade_type: e.target.value })}>
              <option value="BUY">Long (BUY)</option>
              <option value="SELL">Short (SELL)</option>
            </select>
          </label>
          {field('entry_price', 'Entry price', 'number', { required: true, step: '0.01', min: '0.01' })}
          {field('quantity', 'Quantity', 'number', { required: true, step: '1', min: '1' })}
          {field('stop_loss', 'Stop loss (optional)', 'number', { step: '0.01' })}
          {field('take_profit', 'Take profit (optional)', 'number', { step: '0.01' })}
          <div className="form-actions">
            <button type="submit" className="btn btn-primary">Save trade</button>
            <span className="muted small">Records a trade you placed elsewhere. No order is sent.</span>
          </div>
        </form>
      )}

      {error && <div className="error-message">{error}</div>}

      {loading && !trades.length ? (
        <div className="loading">Loading trades…</div>
      ) : (
        <TradeTable trades={trades} onChange={fetchTrades} />
      )}
    </div>
  );
};

export default TradesPanel;
