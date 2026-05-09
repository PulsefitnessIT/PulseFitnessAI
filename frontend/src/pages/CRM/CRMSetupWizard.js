/**
 * CRM 4-step Setup Wizard — parity with Memberships SetupWizard.
 *
 * Mounted at /crm/setup. Steps: pipeline → contact → deal → done.
 * Resumable via the org doc's `crm_setup_step` cursor.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import {
  CheckCircle2, ChevronRight, ChevronLeft, Sparkles, Loader2,
  TrendingUp, UserPlus, Target, X,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const STEPS = [
  { id: 'pipeline', label: 'Pipeline', icon: Target },
  { id: 'contacts', label: 'Contact',  icon: UserPlus },
  { id: 'deal',     label: 'First deal', icon: TrendingUp },
  { id: 'done',     label: 'Done',    icon: CheckCircle2 },
];

const DEFAULT_STAGES = ['Lead', 'Qualified', 'Proposal', 'Negotiation', 'Closed Won'];

export default function CRMSetupWizard() {
  const navigate = useNavigate();
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);

  const [stepIdx, setStepIdx] = useState(0);
  const [status, setStatus]   = useState(null);
  const [busy, setBusy]       = useState(false);

  // Form state
  const [pipelineName, setPipelineName] = useState('Sales pipeline');
  const [stages, setStages]             = useState(DEFAULT_STAGES);
  const [contact, setContact] = useState({ full_name: '', email: '', phone: '', company: '' });
  const [createdContactId, setCreatedContactId] = useState(null);
  const [deal, setDeal] = useState({ title: '', value_pence: 0 });

  const refresh = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/crm/setup/status`, { headers });
      setStatus(data);
      const cursor = data.organization?.crm_setup_step || 'pipeline';
      const idx = Math.max(0, STEPS.findIndex((s) => s.id === cursor));
      setStepIdx(idx);
    } catch (e) {
      notifyApiError(notify, e, 'Failed to load CRM setup');
    }
  }, [headers]);
  useEffect(() => { refresh(); }, [refresh]);

  const skip = async () => {
    try {
      await axios.post(`${API}/crm/setup/skip`, {}, { headers });
      navigate('/crm');
    } catch (e) {
      notifyApiError(notify, e, 'Skip failed');
    }
  };

  const savePipeline = async () => {
    setBusy(true);
    try {
      await axios.post(`${API}/crm/setup/pipeline`, { name: pipelineName, stages: stages.filter(Boolean) }, { headers });
      notify.success('Pipeline saved');
      setStepIdx(1);
    } catch (e) {
      notifyApiError(notify, e, 'Failed to save pipeline');
    }
    setBusy(false);
  };

  const saveContact = async () => {
    if (!contact.full_name.trim()) { notify.error('Full name is required'); return; }
    setBusy(true);
    try {
      const { data } = await axios.post(`${API}/crm/setup/contact`, contact, { headers });
      setCreatedContactId(data.contact_id);
      notify.success('Contact added');
      setStepIdx(2);
    } catch (e) {
      notifyApiError(notify, e, 'Failed to save contact');
    }
    setBusy(false);
  };

  const skipContact = () => setStepIdx(2);

  const saveDeal = async () => {
    if (!deal.title.trim()) { notify.error('Deal title is required'); return; }
    setBusy(true);
    try {
      await axios.post(`${API}/crm/setup/deal`, {
        title: deal.title,
        contact_id: createdContactId,
        value_pence: Math.round(parseFloat(deal.value_pence || 0) * 100),
      }, { headers });
      notify.success('Deal created');
      setStepIdx(3);
    } catch (e) {
      notifyApiError(notify, e, 'Failed to save deal');
    }
    setBusy(false);
  };

  const skipDeal = () => setStepIdx(3);

  const finish = async () => {
    setBusy(true);
    try {
      await axios.post(`${API}/crm/setup/complete`, {}, { headers });
      navigate('/crm');
    } catch (e) {
      notifyApiError(notify, e, 'Failed to complete setup');
    }
    setBusy(false);
  };

  const counts = status?.counts || {};
  const Step = STEPS[stepIdx];

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950 px-4 py-10" data-testid="crm-setup-wizard">
      <div className="max-w-2xl mx-auto">
        <div className="text-center mb-6">
          <div className="inline-flex w-14 h-14 rounded-2xl bg-gradient-to-br from-blue-500 to-violet-500 items-center justify-center text-white shadow-md mb-3">
            <Sparkles size={22} />
          </div>
          <h1 className="text-2xl font-extrabold pulse-font-heading text-zinc-900 dark:text-zinc-100">
            Set up your CRM
          </h1>
          <p className="text-sm text-zinc-600 dark:text-zinc-400 mt-1">Four quick steps. You can skip and come back later.</p>
        </div>

        {/* Step bar */}
        <div className="flex items-center justify-between mb-5">
          {STEPS.map((s, i) => {
            const Icon = s.icon;
            const on = i === stepIdx;
            const done = i < stepIdx;
            return (
              <React.Fragment key={s.id}>
                <div className="flex flex-col items-center" data-testid={`crm-setup-step-${s.id}`}>
                  <div className={`w-9 h-9 rounded-full flex items-center justify-center border-2 ${on ? 'bg-blue-600 border-blue-600 text-white' : done ? 'bg-emerald-500 border-emerald-500 text-white' : 'border-zinc-300 dark:border-zinc-700 text-zinc-400'}`}>
                    {done ? <CheckCircle2 size={16} /> : <Icon size={14} />}
                  </div>
                  <p className={`text-[10px] uppercase tracking-wider font-bold mt-1 ${on ? 'text-blue-600' : done ? 'text-emerald-600' : 'text-zinc-400'}`}>{s.label}</p>
                </div>
                {i < STEPS.length - 1 && (
                  <div className={`flex-1 h-0.5 mx-1 ${i < stepIdx ? 'bg-emerald-500' : 'bg-zinc-200 dark:bg-zinc-800'}`} />
                )}
              </React.Fragment>
            );
          })}
        </div>

        <div className="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-6 shadow-sm">
          {/* PIPELINE */}
          {Step.id === 'pipeline' && (
            <div className="space-y-4" data-testid="crm-setup-pipeline">
              <div>
                <label className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">Pipeline name</label>
                <input value={pipelineName} onChange={(e) => setPipelineName(e.target.value)}
                  className="mt-1 w-full h-10 rounded-md border border-zinc-200 dark:border-zinc-800 bg-transparent px-3 text-sm"
                  data-testid="crm-setup-pipeline-name" />
              </div>
              <div>
                <label className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">Stages (in order)</label>
                <div className="space-y-2 mt-2">
                  {stages.map((s, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <input value={s} onChange={(e) => { const n = [...stages]; n[i] = e.target.value; setStages(n); }}
                        className="flex-1 h-9 rounded-md border border-zinc-200 dark:border-zinc-800 bg-transparent px-3 text-sm"
                        data-testid={`crm-setup-stage-${i}`} />
                      <button type="button" onClick={() => setStages(stages.filter((_, j) => j !== i))} className="p-1.5 text-zinc-400 hover:text-rose-500">
                        <X size={14} />
                      </button>
                    </div>
                  ))}
                  <button type="button" onClick={() => setStages([...stages, ''])}
                    className="text-xs font-semibold text-blue-600 hover:underline" data-testid="crm-setup-stage-add">
                    + Add stage
                  </button>
                </div>
              </div>
              <div className="flex items-center justify-between pt-3 border-t border-zinc-100 dark:border-zinc-800">
                <button onClick={skip} className="text-xs text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-200" data-testid="crm-setup-skip">Skip setup</button>
                <button onClick={savePipeline} disabled={busy}
                  className="px-4 py-2 rounded-md bg-blue-600 hover:bg-blue-700 text-white text-sm font-bold disabled:opacity-50 inline-flex items-center gap-1.5"
                  data-testid="crm-setup-pipeline-save">
                  {busy ? <Loader2 size={13} className="animate-spin" /> : <ChevronRight size={13} />} Save & continue
                </button>
              </div>
            </div>
          )}

          {/* CONTACT */}
          {Step.id === 'contacts' && (
            <div className="space-y-4" data-testid="crm-setup-contact">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <Field label="Full name *" value={contact.full_name} onChange={(v) => setContact({ ...contact, full_name: v })} testId="crm-setup-contact-name" />
                <Field label="Email"        value={contact.email}     onChange={(v) => setContact({ ...contact, email: v })}      testId="crm-setup-contact-email" />
                <Field label="Phone"        value={contact.phone}     onChange={(v) => setContact({ ...contact, phone: v })}      testId="crm-setup-contact-phone" />
                <Field label="Company"      value={contact.company}   onChange={(v) => setContact({ ...contact, company: v })}    testId="crm-setup-contact-company" />
              </div>
              <div className="flex items-center justify-between pt-3 border-t border-zinc-100 dark:border-zinc-800">
                <div className="flex items-center gap-3">
                  <button onClick={() => setStepIdx(0)} className="text-xs text-zinc-500 inline-flex items-center gap-1" data-testid="crm-setup-back-1">
                    <ChevronLeft size={12} /> Back
                  </button>
                  <button onClick={skipContact} className="text-xs text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-200" data-testid="crm-setup-contact-skip">
                    Skip — I'll import later
                  </button>
                </div>
                <button onClick={saveContact} disabled={busy || !contact.full_name.trim()}
                  className="px-4 py-2 rounded-md bg-blue-600 hover:bg-blue-700 text-white text-sm font-bold disabled:opacity-50 inline-flex items-center gap-1.5"
                  data-testid="crm-setup-contact-save">
                  {busy ? <Loader2 size={13} className="animate-spin" /> : <ChevronRight size={13} />} Save & continue
                </button>
              </div>
            </div>
          )}

          {/* DEAL */}
          {Step.id === 'deal' && (
            <div className="space-y-4" data-testid="crm-setup-deal">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <Field label="Deal title *" value={deal.title} onChange={(v) => setDeal({ ...deal, title: v })} testId="crm-setup-deal-title" />
                <Field label="Value (£)" type="number" value={deal.value_pence} onChange={(v) => setDeal({ ...deal, value_pence: v })} testId="crm-setup-deal-value" />
              </div>
              <p className="text-xs text-zinc-500 dark:text-zinc-400">Drops onto the first stage of your new pipeline.</p>
              <div className="flex items-center justify-between pt-3 border-t border-zinc-100 dark:border-zinc-800">
                <div className="flex items-center gap-3">
                  <button onClick={() => setStepIdx(1)} className="text-xs text-zinc-500 inline-flex items-center gap-1" data-testid="crm-setup-back-2">
                    <ChevronLeft size={12} /> Back
                  </button>
                  <button onClick={skipDeal} className="text-xs text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-200" data-testid="crm-setup-deal-skip">
                    Skip — no deal yet
                  </button>
                </div>
                <button onClick={saveDeal} disabled={busy || !deal.title.trim()}
                  className="px-4 py-2 rounded-md bg-blue-600 hover:bg-blue-700 text-white text-sm font-bold disabled:opacity-50 inline-flex items-center gap-1.5"
                  data-testid="crm-setup-deal-save">
                  {busy ? <Loader2 size={13} className="animate-spin" /> : <ChevronRight size={13} />} Save & continue
                </button>
              </div>
            </div>
          )}

          {/* DONE */}
          {Step.id === 'done' && (
            <div className="text-center py-6" data-testid="crm-setup-done">
              <div className="inline-flex w-14 h-14 rounded-full bg-emerald-100 dark:bg-emerald-900/30 items-center justify-center text-emerald-600 mb-4">
                <CheckCircle2 size={28} />
              </div>
              <h2 className="text-xl font-bold text-zinc-900 dark:text-zinc-100 mb-1">You're all set</h2>
              <p className="text-sm text-zinc-600 dark:text-zinc-400 mb-4">
                {counts.pipelines || 0} pipeline · {counts.contacts || 0} contact{counts.contacts === 1 ? '' : 's'} · {counts.deals || 0} deal{counts.deals === 1 ? '' : 's'} created.
              </p>
              <button onClick={finish} disabled={busy}
                className="px-5 py-2.5 rounded-md bg-gradient-to-r from-blue-600 to-violet-600 text-white text-sm font-bold inline-flex items-center gap-1.5"
                data-testid="crm-setup-finish">
                {busy ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />} Open my CRM
              </button>
            </div>
          )}
        </div>

        <p className="text-center text-[10px] text-zinc-400 mt-4">
          You can re-run this wizard any time from CRM → Settings.
        </p>
      </div>
    </div>
  );
}

function Field({ label, value, onChange, type = 'text', testId }) {
  return (
    <div>
      <label className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">{label}</label>
      <input type={type} value={value} onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full h-10 rounded-md border border-zinc-200 dark:border-zinc-800 bg-transparent px-3 text-sm"
        data-testid={testId} />
    </div>
  );
}
