import React, { useState, useEffect, useCallback } from 'react';
import { signalsAPI, errorMessage } from '../api/client';
import SignalCard from './SignalCard';

const SignalsPanel = () => {
  const [signals, setSignals] = useState([]);
  const [hours, setHours] = useState(24);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);

  const fetchSignals = useCallback(async () => {
    try {
      const response = await signalsAPI.getRecent(hours);
      setSignals(response.data.signals);
      setError(null);
    } catch (err) {
      setError(`Failed to fetch signals: ${errorMessage(err)}`);
    }
  }, [hours]);

  useEffect(() => {
    fetchSignals();
    const interval = setInterval(fetchSignals, 60000);
    return () => clearInterval(interval);
  }, [fetchSignals]);

  const generateNewSignals = async () => {
    setLoading(true);
    setNotice(null);
    try {
      const response = await signalsAPI.generate();
      const { count, scanned = 0, no_data: noData = [] } = response.data;
      if (scanned > 0 && noData.length === scanned) {
        setError('Alpaca returned no market data for any stock. Check your API keys in .env and the backend log.');
        return;
      }
      setNotice(
        (count ? `${count} new signal(s) generated` : 'No new signals met the confidence threshold') +
          ` (${scanned - noData.length} of ${scanned} stocks analyzed)`
      );
      await fetchSignals();
      setError(null);
    } catch (err) {
      setError(`Failed to generate signals: ${errorMessage(err)}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="signals-panel">
      <div className="panel-header">
        <h2>Trading Signals</h2>
        <div className="row-gap">
          <select className="select" value={hours} onChange={(e) => setHours(parseInt(e.target.value, 10))}>
            <option value={1}>Last hour</option>
            <option value={24}>Last 24 hours</option>
            <option value={168}>Last 7 days</option>
          </select>
          <button onClick={generateNewSignals} disabled={loading} className="btn btn-primary">
            {loading ? 'Scanning…' : 'Scan Now'}
          </button>
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}
      {notice && <div className="info-message">{notice}</div>}

      <div className="signals-grid">
        {signals.length > 0 ? (
          signals.map((signal) => (
            <SignalCard key={signal.id} signal={signal} onExecuted={fetchSignals} />
          ))
        ) : (
          <div className="no-signals">No signals in this window</div>
        )}
      </div>
    </div>
  );
};

export default SignalsPanel;
