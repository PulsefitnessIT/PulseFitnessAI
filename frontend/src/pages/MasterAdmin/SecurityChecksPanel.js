/**
 * SecurityChecksPanel
 * --------------------
 *
 * Sub-tab inside Master Admin → Trust & Reliability that surfaces:
 *  1. The curated build-hardening timeline (every security control we
 *     deliberately added during the build) — what an auditor wants.
 *  2. The most recent live audit events from `security_audit_log` —
 *     what the on-call operator wants.
 *
 * Visible to both Pulse Fitness and Pulse Fitness master admins (the backend
 * checks `platform_role == "master_admin"` regardless of brand).
 */
import { useEffect, useState, useMemo } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  ShieldCheck, Lock, Database, Server, Gauge, FileCheck, AlertTriangle,
  Loader2, Activity, Download,
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

// One Lucide icon per build-checks category — keeps the timeline scannable.
const CATEGORY_ICONS = {
  auth:        Lock,
  data:        Database,
  ops:         Server,
  scale:       Gauge,
  code:        FileCheck,
  integration: ShieldCheck,
  review:      AlertTriangle,
};

const STATUS_BADGES = {
  passed:  { label: 'Passed',     bg: 'bg-emerald-100', fg: 'text-emerald-800', ring: 'ring-emerald-300' },
  partial: { label: 'Partial',    bg: 'bg-amber-100',   fg: 'text-amber-800',   ring: 'ring-amber-300' },
  review:  { label: 'In review',  bg: 'bg-blue-100',    fg: 'text-blue-800',    ring: 'ring-blue-300' },
};

const CATEGORY_LABELS = {
  auth: 'Authentication', data: 'Data protection', ops: 'Operations',
  scale: 'Scale & performance', code: 'Code quality', integration: 'Integrations',
  review: 'External review',
};


function CategoryFilterPill({ id, count, active, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-3 py-1.5 rounded-full text-xs font-bold border transition ${
        active
          ? 'bg-[var(--color-brand-blue)] text-white border-[var(--color-brand-blue)]'
          : 'bg-white text-zinc-700 border-zinc-200 hover:border-[rgb(var(--rgb-brand-blue)/0.4)]'
      }`}
      data-testid={`sec-cat-${id}`}
    >
      {CATEGORY_LABELS[id] || id} <span className="opacity-60 ml-1">({count})</span>
    </button>
  );
}


function CheckCard({ check }) {
  const Icon = CATEGORY_ICONS[check.category] || ShieldCheck;
  const status = STATUS_BADGES[check.status] || STATUS_BADGES.passed;
  return (
    <div
      className="rounded-xl border border-zinc-200 bg-white p-4 hover:border-[rgb(var(--rgb-brand-blue)/0.4)] transition"
      data-testid={`sec-check-${check.id}`}
    >
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[rgb(var(--rgb-brand-blue)/0.1)]">
          <Icon size={18} className="text-[var(--color-brand-blue)]" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`text-[10px] uppercase tracking-wide font-bold px-2 py-0.5 rounded ${status.bg} ${status.fg} ring-1 ${status.ring}`}>
              {status.label}
            </span>
            <code className="text-[10px] text-zinc-400 font-mono">{check.date}</code>
            <code className="text-[10px] text-zinc-400 font-mono">· {check.category}</code>
          </div>
          <p className="mt-1.5 text-sm font-bold text-zinc-900">{check.title}</p>
          <p className="mt-1 text-xs text-zinc-600 leading-relaxed">{check.description}</p>
          {check.evidence?.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {check.evidence.map((e, i) => (
                <code key={i} className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-zinc-100 text-zinc-600">{e}</code>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}


function AuditRow({ ev }) {
  // security_audit_log rows are already _id-stripped by the backend.
  const ts = ev.ts || ev.created_at || ev.timestamp;
  return (
    <div className="flex items-start gap-3 py-2 border-b border-zinc-100 last:border-b-0" data-testid={`sec-audit-${ev.id || ts}`}>
      <Activity size={14} className="text-zinc-400 mt-0.5 shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <code className="text-[11px] font-mono text-zinc-700 font-bold">{ev.event || ev.type || 'event'}</code>
          {ev.organization_id && (
            <span className="text-[10px] text-zinc-400">org · {String(ev.organization_id).slice(0, 8)}</span>
          )}
        </div>
        {ts && <p className="text-[10px] text-zinc-400 mt-0.5">{new Date(ts).toLocaleString('en-GB')}</p>}
      </div>
    </div>
  );
}


export default function SecurityChecksPanel() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');

  useEffect(() => {
    const hdr = { headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } };
    axios.get(`${API}/api/master-admin/security-checks`, hdr)
      .then(r => setData(r.data))
      .finally(() => setLoading(false));
  }, []);

  const visibleChecks = useMemo(() => {
    if (!data) return [];
    if (filter === 'all') return data.build_checks;
    return data.build_checks.filter(c => c.category === filter);
  }, [data, filter]);

  if (loading) {
    return (
      <div className="p-8 text-center text-zinc-500 flex items-center justify-center gap-2" data-testid="sec-loading">
        <Loader2 size={16} className="animate-spin" /> Loading security checks…
      </div>
    );
  }
  if (!data) return null;

  const handleDownloadPdf = () => {
    // Use fetch + blob so we attach the auth header — a plain anchor would
    // hit the endpoint without it and be redirected to login.
    fetch(`${API}/api/master-admin/security-checks/export.pdf`, {
      headers: { Authorization: `Bearer ${localStorage.getItem('token')}` },
    })
      .then((r) => r.blob())
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `gymaxis-security-controls-${new Date().toISOString().slice(0, 10)}.pdf`;
        a.click();
        URL.revokeObjectURL(url);
      });
  };

  const categories = Object.keys(data.summary.by_category || {});

  return (
    <div className="space-y-6" data-testid="security-checks-panel">
      {/* Summary tiles */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="p-5" data-testid="sec-tile-total">
          <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Total checks</p>
          <p className="mt-2 text-3xl font-bold text-zinc-900">{data.summary.total}</p>
        </Card>
        <Card className="p-5 border-l-4 border-emerald-500" data-testid="sec-tile-passed">
          <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Passed</p>
          <p className="mt-2 text-3xl font-bold text-emerald-700">{data.summary.passed}</p>
        </Card>
        <Card className="p-5 border-l-4 border-blue-500" data-testid="sec-tile-review">
          <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">In review</p>
          <p className="mt-2 text-3xl font-bold text-blue-700">{data.summary.review}</p>
        </Card>
        <Card className="p-5" data-testid="sec-tile-audit">
          <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Live audit events</p>
          <p className="mt-2 text-3xl font-bold text-zinc-900">{data.audit_events.length}</p>
          <p className="mt-1 text-[11px] text-zinc-500">last 24h</p>
        </Card>
      </div>

      {/* Category filter pills */}
      <div className="flex items-center gap-2 flex-wrap" data-testid="sec-category-filter">
        <CategoryFilterPill id="all" count={data.build_checks.length} active={filter === 'all'} onClick={() => setFilter('all')} />
        {categories.map(cat => (
          <CategoryFilterPill
            key={cat}
            id={cat}
            count={data.summary.by_category[cat]}
            active={filter === cat}
            onClick={() => setFilter(cat)}
          />
        ))}
        <div className="ml-auto">
          <button
            type="button"
            onClick={handleDownloadPdf}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold bg-[var(--color-brand-blue)] text-white hover:bg-[var(--color-brand-blue-hover)] transition"
            data-testid="sec-download-pdf"
            title="Download as PDF — share with auditors / pen-testers / prospects"
          >
            <Download size={12} /> Download PDF
          </button>
        </div>
      </div>

      {/* Build-hardening timeline */}
      <Card className="p-5" data-testid="sec-build-timeline">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="text-sm font-bold uppercase tracking-wide text-zinc-700">Build hardening timeline</h3>
            <p className="text-xs text-zinc-500 mt-0.5">Curated record of every security control we deliberately added during the build.</p>
          </div>
          <Badge variant="outline" className="text-xs">{visibleChecks.length} shown</Badge>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {visibleChecks.map(c => <CheckCard key={c.id} check={c} />)}
        </div>
      </Card>

      {/* Live audit feed */}
      <Card className="p-5" data-testid="sec-audit-feed">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="text-sm font-bold uppercase tracking-wide text-zinc-700">Live audit events</h3>
            <p className="text-xs text-zinc-500 mt-0.5">From <code className="text-[10px]">security_audit_log</code> — supplier tokens issued, MFA challenges, password resets, role changes, etc.</p>
          </div>
          <Badge variant="outline" className="text-xs">{data.audit_events.length}</Badge>
        </div>
        {data.audit_events.length === 0 ? (
          <div className="py-8 text-center text-zinc-500 text-sm" data-testid="sec-audit-empty">
            No audit events recorded yet. Sensitive runtime actions will appear here as they happen.
          </div>
        ) : (
          <div className="divide-y divide-zinc-100">
            {data.audit_events.slice(0, 50).map((ev, i) => <AuditRow key={i} ev={ev} />)}
          </div>
        )}
      </Card>
    </div>
  );
}
