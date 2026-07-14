import axios from 'axios';

const BASE = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api/dealer-parts`
  : '/api/dealer-parts';

const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });

export const dpApi = {
  dashboard: () => axios.get(`${BASE}/dashboard`, auth()).then((r) => r.data),
  getSettings: () => axios.get(`${BASE}/settings`, auth()).then((r) => r.data),
  saveSettings: (data) => axios.put(`${BASE}/settings`, data, auth()).then((r) => r.data),

  listDealers: (params = {}) => axios.get(`${BASE}/dealers`, { ...auth(), params }).then((r) => r.data),
  createDealer: (data) => axios.post(`${BASE}/dealers`, data, auth()).then((r) => r.data),
  getDealer: (id) => axios.get(`${BASE}/dealers/${id}`, auth()).then((r) => r.data),
  updateDealer: (id, data) => axios.patch(`${BASE}/dealers/${id}`, data, auth()).then((r) => r.data),

  listOrders: (params = {}) => axios.get(`${BASE}/orders`, { ...auth(), params }).then((r) => r.data),
  createOrder: (data) => axios.post(`${BASE}/orders`, data, auth()).then((r) => r.data),

  listAllocations: (params = {}) => axios.get(`${BASE}/allocations`, { ...auth(), params }).then((r) => r.data),
  createAllocation: (data) => axios.post(`${BASE}/allocations`, data, auth()).then((r) => r.data),
  updateAllocation: (id, data) => axios.patch(`${BASE}/allocations/${id}`, data, auth()).then((r) => r.data),
  submitAllocation: (id) => axios.post(`${BASE}/allocations/${id}/submit`, {}, auth()).then((r) => r.data),
  approveAllocation: (id, data = {}) => axios.post(`${BASE}/allocations/${id}/approve`, data, auth()).then((r) => r.data),
  dispatchAllocation: (id, data = {}) => axios.post(`${BASE}/allocations/${id}/dispatch`, data, auth()).then((r) => r.data),
  receiveAllocation: (id, data = {}) => axios.post(`${BASE}/allocations/${id}/receive`, data, auth()).then((r) => r.data),

  listStores: (params = {}) => axios.get(`${BASE}/stores`, { ...auth(), params }).then((r) => r.data),
  createStore: (data) => axios.post(`${BASE}/stores`, data, auth()).then((r) => r.data),
  storeStock: (id) => axios.get(`${BASE}/stores/${id}/stock`, auth()).then((r) => r.data),

  listMovements: (params = {}) => axios.get(`${BASE}/movements`, { ...auth(), params }).then((r) => r.data),
};
