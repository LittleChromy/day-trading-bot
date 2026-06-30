import React, { useState, useEffect } from 'react';
import { analyticsAPI } from '../api/client';
import { Line, Bar } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend
);

const AnalyticsPanel = () => {
  const [performance, setPerformance] = useState(null);
  const [bySymbol, setBySymbol] = useState([]);
  const [accuracy, setAccuracy] = useState(null);
  const [days, setDays] = useState(7);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchAnalytics();
  }, [days]);

  const fetchAnalytics = async () => {
    setLoading(true);
    try {
      const [perfRes, symbolRes, accRes] = await Promise.all([
        analyticsAPI.getPerformance(days),
        analyticsAPI.getPerformanceBySymbol(),
        analyticsAPI.getSignalAccuracy(),
      ]);
      
      setPerformance(perfRes.data.metrics);
      setBySymbol(symbolRes.data.by_symbol);
      setAccuracy(accRes.data.accuracy_metrics);
    } catch (err) {
      console.error('Failed to fetch analytics:', err);
    } finally {
      setLoading(false);
    }
  };

  if (loading || !performance) {
    return <div className="loading">Loading analytics...</div>;
  }

  const symbolChartData = {
    labels: bySymbol.map(s => s.symbol),
    datasets: [
      {
        label: 'Profit/Loss ($)',
        data: bySymbol.map(s => s.total_pnl),
        backgroundColor: bySymbol.map(s => s.total_pnl >= 0 ? '#10b981' : '#ef4444'),
      },
    ],
  };

  return (
    <div className="analytics-panel">
      <div className="panel-header">
        <h2>Performance Analytics</h2>
        <select 
          value={days} 
          onChange={(e) => setDays(parseInt(e.target.value))}
          className="select"
        >
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
        </select>
      </div>

      <div className="metrics-grid">
        <MetricCard 
          label="Total Trades" 
          value={performance.total_trades} 
        />
        <MetricCard 
          label="Win Rate" 
          value={`${performance.win_rate.toFixed(1)}%`}
          color={performance.win_rate >= 50 ? 'green' : 'red'}
        />
        <MetricCard 
          label="Total P&L" 
          value={`$${performance.total_profit_loss.toFixed(2)}`}
          color={performance.total_profit_loss >= 0 ? 'green' : 'red'}
        />
        <MetricCard 
          label="Avg Profit" 
          value={`$${performance.avg_profit.toFixed(2)}`}
        />
        <MetricCard 
          label="Avg Loss" 
          value={`$${performance.avg_loss.toFixed(2)}`}
        />
        {accuracy && (
          <MetricCard 
            label="Signal Accuracy" 
            value={`${accuracy.accuracy_rate.toFixed(1)}%`}
            color={accuracy.accuracy_rate >= 60 ? 'green' : 'yellow'}
          />
        )}
      </div>

      {bySymbol.length > 0 && (
        <div className="chart-container">
          <h3>P&L by Symbol</h3>
          <Bar data={symbolChartData} />
        </div>
      )}
    </div>
  );
};

const MetricCard = ({ label, value, color = 'blue' }) => {
  const colorClass = {
    green: 'text-green-600',
    red: 'text-red-600',
    yellow: 'text-yellow-600',
    blue: 'text-blue-600',
  }[color];

  return (
    <div className="metric-card border rounded-lg p-4 bg-white shadow">
      <p className="text-gray-600 text-sm">{label}</p>
      <p className={`text-2xl font-bold ${colorClass}`}>{value}</p>
    </div>
  );
};

export default AnalyticsPanel;
