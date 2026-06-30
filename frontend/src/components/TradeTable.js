import React from 'react';
import { tradesAPI } from '../api/client';

const TradeTable = ({ trades, onClose }) => {
  const handleCloseTrade = async (tradeId) => {
    const exitPrice = prompt('Enter exit price:');
    if (exitPrice) {
      try {
        await tradesAPI.close(tradeId, parseFloat(exitPrice));
        onClose();
        alert('Trade closed successfully');
      } catch (err) {
        alert('Failed to close trade: ' + err.message);
      }
    }
  };

  return (
    <div className="trade-table-container overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
          <tr className="bg-gray-200">
            <th className="border p-2 text-left">Symbol</th>
            <th className="border p-2 text-left">Type</th>
            <th className="border p-2 text-right">Entry</th>
            <th className="border p-2 text-right">Exit</th>
            <th className="border p-2 text-right">Qty</th>
            <th className="border p-2 text-right">P&L</th>
            <th className="border p-2 text-center">Status</th>
            <th className="border p-2 text-center">Action</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((trade) => (
            <tr key={trade.id} className="hover:bg-gray-50">
              <td className="border p-2 font-bold">{trade.symbol}</td>
              <td className={`border p-2 ${trade.type === 'BUY' ? 'text-green-600' : 'text-red-600'}`}>
                {trade.type}
              </td>
              <td className="border p-2 text-right">${trade.entry_price.toFixed(2)}</td>
              <td className="border p-2 text-right">
                {trade.exit_price ? `$${trade.exit_price.toFixed(2)}` : '-'}
              </td>
              <td className="border p-2 text-right">{trade.quantity}</td>
              <td className={`border p-2 text-right font-semibold ${
                trade.profit_loss > 0 ? 'text-green-600' : trade.profit_loss < 0 ? 'text-red-600' : ''
              }`}>
                {trade.profit_loss ? `$${trade.profit_loss.toFixed(2)}` : '-'}
              </td>
              <td className="border p-2 text-center">
                <span className={`px-2 py-1 rounded text-xs font-semibold ${
                  trade.status === 'OPEN' ? 'bg-blue-100 text-blue-800' : 'bg-green-100 text-green-800'
                }`}>
                  {trade.status}
                </span>
              </td>
              <td className="border p-2 text-center">
                {trade.status === 'OPEN' && (
                  <button
                    className="btn btn-sm btn-warning"
                    onClick={() => handleCloseTrade(trade.id)}
                  >
                    Close
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default TradeTable;
