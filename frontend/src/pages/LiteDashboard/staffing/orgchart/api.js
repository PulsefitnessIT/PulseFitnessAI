/** Org Chart API client + small helpers. */
import axios from 'axios';

const API = `${process.env.REACT_APP_BACKEND_URL}/api/staffing/orgchart`;

const auth = () => {
  const t = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  return { Authorization: `Bearer ${t}` };
};

export const ocApi = {
  listCharts: () => axios.get(`${API}/charts`, { headers: auth() }).then((r) => r.data),
  createChart: (body) => axios.post(`${API}/charts`, body, { headers: auth() }).then((r) => r.data),
  getChart: (cid) => axios.get(`${API}/charts/${cid}`, { headers: auth() }).then((r) => r.data),
  updateChart: (cid, body) => axios.patch(`${API}/charts/${cid}`, body, { headers: auth() }).then((r) => r.data),
  deleteChart: (cid) => axios.delete(`${API}/charts/${cid}`, { headers: auth() }).then((r) => r.data),
  syncStaff: (cid) => axios.post(`${API}/charts/${cid}/sync-staff`, {}, { headers: auth() }).then((r) => r.data),
  createNode: (cid, body) => axios.post(`${API}/charts/${cid}/nodes`, body, { headers: auth() }).then((r) => r.data),
  updateNode: (cid, nid, body) => axios.patch(`${API}/charts/${cid}/nodes/${nid}`, body, { headers: auth() }).then((r) => r.data),
  deleteNode: (cid, nid) => axios.delete(`${API}/charts/${cid}/nodes/${nid}`, { headers: auth() }).then((r) => r.data),
  insights: (cid) => axios.get(`${API}/charts/${cid}/insights`, { headers: auth() }).then((r) => r.data),
  importPreview: (cid, rows) => axios.post(`${API}/charts/${cid}/import/preview`, { rows }, { headers: auth() }).then((r) => r.data),
  importApply: (cid, rows, options) => axios.post(`${API}/charts/${cid}/import/apply`, { rows, options }, { headers: auth() }).then((r) => r.data),
  exportCsvUrl: (cid) => `${API}/charts/${cid}/export.csv`,
};

// Deterministic department colour so branches read consistently.
const DEPT_COLORS = [
  '#2563eb', '#7c3aed', '#0891b2', '#db2777', '#ea580c',
  '#16a34a', '#ca8a04', '#dc2626', '#4f46e5', '#0d9488',
];
export function deptColor(dept) {
  if (!dept) return '#94a3b8';
  let h = 0;
  for (let i = 0; i < dept.length; i += 1) h = (h * 31 + dept.charCodeAt(i)) % 997;
  return DEPT_COLORS[h % DEPT_COLORS.length];
}

export const humanize = (s) => (s ? String(s).replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) : '');

export const NODE_LABELS = {
  staff: 'Staff', vacancy: 'Vacancy', placeholder: 'Placeholder', contractor: 'Contractor',
};

export const VACANCY_STAGES = [
  'Planned', 'Approved', 'Recruiting', 'Interviewing', 'Offer Made', 'Filled', 'On Hold', 'Cancelled',
];
