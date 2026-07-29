/* Insights tab — proactive opportunity tiles */
import { useEffect, useState } from 'react';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import { Calendar, TrendingDown, AlertTriangle, Sparkles, ChevronRight, Loader2 } from 'lucide-react';

const ICONS = { calendar: Calendar, 'trending-down': TrendingDown, 'alert-triangle': AlertTriangle, sparkles: Sparkles };

const InsightsTab = ({ API, headers, setTab }) => {
  const { t } = useTranslation();
  const [insights, setInsights] = useState(null);
  useEffect(() => {
    axios.get(`${API}/api/marketing/insights`, { headers }).then((r) => setInsights(r.data.insights)).catch(() => setInsights([]));
    // eslint-disable-next-line
  }, []);
  if (!insights) return <div className="flex items-center gap-2 text-zinc-400 dark:text-zinc-500 py-8"><Loader2 className="animate-spin" size={14} /> {t('mkt.ins_analysing', 'Analysing your gym…')}</div>;
  return (
    <div className="space-y-4" data-testid="marketing-insights-tab">
      {insights.length === 0 && <p className="text-sm text-zinc-400 dark:text-zinc-500">{t('mkt.ins_none', 'No opportunities right now — your engagement is healthy.')}</p>}
      <div className="grid md:grid-cols-2 gap-3">
        {insights.map((i) => {
          const Icon = ICONS[i.icon] || Sparkles;
          return (
            <div key={i.id} className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-4 hover:shadow-md transition" data-testid={`insight-${i.id}`}>
              <div className="flex items-start gap-3">
                <div className="w-9 h-9 rounded-lg bg-amber-50 flex items-center justify-center shrink-0">
                  <Icon className="text-amber-600" size={16} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-zinc-900 dark:text-zinc-100 text-sm">{i.title}</p>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400 dark:text-zinc-500 mt-1 leading-relaxed">{i.body}</p>
                  {i.predicted_revenue_uplift_gbp > 0 && (
                    <p className="text-[11px] text-emerald-700 mt-2 font-semibold">{t('mkt.ins_uplift', '+£{{n}} potential uplift', { n: i.predicted_revenue_uplift_gbp.toLocaleString() })}</p>
                  )}
                  <button
                    onClick={() => setTab(i.cta?.action === 'start_journey' ? 'journeys' : 'campaigns')}
                    className="mt-3 inline-flex items-center gap-1 text-[11px] font-semibold text-[var(--color-brand-blue)] hover:underline"
                    data-testid={`insight-cta-${i.id}`}
                  >
                    {i.cta?.label || t('mkt.ins_take_action', 'Take action')} <ChevronRight size={12} />
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default InsightsTab;
