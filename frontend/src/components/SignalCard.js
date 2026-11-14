import React, { useState } from 'react';
import { signalsAPI, errorMessage } from '../api/client';
import { useAccess } from '../access';

const fmtPct = (v) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`);

const SignalCard = ({ signal, onExecuted }) => {
  const { canControl } = useAccess();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const confidenceClass =
    signal.confidence >= 0.7 ? 'pill-green' : signal.confidence >= 0.5 ? 'pill-yellow' : 'pill-red';

  const execute = async () => {
    const input = window.prompt(
      `Open a ${signal.signal} trade in ${signal.symbol}.\n` +
        'Enter a share quantity, or leave blank to size it from your risk settings:',
      ''
    );
    if (input === null) return;
    const qty = input.trim() === '' ? null : parseInt(input, 10);
    if (qty !== null && (!Number.isInteger(qty) || qty <= 0)) {
      setError('Quantity must be a positive whole number');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await signalsAPI.execute(signal.id, qty);
      onExecuted && onExecuted();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const strategies = signal.strategies || {};

  return (
    <div className="signal-card">
      <div className="row-between">
        <div>
          <h3 className="card-title">{signal.symbol}</h3>
          <p className="muted small">{new Date(signal.timestamp + 'Z').toLocaleString()}</p>
        </div>
        <span className={`signal-type ${signal.signal === 'BUY' ? 'text-green' : 'text-red'}`}>
          {signal.signal}
        </span>
      </div>

      <p className="muted">Price: ${Number(signal.price).toFixed(2)}</p>
      <div className="pill-row">
        <span className={`pill ${confidenceClass}`}>Confidence {fmtPct(signal.confidence)}</span>
        {signal.base_confidence != null && signal.base_confidence !== signal.confidence && (
          <span className="pill pill-gray" title="Before ML adjustment">
            Strategies {fmtPct(signal.base_confidence)}
          </span>
        )}
      </div>

      <ul className="strategy-list">
        {Object.entries(strategies).map(([name, info]) => (
          <li key={name}>
            <span>{name.replace(/_/g, ' ')}</span>
            <span className={info.signal === 'BUY' ? 'text-green' : 'text-red'}>{info.signal}</span>
          </li>
        ))}
      </ul>

      {error && <p className="error-inline">{error}</p>}

      {signal.acted_upon ? (
        <p className="text-green center small">✓ Trade #{signal.trade_id} opened</p>
      ) : canControl ? (
        <button className="btn btn-success full" onClick={execute} disabled={busy}>
          {busy ? 'Placing…' : 'Execute Trade'}
        </button>
      ) : (
        <p className="muted center small">Not traded</p>
      )}
    </div>
  );
};

export default SignalCard;
