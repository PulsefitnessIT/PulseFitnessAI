/**
 * Marketing Suite Product Tour
 *
 * Auto-opens for first-time visitors (state stored on the backend so the
 * tour persists across devices). Walks through the 7 main tabs with a
 * short pitch + an animated illustration of what each tab does, and
 * finishes with an offer to seed disposable demo data so the user can
 * actually FEEL the platform — audience, draft campaign, AI poster,
 * mini journey — all tagged `is_demo` and removable in one click.
 *
 * Design notes:
 *   • Centred modal with backdrop blur, theme-aware via CSS vars
 *   • Step illustrations are pure SVG so they look crisp in light + dark
 *   • Progress dots top, Skip / Back / Next bottom
 *   • The final step shows a "Create demo data" primary CTA
 *   • Re-openable via the floating "Take a tour" pill on every tab
 */
import { useEffect, useState } from 'react';
import axios from 'axios';
import {
  Sparkles, X, ChevronLeft, ChevronRight, Loader2, Users, Mail, Workflow, ImagePlus, BarChart3, Rocket, Trash2,
} from 'lucide-react';
import { notify, useConfirm } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

const STEPS = [
  {
    id: 'welcome',
    icon: Rocket,
    accent: 'var(--color-brand-cyan)',
    title: 'Your AI marketing co-pilot',
    body: 'Built for fitness operators — segmentation, campaigns, AI creatives, and visual journeys, all in one place. The next 60 seconds will show you the four things that get a Pulse club its first £1k of recovered revenue.',
    illustration: 'rocket',
  },
  {
    id: 'audiences',
    icon: Users,
    accent: 'var(--color-brand-blue)',
    title: 'Audiences in plain English',
    body: 'Type "high spenders at risk of churning" — AI builds a live, dynamic segment that updates as members come and go. No SQL. No spreadsheets. Just intent.',
    illustration: 'audience',
    tabHint: 'audiences',
  },
  {
    id: 'campaigns',
    icon: Mail,
    accent: 'var(--color-brand-blue)',
    title: 'Quick-start campaign templates',
    body: '6 pre-built recipes — Welcome new member, Win-back, Class promo, PT upsell, Failed payment, Referral — auto-target the right audience with copy already filled in. Ship in 60 seconds.',
    illustration: 'campaigns',
    tabHint: 'campaigns',
  },
  {
    id: 'creative',
    icon: ImagePlus,
    accent: 'var(--color-pink)',
    title: 'AI-generated marketing imagery',
    body: 'Type a mood — "high-energy spin Saturday morning" — and gpt-image-1 generates branded posters, social tiles, and email heroes in ~30 seconds. Or upload your own photos.',
    illustration: 'creative',
    tabHint: 'creative',
  },
  {
    id: 'journeys',
    icon: Workflow,
    accent: 'var(--color-accent-purple)',
    title: 'Visual automation journeys',
    body: 'Drag-and-drop trigger → wait → send → branch → tag. Welcome series, win-back sequences, post-class follow-ups — design them like a flowchart and they run themselves.',
    illustration: 'journey',
    tabHint: 'journeys',
  },
  {
    id: 'performance',
    icon: BarChart3,
    accent: 'var(--color-success)',
    title: 'Attribution that actually works',
    body: 'Every booking and payment within 7 days of an opened/clicked email auto-attributes back to the campaign. See which messages drive real money — not just clicks.',
    illustration: 'metrics',
    tabHint: 'performance',
  },
  {
    id: 'demo',
    icon: Sparkles,
    accent: 'var(--color-brand-cyan)',
    title: 'Want to see it with your data?',
    body: 'I can spin up disposable demo data right now — one VIP audience, a draft Saturday-spin campaign, an AI-generated poster, and a Welcome-new-member journey. Tagged "demo" and removable in one click.',
    illustration: 'sparkle',
    final: true,
  },
];

const ILLUSTRATIONS = {
  rocket: (
    <svg viewBox="0 0 240 160" className="w-full h-32">
      <defs>
        <linearGradient id="rk" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="var(--color-brand-cyan)" />
          <stop offset="100%" stopColor="var(--color-brand-blue)" />
        </linearGradient>
      </defs>
      <circle cx="60" cy="80" r="3" fill="var(--color-brand-cyan)" opacity="0.4"><animate attributeName="opacity" values="0.4;1;0.4" dur="2s" repeatCount="indefinite" /></circle>
      <circle cx="180" cy="40" r="2" fill="var(--color-brand-cyan)" opacity="0.6"><animate attributeName="opacity" values="0.6;1;0.6" dur="1.5s" repeatCount="indefinite" /></circle>
      <circle cx="200" cy="110" r="2" fill="var(--color-brand-cyan)" opacity="0.5"><animate attributeName="opacity" values="0.5;1;0.5" dur="2.2s" repeatCount="indefinite" /></circle>
      <g transform="translate(120 80)">
        <path d="M -20 30 L 0 -40 L 20 30 Z" fill="url(#rk)" />
        <circle cx="0" cy="-10" r="6" fill="white" opacity="0.9" />
        <path d="M -15 30 L -25 50 L -10 40 Z" fill="var(--color-orange-warm)" opacity="0.8">
          <animate attributeName="opacity" values="0.8;0.3;0.8" dur="0.4s" repeatCount="indefinite" />
        </path>
        <path d="M 15 30 L 25 50 L 10 40 Z" fill="var(--color-orange-warm)" opacity="0.8">
          <animate attributeName="opacity" values="0.3;0.8;0.3" dur="0.4s" repeatCount="indefinite" />
        </path>
      </g>
    </svg>
  ),
  audience: (
    <svg viewBox="0 0 240 160" className="w-full h-32">
      <defs><linearGradient id="ad" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stopColor="var(--color-brand-blue)" /><stop offset="100%" stopColor="var(--color-brand-cyan)" /></linearGradient></defs>
      <rect x="20" y="40" width="200" height="22" rx="11" fill="url(#ad)" opacity="0.15" />
      <rect x="20" y="40" width="80" height="22" rx="11" fill="url(#ad)">
        <animate attributeName="width" values="40;140;80" dur="3s" repeatCount="indefinite" />
      </rect>
      <text x="20" y="32" fontSize="11" fill="currentColor" opacity="0.6">"high spenders at risk"</text>
      <text x="20" y="86" fontSize="14" fill="currentColor" fontWeight="700">23 contacts match</text>
      <g transform="translate(20 100)">
        {[0,1,2,3,4,5].map(i => (
          <circle key={i} cx={i*22 + 12} cy="20" r="11" fill="url(#ad)" opacity={0.4 + i*0.1}>
            <animate attributeName="r" values="9;12;9" dur="2s" begin={`${i*0.15}s`} repeatCount="indefinite" />
          </circle>
        ))}
      </g>
    </svg>
  ),
  campaigns: (
    <svg viewBox="0 0 240 160" className="w-full h-32">
      {[0,1,2].map(i => (
        <g key={i} transform={`translate(${20 + i*70} ${30 + i*15})`}>
          <rect width="60" height="80" rx="8" fill="white" stroke="var(--color-brand-blue)" strokeOpacity="0.3" />
          <rect x="8" y="10" width="44" height="6" rx="3" fill="var(--color-brand-blue)" opacity="0.6" />
          <rect x="8" y="22" width="30" height="4" rx="2" fill="currentColor" opacity="0.3" />
          <rect x="8" y="30" width="36" height="4" rx="2" fill="currentColor" opacity="0.3" />
          <rect x="8" y="60" width="44" height="12" rx="6" fill="var(--color-brand-cyan)">
            <animate attributeName="opacity" values="0.5;1;0.5" dur="2s" begin={`${i*0.3}s`} repeatCount="indefinite" />
          </rect>
        </g>
      ))}
    </svg>
  ),
  creative: (
    <svg viewBox="0 0 240 160" className="w-full h-32">
      <defs><linearGradient id="cv" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stopColor="var(--color-pink)" /><stop offset="100%" stopColor="var(--color-accent-purple)" /></linearGradient></defs>
      <rect x="40" y="20" width="160" height="100" rx="10" fill="url(#cv)" />
      <g transform="translate(120 70)">
        <circle r="20" fill="white" opacity="0.2">
          <animate attributeName="r" values="15;22;15" dur="2s" repeatCount="indefinite" />
        </circle>
        <path d="M -8 -8 L 8 0 L -8 8 Z" fill="white" />
      </g>
      <text x="120" y="115" fontSize="9" fill="white" textAnchor="middle" fontWeight="600" opacity="0.9">SATURDAY SPIN · 8AM</text>
      <g transform="translate(180 30)">
        <Sparkle />
      </g>
    </svg>
  ),
  journey: (
    <svg viewBox="0 0 240 160" className="w-full h-32">
      <defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M 0 0 L 6 3 L 0 6 Z" fill="var(--color-accent-purple)" /></marker></defs>
      {[
        {x:30, label:'Trigger', color:'var(--color-brand-cyan)'},
        {x:100, label:'Wait 1d', color:'#FF9933'},
        {x:170, label:'Email', color:'var(--color-brand-blue)'},
      ].map((node, i) => (
        <g key={i}>
          <rect x={node.x} y="60" width="50" height="40" rx="8" fill={node.color} opacity="0.85">
            <animate attributeName="opacity" values="0.6;1;0.6" dur="3s" begin={`${i*0.6}s`} repeatCount="indefinite" />
          </rect>
          <text x={node.x + 25} y="84" fontSize="9" fill="white" textAnchor="middle" fontWeight="700">{node.label}</text>
        </g>
      ))}
      <line x1="80" y1="80" x2="100" y2="80" stroke="var(--color-accent-purple)" strokeWidth="2" markerEnd="url(#arrow)" />
      <line x1="150" y1="80" x2="170" y2="80" stroke="var(--color-accent-purple)" strokeWidth="2" markerEnd="url(#arrow)" />
    </svg>
  ),
  metrics: (
    <svg viewBox="0 0 240 160" className="w-full h-32">
      <defs><linearGradient id="mt" x1="0%" y1="100%" x2="0%" y2="0%"><stop offset="0%" stopColor="var(--color-success)" stopOpacity="0.1" /><stop offset="100%" stopColor="var(--color-success)" stopOpacity="0.6" /></linearGradient></defs>
      <path d="M 20 130 L 60 90 L 100 100 L 140 60 L 180 70 L 220 30 L 220 140 L 20 140 Z" fill="url(#mt)" />
      <path d="M 20 130 L 60 90 L 100 100 L 140 60 L 180 70 L 220 30" fill="none" stroke="var(--color-success)" strokeWidth="2.5" />
      {[60,100,140,180,220].map((x, i) => {
        const y = [90,100,60,70,30][i];
        return <circle key={i} cx={x} cy={y} r="4" fill="var(--color-success)"><animate attributeName="r" values="3;5;3" dur="2s" begin={`${i*0.2}s`} repeatCount="indefinite" /></circle>;
      })}
      <text x="120" y="20" fontSize="11" fill="currentColor" textAnchor="middle" fontWeight="700">£3,420 attributed (30d)</text>
    </svg>
  ),
  sparkle: (
    <svg viewBox="0 0 240 160" className="w-full h-32">
      <defs><radialGradient id="sp"><stop offset="0%" stopColor="var(--color-brand-cyan)" /><stop offset="100%" stopColor="var(--color-brand-cyan)" stopOpacity="0" /></radialGradient></defs>
      <circle cx="120" cy="80" r="60" fill="url(#sp)" opacity="0.4">
        <animate attributeName="r" values="40;70;40" dur="3s" repeatCount="indefinite" />
      </circle>
      {[[120,30],[60,60],[180,60],[120,130],[40,110],[200,110]].map(([x,y], i) => (
        <g key={i} transform={`translate(${x} ${y})`}>
          <path d="M 0 -8 L 2 -2 L 8 0 L 2 2 L 0 8 L -2 2 L -8 0 L -2 -2 Z" fill="var(--color-brand-cyan)">
            <animateTransform attributeName="transform" type="rotate" from="0" to="360" dur={`${4+i}s`} repeatCount="indefinite" />
          </path>
        </g>
      ))}
    </svg>
  ),
};

function Sparkle() {
  return <path d="M 0 -8 L 2 -2 L 8 0 L 2 2 L 0 8 L -2 2 L -8 0 L -2 -2 Z" fill="white" opacity="0.9" />;
}

const MarketingTour = ({ API, headers, onJumpToTab, onComplete }) => {
  const confirm = useConfirm();
  const [open, setOpen] = useState(false);
  const [stepIdx, setStepIdx] = useState(0);
  const [status, setStatus] = useState({ tour_seen: true, demo_data_exists: false });
  const [seeding, setSeeding] = useState(false);
  const step = STEPS[stepIdx];

  // Iter 216h49 — Auto-open disabled. The tour content is out of date
  // ("not pointing at the right buttons" per Lee). Manual launch via
  // the sidebar trigger (setStepIdx + setOpen) still works.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { data } = await axios.get(`${API}/api/marketing/tour/status`, { headers });
        if (!cancelled) {
          setStatus(data);
        }
      } catch { /* sidebar isn't critical */ }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line
  }, []);

  // When step changes, hint the parent to switch tabs so the user sees real context behind the modal.
  useEffect(() => {
    if (open && step.tabHint && onJumpToTab) onJumpToTab(step.tabHint);
  }, [stepIdx, open, step.tabHint, onJumpToTab]);

  const skip = async () => {
    try { await axios.post(`${API}/api/marketing/tour/dismiss`, {}, { headers }); } catch { /* ignore */ }
    setStatus((s) => ({ ...s, tour_seen: true }));
    setOpen(false);
    if (onComplete) onComplete();
  };

  const seedDemo = async () => {
    setSeeding(true);
    try {
      const { data } = await axios.post(`${API}/api/marketing/tour/seed`, {}, { headers });
      const realAi = data.creative_used_real_ai;
      notify.success(
        'Demo data ready',
        realAi
          ? 'Audience, draft campaign, AI-generated poster, and Welcome journey created. Have a play — they\'re tagged "demo" and removable in one click.'
          : 'Audience, draft campaign, sample poster, and Welcome journey created (image fallback used). Have a play!',
      );
      setStatus({ tour_seen: true, demo_data_exists: true });
      setOpen(false);
      if (onComplete) onComplete();
      if (onJumpToTab) onJumpToTab('campaigns');
    } catch (err) {
      notify.error(err.response?.data?.detail || 'Couldn\'t seed demo data');
    } finally {
      setSeeding(false);
    }
  };

  const clearDemo = async () => {
    const ok = await confirm({
      title: 'Clear all demo data?',
      detail: 'Removes the tour audience, campaign, poster, and journey. Your real data is untouched.',
      tone: 'warning', confirmLabel: 'Clear demo',
    });
    if (!ok) return;
    try {
      const { data } = await axios.delete(`${API}/api/marketing/tour/demo-data`, { headers });
      const total = data.audiences_removed + data.campaigns_removed + data.journeys_removed + data.creatives_removed;
      notify.success('Demo data cleared', `${total} item${total === 1 ? '' : 's'} removed.`);
      setStatus({ tour_seen: true, demo_data_exists: false });
    } catch (err) {
      notifyApiError(notify, err, 'Clear failed');
    }
  };

  const Icon = step.icon;
  const Illust = ILLUSTRATIONS[step.illustration];

  return (
    <>
      {/* Floating "Take a tour" pill — always available, lower-left */}
      <div className="fixed bottom-4 left-4 z-40 flex flex-col gap-2" data-testid="marketing-tour-launcher-host">
        <button
          onClick={() => { setStepIdx(0); setOpen(true); }}
          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-full bg-gradient-to-r from-[var(--color-brand-blue)] to-[var(--color-brand-cyan)] text-white text-xs font-semibold shadow-lg hover:shadow-xl hover:scale-[1.02] transition"
          data-testid="marketing-tour-launcher"
          aria-label="Take a product tour"
        >
          <Sparkles size={13} /> Take a tour
        </button>
        {status.demo_data_exists && (
          <button
            onClick={clearDemo}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-full bg-zinc-900/80 dark:bg-zinc-100/10 text-white text-[10px] font-semibold backdrop-blur shadow"
            data-testid="marketing-tour-clear-demo"
          >
            <Trash2 size={11} /> Clear demo data
          </button>
        )}
      </div>

      {!open ? null : (
        <div
          className="fixed inset-0 z-[200] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4"
          onClick={skip}
          data-testid="marketing-tour-modal"
        >
          <div
            className="w-full max-w-lg rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[calc(100vh-2rem)]"
            style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)', borderWidth: 1 }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header strip — accent gradient + progress dots */}
            <div className="relative px-6 pt-6 pb-4 flex-shrink-0" style={{ background: `linear-gradient(135deg, ${step.accent}15, transparent)` }}>
              <button
                onClick={skip}
                className="absolute top-4 right-4 p-1 rounded-md hover:bg-black/10 dark:hover:bg-white/10 transition"
                data-testid="marketing-tour-close"
                aria-label="Skip tour"
              >
                <X size={16} style={{ color: 'var(--theme-text-muted)' }} />
              </button>
              <div className="flex items-center gap-1.5 mb-3" data-testid="marketing-tour-progress">
                {STEPS.map((_, i) => (
                  <button
                    key={i}
                    onClick={() => setStepIdx(i)}
                    className="h-1.5 rounded-full transition-all"
                    style={{
                      width: i === stepIdx ? 24 : 8,
                      background: i <= stepIdx ? step.accent : 'var(--theme-border)',
                    }}
                    aria-label={`Step ${i + 1}`}
                    data-testid={`marketing-tour-dot-${i}`}
                  />
                ))}
              </div>
              <div className="flex items-center gap-2">
                <div
                  className="w-9 h-9 rounded-lg flex items-center justify-center"
                  style={{ background: `${step.accent}20`, color: step.accent }}
                >
                  <Icon size={18} />
                </div>
                <span className="text-[10px] font-bold uppercase tracking-[0.2em]" style={{ color: 'var(--theme-text-muted)' }}>
                  Step {stepIdx + 1} of {STEPS.length}
                </span>
              </div>
            </div>

            {/* Body — illustration + title + copy */}
            <div className="px-6 pb-2 flex-1 overflow-y-auto" style={{ color: 'var(--theme-text)' }}>
              <div className="rounded-xl p-2 mb-4" style={{ background: 'var(--theme-bg)' }} data-testid={`marketing-tour-illust-${step.illustration}`}>
                {Illust}
              </div>
              <h2 className="text-xl font-bold mb-2 leading-tight pulse-font-heading">{step.title}</h2>
              <p className="text-sm leading-relaxed" style={{ color: 'var(--theme-text-muted)' }}>{step.body}</p>
            </div>

            {/* Footer actions */}
            <div className="px-6 py-4 flex items-center gap-2 flex-shrink-0 border-t" style={{ borderColor: 'var(--theme-border)' }}>
              <button
                onClick={skip}
                className="text-xs font-semibold hover:underline"
                style={{ color: 'var(--theme-text-muted)' }}
                data-testid="marketing-tour-skip"
              >
                Skip tour
              </button>
              <div className="ml-auto flex gap-2">
                <button
                  onClick={() => setStepIdx((i) => Math.max(0, i - 1))}
                  disabled={stepIdx === 0}
                  className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md text-xs font-semibold border disabled:opacity-40"
                  style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
                  data-testid="marketing-tour-back"
                >
                  <ChevronLeft size={12} /> Back
                </button>
                {step.final ? (
                  <button
                    onClick={seedDemo}
                    disabled={seeding}
                    className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-md text-xs font-bold text-white shadow disabled:opacity-50"
                    style={{ background: `linear-gradient(135deg, ${step.accent}, var(--color-brand-blue))` }}
                    data-testid="marketing-tour-seed"
                  >
                    {seeding ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
                    {seeding ? 'Creating…' : 'Create demo data'}
                  </button>
                ) : (
                  <button
                    onClick={() => setStepIdx((i) => Math.min(STEPS.length - 1, i + 1))}
                    className="inline-flex items-center gap-1 px-4 py-1.5 rounded-md text-xs font-bold text-white shadow"
                    style={{ background: step.accent }}
                    data-testid="marketing-tour-next"
                  >
                    Next <ChevronRight size={12} />
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default MarketingTour;
