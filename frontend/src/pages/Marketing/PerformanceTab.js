/* Performance — KPI dashboard */
import { useEffect, useState } from 'react';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import { Mail, MousePointerClick, Users, Workflow, TrendingUp, Loader2 } from 'lucide-react';

const Tile = ({ icon: Icon, label, value, sub, accent = 'text-zinc-900 dark:text-zinc-100' }) => (
  <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-4">
    <div className="flex items-center gap-2 text-zinc-400 dark:text-zinc-500 text-[10px] uppercase tracking-wider font-semibold">
      <Icon size={12} /> {label}
    </div>
    <p className={`text-2xl font-bold mt-1 ${accent}`}>{value}</p>
    {sub && <p className="text-[11px] text-zinc-400 dark:text-zinc-500 mt-1">{sub}</p>}
  </div>
);

const PerformanceTab = ({ API, headers }) => {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  useEffect(() => {
    axios.get(`${API}/api/marketing/dashboard/v2`, { headers })
      .then((r) => setData(r.data))
      .catch(() => axios.get(`${API}/api/marketing/dashboard`, { headers }).then((r) => setData(r.data)).catch(() => setData({})));
    // eslint-disable-next-line
  }, []);
  if (!data) return <div className="flex items-center gap-2 text-zinc-400 dark:text-zinc-500 py-8"><Loader2 className="animate-spin" size={14} /> {t('mkt.perf_loading', 'Loading…')}</div>;
  return (
    <div className="space-y-4" data-testid="marketing-performance-tab">
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <Tile icon={Mail} label={t('mkt.perf_campaigns_sent', 'Campaigns sent (30d)')} value={data.campaigns_30d || 0} />
        <Tile icon={Mail} label={t('mkt.perf_messages_sent', 'Messages sent')} value={(data.messages_sent_30d || 0).toLocaleString()} />
        <Tile icon={MousePointerClick} label={t('mkt.perf_open_rate', 'Open rate')} value={`${data.open_rate_pct || 0}%`} sub={t('mkt.perf_opens', '{{n}} opens', { n: data.opens_30d || 0 })} accent="text-emerald-700" />
        <Tile icon={MousePointerClick} label={t('mkt.perf_click_rate', 'Click rate')} value={`${data.click_rate_pct || 0}%`} sub={t('mkt.perf_clicks', '{{n}} clicks', { n: data.clicks_30d || 0 })} accent="text-blue-700" />
        <Tile icon={Users} label={t('mkt.perf_audiences_saved', 'Audiences saved')} value={data.audiences_total || 0} />
        <Tile icon={Workflow} label={t('mkt.perf_active_journeys', 'Active journeys')} value={data.journeys_active || 0} />
        <Tile icon={TrendingUp} label={t('mkt.perf_conversions', 'Conversions (30d)')} value={data.conversions_30d || 0} accent="text-violet-700" />
        <Tile icon={TrendingUp} label={t('mkt.perf_attributed_revenue', 'Attributed revenue')} value={`£${(data.revenue_attributed_gbp || 0).toLocaleString()}`} sub={t('mkt.perf_attribution_window', '7-day click-to-conversion window')} accent="text-emerald-700" />
      </div>
    </div>
  );
};

export default PerformanceTab;
