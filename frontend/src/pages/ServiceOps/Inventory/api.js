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
  parseInvoiceOrder: (file) => { const fd = new FormData(); fd.append('file', file); return axios.post(`${base}/orders/parse-invoice`, fd, auth()).then((r) => r.data); },
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

  // Phase 4 — dealer distribution
  shipments: (status) => axios.get(`${base}/dist/shipments`, { ...auth(), params: { status } }).then((r) => r.data),
  shipment: (id) => axios.get(`${base}/dist/shipments/${id}`, auth()).then((r) => r.data),
  shipmentStatus: (id, body) => axios.post(`${base}/dist/shipments/${id}/status`, body, auth()).then((r) => r.data),
  setCustoms: (id, body) => axios.put(`${base}/dist/shipments/${id}/customs`, body, auth()).then((r) => r.data),
  genDocument: (id, body) => axios.post(`${base}/dist/shipments/${id}/documents`, body, auth()).then((r) => r.data),
  dealerReceive: (id, body) => axios.post(`${base}/dist/shipments/${id}/receive`, body, auth()).then((r) => r.data),
  dealerInventory: (params) => axios.get(`${base}/dist/dealer-inventory`, { ...auth(), params }).then((r) => r.data),
  transfers: () => axios.get(`${base}/dist/transfers`, auth()).then((r) => r.data),
  createTransfer: (body) => axios.post(`${base}/dist/transfers`, body, auth()).then((r) => r.data),
  transferAction: (id, action) => axios.post(`${base}/dist/transfers/${id}/${action}`, {}, auth()).then((r) => r.data),
  distSummary: () => axios.get(`${base}/dist/summary`, auth()).then((r) => r.data),

  // Phase 5 — customer allocation
  allocAvailable: (dealerId) => axios.get(`${base}/alloc/available`, { ...auth(), params: { dealer_id: dealerId } }).then((r) => r.data),
  custSearch: (q) => axios.get(`${base}/alloc/customers/search`, { ...auth(), params: { q } }).then((r) => r.data),
  createCustomer: (body) => axios.post(`${base}/alloc/customers`, body, auth()).then((r) => r.data),
  allocate: (body) => axios.post(`${base}/alloc/allocate`, body, auth()).then((r) => r.data),
  allocations: (status) => axios.get(`${base}/alloc/allocations`, { ...auth(), params: { status } }).then((r) => r.data),
  allocation: (id) => axios.get(`${base}/alloc/allocations/${id}`, auth()).then((r) => r.data),
  install: (id, body) => axios.post(`${base}/alloc/allocations/${id}/install`, body, auth()).then((r) => r.data),
  scheduleInstall: (id, body) => axios.post(`${base}/alloc/allocations/${id}/schedule`, body, auth()).then((r) => r.data),
  installPack: (id) => axios.get(`${base}/alloc/allocations/${id}/install-pack`, auth()).then((r) => r.data),
  surveyCandidates: (id) => axios.get(`${base}/alloc/allocations/${id}/survey-candidates`, auth()).then((r) => r.data),
  linkSurvey: (id, surveyId) => axios.post(`${base}/alloc/allocations/${id}/link-survey`, { survey_id: surveyId }, auth()).then((r) => r.data),
  surveyAttachmentUrl: (attId) => `${base}/alloc/survey-attachment/${attId}/download`,
  drawingFileUrl: (drawingId) => `${API}/exploded-drawings/${drawingId}/file`,
  // Logistics portal + provisioning
  logisticsUsers: () => axios.get(`${base}/logistics/users`, auth()).then((r) => r.data),
  createLogisticsUser: (body) => axios.post(`${base}/logistics/users`, body, auth()).then((r) => r.data),
  setLogisticsUserStatus: (id, status) => axios.post(`${base}/logistics/users/${id}/status`, { status }, auth()).then((r) => r.data),
  resetLogisticsPassword: (id, password) => axios.post(`${base}/logistics/users/${id}/reset-password`, { password }, auth()).then((r) => r.data),
  logisticsInstalls: () => axios.get(`${base}/logistics/installs`, auth()).then((r) => r.data),
  logisticsPack: (id) => axios.get(`${base}/logistics/installs/${id}/pack`, auth()).then((r) => r.data),
  customerPortal: (companyId) => axios.get(`${base}/alloc/customer-portal/${companyId}/equipment`, auth()).then((r) => r.data),
  allocSummary: () => axios.get(`${base}/alloc/summary`, auth()).then((r) => r.data),

  // Phase 6 — dealer service desks
  desks: () => axios.get(`${base}/svc/desks`, auth()).then((r) => r.data),
  createDesk: (body) => axios.post(`${base}/svc/desks`, body, auth()).then((r) => r.data),
  activateDesk: (id) => axios.post(`${base}/svc/desks/${id}/activate`, {}, auth()).then((r) => r.data),
  desk: (id) => axios.get(`${base}/svc/desks/${id}`, auth()).then((r) => r.data),
  routeFault: (serial) => axios.get(`${base}/svc/route`, { ...auth(), params: { serial } }).then((r) => r.data),
  logFault: (body) => axios.post(`${base}/svc/faults`, body, auth()).then((r) => r.data),
  escalateFault: (id) => axios.post(`${base}/svc/faults/${id}/escalate`, {}, auth()).then((r) => r.data),
  warrantyParts: (dealerId) => axios.get(`${base}/svc/warranty-parts`, { ...auth(), params: { dealer_id: dealerId } }).then((r) => r.data),
  svcSummary: () => axios.get(`${base}/svc/summary`, auth()).then((r) => r.data),

  // Phase 7 — intelligence
  intelOverview: () => axios.get(`${base}/intel/overview`, auth()).then((r) => r.data),
  intelScan: () => axios.post(`${base}/intel/scan`, {}, auth()).then((r) => r.data),
  intelAlerts: (params) => axios.get(`${base}/intel/alerts`, { ...auth(), params }).then((r) => r.data),
  intelSetAlertStatus: (id, status) => axios.post(`${base}/intel/alerts/${id}/status`, { status }, auth()).then((r) => r.data),
  intelReport: (report) => axios.get(`${base}/intel/reports/${report}`, auth()).then((r) => r.data),
  intelReplenishment: (reorderPoint) => axios.get(`${base}/intel/replenishment`, { ...auth(), params: { reorder_point: reorderPoint } }).then((r) => r.data),
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
