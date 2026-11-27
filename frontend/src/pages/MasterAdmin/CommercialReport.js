import { useEffect, useState } from 'react';
import axios from 'axios';
import { Loader2, TrendingUp } from 'lucide-react';
import { Card } from '@/components/ui/card';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const gbp = (n) => `£${Number(n || 0).toLocaleString('en-GB', { maximumFractionDigits: 0 })}`;
const EVENT = {
  upgraded_lite_to_pro: 'LITE → PRO upgrade', purchased: 'Product bought', reactivated: 'Re-subscribed',
  cancellation_scheduled: 'Cancellation scheduled', cancellation_withdrawn: 'Cancellation withdrawn', ended: 'Product ended',
};

const Stat = ({ label, value, testId }) => (
  <div className="rounded-xl border border-zinc-200 bg-white px-4 py-3" data-testid={testId}>
    <p className="text-[11px] text-zinc-500">{label}</p><p className="text-2xl font-bold tabular-nums">{value}</p>
  </div>
);

const Products = ({ rows }) => (
  <Card className="rounded-xl border-zinc-200 overflow-auto">
    <table className="w-full text-xs" data-testid="commercial-products">
      <thead className="bg-zinc-50 text-left text-zinc-500"><tr>{['Product', 'Paying', 'Annual', 'Cancelling', 'Trials', 'Included by Pulse', 'Ended', 'MRR'].map((h) => <th key={h} className="p-2">{h}</th>)}</tr></thead>
      <tbody>{rows.map((p) => (
        <tr key={p.module} className="border-t" data-testid={`commercial-row-${p.module}`}>
          <td className="p-2 font-medium">{p.name}</td><td className="p-2">{p.paying}</td><td className="p-2">{p.annual}</td><td className="p-2">{p.cancelling}</td>
          <td className="p-2">{p.trials}</td><td className="p-2">{p.included_by_pulse}</td><td className="p-2">{p.ended}</td><td className="p-2 font-semibold">{gbp(p.mrr)}</td>
        </tr>))}</tbody>
    </table>
  </Card>
);

export default function CommercialReport() {
  const [d, setD] = useState(null);
  const [err, setErr] = useState('');
  useEffect(() => {
    axios.get(`${API}/master-admin/commercial/summary`, { headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } })
      .then((r) => setD(r.data)).catch((e) => setErr(e.response?.data?.detail || 'Could not load the report'));
  }, []);
  if (err) return <p className="text-sm text-red-600" data-testid="commercial-error">{String(err)}</p>;
  if (!d) return <p className="text-sm text-zinc-500 flex gap-2"><Loader2 className="animate-spin" size={14} />Loading…</p>;
  const l30 = d.last_30_days;
  return (
    <div className="space-y-4" data-testid="commercial-report">
      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-6 gap-2">
        <Stat label="Monthly recurring revenue" value={gbp(d.mrr)} testId="commercial-mrr" />
        <Stat label="LITE customers" value={d.accounts.lite} testId="commercial-lite" />
        <Stat label="PRO customers" value={d.accounts.pro} testId="commercial-pro" />
        <Stat label="Awaiting activation" value={d.accounts.awaiting_activation} testId="commercial-awaiting" />
        <Stat label="Owner invited" value={d.accounts.owner_invited} testId="commercial-invited" />
        <Stat label="Activated by invitation" value={d.accounts.activated_by_invitation} testId="commercial-activated" />
      </div>
      <Products rows={d.products} />
      <Card className="p-4 rounded-xl border-zinc-200">
        <p className="text-sm font-semibold flex items-center gap-2 mb-2"><TrendingUp size={15} />Last 30 days</p>
        <div className="grid grid-cols-2 md:grid-cols-6 gap-2 text-xs" data-testid="commercial-30d">
          {Object.entries(l30).map(([k, v]) => <div key={k}><p className="text-zinc-500">{k.replace(/_/g, ' ')}</p><p className="text-lg font-bold">{v}</p></div>)}
        </div>
      </Card>
      <Card className="rounded-xl border-zinc-200 overflow-auto">
        <table className="w-full text-xs" data-testid="commercial-events">
          <thead className="bg-zinc-50 text-left text-zinc-500"><tr><th className="p-2">When</th><th className="p-2">Customer</th><th className="p-2">Product</th><th className="p-2">Event</th></tr></thead>
          <tbody>{d.recent_events.map((e) => (
            <tr key={e.id} className="border-t"><td className="p-2">{e.at.slice(0, 16).replace('T', ' ')}</td><td className="p-2">{e.organization_name || e.organization_id}</td><td className="p-2">{e.module}</td><td className="p-2">{EVENT[e.event] || e.event}</td></tr>
          ))}</tbody>
        </table>
        {!d.recent_events.length && <p className="p-3 text-xs text-zinc-500">No product changes recorded yet.</p>}
      </Card>
      <p className="text-[11px] text-zinc-500">{d.note}</p>
    </div>
  );
}
