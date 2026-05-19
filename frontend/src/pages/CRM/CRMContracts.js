import { useState, useEffect, useCallback, useRef } from 'react';
import { useCRM } from './CRMApp';
import {
  Plus, FileText, ChevronRight, ArrowLeft, Building2, MapPin,
  Calendar, DollarSign, Shield, Clock, CheckCircle, AlertTriangle,
  Edit2, Trash2, X, Wrench, Activity, Copy, Send, ThumbsUp,
  ThumbsDown, RefreshCw, Link2, PenTool, BarChart3,
  Settings2, ExternalLink, Zap
} from 'lucide-react';
import axios from 'axios';
import Button from '@/components/shared/Button';
import RowActions from '@/components/shared/RowActions';
import ListPanel from '@/components/shared/ListPanel';

const TIER_COLORS = { warranty: 'var(--color-text-faint-alt)', bronze: 'var(--color-bronze)', silver: 'var(--color-silver)', gold: 'var(--color-gold)', platinum: '#E5E4E2', bespoke: 'var(--color-accent-violet)' };
const STATUS_COLORS = { draft: 'var(--color-text-faint-alt)', pending_approval: 'var(--color-warning)', approved: 'var(--color-success-alt-2)', sent: 'var(--color-info-ios)', negotiation: 'var(--color-accent-magenta)', signed: 'var(--color-success-alt)', active: 'var(--color-info-ios)', expiring: 'var(--color-accent-amber)', expired: 'var(--color-danger-alt)', renewed: 'var(--color-success-alt)', cancelled: 'var(--color-danger)', amended: 'var(--color-accent-violet)' };
const fmt = v => `£${(v || 0).toLocaleString('en-GB', { minimumFractionDigits: 0 })}`;
const fmtDate = d => d ? new Date(d).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) : '—';

/* ═══ STAT CARD ═══ */
function StatCard({ label, value, sub, icon: Icon, color, isDark, c }) {
  return (
    <div className="p-4 rounded-xl border" style={{ background: isDark ? '#111' : 'var(--color-neutral-50)', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
      <div className="flex items-center justify-between mb-2">
        <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: `${color}15` }}>
          <Icon size={15} style={{ color }} />
        </div>
        {sub && <span className="text-[10px] font-medium px-1.5 py-0.5 rounded" style={{ background: `${color}10`, color }}>{sub}</span>}
      </div>
      <p className="text-xl font-bold tracking-tight" style={{ color: c.text }}>{value}</p>
      <p className="text-[10px] uppercase tracking-wider mt-0.5" style={{ color: c.textDim }}>{label}</p>
    </div>
  );
}

/* ═══ MODAL SHELL ═══ */
function Modal({ open, onClose, title, children, isDark, c, wide }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={onClose}>
      <div className={`${wide ? 'max-w-2xl' : 'max-w-lg'} w-full mx-4 rounded-xl p-6 shadow-2xl max-h-[85vh] overflow-y-auto`}
        style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', border: `1px solid ${c.border}` }} onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold" style={{ color: c.text }}>{title}</h2>
          <button onClick={onClose} className="p-1 rounded hover:bg-white/10 dark:bg-zinc-900"><X size={16} style={{ color: c.textDim }} /></button>
        </div>
        {children}
      </div>
    </div>
  );
}

/* ═══ INPUT FIELD ═══ */
function Field({ label, children, span }) {
  const { c } = useCRM();
  return (
    <div className={span === 2 ? 'col-span-2' : ''}>
      <label className="text-[10px] uppercase tracking-wider font-medium block mb-1" style={{ color: c.textDim }}>{label}</label>
      {children}
    </div>
  );
}

function useInput(isDark, c) {
  return { className: 'w-full px-3 py-2 text-sm rounded-md', style: { background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text } };
}

/* ═══ CONTRACT LIST ═══ */
function ContractList({ c, isDark, API, headers, onSelect }) {
  const [contracts, setContracts] = useState([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [companies, setCompanies] = useState([]);
  const [contacts, setContacts] = useState([]);
  const [form, setForm] = useState({ title: '', type: 'service', tier: 'silver', company_id: '', contact_id: '', start_date: '', end_date: '', annual_value: '', billing_frequency: 'annual' });
  const [saving, setSaving] = useState(false);
  const inp = useInput(isDark, c);

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams({ limit: '200' });
      if (statusFilter) params.set('status', statusFilter);
      const [res, sRes] = await Promise.all([
        axios.get(`${API}/crm/v2/contracts?${params}`, { headers: headers() }),
        axios.get(`${API}/crm/v2/contracts/stats`, { headers: headers() }),
      ]);
      setContracts(res.data.contracts || []);
      setTotal(res.data.total || 0);
      setStats(sRes.data);
    } catch (e) { console.error(e); }
    setLoading(false);
  }, [API, headers, statusFilter]);

  useEffect(() => { load(); }, [load]);

  const openCreate = async () => {
    try {
      const [coRes, ctRes] = await Promise.all([
        axios.get(`${API}/crm/v2/companies?limit=200`, { headers: headers() }),
        axios.get(`${API}/crm/v2/contacts?limit=200`, { headers: headers() }),
      ]);
      setCompanies(coRes.data.companies || []);
      setContacts(ctRes.data.contacts || []);
    } catch (e) { console.error(e); }
    setShowCreate(true);
  };

  const handleCreate = async () => {
    if (!form.title.trim()) return;
    setSaving(true);
    try {
      const co = companies.find(x => x.id === form.company_id);
      const ct = contacts.find(x => x.id === form.contact_id);
      const payload = { ...form, annual_value: parseFloat(form.annual_value) || 0, total_value: parseFloat(form.annual_value) || 0, company_name: co?.name || '', contact_name: ct ? `${ct.first_name} ${ct.last_name}` : '' };
      const res = await axios.post(`${API}/crm/v2/contracts`, payload, { headers: headers() });
      setShowCreate(false);
      setForm({ title: '', type: 'service', tier: 'silver', company_id: '', contact_id: '', start_date: '', end_date: '', annual_value: '', billing_frequency: 'annual' });
      onSelect(res.data.id);
    } catch (e) { console.error(e); }
    setSaving(false);
  };

  const filtered = search ? contracts.filter(x => x.title?.toLowerCase().includes(search.toLowerCase()) || x.contract_number?.toLowerCase().includes(search.toLowerCase()) || x.company_name?.toLowerCase().includes(search.toLowerCase())) : contracts;
  const filteredContacts = form.company_id ? contacts.filter(ct => ct.company_id === form.company_id) : contacts;

  if (loading) return <div className="flex justify-center py-12"><div className="w-5 h-5 border-2 border-[var(--color-info-ios)] border-t-transparent rounded-full animate-spin" /></div>;

  return (
    <div data-testid="contracts-list">
      {/* Stats Row */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3 mb-5" data-testid="contracts-stats">
          <StatCard label="Total" value={stats.total} icon={FileText} color="var(--color-info-ios)" isDark={isDark} c={c} />
          <StatCard label="Active" value={stats.active} icon={CheckCircle} color="var(--color-success-alt)" isDark={isDark} c={c} />
          <StatCard label="Draft" value={stats.draft} icon={Edit2} color="var(--color-text-faint-alt)" isDark={isDark} c={c} />
          <StatCard label="Pending Approval" value={stats.pending_approval} icon={Clock} color="var(--color-warning)" isDark={isDark} c={c} />
          <StatCard label="Expiring Soon" value={stats.expiring_soon} sub="90 days" icon={AlertTriangle} color="var(--color-accent-amber)" isDark={isDark} c={c} />
          <StatCard label="Active Value" value={fmt(stats.active_annual_value)} sub="/yr" icon={DollarSign} color="var(--color-success-alt)" isDark={isDark} c={c} />
        </div>
      )}

      <ListPanel
        search={{ value: search, onChange: setSearch, placeholder: 'Search contracts...', testId: 'contracts-search' }}
        count={{ value: total, label: 'contract' }}
        primaryAction={{ label: 'New Contract', icon: Plus, onClick: openCreate, testId: 'create-contract-btn' }}
        empty={{
          when: filtered.length === 0,
          icon: FileText,
          title: 'No contracts found',
          hint: search || statusFilter ? 'Try clearing your search or filters.' : 'Create your first contract to start tracking deliverables and renewals.',
          primaryAction: search || statusFilter ? undefined : { label: 'Create a contract', onClick: openCreate },
          testId: 'contracts-empty',
        }}
        toolbarRight={(
          <div className="flex gap-1 overflow-x-auto">
            {['', 'active', 'draft', 'pending_approval', 'approved', 'expiring', 'expired'].map(s => (
              <button key={s} onClick={() => setStatusFilter(s)}
                className={`px-3 py-1.5 text-xs font-medium rounded-md whitespace-nowrap transition-colors ${statusFilter === s ? 'bg-[var(--color-info-ios)] text-white' : ''}`}
                style={statusFilter !== s ? { background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-100)', color: c.textMuted } : {}}
                data-testid={`filter-${s || 'all'}`}>
                {s ? s.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase()) : 'All'}
              </button>
            ))}
          </div>
        )}
      >
        {filtered.map(contract => {
          const sc = STATUS_COLORS[contract.status] || 'var(--color-text-faint-alt)';
          const tc = TIER_COLORS[contract.tier] || 'var(--color-text-faint-alt)';
          return (
            <div key={contract.id} onClick={() => onSelect(contract.id)}
              className="flex items-center gap-4 p-4 rounded-lg border cursor-pointer transition-all hover:scale-[1.002]"
              style={{ background: isDark ? '#111' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}
              data-testid={`contract-row-${contract.id}`}>
              <div className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0" style={{ background: `${tc}20` }}>
                <Shield size={18} style={{ color: tc }} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-semibold truncate" style={{ color: c.text }}>{contract.title || contract.contract_number}</p>
                  <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded shrink-0" style={{ background: `${sc}15`, color: sc }}>{contract.status?.replace('_', ' ')}</span>
                  <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded shrink-0" style={{ background: `${tc}15`, color: tc }}>{contract.tier}</span>
                </div>
                <div className="flex items-center gap-3 mt-0.5">
                  <span className="text-[11px]" style={{ color: c.textDim }}>{contract.contract_number}</span>
                  {contract.company_name && <span className="text-[11px] flex items-center gap-0.5" style={{ color: 'var(--color-info-ios)' }}><Building2 size={9} />{contract.company_name}</span>}
                  {contract.end_date && <span className="text-[11px]" style={{ color: c.textDim }}>Expires: {fmtDate(contract.end_date)}</span>}
                </div>
              </div>
              <span className="text-sm font-bold shrink-0" style={{ color: 'var(--color-success-alt)' }}>{fmt(contract.annual_value)}/yr</span>
              <ChevronRight size={16} style={{ color: c.textDim }} />
            </div>
          );
        })}
      </ListPanel>

      {/* Create Modal */}
      <Modal open={showCreate} onClose={() => setShowCreate(false)} title="New Contract" isDark={isDark} c={c}>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Contract Title *" span={2}>
            <input value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} placeholder="e.g. Annual Maintenance Agreement" {...inp} data-testid="contract-title-input" />
          </Field>
          <Field label="Company">
            <select value={form.company_id} onChange={e => setForm({ ...form, company_id: e.target.value, contact_id: '' })} {...inp}>
              <option value="">Select...</option>
              {companies.map(co => <option key={co.id} value={co.id}>{co.name}</option>)}
            </select>
          </Field>
          <Field label="Contact">
            <select value={form.contact_id} onChange={e => setForm({ ...form, contact_id: e.target.value })} {...inp}>
              <option value="">{form.company_id ? 'Select...' : 'Select company first'}</option>
              {filteredContacts.map(ct => <option key={ct.id} value={ct.id}>{ct.first_name} {ct.last_name}</option>)}
            </select>
          </Field>
          <Field label="Tier">
            <select value={form.tier} onChange={e => setForm({ ...form, tier: e.target.value })} {...inp}>
              {['bronze', 'silver', 'gold', 'platinum', 'bespoke'].map(t => <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>)}
            </select>
          </Field>
          <Field label="Type">
            <select value={form.type} onChange={e => setForm({ ...form, type: e.target.value })} {...inp}>
              {['service', 'supply', 'maintenance', 'umbrella'].map(t => <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>)}
            </select>
          </Field>
          <Field label="Annual Value (£)">
            <input type="number" value={form.annual_value} onChange={e => setForm({ ...form, annual_value: e.target.value })} {...inp} />
          </Field>
          <Field label="Billing">
            <select value={form.billing_frequency} onChange={e => setForm({ ...form, billing_frequency: e.target.value })} {...inp}>
              {['monthly', 'quarterly', 'annual', 'one_off'].map(f => <option key={f} value={f}>{f.replace('_', ' ')}</option>)}
            </select>
          </Field>
          <Field label="Start Date">
            <input type="date" value={form.start_date} onChange={e => setForm({ ...form, start_date: e.target.value })} {...inp} />
          </Field>
          <Field label="End Date">
            <input type="date" value={form.end_date} onChange={e => setForm({ ...form, end_date: e.target.value })} {...inp} />
          </Field>
        </div>
        <div className="flex gap-2 mt-5 justify-end">
          <button onClick={() => setShowCreate(false)} className="px-4 py-2 text-sm" style={{ color: c.textMuted }}>Cancel</button>
          <button onClick={handleCreate} disabled={saving || !form.title.trim()} className="px-4 py-2 bg-[var(--color-info-ios)] text-white text-sm font-medium rounded-md disabled:opacity-50" data-testid="save-contract-btn">{saving ? 'Creating...' : 'Create Contract'}</button>
        </div>
      </Modal>
    </div>
  );
}


/* ═══ SITES TAB ═══ */
function SitesTab({ contract, contractId, API, headers, isDark, c, reload }) {
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ site_name: '', address: '', city: '', postcode: '', notes: '' });
  const [saving, setSaving] = useState(false);
  const inp = useInput(isDark, c);

  const addSite = async () => {
    if (!form.site_name.trim()) return;
    setSaving(true);
    try {
      await axios.post(`${API}/crm/v2/contracts/${contractId}/sites`, form, { headers: headers() });
      setShowAdd(false);
      setForm({ site_name: '', address: '', city: '', postcode: '', notes: '' });
      reload();
    } catch (e) { console.error(e); }
    setSaving(false);
  };

  const removeSite = async (siteId) => {
    if (!window.confirm('Remove this site?')) return;
    try {
      await axios.delete(`${API}/crm/v2/contracts/${contractId}/sites/${siteId}`, { headers: headers() });
      reload();
    } catch (e) { console.error(e); }
  };

  return (
    <div data-testid="sites-tab">
      <div className="flex items-center justify-between mb-3">
        <p className="text-sm font-medium" style={{ color: c.text }}>{(contract.sites || []).length} Sites</p>
        <button onClick={() => setShowAdd(true)} className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-md bg-[var(--color-info-ios)] text-white" data-testid="add-site-btn">
          <Plus size={12} /> Add Site
        </button>
      </div>
      <div className="space-y-2">
        {(contract.sites || []).map(site => (
          <div key={site.id} className="p-3 rounded-lg border flex items-center gap-3 group" style={{ background: isDark ? '#111' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
            <MapPin size={16} style={{ color: 'var(--color-info-ios)' }} />
            <div className="flex-1">
              <p className="text-sm font-medium" style={{ color: c.text }}>{site.site_name}</p>
              <p className="text-[11px]" style={{ color: c.textDim }}>{[site.address, site.city, site.postcode].filter(Boolean).join(', ')}</p>
              {site.notes && <p className="text-[10px] mt-0.5 italic" style={{ color: c.textDim }}>{site.notes}</p>}
            </div>
            <RowActions>
              <Button variant="ghostDestructive" size="iconSm" onClick={() => removeSite(site.id)} icon={Trash2} title="Remove site" data-testid={`remove-site-${site.id}`} />
            </RowActions>
          </div>
        ))}
        {(contract.sites || []).length === 0 && <p className="text-center py-8 text-sm" style={{ color: c.textDim }}>No sites added yet</p>}
      </div>

      <Modal open={showAdd} onClose={() => setShowAdd(false)} title="Add Site" isDark={isDark} c={c}>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Site Name *" span={2}><input value={form.site_name} onChange={e => setForm({ ...form, site_name: e.target.value })} placeholder="e.g. Main Gym Floor" {...inp} data-testid="site-name-input" /></Field>
          <Field label="Address" span={2}><input value={form.address} onChange={e => setForm({ ...form, address: e.target.value })} {...inp} /></Field>
          <Field label="City"><input value={form.city} onChange={e => setForm({ ...form, city: e.target.value })} {...inp} /></Field>
          <Field label="Postcode"><input value={form.postcode} onChange={e => setForm({ ...form, postcode: e.target.value })} {...inp} /></Field>
          <Field label="Notes" span={2}><textarea value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} rows={2} {...inp} className="w-full px-3 py-2 text-sm rounded-md resize-none" /></Field>
        </div>
        <div className="flex gap-2 mt-4 justify-end">
          <button onClick={() => setShowAdd(false)} className="px-4 py-2 text-sm" style={{ color: c.textMuted }}>Cancel</button>
          <button onClick={addSite} disabled={saving || !form.site_name.trim()} className="px-4 py-2 bg-[var(--color-info-ios)] text-white text-sm font-medium rounded-md disabled:opacity-50" data-testid="save-site-btn">{saving ? 'Adding...' : 'Add Site'}</button>
        </div>
      </Modal>
    </div>
  );
}


/* ═══ ASSETS TAB ═══ */
function AssetsTab({ contract, contractId, API, headers, isDark, c, reload }) {
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ asset_name: '', model_code: '', serial_number: '', warranty_end: '', coverage_type: 'full', site_id: '', exclusions: '' });
  const [saving, setSaving] = useState(false);
  const inp = useInput(isDark, c);

  const addAsset = async () => {
    if (!form.asset_name.trim()) return;
    setSaving(true);
    try {
      await axios.post(`${API}/crm/v2/contracts/${contractId}/assets`, form, { headers: headers() });
      setShowAdd(false);
      setForm({ asset_name: '', model_code: '', serial_number: '', warranty_end: '', coverage_type: 'full', site_id: '', exclusions: '' });
      reload();
    } catch (e) { console.error(e); }
    setSaving(false);
  };

  const removeAsset = async (assetId) => {
    if (!window.confirm('Remove this asset?')) return;
    try {
      await axios.delete(`${API}/crm/v2/contracts/${contractId}/assets/${assetId}`, { headers: headers() });
      reload();
    } catch (e) { console.error(e); }
    setSaving(false);
  };

  const coverageColors = { full: 'var(--color-success-alt)', parts_only: 'var(--color-accent-amber)', labour_only: 'var(--color-info-ios)', inspection: 'var(--color-accent-violet)' };

  return (
    <div data-testid="assets-tab">
      <div className="flex items-center justify-between mb-3">
        <p className="text-sm font-medium" style={{ color: c.text }}>{(contract.covered_assets || []).length} Covered Assets</p>
        <button onClick={() => setShowAdd(true)} className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-md bg-[var(--color-info-ios)] text-white" data-testid="add-asset-btn">
          <Plus size={12} /> Add Asset
        </button>
      </div>
      <div className="space-y-2">
        {(contract.covered_assets || []).map(asset => {
          const cc = coverageColors[asset.coverage_type] || 'var(--color-text-faint-alt)';
          return (
            <div key={asset.id} className="p-3 rounded-lg border flex items-center gap-3 group" style={{ background: isDark ? '#111' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
              <Wrench size={16} style={{ color: 'var(--color-accent-amber)' }} />
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-medium" style={{ color: c.text }}>{asset.asset_name}</p>
                  <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded" style={{ background: `${cc}15`, color: cc }}>{asset.coverage_type?.replace('_', ' ')}</span>
                </div>
                <p className="text-[11px]" style={{ color: c.textDim }}>
                  {asset.model_code && `${asset.model_code} · `}SN: {asset.serial_number || '—'}
                  {asset.warranty_end && ` · Warranty: ${fmtDate(asset.warranty_end)}`}
                </p>
              </div>
              <RowActions>
                <Button variant="ghostDestructive" size="iconSm" onClick={() => removeAsset(asset.id)} icon={Trash2} title="Remove asset" data-testid={`remove-asset-${asset.id}`} />
              </RowActions>
            </div>
          );
        })}
        {(contract.covered_assets || []).length === 0 && <p className="text-center py-8 text-sm" style={{ color: c.textDim }}>No assets covered yet</p>}
      </div>

      <Modal open={showAdd} onClose={() => setShowAdd(false)} title="Add Covered Asset" isDark={isDark} c={c}>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Asset Name *" span={2}><input value={form.asset_name} onChange={e => setForm({ ...form, asset_name: e.target.value })} placeholder="e.g. Treadmill X500" {...inp} data-testid="asset-name-input" /></Field>
          <Field label="Model Code"><input value={form.model_code} onChange={e => setForm({ ...form, model_code: e.target.value })} {...inp} /></Field>
          <Field label="Serial Number"><input value={form.serial_number} onChange={e => setForm({ ...form, serial_number: e.target.value })} {...inp} /></Field>
          <Field label="Coverage Type">
            <select value={form.coverage_type} onChange={e => setForm({ ...form, coverage_type: e.target.value })} {...inp}>
              {['full', 'parts_only', 'labour_only', 'inspection'].map(t => <option key={t} value={t}>{t.replace('_', ' ')}</option>)}
            </select>
          </Field>
          <Field label="Warranty End"><input type="date" value={form.warranty_end} onChange={e => setForm({ ...form, warranty_end: e.target.value })} {...inp} /></Field>
          {(contract.sites || []).length > 0 && (
            <Field label="Site" span={2}>
              <select value={form.site_id} onChange={e => setForm({ ...form, site_id: e.target.value })} {...inp}>
                <option value="">No specific site</option>
                {(contract.sites || []).map(s => <option key={s.id} value={s.id}>{s.site_name}</option>)}
              </select>
            </Field>
          )}
          <Field label="Exclusions" span={2}><textarea value={form.exclusions} onChange={e => setForm({ ...form, exclusions: e.target.value })} rows={2} placeholder="Any exclusions..." {...inp} className="w-full px-3 py-2 text-sm rounded-md resize-none" /></Field>
        </div>
        <div className="flex gap-2 mt-4 justify-end">
          <button onClick={() => setShowAdd(false)} className="px-4 py-2 text-sm" style={{ color: c.textMuted }}>Cancel</button>
          <button onClick={addAsset} disabled={saving || !form.asset_name.trim()} className="px-4 py-2 bg-[var(--color-info-ios)] text-white text-sm font-medium rounded-md disabled:opacity-50" data-testid="save-asset-btn">{saving ? 'Adding...' : 'Add Asset'}</button>
        </div>
      </Modal>
    </div>
  );
}


/* ═══ SLA TAB ═══ */
function SLATab({ contract, contractId, API, headers, isDark, c, reload }) {
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);
  const inp = useInput(isDark, c);

  const startEdit = () => {
    const sla = contract.sla || {};
    setForm({
      response_hours: sla.response_hours || 8,
      resolution_hours: sla.resolution_hours || 48,
      parts_included: sla.parts_included || false,
      labour_included: sla.labour_included !== false,
      visits_per_year: sla.visits_per_year || '',
      preventive_maintenance: sla.preventive_maintenance || false,
    });
    setEditing(true);
  };

  const saveSLA = async () => {
    setSaving(true);
    try {
      await axios.put(`${API}/crm/v2/contracts/${contractId}/sla`, form, { headers: headers() });
      setEditing(false);
      reload();
    } catch (e) { console.error(e); }
    setSaving(false);
  };

  const sla = contract.sla || {};

  return (
    <div data-testid="sla-tab">
      <div className="flex items-center justify-between mb-3">
        <p className="text-sm font-medium" style={{ color: c.text }}>SLA & Coverage</p>
        {!editing && (
          <button onClick={startEdit} className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-md border" style={{ borderColor: c.border, color: c.textMuted }} data-testid="edit-sla-btn">
            <Edit2 size={12} /> Edit SLA
          </button>
        )}
      </div>

      {!editing ? (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
            {[
              { l: 'Response Time', v: `${sla.response_hours || 8}h`, color: 'var(--color-accent-amber)' },
              { l: 'Resolution Time', v: `${sla.resolution_hours || 48}h`, color: 'var(--color-info-ios)' },
              { l: 'Parts Included', v: sla.parts_included ? 'Yes' : 'No', color: sla.parts_included ? 'var(--color-success-alt)' : 'var(--color-danger)' },
              { l: 'Labour Included', v: sla.labour_included !== false ? 'Yes' : 'No', color: sla.labour_included !== false ? 'var(--color-success-alt)' : 'var(--color-danger)' },
              { l: 'Visits/Year', v: sla.visits_per_year || 'Unlimited', color: 'var(--color-accent-violet)' },
              { l: 'Preventive Maintenance', v: sla.preventive_maintenance ? 'Included' : 'Not Included', color: sla.preventive_maintenance ? 'var(--color-success-alt)' : 'var(--color-text-faint-alt)' },
            ].map(item => (
              <div key={item.l} className="p-3 rounded-lg border" style={{ background: isDark ? '#111' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
                <p className="text-[10px] uppercase tracking-wider" style={{ color: c.textDim }}>{item.l}</p>
                <p className="text-sm font-semibold mt-0.5" style={{ color: item.color }}>{item.v}</p>
              </div>
            ))}
          </div>
          {contract.coverage_notes && (
            <div className="mt-3 p-3 rounded-lg border" style={{ background: isDark ? '#111' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
              <p className="text-[10px] uppercase tracking-wider" style={{ color: c.textDim }}>Coverage Notes</p>
              <p className="text-sm mt-1 whitespace-pre-wrap" style={{ color: c.text }}>{contract.coverage_notes}</p>
            </div>
          )}
          {contract.exclusions && (
            <div className="mt-3 p-3 rounded-lg border" style={{ background: isDark ? '#0F0A0A' : 'var(--color-rose-50)', borderColor: isDark ? '#3D1F1F' : '#FECACA' }}>
              <p className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--color-danger)' }}>Exclusions</p>
              <p className="text-sm mt-1 whitespace-pre-wrap" style={{ color: c.text }}>{contract.exclusions}</p>
            </div>
          )}
        </>
      ) : (
        <div className="grid grid-cols-2 gap-3">
          <Field label="Response Hours"><input type="number" value={form.response_hours} onChange={e => setForm({ ...form, response_hours: parseInt(e.target.value) || 0 })} {...inp} /></Field>
          <Field label="Resolution Hours"><input type="number" value={form.resolution_hours} onChange={e => setForm({ ...form, resolution_hours: parseInt(e.target.value) || 0 })} {...inp} /></Field>
          <Field label="Parts Included">
            <select value={form.parts_included ? 'yes' : 'no'} onChange={e => setForm({ ...form, parts_included: e.target.value === 'yes' })} {...inp}>
              <option value="no">No</option><option value="yes">Yes</option>
            </select>
          </Field>
          <Field label="Labour Included">
            <select value={form.labour_included ? 'yes' : 'no'} onChange={e => setForm({ ...form, labour_included: e.target.value === 'yes' })} {...inp}>
              <option value="no">No</option><option value="yes">Yes</option>
            </select>
          </Field>
          <Field label="Visits Per Year"><input type="number" value={form.visits_per_year} onChange={e => setForm({ ...form, visits_per_year: parseInt(e.target.value) || null })} placeholder="Leave empty for unlimited" {...inp} /></Field>
          <Field label="Preventive Maintenance">
            <select value={form.preventive_maintenance ? 'yes' : 'no'} onChange={e => setForm({ ...form, preventive_maintenance: e.target.value === 'yes' })} {...inp}>
              <option value="no">No</option><option value="yes">Yes</option>
            </select>
          </Field>
          <div className="col-span-2 flex gap-2 justify-end mt-2">
            <button onClick={() => setEditing(false)} className="px-4 py-2 text-sm" style={{ color: c.textMuted }}>Cancel</button>
            <button onClick={saveSLA} disabled={saving} className="px-4 py-2 bg-[var(--color-info-ios)] text-white text-sm font-medium rounded-md disabled:opacity-50" data-testid="save-sla-btn">{saving ? 'Saving...' : 'Save SLA'}</button>
          </div>
        </div>
      )}
    </div>
  );
}


/* ═══ SERVICE INTEGRATION TAB ═══ */
function ServiceTab({ contract, contractId, API, headers, isDark, c, reload }) {
  const [syncing, setSyncing] = useState('');

  const syncSicon = async () => {
    setSyncing('sicon');
    try {
      await axios.post(`${API}/crm/v2/contracts/${contractId}/sync-sicon`, {}, { headers: headers() });
      reload();
    } catch (e) { alert(e.response?.data?.detail || 'Sync failed'); }
    setSyncing('');
  };

  const syncSage = async () => {
    setSyncing('sage');
    try {
      await axios.post(`${API}/crm/v2/contracts/${contractId}/sync-sage`, {}, { headers: headers() });
      reload();
    } catch (e) { alert(e.response?.data?.detail || 'Sync failed'); }
    setSyncing('');
  };

  return (
    <div data-testid="service-tab">
      <p className="text-sm font-medium mb-3" style={{ color: c.text }}>Service Integration</p>

      {/* Integration Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
        {/* Sicon */}
        <div className="p-4 rounded-xl border" style={{ background: isDark ? '#111' : 'var(--color-neutral-50)', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
          <div className="flex items-center gap-2 mb-3">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'var(--color-accent-violet)20' }}>
              <Link2 size={15} style={{ color: 'var(--color-accent-violet)' }} />
            </div>
            <div>
              <p className="text-sm font-semibold" style={{ color: c.text }}>Sicon Service Contracts</p>
              <p className="text-[10px]" style={{ color: c.textDim }}>Service coverage & SLA execution</p>
            </div>
          </div>
          {contract.sicon_contract_id ? (
            <div className="flex items-center gap-2 mb-2">
              <CheckCircle size={13} style={{ color: 'var(--color-success-alt)' }} />
              <span className="text-xs font-medium" style={{ color: 'var(--color-success-alt)' }}>Synced</span>
              <span className="text-[11px] font-mono px-1.5 py-0.5 rounded" style={{ background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-100)', color: c.text }}>{contract.sicon_contract_id}</span>
            </div>
          ) : (
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle size={13} style={{ color: 'var(--color-accent-amber)' }} />
              <span className="text-xs" style={{ color: 'var(--color-accent-amber)' }}>Not synced</span>
            </div>
          )}
          <button onClick={syncSicon} disabled={syncing === 'sicon'}
            className="w-full mt-1 flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium rounded-md border transition-colors"
            style={{ borderColor: 'var(--color-accent-violet)40', color: 'var(--color-accent-violet)', background: syncing === 'sicon' ? 'var(--color-accent-violet)10' : 'transparent' }}
            data-testid="sync-sicon-btn">
            {syncing === 'sicon' ? <RefreshCw size={12} className="animate-spin" /> : <Zap size={12} />}
            {contract.sicon_contract_id ? 'Re-sync to Sicon' : 'Push to Sicon'}
          </button>
        </div>

        {/* Sage 200 */}
        <div className="p-4 rounded-xl border" style={{ background: isDark ? '#111' : 'var(--color-neutral-50)', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
          <div className="flex items-center gap-2 mb-3">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'var(--color-info-ios)20' }}>
              <DollarSign size={15} style={{ color: 'var(--color-info-ios)' }} />
            </div>
            <div>
              <p className="text-sm font-semibold" style={{ color: c.text }}>Sage 200</p>
              <p className="text-[10px]" style={{ color: c.textDim }}>Financial postings & invoicing</p>
            </div>
          </div>
          {contract.sage_reference ? (
            <div className="flex items-center gap-2 mb-2">
              <CheckCircle size={13} style={{ color: 'var(--color-success-alt)' }} />
              <span className="text-xs font-medium" style={{ color: 'var(--color-success-alt)' }}>Synced</span>
              <span className="text-[11px] font-mono px-1.5 py-0.5 rounded" style={{ background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-100)', color: c.text }}>{contract.sage_reference}</span>
            </div>
          ) : (
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle size={13} style={{ color: 'var(--color-accent-amber)' }} />
              <span className="text-xs" style={{ color: 'var(--color-accent-amber)' }}>Not synced</span>
            </div>
          )}
          <button onClick={syncSage} disabled={syncing === 'sage'}
            className="w-full mt-1 flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium rounded-md border transition-colors"
            style={{ borderColor: 'var(--color-info-ios)40', color: 'var(--color-info-ios)', background: syncing === 'sage' ? 'var(--color-info-ios)10' : 'transparent' }}
            data-testid="sync-sage-btn">
            {syncing === 'sage' ? <RefreshCw size={12} className="animate-spin" /> : <ExternalLink size={12} />}
            {contract.sage_reference ? 'Re-sync to Sage' : 'Push to Sage 200'}
          </button>
        </div>
      </div>

      {/* Service Cases */}
      {(contract.service_cases || []).length > 0 && (
        <div>
          <p className="text-xs font-medium uppercase tracking-wider mb-2" style={{ color: c.textDim }}>Linked Service Cases</p>
          <div className="space-y-2">
            {contract.service_cases.map(sc => (
              <div key={sc.id} className="p-3 rounded-lg border flex items-center gap-3" style={{ background: isDark ? '#111' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
                <Settings2 size={14} style={{ color: 'var(--color-accent-amber)' }} />
                <div className="flex-1">
                  <p className="text-sm font-medium" style={{ color: c.text }}>{sc.subject || sc.title || 'Service Case'}</p>
                  <p className="text-[10px]" style={{ color: c.textDim }}>{sc.status} · {fmtDate(sc.created_at)}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
      {(contract.service_cases || []).length === 0 && (
        <p className="text-center py-4 text-xs" style={{ color: c.textDim }}>No service cases linked to this contract</p>
      )}
    </div>
  );
}


/* ═══ APPROVAL TAB ═══ */
function ApprovalTab({ contract, contractId, API, headers, isDark, c, reload, _user }) {
  const [approvals, setApprovals] = useState([]);
  const [showSubmit, setShowSubmit] = useState(false);
  const [showDecision, setShowDecision] = useState(false);
  const [form, setForm] = useState({ approver_name: '', notes: '' });
  const [decisionForm, setDecisionForm] = useState({ decision: 'approved', notes: '' });
  const [saving, setSaving] = useState(false);
  const inp = useInput(isDark, c);

  const loadApprovals = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/crm/v2/contracts/${contractId}/approvals`, { headers: headers() });
      setApprovals(res.data.approvals || []);
    } catch (e) { console.error(e); }
  }, [API, headers, contractId]);

  useEffect(() => { loadApprovals(); }, [loadApprovals]);

  const submitForApproval = async () => {
    setSaving(true);
    try {
      await axios.post(`${API}/crm/v2/contracts/${contractId}/submit-approval`, form, { headers: headers() });
      setShowSubmit(false);
      setForm({ approver_name: '', notes: '' });
      loadApprovals();
      reload();
    } catch (e) { alert(e.response?.data?.detail || 'Failed'); }
    setSaving(false);
  };

  const submitDecision = async () => {
    setSaving(true);
    try {
      await axios.post(`${API}/crm/v2/contracts/${contractId}/approve`, decisionForm, { headers: headers() });
      setShowDecision(false);
      setDecisionForm({ decision: 'approved', notes: '' });
      loadApprovals();
      reload();
    } catch (e) { alert(e.response?.data?.detail || 'Failed'); }
    setSaving(false);
  };

  const canSubmit = ['draft', 'negotiation', 'amended'].includes(contract.status);
  const canDecide = contract.status === 'pending_approval';

  return (
    <div data-testid="approval-tab">
      <div className="flex items-center justify-between mb-3">
        <p className="text-sm font-medium" style={{ color: c.text }}>Approval Workflow</p>
        <div className="flex gap-2">
          {canSubmit && (
            <button onClick={() => setShowSubmit(true)} className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-md bg-[var(--color-warning)] text-white" data-testid="submit-approval-btn">
              <Send size={12} /> Submit for Approval
            </button>
          )}
          {canDecide && (
            <button onClick={() => setShowDecision(true)} className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-md bg-[var(--color-success-alt)] text-white" data-testid="review-approval-btn">
              <ThumbsUp size={12} /> Review
            </button>
          )}
        </div>
      </div>

      {/* Current Status */}
      <div className="p-3 rounded-lg border mb-4 flex items-center gap-3" style={{ background: isDark ? '#111' : 'var(--color-neutral-50)', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
        <div className="w-8 h-8 rounded-full flex items-center justify-center" style={{ background: `${STATUS_COLORS[contract.status] || 'var(--color-text-faint-alt)'}15` }}>
          {contract.status === 'pending_approval' ? <Clock size={14} style={{ color: 'var(--color-warning)' }} /> :
           contract.status === 'approved' ? <CheckCircle size={14} style={{ color: 'var(--color-success-alt)' }} /> :
           <FileText size={14} style={{ color: 'var(--color-text-faint-alt)' }} />}
        </div>
        <div>
          <p className="text-sm font-medium capitalize" style={{ color: STATUS_COLORS[contract.status] || c.text }}>{contract.status?.replace('_', ' ')}</p>
          <p className="text-[10px]" style={{ color: c.textDim }}>Current contract status</p>
        </div>
      </div>

      {/* History */}
      <p className="text-xs font-medium uppercase tracking-wider mb-2" style={{ color: c.textDim }}>Approval History</p>
      <div className="space-y-2">
        {approvals.map(a => {
          const dc = a.decision === 'approved' ? 'var(--color-success-alt)' : a.decision === 'rejected' ? 'var(--color-danger)' : 'var(--color-warning)';
          return (
            <div key={a.id} className="p-3 rounded-lg border" style={{ background: isDark ? '#111' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
              <div className="flex items-center gap-2 mb-1">
                {a.status === 'pending' ? <Clock size={13} style={{ color: 'var(--color-warning)' }} /> :
                 a.decision === 'approved' ? <ThumbsUp size={13} style={{ color: 'var(--color-success-alt)' }} /> :
                 <ThumbsDown size={13} style={{ color: 'var(--color-danger)' }} />}
                <span className="text-xs font-semibold capitalize" style={{ color: dc }}>{a.status}</span>
                <span className="text-[10px]" style={{ color: c.textDim }}>{fmtDate(a.created_at)}</span>
              </div>
              <p className="text-xs" style={{ color: c.text }}>Submitted by {a.submitted_by}{a.approver_name ? ` → ${a.approver_name}` : ''}</p>
              {a.notes && <p className="text-[11px] mt-0.5 italic" style={{ color: c.textDim }}>{a.notes}</p>}
              {a.decision_notes && <p className="text-[11px] mt-0.5" style={{ color: c.textDim }}>Decision: {a.decision_notes}</p>}
            </div>
          );
        })}
        {approvals.length === 0 && <p className="text-center py-4 text-xs" style={{ color: c.textDim }}>No approval requests yet</p>}
      </div>

      {/* Submit Modal */}
      <Modal open={showSubmit} onClose={() => setShowSubmit(false)} title="Submit for Approval" isDark={isDark} c={c}>
        <div className="space-y-3">
          <Field label="Approver Name"><input value={form.approver_name} onChange={e => setForm({ ...form, approver_name: e.target.value })} placeholder="e.g. Craig Henshall" {...inp} data-testid="approver-name-input" /></Field>
          <Field label="Notes"><textarea value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} rows={3} placeholder="Any notes for the approver..." {...inp} className="w-full px-3 py-2 text-sm rounded-md resize-none" /></Field>
        </div>
        <div className="flex gap-2 mt-4 justify-end">
          <button onClick={() => setShowSubmit(false)} className="px-4 py-2 text-sm" style={{ color: c.textMuted }}>Cancel</button>
          <button onClick={submitForApproval} disabled={saving} className="px-4 py-2 bg-[var(--color-warning)] text-white text-sm font-medium rounded-md disabled:opacity-50" data-testid="confirm-submit-approval-btn">{saving ? 'Submitting...' : 'Submit'}</button>
        </div>
      </Modal>

      {/* Decision Modal */}
      <Modal open={showDecision} onClose={() => setShowDecision(false)} title="Review Contract" isDark={isDark} c={c}>
        <div className="space-y-3">
          <Field label="Decision">
            <div className="flex gap-2 mt-1">
              <button onClick={() => setDecisionForm({ ...decisionForm, decision: 'approved' })}
                className={`flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-md text-sm font-medium border transition-colors ${decisionForm.decision === 'approved' ? 'bg-[var(--color-success-alt)] text-white border-[var(--color-success-alt)]' : ''}`}
                style={decisionForm.decision !== 'approved' ? { borderColor: c.border, color: c.textMuted } : {}}
                data-testid="approve-decision-btn">
                <ThumbsUp size={14} /> Approve
              </button>
              <button onClick={() => setDecisionForm({ ...decisionForm, decision: 'rejected' })}
                className={`flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-md text-sm font-medium border transition-colors ${decisionForm.decision === 'rejected' ? 'bg-[var(--color-danger)] text-white border-[var(--color-danger)]' : ''}`}
                style={decisionForm.decision !== 'rejected' ? { borderColor: c.border, color: c.textMuted } : {}}
                data-testid="reject-decision-btn">
                <ThumbsDown size={14} /> Reject
              </button>
            </div>
          </Field>
          <Field label="Notes"><textarea value={decisionForm.notes} onChange={e => setDecisionForm({ ...decisionForm, notes: e.target.value })} rows={3} placeholder="Decision notes..." {...inp} className="w-full px-3 py-2 text-sm rounded-md resize-none" /></Field>
        </div>
        <div className="flex gap-2 mt-4 justify-end">
          <button onClick={() => setShowDecision(false)} className="px-4 py-2 text-sm" style={{ color: c.textMuted }}>Cancel</button>
          <button onClick={submitDecision} disabled={saving}
            className={`px-4 py-2 text-white text-sm font-medium rounded-md disabled:opacity-50 ${decisionForm.decision === 'approved' ? 'bg-[var(--color-success-alt)]' : 'bg-[var(--color-danger)]'}`}
            data-testid="confirm-decision-btn">{saving ? 'Submitting...' : `Confirm ${decisionForm.decision === 'approved' ? 'Approval' : 'Rejection'}`}</button>
        </div>
      </Modal>
    </div>
  );
}


/* ═══ BILLING TAB ═══ */
function BillingTab({ contract, isDark, c }) {
  const billingPeriod = {
    monthly: 'Monthly', quarterly: 'Quarterly', annual: 'Annual', one_off: 'One-off'
  };
  const periodValue = {
    monthly: (contract.annual_value || 0) / 12,
    quarterly: (contract.annual_value || 0) / 4,
    annual: contract.annual_value || 0,
    one_off: contract.total_value || contract.annual_value || 0,
  };

  return (
    <div data-testid="billing-tab">
      <p className="text-sm font-medium mb-3" style={{ color: c.text }}>Billing & Financials</p>
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
        <div className="p-4 rounded-xl border" style={{ background: isDark ? '#111' : 'var(--color-neutral-50)', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
          <DollarSign size={14} style={{ color: 'var(--color-success-alt)' }} />
          <p className="text-xl font-bold mt-2" style={{ color: 'var(--color-success-alt)' }}>{fmt(contract.annual_value)}</p>
          <p className="text-[10px] uppercase" style={{ color: c.textDim }}>Annual Value</p>
        </div>
        <div className="p-4 rounded-xl border" style={{ background: isDark ? '#111' : 'var(--color-neutral-50)', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
          <Calendar size={14} style={{ color: 'var(--color-info-ios)' }} />
          <p className="text-lg font-bold mt-2" style={{ color: c.text }}>{fmt(periodValue[contract.billing_frequency] || 0)}</p>
          <p className="text-[10px] uppercase" style={{ color: c.textDim }}>Per {billingPeriod[contract.billing_frequency] || 'Period'}</p>
        </div>
        <div className="p-4 rounded-xl border" style={{ background: isDark ? '#111' : 'var(--color-neutral-50)', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
          <BarChart3 size={14} style={{ color: 'var(--color-accent-violet)' }} />
          <p className="text-sm font-semibold capitalize mt-2" style={{ color: c.text }}>{contract.billing_frequency?.replace('_', ' ')}</p>
          <p className="text-[10px] uppercase" style={{ color: c.textDim }}>Billing Frequency</p>
        </div>
      </div>

      {/* External References */}
      <p className="text-xs font-medium uppercase tracking-wider mt-5 mb-2" style={{ color: c.textDim }}>External References</p>
      <div className="grid grid-cols-2 gap-3">
        <div className="p-3 rounded-lg border" style={{ background: isDark ? '#111' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
          <p className="text-[10px] uppercase" style={{ color: c.textDim }}>Sage 200 Reference</p>
          <p className="text-sm font-semibold mt-0.5 font-mono" style={{ color: contract.sage_reference ? 'var(--color-success-alt)' : c.textDim }}>{contract.sage_reference || 'Not synced'}</p>
        </div>
        <div className="p-3 rounded-lg border" style={{ background: isDark ? '#111' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
          <p className="text-[10px] uppercase" style={{ color: c.textDim }}>Sicon Contract ID</p>
          <p className="text-sm font-semibold mt-0.5 font-mono" style={{ color: contract.sicon_contract_id ? 'var(--color-success-alt)' : c.textDim }}>{contract.sicon_contract_id || 'Not linked'}</p>
        </div>
      </div>

      {/* Contract Duration */}
      <p className="text-xs font-medium uppercase tracking-wider mt-5 mb-2" style={{ color: c.textDim }}>Contract Period</p>
      <div className="p-3 rounded-lg border flex items-center gap-4" style={{ background: isDark ? '#111' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
        <div>
          <p className="text-[10px] uppercase" style={{ color: c.textDim }}>Start</p>
          <p className="text-sm font-medium" style={{ color: c.text }}>{fmtDate(contract.start_date)}</p>
        </div>
        <ChevronRight size={14} style={{ color: c.textDim }} />
        <div>
          <p className="text-[10px] uppercase" style={{ color: c.textDim }}>End</p>
          <p className="text-sm font-medium" style={{ color: c.text }}>{fmtDate(contract.end_date)}</p>
        </div>
        <div className="ml-auto">
          <p className="text-[10px] uppercase" style={{ color: c.textDim }}>Auto-Renew</p>
          <p className="text-sm font-medium" style={{ color: contract.auto_renew ? 'var(--color-success-alt)' : c.textDim }}>{contract.auto_renew ? 'Yes' : 'No'}</p>
        </div>
      </div>
    </div>
  );
}


/* ═══ SIGNATURE PAD ═══ */
function SignatureModal({ open, onClose, onSign, isDark, c }) {
  const canvasRef = useRef(null);
  const [drawing, setDrawing] = useState(false);
  const [signerName, setSignerName] = useState('');
  const [saving, setSaving] = useState(false);
  const inp = useInput(isDark, c);

  useEffect(() => {
    if (open && canvasRef.current) {
      const canvas = canvasRef.current;
      const ctx = canvas.getContext('2d');
      const rect = canvas.getBoundingClientRect();
      canvas.width = rect.width;
      canvas.height = rect.height;
      ctx.fillStyle = isDark ? 'var(--color-ink-alt)' : '#fff';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.strokeStyle = isDark ? 'var(--color-border-alt)' : 'var(--color-surface-dark-panel)';
      ctx.lineWidth = 2;
      ctx.lineCap = 'round';
    }
  }, [open, isDark]);

  const getPos = (e) => {
    const rect = canvasRef.current.getBoundingClientRect();
    const touch = e.touches ? e.touches[0] : e;
    return { x: touch.clientX - rect.left, y: touch.clientY - rect.top };
  };

  const startDraw = (e) => {
    e.preventDefault();
    setDrawing(true);
    const ctx = canvasRef.current.getContext('2d');
    const pos = getPos(e);
    ctx.beginPath();
    ctx.moveTo(pos.x, pos.y);
  };

  const draw = (e) => {
    if (!drawing) return;
    e.preventDefault();
    const ctx = canvasRef.current.getContext('2d');
    const pos = getPos(e);
    ctx.lineTo(pos.x, pos.y);
    ctx.stroke();
  };

  const stopDraw = () => setDrawing(false);

  const clearCanvas = () => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = isDark ? 'var(--color-ink-alt)' : '#fff';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
  };

  const handleSign = async () => {
    setSaving(true);
    const signature = canvasRef.current.toDataURL('image/png');
    await onSign({ signature, signer_name: signerName });
    setSaving(false);
  };

  if (!open) return null;

  return (
    <Modal open={open} onClose={onClose} title="Sign Contract" isDark={isDark} c={c} wide>
      <Field label="Signer Name">
        <input value={signerName} onChange={e => setSignerName(e.target.value)} placeholder="Full legal name" {...inp} data-testid="signer-name-input" />
      </Field>
      <div className="mt-3">
        <label className="text-[10px] uppercase tracking-wider font-medium block mb-1" style={{ color: c.textDim }}>Signature</label>
        <canvas ref={canvasRef}
          className="w-full rounded-lg border cursor-crosshair touch-none"
          style={{ height: 150, borderColor: c.border, background: isDark ? 'var(--color-ink-alt)' : '#fff' }}
          onMouseDown={startDraw} onMouseMove={draw} onMouseUp={stopDraw} onMouseLeave={stopDraw}
          onTouchStart={startDraw} onTouchMove={draw} onTouchEnd={stopDraw}
          data-testid="signature-canvas" />
        <button onClick={clearCanvas} className="text-xs mt-1" style={{ color: 'var(--color-info-ios)' }}>Clear</button>
      </div>
      <div className="flex gap-2 mt-4 justify-end">
        <button onClick={onClose} className="px-4 py-2 text-sm" style={{ color: c.textMuted }}>Cancel</button>
        <button onClick={handleSign} disabled={saving || !signerName.trim()}
          className="px-4 py-2 bg-[var(--color-success-alt)] text-white text-sm font-medium rounded-md disabled:opacity-50"
          data-testid="confirm-sign-btn">{saving ? 'Signing...' : 'Sign & Activate'}</button>
      </div>
    </Modal>
  );
}


/* ═══ CONTRACT DETAIL ═══ */
function ContractDetail({ contractId, onBack, c, isDark, API, headers, _navigateTo, user }) {
  const [contract, setContract] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [showEdit, setShowEdit] = useState(false);
  const [editForm, setEditForm] = useState({});
  const [savingEdit, setSavingEdit] = useState(false);
  const [showSign, setShowSign] = useState(false);
  const inp = useInput(isDark, c);

  const load = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/crm/v2/contracts/${contractId}`, { headers: headers() });
      setContract(res.data);
    } catch (e) { console.error(e); }
  }, [API, headers, contractId]);

  useEffect(() => { load(); }, [load]);

  const openEdit = () => {
    setEditForm({
      title: contract.title, tier: contract.tier, status: contract.status,
      annual_value: contract.annual_value, start_date: contract.start_date,
      end_date: contract.end_date, billing_frequency: contract.billing_frequency,
      coverage_notes: contract.coverage_notes || '', exclusions: contract.exclusions || '',
      auto_renew: contract.auto_renew || false, renewal_notice_days: contract.renewal_notice_days || 90,
    });
    setShowEdit(true);
  };

  const saveEdit = async () => {
    setSavingEdit(true);
    try {
      await axios.put(`${API}/crm/v2/contracts/${contractId}`, { ...editForm, annual_value: parseFloat(editForm.annual_value) || 0 }, { headers: headers() });
      setShowEdit(false);
      load();
    } catch (e) { console.error(e); }
    setSavingEdit(false);
  };

  const handleRenew = async () => {
    if (!window.confirm('Create a renewal from this contract? This will generate a new draft contract and renewal opportunity.')) return;
    try {
      const res = await axios.post(`${API}/crm/v2/contracts/${contractId}/renew`, {}, { headers: headers() });
      if (res.data.contract?.id) onBack();
    } catch (e) { alert(e.response?.data?.detail || 'Failed'); }
  };

  const handleSign = async (data) => {
    try {
      await axios.post(`${API}/crm/v2/contracts/${contractId}/sign`, data, { headers: headers() });
      setShowSign(false);
      load();
    } catch (e) { alert(e.response?.data?.detail || 'Failed'); }
  };

  const handleDelete = async () => {
    if (!window.confirm('Delete this contract? This cannot be undone.')) return;
    try {
      await axios.delete(`${API}/crm/v2/contracts/${contractId}`, { headers: headers() });
      onBack();
    } catch (e) { alert(e.response?.data?.detail || 'Cannot delete'); }
  };

  if (!contract) return <div className="flex justify-center py-12"><div className="w-5 h-5 border-2 border-[var(--color-info-ios)] border-t-transparent rounded-full animate-spin" /></div>;

  const sc = STATUS_COLORS[contract.status] || 'var(--color-text-faint-alt)';
  const tc = TIER_COLORS[contract.tier] || 'var(--color-text-faint-alt)';
  const tabs = [
    { id: 'overview', label: 'Overview', icon: FileText },
    { id: 'sites', label: `Sites (${contract.sites?.length || 0})`, icon: MapPin },
    { id: 'assets', label: `Assets (${contract.covered_assets?.length || 0})`, icon: Wrench },
    { id: 'sla', label: 'SLA & Coverage', icon: Shield },
    { id: 'service', label: 'Service Integration', icon: Link2 },
    { id: 'billing', label: 'Billing', icon: DollarSign },
    { id: 'approvals', label: 'Approvals', icon: CheckCircle },
    { id: 'timeline', label: 'Timeline', icon: Activity },
  ];

  const canSign = ['approved', 'sent'].includes(contract.status);
  const canDelete = !['active', 'signed'].includes(contract.status);

  return (
    <div data-testid="contract-detail">
      {/* Back */}
      <button onClick={onBack} className="flex items-center gap-1 text-xs mb-3 hover:underline" style={{ color: c.textDim }} data-testid="back-to-contracts-btn">
        <ArrowLeft size={14} /> Back to Contracts
      </button>

      {/* Header */}
      <div className="flex items-start justify-between mb-5">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-xl font-bold" style={{ color: c.text }}>{contract.title}</h1>
            <span className="text-[9px] font-bold uppercase px-2 py-0.5 rounded" style={{ background: `${sc}15`, color: sc }}>{contract.status?.replace('_', ' ')}</span>
            <span className="text-[9px] font-bold uppercase px-2 py-0.5 rounded" style={{ background: `${tc}15`, color: tc }}>{contract.tier}</span>
          </div>
          <p className="text-xs mt-0.5" style={{ color: c.textDim }}>
            {contract.contract_number} · {contract.company_name || 'No company'} · v{contract.version}
            {contract.signed_by && <> · Signed by {contract.signed_by}</>}
          </p>
        </div>
        <div className="flex gap-2 shrink-0">
          {canSign && (
            <button onClick={() => setShowSign(true)} className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-md bg-[var(--color-success-alt)] text-white" data-testid="sign-contract-btn">
              <PenTool size={12} /> Sign
            </button>
          )}
          <button onClick={openEdit} className="px-3 py-1.5 text-xs font-medium rounded-md border" style={{ borderColor: c.border, color: c.textMuted }} data-testid="contract-edit-btn">
            <Edit2 size={12} className="inline mr-1" />Edit
          </button>
          {contract.status === 'active' && (
            <button onClick={handleRenew} className="px-3 py-1.5 text-xs font-medium rounded-md border" style={{ borderColor: 'var(--color-success-alt)40', color: 'var(--color-success-alt)' }} data-testid="contract-renew-btn">
              <Copy size={12} className="inline mr-1" />Renew
            </button>
          )}
          {canDelete && (
            <button onClick={handleDelete} className="px-3 py-1.5 text-xs font-medium rounded-md border" style={{ borderColor: 'var(--color-danger)40', color: 'var(--color-danger)' }} data-testid="contract-delete-btn">
              <Trash2 size={12} className="inline mr-1" />Delete
            </button>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-5 overflow-x-auto pb-1">
        {tabs.map(tab => (
          <button key={tab.id} onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md whitespace-nowrap transition-colors ${activeTab === tab.id ? 'bg-[var(--color-info-ios)] text-white' : ''}`}
            style={activeTab !== tab.id ? { background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-100)', color: c.textMuted } : {}}
            data-testid={`tab-${tab.id}`}>
            <tab.icon size={12} /> {tab.label}
          </button>
        ))}
      </div>

      {/* Overview */}
      {activeTab === 'overview' && (
        <div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
            {[
              { l: 'Annual Value', v: fmt(contract.annual_value), icon: DollarSign, color: 'var(--color-success-alt)' },
              { l: 'Billing', v: contract.billing_frequency?.replace('_', ' '), icon: Calendar, color: 'var(--color-info-ios)' },
              { l: 'Start Date', v: fmtDate(contract.start_date), icon: Calendar, color: 'var(--color-success-alt-2)' },
              { l: 'End Date', v: fmtDate(contract.end_date), icon: Clock, color: 'var(--color-accent-amber)' },
            ].map(kpi => (
              <div key={kpi.l} className="p-3 rounded-lg border" style={{ background: isDark ? '#111' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
                <kpi.icon size={14} style={{ color: kpi.color }} />
                <p className="text-lg font-bold mt-1" style={{ color: c.text }}>{kpi.v}</p>
                <p className="text-[10px]" style={{ color: c.textDim }}>{kpi.l}</p>
              </div>
            ))}
          </div>

          {/* Quick Info */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
            <div className="p-3 rounded-lg border" style={{ background: isDark ? '#111' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
              <p className="text-[10px] uppercase" style={{ color: c.textDim }}>Type</p>
              <p className="text-sm font-semibold capitalize mt-0.5" style={{ color: c.text }}>{contract.type}</p>
            </div>
            <div className="p-3 rounded-lg border" style={{ background: isDark ? '#111' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
              <p className="text-[10px] uppercase" style={{ color: c.textDim }}>Owner</p>
              <p className="text-sm font-semibold mt-0.5" style={{ color: c.text }}>{contract.owner_name || '—'}</p>
            </div>
            <div className="p-3 rounded-lg border" style={{ background: isDark ? '#111' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
              <p className="text-[10px] uppercase" style={{ color: c.textDim }}>Auto-Renew</p>
              <p className="text-sm font-semibold mt-0.5" style={{ color: contract.auto_renew ? 'var(--color-success-alt)' : c.textDim }}>{contract.auto_renew ? 'Yes' : 'No'}</p>
            </div>
            <div className="p-3 rounded-lg border" style={{ background: isDark ? '#111' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
              <p className="text-[10px] uppercase" style={{ color: c.textDim }}>Renewal Notice</p>
              <p className="text-sm font-semibold mt-0.5" style={{ color: c.text }}>{contract.renewal_notice_days || 90} days</p>
            </div>
          </div>

          {/* Signature */}
          {contract.signed_by && (
            <div className="p-3 rounded-lg border mb-5" style={{ background: isDark ? '#081408' : '#F0FDF4', borderColor: isDark ? '#1A3D1A' : '#BBF7D0' }}>
              <div className="flex items-center gap-2 mb-1">
                <PenTool size={13} style={{ color: 'var(--color-success-alt)' }} />
                <span className="text-xs font-semibold" style={{ color: 'var(--color-success-alt)' }}>Signed</span>
              </div>
              <p className="text-sm" style={{ color: c.text }}>Signed by <strong>{contract.signed_by}</strong> on {fmtDate(contract.signed_at)}</p>
            </div>
          )}

          {/* Umbrella children */}
          {contract.type === 'umbrella' && (contract.child_contracts || []).length > 0 && (
            <div className="mt-3">
              <h3 className="text-sm font-semibold mb-2" style={{ color: c.text }}>Site Contracts</h3>
              <div className="space-y-2">
                {contract.child_contracts.map(child => (
                  <div key={child.id} className="p-3 rounded-lg border flex items-center justify-between" style={{ background: isDark ? '#111' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
                    <div>
                      <p className="text-sm font-medium" style={{ color: c.text }}>{child.title}</p>
                      <p className="text-[11px]" style={{ color: c.textDim }}>{child.company_name}</p>
                    </div>
                    <span className="text-sm font-bold" style={{ color: 'var(--color-success-alt)' }}>{fmt(child.annual_value)}/yr</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Tabs Content */}
      {activeTab === 'sites' && <SitesTab contract={contract} contractId={contractId} API={API} headers={headers} isDark={isDark} c={c} reload={load} />}
      {activeTab === 'assets' && <AssetsTab contract={contract} contractId={contractId} API={API} headers={headers} isDark={isDark} c={c} reload={load} />}
      {activeTab === 'sla' && <SLATab contract={contract} contractId={contractId} API={API} headers={headers} isDark={isDark} c={c} reload={load} />}
      {activeTab === 'service' && <ServiceTab contract={contract} contractId={contractId} API={API} headers={headers} isDark={isDark} c={c} reload={load} />}
      {activeTab === 'billing' && <BillingTab contract={contract} isDark={isDark} c={c} />}
      {activeTab === 'approvals' && <ApprovalTab contract={contract} contractId={contractId} API={API} headers={headers} isDark={isDark} c={c} reload={load} user={user} />}

      {/* Timeline */}
      {activeTab === 'timeline' && (
        <div className="space-y-3" data-testid="timeline-tab">
          {(contract.activities || []).map((act, i) => (
            <div key={act.id || i} className="flex gap-3 p-3 rounded-lg border" style={{ background: isDark ? '#111' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
              <Activity size={14} style={{ color: 'var(--color-info-ios)' }} className="mt-0.5 shrink-0" />
              <div>
                <p className="text-sm font-medium" style={{ color: c.text }}>{act.subject}</p>
                {act.body && <p className="text-xs mt-0.5" style={{ color: c.textDim }}>{act.body}</p>}
                <p className="text-[10px] mt-1" style={{ color: c.textDim }}>{act.owner_name} · {new Date(act.created_at).toLocaleString('en-GB')}</p>
              </div>
            </div>
          ))}
          {(contract.activities || []).length === 0 && <p className="text-center py-8 text-sm" style={{ color: c.textDim }}>No activity yet</p>}
        </div>
      )}

      {/* Edit Dialog */}
      <Modal open={showEdit} onClose={() => setShowEdit(false)} title="Edit Contract" isDark={isDark} c={c} wide>
        <div className="grid grid-cols-2 gap-3">
          {[
            { key: 'title', label: 'Title', span: 2 },
            { key: 'tier', label: 'Tier', type: 'select', options: ['bronze', 'silver', 'gold', 'platinum', 'bespoke'] },
            { key: 'status', label: 'Status', type: 'select', options: ['draft', 'pending_approval', 'approved', 'sent', 'negotiation', 'signed', 'active', 'expiring', 'expired', 'renewed', 'cancelled'] },
            { key: 'annual_value', label: 'Annual Value (£)', type: 'number' },
            { key: 'billing_frequency', label: 'Billing', type: 'select', options: ['monthly', 'quarterly', 'annual', 'one_off'] },
            { key: 'start_date', label: 'Start Date', type: 'date' },
            { key: 'end_date', label: 'End Date', type: 'date' },
            { key: 'coverage_notes', label: 'Coverage Notes', span: 2, type: 'textarea' },
            { key: 'exclusions', label: 'Exclusions', span: 2, type: 'textarea' },
          ].map(f => (
            <div key={f.key} className={f.span === 2 ? 'col-span-2' : ''}>
              <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>{f.label}</label>
              {f.type === 'select' ? (
                <select value={editForm[f.key] || ''} onChange={e => setEditForm({ ...editForm, [f.key]: e.target.value })} {...inp} className="w-full px-3 py-2 text-sm rounded-md capitalize">
                  {f.options.map(o => <option key={o} value={o}>{o.replace('_', ' ')}</option>)}
                </select>
              ) : f.type === 'textarea' ? (
                <textarea value={editForm[f.key] || ''} onChange={e => setEditForm({ ...editForm, [f.key]: e.target.value })} rows={2} {...inp} className="w-full px-3 py-2 text-sm rounded-md resize-none" />
              ) : (
                <input type={f.type || 'text'} value={editForm[f.key] || ''} onChange={e => setEditForm({ ...editForm, [f.key]: e.target.value })} {...inp} />
              )}
            </div>
          ))}
        </div>
        <div className="flex gap-2 mt-5 justify-end">
          <button onClick={() => setShowEdit(false)} className="px-4 py-2 text-sm" style={{ color: c.textMuted }}>Cancel</button>
          <button onClick={saveEdit} disabled={savingEdit} className="px-4 py-2 bg-[var(--color-info-ios)] text-white text-sm font-medium rounded-md disabled:opacity-50" data-testid="save-contract-edit-btn">{savingEdit ? 'Saving...' : 'Save Changes'}</button>
        </div>
      </Modal>

      {/* Sign Modal */}
      <SignatureModal open={showSign} onClose={() => setShowSign(false)} onSign={handleSign} isDark={isDark} c={c} />
    </div>
  );
}


/* ═══ MAIN EXPORT ═══ */
export default function CRMContracts() {
  const crm = useCRM();
  const { navTarget, setNavTarget } = crm;
  const [selectedId, setSelectedId] = useState(null);

  useEffect(() => {
    if (navTarget?.type === 'contract' && navTarget?.id) {
      setSelectedId(navTarget.id);
      setNavTarget(null);
    }
  }, [navTarget, setNavTarget]);

  if (selectedId) return <ContractDetail contractId={selectedId} onBack={() => setSelectedId(null)} {...crm} />;
  return <ContractList onSelect={setSelectedId} {...crm} />;
}
