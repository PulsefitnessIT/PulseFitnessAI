/**
 * PartnerActivationChecklist.js (iter 216h284)
 *
 * "First 7 days" checklist shown on the partner dashboard. Six steps,
 * most auto-resolved server-side from the partner record + referrals
 * + compliance docs. Manual-ack steps (currently just "copy referral
 * link") hit POST /partners/me/checklist/ack.
 *
 * Collapses to a one-line trophy banner once 100% complete so it
 * doesn't keep nagging seasoned partners.
 */
import { useEffect, useState } from 'react';
import axios from 'axios';
import { CheckCircle2, Circle, Trophy, ChevronRight, Sparkles } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

export default function PartnerActivationChecklist({ onCopyLink, onSubscribeClick, onComplianceClick }) {
  const [data, setData] = useState(null);
  const [busyKey, setBusyKey] = useState(null);
  const [collapsed, setCollapsed] = useState(false);
  const headers = { Authorization: `Bearer ${localStorage.getItem('token')}` };

  const load = async () => {
    try {
      const r = await axios.get(`${API}/api/partners/me/checklist`, { headers });
      setData(r.data.checklist);
    } catch { /* hidden silently for non-partners */ }
  };
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  if (!data) return null;
  const pct = Math.round((data.done / data.total) * 100);

  // Once 100 % complete render a compact trophy banner — keep it on
  // screen for one session so the engineer sees the milestone, then
  // they can dismiss with the chevron.
  if (data.complete && collapsed) return null;
  if (data.complete) {
    return (
      <div
        className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 flex items-center gap-3"
        data-testid="partner-activation-complete"
      >
        <Trophy size={18} className="text-emerald-700 shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-bold text-emerald-900">You're fully set up — 7/7 milestones cleared.</p>
          <p className="text-[11px] text-emerald-800">Time to focus on referrals. The next reward unlocks at 5 referred gyms.</p>
        </div>
        <button
          onClick={() => setCollapsed(true)}
          className="text-emerald-700 hover:text-emerald-900 text-[11px] font-bold"
          data-testid="partner-activation-dismiss"
        >Dismiss</button>
      </div>
    );
  }

  const handleClick = async (step) => {
    if (step.done) return;
    // Manual-ack steps: hit the backend.
    if (data.ackable_keys.includes(step.key)) {
      setBusyKey(step.key);
      try {
        if (step.key === 'referral_link_copied' && onCopyLink) {
          await onCopyLink(); // reuse the parent's copy handler
        }
        const r = await axios.post(`${API}/api/partners/me/checklist/ack`,
          { key: step.key }, { headers });
        setData(r.data.checklist);
      } finally { setBusyKey(null); }
      return;
    }
    // Auto-resolved steps: nudge the parent to scroll to / open the
    // matching section. We pass a no-op for steps with no parent hook.
    const hooks = {
      subscribed: onSubscribeClick,
      compliance_uploaded: onComplianceClick,
    };
    const fn = hooks[step.key];
    if (typeof fn === 'function') fn();
  };

  return (
    <div className="rounded-xl border border-zinc-200 bg-white overflow-hidden" data-testid="partner-activation-checklist">
      <div className="px-4 py-3 flex items-center gap-3 border-b border-zinc-100 bg-gradient-to-r from-cyan-50/60 to-white">
        <Sparkles size={16} className="text-cyan-600 shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-bold text-zinc-900">Your first 7 days</p>
          <p className="text-[11px] text-zinc-500">
            {data.done} of {data.total} complete · {pct}% there
          </p>
        </div>
        <div className="h-1.5 w-24 sm:w-40 bg-zinc-200 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-cyan-500 to-emerald-500 transition-all duration-500"
            style={{ width: `${pct}%` }}
            data-testid="partner-activation-progress"
          />
        </div>
      </div>
      <ul className="divide-y divide-zinc-100" data-testid="partner-activation-steps">
        {data.steps.map((step) => {
          const Icon = step.done ? CheckCircle2 : Circle;
          const interactive = !step.done;
          const Tag = interactive ? 'button' : 'div';
          return (
            <Tag
              key={step.key}
              type={interactive ? 'button' : undefined}
              onClick={interactive ? () => handleClick(step) : undefined}
              disabled={busyKey === step.key}
              className={`w-full flex items-center gap-3 px-4 py-2.5 text-left ${interactive ? 'hover:bg-zinc-50' : 'opacity-80'}`}
              data-testid={`partner-activation-step-${step.key}`}
            >
              <Icon
                size={16}
                className={step.done ? 'text-emerald-600 shrink-0' : 'text-zinc-300 shrink-0'}
              />
              <div className="flex-1 min-w-0">
                <p className={`text-[13px] font-bold ${step.done ? 'text-zinc-500 line-through' : 'text-zinc-900'}`}>
                  {step.label}
                </p>
                <p className="text-[11px] text-zinc-500 truncate">{step.hint}</p>
              </div>
              {interactive && <ChevronRight size={13} className="text-zinc-300 shrink-0" />}
            </Tag>
          );
        })}
      </ul>
    </div>
  );
}
