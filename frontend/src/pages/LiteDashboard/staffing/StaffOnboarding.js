/**
 * StaffOnboarding — HR console for the Staff Onboarding, Offer & Contract wizard.
 * Mounted at Operations → Staffing → People → Staff Onboarding.
 * Single person record (staff_members) progresses candidate→…→employee.
 */
import { useCallback, useEffect, useState, useRef } from 'react';
import { createPortal } from 'react-dom';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import {
  UserPlus, Loader2, X, FileText, FileSignature, CheckCircle2, ShieldCheck,
  ClipboardList, ScrollText, ArrowRight, AlertTriangle, History, Bell,
  Download, Pencil, RotateCcw, Plus, ShieldAlert, Settings, Mail,
} from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

async function openPdf(url, headers) {
  const r = await axios.get(url, { headers, responseType: 'blob' });
  const blobUrl = URL.createObjectURL(new Blob([r.data], { type: 'application/pdf' }));
  window.open(blobUrl, '_blank');
}

const surface = { background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' };
const STATUS_LABELS_EN = {
  not_started: 'Not Started', in_progress: 'In Progress', awaiting_hr_review: 'Awaiting HR Review',
  awaiting_offer: 'Awaiting Offer', offer_issued: 'Offer Issued', offer_accepted: 'Offer Accepted',
  offer_declined: 'Offer Declined', contract_issued: 'Contract Issued',
  awaiting_employer_signature: 'Awaiting Employer Signature', ready_to_activate: 'Ready to Activate',
  complete: 'Complete',
};
function statusLabel(t, s) {
  return t(`staffing.onb_status_${s}`, STATUS_LABELS_EN[s] || s);
}

function Pill({ children, tone = 'slate' }) {
  const tones = {
    slate: 'bg-slate-500/15 text-slate-300', blue: 'bg-cyan-500/15 text-cyan-300',
    green: 'bg-emerald-500/15 text-emerald-300', amber: 'bg-amber-500/15 text-amber-300',
    red: 'bg-red-500/15 text-red-300',
  };
  return <span className={`px-2 py-0.5 rounded-full text-[11px] font-semibold ${tones[tone]}`}>{children}</span>;
}

export default function StaffOnboarding({ headers }) {
  const { t } = useTranslation();
  const [cards, setCards] = useState({});
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showWizard, setShowWizard] = useState(false);
  const [openCase, setOpenCase] = useState(null);
  const [notifs, setNotifs] = useState({ notifications: [], unread: 0 });
  const [showNotifs, setShowNotifs] = useState(false);
  const [showTemplates, setShowTemplates] = useState(false);
  const [showSettings, setShowSettings] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [d, c, n] = await Promise.all([
        axios.get(`${API}/staff-onboarding/dashboard`, { headers }),
        axios.get(`${API}/staff-onboarding/cases`, { headers }),
        axios.get(`${API}/staff-onboarding/notifications`, { headers }).catch(() => ({ data: { notifications: [], unread: 0 } })),
      ]);
      setCards(d.data.cards || {});
      setCases(c.data.cases || []);
      setNotifs(n.data || { notifications: [], unread: 0 });
    } catch (e) { /* noop */ } finally { setLoading(false); }
  }, [headers]);

  const openNotifs = async () => {
    setShowNotifs((v) => !v);
    if (!showNotifs && notifs.unread > 0) {
      try { await axios.post(`${API}/staff-onboarding/notifications/read`, {}, { headers }); setNotifs((p) => ({ ...p, unread: 0 })); } catch (e) {}
    }
  };

  useEffect(() => { load(); }, [load]);

  const CARD_DEFS = [
    ['paperwork_awaiting_review', t('staffing.onb_card_awaiting_review', 'Awaiting review'), 'amber'],
    ['ready_for_offer', t('staffing.onb_card_ready_offer', 'Ready for offer'), 'blue'],
    ['offers_issued', t('staffing.onb_card_offers_issued', 'Offers issued'), 'blue'],
    ['offers_accepted', t('staffing.onb_card_offers_accepted', 'Offers accepted'), 'green'],
    ['contracts_awaiting_signature', t('staffing.onb_card_contracts_sign', 'Contracts to sign'), 'amber'],
    ['contracts_fully_signed', t('staffing.onb_card_fully_signed', 'Fully signed'), 'green'],
    ['ready_to_activate', t('staffing.onb_card_ready_activate', 'Ready to activate'), 'green'],
    ['total_cases', t('staffing.onb_card_total', 'Total cases'), 'slate'],
  ];

  return (
    <div className="space-y-5" data-testid="staff-onboarding-console">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-xl font-bold" style={{ color: 'var(--theme-text)' }}>{t('staffing.onb_title', 'Staff Onboarding')}</h2>
          <p className="text-sm opacity-70" style={{ color: 'var(--theme-text)' }}>
            {t('staffing.onb_subtitle', 'Paperless recruitment-to-employment — one person record, offer letter, contract & e-signature.')}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <button onClick={openNotifs} data-testid="notifications-bell"
              className="relative p-2 rounded-xl border" style={{ color: 'var(--theme-text)', borderColor: 'var(--theme-border)' }}>
              <Bell size={18} />
              {notifs.unread > 0 && <span className="absolute -top-1 -right-1 bg-red-500 text-white text-[10px] rounded-full w-4 h-4 flex items-center justify-center">{notifs.unread}</span>}
            </button>
            {showNotifs && (
              <div className="absolute right-0 mt-2 w-80 max-h-96 overflow-auto rounded-xl border shadow-xl z-50 p-2" data-testid="notifications-panel"
                style={{ background: 'var(--theme-bg,#0f1417)', borderColor: 'var(--theme-border)' }}>
                {notifs.notifications.length === 0 ? (
                  <div className="p-4 text-sm opacity-60 text-center" style={{ color: 'var(--theme-text)' }}>{t('staffing.onb_no_notifs', 'No notifications')}</div>
                ) : notifs.notifications.map((n) => (
                  <div key={n.id} className="px-3 py-2 rounded-lg text-sm" style={{ color: 'var(--theme-text)' }}>
                    <div className="font-medium">{n.message}</div>
                    <div className="text-xs opacity-50">{new Date(n.created_at).toLocaleString()}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
          <button onClick={() => setShowTemplates(true)} data-testid="open-templates-btn"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl font-semibold border"
            style={{ color: 'var(--theme-text)', borderColor: 'var(--theme-border)' }}>
            <ScrollText size={16} /> {t('staffing.onb_templates', 'Templates')}
          </button>
          <button onClick={() => setShowSettings(true)} data-testid="open-settings-btn"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl font-semibold border"
            style={{ color: 'var(--theme-text)', borderColor: 'var(--theme-border)' }}>
            <Settings size={16} /> {t('staffing.onb_settings', 'Settings')}
          </button>
          <button onClick={() => setShowWizard(true)} data-testid="new-onboarding-case-btn"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl font-semibold text-slate-900"
            style={{ background: 'var(--color-brand-cyan, #19CDFF)' }}>
            <UserPlus size={16} /> {t('staffing.onb_create_case', 'Create Onboarding Case')}
          </button>
        </div>
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
          <span className="font-semibold" style={{ color: 'var(--theme-text)' }}>{t('staffing.onb_cases', 'Onboarding Cases')}</span>
        </div>
        {loading ? (
          <div className="p-8 flex justify-center"><Loader2 className="animate-spin" style={{ color: 'var(--theme-text)' }} /></div>
        ) : cases.length === 0 ? (
          <div className="p-8 text-center opacity-70 text-sm" style={{ color: 'var(--theme-text)' }}>
            {t('staffing.onb_no_cases', 'No onboarding cases yet. Create one to invite a new recruit.')}
          </div>
        ) : (
          <div className="divide-y" style={{ borderColor: 'var(--theme-border)' }}>
            {cases.map((c) => (
              <button key={c.id} onClick={() => setOpenCase(c.id)} data-testid={`case-row-${c.id}`}
                className="w-full text-left px-4 py-3 hover:bg-white/[0.03] transition-colors flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-semibold truncate" style={{ color: 'var(--theme-text)' }}>
                    {c.person?.full_name || t('staffing.onb_new_recruit', 'New recruit')}
                  </div>
                  <div className="text-xs opacity-60 truncate" style={{ color: 'var(--theme-text)' }}>
                    {c.employment_proposal?.job_title || c.employment_proposal?.position || '—'} · {c.package || t('staffing.onb_no_package', 'no package')}
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <Pill tone={c.status === 'complete' ? 'green' : c.status?.includes('offer') ? 'blue' : 'amber'}>
                    {statusLabel(t, c.status)}
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
      {showTemplates && <TemplateManager headers={headers} onClose={() => setShowTemplates(false)} />}
      {showSettings && <PackSettings headers={headers} onClose={() => setShowSettings(false)} />}
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

function WizardSelect({ label, k, val, on, options, placeholder }) {
  const { t } = useTranslation();
  const ph = placeholder || t('staffing.onb_select', 'Select…');
  return (
    <label className="block">
      <span className="text-xs opacity-70" style={{ color: 'var(--theme-text)' }}>{label}</span>
      <select value={val} onChange={on} data-testid={`wizard-${k}`}
        className="mt-1 w-full rounded-lg px-3 py-2 text-sm border bg-transparent"
        style={{ color: 'var(--theme-text)', borderColor: 'var(--theme-border)' }}>
        <option value="" style={{ color: '#111' }}>{ph}</option>
        {options.map((o) => <option key={o} value={o} style={{ color: '#111' }}>{o}</option>)}
      </select>
    </label>
  );
}

// Editable dropdown (native datalist) — HR can pick a suggestion or type a custom value.
function WizardCombo({ label, k, val, on, options, placeholder }) {
  const listId = `dl-${k}`;
  return (
    <label className="block">
      <span className="text-xs opacity-70" style={{ color: 'var(--theme-text)' }}>{label}</span>
      <input list={listId} value={val} onChange={on} data-testid={`wizard-${k}`} placeholder={placeholder}
        className="mt-1 w-full rounded-lg px-3 py-2 text-sm border bg-transparent"
        style={{ color: 'var(--theme-text)', borderColor: 'var(--theme-border)' }} />
      <datalist id={listId}>{options.map((o) => <option key={o} value={o} />)}</datalist>
    </label>
  );
}

const DEPARTMENTS = ['Service', 'Sales', 'Operations', 'Installation', 'Warehouse / Stores',
  'Finance', 'HR', 'Marketing', 'IT', 'Customer Support', 'Management', 'Admin'];
const EMPLOYMENT_TYPES = ['Permanent full time', 'Permanent part time', 'Fixed-term contract',
  'Temporary', 'Apprenticeship', 'Zero-hours', 'Consultant / Contractor'];
const PROBATION_PERIODS = ['None', '1 month', '3 months', '6 months', '12 months'];
const NOTICE_PERIODS = ['1 week', '2 weeks', '1 month', '2 months', '3 months', '6 months'];
const HOLIDAY_OPTIONS = ['20 days', '22 days', '25 days', '28 days (incl. bank holidays)',
  '30 days', '33 days (incl. bank holidays)'];
const SITE_OPTIONS = ['Head Office', 'Remote', 'Field-based', 'Hybrid'];
const COMPANY_OPTIONS = ['Pulse Fitness'];

/* ───────────────── Create Onboarding Case Wizard ───────────────── */
function CaseWizard({ headers, onClose, onCreated }) {
  const { t } = useTranslation();
  const [step, setStep] = useState(1);
  const [f, setF] = useState({ legal_first_name: '', surname: '', preferred_name: '', personal_email: '', mobile: '', position: '', proposed_start_date: '' });
  const [prop, setProp] = useState({ employing_company: 'Pulse Fitness', job_title: '', department: '', site: '', line_manager: '', salary: '', hours_per_week: '', employment_type: 'Permanent full time', probation_period: '', notice_period: '', holiday_entitlement: '', authorised_signatory: '' });
  const [pkg, setPkg] = useState('standard');
  const [packages, setPackages] = useState([]);
  const [staffNames, setStaffNames] = useState([]);
  const [dup, setDup] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const set = (k) => (e) => setF((p) => ({ ...p, [k]: e.target.value }));
  const setP = (k) => (e) => setProp((p) => ({ ...p, [k]: e.target.value }));

  useEffect(() => {
    axios.get(`${API}/staff-onboarding/packages`, { headers }).then(r => setPackages(r.data.packages || [])).catch(() => {});
    axios.get(`${API}/staffing/staff`, { headers }).then(r => setStaffNames((r.data.staff || []).map(s => s.full_name).filter(Boolean))).catch(() => {});
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
      setErr(e?.response?.data?.detail?.message || e?.response?.data?.detail || t('staffing.onb_create_failed', 'Could not create case'));
      setBusy(false);
    }
  };

  const Field = WizardField;

  return (
    <Modal onClose={onClose} title={t('staffing.onb_create_case', 'Create Onboarding Case')} testId="case-wizard">
      <div className="flex gap-2 mb-4 text-xs">
        {[t('staffing.onb_step_recruit', 'Select Recruit'), t('staffing.onb_step_proposal', 'Employment Proposal'), t('staffing.onb_step_package', 'Package')].map((s, i) => (
          <div key={s} className={`px-2 py-1 rounded-full ${step === i + 1 ? 'bg-cyan-500/20 text-cyan-300' : 'opacity-50'}`}
            style={{ color: step === i + 1 ? undefined : 'var(--theme-text)' }}>{i + 1}. {s}</div>
        ))}
      </div>

      {step === 1 && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <Field label={t('staffing.onb_legal_first', 'Legal first name')} k="legal_first_name" on={set('legal_first_name')} val={f.legal_first_name} />
            <Field label={t('staffing.onb_surname', 'Surname')} k="surname" on={set('surname')} val={f.surname} />
            <Field label={t('staffing.onb_preferred', 'Preferred name')} k="preferred_name" on={set('preferred_name')} val={f.preferred_name} />
            <Field label={t('staffing.onb_personal_email', 'Personal email')} k="personal_email" on={set('personal_email')} val={f.personal_email} />
            <Field label={t('staffing.onb_mobile', 'Mobile')} k="mobile" on={set('mobile')} val={f.mobile} />
            <Field label={t('staffing.onb_position', 'Position')} k="position" on={set('position')} val={f.position} />
            <Field label={t('staffing.onb_start_date', 'Proposed start date')} k="proposed_start_date" on={set('proposed_start_date')} val={f.proposed_start_date} type="date" />
          </div>
          {dup?.has_active_employee && (
            <div className="flex items-center gap-2 text-amber-300 text-sm" data-testid="dup-warning">
              <AlertTriangle size={16} /> {t('staffing.onb_dup_warning', 'An active staff record already exists — avoid duplicates.')}
            </div>
          )}
          <div className="flex justify-end">
            <button onClick={checkDup} disabled={busy} data-testid="wizard-next-1"
              className="px-4 py-2 rounded-lg text-slate-900 font-semibold" style={{ background: 'var(--color-brand-cyan,#19CDFF)' }}>
              {busy ? '…' : t('staffing.onb_next', 'Next')}
            </button>
          </div>
        </div>
      )}

      {step === 2 && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <WizardCombo label={t('staffing.onb_employing_company', 'Employing company')} k="ec" on={setP('employing_company')} val={prop.employing_company} options={COMPANY_OPTIONS} />
            <Field label={t('staffing.onb_job_title', 'Job title')} k="job_title" on={setP('job_title')} val={prop.job_title} />
            <WizardSelect label={t('staffing.onb_department', 'Department')} k="department" on={setP('department')} val={prop.department} options={DEPARTMENTS} />
            <WizardCombo label={t('staffing.onb_site', 'Site / place of work')} k="site" on={setP('site')} val={prop.site} options={SITE_OPTIONS} placeholder={t('staffing.onb_select_type', 'Select or type…')} />
            <WizardCombo label={t('staffing.onb_line_manager', 'Line manager')} k="line_manager" on={setP('line_manager')} val={prop.line_manager} options={staffNames} placeholder={t('staffing.onb_select_type', 'Select or type…')} />
            <Field label={t('staffing.onb_salary', 'Salary')} k="salary" on={setP('salary')} val={prop.salary} />
            <Field label={t('staffing.onb_hours', 'Hours per week')} k="hours" on={setP('hours_per_week')} val={prop.hours_per_week} type="number" />
            <WizardSelect label={t('staffing.onb_employment_type', 'Employment type')} k="etype" on={setP('employment_type')} val={prop.employment_type} options={EMPLOYMENT_TYPES} />
            <WizardSelect label={t('staffing.onb_probation', 'Probation period')} k="probation" on={setP('probation_period')} val={prop.probation_period} options={PROBATION_PERIODS} />
            <WizardSelect label={t('staffing.onb_notice', 'Notice period')} k="notice" on={setP('notice_period')} val={prop.notice_period} options={NOTICE_PERIODS} />
            <WizardSelect label={t('staffing.onb_holiday', 'Holiday entitlement')} k="holiday" on={setP('holiday_entitlement')} val={prop.holiday_entitlement} options={HOLIDAY_OPTIONS} />
            <WizardCombo label={t('staffing.onb_signatory', 'Authorised signatory')} k="signatory" on={setP('authorised_signatory')} val={prop.authorised_signatory} options={staffNames} placeholder={t('staffing.onb_select_type', 'Select or type…')} />
          </div>
          <div className="flex justify-between">
            <button onClick={() => setStep(1)} className="px-4 py-2 rounded-lg border" style={{ color: 'var(--theme-text)', borderColor: 'var(--theme-border)' }}>{t('staffing.onb_back', 'Back')}</button>
            <button onClick={() => setStep(3)} data-testid="wizard-next-2" className="px-4 py-2 rounded-lg text-slate-900 font-semibold" style={{ background: 'var(--color-brand-cyan,#19CDFF)' }}>{t('staffing.onb_next', 'Next')}</button>
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="space-y-3">
          <span className="text-xs opacity-70" style={{ color: 'var(--theme-text)' }}>{t('staffing.onb_package', 'Onboarding package')}</span>
          <div className="grid grid-cols-3 gap-2">
            {packages.map((p) => (
              <button key={p.id} onClick={() => setPkg(p.id)} data-testid={`pkg-${p.id}`}
                className={`px-3 py-2 rounded-lg border text-sm text-left ${pkg === p.id ? 'ring-2 ring-cyan-400' : ''}`}
                style={{ color: 'var(--theme-text)', borderColor: 'var(--theme-border)' }}>{p.name}</button>
            ))}
          </div>
          {err && <div className="text-red-400 text-sm">{err}</div>}
          <div className="flex justify-between">
            <button onClick={() => setStep(2)} className="px-4 py-2 rounded-lg border" style={{ color: 'var(--theme-text)', borderColor: 'var(--theme-border)' }}>{t('staffing.onb_back', 'Back')}</button>
            <button onClick={create} disabled={busy} data-testid="wizard-create-case"
              className="px-4 py-2 rounded-lg text-slate-900 font-semibold" style={{ background: 'var(--color-brand-cyan,#19CDFF)' }}>
              {busy ? t('staffing.onb_creating', 'Creating…') : t('staffing.onb_create_case_btn', 'Create case')}
            </button>
          </div>
        </div>
      )}
    </Modal>
  );
}

/* ───────────────── Case Detail ───────────────── */
function CaseDetail({ headers, caseId, onClose }) {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [tab, setTab] = useState('overview');
  const [busy, setBusy] = useState(false);
  const [invite, setInvite] = useState(null);
  const [templates, setTemplates] = useState({ offer: [], contract: [] });
  const [audit, setAudit] = useState([]);
  const [msg, setMsg] = useState('');
  const [dupResult, setDupResult] = useState(null);
  const [consResult, setConsResult] = useState(null);
  const [aiBusy, setAiBusy] = useState('');

  const load = useCallback(async () => {
    const [d, tRes] = await Promise.all([
      axios.get(`${API}/staff-onboarding/cases/${caseId}`, { headers }),
      axios.get(`${API}/staff-onboarding/templates`, { headers }),
    ]);
    setData(d.data); setTemplates(tRes.data);
  }, [caseId, headers]);
  useEffect(() => { load(); }, [load]);

  const act = async (fn, ok) => {
    setBusy(true); setMsg('');
    try { await fn(); setMsg(ok || t('staffing.onb_done', 'Done')); await load(); }
    catch (e) { setMsg('⚠ ' + (e?.response?.data?.detail?.message || e?.response?.data?.detail || t('staffing.onb_action_failed', 'Action failed'))); }
    finally { setBusy(false); }
  };

  const doInvite = () => act(async () => {
    const r = await axios.post(`${API}/staff-onboarding/cases/${caseId}/invite`, { expiry_days: 14 }, { headers });
    setInvite(r.data);
  }, t('staffing.onb_invite_created', 'Invitation created'));
  const setRTW = () => act(() => axios.post(`${API}/staff-onboarding/cases/${caseId}/right-to-work`, { method: 'share_code', result: 'verified' }, { headers }), t('staffing.onb_rtw_verified', 'Right to Work verified'));
  const paperworkComplete = () => act(() => axios.post(`${API}/staff-onboarding/cases/${caseId}/paperwork-complete`, { comment: 'Reviewed & ready for offer' }, { headers }), t('staffing.onb_paperwork_complete_msg', 'Paperwork marked complete'));
  const createOffer = (tid) => act(() => axios.post(`${API}/staff-onboarding/cases/${caseId}/offer`, { template_id: tid, conditions: [{ label: 'Satisfactory Right to Work', required: true, status: 'pending' }] }, { headers }), t('staffing.onb_offer_drafted', 'Offer drafted'));
  const approveOffer = () => act(() => axios.post(`${API}/staff-onboarding/cases/${caseId}/offer/approve`, {}, { headers }), t('staffing.onb_offer_approved', 'Offer approved'));
  const issueOffer = () => act(() => axios.post(`${API}/staff-onboarding/cases/${caseId}/offer/issue`, {}, { headers }), t('staffing.onb_offer_issued_msg', 'Offer issued to portal'));
  const createContract = (tid) => act(() => axios.post(`${API}/staff-onboarding/cases/${caseId}/contract`, { template_id: tid }, { headers }), t('staffing.onb_contract_drafted', 'Contract drafted'));
  const approveContract = () => act(() => axios.post(`${API}/staff-onboarding/cases/${caseId}/contract/approve`, {}, { headers }), t('staffing.onb_contract_approved', 'Contract approved'));
  const issueContract = () => act(() => axios.post(`${API}/staff-onboarding/cases/${caseId}/contract/issue`, {}, { headers }), t('staffing.onb_contract_issued_msg', 'Contract issued to portal'));
  const countersign = () => act(() => axios.post(`${API}/staff-onboarding/cases/${caseId}/contract/countersign`, { signature_name: 'Authorised Signatory', signature_method: 'typed' }, { headers }), t('staffing.onb_countersigned', 'Contract countersigned & locked'));
  const activate = () => act(() => axios.post(`${API}/staff-onboarding/cases/${caseId}/activate`, {}, { headers }), t('staffing.onb_activated', 'Employee activated'));
  const loadAudit = () => axios.get(`${API}/staff-onboarding/cases/${caseId}/audit`, { headers }).then(r => setAudit(r.data.events || []));
  const dupScan = async () => { setAiBusy('dup'); setDupResult(null); try { const r = await axios.post(`${API}/staff-onboarding/cases/${caseId}/ai/duplicate-scan`, {}, { headers }); setDupResult(r.data); } catch (e) { setDupResult({ error: e?.response?.data?.detail || t('staffing.onb_ai_scan_failed', 'AI scan failed') }); } finally { setAiBusy(''); } };
  const aiConsistency = async () => { setAiBusy('cons'); setConsResult(null); try { const r = await axios.post(`${API}/staff-onboarding/cases/${caseId}/ai/consistency`, {}, { headers }); setConsResult(r.data); } catch (e) { setConsResult({ error: e?.response?.data?.detail || t('staffing.onb_ai_check_failed', 'AI check failed') }); } finally { setAiBusy(''); } };

  if (!data) return <Modal onClose={onClose} title={t('staffing.onb_loading', 'Loading…')} testId="case-detail-loading"><Loader2 className="animate-spin mx-auto" style={{ color: 'var(--theme-text)' }} /></Modal>;

  const c = data.case, offer = c.offer, contract = c.contract;
  const TABS = [['overview', t('staffing.onb_tab_overview', 'Overview'), FileText], ['paperwork', t('staffing.onb_tab_paperwork', 'Paperwork'), ClipboardList],
    ['checks', t('staffing.onb_tab_checks', 'DBS / RTW'), ShieldCheck],
    ['offer', t('staffing.onb_tab_offer', 'Offer Letter'), ScrollText], ['contract', t('staffing.onb_tab_contract', 'Contract'), FileSignature],
    ['activate', t('staffing.onb_tab_activate', 'Activate'), CheckCircle2], ['audit', t('staffing.onb_tab_audit', 'Audit'), History]];

  return (
    <Modal onClose={onClose} title={`${data.person?.full_name || t('staffing.onb_recruit', 'Recruit')} — ${statusLabel(t, c.status)}`} testId="case-detail" wide>
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
          <Row k={t('staffing.onb_position', 'Position')} v={c.employment_proposal?.job_title || c.employment_proposal?.position} />
          <Row k={t('staffing.onb_company_site', 'Company / site')} v={`${c.employment_proposal?.employing_company || '—'} · ${c.employment_proposal?.site || '—'}`} />
          <Row k={t('staffing.onb_salary', 'Salary')} v={c.employment_proposal?.salary} />
          <Row k={t('staffing.onb_package_label', 'Package')} v={c.package} />
          <Row k={t('staffing.onb_docs_uploaded', 'Documents uploaded')} v={data.documents?.length} />
          <div className="pt-2 flex gap-2 flex-wrap">
            <Btn onClick={doInvite} busy={busy} testId="btn-invite">{t('staffing.onb_send_invite', 'Send portal invitation')}</Btn>
            {invite && (
              <div className="w-full mt-2 p-3 rounded-lg text-xs" style={{ background: 'var(--theme-surface)', color: 'var(--theme-text)' }} data-testid="invite-link">
                {t('staffing.onb_portal_link', 'New Starter Portal link (share securely):')}<br />
                <code className="text-cyan-300 break-all">{window.location.origin}/new-starter/{invite.invite_token}</code>
              </div>
            )}
          </div>

          <div className="pt-3 border-t" style={{ borderColor: 'var(--theme-border)' }}>
            <div className="text-xs opacity-70 mb-2">{t('staffing.onb_documents_pdf', 'Documents (PDF)')}</div>
            <div className="flex gap-2 flex-wrap">
              <Btn onClick={() => openPdf(`${API}/staff-onboarding/cases/${caseId}/forms.pdf`, headers)} testId="btn-forms-pdf"><Download size={13} /> {t('staffing.onb_completed_forms', 'Completed forms')}</Btn>
              <Btn onClick={() => openPdf(`${API}/staff-onboarding/cases/${caseId}/pack.pdf`, headers)} testId="btn-pack-pdf" primary><Download size={13} /> {t('staffing.onb_onboarding_pack', 'Onboarding pack')}</Btn>
            </div>
          </div>

          <div className="pt-3 border-t" style={{ borderColor: 'var(--theme-border)' }}>
            <div className="flex items-center gap-2 mb-2"><span className="text-xs opacity-70">{t('staffing.onb_ai_assist', 'AI assist')}</span></div>
            <Btn onClick={dupScan} busy={aiBusy === 'dup'} testId="btn-ai-duplicate-scan"><ShieldAlert size={13} /> {t('staffing.onb_ai_dup_scan', 'AI duplicate scan')}</Btn>
            {dupResult && (
              <div className="mt-2 p-3 rounded-lg text-xs" data-testid="ai-duplicate-result" style={{ background: 'var(--theme-surface)' }}>
                {dupResult.error ? <span className="text-red-400">{dupResult.error}</span> : (
                  <>
                    <div className="opacity-80 mb-1">{dupResult.summary || `${(dupResult.matches || []).length} ${t('staffing.onb_possible_matches', 'possible match(es)')}`}</div>
                    {(dupResult.matches || []).map((m, i) => (
                      <div key={i} className="flex items-start gap-2 py-1">
                        <Pill tone={m.confidence >= 75 ? 'red' : 'amber'}>{m.confidence}%</Pill>
                        <div><span className="font-medium">{m.full_name}</span>{m.active_employee && <span className="ml-1 text-emerald-400">{t('staffing.onb_active_paren', '(active)')}</span>}
                          <div className="opacity-60">{(m.reasons || []).join('; ')}</div></div>
                      </div>
                    ))}
                    {(dupResult.matches || []).length === 0 && <div className="text-emerald-400">{t('staffing.onb_no_dups', 'No likely duplicates found ✓')}</div>}
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {tab === 'paperwork' && (
        <div className="space-y-3 text-sm" style={{ color: 'var(--theme-text)' }}>
          <PaperworkChecks headers={headers} caseId={caseId} />
          <div className="flex gap-2 flex-wrap pt-2">
            <Btn onClick={setRTW} busy={busy} testId="btn-verify-rtw"><ShieldCheck size={14} /> {t('staffing.onb_verify_rtw', 'Verify Right to Work')}</Btn>
            <Btn onClick={paperworkComplete} busy={busy} testId="btn-paperwork-complete" primary>{t('staffing.onb_mark_paperwork', 'Mark Paperwork Complete')}</Btn>
          </div>
        </div>
      )}

      {tab === 'checks' && (
        <ChecksPanel headers={headers} caseId={caseId} />
      )}

      {tab === 'offer' && (
        <div className="space-y-3 text-sm" style={{ color: 'var(--theme-text)' }}>
          {!offer && (
            <>
              <div className="opacity-70">{t('staffing.onb_create_offer', 'Create an offer from an approved template (paperwork must be complete):')}</div>
              <div className="grid grid-cols-2 gap-2">
                {templates.offer.map((tpl) => (
                  <button key={tpl.id} onClick={() => createOffer(tpl.id)} data-testid={`offer-tmpl-${tpl.key}`}
                    className="px-3 py-2 rounded-lg border text-left" style={{ color: 'var(--theme-text)', borderColor: 'var(--theme-border)' }}>
                    {tpl.title}{tpl.is_sample && <span className="ml-1 text-[10px] text-amber-300">{t('staffing.onb_sample', 'SAMPLE')}</span>}
                  </button>
                ))}
              </div>
            </>
          )}
          {offer && (
            <>
              <div className="flex items-center gap-2"><Pill tone="blue">{offer.status}</Pill>{offer.conditional && <Pill tone="amber">{t('staffing.onb_conditional', 'Conditional')}</Pill>}
                <button onClick={() => openPdf(`${API}/staff-onboarding/cases/${caseId}/offer.pdf`, headers)} data-testid="btn-offer-pdf"
                  className="ml-auto inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border" style={{ color: 'var(--theme-text)', borderColor: 'var(--theme-border)' }}>
                  <Download size={13} /> {t('staffing.onb_pdf', 'PDF')}</button></div>
              <pre className="whitespace-pre-wrap p-3 rounded-lg text-xs max-h-64 overflow-auto" data-testid="offer-preview"
                style={{ background: 'var(--theme-surface)' }}>{offer.rendered}</pre>
              <div className="flex gap-2 flex-wrap">
                {offer.status === 'draft' && <Btn onClick={approveOffer} busy={busy} testId="btn-approve-offer">{t('staffing.onb_approve', 'Approve')}</Btn>}
                {(offer.status === 'approved') && <Btn onClick={issueOffer} busy={busy} testId="btn-issue-offer" primary>{t('staffing.onb_issue_portal', 'Issue to portal')}</Btn>}
                {offer.status === 'issued' && <Pill tone="amber">{t('staffing.onb_awaiting_response', 'Awaiting recruit response')}</Pill>}
                {offer.status === 'accepted' && <Pill tone="green">{t('staffing.onb_accepted', 'Accepted ✓')}</Pill>}
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
                ? <div className="text-amber-300">{t('staffing.onb_offer_first', 'The offer must be accepted before creating the contract.')}</div>
                : <>
                    <div className="opacity-70">{t('staffing.onb_create_contract', 'Create the contract from the accepted offer:')}</div>
                    <div className="grid grid-cols-2 gap-2">
                      {templates.contract.map((tpl) => (
                        <button key={tpl.id} onClick={() => createContract(tpl.id)} data-testid={`contract-tmpl-${tpl.key}`}
                          className="px-3 py-2 rounded-lg border text-left" style={{ color: 'var(--theme-text)', borderColor: 'var(--theme-border)' }}>
                          {tpl.title}{tpl.is_sample && <span className="ml-1 text-[10px] text-amber-300">{t('staffing.onb_sample', 'SAMPLE')}</span>}
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
                  ? <Pill tone="red">{t('staffing.onb_contract_differs', 'Contract differs from offer')} ({contract.differences.length})</Pill>
                  : <Pill tone="green">{t('staffing.onb_matches_offer', 'Matches accepted offer')}</Pill>}
                <button onClick={() => openPdf(`${API}/staff-onboarding/cases/${caseId}/contract.pdf`, headers)} data-testid="btn-contract-pdf"
                  className="ml-auto inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border" style={{ color: 'var(--theme-text)', borderColor: 'var(--theme-border)' }}>
                  <Download size={13} /> {t('staffing.onb_pdf', 'PDF')}</button></div>
              <pre className="whitespace-pre-wrap p-3 rounded-lg text-xs max-h-64 overflow-auto" data-testid="contract-preview"
                style={{ background: 'var(--theme-surface)' }}>{contract.rendered}</pre>
              <div className="flex gap-2 flex-wrap">
                {contract.status === 'draft' && <Btn onClick={approveContract} busy={busy} testId="btn-approve-contract">{t('staffing.onb_approve', 'Approve')}</Btn>}
                {contract.status === 'approved' && <Btn onClick={issueContract} busy={busy} testId="btn-issue-contract" primary>{t('staffing.onb_issue_portal', 'Issue to portal')}</Btn>}
                {contract.status === 'issued' && <Pill tone="amber">{t('staffing.onb_awaiting_signature', 'Awaiting recruit signature')}</Pill>}
                {(contract.status === 'employee_signed' || c.status === 'awaiting_employer_signature') && <Btn onClick={countersign} busy={busy} testId="btn-countersign" primary>{t('staffing.onb_employer_countersign', 'Employer countersign')}</Btn>}
                {contract.status === 'fully_signed' && <Pill tone="green">{t('staffing.onb_fully_signed', 'Fully signed & locked ✓')}</Pill>}
              </div>
              <div className="pt-1">
                <Btn onClick={aiConsistency} busy={aiBusy === 'cons'} testId="btn-ai-consistency"><ShieldAlert size={13} /> {t('staffing.onb_ai_consistency', 'AI consistency check')}</Btn>
                {consResult && (
                  <div className="mt-2 p-3 rounded-lg text-xs" data-testid="ai-consistency-result" style={{ background: 'var(--theme-surface)' }}>
                    {consResult.error ? <span className="text-red-400">{consResult.error}</span> : (
                      <>
                        <div className="flex items-center gap-2 mb-1">{t('staffing.onb_risk', 'Risk:')}
                          <Pill tone={consResult.risk_level === 'high' ? 'red' : consResult.risk_level === 'medium' ? 'amber' : 'green'}>{consResult.risk_level || 'n/a'}</Pill></div>
                        <div className="opacity-80">{consResult.summary}</div>
                        {(consResult.inconsistencies || []).map((x, i) => (
                          <div key={i} className="opacity-70 mt-1">• <b>{x.field}</b>: {t('staffing.onb_offer_lc', 'offer')} “{x.offer}” {t('staffing.onb_vs_contract', 'vs contract')} “{x.contract}” — {x.note}</div>
                        ))}
                      </>
                    )}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {tab === 'activate' && (
        <div className="space-y-4">
          <ActivatePanel headers={headers} caseId={caseId} onActivate={activate} busy={busy} status={c.status} />
          <LineManagerPanel headers={headers} caseId={caseId} />
        </div>
      )}

      {tab === 'audit' && (
        <div className="space-y-1.5 text-sm max-h-96 overflow-auto" data-testid="audit-trail" style={{ color: 'var(--theme-text)' }}>
          {audit.length === 0 && <div className="opacity-60">{t('staffing.onb_no_events', 'No events.')}</div>}
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
  const { t } = useTranslation();
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
        ? <Pill tone="green">{t('staffing.onb_activated_pill', 'Employee activated — staff portal enabled ✓')}</Pill>
        : <Btn onClick={onActivate} busy={busy} testId="btn-activate" primary disabled={!st?.ready}>{t('staffing.onb_activate_member', 'Activate Staff Member')}</Btn>}
    </div>
  );
}

function LineManagerPanel({ headers, caseId }) {
  const { t } = useTranslation();
  const [managers, setManagers] = useState([]);
  const [current, setCurrent] = useState(null);
  const [sel, setSel] = useState('');
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState(false);
  useEffect(() => {
    axios.get(`${API}/staff-onboarding/managers`, { headers }).then(r => setManagers(r.data.managers || [])).catch(() => {});
    axios.get(`${API}/staff-onboarding/cases/${caseId}/line-manager`, { headers })
      .then(r => { setCurrent(r.data); setSel(r.data.line_manager_staff_id || ''); }).catch(() => {});
  }, [caseId, headers]);
  const save = async () => {
    if (!sel) return;
    setBusy(true); setOk(false);
    try {
      const r = await axios.post(`${API}/staff-onboarding/cases/${caseId}/line-manager`, { line_manager_staff_id: sel }, { headers });
      setCurrent({ line_manager_staff_id: sel, line_manager_name: r.data.line_manager_name }); setOk(true);
    } finally { setBusy(false); }
  };
  return (
    <div className="rounded-xl p-4 border" style={{ borderColor: 'var(--theme-border)' }} data-testid="line-manager-panel">
      <div className="text-sm font-semibold mb-1" style={{ color: 'var(--theme-text)' }}>{t('staffing.onb_line_manager_access', 'Line manager (system access)')}</div>
      <p className="text-xs mb-3" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.onb_line_manager_note', 'Assign a line manager — they approve which modules this employee can use, in Staffing → People → Team Access.')}</p>
      <div className="flex flex-wrap items-center gap-2">
        <select value={sel} onChange={(e) => setSel(e.target.value)} data-testid="line-manager-select"
          className="rounded-lg border px-3 py-2 text-sm" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)', color: 'var(--theme-text)' }}>
          <option value="">{t('staffing.onb_select_line_manager', 'Select a line manager…')}</option>
          {managers.map((m) => <option key={m.staff_id} value={m.staff_id}>{m.full_name}{m.role ? ` — ${m.role}` : ''}</option>)}
        </select>
        <Btn onClick={save} busy={busy} testId="line-manager-save" primary disabled={!sel}>{t('staffing.onb_assign', 'Assign')}</Btn>
        {ok && <span className="text-xs text-emerald-400" data-testid="line-manager-ok">{t('staffing.onb_assigned', 'Assigned ✓')}</span>}
      </div>
      {current?.line_manager_name && !ok && <div className="text-xs mt-2" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.onb_current', 'Current:')} {current.line_manager_name}</div>}
    </div>
  );
}

/* ───────────────── Checks: DBS + Right to Work ───────────────── */
function ChecksPanel({ headers, caseId }) {
  const { t } = useTranslation();
  const [opts, setOpts] = useState(null);
  const [state, setState] = useState(null);
  const [providers, setProviders] = useState([]);
  const [busy, setBusy] = useState('');
  const [msg, setMsg] = useState('');
  const [rtw, setRtw] = useState({ method: 'share_code', result: 'verified', document_type: '', share_code: '', expiry: '', notes: '', provider: 'manual', provider_reference: '' });
  const [dbs, setDbs] = useState({ level: 'basic', status: 'requested', certificate_number: '', issue_date: '', notes: '', provider: 'manual', provider_reference: '' });

  const load = useCallback(async () => {
    const [o, s, p] = await Promise.all([
      axios.get(`${API}/staff-onboarding/checks/options`, { headers }),
      axios.get(`${API}/staff-onboarding/cases/${caseId}/checks`, { headers }),
      axios.get(`${API}/staff-onboarding/verification/providers`, { headers }).catch(() => ({ data: { providers: [] } })),
    ]);
    setOpts(o.data); setState(s.data); setProviders(p.data.providers || []);
    if (s.data.right_to_work) setRtw((pv) => ({ ...pv, ...pick(s.data.right_to_work, ['result', 'document_type', 'share_code', 'expiry', 'notes', 'provider', 'provider_reference']), method: s.data.right_to_work.check_method || pv.method }));
    if (s.data.dbs) setDbs((pv) => ({ ...pv, ...pick(s.data.dbs, ['level', 'status', 'certificate_number', 'issue_date', 'notes', 'provider', 'provider_reference']) }));
  }, [caseId, headers]);
  useEffect(() => { load(); }, [load]);

  const run = async (fn, ok) => { setBusy(ok); setMsg(''); try { await fn(); setMsg(ok); await load(); } catch (e) { setMsg('⚠ ' + (e?.response?.data?.detail || t('staffing.onb_failed', 'Failed'))); } finally { setBusy(''); } };
  const saveRtw = () => run(() => axios.post(`${API}/staff-onboarding/cases/${caseId}/right-to-work`, rtw, { headers }), t('staffing.onb_rtw_saved', 'Right to Work saved'));
  const saveDbs = () => run(() => axios.post(`${API}/staff-onboarding/cases/${caseId}/dbs`, dbs, { headers }), t('staffing.onb_dbs_saved', 'DBS check saved'));
  const toggleReq = (v) => run(() => axios.post(`${API}/staff-onboarding/cases/${caseId}/dbs-required?required=${v}`, {}, { headers }), v ? t('staffing.onb_dbs_required', 'DBS marked required') : t('staffing.onb_dbs_not_required', 'DBS not required'));

  if (!opts || !state) return <Loader2 className="animate-spin" style={{ color: 'var(--theme-text)' }} />;
  const cur = state.right_to_work, curD = state.dbs;

  return (
    <div className="space-y-5 text-sm" style={{ color: 'var(--theme-text)' }} data-testid="checks-panel">
      {msg && <div className="text-xs px-3 py-2 rounded-lg" style={{ background: 'var(--theme-surface)' }} data-testid="checks-msg">{msg}</div>}

      {/* Right to Work */}
      <div className="rounded-xl border p-4" style={surface}>
        <div className="flex items-center gap-2 mb-3"><ShieldCheck size={16} className="text-cyan-400" />
          <span className="font-semibold">{t('staffing.onb_rtw_title', 'Right to Work')}</span>
          {cur && <Pill tone={['verified', 'time_limited'].includes(cur.result) ? 'green' : cur.result === 'follow_up' ? 'amber' : 'red'}>{cur.result}</Pill>}
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Select label={t('staffing.onb_method', 'Method')} testId="rtw-method" value={rtw.method} onChange={(v) => setRtw((p) => ({ ...p, method: v }))} options={opts.rtw_methods} />
          <Select label={t('staffing.onb_result', 'Result')} testId="rtw-result" value={rtw.result} onChange={(v) => setRtw((p) => ({ ...p, result: v }))} options={opts.rtw_results} />
          <TextIn label={t('staffing.onb_doc_type', 'Document type')} testId="rtw-doc" value={rtw.document_type} onChange={(v) => setRtw((p) => ({ ...p, document_type: v }))} />
          <TextIn label={t('staffing.onb_share_code', 'Share code')} testId="rtw-share" value={rtw.share_code} onChange={(v) => setRtw((p) => ({ ...p, share_code: v }))} />
          <TextIn label={t('staffing.onb_expiry_tl', 'Expiry (if time-limited)')} testId="rtw-expiry" type="date" value={rtw.expiry} onChange={(v) => setRtw((p) => ({ ...p, expiry: v }))} />
          <Select label={t('staffing.onb_provider', 'Provider')} testId="rtw-provider" value={rtw.provider} onChange={(v) => setRtw((p) => ({ ...p, provider: v }))} options={providers.filter((p) => p.types.includes('rtw')).map((p) => ({ id: p.key, label: p.name + (p.configured ? '' : ` ${t('staffing.onb_manual_paren', '(manual)')}`) }))} />
          <TextIn label={t('staffing.onb_provider_ref', 'Provider reference')} testId="rtw-provider-ref" value={rtw.provider_reference} onChange={(v) => setRtw((p) => ({ ...p, provider_reference: v }))} />
          <TextIn label={t('staffing.onb_notes', 'Notes')} testId="rtw-notes" value={rtw.notes} onChange={(v) => setRtw((p) => ({ ...p, notes: v }))} />
        </div>
        <Btn onClick={saveRtw} busy={busy === t('staffing.onb_rtw_saved', 'Right to Work saved')} testId="btn-save-rtw" primary>{t('staffing.onb_save_rtw', 'Save Right to Work')}</Btn>
      </div>

      {/* DBS */}
      <div className="rounded-xl border p-4" style={surface}>
        <div className="flex items-center gap-2 mb-3"><ShieldAlert size={16} className="text-cyan-400" />
          <span className="font-semibold">{t('staffing.onb_dbs_title', 'DBS (Disclosure & Barring)')}</span>
          {curD && <Pill tone={curD.status === 'clear' ? 'green' : curD.status === 'not_clear' ? 'red' : 'amber'}>{curD.status}</Pill>}
          <label className="ml-auto inline-flex items-center gap-2 text-xs cursor-pointer" data-testid="dbs-required-toggle">
            <input type="checkbox" checked={!!state.dbs_required} onChange={(e) => toggleReq(e.target.checked)} />
            {t('staffing.onb_required_role', 'Required for this role')}
          </label>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Select label={t('staffing.onb_level', 'Level')} testId="dbs-level" value={dbs.level} onChange={(v) => setDbs((p) => ({ ...p, level: v }))} options={opts.dbs_levels} />
          <Select label={t('staffing.onb_status_label', 'Status')} testId="dbs-status" value={dbs.status} onChange={(v) => setDbs((p) => ({ ...p, status: v }))} options={opts.dbs_statuses} />
          <TextIn label={t('staffing.onb_cert_number', 'Certificate number')} testId="dbs-cert" value={dbs.certificate_number} onChange={(v) => setDbs((p) => ({ ...p, certificate_number: v }))} />
          <TextIn label={t('staffing.onb_issue_date', 'Issue date')} testId="dbs-issue" type="date" value={dbs.issue_date} onChange={(v) => setDbs((p) => ({ ...p, issue_date: v }))} />
          <Select label={t('staffing.onb_provider', 'Provider')} testId="dbs-provider" value={dbs.provider} onChange={(v) => setDbs((p) => ({ ...p, provider: v }))} options={providers.filter((p) => p.types.includes('dbs')).map((p) => ({ id: p.key, label: p.name + (p.configured ? '' : ` ${t('staffing.onb_manual_paren', '(manual)')}`) }))} />
          <TextIn label={t('staffing.onb_provider_ref', 'Provider reference')} testId="dbs-provider-ref" value={dbs.provider_reference} onChange={(v) => setDbs((p) => ({ ...p, provider_reference: v }))} />
          <TextIn label={t('staffing.onb_notes', 'Notes')} testId="dbs-notes" value={dbs.notes} onChange={(v) => setDbs((p) => ({ ...p, notes: v }))} />
        </div>
        <Btn onClick={saveDbs} busy={busy === t('staffing.onb_dbs_saved', 'DBS check saved')} testId="btn-save-dbs" primary>{t('staffing.onb_save_dbs', 'Save DBS Check')}</Btn>
      </div>
    </div>
  );
}

function pick(o, keys) { const r = {}; keys.forEach((k) => { if (o[k] != null) r[k] = o[k]; }); return r; }

function Select({ label, value, onChange, options, testId }) {
  return (
    <label className="block"><span className="text-xs opacity-70" style={{ color: 'var(--theme-text)' }}>{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)} data-testid={testId}
        className="mt-1 w-full rounded-lg px-3 py-2 text-sm border bg-transparent"
        style={{ color: 'var(--theme-text)', borderColor: 'var(--theme-border)' }}>
        {options.map((o) => <option key={o.id} value={o.id} style={{ color: '#111' }}>{o.label}</option>)}
      </select></label>
  );
}
function TextIn({ label, value, onChange, testId, type = 'text' }) {
  return (
    <label className="block"><span className="text-xs opacity-70" style={{ color: 'var(--theme-text)' }}>{label}</span>
      <input type={type} value={value || ''} onChange={(e) => onChange(e.target.value)} data-testid={testId}
        className="mt-1 w-full rounded-lg px-3 py-2 text-sm border bg-transparent"
        style={{ color: 'var(--theme-text)', borderColor: 'var(--theme-border)' }} /></label>
  );
}

/* ───────────────── Template Builder (offer & contract) ───────────────── */
function TemplateManager({ headers, onClose }) {
  const { t } = useTranslation();
  const [kind, setKind] = useState('offer');
  const [templates, setTemplates] = useState({ offer: [], contract: [] });
  const [fields, setFields] = useState([]);
  const [sel, setSel] = useState(null);
  const [draft, setDraft] = useState({ title: '', target_roles: '', body: '' });
  const [preview, setPreview] = useState('');
  const [busy, setBusy] = useState('');
  const [msg, setMsg] = useState('');
  const taRef = useRef(null);

  const load = useCallback(async () => {
    const [tRes, f] = await Promise.all([
      axios.get(`${API}/staff-onboarding/templates`, { headers }),
      axios.get(`${API}/staff-onboarding/merge-fields`, { headers }),
    ]);
    setTemplates({ offer: tRes.data.offer || [], contract: tRes.data.contract || [] });
    setFields(f.data.fields || []);
  }, [headers]);
  useEffect(() => { load(); }, [load]);

  const openTmpl = (tpl) => { setSel(tpl); setPreview(''); setMsg(''); setDraft({ title: tpl.title || '', target_roles: (tpl.target_roles || []).join(', '), body: tpl.body || '' }); };
  const newTmpl = () => { setSel({ id: null, key: 'new' }); setPreview(''); setMsg(''); setDraft({ title: '', target_roles: '', body: kind === 'offer' ? 'Dear {{preferred_name}},\n\n' : 'CONTRACT OF EMPLOYMENT\n\n' }); };

  const insertField = (token) => {
    const ta = taRef.current;
    if (!ta) { setDraft((p) => ({ ...p, body: p.body + token })); return; }
    const s = ta.selectionStart, e = ta.selectionEnd;
    const nv = draft.body.slice(0, s) + token + draft.body.slice(e);
    setDraft((p) => ({ ...p, body: nv }));
    setTimeout(() => { ta.focus(); ta.selectionStart = ta.selectionEnd = s + token.length; }, 0);
  };

  const doPreview = async () => {
    setBusy('preview');
    try { const r = await axios.post(`${API}/staff-onboarding/templates/preview`, { body: draft.body }, { headers }); setPreview(r.data.rendered); }
    finally { setBusy(''); }
  };
  const save = async () => {
    setBusy('save'); setMsg('');
    const payload = { title: draft.title, target_roles: draft.target_roles.split(',').map((s) => s.trim()).filter(Boolean), body: draft.body };
    try {
      if (sel?.id) await axios.put(`${API}/staff-onboarding/templates/${kind}/${sel.id}`, payload, { headers });
      else await axios.post(`${API}/staff-onboarding/templates/${kind}`, payload, { headers });
      setMsg(t('staffing.onb_saved', 'Saved ✓')); await load(); setSel(null);
    } catch (e) { setMsg('⚠ ' + (e?.response?.data?.detail || t('staffing.onb_save_failed', 'Save failed'))); } finally { setBusy(''); }
  };
  const resetDefaults = async () => {
    setBusy('reset');
    try { const r = await axios.post(`${API}/staff-onboarding/templates/reset-defaults`, {}, { headers }); setMsg(`${t('staffing.onb_reset', 'Reset')} ${r.data.reset} ${t('staffing.onb_builtin_templates', 'built-in templates')}`); await load(); }
    finally { setBusy(''); }
  };

  const list = templates[kind] || [];

  return (
    <Modal onClose={onClose} title={t('staffing.onb_templates_title', 'Offer & Contract Templates')} testId="template-manager" wide>
      <div className="flex items-center gap-2 mb-3">
        {['offer', 'contract'].map((k) => (
          <button key={k} onClick={() => { setKind(k); setSel(null); }} data-testid={`tmpl-kind-${k}`}
            className={`px-3 py-1.5 rounded-lg text-sm capitalize ${kind === k ? 'bg-cyan-500/20 text-cyan-300' : 'opacity-70'}`}
            style={{ color: kind === k ? undefined : 'var(--theme-text)' }}>{k === 'offer' ? t('staffing.onb_offer_letters', 'offer letters') : t('staffing.onb_contract_letters', 'contract letters')}</button>
        ))}
        <button onClick={newTmpl} data-testid="tmpl-new"
          className="ml-auto inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border" style={{ color: 'var(--theme-text)', borderColor: 'var(--theme-border)' }}><Plus size={13} /> {t('staffing.onb_new', 'New')}</button>
        <button onClick={resetDefaults} disabled={busy === 'reset'} data-testid="tmpl-reset"
          className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border" style={{ color: 'var(--theme-text)', borderColor: 'var(--theme-border)' }}><RotateCcw size={13} /> {t('staffing.onb_reset_defaults', 'Reset defaults')}</button>
      </div>
      {msg && <div className="mb-3 text-xs px-3 py-2 rounded-lg" data-testid="tmpl-msg" style={{ background: 'var(--theme-surface)', color: 'var(--theme-text)' }}>{msg}</div>}

      {!sel ? (
        <div className="space-y-2" data-testid="tmpl-list">
          {list.map((tpl) => (
            <button key={tpl.id} onClick={() => openTmpl(tpl)} data-testid={`tmpl-row-${tpl.key}`}
              className="w-full text-left px-3 py-2.5 rounded-lg border flex items-center justify-between gap-2 hover:bg-white/[0.03]" style={surface}>
              <div>
                <div className="font-medium" style={{ color: 'var(--theme-text)' }}>{tpl.title}
                  {tpl.is_sample && <span className="ml-2 text-[10px] text-amber-300">{t('staffing.onb_placeholder', 'PLACEHOLDER')}</span>}</div>
                <div className="text-xs opacity-60" style={{ color: 'var(--theme-text)' }}>{(tpl.target_roles || []).join(', ') || t('staffing.onb_all_roles', 'all roles')} · v{tpl.version}</div>
              </div>
              <Pencil size={14} style={{ color: 'var(--theme-text)' }} />
            </button>
          ))}
        </div>
      ) : (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <TextIn label={t('staffing.onb_template_title', 'Template title')} testId="tmpl-title" value={draft.title} onChange={(v) => setDraft((p) => ({ ...p, title: v }))} />
            <TextIn label={t('staffing.onb_target_roles', 'Target roles (comma separated)')} testId="tmpl-roles" value={draft.target_roles} onChange={(v) => setDraft((p) => ({ ...p, target_roles: v }))} />
          </div>
          <div>
            <div className="text-xs opacity-70 mb-1" style={{ color: 'var(--theme-text)' }}>{t('staffing.onb_merge_fields', 'Merge fields (click to insert)')}</div>
            <div className="flex flex-wrap gap-1.5" data-testid="tmpl-merge-fields">
              {fields.map((f) => (
                <button key={f.key} onClick={() => insertField(f.token)} data-testid={`merge-${f.key}`} title={f.label}
                  className="text-[11px] px-2 py-1 rounded-md border" style={{ color: 'var(--theme-text)', borderColor: 'var(--theme-border)' }}>{f.token}</button>
              ))}
            </div>
          </div>
          <label className="block">
            <span className="text-xs opacity-70" style={{ color: 'var(--theme-text)' }}>{t('staffing.onb_doc_body', 'Document body')}</span>
            <textarea ref={taRef} value={draft.body} onChange={(e) => setDraft((p) => ({ ...p, body: e.target.value }))} data-testid="tmpl-body"
              rows={14} className="mt-1 w-full rounded-lg px-3 py-2 text-xs font-mono border bg-transparent"
              style={{ color: 'var(--theme-text)', borderColor: 'var(--theme-border)' }} />
          </label>
          <div className="flex gap-2 flex-wrap">
            <Btn onClick={() => setSel(null)} testId="tmpl-back">{t('staffing.onb_back', 'Back')}</Btn>
            <Btn onClick={doPreview} busy={busy === 'preview'} testId="tmpl-preview-btn">{t('staffing.onb_preview', 'Preview')}</Btn>
            <Btn onClick={save} busy={busy === 'save'} testId="tmpl-save" primary>{t('staffing.onb_save_template', 'Save template')}</Btn>
          </div>
          {preview && (
            <pre className="whitespace-pre-wrap p-3 rounded-lg text-xs max-h-64 overflow-auto" data-testid="tmpl-preview"
              style={{ background: 'var(--theme-surface)', color: 'var(--theme-text)' }}>{preview}</pre>
          )}
        </div>
      )}
    </Modal>
  );
}

/* ───────────────── Onboarding settings (pack email) ───────────────── */
function PackSettings({ headers, onClose }) {
  const { t } = useTranslation();
  const [s, setS] = useState(null);
  const [recips, setRecips] = useState('');
  const [enabled, setEnabled] = useState(true);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');

  useEffect(() => {
    axios.get(`${API}/staff-onboarding/settings`, { headers }).then((r) => {
      setS(r.data); setEnabled(r.data.email_pack_on_activation !== false);
      setRecips((r.data.pack_recipient_emails || []).join('\n'));
    });
  }, [headers]);

  const save = async () => {
    setBusy(true); setMsg('');
    const list = recips.split(/[\n,;]+/).map((x) => x.trim()).filter((x) => x.includes('@'));
    try {
      const r = await axios.put(`${API}/staff-onboarding/settings`,
        { email_pack_on_activation: enabled, pack_recipient_emails: list }, { headers });
      setRecips((r.data.pack_recipient_emails || []).join('\n')); setMsg(t('staffing.onb_saved', 'Saved ✓'));
    } catch (e) { setMsg('⚠ ' + (e?.response?.data?.detail || t('staffing.onb_save_failed', 'Save failed'))); } finally { setBusy(false); }
  };

  if (!s) return null;
  return (
    <Modal onClose={onClose} title={t('staffing.onb_settings_title', 'Onboarding settings')} testId="pack-settings">
      <div className="space-y-4 text-sm" style={{ color: 'var(--theme-text)' }}>
        <label className="flex items-start gap-3 cursor-pointer" data-testid="pack-email-toggle">
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} className="mt-1" />
          <span><span className="font-medium flex items-center gap-1.5"><Mail size={14} /> {t('staffing.onb_email_pack', 'Email the Onboarding Pack on activation')}</span>
            <span className="block opacity-60 text-xs mt-0.5">{t('staffing.onb_email_pack_note', 'When an employee is activated, the audit-ready Onboarding Pack PDF is emailed to the recipients below (plus the person activating).')}</span></span>
        </label>
        <label className="block">
          <span className="text-xs opacity-70">{t('staffing.onb_recipients', 'HR / payroll recipients (one per line)')}</span>
          <textarea value={recips} onChange={(e) => setRecips(e.target.value)} data-testid="pack-recipients"
            rows={5} placeholder="hr@company.com&#10;payroll@company.com"
            className="mt-1 w-full rounded-lg px-3 py-2 text-sm border bg-transparent"
            style={{ color: 'var(--theme-text)', borderColor: 'var(--theme-border)' }} />
        </label>
        {msg && <div className="text-xs" data-testid="pack-settings-msg">{msg}</div>}
        <div className="flex gap-2">
          <Btn onClick={save} busy={busy} testId="pack-settings-save" primary>{t('staffing.onb_save_settings', 'Save settings')}</Btn>
          <Btn onClick={onClose} testId="pack-settings-close">{t('staffing.onb_close', 'Close')}</Btn>
        </div>

        <div className="pt-4 border-t" style={{ borderColor: 'var(--theme-border)' }}>
          <DocsManager headers={headers} />
        </div>
      </div>
    </Modal>
  );
}

/* Company policies & agreements — upload your own docs; AI detects signature points. */
function DocsManager({ headers }) {
  const { t } = useTranslation();
  const [docs, setDocs] = useState({ policies: [], agreements: [] });
  const [newTitle, setNewTitle] = useState({ policies: '', agreements: '' });
  const [busy, setBusy] = useState('');
  const [ai, setAi] = useState({});

  const load = useCallback(async () => {
    const r = await axios.get(`${API}/staff-onboarding/templates`, { headers });
    setDocs({ policies: r.data.policies || [], agreements: r.data.agreements || [] });
  }, [headers]);
  useEffect(() => { load(); }, [load]);

  const add = async (kind) => {
    const title = newTitle[kind].trim(); if (!title) return;
    setBusy(`add-${kind}`);
    try { await axios.post(`${API}/staff-onboarding/${kind}`, { title }, { headers }); setNewTitle((p) => ({ ...p, [kind]: '' })); await load(); }
    finally { setBusy(''); }
  };
  const remove = async (kind, key) => {
    setBusy(`del-${key}`);
    try { await axios.delete(`${API}/staff-onboarding/${kind}/${key}`, { headers }); await load(); }
    finally { setBusy(''); }
  };
  const upload = async (kind, key, e) => {
    const file = e.target.files?.[0]; if (!file) return;
    setBusy(`up-${key}`); setAi((p) => ({ ...p, [key]: null }));
    const fd = new FormData(); fd.append('file', file);
    try {
      const r = await axios.post(`${API}/staff-onboarding/${kind}/${key}/upload`, fd, { headers });
      setAi((p) => ({ ...p, [key]: r.data.ai })); await load();
    } finally { setBusy(''); }
  };

  const renderList = (kind, label) => (
    <div>
      <div className="font-semibold text-sm mb-2" style={{ color: 'var(--theme-text)' }}>{label}</div>
      <div className="space-y-2">
        {docs[kind].map((d) => (
          <div key={d.key} className="rounded-lg border p-2.5" style={surface} data-testid={`doc-row-${d.key}`}>
            <div className="flex items-center gap-2">
              <span className="text-sm flex-1" style={{ color: 'var(--theme-text)' }}>{d.title}
                {d.is_sample && <span className="ml-1 text-[10px] text-amber-400">{t('staffing.onb_sample', 'SAMPLE')}</span>}
                {d.pdf_filename && <span className="ml-1 text-[10px] text-emerald-400">{t('staffing.onb_pdf_ok', 'PDF ✓')}</span>}</span>
              <label className="text-xs px-2 py-1 rounded-md border cursor-pointer" style={{ color: 'var(--theme-text)', borderColor: 'var(--theme-border)' }} data-testid={`doc-upload-${d.key}`}>
                {busy === `up-${d.key}` ? t('staffing.onb_analysing', 'Analysing…') : t('staffing.onb_upload_pdf', 'Upload PDF')}
                <input type="file" accept="application/pdf" className="hidden" onChange={(e) => upload(kind, d.key, e)} />
              </label>
              <button onClick={() => remove(kind, d.key)} disabled={busy === `del-${d.key}`} data-testid={`doc-del-${d.key}`}
                className="text-slate-400 hover:text-red-400"><X size={15} /></button>
            </div>
            {(ai[d.key] || d.signature_fields?.length > 0) && (
              <div className="mt-1.5 text-[11px]" style={{ color: 'var(--theme-text)', opacity: 0.7 }} data-testid={`doc-ai-${d.key}`}>
                {ai[d.key]?.summary || (d.signature_fields?.length ? t('staffing.onb_sig_detected', 'Signature points detected on upload.') : '')}
                {(ai[d.key]?.signature_fields || d.signature_fields || []).length > 0 &&
                  <span className="ml-1">{t('staffing.onb_sig_points', 'Signature points:')} {(ai[d.key]?.signature_fields || d.signature_fields).map((f) => f.label).join(', ')}</span>}
              </div>
            )}
          </div>
        ))}
      </div>
      <div className="flex gap-2 mt-2">
        <input value={newTitle[kind]} onChange={(e) => setNewTitle((p) => ({ ...p, [kind]: e.target.value }))} data-testid={`doc-new-${kind}`}
          placeholder={kind === 'policies' ? t('staffing.onb_new_policy', 'New policy title') : t('staffing.onb_new_agreement', 'New agreement title')}
          className="flex-1 rounded-lg px-3 py-1.5 text-sm border bg-transparent" style={{ color: 'var(--theme-text)', borderColor: 'var(--theme-border)' }} />
        <Btn onClick={() => add(kind)} busy={busy === `add-${kind}`} testId={`doc-add-${kind}`}><Plus size={13} /> {t('staffing.onb_add', 'Add')}</Btn>
      </div>
    </div>
  );

  return (
    <div className="space-y-4" data-testid="docs-manager">
      <div>
        <div className="font-semibold flex items-center gap-1.5" style={{ color: 'var(--theme-text)' }}><ScrollText size={15} /> {t('staffing.onb_policies_agreements', 'Your policies & agreements')}</div>
        <div className="text-xs opacity-60 mb-3" style={{ color: 'var(--theme-text)' }}>{t('staffing.onb_policies_note', "Upload your company's own documents. When you upload a PDF, AI reads it and flags where signatures/initials are required.")}</div>
      </div>
      {renderList('policies', t('staffing.onb_policies', 'Policies (read & acknowledge)'))}
      {renderList('agreements', t('staffing.onb_agreements', 'Agreements (require signature)'))}
    </div>
  );
}

/* ───────────────── shared UI ───────────────── */
function Modal({ children, onClose, title, testId, wide }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = prev; };
  }, [onClose]);
  return createPortal(
    <div className="fixed inset-0 z-[300] flex items-start justify-center p-4 overflow-y-auto"
      style={{ background: 'rgba(0,0,0,0.7)' }} data-testid={testId}
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={`w-full ${wide ? 'max-w-3xl' : 'max-w-2xl'} rounded-2xl border my-8 max-h-[calc(100vh-4rem)] overflow-y-auto`}
        style={{ background: 'var(--theme-bg, #0f1417)', borderColor: 'var(--theme-border)' }}>
        <div className="flex items-center justify-between px-5 py-3 border-b sticky top-0 z-10"
          style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-bg, #0f1417)' }}>
          <h3 className="font-bold" style={{ color: 'var(--theme-text)' }}>{title}</h3>
          <button onClick={onClose} data-testid="modal-close"><X size={18} style={{ color: 'var(--theme-text)' }} /></button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>,
    document.body,
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
