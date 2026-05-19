import { useEffect, useState } from 'react';
import axios from 'axios';
import { useAuth } from '@/App';
import { TrendingUp, TrendingDown, MessageSquareHeart } from 'lucide-react';

/**
 * AdminNpsPanel (iter 215c0)
 * Master-admin roll-up of in-app NPS responses.
 */
const AdminNpsPanel = () => {
  const { API } = useAuth();
  const [data, setData] = useState(null);
  const [days, setDays] = useState(90);

  useEffect(() => {
    const run = async () => {
      const token = localStorage.getItem('token');
      try {
        const res = await axios.get(`${API}/feedback/master-admin/nps`, {
          headers: { Authorization: `Bearer ${token}` },
          params: { days },
        });
        setData(res.data);
      } catch { setData(null); }
    };
    run();
  }, [API, days]);

  if (!data) return <div className="text-sm text-[var(--color-text-muted)]" data-testid="admin-nps-loading">Loading NPS…</div>;
  const npsColor = data.nps >= 50 ? 'text-emerald-600' : data.nps >= 0 ? 'text-amber-600' : 'text-red-600';
  const TrendIcon = data.nps >= 0 ? TrendingUp : TrendingDown;

  return (
    <div className="rounded-2xl bg-[var(--theme-surface)] border border-[var(--theme-border)] p-6 shadow-sm" data-testid="admin-nps-panel">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-[var(--color-brand-blue)]/10 flex items-center justify-center">
            <MessageSquareHeart className="w-5 h-5 text-[var(--color-brand-blue)]" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-[var(--theme-text)]">In-app NPS</h2>
            <p className="text-xs text-[var(--color-text-muted)]">Net Promoter Score across the last {data.window_days} days.</p>
          </div>
        </div>
        <select
          value={days}
          onChange={(e) => setDays(parseInt(e.target.value, 10))}
          data-testid="admin-nps-window"
          className="text-sm rounded-md border border-[var(--theme-border)] bg-[var(--theme-surface)] px-2 py-1"
        >
          <option value={30}>30 days</option>
          <option value={90}>90 days</option>
          <option value={180}>6 months</option>
          <option value={365}>12 months</option>
        </select>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-5">
        <Stat label="NPS" value={`${data.nps}`} accent={`${npsColor}`} icon={<TrendIcon className="w-3.5 h-3.5" />} testId="admin-nps-score" />
        <Stat label="Responses" value={`${data.total_responses}`} testId="admin-nps-total" />
        <Stat label="Promoters" value={`${data.promoters}`} accent="text-emerald-600" testId="admin-nps-promoters" />
        <Stat label="Passives" value={`${data.passives}`} accent="text-amber-600" testId="admin-nps-passives" />
        <Stat label="Detractors" value={`${data.detractors}`} accent="text-red-600" testId="admin-nps-detractors" />
      </div>

      <div className="mb-5">
        <p className="text-xs font-semibold text-[var(--theme-text)] mb-2">Score distribution</p>
        <div className="grid grid-cols-11 gap-1">
          {Object.entries(data.distribution || {}).sort((a, b) => parseInt(a[0]) - parseInt(b[0])).map(([score, count]) => {
            const max = Math.max(1, ...Object.values(data.distribution));
            const pct = (count / max) * 100;
            const tone = parseInt(score) >= 9 ? 'bg-emerald-500' : parseInt(score) >= 7 ? 'bg-amber-500' : 'bg-red-500';
            return (
              <div key={score} className="flex flex-col items-center" data-testid={`admin-nps-bar-${score}`}>
                <div className="w-full h-16 flex items-end">
                  <div className={`w-full rounded-t ${tone}`} style={{ height: `${pct}%` }} />
                </div>
                <span className="text-[10px] text-[var(--color-text-muted)] mt-1">{score}</span>
                <span className="text-[10px] font-medium text-[var(--theme-text)]">{count}</span>
              </div>
            );
          })}
        </div>
      </div>

      {data.verbatim?.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-[var(--theme-text)] mb-2">Recent comments</p>
          <ul className="space-y-2 max-h-72 overflow-y-auto" data-testid="admin-nps-verbatim">
            {data.verbatim.slice(0, 10).map((v, i) => (
              <li key={i} className="text-xs border border-[var(--theme-border)] rounded-md p-2">
                <div className="flex items-center justify-between">
                  <span className={`px-1.5 py-0.5 rounded text-white text-[10px] ${v.score >= 9 ? 'bg-emerald-500' : v.score >= 7 ? 'bg-amber-500' : 'bg-red-500'}`}>
                    {v.score}
                  </span>
                  <span className="text-[var(--color-text-muted)]">{v.user_email}</span>
                </div>
                <p className="text-[var(--theme-text)] mt-1">{v.comment}</p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

const Stat = ({ label, value, accent = 'text-[var(--theme-text)]', icon, testId }) => (
  <div className="rounded-lg border border-[var(--theme-border)] p-3" data-testid={testId}>
    <p className="text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">{label}</p>
    <p className={`text-xl font-bold tabular-nums flex items-center gap-1 ${accent}`}>
      {value}{icon}
    </p>
  </div>
);

export default AdminNpsPanel;
