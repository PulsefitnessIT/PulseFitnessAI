/* Trial Funnel Analytics Strip — Master Admin Overview */
import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/App';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
  Timer, AlertTriangle, Zap, ArrowRight,
  Clock, CheckCircle2, Target
} from 'lucide-react';

export default function TrialFunnelStrip({ onOpen }) {
  const { API } = useAuth();
  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/master-admin/trials/summary`, { headers });
      setData(res.data);
    } catch {
      setData(null);
    } finally { setLoading(false); }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — effect either runs once on mount or re-fires on the listed trigger deps; omitted refs are stable identities or fetcher closures that read live state at call time, so including them would re-fire without changing semantics.
  }, [API]);

  useEffect(() => { load(); }, [load]);

  if (loading || !data) return null;
  const totalTouched = (data.total || 0) + (data.by_status?.converted || 0);
  if (totalTouched === 0) return null;

  const active = data.by_status?.active || 0;
  const _expiringSoon = data.by_status?.expiring_soon || 0;
  const expired = data.by_status?.expired || 0;
  const converted = data.by_status?.converted || 0;
  const rate = data.conversion_rate_30d || 0;
  const expiringWeek = data.expiring_this_week || 0;
  const avgDays = data.avg_days_to_convert || 0;

  const rateColor = rate >= 60 ? 'text-emerald-600' : rate >= 30 ? 'text-amber-600' : 'text-red-600';
  const rateBar = rate >= 60 ? 'bg-emerald-500' : rate >= 30 ? 'bg-amber-500' : 'bg-red-500';

  return (
    <Card className="bg-white border-zinc-200 shadow-sm p-5 lg:p-5" data-testid="trial-funnel-strip">
      <div className="flex items-start justify-between gap-3 mb-3 flex-wrap">
        <div>
          <h3 className="text-base font-medium text-zinc-900 flex items-center gap-2">
            <Timer size={16} className="text-blue-600" />
            Trial Funnel
          </h3>
          <p className="text-xs text-zinc-500 mt-0.5">
            {data.ended_30d || 0} trials ended in last 30 days · {converted} converted · avg {avgDays > 0 ? `${avgDays}d` : '—'} to convert
          </p>
        </div>
        <Button size="sm" variant="outline" onClick={onOpen} data-testid="trial-funnel-manage">
          Manage trials <ArrowRight size={12} className="ml-1" />
        </Button>
      </div>

      {/* Funnel tiles */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-2 lg:gap-3">
        <FunnelTile icon={Clock} label="Active" value={active} tone="emerald" testid="trial-tile-active" />
        <FunnelTile icon={AlertTriangle} label="Expiring ≤7 days" value={expiringWeek} tone={expiringWeek > 0 ? 'amber' : 'zinc'} testid="trial-tile-expiring" />
        <FunnelTile icon={Zap} label="Expired" value={expired} tone={expired > 0 ? 'red' : 'zinc'} testid="trial-tile-expired" />
        <FunnelTile icon={CheckCircle2} label="Converted (30d)" value={converted} tone="blue" testid="trial-tile-converted" />
        <FunnelTile icon={Target} label="Conversion rate" value={`${rate}%`} tone="zinc" tonedValue={rateColor} testid="trial-tile-rate" />
      </div>

      {/* Conversion progress bar */}
      <div className="mt-3 flex items-center gap-3">
        <span className="text-[11px] text-zinc-500 font-medium">30-day conversion:</span>
        <div className="flex-1 h-1.5 bg-zinc-100 rounded-full overflow-hidden">
          <div className={`h-full ${rateBar} transition-all`} style={{ width: `${Math.min(100, rate)}%` }} />
        </div>
        <span className={`text-xs font-bold tabular-nums ${rateColor}`}>{converted} / {data.ended_30d || 0}</span>
      </div>

      {/* Expiring-this-week warning */}
      {expiringWeek > 0 && (
        <div className="mt-3 bg-amber-50 border border-amber-200 rounded-lg p-3 flex items-start gap-2" data-testid="trial-expiring-alert">
          <AlertTriangle size={14} className="text-amber-600 flex-shrink-0 mt-0.5" />
          <div className="flex-1 text-sm text-amber-800">
            <strong>{expiringWeek}</strong> trial{expiringWeek === 1 ? '' : 's'} expiring in the next 7 days.
          </div>
          <Button size="sm" variant="outline" onClick={onOpen} className="border-amber-300 text-amber-700 hover:bg-amber-100" data-testid="trial-review-expiring">
            Review
          </Button>
        </div>
      )}

      {/* Source split */}
      {data.by_source && (data.by_source.crm_linked > 0 || data.by_source.direct > 0) && (
        <div className="mt-3 flex items-center gap-4 text-[11px] text-zinc-500">
          <span>Sources:</span>
          <span><strong className="text-zinc-700">{data.by_source.crm_linked}</strong> from CRM</span>
          <span>·</span>
          <span><strong className="text-zinc-700">{data.by_source.direct}</strong> direct</span>
        </div>
      )}
    </Card>
  );
}

function FunnelTile({ icon: Icon, label, value, tone = 'zinc', tonedValue, testid }) {
  const tones = {
    emerald: 'bg-emerald-50 border-emerald-200 text-emerald-700',
    amber: 'bg-amber-50 border-amber-200 text-amber-700',
    red: 'bg-red-50 border-red-200 text-red-700',
    blue: 'bg-blue-50 border-blue-200 text-blue-700',
    zinc: 'bg-zinc-50 border-zinc-200 text-zinc-700',
  };
  return (
    <div className={`border rounded-lg p-3 ${tones[tone]}`} data-testid={testid}>
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-widest font-semibold opacity-80">{label}</span>
        <Icon size={13} className="opacity-60" />
      </div>
      <p className={`mt-1 text-2xl font-bold tabular-nums ${tonedValue || ''}`}>{value}</p>
    </div>
  );
}
