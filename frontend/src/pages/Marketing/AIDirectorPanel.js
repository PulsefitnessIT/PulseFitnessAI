/**
 * AI Creative Director — Phase 1+2
 *
 * Single prompt → full campaign brief (strategy + audience + multi-format
 * copy pack + Gemini-generated branded poster).
 *
 * UX (top → bottom):
 *   1. Prompt-first input (like ChatGPT) with goal & tone selectors
 *   2. "Generate Campaign" → ~30-60s wait → full brief returned
 *   3. Strategy card (audience, channels, schedule)
 *   4. Poster preview with regenerate button
 *   5. Channel cards (email/IG/FB/SMS/push) — copyable, individually refinable
 *   6. Alt-tones grid (A/B variants)
 *   7. "Make it better" toolbar (punchier, urgency, shorter, premium)
 *   8. "Launch as campaign" CTA
 */
import { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  Sparkles, Loader2, Wand2, RefreshCw, Copy, Send, Mail, Instagram, Facebook,
  MessageSquare, Bell, Image as ImageIcon, ChevronRight, Megaphone, Target,
  Clock, Users, Zap, Check, Edit3, Lock, Rocket, X,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import Button from '@/components/shared/Button';
import RowActions from '@/components/shared/RowActions';

const CHANNEL_META = {
  email:     { icon: Mail,           label: 'Email',     color: 'text-blue-500' },
  instagram: { icon: Instagram,      label: 'Instagram', color: 'text-pink-500' },
  facebook:  { icon: Facebook,       label: 'Facebook',  color: 'text-indigo-500' },
  sms:       { icon: MessageSquare,  label: 'SMS',       color: 'text-emerald-500' },
  push:      { icon: Bell,           label: 'Push',      color: 'text-amber-500' },
  poster:    { icon: ImageIcon,      label: 'Poster',    color: 'text-violet-500' },
};

const FALLBACK_TONES = [
  { key: 'high_energy', label: 'High Energy' },
  { key: 'motivational', label: 'Motivational' },
  { key: 'premium', label: 'Premium' },
  { key: 'community', label: 'Community' },
  { key: 'urgent', label: 'Urgent' },
  { key: 'friendly', label: 'Friendly' },
  { key: 'wellness', label: 'Wellness' },
  { key: 'expert_coach', label: 'Expert Coach' },
  { key: 'family', label: 'Family' },
  { key: 'mod_military', label: 'MOD / Military' },
  { key: 'corporate', label: 'Corporate' },
];

const FALLBACK_GOALS = [
  { key: 'promote_class', label: 'Promote a class' },
  { key: 'winback_lapsed', label: 'Winback lapsed members' },
  { key: 'upgrade_pt', label: 'Upsell to PT' },
  { key: 'new_member_welcome', label: 'New member welcome' },
  { key: 'open_day', label: 'Open day / event' },
  { key: 'referral', label: 'Drive referrals' },
  { key: 'renewal', label: 'Renewals' },
  { key: 'off_peak', label: 'Off-peak fill' },
  { key: 'challenge', label: 'Fitness challenge' },
  { key: 'newsletter', label: 'Newsletter' },
];

const SEGMENT_OPTIONS = [
  { key: 'lapsed_30d',       label: 'Lapsed 30d',       hint: 'Hasn\'t visited in 30+ days' },
  { key: 'active_regulars',  label: 'Active regulars',  hint: 'Visits 3+/week' },
  { key: 'new_members_30d',  label: 'New members',      hint: 'Joined in last 30 days' },
  { key: 'pt_eligible',      label: 'PT eligible',      hint: 'Regular but no PT yet' },
  { key: 'off_peak_visitors',label: 'Off-peak crowd',   hint: 'Pre-10am or post-7pm' },
  { key: 'frozen_members',   label: 'Frozen members',   hint: 'Plan currently on freeze' },
];

const REFINE_QUICKACTIONS = [
  { label: 'Make it punchier',   instr: 'Make every line punchier and shorter; cut filler' },
  { label: 'Add urgency',        instr: 'Add tasteful urgency — limited spots, ends soon' },
  { label: 'Less salesy',        instr: 'Soften the sales tone; lead with member benefit' },
  { label: 'More premium',       instr: 'Elevate the tone to premium / boutique-club polish' },
  { label: 'Highlight the offer', instr: 'Lead every channel with the offer/value clearly' },
  { label: 'Friendlier voice',   instr: 'Make the voice warmer and more conversational' },
];

// ── Iter 216h113i — Pre-built campaign templates ───────────────────
// One-click starter briefs that pre-fill the prompt + goal + tone +
// audience hint, so a customer can hit "Generate Campaign" within
// 5 seconds of opening the Director and get a poster using their
// saved brand kit (logo, primary/secondary colours, heading & body
// fonts). Tagline shown on hover.
const QUICKSTART_TEMPLATES = [
  {
    id: 'join_now',
    label: 'Join now',
    tagline: 'Headline join offer — works year-round',
    goal: 'new_member_welcome',
    tone: 'high_energy',
    audience: 'prospects',
    prompt: 'Join now — flagship membership offer poster for prospects who have visited the website but not yet signed up. Lead with one bold benefit, finish with a strong CTA.',
  },
  {
    id: 'refer_a_friend',
    label: 'Refer a friend',
    tagline: 'Member-get-member referral push',
    goal: 'referral',
    tone: 'community',
    audience: 'active_regulars',
    prompt: 'Refer a friend — share-worthy social poster for our active regulars. Both members get one free month when their friend joins.',
  },
  {
    id: 'pt_kickstart',
    label: 'PT kickstart',
    tagline: 'Free intro PT session for engaged members',
    goal: 'upgrade_pt',
    tone: 'premium',
    audience: 'pt_eligible',
    prompt: 'PT kickstart — premium poster offering a free 1-on-1 PT intro session to members who have trained 8+ times in the last month but never booked PT.',
  },
  {
    id: 'open_day',
    label: 'Open day',
    tagline: 'Free guest day to drive walk-ins',
    goal: 'open_day',
    tone: 'community',
    audience: 'prospects',
    prompt: 'Open day — bring-a-friend day at the club, free guest entry, complimentary class. Encourage walk-ins; lead with the date.',
  },
  {
    id: 'winback',
    label: 'Win-back lapsed',
    tagline: 'Reactivate members inactive 30+ days',
    goal: 'winback_lapsed',
    tone: 'motivational',
    audience: 'lapsed_30d',
    prompt: 'Win-back poster for lapsed members — speak to the temporary nature of life getting in the way and offer 20% off the next month to come back.',
  },
  {
    id: 'class_promo',
    label: 'Class promo',
    tagline: 'Fill an under-booked signature class',
    goal: 'promote_class',
    tone: 'high_energy',
    audience: 'off_peak_visitors',
    prompt: 'Class promo poster for our signature Saturday morning spin class. High energy, soundtrack-led, get on a bike with a friend.',
  },
  {
    id: 'newsletter',
    label: 'Monthly newsletter',
    tagline: 'House-style monthly digest cover',
    goal: 'newsletter',
    tone: 'premium',
    audience: 'active_regulars',
    prompt: 'Monthly newsletter cover — premium magazine-style layout featuring this month\u2019s standout classes, member story, and recovery tip.',
  },
  {
    id: 'challenge',
    label: '30-day challenge',
    tagline: 'Community fitness challenge launch',
    goal: 'challenge',
    tone: 'motivational',
    audience: 'active_regulars',
    prompt: '30-day challenge launch poster — community-driven, set a measurable goal (e.g. 20 sessions this month), prizes for top three.',
  },
];

const AIDirectorPanel = ({ API, headers, entitlement, seedBriefId, onSeedConsumed }) => {
  const [presets, setPresets] = useState({ tones: FALLBACK_TONES, goals: FALLBACK_GOALS, channels: [] });
  const [recentBriefs, setRecentBriefs] = useState([]);

  const [prompt, setPrompt] = useState('');
  const [goal, setGoal] = useState('');
  const [tone, setTone] = useState('high_energy');
  const [audienceHint, setAudienceHint] = useState('');
  const [brandLock, setBrandLock] = useState(true);
  const [resPreset, setResPreset] = useState('1080x1350');
  const [segmentKeys, setSegmentKeys] = useState([]);

  const [busy, setBusy] = useState(false);
  const [refineBusy, setRefineBusy] = useState(false);
  const [brief, setBrief] = useState(null);
  const [autoPilot, setAutoPilot] = useState(false);
  const [perRecipient, setPerRecipient] = useState(false);
  const [optimalWindow, setOptimalWindow] = useState(null);
  const [coverage, setCoverage] = useState(null);

  // Phase 7 — fetch the org's optimal send window for autopilot UX hints
  useEffect(() => {
    (async () => {
      try {
        const [w, c] = await Promise.all([
          axios.get(`${API}/api/marketing/creative/director/optimal-window`, { headers }),
          axios.get(`${API}/api/marketing/creative/director/per-recipient-coverage`, { headers }),
        ]);
        setOptimalWindow(w.data);
        setCoverage(c.data);
      } catch { /* soft-fail */ }
    })();
  }, [API, headers]);

  const locked = entitlement && !entitlement.features?.ai_creative_studio;

  useEffect(() => {
    (async () => {
      try {
        const [presetsR, briefsR] = await Promise.all([
          axios.get(`${API}/api/marketing/creative/director/presets`, { headers }),
          axios.get(`${API}/api/marketing/creative/director/briefs`, { headers }),
        ]);
        setPresets(presetsR.data || {});
        setRecentBriefs(briefsR.data?.briefs || []);
      } catch (e) {
        // soft-fail; the form still works
      }
    })();
  }, [API, headers]);

  // Phase 4 — load a seeded brief from the legacy Single-Asset tab
  useEffect(() => {
    if (seedBriefId) {
      loadBrief(seedBriefId);
      onSeedConsumed?.();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — effect either runs once on mount or re-fires on the listed trigger deps; omitted refs are stable identities or fetcher closures that read live state at call time, so including them would re-fire without changing semantics.
  }, [seedBriefId]);

  // Dedup — accept a seed prompt forwarded from the floating AI Assistant
  useEffect(() => {
    const handler = (e) => {
      const seedPrompt = e?.detail?.prompt;
      if (seedPrompt) {
        setPrompt(seedPrompt);
        setBrief(null);
        const el = document.querySelector('[data-testid="director-prompt-input"]');
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        notify.success('Prompt brought across from AI Assistant — review and hit Generate');
      }
    };
    window.addEventListener('director:seed-prompt', handler);
    return () => window.removeEventListener('director:seed-prompt', handler);
  }, []);

  const resolution = useMemo(() => {
    const [w, h] = resPreset.split('x').map((n) => parseInt(n, 10));
    return { w, h };
  }, [resPreset]);

  const generate = async () => {
    if (!prompt.trim()) {
      notify.error('Tell the Director what to promote');
      return;
    }
    setBusy(true);
    setBrief(null);
    try {
      const r = await axios.post(`${API}/api/marketing/creative/director/build`, {
        prompt, goal, tone, audience_hint: audienceHint, brand_lock: brandLock,
        resolution, segment_keys: segmentKeys,
      }, { headers, timeout: 240000 });
      setBrief(r.data);
      notify.success('Director draft ready — review and refine');
      const list = await axios.get(`${API}/api/marketing/creative/director/briefs`, { headers });
      setRecentBriefs(list.data?.briefs || []);
    } catch (e) {
      notifyApiError(notify, e, 'Director failed — please try again');
    }
    setBusy(false);
  };

  const refine = async (instruction, channel = null, regenerateImage = false) => {
    if (!brief?.id) return;
    setRefineBusy(true);
    try {
      const r = await axios.post(`${API}/api/marketing/creative/director/refine`, {
        brief_id: brief.id, instruction, channel, regenerate_image: regenerateImage,
      }, { headers, timeout: 120000 });
      setBrief(r.data);
      notify.success('Refined');
    } catch (e) {
      notifyApiError(notify, e, 'Refine failed');
    }
    setRefineBusy(false);
  };

  const launchAsCampaign = async () => {
    if (!brief?.id) return;
    try {
      const r = await axios.post(
        `${API}/api/marketing/creative/director/briefs/${brief.id}/launch`,
        { auto_pilot: autoPilot, auto_post_mortem: true, per_recipient_timing: perRecipient },
        { headers },
      );
      const note = r.data?.scheduled_for
        ? `Scheduled for ${optimalWindow?.label || 'optimal window'}`
        : (r.data?.already_launched ? 'Already launched as a campaign' : 'Campaign created — find it on the Campaigns tab');
      notify.success(note);
      setBrief({ ...brief, campaign_id: r.data.campaign_id, scheduled_for: r.data.scheduled_for });
    } catch (e) {
      notifyApiError(notify, e, 'Launch failed');
    }
  };

  const loadBrief = async (id) => {
    setBusy(true);
    try {
      const r = await axios.get(`${API}/api/marketing/creative/director/briefs/${id}`, { headers });
      setBrief(r.data);
    } catch {
      notify.error('Could not load brief');
    }
    setBusy(false);
  };

  if (locked) {
    return (
      <div className="rounded-xl border border-amber-200 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/40 p-6 text-center" data-testid="ai-director-locked">
        <Lock className="mx-auto text-amber-500 mb-2" size={28} />
        <h2 className="text-lg font-bold text-zinc-900 dark:text-zinc-100">AI Creative Director is a Pro feature</h2>
        <p className="text-sm text-zinc-600 dark:text-zinc-400 mt-1">Upgrade to Pro to generate full campaigns from a single prompt.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid="ai-director-panel">

      {/* ── Prompt hero ───────────────────────────────────────────── */}
      <div className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-gradient-to-br from-white via-white to-blue-50/30 dark:from-zinc-900 dark:via-zinc-900 dark:to-blue-950/10 p-5 shadow-sm">
        <div className="flex items-center gap-2 mb-3">
          <Sparkles className="text-[var(--color-brand-blue)]" size={18} />
          <h2 className="text-lg font-bold text-zinc-900 dark:text-zinc-100">AI Creative Director</h2>
          <span className="ml-2 text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-[rgb(var(--rgb-brand-blue)/0.1)] text-[var(--color-brand-blue)]">Phase 1</span>
        </div>
        <p className="text-xs text-zinc-500 dark:text-zinc-400 mb-3">
          One prompt → full campaign. Strategy, multi-format copy (email/IG/FB/SMS/push),
          and a branded Gemini poster — under 60 seconds.
        </p>

        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="e.g. Promote Saturday morning spin classes to members who haven't attended in 30+ days"
          rows={3}
          className="w-full px-3 py-2.5 border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100 rounded-lg text-sm focus:outline-none focus:border-[var(--color-brand-blue)] resize-none"
          data-testid="director-prompt-input"
        />

        {/* ── Quick-start templates (Iter 216h113i) ──────────────────
            Pre-built campaigns that customers can launch with one click.
            They pre-fill the prompt + goal + tone so the AI generates a
            poster using the customer's saved brand kit immediately. */}
        <div className="mt-3">
          <p className="text-[10px] uppercase tracking-wider text-zinc-500 dark:text-zinc-400 mb-1.5 font-semibold flex items-center gap-1">
            <Sparkles size={10}/> Quick-start templates <span className="text-[9px] font-normal text-zinc-400">— one click, brand-kit applied</span>
          </p>
          <div className="flex flex-wrap gap-1.5">
            {QUICKSTART_TEMPLATES.map((qs) => (
              <button
                key={qs.id}
                type="button"
                onClick={() => {
                  setPrompt(qs.prompt);
                  setGoal(qs.goal);
                  setTone(qs.tone);
                  if (qs.audience) setAudienceHint(qs.audience);
                }}
                title={qs.tagline}
                className="px-3 py-1.5 rounded-full text-[11px] font-semibold border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-950 text-zinc-700 dark:text-zinc-200 hover:border-[var(--color-brand-blue)] hover:text-[var(--color-brand-blue)] transition"
                data-testid={`director-quickstart-${qs.id}`}
              >
                {qs.label}
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-3">
          <Select label="Goal" value={goal} onChange={setGoal} testId="director-goal"
            options={[{ key: '', label: '— optional —' }, ...(presets.goals || [])]} />
          <Select label="Tone" value={tone} onChange={setTone} testId="director-tone"
            options={(presets.tones || []).map((t) => ({ key: t.key, label: t.label, hint: t.hint }))} />
          <Select label="Resolution" value={resPreset} onChange={setResPreset} testId="director-resolution"
            options={[
              { key: '1080x1350', label: 'Instagram portrait (1080×1350)' },
              { key: '1080x1080', label: 'Square (1080×1080)' },
              { key: '1080x1920', label: 'Story / Reel (1080×1920)' },
              { key: '1200x628',  label: 'Facebook / email (1200×628)' },
              { key: '2480x3508', label: 'A4 print poster' },
            ]} />
          <div>
            <p className="text-[10px] uppercase tracking-wider text-zinc-500 dark:text-zinc-400 mb-1 font-semibold">Brand lock</p>
            <button onClick={() => setBrandLock((v) => !v)}
              className={`w-full px-2 py-2 rounded-md text-xs font-medium border ${
                brandLock
                  ? 'bg-[var(--color-brand-blue)] text-white border-[var(--color-brand-blue)]'
                  : 'bg-white dark:bg-zinc-950 text-zinc-600 dark:text-zinc-300 border-zinc-200 dark:border-zinc-700'
              }`}
              data-testid="director-brand-lock">
              <Lock size={11} className="inline mr-1" />
              {brandLock ? 'On' : 'Off'}
            </button>
          </div>
        </div>

        <input
          value={audienceHint}
          onChange={(e) => setAudienceHint(e.target.value)}
          placeholder="Audience hint (optional) — e.g. PT eligible, lapsed 30 days, family members"
          className="w-full mt-3 px-3 py-2 border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100 rounded-md text-xs focus:outline-none focus:border-[var(--color-brand-blue)]"
          data-testid="director-audience-hint"
        />

        {/* Phase 3 — segment chips */}
        <div className="mt-3">
          <p className="text-[10px] uppercase tracking-wider text-zinc-500 dark:text-zinc-400 mb-1.5 font-semibold flex items-center gap-1">
            <Users size={10}/> Behaviour-driven variants <span className="text-[9px] font-normal text-zinc-400">(optional — generates per-segment copy)</span>
          </p>
          <div className="flex flex-wrap gap-1.5">
            {SEGMENT_OPTIONS.map((s) => {
              const active = segmentKeys.includes(s.key);
              return (
                <button key={s.key}
                  onClick={() => setSegmentKeys((arr) => active ? arr.filter(k => k !== s.key) : [...arr, s.key])}
                  title={s.hint}
                  className={`px-2 py-1 rounded-full text-[10px] font-medium border transition ${
                    active
                      ? 'bg-[var(--color-brand-blue)] text-white border-[var(--color-brand-blue)]'
                      : 'bg-white dark:bg-zinc-950 text-zinc-600 dark:text-zinc-300 border-zinc-200 dark:border-zinc-700 hover:border-[var(--color-brand-blue)] hover:text-[var(--color-brand-blue)]'
                  }`}
                  data-testid={`director-segment-${s.key}`}>
                  {s.label}
                </button>
              );
            })}
          </div>
        </div>

        <div className="flex items-center justify-between mt-4">
          <p className="text-[10px] text-zinc-400 dark:text-zinc-500">
            Powered by Claude Sonnet 4.5 + Gemini Nano Banana
          </p>
          <button onClick={generate} disabled={busy || !prompt.trim()}
            className="px-4 py-2 rounded-lg bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-alt2)] disabled:bg-zinc-300 disabled:dark:bg-zinc-700 disabled:cursor-not-allowed text-white font-semibold text-sm flex items-center gap-2 transition shadow-sm"
            data-testid="director-generate-btn">
            {busy ? <><Loader2 size={14} className="animate-spin"/> Directing campaign…</> : <><Sparkles size={14}/> Generate Campaign</>}
          </button>
        </div>
      </div>

      {/* ── Recent briefs strip ─────────────────────────────────── */}
      {recentBriefs.length > 0 && !brief && (
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-3">
          <p className="text-[10px] uppercase tracking-wider text-zinc-500 dark:text-zinc-400 font-semibold mb-2">
            Recent Director briefs
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
            {recentBriefs.slice(0, 6).map((b) => (
              <div key={b.id}
                className="group relative rounded-md border border-zinc-200 dark:border-zinc-700 hover:border-[var(--color-brand-blue)] hover:bg-[rgb(var(--rgb-brand-blue)/0.05)] transition"
                data-testid={`director-recent-${b.id}`}>
                <button onClick={() => loadBrief(b.id)} className="w-full text-left p-2 pr-7">
                  <p className="text-xs font-medium text-zinc-800 dark:text-zinc-100 truncate">{b.prompt}</p>
                  <p className="text-[10px] text-zinc-500 dark:text-zinc-400 mt-0.5 flex items-center gap-1">
                    <Target size={9}/> {b.goal || 'no goal'} · refined ×{b.refined_count || 0}
                  </p>
                </button>
                <RowActions className="!absolute top-1 right-1">
                  <Button
                    variant="ghostDestructive"
                    size="iconSm"
                    icon={X}
                    title="Delete this brief from history"
                    aria-label="Delete brief"
                    data-testid={`director-recent-delete-${b.id}`}
                    onClick={async (e) => {
                      e.stopPropagation();
                      try {
                        await axios.delete(`${API}/api/marketing/creative/director/briefs/${b.id}`, { headers });
                        setRecentBriefs((prev) => prev.filter((x) => x.id !== b.id));
                        notify.success('Brief removed from history');
                      } catch (err) {
                        notifyApiError(notify, err, 'Delete failed');
                      }
                    }}
                  />
                </RowActions>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Brief output ────────────────────────────────────────── */}
      {brief && (
        <div className="space-y-4" data-testid="director-output">
          {/* Strategy card */}
          <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-4 shadow-sm">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Megaphone className="text-[var(--color-brand-blue)]" size={16}/>
                <h3 className="font-bold text-zinc-900 dark:text-zinc-100 text-sm">Strategy</h3>
                {Array.isArray(brief.learnings_applied) && brief.learnings_applied.length > 0 && (
                  <span className="ml-1 inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300 font-semibold"
                    title={brief.learnings_applied.map((x, i) => `${i + 1}. ${x}`).join('\n')}
                    data-testid="director-learnings-badge">
                    <Sparkles size={9}/> Applying {brief.learnings_applied.length} past learning{brief.learnings_applied.length === 1 ? '' : 's'}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <button onClick={() => setAutoPilot((v) => !v)}
                  disabled={!!brief.campaign_id}
                  title={optimalWindow?.source === 'history'
                    ? `Auto-schedule for the org's best-performing window (${optimalWindow.label}, ${(optimalWindow.open_rate*100).toFixed(0)}% avg open rate from ${optimalWindow.sample_size} past sends) and run an AI post-mortem 72h later`
                    : `Auto-schedule for ${optimalWindow?.label || 'Tuesday 6PM'} (industry default — needs more send history for org-tuned timing) and run an AI post-mortem 72h later`}
                  className={`px-2.5 py-1.5 rounded-md text-[11px] font-semibold border flex items-center gap-1 transition ${
                    autoPilot
                      ? 'bg-purple-500 text-white border-purple-500'
                      : 'bg-white dark:bg-zinc-900 text-zinc-600 dark:text-zinc-300 border-zinc-200 dark:border-zinc-700 hover:border-purple-500 hover:text-purple-600'
                  } ${brief.campaign_id ? 'opacity-50 cursor-not-allowed' : ''}`}
                  data-testid="director-autopilot-toggle">
                  <Rocket size={11}/> Auto-pilot {autoPilot && optimalWindow ? `· ${optimalWindow.label}` : ''}
                </button>
                <button onClick={() => setPerRecipient((v) => !v)}
                  disabled={!!brief.campaign_id}
                  title={coverage && coverage.total_members > 0
                    ? `Send each recipient at their personal best hour (${coverage.personal}/${coverage.total_members} members have personal data — ${coverage.coverage_pct}% coverage; the rest fall back to ${optimalWindow?.label || 'the org-best window'})`
                    : `Send each recipient at their personal best hour. No member email-open data yet — every recipient will fall back to ${optimalWindow?.label || 'the org-best window'} until opens accrue.`}
                  className={`px-2.5 py-1.5 rounded-md text-[11px] font-semibold border flex items-center gap-1 transition ${
                    perRecipient
                      ? 'bg-fuchsia-500 text-white border-fuchsia-500'
                      : 'bg-white dark:bg-zinc-900 text-zinc-600 dark:text-zinc-300 border-zinc-200 dark:border-zinc-700 hover:border-fuchsia-500 hover:text-fuchsia-600'
                  } ${brief.campaign_id ? 'opacity-50 cursor-not-allowed' : ''}`}
                  data-testid="director-per-recipient-toggle">
                  <Users size={11}/> Per-recipient {perRecipient && coverage && coverage.total_members > 0 ? `· ${coverage.coverage_pct}% personal` : ''}
                </button>
                <button onClick={launchAsCampaign}
                  disabled={!!brief.campaign_id}
                  className="px-3 py-1.5 rounded-md bg-emerald-500 hover:bg-emerald-600 disabled:bg-zinc-300 disabled:dark:bg-zinc-700 text-white text-xs font-semibold flex items-center gap-1.5"
                  data-testid="director-launch-campaign">
                  {brief.campaign_id ? <><Check size={12}/> Launched</> : <><Send size={12}/> {autoPilot ? 'Schedule send' : 'Launch as Campaign'}</>}
                </button>
              </div>
            </div>
            <p className="text-sm text-zinc-700 dark:text-zinc-200 mb-3">
              {brief.strategy?.summary}
            </p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
              <Stat icon={Users} label="Audience" value={brief.strategy?.audience?.name || '—'}
                hint={brief.strategy?.audience?.segment_filter_hint} />
              <Stat icon={Zap} label="Channels" value={(brief.strategy?.channels || []).join(', ') || '—'} />
              <Stat icon={Clock} label="Send window"
                value={brief.strategy?.schedule?.send_window || '—'}
                hint={brief.strategy?.schedule?.frequency} />
              <Stat icon={Target} label="Tone" value={brief.tone} />
            </div>
          </div>

          {/* Refine toolbar */}
          <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900/60 p-3">
            <div className="flex items-center gap-2 mb-2">
              <Wand2 className="text-[var(--color-brand-blue)]" size={14}/>
              <p className="text-[11px] uppercase tracking-wider font-semibold text-zinc-600 dark:text-zinc-300">
                Make it better
              </p>
              {refineBusy && <Loader2 size={12} className="animate-spin text-[var(--color-brand-blue)]"/>}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {REFINE_QUICKACTIONS.map((qa) => (
                <button key={qa.label}
                  disabled={refineBusy}
                  onClick={() => refine(qa.instr)}
                  className="px-2.5 py-1 rounded-full border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 text-[11px] font-medium text-zinc-700 dark:text-zinc-200 hover:border-[var(--color-brand-blue)] hover:text-[var(--color-brand-blue)] disabled:opacity-50 transition"
                  data-testid={`director-refine-${qa.label.toLowerCase().replace(/[^a-z]/g,'-')}`}>
                  {qa.label}
                </button>
              ))}
            </div>
          </div>

          {/* Poster + channel cards */}
          <div className="grid grid-cols-1 lg:grid-cols-[1fr_1.2fr] gap-4">
            <PosterCard brief={brief} onRegenerate={() =>
              refine('Regenerate the poster image with the same copy but a fresh visual angle', 'poster', true)
            } refineBusy={refineBusy}/>
            <div className="space-y-2">
              {Object.keys(CHANNEL_META).filter(k => k !== 'poster').map((k) => (
                <ChannelCard key={k} channelKey={k} copy={brief.copy?.[k]}
                  onRefine={(instr) => refine(instr, k)} disabled={refineBusy}/>
              ))}
            </div>
          </div>

          {/* Alt-tones / variation grid */}
          {Array.isArray(brief.alt_tones) && brief.alt_tones.length > 0 && (
            <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-4">
              <p className="text-[11px] uppercase tracking-wider font-semibold text-zinc-500 dark:text-zinc-400 mb-2">
                Alt-tone variations (A/B)
              </p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {brief.alt_tones.map((alt, i) => (
                  <div key={i}
                    className="rounded-md border border-zinc-200 dark:border-zinc-700 p-3"
                    data-testid={`director-alt-tone-${i}`}>
                    <p className="text-[10px] uppercase tracking-wider font-semibold text-[var(--color-brand-blue)] mb-1">{alt.tone}</p>
                    <p className="text-sm font-bold text-zinc-900 dark:text-zinc-100 mb-1">{alt.headline}</p>
                    <p className="text-xs text-zinc-600 dark:text-zinc-300 mb-1"><strong>Email:</strong> {alt.email_subject}</p>
                    <p className="text-xs text-zinc-600 dark:text-zinc-300"><strong>SMS:</strong> {alt.sms}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Phase 3 — Behaviour-driven per-segment variants */}
          {Array.isArray(brief.segment_variants) && brief.segment_variants.length > 0 && (
            <div className="rounded-xl border border-emerald-200 dark:border-emerald-800 bg-emerald-50/30 dark:bg-emerald-950/20 p-4" data-testid="director-segment-variants">
              <div className="flex items-center gap-2 mb-2">
                <Users size={14} className="text-emerald-600 dark:text-emerald-400"/>
                <p className="text-[11px] uppercase tracking-wider font-semibold text-emerald-700 dark:text-emerald-300">
                  Behaviour-Driven Variants ({brief.segment_variants.length})
                </p>
                <span className="text-[10px] text-zinc-500 dark:text-zinc-400">— Same campaign, different copy per segment</span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {brief.segment_variants.map((v, i) => (
                  <div key={i}
                    className="rounded-md border border-emerald-100 dark:border-emerald-800/40 p-3 bg-white dark:bg-zinc-900"
                    data-testid={`director-segment-variant-${v.segment_key}`}>
                    <div className="flex items-center justify-between mb-1.5">
                      <p className="text-[11px] font-bold text-emerald-700 dark:text-emerald-300">{v.segment_label}</p>
                      <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-700 dark:text-emerald-300">
                        {v.audience_count != null ? `${v.audience_count} member${v.audience_count === 1 ? '' : 's'}` : 'live count'}
                      </span>
                    </div>
                    {v.behaviour && <p className="text-[10px] text-zinc-500 dark:text-zinc-400 italic mb-2">{v.behaviour}</p>}
                    <p className="text-sm font-bold text-zinc-900 dark:text-zinc-100 mb-1">{v.headline}</p>
                    <p className="text-xs text-zinc-700 dark:text-zinc-200 mb-1"><strong>Email:</strong> {v.email_subject}</p>
                    <p className="text-xs text-zinc-700 dark:text-zinc-200 mb-1"><strong>SMS:</strong> {v.sms}</p>
                    {v.lever_used && (
                      <p className="text-[10px] text-emerald-600 dark:text-emerald-400 mt-1.5 italic">
                        <Zap size={9} className="inline mr-0.5"/> {v.lever_used}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// ───────────────────────── Sub-components ─────────────────────────

const Select = ({ label, value, onChange, options, testId }) => (
  <div>
    <p className="text-[10px] uppercase tracking-wider text-zinc-500 dark:text-zinc-400 mb-1 font-semibold">{label}</p>
    <select value={value} onChange={(e) => onChange(e.target.value)}
      className="w-full px-2 py-2 border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100 rounded-md text-xs"
      data-testid={testId}>
      {options.map((opt) => (
        <option key={opt.key} value={opt.key} title={opt.hint || ''}>{opt.label}</option>
      ))}
    </select>
  </div>
);

const Stat = ({ icon: Icon, label, value, hint }) => (
  <div className="rounded-md border border-zinc-100 dark:border-zinc-800 p-2 bg-zinc-50/50 dark:bg-zinc-900/40">
    <div className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-zinc-500 dark:text-zinc-400 font-semibold">
      <Icon size={10}/> {label}
    </div>
    <p className="text-xs font-medium text-zinc-800 dark:text-zinc-100 mt-0.5 break-words">{value}</p>
    {hint && <p className="text-[10px] text-zinc-400 dark:text-zinc-500 mt-0.5">{hint}</p>}
  </div>
);

const PosterCard = ({ brief, onRegenerate, refineBusy }) => {
  const url = brief?.poster_data_url;
  return (
    <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-3" data-testid="director-poster-card">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5">
          <ImageIcon className="text-violet-500" size={14}/>
          <p className="text-xs font-semibold text-zinc-700 dark:text-zinc-200">Poster — Gemini Nano Banana</p>
        </div>
        <button onClick={onRegenerate} disabled={refineBusy}
          className="px-2 py-1 rounded-md text-[10px] font-medium border border-zinc-200 dark:border-zinc-700 hover:border-[var(--color-brand-blue)] hover:text-[var(--color-brand-blue)] disabled:opacity-50 flex items-center gap-1"
          data-testid="director-regenerate-poster">
          {refineBusy ? <Loader2 size={10} className="animate-spin"/> : <RefreshCw size={10}/>}
          Regenerate
        </button>
      </div>
      <div className="rounded-md overflow-hidden bg-zinc-100 dark:bg-zinc-950 aspect-[4/5] flex items-center justify-center">
        {url ? (
          <img src={url} alt="AI poster"
            className="w-full h-full object-contain"
            data-testid="director-poster-img"/>
        ) : (
          <div className="text-center text-xs text-zinc-400 dark:text-zinc-500 p-6">
            <ImageIcon size={28} className="mx-auto mb-2 opacity-50"/>
            Poster generation skipped or unavailable
          </div>
        )}
      </div>
      <div className="mt-2 text-xs space-y-0.5">
        <p className="font-bold text-zinc-900 dark:text-zinc-100">{brief?.copy?.poster?.headline}</p>
        {brief?.copy?.poster?.subheadline && <p className="text-zinc-600 dark:text-zinc-300">{brief.copy.poster.subheadline}</p>}
        {brief?.copy?.poster?.cta && <p className="text-[var(--color-brand-blue)] font-semibold">{brief.copy.poster.cta} →</p>}
      </div>
    </div>
  );
};

const ChannelCard = ({ channelKey, copy, onRefine, disabled }) => {
  const meta = CHANNEL_META[channelKey];
  const [refineOpen, setRefineOpen] = useState(false);
  const [refineText, setRefineText] = useState('');
  if (!copy) return null;
  const Icon = meta.icon;

  const fullText = (() => {
    if (channelKey === 'email') return `${copy.subject || ''}\n\n${copy.preheader || ''}\n\n${copy.body_html || ''}`;
    if (channelKey === 'instagram') return `${copy.caption || ''}\n\n${(copy.hashtags || []).join(' ')}`;
    if (channelKey === 'facebook') return copy.post || '';
    if (channelKey === 'sms') return copy.body || '';
    if (channelKey === 'push') return `${copy.title || ''} — ${copy.body || ''}`;
    return JSON.stringify(copy);
  })();

  const submitRefine = () => {
    if (!refineText.trim()) return;
    onRefine(refineText.trim());
    setRefineText('');
    setRefineOpen(false);
  };

  return (
    <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-3" data-testid={`director-channel-${channelKey}`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5">
          <Icon className={meta.color} size={14}/>
          <p className="text-xs font-semibold text-zinc-800 dark:text-zinc-100">{meta.label}</p>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={() => { navigator.clipboard.writeText(fullText); notify.success('Copied'); }}
            className="p-1.5 rounded-md text-zinc-500 hover:text-[var(--color-brand-blue)] hover:bg-[rgb(var(--rgb-brand-blue)/0.05)]"
            title="Copy" data-testid={`director-${channelKey}-copy`}>
            <Copy size={11}/>
          </button>
          <button onClick={() => setRefineOpen((v) => !v)} disabled={disabled}
            className="p-1.5 rounded-md text-zinc-500 hover:text-[var(--color-brand-blue)] hover:bg-[rgb(var(--rgb-brand-blue)/0.05)] disabled:opacity-50"
            title="Refine this channel" data-testid={`director-${channelKey}-refine`}>
            <Edit3 size={11}/>
          </button>
        </div>
      </div>
      <ChannelBody channelKey={channelKey} copy={copy}/>
      {refineOpen && (
        <div className="mt-2 flex gap-1">
          <input value={refineText} onChange={(e) => setRefineText(e.target.value)}
            placeholder={`How should I improve ${meta.label}? e.g. shorter, add emoji…`}
            className="flex-1 px-2 py-1 border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100 rounded-md text-xs"
            onKeyDown={(e) => e.key === 'Enter' && submitRefine()}
            data-testid={`director-${channelKey}-refine-input`}/>
          <button onClick={submitRefine}
            className="px-2 py-1 rounded-md bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-alt2)] text-white text-xs font-medium flex items-center gap-1">
            <ChevronRight size={11}/>
          </button>
        </div>
      )}
    </div>
  );
};

const ChannelBody = ({ channelKey, copy }) => {
  if (channelKey === 'email') {
    return (
      <div className="text-xs space-y-1">
        <p><span className="font-semibold text-zinc-700 dark:text-zinc-200">Subject:</span> {copy.subject}</p>
        {copy.preheader && <p className="text-zinc-500 dark:text-zinc-400 italic">Preview: {copy.preheader}</p>}
        <div
          className="rounded-md border border-zinc-100 dark:border-zinc-800 p-2 bg-zinc-50/50 dark:bg-zinc-950 prose prose-sm dark:prose-invert max-w-none"
          dangerouslySetInnerHTML={{ __html: copy.body_html || '' }}
        />
      </div>
    );
  }
  if (channelKey === 'instagram') {
    return (
      <div className="text-xs space-y-1">
        <p className="text-zinc-700 dark:text-zinc-200 whitespace-pre-line">{copy.caption}</p>
        <p className="text-pink-500 text-[11px]">{(copy.hashtags || []).join(' ')}</p>
      </div>
    );
  }
  if (channelKey === 'facebook') {
    return <p className="text-xs text-zinc-700 dark:text-zinc-200 whitespace-pre-line">{copy.post}</p>;
  }
  if (channelKey === 'sms') {
    return (
      <div className="text-xs">
        <p className="text-zinc-700 dark:text-zinc-200 font-mono bg-zinc-50 dark:bg-zinc-950 p-2 rounded">{copy.body}</p>
        <p className="text-[10px] text-zinc-400 dark:text-zinc-500 mt-1">{(copy.body || '').length}/160 chars</p>
      </div>
    );
  }
  if (channelKey === 'push') {
    return (
      <div className="text-xs">
        <p className="font-semibold text-zinc-900 dark:text-zinc-100">{copy.title}</p>
        <p className="text-zinc-600 dark:text-zinc-300">{copy.body}</p>
      </div>
    );
  }
  return null;
};

export default AIDirectorPanel;
