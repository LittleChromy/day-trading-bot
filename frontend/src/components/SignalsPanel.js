import React, { useState, useEffect } from 'react';
import { signalsAPI } from '../api/client';
import SignalCard from './SignalCard';

const SignalsPanel = () => {
  const [signals, setSignals] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchSignals();
    const interval = setInterval(fetchSignals, 60000); // Refresh every minute
    return () => clearInterval(interval);
  }, []);

  const fetchSignals = async () => {
    setLoading(true);
    try {
      const response = await signalsAPI.getRecent(24);
      setSignals(response.data.signals);
      setError(null);
    } catch (err) {
      setError('Failed to fetch signals');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const generateNewSignals = async () => {
    setLoading(true);
    try {
      const response = await signalsAPI.generate();
      setSignals(response.data.signals);
      setError(null);
    } catch (err) {
      setError('Failed to generate signals');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="signals-panel">
      <div className="panel-header">
        <h2>Trading Signals</h2>
        <button 
          onClick={generateNewSignals} 
          disabled={loading}
          className="btn btn-primary"
        >
          {loading ? 'Loading...' : 'Generate Signals'}
        </button>
      </div>

      {error && <div className="error-message">{error}</div>}

      <div className="signals-grid">
        {signals.length > 0 ? (
          signals.map((signal) => (
            <SignalCard key={signal.id} signal={signal} />
          ))
        ) : (
          <div className="no-signals">No signals available</div>
        )}
      </div>
    </div>
  );
};

export default SignalsPanel;
