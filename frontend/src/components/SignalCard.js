import React from 'react';

const SignalCard = ({ signal }) => {
  const getSignalColor = (type) => {
    return type === 'BUY' ? 'text-green-600' : 'text-red-600';
  };

  const getConfidenceColor = (confidence) => {
    if (confidence >= 0.7) return 'bg-green-100 text-green-800';
    if (confidence >= 0.5) return 'bg-yellow-100 text-yellow-800';
    return 'bg-red-100 text-red-800';
  };

  return (
    <div className="signal-card border rounded-lg p-4 shadow-md hover:shadow-lg transition">
      <div className="flex justify-between items-start mb-3">
        <div>
          <h3 className="text-lg font-bold">{signal.symbol}</h3>
          <p className="text-sm text-gray-500">{new Date(signal.timestamp).toLocaleString()}</p>
        </div>
        <span className={`text-2xl font-bold ${getSignalColor(signal.signal)}`}>
          {signal.signal}
        </span>
      </div>

      <div className="mb-3">
        <p className="text-sm text-gray-600">Price: ${signal.price.toFixed(2)}</p>
        <div className="mt-2">
          <span className={`inline-block px-3 py-1 rounded-full text-sm font-semibold ${getConfidenceColor(signal.confidence)}`}>
            Confidence: {(signal.confidence * 100).toFixed(1)}%
          </span>
        </div>
      </div>

      <div className="strategies text-xs">
        <p className="font-semibold mb-1">Strategies:</p>
        <ul className="text-gray-600">
          {Object.keys(signal.strategies).map((strategy) => (
            <li key={strategy}>• {strategy}: {signal.strategies[strategy].signal || 'N/A'}</li>
          ))}
        </ul>
      </div>

      {!signal.acted_upon && (
        <button className="mt-3 btn btn-sm btn-success w-full">Execute Trade</button>
      )}
      {signal.acted_upon && (
        <p className="mt-3 text-sm text-green-600 text-center">✓ Trade Executed</p>
      )}
    </div>
  );
};

export default SignalCard;
