import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });

const base = `${API}/inventory`;

export const invApi = {
  meta: () => axios.get(`${base}/meta`, auth()).then((r) => r.data),
  fieldOwnership: () => axios.get(`${base}/field-ownership`, auth()).then((r) => r.data),
  dashboard: () => axios.get(`${base}/dashboard`, auth()).then((r) => r.data),

  settings: () => axios.get(`${base}/settings`, auth()).then((r) => r.data),
  saveSettings: (body) => axios.put(`${base}/settings`, body, auth()).then((r) => r.data),

  dealers: (q) => axios.get(`${base}/dealers`, { ...auth(), params: { q } }).then((r) => r.data),
  products: (q) => axios.get(`${base}/products`, { ...auth(), params: { q } }).then((r) => r.data),

  warehouses: () => axios.get(`${base}/warehouses`, auth()).then((r) => r.data),
  createWarehouse: (body) => axios.post(`${base}/warehouses`, body, auth()).then((r) => r.data),
  locations: (id) => axios.get(`${base}/warehouses/${id}/locations`, auth()).then((r) => r.data),
  createLocation: (id, body) => axios.post(`${base}/warehouses/${id}/locations`, body, auth()).then((r) => r.data),

  orders: (params) => axios.get(`${base}/orders`, { ...auth(), params }).then((r) => r.data),
  createOrder: (body) => axios.post(`${base}/orders`, body, auth()).then((r) => r.data),
  order: (id) => axios.get(`${base}/orders/${id}`, auth()).then((r) => r.data),
  setStatus: (id, body) => axios.post(`${base}/orders/${id}/status`, body, auth()).then((r) => r.data),
  validate: (id) => axios.post(`${base}/orders/${id}/validate`, {}, auth()).then((r) => r.data),
  reserve: (id) => axios.post(`${base}/orders/${id}/reserve`, {}, auth()).then((r) => r.data),
  units: (id) => axios.get(`${base}/orders/${id}/units`, auth()).then((r) => r.data),
  assignSerial: (unitId, body) => axios.post(`${base}/units/${unitId}/assign-serial`, body, auth()).then((r) => r.data),

  receiveStock: (body) => axios.post(`${base}/stock/receive`, body, auth()).then((r) => r.data),
  availability: (params) => axios.get(`${base}/stock/availability`, { ...auth(), params }).then((r) => r.data),
  checkSerial: (serial) => axios.get(`${base}/serials/check`, { ...auth(), params: { serial } }).then((r) => r.data),

  sageConnection: () => axios.get(`${base}/sage/connection`, auth()).then((r) => r.data),
  saveSageConnection: (body) => axios.post(`${base}/sage/connection`, body, auth()).then((r) => r.data),
  sageDiscover: () => axios.get(`${base}/sage/capabilities/discover`, auth()).then((r) => r.data),

  // Phase 2 — Sage order sync
  syncStatus: () => axios.get(`${base}/sage/sync/status`, auth()).then((r) => r.data),
  runSync: (body) => axios.post(`${base}/sage/sync/run`, body || {}, auth()).then((r) => r.data),
  syncRuns: () => axios.get(`${base}/sage/runs`, auth()).then((r) => r.data),
  sageOrders: (state) => axios.get(`${base}/sage/orders`, { ...auth(), params: { state } }).then((r) => r.data),
  sageExceptions: () => axios.get(`${base}/sage/exceptions`, auth()).then((r) => r.data),
  sageFieldMap: () => axios.get(`${base}/sage/field-map`, auth()).then((r) => r.data),
  mapDealer: (body) => axios.post(`${base}/sage/mappings/dealer`, body, auth()).then((r) => r.data),
  mapProduct: (body) => axios.post(`${base}/sage/mappings/product`, body, auth()).then((r) => r.data),
  retrySageOrder: (mirrorId) => axios.post(`${base}/sage/orders/${mirrorId}/retry`, {}, auth()).then((r) => r.data),

  // Phase 3 — warehouse ops
  release: (id) => axios.post(`${base}/ops/orders/${id}/release`, {}, auth()).then((r) => r.data),
  fulfilment: (id) => axios.get(`${base}/ops/orders/${id}/fulfilment`, auth()).then((r) => r.data),
  pick: (taskId, body) => axios.post(`${base}/ops/pick-tasks/${taskId}/pick`, body, auth()).then((r) => r.data),
  rack: (unitId, body) => axios.post(`${base}/ops/units/${unitId}/rack`, body, auth()).then((r) => r.data),
  qcTemplates: () => axios.get(`${base}/ops/qc/templates`, auth()).then((r) => r.data),
  qcUnit: (unitId, body) => axios.post(`${base}/ops/units/${unitId}/qc`, body, auth()).then((r) => r.data),
  createPackage: (id, body) => axios.post(`${base}/ops/orders/${id}/packages`, body, auth()).then((r) => r.data),
  addToPackage: (pkgId, body) => axios.post(`${base}/ops/packages/${pkgId}/add-unit`, body, auth()).then((r) => r.data),
  sealPackage: (pkgId, body) => axios.post(`${base}/ops/packages/${pkgId}/seal`, body || {}, auth()).then((r) => r.data),
  dispatch: (id, body) => axios.post(`${base}/ops/orders/${id}/dispatch`, body, auth()).then((r) => r.data),
  queue: (stage) => axios.get(`${base}/ops/queues/${stage}`, auth()).then((r) => r.data),
};

export const CUR = { GBP: '£', EUR: '€', USD: '$' };
export function money(v, cur = 'GBP') {
  const n = Number(v || 0);
  return `${CUR[cur] || ''}${n.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;
}
export function fmtDate(v) {
  if (!v) return '—';
  try { return new Date(v).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }); } catch { return '—'; }
}
export function statusLabel(s) {
  return (s || '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}
