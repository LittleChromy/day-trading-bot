import axios from 'axios';

// '/api' is relative to wherever the page was loaded from, so a shared link just works.
// (nginx proxies it in Docker; the "proxy" entry in package.json does it for `npm start`.)
const API_BASE_URL = process.env.REACT_APP_API_URL || '/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
});

// ---- login session ----
const TOKEN_KEY = 'dtb_session';
const readToken = () => {
  try {
    return window.localStorage.getItem(TOKEN_KEY) || '';
  } catch (e) {
    return '';
  }
};
let sessionToken = readToken();
let onLoggedOut = null;

export const getSessionToken = () => sessionToken;

export const setSessionToken = (token) => {
  sessionToken = token || '';
  try {
    if (sessionToken) window.localStorage.setItem(TOKEN_KEY, sessionToken);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch (e) {
    /* storage unavailable: keep it in memory for this visit */
  }
};

// App registers a callback so an expired session sends the user back to the login page
export const setLoggedOutHandler = (fn) => {
  onLoggedOut = fn;
};

api.interceptors.request.use((config) => {
  if (sessionToken) config.headers.Authorization = `Bearer ${sessionToken}`;
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401 && error.response.data?.code === 'login_required' && sessionToken) {
      setSessionToken('');
      if (onLoggedOut) onLoggedOut();
    }
    return Promise.reject(error);
  }
);

export const authAPI = {
  config: () => api.get('/auth/config'),
  login: (username, password) => api.post('/auth/login', { username, password }),
  register: (username, password) => api.post('/auth/register', { username, password }),
  me: () => api.get('/auth/me'),
  changePassword: (currentPassword, newPassword) =>
    api.put('/auth/password', { current_password: currentPassword, new_password: newPassword }),
};

export const accountAPI = {
  settings: () => api.get('/account/settings'),
  update: (body) => api.put('/account/settings', body),
  reset: () => api.post('/account/reset', { confirm: 'RESET' }),
};

export const adminAPI = {
  users: () => api.get('/admin/users'),
  createUser: (username, password, role = 'user') => api.post('/admin/users', { username, password, role }),
  updateUser: (id, body) => api.put(`/admin/users/${id}`, body),
  deleteUser: (id) => api.delete(`/admin/users/${id}`),
  setSignup: (allowed) => api.put('/admin/signup', { allowed }),
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
  events: (limit = 50, all = false) => api.get('/bot/events', { params: { limit, ...(all ? { all: 1 } : {}) } }),
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
