/**
 * Outbound Emails — Master Admin → Growth (Iter 216h99).
 *
 * Every email the platform sends — sales-enquiry notifications,
 * Communications Inbox replies, signup welcomes, password resets,
 * service-report PDFs, payment receipts, supplier POs — is captured
 * in ``email_send_events`` by ``utils.email.send_email`` and surfaced
 * here.
 *
 * Filters: status (all / sent / failed), free-text search. Rolling 24h
 * counts in the header mirror the global "Email" health pill.
 */
import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import {
  Mail, RefreshCw, Search, CheckCircle2, AlertTriangle, ChevronDown,
} from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

function authHeader() {
  const token = localStorage.getItem('token') || localStorage.getItem('gymaxis_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function relativeTime(iso) {
  if (!iso) return '—';
  const diff = Math.max(0, Date.now() - new Date(iso).getTime());
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d}d ago`;
  return new Date(iso).toLocaleDateString();
}

export default function AdminEmails() {
  const [data, setData] = useState({ items: [], sent_24h: 0, failed_24h: 0, total_all_time: 0, sender: '' });
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState('all');   // all | sent | failed
  const [search, setSearch] = useState('');
  const [expandedId, setExpandedId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { limit: 200 };
      if (status !== 'all') params.status = status;
      if (search.trim()) params.search = search.trim();
      const r = await axios.get(`${API}/master-admin/emails`, { params, headers: authHeader() });
      setData(r.data || { items: [] });
    } catch (e) {
      toast.error('Failed to load outbound emails');
    } finally {
      setLoading(false);
    }
  }, [status, search]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-5" data-testid="admin-emails">
      <Header data={data} loading={loading} onRefresh={load} />
      <FiltersBar status={status} setStatus={setStatus} search={search} setSearch={setSearch} />
      <ListView items={data.items} expandedId={expandedId} setExpandedId={setExpandedId} />
    </div>
  );
}

function Header({ data, loading, onRefresh }) {
  const total24 = (data.sent_24h || 0) + (data.failed_24h || 0);
  const failPct = total24 > 0 ? Math.round((data.failed_24h / total24) * 100) : 0;
  const healthy = total24 === 0 || data.failed_24h === 0;
  return (
    <div className="bg-white border border-zinc-200 rounded-2xl p-5 shadow-sm">
      <div className="flex items-center justify-between gap-4 mb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-blue-50">
            <Mail size={18} className="text-blue-600" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-zinc-900">Outbound emails</h2>
            <p className="text-xs text-zinc-500">
              Every email sent via Resend — sender: <code className="font-mono">{data.sender || '(unconfigured)'}</code>
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={loading}
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-zinc-700 hover:text-zinc-900 disabled:opacity-50"
          data-testid="emails-refresh"
        >
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Stat label="Sent (24h)"   value={data.sent_24h}      tone="green" />
        <Stat label="Failed (24h)" value={data.failed_24h}    tone={data.failed_24h > 0 ? 'red' : 'green'} />
        <Stat label="Failure rate" value={`${failPct}%`}      tone={healthy ? 'green' : 'amber'} />
        <Stat label="All-time"     value={data.total_all_time} tone="neutral" />
      </div>
    </div>
  );
}

function Stat({ label, value, tone }) {
  const colours = {
    green:   'bg-emerald-50 border-emerald-100 text-emerald-900',
    amber:   'bg-amber-50 border-amber-100 text-amber-900',
    red:     'bg-rose-50 border-rose-100 text-rose-900',
    neutral: 'bg-zinc-50 border-zinc-100 text-zinc-900',
  }[tone] || 'bg-zinc-50 border-zinc-100 text-zinc-900';
  return (
    <div className={`rounded-xl border px-3 py-2.5 ${colours}`}>
      <div className="text-[10px] uppercase tracking-[0.12em] font-bold opacity-70">{label}</div>
      <div className="text-xl font-bold tabular-nums">{value}</div>
    </div>
  );
}

const STATUS_TABS = [
  { id: 'all',    label: 'All' },
  { id: 'sent',   label: 'Sent' },
  { id: 'failed', label: 'Failed' },
];

function FiltersBar({ status, setStatus, search, setSearch }) {
  return (
    <div className="bg-white border border-zinc-200 rounded-2xl p-3 flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
      <div className="flex gap-2" role="tablist">
        {STATUS_TABS.map((t) => {
          const active = status === t.id;
          return (
            <button
              key={t.id}
              type="button"
              role="tab"
              onClick={() => setStatus(t.id)}
              className="inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-xs font-semibold border transition whitespace-nowrap hover:border-zinc-400"
              style={active
                ? { background: '#0F172A', color: '#FFFFFF', borderColor: '#0F172A' }
                : { background: '#FFFFFF', color: '#3F3F46', borderColor: '#E4E4E7' }
              }
              data-testid={`emails-tab-${t.id}`}
            >
              {t.label}
            </button>
          );
        })}
      </div>
      <div className="flex-1 relative">
        <Search size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-400" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by recipient, subject, sender, or error"
          className="w-full rounded-xl border border-zinc-200 bg-white pl-10 pr-3 py-2 text-sm focus:outline-none focus:border-zinc-400"
          data-testid="emails-search"
        />
      </div>
    </div>
  );
}

function ListView({ items, expandedId, setExpandedId }) {
  if (items.length === 0) {
    return (
      <div className="bg-white border border-zinc-200 rounded-2xl py-16 text-center" data-testid="emails-empty">
        <Mail size={36} className="mx-auto text-zinc-300" />
        <p className="mt-3 text-sm text-zinc-500">No emails match this filter. Try widening the search.</p>
      </div>
    );
  }
  return (
    <div className="bg-white border border-zinc-200 rounded-2xl overflow-hidden">
      <div className="divide-y divide-zinc-100" data-testid="emails-list">
        {items.map((e, i) => {
          const sent = e.status === 'sent';
          const open = expandedId === i;
          const id = `${e.created_at}-${i}`;
          return (
            <div key={id} className="px-5 py-3.5">
              <button
                type="button"
                onClick={() => setExpandedId(open ? null : i)}
                className="w-full text-left flex items-start gap-4 hover:bg-zinc-50/50 -mx-2 px-2 py-1 rounded-lg"
                data-testid={`emails-row-${i}`}
              >
                <div className={`w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 ${sent ? 'bg-emerald-50' : 'bg-rose-50'}`}>
                  {sent
                    ? <CheckCircle2 size={13} className="text-emerald-600" />
                    : <AlertTriangle size={13} className="text-rose-600" />}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-zinc-900 truncate">{e.subject || '(no subject)'}</p>
                  <p className="text-xs text-zinc-500 truncate">
                    To: <span className="text-zinc-700">{e.to || '—'}</span>
                    {e.sender && <> · From: <span className="font-mono text-zinc-500">{e.sender}</span></>}
                  </p>
                </div>
                <div className="flex flex-col items-end gap-1 flex-shrink-0">
                  <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${sent ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-rose-50 text-rose-700 border-rose-200'}`}>
                    {sent ? 'Sent' : 'Failed'}
                  </span>
                  <span className="text-[10px] text-zinc-400">{relativeTime(e.created_at)}</span>
                </div>
                <ChevronDown size={14} className={`text-zinc-300 transition-transform ${open ? 'rotate-180' : ''}`} />
              </button>
              {open && (
                <div className="mt-2 ml-11 rounded-lg bg-zinc-50/60 border border-zinc-100 p-3 text-xs text-zinc-700 space-y-1.5" data-testid={`emails-detail-${i}`}>
                  <div><strong className="text-zinc-500 font-semibold mr-2">Sent at:</strong>{e.created_at ? new Date(e.created_at).toLocaleString() : '—'}</div>
                  <div><strong className="text-zinc-500 font-semibold mr-2">To:</strong>{e.to || '—'}</div>
                  <div><strong className="text-zinc-500 font-semibold mr-2">From:</strong><span className="font-mono">{e.sender || '—'}</span></div>
                  <div><strong className="text-zinc-500 font-semibold mr-2">Subject:</strong>{e.subject || '—'}</div>
                  {e.error && (
                    <div className="mt-2 rounded-md bg-rose-50 border border-rose-200 p-2 text-rose-800 font-mono text-[11px] break-all">
                      <strong className="font-semibold mr-1">Resend error:</strong>{e.error}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
