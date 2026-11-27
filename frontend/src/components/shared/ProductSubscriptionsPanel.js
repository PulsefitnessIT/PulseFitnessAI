import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Link } from 'react-router-dom';
import { Package, Loader2 } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { formatApiError } from '@/lib/formatApiError';

// Release E — each paid product with its own status, cancel at period end, and undo.
const LABEL = {
  active: 'Active', cancelling: 'Ends at period end', trial: 'Free trial', included: 'Included in your agreement with Pulse Fitness (no card payment)',
  ended: 'Ended (data kept)', lite: 'LITE (free)', not_subscribed: 'Not subscribed',
};

const Row = ({ p, isOwner, onAction, busy }) => (
  <div className="flex flex-wrap items-center justify-between gap-2 py-2 border-t border-[var(--theme-border)]" data-testid={`product-row-${p.module}`}>
    <div>
      <p className="text-[var(--theme-text)] text-sm font-medium">{p.name}</p>
      <p className="text-xs text-[var(--color-text-muted)]" data-testid={`product-status-${p.module}`}>
        {LABEL[p.status] || p.status}{p.status === 'cancelling' && p.current_period_end ? ` · ${p.current_period_end.slice(0, 10)}` : ''}
        {p.monthly_price && ['not_subscribed', 'ended', 'lite', 'trial'].includes(p.status) ? ` · £${p.monthly_price}/mo` : ''}
      </p>
    </div>
    {isOwner && p.status === 'active' && p.has_stripe_subscription && (
      <Button size="sm" variant="outline" disabled={busy} onClick={() => onAction(p.module, 'cancel')} data-testid={`product-cancel-${p.module}`}>Cancel at period end</Button>
    )}
    {isOwner && p.status === 'cancelling' && (
      <Button size="sm" disabled={busy} onClick={() => onAction(p.module, 'reactivate')} data-testid={`product-keep-${p.module}`}>Keep it</Button>
    )}
    {isOwner && ['not_subscribed', 'ended', 'lite'].includes(p.status) && (
      <Button size="sm" asChild data-testid={`product-subscribe-${p.module}`}><Link to="/choose-plan">{p.status === 'ended' ? 'Subscribe again' : p.module === 'operations' ? 'Upgrade to PRO' : 'Add'}</Link></Button>
    )}
  </div>
);

export default function ProductSubscriptionsPanel({ API }) {
  const [d, setD] = useState(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');
  const H = { headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const load = useCallback(() => axios.get(`${API}/account/billing/modules`, H).then((r) => setD(r.data)).catch(() => setD({ products: [] })), [API]);
  useEffect(() => { load(); }, [load]);
  const onAction = async (module, what) => {
    let body = {};
    if (what === 'cancel') {
      const reason = window.prompt('Why are you cancelling? (required)');
      if (!reason || reason.trim().length < 2) return;
      body = { reason };
    }
    setBusy(true); setMsg('');
    try { const r = await axios.post(`${API}/account/billing/modules/${module}/${what}`, body, H); setMsg(r.data.message); load(); } catch (e) { { const f = formatApiError(e); setMsg(f.detail || f.title); }; }
    setBusy(false);
  };
  if (!d) return <Card className="bg-[var(--theme-surface)] border-[var(--theme-border)] p-5"><Loader2 className="animate-spin text-[var(--theme-text)]" size={16} /></Card>;
  return (
    <Card className="bg-[var(--theme-surface)] border-[var(--theme-border)] p-5" data-testid="product-subscriptions-panel">
      <h3 className="text-sm font-medium text-[var(--color-text-muted)] uppercase tracking-wider mb-2 flex items-center gap-2"><Package size={14} /> Products</h3>
      {d.products.map((p) => <Row key={p.module} p={p} isOwner={d.is_owner} onAction={onAction} busy={busy} />)}
      <p className="text-[11px] text-[var(--color-text-muted)] mt-2">Cancelling keeps the product until the end of the billing period. Your equipment, sites and history are never deleted; Operations returns to LITE.</p>
      {msg && <p className="text-xs text-[var(--color-brand-blue)] mt-2" data-testid="product-message">{msg}</p>}
    </Card>
  );
}
