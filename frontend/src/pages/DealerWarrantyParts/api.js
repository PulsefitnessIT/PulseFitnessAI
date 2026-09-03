import axios from 'axios';

const BASE = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api/dealer-parts`
  : '/api/dealer-parts';

const ROOT = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';

const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });

const _sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Retry a request with exponential backoff. Only retries network errors and
// 5xx / 408 / 429 (transient) — never 4xx auth/validation. Chunk uploads are
// idempotent per seq on the server (upsert), so retrying a chunk is always safe.
const _withRetry = async (fn, { attempts = 4, baseDelay = 800 } = {}) => {
  let lastErr;
  for (let i = 0; i < attempts; i += 1) {
    try { return await fn(); }
    catch (e) {
      lastErr = e;
      const status = e?.response?.status;
      if (status && status !== 408 && status !== 429 && status < 500) throw e;
      if (i < attempts - 1) await _sleep(baseDelay * 2 ** i);
    }
  }
  throw lastErr;
};

// Upload a file to a MongoDB-backed session in ~1.4 MB chunks, retrying any
// single failed chunk (rather than restarting the whole upload). Returns the
// upload_id so the caller can call finish / finish-invoice.
const _uploadChunks = async (file, onProgress, cap = 100) => {
  const { data: init } = await _withRetry(() => axios.post(`${BASE}/data/upload/init`, {}, auth()));
  const uploadId = init.upload_id;
  const CHUNK = 1_400_000;
  let seq = 0;
  for (let start = 0; start < file.size; start += CHUNK) {
    const blob = file.slice(start, start + CHUNK);
    const s = seq;
    await _withRetry(() => {
      const fd = new FormData();
      fd.append('chunk', blob);
      return axios.post(`${BASE}/data/upload/${uploadId}/chunk?seq=${s}`, fd, auth());
    });
    seq += 1;
    if (onProgress) onProgress(Math.min(cap, Math.round(((start + CHUNK) / file.size) * 100)));
  }
  return uploadId;
};

export const dpApi = {
  dashboard: () => axios.get(`${BASE}/dashboard`, auth()).then((r) => r.data),
  listPartsRequests: (params = {}) => axios.get(`${ROOT}/parts-requests`, { ...auth(), params }).then((r) => r.data),
  getSettings: () => axios.get(`${BASE}/settings`, auth()).then((r) => r.data),
  saveSettings: (data) => axios.put(`${BASE}/settings`, data, auth()).then((r) => r.data),

  listDealers: (params = {}) => axios.get(`${BASE}/dealers`, { ...auth(), params }).then((r) => r.data),
  createDealer: (data) => axios.post(`${BASE}/dealers`, data, auth()).then((r) => r.data),
  getDealer: (id) => axios.get(`${BASE}/dealers/${id}`, auth()).then((r) => r.data),
  updateDealer: (id, data) => axios.patch(`${BASE}/dealers/${id}`, data, auth()).then((r) => r.data),

  // Dealer setup dropdowns — link to CRM companies + internal Pulse Fitness staff.
  listCrmCompanies: (search = '') => axios.get(`${BASE}/crm-companies`, { ...auth(), params: { search } }).then((r) => r.data),
  createCrmCompany: (data) => axios.post(`${BASE}/crm-companies`, data, auth()).then((r) => r.data),
  listOrgStaff: () => axios.get(`${BASE}/staff`, auth()).then((r) => r.data),

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
  portalMeOverview: () => axios.get(`${BASE}/portal/me/overview`, auth()).then((r) => r.data),
  portalMeRequest: (data) => axios.post(`${BASE}/portal/me/request-replenishment`, data, auth()).then((r) => r.data),
  listDealerUsers: (dealerId) => axios.get(`${BASE}/dealers/${dealerId}/users`, auth()).then((r) => r.data),
  createDealerUser: (dealerId, data) => axios.post(`${BASE}/dealers/${dealerId}/users`, data, auth()).then((r) => r.data),
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

  // ── Phase 1 Data & Intelligence engine ──
  listImports: (kind = '') => axios.get(`${BASE}/data/imports`, { ...auth(), params: kind ? { kind } : {} }).then((r) => r.data),
  importWarrantyPlan: (file) => { const fd = new FormData(); fd.append('file', file); return axios.post(`${BASE}/data/warranty-plan/import`, fd, auth()).then((r) => r.data); },
  getWarrantyPlan: () => axios.get(`${BASE}/data/warranty-plan`, auth()).then((r) => r.data),
  reverseImport: (id) => axios.post(`${BASE}/data/imports/${id}/reverse`, {}, auth()).then((r) => r.data),
  // Chunked upload (MongoDB-backed, replica-safe) with per-chunk auto-retry.
  uploadSpreadsheet: async (file, kind, onProgress) => {
    const uploadId = await _uploadChunks(file, onProgress, 100);
    const { data } = await _withRetry(() => axios.post(`${BASE}/data/upload/${uploadId}/finish`, { kind, filename: file.name }, auth()));
    if (onProgress) onProgress(100);
    return data;
  },
  mostUsedAnalysis: (params = {}) => axios.get(`${BASE}/data/most-used-analysis`, { ...auth(), params }).then((r) => r.data),
  unmatched: (params = {}) => axios.get(`${BASE}/data/unmatched`, { ...auth(), params }).then((r) => r.data),
  runMatching: () => axios.post(`${BASE}/data/match/run`, {}, auth()).then((r) => r.data),
  listDataMatches: (params = {}) => axios.get(`${BASE}/data/matches`, { ...auth(), params }).then((r) => r.data),
  reviewMatch: (id, action) => axios.post(`${BASE}/data/matches/${id}/review`, { action }, auth()).then((r) => r.data),
  listAliases: (status = '') => axios.get(`${BASE}/data/aliases`, { ...auth(), params: status ? { status } : {} }).then((r) => r.data),
  createAlias: (data) => axios.post(`${BASE}/data/aliases`, data, auth()).then((r) => r.data),
  reviewAlias: (id, action) => axios.post(`${BASE}/data/aliases/${id}/review`, { action }, auth()).then((r) => r.data),
  unmatchedAction: (codeNorm, data) => axios.post(`${BASE}/data/unmatched/${encodeURIComponent(codeNorm)}/action`, data, auth()).then((r) => r.data),
  listDataMachines: (params = {}) => axios.get(`${BASE}/data/machines`, { ...auth(), params }).then((r) => r.data),
  machineParts: (topLevelRef) => axios.get(`${BASE}/data/machine-parts`, { ...auth(), params: { top_level_ref: topLevelRef } }).then((r) => r.data),
  getDataSettings: () => axios.get(`${BASE}/data/settings`, auth()).then((r) => r.data),
  saveDataSettings: (data) => axios.put(`${BASE}/data/settings`, data, auth()).then((r) => r.data),
  matchMachine: (q) => axios.get(`${BASE}/data/match-machine`, { ...auth(), params: { q } }).then((r) => r.data),
  recommendFromInvoice: (data) => axios.post(`${BASE}/data/recommend`, data, auth()).then((r) => r.data),
  planVsActuals: (data) => axios.post(`${BASE}/data/plan-vs-actuals`, data, auth()).then((r) => r.data),
  updateWarrantyPlanPart: (data) => axios.post(`${BASE}/data/warranty-plan/update-part`, data, auth()).then((r) => r.data),
  dataMonitoring: () => axios.get(`${BASE}/data/monitoring`, auth()).then((r) => r.data),
  aiParseInvoiceFile: async (file, onProgress) => {
    // Chunked upload (MongoDB-backed, per-chunk retry) → async parse job → poll.
    // The parse runs in the background so slow LLM reads never hit the ~100s
    // Cloudflare origin timeout. Handles files of any size; poll survives blips.
    const uploadId = await _uploadChunks(file, onProgress, 99);
    const { data: started } = await _withRetry(() => axios.post(`${BASE}/data/upload/${uploadId}/finish-invoice`, { filename: file.name, content_type: file.type }, auth()));
    if (onProgress) onProgress(100);
    // Backward-compatible: if the server parsed inline, return immediately.
    if (!started.job_id) return started;
    const jobId = started.job_id;
    // Poll up to ~10 minutes (300 × 2s) — safely beyond any LLM parse time.
    // Transient network errors during polling are ignored (keep polling).
    for (let i = 0; i < 300; i += 1) {
      await _sleep(2000);
      try {
        const { data: job } = await axios.get(`${BASE}/data/invoice-jobs/${jobId}`, auth());
        if (job.status === 'done' || job.status === 'error') return job;
      } catch (e) { /* transient blip — keep polling */ }
    }
    return { available: false, error: 'AI parsing timed out. Please try again.' };
  },
  downloadDataReport: async (report, topLevelRef = '') => {
    const res = await axios.get(`${BASE}/data/reports/${report}.csv`, { ...auth(), params: topLevelRef ? { top_level_ref: topLevelRef } : {}, responseType: 'blob' });
    const url = window.URL.createObjectURL(new Blob([res.data]));
    const a = document.createElement('a');
    a.href = url; a.download = `${report}.csv`;
    document.body.appendChild(a); a.click(); a.remove();
    window.URL.revokeObjectURL(url);
  },
};
