/**
 * Iter 216h21 — Org-scoped Integrations tab (P4 redesign).
 *
 * Surfaces every third-party connection that affects a single
 * organisation in one place: Stripe Connect, Sicon Service ledger,
 * Orbit 4 stock, Sage 200, plus a quick health check. Master admins
 * used to hunt across Finance, Integrations and Billing tabs to
 * piece this picture together — this tab puts it all on one page
 * and links out to the global Integrations console for editing.
 *
 * The fields rendered here are READ-ONLY snapshots: the canonical
 * editors stay in their existing global panels (Stripe Connect page,
 * Sicon Service page, Orbit 4 page, Billing tab on the same drawer).
 */
import { useEffect, useState } from 'react';
import axios from 'axios';
import { Banknote, Plug, ArrowUpRight, CheckCircle2, AlertCircle, RefreshCw } from 'lucide-react';
import Button from '@/components/shared/Button';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const StatusPill = ({ ok, labelOk = 'Connected', labelOff = 'Not configured', testId }) => (
  <span
    className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${
      ok ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-zinc-50 text-zinc-500 border border-zinc-200'
    }`}
    data-testid={testId}
  >
    {ok ? <CheckCircle2 size={10} /> : <AlertCircle size={10} />}
    {ok ? labelOk : labelOff}
  </span>
);

const Row = ({ icon: Icon, name, description, status, action, testId }) => (
  <div className="flex items-start gap-3 p-3 rounded-lg border bg-white" style={{ borderColor: '#E4E4E7' }} data-testid={testId}>
    <div className="w-8 h-8 rounded-md flex items-center justify-center flex-shrink-0 bg-zinc-50">
      <Icon size={14} className="text-zinc-600" />
    </div>
    <div className="min-w-0 flex-1">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-sm font-semibold text-zinc-900">{name}</span>
        {status}
      </div>
      <p className="text-[11px] text-zinc-500 mt-0.5">{description}</p>
    </div>
    {action}
  </div>
);

const OrgIntegrationsTab = ({ org }) => {
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const load = async () => {
    setLoading(true); setError('');
    try {
      const token = localStorage.getItem('token');
      const { data } = await axios.get(
        `${API}/master-admin/organizations/${org.id}/integration-health`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      setHealth(data);
    } catch (e) {
      // Endpoint is best-effort — fall back to the local org record.
      setError(e.response?.data?.detail || 'Live status unavailable, using stored config.');
      setHealth(null);
    }
    setLoading(false);
  };

  useEffect(() => { load();   }, [org.id]);

  // Derive per-integration "connected" booleans from health (if returned)
  // OR from the org doc itself (graceful fallback).
  const stripeOk  = !!(health?.stripe_connect?.connected ?? org.stripe_connect_account_id ?? org.stripe_account_id);
  const siconOk   = !!(health?.sicon?.configured ?? org.sicon_customer_account_number);
  const orbitOk   = !!(health?.orbit4?.configured ?? org.orbit4_customer_id);
  const sageOk    = !!(health?.sage200?.configured ?? org.sage_customer_number);

  const open = (path) => {
    try {
      window.history.pushState({}, '', `?section=${path}`);
      window.dispatchEvent(new CustomEvent('gymaxis:set-section', { detail: { section: path } }));
    } catch { /* noop */ }
  };

  return (
    <div className="space-y-3" data-testid={`org-integrations-panel-${org.id}`}>
      <div className="flex items-center justify-between">
        <p className="text-xs text-zinc-500">
          Per-org connection status. Click <strong className="text-zinc-700">Manage</strong> to jump to the global console.
        </p>
        <Button
          variant="tertiary" size="sm"
          loading={loading}
          icon={loading ? undefined : RefreshCw}
          onClick={load}
          disabled={loading}
          data-testid={`org-integrations-refresh-${org.id}`}
        >
          Refresh
        </Button>
      </div>

      {error && (
        <p className="text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1.5">{error}</p>
      )}

      <Row
        icon={Banknote}
        name="Stripe Connect"
        description={stripeOk
          ? `Account ${health?.stripe_connect?.account_id || org.stripe_connect_account_id || org.stripe_account_id} · platform fee ${health?.stripe_connect?.platform_fee_pct ?? '—'}%`
          : 'No Stripe Connect onboarding completed for this org yet.'}
        status={<StatusPill ok={stripeOk} testId={`org-int-stripe-status-${org.id}`} />}
        action={(
          <button
            type="button"
            onClick={() => open('stripe-connect')}
            className="text-[11px] font-semibold text-blue-700 hover:text-blue-900 inline-flex items-center gap-1"
            data-testid={`org-int-stripe-manage-${org.id}`}
          >
            Manage <ArrowUpRight size={11} />
          </button>
        )}
        testId={`org-int-stripe-${org.id}`}
      />

      <Row
        icon={Plug}
        name="Sicon Service (Sage 200 ledger)"
        description={siconOk
          ? `Customer ${org.sicon_customer_account_number || health?.sicon?.account_ref} · auto-posting ${health?.sicon?.auto_post ? 'on' : 'manual'}`
          : 'Not linked. Map a Sicon customer to auto-post invoices.'}
        status={<StatusPill ok={siconOk} testId={`org-int-sicon-status-${org.id}`} />}
        action={(
          <button
            type="button"
            onClick={() => open('sicon-integration')}
            className="text-[11px] font-semibold text-blue-700 hover:text-blue-900 inline-flex items-center gap-1"
            data-testid={`org-int-sicon-manage-${org.id}`}
          >
            Manage <ArrowUpRight size={11} />
          </button>
        )}
        testId={`org-int-sicon-${org.id}`}
      />

      <Row
        icon={Plug}
        name="Orbit 4 (stock / equipment master)"
        description={orbitOk
          ? `Customer ${org.orbit4_customer_id || health?.orbit4?.customer_id}`
          : 'Not linked. Connect Orbit 4 to pull equipment + stock.'}
        status={<StatusPill ok={orbitOk} testId={`org-int-orbit-status-${org.id}`} />}
        action={(
          <button
            type="button"
            onClick={() => open('orbit4')}
            className="text-[11px] font-semibold text-blue-700 hover:text-blue-900 inline-flex items-center gap-1"
            data-testid={`org-int-orbit-manage-${org.id}`}
          >
            Manage <ArrowUpRight size={11} />
          </button>
        )}
        testId={`org-int-orbit-${org.id}`}
      />

      <Row
        icon={Plug}
        name="Sage 200 (customer ledger)"
        description={sageOk
          ? `Customer ${org.sage_customer_number || health?.sage200?.account_ref}`
          : 'No Sage 200 customer number on file. Add one in Billing tab.'}
        status={<StatusPill ok={sageOk} testId={`org-int-sage-status-${org.id}`} />}
        action={null}
        testId={`org-int-sage-${org.id}`}
      />

      <p className="text-[10px] text-zinc-400 italic pt-1">
        Health snapshot updates when you click Refresh. Live keys are managed on the global Integrations pages.
      </p>
    </div>
  );
};

export default OrgIntegrationsTab;
