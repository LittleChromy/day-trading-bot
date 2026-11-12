import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
});

// Pull the backend's error message out of an axios error
export const errorMessage = (err) =>
  err?.response?.data?.message || err?.message || 'Request failed';

export const signalsAPI = {
  generate: (symbols) => api.post('/signals/generate', symbols ? { symbols } : {}),
  getRecent: (hours = 24) => api.get('/signals/recent', { params: { hours } }),
  getBySymbol: (symbol) => api.get(`/signals/by-symbol/${symbol}`),
  execute: (signalId, quantity) =>
    api.post(`/signals/${signalId}/execute`, quantity ? { quantity } : {}),
};

export const tradesAPI = {
  create: (tradeData) => api.post('/trades/create', tradeData),
  close: (tradeId, exitPrice) =>
    api.put(`/trades/close/${tradeId}`, exitPrice != null ? { exit_price: exitPrice } : {}),
  cancel: (tradeId) => api.put(`/trades/cancel/${tradeId}`),
  getAll: (status = null, symbol = null, limit = 50) =>
    api.get('/trades/all', {
      params: { limit, ...(status ? { status } : {}), ...(symbol ? { symbol } : {}) },
    }),
  getOne: (tradeId) => api.get(`/trades/${tradeId}`),
};

export const analyticsAPI = {
  getPerformance: (days = 7) => api.get('/analytics/performance', { params: { days } }),
  getPerformanceBySymbol: () => api.get('/analytics/by-symbol'),
  getSignalAccuracy: () => api.get('/analytics/signal-accuracy'),
  getStrategies: () => api.get('/analytics/strategies'),
  getEquityCurve: (days = 30) => api.get('/analytics/equity-curve', { params: { days } }),
};

export const botAPI = {
  status: () => api.get('/bot/status'),
  account: () => api.get('/bot/account'),
  setAutoTrade: (enabled) => api.post('/bot/auto-trade', { enabled }),
  run: () => api.post('/bot/run'),
  flatten: () => api.post('/bot/flatten'),
  events: (limit = 50) => api.get('/bot/events', { params: { limit } }),
  retrain: () => api.post('/bot/retrain'),
  models: () => api.get('/bot/models'),
  universe: () => api.get('/bot/universe'),
  rescan: () => api.post('/bot/universe'),
  notifyTest: () => api.post('/bot/notify-test'),
};

export const backtestAPI = {
  run: (params) => api.post('/backtest/run', params),
};

export const healthAPI = {
  checkStatus: () => api.get('/health/status'),
};

export default api;
