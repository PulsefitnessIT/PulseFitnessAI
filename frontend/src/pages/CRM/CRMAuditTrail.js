/**
 * CRMAuditTrail — iter 215dd.
 *
 * Reusable "Who changed what, when" timeline. Fetches
 * GET /api/crm/audit?entity_type=X&entity_id=Y and renders each
 * entry with the actor, summary, relative time, and (for updates)
 * a small field-by-field diff list.
 *
 * Usage:
 *   <CRMAuditTrail entityType="contact" entityId={id} />
 *   <CRMAuditTrail /> // Org-wide recent stream when no entity passed.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Shield, UserCircle2, Plus, Pencil, Trash2, GitBranch, FileSignature, CheckCircle2 } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('crm_token') || localStorage.getItem('token') || ''}` } });

const ACTION_ICONS = {
  create: Plus,
  update: Pencil,
  delete: Trash2,
  stage_change: GitBranch,
  sign: FileSignature,
  approve: CheckCircle2,
};

const ACTION_COLORS = {
  create: 'var(--color-success-green, #10b981)',
  update: 'var(--color-brand-blue, #1d4ed8)',
  delete: 'var(--color-danger-red, #ef4444)',
  stage_change: 'var(--color-info-ios, #3b82f6)',
  sign: 'var(--color-accent-indigo, #6366f1)',
  approve: 'var(--color-accent-magenta, #d946ef)',
};

function formatRelative(iso) {
  if (!iso) return '';
  const then = new Date(iso).getTime();
  const now = Date.now();
  const secs = Math.max(0, Math.floor((now - then) / 1000));
  if (secs < 60) return `${secs}s ago`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  const days = Math.floor(secs / 86400);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

function renderValue(v) {
  if (v === null || v === undefined || v === '') return <span className="italic opacity-60">empty</span>;
  if (typeof v === 'boolean') return v ? 'Yes' : 'No';
  if (Array.isArray(v)) return v.length === 0 ? <span className="italic opacity-60">empty</span> : v.join(', ');
  if (typeof v === 'object') return <code className="text-[10px]">{JSON.stringify(v).slice(0, 80)}</code>;
  const s = String(v);
  return s.length > 80 ? `${s.slice(0, 77)}…` : s;
}

export default function CRMAuditTrail({ entityType = '', entityId = '', limit = 50, emptyText = 'No audit entries yet.' }) {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams();
      if (entityType) params.set('entity_type', entityType);
      if (entityId) params.set('entity_id', entityId);
      params.set('limit', String(limit));
      const path = (entityType || entityId) ? `/crm/audit?${params.toString()}` : `/crm/audit/recent?limit=${limit}`;
      const r = await axios.get(`${API}${path}`, auth());
      setEntries(r.data.entries || []);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Unable to load audit trail');
    } finally {
      setLoading(false);
    }
  }, [entityType, entityId, limit]);

  useEffect(() => { load(); }, [load]);

  const visible = useMemo(() => entries, [entries]);

  if (loading) return <p className="text-sm text-[color:var(--theme-text-muted,#6b7280)]" data-testid="audit-loading">Loading audit trail…</p>;
  if (error) return <p className="text-sm text-red-500" data-testid="audit-error">{error}</p>;
  if (!visible.length) {
    return (
      <div className="rounded-lg border border-dashed p-6 text-center" style={{ borderColor: 'var(--theme-border, #e5e7eb)' }} data-testid="audit-empty">
        <Shield size={20} className="mx-auto mb-2 opacity-40" />
        <p className="text-sm opacity-70">{emptyText}</p>
      </div>
    );
  }

  return (
    <div className="space-y-3" data-testid="audit-trail">
      {visible.map((e, i) => {
        const Icon = ACTION_ICONS[e.action] || Shield;
        const colour = ACTION_COLORS[e.action] || 'var(--color-brand-blue, #1d4ed8)';
        const hasChanges = Array.isArray(e.changes) && e.changes.length > 0;
        return (
          <div key={e.id || i} className="flex gap-3 relative" data-testid={`audit-entry-${e.id || i}`}>
            {i < visible.length - 1 ? (
              <div className="absolute left-4 top-8 bottom-0 w-px" style={{ background: 'var(--theme-border, #e5e7eb)' }} />
            ) : null}
            <div
              className="h-8 w-8 rounded-full flex items-center justify-center shrink-0 z-10"
              style={{ background: colour, color: 'white' }}
            >
              <Icon size={14} />
            </div>
            <div className="flex-1 min-w-0 pb-2">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                <p className="text-sm font-semibold" style={{ color: 'var(--theme-text, #111827)' }}>
                  {e.summary}
                </p>
                <span className="text-[11px] opacity-60">{formatRelative(e.at)}</span>
              </div>
              <div className="flex items-center gap-1.5 mt-0.5 text-[11px] opacity-70">
                <UserCircle2 size={11} />
                <span>{e.actor_name || e.actor_email || 'Unknown'}</span>
                {e.actor_email && e.actor_email !== e.actor_name ? (
                  <span className="opacity-60">· {e.actor_email}</span>
                ) : null}
              </div>
              {hasChanges ? (
                <div className="mt-2 rounded-md border p-2 text-[11px] space-y-1" style={{ borderColor: 'var(--theme-border, #e5e7eb)', background: 'var(--theme-surface, transparent)' }}>
                  {e.changes.slice(0, 8).map((ch, k) => (
                    <div key={k} className="flex items-baseline gap-2 flex-wrap" data-testid={`audit-change-${ch.field}`}>
                      <span className="font-semibold min-w-[7rem] opacity-80">{ch.field}</span>
                      <span className="line-through opacity-60">{renderValue(ch.before)}</span>
                      <span className="opacity-60">→</span>
                      <span className="font-medium">{renderValue(ch.after)}</span>
                    </div>
                  ))}
                  {e.changes.length > 8 ? (
                    <p className="italic opacity-60">+{e.changes.length - 8} more change(s)</p>
                  ) : null}
                </div>
              ) : null}
            </div>
          </div>
        );
      })}
    </div>
  );
}
