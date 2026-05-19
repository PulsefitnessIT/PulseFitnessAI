import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

const STATUS_STYLES = {
  active: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  trial: 'bg-blue-50 text-blue-700 border-blue-200',
  suspended: 'bg-amber-50 text-amber-700 border-amber-200',
  cancelled: 'bg-red-50 text-red-700 border-red-200',
};

const TIER_STYLES = {
  free: 'bg-zinc-100 text-zinc-600',
  pro: 'bg-blue-50 text-blue-700',
  premium: 'bg-amber-50 text-amber-700',
  enterprise: 'bg-violet-50 text-violet-700',
};

const AdminPayments = ({ stats, organizations }) => {
  if (!stats) return null;
  const paymentOrgs = organizations.filter(o => o.subscription_tier && o.subscription_tier !== 'free');
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-4">
        <Card className="bg-white border-zinc-200 shadow-sm p-5">
          <p className="text-xs font-bold uppercase tracking-wider text-zinc-400">Monthly Revenue</p>
          <p className="text-3xl font-semibold text-zinc-900 mt-1">£{stats.mrr.toLocaleString()}</p>
        </Card>
        <Card className="bg-white border-zinc-200 shadow-sm p-5">
          <p className="text-xs font-bold uppercase tracking-wider text-zinc-400">Total Payments</p>
          <p className="text-3xl font-semibold text-zinc-900 mt-1">{stats.payments.total}</p>
        </Card>
        <Card className="bg-white border-zinc-200 shadow-sm p-5">
          <p className="text-xs font-bold uppercase tracking-wider text-zinc-400">Failed Payments</p>
          <p className="text-3xl font-semibold text-red-600 mt-1">{stats.payments.failed}</p>
        </Card>
      </div>

      <Card className="bg-white border-zinc-200 shadow-sm overflow-hidden">
        <div className="p-4 border-b border-zinc-100">
          <h3 className="font-medium text-zinc-900">Paying Organisations</h3>
        </div>
        <div className="overflow-x-auto">
        <table className="w-full text-sm min-w-[640px]">
          <thead>
            <tr className="border-b border-zinc-100 bg-zinc-50">
              <th className="text-left p-3 text-xs font-bold uppercase tracking-wider text-zinc-400">Organisation</th>
              <th className="text-left p-3 text-xs font-bold uppercase tracking-wider text-zinc-400">Plan</th>
              <th className="text-left p-3 text-xs font-bold uppercase tracking-wider text-zinc-400">Status</th>
              <th className="text-center p-3 text-xs font-bold uppercase tracking-wider text-zinc-400">Users</th>
              <th className="text-right p-3 text-xs font-bold uppercase tracking-wider text-zinc-400">Est. Monthly</th>
            </tr>
          </thead>
          <tbody>
            {paymentOrgs.map(org => {
              const prices = { pro: 49, premium: 99, enterprise: 199 };
              return (
                <tr key={org.id} className="border-b border-zinc-50 hover:bg-zinc-50">
                  <td className="p-3 font-medium text-zinc-900">{org.name}</td>
                  <td className="p-3"><Badge className={TIER_STYLES[org.subscription_tier]}>{org.subscription_tier}</Badge></td>
                  <td className="p-3"><Badge className={STATUS_STYLES[org.status || 'active']}>{org.status || 'active'}</Badge></td>
                  <td className="p-3 text-center text-zinc-900">{org.user_count}</td>
                  <td className="p-3 text-right font-medium text-zinc-900">£{prices[org.subscription_tier] || 0}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        </div>
        {paymentOrgs.length === 0 && <p className="text-center text-zinc-400 py-12 text-sm">No paying customers yet</p>}
      </Card>
    </div>
  );
};

export default AdminPayments;
