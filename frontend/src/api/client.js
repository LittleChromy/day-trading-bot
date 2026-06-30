import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Signals API
export const signalsAPI = {
  generate: (symbols) => api.post('/signals/generate', { symbols }),
  getRecent: (hours = 24) => api.get(`/signals/recent?hours=${hours}`),
  getBySymbol: (symbol) => api.get(`/signals/by-symbol/${symbol}`),
};

// Trades API
export const tradesAPI = {
  create: (tradeData) => api.post('/trades/create', tradeData),
  close: (tradeId, exitPrice) => api.put(`/trades/close/${tradeId}`, { exit_price: exitPrice }),
  getAll: (status = null, symbol = null, limit = 50) => {
    let url = '/trades/all?limit=' + limit;
    if (status) url += '&status=' + status;
    if (symbol) url += '&symbol=' + symbol;
    return api.get(url);
  },
  getOne: (tradeId) => api.get(`/trades/${tradeId}`),
};

// Analytics API
export const analyticsAPI = {
  getPerformance: (days = 7) => api.get(`/analytics/performance?days=${days}`),
  getPerformanceBySymbol: () => api.get('/analytics/by-symbol'),
  getSignalAccuracy: () => api.get('/analytics/signal-accuracy'),
};

// Health API
export const healthAPI = {
  checkStatus: () => api.get('/health/status'),
};

export default api;
