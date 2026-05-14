/**
 * Theme Settings Panel — Master Admin → Settings & Compliance (Iter 216h95).
 *
 * Two-pane layout:
 *   • Left  — Isolation audit. Two columns of design tokens (GymAxis +
 *             Pulse) side-by-side with a green status pill confirming
 *             namespace separation.
 *   • Right — Per-tenant overrides. Pick an organisation from a dropdown
 *             and tune their primary / accent / surface colours. Saves
 *             go to /api/master-admin/theme/orgs/{id}.
 *
 * The component is intentionally read-mostly. We don't ship a live theme
 * editor for the platform's default palette — that lives in source code
 * (CSS variable files) so it can be code-reviewed. The override flow is
 * the supported way to customise individual customer brands without a
 * deploy.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import {
  Palette, ShieldCheck, AlertTriangle, RefreshCw, Save, Eye, Building2,
} from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const OVERRIDE_FIELDS = [
  { key: 'primary',       label: 'Primary action',  placeholder: '#19CDFF' },
  { key: 'primary_hover', label: 'Primary hover',   placeholder: '#4DBFFF' },
  { key: 'accent',        label: 'Accent',          placeholder: '#10B981' },
  { key: 'surface',       label: 'Card surface',    placeholder: '#FFFFFF' },
  { key: 'text',          label: 'Body text',       placeholder: '#0A0C10' },
  { key: 'text_muted',    label: 'Muted text',      placeholder: '#52525B' },
  { key: 'border',        label: 'Border',          placeholder: '#E4E4E7' },
];

function authHeader() {
  const token = localStorage.getItem('token') || localStorage.getItem('gymaxis_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export default function ThemeSettingsPanel() {
  const [audit, setAudit] = useState(null);
  const [loading, setLoading] = useState(false);
  const [orgs, setOrgs] = useState([]);
  const [orgId, setOrgId] = useState('');
  const [orgTheme, setOrgTheme] = useState(null);
  const [draft, setDraft] = useState({});
  const [saving, setSaving] = useState(false);

  const loadAudit = useCallback(async () => {
    setLoading(true);
    try {
      const [a, o] = await Promise.all([
        axios.get(`${API}/master-admin/theme/audit`, { headers: authHeader() }),
        axios.get(`${API}/master-admin/organizations`, { headers: authHeader() }),
      ]);
      setAudit(a.data);
      const list = Array.isArray(o.data) ? o.data : (o.data?.organizations || o.data?.items || []);
      setOrgs(list.map((x) => ({ id: x.id, name: x.name, account_type: x.account_type })).filter((x) => x.id));
    } catch (e) {
      toast.error('Failed to load theme audit');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadAudit(); }, [loadAudit]);

  const loadOrg = useCallback(async (id) => {
    if (!id) { setOrgTheme(null); setDraft({}); return; }
    try {
      const r = await axios.get(`${API}/master-admin/theme/orgs/${id}`, { headers: authHeader() });
      setOrgTheme(r.data);
      setDraft({ ...(r.data?.theme_overrides || {}) });
    } catch (e) {
      toast.error('Failed to load tenant theme');
    }
  }, []);

  useEffect(() => { loadOrg(orgId); }, [orgId, loadOrg]);

  const save = async () => {
    if (!orgId) return;
    setSaving(true);
    try {
      const payload = {};
      OVERRIDE_FIELDS.forEach(({ key }) => {
        const cur = draft[key];
        if (cur != null) payload[key] = cur === '' ? '' : cur.toUpperCase();
      });
      const r = await axios.put(`${API}/master-admin/theme/orgs/${orgId}`, payload, { headers: authHeader() });
      setOrgTheme((t) => ({ ...(t || {}), theme_overrides: r.data?.theme_overrides || {} }));
      setDraft({ ...(r.data?.theme_overrides || {}) });
      toast.success('Tenant theme saved.');
    } catch (e) {
      const msg = e.response?.data?.detail || 'Save failed';
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  const clear = async () => {
    if (!orgId) return;
    setSaving(true);
    try {
      const payload = {};
      OVERRIDE_FIELDS.forEach(({ key }) => { payload[key] = ''; });
      await axios.put(`${API}/master-admin/theme/orgs/${orgId}`, payload, { headers: authHeader() });
      setDraft({});
      setOrgTheme((t) => ({ ...(t || {}), theme_overrides: {} }));
      toast.success('Overrides cleared.');
    } catch (e) {
      toast.error('Failed to clear overrides');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-5" data-testid="theme-settings-panel">
      <Header audit={audit} onRefresh={loadAudit} loading={loading} />
      <div className="grid lg:grid-cols-3 gap-5">
        <div className="lg:col-span-2 space-y-5">
          {audit?.namespaces?.map((ns) => (
            <NamespaceCard key={ns.id} ns={ns} />
          ))}
        </div>
        <OverridesCard
          orgs={orgs}
          orgId={orgId}
          setOrgId={setOrgId}
          orgTheme={orgTheme}
          draft={draft}
          setDraft={setDraft}
          onSave={save}
          onClear={clear}
          saving={saving}
        />
      </div>
    </div>
  );
}

function Header({ audit, onRefresh, loading }) {
  const ok = audit?.status === 'ok';
  return (
    <div className="bg-white border border-zinc-200 rounded-2xl p-5 shadow-sm">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-indigo-50">
            <Palette size={18} className="text-indigo-600" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-zinc-900">Theme settings & isolation audit</h2>
            <p className="text-xs text-zinc-500">GymAxis (marketing/admin) vs Pulse Fitness (operator) design tokens — separated by CSS namespace and verified here.</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold ${ok ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-amber-50 text-amber-800 border-amber-200'}`} data-testid="theme-audit-status">
            {ok ? <ShieldCheck size={12} /> : <AlertTriangle size={12} />}
            {ok ? 'Isolation OK' : 'Conflict detected'}
          </span>
          <button type="button" onClick={onRefresh} disabled={loading} className="inline-flex items-center gap-1.5 text-xs font-semibold text-zinc-700 hover:text-zinc-900 disabled:opacity-50" data-testid="theme-refresh">
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
        </div>
      </div>
      {audit?.overlap?.length > 0 && (
        <div className="mt-4 rounded-xl bg-amber-50 border border-amber-200 p-3 text-xs text-amber-800">
          <strong>Conflict:</strong> the following variable names appear in both namespaces and will collide at runtime:{' '}
          <code className="font-mono">{audit.overlap.join(', ')}</code>
        </div>
      )}
      {audit && (
        <div className="mt-4 text-[11px] text-zinc-400">
          {audit.tenant_overrides_active} tenant{audit.tenant_overrides_active === 1 ? '' : 's'} {audit.tenant_overrides_active === 1 ? 'has' : 'have'} custom overrides active.
        </div>
      )}
    </div>
  );
}

function NamespaceCard({ ns }) {
  return (
    <div className="bg-white border border-zinc-200 rounded-2xl overflow-hidden" data-testid={`theme-ns-${ns.id}`}>
      <div className="px-5 py-4 border-b border-zinc-100">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-zinc-900">{ns.label} <span className="ml-2 text-xs font-mono text-zinc-400">{ns.prefix}</span></h3>
            <p className="text-xs text-zinc-500 mt-0.5">{ns.surface_scope}</p>
          </div>
          <span className="text-[10px] text-zinc-400 font-mono">{ns.css_source}</span>
        </div>
      </div>
      <div className="divide-y divide-zinc-50">
        {ns.tokens.map((t) => (
          <div key={t.var} className="flex items-center gap-4 px-5 py-3">
            <div className="w-7 h-7 rounded-md border border-zinc-200" style={{ background: t.value }} />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <code className="font-mono text-xs text-zinc-700">{t.var}</code>
                <code className="font-mono text-xs text-zinc-400">{t.value}</code>
              </div>
              <div className="text-xs text-zinc-500 mt-0.5">{t.role}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function OverridesCard({ orgs, orgId, setOrgId, orgTheme, draft, setDraft, onSave, onClear, saving }) {
  const selectedOrg = useMemo(() => orgs.find((o) => o.id === orgId), [orgs, orgId]);
  const hasOverrides = Object.values(draft || {}).some((v) => v && v.length > 0);
  return (
    <div className="bg-white border border-zinc-200 rounded-2xl p-5" data-testid="theme-overrides-card">
      <div className="flex items-center gap-2 mb-3">
        <Building2 size={14} className="text-zinc-500" />
        <h3 className="text-sm font-semibold text-zinc-900">Per-tenant overrides</h3>
      </div>
      <p className="text-xs text-zinc-500 mb-4">Pick a tenant to tune their brand colours. Empty fields use the namespace defaults.</p>
      <select
        value={orgId}
        onChange={(e) => setOrgId(e.target.value)}
        className="w-full rounded-xl border border-zinc-200 bg-white px-3 py-2.5 text-sm focus:outline-none focus:border-zinc-400 mb-4"
        data-testid="theme-org-picker"
      >
        <option value="">— Pick an organisation —</option>
        {orgs.map((o) => (
          <option key={o.id} value={o.id}>{o.name} {o.account_type ? `(${o.account_type})` : ''}</option>
        ))}
      </select>

      {orgId && orgTheme && (
        <>
          <div className="mb-4 rounded-lg bg-zinc-50 border border-zinc-100 px-3 py-2 text-[11px] text-zinc-600">
            <strong className="text-zinc-800">{orgTheme.org_name}</strong> uses the <strong>{orgTheme.default_namespace}</strong> namespace by default.
          </div>
          <div className="space-y-3" data-testid="theme-override-fields">
            {OVERRIDE_FIELDS.map(({ key, label, placeholder }) => (
              <div key={key} className="flex items-center gap-2">
                <label className="text-xs font-semibold text-zinc-700 flex-1">{label}</label>
                <div className="w-7 h-7 rounded-md border border-zinc-200" style={{ background: draft[key] || 'transparent' }} />
                <input
                  type="text"
                  value={draft[key] || ''}
                  onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))}
                  placeholder={placeholder}
                  className="w-28 rounded-lg border border-zinc-200 bg-white px-2 py-1.5 text-xs font-mono uppercase focus:outline-none focus:border-zinc-400"
                  data-testid={`theme-override-${key}`}
                />
              </div>
            ))}
          </div>
          <div className="mt-5 flex items-center gap-2">
            <button
              type="button"
              onClick={onSave}
              disabled={saving}
              className="inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-xs font-semibold disabled:opacity-50"
              style={{ background: '#0F172A', color: '#FFFFFF' }}
              data-testid="theme-save"
            >
              <Save size={12} /> {saving ? 'Saving…' : 'Save overrides'}
            </button>
            {hasOverrides && (
              <button
                type="button"
                onClick={onClear}
                disabled={saving}
                className="inline-flex items-center gap-1.5 rounded-full border border-zinc-200 px-4 py-2 text-xs font-semibold text-zinc-700 hover:bg-zinc-50 disabled:opacity-50"
                data-testid="theme-clear"
              >
                Clear all
              </button>
            )}
          </div>
          {hasOverrides && (
            <div className="mt-5 rounded-xl border border-zinc-100 p-4 bg-zinc-50/50" data-testid="theme-preview">
              <div className="text-[10px] uppercase tracking-[0.12em] font-bold text-zinc-400 mb-2 flex items-center gap-1"><Eye size={10} /> Live preview</div>
              <div
                className="rounded-lg p-4"
                style={{
                  background: draft.surface || '#FFFFFF',
                  color: draft.text || '#0A0C10',
                  border: `1px solid ${draft.border || '#E4E4E7'}`,
                }}
              >
                <div className="text-sm font-semibold">Card title</div>
                <div className="text-xs mt-1" style={{ color: draft.text_muted || '#52525B' }}>
                  This is how a tenant-themed card looks with the overrides applied.
                </div>
                <button
                  type="button"
                  className="mt-3 inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-semibold"
                  style={{ background: draft.primary || '#19CDFF', color: '#0A0C10' }}
                >
                  Primary action
                </button>
                {draft.accent && (
                  <span className="ml-2 inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-semibold" style={{ background: `${draft.accent}1F`, color: draft.accent }}>
                    Accent pill
                  </span>
                )}
              </div>
            </div>
          )}
          {selectedOrg?.account_type === 'pulse_pro' && (
            <div className="mt-4 text-[11px] text-zinc-400 leading-relaxed">
              Pulse-Pro tenants inherit <code className="font-mono">--pulse-*</code> by default. Your overrides cascade on top of those.
            </div>
          )}
        </>
      )}
      {!orgId && (
        <div className="text-xs text-zinc-400 italic">No tenant selected.</div>
      )}
    </div>
  );
}
