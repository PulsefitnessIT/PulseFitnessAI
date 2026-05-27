/**
 * GdprErasurePanel — Master-Admin-only Data Subject Erasure (Art. 17)
 * workflow. Reused on Master Admin → Settings & Compliance → Data Subject
 * Requests and inside CRM Settings → Privacy & GDPR.
 *
 * Iter 220ao.
 */
import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { ShieldOff, AlertTriangle, CheckCircle2, Clock, Search, X, RefreshCw } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

const SUBJECT_TYPES = [
  { id: 'member', label: 'Gym Member', collection: 'members' },
  { id: 'instructor', label: 'Instructor', collection: 'membership_instructors' },
  { id: 'crm_contact', label: 'CRM Contact', collection: 'crm2_contacts' },
];

const STATUS_COLORS = {
  pending: 'bg-amber-100 text-amber-700 border-amber-200',
  executed: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  cancelled: 'bg-zinc-100 text-zinc-600 border-zinc-200',
  failed: 'bg-rose-100 text-rose-700 border-rose-200',
};

function authHeaders() {
  const token = localStorage.getItem('token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export default function GdprErasurePanel() {
  const [requests, setRequests] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [activeDetail, setActiveDetail] = useState(null);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (statusFilter) params.set('status', statusFilter);
      const r = await axios.get(`${API}/api/gdpr/erasure/requests?${params.toString()}`, { headers: authHeaders() });
      setRequests(r.data.requests || []);
      setTotal(r.data.total || 0);
      setError('');
    } catch (e) {
      setError(e?.response?.data?.detail || 'Failed to load erasure requests');
    }
    setLoading(false);
  }, [statusFilter]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-5" data-testid="gdpr-erasure-panel">
      {/* Hero */}
      <div className="rounded-2xl border p-5 bg-gradient-to-br from-rose-50 to-white border-rose-200" data-testid="gdpr-erasure-hero">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-lg bg-rose-100 flex items-center justify-center shrink-0">
            <ShieldOff size={20} className="text-rose-600" />
          </div>
          <div className="flex-1">
            <h2 className="text-base font-semibold text-zinc-900">GDPR Article 17 · Right to Erasure</h2>
            <p className="text-sm text-zinc-600 mt-1 leading-relaxed">
              File and execute Data Subject Erasure Requests against gym members, instructors and CRM contacts.
              PII (name, email, phone, address, DOB) is anonymised in place — invoices, bookings and audit logs survive
              for Art. 17(3)(b) compliance. A <strong>30-day cooling-off window</strong> precedes execution unless the
              data subject explicitly requests immediate action (force).
            </p>
          </div>
          <button
            onClick={() => setShowCreate(true)}
            className="px-3 py-1.5 text-xs font-semibold rounded-md bg-rose-600 text-white hover:bg-rose-700 shrink-0"
            data-testid="gdpr-new-request-btn"
          >
            + New erasure request
          </button>
        </div>
      </div>

      {/* Filter strip */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex gap-1">
          {['', 'pending', 'executed', 'cancelled'].map(s => (
            <button
              key={s || 'all'}
              onClick={() => setStatusFilter(s)}
              className={`px-3 py-1.5 text-xs font-medium rounded-md border transition ${
                statusFilter === s
                  ? 'bg-zinc-900 text-white border-zinc-900'
                  : 'bg-white text-zinc-600 border-zinc-200 hover:bg-zinc-50'
              }`}
              data-testid={`gdpr-status-filter-${s || 'all'}`}
            >
              {s ? s.charAt(0).toUpperCase() + s.slice(1) : `All (${total})`}
            </button>
          ))}
        </div>
        <button
          onClick={load}
          className="text-xs text-zinc-500 hover:text-zinc-900 flex items-center gap-1"
          data-testid="gdpr-refresh-btn"
        >
          <RefreshCw size={12} /> Refresh
        </button>
      </div>

      {error && (
        <div className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700" data-testid="gdpr-error">
          {error}
        </div>
      )}

      {/* List */}
      <div className="rounded-lg border border-zinc-200 bg-white overflow-hidden" data-testid="gdpr-requests-list">
        {loading && (
          <p className="px-4 py-8 text-center text-sm text-zinc-500" data-testid="gdpr-loading">Loading erasure requests…</p>
        )}
        {!loading && requests.length === 0 && (
          <p className="px-4 py-8 text-center text-sm text-zinc-500" data-testid="gdpr-empty">
            No erasure requests {statusFilter && `with status "${statusFilter}"`} found.
          </p>
        )}
        {!loading && requests.map(r => {
          const subjectLabel = SUBJECT_TYPES.find(s => s.id === r.subject_type)?.label || r.subject_type;
          return (
            <div
              key={r.id}
              onClick={() => setActiveDetail(r)}
              className="flex items-center gap-3 px-4 py-3 border-b border-zinc-100 last:border-b-0 cursor-pointer hover:bg-zinc-50"
              data-testid={`gdpr-request-row-${r.id}`}
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-semibold text-zinc-900 truncate">{r.subject_label || r.subject_id}</p>
                  <span className="text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded border bg-zinc-50 text-zinc-600 border-zinc-200">
                    {subjectLabel}
                  </span>
                  <span className={`text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded border ${STATUS_COLORS[r.status] || ''}`}>
                    {r.status}
                  </span>
                </div>
                <p className="text-[11px] text-zinc-500 mt-0.5">
                  Requested {new Date(r.requested_at).toLocaleDateString('en-GB')} by {r.requested_by_email || r.requested_by}
                  {r.status === 'pending' && r.execute_after && (
                    <> · Executes after {new Date(r.execute_after).toLocaleDateString('en-GB')}</>
                  )}
                  {r.reason && <> · {r.reason.substring(0, 80)}{r.reason.length > 80 ? '…' : ''}</>}
                </p>
              </div>
              {r.status === 'pending' && (
                <Clock size={16} className="text-amber-500 shrink-0" />
              )}
              {r.status === 'executed' && (
                <CheckCircle2 size={16} className="text-emerald-500 shrink-0" />
              )}
            </div>
          );
        })}
      </div>

      {showCreate && (
        <CreateRequestModal
          onClose={() => setShowCreate(false)}
          onCreated={() => { setShowCreate(false); load(); }}
        />
      )}

      {activeDetail && (
        <RequestDetailModal
          request={activeDetail}
          onClose={() => setActiveDetail(null)}
          onChange={() => { setActiveDetail(null); load(); }}
        />
      )}
    </div>
  );
}

/* ── Create modal ───────────────────────────────────────────────── */

function CreateRequestModal({ onClose, onCreated }) {
  const [subjectType, setSubjectType] = useState('member');
  const [subjectId, setSubjectId] = useState('');
  const [reason, setReason] = useState('');
  const [preview, setPreview] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const runPreview = async () => {
    setError('');
    setPreview(null);
    if (!subjectId.trim()) {
      setError('Please enter the subject id.');
      return;
    }
    try {
      const r = await axios.post(`${API}/api/gdpr/erasure/preview`, {
        subject_type: subjectType, subject_id: subjectId.trim(),
      }, { headers: authHeaders() });
      setPreview(r.data);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Preview failed');
    }
  };

  const submit = async () => {
    setSaving(true);
    setError('');
    try {
      await axios.post(`${API}/api/gdpr/erasure/requests`, {
        subject_type: subjectType, subject_id: subjectId.trim(), reason,
      }, { headers: authHeaders() });
      onCreated();
    } catch (e) {
      setError(e?.response?.data?.detail || 'Failed to create request');
    }
    setSaving(false);
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onClose}
      data-testid="gdpr-create-modal"
    >
      <div
        className="w-full max-w-xl rounded-xl bg-white shadow-2xl max-h-[90vh] overflow-y-auto"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b">
          <h3 className="text-base font-semibold text-zinc-900">New Erasure Request</h3>
          <button onClick={onClose} className="text-zinc-400 hover:text-zinc-900" data-testid="gdpr-create-close"><X size={16} /></button>
        </div>
        <div className="p-5 space-y-3">
          <div>
            <label className="text-[10px] uppercase tracking-wider font-semibold text-zinc-500">Subject Type</label>
            <select
              value={subjectType}
              onChange={e => { setSubjectType(e.target.value); setPreview(null); }}
              className="w-full mt-1 px-3 py-2 text-sm rounded-md border border-zinc-200"
              data-testid="gdpr-create-subject-type"
            >
              {SUBJECT_TYPES.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
            </select>
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-wider font-semibold text-zinc-500">Subject Id (UUID)</label>
            <div className="flex gap-2 mt-1">
              <input
                value={subjectId}
                onChange={e => setSubjectId(e.target.value)}
                placeholder="e.g. b3c8…"
                className="flex-1 px-3 py-2 text-sm rounded-md border border-zinc-200"
                data-testid="gdpr-create-subject-id"
              />
              <button
                onClick={runPreview}
                className="px-3 py-2 text-xs font-semibold rounded-md bg-zinc-900 text-white hover:bg-zinc-800"
                data-testid="gdpr-create-preview"
              >
                <Search size={12} className="inline -mt-0.5 mr-1" /> Preview
              </button>
            </div>
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-wider font-semibold text-zinc-500">Reason (optional)</label>
            <textarea
              value={reason}
              onChange={e => setReason(e.target.value)}
              rows={2}
              placeholder="e.g. member emailed asking for full deletion (ticket #1234)"
              className="w-full mt-1 px-3 py-2 text-sm rounded-md border border-zinc-200"
              data-testid="gdpr-create-reason"
            />
          </div>

          {preview && (
            <div className="rounded-md border border-zinc-200 bg-zinc-50 p-3" data-testid="gdpr-create-preview-result">
              <p className="text-xs font-semibold text-zinc-900 mb-1">Preview · {preview.label}</p>
              {preview.already_erased ? (
                <p className="text-xs text-rose-700">This subject has already been erased.</p>
              ) : (
                <>
                  <p className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Planned changes</p>
                  <ul className="text-xs text-zinc-700 space-y-0.5">
                    {Object.entries(preview.plan || {}).map(([field, change]) => (
                      <li key={field}>
                        <code className="text-rose-700">{field}</code>: <span className="text-zinc-500">{String(change.before)}</span> → <span className="font-semibold">{change.after === null ? 'cleared' : String(change.after)}</span>
                      </li>
                    ))}
                  </ul>
                  {Object.keys(preview.plan || {}).length === 0 && (
                    <p className="text-xs text-zinc-500">No PII fields populated on this record.</p>
                  )}
                </>
              )}
            </div>
          )}

          {error && (
            <p className="text-xs text-rose-700" data-testid="gdpr-create-error">{error}</p>
          )}

          <div className="flex items-center gap-2 pt-2">
            <AlertTriangle size={14} className="text-amber-600 shrink-0" />
            <p className="text-[11px] text-amber-700">
              A 30-day cooling-off window will start. Master Admin can fast-track via the request detail.
            </p>
          </div>
        </div>
        <div className="flex justify-end gap-2 px-5 py-3 border-t bg-zinc-50">
          <button onClick={onClose} className="px-3 py-1.5 text-xs text-zinc-600" data-testid="gdpr-create-cancel">Cancel</button>
          <button
            onClick={submit}
            disabled={saving || !preview || preview.already_erased}
            className="px-3 py-1.5 text-xs font-semibold rounded-md bg-rose-600 text-white hover:bg-rose-700 disabled:opacity-50"
            data-testid="gdpr-create-submit"
          >
            {saving ? 'Filing…' : 'File erasure request'}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── Detail modal — execute / cancel ───────────────────────────── */

function RequestDetailModal({ request, onClose, onChange }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [plan, setPlan] = useState(null);

  useEffect(() => {
    // Refresh server-side plan in case PII changed between request creation
    // and now (e.g. operator updated a phone number).
    (async () => {
      try {
        const r = await axios.get(`${API}/api/gdpr/erasure/requests/${request.id}`, { headers: authHeaders() });
        setPlan(r.data.plan || null);
      } catch { /* noop */ }
    })();
  }, [request.id]);

  const execute = async (force) => {
    if (!window.confirm(`Execute erasure for ${request.subject_label}? This anonymises PII in place and CANNOT be undone.`)) return;
    setBusy(true);
    setError('');
    try {
      await axios.post(`${API}/api/gdpr/erasure/requests/${request.id}/execute`, { force }, { headers: authHeaders() });
      onChange();
    } catch (e) {
      setError(e?.response?.data?.detail || 'Execute failed');
    }
    setBusy(false);
  };

  const cancel = async () => {
    if (!window.confirm(`Cancel this erasure request?`)) return;
    setBusy(true);
    setError('');
    try {
      await axios.post(`${API}/api/gdpr/erasure/requests/${request.id}/cancel`, {}, { headers: authHeaders() });
      onChange();
    } catch (e) {
      setError(e?.response?.data?.detail || 'Cancel failed');
    }
    setBusy(false);
  };

  const isPending = request.status === 'pending';
  const coolingOver = isPending && request.execute_after && new Date(request.execute_after) <= new Date();

  return (
    <div
      className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onClose}
      data-testid="gdpr-detail-modal"
    >
      <div
        className="w-full max-w-xl rounded-xl bg-white shadow-2xl max-h-[90vh] overflow-y-auto"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b">
          <h3 className="text-base font-semibold text-zinc-900">Erasure Request · {request.subject_label}</h3>
          <button onClick={onClose} className="text-zinc-400 hover:text-zinc-900" data-testid="gdpr-detail-close"><X size={16} /></button>
        </div>
        <div className="p-5 space-y-3">
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <p className="text-[10px] uppercase tracking-wider text-zinc-500">Status</p>
              <p className={`inline-block mt-1 text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded border ${STATUS_COLORS[request.status] || ''}`}>
                {request.status}
              </p>
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-wider text-zinc-500">Subject Type</p>
              <p className="text-sm text-zinc-900">{request.subject_type}</p>
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-wider text-zinc-500">Requested</p>
              <p className="text-sm text-zinc-900">{new Date(request.requested_at).toLocaleString('en-GB')}</p>
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-wider text-zinc-500">Cooling-off ends</p>
              <p className="text-sm text-zinc-900">{request.execute_after ? new Date(request.execute_after).toLocaleString('en-GB') : '—'}</p>
            </div>
          </div>

          {request.reason && (
            <div className="rounded-md border border-zinc-200 bg-zinc-50 p-3">
              <p className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Reason</p>
              <p className="text-xs text-zinc-700">{request.reason}</p>
            </div>
          )}

          {isPending && plan && Object.keys(plan).length > 0 && (
            <div className="rounded-md border border-amber-200 bg-amber-50 p-3" data-testid="gdpr-detail-plan">
              <p className="text-[10px] uppercase tracking-wider text-amber-800 mb-1">Will be anonymised</p>
              <ul className="text-xs text-zinc-800 space-y-0.5">
                {Object.entries(plan).map(([field, change]) => (
                  <li key={field}>
                    <code className="text-rose-700">{field}</code>: <span className="text-zinc-500">{String(change.before)}</span> → <span className="font-semibold">{change.after === null ? 'cleared' : String(change.after)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {request.scrub_summary && (
            <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3" data-testid="gdpr-detail-scrub-summary">
              <p className="text-[10px] uppercase tracking-wider text-emerald-800 mb-1">Scrub summary</p>
              <pre className="text-[11px] text-zinc-700 whitespace-pre-wrap">{JSON.stringify(request.scrub_summary, null, 2)}</pre>
            </div>
          )}

          {error && <p className="text-xs text-rose-700" data-testid="gdpr-detail-error">{error}</p>}
        </div>

        {isPending && (
          <div className="flex justify-between gap-2 px-5 py-3 border-t bg-zinc-50">
            <button
              onClick={cancel}
              disabled={busy}
              className="px-3 py-1.5 text-xs text-zinc-700 border border-zinc-200 rounded-md hover:bg-white disabled:opacity-50"
              data-testid="gdpr-detail-cancel-btn"
            >
              Cancel request
            </button>
            <div className="flex gap-2">
              {coolingOver ? (
                <button
                  onClick={() => execute(false)}
                  disabled={busy}
                  className="px-3 py-1.5 text-xs font-semibold rounded-md bg-rose-600 text-white hover:bg-rose-700 disabled:opacity-50"
                  data-testid="gdpr-detail-execute-btn"
                >
                  Execute now
                </button>
              ) : (
                <button
                  onClick={() => execute(true)}
                  disabled={busy}
                  className="px-3 py-1.5 text-xs font-semibold rounded-md bg-rose-700 text-white hover:bg-rose-800 disabled:opacity-50"
                  data-testid="gdpr-detail-force-execute-btn"
                  title="Fast-track erasure at the data subject's explicit request"
                >
                  Force execute (skip cooling-off)
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
