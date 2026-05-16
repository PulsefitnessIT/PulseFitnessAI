/**
 * AdminPartsRequests — /admin/parts-requests
 *
 * Iter 216h136. Master-admin inbox for engineer parts requests:
 *   pending → approve (allocates to van + case) | reject (with reason)
 *
 * Backed by:
 *   GET  /api/admin/parts-requests
 *   POST /api/admin/parts-requests/{id}/approve { ship_from, supplier_ref?, notes? }
 *   POST /api/admin/parts-requests/{id}/reject  { reason }
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft, Package, RefreshCw, Loader2, Check, X, AlertTriangle,
  Inbox, CheckCircle2, XCircle, Send, Filter, ChevronRight,
} from 'lucide-react';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });

const STATUS_TABS = [
  { id: 'pending',   label: 'Pending',   icon: Inbox },
  { id: 'approved',  label: 'Approved',  icon: CheckCircle2 },
  { id: 'rejected',  label: 'Rejected',  icon: XCircle },
  { id: 'cancelled', label: 'Cancelled', icon: X },
];

const URGENCY_COLORS = {
  critical: 'bg-rose-100 text-rose-800 border-rose-200',
  urgent:   'bg-amber-100 text-amber-800 border-amber-200',
  normal:   'bg-blue-100 text-blue-800 border-blue-200',
};

export default function AdminPartsRequests() {
  const navigate = useNavigate();
  const [status, setStatus] = useState('pending');
  const [urgency, setUrgency] = useState('');
  const [rows, setRows] = useState([]);
  const [counts, setCounts] = useState({});
  const [loading, setLoading] = useState(true);
  const [showAction, setShowAction] = useState(null);  // { request, mode } | null

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/admin/parts-requests`, {
        ...auth(), params: { status, urgency: urgency || undefined },
      });
      setRows(r.data?.items || []);
      setCounts(r.data?.counts || {});
    } catch (e) {
      notify.error('Could not load requests');
    } finally { setLoading(false); }
  }, [status, urgency]);

  useEffect(() => { load(); }, [load]);

  const action = async (request, mode, payload) => {
    try {
      const endpoint = mode === 'approve' ? 'approve' : 'reject';
      await axios.post(
        `${API}/admin/parts-requests/${request.id}/${endpoint}`,
        payload, auth(),
      );
      notify.success(mode === 'approve' ? 'Allocated to engineer' : 'Request rejected');
      setShowAction(null);
      await load();
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Action failed');
    }
  };

  return (
    <div className="min-h-screen bg-slate-50" data-testid="admin-parts-requests-page">
      <header className="sticky top-0 z-10 bg-white/95 backdrop-blur border-b border-slate-200">
        <div className="max-w-5xl mx-auto px-4 py-3 flex items-center gap-3">
          <button
            type="button"
            onClick={() => navigate('/master-admin')}
            className="p-2 rounded-full hover:bg-slate-100"
            aria-label="Back"
            data-testid="parts-requests-back"
          >
            <ArrowLeft size={18} />
          </button>
          <div className="flex-1">
            <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500">
              Master admin · Engineer Network
            </p>
            <h1 className="text-lg font-extrabold flex items-center gap-2">
              <Package size={18} /> Parts requests
            </h1>
          </div>
          <button
            type="button"
            onClick={load}
            aria-label="Refresh"
            className="p-2 rounded-full border border-slate-200 bg-white"
            data-testid="parts-requests-refresh"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
        <nav className="max-w-5xl mx-auto px-2 flex items-center gap-0.5 overflow-x-auto" data-testid="parts-requests-tabs">
          {STATUS_TABS.map(t => {
            const Icon = t.icon;
            const active = status === t.id;
            const count = counts[t.id] || 0;
            return (
              <button key={t.id} type="button" onClick={() => setStatus(t.id)}
                className={`relative flex items-center gap-1.5 px-3 py-2 text-xs font-bold uppercase tracking-wide ${active ? 'text-blue-700' : 'text-slate-500 hover:text-slate-700'}`}
                data-testid={`parts-requests-tab-${t.id}`}>
                <Icon size={13} />
                {t.label}
                {count > 0 && (
                  <span className="ml-1 inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full bg-slate-100 text-slate-700 text-[10px] font-bold tabular-nums">
                    {count}
                  </span>
                )}
                {active && <span className="absolute bottom-0 left-2 right-2 h-0.5 bg-blue-700 rounded-t" />}
              </button>
            );
          })}
        </nav>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-5 pb-20 space-y-4">
        {/* Urgency filter */}
        <div className="flex items-center gap-2 text-xs" data-testid="parts-requests-filter-urgency">
          <Filter size={12} className="text-slate-400" />
          <span className="text-slate-500">Urgency:</span>
          {['', 'normal', 'urgent', 'critical'].map(u => (
            <button key={u || 'all'} onClick={() => setUrgency(u)}
              className={`px-2.5 py-1 rounded-full text-[11px] font-bold capitalize border ${urgency === u ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-slate-700 border-slate-200'}`}
              data-testid={`parts-requests-urgency-${u || 'all'}`}>
              {u || 'all'}
            </button>
          ))}
        </div>

        {loading && rows.length === 0 ? (
          <div className="text-center py-16 text-slate-400">
            <Loader2 className="animate-spin mx-auto mb-2" size={20} /> Loading…
          </div>
        ) : rows.length === 0 ? (
          <EmptyState status={status} />
        ) : (
          <ul className="space-y-2">
            {rows.map(r => (
              <RequestRow key={r.id} req={r}
                onApprove={() => setShowAction({ request: r, mode: 'approve' })}
                onReject={() => setShowAction({ request: r, mode: 'reject' })}
              />
            ))}
          </ul>
        )}
      </main>

      {showAction && (
        <ActionModal
          mode={showAction.mode}
          request={showAction.request}
          onCancel={() => setShowAction(null)}
          onSubmit={(payload) => action(showAction.request, showAction.mode, payload)}
        />
      )}
    </div>
  );
}

function RequestRow({ req, onApprove, onReject }) {
  const cl = URGENCY_COLORS[req.urgency] || URGENCY_COLORS.normal;
  return (
    <li className="bg-white rounded-2xl border border-slate-200 p-4 flex items-center gap-3" data-testid={`parts-request-row-${req.id}`}>
      <div className="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center flex-shrink-0">
        <Package size={18} className="text-slate-500" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <p className="text-sm font-extrabold text-slate-900 tabular-nums">{req.qty} × {req.part_sku}</p>
          <span className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded-full border ${cl}`}>{req.urgency}</span>
          {!req.in_catalogue && (
            <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded-full border bg-violet-50 text-violet-700 border-violet-200">
              not in catalogue
            </span>
          )}
        </div>
        <p className="text-xs text-slate-600 truncate">{req.part_name}</p>
        <p className="text-[11px] text-slate-500 truncate">
          {req.engineer_name || 'Engineer'} · case <code>{req.case_reference || req.case_id}</code>
          {req.notes ? ` · ${req.notes}` : ''}
        </p>
        {req.status === 'rejected' && req.reject_reason && (
          <p className="text-[11px] text-rose-600 mt-1">Reason: {req.reject_reason}</p>
        )}
        {req.status === 'approved' && req.ship_from && (
          <p className="text-[11px] text-emerald-700 mt-1">
            Approved via <b>{req.ship_from}</b>
            {req.supplier_ref ? ` · ref ${req.supplier_ref}` : ''}
          </p>
        )}
      </div>
      {req.status === 'pending' ? (
        <div className="flex gap-2 shrink-0">
          <button onClick={onReject} className="inline-flex items-center gap-1 px-3 py-1.5 rounded-full bg-white border border-slate-200 text-slate-700 text-xs font-bold hover:bg-slate-50" data-testid={`parts-request-reject-btn-${req.id}`}>
            <X size={12} /> Reject
          </button>
          <button onClick={onApprove} className="inline-flex items-center gap-1 px-3 py-1.5 rounded-full bg-emerald-600 text-white text-xs font-bold hover:bg-emerald-700" data-testid={`parts-request-approve-btn-${req.id}`}>
            <Check size={12} /> Approve
          </button>
        </div>
      ) : (
        <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">{req.status}</span>
      )}
    </li>
  );
}

function EmptyState({ status }) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-200 bg-white p-12 text-center" data-testid="parts-requests-empty">
      <Inbox size={28} className="mx-auto text-slate-300 mb-2" />
      <p className="text-sm font-bold text-slate-700">No {status} requests</p>
      <p className="text-xs text-slate-500 mt-1">
        {status === 'pending'
          ? "When an engineer needs a part that isn't allocated yet, it lands here for your approval."
          : `Requests will appear once they move to ${status}.`}
      </p>
    </div>
  );
}

function ActionModal({ mode, request, onCancel, onSubmit }) {
  const [shipFrom, setShipFrom] = useState('warehouse');
  const [supplierRef, setSupplierRef] = useState('');
  const [notes, setNotes] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (mode === 'reject' && !reason.trim()) {
      notify.error('Please add a reject reason');
      return;
    }
    setBusy(true);
    try {
      if (mode === 'approve') {
        await onSubmit({ ship_from: shipFrom, supplier_ref: supplierRef, notes });
      } else {
        await onSubmit({ reason: reason.trim() });
      }
    } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 flex items-end md:items-center justify-center p-4" data-testid="parts-request-action-modal">
      <div className="bg-white rounded-2xl w-full max-w-md p-5 shadow-xl border border-slate-200">
        <div className="flex items-center gap-2 mb-3">
          {mode === 'approve' ? (
            <><Check size={16} className="text-emerald-600" /><h3 className="text-base font-bold text-slate-900">Approve &amp; allocate</h3></>
          ) : (
            <><X size={16} className="text-rose-600" /><h3 className="text-base font-bold text-slate-900">Reject request</h3></>
          )}
        </div>
        <div className="text-xs text-slate-600 mb-3 rounded-lg bg-slate-50 border border-slate-200 p-2">
          <b>{request.qty} × {request.part_sku}</b> — {request.part_name}<br />
          for {request.engineer_name} on case <code>{request.case_reference || request.case_id}</code>
        </div>

        {mode === 'approve' ? (
          <div className="space-y-3">
            <div>
              <label className="text-[11px] uppercase font-bold tracking-wide text-slate-500 block mb-1">Ship from</label>
              <div className="flex gap-1">
                {[
                  { id: 'warehouse',         label: 'Warehouse' },
                  { id: 'supplier_direct',   label: 'Supplier direct' },
                ].map(o => (
                  <button key={o.id} type="button" onClick={() => setShipFrom(o.id)}
                    className={`flex-1 py-1.5 rounded-lg text-xs font-bold border ${shipFrom === o.id ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-slate-700 border-slate-200'}`}
                    data-testid={`parts-request-shipfrom-${o.id}`}>
                    {o.label}
                  </button>
                ))}
              </div>
            </div>
            {shipFrom === 'supplier_direct' && (
              <div>
                <label className="text-[11px] uppercase font-bold tracking-wide text-slate-500 block mb-1">Supplier reference</label>
                <input value={supplierRef} onChange={e => setSupplierRef(e.target.value)} className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white" placeholder="PO-XXXX or supplier order #" data-testid="parts-request-supplier-ref" />
              </div>
            )}
            <div>
              <label className="text-[11px] uppercase font-bold tracking-wide text-slate-500 block mb-1">Notes (optional)</label>
              <textarea rows={2} value={notes} onChange={e => setNotes(e.target.value)} className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white" placeholder="ETA, special handling…" data-testid="parts-request-approve-notes" />
            </div>
          </div>
        ) : (
          <div>
            <label className="text-[11px] uppercase font-bold tracking-wide text-slate-500 block mb-1">Reason *</label>
            <textarea rows={3} value={reason} onChange={e => setReason(e.target.value)} className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white" placeholder="e.g. Out of stock with no ETA, customer to source themselves." data-testid="parts-request-reject-reason" />
          </div>
        )}

        <div className="mt-4 flex justify-end gap-2">
          <button onClick={onCancel} className="px-4 py-2 rounded-full bg-white border border-slate-200 text-slate-700 text-sm font-bold" data-testid="parts-request-modal-cancel">Cancel</button>
          <button onClick={submit} disabled={busy} className={`inline-flex items-center gap-2 px-4 py-2 rounded-full text-white text-sm font-bold disabled:opacity-50 ${mode === 'approve' ? 'bg-emerald-600 hover:bg-emerald-700' : 'bg-rose-600 hover:bg-rose-700'}`} data-testid="parts-request-modal-submit">
            {busy ? <Loader2 size={14} className="animate-spin" /> : (mode === 'approve' ? <Check size={14} /> : <X size={14} />)}
            {mode === 'approve' ? 'Approve' : 'Reject'}
          </button>
        </div>
      </div>
    </div>
  );
}
