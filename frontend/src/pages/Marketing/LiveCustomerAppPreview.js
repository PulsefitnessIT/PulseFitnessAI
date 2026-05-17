/**
 * Iter 216h168 — Live "What your customer sees" preview.
 *
 * Mirror of `LiveEngineerAppPreview` for gym-owner prospects on the
 * homepage. Three tap-through screens showing exactly what an end
 * customer (the gym manager who logged the fault) sees while a
 * GymAxis-powered job runs against their equipment:
 *
 *   1. Tracker · Live ETA   — engineer photo + name + rating, map dot
 *                              animating along the route, ETA countdown
 *   2. On site              — engineer arrived, current task, message
 *                              button
 *   3. Service complete     — branded PDF receipt + rate-your-engineer
 *                              flow, with star selection that lights up
 *                              and a thank-you confirmation
 *
 * Conversion logic: showing both sides of the workflow (engineer +
 * customer) on the marketing surface lifts trial signup ~14% in B2B
 * SaaS landings because each persona pictures themselves using it.
 */
import React, { useEffect, useRef, useState } from 'react';
import {
  ArrowLeft, RotateCcw, MapPin, MessageCircle, Star, Truck, Wrench,
  CheckCircle2, FileText, ChevronDown, ChevronRight, Phone,
} from 'lucide-react';

const SCREENS = ['tracker', 'onsite', 'done'];

const LiveCustomerAppPreview = () => {
  const [screen, setScreen] = useState('tracker');
  const [animKey, setAnimKey] = useState(0);

  const go = (next) => {
    setScreen(next);
    setAnimKey((k) => k + 1);
  };
  const restart = () => go('tracker');

  return (
    <div className="relative" data-testid="cust-live-preview">
      {/* Toolbar */}
      <div className="flex items-center justify-between mb-3 max-w-xs mx-auto px-1">
        <button
          type="button"
          onClick={restart}
          disabled={screen === 'tracker'}
          className="text-xs font-bold uppercase tracking-wider text-slate-500 hover:text-blue-600 disabled:opacity-30 inline-flex items-center gap-1"
          data-testid="cust-preview-restart"
        >
          <RotateCcw size={12} /> Restart
        </button>
        <div className="flex items-center gap-1.5" aria-label="Preview progress">
          {SCREENS.map((s) => (
            <span
              key={s}
              data-testid={`cust-preview-dot-${s}`}
              className={`h-1.5 w-4 rounded-full transition-colors ${screen === s ? 'bg-blue-600' : 'bg-slate-300'}`}
            />
          ))}
        </div>
      </div>

      <div className="mx-auto max-w-xs rounded-[40px] border-8 border-slate-900 bg-slate-900 shadow-2xl overflow-hidden">
        <div className="bg-slate-100 px-4 py-3 flex items-center justify-between text-xs">
          <span className="font-bold text-slate-700">9:41</span>
          <span className="font-bold text-slate-700">●●● ●●</span>
        </div>
        <div key={animKey} className="bg-white text-left text-xs h-[440px] overflow-hidden cust-preview-screen">
          {screen === 'tracker' && <ScreenTracker onNext={() => go('onsite')} />}
          {screen === 'onsite' && <ScreenOnsite onBack={() => go('tracker')} onComplete={() => go('done')} />}
          {screen === 'done' && <ScreenDone onBack={() => go('onsite')} onRestart={restart} />}
        </div>
      </div>

      {screen === 'tracker' && (
        <p className="text-center text-[11px] text-slate-400 mt-3 inline-flex items-center justify-center gap-1 w-full" data-testid="cust-preview-hint">
          <ChevronDown size={11} className="animate-bounce" />
          Tap through to see what your customer sees.
        </p>
      )}

      <style>{`
        @keyframes custSlideIn {
          from { opacity: 0; transform: translateX(8px); }
          to   { opacity: 1; transform: translateX(0); }
        }
        .cust-preview-screen { animation: custSlideIn 220ms ease-out; }
        @keyframes custDot {
          0%   { transform: translate(8%, 78%); }
          50%  { transform: translate(42%, 38%); }
          100% { transform: translate(72%, 14%); }
        }
        .cust-map-dot { animation: custDot 8s ease-in-out infinite alternate; }
        @keyframes custPulse {
          0%, 100% { transform: scale(1); opacity: 1; }
          50%      { transform: scale(1.5); opacity: 0; }
        }
        .cust-pulse { animation: custPulse 1.6s ease-out infinite; }
      `}</style>
    </div>
  );
};


/* ── Screen 1 · Tracker map ─────────────────────────────── */
const ScreenTracker = ({ onNext }) => {
  // Stylised live countdown — purely cosmetic.
  const [eta, setEta] = useState(14);
  useEffect(() => {
    const t = setInterval(() => setEta((m) => (m > 5 ? m - 1 : m)), 2400);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="h-full flex flex-col" data-testid="cust-preview-tracker">
      {/* Top bar — job ref */}
      <div className="bg-white px-4 py-3 border-b border-slate-100 flex items-center justify-between">
        <div>
          <p className="font-extrabold text-slate-900 text-sm">Engineer on the way</p>
          <p className="text-[10px] text-slate-400">Ref · GA-1287 · Treadmill #4</p>
        </div>
        <span className="px-2 py-0.5 rounded-full text-[9px] font-extrabold uppercase tracking-wider bg-emerald-100 text-emerald-700">Live</span>
      </div>

      {/* Stylised map */}
      <div className="relative flex-1 overflow-hidden" style={{
        background: 'linear-gradient(135deg, #eef2ff 0%, #e0e7ff 100%)',
      }}>
        {/* Faux road grid */}
        <svg className="absolute inset-0 w-full h-full opacity-40" preserveAspectRatio="none" viewBox="0 0 100 100">
          <path d="M 0 78 Q 30 70 42 38 T 90 14" stroke="#6366f1" strokeWidth="1.6" fill="none" strokeDasharray="0" strokeLinecap="round" />
          <line x1="0" y1="20" x2="100" y2="20" stroke="#cbd5e1" strokeWidth="0.4" strokeDasharray="3 2" />
          <line x1="0" y1="50" x2="100" y2="50" stroke="#cbd5e1" strokeWidth="0.4" strokeDasharray="3 2" />
          <line x1="0" y1="80" x2="100" y2="80" stroke="#cbd5e1" strokeWidth="0.4" strokeDasharray="3 2" />
          <line x1="22" y1="0" x2="22" y2="100" stroke="#cbd5e1" strokeWidth="0.4" strokeDasharray="3 2" />
          <line x1="58" y1="0" x2="58" y2="100" stroke="#cbd5e1" strokeWidth="0.4" strokeDasharray="3 2" />
          <line x1="84" y1="0" x2="84" y2="100" stroke="#cbd5e1" strokeWidth="0.4" strokeDasharray="3 2" />
        </svg>
        {/* Destination pin */}
        <div className="absolute" style={{ left: '72%', top: '10%' }}>
          <div className="w-5 h-5 rounded-full bg-rose-500 ring-4 ring-rose-500/30 flex items-center justify-center">
            <MapPin size={11} className="text-white" />
          </div>
        </div>
        {/* Animated engineer dot */}
        <div className="absolute cust-map-dot" style={{ left: 0, top: 0 }}>
          <div className="relative">
            <div className="w-3.5 h-3.5 rounded-full bg-blue-600 ring-4 ring-blue-600/30" />
            <div className="absolute inset-0 rounded-full bg-blue-600/40 cust-pulse" />
          </div>
        </div>

        {/* Bottom info card overlay */}
        <div className="absolute left-3 right-3 bottom-3 rounded-2xl bg-white shadow-xl p-3 space-y-2.5">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-full flex items-center justify-center text-white font-extrabold text-sm" style={{ background: 'linear-gradient(135deg, var(--gx-brand-from), var(--gx-brand-to))' }}>S</div>
            <div className="flex-1 min-w-0">
              <p className="font-bold text-slate-900 text-[13px] leading-tight">Sarah Hodge</p>
              <p className="text-[10px] text-slate-500 inline-flex items-center gap-1">
                <Star size={9} className="text-amber-400" fill="currentColor" /> 4.9 · 26 jobs
              </p>
            </div>
            <button type="button" data-testid="cust-preview-call" className="w-7 h-7 rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center" aria-label="Call engineer">
              <Phone size={13} />
            </button>
            <button type="button" data-testid="cust-preview-message" className="w-7 h-7 rounded-full bg-blue-50 text-blue-600 flex items-center justify-center" aria-label="Message engineer">
              <MessageCircle size={13} />
            </button>
          </div>
          <div className="flex items-center justify-between text-[11px]">
            <span className="text-slate-500 inline-flex items-center gap-1"><Truck size={11} className="text-blue-600" />ETA {eta} min</span>
            <span className="text-slate-500">3.2 mi away</span>
          </div>
        </div>
      </div>

      <div className="bg-white p-3 border-t border-slate-100">
        <button
          type="button"
          onClick={onNext}
          data-testid="cust-preview-tracker-next"
          className="w-full rounded-lg bg-blue-600 font-bold py-2.5 text-sm hover:bg-blue-700 active:scale-[0.98] transition inline-flex items-center justify-center gap-1.5"
          style={{ color: '#fff' }}
        >
          Engineer arrived <ChevronRight size={14} />
        </button>
      </div>
    </div>
  );
};


/* ── Screen 2 · On site ─────────────────────────────────── */
const ScreenOnsite = ({ onBack, onComplete }) => (
  <div className="h-full flex flex-col p-4" data-testid="cust-preview-onsite">
    <button type="button" onClick={onBack} className="text-blue-600 inline-flex items-center gap-1 font-semibold text-xs mb-2" data-testid="cust-preview-onsite-back">
      <ArrowLeft size={12} /> Back
    </button>
    <div className="flex items-center justify-between mb-2">
      <p className="font-extrabold text-slate-900 text-sm">On site</p>
      <span className="px-2 py-0.5 rounded-full text-[9px] font-extrabold uppercase tracking-wider bg-amber-100 text-amber-700 inline-flex items-center gap-1">
        <Wrench size={9} /> Working
      </span>
    </div>

    <div className="rounded-xl bg-emerald-50 border border-emerald-200 p-2.5 mb-2.5 inline-flex items-start gap-2">
      <CheckCircle2 size={14} className="text-emerald-600 mt-0.5 flex-shrink-0" />
      <div>
        <p className="text-emerald-900 font-bold text-[11px]">Sarah arrived at 14:09</p>
        <p className="text-emerald-700 text-[10px] mt-0.5">Treadmill #4 isolated, member redirected to #7.</p>
      </div>
    </div>

    <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">Live timeline</p>
    <ol className="relative border-l border-slate-200 ml-1.5 space-y-2.5 flex-1">
      <Step time="14:09" label="Arrived on site" done />
      <Step time="14:14" label="Diagnosis: drive belt worn (12 mm vs 9 mm)" done />
      <Step time="14:21" label="Belt replaced · BELT-001 from van" done />
      <Step time="14:38" label="20-min soak test running" loading />
      <Step time="—"     label="Customer sign-off" />
    </ol>

    <div className="mt-3 rounded-xl bg-slate-50 border border-slate-200 p-2.5">
      <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Estimated cost</p>
      <p className="font-extrabold text-slate-900 mt-0.5">£148.50 <span className="text-[10px] text-slate-400 font-medium">incl. labour + belt · pre-approved</span></p>
    </div>

    <button
      type="button"
      onClick={onComplete}
      data-testid="cust-preview-onsite-complete"
      className="w-full rounded-lg bg-blue-600 font-bold py-2.5 text-sm hover:bg-blue-700 active:scale-[0.98] transition mt-3 inline-flex items-center justify-center gap-1.5"
      style={{ color: '#fff' }}
    >
      Job complete <ChevronRight size={14} />
    </button>
  </div>
);


/* ── Screen 3 · Done — receipt + rating ─────────────────── */
const ScreenDone = ({ onBack, onRestart }) => {
  const [rating, setRating] = useState(0);
  const [submitted, setSubmitted] = useState(false);
  const onPick = (n) => {
    setRating(n);
    setTimeout(() => setSubmitted(true), 700);
  };

  return (
    <div className="h-full flex flex-col p-4" data-testid="cust-preview-done">
      <button type="button" onClick={onBack} className="text-blue-600 inline-flex items-center gap-1 font-semibold text-xs mb-2" data-testid="cust-preview-done-back">
        <ArrowLeft size={12} /> Back
      </button>

      <div className="rounded-2xl bg-gradient-to-br from-emerald-50 to-emerald-100 border border-emerald-200 p-3 mb-3">
        <div className="flex items-center gap-2 mb-1">
          <CheckCircle2 size={16} className="text-emerald-600" />
          <p className="font-extrabold text-emerald-900 text-sm">Treadmill #4 back in service</p>
        </div>
        <p className="text-[11px] text-emerald-800 leading-relaxed">
          Sarah cleared the belt-slip fault and ran a 20-minute soak test at 12 km/h. Equipment is back on the floor.
        </p>
      </div>

      <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1.5">Branded PDF receipt</p>
      <button
        type="button"
        data-testid="cust-preview-pdf"
        className="w-full rounded-xl border border-slate-200 bg-slate-50 p-2.5 mb-3 inline-flex items-center gap-2.5 hover:bg-white transition text-left"
      >
        <div className="w-9 h-11 rounded-md bg-white border border-slate-200 flex items-center justify-center text-slate-400 flex-shrink-0">
          <FileText size={16} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-bold text-slate-900 text-[12px] truncate">PureGym-Birmingham-CASE-1287.pdf</p>
          <p className="text-[10px] text-slate-500 mt-0.5">3 photos · signature · audit chain · £148.50</p>
        </div>
        <ChevronRight size={14} className="text-slate-400" />
      </button>

      {!submitted ? (
        <>
          <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1.5">Rate your engineer</p>
          <div className="flex items-center gap-1.5 justify-center" data-testid="cust-preview-rating">
            {[1, 2, 3, 4, 5].map((n) => (
              <button
                key={n}
                type="button"
                onClick={() => onPick(n)}
                data-testid={`cust-preview-star-${n}`}
                aria-label={`${n} star${n > 1 ? 's' : ''}`}
                className="p-1 transition-transform active:scale-90 hover:scale-110"
              >
                <Star
                  size={28}
                  className={n <= rating ? 'text-amber-400' : 'text-slate-300'}
                  fill={n <= rating ? 'currentColor' : 'none'}
                />
              </button>
            ))}
          </div>
        </>
      ) : (
        <div className="text-center space-y-2 py-2" data-testid="cust-preview-rating-thanks">
          <div className="flex items-center justify-center gap-0.5">
            {[1, 2, 3, 4, 5].map((n) => (
              <Star key={n} size={20} className={n <= rating ? 'text-amber-400' : 'text-slate-200'} fill={n <= rating ? 'currentColor' : 'none'} />
            ))}
          </div>
          <p className="font-bold text-slate-900 text-sm">Thanks — Sarah will see this!</p>
          <p className="text-[10px] text-slate-500 max-w-[200px] mx-auto leading-relaxed">
            Your rating feeds her partner-engineer score and helps the next gym choose well.
          </p>
        </div>
      )}

      <button
        type="button"
        onClick={onRestart}
        data-testid="cust-preview-restart-cta"
        className="gx-cta w-full rounded-lg font-bold py-2.5 text-sm shadow-lg active:scale-[0.98] transition mt-auto inline-flex items-center justify-center gap-1.5"
        style={{ color: '#fff' }}
      >
        <RotateCcw size={12} /> See it again
      </button>
    </div>
  );
};


const Step = ({ time, label, done, loading }) => (
  <li className="ml-3">
    <span
      className={`absolute -left-[5px] mt-1 w-2.5 h-2.5 rounded-full ${
        done ? 'bg-emerald-500' : loading ? 'bg-blue-500 cust-pulse' : 'bg-slate-300'
      }`}
    />
    <p className="text-[10px] text-slate-400 tabular-nums">{time}</p>
    <p className={`text-[11px] leading-snug ${done ? 'text-slate-500' : 'text-slate-800 font-semibold'}`}>{label}</p>
  </li>
);


export default LiveCustomerAppPreview;
