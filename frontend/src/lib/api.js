// Central API client shim (Pulse Fitness).
// Provides a shared axios instance `api` (baseURL includes `/api`) plus the
// legacy `API` / `API_BASE` constants. Auth uses the operator JWT stored in
// localStorage('token') — matching the rest of the Pulse frontend.
import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';

/** Host only, e.g. https://app.example.com (no trailing /api). */
export const API_BASE = BACKEND_URL;
/** Full API root, e.g. https://app.example.com/api. */
export const API = BACKEND_URL ? `${BACKEND_URL}/api` : '/api';

/** Canonical axios instance. Call with backend-relative paths: api.get('/svc/scheduling/board'). */
export const api = axios.create({ baseURL: API });

// Inject the operator Bearer token on every request (unless one is already set,
// or the call targets the CRM / member portals which manage their own auth).
api.interceptors.request.use((config) => {
  try {
    const url = `${config.baseURL || ''}${config.url || ''}`;
    if (!url.includes('/api/crm/') && !url.includes('/api/member/')) {
      config.headers = config.headers || {};
      const existing = config.headers.Authorization || config.headers.authorization;
      if (!existing) {
        const tok = localStorage.getItem('token');
        if (tok) config.headers.Authorization = `Bearer ${tok}`;
      }
    }
  } catch { /* never block a request on header injection */ }
  return config;
});

export default api;

// CRM SPA authenticates with a dedicated `crm_token` (falls back to the
// operator `token`). The operator interceptor on `api` skips `/api/crm/`,
// so CRM calls use this instance. Call with backend-relative paths, e.g.
// crmApi.get('/crm/v2/tenders').
export const CRM_TOKEN_KEY = 'crm_token';
export const crmApi = axios.create({ baseURL: API });
crmApi.interceptors.request.use((config) => {
  try {
    config.headers = config.headers || {};
    const existing = config.headers.Authorization || config.headers.authorization;
    if (!existing) {
      // CRM endpoints only accept a crm_token. NEVER fall back to the main
      // platform `token` — a valid non-CRM JWT fails crm_verify_token and
      // surfaces a misleading "Invalid CRM token" toast (seen during
      // master-admin impersonation, when the crm_token is briefly re-minted).
      const tok = localStorage.getItem(CRM_TOKEN_KEY);
      if (tok) config.headers.Authorization = `Bearer ${tok}`;
    }
  } catch { /* never block a request */ }
  return config;
});