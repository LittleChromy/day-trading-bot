import React from 'react';
import { tradesAPI, errorMessage } from '../api/client';
import { useAccess } from '../access';

const money = (v) => (v == null ? '—' : `${v < 0 ? '-' : ''}$${Math.abs(v).toFixed(2)}`);
const pnlClass = (v) => (v > 0 ? 'text-green' : v < 0 ? 'text-red' : '');

const TradeTable = ({ trades, onChange }) => {
  const { canControl } = useAccess();
  const handleClose = async (trade) => {
    const managed = trade.execution_mode === 'simulated' || trade.execution_mode === 'alpaca';
    const hint = managed ? ' (leave blank to close at the market price)' : '';
    const input = window.prompt(`Exit price for ${trade.symbol}${hint}:`, '');
    if (input === null) return;
    const price = input.trim() === '' ? null : parseFloat(input);
    if (price !== null && (!Number.isFinite(price) || price <= 0)) {
      window.alert('Enter a positive number');
      return;
    }
    try {
      await tradesAPI.close(trade.id, price);
      onChange();
    } catch (err) {
      window.alert(`Failed to close trade: ${errorMessage(err)}`);
    }
  };

  const handleCancel = async (trade) => {
    if (!window.confirm(`Cancel trade #${trade.id} (${trade.symbol})? It will be excluded from stats.`)) return;
    try {
      await tradesAPI.cancel(trade.id);
      onChange();
    } catch (err) {
      window.alert(`Failed to cancel trade: ${errorMessage(err)}`);
    }
  };

  if (!trades.length) return <div className="no-signals">No trades</div>;

  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Side</th>
            <th className="num">Qty</th>
            <th className="num">Entry</th>
            <th className="num">Stop / Target</th>
            <th className="num">Exit / Last</th>
            <th className="num">P&amp;L</th>
            <th>Status</th>
            <th>Source</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => {
            const pnl = t.status === 'OPEN' ? t.unrealized_pnl : t.profit_loss;
            const exitOrLast = t.status === 'OPEN' ? t.current_price : t.exit_price;
            return (
              <tr key={t.id}>
                <td className="bold">{t.symbol}</td>
                <td className={t.type === 'BUY' ? 'text-green' : 'text-red'}>
                  {t.type === 'BUY' ? 'LONG' : 'SHORT'}
                </td>
                <td className="num">{t.quantity}</td>
                <td className="num">{money(t.entry_price)}</td>
                <td className="num muted">
                  {t.stop_loss ? `${money(t.stop_loss)} / ${money(t.take_profit)}` : '—'}
                </td>
                <td className="num">{money(exitOrLast)}</td>
                <td className={`num bold ${pnlClass(pnl)}`}>
                  {money(pnl)}
                  {t.status === 'OPEN' && pnl != null && <span className="muted small"> unrl.</span>}
                </td>
                <td>
                  <span className={`pill ${t.status === 'OPEN' ? 'pill-blue' : t.status === 'CLOSED' ? 'pill-green' : 'pill-gray'}`}>
                    {t.status}
                  </span>
                  {t.exit_reason && <div className="muted small">{t.exit_reason.replace(/_/g, ' ').toLowerCase()}</div>}
                </td>
                <td className="muted small">
                  {t.source || 'MANUAL'}
                  {t.execution_mode ? ` · ${t.execution_mode}` : ''}
                </td>
                <td>
                  {t.status === 'OPEN' && canControl && (
                    <div className="actions">
                      <button className="btn btn-sm btn-warning" onClick={() => handleClose(t)}>Close</button>
                      {t.execution_mode !== 'alpaca' && (
                        <button className="btn btn-sm btn-secondary" onClick={() => handleCancel(t)}>Cancel</button>
                      )}
                    </div>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

export default TradeTable;
