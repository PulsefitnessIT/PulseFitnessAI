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
import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { useCRM } from '../CRMApp';
import CRMContracts from '../CRMContracts';
import {
  LayoutDashboard, SlidersHorizontal, Wrench, ShieldCheck, RefreshCw, AlertTriangle,
  Clock, FileSignature, Calculator, Plus, Trash2, Check, Search, TrendingUp, Shield,
  Zap, Building2, Rocket, FileCheck2, PenLine, CheckCircle2, Circle,
} from 'lucide-react';

const gbp = (v) => '£' + Number(v || 0).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const gbp0 = (v) => '£' + Number(v || 0).toLocaleString('en-GB', { maximumFractionDigits: 0 });
const pct = (v) => (Number(v || 0) * 100).toFixed(2).replace(/\.00$/, '') + '%';

const SUB_TABS = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'autoquote', label: 'Build Quote', icon: Zap },
  { id: 'agreements', label: 'Agreements', icon: FileCheck2 },
  { id: 'renewals', label: 'Renewals & RPI', icon: RefreshCw },
  { id: 'contracts', label: 'Contracts & Renewals', icon: Shield },
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
  useEffect(() => { load(); }, [load]);

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
function AutoQuoteTab({ API, headers, c, isDark }) {
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
                <option value="silver">Silver</option><option value="gold">Gold</option><option value="platinum">Platinum</option></select></label>
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

        <button data-testid="afs-aq-build" onClick={() => build(false)} disabled={!companyId || busy}
          className="mt-4 inline-flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-bold disabled:opacity-40"
          style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}>
          <Rocket size={16} /> {busy ? 'Building…' : 'Build Quote From Estate'}
        </button>
      </Card>

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

function AgreementsTab({ API, headers, c, isDark }) {
  const [agreements, setAgreements] = useState([]);
  const [quotes, setQuotes] = useState([]);
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
      setQuotes((q.data.quotes || []).filter(x => ['draft', 'accepted'].includes(x.status)));
    });
  }, [API, headers]);
  useEffect(load, [load]);

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
  return (
    <div data-testid="afs-agreements">
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
    </div>
  );
}

// ───────────────────────────────────────────────────────── Shell
export default function AftersalesApp() {
  const crm = useCRM();
  const { API, headers, c, isDark } = crm;
  const [tab, setTab] = useState('dashboard');
  const TabComp = { dashboard: DashboardTab, autoquote: AutoQuoteTab, agreements: AgreementsTab, renewals: RenewalsRpiTab, pricing: PricingTab, equipment: EquipmentTab, supportability: SupportabilityTab }[tab];
  return (
    <div data-testid="afs-app">
      <div className="mb-4">
        <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight pulse-font-heading" style={{ color: c.text }}>Aftersales Contracts</h1>
        <p className="text-sm" style={{ color: c.textDim }}>Enter once → reuse everywhere → manage by exception.</p>
      </div>
      <div className="flex gap-1.5 mb-5 overflow-x-auto pb-1" data-testid="afs-subnav">
        {SUB_TABS.map(t => (
          <button key={t.id} data-testid={`afs-tab-${t.id}`} onClick={() => setTab(t.id)}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-colors"
            style={tab === t.id
              ? { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }
              : { background: 'transparent', color: c.textDim, border: `1px solid ${c.border}` }}>
            <t.icon size={15} /> {t.label}
          </button>
        ))}
      </div>
      {tab === 'contracts'
        ? <CRMContracts />
        : <TabComp API={API} headers={headers} c={c} isDark={isDark} />}
    </div>
  );
}
