/**
 * InvoiceParseProgress — phased progress indicator for AI invoice parsing.
 * (Iter 216m.)
 *
 * The /api/master-admin/invoice/parse-for-wizard endpoint takes 30–35 s
 * for a 20-page invoice with claude-haiku-4-5. We can't speed it up
 * (gateway serialises concurrent calls, output tokens dominate latency
 * — see PRD 216l), but we can dramatically improve perceived UX with a
 * realistic phased progress bar.
 *
 * Phases:
 *   0–15%   — Upload (driven by axios onUploadProgress, real bytes)
 *   15–30%  — Extracting text from PDF
 *   30–95%  — Reading page X of Y with AI (animated by elapsed time)
 *   95–100% — Done
 *
 * Usage:
 *   const [progress, setProgress] = useState(null);
 *   // While uploading:
 *   setProgress({ phase: 'upload', pct: pctFromAxios });
 *   // After upload settles, until response lands:
 *   setProgress({ phase: 'parse', pageCount });
 *   // On success/error:
 *   setProgress(null);
 *
 *   <InvoiceParseProgress state={progress} />
 */
import React, { useEffect, useState } from 'react';
import { FileText, Sparkles, CheckCircle2, Loader2 } from 'lucide-react';

// Average wall-time for the AI parse phase (Carshalton 25 k chars
// benches at 32–35 s). The animation tracks this so the bar moves
// smoothly without lying — we cap at 95 % until the actual response
// lands so users never see the bar stick at 100 % for 10 s.
const AVG_AI_PARSE_MS = 33000;

const Bar = ({ pct, color = 'var(--color-brand-blue)' }) => (
  <div className="w-full h-1.5 rounded-full overflow-hidden bg-zinc-100" data-testid="invoice-progress-bar-track">
    <div
      className="h-full rounded-full transition-all duration-300"
      style={{ width: `${Math.max(0, Math.min(100, pct))}%`, background: color }}
      data-testid="invoice-progress-bar-fill"
    />
  </div>
);

const InvoiceParseProgress = ({ state }) => {
  const [parseElapsed, setParseElapsed] = useState(0);
  const [parsePage, setParsePage] = useState(1);

  // Tick once a second while we're in the parse phase so the bar moves
  // smoothly toward the AVG_AI_PARSE_MS target. Capped at 95 % until
  // the real response lands.
  useEffect(() => {
    if (state?.phase !== 'parse') {
      setParseElapsed(0);
      setParsePage(1);
      return undefined;
    }
    const start = Date.now();
    const id = setInterval(() => {
      const ms = Date.now() - start;
      setParseElapsed(ms);
      const total = state.pageCount || 20;
      // Map elapsed to a "current page" — 95% of the bar covers all
      // pages, the last 5% is reserved for the merge step.
      const pageEst = Math.min(total, Math.max(1, Math.ceil((ms / AVG_AI_PARSE_MS) * total)));
      setParsePage(pageEst);
    }, 250);
    return () => clearInterval(id);
  }, [state?.phase, state?.pageCount]);

  if (!state) return null;

  let pct = 0;
  let label = '';
  let Icon = Loader2;
  let iconClass = 'animate-spin text-[var(--color-brand-blue)]';

  if (state.phase === 'upload') {
    pct = Math.min(15, (state.pct || 0) * 0.15);
    label = `Uploading PDF… ${Math.round(state.pct || 0)}%`;
    Icon = FileText;
    iconClass = 'text-[var(--color-brand-blue)]';
  } else if (state.phase === 'extract') {
    pct = 22;
    label = 'Extracting text from PDF…';
    Icon = FileText;
  } else if (state.phase === 'parse') {
    const parsePctOfPhase = Math.min(0.95, parseElapsed / AVG_AI_PARSE_MS);
    pct = 30 + parsePctOfPhase * 65; // 30 → 95
    const total = state.pageCount;
    label = total
      ? `Reading page ${parsePage} of ${total} with AI…`
      : `Reading invoice with AI…`;
    Icon = Sparkles;
    iconClass = 'animate-pulse text-[var(--color-brand-cyan-hover)]';
  } else if (state.phase === 'done') {
    pct = 100;
    label = `Extracted ${state.itemCount ?? '?'} machine(s) from invoice`;
    Icon = CheckCircle2;
    iconClass = 'text-emerald-500';
  } else if (state.phase === 'error') {
    pct = 100;
    label = state.message || 'Parse failed';
    Icon = FileText;
    iconClass = 'text-red-500';
  }

  return (
    <div
      className="rounded-md border bg-blue-50/60 border-blue-200 p-2.5 mt-2 space-y-1.5"
      style={{ borderColor: state.phase === 'error' ? 'rgb(254 202 202)' : undefined, background: state.phase === 'error' ? 'rgb(254 242 242 / 0.7)' : undefined }}
      data-testid="invoice-parse-progress"
    >
      <div className="flex items-center gap-2">
        <Icon size={13} className={iconClass} />
        <span className="text-[11px] font-semibold flex-1" style={{ color: state.phase === 'error' ? 'rgb(153 27 27)' : 'var(--theme-text)' }} data-testid="invoice-parse-progress-label">
          {label}
        </span>
        {state.phase !== 'error' && state.phase !== 'done' ? (
          <span className="text-[10px] font-mono" style={{ color: 'var(--theme-text-muted)' }} data-testid="invoice-parse-progress-pct">
            {Math.round(pct)}%
          </span>
        ) : null}
      </div>
      <Bar
        pct={pct}
        color={state.phase === 'error' ? '#dc2626' : (state.phase === 'done' ? '#10b981' : 'var(--color-brand-blue)')}
      />
      {state.phase === 'parse' ? (
        <p className="text-[10px]" style={{ color: 'var(--theme-text-muted)' }}>
          Large invoices can take up to 60 s — please don&apos;t refresh.
        </p>
      ) : null}
    </div>
  );
};

export default InvoiceParseProgress;
