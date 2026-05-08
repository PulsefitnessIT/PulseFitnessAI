/**
 * GymAxis Memberships — 6-step Setup Wizard.
 *
 * First-time onboarding for a gym. Runs at /memberships/setup.
 *   1. Studio basics — name, slug, brand colour, timezone, currency, logo
 *   2. Payment method — Manual / Direct Debit (soon) / Stripe Connect (soon)
 *   3. Starter plans — 3 editable templates (can skip)
 *   4. First class — optional class template
 *   5. Invite instructors — optional
 *   6. Done — success state with the branded app URL
 *
 * Progress persists on the org doc (setup_step + setup_completed).
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import {
  CheckCircle2, ChevronRight, ChevronLeft, Sparkles, Link as LinkIcon,
  Copy, CreditCard, Banknote, Wand2, Check, X, Plus, Loader2,
} from 'lucide-react';
import { useAuth } from '@/App';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const STEPS = [
  { id: 'basics',   label: 'Studio' },
  { id: 'payment',  label: 'Payment' },
  { id: 'plans',    label: 'Plans' },
  { id: 'class',    label: 'Class' },
  { id: 'team',     label: 'Team' },
  { id: 'done',     label: 'Done' },
];

export default function SetupWizard() {
  // Iter 216aj — AuthContext does NOT expose `token` (only user/login/logout/…);
  // the previous `const { token } = useAuth()` was always undefined, which is
  // why the "OPEN WIZARD" button produced an Invalid-Token screen. Pull the
  // real token from localStorage like every other authenticated page.
  useAuth(); // still touch the context so the gate stays mounted
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  const navigate = useNavigate();
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);

  const [status, setStatus] = useState(null);
  const [stepIdx, setStepIdx] = useState(0);

  const refresh = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/memberships/setup/status`, { headers });
      setStatus(data);
      const cursor = data.organization.setup_step || 'basics';
      const idx = Math.max(0, STEPS.findIndex((s) => s.id === cursor));
      setStepIdx(idx);
    } catch { notify.error('Failed to load setup status'); }
  }, [headers]);
  useEffect(() => { refresh(); }, [refresh]);

  if (!status) return <FullPageLoader />;

  const current = STEPS[stepIdx];

  return (
    <div className="min-h-screen bg-[var(--color-surface-darker)] text-white" data-testid="mbr-setup">
      <header className="border-b border-white/10 bg-[var(--color-ink)]">
        <div className="max-w-4xl mx-auto px-6 py-5 flex items-center justify-between">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-[0.25em] text-[var(--color-brand-cyan)]">Setup</div>
            <div className="text-lg font-extrabold mt-0.5">Welcome to Memberships</div>
          </div>
          <button onClick={() => navigate('/memberships')} className="text-xs font-bold text-white/60 hover:text-white" data-testid="mbr-setup-skip">
            Skip for now
          </button>
        </div>
        <StepBar stepIdx={stepIdx} setStepIdx={(i) => i < stepIdx && setStepIdx(i)} />
      </header>
      <main className="max-w-xl mx-auto px-6 py-10">
        {current.id === 'basics'  && <StudioBasics  headers={headers} status={status} onNext={() => setStepIdx(1)} />}
        {current.id === 'payment' && <PaymentMethod headers={headers} status={status} onNext={() => setStepIdx(2)} onBack={() => setStepIdx(0)} />}
        {current.id === 'plans'   && <StarterPlans  headers={headers} status={status} onNext={refresh_then(setStepIdx, 3, refresh)} onBack={() => setStepIdx(1)} />}
        {current.id === 'class'   && <FirstClass    headers={headers} status={status} onNext={refresh_then(setStepIdx, 4, refresh)} onBack={() => setStepIdx(2)} />}
        {current.id === 'team'    && <InviteTeam    headers={headers} status={status} onNext={() => setStepIdx(5)} onBack={() => setStepIdx(3)} />}
        {current.id === 'done'    && <AllDone       headers={headers} status={status} onFinish={() => navigate('/memberships')} />}
      </main>
    </div>
  );
}

function refresh_then(setStepIdx, target, refresh) {
  return async () => { await refresh(); setStepIdx(target); };
}


/* ─────────────────── Step bar ─────────────────── */

function StepBar({ stepIdx, setStepIdx }) {
  return (
    <div className="max-w-4xl mx-auto px-6 pb-4">
      <ol className="flex items-center gap-2">
        {STEPS.map((s, i) => {
          const done = i < stepIdx;
          const active = i === stepIdx;
          return (
            <li key={s.id} className="flex-1 flex items-center gap-2">
              <button onClick={() => setStepIdx(i)} data-testid={`mbr-setup-step-${s.id}`}
                className={`flex items-center gap-2 transition ${done || active ? 'opacity-100' : 'opacity-40'}`}
                disabled={!done}>
                <span className={`w-6 h-6 rounded-full grid place-items-center text-[10px] font-extrabold ${done ? 'bg-emerald-500 text-black' : active ? 'bg-[var(--color-brand-cyan)] text-black' : 'bg-white dark:bg-zinc-900/10'}`}>
                  {done ? <Check size={12} /> : i + 1}
                </span>
                <span className={`text-[10px] font-extrabold uppercase tracking-wider ${active ? 'text-white' : 'text-white/60'}`}>{s.label}</span>
              </button>
              {i < STEPS.length - 1 && <div className="h-px flex-1 bg-white dark:bg-zinc-900/10" />}
            </li>
          );
        })}
      </ol>
    </div>
  );
}


/* ─────────────────── Step 1 — Basics ─────────────────── */

function StudioBasics({ headers, status, onNext }) {
  const org = status.organization;
  const [f, setF] = useState({
    name: org.name || '',
    slug: org.slug || '',
    primary_brand_colour: org.primary_brand_colour || 'var(--color-brand-cyan)',
    timezone: org.timezone || 'Europe/London',
    currency: org.currency || 'GBP',
    logo_url: org.logo_url || '',
  });
  const [saving, setSaving] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!f.name.trim()) { notify.error('Studio name required'); return; }
    setSaving(true);
    try {
      await axios.post(`${API}/memberships/setup/basics`, f, { headers });
      notify.success('Studio saved');
      onNext();
    } catch (err) { notifyApiError(notify, err, 'Failed'); }
    finally { setSaving(false); }
  };
  const up = (k) => (v) => setF((p) => ({ ...p, [k]: v }));

  return (
    <StepShell title="Tell us about your studio" subtitle="This shapes your member-facing app.">
      <form onSubmit={submit} className="space-y-4" data-testid="mbr-setup-basics">
        <Input label="Studio name" value={f.name} onChange={up('name')} required testid="mbr-setup-name" />
        <Input label="App URL slug" hint="Members will visit /m/YOUR-SLUG" value={f.slug} onChange={(v) => up('slug')(v.toLowerCase().replace(/[^a-z0-9-]/g, '-'))} testid="mbr-setup-slug" />
        <div className="grid grid-cols-2 gap-3">
          <Input label="Timezone" value={f.timezone} onChange={up('timezone')} testid="mbr-setup-timezone" />
          <Select label="Currency" value={f.currency} onChange={up('currency')} options={['GBP', 'EUR', 'USD']} testid="mbr-setup-currency" />
        </div>
        <div className="grid grid-cols-[1fr_auto] gap-3 items-end">
          <Input label="Logo URL (optional)" hint="Square image, 200×200+" value={f.logo_url} onChange={up('logo_url')} testid="mbr-setup-logo" />
          <label className="block">
            <span className="text-[10px] font-bold uppercase tracking-wider text-white/50">Brand colour</span>
            <input type="color" value={f.primary_brand_colour} onChange={(e) => up('primary_brand_colour')(e.target.value)} className="mt-1 h-10 w-16 rounded cursor-pointer bg-transparent" data-testid="mbr-setup-colour" />
          </label>
        </div>
        <StepActions primaryLabel="Save & continue" saving={saving} testId="mbr-setup-basics-next" />
      </form>
    </StepShell>
  );
}


/* ─────────────────── Step 2 — Payment Method ─────────────────── */

function PaymentMethod({ headers, status, onNext, onBack }) {
  const [choice, setChoice] = useState(status.organization.payment_method || 'manual');
  const [saving, setSaving] = useState(false);
  const options = [
    { id: 'manual',         label: 'Manual / Cash / Invoice',   icon: Banknote,     desc: 'Collect any way you like. Staff record payments in the app. Available now.', soon: false },
    { id: 'direct_debit',   label: 'Direct Debit (GoCardless)', icon: LinkIcon,     desc: 'Auto-collect monthly DD mandates. Recurring, bank-level fees.',             soon: true },
    { id: 'stripe_connect', label: 'Stripe Connect',            icon: CreditCard,   desc: 'Members pay card — funds land in YOUR Stripe account, not ours.',         soon: true },
  ];
  const save = async () => {
    setSaving(true);
    try {
      await axios.post(`${API}/memberships/setup/payment-method`, { payment_method: choice }, { headers });
      notify.success('Payment method saved');
      onNext();
    } catch (err) { notifyApiError(notify, err, 'Failed'); }
    finally { setSaving(false); }
  };
  return (
    <StepShell title="How will you collect from members?" subtitle="You can change this any time.">
      <div className="space-y-2" data-testid="mbr-setup-payment">
        {options.map((o) => (
          <button key={o.id} onClick={() => setChoice(o.id)} data-testid={`mbr-setup-pay-${o.id}`}
            className={`w-full text-left rounded-xl border p-4 transition flex items-start gap-3 ${choice === o.id ? 'border-[var(--color-brand-cyan)] bg-[rgb(var(--rgb-brand-cyan)/0.1)]' : 'border-white/10 bg-white dark:bg-zinc-900/[0.02] hover:border-white/20'}`}>
            <o.icon size={18} className={choice === o.id ? 'text-[var(--color-brand-cyan)]' : 'text-white/60'} />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-bold text-white text-sm">{o.label}</span>
                {o.soon && <span className="text-[9px] font-extrabold uppercase tracking-wider bg-amber-500/20 text-amber-200 px-1.5 py-0.5 rounded">Soon</span>}
              </div>
              <div className="text-xs text-white/60 mt-0.5">{o.desc}</div>
            </div>
          </button>
        ))}
      </div>
      <StepActions onBack={onBack} primaryLabel="Save & continue" onPrimary={save} saving={saving} testId="mbr-setup-payment-next" />
    </StepShell>
  );
}


/* ─────────────────── Step 3 — Starter plans ─────────────────── */

const STARTER_PLANS = [
  { name: 'Monthly Unlimited', kind: 'recurring',  billing_cycle: 'monthly', price_pence: 5000, included_classes: 'unlimited', colour: 'var(--color-brand-cyan)', display_order: 1 },
  { name: '10-Class Pack',     kind: 'class_pack', billing_cycle: 'oneoff',  price_pence: 7500, credits_count: 10, included_classes: 'credits_only', colour: 'var(--color-warning)', display_order: 2 },
  { name: 'Day Pass',          kind: 'payg',       billing_cycle: 'oneoff',  price_pence: 1200, included_classes: 'credits_only', credits_count: 1, colour: 'var(--color-success)', display_order: 3 },
];

function StarterPlans({ headers, status, onNext, onBack }) {
  const [selected, setSelected] = useState(status.counts.plans > 0 ? [] : STARTER_PLANS.map((_, i) => i));
  const [plans, setPlans] = useState(STARTER_PLANS.map((p) => ({ ...p })));
  const [saving, setSaving] = useState(false);
  const toggle = (i) => setSelected((s) => s.includes(i) ? s.filter((x) => x !== i) : [...s, i]);
  const up = (i, k) => (v) => setPlans((ps) => ps.map((p, idx) => idx === i ? { ...p, [k]: v } : p));

  const save = async () => {
    const chosen = selected.map((i) => ({ ...plans[i] }));
    setSaving(true);
    try {
      await axios.post(`${API}/memberships/setup/plans`, { plans: chosen }, { headers });
      notify.success(`${chosen.length} plans created`);
      onNext();
    } catch (err) { notifyApiError(notify, err, 'Failed'); }
    finally { setSaving(false); }
  };
  return (
    <StepShell title="Pick starter plans" subtitle="Tweak prices if you like — you can always add more later.">
      {status.counts.plans > 0 && (
        <div className="rounded-xl border border-emerald-400/30 bg-emerald-500/10 p-3 mb-4 text-xs text-emerald-200">
          <CheckCircle2 size={12} className="inline mr-1" /> You already have {status.counts.plans} plans — pick extra templates or skip ahead.
        </div>
      )}
      <div className="space-y-2" data-testid="mbr-setup-plans">
        {plans.map((p, i) => {
          const on = selected.includes(i);
          return (
            <div key={i} onClick={() => toggle(i)} data-testid={`mbr-setup-plan-${i}`}
              className={`rounded-xl border p-3.5 cursor-pointer transition ${on ? 'border-[var(--color-brand-cyan)] bg-[rgb(var(--rgb-brand-cyan)/0.1)]' : 'border-white/10 bg-white dark:bg-zinc-900/[0.02]'}`}>
              <div className="flex items-center gap-3">
                <div className={`w-5 h-5 rounded grid place-items-center shrink-0 ${on ? 'bg-[var(--color-brand-cyan)]' : 'border border-white/20'}`}>
                  {on && <Check size={12} className="text-black" />}
                </div>
                <input value={p.name} onChange={(e) => up(i, 'name')(e.target.value)} onClick={(e) => e.stopPropagation()}
                  className="flex-1 bg-transparent font-bold text-white focus:outline-none" />
                <div className="flex items-center gap-1">
                  <span className="text-white/50 text-xs">£</span>
                  <input type="number" value={(p.price_pence / 100).toFixed(2)}
                    onChange={(e) => up(i, 'price_pence')(Math.round(Number(e.target.value) * 100))}
                    onClick={(e) => e.stopPropagation()}
                    className="w-16 bg-black/30 rounded px-2 py-1 text-right text-xs font-bold focus:outline-none" />
                </div>
              </div>
              <div className="text-[10px] text-white/50 mt-1 ml-8 uppercase tracking-wider">
                {p.kind.replace('_', ' ')} · {p.billing_cycle}
              </div>
            </div>
          );
        })}
      </div>
      <StepActions onBack={onBack} primaryLabel={selected.length ? `Create ${selected.length} plans` : 'Skip'}
        onPrimary={save} saving={saving} testId="mbr-setup-plans-next" />
    </StepShell>
  );
}


/* ─────────────────── Step 4 — First class ─────────────────── */

const DAYS = [{ v: 0, l: 'Mon' }, { v: 1, l: 'Tue' }, { v: 2, l: 'Wed' }, { v: 3, l: 'Thu' }, { v: 4, l: 'Fri' }, { v: 5, l: 'Sat' }, { v: 6, l: 'Sun' }];

function FirstClass({ headers, status, onNext, onBack }) {
  const [f, setF] = useState({
    name: '', category: 'Group', duration_min: 45, capacity: 20,
    recurs_days: [0, 2, 4], start_time: '18:00', colour: 'var(--color-danger)',
    instructor_name: '', room_name: 'Studio 1', credits_to_book: 1,
    waitlist_enabled: true, max_waitlist: 10,
    booking_opens_hours_before: 168, cancellation_cutoff_hours_before: 12,
  });
  const [saving, setSaving] = useState(false);
  const up = (k) => (v) => setF((p) => ({ ...p, [k]: v }));
  const toggleDay = (d) => up('recurs_days')(f.recurs_days.includes(d) ? f.recurs_days.filter((x) => x !== d) : [...f.recurs_days, d].sort());
  const skip = () => onNext();
  const save = async () => {
    if (!f.name.trim()) { notify.error('Class name required'); return; }
    if (f.recurs_days.length === 0) { notify.error('Pick at least one day'); return; }
    setSaving(true);
    try {
      await axios.post(`${API}/memberships/classes/templates`, {
        ...f,
        duration_min: Number(f.duration_min), capacity: Number(f.capacity),
        credits_to_book: Number(f.credits_to_book),
      }, { headers });
      notify.success('Class created · 8 weeks of occurrences generated');
      onNext();
    } catch (err) { notifyApiError(notify, err, 'Failed'); }
    finally { setSaving(false); }
  };
  return (
    <StepShell title="Add your first class" subtitle="Optional — you can add classes any time from the timetable.">
      <div className="space-y-3" data-testid="mbr-setup-class">
        <Input label="Class name" value={f.name} onChange={up('name')} testid="mbr-setup-class-name" />
        <div className="grid grid-cols-2 gap-3">
          <Input label="Category" value={f.category} onChange={up('category')} testid="mbr-setup-class-category" />
          <Input label="Start time" value={f.start_time} onChange={up('start_time')} testid="mbr-setup-class-time" />
        </div>
        <div>
          <span className="text-[10px] font-bold uppercase tracking-wider text-white/50">Days</span>
          <div className="flex gap-1.5 mt-1">
            {DAYS.map((d) => {
              const on = f.recurs_days.includes(d.v);
              return (
                <button key={d.v} type="button" onClick={() => toggleDay(d.v)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-extrabold uppercase transition ${on ? 'bg-[var(--color-brand-cyan)] text-[var(--color-surface-darker)]' : 'border border-white/15 text-white/60'}`}
                  data-testid={`mbr-setup-class-day-${d.v}`}>
                  {d.l}
                </button>
              );
            })}
          </div>
        </div>
        <div className="grid grid-cols-3 gap-3">
          <Input label="Duration (min)" type="number" value={f.duration_min} onChange={up('duration_min')} testid="mbr-setup-class-dur" />
          <Input label="Capacity" type="number" value={f.capacity} onChange={up('capacity')} testid="mbr-setup-class-cap" />
          <Input label="Credits" type="number" value={f.credits_to_book} onChange={up('credits_to_book')} testid="mbr-setup-class-credits" />
        </div>
        <Input label="Instructor name" value={f.instructor_name} onChange={up('instructor_name')} testid="mbr-setup-class-instructor" />
      </div>
      <div className="flex items-center justify-between gap-3 mt-6">
        <button onClick={onBack} className="text-xs font-bold text-white/60 hover:text-white"><ChevronLeft size={12} className="inline" /> Back</button>
        <div className="flex gap-2">
          <button onClick={skip} className="rounded-lg px-3 py-2 text-xs font-bold border border-white/15 text-white/80 hover:bg-white dark:bg-zinc-900/5" data-testid="mbr-setup-class-skip">Skip</button>
          <button onClick={save} disabled={saving} className="rounded-lg px-4 py-2 text-xs font-extrabold uppercase tracking-wider disabled:opacity-50"
            style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }} data-testid="mbr-setup-class-next">
            {saving ? '…' : 'Save & continue'} <ChevronRight size={12} className="inline ml-1" />
          </button>
        </div>
      </div>
    </StepShell>
  );
}


/* ─────────────────── Step 5 — Invite team ─────────────────── */

function InviteTeam({ headers: _h, status: _s, onNext, onBack }) {
  // Team-invite backend isn't wired in this round — this step surfaces the
  // intent and lets the operator proceed. Instructor seeding lives in
  // /memberships Team tab (future).
  return (
    <StepShell title="Invite your instructors" subtitle="(Coming soon — for now, add instructor users from the admin console.)">
      <div className="rounded-xl border border-white/10 bg-white dark:bg-zinc-900/[0.02] p-5 text-center text-white/60">
        <Sparkles size={20} className="mx-auto text-[var(--color-brand-cyan)] mb-3" />
        <p className="text-sm">The instructor inviter email flow lands in the next release.</p>
        <p className="text-xs text-white/40 mt-1">In the meantime, your demo instructor (Jake Ellis) is ready to test the instructor portal at <code>/instructor</code>.</p>
      </div>
      <StepActions onBack={onBack} primaryLabel="Finish setup" onPrimary={onNext} testId="mbr-setup-team-next" />
    </StepShell>
  );
}


/* ─────────────────── Step 6 — Done ─────────────────── */

function AllDone({ headers, status, onFinish }) {
  const org = status.organization;
  const appUrl = `${window.location.origin}/m/${org.slug}`;
  const [done, setDone] = useState(false);
  useEffect(() => {
    if (done) return;
    axios.post(`${API}/memberships/setup/complete`, {}, { headers })
      .then(() => setDone(true)).catch(() => {});
  }, [headers, done]);
  const copy = async () => {
    try { await navigator.clipboard.writeText(appUrl); notify.success('Link copied'); }
    catch { window.prompt('Share your app URL:', appUrl); }
  };
  return (
    <StepShell title="You're live." subtitle="Share the link below with your members — they'll land on your branded app.">
      <div className="rounded-2xl border border-[rgb(var(--rgb-brand-cyan)/0.3)] bg-gradient-to-br from-[rgb(var(--rgb-brand-cyan)/0.1)] to-transparent p-6 text-center" data-testid="mbr-setup-done">
        <div className="w-16 h-16 rounded-full bg-emerald-500/20 mx-auto grid place-items-center mb-4">
          <CheckCircle2 className="text-emerald-300" size={32} />
        </div>
        <h3 className="text-2xl font-extrabold tracking-tight">All set, {org.name}</h3>
        <p className="text-sm text-white/60 mt-2">Your members can book, pay, and check in — all from the link below.</p>
        <div className="mt-5 rounded-xl bg-black/40 border border-white/10 p-4">
          <div className="text-[10px] uppercase tracking-[0.25em] font-extrabold text-[var(--color-brand-cyan)] mb-1">Your app URL</div>
          <div className="flex items-center gap-2">
            <code className="flex-1 text-left text-sm text-white font-mono truncate" data-testid="mbr-setup-app-url">{appUrl}</code>
            <button onClick={copy} className="p-2 rounded-lg hover:bg-white dark:bg-zinc-900/10 text-white/70" data-testid="mbr-setup-copy"><Copy size={14} /></button>
          </div>
        </div>
      </div>
      <StepActions primaryLabel="Open my dashboard" onPrimary={onFinish} testId="mbr-setup-finish" />
    </StepShell>
  );
}


/* ─────────────────── Step shell & helpers ─────────────────── */

function StepShell({ title, subtitle, children }) {
  return (
    <div>
      <h1 className="text-3xl font-extrabold tracking-tight" style={{ letterSpacing: '-0.025em' }}>{title}</h1>
      {subtitle && <p className="text-sm text-white/60 mt-2">{subtitle}</p>}
      <div className="mt-6">{children}</div>
    </div>
  );
}

function StepActions({ onBack, primaryLabel, onPrimary, saving, testId }) {
  return (
    <div className="flex items-center justify-between gap-3 mt-6">
      {onBack ? <button onClick={onBack} className="text-xs font-bold text-white/60 hover:text-white" data-testid="mbr-setup-back"><ChevronLeft size={12} className="inline" /> Back</button> : <span />}
      <button
        {...(onPrimary ? { onClick: onPrimary } : { type: 'submit' })}
        disabled={saving}
        className="rounded-lg px-5 py-2.5 text-xs font-extrabold uppercase tracking-wider disabled:opacity-50"
        style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
        data-testid={testId}>
        {saving ? '…' : primaryLabel} <ChevronRight size={12} className="inline ml-1" />
      </button>
    </div>
  );
}

function Input({ label, value, onChange, type = 'text', required, testid, hint }) {
  return (
    <label className="block">
      <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-white/50">{label}{required ? ' *' : ''}</span>
      <input type={type} value={value} onChange={(e) => onChange(e.target.value)} required={required}
        className="mt-1 w-full rounded-lg bg-black/40 border border-white/10 px-3 py-2.5 text-sm text-white placeholder-white/30 focus:outline-none focus:border-[rgb(var(--rgb-brand-cyan)/0.6)]"
        data-testid={testid} />
      {hint && <span className="text-[10px] text-white/40 mt-1 block">{hint}</span>}
    </label>
  );
}

function Select({ label, value, onChange, options, testid }) {
  return (
    <label className="block">
      <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-white/50">{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)} data-testid={testid}
        className="mt-1 w-full rounded-lg bg-black/40 border border-white/10 px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[rgb(var(--rgb-brand-cyan)/0.6)]">
        {options.map((o) => <option key={o} value={o} className="bg-[var(--color-ink-deep)]">{o}</option>)}
      </select>
    </label>
  );
}

function FullPageLoader() {
  return <div className="min-h-screen bg-[var(--color-surface-darker)] text-white grid place-items-center"><Loader2 className="animate-spin text-[var(--color-brand-cyan)]" /></div>;
}
