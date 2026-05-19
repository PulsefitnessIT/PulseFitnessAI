/**
 * SignupsFunnelTab — Master Admin · Memberships · Online Sign-ups.
 *
 * Funnel (views → drafts → completed → paid + revenue), per-org breakdown,
 * and the most recent 25 sign-ups. Backed by /master-admin/signups/funnel.
 */
import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  RefreshCw, Eye, FileText, Check, PoundSterling, AlertTriangle,
  TrendingUp, Activity, Users,
} from 'lucide-react';
import { notify } from '@/components/notifications';

const fmtMoney = (pence) => `£${(Number(pence || 0) / 100).toFixed(2)}`;

const Stat = ({ label, value, hint, Icon, color = 'text-zinc-700', bg = 'bg-zinc-50', testid }) => (
  <Card className="p-4 border-zinc-200" data-testid={testid}>
    <div className="flex items-start justify-between mb-2">
      <p className="text-[11px] uppercase tracking-wide text-zinc-500 font-semibold">{label}</p>
      {Icon && <div className={`h-8 w-8 ${bg} rounded-md flex items-center justify-center ${color}`}><Icon size={14} /></div>}
    </div>
    <p className="text-2xl font-bold text-zinc-900 tabular-nums">{value}</p>
    {hint && <p className="text-[11px] text-zinc-500 mt-0.5">{hint}</p>}
  </Card>
);

const SignupsFunnelTab = () => {
  const { API } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(30);

  const headers = () => ({ Authorization: `Bearer ${localStorage.getItem('token')}` });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/master-admin/signups/funnel?days=${days}`, { headers: headers() });
      setData(r.data);
    } catch (e) {
      notify.error('Could not load funnel', e.response?.data?.detail);
    }
    setLoading(false);
  }, [API, days]);

  useEffect(() => { load(); }, [load]);

  const k = data?.kpis || {};

  return (
    <div className="space-y-4" data-testid="signups-funnel-tab">
      <Card className="p-4 border-zinc-200">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <h4 className="text-sm font-semibold text-zinc-900 flex items-center gap-2">
              <Activity size={15} className="text-blue-600" /> Online sign-ups · last {days} days
            </h4>
            <p className="text-[11px] text-zinc-500 mt-0.5">
              Funnel view across every gym using the public sign-up page.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1 p-1 bg-zinc-100 rounded-md">
              {[7, 30, 90].map((d) => (
                <button
                  key={d}
                  onClick={() => setDays(d)}
                  className={`px-3 py-1 text-xs rounded-sm font-medium ${days === d ? 'bg-white text-zinc-900 shadow-sm' : 'text-zinc-500 hover:text-zinc-800'}`}
                  data-testid={`funnel-range-${d}`}
                >
                  {d}d
                </button>
              ))}
            </div>
            <Button size="sm" variant="outline" onClick={load} disabled={loading} data-testid="funnel-refresh">
              <RefreshCw size={11} className={`mr-1 ${loading ? 'animate-spin' : ''}`} /> Refresh
            </Button>
          </div>
        </div>
      </Card>

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <Stat label="Page views" value={(k.views ?? 0).toLocaleString()} Icon={Eye} color="text-zinc-600" bg="bg-zinc-100" testid="funnel-stat-views" />
        <Stat label="Drafts started" value={(k.drafts_started ?? 0).toLocaleString()} hint={`${k.view_to_draft_pct ?? 0}% of views`} Icon={FileText} color="text-amber-600" bg="bg-amber-50" testid="funnel-stat-drafts" />
        <Stat label="Drafts completed" value={(k.drafts_completed ?? 0).toLocaleString()} Icon={Check} color="text-emerald-600" bg="bg-emerald-50" testid="funnel-stat-completed" />
        <Stat label="Paid sign-ups" value={(k.paid ?? 0).toLocaleString()} hint={`${k.draft_to_paid_pct ?? 0}% of drafts`} Icon={Users} color="text-blue-600" bg="bg-blue-50" testid="funnel-stat-paid" />
        <Stat label="Revenue" value={fmtMoney(k.revenue_pence ?? 0)} Icon={PoundSterling} color="text-violet-600" bg="bg-violet-50" testid="funnel-stat-revenue" />
      </div>

      {/* Funnel bar */}
      <Card className="p-4 border-zinc-200">
        <p className="text-xs uppercase tracking-wide text-zinc-500 font-semibold mb-3 flex items-center gap-2">
          <TrendingUp size={12} /> Conversion funnel
        </p>
        {(k.views ?? 0) > 0 ? (
          <div className="space-y-1.5" data-testid="funnel-bars">
            {[
              { label: 'Page views', count: k.views, color: 'bg-zinc-300' },
              { label: 'Started sign-up', count: k.drafts_started, color: 'bg-amber-400' },
              { label: 'Completed form', count: k.drafts_completed, color: 'bg-emerald-400' },
              { label: 'Paid (became member)', count: k.paid, color: 'bg-blue-500' },
            ].map((row) => {
              const pct = k.views ? Math.max(2, Math.round((row.count / k.views) * 100)) : 0;
              return (
                <div key={row.label} className="flex items-center gap-2 text-xs">
                  <span className="w-44 text-zinc-600">{row.label}</span>
                  <div className="flex-1 h-6 bg-zinc-100 rounded">
                    <div className={`h-full ${row.color} rounded transition-all`} style={{ width: `${pct}%` }} />
                  </div>
                  <span className="w-12 text-right tabular-nums font-semibold">{(row.count ?? 0).toLocaleString()}</span>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="text-sm text-zinc-400 py-4">No traffic yet. Once members visit /m/&lt;slug&gt;/join the funnel populates in real time.</p>
        )}
      </Card>

      {/* Per-org */}
      {data?.by_org?.length > 0 && (
        <Card className="p-4 border-zinc-200" data-testid="funnel-by-org">
          <p className="text-xs uppercase tracking-wide text-zinc-500 font-semibold mb-3">
            Sign-ups by gym
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[11px] uppercase tracking-wider text-zinc-400 border-b border-zinc-100">
                  <th className="text-left py-2">Gym</th>
                  <th className="text-right py-2">New members</th>
                </tr>
              </thead>
              <tbody>
                {data.by_org.map((o) => (
                  <tr key={o.organization_id} className="border-b border-zinc-50">
                    <td className="py-2 font-medium">{o.name}</td>
                    <td className="py-2 text-right tabular-nums">{o.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Recent */}
      <Card className="p-4 border-zinc-200" data-testid="funnel-recent">
        <p className="text-xs uppercase tracking-wide text-zinc-500 font-semibold mb-3 flex items-center gap-2">
          <Users size={12} /> Most recent sign-ups
        </p>
        {(data?.recent || []).length === 0 ? (
          <p className="text-sm text-zinc-400 py-4">No completed sign-ups in this window.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[11px] uppercase tracking-wider text-zinc-400 border-b border-zinc-100">
                  <th className="text-left py-2">Member</th>
                  <th className="text-left py-2">Email</th>
                  <th className="text-left py-2">Joined</th>
                  <th className="text-left py-2">Flags</th>
                </tr>
              </thead>
              <tbody>
                {data.recent.map((m) => (
                  <tr key={m.id} className="border-b border-zinc-50" data-testid={`funnel-recent-row-${m.id}`}>
                    <td className="py-2 font-medium">{m.name || '—'}</td>
                    <td className="py-2 text-zinc-600">{m.email}</td>
                    <td className="py-2 text-zinc-500 text-xs">{m.joined_at?.slice(0, 10) || '—'}</td>
                    <td className="py-2">
                      {m.parq_clearance_required && (
                        <Badge className="bg-amber-100 text-amber-800 border border-amber-200 text-[10px]">
                          <AlertTriangle size={9} className="mr-1" /> GP clearance
                        </Badge>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Journey jobs status */}
      {data?.journey_jobs && Object.keys(data.journey_jobs).length > 0 && (
        <Card className="p-4 border-zinc-200" data-testid="funnel-journey-jobs">
          <p className="text-xs uppercase tracking-wide text-zinc-500 font-semibold mb-3">
            Welcome-journey email queue
          </p>
          <div className="flex items-center gap-3 flex-wrap">
            {Object.entries(data.journey_jobs).map(([status, count]) => (
              <Badge key={status} className={`${status === 'sent' ? 'bg-emerald-100 text-emerald-800 border-emerald-200' : status === 'failed' ? 'bg-rose-100 text-rose-800 border-rose-200' : 'bg-zinc-100 text-zinc-700 border-zinc-200'} border text-[11px]`}>
                {status}: {count}
              </Badge>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
};

export default SignupsFunnelTab;
