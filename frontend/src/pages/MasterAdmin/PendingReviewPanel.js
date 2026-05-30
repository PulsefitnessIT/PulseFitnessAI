/**
 * PendingReviewPanel — Iter 220dh.
 *
 * Master-Admin unified inbox for items needing action across the
 * platform. Aggregates partner-engineer applications, PTW requests
 * and parts requests behind a single tabbed list. Each row carries
 * inline Approve / Reject so the admin can keep flowing without
 * opening three different panels.
 *
 * Data source: ``GET /api/master-admin/pending-review`` + per-kind
 * counts at ``GET /api/master-admin/pending-review/count``.
 */
import { useEffect, useMemo, useState, useCallback } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import {
  Loader2, RefreshCw, Check, X, ExternalLink, AlertCircle,
  ShieldAlert, Handshake, Package,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL;
const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
});

const KIND_META = {
  partner_application: {
    label: 'Partner applications',
    icon: Handshake,
    tone: 'bg-purple-50 text-purple-800 border-purple-200',
    chip: 'bg-purple-600',
  },
  ptw_request: {
    label: 'Permit to Work',
    icon: ShieldAlert,
    tone: 'bg-amber-50 text-amber-800 border-amber-200',
    chip: 'bg-amber-600',
  },
  parts_request: {
    label: 'Parts requests',
    icon: Package,
    tone: 'bg-blue-50 text-blue-800 border-blue-200',
    chip: 'bg-blue-600',
  },
};

const ALL_KINDS = Object.keys(KIND_META);

export default function PendingReviewPanel() {
  const navigate = useNavigate();
  const [counts, setCounts] = useState({ total: 0, by_kind: {} });
  const [items, setItems] = useState([]);
  const [filter, setFilter] = useState('all');
  const [loading, setLoading] = useState(true);
  const [busyIds, setBusyIds] = useState(new Set());
  const [rejecting, setRejecting] = useState(null); // {id, kind, reject_url}
  const [rejectReason, setRejectReason] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [list, c] = await Promise.all([
        axios.get(`${API}/api/master-admin/pending-review`, {
          ...auth(),
          params: { limit: 100, ...(filter !== 'all' ? { kind: filter } : {}) },
        }),
        axios.get(`${API}/api/master-admin/pending-review/count`, auth()),
      ]);
      setItems(list.data?.items || []);
      setCounts(c.data || { total: 0, by_kind: {} });
    } catch (e) {
      notify.error('Could not load queue', e?.response?.data?.detail || e?.message);
    } finally { setLoading(false); }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  const markBusy = (id, on) => {
    setBusyIds((prev) => {
      const next = new Set(prev);
      if (on) next.add(id); else next.delete(id);
      return next;
    });
  };

  const approve = async (row) => {
    if (!row.approve_url) return;
    markBusy(row.id, true);
    try {
      const url = `${API}${row.approve_url}`;
      await axios.post(url, {}, auth());
      notify.success('Approved', row.title);
      setItems((prev) => prev.filter((r) => r.id !== row.id));
      // Optimistic count update.
      setCounts((c) => ({
        ...c,
        total: Math.max(0, c.total - 1),
        by_kind: { ...c.by_kind, [row.kind]: Math.max(0, (c.by_kind[row.kind] || 0) - 1) },
      }));
    } catch (e) {
      notify.error('Approve failed', e?.response?.data?.detail || e?.message);
    } finally { markBusy(row.id, false); }
  };

  const submitReject = async () => {
    if (!rejecting?.reject_url) return;
    const reason = rejectReason.trim();
    if (!reason) {
      notify.error('Reason required', 'Please tell the requester why.');
      return;
    }
    markBusy(rejecting.id, true);
    try {
      const url = `${API}${rejecting.reject_url}`;
      await axios.post(url, { reason }, auth());
      notify.success('Rejected', rejecting.title);
      setItems((prev) => prev.filter((r) => r.id !== rejecting.id));
      setCounts((c) => ({
        ...c,
        total: Math.max(0, c.total - 1),
        by_kind: { ...c.by_kind, [rejecting.kind]: Math.max(0, (c.by_kind[rejecting.kind] || 0) - 1) },
      }));
      setRejecting(null);
      setRejectReason('');
    } catch (e) {
      notify.error('Reject failed', e?.response?.data?.detail || e?.message);
    } finally { markBusy(rejecting?.id, false); }
  };

  const filteredItems = useMemo(
    () => (filter === 'all' ? items : items.filter((r) => r.kind === filter)),
    [items, filter],
  );

  return (
    <div className="p-6 space-y-5" data-testid="pending-review-panel">
      <header className="flex flex-wrap items-end gap-3 justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <AlertCircle size={22} className="text-amber-600" /> Pending review
            <span
              className="ml-2 inline-flex items-center justify-center px-2.5 py-0.5 rounded-full bg-rose-600 text-white text-xs font-bold"
              data-testid="pending-review-total"
            >
              {counts.total}
            </span>
          </h1>
          <p className="text-sm text-slate-500">
            Items across the platform that need Master-Admin action. Approve / Reject inline.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={load}
          disabled={loading}
          data-testid="pending-review-refresh"
        >
          {loading ? <Loader2 size={14} className="animate-spin mr-1.5" /> : <RefreshCw size={14} className="mr-1.5" />}
          Refresh
        </Button>
      </header>

      {/* Filter tabs */}
      <div className="flex flex-wrap gap-1.5" data-testid="pending-review-filters">
        <FilterChip
          label={`All (${counts.total})`}
          active={filter === 'all'}
          onClick={() => setFilter('all')}
          testId="pending-review-filter-all"
        />
        {ALL_KINDS.map((k) => {
          const meta = KIND_META[k];
          const n = counts.by_kind?.[k] || 0;
          return (
            <FilterChip
              key={k}
              label={`${meta.label} (${n})`}
              icon={meta.icon}
              active={filter === k}
              onClick={() => setFilter(k)}
              testId={`pending-review-filter-${k}`}
            />
          );
        })}
      </div>

      {loading ? (
        <div className="py-12 flex items-center justify-center text-slate-400">
          <Loader2 size={20} className="animate-spin" />
        </div>
      ) : filteredItems.length === 0 ? (
        <div
          className="py-16 text-center text-slate-500"
          data-testid="pending-review-empty"
        >
          <Check size={28} className="inline text-emerald-500" />
          <p className="mt-2 text-sm">Nothing pending — you're all caught up.</p>
        </div>
      ) : (
        <ul className="space-y-2" data-testid="pending-review-list">
          {filteredItems.map((row) => (
            <ReviewRow
              key={`${row.kind}-${row.id}`}
              row={row}
              busy={busyIds.has(row.id)}
              onApprove={() => approve(row)}
              onReject={() => { setRejecting(row); setRejectReason(''); }}
              onOpen={() => navigate(row.link)}
            />
          ))}
        </ul>
      )}

      {rejecting && (
        <RejectModal
          row={rejecting}
          value={rejectReason}
          setValue={setRejectReason}
          onClose={() => { setRejecting(null); setRejectReason(''); }}
          onSubmit={submitReject}
        />
      )}
    </div>
  );
}

function FilterChip({ label, icon: Icon, active, onClick, testId }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold transition-colors ${
        active
          ? 'bg-slate-900 text-white'
          : 'bg-white text-slate-700 border border-slate-200 hover:bg-slate-50'
      }`}
      data-testid={testId}
    >
      {Icon && <Icon size={12} />}
      {label}
    </button>
  );
}

function ReviewRow({ row, busy, onApprove, onReject, onOpen }) {
  const meta = KIND_META[row.kind] || {};
  const Icon = meta.icon || AlertCircle;
  const created = row.created_at
    ? new Date(row.created_at).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
    : '';
  return (
    <li
      className={`rounded-2xl border bg-white p-3 flex items-start gap-3 ${meta.tone || ''}`}
      data-testid={`pending-review-row-${row.id}`}
    >
      <div className={`w-9 h-9 rounded-full ${meta.chip || 'bg-slate-600'} text-white flex items-center justify-center flex-shrink-0`}>
        <Icon size={14} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-bold text-slate-900 truncate">{row.title}</p>
        {row.subtitle ? <p className="text-xs text-slate-500 truncate">{row.subtitle}</p> : null}
        <p className="text-[10px] text-slate-400 mt-0.5">
          {created}
          {row.organization_name ? ` · ${row.organization_name}` : ''}
        </p>
      </div>
      <div className="flex items-center gap-1 flex-shrink-0">
        <Button
          variant="outline"
          size="sm"
          onClick={onOpen}
          data-testid={`pending-review-open-${row.id}`}
          title="Open detail"
        >
          <ExternalLink size={13} />
        </Button>
        {row.approve_url && (
          <Button
            size="sm"
            onClick={onApprove}
            disabled={busy}
            className="bg-emerald-600 hover:bg-emerald-700 text-white"
            data-testid={`pending-review-approve-${row.id}`}
          >
            {busy ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />}
            <span className="ml-1 hidden sm:inline">Approve</span>
          </Button>
        )}
        {row.reject_url && (
          <Button
            size="sm"
            variant="outline"
            onClick={onReject}
            disabled={busy}
            className="border-rose-200 text-rose-700 hover:bg-rose-50"
            data-testid={`pending-review-reject-${row.id}`}
          >
            <X size={13} />
            <span className="ml-1 hidden sm:inline">Reject</span>
          </Button>
        )}
      </div>
    </li>
  );
}

function RejectModal({ row, value, setValue, onClose, onSubmit }) {
  return (
    <div
      className="fixed inset-0 z-50 bg-slate-900/60 flex items-end sm:items-center justify-center p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      data-testid="pending-review-reject-modal"
    >
      <div className="w-full max-w-md bg-white rounded-2xl shadow-xl p-5">
        <p className="text-sm font-bold text-slate-900 mb-1">Reject?</p>
        <p className="text-xs text-slate-500 mb-3 truncate">{row.title}</p>
        <textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          rows={3}
          maxLength={400}
          placeholder="Reason (shown to the requester)"
          className="w-full px-3 py-2 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-rose-500"
          data-testid="pending-review-reject-reason"
        />
        <div className="mt-3 flex items-center justify-end gap-2">
          <Button variant="outline" size="sm" onClick={onClose}>Cancel</Button>
          <Button
            size="sm"
            onClick={onSubmit}
            className="bg-rose-600 hover:bg-rose-700 text-white"
            data-testid="pending-review-reject-submit"
          >
            Reject
          </Button>
        </div>
      </div>
    </div>
  );
}
