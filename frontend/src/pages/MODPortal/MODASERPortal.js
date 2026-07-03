/**
 * ASER — Activity Safety Events Register (MOD-exclusive).
 *
 * Full-screen overlay opened from the MOD Service Portal → Reports → ASER.
 * Lets MOD site users log equipment-related safety events that impact rehab
 * delivery, review a register, and (managers) close / flag CAPEX / dispose
 * of equipment. Reuses existing equipment + faults; never duplicates records.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  X, Plus, Search, ShieldAlert, AlertTriangle, Loader2, Upload, Trash2,
  PoundSterling, Wrench, CheckCircle2, ArrowLeft, ClipboardList, Ban, Link2,
} from 'lucide-react';
import { useAuth } from '@/App';
import { notify } from '@/components/notifications';

const RISK_STYLES = {
  low: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
  medium: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
  high: 'bg-orange-500/20 text-orange-300 border-orange-500/40',
  critical: 'bg-red-500/20 text-red-300 border-red-500/40',
};
const REPEATED_LABELS = {
  monitor: 'Monitor',
  repeated_issue: 'Repeated Issue',
  escalation_recommended: 'Escalation Recommended',
  replacement_evidence_building: 'Replacement Evidence Building',
  replacement_strongly_recommended: 'Replacement Strongly Recommended',
};
const REMOVAL_STATUSES = ['removed_from_use', 'awaiting_replacement', 'replacement_recommended'];
const titleCase = (s) => (s || '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

export default function MODASERPortal({ onClose }) {
  const { API } = useAuth();
  const token = localStorage.getItem('token');
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);

  const [config, setConfig] = useState(null);
  const [view, setView] = useState('register'); // register | new | detail
  const [entries, setEntries] = useState([]);
  const [dash, setDash] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeId, setActiveId] = useState(null);
  const [filters, setFilters] = useState({ q: '', risk: '', status: '', event_type: '' });

  const loadConfig = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/mod/aser/config`, { headers });
      setConfig(data);
    } catch { setConfig({ event_types: [], sites: [], is_manager: false }); }
  }, [API, headers]);

  const loadRegister = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      Object.entries(filters).forEach(([k, v]) => v && params.set(k, v));
      const [reg, d] = await Promise.all([
        axios.get(`${API}/mod/aser?${params.toString()}`, { headers }),
        axios.get(`${API}/mod/aser/dashboard`, { headers }),
      ]);
      setEntries(reg.data.entries || []);
      setDash(d.data);
    } catch { setEntries([]); }
    setLoading(false);
  }, [API, headers, filters]);

  useEffect(() => { loadConfig(); }, [loadConfig]);
  useEffect(() => { if (view === 'register') loadRegister(); }, [view, loadRegister]);

  return (
    <div className="fixed inset-0 z-50 bg-[var(--color-ink-deep)] text-white overflow-y-auto" data-testid="mod-aser-portal">
      <header className="border-b border-white/10 bg-[var(--color-surface-darker)] sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-5 py-4 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            {view !== 'register' && (
              <button onClick={() => { setView('register'); setActiveId(null); }} className="text-white/60 hover:text-white" data-testid="aser-back">
                <ArrowLeft size={20} />
              </button>
            )}
            <div>
              <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--color-brand-cyan)]">
                MOD Service Portal · Reports
              </div>
              <h1 className="text-white text-lg sm:text-xl font-extrabold tracking-tight" data-testid="aser-title">
                ASER — Activity Safety Events Register
              </h1>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {view === 'register' && (
              <button onClick={() => setView('new')} className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-extrabold rounded-lg bg-[var(--color-brand-cyan)] text-black hover:opacity-90" data-testid="aser-new-btn">
                <Plus size={14} /> New ASER Entry
              </button>
            )}
            <button onClick={onClose} className="flex items-center gap-1.5 px-3 py-2 text-xs font-bold rounded-lg border border-white/10 hover:bg-white/5" data-testid="aser-close">
              <X size={14} /> Close
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-5 py-6">
        {view === 'register' && (
          <RegisterView
            config={config} dash={dash} entries={entries} loading={loading}
            filters={filters} setFilters={setFilters} onReload={loadRegister}
            onOpen={(id) => { setActiveId(id); setView('detail'); }}
          />
        )}
        {view === 'new' && (
          <NewEntryWizard
            config={config} API={API} headers={headers}
            onCancel={() => setView('register')}
            onDone={() => { setView('register'); }}
          />
        )}
        {view === 'detail' && activeId && (
          <DetailView
            entryId={activeId} config={config} API={API} headers={headers}
            onBack={() => { setView('register'); setActiveId(null); }}
            onChanged={loadRegister}
          />
        )}
      </main>
    </div>
  );
}

// ── Register + dashboard ────────────────────────────────────────────
function RegisterView({ config, dash, entries, loading, filters, setFilters, onOpen }) {
  const cards = dash?.cards || {};
  const card = (label, value, testid, tone = 'neutral') => (
    <div className={`rounded-xl border p-3.5 ${tone === 'red' ? 'border-red-500/40 bg-red-500/10' : 'border-white/10 bg-white/[0.03]'}`} data-testid={testid}>
      <div className="text-[10px] uppercase tracking-wider font-bold text-white/50">{label}</div>
      <div className="text-2xl font-extrabold text-white tracking-tight">{value ?? 0}</div>
    </div>
  );
  return (
    <div className="space-y-5">
      {/* Dashboard cards */}
      <section className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3" data-testid="aser-dashboard-cards">
        {card('Entries this month', cards.entries_this_month, 'aser-card-month')}
        {card('Open entries', cards.open_entries, 'aser-card-open')}
        {card('High-risk', cards.high_risk_entries, 'aser-card-highrisk', cards.high_risk_entries > 0 ? 'red' : 'neutral')}
        {card('Removed from use', cards.removed_from_use, 'aser-card-removed', cards.removed_from_use > 0 ? 'red' : 'neutral')}
        {card('Repeated-issue kit', cards.repeated_issue_equipment, 'aser-card-repeated')}
        {card('Rehab sessions impacted', cards.sessions_impacted, 'aser-card-sessions')}
        {card('Group programmes', cards.group_programmes_impacted, 'aser-card-group')}
        {card('Individual programmes', cards.individual_programmes_impacted, 'aser-card-individual')}
        {card('CAPEX evidence flags', cards.capex_evidence_flags, 'aser-card-capex')}
        {card('Total entries', cards.total_entries, 'aser-card-total')}
      </section>

      {/* Filters */}
      <div className="flex flex-wrap gap-2 items-center">
        <div className="relative flex-1 min-w-[200px]">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/40" />
          <input value={filters.q} onChange={(e) => setFilters({ ...filters, q: e.target.value })}
            placeholder="Search ref, title, asset, serial…" className="w-full pl-9 pr-3 py-2 rounded-lg bg-white/5 border border-white/10 text-sm text-white placeholder:text-white/30" data-testid="aser-filter-q" />
        </div>
        <select value={filters.risk} onChange={(e) => setFilters({ ...filters, risk: e.target.value })} className="px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-sm text-white" data-testid="aser-filter-risk">
          <option value="">All risk</option>
          {(config?.risk_rating || ['low', 'medium', 'high', 'critical']).map((r) => <option key={r} value={r}>{titleCase(r)}</option>)}
        </select>
        <select value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })} className="px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-sm text-white" data-testid="aser-filter-status">
          <option value="">All status</option>
          {(config?.entry_statuses || []).map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}
        </select>
      </div>

      {/* Register list */}
      {loading ? (
        <div className="py-16 text-center text-white/50"><Loader2 className="animate-spin inline" /></div>
      ) : entries.length === 0 ? (
        <div className="rounded-xl border border-dashed border-white/15 py-16 text-center" data-testid="aser-empty">
          <ClipboardList className="mx-auto text-white/40 mb-3" size={40} />
          <p className="text-white/60 font-medium">No ASER entries yet</p>
          <p className="text-sm text-white/40">Log the first equipment safety event impacting rehab / activity delivery.</p>
        </div>
      ) : (
        <div className="space-y-2" data-testid="aser-register-list">
          {entries.map((e) => {
            const removal = REMOVAL_STATUSES.includes(e.equipment_status);
            return (
              <button key={e.id} onClick={() => onOpen(e.id)}
                className={`w-full text-left rounded-xl border p-4 transition-colors ${removal ? 'border-red-500/60 bg-red-500/10 hover:bg-red-500/15' : 'border-white/10 bg-white/[0.03] hover:border-white/25'}`}
                data-testid={`aser-row-${e.id}`}>
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-bold text-white text-sm font-mono">{e.aser_ref}</span>
                      <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full border ${RISK_STYLES[e.risk?.rating] || RISK_STYLES.low}`}>{titleCase(e.risk?.rating)}</span>
                      {removal && <span className="text-[10px] font-extrabold px-1.5 py-0.5 rounded-full bg-red-600 text-white inline-flex items-center gap-1"><Ban size={9} /> {titleCase(e.equipment_status)}</span>}
                      {e.capex_flagged && <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 inline-flex items-center gap-1"><PoundSterling size={9} /> CAPEX</span>}
                    </div>
                    <div className="text-sm text-white mt-1 font-semibold truncate">{e.title}</div>
                    <div className="text-xs text-white/50 mt-0.5 truncate">
                      {e.equipment_snapshot?.name} · {e.equipment_snapshot?.serial_number || '—'} · {titleCase(e.event_type)}
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-white/10 text-white/70">{titleCase(e.status)}</span>
                    {e.repeated_issue?.label && e.repeated_issue.label !== 'monitor' && (
                      <div className="text-[10px] text-amber-300 mt-1">{REPEATED_LABELS[e.repeated_issue.label]}</div>
                    )}
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── New entry wizard ────────────────────────────────────────────────
const emptyForm = {
  site_id: '', equipment_id: '', event_type: 'equipment_failure_rehab',
  title: '', description: '', what_happened: '', immediate_action: '',
  activity_impact: {
    impacted_rehab: false, impacted_group: false, impacted_individual: false, impacted_clinic_output: false,
    activity_affected: '', sessions_affected: 0, patients_affected: 0,
    programme_cancelled: false, programme_delayed: false, programme_modified: false,
    alternative_equipment_used: false, impact_summary: '',
  },
  safety_impact: {
    anyone_injured: false, near_miss: false, equipment_removed: false,
    area_isolated: false, warning_signage: false, concern_description: '',
  },
  risk: { actual_harm: 'no_harm', potential_severity: 'low', likelihood: 'possible', rating: 'low' },
  equipment_status: 'operational',
  follow_up_actions: '', action_owner: '', due_date: '',
  attachment_urls: [], linked_fault_id: null, capex_flagged: false,
};

function NewEntryWizard({ config, API, headers, onCancel, onDone }) {
  const [form, setForm] = useState({ ...emptyForm });
  const [equipment, setEquipment] = useState([]);
  const [eqQuery, setEqQuery] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const sites = config?.sites || [];

  // default site if only one
  useEffect(() => {
    if (sites.length === 1 && !form.site_id) setForm((f) => ({ ...f, site_id: sites[0].id }));
  }, [sites, form.site_id]);

  const loadEquipment = useCallback(async () => {
    if (!form.site_id) { setEquipment([]); return; }
    try {
      const params = new URLSearchParams({ site_id: form.site_id });
      if (eqQuery) params.set('q', eqQuery);
      const { data } = await axios.get(`${API}/mod/aser/equipment?${params.toString()}`, { headers });
      setEquipment(data.equipment || []);
    } catch { setEquipment([]); }
  }, [API, headers, form.site_id, eqQuery]);
  useEffect(() => { loadEquipment(); }, [loadEquipment]);

  const selectedEq = equipment.find((e) => e.id === form.equipment_id);
  const ai = form.activity_impact; const si = form.safety_impact;
  const setAI = (k, v) => setForm({ ...form, activity_impact: { ...ai, [k]: v } });
  const setSI = (k, v) => setForm({ ...form, safety_impact: { ...si, [k]: v } });
  const setRisk = (k, v) => setForm({ ...form, risk: { ...form.risk, [k]: v } });

  const uploadFile = async (file) => {
    if (!file) return;
    const fd = new FormData(); fd.append('file', file);
    try {
      const { data } = await axios.post(`${API}/mod/site/attachments`, fd, { headers });
      setForm((f) => ({ ...f, attachment_urls: [...f.attachment_urls, data.path] }));
      notify.success('Evidence uploaded');
    } catch (e) { notify.error(e?.response?.data?.detail || 'Upload failed'); }
  };

  const submit = async (asDraft = false) => {
    if (!form.site_id) return notify.error('Select a site');
    if (!form.equipment_id) return notify.error('Select equipment from your site');
    if (form.title.trim().length < 3) return notify.error('Add an event title');
    if (form.description.trim().length < 10) return notify.error('Describe what happened (min 10 chars)');
    setSubmitting(true);
    try {
      const { data } = await axios.post(`${API}/mod/aser`, { ...form, submit: !asDraft }, { headers });
      notify.success(asDraft ? 'Draft saved' : `ASER logged — ${data.aser_ref}`);
      onDone();
    } catch (e) { notify.error(e?.response?.data?.detail || 'Could not save ASER entry'); }
    finally { setSubmitting(false); }
  };

  const Toggle = ({ label, value, onChange, testid }) => (
    <label className="flex items-center justify-between gap-2 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 cursor-pointer">
      <span className="text-xs text-white/80">{label}</span>
      <input type="checkbox" checked={value} onChange={(e) => onChange(e.target.checked)} className="accent-[var(--color-brand-cyan)]" data-testid={testid} />
    </label>
  );
  const removalSelected = REMOVAL_STATUSES.includes(form.equipment_status);

  return (
    <div className="max-w-3xl mx-auto space-y-5" data-testid="aser-wizard">
      {/* Privacy guidance */}
      <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200" data-testid="aser-privacy-note">
        Do not enter patient-identifiable medical information unless your organisation has explicitly authorised this. ASER records equipment safety &amp; activity-delivery impact — not clinical records.
      </div>

      {/* Site + equipment */}
      <Section title="1 · Site & equipment">
        {sites.length > 1 && (
          <Field label="Site">
            <select value={form.site_id} onChange={(e) => setForm({ ...form, site_id: e.target.value, equipment_id: '' })} className="input" data-testid="aser-site-select">
              <option value="">Select site…</option>
              {sites.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </Field>
        )}
        <div className="relative">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/40" />
          <input value={eqQuery} onChange={(e) => setEqQuery(e.target.value)} placeholder="Search asset no., serial, model, type…" className="input pl-9" data-testid="aser-equipment-search" disabled={!form.site_id} />
        </div>
        <div className="max-h-56 overflow-auto space-y-1.5 mt-2">
          {equipment.length === 0 ? (
            <p className="text-xs text-white/40 py-4 text-center">
              {form.site_id ? 'No equipment found. Equipment not listed? Contact Pulse Fitness / your site administrator to update the site equipment list.' : 'Select a site to load equipment.'}
            </p>
          ) : equipment.map((e) => {
            const removed = e.aser_removed_from_use;
            const on = form.equipment_id === e.id;
            return (
              <button key={e.id} onClick={() => setForm({ ...form, equipment_id: e.id })}
                className={`w-full text-left rounded-lg border px-3 py-2 transition-colors ${removed ? 'border-red-500/60 bg-red-500/10' : on ? 'border-[var(--color-brand-cyan)] bg-[var(--color-brand-cyan)]/10' : 'border-white/10 bg-white/[0.03] hover:border-white/25'}`}
                data-testid={`aser-eq-${e.id}`}>
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-sm font-semibold text-white truncate">{e.name} {removed && <span className="text-[10px] font-extrabold text-red-300">· FLAGGED FOR REMOVAL</span>}</div>
                    <div className="text-[11px] text-white/50 truncate">{e.equipment_type} · {e.serial_number || 'no serial'} · {e.location || '—'}</div>
                  </div>
                  <div className="text-right text-[10px] text-white/50 shrink-0">
                    {e.open_faults > 0 && <div className="text-amber-300">{e.open_faults} open fault(s)</div>}
                    {e.previous_aser_count > 0 && <div>{e.previous_aser_count} prior ASER</div>}
                  </div>
                </div>
              </button>
            );
          })}
        </div>
        {selectedEq && (
          <div className="mt-2 rounded-lg border border-white/10 bg-white/[0.03] p-3 text-xs text-white/70" data-testid="aser-eq-confirm">
            <span className="font-semibold text-white">{selectedEq.name}</span> · Asset {selectedEq.asset_number || '—'} · {selectedEq.model || '—'} · {selectedEq.equipment_type}
          </div>
        )}
      </Section>

      {/* Event */}
      <Section title="2 · Event">
        <Field label="Event type">
          <select value={form.event_type} onChange={(e) => setForm({ ...form, event_type: e.target.value })} className="input" data-testid="aser-event-type">
            {(config?.event_types || []).map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
          </select>
        </Field>
        <Field label="Event title">
          <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className="input" placeholder="Short summary" data-testid="aser-event-title" />
        </Field>
        <Field label="Description / what happened">
          <textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} rows={3} className="input" placeholder="Describe the equipment issue and how it occurred" data-testid="aser-event-desc" />
        </Field>
        <Field label="Immediate action taken">
          <input value={form.immediate_action} onChange={(e) => setForm({ ...form, immediate_action: e.target.value })} className="input" placeholder="e.g. Isolated machine, put up signage" data-testid="aser-immediate-action" />
        </Field>
      </Section>

      {/* Rehab / activity impact */}
      <Section title="3 · Rehab / activity impact">
        <div className="grid grid-cols-2 gap-2">
          <Toggle label="Impacted rehab delivery" value={ai.impacted_rehab} onChange={(v) => setAI('impacted_rehab', v)} testid="aser-impact-rehab" />
          <Toggle label="Impacted group programme" value={ai.impacted_group} onChange={(v) => setAI('impacted_group', v)} testid="aser-impact-group" />
          <Toggle label="Impacted individual programme" value={ai.impacted_individual} onChange={(v) => setAI('impacted_individual', v)} testid="aser-impact-individual" />
          <Toggle label="Impacted clinic/activity output" value={ai.impacted_clinic_output} onChange={(v) => setAI('impacted_clinic_output', v)} testid="aser-impact-clinic" />
          <Toggle label="Programme cancelled" value={ai.programme_cancelled} onChange={(v) => setAI('programme_cancelled', v)} testid="aser-prog-cancelled" />
          <Toggle label="Programme delayed" value={ai.programme_delayed} onChange={(v) => setAI('programme_delayed', v)} testid="aser-prog-delayed" />
          <Toggle label="Programme modified" value={ai.programme_modified} onChange={(v) => setAI('programme_modified', v)} testid="aser-prog-modified" />
          <Toggle label="Alternative equipment used" value={ai.alternative_equipment_used} onChange={(v) => setAI('alternative_equipment_used', v)} testid="aser-alt-equip" />
        </div>
        <div className="grid grid-cols-2 gap-2 mt-2">
          <Field label="Rehab sessions affected">
            <input type="number" min="0" value={ai.sessions_affected} onChange={(e) => setAI('sessions_affected', parseInt(e.target.value || '0', 10))} className="input" data-testid="aser-sessions" />
          </Field>
          <Field label="Patients/service users affected">
            <input type="number" min="0" value={ai.patients_affected} onChange={(e) => setAI('patients_affected', parseInt(e.target.value || '0', 10))} className="input" data-testid="aser-patients" />
          </Field>
        </div>
      </Section>

      {/* Safety + risk */}
      <Section title="4 · Safety & risk">
        <div className="grid grid-cols-2 gap-2">
          <Toggle label="Anyone injured" value={si.anyone_injured} onChange={(v) => setSI('anyone_injured', v)} testid="aser-injured" />
          <Toggle label="Near miss" value={si.near_miss} onChange={(v) => setSI('near_miss', v)} testid="aser-nearmiss" />
          <Toggle label="Equipment removed from use" value={si.equipment_removed} onChange={(v) => setSI('equipment_removed', v)} testid="aser-removed" />
          <Toggle label="Area isolated" value={si.area_isolated} onChange={(v) => setSI('area_isolated', v)} testid="aser-isolated" />
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-2">
          <Field label="Actual harm"><select value={form.risk.actual_harm} onChange={(e) => setRisk('actual_harm', e.target.value)} className="input" data-testid="aser-actual-harm">{(config?.actual_harm || []).map((x) => <option key={x} value={x}>{titleCase(x)}</option>)}</select></Field>
          <Field label="Potential severity"><select value={form.risk.potential_severity} onChange={(e) => setRisk('potential_severity', e.target.value)} className="input" data-testid="aser-severity">{(config?.potential_severity || []).map((x) => <option key={x} value={x}>{titleCase(x)}</option>)}</select></Field>
          <Field label="Likelihood"><select value={form.risk.likelihood} onChange={(e) => setRisk('likelihood', e.target.value)} className="input" data-testid="aser-likelihood">{(config?.likelihood || []).map((x) => <option key={x} value={x}>{titleCase(x)}</option>)}</select></Field>
          <Field label="Risk rating"><select value={form.risk.rating} onChange={(e) => setRisk('rating', e.target.value)} className="input" data-testid="aser-risk-rating">{(config?.risk_rating || []).map((x) => <option key={x} value={x}>{titleCase(x)}</option>)}</select></Field>
        </div>
        {['high', 'critical'].includes(form.risk.rating) && (
          <p className="text-[11px] text-amber-300 mt-2 flex items-center gap-1"><AlertTriangle size={12} /> High/critical risk — this entry will be flagged for manager review.</p>
        )}
      </Section>

      {/* Equipment status + follow up + evidence */}
      <Section title="5 · Status, follow-up & evidence">
        <Field label="Recommended equipment status">
          <select value={form.equipment_status} onChange={(e) => setForm({ ...form, equipment_status: e.target.value })} className="input" data-testid="aser-equip-status">
            {(config?.equipment_statuses || []).map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}
          </select>
        </Field>
        {removalSelected && (
          <p className="text-[11px] text-red-300 mt-1 flex items-center gap-1" data-testid="aser-removal-warn"><Ban size={12} /> This machine will be highlighted in red across the portal as flagged for removal. A manager can dispose of it later.</p>
        )}
        <div className="grid grid-cols-2 gap-2 mt-2">
          <Field label="Follow-up action owner"><input value={form.action_owner} onChange={(e) => setForm({ ...form, action_owner: e.target.value })} className="input" data-testid="aser-action-owner" /></Field>
          <Field label="Due date"><input type="date" value={form.due_date || ''} onChange={(e) => setForm({ ...form, due_date: e.target.value })} className="input" data-testid="aser-due-date" /></Field>
        </div>
        <Field label="Follow-up actions"><textarea value={form.follow_up_actions} onChange={(e) => setForm({ ...form, follow_up_actions: e.target.value })} rows={2} className="input" data-testid="aser-followup" /></Field>
        <label className="flex items-center gap-2 mt-1 text-sm text-white/80">
          <input type="checkbox" checked={form.capex_flagged} onChange={(e) => setForm({ ...form, capex_flagged: e.target.checked })} className="accent-emerald-500" data-testid="aser-capex-flag" />
          Flag this equipment for CAPEX / replacement review
        </label>
        <div className="mt-3">
          <label className="inline-flex items-center gap-2 text-sm font-medium text-[var(--color-brand-cyan)] cursor-pointer" data-testid="aser-upload-label">
            <Upload size={14} /> Add photo / document evidence
            <input type="file" className="hidden" onChange={(e) => uploadFile(e.target.files?.[0])} />
          </label>
          {form.attachment_urls.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-2">
              {form.attachment_urls.map((p, i) => (
                <span key={i} className="inline-flex items-center gap-1 text-[11px] bg-white/5 border border-white/10 rounded px-2 py-1" data-testid={`aser-attach-${i}`}>
                  Evidence {i + 1}
                  <button onClick={() => setForm({ ...form, attachment_urls: form.attachment_urls.filter((_, j) => j !== i) })} className="text-white/40 hover:text-rose-400"><Trash2 size={11} /></button>
                </span>
              ))}
            </div>
          )}
        </div>
      </Section>

      <div className="flex justify-end gap-2 pb-10">
        <button onClick={onCancel} className="px-4 py-2 rounded-lg border border-white/10 text-sm text-white/80 hover:bg-white/5" data-testid="aser-cancel">Cancel</button>
        <button onClick={() => submit(true)} disabled={submitting} className="px-4 py-2 rounded-lg border border-white/10 text-sm text-white/80 hover:bg-white/5" data-testid="aser-save-draft">Save draft</button>
        <button onClick={() => submit(false)} disabled={submitting} className="px-5 py-2 rounded-lg bg-[var(--color-brand-cyan)] text-black text-sm font-extrabold inline-flex items-center gap-2 disabled:opacity-60" data-testid="aser-submit">
          {submitting ? <Loader2 size={15} className="animate-spin" /> : <CheckCircle2 size={15} />} Submit ASER entry
        </button>
      </div>

      <style>{`.input{width:100%;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:8px;padding:8px 12px;font-size:14px;color:#fff}.input::placeholder{color:rgba(255,255,255,0.3)}`}</style>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4 space-y-2">
      <h3 className="text-xs font-extrabold uppercase tracking-wider text-[var(--color-brand-cyan)]">{title}</h3>
      {children}
    </div>
  );
}
function Field({ label, children }) {
  return (
    <div>
      <label className="block text-[11px] font-bold uppercase tracking-wider text-white/50 mb-1">{label}</label>
      {children}
    </div>
  );
}

// ── Detail view ─────────────────────────────────────────────────────
function DetailView({ entryId, config, API, headers, onBack, onChanged }) {
  const [entry, setEntry] = useState(null);
  const [busy, setBusy] = useState(false);
  const isManager = config?.is_manager;

  const load = useCallback(async () => {
    try { const { data } = await axios.get(`${API}/mod/aser/${entryId}`, { headers }); setEntry(data); }
    catch { setEntry(null); }
  }, [API, headers, entryId]);
  useEffect(() => { load(); }, [load]);

  const act = async (path, label, body = {}) => {
    setBusy(true);
    try { await axios.post(`${API}/mod/aser/${entryId}/${path}`, body, { headers }); notify.success(label); await load(); onChanged?.(); }
    catch (e) { notify.error(e?.response?.data?.detail || 'Action failed'); }
    finally { setBusy(false); }
  };

  if (!entry) return <div className="py-16 text-center text-white/50"><Loader2 className="animate-spin inline" /></div>;
  const removal = REMOVAL_STATUSES.includes(entry.equipment_status);
  const ai = entry.activity_impact || {}; const si = entry.safety_impact || {};

  return (
    <div className="max-w-3xl mx-auto space-y-4" data-testid="aser-detail">
      <div className={`rounded-xl border p-4 ${removal ? 'border-red-500/60 bg-red-500/10' : 'border-white/10 bg-white/[0.03]'}`}>
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-mono font-bold text-white">{entry.aser_ref}</span>
          <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full border ${RISK_STYLES[entry.risk?.rating] || RISK_STYLES.low}`}>{titleCase(entry.risk?.rating)} risk</span>
          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-white/10 text-white/70">{titleCase(entry.status)}</span>
          {removal && <span className="text-[10px] font-extrabold px-1.5 py-0.5 rounded-full bg-red-600 text-white inline-flex items-center gap-1"><Ban size={9} /> {titleCase(entry.equipment_status)}</span>}
          {entry.capex_flagged && <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300">CAPEX flagged</span>}
        </div>
        <h2 className="text-lg font-extrabold text-white mt-2">{entry.title}</h2>
        <p className="text-sm text-white/70 mt-1">{titleCase(entry.event_type)} · {entry.equipment_snapshot?.name} · {entry.equipment_snapshot?.serial_number || '—'} · {entry.site_name}</p>
        {entry.repeated_issue?.label && entry.repeated_issue.label !== 'monitor' && (
          <div className="mt-2 text-xs text-amber-300 flex items-center gap-1"><AlertTriangle size={12} /> {REPEATED_LABELS[entry.repeated_issue.label]} — {(entry.repeated_issue.triggers || []).join(', ')}</div>
        )}
      </div>

      <InfoBlock title="What happened">{entry.description}{entry.immediate_action ? `\n\nImmediate action: ${entry.immediate_action}` : ''}</InfoBlock>

      <div className="grid sm:grid-cols-2 gap-3">
        <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
          <h3 className="text-xs font-bold uppercase tracking-wider text-white/50 mb-2">Rehab / activity impact</h3>
          <ul className="text-sm text-white/80 space-y-0.5">
            {ai.impacted_rehab && <li>· Impacted rehab delivery</li>}
            {ai.impacted_group && <li>· Impacted group programme</li>}
            {ai.impacted_individual && <li>· Impacted individual programme</li>}
            {ai.programme_cancelled && <li>· Programme cancelled</li>}
            <li>· Sessions affected: <b>{ai.sessions_affected || 0}</b></li>
            <li>· Patients affected: <b>{ai.patients_affected || 0}</b></li>
          </ul>
        </div>
        <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
          <h3 className="text-xs font-bold uppercase tracking-wider text-white/50 mb-2">Safety</h3>
          <ul className="text-sm text-white/80 space-y-0.5">
            <li>· Injured: <b>{si.anyone_injured ? 'Yes' : 'No'}</b></li>
            <li>· Near miss: <b>{si.near_miss ? 'Yes' : 'No'}</b></li>
            <li>· Equipment removed: <b>{si.equipment_removed ? 'Yes' : 'No'}</b></li>
            <li>· Area isolated: <b>{si.area_isolated ? 'Yes' : 'No'}</b></li>
          </ul>
        </div>
      </div>

      {/* Actions */}
      <div className="flex flex-wrap gap-2">
        {!entry.linked_fault_id && (
          <button onClick={() => act('create-fault', 'Fault created & linked')} disabled={busy} className="px-3 py-2 rounded-lg border border-white/10 text-sm text-white hover:bg-white/5 inline-flex items-center gap-1.5" data-testid="aser-create-fault"><Wrench size={14} /> Create fault</button>
        )}
        {entry.linked_fault_id && (
          <span className="px-3 py-2 rounded-lg bg-cyan-500/15 border border-cyan-500/40 text-cyan-200 text-sm inline-flex items-center gap-1.5" data-testid="aser-linked-fault"><Link2 size={14} /> Linked to fault {entry.linked_fault_ref || ''}</span>
        )}
        {!entry.capex_flagged && (
          <button onClick={() => act('flag-capex', 'Flagged for CAPEX review')} disabled={busy} className="px-3 py-2 rounded-lg border border-emerald-500/40 bg-emerald-500/10 text-emerald-200 text-sm hover:bg-emerald-500/20 inline-flex items-center gap-1.5" data-testid="aser-flag-capex"><PoundSterling size={14} /> Flag CAPEX</button>
        )}
        {isManager && entry.status !== 'closed' && (
          <button onClick={() => act('close', 'ASER entry closed', { manager_override: true })} disabled={busy} className="px-3 py-2 rounded-lg border border-white/10 text-sm text-white hover:bg-white/5 inline-flex items-center gap-1.5" data-testid="aser-close-entry"><CheckCircle2 size={14} /> Close entry</button>
        )}
        {isManager && removal && !entry.disposed && (
          <button onClick={() => { if (window.confirm('Dispose of this machine? It will be marked disposed and removed from the active register.')) act('dispose', 'Equipment disposed'); }} disabled={busy} className="px-3 py-2 rounded-lg bg-red-600 text-white text-sm font-bold hover:bg-red-700 inline-flex items-center gap-1.5" data-testid="aser-dispose"><Ban size={14} /> Dispose machine</button>
        )}
      </div>
    </div>
  );
}

function InfoBlock({ title, children }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
      <h3 className="text-xs font-bold uppercase tracking-wider text-white/50 mb-2">{title}</h3>
      <p className="text-sm text-white/80 whitespace-pre-line">{children}</p>
    </div>
  );
}
