/**
 * Product Preview Modal — Iter 216ba.
 *
 * Self-running interactive product walkthrough that replaces the
 * "Book a Demo" gatekeeper. The buyer sees the product without
 * needing to talk to anyone.
 *
 * Six stylised "scenes" cycling automatically every 5s, each showing
 * a plausible UI mock with a 1-line caption explaining what's
 * happening. Tap-or-click to advance / pause. Esc to close.
 *
 * Triggered the same way as the trial modal:
 *   window.dispatchEvent(new CustomEvent('gymaxis:open-preview'));
 */
import { useCallback, useEffect, useState } from 'react';
import {
  X, ArrowRight, ChevronLeft, ChevronRight, Pause, Play, Sparkles,
  Wrench, Calendar, Megaphone, UserCog, BarChart3, Users, ArrowUpRight,
} from 'lucide-react';
import { openTrial } from './TrialSignupModal';

const SCENES = [
  {
    id: 'fault-triage',
    icon: Wrench,
    accent: '#06B6D4',
    title: 'Operations · AI fault triage',
    caption: 'Snap the fault. Claude triages it, suggests parts, routes the ticket — in under 6 seconds.',
    body: () => (
      <div className="grid md:grid-cols-2 gap-3 h-full">
        <div className="rounded-xl bg-slate-100 p-4 flex flex-col dark:bg-zinc-800">
          <p className="text-[10px] uppercase tracking-wider font-bold text-slate-500">Photo evidence</p>
          <div className="mt-2 flex-1 rounded-lg bg-gradient-to-br from-slate-200 to-slate-300 flex items-center justify-center">
            <Wrench size={48} className="text-slate-400" />
          </div>
          <p className="mt-2 text-[11px] text-slate-500">Treadmill 3 · belt slipping</p>
        </div>
        <div className="rounded-xl bg-white border border-slate-200 p-4 space-y-2 dark:bg-zinc-900 dark:border-zinc-800">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <p className="text-[10px] uppercase tracking-wider font-bold text-emerald-700">AI triage complete</p>
          </div>
          <p className="text-sm font-bold text-slate-900 dark:text-zinc-100">Belt slip · service-required</p>
          <ul className="text-[12px] text-slate-700 space-y-1">
            <li>• Likely worn drive belt or low lubrication</li>
            <li>• Inspect motor coupling alignment</li>
            <li>• Estimated 30-45 min service</li>
          </ul>
          <div className="rounded-lg bg-cyan-50 p-2 text-[11px] text-cyan-800">
            Routed → Mike (Lead Technician) · ETA 14:30
          </div>
        </div>
      </div>
    ),
  },
  {
    id: 'rota',
    icon: UserCog,
    accent: '#A855F7',
    title: 'Staffing · AI rota in seconds',
    caption: 'Claude builds a fair, compliant week. £-cost roll-up. One-click apply. Sage CSV export.',
    body: () => (
      <div className="space-y-2">
        <div className="grid grid-cols-7 gap-1">
          {['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map((d) => (
            <div key={d} className="text-center text-[10px] font-bold uppercase tracking-wider text-slate-400 pb-1">{d}</div>
          ))}
          {Array.from({ length: 28 }).map((_, i) => (
            <div key={i} className="rounded-md bg-gradient-to-br from-violet-100 to-fuchsia-100 border border-violet-200/50 p-1.5">
              <div className="text-[10px] font-bold text-violet-900 truncate">{['Sam','Alex','Mia','Jay','Tom'][i % 5]}</div>
              <div className="text-[9px] text-violet-700">09–17 · {['Rec','Inst','Mgr','Rec','PT'][i % 5]}</div>
            </div>
          ))}
        </div>
        <div className="grid grid-cols-3 gap-2 mt-2">
          <div className="rounded-lg bg-slate-100 p-2 text-center dark:bg-zinc-800">
            <p className="text-[9px] uppercase font-bold text-slate-500">Engine</p>
            <p className="text-xs font-bold">Claude AI</p>
          </div>
          <div className="rounded-lg bg-slate-100 p-2 text-center dark:bg-zinc-800">
            <p className="text-[9px] uppercase font-bold text-slate-500">Hours</p>
            <p className="text-xs font-bold">186h</p>
          </div>
          <div className="rounded-lg bg-emerald-50 p-2 text-center">
            <p className="text-[9px] uppercase font-bold text-emerald-700">Cost</p>
            <p className="text-xs font-bold text-emerald-900">£2,790</p>
          </div>
        </div>
      </div>
    ),
  },
  {
    id: 'campaign',
    icon: Megaphone,
    accent: '#D946EF',
    title: 'Marketing · AI Director writes your campaign',
    caption: 'Pick a goal. AI drafts copy + audience + send time. Approve. Send. £14 average revenue lift per member.',
    body: () => (
      <div className="grid md:grid-cols-2 gap-3 h-full">
        <div className="rounded-xl bg-slate-100 p-4 space-y-2 dark:bg-zinc-800">
          <p className="text-[10px] uppercase tracking-wider font-bold text-slate-500">Goal</p>
          <p className="text-sm font-bold text-slate-900 dark:text-zinc-100">Win back lapsed members</p>
          <p className="text-[10px] uppercase tracking-wider font-bold text-slate-500 mt-2">Audience</p>
          <p className="text-sm text-slate-800">142 members · last booking 60-90 days ago</p>
          <p className="text-[10px] uppercase tracking-wider font-bold text-slate-500 mt-2">Send when</p>
          <p className="text-sm text-slate-800">Tomorrow 09:30 · highest open-rate slot</p>
        </div>
        <div className="rounded-xl bg-white border border-slate-200 p-4 dark:bg-zinc-900 dark:border-zinc-800">
          <p className="text-[10px] uppercase tracking-wider font-bold text-fuchsia-700">AI-drafted email</p>
          <p className="mt-2 text-sm font-bold text-slate-900 dark:text-zinc-100">Miss us, Sarah?</p>
          <p className="mt-1 text-[12px] text-slate-700 leading-relaxed">
            We've added Saturday morning HIIT — small group, big results. As a thank-you for being with us, your next class is on the house. Pick a slot →
          </p>
          <div className="mt-3 inline-flex items-center gap-1.5 rounded-full bg-fuchsia-100 text-fuchsia-800 px-2.5 py-1 text-[11px] font-bold">
            <Sparkles size={10} /> Estimated open-rate: 38%
          </div>
        </div>
      </div>
    ),
  },
  {
    id: 'memberships',
    icon: Calendar,
    accent: '#8B5CF6',
    title: 'Memberships · Family Auto-Bill',
    caption: 'One household. Multiple plans. Sibling discounts auto-applied. One Stripe invoice.',
    body: () => (
      <div className="space-y-2">
        <div className="rounded-xl bg-white border border-slate-200 p-4 dark:bg-zinc-900 dark:border-zinc-800">
          <div className="flex items-center justify-between">
            <p className="text-sm font-bold text-slate-900 dark:text-zinc-100">Davies family</p>
            <p className="text-[11px] text-slate-500">3 active plans</p>
          </div>
          <div className="mt-3 space-y-1.5 text-[12px]">
            {[
              { n: 'Sarah Davies', p: 'Adult unlimited',  cost: '£59.00', tag: 'Primary' },
              { n: 'Tom Davies',   p: 'Junior pack',      cost: '£24.00', tag: 'Sibling 10%' },
              { n: 'Mia Davies',   p: 'Junior pack',      cost: '£21.60', tag: 'Sibling 20%' },
            ].map((r) => (
              <div key={r.n} className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-1.5 dark:bg-zinc-900">
                <span className="font-semibold text-slate-900 dark:text-zinc-100">{r.n}</span>
                <span className="text-slate-500">{r.p}</span>
                <span className="text-[10px] uppercase tracking-wider font-bold text-violet-700">{r.tag}</span>
                <span className="font-bold text-slate-900 tabular-nums dark:text-zinc-100">{r.cost}</span>
              </div>
            ))}
          </div>
          <div className="mt-3 flex items-center justify-between rounded-lg bg-violet-50 p-2.5 text-[12px]">
            <span className="font-bold text-violet-900">Total billed Apr 1</span>
            <span className="font-black text-violet-900 tabular-nums">£104.60</span>
          </div>
        </div>
      </div>
    ),
  },
  {
    id: 'crm',
    icon: Users,
    accent: '#6366F1',
    title: 'CRM · AI lead scoring',
    caption: 'Prioritise the lead most likely to close. AI explains why. Drop into a sequence. One click.',
    body: () => (
      <div className="space-y-1.5">
        {[
          { n: 'Acme Health Group', s: 92, why: 'Visited /pricing 5×, demo requested 2 days ago', tone: 'emerald' },
          { n: 'Riverside Studio',  s: 78, why: 'Filled trial form, lapsed 8 days ago — re-engage',  tone: 'amber' },
          { n: 'PowerHouse Gyms',   s: 45, why: 'Cold lead from list, no engagement',                 tone: 'slate' },
        ].map((r) => (
          <div key={r.n} className="flex items-center gap-3 rounded-lg bg-white border border-slate-200 p-3 dark:bg-zinc-900 dark:border-zinc-800" data-testid={`gx-preview-lead-${r.n}`}>
            <div className={`w-10 h-10 rounded-lg flex items-center justify-center font-black text-white text-sm ${r.tone === 'emerald' ? 'bg-emerald-500' : r.tone === 'amber' ? 'bg-amber-500' : 'bg-slate-400'}`}>{r.s}</div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-bold text-slate-900 dark:text-zinc-100">{r.n}</p>
              <p className="text-[11px] text-slate-500 truncate">{r.why}</p>
            </div>
            <button type="button" className="text-[11px] font-bold text-indigo-600 hover:underline inline-flex items-center gap-1">Open <ArrowUpRight size={11} /></button>
          </div>
        ))}
      </div>
    ),
  },
  {
    id: 'reporting',
    icon: BarChart3,
    accent: '#2563EB',
    title: 'Reporting · One-screen weekly digest',
    caption: 'Revenue. Churn. Faults. Cohort retention. Auto-emailed every Monday — to you and your owner.',
    body: () => (
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        {[
          { l: 'MRR',          v: '£18,420', d: '+£1,140 vs last wk', t: 'emerald' },
          { l: 'Active members', v: '423',  d: '+11 net new',         t: 'emerald' },
          { l: 'Open faults',   v: '7',     d: '4 resolved this wk',  t: 'amber' },
          { l: 'Class fill-rate', v: '82%', d: '+3% vs last wk',      t: 'emerald' },
        ].map((s) => (
          <div key={s.l} className="rounded-xl bg-white border border-slate-200 p-3 dark:bg-zinc-900 dark:border-zinc-800">
            <p className="text-[10px] uppercase tracking-wider font-bold text-slate-500">{s.l}</p>
            <p className="text-2xl font-black text-slate-900 tabular-nums mt-1 dark:text-zinc-100">{s.v}</p>
            <p className={`text-[11px] font-semibold mt-0.5 ${s.t === 'emerald' ? 'text-emerald-700' : 'text-amber-700'}`}>{s.d}</p>
          </div>
        ))}
        <div className="col-span-2 md:col-span-4 rounded-xl bg-blue-50 border border-blue-200/50 p-3 text-[12px] text-blue-900">
          📧 Digest sent to <strong>you@yourgym.co.uk</strong> + <strong>owner@yourgym.co.uk</strong> · Mon 06:00.
        </div>
      </div>
    ),
  },
];

export default function ProductPreviewModal() {
  const [open, setOpen] = useState(false);
  const [idx, setIdx] = useState(0);
  const [paused, setPaused] = useState(false);

  // Open / close via window events.
  useEffect(() => {
    const onOpen = () => { setOpen(true); setIdx(0); setPaused(false); };
    const onClose = () => setOpen(false);
    window.addEventListener('gymaxis:open-preview', onOpen);
    window.addEventListener('gymaxis:close-preview', onClose);
    return () => {
      window.removeEventListener('gymaxis:open-preview', onOpen);
      window.removeEventListener('gymaxis:close-preview', onClose);
    };
  }, []);

  // Esc-to-close + body-scroll lock + autoplay.
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') setOpen(false);
      if (e.key === 'ArrowRight') setIdx((i) => (i + 1) % SCENES.length);
      if (e.key === 'ArrowLeft')  setIdx((i) => (i - 1 + SCENES.length) % SCENES.length);
      if (e.key === ' ')          setPaused((p) => !p);
    };
    document.addEventListener('keydown', onKey);
    document.body.style.overflow = 'hidden';
    let timer = null;
    if (!paused) {
      timer = setInterval(() => setIdx((i) => (i + 1) % SCENES.length), 5500);
    }
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = '';
      if (timer) clearInterval(timer);
    };
  }, [open, paused]);

  const next = useCallback(() => setIdx((i) => (i + 1) % SCENES.length), []);
  const prev = useCallback(() => setIdx((i) => (i - 1 + SCENES.length) % SCENES.length), []);

  if (!open) return null;
  const scene = SCENES[idx];
  const Icon = scene.icon;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-sm"
      role="dialog" aria-modal="true" aria-label="Product preview"
      data-testid="gx-product-preview"
      onClick={(e) => { if (e.target === e.currentTarget) setOpen(false); }}
    >
      <div className="w-full max-w-4xl rounded-3xl bg-white shadow-2xl overflow-hidden flex flex-col dark:bg-zinc-900" style={{ maxHeight: '92vh' }}>
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 dark:border-zinc-800">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center text-white" style={{ background: scene.accent }}>
              <Icon size={18} />
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-wider font-bold text-slate-500">Scene {idx + 1} of {SCENES.length}</p>
              <p className="text-sm font-bold text-slate-900 dark:text-zinc-100">{scene.title}</p>
            </div>
          </div>
          <button type="button" onClick={() => setOpen(false)} className="p-2 rounded-full hover:bg-slate-100 dark:bg-zinc-800" aria-label="Close" data-testid="gx-preview-close">
            <X size={18} />
          </button>
        </div>

        {/* Stage */}
        <div className="flex-1 overflow-y-auto p-6 sm:p-8 bg-slate-50/40" data-testid={`gx-preview-scene-${scene.id}`}>
          <div className="rounded-2xl bg-white border border-slate-200 p-4 sm:p-6 min-h-[260px] dark:bg-zinc-900 dark:border-zinc-800">
            {scene.body()}
          </div>
          <p className="mt-5 text-base sm:text-lg text-slate-700 leading-snug max-w-2xl">
            {scene.caption}
          </p>
        </div>

        {/* Controls + CTA */}
        <div className="px-6 py-4 border-t border-slate-100 flex items-center gap-3 flex-wrap dark:border-zinc-800">
          <div className="flex items-center gap-1">
            <button type="button" onClick={prev} className="p-2 rounded-full hover:bg-slate-100 dark:bg-zinc-800" aria-label="Previous" data-testid="gx-preview-prev"><ChevronLeft size={16} /></button>
            <button type="button" onClick={() => setPaused((p) => !p)} className="p-2 rounded-full hover:bg-slate-100 dark:bg-zinc-800" aria-label={paused ? 'Play' : 'Pause'} data-testid="gx-preview-pause">
              {paused ? <Play size={14} /> : <Pause size={14} />}
            </button>
            <button type="button" onClick={next} className="p-2 rounded-full hover:bg-slate-100 dark:bg-zinc-800" aria-label="Next" data-testid="gx-preview-next"><ChevronRight size={16} /></button>
          </div>
          <div className="flex items-center gap-1.5">
            {SCENES.map((_, i) => (
              <button key={i} type="button" onClick={() => setIdx(i)} aria-label={`Go to scene ${i + 1}`}
                className={`h-1 rounded-full transition-all ${i === idx ? 'w-8 bg-slate-900' : 'w-3 bg-slate-300 hover:bg-slate-400'}`} />
            ))}
          </div>
          <div className="ml-auto flex items-center gap-2 flex-wrap">
            <button type="button" onClick={() => { setOpen(false); openTrial(); }}
              className="gx-cta inline-flex items-center gap-1.5 rounded-full px-5 py-2.5 text-sm font-bold"
              data-testid="gx-preview-trial">
              Try it free <ArrowRight size={14} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Helper any CTA can call. */
export function openPreview() {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('gymaxis:open-preview'));
  }
}
