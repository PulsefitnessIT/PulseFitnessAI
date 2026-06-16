/**
 * Theme Settings Panel — Master Admin → Settings & Compliance (Iter 216h95).
 *
 * Two-pane layout:
 *   • Left  — Isolation audit. Two columns of design tokens (Pulse Fitness +
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
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { useAuth } from '@/App';
import {
  Palette, ShieldCheck, AlertTriangle, RefreshCw, Save, Eye, Building2,
  Inbox, Hourglass, Sparkles, FileText, Image as ImageIcon,
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

/* Iter 216h107 — Tender PDF branding overrides. These do NOT theme the
   live UI — they only feed the CRM Tender Engine PDF / pitch-deck
   generator. Leaving any field blank inherits the platform default
   (currently "Pulse Fitness"). Stored on the same `theme_overrides`
   sub-document on the organisation. */
const TENDER_BRANDING_FIELDS = [
  { key: 'tender_company_name',  label: 'Cover company name',  type: 'text',  placeholder: 'Pulse Fitness' },
  { key: 'tender_primary_color', label: 'PDF primary colour',  type: 'color', placeholder: '#19CDFF' },
  { key: 'tender_logo_url',      label: 'Cover logo URL',      type: 'url',   placeholder: 'https://cdn.example.com/logo.png' },
];

// Iter 216h100 — preset palettes. Two presets: the platform's own
// brand defaults so an operator can revert quickly without typing 7
// hex codes by hand.
const BRAND_PRESETS = {
  pulse: {
    label: 'Pulse Fitness',
    primary:       '#66CCFF',
    primary_hover: '#4DBFFF',
    accent:        '#19CDFF',
    surface:       '#FFFFFF',
    text:          '#212721',
    text_muted:    '#505759',
    border:        '#E4E4E7',
  },
  gymaxis: {
    label: 'Pulse Fitness',
    primary:       '#2563EB',
    primary_hover: '#1D4ED8',
    accent:        '#9D4CDD',
    surface:       '#FFFFFF',
    text:          '#0F172A',
    text_muted:    '#475569',
    border:        '#E2E8F0',
  },
};

function authHeader() {
  const token = localStorage.getItem('token') || localStorage.getItem('gymaxis_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export default function ThemeSettingsPanel() {
  const { user } = useAuth();
  const isPulseAdmin = !!(user?.is_pulse_admin && !user?.is_master_admin);
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
      TENDER_BRANDING_FIELDS.forEach(({ key, type }) => {
        const cur = draft[key];
        if (cur == null) return;
        if (type === 'color') payload[key] = cur === '' ? '' : cur.toUpperCase();
        else payload[key] = cur; // freeform — keep case
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
      TENDER_BRANDING_FIELDS.forEach(({ key }) => { payload[key] = ''; });
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
      <Header audit={audit} onRefresh={loadAudit} loading={loading} isPulseAdmin={isPulseAdmin} />
      <InboxSlaCard />
      <div className="grid lg:grid-cols-3 gap-5">
        <div className="lg:col-span-2 space-y-5">
          {audit?.namespaces?.filter((ns) => !isPulseAdmin || ns.id !== 'gymaxis').map((ns) => (
            <NamespaceCard key={ns.id} ns={ns} />
          ))}
        </div>
        <OverridesCard
          isPulseAdmin={isPulseAdmin}
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

function InboxSlaCard() {
  const [settings, setSettings] = useState({ warning_hours: 4, breach_hours: 24 });
  const [draft, setDraft] = useState({ warning_hours: 4, breach_hours: 24 });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/master-admin/communications/settings`, { headers: authHeader() });
        const s = r.data?.settings || { warning_hours: 4, breach_hours: 24 };
        setSettings(s);
        setDraft(s);
      } catch (e) {
        // Endpoint may not be available yet — fall back to defaults.
      }
    })();
  }, []);

  const save = async () => {
    if (draft.breach_hours <= draft.warning_hours) {
      toast.error('Breach hours must be greater than warning hours.');
      return;
    }
    setSaving(true);
    try {
      const r = await axios.put(`${API}/master-admin/communications/settings`, draft, { headers: authHeader() });
      setSettings(r.data?.settings || draft);
      toast.success('SLA settings saved.');
    } catch (e) {
      const msg = e.response?.data?.detail || 'Save failed';
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  const dirty = draft.warning_hours !== settings.warning_hours || draft.breach_hours !== settings.breach_hours;

  return (
    <div className="bg-white border border-zinc-200 rounded-2xl p-5" data-testid="inbox-sla-card">
      <div className="flex items-start justify-between gap-4 mb-3">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-amber-50">
            <Hourglass size={18} className="text-amber-700" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-zinc-900 flex items-center gap-2">
              <Inbox size={13} className="text-zinc-400" /> Communications inbox SLA
            </h3>
            <p className="text-xs text-zinc-500 mt-0.5">Sales-enquiry response thresholds. Open enquiries past these limits get warning / breach badges in the inbox.</p>
          </div>
        </div>
      </div>
      <div className="grid sm:grid-cols-2 gap-4 mt-3">
        <SlaField
          label="Warning after"
          value={draft.warning_hours}
          onChange={(v) => setDraft((d) => ({ ...d, warning_hours: v }))}
          testid="sla-warning-hours"
          tone="amber"
        />
        <SlaField
          label="Breach after"
          value={draft.breach_hours}
          onChange={(v) => setDraft((d) => ({ ...d, breach_hours: v }))}
          testid="sla-breach-hours"
          tone="rose"
        />
      </div>
      <div className="mt-4 flex items-center justify-end gap-2">
        <button
          type="button"
          onClick={save}
          disabled={!dirty || saving}
          className="inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-xs font-semibold disabled:opacity-50"
          style={{ background: '#0F172A', color: '#FFFFFF' }}
          data-testid="sla-save"
        >
          <Save size={12} /> {saving ? 'Saving…' : 'Save SLA settings'}
        </button>
      </div>
    </div>
  );
}

function SlaField({ label, value, onChange, testid, tone }) {
  const ring = tone === 'rose' ? 'border-rose-200 focus:border-rose-400' : 'border-amber-200 focus:border-amber-400';
  return (
    <label className="block">
      <span className="text-[11px] font-semibold text-zinc-600 uppercase tracking-wide">{label}</span>
      <div className="mt-1 flex items-center gap-2">
        <input
          type="number"
          min={1}
          max={720}
          value={value}
          onChange={(e) => onChange(Math.max(1, Math.min(720, parseInt(e.target.value || '0', 10))))}
          className={`w-24 rounded-lg border bg-white px-3 py-2 text-sm font-mono focus:outline-none ${ring}`}
          data-testid={testid}
        />
        <span className="text-xs text-zinc-500">hours</span>
      </div>
    </label>
  );
}

function Header({ audit, onRefresh, loading, isPulseAdmin }) {
  const ok = audit?.status === 'ok';
  return (
    <div className="bg-white border border-zinc-200 rounded-2xl p-5 shadow-sm">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-indigo-50">
            <Palette size={18} className="text-indigo-600" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-zinc-900">Theme settings{isPulseAdmin ? '' : ' & isolation audit'}</h2>
            <p className="text-xs text-zinc-500">{isPulseAdmin
              ? 'Your Pulse Fitness design tokens plus per-tenant brand overrides.'
              : 'Pulse Fitness (marketing/admin) vs Pulse Fitness (operator) design tokens — separated by CSS namespace and verified here.'}</p>
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

function OverridesCard({ orgs, orgId, setOrgId, orgTheme, draft, setDraft, onSave, onClear, saving, isPulseAdmin }) {
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
          <div className="mb-3 rounded-lg bg-zinc-50 border border-zinc-100 px-3 py-2 text-[11px] text-zinc-600">
            <strong className="text-zinc-800">{orgTheme.org_name}</strong> uses the <strong>{orgTheme.default_namespace}</strong> namespace by default.
          </div>
          <div className="mb-4 flex items-center gap-2 flex-wrap" data-testid="theme-presets">
            <span className="text-[10px] uppercase tracking-[0.12em] font-bold text-zinc-400 mr-1 flex items-center gap-1">
              <Sparkles size={10} /> Apply preset:
            </span>
            {Object.entries(BRAND_PRESETS).filter(([id]) => !isPulseAdmin || id !== 'gymaxis').map(([id, preset]) => (
              <button
                key={id}
                type="button"
                onClick={() => setDraft({ ...preset })}
                className="inline-flex items-center gap-1.5 rounded-full border border-zinc-200 bg-white px-3 py-1 text-[11px] font-semibold text-zinc-700 hover:border-zinc-400"
                data-testid={`theme-preset-${id}`}
              >
                <span className="w-3 h-3 rounded-full" style={{ background: preset.primary }} />
                {preset.label}
              </button>
            ))}
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

          {/* Iter 216h107 — Tender PDF branding overrides */}
          <TenderBrandingSection draft={draft} setDraft={setDraft} orgName={orgTheme?.org_name} />
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


/* ── Iter 216h107 — Tender PDF branding section ───────────────────── */
function TenderBrandingSection({ draft, setDraft, orgName }) {
  const company = (draft.tender_company_name || '').trim();
  const color = (draft.tender_primary_color || '').trim() || '#19CDFF';
  const logo = (draft.tender_logo_url || '').trim();
  const previewCompany = company || 'Pulse Fitness';

  return (
    <div
      className="mt-6 pt-5 border-t border-zinc-100"
      data-testid="tender-branding-section"
    >
      <div className="flex items-center gap-2 mb-1">
        <FileText size={13} className="text-zinc-500" />
        <h4 className="text-sm font-semibold text-zinc-900">Tender PDF branding</h4>
      </div>
      <p className="text-[11px] text-zinc-500 mb-3 leading-relaxed">
        Customises the cover slide of CRM Tender Engine PDFs and pitch decks for{' '}
        <strong className="text-zinc-700">{orgName || 'this tenant'}</strong>.
        These overrides only affect generated PDFs — not the live UI.
      </p>

      <div className="space-y-3">
        {TENDER_BRANDING_FIELDS.map(({ key, label, placeholder, type }) => (
          <div key={key} className="flex items-center gap-2">
            <label className="text-xs font-semibold text-zinc-700 flex-1">{label}</label>
            {type === 'color' && (
              <div
                className="w-7 h-7 rounded-md border border-zinc-200"
                style={{ background: draft[key] || 'transparent' }}
              />
            )}
            <input
              type="text"
              value={draft[key] || ''}
              onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))}
              placeholder={placeholder}
              className={`rounded-lg border border-zinc-200 bg-white px-2 py-1.5 text-xs focus:outline-none focus:border-zinc-400 ${
                type === 'color' ? 'w-28 font-mono uppercase' : 'flex-[2_2_0%] font-sans'
              }`}
              data-testid={`tender-brand-${key}`}
            />
          </div>
        ))}
      </div>

      {/* Live PDF cover preview */}
      <div className="mt-4 rounded-xl border border-zinc-200 bg-white overflow-hidden shadow-sm" data-testid="tender-brand-preview">
        <div className="px-4 py-2 bg-zinc-50 border-b border-zinc-100 flex items-center justify-between">
          <span className="text-[10px] uppercase tracking-[0.12em] font-bold text-zinc-400 flex items-center gap-1">
            <Eye size={10} /> PDF cover preview
          </span>
          <span className="text-[10px] text-zinc-400 font-mono">A4 · landscape</span>
        </div>
        <div className="p-5">
          {logo ? (
            <img
              src={logo}
              alt="Logo"
              className="h-9 mb-3 object-contain"
              onError={(e) => { e.target.style.display = 'none'; }}
              data-testid="tender-brand-preview-logo"
            />
          ) : (
            <div className="h-9 mb-3 flex items-center gap-1 text-[11px] uppercase tracking-[0.15em] font-bold" style={{ color }}>
              <ImageIcon size={12} /> {previewCompany}
            </div>
          )}
          <p className="text-[10px] uppercase tracking-[0.18em] font-bold text-zinc-400">Cover</p>
          <p className="text-xl font-black tracking-tight text-zinc-900 leading-tight">
            Your tender opportunity
          </p>
          <p className="mt-1 text-sm font-semibold" style={{ color }}>
            A pitch from {previewCompany} for your team
          </p>
          <div className="mt-3 inline-flex items-center gap-2 rounded-full px-3 py-1 text-[11px] font-semibold text-white" style={{ background: color }}>
            <FileText size={11} /> Tender response
          </div>
        </div>
      </div>
    </div>
  );
}
