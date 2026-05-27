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
import { useCallback, useEffect, useMemo, useState } from 'react';
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
  ClipboardCheck, Wrench, FileWarning, Search,
} from 'lucide-react';

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
  const [filters, setFilters] = useState({ kind: '', severity: '', riddor: '', q: '' });
  const [showQuickLog, setShowQuickLog] = useState(false);
  const [activeIncidentId, setActiveIncidentId] = useState(null);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filters.kind) params.set('kind', filters.kind);
      if (filters.severity) params.set('severity', filters.severity);
      if (filters.riddor) params.set('riddor', filters.riddor);
      if (filters.q) params.set('q', filters.q);
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
          ? 'bg-slate-900 text-white'
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
  const [form, setForm] = useState({
    kind: 'accident', severity: 'minor', category: 'other', description: '',
    location_area: '', first_aid_given: false, hospital_treatment: false,
  });
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    if ((form.description || '').trim().length < 10) {
      notify.error('Describe the incident in at least 10 characters');
      return;
    }
    setSaving(true);
    try {
      const res = await axios.post(`${API}/incidents`, form, {
        headers: { Authorization: `Bearer ${token}` },
      });
      notify.success(`Incident ${res.data.reference} logged`);
      onCreated(res.data);
      setForm({ kind: 'accident', severity: 'minor', category: 'other', description: '',
        location_area: '', first_aid_given: false, hospital_treatment: false });
    } catch (e) {
      notify.error(e.response?.data?.detail || 'Failed to log incident');
    } finally {
      setSaving(false);
    }
  };

  if (!picklists) return null;
  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto" data-testid="incident-quick-log-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Plus size={16} /> Log incident</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
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
            <Label className="text-xs font-bold uppercase tracking-wider">Description</Label>
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
            {tab === 'overview' && <OverviewPane incident={incident} />}
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


function OverviewPane({ incident }) {
  const sev = SEVERITY_TONE[incident.severity] || SEVERITY_TONE.minor;
  const rid = RIDDOR_TONE[(incident.riddor || {}).status || 'not_assessed'];
  return (
    <div className="space-y-4 text-sm">
      <div className="flex flex-wrap gap-2">
        <Badge className={`${sev.bg} ${sev.text} border-0 font-bold uppercase`}>{incident.severity}</Badge>
        <Badge className={`${rid.bg} ${rid.text} border-0 font-bold uppercase`}>{rid.label}</Badge>
        <Badge variant="outline" className="font-bold uppercase">{incident.status?.replace(/_/g, ' ')}</Badge>
        {incident.fatality ? <Badge className="bg-rose-200 text-rose-900 border-0 font-bold uppercase">Fatality</Badge> : null}
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
            {incident.witnesses.map((w, i) => <li key={i}>{w.name}{w.role ? ` · ${w.role}` : ''}</li>)}
          </ul>
        </div>
      ) : null}
    </div>
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
        <Button onClick={runAssess} disabled={running} className="bg-blue-600 hover:bg-blue-700 text-white"
                data-testid="riddor-run-assess">
          {running ? <Loader2 className="animate-spin mr-2" size={14} /> : null}
          Run RIDDOR assessment
        </Button>
      </div>

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

  return (
    <div className="space-y-3 text-sm" data-testid="investigation-pane">
      <div>
        <Label className="text-xs font-bold uppercase tracking-wider">Investigator findings</Label>
        <Textarea rows={5} value={findings} onChange={(e) => setFindings(e.target.value)}
                  placeholder="What did the investigation reveal? Witness statements, equipment checks, environmental factors…"
                  data-testid="investigation-findings" />
      </div>
      <div>
        <Label className="text-xs font-bold uppercase tracking-wider">Root cause(s)</Label>
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
