/* Onboarding Funnel Strip — Master Admin Overview */
import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/App';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Clipboard, Clock, CheckCircle2, AlertCircle, ArrowRight, Timer, Users
} from 'lucide-react';

const fmtHours = (h) => {
  if (!h) return '—';
  if (h < 24) return `${h.toFixed(1)}h`;
  return `${(h / 24).toFixed(1)}d`;
};

export default function OnboardingFunnelStrip({ onOpen }) {
  const { API } = useAuth();
  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/onboarding-packets/analytics/summary`, { headers });
      setData(res.data);
    } catch (e) {
      // silently fail — strip just hides
      setData(null);
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — effect either runs once on mount or re-fires on the listed trigger deps; omitted refs are stable identities or fetcher closures that read live state at call time, so including them would re-fire without changing semantics.
  }, [API]);

  useEffect(() => { load(); }, [load]);

  if (loading || !data || data.total === 0) return null;

  const funnel = [
    { key: 'draft', label: 'Draft', value: data.draft || 0, icon: Clipboard, tone: 'bg-zinc-100 text-zinc-600 border-zinc-200' },
    { key: 'submitted', label: 'Awaiting Review', value: data.submitted || 0, icon: Clock, tone: 'bg-amber-50 text-amber-700 border-amber-200' },
    { key: 'provisioned', label: 'Provisioned', value: data.provisioned || 0, icon: CheckCircle2, tone: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  ];

  const oldest = data.oldest_unprovisioned;
  const hasAlert = oldest && oldest.age_hours > 72; // 3+ days

  return (
    <Card className="bg-white border-zinc-200 shadow-sm p-5 lg:p-5" data-testid="onboarding-funnel-strip">
      <div className="flex items-start justify-between gap-3 mb-3 flex-wrap">
        <div>
          <h3 className="text-base font-medium text-zinc-900 flex items-center gap-2">
            <Users size={16} className="text-blue-600" />
            Customer Onboarding Funnel
          </h3>
          <p className="text-xs text-zinc-500 mt-0.5">
            {data.created_7d || 0} new in last 7 days · {data.provisioned_7d || 0} provisioned · avg review: {fmtHours(data.avg_review_hours)}
          </p>
        </div>
        <Button size="sm" variant="outline" onClick={onOpen} data-testid="funnel-open-packets">
          Manage packets <ArrowRight size={12} className="ml-1" />
        </Button>
      </div>

      {/* 3-stage funnel + avg time */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2 lg:gap-3">
        {funnel.map(f => {
          const Icon = f.icon;
          return (
            <div key={f.key} className={`border rounded-lg p-3 ${f.tone}`} data-testid={`funnel-${f.key}`}>
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-semibold uppercase tracking-wider opacity-75">{f.label}</span>
                <Icon size={13} className="opacity-60" />
              </div>
              <p className="mt-1 text-2xl font-bold tabular-nums">{f.value}</p>
            </div>
          );
        })}
        <div className="border rounded-lg p-3 bg-blue-50 text-blue-800 border-blue-200" data-testid="funnel-avg-time">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-semibold uppercase tracking-wider opacity-75">Avg time to provision</span>
            <Timer size={13} className="opacity-60" />
          </div>
          <p className="mt-1 text-2xl font-bold tabular-nums">{fmtHours(data.avg_provision_hours)}</p>
        </div>
      </div>

      {/* Stale packet alert */}
      {hasAlert && (
        <div className="mt-3 bg-red-50 border border-red-200 rounded-lg p-3 flex items-start gap-2" data-testid="funnel-stale-alert">
          <AlertCircle size={16} className="text-red-600 flex-shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-red-800 truncate">
              Oldest unprovisioned: <strong>{oldest.customer_display_name || 'Untitled'}</strong>
            </p>
            <p className="text-xs text-red-700 mt-0.5">
              Status <Badge className="bg-white text-red-700 border border-red-200">{oldest.status}</Badge>
              · {fmtHours(oldest.age_hours)} old
            </p>
          </div>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              if (oldest?.id) {
                window.dispatchEvent(new CustomEvent('onboarding-focus-packet', { detail: { packet_id: oldest.id } }));
              }
              onOpen?.();
            }}
            className="border-red-300 text-red-700 hover:bg-red-100"
            data-testid="funnel-review-now"
          >
            Review now
          </Button>
        </div>
      )}
    </Card>
  );
}
