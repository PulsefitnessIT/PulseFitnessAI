import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Users, Building2, Clock, Archive, ScrollText, CreditCard, Loader2 } from 'lucide-react';
import { authConfig } from './authConfig';
import DeskPerformance from './DeskPerformance';

/** Iter 258b — subscription status card for provider dashboards:
 *  trial → upgrade CTA; active → plan + renewal + Stripe billing portal. */
function SubscriptionCard({ API }) {
  const navigate = useNavigate();
  const [sub, setSub] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    axios.get(`${API}/service-provider/subscription`, authConfig())
      .then((r) => setSub(r.data)).catch(() => {});
  }, [API]);

  const managePortal = async () => {
    setBusy(true);
    try {
      const { data } = await axios.post(`${API}/service-provider/billing-portal`,
        { origin_url: window.location.origin }, authConfig());
      window.location.href = data.url;
    } catch { setBusy(false); }
  };

  if (!sub) return null;
  const isTrial = sub.status === 'trial';
  return (
    <Card className={`p-5 ${isTrial ? 'border-amber-200 bg-gradient-to-br from-amber-50 to-orange-50 dark:from-amber-950/30 dark:to-orange-950/30 dark:border-amber-900/40' : 'border-emerald-200 bg-gradient-to-br from-emerald-50 to-teal-50 dark:from-emerald-950/30 dark:to-teal-950/30 dark:border-emerald-900/40'}`} data-testid="desk-subscription-card">
      <div className="flex items-center gap-2 mb-2">
        <CreditCard className={`w-4 h-4 ${isTrial ? 'text-amber-600' : 'text-emerald-600'}`} />
        <div className="text-sm font-medium text-zinc-900 dark:text-zinc-100">Subscription</div>
        <span className={`ml-auto text-[10px] font-black uppercase tracking-wider px-2 py-0.5 rounded-full ${isTrial ? 'bg-amber-100 text-amber-700' : 'bg-emerald-100 text-emerald-700'}`} data-testid="desk-subscription-badge">
          {isTrial ? 'Trial' : 'Pro'}
        </span>
      </div>
      <div className="text-lg font-bold text-zinc-900 dark:text-zinc-100" data-testid="desk-subscription-plan">{sub.plan_name}</div>
      <div className="text-xs text-zinc-500 mt-0.5">
        {isTrial
          ? `${sub.days_left ?? '—'} day${sub.days_left === 1 ? '' : 's'} left · ${sub.price_display}`
          : `${sub.price_display}${sub.renewal_at ? ` · renews ${sub.renewal_at.slice(0, 10)}` : ''}`}
      </div>
      <div className="mt-3">
        {isTrial ? (
          <Button size="sm" onClick={() => navigate('/service-desk/upgrade')}
            className="bg-orange-600 hover:bg-orange-700 text-white" data-testid="desk-subscription-upgrade">
            Upgrade to Pro
          </Button>
        ) : sub.can_manage ? (
          <Button size="sm" variant="outline" onClick={managePortal} disabled={busy}
            className="border-emerald-300 text-emerald-700 hover:bg-emerald-100" data-testid="desk-subscription-manage">
            {busy ? <Loader2 size={13} className="animate-spin" /> : 'Manage billing'}
          </Button>
        ) : null}
      </div>
    </Card>
  );
}

export default function DeskSummary({ API, onNavigate }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const run = async () => {
      try {
        const r = await axios.get(`${API}/service-desk/summary`, authConfig());
        setData(r.data);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    run();
  }, [API]);

  if (loading) return <div className="text-zinc-500">Loading…</div>;
  if (!data) return <div className="text-red-500">Failed to load summary</div>;

  const { organizations, recent_actions_7d } = data;
  // Iter 253 — self-serve providers see their OWN desk's numbers, not the
  // platform customer-org estate (and none of the Pulse-specific copy).
  const isProvider = data.desk_kind === 'provider';
  // Iter 262 — every stat card navigates to the tab holding its detail.
  const stats = isProvider
    ? [
        { label: 'Open Cases', value: data.provider.open_cases, icon: Clock, colour: 'bg-orange-50 text-orange-700', goto: 'cases', nav: { status: 'open' } },
        { label: 'Total Cases', value: data.provider.total_cases, icon: ScrollText, colour: 'bg-zinc-100 text-zinc-600 dark:bg-zinc-800', goto: 'cases', nav: { status: '' } },
        { label: 'Engineers', value: data.provider.engineers, icon: Users, colour: 'bg-emerald-50 text-emerald-700', goto: 'engineers' },
        { label: 'Customers', value: data.provider.customers, icon: Building2, colour: 'bg-cyan-50 text-cyan-700', goto: 'customers' },
      ]
    : [
        { label: 'Total Customers', value: organizations.total, icon: Building2, colour: 'bg-orange-50 text-orange-700', goto: 'customers', status: '' },
        { label: 'Active', value: organizations.active, icon: Users, colour: 'bg-emerald-50 text-emerald-700', goto: 'customers', status: 'active' },
        { label: 'Pending Invite', value: organizations.pending_invite, icon: Clock, colour: 'bg-amber-50 text-amber-700', goto: 'customers', status: 'pending_invite' },
        { label: 'Archived', value: organizations.archived, icon: Archive, colour: 'bg-zinc-100 text-zinc-600 dark:bg-zinc-800', goto: 'customers', status: 'archived' },
      ];

  return (
    <div className="space-y-6" data-testid="desk-summary">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">Service Desk</h1>
        <p className="text-sm text-zinc-500 mt-1">
          {isProvider
            ? 'Cases, engineers and customers for your service operation.'
            : 'Customer operations, imports, and staff management for Pulse Fitness.'}
        </p>
      </div>

      {/* Iter 262 — 2-up on mobile, 4-up on desktop; every card is a
          button that jumps to the tab holding the underlying records. */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        {stats.map(({ label, value, icon: Icon, colour, goto, status, nav }) => (
          <Card
            key={label}
            role="button"
            tabIndex={0}
            onClick={() => onNavigate && onNavigate(goto, nav ?? status)}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onNavigate && onNavigate(goto, nav ?? status); } }}
            className="p-4 sm:p-5 cursor-pointer transition-all hover:shadow-md hover:border-orange-200 active:scale-[0.98]"
            data-testid={`desk-stat-${label.toLowerCase().replace(/\s+/g, '-')}`}
          >
            <div className={`w-8 h-8 rounded ${colour} flex items-center justify-center mb-3`}>
              <Icon className="w-4 h-4" />
            </div>
            <div className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">{value.toLocaleString()}</div>
            <div className="text-xs text-zinc-500 mt-1">{label}</div>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
        {isProvider && <SubscriptionCard API={API} />}
        <Card
          className="p-5 cursor-pointer transition-all hover:shadow-md hover:border-orange-200 active:scale-[0.99]"
          role="button"
          tabIndex={0}
          onClick={() => onNavigate && onNavigate('audit')}
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onNavigate && onNavigate('audit'); } }}
          data-testid="desk-stat-recent-activity"
        >
          <div className="flex items-center gap-2 mb-3">
            <ScrollText className="w-4 h-4 text-zinc-500" />
            <div className="text-sm font-medium text-zinc-900 dark:text-zinc-100">Recent Activity</div>
          </div>
          <div className="text-3xl font-semibold text-zinc-900 dark:text-zinc-100">{recent_actions_7d}</div>
          <div className="text-xs text-zinc-500 mt-1">Service Desk actions in the last 7 days · tap to open the audit log</div>
        </Card>
      </div>

      {/* Iter 290 — team-performance KPIs (FTF/RTF, SLA health, leaderboard) */}
      <DeskPerformance API={API} onNavigate={onNavigate} />
    </div>
  );
}
