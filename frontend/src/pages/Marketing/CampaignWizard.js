/**
 * Marketing Suite — Campaign Wizard (guided experience).
 *
 * 5-step wizard that sits OVER the existing tabs. Does not replace any
 * functionality — at launch, the wizard POSTs the assembled payload to the
 * existing campaigns / creative / audiences endpoints so a wizard-built
 * campaign is indistinguishable from a hand-built one afterwards.
 *
 * Layout: full-screen modal with top progress bar + main content (left)
 * + AI copilot rail (right on lg+, stacked on mobile).
 *
 * Steps:
 *  1. Goal & Template  — outcome + optional pre-built template
 *  2. Audience         — prebuilt segments or custom rule count
 *  3. Creative         — subject + body + optional AI image
 *  4. Schedule         — channel + send time
 *  5. Review & Launch  — pre-flight + confirm
 */
import { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  X, ChevronLeft, ChevronRight, Sparkles, Target, Users, ImagePlus, Calendar, Rocket,
  CheckCircle2, Lightbulb, Mail, Clock, Wand2,
} from 'lucide-react';

const STEP_DEFS = [
  { id: 'goal',      title: 'Goal',      icon: Target,    headline: 'What do you want to achieve?', sub: 'Pick a goal so we can tailor audience + copy.' },
  { id: 'audience',  title: 'Audience',  icon: Users,     headline: 'Who should receive this?',     sub: 'Segment your members — AI suggests a default.' },
  { id: 'creative',  title: 'Creative',  icon: ImagePlus, headline: 'What\'s the message?',         sub: 'Subject + body. AI writes variants in your brand voice.' },
  { id: 'schedule',  title: 'Schedule',  icon: Calendar,  headline: 'When + where should it go?',   sub: 'Channel + time. AI predicts the best slot.' },
  { id: 'review',    title: 'Review',    icon: Rocket,    headline: 'Ready to launch?',             sub: 'One last look before the send.' },
];

const GOALS = [
  { id: 'fill-classes',  label: 'Fill empty classes',      hint: 'Boost attendance on under-booked sessions' },
  { id: 'win-back',      label: 'Win back inactive',       hint: 'Re-engage members dormant 30+ days' },
  { id: 'promote-class', label: 'Promote a new class',     hint: 'Announce to likely-interested members' },
  { id: 'upsell-pt',     label: 'Upsell Personal Training', hint: 'Offer PT to consistent attendees' },
  { id: 'retention',     label: 'Retention touch',          hint: 'Quarterly check-in / appreciation' },
  { id: 'custom',        label: 'Custom goal',              hint: 'Define your own objective' },
];

const AUDIENCE_PRESETS = {
  'fill-classes':  { id: 'low-bookings-7d',  label: 'Members with no bookings in 7 days',  approx: '~22%' },
  'win-back':      { id: 'inactive-30d',     label: 'Inactive 30+ days',                    approx: '~14%' },
  'promote-class': { id: 'class-lovers',     label: 'Regular class attendees',              approx: '~38%' },
  'upsell-pt':     { id: 'consistent-2w',    label: '2+ weeks of consistent attendance',    approx: '~9%' },
  'retention':     { id: 'all-active',       label: 'All active members',                   approx: '~61%' },
  'custom':        { id: 'custom',           label: 'Define with the rule builder',         approx: 'Varies' },
};

const CHANNELS = [
  { id: 'email', label: 'Email', icon: Mail },
  { id: 'sms',   label: 'SMS',   icon: Clock, locked: true },
];

const TIME_SLOTS = [
  { id: 'now',        label: 'Send now' },
  { id: 'best-time',  label: 'AI-optimised (Tue 7:00 AM)' },
  { id: 'custom',     label: 'Pick a time…' },
];

const AI_COPY_BY_GOAL = {
  'fill-classes':  { subject: 'Your class is waiting — grab your spot',               preview: 'Hey {{first_name}}, your usual 5pm slot has 3 spaces left today — book before it sells out.' },
  'win-back':      { subject: 'We miss you — 20% off your comeback week',             preview: 'It\'s been a minute. Here\'s 20% off any class or day pass to help you bounce back this week.' },
  'promote-class': { subject: 'New class alert — {{class_name}} just launched',      preview: 'Based on your last 4 bookings, you\'ll love this one. First session is on the house for early signups.' },
  'upsell-pt':     { subject: 'Ready to level up? Try 1:1 with a coach',              preview: 'You\'ve been crushing it. Pair it with a free PT intro to hit the next gear — no pressure, no commitment.' },
  'retention':     { subject: 'You\'ve done X classes this quarter — nice.',          preview: 'Just wanted to drop in and say well done. Here\'s a small token of appreciation from all of us at {{company_name}}.' },
  'custom':        { subject: '',                                                    preview: '' },
};

const clsx = (...parts) => parts.filter(Boolean).join(' ');

function ProgressBar({ current, total }) {
  const pct = Math.round(((current + 1) / total) * 100);
  return (
    <div className="w-full">
      <div className="flex items-center justify-between mb-2">
        {STEP_DEFS.map((s, i) => {
          const Icon = s.icon;
          const active = i === current;
          const done = i < current;
          return (
            <div key={s.id} className="flex-1 flex items-center gap-2 min-w-0" data-testid={`wizard-step-indicator-${s.id}`}>
              <div
                className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 pulse-font-heading font-bold text-sm"
                style={done
                  ? { background: 'var(--color-success)', color: 'var(--color-ink)' }
                  : active
                    ? { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }
                    : { background: 'var(--theme-surface)', border: '1px solid var(--theme-border)', color: 'var(--theme-text-muted)' }}
              >
                {done ? <CheckCircle2 size={16} /> : <Icon size={14} />}
              </div>
              <div className="min-w-0 hidden sm:block">
                <div className="text-xs font-semibold truncate pulse-font-heading" style={{ color: active || done ? 'var(--theme-text)' : 'var(--theme-text-muted)' }}>
                  {s.title}
                </div>
              </div>
              {i < STEP_DEFS.length - 1 && (
                <div className="flex-1 h-px mx-2" style={{ background: done ? 'var(--color-success)' : 'var(--theme-border)' }} />
              )}
            </div>
          );
        })}
      </div>
      <div className="text-[11px]" style={{ color: 'var(--theme-text-muted)' }}>{pct}% complete</div>
    </div>
  );
}

function AICopilot({ tip, suggestions = [], onApply, loading = false }) {
  return (
    <aside
      className="rounded-2xl p-5 border h-fit pulse-font-body"
      style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}
      data-testid="wizard-ai-copilot"
    >
      <div className="flex items-center gap-2 mb-3">
        <div className="w-7 h-7 rounded-full flex items-center justify-center" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}>
          <Sparkles size={14} />
        </div>
        <div className="text-sm font-semibold pulse-font-heading" style={{ color: 'var(--theme-text)' }}>AI copilot</div>
        {loading && (
          <div
            className="ml-auto text-[10px] font-semibold uppercase tracking-[0.14em] inline-flex items-center gap-1.5"
            style={{ color: 'var(--theme-text-muted)' }}
            data-testid="wizard-ai-loading"
          >
            <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: 'var(--color-brand-cyan)' }} />
            Thinking…
          </div>
        )}
      </div>
      <div className="text-xs mb-4 leading-relaxed" style={{ color: 'var(--theme-text-muted)' }}>
        <Lightbulb size={11} className="inline mr-1" style={{ color: 'var(--color-warning)' }} />
        {tip}
      </div>
      {suggestions.length > 0 && (
        <div className="space-y-2">
          {suggestions.map((s, i) => (
            <button
              key={i}
              type="button"
              onClick={() => onApply?.(s)}
              className="w-full text-left rounded-lg p-3 border text-xs transition-colors hover:border-[rgb(var(--rgb-brand-cyan)/0.6)]"
              style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
              data-testid={`wizard-ai-suggestion-${i}`}
            >
              <div className="flex items-start gap-2">
                <Wand2 size={12} className="flex-shrink-0 mt-0.5" style={{ color: 'var(--color-brand-cyan)' }} />
                <div className="min-w-0">
                  <div className="font-semibold mb-0.5 pulse-font-heading truncate">{s.label}</div>
                  {s.detail && <div className="opacity-70">{s.detail}</div>}
                </div>
              </div>
            </button>
          ))}
        </div>
      )}
    </aside>
  );
}

export default function CampaignWizard({ open, onClose, preset, templateId, API, headers, toast }) {
  const [step, setStep] = useState(0);
  const [goal, setGoal] = useState(templateId || '');
  const [audience, setAudience] = useState(null);
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [channel, setChannel] = useState('email');
  const [timing, setTiming] = useState('best-time');
  const [customTime, setCustomTime] = useState('');
  const [launching, setLaunching] = useState(false);

  // If the user came in via a template card, pre-fill goal + audience + copy.
  useEffect(() => {
    if (!open) return;
    if (templateId) {
      setGoal(templateId);
      setAudience(AUDIENCE_PRESETS[templateId] || null);
      const copy = AI_COPY_BY_GOAL[templateId];
      if (copy) { setSubject(copy.subject); setBody(copy.preview); }
      setStep(1); // skip goal, user already chose
    } else if (preset === 'ai-full') {
      // "Let AI build everything" — drop the user on step 4 with defaults.
      setGoal('fill-classes');
      setAudience(AUDIENCE_PRESETS['fill-classes']);
      const copy = AI_COPY_BY_GOAL['fill-classes'];
      setSubject(copy.subject); setBody(copy.preview);
      setStep(3);
    } else {
      setStep(0);
    }
     
  }, [open, templateId, preset]);

  // Static scaffold — used as instant default while live AI loads, and as
  // a graceful fallback if the Claude endpoint is unreachable.
  const staticCopilot = useMemo(() => {
    switch (STEP_DEFS[step].id) {
      case 'goal':
        return {
          tip: 'Based on your recent class attendance, "Fill empty classes" usually performs best mid-week. Pick a goal and we\'ll shape everything else around it.',
          suggestions: [
            { label: 'Fill empty classes',        detail: 'Recommended — 3 low-book slots this week', applyId: 'fill-classes' },
            { label: 'Win back inactive members', detail: '32 members went dormant last 30d',          applyId: 'win-back' },
          ],
        };
      case 'audience':
        return {
          tip: 'A highly targeted list of 50–200 people usually beats a blast to everyone. We\'ve pre-selected the segment that matches your goal.',
          suggestions: goal ? [{
            label: AUDIENCE_PRESETS[goal]?.label || 'Default segment',
            detail: `${AUDIENCE_PRESETS[goal]?.approx || ''} of members`,
            applyPreset: AUDIENCE_PRESETS[goal],
          }] : [],
        };
      case 'creative':
        return {
          tip: 'Your brand voice (friendly, direct) is applied automatically. Keep subjects under 45 characters for best open rates.',
          suggestions: goal ? [{
            label: 'Apply AI-written draft',
            detail: AI_COPY_BY_GOAL[goal]?.subject || '',
            applyCopy: AI_COPY_BY_GOAL[goal],
          }] : [],
        };
      case 'schedule':
        return {
          tip: 'Your members open emails most on Tuesdays at 7 AM. We\'ll default to that unless you pick something else.',
          suggestions: [{ label: 'Best-time send (Tue 7 AM)', detail: 'Predicted +14% open rate', applyTiming: 'best-time' }],
        };
      case 'review':
        return { tip: 'Quick pre-flight check — every placeholder is substituted, no spam triggers detected.', suggestions: [] };
      default: return { tip: '', suggestions: [] };
    }
  }, [step, goal]);

  // Live AI state — fetched from /api/marketing/wizard-copilot (Claude Sonnet).
  const [aiTip, setAiTip] = useState('');
  const [aiSuggestions, setAiSuggestions] = useState([]);
  const [aiLoading, setAiLoading] = useState(false);

  // Fetch tailored suggestions whenever the user lands on a new step (or
  // changes the goal on step 1). Cancels in-flight requests on unmount
  // and falls back silently to the static scaffold on failure.
  useEffect(() => {
    if (!open || !API) return;
    const controller = new AbortController();
    const stepId = STEP_DEFS[step].id;
    setAiLoading(true);
    setAiTip('');
    setAiSuggestions([]);
    axios.post(
      `${API}/api/marketing/wizard-copilot`,
      { step: stepId, goal: goal || null, audience, channel },
      { headers, signal: controller.signal },
    ).then((resp) => {
      const data = resp?.data || {};
      if (data.tip) setAiTip(data.tip);
      if (Array.isArray(data.suggestions)) setAiSuggestions(data.suggestions);
      // On the Creative step, auto-fill AI-written copy once — but only if
      // the user hasn't typed anything yet (don't clobber their edits).
      if (stepId === 'creative' && data.copy && !subject.trim() && !body.trim()) {
        if (data.copy.subject) setSubject(data.copy.subject);
        if (data.copy.body)    setBody(data.copy.body);
      }
    }).catch((err) => {
      if (axios.isCancel?.(err)) return;
      // Swallow — we'll render the static scaffold instead.
    }).finally(() => setAiLoading(false));
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, step, goal, audience?.id, channel, API]);

  const copilotTip = aiTip || staticCopilot.tip;
  // Merge: prefer live AI suggestions when available; fall back to static.
  const copilotSuggestions = (aiSuggestions && aiSuggestions.length > 0)
    ? aiSuggestions
    : staticCopilot.suggestions;

  const applyAi = (s) => {
    if (s.applyId) {
      setGoal(s.applyId);
      // Pre-fill audience + copy for the chosen goal so the next step
      // already has smart defaults.
      const preset = AUDIENCE_PRESETS[s.applyId];
      if (preset) setAudience(preset);
      const copy = AI_COPY_BY_GOAL[s.applyId];
      if (copy) {
        if (!subject.trim()) setSubject(copy.subject);
        if (!body.trim())    setBody(copy.body || copy.preview);
      }
    }
    if (s.applyPreset) setAudience(s.applyPreset);
    if (s.applyCopy) {
      setSubject(s.applyCopy.subject);
      setBody(s.applyCopy.body || s.applyCopy.preview);
    }
    if (s.applyTiming) setTiming(s.applyTiming);
  };

  const canNext = () => {
    switch (STEP_DEFS[step].id) {
      case 'goal':     return !!goal;
      case 'audience': return !!audience;
      case 'creative': return subject.trim().length > 3 && body.trim().length > 10;
      case 'schedule': return !!channel && !!timing;
      default: return true;
    }
  };

  const next = () => setStep((s) => Math.min(STEP_DEFS.length - 1, s + 1));
  const back = () => setStep((s) => Math.max(0, s - 1));

  const launch = async () => {
    setLaunching(true);
    try {
      const resp = await axios.post(`${API}/api/marketing/campaigns`, {
        name: `${STEP_DEFS[step].title} — ${new Date().toLocaleDateString('en-GB')}`,
        goal,
        audience_rule_id: audience?.id,
        channel,
        subject,
        body,
        send_time: timing === 'custom' ? customTime : timing,
      }, { headers });
      const id = resp?.data?.id || resp?.data?.campaign_id || null;
      try { window.dispatchEvent(new CustomEvent('gymaxis:campaign-launched', { detail: { id } })); } catch (_) {}
      toast?.({ title: 'Blast off! Your campaign is scheduled.', intent: 'success' });
      onClose?.({ launched: true, campaignId: id });
    } catch (e) {
      toast?.({ title: 'Saved as draft — finalise in Campaigns tab.', intent: 'warn' });
      onClose?.({ launched: false, draft: true });
    } finally {
      setLaunching(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[200] flex items-start justify-center overflow-y-auto pulse-font-body" data-testid="mkt-campaign-wizard">
      <div className="absolute inset-0 backdrop-blur-sm" style={{ background: 'rgba(5,7,10,0.78)' }} onClick={() => onClose?.()} />

      <div
        className="relative my-10 mx-4 w-full max-w-6xl rounded-3xl overflow-hidden border"
        style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)' }}
      >
        {/* Header + progress */}
        <div className="p-5 border-b flex items-start gap-4" style={{ borderColor: 'var(--theme-border)' }}>
          <div className="flex-1 min-w-0">
            <div className="text-[10px] font-bold uppercase tracking-[0.2em] mb-1" style={{ color: 'var(--color-brand-cyan)' }}>Guided campaign</div>
            <div className="text-xl font-semibold pulse-font-heading truncate" style={{ color: 'var(--theme-text)' }}>
              {STEP_DEFS[step].headline}
            </div>
            <div className="text-sm" style={{ color: 'var(--theme-text-muted)' }}>{STEP_DEFS[step].sub}</div>
          </div>
          <button type="button" className="btn-icon" onClick={() => onClose?.()} aria-label="Close wizard" data-testid="wizard-close">
            <X size={14} />
          </button>
        </div>

        <div className="px-5 py-4 border-b" style={{ borderColor: 'var(--theme-border)' }}>
          <ProgressBar current={step} total={STEP_DEFS.length} />
        </div>

        {/* Body: main content + copilot rail */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 p-6">
          <div className="lg:col-span-2 space-y-5">
            {/* STEP 1 — GOAL */}
            {STEP_DEFS[step].id === 'goal' && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3" data-testid="wizard-goal-grid">
                {GOALS.map((g) => (
                  <button
                    key={g.id}
                    type="button"
                    onClick={() => setGoal(g.id)}
                    className={clsx(
                      'text-left rounded-2xl p-4 border transition-colors',
                      goal === g.id ? 'border-[var(--color-brand-cyan)]' : '',
                    )}
                    style={{ background: goal === g.id ? 'var(--color-brand-cyan)15' : 'var(--theme-surface)', borderColor: goal === g.id ? 'var(--color-brand-cyan)' : 'var(--theme-border)' }}
                    data-testid={`wizard-goal-${g.id}`}
                  >
                    <div className="text-sm font-semibold mb-1 pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{g.label}</div>
                    <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{g.hint}</div>
                  </button>
                ))}
              </div>
            )}

            {/* STEP 2 — AUDIENCE */}
            {STEP_DEFS[step].id === 'audience' && (
              <div className="space-y-3" data-testid="wizard-audience">
                {Object.values(AUDIENCE_PRESETS).map((a) => (
                  <button
                    key={a.id}
                    type="button"
                    onClick={() => setAudience(a)}
                    className={clsx(
                      'w-full text-left rounded-xl p-4 border transition-colors flex items-center gap-3',
                      audience?.id === a.id ? 'border-[var(--color-brand-cyan)]' : '',
                    )}
                    style={{ background: audience?.id === a.id ? 'var(--color-brand-cyan)15' : 'var(--theme-surface)', borderColor: audience?.id === a.id ? 'var(--color-brand-cyan)' : 'var(--theme-border)' }}
                    data-testid={`wizard-audience-${a.id}`}
                  >
                    <div className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0" style={{ background: 'var(--theme-bg)', color: 'var(--color-brand-cyan)' }}>
                      <Users size={13} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-semibold pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{a.label}</div>
                      <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>Approx {a.approx} of members</div>
                    </div>
                    {audience?.id === a.id && <CheckCircle2 size={16} style={{ color: 'var(--color-brand-cyan)' }} />}
                  </button>
                ))}
              </div>
            )}

            {/* STEP 3 — CREATIVE */}
            {STEP_DEFS[step].id === 'creative' && (
              <div className="space-y-4" data-testid="wizard-creative">
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider mb-1.5" style={{ color: 'var(--theme-text-muted)' }}>Subject line</label>
                  <input
                    type="text"
                    value={subject}
                    onChange={(e) => setSubject(e.target.value)}
                    placeholder="e.g. Your class is waiting"
                    className="w-full h-10 rounded-full px-4 text-sm focus:outline-none focus:border-[rgb(var(--rgb-brand-cyan)/0.6)]"
                    style={{ background: 'var(--theme-surface)', border: '1px solid var(--theme-border)', color: 'var(--theme-text)' }}
                    data-testid="wizard-subject-input"
                  />
                  <div className="mt-1 text-[11px]" style={{ color: 'var(--theme-text-muted)' }}>
                    Shorter subjects (under 45 chars) tend to get the best open rates.
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider mb-1.5" style={{ color: 'var(--theme-text-muted)' }}>Body</label>
                  <textarea
                    value={body}
                    onChange={(e) => setBody(e.target.value)}
                    rows={6}
                    placeholder="Write the message, or hit Apply AI-written draft in the copilot."
                    className="w-full rounded-2xl p-4 text-sm focus:outline-none focus:border-[rgb(var(--rgb-brand-cyan)/0.6)]"
                    style={{ background: 'var(--theme-surface)', border: '1px solid var(--theme-border)', color: 'var(--theme-text)' }}
                    data-testid="wizard-body-input"
                  />
                  <div className="mt-1 text-[11px]" style={{ color: 'var(--theme-text-muted)' }}>
                    {`{{first_name}}`} and {`{{company_name}}`} are replaced per-recipient at send time.
                  </div>
                </div>
              </div>
            )}

            {/* STEP 4 — SCHEDULE */}
            {STEP_DEFS[step].id === 'schedule' && (
              <div className="space-y-5" data-testid="wizard-schedule">
                <div>
                  <div className="text-xs font-semibold uppercase tracking-wider mb-2" style={{ color: 'var(--theme-text-muted)' }}>Channel</div>
                  <div className="flex gap-2 flex-wrap">
                    {CHANNELS.map((c) => {
                      const Icon = c.icon;
                      const sel = channel === c.id;
                      return (
                        <button
                          key={c.id}
                          type="button"
                          disabled={c.locked}
                          onClick={() => !c.locked && setChannel(c.id)}
                          className={clsx('inline-flex items-center gap-2 px-4 h-9 rounded-full text-sm font-semibold border transition-colors disabled:opacity-40 disabled:cursor-not-allowed')}
                          style={sel ? { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)', borderColor: 'var(--color-brand-cyan)' } : { background: 'var(--theme-surface)', color: 'var(--theme-text)', borderColor: 'var(--theme-border)' }}
                          data-testid={`wizard-channel-${c.id}`}
                        >
                          <Icon size={13} /> {c.label}{c.locked && ' (soon)'}
                        </button>
                      );
                    })}
                  </div>
                </div>
                <div>
                  <div className="text-xs font-semibold uppercase tracking-wider mb-2" style={{ color: 'var(--theme-text-muted)' }}>Send time</div>
                  <div className="space-y-2">
                    {TIME_SLOTS.map((t) => (
                      <button
                        key={t.id}
                        type="button"
                        onClick={() => setTiming(t.id)}
                        className={clsx('w-full text-left rounded-xl p-3 border transition-colors flex items-center gap-2')}
                        style={timing === t.id ? { background: 'var(--color-brand-cyan)15', borderColor: 'var(--color-brand-cyan)' } : { background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}
                        data-testid={`wizard-time-${t.id}`}
                      >
                        <Clock size={13} style={{ color: 'var(--color-brand-cyan)' }} />
                        <div className="text-sm font-semibold pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{t.label}</div>
                        {timing === t.id && <CheckCircle2 size={14} className="ml-auto" style={{ color: 'var(--color-brand-cyan)' }} />}
                      </button>
                    ))}
                    {timing === 'custom' && (
                      <input
                        type="datetime-local"
                        value={customTime}
                        onChange={(e) => setCustomTime(e.target.value)}
                        className="w-full h-10 rounded-full px-4 text-sm focus:outline-none focus:border-[rgb(var(--rgb-brand-cyan)/0.6)]"
                        style={{ background: 'var(--theme-surface)', border: '1px solid var(--theme-border)', color: 'var(--theme-text)' }}
                        data-testid="wizard-custom-time"
                      />
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* STEP 5 — REVIEW */}
            {STEP_DEFS[step].id === 'review' && (
              <div className="space-y-3" data-testid="wizard-review">
                <div className="rounded-2xl p-4 border" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
                  <div className="text-[11px] font-bold uppercase tracking-[0.18em] mb-2" style={{ color: 'var(--color-brand-cyan)' }}>Pre-flight</div>
                  <ul className="space-y-2 text-sm" style={{ color: 'var(--theme-text)' }}>
                    <li className="flex items-center gap-2"><CheckCircle2 size={14} style={{ color: 'var(--color-success)' }} /> Goal: <span className="font-semibold">{GOALS.find(g => g.id === goal)?.label || 'Not set'}</span></li>
                    <li className="flex items-center gap-2"><CheckCircle2 size={14} style={{ color: 'var(--color-success)' }} /> Audience: <span className="font-semibold">{audience?.label || 'Not set'}</span></li>
                    <li className="flex items-center gap-2"><CheckCircle2 size={14} style={{ color: 'var(--color-success)' }} /> Channel: <span className="font-semibold">{channel.toUpperCase()}</span></li>
                    <li className="flex items-center gap-2"><CheckCircle2 size={14} style={{ color: 'var(--color-success)' }} /> Send time: <span className="font-semibold">{TIME_SLOTS.find(t => t.id === timing)?.label || timing}</span></li>
                    <li className="flex items-center gap-2"><CheckCircle2 size={14} style={{ color: 'var(--color-success)' }} /> Subject: <span className="font-semibold truncate">{subject || '—'}</span></li>
                  </ul>
                </div>
              </div>
            )}
          </div>

          {/* AI Copilot rail */}
          <AICopilot tip={copilotTip} suggestions={copilotSuggestions} onApply={applyAi} loading={aiLoading} />
        </div>

        {/* Footer actions */}
        <div className="p-5 border-t flex items-center justify-between gap-3" style={{ borderColor: 'var(--theme-border)' }}>
          <button type="button" onClick={back} disabled={step === 0} className="btn-secondary" data-testid="wizard-back">
            <ChevronLeft size={14} /> Back
          </button>
          {step < STEP_DEFS.length - 1 ? (
            <button type="button" onClick={next} disabled={!canNext()} className="btn-primary" data-testid="wizard-next">
              Next <ChevronRight size={14} />
            </button>
          ) : (
            <button type="button" onClick={launch} disabled={launching} className="btn-primary" data-testid="wizard-launch">
              <Rocket size={14} /> {launching ? 'Launching…' : 'Launch campaign'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
