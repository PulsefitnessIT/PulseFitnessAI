/**
 * PaymentSetupCard — Master Admin → org drawer.
 *
 * Three states:
 *   1. Not connected         → "Connect Stripe (Express)" + "Link existing"
 *   2. Connecting / pending  → "Continue onboarding"
 *   3. Connected & ready     → status row + "Open dashboard" + "Disconnect"
 */
import React, { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { CreditCard, ExternalLink, Link2, ShieldCheck, AlertCircle, Loader2, RefreshCw, Unplug, Banknote } from 'lucide-react';
import { notify } from '@/components/notifications';

const PaymentSetupCard = ({ organizationId }) => {
  const { API } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [acctIdInput, setAcctIdInput] = useState('');

  const headers = () => ({ Authorization: `Bearer ${localStorage.getItem('token')}` });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/stripe-connect/orgs/${organizationId}/status`, { headers: headers() });
      setData(r.data);
    } catch (e) {
      notify.error('Could not load Stripe status', e.response?.data?.detail);
    }
    setLoading(false);
  }, [API, organizationId]);

  useEffect(() => { load(); }, [load]);

  const startOnboarding = async () => {
    setBusy(true);
    try {
      const r = await axios.post(
        `${API}/stripe-connect/orgs/${organizationId}/onboarding-link`,
        { country: 'GB' },
        { headers: headers() },
      );
      if (r.data?.url) {
        window.open(r.data.url, '_blank', 'noopener');
        notify.success('Onboarding link opened', 'Complete the form in the new tab. Refresh this card after you finish.');
      }
    } catch (e) {
      notify.error('Could not start onboarding', e.response?.data?.detail);
    }
    setBusy(false);
  };

  const linkExisting = async () => {
    if (!acctIdInput.trim()) {
      notify.error('Missing account id', 'Paste an acct_… id from Stripe.');
      return;
    }
    setBusy(true);
    try {
      await axios.post(
        `${API}/stripe-connect/orgs/${organizationId}/link-existing`,
        { account_id: acctIdInput.trim() },
        { headers: headers() },
      );
      notify.success('Stripe account linked', acctIdInput.trim());
      setAcctIdInput('');
      await load();
    } catch (e) {
      notify.error('Link failed', e.response?.data?.detail);
    }
    setBusy(false);
  };

  const openDashboard = async () => {
    setBusy(true);
    try {
      const r = await axios.post(`${API}/stripe-connect/orgs/${organizationId}/dashboard-link`, {}, { headers: headers() });
      if (r.data?.url) window.open(r.data.url, '_blank', 'noopener');
    } catch (e) {
      notify.error('Could not open dashboard', e.response?.data?.detail);
    }
    setBusy(false);
  };

  const disconnect = async () => {
    if (!window.confirm('Disconnect this org from Stripe? Active subscriptions remain on Stripe but new sign-ups will be blocked.')) return;
    setBusy(true);
    try {
      await axios.delete(`${API}/stripe-connect/orgs/${organizationId}/disconnect`, { headers: headers() });
      notify.success('Disconnected', 'Stripe account unlinked.');
      await load();
    } catch (e) {
      notify.error('Disconnect failed', e.response?.data?.detail);
    }
    setBusy(false);
  };

  if (loading) {
    return (
      <Card className="p-4 border-zinc-200" data-testid="payment-setup-loading">
        <div className="flex items-center gap-2 text-zinc-400 text-sm"><Loader2 size={14} className="animate-spin" /> Loading payment setup…</div>
      </Card>
    );
  }

  const acct = data?.account;
  const fee = data?.platform_fee_percent ?? 1.0;

  return (
    <Card className="p-4 border-zinc-200" data-testid="payment-setup-card">
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <h4 className="text-sm font-semibold text-zinc-900 flex items-center gap-2">
          <CreditCard size={15} className="text-fuchsia-600" /> Payment setup
        </h4>
        <Button size="sm" variant="outline" onClick={load} disabled={busy} data-testid="payment-setup-refresh">
          <RefreshCw size={11} className={`mr-1 ${busy ? 'animate-spin' : ''}`} /> Refresh
        </Button>
      </div>

      {!data?.connected ? (
        <div className="space-y-3" data-testid="payment-setup-empty">
          <p className="text-xs text-zinc-500">
            Connect a Stripe account so members can sign up and pay online. We charge a {fee}% platform fee on each transaction (members pay this; you don't).
          </p>
          <Button onClick={startOnboarding} disabled={busy} className="w-full bg-[#635bff] hover:bg-[#4d44ee] text-white" data-testid="payment-setup-start">
            {busy ? <Loader2 size={14} className="animate-spin mr-2" /> : <ShieldCheck size={14} className="mr-2" />}
            Connect Stripe (Express · 5 min)
          </Button>

          <div className="border-t border-zinc-100 pt-3">
            <p className="text-[11px] uppercase tracking-wide text-zinc-400 font-semibold mb-2 flex items-center gap-1.5">
              <Link2 size={10} /> Already have a Stripe account?
            </p>
            <div className="flex items-center gap-2">
              <Input
                placeholder="acct_1ABC…"
                value={acctIdInput}
                onChange={(e) => setAcctIdInput(e.target.value)}
                className="h-9 font-mono text-xs"
                data-testid="payment-setup-acct-input"
              />
              <Button onClick={linkExisting} disabled={busy} variant="outline" size="sm" className="h-9 whitespace-nowrap" data-testid="payment-setup-link-existing">
                Link
              </Button>
            </div>
            <p className="text-[10px] text-zinc-400 mt-1">Find this in Stripe → Settings → Account info → Account ID.</p>
          </div>
        </div>
      ) : !data?.ready ? (
        <div className="space-y-3" data-testid="payment-setup-pending">
          <div className="p-3 rounded-lg bg-amber-50 border border-amber-200 text-xs text-amber-800 flex items-start gap-2">
            <AlertCircle size={14} className="mt-0.5" />
            <div>
              Onboarding not yet complete. Stripe needs more info before payouts can run.
              {acct?.requirements_due?.length > 0 && (
                <ul className="mt-1 list-disc list-inside text-[11px]">
                  {acct.requirements_due.slice(0, 5).map((r) => <li key={r} className="font-mono">{r}</li>)}
                </ul>
              )}
            </div>
          </div>
          <Button onClick={startOnboarding} disabled={busy} className="w-full bg-[#635bff] hover:bg-[#4d44ee] text-white" data-testid="payment-setup-continue">
            Continue onboarding
            <ExternalLink size={12} className="ml-2" />
          </Button>
          <Button onClick={disconnect} disabled={busy} variant="ghost" size="sm" className="w-full text-rose-600 hover:bg-rose-50 text-xs" data-testid="payment-setup-disconnect">
            <Unplug size={11} className="mr-1" /> Disconnect
          </Button>
        </div>
      ) : (
        <div className="space-y-3" data-testid="payment-setup-ready">
          <div className="p-3 rounded-lg bg-emerald-50 border border-emerald-200 text-xs text-emerald-800 flex items-start gap-2">
            <ShieldCheck size={14} className="mt-0.5" />
            <div>
              <strong>Live & ready.</strong> {acct?.business_profile_name || 'Your gym'} can take member payments. Charges & payouts enabled.
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2 text-[11px]">
            <div className="p-2 rounded bg-zinc-50 border border-zinc-100">
              <p className="text-zinc-400 uppercase font-semibold">Account</p>
              <p className="font-mono break-all text-zinc-700">{acct?.account_id}</p>
            </div>
            <div className="p-2 rounded bg-zinc-50 border border-zinc-100">
              <p className="text-zinc-400 uppercase font-semibold">Country · Currency</p>
              <p className="text-zinc-700">{(acct?.country || '').toUpperCase()} · {(acct?.default_currency || '').toUpperCase()}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button onClick={openDashboard} disabled={busy} variant="outline" size="sm" className="flex-1" data-testid="payment-setup-dashboard">
              <Banknote size={12} className="mr-1" /> Stripe dashboard
              <ExternalLink size={11} className="ml-1" />
            </Button>
            <Button onClick={disconnect} disabled={busy} variant="ghost" size="sm" className="text-rose-600 hover:bg-rose-50" data-testid="payment-setup-disconnect-2">
              <Unplug size={11} />
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
};

export default PaymentSetupCard;
