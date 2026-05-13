/**
 * Marketing Suite — Start tab (guided experience layer).
 *
 * A "home" for the Marketing module that follows the 5-part structure:
 *  1. Section Overview           — title + single-sentence promise
 *  2. What You Can Achieve       — 4 outcome cards with icons
 *  3. Step-by-step Actions       — clickable 5-step tease for the wizard
 *  4. Quick Start                — 3 big CTAs (60-sec campaign, Template, AI)
 *  5. Templates                  — 4 pre-built campaign blueprints
 *  6. Suggested Next Steps       — contextual nudges once a campaign ships
 *
 * This tab DOES NOT replace any existing Marketing functionality. It acts as
 * a guided overlay that funnels the user into either (a) the CampaignWizard
 * for a guided build, (b) an existing tab (Audiences / Creative / Campaigns)
 * for a power-user workflow, or (c) a templated quick-launch.
 */
import React, { useMemo } from 'react';
import {
  Zap, Target, Users, Sparkles, Calendar, ArrowRight, Send, TrendingUp,
  HeartHandshake, Dumbbell, PartyPopper, CheckCircle2, Flame, EyeOff,
} from 'lucide-react';
import { useUserPref } from '@/utils/userPrefs';
import ActivationMilestonesCard from '@/components/shared/ActivationMilestonesCard';

const OUTCOMES = [
  { icon: Calendar,   title: 'Fill empty classes',        note: 'Automated nudges for low-attendance sessions' },
  { icon: HeartHandshake, title: 'Re-engage inactive members', note: 'Win back lapsed members with the right offer' },
  { icon: Dumbbell,   title: 'Promote new services',      note: 'Launch classes, PT, or events to the right segment' },
  { icon: TrendingUp, title: 'Increase revenue',          note: 'Upsell PT, merch, and add-ons to fitting buyers' },
];

const STEPS = [
  { n: 1, title: 'Choose your goal',     note: 'What outcome do you want?' },
  { n: 2, title: 'Select your audience', note: 'Who should receive this?' },
  { n: 3, title: 'Create your content',  note: 'AI writes copy + imagery' },
  { n: 4, title: 'Schedule your send',   note: 'Pick channels + best time' },
  { n: 5, title: 'Launch & track',       note: 'Live results in Performance' },
];

const TEMPLATES = [
  {
    id: 'fill-classes',
    title: 'Fill empty classes',
    desc: 'Target members who haven\'t booked this week. AI suggests the class with most open slots.',
    cover: 'https://images.unsplash.com/photo-1773558057883-c15a220761ce?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjAzMjV8MHwxfHNlYXJjaHwyfHxhYnN0cmFjdCUyMGRhcmslMjBiYWNrZ3JvdW5kJTIwZ2xvd2luZyUyMGJsdWUlMjBuZW9ufGVufDB8fHx8MTc3NzMxNzkyNHww&ixlib=rb-4.1.0&q=85&w=800',
    accent: 'from-[rgb(var(--rgb-brand-cyan)/0.2)] to-transparent',
    icon: Calendar,
  },
  {
    id: 'win-back',
    title: 'Win back inactive members',
    desc: 'Haven\'t checked in for 30+ days? This template offers a comeback incentive.',
    cover: 'https://images.unsplash.com/photo-1759735541630-036eefb7cd3a?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjAzMjV8MHwxfHNlYXJjaHwxfHxhYnN0cmFjdCUyMGRhcmslMjBiYWNrZ3JvdW5kJTIwZ2xvd2luZyUyMGJsdWUlMjBuZW9ufGVufDB8fHx8MTc3NzMxNzkyNHww&ixlib=rb-4.1.0&q=85&w=800',
    accent: 'from-fuchsia-500/20 to-transparent',
    icon: HeartHandshake,
  },
  {
    id: 'promote-class',
    title: 'Promote a new class',
    desc: 'Announce a new class to members most likely to attend based on history.',
    cover: 'https://images.pexels.com/photos/9404662/pexels-photo-9404662.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=450&w=800',
    accent: 'from-[rgb(var(--rgb-success)/0.2)] to-transparent',
    icon: PartyPopper,
  },
  {
    id: 'upsell-pt',
    title: 'Upsell Personal Training',
    desc: 'Target members with 2+ weeks of consistent attendance — they\'re ready for PT.',
    cover: 'https://images.unsplash.com/photo-1776106904780-88a00fc3d393?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjAzMjV8MHwxfHNlYXJjaHw0fHxhYnN0cmFjdCUyMGRhcmslMjBiYWNrZ3JvdW5kJTIwZ2xvd2luZyUyMGJsdWUlMjBuZW9ufGVufDB8fHx8MTc3NzMxNzkyNHww&ixlib=rb-4.1.0&q=85&w=800',
    accent: 'from-amber-500/20 to-transparent',
    icon: Flame,
  },
];

const OutcomeCard = ({ icon: Icon, title, note }) => (
  <div
    className="rounded-2xl p-4 border transition-colors"
    style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}
    data-testid={`mkt-outcome-${title.toLowerCase().replace(/\s+/g, '-')}`}
  >
    <div className="w-9 h-9 rounded-full flex items-center justify-center mb-3" style={{ background: 'var(--color-brand-cyan)22', color: 'var(--color-brand-cyan)' }}>
      <Icon size={16} />
    </div>
    <div className="text-sm font-semibold mb-1 pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{title}</div>
    <div className="text-xs pulse-font-body" style={{ color: 'var(--theme-text-muted)' }}>{note}</div>
  </div>
);

export default function StartTab({ openWizard, setTab }) {
  // eslint-disable-next-line no-unused-vars
  const [, setHideStart] = useUserPref('hideStartTabs', false);
  const quickStart = useMemo(() => [
    { id: 'qs-60sec',   title: 'Create campaign in 60 seconds', desc: 'AI picks audience + writes content', icon: Zap,      cta: () => openWizard({ preset: 'fast' }) },
    { id: 'qs-template', title: 'Start from a template',         desc: 'Pre-built for the most common gym goals', icon: Target,   cta: () => openWizard({ preset: 'template' }) },
    { id: 'qs-ai',      title: 'Let AI build everything',       desc: 'Goal → audience → creative → schedule',    icon: Sparkles, cta: () => openWizard({ preset: 'ai-full' }) },
  ], [openWizard]);

  return (
    <div className="space-y-8 pulse-font-body" data-testid="mkt-start-tab">
      {/* Iter 216h70 — same auto-hiding "first wins" checklist that the
          other modules show. Once every milestone fires, the card
          flips `hideStartTabs=true` and Start disappears from the tab
          bar (Dashboard becomes the new first tab) — matching the
          rest of the platform's onboarding pattern. */}
      <ActivationMilestonesCard />

      {/* 1. SECTION OVERVIEW */}
      <div>
        <h2 className="text-2xl sm:text-3xl tracking-tight font-semibold pulse-font-heading mb-1" style={{ color: 'var(--theme-text)' }}>
          Your Marketing Command Center
        </h2>
        <p className="text-sm" style={{ color: 'var(--theme-text-muted)' }}>
          Create and launch targeted campaigns that increase bookings and retention.
          Any user can run a high-quality campaign in minutes — no marketing background needed.
        </p>
        <button
          type="button"
          onClick={() => { setHideStart(true); setTab('insights'); }}
          className="mt-2 inline-flex items-center gap-1 text-xs opacity-70 hover:opacity-100"
          style={{ color: 'var(--theme-text-muted)' }}
          data-testid="mkt-hide-start-btn"
        >
          <EyeOff size={11} /> Hide this tab
        </button>
      </div>

      {/* 2. WHAT YOU CAN ACHIEVE */}
      <section data-testid="mkt-outcomes">
        <div className="text-[11px] font-bold uppercase tracking-[0.18em] mb-3" style={{ color: 'var(--color-brand-cyan)' }}>
          What you can achieve
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {OUTCOMES.map((o) => (
            <OutcomeCard key={o.title} {...o} />
          ))}
        </div>
      </section>

      {/* 3. QUICK START */}
      <section data-testid="mkt-quick-start">
        <div className="text-[11px] font-bold uppercase tracking-[0.18em] mb-3" style={{ color: 'var(--color-brand-cyan)' }}>
          Quick start
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {quickStart.map((q) => {
            const Icon = q.icon;
            return (
              <button
                key={q.id}
                type="button"
                onClick={q.cta}
                className="group rounded-2xl p-5 text-left border transition-all hover:-translate-y-0.5 hover:border-[rgb(var(--rgb-brand-cyan)/0.6)]"
                style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}
                data-testid={q.id}
              >
                <div className="flex items-start justify-between mb-6">
                  <div className="w-10 h-10 rounded-full flex items-center justify-center" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}>
                    <Icon size={18} />
                  </div>
                  <ArrowRight size={16} className="opacity-40 group-hover:opacity-100 group-hover:text-[var(--color-brand-cyan)] transition-all" />
                </div>
                <div className="text-base font-semibold mb-1 pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{q.title}</div>
                <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{q.desc}</div>
              </button>
            );
          })}
        </div>
      </section>

      {/* 4. STEP-BY-STEP PREVIEW */}
      <section data-testid="mkt-steps-preview">
        <div className="text-[11px] font-bold uppercase tracking-[0.18em] mb-3" style={{ color: 'var(--color-brand-cyan)' }}>
          How the guided campaign works
        </div>
        <ol className="grid grid-cols-1 md:grid-cols-5 gap-2 rounded-2xl p-3 border" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
          {STEPS.map((s, i) => (
            <li key={s.n} className="flex items-start gap-3 p-2">
              <div className="w-7 h-7 rounded-full flex-shrink-0 flex items-center justify-center text-xs font-bold pulse-font-heading" style={{ background: 'var(--color-brand-cyan)22', color: 'var(--color-brand-cyan)' }}>
                {s.n}
              </div>
              <div className="min-w-0">
                <div className="text-sm font-semibold truncate pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{s.title}</div>
                <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{s.note}</div>
              </div>
              {i < STEPS.length - 1 && (
                <div className="hidden md:block flex-1 h-px self-center" style={{ background: 'var(--theme-border)' }} />
              )}
            </li>
          ))}
        </ol>
        <div className="mt-3">
          <button type="button" onClick={() => openWizard({ preset: 'wizard' })} className="btn-primary" data-testid="mkt-start-wizard-btn">
            <Send size={14} /> Start guided campaign
          </button>
        </div>
      </section>

      {/* 5. TEMPLATES */}
      <section data-testid="mkt-templates">
        <div className="text-[11px] font-bold uppercase tracking-[0.18em] mb-3" style={{ color: 'var(--color-brand-cyan)' }}>
          Pre-built templates
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {TEMPLATES.map((t) => {
            const Icon = t.icon;
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => openWizard({ preset: 'template', templateId: t.id })}
                className="group text-left rounded-2xl overflow-hidden border transition-all hover:-translate-y-0.5 hover:border-[rgb(var(--rgb-brand-cyan)/0.6)]"
                style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}
                data-testid={`mkt-template-${t.id}`}
              >
                <div className="relative h-28 overflow-hidden">
                  <img src={t.cover} alt="" className="w-full h-full object-cover opacity-60 group-hover:opacity-80 transition-opacity" loading="lazy" />
                  <div className={`absolute inset-0 bg-gradient-to-b ${t.accent}`} />
                  <div className="absolute top-3 left-3 w-8 h-8 rounded-full flex items-center justify-center" style={{ background: 'var(--color-ink)CC', color: 'var(--color-brand-cyan)' }}>
                    <Icon size={14} />
                  </div>
                </div>
                <div className="p-4">
                  <div className="text-sm font-semibold mb-1 pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{t.title}</div>
                  <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{t.desc}</div>
                  <div className="mt-3 text-xs font-semibold inline-flex items-center gap-1" style={{ color: 'var(--color-brand-cyan)' }}>
                    Use this template <ArrowRight size={12} />
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </section>

      {/* 6. SUGGESTED NEXT STEPS — entry points into existing tabs */}
      <section data-testid="mkt-next-steps">
        <div className="text-[11px] font-bold uppercase tracking-[0.18em] mb-3" style={{ color: 'var(--color-brand-cyan)' }}>
          Or jump straight in
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {[
            { label: 'Build an audience',   tab: 'audiences',  icon: Users,     desc: 'Segment by behaviour or lifecycle' },
            { label: 'Design an image',     tab: 'creative',   icon: Sparkles,  desc: 'AI-generated posters and socials' },
            { label: 'See what\'s working', tab: 'performance', icon: CheckCircle2, desc: 'Channel-level performance last 30 days' },
          ].map((j) => {
            const Icon = j.icon;
            return (
              <button
                key={j.tab}
                type="button"
                onClick={() => setTab(j.tab)}
                className="group rounded-xl p-4 border text-left transition-colors hover:border-[rgb(var(--rgb-brand-cyan)/0.6)] flex items-center gap-3"
                style={{ background: 'transparent', borderColor: 'var(--theme-border)' }}
                data-testid={`mkt-jump-${j.tab}`}
              >
                <div className="w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0" style={{ background: 'var(--theme-surface)', color: 'var(--color-brand-cyan)' }}>
                  <Icon size={14} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{j.label}</div>
                  <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{j.desc}</div>
                </div>
                <ArrowRight size={14} className="opacity-40 group-hover:opacity-100 transition-opacity" style={{ color: 'var(--color-brand-cyan)' }} />
              </button>
            );
          })}
        </div>
      </section>
    </div>
  );
}
