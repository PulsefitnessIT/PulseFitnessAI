/**
 * StaffOnboarding — HR console for the Staff Onboarding, Offer & Contract wizard.
 * Mounted at Operations → Staffing → People → Staff Onboarding.
 * Single person record (staff_members) progresses candidate→…→employee.
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import {
  UserPlus, Loader2, X, FileText, FileSignature, CheckCircle2, ShieldCheck,
  ClipboardList, ScrollText, ArrowRight, AlertTriangle, History,
} from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const surface = { background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' };
const STATUS_LABELS = {
  not_started: 'Not Started', in_progress: 'In Progress', awaiting_hr_review: 'Awaiting HR Review',
  awaiting_offer: 'Awaiting Offer', offer_issued: 'Offer Issued', offer_accepted: 'Offer Accepted',
  offer_declined: 'Offer Declined', contract_issued: 'Contract Issued',
  awaiting_employer_signature: 'Awaiting Employer Signature', ready_to_activate: 'Ready to Activate',
  complete: 'Complete',
};

function Pill({ children, tone = 'slate' }) {
  const tones = {
    slate: 'bg-slate-500/15 text-slate-300', blue: 'bg-cyan-500/15 text-cyan-300',
    green: 'bg-emerald-500/15 text-emerald-300', amber: 'bg-amber-500/15 text-amber-300',
    red: 'bg-red-500/15 text-red-300',
  };
  return <span className={`px-2 py-0.5 rounded-full text-[11px] font-semibold ${tones[tone]}`}>{children}</span>;
}

export default function StaffOnboarding({ headers }) {
  const [cards, setCards] = useState({});
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showWizard, setShowWizard] = useState(false);
  const [openCase, setOpenCase] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [d, c] = await Promise.all([
        axios.get(`${API}/staff-onboarding/dashboard`, { headers }),
        axios.get(`${API}/staff-onboarding/cases`, { headers }),
      ]);
      setCards(d.data.cards || {});
      setCases(c.data.cases || []);
    } catch (e) { /* noop */ } finally { setLoading(false); }
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  const CARD_DEFS = [
    ['paperwork_awaiting_review', 'Awaiting review', 'amber'],
    ['ready_for_offer', 'Ready for offer', 'blue'],
    ['offers_issued', 'Offers issued', 'blue'],
    ['offers_accepted', 'Offers accepted', 'green'],
    ['contracts_awaiting_signature', 'Contracts to sign', 'amber'],
    ['contracts_fully_signed', 'Fully signed', 'green'],
    ['ready_to_activate', 'Ready to activate', 'green'],
    ['total_cases', 'Total cases', 'slate'],
  ];

  return (
    <div className="space-y-5" data-testid="staff-onboarding-console">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-xl font-bold" style={{ color: 'var(--theme-text)' }}>Staff Onboarding</h2>
          <p className="text-sm opacity-70" style={{ color: 'var(--theme-text)' }}>
            Paperless recruitment-to-employment — one person record, offer letter, contract & e-signature.
          </p>
        </div>
        <button onClick={() => setShowWizard(true)} data-testid="new-onboarding-case-btn"
          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl font-semibold text-slate-900"
          style={{ background: 'var(--color-brand-cyan, #19CDFF)' }}>
          <UserPlus size={16} /> Create Onboarding Case
        </button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {CARD_DEFS.map(([k, label, tone]) => (
          <div key={k} className="rounded-2xl p-4 border" style={surface} data-testid={`card-${k}`}>
            <div className="text-3xl font-bold" style={{ color: 'var(--theme-text)' }}>{cards[k] ?? 0}</div>
            <div className="mt-1"><Pill tone={tone}>{label}</Pill></div>
          </div>
        ))}
      </div>

      <div className="rounded-2xl border overflow-hidden" style={surface}>
        <div className="px-4 py-3 border-b flex items-center gap-2" style={{ borderColor: 'var(--theme-border)' }}>
          <ClipboardList size={16} style={{ color: 'var(--theme-text)' }} />
          <span className="font-semibold" style={{ color: 'var(--theme-text)' }}>Onboarding Cases</span>
        </div>
        {loading ? (
          <div className="p-8 flex justify-center"><Loader2 className="animate-spin" style={{ color: 'var(--theme-text)' }} /></div>
        ) : cases.length === 0 ? (
          <div className="p-8 text-center opacity-70 text-sm" style={{ color: 'var(--theme-text)' }}>
            No onboarding cases yet. Create one to invite a new recruit.
          </div>
        ) : (
          <div className="divide-y" style={{ borderColor: 'var(--theme-border)' }}>
            {cases.map((c) => (
              <button key={c.id} onClick={() => setOpenCase(c.id)} data-testid={`case-row-${c.id}`}
                className="w-full text-left px-4 py-3 hover:bg-white/[0.03] transition-colors flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-semibold truncate" style={{ color: 'var(--theme-text)' }}>
                    {c.person?.full_name || 'New recruit'}
                  </div>
                  <div className="text-xs opacity-60 truncate" style={{ color: 'var(--theme-text)' }}>
                    {c.employment_proposal?.job_title || c.employment_proposal?.position || '—'} · {c.package || 'no package'}
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <Pill tone={c.status === 'complete' ? 'green' : c.status?.includes('offer') ? 'blue' : 'amber'}>
                    {STATUS_LABELS[c.status] || c.status}
                  </Pill>
                  <ArrowRight size={16} style={{ color: 'var(--theme-text)' }} />
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {showWizard && <CaseWizard headers={headers} onClose={() => setShowWizard(false)}
        onCreated={(id) => { setShowWizard(false); load(); setOpenCase(id); }} />}
      {openCase && <CaseDetail headers={headers} caseId={openCase}
        onClose={() => { setOpenCase(null); load(); }} />}
    </div>
  );
}

function WizardField({ label, k, on, val, type = 'text' }) {
  return (
    <label className="block">
      <span className="text-xs opacity-70" style={{ color: 'var(--theme-text)' }}>{label}</span>
      <input type={type} value={val} onChange={on} data-testid={`wizard-${k}`}
        className="mt-1 w-full rounded-lg px-3 py-2 text-sm border bg-transparent"
        style={{ color: 'var(--theme-text)', borderColor: 'var(--theme-border)' }} />
    </label>
  );
}

/* ───────────────── Create Onboarding Case Wizard ───────────────── */
function CaseWizard({ headers, onClose, onCreated }) {
  const [step, setStep] = useState(1);
  const [f, setF] = useState({ legal_first_name: '', surname: '', preferred_name: '', personal_email: '', mobile: '', position: '', proposed_start_date: '' });
  const [prop, setProp] = useState({ employing_company: 'Pulse Fitness', job_title: '', department: '', site: '', line_manager: '', salary: '', hours_per_week: '', employment_type: 'Permanent full time', probation_period: '', notice_period: '', holiday_entitlement: '', authorised_signatory: '' });
  const [pkg, setPkg] = useState('standard');
  const [packages, setPackages] = useState([]);
  const [dup, setDup] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const set = (k) => (e) => setF((p) => ({ ...p, [k]: e.target.value }));
  const setP = (k) => (e) => setProp((p) => ({ ...p, [k]: e.target.value }));

  useEffect(() => {
    axios.get(`${API}/staff-onboarding/packages`, { headers }).then(r => setPackages(r.data.packages || [])).catch(() => {});
  }, [headers]);

  const checkDup = async () => {
    if (!f.personal_email && !f.mobile) { setStep(2); return; }
    setBusy(true);
    try {
      const r = await axios.post(`${API}/staff-onboarding/cases/duplicate-check`,
        { personal_email: f.personal_email, mobile: f.mobile, legal_name: `${f.legal_first_name} ${f.surname}`.trim() }, { headers });
      setDup(r.data);
      setStep(2);
    } catch (e) { setStep(2); } finally { setBusy(false); }
  };

  const create = async () => {
    setBusy(true); setErr('');
    try {
      const c = await axios.post(`${API}/staff-onboarding/cases`, { ...f }, { headers });
      const id = c.data.id;
      await axios.patch(`${API}/staff-onboarding/cases/${id}`, { package: pkg, employment_proposal: { ...prop, proposed_start_date: f.proposed_start_date, preferred_name: f.preferred_name } }, { headers });
      onCreated(id);
    } catch (e) {
      setErr(e?.response?.data?.detail?.message || e?.response?.data?.detail || 'Could not create case');
      setBusy(false);
    }
  };

  const Field = WizardField;

  return (
    <Modal onClose={onClose} title="Create Onboarding Case" testId="case-wizard">
      <div className="flex gap-2 mb-4 text-xs">
        {['Select Recruit', 'Employment Proposal', 'Package'].map((s, i) => (
          <div key={s} className={`px-2 py-1 rounded-full ${step === i + 1 ? 'bg-cyan-500/20 text-cyan-300' : 'opacity-50'}`}
            style={{ color: step === i + 1 ? undefined : 'var(--theme-text)' }}>{i + 1}. {s}</div>
        ))}
      </div>

      {step === 1 && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Legal first name" k="legal_first_name" on={set('legal_first_name')} val={f.legal_first_name} />
            <Field label="Surname" k="surname" on={set('surname')} val={f.surname} />
            <Field label="Preferred name" k="preferred_name" on={set('preferred_name')} val={f.preferred_name} />
            <Field label="Personal email" k="personal_email" on={set('personal_email')} val={f.personal_email} />
            <Field label="Mobile" k="mobile" on={set('mobile')} val={f.mobile} />
            <Field label="Position" k="position" on={set('position')} val={f.position} />
            <Field label="Proposed start date" k="proposed_start_date" on={set('proposed_start_date')} val={f.proposed_start_date} type="date" />
          </div>
          {dup?.has_active_employee && (
            <div className="flex items-center gap-2 text-amber-300 text-sm" data-testid="dup-warning">
              <AlertTriangle size={16} /> An active staff record already exists — avoid duplicates.
            </div>
          )}
          <div className="flex justify-end">
            <button onClick={checkDup} disabled={busy} data-testid="wizard-next-1"
              className="px-4 py-2 rounded-lg text-slate-900 font-semibold" style={{ background: 'var(--color-brand-cyan,#19CDFF)' }}>
              {busy ? '…' : 'Next'}
            </button>
          </div>
        </div>
      )}

      {step === 2 && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Employing company" k="ec" on={setP('employing_company')} val={prop.employing_company} />
            <Field label="Job title" k="job_title" on={setP('job_title')} val={prop.job_title} />
            <Field label="Department" k="department" on={setP('department')} val={prop.department} />
            <Field label="Site / place of work" k="site" on={setP('site')} val={prop.site} />
            <Field label="Line manager" k="line_manager" on={setP('line_manager')} val={prop.line_manager} />
            <Field label="Salary" k="salary" on={setP('salary')} val={prop.salary} />
            <Field label="Hours per week" k="hours" on={setP('hours_per_week')} val={prop.hours_per_week} />
            <Field label="Employment type" k="etype" on={setP('employment_type')} val={prop.employment_type} />
            <Field label="Probation period" k="probation" on={setP('probation_period')} val={prop.probation_period} />
            <Field label="Notice period" k="notice" on={setP('notice_period')} val={prop.notice_period} />
            <Field label="Holiday entitlement" k="holiday" on={setP('holiday_entitlement')} val={prop.holiday_entitlement} />
            <Field label="Authorised signatory" k="signatory" on={setP('authorised_signatory')} val={prop.authorised_signatory} />
          </div>
          <div className="flex justify-between">
            <button onClick={() => setStep(1)} className="px-4 py-2 rounded-lg border" style={{ color: 'var(--theme-text)', borderColor: 'var(--theme-border)' }}>Back</button>
            <button onClick={() => setStep(3)} data-testid="wizard-next-2" className="px-4 py-2 rounded-lg text-slate-900 font-semibold" style={{ background: 'var(--color-brand-cyan,#19CDFF)' }}>Next</button>
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="space-y-3">
          <span className="text-xs opacity-70" style={{ color: 'var(--theme-text)' }}>Onboarding package</span>
          <div className="grid grid-cols-3 gap-2">
            {packages.map((p) => (
              <button key={p.id} onClick={() => setPkg(p.id)} data-testid={`pkg-${p.id}`}
                className={`px-3 py-2 rounded-lg border text-sm text-left ${pkg === p.id ? 'ring-2 ring-cyan-400' : ''}`}
                style={{ color: 'var(--theme-text)', borderColor: 'var(--theme-border)' }}>{p.name}</button>
            ))}
          </div>
          {err && <div className="text-red-400 text-sm">{err}</div>}
          <div className="flex justify-between">
            <button onClick={() => setStep(2)} className="px-4 py-2 rounded-lg border" style={{ color: 'var(--theme-text)', borderColor: 'var(--theme-border)' }}>Back</button>
            <button onClick={create} disabled={busy} data-testid="wizard-create-case"
              className="px-4 py-2 rounded-lg text-slate-900 font-semibold" style={{ background: 'var(--color-brand-cyan,#19CDFF)' }}>
              {busy ? 'Creating…' : 'Create case'}
            </button>
          </div>
        </div>
      )}
    </Modal>
  );
}

/* ───────────────── Case Detail ───────────────── */
function CaseDetail({ headers, caseId, onClose }) {
  const [data, setData] = useState(null);
  const [tab, setTab] = useState('overview');
  const [busy, setBusy] = useState(false);
  const [invite, setInvite] = useState(null);
  const [templates, setTemplates] = useState({ offer: [], contract: [] });
  const [audit, setAudit] = useState([]);
  const [msg, setMsg] = useState('');

  const load = useCallback(async () => {
    const [d, t] = await Promise.all([
      axios.get(`${API}/staff-onboarding/cases/${caseId}`, { headers }),
      axios.get(`${API}/staff-onboarding/templates`, { headers }),
    ]);
    setData(d.data); setTemplates(t.data);
  }, [caseId, headers]);
  useEffect(() => { load(); }, [load]);

  const act = async (fn, ok) => {
    setBusy(true); setMsg('');
    try { await fn(); setMsg(ok || 'Done'); await load(); }
    catch (e) { setMsg('⚠ ' + (e?.response?.data?.detail?.message || e?.response?.data?.detail || 'Action failed')); }
    finally { setBusy(false); }
  };

  const doInvite = () => act(async () => {
    const r = await axios.post(`${API}/staff-onboarding/cases/${caseId}/invite`, { expiry_days: 14 }, { headers });
    setInvite(r.data);
  }, 'Invitation created');
  const setRTW = () => act(() => axios.post(`${API}/staff-onboarding/cases/${caseId}/right-to-work`, { method: 'share_code', result: 'verified' }, { headers }), 'Right to Work verified');
  const paperworkComplete = () => act(() => axios.post(`${API}/staff-onboarding/cases/${caseId}/paperwork-complete`, { comment: 'Reviewed & ready for offer' }, { headers }), 'Paperwork marked complete');
  const createOffer = (tid) => act(() => axios.post(`${API}/staff-onboarding/cases/${caseId}/offer`, { template_id: tid, conditions: [{ label: 'Satisfactory Right to Work', required: true, status: 'pending' }] }, { headers }), 'Offer drafted');
  const approveOffer = () => act(() => axios.post(`${API}/staff-onboarding/cases/${caseId}/offer/approve`, {}, { headers }), 'Offer approved');
  const issueOffer = () => act(() => axios.post(`${API}/staff-onboarding/cases/${caseId}/offer/issue`, {}, { headers }), 'Offer issued to portal');
  const createContract = (tid) => act(() => axios.post(`${API}/staff-onboarding/cases/${caseId}/contract`, { template_id: tid }, { headers }), 'Contract drafted');
  const approveContract = () => act(() => axios.post(`${API}/staff-onboarding/cases/${caseId}/contract/approve`, {}, { headers }), 'Contract approved');
  const issueContract = () => act(() => axios.post(`${API}/staff-onboarding/cases/${caseId}/contract/issue`, {}, { headers }), 'Contract issued to portal');
  const countersign = () => act(() => axios.post(`${API}/staff-onboarding/cases/${caseId}/contract/countersign`, { signature_name: 'Authorised Signatory', signature_method: 'typed' }, { headers }), 'Contract countersigned & locked');
  const activate = () => act(() => axios.post(`${API}/staff-onboarding/cases/${caseId}/activate`, {}, { headers }), 'Employee activated');
  const loadAudit = () => axios.get(`${API}/staff-onboarding/cases/${caseId}/audit`, { headers }).then(r => setAudit(r.data.events || []));

  if (!data) return <Modal onClose={onClose} title="Loading…" testId="case-detail-loading"><Loader2 className="animate-spin mx-auto" style={{ color: 'var(--theme-text)' }} /></Modal>;

  const c = data.case, offer = c.offer, contract = c.contract;
  const TABS = [['overview', 'Overview', FileText], ['paperwork', 'Paperwork', ClipboardList],
    ['offer', 'Offer Letter', ScrollText], ['contract', 'Contract', FileSignature],
    ['activate', 'Activate', CheckCircle2], ['audit', 'Audit', History]];

  return (
    <Modal onClose={onClose} title={`${data.person?.full_name || 'Recruit'} — ${STATUS_LABELS[c.status] || c.status}`} testId="case-detail" wide>
      <div className="flex gap-1 mb-4 flex-wrap">
        {TABS.map(([id, label, Icon]) => (
          <button key={id} onClick={() => { setTab(id); if (id === 'audit') loadAudit(); }} data-testid={`case-tab-${id}`}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm ${tab === id ? 'bg-cyan-500/20 text-cyan-300' : 'opacity-70'}`}
            style={{ color: tab === id ? undefined : 'var(--theme-text)' }}><Icon size={14} /> {label}</button>
        ))}
      </div>
      {msg && <div className="mb-3 text-sm px-3 py-2 rounded-lg" data-testid="case-action-msg"
        style={{ background: 'var(--theme-surface)', color: 'var(--theme-text)' }}>{msg}</div>}

      {tab === 'overview' && (
        <div className="space-y-3 text-sm" style={{ color: 'var(--theme-text)' }}>
          <Row k="Position" v={c.employment_proposal?.job_title || c.employment_proposal?.position} />
          <Row k="Company / site" v={`${c.employment_proposal?.employing_company || '—'} · ${c.employment_proposal?.site || '—'}`} />
          <Row k="Salary" v={c.employment_proposal?.salary} />
          <Row k="Package" v={c.package} />
          <Row k="Documents uploaded" v={data.documents?.length} />
          <div className="pt-2 flex gap-2 flex-wrap">
            <Btn onClick={doInvite} busy={busy} testId="btn-invite">Send portal invitation</Btn>
            {invite && (
              <div className="w-full mt-2 p-3 rounded-lg text-xs" style={{ background: 'var(--theme-surface)', color: 'var(--theme-text)' }} data-testid="invite-link">
                New Starter Portal link (share securely):<br />
                <code className="text-cyan-300 break-all">{window.location.origin}/new-starter/{invite.invite_token}</code>
              </div>
            )}
          </div>
        </div>
      )}

      {tab === 'paperwork' && (
        <div className="space-y-3 text-sm" style={{ color: 'var(--theme-text)' }}>
          <PaperworkChecks headers={headers} caseId={caseId} />
          <div className="flex gap-2 flex-wrap pt-2">
            <Btn onClick={setRTW} busy={busy} testId="btn-verify-rtw"><ShieldCheck size={14} /> Verify Right to Work</Btn>
            <Btn onClick={paperworkComplete} busy={busy} testId="btn-paperwork-complete" primary>Mark Paperwork Complete</Btn>
          </div>
        </div>
      )}

      {tab === 'offer' && (
        <div className="space-y-3 text-sm" style={{ color: 'var(--theme-text)' }}>
          {!offer && (
            <>
              <div className="opacity-70">Create an offer from an approved template (paperwork must be complete):</div>
              <div className="grid grid-cols-2 gap-2">
                {templates.offer.map((t) => (
                  <button key={t.id} onClick={() => createOffer(t.id)} data-testid={`offer-tmpl-${t.key}`}
                    className="px-3 py-2 rounded-lg border text-left" style={{ color: 'var(--theme-text)', borderColor: 'var(--theme-border)' }}>
                    {t.title}{t.is_sample && <span className="ml-1 text-[10px] text-amber-300">SAMPLE</span>}
                  </button>
                ))}
              </div>
            </>
          )}
          {offer && (
            <>
              <div className="flex items-center gap-2"><Pill tone="blue">{offer.status}</Pill>{offer.conditional && <Pill tone="amber">Conditional</Pill>}</div>
              <pre className="whitespace-pre-wrap p-3 rounded-lg text-xs max-h-64 overflow-auto" data-testid="offer-preview"
                style={{ background: 'var(--theme-surface)' }}>{offer.rendered}</pre>
              <div className="flex gap-2 flex-wrap">
                {offer.status === 'draft' && <Btn onClick={approveOffer} busy={busy} testId="btn-approve-offer">Approve</Btn>}
                {(offer.status === 'approved') && <Btn onClick={issueOffer} busy={busy} testId="btn-issue-offer" primary>Issue to portal</Btn>}
                {offer.status === 'issued' && <Pill tone="amber">Awaiting recruit response</Pill>}
                {offer.status === 'accepted' && <Pill tone="green">Accepted ✓</Pill>}
              </div>
            </>
          )}
        </div>
      )}

      {tab === 'contract' && (
        <div className="space-y-3 text-sm" style={{ color: 'var(--theme-text)' }}>
          {!contract && (
            <>
              {offer?.status !== 'accepted'
                ? <div className="text-amber-300">The offer must be accepted before creating the contract.</div>
                : <>
                    <div className="opacity-70">Create the contract from the accepted offer:</div>
                    <div className="grid grid-cols-2 gap-2">
                      {templates.contract.map((t) => (
                        <button key={t.id} onClick={() => createContract(t.id)} data-testid={`contract-tmpl-${t.key}`}
                          className="px-3 py-2 rounded-lg border text-left" style={{ color: 'var(--theme-text)', borderColor: 'var(--theme-border)' }}>
                          {t.title}{t.is_sample && <span className="ml-1 text-[10px] text-amber-300">SAMPLE</span>}
                        </button>
                      ))}
                    </div>
                  </>}
            </>
          )}
          {contract && (
            <>
              <div className="flex items-center gap-2"><Pill tone="blue">{contract.status}</Pill>
                {contract.differences?.length > 0
                  ? <Pill tone="red">Contract differs from offer ({contract.differences.length})</Pill>
                  : <Pill tone="green">Matches accepted offer</Pill>}</div>
              <pre className="whitespace-pre-wrap p-3 rounded-lg text-xs max-h-64 overflow-auto" data-testid="contract-preview"
                style={{ background: 'var(--theme-surface)' }}>{contract.rendered}</pre>
              <div className="flex gap-2 flex-wrap">
                {contract.status === 'draft' && <Btn onClick={approveContract} busy={busy} testId="btn-approve-contract">Approve</Btn>}
                {contract.status === 'approved' && <Btn onClick={issueContract} busy={busy} testId="btn-issue-contract" primary>Issue to portal</Btn>}
                {contract.status === 'issued' && <Pill tone="amber">Awaiting recruit signature</Pill>}
                {(contract.status === 'employee_signed' || c.status === 'awaiting_employer_signature') && <Btn onClick={countersign} busy={busy} testId="btn-countersign" primary>Employer countersign</Btn>}
                {contract.status === 'fully_signed' && <Pill tone="green">Fully signed & locked ✓</Pill>}
              </div>
            </>
          )}
        </div>
      )}

      {tab === 'activate' && (
        <ActivatePanel headers={headers} caseId={caseId} onActivate={activate} busy={busy} status={c.status} />
      )}

      {tab === 'audit' && (
        <div className="space-y-1.5 text-sm max-h-96 overflow-auto" data-testid="audit-trail" style={{ color: 'var(--theme-text)' }}>
          {audit.length === 0 && <div className="opacity-60">No events.</div>}
          {audit.map((e) => (
            <div key={e.id} className="flex items-center justify-between gap-2 px-3 py-2 rounded-lg" style={{ background: 'var(--theme-surface)' }}>
              <span className="font-medium">{e.event.replace(/_/g, ' ')}</span>
              <span className="text-xs opacity-60">{e.user_name || '—'} · {new Date(e.at).toLocaleString()}</span>
            </div>
          ))}
        </div>
      )}
    </Modal>
  );
}

function PaperworkChecks({ headers, caseId }) {
  const [st, setSt] = useState(null);
  useEffect(() => { axios.get(`${API}/staff-onboarding/cases/${caseId}/paperwork-state`, { headers }).then(r => setSt(r.data)).catch(() => {}); }, [caseId, headers]);
  if (!st) return <Loader2 className="animate-spin" style={{ color: 'var(--theme-text)' }} />;
  return (
    <div className="grid grid-cols-2 gap-2" data-testid="paperwork-checks">
      {Object.entries(st.checks).map(([k, v]) => (
        <div key={k} className="flex items-center gap-2 px-3 py-2 rounded-lg" style={{ background: 'var(--theme-surface)' }}>
          {v ? <CheckCircle2 size={15} className="text-emerald-400" /> : <X size={15} className="text-red-400" />}
          <span className="text-xs capitalize" style={{ color: 'var(--theme-text)' }}>{k.replace(/_/g, ' ')}</span>
        </div>
      ))}
    </div>
  );
}

function ActivatePanel({ headers, caseId, onActivate, busy, status }) {
  const [st, setSt] = useState(null);
  useEffect(() => { axios.get(`${API}/staff-onboarding/cases/${caseId}/activation-state`, { headers }).then(r => setSt(r.data)).catch(() => {}); }, [caseId, headers, status]);
  return (
    <div className="space-y-3 text-sm" style={{ color: 'var(--theme-text)' }} data-testid="activate-panel">
      {st && Object.entries(st.checks).map(([k, v]) => (
        <div key={k} className="flex items-center gap-2">
          {v ? <CheckCircle2 size={15} className="text-emerald-400" /> : <X size={15} className="text-red-400" />}
          <span className="capitalize">{k.replace(/_/g, ' ')}</span>
        </div>
      ))}
      {status === 'complete'
        ? <Pill tone="green">Employee activated — staff portal enabled ✓</Pill>
        : <Btn onClick={onActivate} busy={busy} testId="btn-activate" primary disabled={!st?.ready}>Activate Staff Member</Btn>}
    </div>
  );
}

/* ───────────────── shared UI ───────────────── */
function Modal({ children, onClose, title, testId, wide }) {
  return (
    <div className="fixed inset-0 z-[200] flex items-start justify-center p-4 overflow-auto" style={{ background: 'rgba(0,0,0,0.6)' }} data-testid={testId}>
      <div className={`w-full ${wide ? 'max-w-3xl' : 'max-w-2xl'} rounded-2xl border my-8`} style={{ background: 'var(--theme-bg, #0f1417)', borderColor: 'var(--theme-border)' }}>
        <div className="flex items-center justify-between px-5 py-3 border-b" style={{ borderColor: 'var(--theme-border)' }}>
          <h3 className="font-bold" style={{ color: 'var(--theme-text)' }}>{title}</h3>
          <button onClick={onClose} data-testid="modal-close"><X size={18} style={{ color: 'var(--theme-text)' }} /></button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}
function Row({ k, v }) {
  return <div className="flex justify-between gap-3 border-b py-1.5" style={{ borderColor: 'var(--theme-border)' }}>
    <span className="opacity-60">{k}</span><span className="font-medium text-right">{v ?? '—'}</span></div>;
}
function Btn({ children, onClick, busy, testId, primary, disabled }) {
  return <button onClick={onClick} disabled={busy || disabled} data-testid={testId}
    className={`inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold disabled:opacity-40 ${primary ? 'text-slate-900' : 'border'}`}
    style={primary ? { background: 'var(--color-brand-cyan,#19CDFF)' } : { color: 'var(--theme-text)', borderColor: 'var(--theme-border)' }}>
    {busy ? <Loader2 size={14} className="animate-spin" /> : children}</button>;
}
