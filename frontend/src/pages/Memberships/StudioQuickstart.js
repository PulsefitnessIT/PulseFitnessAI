/**
 * StudioQuickstart — "Start Your Studio in 10 Minutes" flow.
 *
 * Iter 215p. Shown on the Memberships → Start tab the first time Studio
 * Mode is enabled. Walks the user through four quick choices (brand,
 * class, pricing, schedule) then calls POST /memberships/studio/quickstart
 * which creates a drop-in plan, a monthly unlimited plan, a class
 * template and the next 8 weekly occurrences — and returns a public
 * booking URL ready to share.
 *
 * Design principles (match the brief):
 *   - 2–3 fields per step, sensible defaults everywhere
 *   - Mobile-first: stacked layout, fat tap targets
 *   - End screen shows the shareable link with QR + copy-button
 *   - Idempotent on the backend, so re-running is safe
 */
import { useMemo, useState } from 'react';
import { Sparkles, Check, Copy, QrCode, ExternalLink, Loader2, ArrowRight, ArrowLeft } from 'lucide-react';
import { notify } from '@/components/notifications';
import useStudioMode from './useStudioMode';

const DAYS = [
  { id: 1, label: 'Mon' }, { id: 2, label: 'Tue' }, { id: 3, label: 'Wed' },
  { id: 4, label: 'Thu' }, { id: 5, label: 'Fri' }, { id: 6, label: 'Sat' }, { id: 7, label: 'Sun' },
];

export default function StudioQuickstart({ onComplete }) {
  const { runQuickstart, saving } = useStudioMode();
  const [step, setStep] = useState(0);
  const [form, setForm] = useState({
    class_name: 'Open Flow Yoga',
    class_price_pence: 1500,
    monthly_price_pence: 6500,
    class_capacity: 12,
    weekly_day: 1,
    weekly_start_time: '18:00',
    duration_minutes: 60,
  });
  const [result, setResult] = useState(null);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const publicUrl = useMemo(() => {
    if (!result?.public_booking_url) return '';
    return `${window.location.origin}${result.public_booking_url}`;
  }, [result]);

  const submit = async () => {
    const r = await runQuickstart(form);
    if (r.ok) {
      setResult(r);
      setStep(4);
    } else {
      notify.error('Quickstart failed', r.error || 'Please try again.');
    }
  };

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(publicUrl);
      notify.success('Link copied', 'Paste it in your Instagram bio, email, or socials.');
    } catch {
      notify.error('Copy failed', 'Long-press the link to copy manually.');
    }
  };

  return (
    <div className="max-w-2xl mx-auto" data-testid="studio-quickstart">
      {/* Progress strip */}
      <div className="flex items-center gap-2 mb-6" data-testid="studio-quickstart-progress">
        {[0, 1, 2, 3].map((i) => (
          <div
            key={i}
            className={`flex-1 h-1.5 rounded-full transition-colors ${i <= step ? 'bg-[var(--color-brand-cyan)]' : 'bg-zinc-200 dark:bg-zinc-800'}`}
          />
        ))}
        <span className="text-xs font-semibold text-[color:var(--theme-text-muted)] ml-2 tabular-nums">{Math.min(step + 1, 4)} / 4</span>
      </div>

      <div className="rounded-2xl border border-[color:var(--theme-border)] bg-[var(--theme-surface)] p-6 sm:p-8 shadow-sm">
        <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider font-bold text-[var(--color-brand-cyan-hover)] mb-1">
          <Sparkles size={12} /> Studio Quickstart
        </div>

        {step === 0 && (
          <StepBrand form={form} set={set} onNext={() => setStep(1)} />
        )}
        {step === 1 && (
          <StepPricing form={form} set={set} onBack={() => setStep(0)} onNext={() => setStep(2)} />
        )}
        {step === 2 && (
          <StepSchedule form={form} set={set} onBack={() => setStep(1)} onNext={() => setStep(3)} />
        )}
        {step === 3 && (
          <StepReview form={form} onBack={() => setStep(2)} onSubmit={submit} saving={saving} />
        )}
        {step === 4 && result && (
          <StepDone result={result} publicUrl={publicUrl} onCopy={copyLink} onDone={onComplete} />
        )}
      </div>

      <p className="text-center text-xs text-[color:var(--theme-text-muted)] mt-4">
        You can tweak anything later — Plans, Classes, Timetable tabs have the full controls.
      </p>
    </div>
  );
}

function StepBrand({ form, set, onNext }) {
  return (
    <div className="space-y-4" data-testid="studio-step-brand">
      <h2 className="text-2xl font-bold">What's your first class called?</h2>
      <p className="text-sm text-[color:var(--theme-text-muted)]">
        Pick one class to launch with. You can add more in the Classes tab in under a minute.
      </p>
      <label className="block">
        <span className="text-xs font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)]">Class name</span>
        <input
          className="mt-1 w-full h-12 rounded-lg border border-[color:var(--theme-border)] bg-transparent px-4 text-base"
          value={form.class_name}
          onChange={(e) => set('class_name', e.target.value)}
          placeholder="e.g. Sunrise Yoga"
          data-testid="studio-class-name-input"
        />
      </label>
      <label className="block">
        <span className="text-xs font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)]">Class length</span>
        <div className="mt-1 flex gap-2" data-testid="studio-class-length">
          {[45, 60, 75, 90].map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => set('duration_minutes', m)}
              className={`flex-1 h-11 rounded-lg border text-sm font-semibold transition-colors ${
                form.duration_minutes === m
                  ? 'bg-[var(--color-brand-cyan)] text-[var(--color-ink)] border-transparent'
                  : 'border-[color:var(--theme-border)] text-[color:var(--theme-text)]'
              }`}
              data-testid={`studio-duration-${m}`}
            >{m} min</button>
          ))}
        </div>
      </label>
      <label className="block">
        <span className="text-xs font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)]">Capacity</span>
        <input
          type="number" min={1} max={200}
          className="mt-1 w-full h-12 rounded-lg border border-[color:var(--theme-border)] bg-transparent px-4 text-base"
          value={form.class_capacity}
          onChange={(e) => set('class_capacity', Math.max(1, parseInt(e.target.value || 0, 10)))}
          data-testid="studio-capacity-input"
        />
      </label>
      <div className="flex justify-end pt-2">
        <button
          type="button"
          onClick={onNext}
          disabled={!form.class_name.trim()}
          className="inline-flex items-center gap-2 h-11 px-6 rounded-full bg-[var(--color-brand-cyan)] text-[var(--color-ink)] font-bold disabled:opacity-50"
          data-testid="studio-step-brand-next"
        >
          Next <ArrowRight size={16} />
        </button>
      </div>
    </div>
  );
}

function StepPricing({ form, set, onBack, onNext }) {
  const dropIn = (form.class_price_pence / 100).toFixed(0);
  const monthly = (form.monthly_price_pence / 100).toFixed(0);
  return (
    <div className="space-y-5" data-testid="studio-step-pricing">
      <h2 className="text-2xl font-bold">How do people pay?</h2>
      <p className="text-sm text-[color:var(--theme-text-muted)]">
        We'll create two plans to start — a drop-in for casual bookers, and a monthly unlimited for regulars.
      </p>

      <div>
        <div className="text-xs font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)]">Drop-in price</div>
        <div className="mt-1 flex items-center gap-2">
          <span className="text-3xl font-bold">£</span>
          <input
            type="number" min={0} max={200}
            className="h-14 flex-1 rounded-lg border border-[color:var(--theme-border)] bg-transparent px-4 text-2xl font-bold"
            value={dropIn}
            onChange={(e) => set('class_price_pence', Math.max(0, parseInt(e.target.value || 0, 10)) * 100)}
            data-testid="studio-dropin-price"
          />
          <span className="text-sm text-[color:var(--theme-text-muted)]">per class</span>
        </div>
      </div>

      <div>
        <div className="text-xs font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)]">Monthly unlimited</div>
        <div className="mt-1 flex items-center gap-2">
          <span className="text-3xl font-bold">£</span>
          <input
            type="number" min={0} max={5000}
            className="h-14 flex-1 rounded-lg border border-[color:var(--theme-border)] bg-transparent px-4 text-2xl font-bold"
            value={monthly}
            onChange={(e) => set('monthly_price_pence', Math.max(0, parseInt(e.target.value || 0, 10)) * 100)}
            data-testid="studio-monthly-price"
          />
          <span className="text-sm text-[color:var(--theme-text-muted)]">/ month</span>
        </div>
      </div>

      <div className="rounded-lg bg-[rgb(var(--rgb-brand-cyan)/0.08)] border border-[rgb(var(--rgb-brand-cyan)/0.2)] p-3 text-xs text-[color:var(--theme-text)]">
        💡 Typical pricing: £12-20 drop-in, £55-85 monthly unlimited. You can add class packs, courses, and bundles later.
      </div>

      <div className="flex justify-between pt-2">
        <button type="button" onClick={onBack} className="inline-flex items-center gap-2 h-11 px-5 rounded-full border border-[color:var(--theme-border)] text-sm font-semibold" data-testid="studio-step-pricing-back">
          <ArrowLeft size={16} /> Back
        </button>
        <button type="button" onClick={onNext} className="inline-flex items-center gap-2 h-11 px-6 rounded-full bg-[var(--color-brand-cyan)] text-[var(--color-ink)] font-bold" data-testid="studio-step-pricing-next">
          Next <ArrowRight size={16} />
        </button>
      </div>
    </div>
  );
}

function StepSchedule({ form, set, onBack, onNext }) {
  return (
    <div className="space-y-5" data-testid="studio-step-schedule">
      <h2 className="text-2xl font-bold">When does your first class run?</h2>
      <p className="text-sm text-[color:var(--theme-text-muted)]">
        We'll auto-schedule the next 8 weeks for you — edit or extend any time from the Timetable tab.
      </p>

      <div>
        <div className="text-xs font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)] mb-1">Day of the week</div>
        <div className="grid grid-cols-7 gap-1" data-testid="studio-weekly-day">
          {DAYS.map((d) => (
            <button
              key={d.id} type="button"
              onClick={() => set('weekly_day', d.id)}
              className={`h-11 rounded-lg border text-sm font-semibold transition-colors ${
                form.weekly_day === d.id
                  ? 'bg-[var(--color-brand-cyan)] text-[var(--color-ink)] border-transparent'
                  : 'border-[color:var(--theme-border)] text-[color:var(--theme-text)]'
              }`}
              data-testid={`studio-day-${d.id}`}
            >{d.label}</button>
          ))}
        </div>
      </div>

      <label className="block">
        <span className="text-xs font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)]">Start time</span>
        <input
          type="time"
          className="mt-1 w-full h-12 rounded-lg border border-[color:var(--theme-border)] bg-transparent px-4 text-base"
          value={form.weekly_start_time}
          onChange={(e) => set('weekly_start_time', e.target.value)}
          data-testid="studio-start-time"
        />
      </label>

      <div className="flex justify-between pt-2">
        <button type="button" onClick={onBack} className="inline-flex items-center gap-2 h-11 px-5 rounded-full border border-[color:var(--theme-border)] text-sm font-semibold" data-testid="studio-step-schedule-back">
          <ArrowLeft size={16} /> Back
        </button>
        <button type="button" onClick={onNext} className="inline-flex items-center gap-2 h-11 px-6 rounded-full bg-[var(--color-brand-cyan)] text-[var(--color-ink)] font-bold" data-testid="studio-step-schedule-next">
          Next <ArrowRight size={16} />
        </button>
      </div>
    </div>
  );
}

function StepReview({ form, onBack, onSubmit, saving }) {
  const dayLabel = DAYS.find((d) => d.id === form.weekly_day)?.label;
  return (
    <div className="space-y-5" data-testid="studio-step-review">
      <h2 className="text-2xl font-bold">All set. Ready to launch?</h2>
      <p className="text-sm text-[color:var(--theme-text-muted)]">
        We'll create everything below in one go. Nothing is permanent — edit or delete any time.
      </p>
      <dl className="space-y-2 rounded-lg border border-[color:var(--theme-border)] bg-white/[0.04] p-4 text-sm">
        <div className="flex justify-between"><dt className="text-[color:var(--theme-text-muted)]">Class</dt><dd className="font-semibold">{form.class_name} · {form.duration_minutes} min · cap {form.class_capacity}</dd></div>
        <div className="flex justify-between"><dt className="text-[color:var(--theme-text-muted)]">Drop-in</dt><dd className="font-semibold">£{(form.class_price_pence / 100).toFixed(0)}</dd></div>
        <div className="flex justify-between"><dt className="text-[color:var(--theme-text-muted)]">Monthly unlimited</dt><dd className="font-semibold">£{(form.monthly_price_pence / 100).toFixed(0)} / mo</dd></div>
        <div className="flex justify-between"><dt className="text-[color:var(--theme-text-muted)]">Schedule</dt><dd className="font-semibold">Every {dayLabel} · {form.weekly_start_time} · next 8 weeks</dd></div>
      </dl>
      <div className="flex justify-between pt-2">
        <button type="button" onClick={onBack} className="inline-flex items-center gap-2 h-11 px-5 rounded-full border border-[color:var(--theme-border)] text-sm font-semibold" data-testid="studio-step-review-back">
          <ArrowLeft size={16} /> Back
        </button>
        <button
          type="button" onClick={onSubmit} disabled={saving}
          className="inline-flex items-center gap-2 h-11 px-6 rounded-full bg-[var(--color-brand-cyan)] text-[var(--color-ink)] font-bold disabled:opacity-50"
          data-testid="studio-step-review-submit"
        >
          {saving ? <><Loader2 size={16} className="animate-spin" /> Launching…</> : <>Launch studio <Sparkles size={16} /></>}
        </button>
      </div>
    </div>
  );
}

function StepDone({ result, publicUrl, onCopy, onDone }) {
  const qrUrl = publicUrl
    ? `https://api.qrserver.com/v1/create-qr-code/?size=240x240&data=${encodeURIComponent(publicUrl)}`
    : '';
  return (
    <div className="space-y-5 text-center" data-testid="studio-step-done">
      <div className="mx-auto w-16 h-16 rounded-full bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center">
        <Check size={28} className="text-emerald-600 dark:text-emerald-400" />
      </div>
      <h2 className="text-2xl font-bold">You're live!</h2>
      <p className="text-sm text-[color:var(--theme-text-muted)]">
        {result.created.occurrences} classes scheduled, {result.created.plans.length} plans live.
        Share this link anywhere to start taking bookings.
      </p>
      <div className="flex justify-center" data-testid="studio-qr">
        {qrUrl && <img src={qrUrl} alt="Booking QR code" width={180} height={180} className="rounded-lg border border-[color:var(--theme-border)]" />}
      </div>
      <div className="rounded-lg border border-[color:var(--theme-border)] bg-[rgb(var(--rgb-brand-cyan)/0.06)] p-3 flex items-center gap-2">
        <input
          readOnly value={publicUrl}
          className="flex-1 bg-transparent text-sm font-mono text-[color:var(--theme-text)] min-w-0"
          data-testid="studio-public-url"
        />
        <button type="button" onClick={onCopy} className="inline-flex items-center gap-1 h-9 px-3 rounded-full bg-[var(--color-brand-cyan)] text-[var(--color-ink)] text-xs font-bold" data-testid="studio-copy-url">
          <Copy size={12} /> Copy
        </button>
      </div>
      <div className="flex flex-col sm:flex-row gap-2 pt-2">
        <a
          href={publicUrl} target="_blank" rel="noreferrer"
          className="flex-1 inline-flex items-center justify-center gap-2 h-11 rounded-full border border-[color:var(--theme-border)] text-sm font-semibold"
          data-testid="studio-view-page"
        >
          <ExternalLink size={14} /> View booking page
        </a>
        <button type="button" onClick={onDone}
          className="flex-1 inline-flex items-center justify-center gap-2 h-11 rounded-full bg-[var(--color-brand-cyan)] text-[var(--color-ink)] font-bold"
          data-testid="studio-done"
        >
          <QrCode size={14} /> Go to dashboard
        </button>
      </div>
    </div>
  );
}
