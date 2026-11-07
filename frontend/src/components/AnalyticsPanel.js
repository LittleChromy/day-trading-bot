import React, { useState, useEffect, useCallback } from 'react';
import { analyticsAPI, errorMessage } from '../api/client';
import { Line, Bar } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Filler,
  Title,
  Tooltip,
  Legend,
} from 'chart.js';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, BarElement, Filler, Title, Tooltip, Legend);

const money = (v) => `${v < 0 ? '-' : ''}$${Math.abs(v || 0).toFixed(2)}`;

const AnalyticsPanel = () => {
  const [performance, setPerformance] = useState(null);
  const [bySymbol, setBySymbol] = useState([]);
  const [accuracy, setAccuracy] = useState(null);
  const [strategies, setStrategies] = useState([]);
  const [curve, setCurve] = useState([]);
  const [days, setDays] = useState(7);
  const [error, setError] = useState(null);

  const fetchAnalytics = useCallback(async () => {
    try {
      const [perfRes, symbolRes, accRes, stratRes, curveRes] = await Promise.all([
        analyticsAPI.getPerformance(days),
        analyticsAPI.getPerformanceBySymbol(),
        analyticsAPI.getSignalAccuracy(),
        analyticsAPI.getStrategies(),
        analyticsAPI.getEquityCurve(days),
      ]);
      setPerformance(perfRes.data.metrics);
      setBySymbol(symbolRes.data.by_symbol);
      setAccuracy(accRes.data.accuracy_metrics);
      setStrategies(stratRes.data.strategies);
      setCurve(curveRes.data.points);
      setError(null);
    } catch (err) {
      setError(`Failed to fetch analytics: ${errorMessage(err)}`);
    }
  }, [days]);

  useEffect(() => {
    fetchAnalytics();
  }, [fetchAnalytics]);

  if (error) return <div className="error-message">{error}</div>;
  if (!performance) return <div className="loading">Loading analytics…</div>;

  const symbolChartData = {
    labels: bySymbol.map((s) => s.symbol),
    datasets: [{
      label: 'Profit/Loss ($)',
      data: bySymbol.map((s) => s.total_pnl),
      backgroundColor: bySymbol.map((s) => (s.total_pnl >= 0 ? '#10b981' : '#ef4444')),
      maxBarThickness: 60,
    }],
  };

  const curveData = {
    labels: curve.map((p) => new Date(p.time + 'Z').toLocaleDateString()),
    datasets: [{
      label: 'Cumulative P&L ($)',
      data: curve.map((p) => p.cumulative_pnl),
      borderColor: '#667eea',
      backgroundColor: 'rgba(102,126,234,0.1)',
      fill: true,
      pointRadius: 2,
    }],
  };

  return (
    <div className="analytics-panel">
      <div className="panel-header">
        <h2>Performance Analytics</h2>
        <select value={days} onChange={(e) => setDays(parseInt(e.target.value, 10))} className="select">
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
          <option value={365}>Last year</option>
        </select>
      </div>

      <div className="metrics-grid">
        <MetricCard label="Closed Trades" value={performance.total_trades} />
        <MetricCard label="Win Rate" value={`${performance.win_rate.toFixed(1)}%`}
                    cls={performance.total_trades ? (performance.win_rate >= 50 ? 'text-green' : 'text-red') : ''} />
        <MetricCard label="Total P&L" value={money(performance.total_profit_loss)}
                    cls={performance.total_profit_loss >= 0 ? 'text-green' : 'text-red'} />
        <MetricCard label="Avg Win" value={money(performance.avg_profit)} />
        <MetricCard label="Avg Loss" value={money(performance.avg_loss)} />
        {accuracy && (
          <MetricCard label="Signal Accuracy"
                      value={accuracy.total_signals ? `${accuracy.accuracy_rate.toFixed(1)}%` : '—'}
                      sub={`${accuracy.total_signals} closed of ${accuracy.total_generated ?? '?'} signals`} />
        )}
      </div>

      {curve.length > 0 && (
        <div className="chart-container">
          <h3>Cumulative P&amp;L</h3>
          <div className="chart-box"><Line data={curveData} options={{ maintainAspectRatio: false, plugins: { legend: { display: false } } }} /></div>
        </div>
      )}

      {bySymbol.length > 0 && (
        <div className="chart-container">
          <h3>P&amp;L by Symbol (all time)</h3>
          <div className="chart-box"><Bar data={symbolChartData} options={{ maintainAspectRatio: false, plugins: { legend: { display: false } } }} /></div>
        </div>
      )}

      {strategies.length > 0 && (
        <div className="card">
          <h3>Strategy scorecard</h3>
          <p className="muted small">How often each indicator was right when it agreed with a traded signal.</p>
          <table className="data-table compact">
            <thead><tr><th>Strategy</th><th className="num">Trades</th><th className="num">Win rate</th><th className="num">Net P&amp;L</th></tr></thead>
            <tbody>
              {strategies.map((s) => (
                <tr key={s.strategy}>
                  <td>{s.strategy.replace(/_/g, ' ')}</td>
                  <td className="num">{s.total_signals}</td>
                  <td className={`num ${s.win_rate >= 50 ? 'text-green' : 'text-red'}`}>{s.win_rate.toFixed(1)}%</td>
                  <td className={`num ${s.net_pnl >= 0 ? 'text-green' : 'text-red'}`}>{money(s.net_pnl)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

const MetricCard = ({ label, value, sub, cls = '' }) => (
  <div className="metric-card">
    <p className="metric-label">{label}</p>
    <p className={`metric-value ${cls}`}>{value}</p>
    {sub && <p className="muted small">{sub}</p>}
  </div>
);

export default AnalyticsPanel;
