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

  listBoms: (params = {}) => axios.get(`${BASE}/boms`, { ...auth(), params }).then((r) => r.data),
  createBom: (data) => axios.post(`${BASE}/boms`, data, auth()).then((r) => r.data),
  updateBom: (id, data) => axios.patch(`${BASE}/boms/${id}`, data, auth()).then((r) => r.data),

  listMostUsed: (params = {}) => axios.get(`${BASE}/most-used`, { ...auth(), params }).then((r) => r.data),
  upsertMostUsed: (data) => axios.post(`${BASE}/most-used`, data, auth()).then((r) => r.data),
  deleteMostUsed: (id) => axios.delete(`${BASE}/most-used/${id}`, auth()).then((r) => r.data),

  recommend: (data) => axios.post(`${BASE}/recommend`, data, auth()).then((r) => r.data),

  listUsage: (params = {}) => axios.get(`${BASE}/usage`, { ...auth(), params }).then((r) => r.data),
  logUsage: (data) => axios.post(`${BASE}/usage`, data, auth()).then((r) => r.data),

  storesDashboard: () => axios.get(`${BASE}/stores-dashboard`, auth()).then((r) => r.data),

  listRma: (params = {}) => axios.get(`${BASE}/rma`, { ...auth(), params }).then((r) => r.data),
  createRma: (data) => axios.post(`${BASE}/rma`, data, auth()).then((r) => r.data),
  updateRma: (id, data) => axios.patch(`${BASE}/rma/${id}`, data, auth()).then((r) => r.data),

  intelOverview: (params = {}) => axios.get(`${BASE}/intel/overview`, { ...auth(), params }).then((r) => r.data),
  intelFailures: (params = {}) => axios.get(`${BASE}/intel/failures`, { ...auth(), params }).then((r) => r.data),
  runMonitoring: () => axios.post(`${BASE}/monitoring/run`, {}, auth()).then((r) => r.data),
  listAlerts: (params = {}) => axios.get(`${BASE}/alerts`, { ...auth(), params }).then((r) => r.data),
  updateAlert: (id, data) => axios.patch(`${BASE}/alerts/${id}`, data, auth()).then((r) => r.data),
  replenishment: (params = {}) => axios.get(`${BASE}/replenishment`, { ...auth(), params }).then((r) => r.data),

  aiParseInvoice: (text) => axios.post(`${BASE}/ai/parse-invoice`, { text }, auth()).then((r) => r.data),
  aiDealerSummary: (dealer_id) => axios.post(`${BASE}/ai/dealer-summary`, { dealer_id }, auth()).then((r) => r.data),

  portalOverview: (dealerId) => axios.get(`${BASE}/portal/${dealerId}/overview`, auth()).then((r) => r.data),
  requestReplenishment: (dealerId, data) => axios.post(`${BASE}/portal/${dealerId}/request-replenishment`, data, auth()).then((r) => r.data),
  listReplenishmentRequests: (params = {}) => axios.get(`${BASE}/replenishment-requests`, { ...auth(), params }).then((r) => r.data),
  updateReplenishmentRequest: (id, data) => axios.patch(`${BASE}/replenishment-requests/${id}`, data, auth()).then((r) => r.data),

  downloadReport: async (report, dealer_id = '') => {
    const res = await axios.get(`${BASE}/reports/${report}.csv`, { ...auth(), params: dealer_id ? { dealer_id } : {}, responseType: 'blob' });
    const url = window.URL.createObjectURL(new Blob([res.data]));
    const a = document.createElement('a');
    a.href = url; a.download = `dealer_${report}.csv`;
    document.body.appendChild(a); a.click(); a.remove();
    window.URL.revokeObjectURL(url);
  },
};
