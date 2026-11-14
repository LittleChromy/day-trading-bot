import axios from 'axios';

// '/api' is relative to wherever the page was loaded from, so a shared link just works.
// (nginx proxies it in Docker; the "proxy" entry in package.json does it for `npm start`.)
const API_BASE_URL = process.env.REACT_APP_API_URL || '/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
});

// ---- admin password (unlocks the controls on a shared dashboard) ----
const TOKEN_KEY = 'dtb_admin_token';
const readToken = () => {
  try {
    return window.localStorage.getItem(TOKEN_KEY) || '';
  } catch (e) {
    return '';
  }
};
let adminToken = readToken();

export const setAdminToken = (token) => {
  adminToken = token || '';
  try {
    if (adminToken) window.localStorage.setItem(TOKEN_KEY, adminToken);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch (e) {
    /* storage unavailable: keep it in memory for this visit */
  }
};

api.interceptors.request.use((config) => {
  if (adminToken) config.headers['X-Admin-Token'] = adminToken;
  return config;
});

export const authAPI = {
  status: () => api.get('/auth/status'),
  unlock: (password) => api.post('/auth/unlock', { password }),
};

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
