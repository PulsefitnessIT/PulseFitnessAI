/**
 * EngineerRosterPanel — iter 216h78.
 *
 * Sits inside the customer Service Desk between LiveEngineersPanel and
 * the Filters/Cases stack. Lets a gym (the customer) GRANT specific
 * engineers access to the Engineer App without forcing those engineers
 * to subscribe to the £30/mo Partner Plan — covers the ad-hoc / one-off
 * contractor flow promised in iter 216h75.
 *
 * Endpoints (backend already shipped in h77):
 *   GET    /api/customer-engineer-grants
 *   POST   /api/customer-engineer-grants     {engineer_email, case_ids[], scope, note}
 *   DELETE /api/customer-engineer-grants/{id}
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  UserPlus, Trash2, Loader2, ShieldCheck, X, CheckCircle2, ChevronDown,
  ChevronUp, Mail, Sparkles,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';

function auth() {
  const t = localStorage.getItem('token');
  return { headers: t ? { Authorization: `Bearer ${t}` } : {} };
}

export default function EngineerRosterPanel({ onChange }) {
  const [grants, setGrants] = useState([]);
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [form, setForm] = useState({ engineer_email: '', case_ids: '', scope: 'org_wide', note: '' });
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/customer-engineer-grants`, auth());
      setGrants(r.data?.grants || []);
    } catch {
      /* tolerated */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const submit = async (e) => {
    e?.preventDefault?.();
    if (!form.engineer_email.trim() || !form.engineer_email.includes('@')) {
      notify.error('Enter a valid engineer email');
      return;
    }
    setBusy(true);
    try {
      const payload = {
        engineer_email: form.engineer_email.trim().toLowerCase(),
        case_ids: form.case_ids.split(',').map((s) => s.trim()).filter(Boolean),
        scope: form.scope,
        note: form.note.trim() || undefined,
      };
      await axios.post(`${API}/customer-engineer-grants`, payload, auth());
      notify.success(`${payload.engineer_email} can now access the Engineer App for ${payload.scope === 'org_wide' ? 'all your jobs' : `${payload.case_ids.length} job(s)`}`);
      setForm({ engineer_email: '', case_ids: '', scope: 'org_wide', note: '' });
      setAddOpen(false);
      await load();
      onChange?.();
    } catch (err) {
      notifyApiError(notify, err, 'Could not grant access');
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (g) => {
    if (!window.confirm(`Revoke ${g.engineer_email}'s access? They'll lose the Engineer App immediately for jobs under your gym (unless they have their own subscription).`)) return;
    setBusy(true);
    try {
      await axios.delete(`${API}/customer-engineer-grants/${g.id}`, auth());
      notify.success(`Access revoked for ${g.engineer_email}`);
      await load();
      onChange?.();
    } catch (err) {
      notifyApiError(notify, err, 'Revoke failed');
    } finally {
      setBusy(false);
    }
  };

  const activeGrants = useMemo(() => grants.filter((g) => g.active), [grants]);
  const revokedGrants = useMemo(() => grants.filter((g) => !g.active), [grants]);

  return (
    <div className="svc-section" data-testid="engineer-roster-panel">
      <div className="svc-section-head">
        <div className="flex items-center gap-1.5 text-xs font-bold svc-muted">
          <ShieldCheck size={13} /> Engineer roster
          <span className="ml-1 px-1.5 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-200 text-[9px] font-bold uppercase tracking-wider"
            data-testid="engineer-roster-count">
            {activeGrants.length} active
          </span>
        </div>
        <button
          onClick={() => setAddOpen((v) => !v)}
          className="svc-btn-sm svc-btn-primary"
          data-testid="engineer-roster-add-toggle"
        >
          {addOpen ? <><X size={11} /> Cancel</> : <><UserPlus size={11} /> Add engineer</>}
        </button>
      </div>

      {addOpen && (
        <form onSubmit={submit} className="rounded-lg border border-dashed border-zinc-200 dark:border-zinc-700 p-3 my-2 grid grid-cols-1 sm:grid-cols-2 gap-2"
          data-testid="engineer-roster-add-form">
          <label className="block sm:col-span-2">
            <span className="text-[10px] uppercase tracking-wider font-bold svc-muted">Engineer email *</span>
            <div className="relative mt-1">
              <Mail size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 svc-muted" />
              <input
                type="email" autoFocus required
                value={form.engineer_email}
                onChange={(e) => setForm((f) => ({ ...f, engineer_email: e.target.value }))}
                placeholder="engineer@theirbusiness.com"
                className="svc-input w-full pl-8"
                data-testid="engineer-roster-email"
              />
            </div>
            <p className="text-[10px] svc-muted mt-1">They must already have a GymAxis account — if not, ask them to register first.</p>
          </label>

          <label className="block">
            <span className="text-[10px] uppercase tracking-wider font-bold svc-muted">Scope</span>
            <select
              value={form.scope}
              onChange={(e) => setForm((f) => ({ ...f, scope: e.target.value }))}
              className="svc-select mt-1 w-full"
              data-testid="engineer-roster-scope"
            >
              <option value="org_wide">All jobs at our gym</option>
              <option value="per_case">Specific jobs only</option>
            </select>
          </label>

          <label className="block">
            <span className="text-[10px] uppercase tracking-wider font-bold svc-muted">
              Case IDs {form.scope === 'per_case' ? '*' : '(optional)'}
            </span>
            <input
              type="text"
              value={form.case_ids}
              onChange={(e) => setForm((f) => ({ ...f, case_ids: e.target.value }))}
              placeholder="case-id-1, case-id-2"
              className="svc-input w-full mt-1"
              data-testid="engineer-roster-cases"
            />
          </label>

          <label className="block sm:col-span-2">
            <span className="text-[10px] uppercase tracking-wider font-bold svc-muted">Internal note (optional)</span>
            <input
              type="text"
              value={form.note}
              onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))}
              placeholder="e.g. Approved by Sarah on 13/02, ad-hoc cardio repair contractor"
              className="svc-input w-full mt-1"
              data-testid="engineer-roster-note"
            />
          </label>

          <div className="sm:col-span-2 flex items-center justify-between gap-2 mt-1">
            <p className="text-[10px] svc-muted flex items-start gap-1">
              <Sparkles size={10} className="mt-0.5 shrink-0 opacity-70" />
              <span>Grants are free for your gym. They unlock the Engineer App for this contractor without them needing a Partner Plan subscription.</span>
            </p>
            <button type="submit" disabled={busy} className="svc-btn-sm svc-btn-primary" data-testid="engineer-roster-submit">
              {busy ? <Loader2 size={11} className="animate-spin" /> : <CheckCircle2 size={11} />}
              Grant access
            </button>
          </div>
        </form>
      )}

      {loading ? (
        <p className="text-xs svc-muted py-3 inline-flex items-center gap-1.5">
          <Loader2 size={11} className="animate-spin" /> Loading roster…
        </p>
      ) : activeGrants.length === 0 ? (
        <p className="text-xs svc-muted py-3" data-testid="engineer-roster-empty">
          No engineers granted access yet. Click <strong>Add engineer</strong> to give an ad-hoc contractor access to the Engineer App for your gym's jobs.
        </p>
      ) : (
        <ul className="space-y-2 mt-2">
          {activeGrants.map((g) => (
            <li key={g.id}
              className="flex items-center justify-between gap-2 rounded-lg border border-zinc-200 dark:border-zinc-800 px-3 py-2 bg-white dark:bg-zinc-900"
              data-testid={`engineer-roster-row-${g.id}`}>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-bold truncate">{g.engineer_name || g.engineer_email}</div>
                <div className="text-[11px] svc-muted truncate">
                  {g.engineer_email}{g.scope === 'per_case'
                    ? <> · {g.case_ids?.length || 0} job{g.case_ids?.length === 1 ? '' : 's'}</>
                    : ' · all jobs'}
                  {g.note ? ` · ${g.note}` : ''}
                </div>
              </div>
              <button onClick={() => revoke(g)} disabled={busy}
                className="svc-btn-sm"
                style={{ background: 'transparent', border: '1px solid #fecaca', color: '#b91c1c', display: 'inline-flex', alignItems: 'center', gap: 4 }}
                data-testid={`engineer-roster-revoke-${g.id}`}>
                <Trash2 size={10} /> Revoke
              </button>
            </li>
          ))}
        </ul>
      )}

      {revokedGrants.length > 0 && (
        <details className="mt-3 text-xs" data-testid="engineer-roster-revoked-history">
          <summary className="cursor-pointer svc-muted inline-flex items-center gap-1">
            <ChevronDown size={11} /> {revokedGrants.length} revoked grant{revokedGrants.length === 1 ? '' : 's'} (history)
          </summary>
          <ul className="mt-1.5 space-y-1 pl-4">
            {revokedGrants.slice(0, 10).map((g) => (
              <li key={g.id} className="svc-muted truncate" data-testid={`engineer-roster-revoked-${g.id}`}>
                {g.engineer_email} · revoked {g.revoked_at ? new Date(g.revoked_at).toLocaleDateString() : '—'}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
