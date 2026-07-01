/**
 * SchedulerHub — single Service Desk "Scheduler" tab combining:
 *   • AI Scheduling   — the re-plan/approve agent (default view)
 *   • Diary board     — the manual drag-and-drop diary
 *
 * Replaces the two separate tabs so planners have one home for scheduling.
 */
import { lazy, Suspense, useState, useEffect } from 'react';
import { Sparkles, CalendarDays, Loader2 } from 'lucide-react';
import { api } from '@/lib/api';
import { ServiceOpsEmbeddedContext } from './ServiceOpsShell';

const AIScheduling = lazy(() => import('./AIScheduling'));
const ServiceScheduler = lazy(() => import('./ServiceScheduler'));

const VIEWS = [
  { id: 'ai', label: 'AI Scheduling', icon: Sparkles },
  { id: 'diary', label: 'Diary board', icon: CalendarDays },
];

const Fallback = () => (
  <div className="flex items-center justify-center py-20 text-slate-500 text-sm">
    <Loader2 size={16} className="mr-2 animate-spin" /> Loading…
  </div>
);

export default function SchedulerHub() {
  const [view, setView] = useState('ai');
  const [pendingCount, setPendingCount] = useState(0);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const r = await api.get('/svc/scheduling/proposals', { params: { status: 'awaiting_approval', limit: 50 } });
        if (alive) setPendingCount((r.data.proposals || []).length);
      } catch { /* silent */ }
    };
    load();
    const t = setInterval(load, 60000);
    return () => { alive = false; clearInterval(t); };
  }, [view]);

  return (
    <div className="space-y-4" data-testid="scheduler-hub">
      <div className="inline-flex rounded-xl bg-slate-100 p-1 gap-1" data-testid="scheduler-hub-tabs">
        {VIEWS.map((v) => {
          const Icon = v.icon;
          const active = view === v.id;
          return (
            <button
              key={v.id}
              onClick={() => setView(v.id)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                active ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'
              }`}
              data-testid={`scheduler-hub-tab-${v.id}`}
            >
              <Icon size={15} /> {v.label}
              {v.id === 'ai' && pendingCount > 0 && (
                <span className="ml-1 inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full bg-indigo-600 text-white text-[10px] font-semibold" data-testid="ai-pending-badge">
                  {pendingCount}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {view === 'ai' ? (
        <Suspense fallback={<Fallback />}><AIScheduling /></Suspense>
      ) : (
        <ServiceOpsEmbeddedContext.Provider value={true}>
          <Suspense fallback={<Fallback />}><ServiceScheduler /></Suspense>
        </ServiceOpsEmbeddedContext.Provider>
      )}
    </div>
  );
}
