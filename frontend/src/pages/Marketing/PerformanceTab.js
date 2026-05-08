/* Performance — KPI dashboard */
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { BarChart3, Mail, MousePointerClick, Users, Workflow, TrendingUp, Loader2 } from 'lucide-react';

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
  const [data, setData] = useState(null);
  useEffect(() => {
    axios.get(`${API}/api/marketing/dashboard/v2`, { headers })
      .then((r) => setData(r.data))
      .catch(() => axios.get(`${API}/api/marketing/dashboard`, { headers }).then((r) => setData(r.data)).catch(() => setData({})));
    // eslint-disable-next-line
  }, []);
  if (!data) return <div className="flex items-center gap-2 text-zinc-400 dark:text-zinc-500 py-8"><Loader2 className="animate-spin" size={14} /> Loading…</div>;
  return (
    <div className="space-y-4" data-testid="marketing-performance-tab">
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <Tile icon={Mail} label="Campaigns sent (30d)" value={data.campaigns_30d || 0} />
        <Tile icon={Mail} label="Messages sent" value={(data.messages_sent_30d || 0).toLocaleString()} />
        <Tile icon={MousePointerClick} label="Open rate" value={`${data.open_rate_pct || 0}%`} sub={`${data.opens_30d || 0} opens`} accent="text-emerald-700" />
        <Tile icon={MousePointerClick} label="Click rate" value={`${data.click_rate_pct || 0}%`} sub={`${data.clicks_30d || 0} clicks`} accent="text-blue-700" />
        <Tile icon={Users} label="Audiences saved" value={data.audiences_total || 0} />
        <Tile icon={Workflow} label="Active journeys" value={data.journeys_active || 0} />
        <Tile icon={TrendingUp} label="Conversions (30d)" value={data.conversions_30d || 0} accent="text-violet-700" />
        <Tile icon={TrendingUp} label="Attributed revenue" value={`£${(data.revenue_attributed_gbp || 0).toLocaleString()}`} sub="7-day click-to-conversion window" accent="text-emerald-700" />
      </div>
    </div>
  );
};

export default PerformanceTab;
