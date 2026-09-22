/**
 * CRM → Aftersales Contracts — command centre over the EXISTING CRM /
 * Contracts / Quotes / Assets / Service Desk records.
 *
 * Phase 1 surfaces:
 *   • Dashboard        — coordinator command centre (cards + priorities)
 *   • Pricing & Rules  — editable, versioned rate groups / contract types /
 *                        packages (Gold-baseline model) + wording governance
 *   • Equipment Review — Service Config Master browser + live deterministic
 *                        quote calculator (single pricing engine)
 *   • Supportability   — Service-Manager decision memory + evaluator
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import { useCRM } from '../CRMApp';
import SubTabBar from '../../../components/shared/SubTabBar';
import CRMContracts from '../CRMContracts';
import EstateOnboarding from './EstateOnboarding';
import {
  LayoutDashboard, SlidersHorizontal, Wrench, ShieldCheck, RefreshCw, AlertTriangle,
  Clock, FileSignature, Calculator, Plus, Trash2, Check, Search, TrendingUp, Shield,
  Zap, Building2, Rocket, FileCheck2, PenLine, CheckCircle2, Circle,
  CalendarClock, Receipt, ChevronDown, ChevronRight, RotateCw, MinusCircle,
  FileText, Share2, Bell, Mail, X, Sparkles, Copy, MessageSquare, FileSpreadsheet,
  History, Eye,
} from 'lucide-react';

const gbp = (v) => '£' + Number(v || 0).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const gbp0 = (v) => '£' + Number(v || 0).toLocaleString('en-GB', { maximumFractionDigits: 0 });
const pct = (v) => (Number(v || 0) * 100).toFixed(2).replace(/\.00$/, '') + '%';

const SUB_TABS = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'autoquote', label: 'Build Quote', icon: Zap },
  { id: 'onboarding', label: 'Onboard Estate', icon: FileSpreadsheet },
  { id: 'agreements', label: 'Agreements', icon: FileCheck2 },
  { id: 'renewals', label: 'Renewals & RPI', icon: RefreshCw },
  { id: 'contracts', label: 'Contracts & Renewals', icon: Shield },
  { id: 'finance', label: 'Finance Sync', icon: Receipt },
  { id: 'ai', label: 'AI Assistant', icon: Sparkles },
  { id: 'reports', label: 'Reports', icon: TrendingUp },
  { id: 'pricing', label: 'Pricing & Rules', icon: SlidersHorizontal },
  { id: 'equipment', label: 'Equipment Review', icon: Wrench },
  { id: 'supportability', label: 'Supportability', icon: ShieldCheck },
];

function Spinner() {
  return <div className="flex justify-center py-12"><div className="w-5 h-5 border-2 border-[var(--color-info-ios)] border-t-transparent rounded-full animate-spin" /></div>;
}

function Card({ children, c, isDark, className = '', testId }) {
  return (
    <div data-testid={testId} className={`p-4 rounded-xl border ${className}`}
         style={{ background: isDark ? '#111' : 'var(--color-neutral-50)', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
      {children}
    </div>
  );
}

// ───────────────────────────────────────────────────────── Dashboard
function DashboardTab({ API, headers, c, isDark }) {
  const [cards, setCards] = useState(null);
  const [priorities, setPriorities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [alerts, setAlerts] = useState({ alerts: [], counts: {} });
  const [scanning, setScanning] = useState(false);
  const [alertEmail, setAlertEmail] = useState('');
  const [savedEmail, setSavedEmail] = useState(false);

  const loadAlerts = useCallback(() => {
    axios.get(`${API}/crm/v2/aftersales/alerts`, { headers: headers() })
      .then(r => setAlerts(r.data)).catch(() => setAlerts({ alerts: [], counts: {} }));
    axios.get(`${API}/crm/v2/aftersales/settings`, { headers: headers() })
      .then(r => setAlertEmail(r.data.alert_email || '')).catch(() => {});
  }, [API, headers]);

  const load = useCallback((attempt = 0) => {
    setLoading(true);
    Promise.all([
      axios.get(`${API}/crm/v2/aftersales/dashboard`, { headers: headers() }),
      axios.get(`${API}/crm/v2/aftersales/priorities`, { headers: headers() }),
    ]).then(([d, p]) => { setCards(d.data.cards); setPriorities(p.data.priorities || []); setLoading(false); })
      .catch(() => {
        if (attempt < 3) { setTimeout(() => load(attempt + 1), 800); }
        else { setCards({}); setLoading(false); }
      });
  }, [API, headers]);
  useEffect(() => { load(); loadAlerts(); }, [load, loadAlerts]);

  const runScan = async () => {
    setScanning(true);
    try { await axios.post(`${API}/crm/v2/aftersales/alerts/run`, {}, { headers: headers() }); loadAlerts(); }
    finally { setScanning(false); }
  };
  const dismissAlert = async (id) => {
    await axios.post(`${API}/crm/v2/aftersales/alerts/${id}/dismiss`, {}, { headers: headers() });
    loadAlerts();
  };
  const saveAlertEmail = async () => {
    await axios.put(`${API}/crm/v2/aftersales/settings`, { alert_email: alertEmail }, { headers: headers() });
    setSavedEmail(true); setTimeout(() => setSavedEmail(false), 2500);
  };

  if (loading) return <Spinner />;
  const CARDS = [
    { k: 'renewal_opportunities', label: 'Renewal Opportunities', icon: RefreshCw, color: 'var(--color-info-ios)' },
    { k: 'quotes_to_prepare', label: 'Quotes to Prepare', icon: FileSignature, color: 'var(--color-accent-amber)' },
    { k: 'quotes_awaiting_approval', label: 'Quotes Awaiting Approval', icon: Clock, color: 'var(--color-warning)' },
    { k: 'quotes_with_customer', label: 'Quotes With Customer', icon: TrendingUp, color: 'var(--color-info-ios)' },
    { k: 'agreements_awaiting_signature', label: 'Agreements Awaiting Signature', icon: FileSignature, color: 'var(--color-accent-purple)' },
    { k: 'contracts_ready_to_activate', label: 'Ready to Activate', icon: Check, color: 'var(--color-success-alt)' },
    { k: 'rpi_reviews_due', label: 'RPI Reviews Due', icon: TrendingUp, color: 'var(--color-accent-amber)' },
    { k: 'supportability_reviews', label: 'Supportability Reviews', icon: ShieldCheck, color: 'var(--color-warning)' },
    { k: 'wording_conflicts', label: 'Wording Conflicts', icon: AlertTriangle, color: 'var(--color-danger)' },
  ];
  const levelColor = { HIGH: 'var(--color-danger)', ACTION: 'var(--color-info-ios)', REVIEW: 'var(--color-accent-amber)', RPI: 'var(--color-accent-purple)' };
  return (
    <div data-testid="afs-dashboard">
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm" style={{ color: c.textDim }}>Everything requiring your attention, drawn live from CRM, Quotes and Contracts.</p>
        <button data-testid="afs-dashboard-refresh" onClick={load} className="text-xs px-3 py-1.5 rounded-md border inline-flex items-center gap-1.5" style={{ borderColor: c.border, color: c.text }}><RefreshCw size={13} /> Refresh</button>
      </div>
      {/* Headline value */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
        <Card c={c} isDark={isDark} testId="afs-card-acv" className="md:col-span-1">
          <p className="text-[10px] uppercase tracking-wider" style={{ color: c.textDim }}>Annual Contract Value</p>
          <p className="text-2xl font-extrabold tracking-tight" style={{ color: 'var(--color-success-alt)' }}>{gbp0(cards.annual_contract_value)}</p>
          <p className="text-[11px]" style={{ color: c.textDim }}>{cards.active_contracts} active contract{cards.active_contracts === 1 ? '' : 's'}</p>
        </Card>
        <Card c={c} isDark={isDark} testId="afs-card-renewal-180" className="md:col-span-2 flex items-center justify-around">
          {[['renewal_window_180', '180-day pipeline'], ['renewal_opportunities', '90-day renewals'], ['expired_contracts', 'Expired']].map(([k, lbl]) => (
            <div key={k} className="text-center">
              <p className="text-2xl font-extrabold" style={{ color: c.text }}>{cards[k] ?? 0}</p>
              <p className="text-[10px] uppercase tracking-wider" style={{ color: c.textDim }}>{lbl}</p>
            </div>
          ))}
        </Card>
      </div>
      {/* Action cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-3 gap-3 mb-6">
        {CARDS.map(cd => (
          <Card key={cd.k} c={c} isDark={isDark} testId={`afs-card-${cd.k}`}>
            <div className="flex items-center justify-between mb-1.5"><cd.icon size={15} style={{ color: cd.color }} /></div>
            <p className="text-2xl font-extrabold tracking-tight" style={{ color: c.text }}>{cards[cd.k] ?? 0}</p>
            <p className="text-[10px] uppercase tracking-wider" style={{ color: c.textDim }}>{cd.label}</p>
          </Card>
        ))}
      </div>
      {/* Alerts & reminders — warranty + RPI at 180/120/90 windows */}
      <div data-testid="afs-alerts-panel" className="mb-6">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Bell size={15} style={{ color: 'var(--color-accent-amber)' }} />
            <h3 className="text-sm font-bold" style={{ color: c.text }}>Alerts &amp; reminders</h3>
            {(alerts.counts?.open_total > 0) && (
              <span className="text-[10px] font-bold px-2 py-0.5 rounded-full" style={{ background: 'var(--color-accent-amber)22', color: 'var(--color-accent-amber)' }}>
                {alerts.counts.warranty || 0} warranty · {alerts.counts.rpi || 0} RPI
              </span>
            )}
          </div>
          <button data-testid="afs-alerts-scan" onClick={runScan} disabled={scanning}
            className="text-xs px-3 py-1.5 rounded-md border inline-flex items-center gap-1.5 disabled:opacity-50" style={{ borderColor: c.border, color: c.text }}>
            <Search size={13} /> {scanning ? 'Scanning…' : 'Run scan now'}
          </button>
        </div>
        <div className="flex items-center gap-2 mb-3 flex-wrap" data-testid="afs-alerts-email-row">
          <Mail size={13} style={{ color: c.textDim }} />
          <span className="text-xs" style={{ color: c.textDim }}>Email alerts to</span>
          <input data-testid="afs-alerts-email-input" type="text" value={alertEmail}
            onChange={e => setAlertEmail(e.target.value)} placeholder="coordinator@company.com (blank = org owners)"
            className="text-xs px-2 py-1 rounded-md border flex-1 min-w-[180px]" style={{ background: isDark ? '#0d0d0d' : '#fff', borderColor: c.border, color: c.text }} />
          <button data-testid="afs-alerts-email-save" onClick={saveAlertEmail}
            className="text-xs px-3 py-1 rounded-md" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}>
            {savedEmail ? 'Saved ✓' : 'Save'}
          </button>
        </div>
        <div className="space-y-2" data-testid="afs-alerts-list">
          {(alerts.alerts || []).filter(a => a.status === 'open').length === 0 ? (
            <Card c={c} isDark={isDark} testId="afs-alerts-empty">
              <p className="text-sm" style={{ color: c.textDim }}>No open warranty or RPI reminders. Run a scan to check for warranties or contract anniversaries entering the 180/120/90-day windows.</p>
            </Card>
          ) : (
            (alerts.alerts || []).filter(a => a.status === 'open').map((a) => {
              const isWarranty = a.type === 'warranty_alert';
              const col = a.threshold_days <= 90 ? 'var(--color-danger)' : a.threshold_days <= 120 ? 'var(--color-accent-amber)' : 'var(--color-info-ios)';
              return (
                <div key={a.id} data-testid={`afs-alert-${a.id}`} className="flex items-start gap-3 p-3 rounded-lg border"
                     style={{ background: isDark ? '#0d0d0d' : '#fff', borderColor: c.border }}>
                  <span className="mt-0.5 shrink-0">{isWarranty ? <ShieldCheck size={16} style={{ color: col }} /> : <TrendingUp size={16} style={{ color: col }} />}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded-md" style={{ background: col + '22', color: col }}>≤{a.threshold_days}d</span>
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded-md" style={{ background: isDark ? '#1a1a1a' : 'var(--color-neutral-100)', color: c.textDim }}>{isWarranty ? 'WARRANTY' : 'RPI REVIEW'}</span>
                      <span className="text-sm font-semibold truncate" style={{ color: c.text }}>{a.subject}</span>
                    </div>
                    <p className="text-xs mt-0.5" style={{ color: c.textDim }}>{a.body}</p>
                  </div>
                  <button data-testid={`afs-alert-dismiss-${a.id}`} onClick={() => dismissAlert(a.id)}
                    className="shrink-0 text-xs px-2 py-1 rounded-md border inline-flex items-center gap-1" style={{ borderColor: c.border, color: c.textDim }}>
                    <Check size={12} /> Done
                  </button>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Priorities */}
      <h3 className="text-sm font-bold mb-2" style={{ color: c.text }}>My Priorities Today</h3>
      <div data-testid="afs-priorities" className="space-y-2">
        {priorities.length === 0 && <p className="text-sm py-6 text-center" style={{ color: c.textDim }}>Nothing urgent — you're all caught up.</p>}
        {priorities.map((p, i) => (
          <div key={i} data-testid={`afs-priority-${i}`} className="flex items-center gap-3 p-3 rounded-lg border"
               style={{ background: isDark ? '#0d0d0d' : '#fff', borderColor: c.border }}>
            <span className="text-[10px] font-bold px-2 py-1 rounded-md" style={{ background: levelColor[p.level] + '22', color: levelColor[p.level] }}>{p.level}</span>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold truncate" style={{ color: c.text }}>{p.title}</p>
              <p className="text-xs truncate" style={{ color: c.textDim }}>{p.detail}</p>
            </div>
            {p.value ? <span className="text-xs font-semibold" style={{ color: c.textDim }}>{gbp0(p.value)}</span> : null}
          </div>
        ))}
      </div>
    </div>
  );
}

// ───────────────────────────────────────────────────────── Pricing & Rules
function PricingTab({ API, headers, c, isDark }) {
  const [ruleset, setRuleset] = useState(null);
  const [packages, setPackages] = useState([]);
  const [conflicts, setConflicts] = useState([]);
  const [versions, setVersions] = useState([]);
  const [saving, setSaving] = useState('');
  const [edits, setEdits] = useState({});

  const load = useCallback(() => {
    Promise.all([
      axios.get(`${API}/crm/v2/aftersales/ruleset`, { headers: headers() }),
      axios.get(`${API}/crm/v2/aftersales/packages`, { headers: headers() }),
      axios.get(`${API}/crm/v2/aftersales/wording-conflicts`, { headers: headers() }),
      axios.get(`${API}/crm/v2/aftersales/versions`, { headers: headers() }),
    ]).then(([r, p, w, v]) => { setRuleset(r.data); setPackages(p.data.packages || []); setConflicts(w.data.conflicts || []); setVersions(v.data.versions || []); });
  }, [API, headers]);
  useEffect(load, [load]);
  if (!ruleset) return <Spinner />;

  const saveContractType = async (ct) => {
    const key = `ct-${ct.id}`; setSaving(key);
    const adj = edits[key] != null ? Number(edits[key]) / 100 : ct.adjustment_pct;
    try {
      await axios.put(`${API}/crm/v2/aftersales/contract-types/${ct.id}`, { adjustment_pct: adj }, { headers: headers() });
      setEdits(e => { const n = { ...e }; delete n[key]; return n; }); load();
    } finally { setSaving(''); }
  };
  const saveRateGroup = async (rg, field) => {
    const key = `rg-${rg.id}-${field}`; setSaving(key);
    const val = edits[key] != null ? Number(edits[key]) / 100 : rg[field];
    try {
      await axios.put(`${API}/crm/v2/aftersales/rate-groups/${rg.id}`, { [field]: val }, { headers: headers() });
      setEdits(e => { const n = { ...e }; delete n[key]; return n; }); load();
    } finally { setSaving(''); }
  };
  const inpCls = 'w-20 px-2 py-1 text-sm rounded-md text-right';
  const inpStyle = { background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text };

  return (
    <div data-testid="afs-pricing" className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-sm" style={{ color: c.textDim }}>Gold is the baseline. Order: <b style={{ color: c.text }}>Gold base → contract-type adjustment → quote discount</b>. Edits create a new version so historic quotes never change.</p>
        <span className="text-xs px-2.5 py-1 rounded-md" style={{ background: 'var(--color-info-ios)22', color: 'var(--color-info-ios)' }}>Pricing v{ruleset.version}</span>
      </div>

      {conflicts.length > 0 && (
        <Card c={c} isDark={isDark} testId="afs-wording-conflict" className="border-l-4" >
          <div className="flex items-start gap-2">
            <AlertTriangle size={16} style={{ color: 'var(--color-danger)' }} className="mt-0.5" />
            <div>
              <p className="text-sm font-bold" style={{ color: 'var(--color-danger)' }}>Commercial wording conflict — approval required</p>
              {conflicts.map((w, i) => (
                <p key={i} className="text-xs mt-1" style={{ color: c.textDim }}><b style={{ color: c.text }}>{w.package}:</b> {w.note}</p>
              ))}
            </div>
          </div>
        </Card>
      )}

      {/* Contract type adjustments */}
      <div>
        <h3 className="text-sm font-bold mb-2" style={{ color: c.text }}>Contract Type Adjustments</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {ruleset.contract_types.map(ct => {
            const key = `ct-${ct.id}`;
            return (
              <Card key={ct.id} c={c} isDark={isDark} testId={`afs-ct-${ct.key}`}>
                <p className="text-sm font-bold capitalize mb-2" style={{ color: c.text }}>{ct.name}</p>
                <div className="flex items-center gap-2">
                  <span className="text-xs" style={{ color: c.textDim }}>Adjustment</span>
                  <input data-testid={`afs-ct-input-${ct.key}`} className={inpCls} style={inpStyle} type="number" step="1"
                    value={edits[key] != null ? edits[key] : (ct.adjustment_pct * 100)}
                    onChange={e => setEdits(x => ({ ...x, [key]: e.target.value }))} />
                  <span className="text-xs" style={{ color: c.textDim }}>%</span>
                  {ct.key !== 'gold' && edits[key] != null && (
                    <button data-testid={`afs-ct-save-${ct.key}`} onClick={() => saveContractType(ct)} disabled={saving === key}
                      className="ml-auto text-xs px-2 py-1 rounded-md" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}>{saving === key ? '…' : 'Save'}</button>
                  )}
                </div>
                <p className="text-[11px] mt-1" style={{ color: c.textDim }}>Factor ×{ct.pricing_factor}{ct.key === 'gold' ? ' (baseline)' : ''}</p>
              </Card>
            );
          })}
        </div>
      </div>

      {/* Rate groups */}
      <div>
        <h3 className="text-sm font-bold mb-2" style={{ color: c.text }}>Rate Groups <span className="font-normal text-xs" style={{ color: c.textDim }}>(Gold base % of RRP per equipment class)</span></h3>
        <div className="overflow-x-auto rounded-xl border" style={{ borderColor: c.border }}>
          <table className="w-full text-sm" data-testid="afs-rate-groups-table">
            <thead><tr style={{ color: c.textDim }} className="text-left text-[11px] uppercase tracking-wider">
              <th className="p-2">Rate Group</th><th className="p-2">Standard %</th><th className="p-2">Preferred %</th><th className="p-2">Minimum %</th><th className="p-2">Status</th>
            </tr></thead>
            <tbody>
              {ruleset.rate_groups.map(rg => (
                <tr key={rg.id} data-testid={`afs-rg-${rg.key}`} className="border-t" style={{ borderColor: c.border }}>
                  <td className="p-2 font-medium" style={{ color: c.text }}>{rg.name}<br /><span className="text-[10px] font-normal" style={{ color: c.textDim }}>{rg.notes}</span></td>
                  {['standard_pct', 'preferred_pct', 'minimum_pct'].map(field => {
                    const key = `rg-${rg.id}-${field}`;
                    return (
                      <td key={field} className="p-2">
                        <div className="flex items-center gap-1">
                          <input className={inpCls + ' w-16'} style={inpStyle} type="number" step="0.05"
                            value={edits[key] != null ? edits[key] : (rg[field] * 100)}
                            onChange={e => setEdits(x => ({ ...x, [key]: e.target.value }))} />
                          {edits[key] != null && (
                            <button data-testid={`afs-rg-save-${rg.key}-${field}`} onClick={() => saveRateGroup(rg, field)} disabled={saving === key}
                              className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}>✓</button>
                          )}
                        </div>
                      </td>
                    );
                  })}
                  <td className="p-2"><span className="text-[10px] px-2 py-0.5 rounded" style={{ background: rg.status === 'Active' ? 'var(--color-success-alt)22' : 'var(--color-accent-amber)22', color: rg.status === 'Active' ? 'var(--color-success-alt)' : 'var(--color-accent-amber)' }}>{rg.status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Packages */}
      <div>
        <h3 className="text-sm font-bold mb-2" style={{ color: c.text }}>Maintenance Packages</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {packages.map(p => (
            <Card key={p.id} c={c} isDark={isDark} testId={`afs-pkg-${p.key}`}>
              <div className="flex items-center justify-between mb-1">
                <p className="text-base font-extrabold capitalize" style={{ color: c.text }}>{p.name}</p>
                <span className="text-[10px] px-2 py-0.5 rounded" style={{ background: 'var(--color-success-alt)22', color: 'var(--color-success-alt)' }}>{p.status} v{p.version}</span>
              </div>
              <p className="text-xs mb-2" style={{ color: c.textDim }}>{p.description}</p>
              <p className="text-[10px] uppercase tracking-wider mb-1" style={{ color: c.textDim }}>Includes</p>
              <ul className="text-xs space-y-0.5 mb-2" style={{ color: c.text }}>
                {(p.maintenance || []).map((m, i) => <li key={i} className="flex items-center gap-1"><Check size={11} style={{ color: 'var(--color-success-alt)' }} />{m}</li>)}
              </ul>
              {(p.exclusions || []).length > 0 && <>
                <p className="text-[10px] uppercase tracking-wider mb-1" style={{ color: c.textDim }}>Exclusions</p>
                <p className="text-[11px]" style={{ color: c.textDim }}>{p.exclusions.join(', ')}</p>
              </>}
            </Card>
          ))}
        </div>
      </div>

      {/* Version history */}
      {versions.length > 0 && (
        <div>
          <h3 className="text-sm font-bold mb-2" style={{ color: c.text }}>Pricing Version History</h3>
          <div className="space-y-1" data-testid="afs-versions">
            {versions.slice(0, 8).map(v => (
              <div key={v.id} className="flex items-center gap-3 text-xs p-2 rounded-lg border" style={{ borderColor: c.border, color: c.textDim }}>
                <span className="font-bold" style={{ color: c.text }}>v{v.version}</span>
                <span className="flex-1">{v.reason}</span>
                <span>{(v.created_at || '').slice(0, 10)} · {v.created_by}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ───────────────────────────────────────────────────────── Equipment Review
function EquipmentTab({ API, headers, c, isDark }) {
  const [stats, setStats] = useState(null);
  const [q, setQ] = useState('');
  const [configs, setConfigs] = useState([]);
  const [lines, setLines] = useState([]);
  const [contractType, setContractType] = useState('gold');
  const [level, setLevel] = useState('standard');
  const [discount, setDiscount] = useState(0);
  const [term, setTerm] = useState(1);
  const [quote, setQuote] = useState(null);
  const inpStyle = { background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text };

  useEffect(() => { axios.get(`${API}/crm/v2/aftersales/service-configs/stats`, { headers: headers() }).then(r => setStats(r.data)); }, [API, headers]);
  const search = useCallback(() => {
    axios.get(`${API}/crm/v2/aftersales/service-configs?q=${encodeURIComponent(q)}&limit=40&eligible_only=true`, { headers: headers() })
      .then(r => setConfigs(r.data.configs || []));
  }, [API, headers, q]);
  useEffect(() => { search(); }, [search]);

  const addLine = (cfg) => setLines(l => [...l, { config_id: cfg.id, model: cfg.model, console_type: cfg.console_type, description: cfg.description, qty: 1, approval_status: cfg.approval_status, rrp: cfg.manual_rrp_override || cfg.rrp_snapshot }]);
  const removeLine = (i) => setLines(l => l.filter((_, j) => j !== i));
  const setQty = (i, v) => setLines(l => l.map((x, j) => j === i ? { ...x, qty: Math.max(1, Number(v) || 1) } : x));

  const calculate = useCallback(() => {
    if (lines.length === 0) { setQuote(null); return; }
    axios.post(`${API}/crm/v2/aftersales/pricing/calculate`, {
      lines: lines.map(l => ({ config_id: l.config_id, qty: l.qty })),
      contract_type: contractType, pricing_level: level, quote_discount_pct: Number(discount), term_years: Number(term),
    }, { headers: headers() }).then(r => setQuote(r.data));
  }, [API, headers, lines, contractType, level, discount, term]);
  useEffect(() => { calculate(); }, [calculate]);

  const healthColor = { READY_TO_ISSUE: 'var(--color-success-alt)', REVIEW_REQUIRED: 'var(--color-accent-amber)', BLOCKED: 'var(--color-danger)' };
  return (
    <div data-testid="afs-equipment" className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {/* Left — config browser */}
      <div>
        {stats && (
          <div className="grid grid-cols-4 gap-2 mb-3">
            {[['total', 'Configs'], ['eligible', 'Eligible'], ['provisional', 'Provisional'], ['rrp_required', 'RRP Req.']].map(([k, l]) => (
              <Card key={k} c={c} isDark={isDark} testId={`afs-cfg-stat-${k}`}><p className="text-lg font-extrabold" style={{ color: c.text }}>{stats[k]}</p><p className="text-[10px] uppercase tracking-wider" style={{ color: c.textDim }}>{l}</p></Card>
            ))}
          </div>
        )}
        <div className="flex gap-2 mb-2">
          <div className="flex-1 flex items-center gap-2 px-3 py-2 rounded-md border" style={{ borderColor: c.border }}>
            <Search size={14} style={{ color: c.textDim }} />
            <input data-testid="afs-cfg-search" className="flex-1 bg-transparent text-sm outline-none" style={{ color: c.text }} placeholder="Search model / console…" value={q} onChange={e => setQ(e.target.value)} />
          </div>
        </div>
        <div className="rounded-xl border overflow-hidden" style={{ borderColor: c.border }} data-testid="afs-cfg-list">
          <div className="max-h-[420px] overflow-y-auto">
            {configs.map(cfg => (
              <div key={cfg.id} className="flex items-center gap-2 p-2.5 border-t" style={{ borderColor: c.border }}>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate" style={{ color: c.text }}>{cfg.model} · {cfg.console_type}</p>
                  <p className="text-[11px] truncate" style={{ color: c.textDim }}>{cfg.description} · {cfg.rate_group}</p>
                </div>
                <span className="text-xs" style={{ color: c.textDim }}>{gbp0(cfg.manual_rrp_override || cfg.rrp_snapshot)}</span>
                {(cfg.approval_status || '').toLowerCase().includes('hold')
                  ? <span className="text-[9px] px-1.5 py-0.5 rounded" style={{ background: 'var(--color-danger)22', color: 'var(--color-danger)' }}>RRP</span>
                  : <span className="text-[9px] px-1.5 py-0.5 rounded" style={{ background: 'var(--color-accent-amber)22', color: 'var(--color-accent-amber)' }}>Prov.</span>}
                <button data-testid={`afs-cfg-add-${cfg.id}`} onClick={() => addLine(cfg)} className="p-1 rounded" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}><Plus size={14} /></button>
              </div>
            ))}
            {configs.length === 0 && <p className="text-sm text-center py-8" style={{ color: c.textDim }}>No matches.</p>}
          </div>
        </div>
      </div>

      {/* Right — live calculator */}
      <div>
        <Card c={c} isDark={isDark} testId="afs-calculator">
          <div className="flex items-center gap-2 mb-3"><Calculator size={16} style={{ color: 'var(--color-brand-cyan)' }} /><p className="text-sm font-bold" style={{ color: c.text }}>Live Quote Calculator</p></div>
          <div className="grid grid-cols-2 gap-2 mb-3">
            <label className="text-xs" style={{ color: c.textDim }}>Package
              <select data-testid="afs-calc-type" value={contractType} onChange={e => setContractType(e.target.value)} className="w-full mt-1 px-2 py-1.5 text-sm rounded-md" style={inpStyle}>
                <option value="silver">Silver</option><option value="gold">Gold</option><option value="platinum">Platinum</option>
              </select></label>
            <label className="text-xs" style={{ color: c.textDim }}>Pricing level
              <select data-testid="afs-calc-level" value={level} onChange={e => setLevel(e.target.value)} className="w-full mt-1 px-2 py-1.5 text-sm rounded-md" style={inpStyle}>
                <option value="standard">Standard</option><option value="preferred">Preferred</option><option value="minimum">Minimum</option>
              </select></label>
            <label className="text-xs" style={{ color: c.textDim }}>Discount %
              <input data-testid="afs-calc-discount" type="number" value={discount} onChange={e => setDiscount(e.target.value)} className="w-full mt-1 px-2 py-1.5 text-sm rounded-md" style={inpStyle} /></label>
            <label className="text-xs" style={{ color: c.textDim }}>Term (yrs)
              <input data-testid="afs-calc-term" type="number" min="1" value={term} onChange={e => setTerm(e.target.value)} className="w-full mt-1 px-2 py-1.5 text-sm rounded-md" style={inpStyle} /></label>
          </div>

          <div className="space-y-1 mb-3" data-testid="afs-calc-lines">
            {lines.length === 0 && <p className="text-xs text-center py-4" style={{ color: c.textDim }}>Add equipment from the left to build a quote.</p>}
            {lines.map((l, i) => (
              <div key={i} className="flex items-center gap-2 text-xs p-2 rounded-md border" style={{ borderColor: c.border }}>
                <span className="flex-1 truncate" style={{ color: c.text }}>{l.model} · {l.console_type}</span>
                <input type="number" min="1" value={l.qty} onChange={e => setQty(i, e.target.value)} className="w-12 px-1 py-0.5 rounded text-right" style={inpStyle} data-testid={`afs-calc-qty-${i}`} />
                <button onClick={() => removeLine(i)} data-testid={`afs-calc-remove-${i}`} className="p-0.5" style={{ color: 'var(--color-danger)' }}><Trash2 size={13} /></button>
              </div>
            ))}
          </div>

          {quote && (
            <div data-testid="afs-calc-result" className="pt-3 border-t" style={{ borderColor: c.border }}>
              <div className="flex items-center justify-between mb-2">
                <span className="text-[10px] uppercase tracking-wider" style={{ color: c.textDim }}>Quote Health</span>
                <span data-testid="afs-calc-health" className="text-xs font-bold px-2 py-1 rounded" style={{ background: (healthColor[quote.quote_health] || c.textDim) + '22', color: healthColor[quote.quote_health] || c.textDim }}>{quote.quote_health.replace(/_/g, ' ')}</span>
              </div>
              {quote.health_reasons.length > 0 && (
                <ul className="text-[11px] mb-3 space-y-0.5" data-testid="afs-calc-reasons">
                  {quote.health_reasons.map((r, i) => <li key={i} className="flex items-start gap-1" style={{ color: 'var(--color-accent-amber)' }}><AlertTriangle size={11} className="mt-0.5" />{r}</li>)}
                </ul>
              )}
              <div className="space-y-1 text-sm">
                <Row label="Gold base annual" value={gbp(quote.summary.gold_base_annual)} c={c} />
                <Row label={`Contract type (×${quote.summary.contract_factor})`} value={gbp(quote.summary.contract_type_annual)} c={c} />
                {quote.summary.quote_discount_pct > 0 && <Row label={`Less ${quote.summary.quote_discount_pct}% discount`} value={'−' + gbp(quote.summary.contract_type_annual - quote.summary.final_annual)} c={c} />}
                <div className="flex justify-between pt-1 border-t" style={{ borderColor: c.border }}>
                  <span className="font-bold" style={{ color: c.text }}>Final annual (ex VAT)</span>
                  <span data-testid="afs-calc-final" className="font-extrabold" style={{ color: 'var(--color-success-alt)' }}>{gbp(quote.summary.final_annual)}</span>
                </div>
                <Row label="Monthly equivalent" value={gbp(quote.summary.monthly)} c={c} />
                <Row label={`Term total (${quote.summary.term_years}yr)`} value={gbp(quote.summary.term_total)} c={c} />
                <Row label={`VAT @ ${pct(quote.summary.vat_pct)}`} value={gbp(quote.summary.vat_amount)} c={c} />
              </div>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
function Row({ label, value, c }) {
  return <div className="flex justify-between"><span style={{ color: c.textDim }}>{label}</span><span style={{ color: c.text }}>{value}</span></div>;
}

// ───────────────────────────────────────────────────────── Supportability
function SupportabilityTab({ API, headers, c, isDark }) {
  const [statuses, setStatuses] = useState([]);
  const [decisions, setDecisions] = useState([]);
  const [evalModel, setEvalModel] = useState('');
  const [evalConsole, setEvalConsole] = useState('');
  const [evalResult, setEvalResult] = useState(null);
  const [form, setForm] = useState({ manufacturer: 'Pulse Fitness', model: '', console_type: '', status: 'fully_supported', permitted_contract_types: [], exclusions: [], reason: '' });
  const inpStyle = { background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text };

  const load = useCallback(() => {
    Promise.all([
      axios.get(`${API}/crm/v2/aftersales/supportability/statuses`, { headers: headers() }),
      axios.get(`${API}/crm/v2/aftersales/supportability/decisions`, { headers: headers() }),
    ]).then(([s, d]) => { setStatuses(s.data.statuses); setDecisions(d.data.decisions || []); });
  }, [API, headers]);
  useEffect(load, [load]);

  const statusMeta = (id) => statuses.find(s => s.id === id) || { name: id, color: c.textDim };
  const runEval = () => axios.post(`${API}/crm/v2/aftersales/supportability/evaluate`, { model: evalModel, console_type: evalConsole }, { headers: headers() }).then(r => setEvalResult(r.data));
  const save = async () => {
    if (!form.model) return;
    await axios.post(`${API}/crm/v2/aftersales/supportability/decisions`, form, { headers: headers() });
    setForm({ manufacturer: 'Pulse Fitness', model: '', console_type: '', status: 'fully_supported', permitted_contract_types: [], exclusions: [], reason: '' });
    load();
  };
  const del = async (id) => { await axios.delete(`${API}/crm/v2/aftersales/supportability/decisions/${id}`, { headers: headers() }); load(); };
  const toggleCt = (ct) => setForm(f => ({ ...f, permitted_contract_types: f.permitted_contract_types.includes(ct) ? f.permitted_contract_types.filter(x => x !== ct) : [...f.permitted_contract_types, ct] }));

  return (
    <div data-testid="afs-supportability" className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <div className="lg:col-span-1 space-y-4">
        <Card c={c} isDark={isDark} testId="afs-support-evaluate">
          <p className="text-sm font-bold mb-2" style={{ color: c.text }}>Evaluate an asset</p>
          <input data-testid="afs-eval-model" className="w-full mb-2 px-2 py-1.5 text-sm rounded-md" style={inpStyle} placeholder="Model (e.g. 200H)" value={evalModel} onChange={e => setEvalModel(e.target.value)} />
          <input data-testid="afs-eval-console" className="w-full mb-2 px-2 py-1.5 text-sm rounded-md" style={inpStyle} placeholder="Console (optional)" value={evalConsole} onChange={e => setEvalConsole(e.target.value)} />
          <button data-testid="afs-eval-run" onClick={runEval} className="w-full text-sm px-3 py-2 rounded-md font-semibold" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}>Evaluate</button>
          {evalResult && (
            <div className="mt-3 p-2.5 rounded-md" data-testid="afs-eval-result" style={{ background: statusMeta(evalResult.status).color + '18' }}>
              <p className="text-sm font-bold" style={{ color: statusMeta(evalResult.status).color }}>{statusMeta(evalResult.status).name}</p>
              <p className="text-[11px] mt-0.5" style={{ color: c.textDim }}>{evalResult.reason} <i>({evalResult.source})</i></p>
            </div>
          )}
        </Card>

        <Card c={c} isDark={isDark} testId="afs-support-add">
          <p className="text-sm font-bold mb-2" style={{ color: c.text }}>Record decision (memory)</p>
          <input data-testid="afs-dec-model" className="w-full mb-2 px-2 py-1.5 text-sm rounded-md" style={inpStyle} placeholder="Model *" value={form.model} onChange={e => setForm(f => ({ ...f, model: e.target.value }))} />
          <input data-testid="afs-dec-console" className="w-full mb-2 px-2 py-1.5 text-sm rounded-md" style={inpStyle} placeholder="Console (optional)" value={form.console_type} onChange={e => setForm(f => ({ ...f, console_type: e.target.value }))} />
          <select data-testid="afs-dec-status" className="w-full mb-2 px-2 py-1.5 text-sm rounded-md" style={inpStyle} value={form.status} onChange={e => setForm(f => ({ ...f, status: e.target.value }))}>
            {statuses.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <p className="text-[11px] mb-1" style={{ color: c.textDim }}>Permitted contract types</p>
          <div className="flex gap-1.5 mb-2">
            {['silver', 'gold', 'platinum'].map(ct => (
              <button key={ct} data-testid={`afs-dec-ct-${ct}`} onClick={() => toggleCt(ct)} className="text-xs px-2 py-1 rounded-md capitalize"
                style={{ background: form.permitted_contract_types.includes(ct) ? 'var(--color-brand-cyan)' : 'transparent', color: form.permitted_contract_types.includes(ct) ? 'var(--color-ink)' : c.textDim, border: `1px solid ${c.border}` }}>{ct}</button>
            ))}
          </div>
          <textarea data-testid="afs-dec-reason" className="w-full mb-2 px-2 py-1.5 text-sm rounded-md" style={inpStyle} rows={2} placeholder="Reason / notes" value={form.reason} onChange={e => setForm(f => ({ ...f, reason: e.target.value }))} />
          <button data-testid="afs-dec-save" onClick={save} disabled={!form.model} className="w-full text-sm px-3 py-2 rounded-md font-semibold disabled:opacity-40" style={{ background: 'var(--color-success-alt)', color: '#fff' }}>Save decision</button>
        </Card>
      </div>

      <div className="lg:col-span-2">
        <p className="text-sm font-bold mb-2" style={{ color: c.text }}>Decision Memory <span className="font-normal text-xs" style={{ color: c.textDim }}>— reused automatically on future quotes</span></p>
        <div className="rounded-xl border overflow-hidden" style={{ borderColor: c.border }} data-testid="afs-decisions-list">
          {decisions.length === 0 && <p className="text-sm text-center py-10" style={{ color: c.textDim }}>No decisions yet. Record one to stop re-investigating the same model.</p>}
          {decisions.map(d => (
            <div key={d.id} data-testid={`afs-decision-${d.id}`} className="flex items-center gap-3 p-3 border-t" style={{ borderColor: c.border }}>
              <span className="text-[10px] font-bold px-2 py-1 rounded" style={{ background: statusMeta(d.status).color + '22', color: statusMeta(d.status).color }}>{statusMeta(d.status).name}</span>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium" style={{ color: c.text }}>{d.model}{d.console_type ? ` · ${d.console_type}` : ''} <span className="text-[11px]" style={{ color: c.textDim }}>({d.manufacturer})</span></p>
                <p className="text-[11px] truncate" style={{ color: c.textDim }}>{d.reason || '—'} {d.permitted_contract_types?.length ? `· allows ${d.permitted_contract_types.join('/')}` : ''}</p>
              </div>
              <button onClick={() => del(d.id)} data-testid={`afs-decision-del-${d.id}`} className="p-1" style={{ color: 'var(--color-danger)' }}><Trash2 size={14} /></button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ───────────────────────────────────────────────────────── Build Quote From Estate
function AutoQuoteTab({ API, headers, c, isDark, editQuote, setEditQuote }) {
  const [companies, setCompanies] = useState([]);
  const [companyId, setCompanyId] = useState('');
  const [estate, setEstate] = useState(null);
  const [selSites, setSelSites] = useState({});
  const [contractType, setContractType] = useState('gold');
  const [level, setLevel] = useState('standard');
  const [term, setTerm] = useState(1);
  const [discount, setDiscount] = useState(0);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [rrpEdit, setRrpEdit] = useState({});
  const [warrantyOpps, setWarrantyOpps] = useState([]);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [customData, setCustomData] = useState(null);   // {machine_services:[], travel:[]}
  const [customResult, setCustomResult] = useState(null);
  const [rateCards, setRateCards] = useState([]);
  const [savingCard, setSavingCard] = useState(false);
  const [lastFilename, setLastFilename] = useState('');
  const [customMode, setCustomMode] = useState('quick');   // 'quick' | 'wizard'
  const [wizStep, setWizStep] = useState(1);
  const [estHours, setEstHours] = useState('');
  const [incl, setIncl] = useState({ service: true, repairs: true, travel: true });
  const [visits, setVisits] = useState(1);          // PPM visits/year — travel charged per visit
  const [vatPct, setVatPct] = useState(20);         // VAT % (default 20% UK)
  const [excluded, setExcluded] = useState({});     // asset_id → true (machines left off the quote)
  const [editQuoteId, setEditQuoteId] = useState(''); // set when editing a saved quote (overwrite)
  const [includeAnnexe, setIncludeAnnexe] = useState(false); // append per-site equipment appendix to PDF
  const fileRef = useRef(null);
  const isCustom = contractType === 'custom';
  useEffect(() => {
    if (!isCustom || !companyId) { setRateCards([]); return; }
    axios.get(`${API}/crm/v2/aftersales/rate-cards?company_id=${companyId}`, { headers: headers() })
      .then(r => setRateCards(r.data?.rate_cards || [])).catch(() => setRateCards([]));
  }, [isCustom, companyId]);  // eslint-disable-line react-hooks/exhaustive-deps
  const loadCard = (rc) => {
    setCustomData({ machine_services: (rc.machine_rates || []).map(m => ({ type: m.type, service_price: m.service_price })), travel: (rc.travel_rates || []).map(t => ({ location: t.location, price: t.price })), repairs: (rc.repair_rates || []).map(r => ({ type: r.type, hourly_rate: r.hourly_rate })), summary: null });
    setCustomResult(null);
    setLastFilename(rc.name || '');
  };
  const saveCard = async () => {
    if (!companyId || !customData) return;
    const name = window.prompt('Name this rate card', lastFilename || 'Tender rate card');
    if (name === null) return;
    setSavingCard(true);
    try {
      await axios.post(`${API}/crm/v2/aftersales/rate-cards`, {
        company_id: companyId, name,
        machine_rates: (customData.machine_services || []).map(m => ({ type: m.type, service_price: Number(m.service_price) })),
        travel_rates: (customData.travel || []).map(t => ({ location: t.location, price: Number(t.price) })),
        repair_rates: (customData.repairs || []).map(rp => ({ type: rp.type, hourly_rate: Number(rp.hourly_rate) })),
        source_filename: lastFilename,
      }, { headers: headers() });
      const r = await axios.get(`${API}/crm/v2/aftersales/rate-cards?company_id=${companyId}`, { headers: headers() });
      setRateCards(r.data?.rate_cards || []);
      alert('Rate card saved for this customer');
    } catch (err) {
      alert('Could not save rate card: ' + (err?.response?.data?.detail || err.message));
    } finally { setSavingCard(false); }
  };
  const onUploadPricing = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setUploadBusy(true); setCustomData(null); setCustomResult(null);
    try {
      const fd = new FormData(); fd.append('file', f);
      const mainTok = localStorage.getItem('token');
      const up = await axios.post(`${API}/files/upload?category=contracts`, fd,
        { headers: { Authorization: `Bearer ${mainTok}` } });
      const fid = up.data?.id;
      const ex = await axios.post(`${API}/crm/v2/aftersales/extract-pricing-document?file_id=${fid}`, {},
        { headers: headers() });
      setCustomData({ machine_services: ex.data.machine_services || [], travel: ex.data.travel || [], repairs: ex.data.repairs || [], summary: ex.data.summary || null });
      setLastFilename(ex.data.source_filename || f.name || '');
      if (customMode === 'wizard') setWizStep(2);
    } catch (err) {
      alert('Could not read that document: ' + (err?.response?.data?.detail || err.message));
    } finally {
      setUploadBusy(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };
  const buildCustom = async (save) => {
    if (!companyId || !customData) return;
    setBusy(true);
    const site_ids = Object.keys(selSites).filter(k => selSites[k] && k !== '__unassigned__');
    const excluded_asset_ids = Object.keys(excluded).filter(k => excluded[k]);
    try {
      const r = await axios.post(`${API}/crm/v2/aftersales/build-custom-quote`, {
        company_id: companyId, site_ids,
        machine_rates: incl.service ? (customData.machine_services || []).map(m => ({ type: m.type, service_price: Number(m.service_price) })) : [],
        travel_rates: incl.travel ? (customData.travel || []).map(t => ({ location: t.location, price: Number(t.price) })) : [],
        repair_rates: incl.repairs ? (customData.repairs || []).map(rp => ({ type: rp.type, hourly_rate: Number(rp.hourly_rate) })) : [],
        estimated_repair_hours: incl.repairs ? Number(estHours || 0) : 0,
        term_years: Number(term), quote_discount_pct: Number(discount),
        visits_per_year: Number(visits || 1), vat_pct: Number(vatPct || 0) / 100,
        excluded_asset_ids,
        include_site_annexe: !!includeAnnexe,
        overwrite_quote_id: save ? (editQuoteId || undefined) : undefined,
        save: !!save,
      }, { headers: headers() });
      setCustomResult(r.data);
      if (save && r.data.saved_quote_id) setEditQuoteId(r.data.saved_quote_id);
    } catch (err) {
      alert(err?.response?.data?.detail || 'Could not build the quote.');
    } finally { setBusy(false); }
  };
  const toggleExcludeGroup = (item) => {
    const ids = item.asset_ids || (item.asset_id ? [item.asset_id] : []);
    setExcluded(prev => {
      const next = { ...prev };
      const on = ids.length > 0 && ids.every(id => next[id]);
      ids.forEach(id => { if (on) delete next[id]; else next[id] = true; });
      return next;
    });
  };
  // Recompute the quote whenever the exclude set changes (so unpriced count updates).
  useEffect(() => {
    if (customResult && customData && companyId) buildCustom(false);
  }, [excluded]);  // eslint-disable-line react-hooks/exhaustive-deps
  // Prefill the builder when editing a saved custom quote (overwrite on save).
  useEffect(() => {
    if (!editQuote) return;
    setContractType('custom');
    setCompanyId(editQuote.company_id || '');
    if (editQuote.company_id) loadEstate(editQuote.company_id);
    setCustomData({
      machine_services: (editQuote.machine_rates || []).map(m => ({ type: m.type, service_price: m.service_price })),
      travel: (editQuote.travel_rates || []).map(t => ({ location: t.location, price: t.price })),
      repairs: (editQuote.repair_rates || []).map(r => ({ type: r.type, hourly_rate: r.hourly_rate })),
      summary: null,
    });
    setTerm(editQuote.term_years || 1);
    setDiscount(editQuote.quote_discount_pct || 0);
    setVisits(editQuote.visits_per_year || (editQuote.summary && editQuote.summary.visits_per_year) || 1);
    setVatPct(Math.round(((editQuote.vat_pct != null ? editQuote.vat_pct : 0.2)) * 100));
    setEstHours(editQuote.estimated_repair_hours || '');
    setIncludeAnnexe(!!editQuote.include_site_annexe);
    const exc = {}; (editQuote.excluded_asset_ids || []).forEach(id => { exc[id] = true; });
    setExcluded(exc);
    setEditQuoteId(editQuote.id);
    setCustomMode('quick');
    setCustomResult(null);
    setEditQuote && setEditQuote(null);
  }, [editQuote]);  // eslint-disable-line react-hooks/exhaustive-deps
  const setMs = (i, v) => setCustomData(d => ({ ...d, machine_services: d.machine_services.map((m, idx) => idx === i ? { ...m, service_price: v } : m) }));
  const setTr = (i, v) => setCustomData(d => ({ ...d, travel: d.travel.map((t, idx) => idx === i ? { ...t, price: v } : t) }));
  const setRp = (i, v) => setCustomData(d => ({ ...d, repairs: (d.repairs || []).map((r, idx) => idx === i ? { ...r, hourly_rate: v } : r) }));
  const inpStyle = { background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text };

  useEffect(() => {
    axios.get(`${API}/crm/v2/companies?limit=200`, { headers: headers() })
      .then(r => setCompanies(r.data.companies || r.data || [])).catch(() => setCompanies([]));
    axios.get(`${API}/crm/v2/aftersales/revenue/warranty-opportunities?window_days=365`, { headers: headers() })
      .then(r => setWarrantyOpps(r.data.opportunities || [])).catch(() => setWarrantyOpps([]));
  }, [API, headers]);

  const buildProposal = useCallback((opp) => {
    setBusy(true);
    setCompanyId(opp.company_id);
    axios.post(`${API}/crm/v2/aftersales/revenue/warranty-opportunities/${opp.company_id}/build-proposal`,
      { window_days: 365, contract_type: contractType, pricing_level: level, term_years: Number(term), quote_discount_pct: Number(discount), save: true },
      { headers: headers() }).then(r => setResult(r.data)).finally(() => setBusy(false));
  }, [API, headers, contractType, level, term, discount]);

  const loadEstate = useCallback((cid) => {
    setEstate(null); setResult(null);
    if (!cid) return;
    axios.get(`${API}/crm/v2/aftersales/estate/${cid}`, { headers: headers() }).then(r => {
      setEstate(r.data);
      const sel = {}; (r.data.sites || []).forEach(s => { sel[s.id] = true; });
      setSelSites(sel);
    }).catch(() => setEstate({ sites: [], totals: {} }));
  }, [API, headers]);

  const build = useCallback((save) => {
    if (!companyId) return;
    setBusy(true);
    const site_ids = Object.keys(selSites).filter(k => selSites[k] && k !== '__unassigned__');
    axios.post(`${API}/crm/v2/aftersales/build-quote-from-estate`, {
      company_id: companyId, site_ids, contract_type: contractType, pricing_level: level,
      term_years: Number(term), quote_discount_pct: Number(discount), save: !!save,
    }, { headers: headers() }).then(r => setResult(r.data)).finally(() => setBusy(false));
  }, [API, headers, companyId, selSites, contractType, level, term, discount]);

  const resolveRrp = async (ex) => {
    const val = Number(rrpEdit[ex.config_id]);
    if (!ex.config_id || !val) return;
    await axios.put(`${API}/crm/v2/aftersales/service-configs/${ex.config_id}`,
      { manual_rrp_override: val, approval_status: 'Approved (manual RRP)' }, { headers: headers() });
    setRrpEdit(e => { const n = { ...e }; delete n[ex.config_id]; return n; });
    build(false);
  };
  const markSupported = async (ex) => {
    await axios.post(`${API}/crm/v2/aftersales/supportability/decisions`,
      { model: ex.model, console_type: ex.console_type || '', status: 'fully_supported',
        permitted_contract_types: ['silver', 'gold', 'platinum'], reason: 'Approved from auto-quote exception queue' },
      { headers: headers() });
    build(false);
  };

  const confColor = { READY_FOR_REVIEW: 'var(--color-success-alt)', REVIEW_REQUIRED: 'var(--color-accent-amber)', CANNOT_AUTO_QUOTE: 'var(--color-danger)' };
  const exColor = { RRP_REQUIRED: 'var(--color-danger)', SUPPORTABILITY: 'var(--color-accent-purple)', NOT_ELIGIBLE: 'var(--color-danger)', NOT_MATCHED: 'var(--color-text-faint-alt)', PROVISIONAL: 'var(--color-accent-amber)' };

  return (
    <div data-testid="afs-autoquote">
      {warrantyOpps.length > 0 && (
        <div className="mb-4" data-testid="afs-warranty-opps">
          <div className="flex items-center gap-2 mb-2">
            <Building2 size={16} style={{ color: 'var(--color-accent-amber)' }} />
            <p className="text-sm font-bold" style={{ color: c.text }}>Warranty → Maintenance Opportunities</p>
            <span className="text-[11px]" style={{ color: c.textDim }}>expiring warranties ready to convert</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {warrantyOpps.map(o => (
              <Card key={o.company_id} c={c} isDark={isDark} testId={`afs-warranty-${o.company_id}`}>
                <p className="text-sm font-bold" style={{ color: c.text }}>{o.company_name}</p>
                <p className="text-xs mb-1" style={{ color: c.textDim }}>{o.assets_ending_warranty} assets ending warranty · from {o.earliest_expiry}{o.days_to_earliest != null ? ` (${o.days_to_earliest}d)` : ''}</p>
                <p className="text-lg font-extrabold" style={{ color: 'var(--color-success-alt)' }}>{gbp0(o.estimated_annual_value)}<span className="text-[10px] font-normal" style={{ color: c.textDim }}> est. annual</span></p>
                <div className="flex items-center gap-2 text-[10px] mt-1 mb-2" style={{ color: c.textDim }}>
                  <span style={{ color: 'var(--color-success-alt)' }}>{o.supportability.supported} ok</span>·
                  <span style={{ color: 'var(--color-accent-amber)' }}>{o.supportability.review} review</span>
                </div>
                <button data-testid={`afs-warranty-build-${o.company_id}`} onClick={() => buildProposal(o)} disabled={busy}
                  className="w-full inline-flex items-center justify-center gap-1.5 py-2 rounded-md text-xs font-bold" style={{ background: 'var(--color-accent-amber)', color: 'var(--color-ink)' }}>
                  <Rocket size={13} /> Build Maintenance Proposal
                </button>
              </Card>
            ))}
          </div>
        </div>
      )}
      <Card c={c} isDark={isDark} className="mb-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 items-end">
          <label className="text-xs" style={{ color: c.textDim }}>Customer
            <select data-testid="afs-aq-company" value={companyId} onChange={e => { setCompanyId(e.target.value); loadEstate(e.target.value); }}
              className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={inpStyle}>
              <option value="">Select a customer…</option>
              {companies.map(co => <option key={co.id} value={co.id}>{co.name}</option>)}
            </select></label>
          <div className="grid grid-cols-4 gap-2">
            <label className="text-xs" style={{ color: c.textDim }}>Package
              <select data-testid="afs-aq-type" value={contractType} onChange={e => setContractType(e.target.value)} className="w-full mt-1 px-2 py-2 text-sm rounded-md" style={inpStyle}>
                <option value="silver">Silver</option><option value="gold">Gold</option><option value="platinum">Platinum</option><option value="custom">Custom (tender)</option></select></label>
            <label className="text-xs" style={{ color: c.textDim }}>Level
              <select value={level} onChange={e => setLevel(e.target.value)} className="w-full mt-1 px-2 py-2 text-sm rounded-md" style={inpStyle}>
                <option value="standard">Standard</option><option value="preferred">Preferred</option><option value="minimum">Minimum</option></select></label>
            <label className="text-xs" style={{ color: c.textDim }}>Term
              <input data-testid="afs-aq-term" type="number" min="1" value={term} onChange={e => setTerm(e.target.value)} className="w-full mt-1 px-2 py-2 text-sm rounded-md" style={inpStyle} /></label>
            <label className="text-xs" style={{ color: c.textDim }}>Disc %
              <input data-testid="afs-aq-discount" type="number" value={discount} onChange={e => setDiscount(e.target.value)} className="w-full mt-1 px-2 py-2 text-sm rounded-md" style={inpStyle} /></label>
          </div>
        </div>

        {estate && estate.linked_organization_id && (
          <div className="mt-3">
            <p className="text-[11px] uppercase tracking-wider mb-1" style={{ color: c.textDim }}>Sites ({estate.totals.assets} assets · {estate.totals.supported} priceable now)</p>
            <div className="flex flex-wrap gap-2" data-testid="afs-aq-sites">
              {estate.sites.map(s => (
                <button key={s.id} data-testid={`afs-aq-site-${s.id}`} onClick={() => setSelSites(x => ({ ...x, [s.id]: !x[s.id] }))}
                  className="text-xs px-2.5 py-1.5 rounded-md" style={{ border: `1px solid ${c.border}`, background: selSites[s.id] ? 'var(--color-brand-cyan)' : 'transparent', color: selSites[s.id] ? 'var(--color-ink)' : c.textDim }}>
                  {s.name} · {s.asset_count}
                </button>
              ))}
            </div>
          </div>
        )}
        {estate && !estate.linked_organization_id && (
          <p className="mt-3 text-sm" style={{ color: 'var(--color-accent-amber)' }} data-testid="afs-aq-nolink">This customer isn't linked to an operations organisation, so there's no asset estate to quote yet.</p>
        )}

        {isCustom && (
          <div className="mt-4 rounded-lg border p-3" style={{ borderColor: c.border }} data-testid="afs-aq-custom-panel">
            <div className="flex items-center gap-2 mb-2">
              <Zap size={15} style={{ color: 'var(--color-brand-cyan)' }} />
              <p className="text-sm font-bold" style={{ color: c.text }}>Custom tender pricing</p>
              <span className="text-[11px]" style={{ color: c.textDim }}>upload the signed agreement / Schedule of Charges — AI reads the prices</span>
            </div>
            {editQuoteId && (
              <div className="mb-3 flex items-center gap-2 text-xs px-3 py-2 rounded-lg" data-testid="afs-aq-editing-banner"
                style={{ background: 'var(--color-accent-purple)22', color: 'var(--color-accent-purple)' }}>
                <PenLine size={13} /> Editing saved quote — saving will overwrite it (same quote number).
                <button data-testid="afs-aq-edit-cancel" onClick={() => { setEditQuoteId(''); setCustomData(null); setCustomResult(null); setExcluded({}); }}
                  className="ml-auto underline">Start a new quote instead</button>
              </div>
            )}
            <div className="grid grid-cols-2 sm:grid-cols-2 gap-3 mb-3">
              <label className="text-xs" style={{ color: c.textDim }}>PPM visits / year (travel charged per visit)
                <input data-testid="afs-aq-visits" type="number" min="1" value={visits} onChange={e => setVisits(e.target.value)}
                  className="w-full mt-1 px-2 py-2 text-sm rounded-md" style={inpStyle} /></label>
              <label className="text-xs" style={{ color: c.textDim }}>VAT %
                <input data-testid="afs-aq-vat" type="number" min="0" step="0.5" value={vatPct} onChange={e => setVatPct(e.target.value)}
                  className="w-full mt-1 px-2 py-2 text-sm rounded-md" style={inpStyle} /></label>
            </div>
            <label className="flex items-start gap-2 mb-3 cursor-pointer text-xs" data-testid="afs-aq-annexe-toggle" style={{ color: c.textDim }}>
              <input type="checkbox" data-testid="afs-aq-annexe-checkbox" checked={includeAnnexe} onChange={e => setIncludeAnnexe(e.target.checked)} className="mt-0.5" />
              <span>Include a <b style={{ color: c.text }}>per-site equipment appendix</b> in the customer PDF — lists every station and its machines (ideal for large estates like Devon &amp; Somerset's 85 sites).</span>
            </label>
            <div className="flex gap-1 mb-3" data-testid="afs-aq-mode-toggle">
              {['quick', 'wizard'].map(m => (
                <button key={m} data-testid={`afs-aq-mode-${m}`} onClick={() => { setCustomMode(m); setWizStep(1); setCustomResult(null); }}
                  className="px-3 py-1 rounded-full text-xs font-bold"
                  style={customMode === m ? { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' } : { border: `1px solid ${c.border}`, color: c.textDim }}>
                  {m === 'quick' ? 'Quick' : 'Tender wizard'}
                </button>
              ))}
            </div>
            {customMode === 'wizard' && (
              <div data-testid="afs-aq-wizard">
                <div className="flex flex-wrap items-center gap-1.5 mb-3 text-[10px]" style={{ color: c.textDim }}>
                  {['Upload', 'Summary', 'Service', 'Repairs', 'Travel', 'Build'].map((s, i) => (
                    <span key={s} data-testid={`afs-wiz-step-${i + 1}`} className="px-2 py-0.5 rounded-full"
                      style={wizStep === i + 1 ? { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)', fontWeight: 700 } : { border: `1px solid ${c.border}` }}>{i + 1}. {s}</span>
                  ))}
                </div>
                {wizStep === 1 && (
                  <div>
                    {rateCards.length > 0 && (
                      <div className="mb-3">
                        <p className="text-[11px] uppercase tracking-wider mb-1" style={{ color: c.textDim }}>Saved rate cards</p>
                        <div className="flex flex-wrap gap-2">
                          {rateCards.map(rc => (
                            <button key={rc.id} data-testid={`afs-wiz-ratecard-${rc.id}`} onClick={() => { loadCard(rc); setWizStep(2); }}
                              className="px-3 py-1.5 rounded-full text-xs font-semibold border" style={{ borderColor: 'var(--color-brand-cyan)', color: c.text }}>
                              {rc.name} · {(rc.machine_rates || []).length} machines
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                    <input ref={fileRef} data-testid="afs-wiz-file" type="file" accept=".pdf,.xlsx,.xls,.docx,.csv,.txt" onChange={onUploadPricing} disabled={uploadBusy} className="block text-xs" style={{ color: c.textDim }} />
                    {uploadBusy && <p className="text-xs mt-2" style={{ color: c.textDim }} data-testid="afs-wiz-uploading">Reading document with AI…</p>}
                    {customData && <button data-testid="afs-wiz-next-1" onClick={() => setWizStep(2)} className="mt-3 px-4 py-2 rounded-lg text-sm font-bold" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}>Next: Summary →</button>}
                  </div>
                )}
                {wizStep === 2 && customData && (
                  <div data-testid="afs-wiz-summary">
                    {customData.summary && (
                      <div className="rounded-lg border p-3 mb-3" style={{ borderColor: c.border }}>
                        <p className="text-sm font-bold mb-1" style={{ color: c.text }}>{customData.summary.headline || 'Tender summary'}</p>
                        <div className="flex flex-wrap gap-3 text-[11px] mb-2" style={{ color: c.textDim }}>
                          {customData.summary.term && <span>Term: <b style={{ color: c.text }}>{customData.summary.term}</b></span>}
                          {customData.summary.ppm_visits && <span>PPM: <b style={{ color: c.text }}>{customData.summary.ppm_visits}</b></span>}
                          {customData.summary.sla && <span>SLA: <b style={{ color: c.text }}>{customData.summary.sla}</b></span>}
                        </div>
                        {(customData.summary.key_points || []).map((k, i) => (
                          <p key={i} className="text-xs" style={{ color: c.textDim }}>• {k}</p>
                        ))}
                      </div>
                    )}
                    <p className="text-[11px] uppercase tracking-wider mb-1" style={{ color: c.textDim }}>Include on the quote</p>
                    <div className="flex flex-wrap gap-4 mb-3">
                      {[['service', `Service (${customData.machine_services.length})`], ['repairs', `Repairs (${(customData.repairs || []).length})`], ['travel', `Travel (${customData.travel.length})`]].map(([k, lbl]) => (
                        <label key={k} className="flex items-center gap-1.5 text-xs" style={{ color: c.text }}>
                          <input type="checkbox" data-testid={`afs-wiz-incl-${k}`} checked={incl[k]} onChange={e => setIncl(s => ({ ...s, [k]: e.target.checked }))} /> {lbl}
                        </label>
                      ))}
                    </div>
                    <div className="flex gap-2">
                      <button data-testid="afs-wiz-back-2" onClick={() => setWizStep(1)} className="px-3 py-2 rounded-lg text-xs border" style={{ borderColor: c.border, color: c.text }}>← Back</button>
                      <button data-testid="afs-wiz-next-2" onClick={() => setWizStep(3)} className="px-4 py-2 rounded-lg text-sm font-bold" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}>Next: Service →</button>
                    </div>
                  </div>
                )}
                {wizStep === 3 && customData && (
                  <div data-testid="afs-wiz-service">
                    <p className="text-[11px] uppercase tracking-wider mb-1" style={{ color: c.textDim }}>Service price per machine type (£)</p>
                    <div className="space-y-1 max-h-52 overflow-auto pr-1 mb-3">
                      {customData.machine_services.map((m, i) => (
                        <div key={i} className="flex items-center gap-2">
                          <span className="flex-1 text-xs truncate" style={{ color: c.text }}>{m.type}</span>
                          <input type="number" step="0.01" value={m.service_price} onChange={e => setMs(i, e.target.value)} data-testid={`afs-wiz-ms-${i}`} className="w-20 px-2 py-1 text-xs rounded" style={inpStyle} />
                        </div>
                      ))}
                    </div>
                    <div className="flex gap-2"><button data-testid="afs-wiz-back-3" onClick={() => setWizStep(2)} className="px-3 py-2 rounded-lg text-xs border" style={{ borderColor: c.border, color: c.text }}>← Back</button><button data-testid="afs-wiz-next-3" onClick={() => setWizStep(4)} className="px-4 py-2 rounded-lg text-sm font-bold" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}>Next: Repairs →</button></div>
                  </div>
                )}
                {wizStep === 4 && customData && (
                  <div data-testid="afs-wiz-repairs">
                    <p className="text-[11px] uppercase tracking-wider mb-1" style={{ color: c.textDim }}>Repair labour £/hour</p>
                    {(customData.repairs || []).length === 0 && <p className="text-xs mb-2" style={{ color: 'var(--color-accent-amber)' }}>No repair rate found in the tender — add hours below only if you have a rate.</p>}
                    <div className="space-y-1 max-h-40 overflow-auto pr-1 mb-2">
                      {(customData.repairs || []).map((r, i) => (
                        <div key={i} className="flex items-center gap-2">
                          <span className="flex-1 text-xs truncate" style={{ color: c.text }}>{r.type}</span>
                          <input type="number" step="0.01" value={r.hourly_rate} onChange={e => setRp(i, e.target.value)} data-testid={`afs-wiz-rp-${i}`} className="w-20 px-2 py-1 text-xs rounded" style={inpStyle} />
                        </div>
                      ))}
                    </div>
                    <label className="block text-xs mb-3" style={{ color: c.textDim }}>Estimated repair hours per year (optional — for an indicative total)
                      <input type="number" min="0" value={estHours} onChange={e => setEstHours(e.target.value)} data-testid="afs-wiz-est-hours" className="w-28 ml-2 px-2 py-1 text-xs rounded" style={inpStyle} placeholder="e.g. 40" /></label>
                    <div className="flex gap-2"><button data-testid="afs-wiz-back-4" onClick={() => setWizStep(3)} className="px-3 py-2 rounded-lg text-xs border" style={{ borderColor: c.border, color: c.text }}>← Back</button><button data-testid="afs-wiz-next-4" onClick={() => setWizStep(5)} className="px-4 py-2 rounded-lg text-sm font-bold" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}>Next: Travel →</button></div>
                  </div>
                )}
                {wizStep === 5 && customData && (
                  <div data-testid="afs-wiz-travel">
                    <p className="text-[11px] uppercase tracking-wider mb-1" style={{ color: c.textDim }}>Travel per site, per visit (£)</p>
                    <div className="space-y-1 max-h-52 overflow-auto pr-1 mb-3">
                      {customData.travel.map((t, i) => (
                        <div key={i} className="flex items-center gap-2">
                          <span className="flex-1 text-xs truncate" style={{ color: c.text }}>{t.location}</span>
                          <input type="number" step="0.01" value={t.price} onChange={e => setTr(i, e.target.value)} data-testid={`afs-wiz-tr-${i}`} className="w-20 px-2 py-1 text-xs rounded" style={inpStyle} />
                        </div>
                      ))}
                    </div>
                    <div className="flex gap-2"><button data-testid="afs-wiz-back-5" onClick={() => setWizStep(4)} className="px-3 py-2 rounded-lg text-xs border" style={{ borderColor: c.border, color: c.text }}>← Back</button><button data-testid="afs-wiz-next-5" onClick={() => setWizStep(6)} className="px-4 py-2 rounded-lg text-sm font-bold" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}>Next: Build →</button></div>
                  </div>
                )}
                {wizStep === 6 && customData && (
                  <div data-testid="afs-wiz-build">
                    <div className="rounded-lg border p-3 mb-3 text-xs" style={{ borderColor: c.border, color: c.textDim }}>
                      <p>Including: {[incl.service && 'Service', incl.repairs && 'Repairs', incl.travel && 'Travel'].filter(Boolean).join(', ') || 'nothing'}</p>
                      <p>Term: <b style={{ color: c.text }}>{term} yr</b> · Discount: <b style={{ color: c.text }}>{discount}%</b>{incl.repairs && estHours ? <> · Est. repair hrs/yr: <b style={{ color: c.text }}>{estHours}</b></> : null}</p>
                    </div>
                    <div className="flex gap-2 flex-wrap">
                      <button data-testid="afs-wiz-back-6" onClick={() => setWizStep(5)} className="px-3 py-2 rounded-lg text-xs border" style={{ borderColor: c.border, color: c.text }}>← Back</button>
                      <button data-testid="afs-wiz-build-btn" onClick={() => buildCustom(false)} disabled={busy} className="px-4 py-2 rounded-lg text-sm font-bold" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}>{busy ? 'Building…' : 'Build quote'}</button>
                      <button data-testid="afs-wiz-save-ratecard" onClick={saveCard} disabled={savingCard} className="px-3 py-2 rounded-lg text-xs border" style={{ borderColor: c.border, color: c.text }}>{savingCard ? 'Saving…' : 'Save as rate card'}</button>
                    </div>
                  </div>
                )}
              </div>
            )}
            {customMode === 'quick' && (<>
            <input ref={fileRef} data-testid="afs-aq-pricing-file" type="file" accept=".pdf,.xlsx,.xls,.docx,.csv,.txt" onChange={onUploadPricing} disabled={uploadBusy}
              className="block text-xs" style={{ color: c.textDim }} />
            {rateCards.length > 0 && (
              <div className="mt-3" data-testid="afs-aq-ratecards">
                <p className="text-[11px] uppercase tracking-wider mb-1" style={{ color: c.textDim }}>Saved rate cards for this customer</p>
                <div className="flex flex-wrap gap-2">
                  {rateCards.map(rc => (
                    <button key={rc.id} data-testid={`afs-aq-ratecard-${rc.id}`} onClick={() => loadCard(rc)}
                      className="px-3 py-1.5 rounded-full text-xs font-semibold border hover:opacity-80 transition-opacity"
                      style={{ borderColor: 'var(--color-brand-cyan)', color: c.text }}>
                      {rc.name} · {(rc.machine_rates || []).length} machines
                    </button>
                  ))}
                </div>
                <p className="text-[11px] mt-1" style={{ color: c.textDim }}>Load a saved card to skip re-uploading, or upload a new document above.</p>
              </div>
            )}
            {uploadBusy && <p className="text-xs mt-2" style={{ color: c.textDim }} data-testid="afs-aq-pricing-uploading">Reading document with AI…</p>}
            {customData && (
              <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-4" data-testid="afs-aq-pricing-review">
                <div>
                  <p className="text-[11px] uppercase tracking-wider mb-1" style={{ color: c.textDim }}>Machine service prices ({customData.machine_services.length})</p>
                  <div className="space-y-1 max-h-52 overflow-auto pr-1">
                    {customData.machine_services.map((m, i) => (
                      <div key={i} className="flex items-center gap-2" data-testid={`afs-aq-ms-${i}`}>
                        <span className="flex-1 text-xs truncate" style={{ color: c.text }}>{m.type}</span>
                        <span className="text-xs" style={{ color: c.textDim }}>£</span>
                        <input type="number" step="0.01" value={m.service_price} onChange={e => setMs(i, e.target.value)}
                          data-testid={`afs-aq-ms-price-${i}`} className="w-20 px-2 py-1 text-xs rounded" style={inpStyle} />
                      </div>
                    ))}
                    {customData.machine_services.length === 0 && <p className="text-xs" style={{ color: 'var(--color-accent-amber)' }}>No machine prices found — check the document.</p>}
                  </div>
                </div>
                <div>
                  <p className="text-[11px] uppercase tracking-wider mb-1" style={{ color: c.textDim }}>Travel per site, per visit ({customData.travel.length})</p>
                  <div className="space-y-1 max-h-52 overflow-auto pr-1">
                    {customData.travel.map((t, i) => (
                      <div key={i} className="flex items-center gap-2" data-testid={`afs-aq-tr-${i}`}>
                        <span className="flex-1 text-xs truncate" style={{ color: c.text }}>{t.location}</span>
                        <span className="text-xs" style={{ color: c.textDim }}>£</span>
                        <input type="number" step="0.01" value={t.price} onChange={e => setTr(i, e.target.value)}
                          data-testid={`afs-aq-tr-price-${i}`} className="w-20 px-2 py-1 text-xs rounded" style={inpStyle} />
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
            <button data-testid="afs-aq-build-custom" onClick={() => buildCustom(false)} disabled={!companyId || !customData || busy}
              className="mt-3 inline-flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-bold disabled:opacity-40"
              style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}>
              <Rocket size={16} /> {busy ? 'Applying…' : 'Apply prices & build quote'}
            </button>
            {customData && (
              <button data-testid="afs-aq-save-ratecard" onClick={saveCard} disabled={savingCard}
                className="mt-3 ml-2 inline-flex items-center gap-1.5 px-3 py-2.5 rounded-lg text-sm font-semibold border disabled:opacity-40"
                style={{ borderColor: c.border, color: c.text }}>
                {savingCard ? 'Saving…' : 'Save as rate card'}
              </button>
            )}
            </>)}
          </div>
        )}
        {!isCustom && (
        <button data-testid="afs-aq-build" onClick={() => build(false)} disabled={!companyId || busy}
          className="mt-4 inline-flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-bold disabled:opacity-40"
          style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}>
          <Rocket size={16} /> {busy ? 'Building…' : 'Build Quote From Estate'}
        </button>
        )}
      </Card>

      {customResult && (
        <div data-testid="afs-aq-custom-result">
          {(customResult.unpriced_count || 0) > 0 && (
            <div className="mb-3 flex items-start gap-2 text-sm px-3 py-2.5 rounded-lg" data-testid="afs-aq-custom-blocked"
              style={{ background: 'var(--color-danger, #EF4444)18', color: 'var(--color-danger, #EF4444)', border: '1px solid var(--color-danger, #EF4444)' }}>
              <AlertTriangle size={16} className="mt-0.5" />
              <span><b>{customResult.unpriced_count} machine(s) aren't priced yet.</b> Add their price in the Service step, or exclude them below. This quote can't be sent until every machine is priced or excluded.</span>
            </div>
          )}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
            <Card c={c} isDark={isDark} testId="afs-aq-custom-priced"><p className="text-2xl font-extrabold" style={{ color: c.text }}>{customResult.assets_priced}/{customResult.assets_total}</p><p className="text-[10px] uppercase tracking-wider" style={{ color: c.textDim }}>Machines priced</p></Card>
            <Card c={c} isDark={isDark} testId="afs-aq-custom-unpriced"><p className="text-2xl font-extrabold" style={{ color: (customResult.unpriced_count || 0) > 0 ? 'var(--color-danger, #EF4444)' : 'var(--color-success-alt)' }}>{customResult.unpriced_count || 0}</p><p className="text-[10px] uppercase tracking-wider" style={{ color: c.textDim }}>Unpriced machines</p></Card>
            <Card c={c} isDark={isDark} testId="afs-aq-custom-annual"><p className="text-2xl font-extrabold" style={{ color: 'var(--color-success-alt)' }}>{gbp0(customResult.summary.final_annual)}</p><p className="text-[10px] uppercase tracking-wider" style={{ color: c.textDim }}>Annual (ex VAT)</p></Card>
            <Card c={c} isDark={isDark} testId="afs-aq-custom-incvat"><p className="text-2xl font-extrabold" style={{ color: c.text }}>{gbp0(customResult.summary.final_annual_inc_vat)}</p><p className="text-[10px] uppercase tracking-wider" style={{ color: c.textDim }}>Annual inc VAT</p></Card>
          </div>
          <Card c={c} isDark={isDark} testId="afs-aq-custom-lines">
            <p className="text-sm font-bold mb-2" style={{ color: c.text }}>Machines</p>
            {customResult.grouped_lines.map((g, i) => (
              <Row key={i} label={`${g.type} × ${g.qty}`} value={`${gbp(g.unit_price)} → ${gbp(g.line_total)}`} c={c} />
            ))}
            {customResult.travel_lines.length > 0 && <p className="text-sm font-bold mt-3 mb-2" style={{ color: c.text }}>Travel &amp; visits ({visits} visit{Number(visits) === 1 ? '' : 's'}/yr)</p>}
            {customResult.travel_lines.map((t, i) => (
              <Row key={i} label={`${t.site_name} (${t.location}) — ${gbp(t.per_visit != null ? t.per_visit : t.price)} × ${t.visits || 1}`} value={gbp(t.annual != null ? t.annual : t.price)} c={c} />
            ))}
            {(customResult.excluded_count || 0) > 0 && (
              <p className="text-[11px] mt-2" style={{ color: c.textDim }} data-testid="afs-aq-custom-excluded-note">{customResult.excluded_count} machine(s) excluded from this quote.</p>
            )}
            <div className="mt-2 pt-2 border-t" style={{ borderColor: c.border }}>
              <Row label="Service (annual)" value={gbp(customResult.summary.service_annual)} c={c} />
              <Row label="Travel &amp; visits (annual)" value={gbp(customResult.summary.travel_total)} c={c} />
              {customResult.summary.repair_cost > 0 && <Row label={`Repairs (est. ${customResult.summary.estimated_repair_hours}h @ ${gbp(customResult.summary.effective_repair_rate)}/hr)`} value={gbp(customResult.summary.repair_cost)} c={c} />}
              {customResult.summary.quote_discount_pct > 0 && <Row label={`Less ${customResult.summary.quote_discount_pct}% discount`} value={''} c={c} />}
              <Row label="Final annual (ex VAT)" value={gbp(customResult.summary.final_annual)} c={c} />
              <Row label={`VAT (${((customResult.summary.vat_pct || 0) * 100).toFixed(0)}%)`} value={gbp(customResult.summary.vat_amount)} c={c} />
              <Row label="Annual inc VAT" value={gbp(customResult.summary.final_annual_inc_vat)} c={c} />
            </div>
            <button data-testid="afs-aq-custom-save" onClick={() => buildCustom(true)} disabled={busy || (customResult.unpriced_count || 0) > 0}
              className="mt-3 w-full py-2 rounded-md text-sm font-bold disabled:opacity-40" style={{ background: 'var(--color-success-alt)', color: '#fff' }}>
              {busy ? 'Saving…' : ((customResult.unpriced_count || 0) > 0 ? 'Resolve unpriced machines to save' : (editQuoteId ? 'Save changes (overwrite)' : 'Save quote'))}
            </button>
            {customResult.saved_quote_id && <p className="text-[11px] mt-1 text-center" style={{ color: 'var(--color-success-alt)' }} data-testid="afs-aq-custom-saved">Saved {customResult.quote_number}</p>}
          </Card>
          {customResult.needs_review.length > 0 && (
            <Card c={c} isDark={isDark} className="mt-3" testId="afs-aq-custom-review-list">
              <p className="text-sm font-bold mb-2" style={{ color: 'var(--color-accent-amber)' }}>Machines & sites AI couldn't price ({customResult.needs_review.length})</p>
              <p className="text-[11px] mb-2" style={{ color: c.textDim }}>Add a matching price on the Service step, or exclude a machine to leave it off the quote.</p>
              {customResult.needs_review.map((r, i) => {
                const ids = r.asset_ids || (r.asset_id ? [r.asset_id] : []);
                const isExcluded = ids.length > 0 && ids.every(id => excluded[id]);
                return (
                  <div key={i} className="flex items-center gap-2 py-1" data-testid={`afs-aq-custom-review-${i}`}>
                    <span className="flex-1 text-xs" style={{ color: c.textDim }}>
                      {r.kind === 'TRAVEL' ? `Travel: ${r.site_name}` : `Machine: ${r.model}${r.count ? ` × ${r.count}` : ''}`} — {r.detail}
                    </span>
                    {r.kind !== 'TRAVEL' && (
                      <button data-testid={`afs-aq-exclude-${i}`} onClick={() => toggleExcludeGroup(r)}
                        className="text-[11px] font-semibold px-2.5 py-1 rounded-md border" style={{ borderColor: c.border, color: isExcluded ? 'var(--color-success-alt)' : c.text }}>
                        {isExcluded ? 'Excluded ✓ (undo)' : 'Exclude'}
                      </button>
                    )}
                  </div>
                );
              })}
            </Card>
          )}
        </div>
      )}

      {result && (
        <div data-testid="afs-aq-result">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
            <Card c={c} isDark={isDark} testId="afs-aq-confidence">
              <p className="text-[10px] uppercase tracking-wider" style={{ color: c.textDim }}>Confidence</p>
              <p className="text-sm font-extrabold" style={{ color: confColor[result.confidence] }}>{result.confidence.replace(/_/g, ' ')}</p>
            </Card>
            <Card c={c} isDark={isDark} testId="afs-aq-pct"><p className="text-2xl font-extrabold" style={{ color: c.text }}>{result.pct_automatically_priced}%</p><p className="text-[10px] uppercase tracking-wider" style={{ color: c.textDim }}>Auto-priced ({result.assets_priced}/{result.assets_total})</p></Card>
            <Card c={c} isDark={isDark} testId="afs-aq-exceptions"><p className="text-2xl font-extrabold" style={{ color: 'var(--color-accent-amber)' }}>{result.exception_count}</p><p className="text-[10px] uppercase tracking-wider" style={{ color: c.textDim }}>Exceptions</p></Card>
            <Card c={c} isDark={isDark} testId="afs-aq-annual"><p className="text-2xl font-extrabold" style={{ color: 'var(--color-success-alt)' }}>{gbp0(result.summary.final_annual)}</p><p className="text-[10px] uppercase tracking-wider" style={{ color: c.textDim }}>Annual (ex VAT)</p></Card>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Commercial grouped lines */}
            <Card c={c} isDark={isDark} testId="afs-aq-groups">
              <p className="text-sm font-bold mb-2" style={{ color: c.text }}>Commercial Quote (grouped)</p>
              <div className="space-y-1">
                {result.grouped_lines.map((g, i) => (
                  <div key={i} className="flex items-center gap-2 text-sm p-2 rounded-md border" style={{ borderColor: c.border }}>
                    <span className="flex-1 truncate" style={{ color: c.text }}>{g.qty} × {g.model} <span className="text-[11px]" style={{ color: c.textDim }}>{g.console_type}</span></span>
                    <span style={{ color: g.annual_total > 0 ? c.text : 'var(--color-danger)' }}>{g.annual_total > 0 ? gbp(g.annual_total) : 'RRP req.'}</span>
                  </div>
                ))}
              </div>
              <div className="mt-3 pt-3 border-t space-y-1 text-sm" style={{ borderColor: c.border }}>
                <Row label="Gold base annual" value={gbp(result.summary.gold_base_annual)} c={c} />
                <Row label={`Contract type (×${result.summary.contract_factor})`} value={gbp(result.summary.contract_type_annual)} c={c} />
                <div className="flex justify-between pt-1 border-t" style={{ borderColor: c.border }}><span className="font-bold" style={{ color: c.text }}>Final annual</span><span className="font-extrabold" style={{ color: 'var(--color-success-alt)' }}>{gbp(result.summary.final_annual)}</span></div>
                <Row label="Monthly" value={gbp(result.summary.monthly)} c={c} />
                <Row label={`Term total (${result.summary.term_years}yr)`} value={gbp(result.summary.term_total)} c={c} />
              </div>
              <button data-testid="afs-aq-save" onClick={() => build(true)} disabled={busy}
                className="mt-3 w-full py-2 rounded-md text-sm font-semibold" style={{ background: 'var(--color-success-alt)', color: '#fff' }}>Save as draft quote</button>
              {result.saved_quote_id && <p className="text-[11px] mt-1 text-center" style={{ color: 'var(--color-success-alt)' }} data-testid="afs-aq-saved">Saved {result.quote_number}</p>}
            </Card>

            {/* Exception queue */}
            <Card c={c} isDark={isDark} testId="afs-aq-exception-queue">
              <p className="text-sm font-bold mb-2" style={{ color: c.text }}>Resolve {result.exception_count} exception{result.exception_count === 1 ? '' : 's'}</p>
              <div className="space-y-2 max-h-[420px] overflow-y-auto">
                {result.exceptions.length === 0 && <p className="text-sm py-6 text-center" style={{ color: c.textDim }}>No exceptions — ready to review.</p>}
                {result.exceptions.map((ex, i) => (
                  <div key={i} data-testid={`afs-aq-exc-${i}`} className="p-2.5 rounded-md border" style={{ borderColor: c.border }}>
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-[9px] font-bold px-1.5 py-0.5 rounded" style={{ background: (exColor[ex.kind] || c.textDim) + '22', color: exColor[ex.kind] || c.textDim }}>{ex.kind.replace(/_/g, ' ')}</span>
                      <span className="text-xs flex-1 truncate" style={{ color: c.text }}>{ex.detail}</span>
                    </div>
                    {(ex.kind === 'RRP_REQUIRED') && ex.config_id && (
                      <div className="flex items-center gap-1.5 mt-1">
                        <input data-testid={`afs-aq-rrp-${i}`} type="number" placeholder="Approved RRP £" value={rrpEdit[ex.config_id] || ''} onChange={e => setRrpEdit(x => ({ ...x, [ex.config_id]: e.target.value }))} className="flex-1 px-2 py-1 text-xs rounded" style={inpStyle} />
                        <button data-testid={`afs-aq-rrp-save-${i}`} onClick={() => resolveRrp(ex)} className="text-xs px-2 py-1 rounded" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}>Set</button>
                      </div>
                    )}
                    {(ex.kind === 'SUPPORTABILITY' || ex.kind === 'PROVISIONAL') && (
                      <button data-testid={`afs-aq-approve-${i}`} onClick={() => markSupported(ex)} className="mt-1 text-xs px-2 py-1 rounded" style={{ background: 'var(--color-success-alt)', color: '#fff' }}>Approve as supported</button>
                    )}
                  </div>
                ))}
              </div>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}

// ───────────────────────────────────────────────────────── Renewals & RPI
function RenewalsRpiTab({ API, headers, c, isDark }) {
  const [rpi, setRpi] = useState([]);
  const [renewals, setRenewals] = useState([]);
  const [edit, setEdit] = useState({});
  const [renResult, setRenResult] = useState({});
  const [busy, setBusy] = useState('');
  const inpStyle = { background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text };

  const load = useCallback(() => {
    Promise.all([
      axios.get(`${API}/crm/v2/aftersales/rpi/reviews?window_days=200`, { headers: headers() }),
      axios.get(`${API}/crm/v2/aftersales/renewals/pipeline?window_days=200`, { headers: headers() }),
    ]).then(([a, b]) => { setRpi(a.data.reviews || []); setRenewals(b.data.renewals || []); });
  }, [API, headers]);
  useEffect(load, [load]);

  const setRpiPct = async (cid) => {
    const pct = Number(edit[cid]); if (!pct) return;
    setBusy('rpi-' + cid);
    try { await axios.post(`${API}/crm/v2/aftersales/rpi/reviews/${cid}`, { rpi_pct: pct, source: 'Manual entry' }, { headers: headers() }); load(); } finally { setBusy(''); }
  };
  const approveRpi = async (rid) => { setBusy('rpi-' + rid); try { await axios.post(`${API}/crm/v2/aftersales/rpi/reviews/${rid}/approve`, {}, { headers: headers() }); load(); } finally { setBusy(''); } };
  const buildRenewal = async (cid) => {
    setBusy('ren-' + cid);
    try { const r = await axios.post(`${API}/crm/v2/aftersales/renewals/${cid}/build`, {}, { headers: headers() }); setRenResult(x => ({ ...x, [cid]: r.data })); load(); }
    catch (e) { setRenResult(x => ({ ...x, [cid]: { error: e.response?.data?.detail || 'Build failed' } })); } finally { setBusy(''); }
  };

  return (
    <div data-testid="afs-renewals" className="space-y-6">
      {/* RPI */}
      <div>
        <div className="flex items-center gap-2 mb-2"><TrendingUp size={16} style={{ color: 'var(--color-accent-amber)' }} /><h3 className="text-sm font-bold" style={{ color: c.text }}>RPI Reviews</h3><span className="text-[11px]" style={{ color: c.textDim }}>index-linked increases (figure entered manually — never assumed)</span></div>
        <div className="space-y-2" data-testid="afs-rpi-list">
          {rpi.length === 0 && <p className="text-sm py-4 text-center" style={{ color: c.textDim }}>No active contracts to review.</p>}
          {rpi.map(r => {
            const rev = r.review;
            return (
              <Card key={r.contract_id} c={c} isDark={isDark} testId={`afs-rpi-${r.contract_id}`}>
                <div className="flex flex-wrap items-center gap-3">
                  <div className="flex-1 min-w-[180px]">
                    <p className="text-sm font-semibold" style={{ color: c.text }}>{r.company_name} {r.due && <span className="text-[9px] px-1.5 py-0.5 rounded ml-1" style={{ background: 'var(--color-accent-amber)22', color: 'var(--color-accent-amber)' }}>DUE</span>}</p>
                    <p className="text-xs" style={{ color: c.textDim }}>Anniversary {r.anniversary_date} ({r.days_to_anniversary}d) · current {gbp(r.current_annual_value)}</p>
                  </div>
                  {(!rev || rev.status !== 'approved') && (
                    <div className="flex items-center gap-1.5">
                      <input data-testid={`afs-rpi-input-${r.contract_id}`} type="number" step="0.1" placeholder="RPI %" value={edit[r.contract_id] ?? (rev?.rpi_pct ?? '')} onChange={e => setEdit(x => ({ ...x, [r.contract_id]: e.target.value }))} className="w-20 px-2 py-1 text-sm rounded-md text-right" style={inpStyle} />
                      <button data-testid={`afs-rpi-set-${r.contract_id}`} onClick={() => setRpiPct(r.contract_id)} disabled={busy === 'rpi-' + r.contract_id} className="text-xs px-2.5 py-1.5 rounded-md" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}>Calculate</button>
                    </div>
                  )}
                  {rev && (
                    <div className="text-right">
                      <p className="text-sm font-bold" style={{ color: rev.status === 'approved' ? 'var(--color-success-alt)' : c.text }}>{gbp(rev.proposed_value)} <span className="text-[10px] font-normal" style={{ color: c.textDim }}>(+{rev.rpi_pct}%)</span></p>
                      <p className="text-[10px]" style={{ color: c.textDim }}>eff {rev.effective_date} · {rev.status}</p>
                    </div>
                  )}
                  {rev && rev.status === 'proposed' && (
                    <button data-testid={`afs-rpi-approve-${r.contract_id}`} onClick={() => approveRpi(rev.id)} disabled={busy === 'rpi-' + rev.id} className="text-xs px-3 py-1.5 rounded-md font-semibold" style={{ background: 'var(--color-success-alt)', color: '#fff' }}>Approve</button>
                  )}
                </div>
              </Card>
            );
          })}
        </div>
      </div>

      {/* Renewals */}
      <div>
        <div className="flex items-center gap-2 mb-2"><RefreshCw size={16} style={{ color: 'var(--color-info-ios)' }} /><h3 className="text-sm font-bold" style={{ color: c.text }}>Renewal Pipeline</h3><span className="text-[11px]" style={{ color: c.textDim }}>contracts approaching expiry — renew against the CURRENT estate</span></div>
        <div className="space-y-2" data-testid="afs-renewals-list">
          {renewals.length === 0 && <p className="text-sm py-4 text-center" style={{ color: c.textDim }}>No contracts due for renewal in the window.</p>}
          {renewals.map(r => {
            const res = renResult[r.id];
            return (
              <Card key={r.id} c={c} isDark={isDark} testId={`afs-renewal-${r.id}`}>
                <div className="flex flex-wrap items-center gap-3">
                  <div className="flex-1 min-w-[180px]">
                    <p className="text-sm font-semibold" style={{ color: c.text }}>{r.company_name}</p>
                    <p className="text-xs" style={{ color: c.textDim }}>Ends {r.end_date} ({r.days_to_expiry}d) · current {gbp(r.annual_value)}</p>
                  </div>
                  <button data-testid={`afs-renewal-build-${r.id}`} onClick={() => buildRenewal(r.id)} disabled={busy === 'ren-' + r.id} className="text-xs px-3 py-1.5 rounded-md font-semibold inline-flex items-center gap-1.5" style={{ background: 'var(--color-info-ios)', color: '#fff' }}><Rocket size={13} /> {busy === 'ren-' + r.id ? 'Building…' : 'Build Renewal'}</button>
                </div>
                {res && res.error && <p className="text-xs mt-2" style={{ color: 'var(--color-accent-amber)' }}>{res.error}</p>}
                {res && res.renewal_comparison && (
                  <div className="mt-2 pt-2 border-t flex flex-wrap items-center gap-4 text-sm" style={{ borderColor: c.border }} data-testid={`afs-renewal-result-${r.id}`}>
                    <span style={{ color: c.textDim }}>Previous <b style={{ color: c.text }}>{gbp(res.renewal_comparison.previous_annual)}</b></span>
                    <span style={{ color: c.textDim }}>Proposed <b style={{ color: 'var(--color-success-alt)' }}>{gbp(res.renewal_comparison.proposed_annual)}</b></span>
                    {res.renewal_comparison.change_pct != null && (
                      <span style={{ color: res.renewal_comparison.change_amount >= 0 ? 'var(--color-success-alt)' : 'var(--color-danger)' }}>
                        {res.renewal_comparison.change_amount >= 0 ? '+' : ''}{gbp(res.renewal_comparison.change_amount)} ({res.renewal_comparison.change_pct}%)
                      </span>
                    )}
                    <span className="text-[11px]" style={{ color: c.textDim }}>{res.assets_priced}/{res.assets_total} priced · {res.exception_count} exceptions · saved {res.quote_number}</span>
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ───────────────────────────────────────────────────────── Agreements + Activation
const AG_STATUS = {
  draft: { label: 'Draft', color: 'var(--color-text-faint-alt)' },
  ready: { label: 'Ready', color: 'var(--color-info-ios)' },
  sent: { label: 'Sent', color: 'var(--color-info-ios)' },
  signed: { label: 'Signed', color: 'var(--color-accent-purple)' },
  active: { label: 'Active', color: 'var(--color-success-alt)' },
  activation_attention: { label: 'Activation Attention', color: 'var(--color-danger)' },
};

function AgreementsTab({ API, headers, c, isDark, setEditQuote, goTo }) {
  const [agreements, setAgreements] = useState([]);
  const [quotes, setQuotes] = useState([]);
  const [allQuotes, setAllQuotes] = useState([]);
  const [portalLinks, setPortalLinks] = useState({});
  const [copiedId, setCopiedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [busy, setBusy] = useState(false);
  const [newQuoteId, setNewQuoteId] = useState('');
  const [startDate, setStartDate] = useState('2026-07-01');
  const [payMethod, setPayMethod] = useState('annual');
  const [visits, setVisits] = useState(2);
  const [sign, setSign] = useState({ signatory_name: '', position: '', email: '', authority_confirmed: false });
  const [showSign, setShowSign] = useState(false);
  const inpStyle = { background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text };

  const load = useCallback(() => {
    Promise.all([
      axios.get(`${API}/crm/v2/aftersales/agreements`, { headers: headers() }),
      axios.get(`${API}/crm/v2/aftersales/quotes`, { headers: headers() }),
    ]).then(([a, q]) => {
      setAgreements(a.data.agreements || []);
      const qs = q.data.quotes || [];
      setAllQuotes(qs);
      setQuotes(qs.filter(x => ['draft', 'accepted'].includes(x.status)));
      setPortalLinks(prev => {
        const next = { ...prev };
        qs.forEach(x => { if (x.public_shortcode) next[x.id] = `${window.location.origin}/aq/${x.public_shortcode}`; });
        return next;
      });
    });
  }, [API, headers]);
  useEffect(load, [load]);

  const viewQuotePdf = async (id) => {
    try {
      const r = await axios.get(`${API}/crm/v2/aftersales/quotes/${id}/pdf`, { headers: headers(), responseType: 'blob' });
      window.open(URL.createObjectURL(r.data), '_blank');
    } catch { alert('Could not open the quote PDF.'); }
  };
  const editQuoteRow = async (q) => {
    try {
      const r = await axios.get(`${API}/crm/v2/aftersales/quotes/${q.id}`, { headers: headers() });
      setEditQuote && setEditQuote(r.data);
      goTo && goTo('autoquote');
    } catch { alert('Could not open this quote for editing.'); }
  };
  const [historyFor, setHistoryFor] = useState(null);
  const [historyData, setHistoryData] = useState(null);
  const [verView, setVerView] = useState(null);
  const [verBusy, setVerBusy] = useState(false);
  const openHistory = async (q) => {
    setHistoryFor(q); setHistoryData(null); setVerView(null);
    try {
      const r = await axios.get(`${API}/crm/v2/aftersales/quotes/${q.id}/versions`, { headers: headers() });
      setHistoryData(r.data);
    } catch { alert('Could not load version history.'); setHistoryFor(null); }
  };
  const viewVersion = async (ver) => {
    try {
      const r = await axios.get(`${API}/crm/v2/aftersales/quotes/${historyFor.id}/versions/${ver}`, { headers: headers() });
      setVerView(r.data);
    } catch { alert('Could not load that version.'); }
  };
  const revertVersion = async (ver) => {
    if (!window.confirm(`Revert this quote to v${ver}? The current version is saved to history first, so you can undo.`)) return;
    setVerBusy(true);
    try {
      await axios.post(`${API}/crm/v2/aftersales/quotes/${historyFor.id}/versions/${ver}/revert`, {}, { headers: headers() });
      const r = await axios.get(`${API}/crm/v2/aftersales/quotes/${historyFor.id}/versions`, { headers: headers() });
      setHistoryData(r.data); setVerView(null);
      load();
    } catch (e) { alert(e?.response?.data?.detail || 'Revert failed.'); }
    finally { setVerBusy(false); }
  };
  const makePortalLink = async (id) => {
    try {
      const r = await axios.post(`${API}/crm/v2/aftersales/quotes/${id}/portal-link`, { valid_days: 30 }, { headers: headers() });
      setPortalLinks(p => ({ ...p, [id]: r.data.url }));
      try { await navigator.clipboard.writeText(r.data.url); setCopiedId(id); setTimeout(() => setCopiedId(null), 2500); } catch {}
      load();
    } catch { alert('Could not create the acceptance link.'); }
  };
  const [emailBusy, setEmailBusy] = useState(null);
  const [emailedId, setEmailedId] = useState(null);
  const sendQuoteEmail = async (q) => {
    let email = q.portal_contact_email;
    if (!email || !email.includes('@')) {
      email = window.prompt(`Send quote ${q.quote_number} to which customer email?`, email || '');
    }
    if (!email || !email.includes('@')) return;
    setEmailBusy(q.id);
    try {
      await axios.post(`${API}/crm/v2/aftersales/quotes/${q.id}/send-email`, { contact_email: email }, { headers: headers() });
      setEmailedId(q.id); setTimeout(() => setEmailedId(null), 3500);
      load();
    } catch (e) { alert(e?.response?.data?.detail || 'Could not send the quote email.'); }
    finally { setEmailBusy(null); }
  };
  const [chaseDays, setChaseDays] = useState('14,5');
  const [chaseSaved, setChaseSaved] = useState(false);
  const [chasersBusy, setChasersBusy] = useState(false);
  const [chaserResult, setChaserResult] = useState(null);
  useEffect(() => {
    axios.get(`${API}/crm/v2/aftersales/settings`, { headers: headers() })
      .then(r => setChaseDays(r.data.quote_chase_days || '14,5')).catch(() => {});
  }, [API, headers]);
  const saveChaseDays = async () => {
    await axios.put(`${API}/crm/v2/aftersales/settings`, { quote_chase_days: chaseDays }, { headers: headers() });
    setChaseSaved(true); setTimeout(() => setChaseSaved(false), 2500);
  };
  const runChasers = async () => {
    setChasersBusy(true);
    try {
      const r = await axios.post(`${API}/crm/v2/aftersales/quotes/chasers/run`, {}, { headers: headers() });
      setChaserResult(r.data); setTimeout(() => setChaserResult(null), 5000); load();
    } catch { alert('Could not run follow-ups.'); }
    finally { setChasersBusy(false); }
  };
  const daysUntil = (s) => {
    if (!s) return null;
    const d = new Date(s); if (isNaN(d)) return null;
    return Math.round((d - new Date()) / 86400000);
  };

  const openDetail = (id) => axios.get(`${API}/crm/v2/aftersales/agreements/${id}`, { headers: headers() }).then(r => { setDetail(r.data); setShowSign(false); });
  const refreshDetail = () => detail && openDetail(detail.id);

  const prepare = async () => {
    if (!newQuoteId) return;
    setBusy(true);
    try {
      const r = await axios.post(`${API}/crm/v2/aftersales/agreements/from-quote/${newQuoteId}`,
        { start_date: startDate, payment_method: payMethod, visits_per_year: Number(visits) }, { headers: headers() });
      setNewQuoteId(''); load(); openDetail(r.data.id);
    } finally { setBusy(false); }
  };
  const patch = async (body) => { await axios.patch(`${API}/crm/v2/aftersales/agreements/${detail.id}`, body, { headers: headers() }); refreshDetail(); };
  const generate = async () => { setBusy(true); try { await axios.post(`${API}/crm/v2/aftersales/agreements/${detail.id}/generate`, {}, { headers: headers() }); refreshDetail(); load(); } catch (e) { alert((e.response?.data?.detail?.reasons || ['Not ready']).join('\n')); } finally { setBusy(false); } };
  const doSign = async () => {
    setBusy(true);
    try { await axios.post(`${API}/crm/v2/aftersales/agreements/${detail.id}/sign`, sign, { headers: headers() }); setShowSign(false); refreshDetail(); load(); }
    catch (e) { alert(e.response?.data?.detail || 'Sign failed'); } finally { setBusy(false); }
  };
  const activate = async () => { setBusy(true); try { await axios.post(`${API}/crm/v2/aftersales/agreements/${detail.id}/activate`, {}, { headers: headers() }); refreshDetail(); load(); } finally { setBusy(false); } };

  const stepIcon = (st) => st === 'ok' ? <CheckCircle2 size={13} style={{ color: 'var(--color-success-alt)' }} />
    : st === 'warning' ? <AlertTriangle size={13} style={{ color: 'var(--color-accent-amber)' }} />
      : st === 'queued' ? <Clock size={13} style={{ color: 'var(--color-info-ios)' }} />
        : <Circle size={13} style={{ color: c.textDim }} />;

  // ── Detail view ──
  if (detail) {
    const ag = detail;
    const s = ag.schedules || {};
    const health = ag.health || { ready: false, reasons: [] };
    const st = AG_STATUS[ag.status] || AG_STATUS.draft;
    const unresolvedWording = (ag.wording_conflicts || []).filter(w => w.status !== 'resolved');
    return (
      <div data-testid="afs-agreement-detail">
        <button data-testid="afs-ag-back" onClick={() => setDetail(null)} className="text-xs mb-3" style={{ color: c.textDim }}>← Back to agreements</button>
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-xl font-extrabold" style={{ color: c.text }}>{ag.agreement_number}</h2>
            <p className="text-sm" style={{ color: c.textDim }}>{ag.company_name} · {ag.contract_type} · {gbp(ag.annual_value)}/yr · {ag.term_years}yr</p>
          </div>
          <span data-testid="afs-ag-status" className="text-xs font-bold px-3 py-1.5 rounded-lg" style={{ background: st.color + '22', color: st.color }}>{st.label}</span>
        </div>

        {/* Health */}
        <Card c={c} isDark={isDark} testId="afs-ag-health" className="mb-3">
          <div className="flex items-center gap-2 mb-1">
            {health.ready ? <CheckCircle2 size={16} style={{ color: 'var(--color-success-alt)' }} /> : <AlertTriangle size={16} style={{ color: 'var(--color-accent-amber)' }} />}
            <p className="text-sm font-bold" style={{ color: health.ready ? 'var(--color-success-alt)' : 'var(--color-accent-amber)' }}>{health.ready ? 'Contract Ready' : `${health.reasons.length} item(s) require attention`}</p>
          </div>
          {health.reasons.map((r, i) => <p key={i} className="text-xs ml-6" style={{ color: c.textDim }}>• {r}</p>)}
        </Card>

        {/* Controls */}
        <Card c={c} isDark={isDark} className="mb-3">
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-xs" style={{ color: c.textDim }}>Payment method
              <select data-testid="afs-ag-payment" value={ag.payment_method || 'annual'} onChange={e => patch({ payment_method: e.target.value })} className="block mt-1 px-2 py-1.5 text-sm rounded-md" style={inpStyle}>
                <option value="annual">Annual</option><option value="monthly">Monthly (Direct Debit)</option><option value="lump_sum">Lump Sum</option></select></label>
            {ag.payment_method === 'monthly' && (
              <label className="text-xs flex items-center gap-1.5" style={{ color: c.textDim }}>
                <input data-testid="afs-ag-dd" type="checkbox" checked={!!ag.direct_debit_received} onChange={e => patch({ direct_debit_received: e.target.checked })} /> DD mandate received</label>
            )}
            {unresolvedWording.length > 0 && (
              <button data-testid="afs-ag-resolve-wording" onClick={() => patch({ resolve_wording: true })} className="text-xs px-3 py-1.5 rounded-md" style={{ background: 'var(--color-danger)22', color: 'var(--color-danger)' }}>Approve wording ({unresolvedWording.length})</button>
            )}
          </div>
        </Card>

        {/* Schedules */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 mb-3">
          <Card c={c} isDark={isDark} testId="afs-ag-s1">
            <p className="text-xs font-bold uppercase tracking-wider mb-2" style={{ color: c.textDim }}>Schedule 1 — Parties & Sites</p>
            <p className="text-sm" style={{ color: c.text }}><b>Supplier:</b> {s.schedule1_parties?.supplier?.name}</p>
            <p className="text-sm" style={{ color: c.text }}><b>Customer:</b> {s.schedule1_parties?.customer?.legal_name || '—'}</p>
            <p className="text-xs mt-1" style={{ color: c.textDim }}>{(s.schedule1_parties?.sites || []).map(x => x.name).join(', ')}</p>
          </Card>
          <Card c={c} isDark={isDark} testId="afs-ag-s2">
            <p className="text-xs font-bold uppercase tracking-wider mb-2" style={{ color: c.textDim }}>Schedule 2 — Agreement & Payment</p>
            <p className="text-sm" style={{ color: c.text }}>{s.schedule2_agreement?.agreement_type}</p>
            <p className="text-xs" style={{ color: c.textDim }}>{ag.start_date} → {ag.end_date}</p>
            <div className="text-xs mt-1" style={{ color: c.textDim }}>Monthly {gbp(s.schedule2_agreement?.payment_options?.monthly)} · Annual {gbp(s.schedule2_agreement?.payment_options?.annual)} · Lump {gbp(s.schedule2_agreement?.payment_options?.lump_sum)}</div>
          </Card>
        </div>
        <Card c={c} isDark={isDark} testId="afs-ag-s3" className="mb-3">
          <p className="text-xs font-bold uppercase tracking-wider mb-2" style={{ color: c.textDim }}>Schedule 3 — Equipment</p>
          <table className="w-full text-sm"><tbody>
            {(s.schedule3_equipment || []).map((row, i) => (
              <tr key={i} className="border-t" style={{ borderColor: c.border }}>
                <td className="py-1.5" style={{ color: c.text }}>{row.quantity} × {row.machine}</td>
                <td className="py-1.5 text-xs" style={{ color: row.serials_assigned < row.serials_expected ? 'var(--color-accent-amber)' : c.textDim }}>serials {row.serials_assigned}/{row.serials_expected}</td>
                <td className="py-1.5 text-right" style={{ color: c.text }}>{gbp(row.annual_total)}</td>
              </tr>
            ))}
          </tbody></table>
        </Card>

        {/* Sign panel */}
        {showSign && (
          <Card c={c} isDark={isDark} testId="afs-ag-sign-form" className="mb-3">
            <p className="text-sm font-bold mb-2" style={{ color: c.text }}>Electronic Signature</p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2 mb-2">
              <input data-testid="afs-sign-name" placeholder="Signatory name" value={sign.signatory_name} onChange={e => setSign(x => ({ ...x, signatory_name: e.target.value }))} className="px-2 py-1.5 text-sm rounded-md" style={inpStyle} />
              <input data-testid="afs-sign-position" placeholder="Position" value={sign.position} onChange={e => setSign(x => ({ ...x, position: e.target.value }))} className="px-2 py-1.5 text-sm rounded-md" style={inpStyle} />
              <input data-testid="afs-sign-email" placeholder="Email" value={sign.email} onChange={e => setSign(x => ({ ...x, email: e.target.value }))} className="px-2 py-1.5 text-sm rounded-md" style={inpStyle} />
            </div>
            <label className="text-xs flex items-center gap-2 mb-2" style={{ color: c.textDim }}>
              <input data-testid="afs-sign-authority" type="checkbox" checked={sign.authority_confirmed} onChange={e => setSign(x => ({ ...x, authority_confirmed: e.target.checked }))} />
              I confirm I have authority to sign this agreement on behalf of the customer.</label>
            <button data-testid="afs-sign-submit" onClick={doSign} disabled={busy || !sign.signatory_name || !sign.authority_confirmed} className="text-sm px-4 py-2 rounded-md font-semibold disabled:opacity-40" style={{ background: 'var(--color-accent-purple)', color: '#fff' }}>Sign agreement</button>
          </Card>
        )}

        {/* Activation steps */}
        {ag.activation_steps && (
          <Card c={c} isDark={isDark} testId="afs-ag-activation" className="mb-3">
            <p className="text-xs font-bold uppercase tracking-wider mb-2" style={{ color: c.textDim }}>Activation</p>
            {ag.activation_steps.map((step, i) => (
              <div key={i} className="flex items-center gap-2 text-xs py-0.5" style={{ color: c.text }}>{stepIcon(step.status)} {step.step.replace(/_/g, ' ')} {step.detail ? <span style={{ color: c.textDim }}>— {step.detail}</span> : null}</div>
            ))}
            {ag.contract_id && <p className="text-[11px] mt-2" style={{ color: 'var(--color-success-alt)' }}>Live contract {ag.agreement_number} created.</p>}
          </Card>
        )}

        {/* Action bar */}
        <div className="flex flex-wrap gap-2">
          {ag.status === 'draft' && <button data-testid="afs-ag-generate" onClick={generate} disabled={busy || !health.ready} className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-bold disabled:opacity-40" style={{ background: 'var(--color-info-ios)', color: '#fff' }}><FileCheck2 size={16} /> Generate Agreement</button>}
          {(ag.status === 'ready' || ag.status === 'sent') && <button data-testid="afs-ag-open-sign" onClick={() => setShowSign(true)} className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-bold" style={{ background: 'var(--color-accent-purple)', color: '#fff' }}><PenLine size={16} /> Review & Sign</button>}
          {ag.status === 'signed' && <button data-testid="afs-ag-activate" onClick={activate} disabled={busy} className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-bold" style={{ background: 'var(--color-success-alt)', color: '#fff' }}><Rocket size={16} /> Activate Contract</button>}
        </div>

        {/* Timeline */}
        {ag.timeline && (
          <div className="mt-4">
            <p className="text-xs font-bold uppercase tracking-wider mb-1" style={{ color: c.textDim }}>Timeline</p>
            {ag.timeline.slice().reverse().map((t, i) => <p key={i} className="text-xs" style={{ color: c.textDim }}>{(t.at || '').slice(0, 16).replace('T', ' ')} — {t.event}</p>)}
          </div>
        )}
      </div>
    );
  }

  // ── List view ──
  const QUOTE_STATUS = {
    draft: { label: 'Draft', color: 'var(--color-text-faint-alt)' },
    sent: { label: 'Sent to customer', color: 'var(--color-info-ios)' },
    accepted: { label: 'Accepted', color: 'var(--color-success-alt)' },
    declined: { label: 'Declined', color: 'var(--color-danger-alt, #EF4444)' },
    agreement: { label: 'Agreement prepared', color: 'var(--color-accent-purple)' },
  };
  return (
    <div data-testid="afs-agreements">
      {/* Customer quotes — PDF + acceptance link (commercial portal) */}
      <Card c={c} isDark={isDark} className="mb-4" testId="afs-customer-quotes">
        <p className="text-sm font-bold mb-1" style={{ color: c.text }}>Customer quotes</p>
        <p className="text-xs mb-3" style={{ color: c.textDim }}>Download the branded PDF or share a secure link for the customer to accept &amp; sign online.</p>
        <div className="flex items-center gap-2 mb-3 flex-wrap" data-testid="afs-chasers-row">
          <Clock size={13} style={{ color: c.textDim }} />
          <span className="text-xs" style={{ color: c.textDim }}>Chase unsigned quotes at (days before expiry)</span>
          <input data-testid="afs-chase-days-input" type="text" value={chaseDays} onChange={e => setChaseDays(e.target.value)}
            placeholder="14,5" className="text-xs px-2 py-1 rounded-md border w-24" style={{ background: isDark ? '#0d0d0d' : '#fff', borderColor: c.border, color: c.text }} />
          <button data-testid="afs-chase-days-save" onClick={saveChaseDays}
            className="text-xs px-3 py-1 rounded-md border" style={{ borderColor: c.border, color: c.text }}>{chaseSaved ? 'Saved ✓' : 'Save'}</button>
          <div className="flex-1" />
          <button data-testid="afs-chasers-run" onClick={runChasers} disabled={chasersBusy}
            className="text-xs px-3 py-1.5 rounded-md inline-flex items-center gap-1.5 disabled:opacity-50" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}>
            <Mail size={13} /> {chasersBusy ? 'Sending…' : 'Run follow-ups now'}
          </button>
          {chaserResult && <span className="text-[11px]" data-testid="afs-chasers-result" style={{ color: c.textDim }}>{chaserResult.chasers_sent} reminder(s), {chaserResult.expired_notified} expired</span>}
        </div>
        {allQuotes.length === 0 ? (
          <p className="text-xs" style={{ color: c.textDim }}>No saved quotes yet — build one in the Build Quote tab.</p>
        ) : (
          <div className="space-y-2">
            {allQuotes.map(q => {
              const ps = q.portal_status || q.status;
              const st = QUOTE_STATUS[ps] || QUOTE_STATUS.draft;
              const link = portalLinks[q.id];
              return (
                <div key={q.id} data-testid={`afs-quote-row-${q.id}`} className="p-3 rounded-lg border" style={{ borderColor: c.border }}>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-semibold" style={{ color: c.text }}>{q.quote_number}</span>
                    <span className="text-xs" style={{ color: c.textDim }}>· {q.company_name} · {gbp0(q.summary?.final_annual)}/yr</span>
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded" style={{ background: st.color + '22', color: st.color }}>{st.label}</span>
                    {(() => {
                      const d = daysUntil(q.valid_until);
                      const unsigned = q.public_shortcode && !['accepted', 'declined'].includes(q.portal_status);
                      if (unsigned && d != null) {
                        const col = d < 0 ? 'var(--color-danger, #EF4444)' : d <= 5 ? 'var(--color-danger, #EF4444)' : d <= 14 ? 'var(--color-accent-amber, #E0972A)' : c.textDim;
                        return <span data-testid={`afs-quote-expiry-${q.id}`} className="text-[10px] font-semibold px-2 py-0.5 rounded" style={{ background: col + '22', color: col }}>{d < 0 ? 'expired' : `expires in ${d}d`}</span>;
                      }
                      return null;
                    })()}
                    {(q.chases_sent || []).length > 0 && (
                      <span data-testid={`afs-quote-chased-${q.id}`} className="text-[10px] px-2 py-0.5 rounded" style={{ background: isDark ? '#1a1a1a' : 'var(--color-neutral-100)', color: c.textDim }}>
                        reminded {q.chases_sent.map(x => `${x}d`).join(', ')}
                      </span>
                    )}
                    {(q.unpriced_count || 0) > 0 && (
                      <span data-testid={`afs-quote-unpriced-${q.id}`} className="text-[10px] font-bold px-2 py-0.5 rounded inline-flex items-center gap-1"
                        style={{ background: 'var(--color-danger, #EF4444)22', color: 'var(--color-danger, #EF4444)' }}>
                        <AlertTriangle size={11} /> {q.unpriced_count} unpriced — edit to send
                      </span>
                    )}
                    <div className="flex-1" />
                    {(q.source === 'custom_tender_upload' || q.contract_type === 'custom') && (
                      <button data-testid={`afs-quote-edit-${q.id}`} onClick={() => editQuoteRow(q)}
                        className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1.5 rounded-md" style={{ background: 'transparent', color: c.textDim, border: `1px solid ${c.border}` }}>
                        <PenLine size={13} /> Edit
                      </button>
                    )}
                    {(q.source === 'custom_tender_upload' || q.contract_type === 'custom') && (q.version || 1) > 1 && (
                      <button data-testid={`afs-quote-history-${q.id}`} onClick={() => openHistory(q)}
                        className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1.5 rounded-md" style={{ background: 'transparent', color: c.textDim, border: `1px solid ${c.border}` }}>
                        <History size={13} /> History (v{q.version})
                      </button>
                    )}
                    <button data-testid={`afs-quote-pdf-${q.id}`} onClick={() => viewQuotePdf(q.id)}
                      className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1.5 rounded-md" style={{ background: 'transparent', color: c.textDim, border: `1px solid ${c.border}` }}>
                      <FileText size={13} /> PDF
                    </button>
                    <button data-testid={`afs-quote-email-${q.id}`} onClick={() => sendQuoteEmail(q)} disabled={emailBusy === q.id || (q.unpriced_count || 0) > 0}
                      title={(q.unpriced_count || 0) > 0 ? 'Resolve unpriced machines before sending' : ''}
                      className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1.5 rounded-md disabled:opacity-40" style={{ background: 'transparent', color: c.textDim, border: `1px solid ${c.border}` }}>
                      <Mail size={13} /> {emailedId === q.id ? 'Sent ✓' : (emailBusy === q.id ? 'Sending…' : 'Send to customer')}
                    </button>
                    <button data-testid={`afs-quote-link-${q.id}`} onClick={() => makePortalLink(q.id)} disabled={(q.unpriced_count || 0) > 0}
                      title={(q.unpriced_count || 0) > 0 ? 'Resolve unpriced machines before sharing' : ''}
                      className="inline-flex items-center gap-1.5 text-xs font-bold px-2.5 py-1.5 rounded-md disabled:opacity-40" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}>
                      <Share2 size={13} /> {copiedId === q.id ? 'Copied ✓' : (link ? 'Copy link' : 'Create link')}
                    </button>
                  </div>
                  {link && (
                    <div className="mt-2 text-[11px] font-mono px-2 py-1 rounded truncate" data-testid={`afs-quote-linkurl-${q.id}`}
                         style={{ background: isDark ? 'var(--color-ink-alt)' : 'var(--color-neutral-100)', color: c.textDim }}>{link}</div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </Card>

      <Card c={c} isDark={isDark} className="mb-4">
        <p className="text-sm font-bold mb-2" style={{ color: c.text }}>Prepare agreement from an accepted quote</p>
        <div className="flex flex-wrap items-end gap-2">
          <label className="text-xs flex-1 min-w-[220px]" style={{ color: c.textDim }}>Quote
            <select data-testid="afs-ag-quote" value={newQuoteId} onChange={e => setNewQuoteId(e.target.value)} className="w-full mt-1 px-2 py-2 text-sm rounded-md" style={inpStyle}>
              <option value="">Select a saved quote…</option>
              {quotes.map(q => <option key={q.id} value={q.id}>{q.quote_number} · {q.company_name} · {gbp0(q.summary?.final_annual)} ({q.status})</option>)}
            </select></label>
          <label className="text-xs" style={{ color: c.textDim }}>Start date
            <input data-testid="afs-ag-start" type="date" value={startDate} onChange={e => setStartDate(e.target.value)} className="block mt-1 px-2 py-2 text-sm rounded-md" style={inpStyle} /></label>
          <label className="text-xs" style={{ color: c.textDim }}>Payment
            <select value={payMethod} onChange={e => setPayMethod(e.target.value)} className="block mt-1 px-2 py-2 text-sm rounded-md" style={inpStyle}>
              <option value="annual">Annual</option><option value="monthly">Monthly</option><option value="lump_sum">Lump Sum</option></select></label>
          <label className="text-xs" style={{ color: c.textDim }}>Visits/yr
            <input type="number" min="1" value={visits} onChange={e => setVisits(e.target.value)} className="block mt-1 w-16 px-2 py-2 text-sm rounded-md" style={inpStyle} /></label>
          <button data-testid="afs-ag-prepare" onClick={prepare} disabled={!newQuoteId || busy} className="px-4 py-2 rounded-lg text-sm font-bold disabled:opacity-40" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}>{busy ? '…' : 'Prepare Agreement'}</button>
        </div>
      </Card>

      <div className="rounded-xl border overflow-hidden" style={{ borderColor: c.border }} data-testid="afs-agreements-list">
        {agreements.length === 0 && <p className="text-sm text-center py-10" style={{ color: c.textDim }}>No agreements yet — prepare one from a saved quote above.</p>}
        {agreements.map(ag => {
          const st = AG_STATUS[ag.status] || AG_STATUS.draft;
          return (
            <button key={ag.id} data-testid={`afs-ag-row-${ag.id}`} onClick={() => openDetail(ag.id)} className="w-full flex items-center gap-3 p-3 border-t text-left" style={{ borderColor: c.border }}>
              <FileCheck2 size={16} style={{ color: st.color }} />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold" style={{ color: c.text }}>{ag.agreement_number} · {ag.company_name}</p>
                <p className="text-xs" style={{ color: c.textDim }}>{ag.contract_type} · {gbp(ag.annual_value)}/yr · {ag.start_date || 'no dates'}</p>
              </div>
              <span className="text-[10px] font-bold px-2 py-1 rounded" style={{ background: st.color + '22', color: st.color }}>{st.label}</span>
            </button>
          );
        })}
      </div>

      {historyFor && (
        <div className="fixed inset-0 z-[300] flex items-center justify-center p-4" data-testid="afs-history-modal"
          style={{ background: 'rgba(0,0,0,0.55)' }} onClick={() => { setHistoryFor(null); setVerView(null); }}>
          <div className="w-full max-w-2xl max-h-[85vh] overflow-y-auto rounded-2xl p-5" style={{ background: isDark ? 'var(--color-ink)' : '#fff', border: `1px solid ${c.border}` }} onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <div>
                <p className="text-sm font-bold" style={{ color: c.text }}>Version history</p>
                <p className="text-xs" style={{ color: c.textDim }}>{historyFor.quote_number} · {historyFor.company_name}</p>
              </div>
              <button data-testid="afs-history-close" onClick={() => { setHistoryFor(null); setVerView(null); }} style={{ color: c.textDim }}><X size={18} /></button>
            </div>

            {!historyData ? (
              <p className="text-sm py-8 text-center" style={{ color: c.textDim }}>Loading…</p>
            ) : (
              <div className="space-y-2">
                <div className="flex items-center justify-between px-3 py-2.5 rounded-lg" data-testid="afs-history-current"
                  style={{ background: 'var(--color-brand-cyan)18', border: '1px solid var(--color-brand-cyan)' }}>
                  <div>
                    <span className="text-sm font-bold" style={{ color: c.text }}>Current · v{historyData.current_version}</span>
                    <span className="text-xs ml-2" style={{ color: c.textDim }}>{gbp0(historyData.current.final_annual)}/yr {historyData.current.quote_health === 'BLOCKED' ? '· ⚠ unpriced' : ''}</span>
                  </div>
                  <span className="text-[10px] uppercase font-bold tracking-wide" style={{ color: 'var(--color-brand-cyan)' }}>Live</span>
                </div>
                {(historyData.versions || []).length === 0 && (
                  <p className="text-xs py-4 text-center" style={{ color: c.textDim }} data-testid="afs-history-empty">No previous versions yet.</p>
                )}
                {(historyData.versions || []).map(v => (
                  <div key={v.version} className="flex items-center gap-3 px-3 py-2.5 rounded-lg border" data-testid={`afs-history-v-${v.version}`} style={{ borderColor: c.border }}>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold" style={{ color: c.text }}>v{v.version} · {gbp0(v.final_annual)}/yr</p>
                      <p className="text-[11px]" style={{ color: c.textDim }}>{v.edited_by || 'unknown'} · {v.created_at ? new Date(v.created_at).toLocaleString('en-GB') : ''}</p>
                    </div>
                    <button data-testid={`afs-history-view-${v.version}`} onClick={() => viewVersion(v.version)}
                      className="inline-flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-md" style={{ background: 'transparent', color: c.textDim, border: `1px solid ${c.border}` }}>
                      <Eye size={13} /> View
                    </button>
                    <button data-testid={`afs-history-revert-${v.version}`} onClick={() => revertVersion(v.version)} disabled={verBusy}
                      className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1.5 rounded-md disabled:opacity-40" style={{ background: 'var(--color-accent-purple)', color: '#fff' }}>
                      <RotateCw size={13} /> Revert
                    </button>
                  </div>
                ))}

                {verView && (
                  <div className="mt-3 pt-3 border-t" data-testid="afs-history-snapshot" style={{ borderColor: c.border }}>
                    <p className="text-sm font-bold mb-2" style={{ color: c.text }}>Viewing v{verView.version}</p>
                    <div className="rounded-lg p-3" style={{ background: isDark ? 'var(--color-ink-alt)' : 'var(--color-neutral-100)' }}>
                      {(verView.snapshot?.grouped_lines || []).map((g, i) => (
                        <Row key={`m${i}`} label={`${g.type || g.model} × ${g.qty}`} value={`${gbp(g.unit_price)} → ${gbp(g.line_total || g.annual_total)}`} c={c} />
                      ))}
                      {(verView.snapshot?.travel_lines || []).map((t, i) => (
                        <Row key={`t${i}`} label={`Travel: ${t.site_name} × ${t.visits || 1}`} value={gbp(t.annual != null ? t.annual : t.price)} c={c} />
                      ))}
                      <div className="mt-2 pt-2 border-t" style={{ borderColor: c.border }}>
                        <Row label="Annual (ex VAT)" value={gbp(verView.snapshot?.summary?.final_annual)} c={c} />
                        <Row label={`VAT (${((verView.snapshot?.summary?.vat_pct || 0) * 100).toFixed(0)}%)`} value={gbp(verView.snapshot?.summary?.vat_amount)} c={c} />
                        <Row label="Annual inc VAT" value={gbp(verView.snapshot?.summary?.final_annual_inc_vat)} c={c} />
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ───────────────────────────────────────────────────────── Live Compliance
const SYNC_META = {
  synced: { label: 'Synced', color: 'var(--color-success-alt)', icon: CheckCircle2 },
  ok: { label: 'Synced', color: 'var(--color-success-alt)', icon: CheckCircle2 },
  pending: { label: 'Pending', color: 'var(--color-warning-alt, #F59E0B)', icon: Clock },
  queued: { label: 'Queued', color: 'var(--color-warning-alt, #F59E0B)', icon: Clock },
  failed: { label: 'Failed', color: 'var(--color-danger-alt, #EF4444)', icon: AlertTriangle },
  not_synced: { label: 'Not synced', color: 'var(--color-text-faint-alt)', icon: MinusCircle },
};

function CompliancePill({ tone, icon: Icon, children, testId }) {
  const map = {
    ok: 'var(--color-success-alt)',
    warn: 'var(--color-warning-alt, #F59E0B)',
    bad: 'var(--color-danger-alt, #EF4444)',
    neutral: 'var(--color-text-faint-alt)',
  };
  const col = map[tone] || map.neutral;
  return (
    <span data-testid={testId} className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-1 rounded-md"
          style={{ background: `${col}18`, color: col }}>
      {Icon && <Icon size={12} />} {children}
    </span>
  );
}

function SyncBadge({ label, status, testId }) {
  const m = SYNC_META[status] || SYNC_META.not_synced;
  const Icon = m.icon;
  return (
    <span data-testid={testId} className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-1 rounded-md"
          style={{ background: `${m.color}14`, color: m.color }}>
      <Icon size={12} /> {label}: {m.label}
    </span>
  );
}

function ReportsTab({ API, headers, c, isDark }) {
  const [data, setData] = useState(null);
  const [labourRate, setLabourRate] = useState('75');
  const [ratio, setRatio] = useState('50');
  const [saved, setSaved] = useState(false);

  const load = useCallback(() => {
    axios.get(`${API}/crm/v2/aftersales/reports`, { headers: headers() })
      .then(r => {
        setData(r.data);
        setLabourRate(String(r.data.high_claim?.labour_rate ?? 75));
        setRatio(String(Math.round((r.data.high_claim?.ratio_threshold ?? 0.5) * 100)));
      }).catch(() => setData({ forecast: {}, high_claim: {} }));
  }, [API, headers]);
  useEffect(() => { load(); }, [load]);

  const saveSettings = async () => {
    await axios.put(`${API}/crm/v2/aftersales/settings`,
      { labour_rate: parseFloat(labourRate) || 75, high_claim_ratio: (parseFloat(ratio) || 50) / 100 },
      { headers: headers() });
    setSaved(true); setTimeout(() => setSaved(false), 2000); load();
  };

  if (!data) return <Spinner />;
  const f = data.forecast || {}; const hc = data.high_claim || {};
  const maxMonth = Math.max(1, ...(f.months || []).map(m => m.amount));
  const stat = (label, val, testId, color) => (
    <div className="p-4 rounded-xl border" data-testid={testId} style={{ background: isDark ? '#111' : 'var(--color-neutral-50)', borderColor: c.border }}>
      <div className="text-2xl font-extrabold" style={{ color: color || c.text }}>{val}</div>
      <div className="text-[11px] font-medium mt-0.5" style={{ color: c.textDim }}>{label}</div>
    </div>
  );

  return (
    <div data-testid="afs-reports">
      <div className="mb-2">
        <h2 className="text-lg font-bold" style={{ color: c.text }}>Profitability &amp; forecast</h2>
        <p className="text-xs" style={{ color: c.textDim }}>Recurring-revenue forecast and high-claim contract warnings — from live billing &amp; service-desk data.</p>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        {stat('Annual recurring revenue', gbp0(f.arr), 'afs-reports-arr', 'var(--color-success-alt)')}
        {stat('Active contracts', f.active_contracts || 0, 'afs-reports-active')}
        {stat('Forecast next 12 mo', gbp0(f.total_12m), 'afs-reports-total12m', 'var(--color-brand-cyan)')}
        {stat('High-claim warnings', hc.flagged_count || 0, 'afs-reports-flagged', (hc.flagged_count ? 'var(--color-danger, #EF4444)' : c.text))}
      </div>

      <Card c={c} isDark={isDark} className="mb-6" testId="afs-reports-forecast">
        <p className="text-sm font-bold mb-3" style={{ color: c.text }}>12-month recurring-revenue forecast</p>
        <div className="space-y-1.5">
          {(f.months || []).map(m => (
            <div key={m.month} data-testid={`afs-report-month-${m.month}`} className="flex items-center gap-3">
              <span className="text-xs w-16 shrink-0" style={{ color: c.textDim }}>{m.month}</span>
              <div className="flex-1 h-4 rounded" style={{ background: isDark ? '#0d0d0d' : 'var(--color-neutral-100)' }}>
                <div className="h-4 rounded" style={{ width: `${Math.round(m.amount / maxMonth * 100)}%`, minWidth: m.amount > 0 ? '4px' : '0', background: 'var(--color-brand-cyan)' }} />
              </div>
              <span className="text-xs w-20 text-right tabular-nums" style={{ color: c.text }}>{gbp0(m.amount)}</span>
            </div>
          ))}
        </div>
        {(f.expiring_soon || []).length > 0 && (
          <div className="mt-4 pt-3 border-t" style={{ borderColor: c.border }} data-testid="afs-reports-expiring">
            <p className="text-xs font-bold mb-1.5" style={{ color: c.textDim }}>Expiring in next 12 months ({f.expiring_soon.length})</p>
            {f.expiring_soon.map(e => (
              <div key={e.contract_id} className="flex justify-between text-xs" style={{ color: c.text }}>
                <span>{e.company_name} · {e.contract_number}</span>
                <span style={{ color: c.textDim }}>{e.end_date} · {gbp0(e.annual_value)}/yr</span>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card c={c} isDark={isDark} testId="afs-reports-highclaim">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <p className="text-sm font-bold" style={{ color: c.text }}>High-claim contract warnings</p>
          <div className="flex items-center gap-2">
            <span className="text-xs" style={{ color: c.textDim }}>Labour £/hr</span>
            <input data-testid="afs-reports-labour-rate" type="number" value={labourRate} onChange={e => setLabourRate(e.target.value)}
              className="text-xs px-2 py-1 rounded-md border w-16" style={{ background: isDark ? '#0d0d0d' : '#fff', borderColor: c.border, color: c.text }} />
            <span className="text-xs" style={{ color: c.textDim }}>Flag at ≥</span>
            <input data-testid="afs-reports-ratio" type="number" value={ratio} onChange={e => setRatio(e.target.value)}
              className="text-xs px-2 py-1 rounded-md border w-14" style={{ background: isDark ? '#0d0d0d' : '#fff', borderColor: c.border, color: c.text }} />
            <span className="text-xs" style={{ color: c.textDim }}>%</span>
            <button data-testid="afs-reports-save" onClick={saveSettings}
              className="text-xs px-3 py-1 rounded-md" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}>{saved ? 'Saved ✓' : 'Save'}</button>
          </div>
        </div>
        {(hc.contracts || []).length === 0 ? (
          <p className="text-xs" style={{ color: c.textDim }}>No reactive/repair service cases logged against active contracts in the last 12 months.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-xs" style={{ color: c.textDim }}>
                <th className="text-left py-1.5">Contract</th><th className="text-right py-1.5">Annual</th>
                <th className="text-right py-1.5">Claims</th><th className="text-right py-1.5">Est. claim cost</th>
                <th className="text-right py-1.5">Margin</th><th className="text-right py-1.5"></th>
              </tr></thead>
              <tbody>
                {hc.contracts.map(r => (
                  <tr key={r.contract_id} data-testid={`afs-highclaim-row-${r.contract_id}`} className="border-t" style={{ borderColor: c.border }}>
                    <td className="py-2" style={{ color: c.text }}>{r.company_name}<br /><span className="text-[10px]" style={{ color: c.textDim }}>{r.contract_number}</span></td>
                    <td className="py-2 text-right tabular-nums" style={{ color: c.textDim }}>{gbp0(r.annual_value)}</td>
                    <td className="py-2 text-right tabular-nums" style={{ color: c.text }}>{r.claim_count}</td>
                    <td className="py-2 text-right tabular-nums" style={{ color: c.text }}>{gbp0(r.est_claim_cost)}</td>
                    <td className="py-2 text-right tabular-nums font-semibold" style={{ color: r.margin_pct != null && r.margin_pct < 50 ? 'var(--color-danger, #EF4444)' : 'var(--color-success-alt)' }}>{r.margin_pct != null ? `${r.margin_pct}%` : '—'}</td>
                    <td className="py-2 text-right">{r.flagged && <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded" style={{ background: 'var(--color-danger, #EF4444)22', color: 'var(--color-danger, #EF4444)' }}><AlertTriangle size={11} /> HIGH</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

function AmendModal({ contractId, API, headers, c, isDark, onClose, onApplied }) {
  const [data, setData] = useState(null);
  const [action, setAction] = useState('add');
  const [selected, setSelected] = useState({});
  const [effDate, setEffDate] = useState(new Date().toISOString().slice(0, 10));
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState([]);

  const load = useCallback(() => {
    axios.get(`${API}/crm/v2/aftersales/contracts/${contractId}/amendable-assets`, { headers: headers() })
      .then(r => setData(r.data)).catch(() => setData({ covered: [], coverable: [] }));
    axios.get(`${API}/crm/v2/aftersales/contracts/${contractId}/amendments`, { headers: headers() })
      .then(r => setHistory(r.data.amendments || [])).catch(() => {});
  }, [API, headers, contractId]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { setSelected({}); setPreview(null); }, [action]);

  const list = data ? (action === 'add' ? data.coverable : data.covered) : [];
  const ids = Object.keys(selected).filter(k => selected[k]);

  const doPreview = async () => {
    if (!ids.length) return;
    setBusy(true);
    try {
      const r = await axios.post(`${API}/crm/v2/aftersales/contracts/${contractId}/amendments/preview`,
        { action, asset_ids: ids, effective_date: effDate }, { headers: headers() });
      setPreview(r.data);
    } catch (e) { alert(e?.response?.data?.detail || 'Preview failed'); }
    finally { setBusy(false); }
  };
  const doApply = async () => {
    if (!ids.length) return;
    setBusy(true);
    try {
      await axios.post(`${API}/crm/v2/aftersales/contracts/${contractId}/amendments`,
        { action, asset_ids: ids, effective_date: effDate }, { headers: headers() });
      onApplied && onApplied();
      onClose();
    } catch (e) { alert(e?.response?.data?.detail || 'Apply failed'); }
    finally { setBusy(false); }
  };

  const panel = isDark ? '#111' : '#fff';
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.5)' }} data-testid="afs-amend-modal">
      <div className="w-full max-w-2xl max-h-[88vh] overflow-y-auto rounded-2xl p-5" style={{ background: panel, border: `1px solid ${c.border}` }}>
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Calculator size={16} style={{ color: 'var(--color-brand-cyan)' }} />
            <h3 className="text-base font-bold" style={{ color: c.text }}>Amend contract</h3>
          </div>
          <button data-testid="afs-amend-close" onClick={onClose} className="p-1 rounded-md" style={{ color: c.textDim }}><X size={18} /></button>
        </div>
        {data && (
          <p className="text-xs mb-3" style={{ color: c.textDim }}>
            {data.contract?.contract_number} · current {gbp0(data.contract?.annual_value)}/yr · pro-rata to {data.contract?.next_anniversary || 'anniversary'}
          </p>
        )}
        <div className="flex gap-1.5 mb-3">
          <button data-testid="afs-amend-tab-add" onClick={() => setAction('add')}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold inline-flex items-center gap-1.5"
            style={action === 'add' ? { background: 'var(--color-success-alt)', color: '#fff' } : { background: 'transparent', color: c.textDim, border: `1px solid ${c.border}` }}>
            <Plus size={13} /> Add equipment
          </button>
          <button data-testid="afs-amend-tab-remove" onClick={() => setAction('remove')}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold inline-flex items-center gap-1.5"
            style={action === 'remove' ? { background: 'var(--color-danger-alt, #EF4444)', color: '#fff' } : { background: 'transparent', color: c.textDim, border: `1px solid ${c.border}` }}>
            <Trash2 size={13} /> Remove equipment
          </button>
        </div>
        <div className="flex items-center gap-2 mb-3">
          <span className="text-xs" style={{ color: c.textDim }}>Effective date</span>
          <input data-testid="afs-amend-effective-date" type="date" value={effDate} onChange={e => { setEffDate(e.target.value); setPreview(null); }}
            className="text-xs px-2 py-1 rounded-md border" style={{ background: isDark ? '#0d0d0d' : '#fff', borderColor: c.border, color: c.text }} />
        </div>
        <div className="rounded-lg border mb-3 max-h-56 overflow-y-auto" style={{ borderColor: c.border }} data-testid="afs-amend-asset-list">
          {!data ? <Spinner /> : list.length === 0 ? (
            <p className="text-xs p-3" style={{ color: c.textDim }}>{action === 'add' ? 'No uncovered machines available on this site.' : 'No machines currently covered by this contract.'}</p>
          ) : list.map(a => (
            <label key={a.asset_id} data-testid={`afs-amend-asset-${a.asset_id}`} className="flex items-center gap-2 px-3 py-2 border-b cursor-pointer" style={{ borderColor: c.border }}>
              <input type="checkbox" checked={!!selected[a.asset_id]} onChange={e => { setSelected(s => ({ ...s, [a.asset_id]: e.target.checked })); setPreview(null); }} />
              <span className="text-sm flex-1" style={{ color: c.text }}>{a.model}{a.console_type ? ` · ${a.console_type}` : ''} {a.serial_number ? <span style={{ color: c.textDim }}>({a.serial_number})</span> : null}</span>
              <span className="text-xs font-semibold" style={{ color: c.textDim }}>{gbp(a.annual)}/yr</span>
            </label>
          ))}
        </div>
        {preview && (
          <div className="rounded-lg p-3 mb-3 text-sm" data-testid="afs-amend-preview-result" style={{ background: isDark ? '#0d0d0d' : 'var(--color-neutral-50)', border: `1px solid ${c.border}` }}>
            <div className="flex justify-between" style={{ color: c.textDim }}><span>Annual change</span><span className="font-semibold" style={{ color: c.text }}>{preview.delta_annual >= 0 ? '+' : ''}{gbp(preview.delta_annual)}</span></div>
            <div className="flex justify-between" style={{ color: c.textDim }}><span>One-off pro-rata ({preview.days_remaining}d to anniversary)</span><span className="font-semibold" style={{ color: preview.pro_rata_amount < 0 ? 'var(--color-danger-alt, #EF4444)' : c.text }}>{preview.pro_rata_amount >= 0 ? '+' : ''}{gbp(preview.pro_rata_amount)}</span></div>
            <div className="flex justify-between border-t pt-1 mt-1" style={{ borderColor: c.border }}><span style={{ color: c.text }}>New annual value</span><span className="font-bold" style={{ color: 'var(--color-brand-cyan)' }}>{gbp(preview.new_annual)}</span></div>
          </div>
        )}
        <div className="flex gap-2">
          <button data-testid="afs-amend-preview-btn" onClick={doPreview} disabled={busy || !ids.length}
            className="flex-1 px-4 py-2.5 rounded-xl text-sm font-bold disabled:opacity-50" style={{ background: 'transparent', color: c.text, border: `1px solid ${c.border}` }}>
            {busy ? '…' : `Preview (${ids.length})`}
          </button>
          <button data-testid="afs-amend-apply-btn" onClick={doApply} disabled={busy || !ids.length || !preview}
            className="flex-1 px-4 py-2.5 rounded-xl text-sm font-bold disabled:opacity-50" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}>
            Confirm amendment
          </button>
        </div>
        {history.length > 0 && (
          <div className="mt-4" data-testid="afs-amend-history">
            <h4 className="text-xs font-bold uppercase mb-1.5" style={{ color: c.textDim }}>Amendment history</h4>
            <ul className="space-y-1">
              {history.map(h => (
                <li key={h.id} className="text-xs flex justify-between" style={{ color: c.textDim }}>
                  <span>{h.effective_date} · {h.action} {h.asset_ids?.length} machine(s)</span>
                  <span>{h.delta_annual >= 0 ? '+' : ''}{gbp(h.delta_annual)} → {gbp0(h.new_annual)}/yr</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}


function FinanceSyncBlock({ contractId, API, headers, c, status, onChanged }) {
  const [busy, setBusy] = useState('');
  const [msg, setMsg] = useState('');

  const dl = async (fmt) => {
    setBusy('dl');
    try {
      const r = await axios.get(`${API}/crm/v2/aftersales/finance/sync/${contractId}/export?format=${fmt}`,
        { headers: headers(), responseType: 'blob' });
      const type = fmt === 'json' ? 'application/json' : 'text/csv';
      const url = URL.createObjectURL(new Blob([r.data], { type }));
      const a = document.createElement('a');
      a.href = url; a.download = `sicon-${contractId}.${fmt}`;
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    } catch { setMsg('Nothing to export yet.'); }
    setBusy('');
  };
  const retry = async () => {
    setBusy('retry'); setMsg('');
    try {
      const r = await axios.post(`${API}/crm/v2/aftersales/finance/sync/${contractId}/retry`, {}, { headers: headers() });
      setMsg(r.data.status === 'synced' ? 'Posted to Sicon ✔'
        : r.data.status === 'awaiting_credentials' ? 'Queued — connect Sicon to auto-post, or export.'
        : `Sync failed: ${r.data.detail || 'see logs'}`);
      onChanged && onChanged();
    } catch { setMsg('Retry failed.'); }
    setBusy('');
  };
  const markSynced = async () => {
    const ref = window.prompt('Enter the Sage/Sicon Sales Order reference (optional):', '');
    if (ref === null) return;
    setBusy('mark'); setMsg('');
    try {
      await axios.post(`${API}/crm/v2/aftersales/finance/sync/${contractId}/mark-synced`,
        { external_ref: ref || null }, { headers: headers() });
      setMsg('Marked as synced ✔'); onChanged && onChanged();
    } catch { setMsg('Could not update.'); }
    setBusy('');
  };

  const label = status === 'synced' ? 'Synced to Sage (via Sicon)'
    : status === 'failed' ? 'Sync failed — retry or export'
    : 'Queued — export for Sage, or connect Sicon to auto-post';
  const col = status === 'synced' ? 'var(--color-success-alt)'
    : status === 'failed' ? 'var(--color-danger-alt, #EF4444)' : 'var(--color-warning-alt, #F59E0B)';

  return (
    <div data-testid={`afs-finance-sync-${contractId}`} className="mt-3 p-3 rounded-lg border"
         style={{ borderColor: c.border }}>
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2 text-xs font-semibold" style={{ color: col }}>
          <Receipt size={13} /> Finance sync (Sage 200 · Sicon): {label}
        </div>
        <div className="flex items-center gap-1.5">
          <button data-testid={`afs-finance-export-csv-${contractId}`} onClick={() => dl('csv')} disabled={!!busy}
            className="text-[11px] font-semibold px-2.5 py-1 rounded-md inline-flex items-center gap-1"
            style={{ border: `1px solid ${c.border}`, color: c.textDim }}>
            <FileSpreadsheet size={12} /> CSV
          </button>
          <button data-testid={`afs-finance-export-json-${contractId}`} onClick={() => dl('json')} disabled={!!busy}
            className="text-[11px] font-semibold px-2.5 py-1 rounded-md inline-flex items-center gap-1"
            style={{ border: `1px solid ${c.border}`, color: c.textDim }}>
            <FileText size={12} /> JSON
          </button>
          <button data-testid={`afs-finance-retry-${contractId}`} onClick={retry} disabled={!!busy}
            className="text-[11px] font-semibold px-2.5 py-1 rounded-md inline-flex items-center gap-1"
            style={{ border: `1px solid ${c.border}`, color: c.textDim }}>
            <RotateCw size={12} className={busy === 'retry' ? 'animate-spin' : ''} /> Sync now
          </button>
          <button data-testid={`afs-finance-mark-${contractId}`} onClick={markSynced} disabled={!!busy}
            className="text-[11px] font-semibold px-2.5 py-1 rounded-md inline-flex items-center gap-1"
            style={{ background: 'var(--color-success-alt)', color: '#fff' }}>
            <CheckCircle2 size={12} /> Mark synced
          </button>
        </div>
      </div>
      {msg && <p className="text-[11px] mt-2" style={{ color: c.textDim }}>{msg}</p>}
    </div>
  );
}

const FIN_META = {
  synced: { label: 'Synced to Sage', color: 'var(--color-success-alt)', icon: CheckCircle2 },
  queued: { label: 'Queued', color: 'var(--color-warning-alt, #F59E0B)', icon: Clock },
  failed: { label: 'Failed', color: 'var(--color-danger-alt, #EF4444)', icon: AlertTriangle },
  no_order: { label: 'No order yet', color: 'var(--color-text-faint-alt)', icon: MinusCircle },
};

function FinanceDashboard({ API, headers, c, isDark }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    axios.get(`${API}/crm/v2/aftersales/finance/dashboard`, { headers: headers() })
      .then(r => setData(r.data))
      .catch(() => setData({ contracts: [], totals: {} }))
      .finally(() => setLoading(false));
  }, [API, headers]);
  useEffect(() => { load(); }, [load]);

  const exportCsv = async (scope) => {
    setBusy('exp-' + scope);
    try {
      if (scope === 'outstanding') {
        await axios.post(`${API}/crm/v2/aftersales/finance/sync/enqueue-outstanding`, {}, { headers: headers() });
      }
      const qs = scope === 'outstanding' ? '?status=outstanding' : '';
      const r = await axios.get(`${API}/crm/v2/aftersales/finance/sync/export/all${qs}`,
        { headers: headers(), responseType: 'blob' });
      const url = URL.createObjectURL(new Blob([r.data], { type: 'text/csv' }));
      const a = document.createElement('a');
      a.href = url; a.download = `sicon-sales-orders-${scope}-${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
      if (scope === 'outstanding') await load();
    } catch { alert(scope === 'outstanding' ? 'Nothing outstanding to export.' : 'Nothing to export yet.'); }
    setBusy('');
  };
  const rowAction = async (cid, kind) => {
    setBusy(cid + kind);
    try {
      if (kind === 'retry') {
        await axios.post(`${API}/crm/v2/aftersales/finance/sync/${cid}/retry`, {}, { headers: headers() });
      } else if (kind === 'mark') {
        const ref = window.prompt('Sage/Sicon Sales Order reference (optional):', '');
        if (ref === null) { setBusy(''); return; }
        await axios.post(`${API}/crm/v2/aftersales/finance/sync/${cid}/mark-synced`, { external_ref: ref || null }, { headers: headers() });
      } else if (kind === 'csv') {
        const r = await axios.get(`${API}/crm/v2/aftersales/finance/sync/${cid}/export?format=csv`, { headers: headers(), responseType: 'blob' });
        const url = URL.createObjectURL(new Blob([r.data], { type: 'text/csv' }));
        const a = document.createElement('a'); a.href = url; a.download = `sicon-${cid}.csv`;
        document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url); setBusy(''); return;
      }
      await load();
    } catch { alert('Action failed.'); }
    setBusy('');
  };

  const t = data?.totals || {};
  const rows = data?.contracts || [];
  const chips = [
    { label: 'Active contracts', value: t.total || 0, tone: 'neutral' },
    { label: 'Synced to Sage', value: t.synced || 0, tone: 'ok' },
    { label: 'Outstanding', value: t.outstanding || 0, tone: t.outstanding ? 'warn' : 'ok' },
    { label: 'Value outstanding', value: gbp0(t.value_outstanding || 0), tone: t.outstanding ? 'warn' : 'ok' },
  ];

  return (
    <div data-testid="afs-finance-dashboard">
      <div className="flex items-start justify-between gap-3 mb-3 flex-wrap">
        <div>
          <h2 className="text-lg font-bold" style={{ color: c.text }}>Finance sync — Sage 200 (via Sicon)</h2>
          <p className="text-xs" style={{ color: c.textDim }}>
            Every active contract's Sales Order posting status.{' '}
            <span data-testid="afs-finance-live-badge" style={{ color: data?.live_connected ? 'var(--color-success-alt)' : 'var(--color-warning-alt, #F59E0B)', fontWeight: 600 }}>
              {data?.live_connected ? 'Sicon WebAPI connected — auto-posting' : 'Sicon WebAPI not connected — export for import'}
            </span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button data-testid="afs-finance-refresh" onClick={load}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium"
            style={{ background: 'transparent', color: c.textDim, border: `1px solid ${c.border}` }}>
            <RotateCw size={13} /> Refresh
          </button>
          <button data-testid="afs-finance-export-outstanding" onClick={() => exportCsv('outstanding')} disabled={!!busy}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold"
            style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}>
            <FileSpreadsheet size={13} /> Export outstanding
          </button>
          <button data-testid="afs-finance-export-all-dash" onClick={() => exportCsv('all')} disabled={!!busy}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium"
            style={{ background: 'transparent', color: c.textDim, border: `1px solid ${c.border}` }}>
            <FileSpreadsheet size={13} /> Export all
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4" data-testid="afs-finance-stats">
        {chips.map(ch => (
          <div key={ch.label} className="p-3 rounded-xl border"
            style={{ background: isDark ? '#111' : 'var(--color-neutral-50)', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
            <div className="text-2xl font-extrabold"
              style={{ color: ch.tone === 'warn' ? 'var(--color-warning-alt, #F59E0B)' : ch.tone === 'ok' ? 'var(--color-success-alt)' : c.text }}>{ch.value}</div>
            <div className="text-[11px] font-medium mt-0.5" style={{ color: c.textDim }}>{ch.label}</div>
          </div>
        ))}
      </div>

      {loading ? <Spinner /> : rows.length === 0 ? (
        <div data-testid="afs-finance-empty" className="p-6 rounded-xl border text-center text-sm"
          style={{ background: isDark ? '#111' : 'var(--color-neutral-50)', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)', color: c.textDim }}>
          No active contracts yet. Activate an agreement to start posting to Sage.
        </div>
      ) : (
        <div className="rounded-xl border overflow-hidden" style={{ borderColor: c.border }}>
          <table className="w-full text-sm" data-testid="afs-finance-table">
            <thead>
              <tr style={{ background: isDark ? '#0d0d0d' : 'var(--color-neutral-50)', color: c.textDim }}>
                <th className="text-left font-semibold px-3 py-2">Customer / Contract</th>
                <th className="text-right font-semibold px-3 py-2">Annual</th>
                <th className="text-left font-semibold px-3 py-2">Sage status</th>
                <th className="text-right font-semibold px-3 py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => {
                const m = FIN_META[r.status] || FIN_META.no_order;
                const Icon = m.icon;
                const noOrder = r.status === 'no_order';
                return (
                  <tr key={r.contract_id} data-testid={`afs-finance-row-${r.contract_id}`}
                    className="border-t" style={{ borderColor: c.border }}>
                    <td className="px-3 py-2">
                      <div className="font-semibold" style={{ color: c.text }}>{r.company_name || 'Contract'}</div>
                      <div className="text-[11px]" style={{ color: c.textDim }}>
                        {r.contract_number || '—'}{r.contract_type ? ` · ${r.contract_type}` : ''}{r.external_ref ? ` · SO ${r.external_ref}` : ''}
                      </div>
                    </td>
                    <td className="px-3 py-2 text-right font-semibold" style={{ color: c.text }}>{gbp0(r.annual_value)}</td>
                    <td className="px-3 py-2">
                      <span className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-1 rounded-md" style={{ background: `${m.color}14`, color: m.color }}>
                        <Icon size={12} /> {m.label}
                      </span>
                      {r.status === 'failed' && r.last_error && <div className="text-[10px] mt-1" style={{ color: 'var(--color-danger-alt, #EF4444)' }}>{String(r.last_error).slice(0, 80)}</div>}
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex items-center justify-end gap-1.5">
                        <button data-testid={`afs-finance-row-sync-${r.contract_id}`} onClick={() => rowAction(r.contract_id, 'retry')} disabled={!!busy}
                          className="text-[11px] font-semibold px-2 py-1 rounded-md inline-flex items-center gap-1" style={{ border: `1px solid ${c.border}`, color: c.textDim }}>
                          <RotateCw size={12} className={busy === r.contract_id + 'retry' ? 'animate-spin' : ''} /> {noOrder ? 'Create & sync' : 'Sync now'}
                        </button>
                        {!noOrder && (
                          <button data-testid={`afs-finance-row-csv-${r.contract_id}`} onClick={() => rowAction(r.contract_id, 'csv')} disabled={!!busy}
                            className="text-[11px] font-semibold px-2 py-1 rounded-md inline-flex items-center gap-1" style={{ border: `1px solid ${c.border}`, color: c.textDim }}>
                            <FileSpreadsheet size={12} /> CSV
                          </button>
                        )}
                        {r.status !== 'synced' && !noOrder && (
                          <button data-testid={`afs-finance-row-mark-${r.contract_id}`} onClick={() => rowAction(r.contract_id, 'mark')} disabled={!!busy}
                            className="text-[11px] font-semibold px-2 py-1 rounded-md inline-flex items-center gap-1" style={{ background: 'var(--color-success-alt)', color: '#fff' }}>
                            <CheckCircle2 size={12} /> Mark synced
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function ComplianceCard({ row, API, headers, c, isDark, onChanged }) {
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false);
  const [amendOpen, setAmendOpen] = useState(false);
  const cid = row.contract_id;
  const svc = row.service || {};
  const bill = row.billing || {};

  const toggle = async () => {
    const next = !open;
    setOpen(next);
    if (next && !detail) {
      setLoading(true);
      try {
        const res = await axios.get(`${API}/crm/v2/aftersales/contracts/${cid}/schedules`, { headers: headers() });
        setDetail(res.data);
      } catch { setDetail({ error: true }); }
      setLoading(false);
    }
  };

  const svcTone = !svc.has_schedule ? 'neutral' : (svc.overdue ? 'bad' : (svc.state === 'complete' ? 'ok' : 'ok'));
  const billTone = !bill.has_schedule ? 'neutral' : (bill.overdue ? 'bad' : 'ok');

  return (
    <div data-testid={`afs-compliance-card-${cid}`} className="rounded-xl border overflow-hidden"
         style={{ background: isDark ? '#111' : 'var(--color-neutral-50)', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
      <button data-testid={`afs-compliance-expand-${cid}`} onClick={toggle}
              className="w-full text-left p-4 flex flex-col gap-3 hover:opacity-95 transition-opacity">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              {open ? <ChevronDown size={16} style={{ color: c.textDim }} /> : <ChevronRight size={16} style={{ color: c.textDim }} />}
              <span className="font-bold truncate" style={{ color: c.text }}>{row.company_name}</span>
              {row.tier && <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded shrink-0"
                                  style={{ background: 'var(--color-brand-cyan)22', color: 'var(--color-brand-cyan)' }}>{row.tier}</span>}
            </div>
            <div className="text-xs mt-0.5 ml-6" style={{ color: c.textDim }}>
              {row.contract_number || '—'} · expires {row.end_date || '—'}
            </div>
          </div>
          <span className="text-sm font-bold shrink-0" style={{ color: 'var(--color-success-alt)' }}>{gbp0(row.annual_value)}/yr</span>
        </div>
        <div className="flex flex-wrap gap-2 ml-6">
          <CompliancePill tone={svcTone} icon={svc.overdue ? AlertTriangle : CalendarClock} testId={`afs-compliance-service-${cid}`}>
            {!svc.has_schedule ? 'No service schedule'
              : svc.overdue ? `Service: ${svc.overdue} overdue`
              : `Service: ${svc.completed}/${svc.required} done`}
            {svc.has_schedule && svc.next_due ? ` · next ${svc.next_due}` : ''}
          </CompliancePill>
          <CompliancePill tone={billTone} icon={bill.overdue ? AlertTriangle : Receipt} testId={`afs-compliance-billing-${cid}`}>
            {!bill.has_schedule ? 'No billing schedule'
              : bill.overdue ? `Billing: ${bill.overdue} overdue`
              : `Billing: ${bill.paid}/${bill.total} paid`}
            {bill.has_schedule && bill.next_due ? ` · next ${bill.next_due} ${bill.next_amount != null ? gbp(bill.next_amount) : ''}` : ''}
          </CompliancePill>
          <SyncBadge label="Sicon" status={row.sicon_sync_status} testId={`afs-compliance-sicon-${cid}`} />
          <SyncBadge label="Sage" status={row.sage_sync_status} testId={`afs-compliance-sage-${cid}`} />
        </div>
      </button>
      {open && (
        <div data-testid={`afs-compliance-detail-${cid}`} className="px-4 pb-4 pt-1 ml-6 border-t"
             style={{ borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
          {loading ? <Spinner /> : detail?.error ? (
            <p className="text-xs py-3" style={{ color: 'var(--color-danger-alt, #EF4444)' }}>Could not load schedule.</p>
          ) : (
            <>
            <div className="flex justify-end pt-3">
              <button data-testid={`afs-amend-open-${cid}`} onClick={() => setAmendOpen(true)}
                className="text-xs font-semibold px-3 py-1.5 rounded-lg inline-flex items-center gap-1.5"
                style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}>
                <Calculator size={13} /> Amend contract
              </button>
            </div>
            <FinanceSyncBlock contractId={cid} API={API} headers={headers} c={c}
              status={row.sicon_sync_status} onChanged={onChanged} />
            <div className="grid md:grid-cols-2 gap-4 pt-3">
              <div>
                <h4 className="text-xs font-bold uppercase mb-2" style={{ color: c.textDim }}>Service visits</h4>
                {(detail?.service?.visits || []).length === 0 ? (
                  <p className="text-xs" style={{ color: c.textMuted }}>No visits scheduled yet.</p>
                ) : (
                  <ul className="space-y-1">
                    {(detail.service.visits || []).map((v, i) => (
                      <li key={i} className="flex items-center justify-between text-xs" style={{ color: c.text }}>
                        <span>Visit {v.visit_no} (yr {v.year}) · {v.planned_date}</span>
                        <span className="font-semibold" style={{ color: v.status === 'completed' ? 'var(--color-success-alt)' : (v.planned_date < new Date().toISOString().slice(0, 10) ? 'var(--color-danger-alt, #EF4444)' : c.textDim) }}>
                          {v.status === 'completed' ? 'Completed' : (v.planned_date < new Date().toISOString().slice(0, 10) ? 'Overdue' : 'Planned')}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div>
                <h4 className="text-xs font-bold uppercase mb-2" style={{ color: c.textDim }}>Invoices</h4>
                {(detail?.billing || []).length === 0 ? (
                  <p className="text-xs" style={{ color: c.textMuted }}>No invoices scheduled yet.</p>
                ) : (
                  <ul className="space-y-1">
                    {(detail.billing || []).map((b, i) => (
                      <li key={i} className="flex items-center justify-between text-xs" style={{ color: c.text }}>
                        <span>{b.due_date} · {gbp(b.amount)}</span>
                        <span className="font-semibold" style={{ color: b.status === 'paid' ? 'var(--color-success-alt)' : (b.due_date < new Date().toISOString().slice(0, 10) ? 'var(--color-danger-alt, #EF4444)' : c.textDim) }}>
                          {b.status === 'paid' ? 'Paid' : (b.due_date < new Date().toISOString().slice(0, 10) ? 'Overdue' : 'Scheduled')}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
            </>
          )}
        </div>
      )}
      {amendOpen && (
        <AmendModal contractId={cid} API={API} headers={headers} c={c} isDark={isDark}
          onClose={() => setAmendOpen(false)}
          onApplied={() => { setDetail(null); onChanged && onChanged(); }} />
      )}
    </div>
  );
}

function LiveCompliancePanel({ API, headers, c, isDark }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    axios.get(`${API}/crm/v2/aftersales/contracts/compliance`, { headers: headers() })
      .then(res => setData(res.data))
      .catch(() => setData({ contracts: [], totals: {} }))
      .finally(() => setLoading(false));
  }, [API, headers]);

  useEffect(() => { load(); }, [load]);

  const totals = data?.totals || {};
  const chips = [
    { label: 'Active contracts', value: totals.active || 0, tone: 'neutral' },
    { label: 'Service overdue', value: totals.service_overdue || 0, tone: totals.service_overdue ? 'bad' : 'ok' },
    { label: 'Billing overdue', value: totals.billing_overdue || 0, tone: totals.billing_overdue ? 'bad' : 'ok' },
    { label: 'Sync pending', value: totals.sync_pending || 0, tone: totals.sync_pending ? 'warn' : 'ok' },
  ];

  return (
    <div data-testid="afs-compliance-panel" className="mb-6">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="text-lg font-bold" style={{ color: c.text }}>Live compliance</h2>
          <p className="text-xs" style={{ color: c.textDim }}>Service visits, billing and Sicon/Sage sync across every active contract.</p>
        </div>
        <div className="flex items-center gap-2">
        <button data-testid="afs-compliance-refresh" onClick={load}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium"
                style={{ background: 'transparent', color: c.textDim, border: `1px solid ${c.border}` }}>
          <RotateCw size={13} /> Refresh
        </button>
        <button data-testid="afs-finance-export-all" onClick={async () => {
                  try {
                    const r = await axios.get(`${API}/crm/v2/aftersales/finance/sync/export/all`,
                      { headers: headers(), responseType: 'blob' });
                    const url = URL.createObjectURL(new Blob([r.data], { type: 'text/csv' }));
                    const a = document.createElement('a');
                    a.href = url; a.download = `sicon-sales-orders-${new Date().toISOString().slice(0, 10)}.csv`;
                    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
                  } catch { alert('Nothing to export yet.'); }
                }}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold"
                style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}>
          <FileSpreadsheet size={13} /> Export all for Sage
        </button>
        </div>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4" data-testid="afs-compliance-stats">
        {chips.map(ch => (
          <div key={ch.label} className="p-3 rounded-xl border"
               style={{ background: isDark ? '#111' : 'var(--color-neutral-50)', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
            <div className="text-2xl font-extrabold"
                 style={{ color: ch.tone === 'bad' ? 'var(--color-danger-alt, #EF4444)' : ch.tone === 'warn' ? 'var(--color-warning-alt, #F59E0B)' : c.text }}>{ch.value}</div>
            <div className="text-[11px] font-medium mt-0.5" style={{ color: c.textDim }}>{ch.label}</div>
          </div>
        ))}
      </div>
      {loading ? <Spinner /> : (data?.contracts || []).length === 0 ? (
        <div data-testid="afs-compliance-empty" className="p-6 rounded-xl border text-center text-sm"
             style={{ background: isDark ? '#111' : 'var(--color-neutral-50)', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)', color: c.textDim }}>
          No active contracts to monitor yet. Activate an agreement to start tracking compliance here.
        </div>
      ) : (
        <div className="space-y-3">
          {(data.contracts || []).map(row => (
            <ComplianceCard key={row.contract_id} row={row} API={API} headers={headers} c={c} isDark={isDark} onChanged={load} />
          ))}
        </div>
      )}
    </div>
  );
}

// ───────────────────────────────────────────────────────── AI Assistant
const EMAIL_TYPES = [
  { id: 'renewal_reminder', label: 'Renewal reminder' },
  { id: 'rpi_increase', label: 'RPI / price-review explainer' },
  { id: 'service_due', label: 'Service visit due' },
  { id: 'welcome', label: 'Welcome / onboarding' },
  { id: 'coverage_confirmation', label: 'Coverage confirmation' },
  { id: 'general', label: 'Other (use my instruction)' },
];

function FactSheet({ facts, c, isDark }) {
  if (!facts) return null;
  const row = (k, v) => (
    <div className="flex justify-between gap-3 py-0.5">
      <span style={{ color: c.textDim }}>{k}</span>
      <span className="text-right font-medium" style={{ color: c.text }}>{v}</span>
    </div>
  );
  const s = facts.service || {}; const b = facts.billing || {}; const r = facts.rpi_review;
  const rc = facts.recent_cases || [];
  return (
    <div className="text-xs space-y-0.5" data-testid="afs-ai-factsheet">
      {row('Contract', facts.contract_number)}
      {row('Customer', facts.company_name)}
      {row('Package', facts.package)}
      {row('Annual value', gbp(facts.annual_value) + ' · ' + (facts.billing_frequency || 'annual'))}
      {row('Term', `${facts.start_date || 'n/a'} → ${facts.end_date || 'n/a'}`)}
      {row('Next anniversary', facts.next_anniversary || 'n/a')}
      {row('Covered equipment', `${facts.covered_equipment_count} machines`)}
      {s.has_schedule ? row('Service', `${s.completed}/${s.required} done · ${s.overdue} overdue · next ${s.next_due || 'n/a'}`) : row('Service', 'none recorded')}
      {b.has_schedule ? row('Billing', `${b.paid}/${b.total} paid · next ${gbp(b.next_amount)} ${b.next_due || ''}`) : row('Billing', 'none recorded')}
      {row('RPI review', r ? `${r.status} · ${r.rpi_pct}% → ${gbp(r.proposed_value)}` : 'none proposed')}
      {row('Service cases', `${facts.service_cases_total || 0} logged · ${facts.service_cases_open || 0} open · ${facts.service_cases_12m || 0} in 12mo`)}
      {rc.length > 0 && (
        <div className="pt-1 mt-1 border-t" style={{ borderColor: c.border }} data-testid="afs-ai-recent-cases">
          <span style={{ color: c.textDim }}>Recent cases</span>
          <div className="mt-0.5 space-y-0.5">
            {rc.map((x, i) => (
              <div key={i} className="flex justify-between gap-3">
                <span style={{ color: c.text }}>{x.reference ? x.reference + ' · ' : ''}{x.title || x.case_type}{x.fault_code ? ` · ${x.fault_code}` : ''}</span>
                <span className="text-right" style={{ color: c.textDim }}>{x.status} · {x.created_at}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function AIAssistantTab({ API, headers, c, isDark }) {
  const [contracts, setContracts] = useState([]);
  const [contractId, setContractId] = useState('');
  const [facts, setFacts] = useState(null);
  const [showFacts, setShowFacts] = useState(false);
  const [mode, setMode] = useState('summary');
  const [emailType, setEmailType] = useState('renewal_reminder');
  const [instruction, setInstruction] = useState('');
  const [question, setQuestion] = useState('');
  const [result, setResult] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [sendTo, setSendTo] = useState('');
  const [sending, setSending] = useState(false);
  const [sendMsg, setSendMsg] = useState('');
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    axios.get(`${API}/crm/v2/aftersales/ai/contracts`, { headers: headers() })
      .then(r => {
        const list = r.data.contracts || [];
        setContracts(list);
        if (list.length && !contractId) setContractId(list[0].id);
      }).catch(() => setContracts([]));
  }, [API, headers]); // eslint-disable-line

  useEffect(() => {
    if (!contractId) { setFacts(null); return; }
    setFacts(null); setResult(''); setSendMsg('');
    axios.get(`${API}/crm/v2/aftersales/ai/contracts/${contractId}/context`, { headers: headers() })
      .then(r => { setFacts(r.data.facts); setSendTo(r.data.facts?.customer_email || ''); })
      .catch(() => setFacts(null));
  }, [API, headers, contractId]);

  const generate = async () => {
    if (!contractId) return;
    setBusy(true); setErr(''); setResult(''); setSendMsg('');
    try {
      const body = { contract_id: contractId, mode };
      if (mode === 'email') { body.email_type = emailType; body.instruction = instruction; }
      if (mode === 'question') body.question = question;
      const r = await axios.post(`${API}/crm/v2/aftersales/ai/assistant`, body, { headers: headers() });
      setResult(r.data.text || '');
      if (r.data.facts) { setFacts(r.data.facts); if (!sendTo) setSendTo(r.data.facts.customer_email || ''); }
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Generation failed. Please try again.');
    } finally { setBusy(false); }
  };

  const sendEmail = async () => {
    const lines = result.split('\n');
    let subject = '';
    const bodyLines = [];
    let subjectDone = false;
    for (const ln of lines) {
      const m = !subjectDone && ln.match(/^\s*subject\s*:\s*(.+)$/i);
      if (m) { subject = m[1].trim(); subjectDone = true; continue; }
      bodyLines.push(ln);
    }
    const bodyText = bodyLines.join('\n').trim();
    setSending(true); setSendMsg('');
    try {
      const r = await axios.post(`${API}/crm/v2/aftersales/ai/assistant/send-email`,
        { contract_id: contractId, subject, body: bodyText, to_email: sendTo }, { headers: headers() });
      setSendMsg(r.data.sent ? `Sent to ${r.data.to}` : `Queued to ${r.data.to} — delivery is only live in production`);
    } catch (e) {
      setSendMsg(e?.response?.data?.detail || 'Send failed. Please try again.');
    } finally { setSending(false); }
  };

  const copyResult = async () => {
    try { await navigator.clipboard.writeText(result); } catch { /* noop */ }
    setCopied(true); setTimeout(() => setCopied(false), 2000);
  };

  const modeBtn = (id, label, Icon) => (
    <button data-testid={`afs-ai-mode-${id}`} onClick={() => { setMode(id); setResult(''); }}
      className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors"
      style={mode === id
        ? { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }
        : { background: 'transparent', color: c.textDim, border: `1px solid ${c.border}` }}>
      <Icon size={14} /> {label}
    </button>
  );
  const canGen = contractId && (mode !== 'question' || question.trim()) && (mode !== 'email' || emailType !== 'general' || instruction.trim());

  return (
    <div data-testid="afs-ai">
      <div className="mb-3">
        <h2 className="text-lg font-bold flex items-center gap-2" style={{ color: c.text }}>
          <Sparkles size={18} style={{ color: 'var(--color-brand-cyan)' }} /> Contract AI Assistant
        </h2>
        <p className="text-xs" style={{ color: c.textDim }}>
          Summaries, customer-email drafts and answers — grounded strictly in this contract's live data. The
          assistant never invents prices, dates or coverage; every figure comes from the record.
        </p>
      </div>

      <Card c={c} isDark={isDark} className="mb-4">
        <label className="text-xs font-semibold block mb-1" style={{ color: c.textDim }}>Contract</label>
        <select data-testid="afs-ai-contract" value={contractId} onChange={e => setContractId(e.target.value)}
          className="w-full px-3 py-2 rounded-lg text-sm mb-1"
          style={{ background: isDark ? '#0d0d0d' : '#fff', color: c.text, border: `1px solid ${c.border}` }}>
          {contracts.length === 0 && <option value="">No active contracts</option>}
          {contracts.map(ct => (
            <option key={ct.id} value={ct.id}>{ct.company_name} · {ct.contract_number} · {gbp(ct.annual_value)}/yr</option>
          ))}
        </select>
        {facts && (
          <div className="mt-2">
            <button data-testid="afs-ai-facts-toggle" onClick={() => setShowFacts(v => !v)}
              className="inline-flex items-center gap-1 text-xs font-medium" style={{ color: 'var(--color-brand-cyan)' }}>
              {showFacts ? <ChevronDown size={13} /> : <ChevronRight size={13} />} {showFacts ? 'Hide' : 'Show'} the facts the assistant will use
            </button>
            {showFacts && (
              <div className="mt-2 p-3 rounded-lg border" style={{ borderColor: c.border, background: isDark ? '#0d0d0d' : 'var(--color-neutral-50)' }}>
                <FactSheet facts={facts} c={c} isDark={isDark} />
              </div>
            )}
          </div>
        )}
      </Card>

      <div className="flex flex-wrap gap-2 mb-4" data-testid="afs-ai-modes">
        {modeBtn('summary', 'Summarise coverage', FileText)}
        {modeBtn('email', 'Draft customer email', Mail)}
        {modeBtn('question', 'Ask a question', MessageSquare)}
      </div>

      {mode === 'email' && (
        <Card c={c} isDark={isDark} className="mb-4">
          <label className="text-xs font-semibold block mb-1" style={{ color: c.textDim }}>Email type</label>
          <select data-testid="afs-ai-email-type" value={emailType} onChange={e => setEmailType(e.target.value)}
            className="w-full px-3 py-2 rounded-lg text-sm mb-3"
            style={{ background: isDark ? '#0d0d0d' : '#fff', color: c.text, border: `1px solid ${c.border}` }}>
            {EMAIL_TYPES.map(t => <option key={t.id} value={t.id}>{t.label}</option>)}
          </select>
          <label className="text-xs font-semibold block mb-1" style={{ color: c.textDim }}>
            Extra instruction {emailType === 'general' ? '(required)' : '(optional)'}
          </label>
          <textarea data-testid="afs-ai-instruction" value={instruction} onChange={e => setInstruction(e.target.value)}
            rows={2} placeholder="e.g. mention we're introducing weekend visits from March"
            className="w-full px-3 py-2 rounded-lg text-sm resize-y"
            style={{ background: isDark ? '#0d0d0d' : '#fff', color: c.text, border: `1px solid ${c.border}` }} />
        </Card>
      )}

      {mode === 'question' && (
        <Card c={c} isDark={isDark} className="mb-4">
          <label className="text-xs font-semibold block mb-1" style={{ color: c.textDim }}>Your question</label>
          <input data-testid="afs-ai-question" value={question} onChange={e => setQuestion(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && canGen) generate(); }}
            placeholder="e.g. When is the next invoice due and how much is it?"
            className="w-full px-3 py-2 rounded-lg text-sm"
            style={{ background: isDark ? '#0d0d0d' : '#fff', color: c.text, border: `1px solid ${c.border}` }} />
        </Card>
      )}

      <button data-testid="afs-ai-generate" onClick={generate} disabled={!canGen || busy}
        className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold transition-opacity"
        style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)', opacity: (!canGen || busy) ? 0.5 : 1 }}>
        {busy ? <RotateCw size={15} className="animate-spin" /> : <Sparkles size={15} />}
        {busy ? 'Generating…' : mode === 'summary' ? 'Summarise coverage' : mode === 'email' ? 'Draft email' : 'Get answer'}
      </button>

      {err && (
        <div data-testid="afs-ai-error" className="mt-4 p-3 rounded-lg text-sm flex items-center gap-2"
          style={{ background: 'rgba(239,68,68,0.1)', color: 'var(--color-danger, #EF4444)' }}>
          <AlertTriangle size={15} /> {err}
        </div>
      )}

      {result && (
        <Card c={c} isDark={isDark} className="mt-4" testId="afs-ai-result">
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm font-bold" style={{ color: c.text }}>
              {mode === 'summary' ? 'Coverage summary' : mode === 'email' ? 'Draft email' : 'Answer'}
            </p>
            <button data-testid="afs-ai-copy" onClick={copyResult}
              className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium"
              style={{ background: 'transparent', color: c.textDim, border: `1px solid ${c.border}` }}>
              {copied ? <Check size={13} /> : <Copy size={13} />} {copied ? 'Copied' : 'Copy'}
            </button>
          </div>
          <textarea data-testid="afs-ai-output" value={result} onChange={e => setResult(e.target.value)}
            rows={Math.min(24, Math.max(8, result.split('\n').length + 2))}
            className="w-full px-3 py-2 rounded-lg text-sm resize-y font-normal leading-relaxed"
            style={{ background: isDark ? '#0d0d0d' : '#fff', color: c.text, border: `1px solid ${c.border}`, whiteSpace: 'pre-wrap' }} />
          <p className="text-[11px] mt-2" style={{ color: c.textDim }}>
            Editable draft — review before sending. Figures are drawn from the live contract record.
          </p>
          {mode === 'email' && (
            <div className="mt-3 pt-3 border-t flex flex-wrap items-center gap-2" style={{ borderColor: c.border }} data-testid="afs-ai-send-row">
              <Mail size={14} style={{ color: c.textDim }} />
              <input data-testid="afs-ai-send-to" type="email" value={sendTo} onChange={e => setSendTo(e.target.value)}
                placeholder="customer@email.com"
                className="flex-1 min-w-[180px] px-3 py-2 rounded-lg text-sm"
                style={{ background: isDark ? '#0d0d0d' : '#fff', color: c.text, border: `1px solid ${c.border}` }} />
              <button data-testid="afs-ai-send" onClick={sendEmail} disabled={sending || !sendTo.trim() || !result.trim()}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-sm font-semibold transition-opacity"
                style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)', opacity: (sending || !sendTo.trim() || !result.trim()) ? 0.5 : 1 }}>
                {sending ? <RotateCw size={14} className="animate-spin" /> : <Share2 size={14} />}
                {sending ? 'Sending…' : 'Send to customer'}
              </button>
              {sendMsg && <span data-testid="afs-ai-send-msg" className="text-xs w-full" style={{ color: c.textDim }}>{sendMsg}</span>}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}

// ───────────────────────────────────────────────────────── Shell
export default function AftersalesApp() {
  const crm = useCRM();
  const { API, headers, c, isDark } = crm;
  const [tab, setTab] = useState('dashboard');
  const [editQuote, setEditQuote] = useState(null);
  const TabComp = { dashboard: DashboardTab, autoquote: AutoQuoteTab, onboarding: EstateOnboarding, agreements: AgreementsTab, renewals: RenewalsRpiTab, ai: AIAssistantTab, reports: ReportsTab, pricing: PricingTab, equipment: EquipmentTab, supportability: SupportabilityTab, finance: FinanceDashboard }[tab];
  return (
    <div data-testid="afs-app">
      <SubTabBar tabs={SUB_TABS} active={tab} onChange={setTab} testId="afs-tab" ariaLabel="Aftersales sections" />
      {tab === 'contracts'
        ? <><LiveCompliancePanel API={API} headers={headers} c={c} isDark={isDark} /><CRMContracts /></>
        : <TabComp API={API} headers={headers} c={c} isDark={isDark} editQuote={editQuote} setEditQuote={setEditQuote} goTo={setTab} />}
    </div>
  );
}
