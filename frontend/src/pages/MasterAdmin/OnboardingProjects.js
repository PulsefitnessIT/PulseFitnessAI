import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import {
  Rocket, Plus, Building2, AlertTriangle, CheckCircle2, Clock, Users2,
  ListChecks, X, Loader2, Sparkles, ChevronRight, Mail, Send,
} from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

const API = process.env.REACT_APP_BACKEND_URL + '/api';

const MODULES = [
  { id: 'operations', label: 'Operations' },
  { id: 'crm', label: 'CRM' },
  { id: 'memberships', label: 'Memberships' },
  { id: 'marketing', label: 'Marketing' },
];

const STATUS_META = {
  not_started:      { label: 'Not started', cls: 'bg-zinc-100 text-zinc-600' },
  in_progress:      { label: 'In progress', cls: 'bg-blue-100 text-blue-700' },
  waiting_customer: { label: 'Waiting customer', cls: 'bg-amber-100 text-amber-700' },
  waiting_admin:    { label: 'Waiting admin', cls: 'bg-amber-100 text-amber-700' },
  blocked:          { label: 'Blocked', cls: 'bg-red-100 text-red-700' },
  ready_for_review: { label: 'Ready for review', cls: 'bg-violet-100 text-violet-700' },
  complete:         { label: 'Complete', cls: 'bg-emerald-100 text-emerald-700' },
  archived:         { label: 'Archived', cls: 'bg-zinc-100 text-zinc-500' },
};
const STEP_STATUSES = ['not_started', 'in_progress', 'waiting_customer', 'waiting_admin', 'blocked', 'ready_for_review', 'complete'];

const PROFILE_FIELDS = [
  ['legal_name', 'Legal name'], ['trading_name', 'Trading name'], ['company_number', 'Company number'],
  ['vat_number', 'VAT / tax number'], ['country', 'Country'], ['primary_address', 'Primary address'],
  ['billing_address', 'Billing address'], ['timezone', 'Timezone'], ['currency', 'Default currency'],
  ['phone', 'Phone'], ['website', 'Website'], ['main_contact', 'Main contact'],
  ['billing_contact', 'Billing contact'], ['business_type', 'Business type'],
  ['num_sites', 'Number of sites'], ['num_users', 'Number of users'], ['num_members', 'Number of members'],
  ['num_assets', 'Number of assets'], ['notes', 'Notes'],
];

const ProgressBar = ({ pct }) => (
  <div className="h-2 w-full rounded-full bg-zinc-200 overflow-hidden" data-testid="onb-progress-bar">
    <div className="h-full rounded-full bg-[var(--color-brand-blue,#2563EB)] transition-all" style={{ width: `${pct}%` }} />
  </div>
);

const StatCard = ({ icon: Icon, label, value, tone = 'text-zinc-900', testId }) => (
  <Card className="p-4 flex items-center gap-3" data-testid={testId}>
    <div className="h-9 w-9 rounded-lg bg-zinc-100 flex items-center justify-center shrink-0">
      <Icon size={16} className="text-zinc-500" />
    </div>
    <div className="min-w-0">
      <div className={`text-xl font-bold leading-tight ${tone}`}>{value}</div>
      <div className="text-[11px] text-zinc-500 truncate">{label}</div>
    </div>
  </Card>
);

const OnboardingProjects = ({ types = [], onLaunchWizard }) => {
  const [dash, setDash] = useState(null);
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('all');
  const [showCreate, setShowCreate] = useState(false);
  const [active, setActive] = useState(null); // selected project for detail

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [d, p] = await Promise.all([
        axios.get(`${API}/onboarding/dashboard`),
        axios.get(`${API}/onboarding/projects`, { params: statusFilter !== 'all' ? { status: statusFilter } : {} }),
      ]);
      setDash(d.data);
      setProjects(p.data.projects || []);
    } catch (e) {
      notifyApiError(notify, e, 'Could not load onboarding');
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-6" data-testid="onboarding-projects">
      {/* Dashboard */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        <StatCard icon={Rocket} label="Onboarding now" value={dash?.onboarding_count ?? '—'} testId="onb-stat-active" />
        <StatCard icon={CheckCircle2} label="Completed" value={dash?.completed_count ?? '—'} tone="text-emerald-600" testId="onb-stat-complete" />
        <StatCard icon={AlertTriangle} label="Blocked" value={dash?.blocked_count ?? '—'} tone="text-red-600" testId="onb-stat-blocked" />
        <StatCard icon={Clock} label="Avg completion" value={dash ? `${dash.avg_completion}%` : '—'} testId="onb-stat-avg" />
        <StatCard icon={Users2} label="Go-lives due" value={dash?.go_lives_due ?? '—'} testId="onb-stat-golive" />
      </div>

      {dash?.common_missing?.length > 0 && (
        <Card className="p-4" data-testid="onb-common-missing">
          <p className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold mb-2">Most common missing data</p>
          <div className="flex flex-wrap gap-2">
            {dash.common_missing.map((m) => (
              <span key={m.label} className="text-xs px-2.5 py-1 rounded-full bg-amber-50 text-amber-800 border border-amber-200">
                {m.label} · {m.count}
              </span>
            ))}
          </div>
        </Card>
      )}

      {/* Projects list */}
      <div>
        <div className="flex items-center justify-between gap-3 mb-3">
          <h3 className="text-base font-semibold text-zinc-900">Onboarding projects</h3>
          <div className="flex items-center gap-2">
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-44 h-9" data-testid="onb-status-filter"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                <SelectItem value="in_progress">In progress</SelectItem>
                <SelectItem value="complete">Complete</SelectItem>
                <SelectItem value="archived">Archived</SelectItem>
              </SelectContent>
            </Select>
            <Button onClick={() => setShowCreate(true)} data-testid="onb-new-project-btn" className="h-9">
              <Plus size={15} className="mr-1.5" /> New project
            </Button>
          </div>
        </div>

        {loading ? (
          <div className="py-12 flex justify-center text-zinc-400"><Loader2 className="animate-spin" /></div>
        ) : projects.length === 0 ? (
          <Card className="p-10 text-center" data-testid="onb-empty">
            <Rocket size={28} className="mx-auto text-zinc-300 mb-3" />
            <p className="text-sm text-zinc-600">No onboarding projects yet. Create one to start tracking a customer setup.</p>
          </Card>
        ) : (
          <div className="space-y-2">
            {projects.map((p) => {
              const sm = STATUS_META[p.status] || STATUS_META.in_progress;
              const tLabel = (types.find((t) => t.id === p.customer_type) || {}).label || p.customer_type;
              return (
                <Card
                  key={p.id}
                  className="p-4 hover:border-zinc-300 cursor-pointer transition-colors"
                  onClick={() => setActive(p)}
                  data-testid={`onb-project-${p.id}`}
                >
                  <div className="flex items-center gap-4">
                    <div className="h-10 w-10 rounded-lg bg-blue-50 flex items-center justify-center shrink-0">
                      <Building2 size={18} className="text-blue-600" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-semibold text-zinc-900 truncate">{p.customer_name}</span>
                        <span className={`text-[10px] px-2 py-0.5 rounded-full ${sm.cls}`}>{sm.label}</span>
                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-zinc-100 text-zinc-600">{tLabel}</span>
                      </div>
                      <div className="mt-2 flex items-center gap-3">
                        <div className="flex-1 max-w-xs"><ProgressBar pct={p.progress?.percent || 0} /></div>
                        <span className="text-xs text-zinc-500 tabular-nums">{p.progress?.percent || 0}%</span>
                        {p.progress?.missing?.length > 0 && (
                          <span className="text-[11px] text-amber-700">{p.progress.missing.length} missing</span>
                        )}
                      </div>
                    </div>
                    <ChevronRight size={16} className="text-zinc-300 shrink-0" />
                  </div>
                </Card>
              );
            })}
          </div>
        )}
      </div>

      {showCreate && (
        <CreateDialog
          open={showCreate}
          types={types}
          onClose={() => setShowCreate(false)}
          onCreated={(proj) => { setShowCreate(false); load(); setActive(proj); }}
        />
      )}

      {active && (
        <ProjectDetail
          project={active}
          types={types}
          onClose={() => setActive(null)}
          onChanged={(updated) => { setActive(updated); load(); }}
          onLaunchWizard={onLaunchWizard}
        />
      )}
    </div>
  );
};

// ── Create dialog ────────────────────────────────────────────────────────
const CreateDialog = ({ open, types, onClose, onCreated }) => {
  const [name, setName] = useState('');
  const [type, setType] = useState('single_site');
  const [modules, setModules] = useState(['operations']);
  const [owner, setOwner] = useState('');
  const [goLive, setGoLive] = useState('');
  const [busy, setBusy] = useState(false);

  const toggleMod = (id) => setModules((m) => (m.includes(id) ? m.filter((x) => x !== id) : [...m, id]));

  const submit = async () => {
    if (!name.trim()) { notify.error('Name required', 'Enter the customer name.'); return; }
    setBusy(true);
    try {
      const { data } = await axios.post(`${API}/onboarding/projects`, {
        customer_name: name.trim(), customer_type: type, modules,
        owner: owner || null, go_live_target: goLive || null,
      });
      notify.success('Project created', `${name} onboarding started.`);
      onCreated(data);
    } catch (e) {
      notifyApiError(notify, e, 'Could not create project');
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg" data-testid="onb-create-dialog">
        <DialogHeader><DialogTitle>New onboarding project</DialogTitle></DialogHeader>
        <div className="space-y-4 pt-1">
          <div>
            <Label className="text-xs">Customer name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Acme Gyms Ltd" data-testid="onb-create-name" />
          </div>
          <div>
            <Label className="text-xs">Customer type</Label>
            <Select value={type} onValueChange={setType}>
              <SelectTrigger data-testid="onb-create-type"><SelectValue /></SelectTrigger>
              <SelectContent>
                {types.map((t) => <SelectItem key={t.id} value={t.id}>{t.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs">Modules</Label>
            <div className="flex flex-wrap gap-2 mt-1">
              {MODULES.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => toggleMod(m.id)}
                  data-testid={`onb-create-mod-${m.id}`}
                  className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
                    modules.includes(m.id) ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-zinc-600 border-zinc-300'
                  }`}
                >{m.label}</button>
              ))}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs">Onboarding owner</Label>
              <Input value={owner} onChange={(e) => setOwner(e.target.value)} placeholder="owner@…" data-testid="onb-create-owner" />
            </div>
            <div>
              <Label className="text-xs">Go-live target</Label>
              <Input type="date" value={goLive} onChange={(e) => setGoLive(e.target.value)} data-testid="onb-create-golive" />
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="outline" onClick={onClose}>Cancel</Button>
            <Button onClick={submit} disabled={busy} data-testid="onb-create-submit">
              {busy ? <Loader2 size={15} className="mr-1.5 animate-spin" /> : <Rocket size={15} className="mr-1.5" />} Create
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

// ── Detail sheet ───────────────────────────────────────────────────────────
const ProjectDetail = ({ project, types, onClose, onChanged, onLaunchWizard }) => {
  const [tab, setTab] = useState('checklist');
  const [profile, setProfile] = useState(project.profile || {});
  const [savingProfile, setSavingProfile] = useState(false);
  const [goingLive, setGoingLive] = useState(false);
  const [readiness, setReadiness] = useState(null);
  const [syncing, setSyncing] = useState(false);
  const [aiSummary, setAiSummary] = useState(null);
  const [aiBusy, setAiBusy] = useState(false);
  const p = project;
  const tLabel = (types.find((t) => t.id === p.customer_type) || {}).label || p.customer_type;

  useEffect(() => {
    axios.get(`${API}/onboarding/projects/${p.id}/readiness`).then((r) => setReadiness(r.data)).catch(() => {});
  }, [p.id]);

  const syncReadiness = async () => {
    setSyncing(true);
    try {
      const { data } = await axios.post(`${API}/onboarding/projects/${p.id}/readiness/sync`);
      setReadiness(data.readiness);
      notify.success('Synced from live data', data.advanced.length ? `${data.advanced.length} step(s) auto-completed.` : 'Checklist already up to date.');
      onChanged(data.project);
    } catch (e) { notifyApiError(notify, e, 'Could not sync readiness'); }
    finally { setSyncing(false); }
  };

  const groups = (p.checklist || []).reduce((acc, s) => { (acc[s.group] = acc[s.group] || []).push(s); return acc; }, {});

  const runAiSummary = async () => {
    setAiBusy(true);
    try {
      const { data } = await axios.post(`${API}/onboarding/projects/${p.id}/ai-summary`);
      setAiSummary(data);
    } catch (e) { notifyApiError(notify, e, 'AI summary failed'); }
    finally { setAiBusy(false); }
  };

  const setStep = async (step, status) => {
    try {
      const { data } = await axios.patch(`${API}/onboarding/projects/${p.id}/checklist/${step.id}`, { status });
      onChanged(data);
    } catch (e) { notifyApiError(notify, e, 'Could not update step'); }
  };

  const saveProfile = async () => {
    setSavingProfile(true);
    try {
      const { data } = await axios.patch(`${API}/onboarding/projects/${p.id}`, { profile });
      notify.success('Profile saved');
      onChanged(data);
    } catch (e) { notifyApiError(notify, e, 'Could not save profile'); }
    finally { setSavingProfile(false); }
  };

  const goLive = async () => {
    setGoingLive(true);
    try {
      const { data } = await axios.post(`${API}/onboarding/projects/${p.id}/go-live`);
      notify.success('Go-live approved', `${p.customer_name} is live.`);
      onChanged(data);
    } catch (e) { notifyApiError(notify, e, 'Cannot go live yet'); }
    finally { setGoingLive(false); }
  };

  return (
    <Sheet open onOpenChange={(o) => !o && onClose()}>
      <SheetContent side="right" className="w-full sm:max-w-2xl overflow-y-auto" data-testid="onb-detail">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            {p.customer_name}
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-zinc-100 text-zinc-600 font-normal">{tLabel}</span>
          </SheetTitle>
        </SheetHeader>

        <div className="mt-3 flex items-center gap-3">
          <div className="flex-1"><ProgressBar pct={p.progress?.percent || 0} /></div>
          <span className="text-sm font-semibold tabular-nums">{p.progress?.percent || 0}%</span>
        </div>

        <div className="flex gap-1 mt-5 border-b border-zinc-200">
          {[['checklist', 'Checklist'], ['readiness', 'Module readiness'], ['profile', 'Business profile'], ['emails', 'Emails'], ['golive', 'Go-live']].map(([id, label]) => (
            <button
              key={id} onClick={() => setTab(id)}
              data-testid={`onb-detail-tab-${id}`}
              className={`px-3 py-2 text-sm font-medium border-b-2 transition-colors ${
                tab === id ? 'border-blue-600 text-blue-600' : 'border-transparent text-zinc-500 hover:text-zinc-800'
              }`}
            >{label}</button>
          ))}
        </div>

        {tab === 'checklist' && (
          <div className="mt-4 space-y-5" data-testid="onb-checklist">
            <div className="flex items-center justify-between">
              <span className="text-xs text-zinc-500">{p.progress?.required_complete}/{p.progress?.required_total} required steps complete</span>
              <Button size="sm" variant="outline" onClick={runAiSummary} disabled={aiBusy} data-testid="onb-ai-summary-btn"
                      className="border-violet-300 text-violet-700 hover:bg-violet-50">
                {aiBusy ? <Loader2 size={13} className="mr-1.5 animate-spin" /> : <Sparkles size={13} className="mr-1.5" />} AI summary
              </Button>
            </div>
            {aiSummary && (
              <div className="rounded-lg border border-violet-200 bg-violet-50 p-3 text-xs space-y-2" data-testid="onb-ai-summary">
                <p className="text-violet-900">{aiSummary.summary}</p>
                {(aiSummary.next_best_actions || []).length > 0 && (
                  <div>
                    <p className="font-medium text-violet-800">Next best actions</p>
                    {aiSummary.next_best_actions.map((a, i) => <p key={i} className="text-violet-700">→ {a}</p>)}
                  </div>
                )}
                {(aiSummary.risks || []).length > 0 && (
                  <div>
                    <p className="font-medium text-amber-800">Risks</p>
                    {aiSummary.risks.map((r, i) => <p key={i} className="text-amber-700">• {r}</p>)}
                  </div>
                )}
                <p className="text-[10px] text-violet-500">AI-generated · advisory only</p>
              </div>
            )}
            {Object.entries(groups).map(([grp, steps]) => (
              <div key={grp}>
                <p className="text-[10px] uppercase tracking-wider text-zinc-400 font-semibold mb-2">{grp}</p>
                <div className="space-y-1.5">
                  {steps.map((s) => (
                    <div key={s.id} className="flex items-center gap-2 p-2 rounded-lg border border-zinc-100" data-testid={`onb-step-${s.key}`}>
                      <ListChecks size={14} className={s.status === 'complete' ? 'text-emerald-500' : 'text-zinc-300'} />
                      <span className="flex-1 text-sm text-zinc-700">
                        {s.label}{s.optional && <span className="text-[10px] text-zinc-400 ml-1">(optional)</span>}
                      </span>
                      {onLaunchWizard && ['sites', 'primary_site', 'site_hierarchy', 'assets', 'contacts', 'members', 'primary_users'].includes(s.key) && (
                        <Button size="sm" variant="ghost" className="h-7 text-[11px]" onClick={() => onLaunchWizard(s.key)} data-testid={`onb-step-launch-${s.key}`}>
                          Open <ChevronRight size={12} />
                        </Button>
                      )}
                      <Select value={s.status} onValueChange={(v) => setStep(s, v)}>
                        <SelectTrigger className="w-40 h-8 text-xs" data-testid={`onb-step-status-${s.key}`}><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {STEP_STATUSES.map((st) => <SelectItem key={st} value={st}>{STATUS_META[st].label}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        {tab === 'readiness' && (
          <div className="mt-4 space-y-4" data-testid="onb-readiness">
            {!p.organization_id ? (
              <Card className="p-5 text-sm text-amber-700 bg-amber-50 border-amber-200">
                Link this project to an organisation to compute live module readiness.
              </Card>
            ) : (
              <>
                <div className="flex items-center justify-between">
                  <p className="text-xs text-zinc-500">
                    {readiness ? `${readiness.ready_count}/${readiness.total_areas} modules ready` : 'Checking live data…'}
                  </p>
                  <Button size="sm" variant="outline" onClick={syncReadiness} disabled={syncing} data-testid="onb-readiness-sync">
                    {syncing ? <Loader2 size={14} className="mr-1.5 animate-spin" /> : <Sparkles size={14} className="mr-1.5" />} Sync checklist from live data
                  </Button>
                </div>
                {(readiness?.areas || []).map((a) => (
                  <Card key={a.area} className="p-4" data-testid={`onb-readiness-${a.area}`}>
                    <div className="flex items-center gap-2 mb-2">
                      <span className={`h-2.5 w-2.5 rounded-full ${a.ready ? 'bg-emerald-500' : 'bg-amber-400'}`} />
                      <span className="font-semibold text-sm text-zinc-800">{a.label}</span>
                      <span className={`text-[10px] px-2 py-0.5 rounded-full ${a.ready ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}`}>
                        {a.ready ? 'Ready' : 'Not ready'}
                      </span>
                    </div>
                    <div className="space-y-1">
                      {a.checks.map((c) => (
                        <div key={c.key} className="flex items-center gap-2 text-sm" data-testid={`onb-check-${a.area}-${c.key}`}>
                          {c.ok ? <CheckCircle2 size={14} className="text-emerald-500" /> : <AlertTriangle size={14} className="text-amber-400" />}
                          <span className="flex-1 text-zinc-700">{c.label}{!c.required && <span className="text-[10px] text-zinc-400 ml-1">(optional)</span>}</span>
                          <span className="text-xs text-zinc-500 tabular-nums">{c.count}</span>
                        </div>
                      ))}
                    </div>
                  </Card>
                ))}
                {readiness && readiness.areas.length === 0 && (
                  <p className="text-sm text-zinc-500">No module readiness areas apply to this customer type / module selection.</p>
                )}
              </>
            )}
          </div>
        )}

        {tab === 'profile' && (
          <div className="mt-4 space-y-3" data-testid="onb-profile">
            <div className="grid grid-cols-2 gap-3">
              {PROFILE_FIELDS.map(([key, label]) => (
                key === 'notes' ? null : (
                  <div key={key}>
                    <Label className="text-xs">{label}</Label>
                    <Input
                      value={profile[key] || ''}
                      onChange={(e) => setProfile((pr) => ({ ...pr, [key]: e.target.value }))}
                      data-testid={`onb-profile-${key}`}
                    />
                  </div>
                )
              ))}
            </div>
            <div>
              <Label className="text-xs">Notes</Label>
              <Textarea value={profile.notes || ''} onChange={(e) => setProfile((pr) => ({ ...pr, notes: e.target.value }))} data-testid="onb-profile-notes" />
            </div>
            <Button onClick={saveProfile} disabled={savingProfile} data-testid="onb-profile-save">
              {savingProfile ? <Loader2 size={15} className="mr-1.5 animate-spin" /> : null} Save profile
            </Button>
          </div>
        )}

        {tab === 'emails' && <EmailsTab project={p} />}

        {tab === 'golive' && (
          <div className="mt-4 space-y-4" data-testid="onb-golive">
            {p.go_live?.approved ? (
              <Card className="p-5 bg-emerald-50 border-emerald-200">
                <div className="flex items-center gap-2 text-emerald-700 font-semibold"><CheckCircle2 size={18} /> Live</div>
                <p className="text-sm text-emerald-800 mt-1">Approved by {p.go_live.approved_by} on {new Date(p.go_live.approved_at).toLocaleString()}.</p>
                <p className="text-xs text-emerald-700 mt-2">{p.go_live.summary?.completed_steps?.length || 0} steps completed across {(p.go_live.summary?.modules || []).join(', ') || 'no modules'}.</p>
              </Card>
            ) : (
              <>
                <Card className="p-4">
                  <p className="text-sm font-semibold text-zinc-800 mb-2">Go-live readiness</p>
                  {p.progress?.missing?.length ? (
                    <div className="space-y-1.5">
                      <p className="text-xs text-amber-700">{p.progress.missing.length} required step(s) outstanding:</p>
                      {p.progress.missing.map((m) => (
                        <div key={m} className="flex items-center gap-2 text-xs text-zinc-600"><AlertTriangle size={12} className="text-amber-500" /> {m}</div>
                      ))}
                    </div>
                  ) : (
                    <div className="flex items-center gap-2 text-emerald-600 text-sm"><CheckCircle2 size={16} /> All required steps complete — ready to go live.</div>
                  )}
                </Card>
                <Button
                  onClick={goLive}
                  disabled={goingLive || (p.progress?.missing?.length > 0)}
                  className="bg-emerald-600 hover:bg-emerald-700"
                  data-testid="onb-golive-approve"
                >
                  {goingLive ? <Loader2 size={15} className="mr-1.5 animate-spin" /> : <Sparkles size={15} className="mr-1.5" />} Approve go-live
                </Button>
              </>
            )}
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
};

// ── Emails tab ─────────────────────────────────────────────────────────────
const EmailsTab = ({ project }) => {
  const [templates, setTemplates] = useState([]);
  const [selected, setSelected] = useState('');
  const [preview, setPreview] = useState(null);
  const [to, setTo] = useState(project.profile?.main_contact || '');
  const [rendering, setRendering] = useState(false);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    axios.get(`${API}/onboarding/email-templates`).then((r) => setTemplates(r.data.templates || [])).catch(() => {});
  }, []);

  const pick = async (id) => {
    setSelected(id);
    setPreview(null);
    if (!id) return;
    setRendering(true);
    try {
      const { data } = await axios.post(`${API}/onboarding/email-templates/render`, { template_id: id, project_id: project.id });
      setPreview(data);
    } catch (e) { notifyApiError(notify, e, 'Could not render template'); }
    finally { setRendering(false); }
  };

  const send = async () => {
    if (!to.trim() || !to.includes('@')) { notify.error('Recipient required', 'Enter a valid email address.'); return; }
    setSending(true);
    try {
      await axios.post(`${API}/onboarding/email-templates/send`, { template_id: selected, project_id: project.id, to: to.trim() });
      notify.success('Email sent', `Sent to ${to.trim()}.`);
    } catch (e) { notifyApiError(notify, e, 'Could not send email'); }
    finally { setSending(false); }
  };

  return (
    <div className="mt-4 space-y-4" data-testid="onb-emails">
      <div>
        <Label className="text-xs">Onboarding email</Label>
        <Select value={selected} onValueChange={pick}>
          <SelectTrigger data-testid="onb-email-template"><SelectValue placeholder="Choose a template…" /></SelectTrigger>
          <SelectContent>
            {templates.map((t) => <SelectItem key={t.id} value={t.id}>{t.label}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      {rendering && <div className="py-6 flex justify-center text-zinc-400"><Loader2 className="animate-spin" /></div>}

      {preview && !rendering && (
        <Card className="p-4 space-y-3" data-testid="onb-email-preview">
          <div>
            <p className="text-[10px] uppercase tracking-wider text-zinc-400 font-semibold">Subject</p>
            <p className="text-sm font-medium text-zinc-900">{preview.subject}</p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wider text-zinc-400 font-semibold mb-1">Body</p>
            <pre className="text-xs text-zinc-700 whitespace-pre-wrap font-sans bg-zinc-50 rounded-lg p-3 border border-zinc-100">{preview.body}</pre>
          </div>
          <div className="flex flex-col sm:flex-row gap-2 sm:items-end pt-1">
            <div className="flex-1">
              <Label className="text-xs">Send to</Label>
              <Input value={to} onChange={(e) => setTo(e.target.value)} placeholder="contact@customer.com" data-testid="onb-email-to" />
            </div>
            <Button onClick={send} disabled={sending} data-testid="onb-email-send">
              {sending ? <Loader2 size={15} className="mr-1.5 animate-spin" /> : <Send size={15} className="mr-1.5" />} Send
            </Button>
          </div>
          <p className="text-[10px] text-zinc-400 flex items-center gap-1"><Mail size={11} /> Sent via Resend with Pulse Fitness branding. Recorded in the project audit trail.</p>
        </Card>
      )}

      {!selected && (
        <Card className="p-8 text-center" data-testid="onb-emails-empty">
          <Mail size={24} className="mx-auto text-zinc-300 mb-2" />
          <p className="text-sm text-zinc-500">Pick a template to preview a personalised onboarding email for {project.customer_name}.</p>
        </Card>
      )}
    </div>
  );
};

export default OnboardingProjects;