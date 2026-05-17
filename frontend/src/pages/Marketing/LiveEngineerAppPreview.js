/**
 * Iter 216h167 — Live, interactive engineer-app preview.
 *
 * Replaces the static phone mock on `/partners/engineers` with a
 * tap-through demo so prospective Partner Engineers can feel the app
 * before they apply. Three screens drive the loop:
 *   1. Job ticket   — assignment summary + asset history + parts
 *   2. Service report — fault, diagnosis, signature, photos
 *   3. Send to customer — confirms a branded PDF was emailed
 *
 * Everything is canned client-side (no API calls), but the controls
 * are real buttons and each transition uses a small slide animation so
 * the experience matches the live Engineer App PWA.
 */
import React, { useEffect, useState } from 'react';
import {
  ArrowLeft, ChevronRight, RotateCcw, CheckCircle2, Mail, Image as ImageIcon,
  PenLine, ChevronDown,
} from 'lucide-react';

const SCREENS = ['job', 'report', 'send'];

const LiveEngineerAppPreview = () => {
  const [screen, setScreen] = useState('job');
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  // Animation key forces a slide-in whenever the screen changes.
  const [animKey, setAnimKey] = useState(0);

  const go = (next) => {
    setScreen(next);
    setAnimKey((k) => k + 1);
    if (next === 'send') {
      // Auto-trigger the "send" loop the moment the screen renders
      // — feels like the engineer just tapped a button and the app
      // started working.
      setSending(true);
      setSent(false);
      setTimeout(() => { setSending(false); setSent(true); }, 1300);
    } else {
      setSending(false);
      setSent(false);
    }
  };

  const restart = () => go('job');

  return (
    <div className="relative" data-testid="pe-live-preview">
      {/* Top toolbar — reset + progress dots */}
      <div className="flex items-center justify-between mb-3 max-w-xs mx-auto px-1">
        <button
          type="button"
          onClick={restart}
          disabled={screen === 'job'}
          className="text-xs font-bold uppercase tracking-wider text-slate-500 hover:text-blue-600 disabled:opacity-30 inline-flex items-center gap-1"
          data-testid="pe-preview-restart"
        >
          <RotateCcw size={12} /> Restart
        </button>
        <div className="flex items-center gap-1.5" aria-label="Preview progress">
          {SCREENS.map((s) => (
            <span
              key={s}
              data-testid={`pe-preview-dot-${s}`}
              className={`h-1.5 w-4 rounded-full transition-colors ${screen === s ? 'bg-blue-600' : 'bg-slate-300'}`}
            />
          ))}
        </div>
      </div>

      {/* Phone chrome */}
      <div className="mx-auto max-w-xs rounded-[40px] border-8 border-slate-900 bg-slate-900 shadow-2xl overflow-hidden">
        <div className="bg-slate-100 px-4 py-3 flex items-center justify-between text-xs">
          <span className="font-bold text-slate-700">9:41</span>
          <span className="font-bold text-slate-700">●●● ●●</span>
        </div>
        <div
          key={animKey}
          className="bg-white p-4 text-left text-xs h-[440px] overflow-y-auto pe-preview-screen"
        >
          {screen === 'job' && <ScreenJob onView={() => go('report')} onSend={() => go('send')} />}
          {screen === 'report' && <ScreenReport onBack={() => go('job')} onSend={() => go('send')} />}
          {screen === 'send' && <ScreenSend sending={sending} sent={sent} onBack={() => go('report')} onDone={restart} />}
        </div>
      </div>

      {/* Tap hint — only on first screen, gentle nudge */}
      {screen === 'job' && (
        <p className="text-center text-[11px] text-slate-400 mt-3 inline-flex items-center justify-center gap-1 w-full" data-testid="pe-preview-hint">
          <ChevronDown size={11} className="animate-bounce" />
          Tap the buttons — this preview is live.
        </p>
      )}

      <style>{`
        @keyframes peSlideIn {
          from { opacity: 0; transform: translateX(8px); }
          to   { opacity: 1; transform: translateX(0); }
        }
        .pe-preview-screen { animation: peSlideIn 220ms ease-out; }
      `}</style>
    </div>
  );
};


/* ── Screen 1 · Job ticket ──────────────────────────────── */
const ScreenJob = ({ onView, onSend }) => (
  <div className="space-y-3" data-testid="pe-preview-job">
    <div className="flex items-center justify-between">
      <p className="font-extrabold text-slate-900 text-sm">Job · CASE-1287</p>
      <span className="px-2 py-0.5 rounded-full text-[9px] font-extrabold uppercase tracking-wider bg-blue-100 text-blue-700">On site</span>
    </div>
    <p className="text-slate-500">PureGym Birmingham · Treadmill #4 · belt slip at 12 km/h</p>
    <div className="rounded-xl bg-amber-50 border border-amber-200 p-2.5 text-amber-900">
      <p className="text-[10px] font-bold uppercase tracking-wider">⚡ Asset history</p>
      <p className="mt-1">3 prior visits in 90 days · last: BELT_SLIP · ★★★★★</p>
    </div>
    <div className="rounded-xl bg-slate-50 border border-slate-200 p-2.5">
      <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Time on site</p>
      <p className="font-bold text-slate-800 mt-0.5">Travel 25m · On site 42m</p>
    </div>
    <div className="rounded-xl bg-slate-50 border border-slate-200 p-2.5">
      <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Parts (1)</p>
      <p className="font-semibold text-slate-800 mt-0.5">1 × BELT-001 <span className="opacity-60">· from van</span></p>
    </div>
    <button
      type="button"
      onClick={onView}
      data-testid="pe-preview-view-report"
      className="w-full mt-2 rounded-lg bg-blue-600 font-bold py-2.5 text-sm hover:bg-blue-700 active:scale-[0.98] transition"
      style={{ color: '#fff' }}
    >
      View report
    </button>
    <button
      type="button"
      onClick={onSend}
      data-testid="pe-preview-send"
      className="w-full rounded-lg border border-slate-200 font-bold py-2.5 text-sm hover:bg-slate-50 active:scale-[0.98] transition bg-white"
      style={{ color: '#334155' }}
    >
      Send to customer
    </button>
  </div>
);


/* ── Screen 2 · Service report ──────────────────────────── */
const ScreenReport = ({ onBack, onSend }) => (
  <div className="space-y-3" data-testid="pe-preview-report">
    <button type="button" onClick={onBack} className="text-blue-600 inline-flex items-center gap-1 font-semibold text-xs" data-testid="pe-preview-report-back">
      <ArrowLeft size={12} /> Back
    </button>
    <div>
      <p className="font-extrabold text-slate-900 text-sm">Service report</p>
      <p className="text-[10px] text-slate-400 mt-0.5">CASE-1287 · drafted just now</p>
    </div>
    <section>
      <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-0.5">Fault reported</p>
      <p className="text-slate-700">Belt slipping at 12 km/h under load. Auto-stop trip after 4 min.</p>
    </section>
    <section>
      <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-0.5">Diagnosis</p>
      <p className="text-slate-700">
        Drive belt worn beyond service limit (12 mm vs 9 mm new). Roller bearings within spec. Replaced belt with BELT-001 from van stock, recalibrated speed sensor, ran 20-minute soak test.
      </p>
    </section>
    <section className="grid grid-cols-3 gap-2">
      {[1, 2, 3].map((i) => (
        <div key={i} className="aspect-square rounded-lg bg-slate-100 border border-slate-200 flex items-center justify-center text-slate-400">
          <ImageIcon size={14} />
        </div>
      ))}
    </section>
    <p className="text-[10px] text-slate-400 -mt-1">3 photos attached</p>

    <section className="rounded-xl border border-slate-200 p-2.5">
      <div className="flex items-center justify-between mb-1.5">
        <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Customer sign-off</p>
        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[9px] font-extrabold uppercase bg-emerald-100 text-emerald-700">
          <CheckCircle2 size={9} /> Signed
        </span>
      </div>
      <div className="h-12 rounded-md bg-gradient-to-br from-white to-slate-50 border border-slate-200 flex items-end px-3 pb-1.5">
        <span
          className="font-[cursive] text-slate-700 text-base italic"
          style={{ fontFamily: '"Brush Script MT", cursive' }}
        >
          J. Reilly
        </span>
        <PenLine size={11} className="text-slate-400 ml-auto mb-1" />
      </div>
      <p className="text-[10px] text-slate-400 mt-1">Manager · PureGym Birmingham · 14:51</p>
    </section>

    <button
      type="button"
      onClick={onSend}
      data-testid="pe-preview-report-send"
      className="w-full rounded-lg bg-blue-600 font-bold py-2.5 text-sm hover:bg-blue-700 active:scale-[0.98] transition inline-flex items-center justify-center gap-1.5"
      style={{ color: '#fff' }}
    >
      Send branded PDF <ChevronRight size={14} />
    </button>
  </div>
);


/* ── Screen 3 · Send to customer ────────────────────────── */
const ScreenSend = ({ sending, sent, onBack, onDone }) => (
  <div className="space-y-3 h-full flex flex-col" data-testid="pe-preview-send-screen">
    <button type="button" onClick={onBack} className="text-blue-600 inline-flex items-center gap-1 font-semibold text-xs" data-testid="pe-preview-send-back">
      <ArrowLeft size={12} /> Back
    </button>
    <div className="flex-1 flex flex-col items-center justify-center text-center">
      {sending && (
        <div className="space-y-3 w-full">
          <Mail size={36} className="mx-auto text-blue-600 animate-pulse" />
          <p className="font-bold text-slate-800 text-sm">Generating branded PDF…</p>
          <div className="space-y-1.5 text-left max-w-[200px] mx-auto">
            <PreviewStep label="Sealing audit chain" done />
            <PreviewStep label="Embedding signature & photos" done />
            <PreviewStep label="Emailing customer" loading />
          </div>
        </div>
      )}
      {sent && (
        <div className="space-y-3 w-full" data-testid="pe-preview-send-success">
          <div className="w-14 h-14 rounded-full bg-emerald-100 mx-auto flex items-center justify-center">
            <CheckCircle2 size={28} className="text-emerald-600" />
          </div>
          <p className="font-extrabold text-slate-900 text-base">Sent to customer</p>
          <p className="text-slate-600 text-xs max-w-[220px] mx-auto leading-relaxed">
            Branded PDF emailed to <strong className="text-slate-800">ops@puregym-birmingham.co.uk</strong>. Receipt + audit chain logged.
          </p>
          <div className="rounded-xl bg-slate-50 border border-slate-200 p-3 text-left">
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">Earned on this job</p>
            <p className="font-extrabold text-emerald-600 text-xl tabular-nums">£148.50</p>
            <p className="text-[10px] text-slate-400 mt-0.5">Labour + 1 × BELT-001 · cleared to wallet on customer pay</p>
          </div>
          <button
            type="button"
            onClick={onDone}
            data-testid="pe-preview-restart-cta"
            className="gx-cta w-full rounded-lg font-bold py-2.5 text-sm shadow-lg active:scale-[0.98] transition inline-flex items-center justify-center gap-1.5 mt-1"
            style={{ color: '#fff' }}
          >
            <RotateCcw size={12} /> Try the flow again
          </button>
        </div>
      )}
    </div>
  </div>
);


const PreviewStep = ({ label, done, loading }) => (
  <div className="flex items-center gap-2 text-xs">
    {done && <CheckCircle2 size={12} className="text-emerald-500 flex-shrink-0" />}
    {loading && (
      <span className="w-3 h-3 rounded-full border-2 border-blue-600 border-t-transparent animate-spin flex-shrink-0" />
    )}
    <span className={done ? 'text-slate-500 line-through' : 'text-slate-700 font-medium'}>{label}</span>
  </div>
);


export default LiveEngineerAppPreview;
