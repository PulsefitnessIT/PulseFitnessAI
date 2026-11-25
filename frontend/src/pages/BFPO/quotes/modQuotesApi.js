import axios from 'axios';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

function authHeader() {
  let t = null;
  try { t = localStorage.getItem('token'); } catch { /* ignore */ }
  return t && t !== 'cookie' ? `Bearer ${t}` : 'Bearer cookie';
}

export const mq = axios.create({ baseURL: `${API}/mod-ops/quotes`, withCredentials: true });
mq.interceptors.request.use((cfg) => { cfg.headers.Authorization = authHeader(); return cfg; });

export const errText = (e) => {
  const d = e?.response?.data?.detail;
  if (!d) return e?.message || 'Something went wrong';
  if (typeof d === 'string') return d;
  if (d.issues) return `${d.message}: ${Object.values(d.issues).flat().join('; ')}`;
  if (d.unverified) return `${d.message} (${d.unverified.length} line(s) — see the approval panel)`;
  return d.message || JSON.stringify(d);
};

export async function downloadBlob(path, filename) {
  const r = await mq.get(path, { responseType: 'blob' });
  const url = URL.createObjectURL(r.data);
  const a = document.createElement('a');
  a.href = url;
  const cd = r.headers['content-disposition'] || '';
  a.download = (cd.match(/filename="([^"]+)"/) || [])[1] || filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export const gbp = (v) => `£${Number(v || 0).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export const TYPE_LABEL = { A: 'Type A', B: 'Type B', AB: 'Type A/B Mix' };
export const TYPE_DESC = {
  A: 'Fully Inclusive Maintenance',
  B: 'One-Off Service or Repair',
  AB: 'Combined Coverage',
};

export const STATUS_LABEL = {
  draft: 'Draft', pending_approval: 'Awaiting approval', approved: 'Approved', published: 'Published to MODService',
  customer_review: 'Customer reviewing', authorisation_submitted: 'Authorisation submitted', accepted: 'Accepted',
  handed_over: 'Handed to Operations', declined: 'Declined', withdrawn: 'Withdrawn', expired: 'Expired',
  superseded: 'Superseded', not_selected: 'Not selected', approved_not_published: 'Approved (not published)',
};

export const STATUS_TONE = {
  draft: 'var(--theme-text-muted)', pending_approval: 'var(--color-warning)', approved: 'var(--color-brand-cyan)',
  published: 'var(--color-brand-cyan)', customer_review: 'var(--color-brand-cyan)',
  authorisation_submitted: 'var(--color-warning)', accepted: 'var(--color-success)',
  handed_over: 'var(--color-success)',
};

export const card = { background: 'var(--theme-surface)', border: '1px solid var(--theme-border)', color: 'var(--theme-text)' };
export const muted = { color: 'var(--theme-text-muted)' };
export const inputStyle = { background: 'var(--theme-input-bg)', border: '1px solid var(--theme-input-border)', color: 'var(--theme-text)' };
export const primaryBtn = { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' };
