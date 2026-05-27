/**
 * IncidentsTab — Iter 220s
 *
 * Unified Accident, Near-Miss, Hazard, RIDDOR control surface.
 *
 * Phase 1 surface:
 *   - Filter pills (kind, severity, RIDDOR)
 *   - Live stats strip (count by status / RIDDOR)
 *   - Quick-log mobile-first form (single modal)
 *   - Detail dialog with tabs: Overview · RIDDOR Wizard · Investigation
 *     · Corrective Actions · Audit Trail
 *
 * All data flows go through `${API}/api/incidents/...`. The backend
 * owns reference numbering, audit log immutability, RIDDOR engine,
 * and escalation emails — this component is a pure view + dispatcher.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { notify } from '@/components/notifications';
import {
  AlertTriangle, Plus, Shield, Activity, Loader2, ChevronRight,
  ClipboardCheck, Wrench, FileWarning, Search, FileDown, UserPlus, BarChart3,
  Sparkles, Mic, Square,
} from 'lucide-react';
import IncidentSignaturePad from './IncidentSignaturePad';

const SEVERITY_TONE = {
  minor: { bg: 'bg-slate-100', text: 'text-slate-700', dot: '#94A3B8' },
  moderate: { bg: 'bg-amber-50', text: 'text-amber-700', dot: '#F59E0B' },
  serious: { bg: 'bg-orange-50', text: 'text-orange-700', dot: '#EA580C' },
  major: { bg: 'bg-red-50', text: 'text-red-700', dot: '#DC2626' },
  fatal: { bg: 'bg-rose-100', text: 'text-rose-800', dot: '#9F1239' },
};

const KIND_LABELS = {
  accident: 'Accident',
  near_miss: 'Near miss',
  hazard: 'Hazard',
  dangerous_occurrence: 'Dangerous occurrence',
};

const RIDDOR_TONE = {
  not_assessed: { bg: 'bg-slate-100', text: 'text-slate-600', label: 'Not assessed' },
  non_riddor: { bg: 'bg-emerald-50', text: 'text-emerald-700', label: 'Non-RIDDOR' },
  potential: { bg: 'bg-amber-100', text: 'text-amber-800', label: 'Potential RIDDOR' },
  confirmed: { bg: 'bg-red-100', text: 'text-red-800', label: 'Confirmed RIDDOR' },
  submitted: { bg: 'bg-blue-100', text: 'text-blue-800', label: 'Submitted to HSE' },
  closed: { bg: 'bg-slate-100', text: 'text-slate-700', label: 'Closed' },
};

const titleCase = (s) => (s || '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

export default function IncidentsTab() {
  const { API } = useAuth();
  const token = useMemo(() => localStorage.getItem('token'), []);
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);
  const [picklists, setPicklists] = useState(null);
  const [incidents, setIncidents] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ kind: '', severity: '', riddor: '', q: '', date_from: '', date_to: '', category: '' });
  const [showQuickLog, setShowQuickLog] = useState(false);
  const [activeIncidentId, setActiveIncidentId] = useState(null);
  const [showDashboard, setShowDashboard] = useState(false);

  const downloadListPdf = useCallback((suffix) => {
    axios.get(`${API}/incidents/pdf/${suffix}`, { headers, responseType: 'blob' })
      .then((res) => {
        const blob = new Blob([res.data], { type: 'application/pdf' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = suffix.replace(/[?=]/g, '-') + '.pdf';
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 5000);
      })
      .catch((e) => notify.error(e.response?.data?.detail || 'Could not generate PDF'));
  }, [API, headers]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filters.kind) params.set('kind', filters.kind);
      if (filters.severity) params.set('severity', filters.severity);
      if (filters.riddor) params.set('riddor', filters.riddor);
      if (filters.q) params.set('q', filters.q);
      if (filters.date_from) params.set('date_from', filters.date_from);
      if (filters.date_to) params.set('date_to', filters.date_to);
      if (filters.category) params.set('category', filters.category);
      params.set('limit', '100');
      const [picksRes, listRes, sumRes] = await Promise.all([
        picklists ? Promise.resolve({ data: picklists }) :
          axios.get(`${API}/incidents/picklists`, { headers }),
        axios.get(`${API}/incidents?${params.toString()}`, { headers }),
        axios.get(`${API}/incidents/stats/summary`, { headers }),
      ]);
      if (!picklists) setPicklists(picksRes.data);
      setIncidents(listRes.data.incidents || []);
      setSummary(sumRes.data);
    } catch (e) {
      notify.error('Failed to load incidents');
    } finally {
      setLoading(false);
    }
  }, [API, headers, filters, picklists]);

  useEffect(() => { loadAll(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [filters]);

  return (
    <div className="space-y-6" data-testid="incidents-tab">
      {/* Header + new incident CTA */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-xl font-extrabold tracking-tight text-slate-900 flex items-center gap-2">
            <Shield size={18} className="text-blue-600" />
            Accidents · Near misses · Hazards · RIDDOR
          </h2>
          <p className="text-sm text-slate-500 mt-1">
            Unified incident management with RIDDOR decision engine, investigations, and corrective actions.
            All entries are immutably audited.
          </p>
        </div>
        <Button
          onClick={() => setShowQuickLog(true)}
          className="bg-gradient-to-r from-blue-600 to-purple-600 hover:opacity-90 text-white font-bold"
          data-testid="incident-quick-log-btn"
        >
          <Plus size={16} className="mr-1" /> Log incident
        </Button>
      </div>

      {/* HSE quick exports + dashboard toggle */}
      <div className="flex items-center gap-2 flex-wrap" data-testid="incident-exports-bar">
        <Button size="sm" variant="outline" onClick={() => downloadListPdf('management-summary?days=30')}
                data-testid="export-mgmt-summary">
          <BarChart3 size={12} className="mr-1" /> Management summary (30d)
        </Button>
        <Button size="sm" variant="outline" onClick={() => downloadListPdf('actions-log')}
                data-testid="export-actions-log">
          <FileDown size={12} className="mr-1" /> Corrective actions log
        </Button>
        <Button size="sm" variant={showDashboard ? 'default' : 'outline'}
                className={showDashboard ? 'bg-blue-600 text-white hover:bg-blue-700' : ''}
                onClick={() => setShowDashboard((v) => !v)}
                data-testid="toggle-hse-dashboard">
          <BarChart3 size={12} className="mr-1" /> {showDashboard ? 'Hide HSE dashboard' : 'HSE dashboard'}
        </Button>
      </div>

      {showDashboard ? <HseDashboardStrip /> : null}

      {/* Stat strip */}
      {summary ? (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3" data-testid="incident-stats-strip">
          <StatCard label="Total" value={summary.total} icon={Activity} />
          <StatCard label="Open" value={
            Object.entries(summary.by_status || {}).filter(([k]) => k !== 'closed').reduce((a, [, v]) => a + v, 0)
          } icon={FileWarning} tone="amber" />
          <StatCard label="Potential RIDDOR" value={summary.riddor_potential || 0} icon={AlertTriangle} tone="amber" />
          <StatCard label="Confirmed RIDDOR" value={summary.riddor_confirmed || 0} icon={AlertTriangle} tone="red" />
        </div>
      ) : null}

      {/* Filters */}
      <Card className="p-3 bg-white border border-slate-200" data-testid="incident-filters">
        <div className="flex flex-wrap items-center gap-2">
          <FilterPill label="All kinds" active={!filters.kind} onClick={() => setFilters({ ...filters, kind: '' })} />
          {Object.entries(KIND_LABELS).map(([k, label]) => (
            <FilterPill key={k} label={label} active={filters.kind === k}
              onClick={() => setFilters({ ...filters, kind: k })}
              testId={`incident-filter-kind-${k}`} />
          ))}
          <span className="text-slate-300 mx-1">·</span>
          <FilterPill label="All RIDDOR" active={!filters.riddor} onClick={() => setFilters({ ...filters, riddor: '' })} />
          {['potential', 'confirmed', 'submitted'].map((rid) => (
            <FilterPill key={rid} label={RIDDOR_TONE[rid].label} active={filters.riddor === rid}
              onClick={() => setFilters({ ...filters, riddor: rid })}
              testId={`incident-filter-riddor-${rid}`} />
          ))}
          <div className="ml-auto flex items-center gap-2 w-full sm:w-auto mt-2 sm:mt-0">
            <Input type="date" value={filters.date_from} onChange={(e) => setFilters({ ...filters, date_from: e.target.value })}
                   className="h-9 text-xs w-36" data-testid="incident-filter-from" placeholder="From" />
            <Input type="date" value={filters.date_to} onChange={(e) => setFilters({ ...filters, date_to: e.target.value })}
                   className="h-9 text-xs w-36" data-testid="incident-filter-to" placeholder="To" />
            <Search size={14} className="text-slate-400" />
            <Input
              value={filters.q}
              onChange={(e) => setFilters({ ...filters, q: e.target.value })}
              placeholder="Search reference, description, name…"
              className="h-9 text-sm"
              data-testid="incident-filter-search"
            />
          </div>
        </div>
      </Card>

      {/* List */}
      {loading ? (
        <div className="flex items-center gap-2 text-sm text-slate-500 py-10 justify-center">
          <Loader2 className="animate-spin" size={16} /> Loading incidents…
        </div>
      ) : incidents.length === 0 ? (
        <Card className="p-12 text-center bg-white border-dashed border-slate-300" data-testid="incidents-empty-state">
          <Shield size={32} className="text-slate-300 mx-auto mb-3" />
          <p className="font-bold text-slate-700">No incidents match these filters.</p>
          <p className="text-sm text-slate-500 mt-1">Log an incident to start the audit trail.</p>
        </Card>
      ) : (
        <div className="space-y-2" data-testid="incidents-list">
          {incidents.map((inc) => (
            <IncidentRow key={inc.id} incident={inc} onOpen={() => setActiveIncidentId(inc.id)} />
          ))}
        </div>
      )}

      {/* Quick-log */}
      <QuickLogDialog
        open={showQuickLog}
        onClose={() => setShowQuickLog(false)}
        picklists={picklists}
        onCreated={(created) => {
          setShowQuickLog(false);
          loadAll();
          setActiveIncidentId(created.id);
        }}
      />

      {/* Detail */}
      <IncidentDetailDialog
        incidentId={activeIncidentId}
        onClose={() => { setActiveIncidentId(null); loadAll(); }}
        picklists={picklists}
      />
    </div>
  );
}


function StatCard({ label, value, icon: Icon, tone }) {
  const palette = {
    amber: 'border-amber-200 bg-amber-50 text-amber-800',
    red: 'border-red-200 bg-red-50 text-red-800',
    default: 'border-slate-200 bg-white text-slate-800',
  }[tone || 'default'];
  return (
    <div className={`rounded-xl border p-3 ${palette}`} data-testid={`incident-stat-${label.toLowerCase().replace(/\s+/g, '-')}`}>
      <div className="text-[10px] uppercase tracking-wider font-bold inline-flex items-center gap-1 opacity-80">
        {Icon ? <Icon size={11} /> : null}{label}
      </div>
      <div className="text-2xl font-black mt-1">{value}</div>
    </div>
  );
}

function FilterPill({ label, active, onClick, testId }) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testId}
      className={`text-xs font-bold px-3 py-1.5 rounded-full transition-colors ${
        active
          ? 'bg-blue-600 text-white shadow-sm ring-1 ring-blue-700'
          : 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-50'
      }`}
    >
      {label}
    </button>
  );
}

function IncidentRow({ incident, onOpen }) {
  const sev = SEVERITY_TONE[incident.severity] || SEVERITY_TONE.minor;
  const rid = RIDDOR_TONE[(incident.riddor || {}).status || 'not_assessed'];
  const occurred = incident.occurred_at ? new Date(incident.occurred_at) : null;
  return (
    <button
      type="button"
      onClick={onOpen}
      className="w-full text-left bg-white border border-slate-200 hover:border-blue-300 rounded-xl p-4 transition-colors flex items-start gap-3"
      data-testid={`incident-row-${incident.reference}`}
    >
      <span className="w-2 h-12 rounded-full mt-0.5 flex-shrink-0" style={{ background: sev.dot }} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-mono text-xs font-bold text-slate-500">{incident.reference}</span>
          <Badge variant="outline" className="text-[10px] font-bold uppercase">{KIND_LABELS[incident.kind] || incident.kind}</Badge>
          <Badge className={`${sev.bg} ${sev.text} border-0 text-[10px] font-bold uppercase`}>{incident.severity}</Badge>
          <Badge className={`${rid.bg} ${rid.text} border-0 text-[10px] font-bold uppercase`}>{rid.label}</Badge>
        </div>
        <p className="font-bold text-slate-800 text-sm mt-1.5 line-clamp-2">{incident.description}</p>
        <p className="text-xs text-slate-500 mt-1">
          {titleCase(incident.category)}{incident.location?.area ? ` · ${incident.location.area}` : ''}
          {occurred ? ` · ${occurred.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })}` : ''}
        </p>
      </div>
      <ChevronRight size={16} className="text-slate-400 self-center" />
    </button>
  );
}


function QuickLogDialog({ open, onClose, picklists, onCreated }) {
  const { API } = useAuth();
  const token = useMemo(() => localStorage.getItem('token'), []);
  const initialForm = {
    kind: 'accident', severity: 'minor', category: 'other', description: '',
    location_area: '',
    // Iter 220w — injured party block
    ip_name: '', ip_role: 'member', ip_contact: '',
    // First aid + emergency response
    first_aid_given: false, first_aider_name: '',
    hospital_treatment: false, emergency_services_called: false,
    // Witness (single — managers can invite more via the detail dialog)
    witness_name: '', witness_contact: '',
    immediate_action_taken: '',
  };
  const [form, setForm] = useState(initialForm);
  const [saving, setSaving] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
  // Accident / dangerous_occurrence default to expanded details (legal +
  // duty-of-care reasons). Hazard / near-miss stay collapsed so the
  // 30-second mobile flow still works.
  useEffect(() => {
    if (open) {
      setShowDetails(form.kind === 'accident' || form.kind === 'dangerous_occurrence');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, form.kind]);

  const submit = async () => {
    if ((form.description || '').trim().length < 10) {
      notify.error('Describe the incident in at least 10 characters');
      return;
    }
    const payload = {
      kind: form.kind, severity: form.severity, category: form.category,
      description: form.description.trim(),
      location_area: form.location_area || null,
      immediate_action_taken: form.immediate_action_taken || null,
      first_aid_given: form.first_aid_given || null,
      first_aider_name: form.first_aider_name || null,
      hospital_treatment: form.hospital_treatment || null,
      emergency_services_called: form.emergency_services_called || null,
    };
    if (form.ip_name || form.ip_role || form.ip_contact) {
      payload.injured_party = {
        name: form.ip_name || null,
        role: form.ip_role || null,
        contact: form.ip_contact || null,
      };
    }
    if (form.witness_name) {
      payload.witnesses = [{
        name: form.witness_name,
        contact: form.witness_contact || null,
      }];
    }
    setSaving(true);
    try {
      const res = await axios.post(`${API}/incidents`, payload, {
        headers: { Authorization: `Bearer ${token}` },
      });
      notify.success(`Incident ${res.data.reference} logged`);
      onCreated(res.data);
      setForm(initialForm);
    } catch (e) {
      notify.error(e.response?.data?.detail || 'Failed to log incident');
    } finally {
      setSaving(false);
    }
  };

  if (!picklists) return null;
  const needsInjuredParty = form.kind === 'accident' || form.kind === 'dangerous_occurrence';
  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-lg max-h-[92vh] overflow-y-auto" data-testid="incident-quick-log-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Plus size={16} /> Log incident</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          {/* Reporter callout — auth context already captures it server-side. */}
          <div className="rounded-lg bg-blue-50 border border-blue-200 px-3 py-2 text-xs text-blue-900">
            You're filing this report. Your name, role, and timestamp are captured in the audit trail automatically.
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs font-bold uppercase tracking-wider">Kind</Label>
              <Select value={form.kind} onValueChange={(v) => setForm({ ...form, kind: v })}>
                <SelectTrigger data-testid="incident-form-kind"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {picklists.kinds.map((k) => <SelectItem key={k} value={k}>{KIND_LABELS[k] || titleCase(k)}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs font-bold uppercase tracking-wider">Severity</Label>
              <Select value={form.severity} onValueChange={(v) => setForm({ ...form, severity: v })}>
                <SelectTrigger data-testid="incident-form-severity"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {picklists.severities.map((s) => <SelectItem key={s} value={s}>{titleCase(s)}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div>
            <Label className="text-xs font-bold uppercase tracking-wider">Category</Label>
            <Select value={form.category} onValueChange={(v) => setForm({ ...form, category: v })}>
              <SelectTrigger data-testid="incident-form-category"><SelectValue /></SelectTrigger>
              <SelectContent>
                {picklists.categories.map((c) => <SelectItem key={c} value={c}>{titleCase(c)}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <div className="flex items-center justify-between">
              <Label className="text-xs font-bold uppercase tracking-wider">Description</Label>
              <VoiceDictate onTranscript={(t) => setForm((p) => ({ ...p, description: ((p.description || '') + ' ' + t).trim() }))} />
            </div>
            <Textarea
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder="What happened, where, who, when. Be factual."
              rows={4}
              data-testid="incident-form-description"
            />
          </div>
          <div>
            <Label className="text-xs font-bold uppercase tracking-wider">Location (area)</Label>
            <Input
              value={form.location_area}
              onChange={(e) => setForm({ ...form, location_area: e.target.value })}
              placeholder="e.g. Free weights area, treadmill row 3"
              data-testid="incident-form-location"
            />
          </div>

          {/* Details collapse: shown automatically for accidents */}
          <div>
            <button
              type="button"
              onClick={() => setShowDetails((v) => !v)}
              className="w-full text-left text-xs font-bold uppercase tracking-wider text-blue-700 hover:underline flex items-center justify-between"
              data-testid="incident-form-toggle-details"
            >
              <span>{needsInjuredParty ? 'Injured party, first aid & witnesses' : 'Optional details'}</span>
              <span className="text-slate-400">{showDetails ? '−' : '+'}</span>
            </button>
            {showDetails ? (
              <div className="mt-3 space-y-3 rounded-xl border border-slate-200 bg-slate-50 p-3">
                {/* Injured party */}
                <div>
                  <p className="text-[10px] uppercase tracking-wider font-bold text-slate-500 mb-1">Injured party</p>
                  <div className="grid grid-cols-2 gap-2">
                    <Input value={form.ip_name} onChange={(e) => setForm({ ...form, ip_name: e.target.value })}
                           placeholder="Full name" data-testid="incident-form-ip-name" />
                    <Select value={form.ip_role} onValueChange={(v) => setForm({ ...form, ip_role: v })}>
                      <SelectTrigger data-testid="incident-form-ip-role"><SelectValue placeholder="Role" /></SelectTrigger>
                      <SelectContent>
                        {(picklists.injured_roles || []).map((r) => (
                          <SelectItem key={r} value={r}>{titleCase(r)}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <Input
                    className="mt-2"
                    value={form.ip_contact}
                    onChange={(e) => setForm({ ...form, ip_contact: e.target.value })}
                    placeholder="Phone or email (for follow-up)"
                    data-testid="incident-form-ip-contact"
                  />
                </div>

                {/* First aid + emergency response */}
                <div className="space-y-2">
                  <p className="text-[10px] uppercase tracking-wider font-bold text-slate-500">Response</p>
                  <label className="flex items-center gap-2 text-sm cursor-pointer">
                    <input type="checkbox" checked={form.first_aid_given}
                           onChange={(e) => setForm({ ...form, first_aid_given: e.target.checked })}
                           data-testid="incident-form-first-aid" />
                    First aid given
                  </label>
                  {form.first_aid_given ? (
                    <Input value={form.first_aider_name}
                           onChange={(e) => setForm({ ...form, first_aider_name: e.target.value })}
                           placeholder="First aider's name"
                           data-testid="incident-form-first-aider-name" />
                  ) : null}
                  <label className="flex items-center gap-2 text-sm cursor-pointer">
                    <input type="checkbox" checked={form.hospital_treatment}
                           onChange={(e) => setForm({ ...form, hospital_treatment: e.target.checked })}
                           data-testid="incident-form-hospital" />
                    Taken to hospital for treatment
                  </label>
                  <label className="flex items-center gap-2 text-sm cursor-pointer">
                    <input type="checkbox" checked={form.emergency_services_called}
                           onChange={(e) => setForm({ ...form, emergency_services_called: e.target.checked })}
                           data-testid="incident-form-emergency" />
                    Emergency services attended
                  </label>
                </div>

                <div>
                  <Label className="text-xs font-bold uppercase tracking-wider">Immediate action taken</Label>
                  <Textarea rows={2} value={form.immediate_action_taken}
                            onChange={(e) => setForm({ ...form, immediate_action_taken: e.target.value })}
                            placeholder="What was done on the spot? E.g. wet floor sign placed, machine isolated, area cordoned off."
                            data-testid="incident-form-immediate-action" />
                </div>

                {/* Single witness fast-capture — invite more from the detail dialog */}
                <div>
                  <p className="text-[10px] uppercase tracking-wider font-bold text-slate-500 mb-1">Witness (you can invite more later)</p>
                  <div className="grid grid-cols-2 gap-2">
                    <Input value={form.witness_name}
                           onChange={(e) => setForm({ ...form, witness_name: e.target.value })}
                           placeholder="Witness name"
                           data-testid="incident-form-witness-name" />
                    <Input value={form.witness_contact}
                           onChange={(e) => setForm({ ...form, witness_contact: e.target.value })}
                           placeholder="Phone or email"
                           data-testid="incident-form-witness-contact" />
                  </div>
                </div>
              </div>
            ) : null}
          </div>

          <div className="flex gap-2 justify-end pt-2">
            <Button variant="outline" onClick={onClose}>Cancel</Button>
            <Button
              onClick={submit}
              disabled={saving}
              className="bg-blue-600 hover:bg-blue-700 text-white"
              data-testid="incident-form-submit"
            >
              {saving ? <Loader2 className="animate-spin mr-2" size={14} /> : null}
              Log incident
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}


function IncidentDetailDialog({ incidentId, onClose, picklists }) {
  const { API } = useAuth();
  const token = useMemo(() => localStorage.getItem('token'), []);
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);
  const [bundle, setBundle] = useState(null);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState('overview');

  const load = useCallback(async () => {
    if (!incidentId) return;
    setLoading(true);
    try {
      const r = await axios.get(`${API}/incidents/${incidentId}`, { headers });
      setBundle(r.data);
    } catch (e) {
      notify.error('Could not load incident');
    } finally {
      setLoading(false);
    }
  }, [API, headers, incidentId]);

  useEffect(() => { if (incidentId) { load(); setTab('overview'); } else { setBundle(null); } }, [incidentId, load]);

  const incident = bundle?.incident;
  if (!incidentId) return null;
  return (
    <Dialog open={!!incidentId} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-3xl max-h-[92vh] overflow-y-auto" data-testid="incident-detail-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Shield size={16} className="text-blue-600" />
            {incident ? `${incident.reference} — ${KIND_LABELS[incident.kind] || titleCase(incident.kind)}` : 'Loading…'}
          </DialogTitle>
        </DialogHeader>
        {loading || !incident ? (
          <div className="py-10 text-center text-slate-500"><Loader2 className="animate-spin inline mr-2" size={14} /> Loading…</div>
        ) : (
          <div className="space-y-4">
            {/* Tabs */}
            <div className="flex gap-1 border-b border-slate-200 overflow-x-auto">
              {[
                { id: 'overview', label: 'Overview', icon: Activity },
                { id: 'riddor', label: 'RIDDOR', icon: AlertTriangle },
                { id: 'investigation', label: 'Investigation', icon: ClipboardCheck },
                { id: 'actions', label: `Actions${bundle.actions?.length ? ` · ${bundle.actions.length}` : ''}`, icon: Wrench },
                { id: 'audit', label: `Audit${bundle.audit?.length ? ` · ${bundle.audit.length}` : ''}`, icon: FileWarning },
              ].map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setTab(t.id)}
                  className={`px-3 py-2 text-xs font-bold uppercase tracking-wider whitespace-nowrap flex items-center gap-1 ${
                    tab === t.id ? 'text-blue-600 border-b-2 border-blue-600' : 'text-slate-500 hover:text-slate-700'
                  }`}
                  data-testid={`incident-tab-${t.id}`}
                >
                  <t.icon size={12} />{t.label}
                </button>
              ))}
            </div>
            {tab === 'overview' && <OverviewPane incident={incident} onChanged={load} />}
            {tab === 'riddor' && <RiddorPane incident={incident} picklists={picklists} onChanged={load} />}
            {tab === 'investigation' && <InvestigationPane incident={incident} picklists={picklists} onChanged={load} />}
            {tab === 'actions' && <ActionsPane incident={incident} actions={bundle.actions} onChanged={load} />}
            {tab === 'audit' && <AuditPane rows={bundle.audit} />}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}


function OverviewPane({ incident, onChanged }) {
  const { API } = useAuth();
  const token = useMemo(() => localStorage.getItem('token'), []);
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);
  const sev = SEVERITY_TONE[incident.severity] || SEVERITY_TONE.minor;
  const rid = RIDDOR_TONE[(incident.riddor || {}).status || 'not_assessed'];
  const [showWitness, setShowWitness] = useState(false);
  const [showSig, setShowSig] = useState(false);

  const downloadPdf = (suffix) => {
    // axios + blob → trigger browser save
    axios.get(`${API}/incidents/${incident.id}/pdf/${suffix}`, { headers, responseType: 'blob' })
      .then((res) => {
        const blob = new Blob([res.data], { type: 'application/pdf' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = `${incident.reference}-${suffix}.pdf`;
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 5000);
      })
      .catch((e) => notify.error(e.response?.data?.detail || 'PDF download failed'));
  };

  return (
    <div className="space-y-4 text-sm">
      <div className="flex flex-wrap gap-2 items-center">
        <Badge className={`${sev.bg} ${sev.text} border-0 font-bold uppercase`}>{incident.severity}</Badge>
        <Badge className={`${rid.bg} ${rid.text} border-0 font-bold uppercase`}>{rid.label}</Badge>
        <Badge variant="outline" className="font-bold uppercase">{incident.status?.replace(/_/g, ' ')}</Badge>
        {incident.fatality ? <Badge className="bg-rose-200 text-rose-900 border-0 font-bold uppercase">Fatality</Badge> : null}
        <div className="ml-auto flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={() => downloadPdf('accident')} data-testid="pdf-accident">
            <FileDown size={12} className="mr-1" /> Accident PDF
          </Button>
          {(incident.riddor?.status && incident.riddor.status !== 'not_assessed') ? (
            <Button size="sm" variant="outline" onClick={() => downloadPdf('riddor')} data-testid="pdf-riddor">
              <FileDown size={12} className="mr-1" /> RIDDOR PDF
            </Button>
          ) : null}
          {incident.investigation ? (
            <Button size="sm" variant="outline" onClick={() => downloadPdf('investigation')} data-testid="pdf-investigation">
              <FileDown size={12} className="mr-1" /> Investigation PDF
            </Button>
          ) : null}
          <Button size="sm" variant="outline" onClick={() => setShowWitness(true)} data-testid="invite-witness-btn">
            <UserPlus size={12} className="mr-1" /> Invite witness
          </Button>
          <Button size="sm" variant="outline" onClick={() => setShowSig(true)} data-testid="sign-incident-btn">
            <ClipboardCheck size={12} className="mr-1" /> Sign
          </Button>
        </div>
      </div>
      <div className="bg-slate-50 rounded-xl border border-slate-200 p-4" data-testid="incident-description">
        <p className="text-[10px] uppercase tracking-wider font-bold text-slate-500 mb-1">Description</p>
        <p className="text-slate-800 whitespace-pre-wrap">{incident.description}</p>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Detail label="Category" value={titleCase(incident.category)} />
        <Detail label="Occurred at" value={incident.occurred_at ? new Date(incident.occurred_at).toLocaleString() : '—'} />
        <Detail label="Location" value={incident.location?.area || '—'} />
        <Detail label="Reported by" value={incident.created_by_name || '—'} />
      </div>
      {incident.immediate_action_taken ? (
        <Detail label="Immediate action taken" value={incident.immediate_action_taken} block />
      ) : null}
      {incident.witnesses?.length ? (
        <div>
          <p className="text-[10px] uppercase tracking-wider font-bold text-slate-500 mb-1">Witnesses</p>
          <ul className="text-sm text-slate-700 list-disc pl-5">
            {incident.witnesses.map((w, i) => (
              <li key={i} className="flex items-center gap-2">
                <span>{w.name}{w.role ? ` · ${w.role}` : ''}{w.submitted_via_token ? ' · signed externally' : ''}</span>
                <button
                  type="button"
                  onClick={() => downloadPdf(`witness/${i}`)}
                  className="text-blue-600 hover:underline text-xs font-bold"
                  data-testid={`pdf-witness-${i}`}
                >
                  Download statement
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {incident.signatures?.length ? (
        <div>
          <p className="text-[10px] uppercase tracking-wider font-bold text-slate-500 mb-1">Signatures</p>
          <ul className="text-sm text-slate-700 list-disc pl-5">
            {incident.signatures.map((s, i) => (
              <li key={i}>{s.name} · {titleCase(s.role)} · {new Date(s.signed_at).toLocaleString()}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <InviteWitnessDialog
        open={showWitness} onClose={() => setShowWitness(false)}
        incidentId={incident.id} onSent={() => { setShowWitness(false); onChanged && onChanged(); }}
      />
      <SignDialog
        open={showSig} onClose={() => setShowSig(false)}
        incidentId={incident.id} onSigned={() => { setShowSig(false); onChanged && onChanged(); }}
      />
    </div>
  );
}


function InviteWitnessDialog({ open, onClose, incidentId, onSent }) {
  const { API } = useAuth();
  const token = useMemo(() => localStorage.getItem('token'), []);
  const [form, setForm] = useState({ name: '', email: '', role: 'member', contact: '' });
  const [sending, setSending] = useState(false);
  const submit = async () => {
    if (!form.name.trim()) return notify.error('Witness name required');
    setSending(true);
    try {
      const r = await axios.post(`${API}/incidents/${incidentId}/witness-invite`, form,
        { headers: { Authorization: `Bearer ${token}` } });
      if (r.data.emailed) notify.success('Witness emailed a one-time statement link');
      else if (form.email) notify.warning('Token created — email send may have failed');
      else notify.info('Token created — share the link manually');
      onSent();
    } catch (e) {
      notify.error(e.response?.data?.detail || 'Failed to invite witness');
    } finally { setSending(false); }
  };
  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-md" data-testid="invite-witness-dialog">
        <DialogHeader><DialogTitle>Invite witness statement</DialogTitle></DialogHeader>
        <div className="space-y-3 text-sm">
          <p className="text-slate-500 text-xs">
            Sends a one-time, 30-day link the witness can fill in themselves — no login required.
            Their statement + drawn signature attach directly to the incident audit trail.
          </p>
          <div>
            <Label className="text-xs font-bold uppercase tracking-wider">Witness name</Label>
            <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                   data-testid="invite-witness-name" />
          </div>
          <div>
            <Label className="text-xs font-bold uppercase tracking-wider">Email (optional but recommended)</Label>
            <Input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })}
                   placeholder="witness@example.com" data-testid="invite-witness-email" />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <Label className="text-xs font-bold uppercase tracking-wider">Role</Label>
              <Input value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} />
            </div>
            <div>
              <Label className="text-xs font-bold uppercase tracking-wider">Contact (phone)</Label>
              <Input value={form.contact} onChange={(e) => setForm({ ...form, contact: e.target.value })} />
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="outline" onClick={onClose}>Cancel</Button>
            <Button onClick={submit} disabled={sending} className="bg-blue-600 hover:bg-blue-700 text-white"
                    data-testid="invite-witness-send">
              {sending ? <Loader2 className="animate-spin mr-2" size={14} /> : null}
              Send invite
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}


function SignDialog({ open, onClose, incidentId, onSigned }) {
  const { API } = useAuth();
  const tokenLs = useMemo(() => localStorage.getItem('token'), []);
  const [name, setName] = useState('');
  const [role, setRole] = useState('manager');
  const [sig, setSig] = useState('');
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    if (!name.trim()) return notify.error('Name required');
    setSaving(true);
    try {
      const b64 = sig.startsWith('data:') ? sig.split(',', 2)[1] : sig;
      await axios.post(`${API}/incidents/${incidentId}/signatures`,
        { name: name.trim(), role, image_b64: b64 },
        { headers: { Authorization: `Bearer ${tokenLs}` } });
      notify.success('Signature recorded');
      setName(''); setSig(''); onSigned();
    } catch (e) {
      notify.error(e.response?.data?.detail || 'Sign failed');
    } finally { setSaving(false); }
  };
  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-md" data-testid="sign-dialog">
        <DialogHeader><DialogTitle>Sign this incident</DialogTitle></DialogHeader>
        <div className="space-y-3 text-sm">
          <div>
            <Label className="text-xs font-bold uppercase tracking-wider">Your name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} data-testid="sign-name" />
          </div>
          <div>
            <Label className="text-xs font-bold uppercase tracking-wider">Role</Label>
            <Select value={role} onValueChange={setRole}>
              <SelectTrigger data-testid="sign-role"><SelectValue /></SelectTrigger>
              <SelectContent>
                {['manager', 'investigator', 'hse_lead', 'injured_person', 'witness', 'other'].map((r) => (
                  <SelectItem key={r} value={r}>{titleCase(r)}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs font-bold uppercase tracking-wider">Signature</Label>
            <IncidentSignaturePad onChange={setSig} testId="sign-pad" />
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={onClose}>Cancel</Button>
            <Button onClick={submit} disabled={saving} className="bg-blue-600 hover:bg-blue-700 text-white"
                    data-testid="sign-submit">
              {saving ? <Loader2 className="animate-spin mr-2" size={14} /> : null}
              Record signature
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function Detail({ label, value, block }) {
  return (
    <div className={block ? 'col-span-2' : ''}>
      <p className="text-[10px] uppercase tracking-wider font-bold text-slate-500">{label}</p>
      <p className="text-sm text-slate-800 font-semibold whitespace-pre-wrap">{value}</p>
    </div>
  );
}


function RiddorPane({ incident, picklists, onChanged }) {
  const { API } = useAuth();
  const token = useMemo(() => localStorage.getItem('token'), []);
  const [answers, setAnswers] = useState(() => ({ ...(incident.riddor?.assessment?.answers || {}) }));
  const [running, setRunning] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submissionRef, setSubmissionRef] = useState('');
  const questions = picklists?.riddor_questions || [];
  const riddor = incident.riddor || {};

  const setAns = (key, v) => setAnswers((prev) => ({ ...prev, [key]: v }));

  const runAssess = async () => {
    setRunning(true);
    try {
      const r = await axios.post(`${API}/incidents/${incident.id}/riddor/assess`,
        { answers }, { headers: { Authorization: `Bearer ${token}` } });
      const status = r.data.verdict.status;
      const msg = status === 'confirmed' ? 'RIDDOR confirmed — review the deadline and submit to HSE'
                : status === 'potential' ? 'Potential RIDDOR — H&S lead review required'
                : 'Assessed: Non-RIDDOR';
      if (status === 'non_riddor') notify.success(msg);
      else notify.warning(msg);
      onChanged();
    } catch (e) {
      notify.error(e.response?.data?.detail || 'RIDDOR assessment failed');
    } finally {
      setRunning(false);
    }
  };

  const [aiLoading, setAiLoading] = useState(false);
  const [aiReasoning, setAiReasoning] = useState('');
  const aiPrefill = async () => {
    setAiLoading(true);
    try {
      const r = await axios.post(`${API}/incidents/${incident.id}/ai/riddor-hint`,
        {}, { headers: { Authorization: `Bearer ${token}` } });
      setAnswers((prev) => ({ ...prev, ...(r.data.answers || {}) }));
      setAiReasoning(r.data.reasoning || '');
      notify.success('AI pre-filled the wizard — review each answer before assessing');
    } catch (e) {
      notify.error(e.response?.data?.detail || 'AI hint unavailable');
    } finally { setAiLoading(false); }
  };

  const submit = async () => {
    if (!submissionRef.trim()) return notify.error('HSE submission reference required');
    setSubmitting(true);
    try {
      await axios.post(`${API}/incidents/${incident.id}/riddor/submit`,
        { submission_ref: submissionRef.trim() }, { headers: { Authorization: `Bearer ${token}` } });
      notify.success('Marked as submitted to HSE');
      setSubmissionRef('');
      onChanged();
    } catch (e) {
      notify.error(e.response?.data?.detail || 'Failed to record submission');
    } finally { setSubmitting(false); }
  };

  return (
    <div className="space-y-4 text-sm">
      {riddor.status && riddor.status !== 'not_assessed' ? (
        <div className="rounded-xl border-2 p-4"
             style={{ borderColor: RIDDOR_TONE[riddor.status]?.text ? undefined : '#E5E7EB' }}>
          <div className="flex items-center gap-2 flex-wrap">
            <Badge className={`${RIDDOR_TONE[riddor.status].bg} ${RIDDOR_TONE[riddor.status].text} border-0 font-bold uppercase`}>
              {RIDDOR_TONE[riddor.status].label}
            </Badge>
            {riddor.form ? <Badge variant="outline" className="font-mono">{riddor.form}</Badge> : null}
            {riddor.deadline_at ? (
              <span className="text-xs text-slate-600">
                Statutory deadline: <strong>{new Date(riddor.deadline_at).toLocaleDateString()}</strong>
              </span>
            ) : null}
          </div>
          {riddor.assessment?.reasons?.length ? (
            <ul className="text-xs text-slate-700 list-disc pl-5 mt-2">
              {riddor.assessment.reasons.map((r, i) => <li key={i}>{r}</li>)}
            </ul>
          ) : null}
        </div>
      ) : null}

      {/* Wizard */}
      <div className="space-y-3" data-testid="riddor-wizard">
        {questions.map((q) => (
          <div key={q.key} className="rounded-lg border border-slate-200 p-3 bg-white">
            <p className="text-sm font-bold text-slate-800">{q.prompt}</p>
            <p className="text-xs text-slate-500 mt-1">{q.help}</p>
            <div className="flex gap-2 mt-2">
              {[
                { label: 'Yes', val: true, tone: 'bg-emerald-600' },
                { label: 'No', val: false, tone: 'bg-slate-600' },
                { label: "Don't know", val: null, tone: 'bg-amber-600' },
              ].map((opt) => {
                const active = answers[q.key] === opt.val;
                return (
                  <button
                    key={String(opt.val)}
                    type="button"
                    onClick={() => setAns(q.key, opt.val)}
                    className={`text-xs font-bold px-3 py-1.5 rounded-full ${
                      active ? `${opt.tone} text-white` : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                    }`}
                    data-testid={`riddor-${q.key}-${opt.label.toLowerCase().replace(/\W+/g, '')}`}
                  >
                    {opt.label}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>
      <div className="flex justify-end gap-2">
        <Button onClick={aiPrefill} variant="outline" disabled={aiLoading}
                className="text-blue-700 border-blue-300 hover:bg-blue-50"
                data-testid="riddor-ai-prefill">
          {aiLoading ? <Loader2 className="animate-spin mr-2" size={14} /> : <Sparkles size={14} className="mr-2" />}
          Pre-fill with AI
        </Button>
        <Button onClick={runAssess} disabled={running} className="bg-blue-600 hover:bg-blue-700 text-white"
                data-testid="riddor-run-assess">
          {running ? <Loader2 className="animate-spin mr-2" size={14} /> : null}
          Run RIDDOR assessment
        </Button>
      </div>
      {aiReasoning ? (
        <div className="rounded-lg bg-blue-50 border border-blue-200 p-3 text-xs text-blue-900">
          <p className="font-bold mb-1 uppercase tracking-wider text-[10px]">AI reasoning (advisory only)</p>
          <p>{aiReasoning}</p>
        </div>
      ) : null}

      {riddor.status === 'confirmed' || riddor.status === 'potential' ? (
        <div className="rounded-xl bg-amber-50 border border-amber-200 p-3 flex flex-col sm:flex-row sm:items-end gap-2">
          <div className="flex-1">
            <Label className="text-xs font-bold uppercase tracking-wider">HSE submission reference (after filing F2508)</Label>
            <Input
              value={submissionRef}
              onChange={(e) => setSubmissionRef(e.target.value)}
              placeholder="e.g. F2508-2026-001234"
              data-testid="riddor-submission-ref"
            />
          </div>
          <Button onClick={submit} disabled={submitting} className="bg-emerald-600 hover:bg-emerald-700 text-white"
                  data-testid="riddor-mark-submitted">
            {submitting ? <Loader2 className="animate-spin mr-2" size={14} /> : null}
            Mark submitted
          </Button>
        </div>
      ) : null}
    </div>
  );
}


function InvestigationPane({ incident, picklists, onChanged }) {
  const { API } = useAuth();
  const token = useMemo(() => localStorage.getItem('token'), []);
  const inv = incident.investigation || {};
  const [findings, setFindings] = useState(inv.findings || '');
  const [rootCauses, setRootCauses] = useState(inv.root_causes || []);
  const [saving, setSaving] = useState(false);
  const [aiBusy, setAiBusy] = useState(false);

  const toggleCause = (c) => {
    setRootCauses((prev) => prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]);
  };
  const save = async (completed = false) => {
    setSaving(true);
    try {
      await axios.post(`${API}/incidents/${incident.id}/investigation`,
        { findings, root_causes: rootCauses, completed },
        { headers: { Authorization: `Bearer ${token}` } });
      notify.success(completed ? 'Investigation closed' : 'Investigation saved');
      onChanged();
    } catch (e) {
      notify.error(e.response?.data?.detail || 'Save failed');
    } finally { setSaving(false); }
  };

  const aiSuggestCauses = async () => {
    setAiBusy(true);
    try {
      const r = await axios.post(`${API}/incidents/${incident.id}/ai/root-causes`,
        {}, { headers: { Authorization: `Bearer ${token}` } });
      const suggested = r.data.root_causes || [];
      setRootCauses((prev) => Array.from(new Set([...prev, ...suggested])));
      notify.success(`AI suggested ${suggested.length} root cause(s) — review before saving`);
    } catch (e) {
      notify.error(e.response?.data?.detail || 'AI suggestion unavailable');
    } finally { setAiBusy(false); }
  };

  const aiSummarise = async () => {
    setAiBusy(true);
    try {
      const r = await axios.post(`${API}/incidents/${incident.id}/ai/summarise`,
        {}, { headers: { Authorization: `Bearer ${token}` } });
      if (r.data.summary) {
        setFindings((prev) => (prev ? `${prev}\n\n— AI summary —\n${r.data.summary}` : r.data.summary));
        notify.success('AI summary drafted into the findings');
      }
    } catch (e) {
      notify.error(e.response?.data?.detail || 'AI summary unavailable');
    } finally { setAiBusy(false); }
  };

  return (
    <div className="space-y-3 text-sm" data-testid="investigation-pane">
      <div>
        <div className="flex items-center justify-between mb-1">
          <Label className="text-xs font-bold uppercase tracking-wider">Investigator findings</Label>
          <Button size="sm" variant="ghost" onClick={aiSummarise} disabled={aiBusy}
                  className="text-blue-700 hover:bg-blue-50 h-7 px-2"
                  data-testid="investigation-ai-summarise">
            {aiBusy ? <Loader2 className="animate-spin" size={12} /> : <Sparkles size={12} />}
            <span className="ml-1 text-xs">AI summarise</span>
          </Button>
        </div>
        <Textarea rows={5} value={findings} onChange={(e) => setFindings(e.target.value)}
                  placeholder="What did the investigation reveal? Witness statements, equipment checks, environmental factors…"
                  data-testid="investigation-findings" />
      </div>
      <div>
        <div className="flex items-center justify-between mb-1">
          <Label className="text-xs font-bold uppercase tracking-wider">Root cause(s)</Label>
          <Button size="sm" variant="ghost" onClick={aiSuggestCauses} disabled={aiBusy}
                  className="text-blue-700 hover:bg-blue-50 h-7 px-2"
                  data-testid="investigation-ai-causes">
            {aiBusy ? <Loader2 className="animate-spin" size={12} /> : <Sparkles size={12} />}
            <span className="ml-1 text-xs">AI suggest</span>
          </Button>
        </div>
        <div className="flex flex-wrap gap-2 mt-1.5">
          {(picklists?.root_causes || []).map((c) => (
            <button key={c} type="button" onClick={() => toggleCause(c)}
                    data-testid={`investigation-cause-${c}`}
                    className={`text-xs font-bold px-3 py-1.5 rounded-full ${
                      rootCauses.includes(c) ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                    }`}>
              {titleCase(c)}
            </button>
          ))}
        </div>
      </div>
      <div className="flex justify-end gap-2 pt-2">
        <Button variant="outline" onClick={() => save(false)} disabled={saving} data-testid="investigation-save">
          {saving ? <Loader2 className="animate-spin mr-2" size={14} /> : null}Save
        </Button>
        <Button onClick={() => save(true)} disabled={saving} className="bg-emerald-600 hover:bg-emerald-700 text-white"
                data-testid="investigation-complete">
          Save &amp; close investigation
        </Button>
      </div>
    </div>
  );
}


function ActionsPane({ incident, actions, onChanged }) {
  const { API } = useAuth();
  const token = useMemo(() => localStorage.getItem('token'), []);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ description: '', priority: 'medium', due_date: '' });

  const submit = async () => {
    if (!form.description.trim()) return notify.error('Action description required');
    setAdding(true);
    try {
      await axios.post(`${API}/incidents/${incident.id}/actions`, form,
        { headers: { Authorization: `Bearer ${token}` } });
      notify.success('Action added');
      setForm({ description: '', priority: 'medium', due_date: '' });
      onChanged();
    } catch (e) {
      notify.error(e.response?.data?.detail || 'Failed to add action');
    } finally { setAdding(false); }
  };

  const flip = async (action, status) => {
    try {
      await axios.patch(`${API}/incidents/${incident.id}/actions/${action.id}`,
        { status }, { headers: { Authorization: `Bearer ${token}` } });
      onChanged();
    } catch (e) { notify.error('Update failed'); }
  };

  const PRI_TONE = {
    low: 'bg-slate-100 text-slate-700',
    medium: 'bg-blue-50 text-blue-700',
    high: 'bg-amber-100 text-amber-800',
    critical: 'bg-red-100 text-red-800',
  };
  const ST_TONE = {
    open: 'bg-slate-100 text-slate-700',
    in_progress: 'bg-blue-100 text-blue-800',
    completed: 'bg-emerald-100 text-emerald-800',
    escalated: 'bg-red-100 text-red-800',
  };

  return (
    <div className="space-y-3 text-sm" data-testid="actions-pane">
      {actions?.length ? (
        <div className="space-y-2">
          {actions.map((a) => (
            <div key={a.id} className="rounded-lg border border-slate-200 p-3 bg-white" data-testid={`action-row-${a.id}`}>
              <div className="flex items-start gap-2">
                <div className="flex-1">
                  <p className="font-bold text-slate-800">{a.description}</p>
                  <div className="flex items-center gap-2 mt-1 flex-wrap">
                    <Badge className={`${PRI_TONE[a.priority] || ''} border-0 text-[10px] font-bold uppercase`}>{a.priority}</Badge>
                    <Badge className={`${ST_TONE[a.status] || ''} border-0 text-[10px] font-bold uppercase`}>{a.status?.replace(/_/g, ' ')}</Badge>
                    {a.due_date ? <span className="text-xs text-slate-500">Due {new Date(a.due_date).toLocaleDateString()}</span> : null}
                  </div>
                </div>
                {a.status !== 'completed' ? (
                  <Button size="sm" variant="outline" onClick={() => flip(a, 'completed')} data-testid={`action-complete-${a.id}`}>
                    Mark done
                  </Button>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-sm text-slate-500">No corrective actions yet.</p>
      )}

      <div className="rounded-xl border border-dashed border-slate-300 p-3 bg-slate-50 space-y-2">
        <Label className="text-xs font-bold uppercase tracking-wider">Add corrective action</Label>
        <Textarea rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })}
                  placeholder="What needs to change to stop this happening again?"
                  data-testid="action-form-description" />
        <div className="grid grid-cols-2 gap-2">
          <Select value={form.priority} onValueChange={(v) => setForm({ ...form, priority: v })}>
            <SelectTrigger data-testid="action-form-priority"><SelectValue /></SelectTrigger>
            <SelectContent>
              {['low', 'medium', 'high', 'critical'].map((p) => <SelectItem key={p} value={p}>{titleCase(p)}</SelectItem>)}
            </SelectContent>
          </Select>
          <Input type="date" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })}
                 data-testid="action-form-due" />
        </div>
        <div className="flex justify-end">
          <Button onClick={submit} disabled={adding} className="bg-blue-600 hover:bg-blue-700 text-white"
                  data-testid="action-form-submit">
            {adding ? <Loader2 className="animate-spin mr-2" size={14} /> : null}Add action
          </Button>
        </div>
      </div>
    </div>
  );
}


function AuditPane({ rows }) {
  if (!rows?.length) return <p className="text-sm text-slate-500">No audit entries yet.</p>;
  return (
    <div className="space-y-2" data-testid="audit-pane">
      {rows.map((r) => (
        <div key={r.id} className="rounded-lg border border-slate-200 p-3 bg-white text-xs">
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="font-mono uppercase">{r.action.replace(/_/g, ' ')}</Badge>
            <span className="text-slate-500">{new Date(r.at).toLocaleString()}</span>
          </div>
          <p className="text-slate-700 mt-1">
            <strong>{r.actor_name || 'system'}</strong>
            {r.actor_role ? ` · ${r.actor_role}` : ''}
            {r.notes ? ` — ${r.notes}` : ''}
          </p>
        </div>
      ))}
    </div>
  );
}



function HseDashboardStrip() {
  const { API } = useAuth();
  const token = useMemo(() => localStorage.getItem('token'), []);
  const [data, setData] = useState(null);
  const [heatmap, setHeatmap] = useState(null);
  const [hotlist, setHotlist] = useState(null);
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    setLoading(true);
    const hdrs = { headers: { Authorization: `Bearer ${token}` } };
    Promise.all([
      axios.get(`${API}/incidents/hse/dashboard?days=${days}`, hdrs),
      axios.get(`${API}/incidents/hse/heatmap?days=${days}`, hdrs),
      axios.get(`${API}/incidents/hse/repeat-detection?window_days=90&threshold=3`, hdrs)
        .catch(() => ({ data: { flagged: [], total_flagged: 0 } })),
    ])
      .then(([d, h, r]) => { setData(d.data); setHeatmap(h.data); setHotlist(r.data); })
      .catch(() => notify.error('Could not load HSE dashboard'))
      .finally(() => setLoading(false));
  }, [API, token, days]);
  if (loading) return (
    <Card className="p-4 bg-white border border-slate-200" data-testid="hse-dashboard">
      <Loader2 className="animate-spin inline mr-2" size={14} /> Loading…
    </Card>
  );
  if (!data) return null;
  const maxBy = (obj) => Math.max(1, ...Object.values(obj || {}));
  const SEV_BAR = {
    minor: '#94A3B8', moderate: '#F59E0B', serious: '#EA580C', major: '#DC2626', fatal: '#9F1239',
  };
  const renderBar = (k, v, max, color) => (
    <div key={k} className="flex items-center gap-2 text-xs">
      <span className="w-24 truncate text-slate-600 font-bold uppercase tracking-wider">{titleCase(k)}</span>
      <div className="flex-1 h-2.5 bg-slate-100 rounded-full overflow-hidden">
        <div className="h-full" style={{ width: `${(v / max) * 100}%`, background: color }} />
      </div>
      <span className="w-8 text-right font-mono text-slate-800">{v}</span>
    </div>
  );
  return (
    <Card className="p-5 bg-white border border-slate-200" data-testid="hse-dashboard">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="text-sm font-extrabold tracking-tight text-slate-800">HSE dashboard</h3>
          <p className="text-xs text-slate-500">
            {data.total} incidents in the last {data.period_days} days · {data.riddor_confirmed} confirmed RIDDOR · {data.fatalities || 0} fatalities
            {hotlist?.total_flagged ? <> · <strong className="text-red-700">{hotlist.total_flagged} asset(s) at repeat-incident threshold</strong></> : null}
          </p>
        </div>
        <div className="flex gap-1">
          {[7, 30, 90, 365].map((d) => (
            <button key={d} type="button"
                    onClick={() => setDays(d)}
                    className={`text-xs font-bold px-2.5 py-1 rounded-full ${days === d ? 'bg-blue-600 text-white shadow-sm' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
                    data-testid={`hse-period-${d}`}>
              {d}d
            </button>
          ))}
        </div>
      </div>

      {/* Trend sparkline */}
      <TrendSparkline points={data.by_day || []} />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-4">
        <div>
          <p className="text-[10px] uppercase tracking-wider font-bold text-slate-500 mb-2">By severity</p>
          <div className="space-y-1.5">
            {Object.entries(data.by_severity || {})
              .sort((a, b) => b[1] - a[1])
              .map(([k, v]) => renderBar(k, v, maxBy(data.by_severity), SEV_BAR[k] || '#64748B'))}
          </div>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-wider font-bold text-slate-500 mb-2">By kind</p>
          <div className="space-y-1.5">
            {Object.entries(data.by_kind || {})
              .sort((a, b) => b[1] - a[1])
              .map(([k, v]) => renderBar(k, v, maxBy(data.by_kind), '#2563EB'))}
          </div>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-wider font-bold text-slate-500 mb-2">By category</p>
          <div className="space-y-1.5">
            {Object.entries(data.by_category || {})
              .sort((a, b) => b[1] - a[1])
              .slice(0, 8)
              .map(([k, v]) => renderBar(k, v, maxBy(data.by_category), '#9D4CDD'))}
          </div>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-wider font-bold text-slate-500 mb-2">Top assets</p>
          {data.top_assets?.length ? (
            <div className="space-y-1.5">
              {data.top_assets.map((r) => (
                <div key={r.asset_id} className="flex items-center gap-2 text-xs">
                  <span className="w-24 truncate text-slate-600 font-bold uppercase tracking-wider">
                    {r.asset_name || r.asset_id}
                  </span>
                  <div className="flex-1 h-2.5 bg-slate-100 rounded-full overflow-hidden">
                    <div className="h-full"
                         style={{
                           width: `${(r.count / Math.max(1, ...data.top_assets.map((x) => x.count))) * 100}%`,
                           background: '#0EA5E9',
                         }} />
                  </div>
                  <span className="w-8 text-right font-mono text-slate-800">{r.count}</span>
                </div>
              ))}
            </div>
          ) : <p className="text-xs text-slate-400">No incidents linked to assets in this period.</p>}
        </div>
      </div>

      {/* Risk hot-list */}
      {hotlist?.flagged?.length ? (
        <div className="mt-5 rounded-xl border border-red-200 bg-red-50 p-4" data-testid="hse-risk-hotlist">
          <p className="text-[10px] uppercase tracking-wider font-bold text-red-700 mb-2">
            Risk hot-list · 3+ incidents in 90 days
          </p>
          <div className="space-y-1.5">
            {hotlist.flagged.slice(0, 8).map((row) => (
              <div key={row.asset_id} className="flex items-center gap-2 text-xs"
                   data-testid={`hotlist-row-${row.asset_id}`}>
                <span className="flex-1 font-bold text-slate-800 truncate">{row.asset_name}</span>
                <Badge className="bg-red-200 text-red-900 border-0 font-mono text-[10px]">
                  {row.count} · score {row.severity_score}
                </Badge>
                {row.capex_already_flagged ? (
                  <Badge className="bg-amber-200 text-amber-900 border-0 text-[10px]">CAPEX flagged</Badge>
                ) : (
                  <Badge className="bg-blue-200 text-blue-900 border-0 text-[10px]">CAPEX recommended</Badge>
                )}
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {/* Heatmap */}
      {heatmap?.total ? (
        <div className="mt-5" data-testid="hse-heatmap">
          <p className="text-[10px] uppercase tracking-wider font-bold text-slate-500 mb-2">
            When do incidents happen? · Day of week × hour
          </p>
          <Heatmap heatmap={heatmap} />
        </div>
      ) : null}
    </Card>
  );
}


function TrendSparkline({ points }) {
  if (!points?.length) return <p className="text-xs text-slate-400">No incidents in this period.</p>;
  const max = Math.max(1, ...points.map((p) => p.count));
  return (
    <div className="rounded-xl bg-slate-50 border border-slate-200 p-3" data-testid="hse-trend">
      <p className="text-[10px] uppercase tracking-wider font-bold text-slate-500 mb-2">Incidents per day</p>
      <div className="flex items-end gap-0.5 h-16">
        {points.map((p) => (
          <div key={p.date} className="flex-1 group relative">
            <div
              className="bg-gradient-to-t from-blue-600 to-purple-600 rounded-t"
              style={{ height: `${(p.count / max) * 100}%`, minHeight: p.count > 0 ? '2px' : '0' }}
              title={`${p.date}: ${p.count}`}
            />
          </div>
        ))}
      </div>
      <div className="flex justify-between text-[10px] text-slate-400 mt-1">
        <span>{points[0]?.date}</span>
        <span>{points[points.length - 1]?.date}</span>
      </div>
    </div>
  );
}


function Heatmap({ heatmap }) {
  const max = Math.max(1, ...heatmap.grid_counts.flat());
  const color = (v) => {
    if (!v) return '#F8FAFC';
    const t = Math.min(1, v / max);
    // navy → red gradient based on intensity
    const r = Math.round(29 + (220 - 29) * t);
    const g = Math.round(78 + (38 - 78) * t);
    const b = Math.round(216 + (38 - 216) * t);
    return `rgb(${r}, ${g}, ${b})`;
  };
  return (
    <div className="overflow-x-auto">
      <table className="text-[9px] border-separate" style={{ borderSpacing: '2px' }}>
        <thead>
          <tr>
            <th />
            {[...Array(24)].map((_, h) => (
              <th key={h} className="font-mono text-slate-400 w-5 text-center">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {heatmap.day_labels.map((label, dow) => (
            <tr key={label}>
              <td className="pr-1 font-bold uppercase tracking-wider text-slate-500">{label}</td>
              {heatmap.grid_counts[dow].map((v, h) => (
                <td key={h}
                    className="rounded-sm cursor-default"
                    title={`${label} ${h}:00 — ${v} incident(s)`}
                    style={{ width: 14, height: 14, background: color(v) }}>
                  &nbsp;
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}


function VoiceDictate({ onTranscript }) {
  const { API } = useAuth();
  const token = useMemo(() => localStorage.getItem('token'), []);
  const [state, setState] = useState('idle'); // idle | recording | uploading
  const mediaRef = useRef(null);
  const chunksRef = useRef([]);

  const start = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      mediaRef.current = rec;
      chunksRef.current = [];
      rec.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      rec.onstop = async () => {
        setState('uploading');
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
        const fd = new FormData();
        fd.append('file', blob, 'incident-dictation.webm');
        try {
          const r = await axios.post(`${API}/incidents/ai/transcribe`, fd, {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (r.data.transcript) {
            onTranscript(r.data.transcript);
            notify.success('Voice note transcribed');
          } else {
            notify.warning('Could not transcribe — please retype');
          }
        } catch (e) {
          notify.error(e.response?.data?.detail || 'Transcription failed');
        } finally {
          setState('idle');
        }
      };
      rec.start();
      setState('recording');
    } catch (e) {
      notify.error('Microphone permission denied or unavailable');
      setState('idle');
    }
  };

  const stop = () => {
    if (mediaRef.current && mediaRef.current.state === 'recording') {
      mediaRef.current.stop();
    }
  };

  return (
    <button
      type="button"
      onClick={state === 'idle' ? start : state === 'recording' ? stop : undefined}
      disabled={state === 'uploading'}
      className={`text-xs font-bold px-2 py-1 rounded-full inline-flex items-center gap-1 ${
        state === 'recording'
          ? 'bg-red-600 text-white animate-pulse'
          : state === 'uploading'
          ? 'bg-slate-300 text-slate-600'
          : 'bg-blue-50 text-blue-700 hover:bg-blue-100'
      }`}
      data-testid="incident-voice-dictate"
      title="Dictate the incident with your voice — saved as text via Whisper"
    >
      {state === 'recording' ? <Square size={12} /> : state === 'uploading' ? <Loader2 className="animate-spin" size={12} /> : <Mic size={12} />}
      {state === 'recording' ? 'Stop & transcribe' : state === 'uploading' ? 'Transcribing…' : 'Dictate'}
    </button>
  );
}

