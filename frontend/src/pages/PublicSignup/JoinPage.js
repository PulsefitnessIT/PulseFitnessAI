/**
 * Public member sign-up page — /m/:slug/join
 *
 * No-auth wizard that sells a membership at a specific gym. Steps:
 *   1) Pick plan
 *   2) Personal details (name, email, phone, DOB, address, emergency contact, marketing consent)
 *   3) PARQ (default 7-question template; per-gym override supported by the backend)
 *   4) Tour / first-class preference (optional)
 *   5) Stripe Checkout redirect
 *
 * After payment Stripe redirects to /m/:slug/join/success, which polls
 * the backend until `payment_status === "paid"` and the member is created.
 */
import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import {
  Check, ChevronRight, ChevronLeft, Loader2, Heart, Mail, AlertTriangle,
  Calendar, MapPin, ShieldCheck,
} from 'lucide-react';
import TourSlotPicker from './TourSlotPicker';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const STEPS = ['plan', 'details', 'parq', 'extras', 'payment'];
const STEP_LABELS = {
  plan: 'Plan', details: 'Your details', parq: 'Health check', extras: 'First visit', payment: 'Payment',
};

const fmtMoney = (pence, ccy = 'GBP') => {
  const sym = ccy === 'GBP' ? '£' : ccy === 'EUR' ? '€' : '$';
  return `${sym}${(Number(pence || 0) / 100).toFixed(2)}`;
};

export default function JoinPage() {
  const { slug } = useParams();
  const _navigate = useNavigate();
  const location = useLocation();

  const [stepIdx, setStepIdx] = useState(0);
  const step = STEPS[stepIdx];
  const [gym, setGym] = useState(null);
  const [parqQuestions, setParqQuestions] = useState([]);
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [draftId, setDraftId] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const [chosenPlanId, setChosenPlanId] = useState(null);
  const [details, setDetails] = useState({
    first_name: '', last_name: '', email: '', phone: '', dob: '', address: '',
    emergency_contact_name: '', emergency_contact_phone: '', marketing_consent: true,
  });
  const [parqAnswers, setParqAnswers] = useState({});
  const [extras, setExtras] = useState({ tour_requested: false, tour_slot_at: null, tour_booking_id: null, skip_extras: false });

  const cancelled = new URLSearchParams(location.search).get('cancelled');

  // Initial load + draft recovery
  useEffect(() => {
    let alive = true;
    const draftFromQuery = new URLSearchParams(location.search).get('draft');
    if (draftFromQuery) setDraftId(draftFromQuery);
    (async () => {
      try {
        const [b, p] = await Promise.all([
          axios.get(`${API}/public/signup/${slug}/branding`),
          axios.get(`${API}/public/signup/${slug}/plans`),
        ]);
        if (!alive) return;
        setGym(b.data?.gym);
        setParqQuestions(b.data?.parq_questions || []);
        setPlans(p.data?.plans || []);
        // Funnel tracking — anonymous page view (Phase-2)
        axios.post(`${API}/public/signup/${slug}/track`, {
          event: 'view',
          ref: document.referrer ? document.referrer.slice(0, 200) : '',
          draft_id: draftFromQuery || null,
        }).catch(() => {});
        // Recover saved draft if magic-link token is present
        if (draftFromQuery) {
          try {
            const r = await axios.get(`${API}/public/signup/${slug}/draft/${draftFromQuery}`);
            const d = r.data?.draft;
            if (d) {
              if (d.plan_id) setChosenPlanId(d.plan_id);
              if (d.details) setDetails((prev) => ({ ...prev, ...d.details }));
              if (d.parq?.answers) setParqAnswers(d.parq.answers);
              setStepIdx(1);  // jump straight to "Your details" — they were past step 0
            }
          } catch (_) { /* graceful */ }
        }
      } catch (e) {
        setError(e.response?.data?.detail || 'Could not load this gym. Check the link.');
      } finally {
        setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [slug, location.search]);

  const chosenPlan = useMemo(
    () => plans.find((p) => p.id === chosenPlanId),
    [plans, chosenPlanId],
  );

  const total = useMemo(() => {
    if (!chosenPlan) return 0;
    return (chosenPlan.monthly_price_pence || 0) + (chosenPlan.joining_fee_pence || 0);
  }, [chosenPlan]);

  const saveDraft = async (extra = {}) => {
    if (!details.email || !details.email.includes('@')) return;
    try {
      const r = await axios.post(`${API}/public/signup/${slug}/draft`, {
        ...details,
        plan_id: chosenPlanId,
        step,
        draft_id: draftId,
        ...extra,
      });
      if (r.data?.draft_id) setDraftId(r.data.draft_id);
    } catch (_) { /* silent — draft save is best-effort */ }
  };

  const next = async () => {
    setError(null);
    if (step === 'plan') {
      if (!chosenPlanId) return setError('Pick a membership plan to continue.');
    } else if (step === 'details') {
      if (!details.first_name || !details.last_name || !details.email) {
        return setError('We need your name and email at minimum.');
      }
      await saveDraft();
    } else if (step === 'parq') {
      try {
        await axios.post(`${API}/public/signup/${slug}/parq`, {
          draft_id: draftId,
          answers: parqAnswers,
        });
      } catch (e) {
        return setError(e.response?.data?.detail || 'Could not save your health check.');
      }
    } else if (step === 'extras') {
      await saveDraft(extras);
    }
    setStepIdx((i) => Math.min(i + 1, STEPS.length - 1));
  };

  const back = () => setStepIdx((i) => Math.max(i - 1, 0));

  const startCheckout = async () => {
    if (!gym?.stripe_ready) {
      setError("This gym hasn't connected payments yet. Please contact them directly.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const r = await axios.post(`${API}/public/signup/${slug}/checkout`, {
        draft_id: draftId,
        plan_id: chosenPlanId,
      });
      if (r.data?.url) {
        window.location.href = r.data.url;
      } else {
        setError('Could not start checkout. Try again.');
      }
    } catch (e) {
      setError(e.response?.data?.detail || 'Checkout failed.');
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-zinc-50">
        <Loader2 size={28} className="text-zinc-400 animate-spin" />
      </div>
    );
  }
  if (!gym) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-zinc-50 p-6">
        <p className="text-zinc-600 max-w-md text-center" data-testid="join-error">{error || 'Gym not found.'}</p>
      </div>
    );
  }

  const accent = gym.primary_colour || '#2563EB';
  const accent2 = gym.accent_colour || '#19CDFF';

  return (
    <div className="min-h-screen bg-zinc-50" data-testid="join-page">
      <header className="bg-white border-b border-zinc-200">
        <div className="max-w-4xl mx-auto px-5 py-4 flex items-center gap-3">
          {gym.logo_url ? (
            <img src={gym.logo_url} alt={gym.name} className="h-10" loading="eager" decoding="async" />
          ) : (
            <div className="h-10 w-10 rounded-md flex items-center justify-center text-white font-bold text-sm" style={{ background: `linear-gradient(135deg, ${accent}, ${accent2})` }}>
              {(gym.name || '').charAt(0)}
            </div>
          )}
          <div className="flex-1">
            <h1 className="text-base font-bold text-zinc-900" data-testid="join-gym-name">{gym.name}</h1>
            <p className="text-[11px] text-zinc-500">{gym.tagline}</p>
          </div>
          <span className="hidden sm:inline-flex items-center gap-1 text-[11px] text-zinc-500">
            <ShieldCheck size={12} /> Powered by GymAxis
          </span>
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-5 py-6">
        {/* Step bar */}
        <ol className="flex items-center gap-1 mb-6 text-[11px] uppercase tracking-wide" data-testid="join-stepper">
          {STEPS.map((s, i) => (
            <React.Fragment key={s}>
              <li className={`flex items-center gap-1.5 ${i < stepIdx ? 'text-emerald-600' : i === stepIdx ? 'font-bold' : 'text-zinc-400'}`}>
                {i < stepIdx ? <Check size={11} /> : <span className={`inline-block h-4 w-4 rounded-full ${i === stepIdx ? 'bg-zinc-900 text-white' : 'border border-zinc-300'} text-center text-[9px] leading-4`}>{i + 1}</span>}
                <span className="hidden sm:inline">{STEP_LABELS[s]}</span>
              </li>
              {i < STEPS.length - 1 && <li className="flex-1 h-px bg-zinc-200" />}
            </React.Fragment>
          ))}
        </ol>

        {cancelled && stepIdx === 0 && (
          <div className="mb-4 p-3 rounded-lg bg-amber-50 border border-amber-200 text-sm text-amber-800" data-testid="join-cancelled-banner">
            Your last payment was cancelled. No charge made. Try again whenever you're ready.
          </div>
        )}

        {error && (
          <div className="mb-4 p-3 rounded-lg bg-rose-50 border border-rose-200 text-sm text-rose-700 flex items-start gap-2" data-testid="join-error-banner">
            <AlertTriangle size={14} className="mt-0.5" /> {error}
          </div>
        )}

        {step === 'plan' && (
          <section data-testid="join-step-plan">
            <h2 className="text-2xl font-bold text-zinc-900 mb-4">Pick your plan</h2>
            {plans.length === 0 ? (
              <p className="text-sm text-zinc-500">No plans published yet. Please contact the gym directly.</p>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {plans.map((p) => {
                  const selected = chosenPlanId === p.id;
                  return (
                    <button
                      type="button"
                      key={p.id}
                      onClick={() => setChosenPlanId(p.id)}
                      className={`text-left p-4 rounded-xl border transition-all ${selected ? 'border-zinc-900 ring-2 ring-zinc-900' : 'border-zinc-200 hover:border-zinc-400'} bg-white`}
                      data-testid={`plan-card-${p.id}`}
                    >
                      <div className="flex items-baseline justify-between mb-1">
                        <span className="font-bold text-zinc-900">{p.name}</span>
                        <span className="text-lg font-bold" style={{ color: accent }}>{fmtMoney(p.monthly_price_pence, p.currency)}<span className="text-[10px] text-zinc-400">/mo</span></span>
                      </div>
                      {p.joining_fee_pence > 0 && (
                        <p className="text-[11px] text-zinc-500">+ {fmtMoney(p.joining_fee_pence, p.currency)} joining fee</p>
                      )}
                      {p.contract_months > 0 && (
                        <p className="text-[11px] text-zinc-500">{p.contract_months}-month contract</p>
                      )}
                      <p className="text-xs text-zinc-600 mt-2">{p.description || p.best_for}</p>
                      {p.perks?.length > 0 && (
                        <ul className="mt-2 space-y-0.5">
                          {p.perks.slice(0, 4).map((perk, i) => (
                            <li key={i} className="text-[11px] text-zinc-600 flex items-center gap-1.5">
                              <Check size={10} className="text-emerald-600" /> {perk}
                            </li>
                          ))}
                        </ul>
                      )}
                    </button>
                  );
                })}
              </div>
            )}
          </section>
        )}

        {step === 'details' && (
          <section data-testid="join-step-details">
            <h2 className="text-2xl font-bold text-zinc-900 mb-4">Tell us about you</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Input label="First name" value={details.first_name} onChange={(v) => setDetails({ ...details, first_name: v })} testid="d-first" />
              <Input label="Last name" value={details.last_name} onChange={(v) => setDetails({ ...details, last_name: v })} testid="d-last" />
              <Input label="Email" type="email" value={details.email} onChange={(v) => setDetails({ ...details, email: v })} testid="d-email" />
              <Input label="Phone" value={details.phone} onChange={(v) => setDetails({ ...details, phone: v })} testid="d-phone" />
              <Input label="Date of birth" type="date" value={details.dob} onChange={(v) => setDetails({ ...details, dob: v })} testid="d-dob" />
              <Input label="Address" value={details.address} onChange={(v) => setDetails({ ...details, address: v })} testid="d-addr" />
              <Input label="Emergency contact name" value={details.emergency_contact_name} onChange={(v) => setDetails({ ...details, emergency_contact_name: v })} testid="d-emerg-name" />
              <Input label="Emergency contact phone" value={details.emergency_contact_phone} onChange={(v) => setDetails({ ...details, emergency_contact_phone: v })} testid="d-emerg-phone" />
            </div>
            <label className="flex items-center gap-2 mt-4 text-sm text-zinc-700">
              <input
                type="checkbox"
                checked={details.marketing_consent}
                onChange={(e) => setDetails({ ...details, marketing_consent: e.target.checked })}
                data-testid="d-consent"
              />
              I agree to receive class reminders and offers from {gym.name}.
            </label>
          </section>
        )}

        {step === 'parq' && (
          <section data-testid="join-step-parq">
            <h2 className="text-2xl font-bold text-zinc-900 mb-2">Quick health check</h2>
            <p className="text-sm text-zinc-500 mb-4 flex items-start gap-2">
              <Heart size={14} className="text-rose-500 mt-0.5" />
              The standard 7-question PARQ-Q. Takes 30 seconds. Required by every UK gym insurer.
            </p>
            <div className="space-y-2">
              {parqQuestions.map((q) => {
                const ans = parqAnswers[q.id];
                return (
                  <div key={q.id} className="p-3 rounded-lg border border-zinc-200 bg-white" data-testid={`parq-${q.id}`}>
                    <p className="text-sm text-zinc-800 mb-2">{q.q}</p>
                    <div className="flex items-center gap-2">
                      {[
                        { v: false, label: 'No' },
                        { v: true,  label: 'Yes' },
                      ].map((o) => (
                        <button
                          type="button"
                          key={String(o.v)}
                          onClick={() => setParqAnswers({ ...parqAnswers, [q.id]: o.v })}
                          className={`px-4 py-1.5 text-xs font-semibold rounded-full transition-colors ${ans === o.v ? (o.v ? 'bg-rose-600 text-white' : 'bg-emerald-600 text-white') : 'bg-zinc-100 text-zinc-700 hover:bg-zinc-200'}`}
                          data-testid={`parq-${q.id}-${o.v ? 'yes' : 'no'}`}
                        >
                          {o.label}
                        </button>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
            {Object.values(parqAnswers).some(Boolean) && (
              <div className="mt-3 p-3 rounded-lg bg-amber-50 border border-amber-200 text-[12px] text-amber-800" data-testid="parq-flagged">
                You answered "yes" to at least one question. Your sign-up will go through, but {gym.name} will follow up to ask for a GP clearance letter within 14 days.
              </div>
            )}
          </section>
        )}

        {step === 'extras' && (
          <section data-testid="join-step-extras">
            <h2 className="text-2xl font-bold text-zinc-900 mb-2">Your first visit</h2>
            <p className="text-sm text-zinc-500 mb-4">Book an induction / tour now — or skip and the team will reach out after you sign up.</p>
            <div className="space-y-3">
              <label className="block p-3 rounded-lg border border-zinc-200 bg-white cursor-pointer">
                <div className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="extras"
                    checked={extras.tour_requested && !extras.skip_extras}
                    onChange={() => setExtras((prev) => ({ ...prev, tour_requested: true, skip_extras: false }))}
                    data-testid="extras-tour"
                  />
                  <Calendar size={14} /> <span className="text-sm font-semibold">Book an induction / tour</span>
                </div>
                {extras.tour_requested && !extras.skip_extras && (
                  <div className="mt-3">
                    {draftId ? (
                      <TourSlotPicker
                        API={API}
                        slug={slug}
                        draftId={draftId}
                        email={details.email}
                        fullName={`${details.first_name} ${details.last_name}`.trim()}
                        value={extras.tour_slot_at ? { slot_at: extras.tour_slot_at, booking_id: extras.tour_booking_id } : null}
                        onChange={(v) => setExtras((prev) => ({
                          ...prev,
                          tour_slot_at: v?.slot_at || null,
                          tour_booking_id: v?.booking_id || null,
                        }))}
                        accent={accent}
                      />
                    ) : (
                      <p className="text-xs text-zinc-500 italic">
                        Saving your details… the slot picker will appear in a moment.
                      </p>
                    )}
                  </div>
                )}
              </label>
              <label className="block p-3 rounded-lg border border-zinc-200 bg-white cursor-pointer">
                <div className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="extras"
                    checked={extras.skip_extras}
                    onChange={() => setExtras({ tour_requested: false, tour_slot_at: null, tour_booking_id: null, skip_extras: true })}
                    data-testid="extras-skip"
                  />
                  <span className="text-sm">Skip — I'll plan it later</span>
                </div>
              </label>
            </div>
          </section>
        )}

        {step === 'payment' && chosenPlan && (
          <section data-testid="join-step-payment">
            <h2 className="text-2xl font-bold text-zinc-900 mb-2">Confirm & pay</h2>
            <p className="text-sm text-zinc-500 mb-4">You'll be redirected to Stripe to enter card / Bacs / Apple Pay details.</p>
            <div className="rounded-xl bg-white border border-zinc-200 p-4 mb-4" data-testid="join-summary">
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-semibold">{chosenPlan.name}</span>
                <span className="text-sm">{fmtMoney(chosenPlan.monthly_price_pence, chosenPlan.currency)}/mo</span>
              </div>
              {chosenPlan.joining_fee_pence > 0 && (
                <div className="flex items-center justify-between text-xs text-zinc-500 mb-1">
                  <span>Joining fee (one-off)</span>
                  <span>{fmtMoney(chosenPlan.joining_fee_pence, chosenPlan.currency)}</span>
                </div>
              )}
              {chosenPlan.contract_months > 0 && (
                <p className="text-[11px] text-zinc-500 mb-2">{chosenPlan.contract_months}-month minimum term applies.</p>
              )}
              <div className="border-t border-zinc-100 mt-2 pt-2 flex items-center justify-between font-bold">
                <span>Today's total</span>
                <span style={{ color: accent }}>{fmtMoney(total, chosenPlan.currency)}</span>
              </div>
            </div>

            {!gym.stripe_ready && (
              <div className="mb-4 p-3 rounded-lg bg-rose-50 border border-rose-200 text-sm text-rose-700" data-testid="join-no-stripe">
                {gym.name} hasn't finished setting up payments yet. Please contact them directly.
              </div>
            )}

            <button
              type="button"
              onClick={startCheckout}
              disabled={submitting || !gym.stripe_ready}
              className="w-full py-3 rounded-md text-white font-bold disabled:opacity-50"
              style={{ background: accent }}
              data-testid="join-pay-btn"
            >
              {submitting ? <Loader2 size={14} className="inline animate-spin mr-2" /> : <Mail size={14} className="inline mr-2" />}
              Pay {fmtMoney(total, chosenPlan.currency)} & join
            </button>
            <p className="mt-3 text-[10px] text-zinc-400 text-center">
              By joining you agree to {gym.name}'s terms of service and privacy policy. Cancellation rights apply per the Consumer Rights Act 2015.
            </p>
          </section>
        )}

        {/* Nav */}
        <div className="flex items-center gap-2 mt-8" data-testid="join-nav">
          {stepIdx > 0 && (
            <button
              type="button"
              onClick={back}
              className="px-4 py-2 text-sm rounded-md border border-zinc-200 text-zinc-700 hover:bg-zinc-50 inline-flex items-center gap-1"
              data-testid="join-back"
            >
              <ChevronLeft size={14} /> Back
            </button>
          )}
          {stepIdx < STEPS.length - 1 && (
            <button
              type="button"
              onClick={next}
              className="ml-auto px-5 py-2 text-sm rounded-md text-white font-semibold inline-flex items-center gap-1"
              style={{ background: accent }}
              data-testid="join-next"
            >
              Continue <ChevronRight size={14} />
            </button>
          )}
        </div>
      </main>

      <footer className="text-center py-8 text-[11px] text-zinc-400">
        {gym.address && <p className="mb-1 inline-flex items-center gap-1"><MapPin size={10} /> {gym.address}</p>}
        <p>© {new Date().getFullYear()} {gym.name}</p>
      </footer>
    </div>
  );
}

const Input = ({ label, value, onChange, type = 'text', testid }) => (
  <label className="block">
    <span className="block text-[11px] font-semibold uppercase tracking-wide text-zinc-500 mb-1">{label}</span>
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full px-3 py-2 text-sm border border-zinc-200 rounded-md focus:outline-none focus:border-zinc-900"
      data-testid={testid}
    />
  </label>
);
