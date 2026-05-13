import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { ArrowUpRight, Check, FileText, Loader2, Plus } from 'lucide-react';
import { useAuth } from '@/App';
import { API, useAuthHeaders } from './shared';


export default function BillingSection({ billing, onClose }) {
  const { user } = useAuth();
  const headers = useAuthHeaders();
  const trial = user?.trial;
  const isTrial = !!trial?.is_trial;
  const [pricing, setPricing] = useState(null);
  const [moduleBusy, setModuleBusy] = useState(null);

  useEffect(() => {
    let cancelled = false;
    axios.get(`${API}/payments/pricing`)
      .then((r) => { if (!cancelled) setPricing(r.data); })
      .catch(() => { if (!cancelled) setPricing(null); });
    return () => { cancelled = true; };
  }, []);

  // Modules already enabled on this org (so we can render Active vs Add-this-module)
  const enabledModules = new Set(Object.entries(user?.module_access || {})
    .filter(([, v]) => !!v).map(([k]) => k));

  const startCheckout = async (plan, opts = {}) => {
    setModuleBusy(opts.module_id || plan);
    try {
      const { data } = await axios.post(
        `${API}/payments/checkout/flex`,
        { plan, origin_url: window.location.origin, ...opts },
        { headers: headers() },
      );
      if (data?.url) {
        window.location.href = data.url;
      }
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Could not open checkout');
      setModuleBusy(null);
    }
  };

  if (!billing) {
    return <div className="text-sm" style={{ color: 'var(--theme-text-muted)' }}>Loading billing…</div>;
  }

  return (
    <div className="space-y-6" data-testid="account-section-billing">
      {/* Trial state — visible when org is in any trial status */}
      {isTrial && (
        <div
          className="rounded-xl p-5"
          style={{
            border: `1px solid ${trial.status === 'expired' || trial.status === 'suspended' ? '#dc2626' : trial.status === 'expiring_soon' ? '#f59e0b' : 'var(--brand-color, #0055FF)'}`,
            background: trial.status === 'expired' || trial.status === 'suspended'
              ? 'color-mix(in srgb, #dc2626 8%, transparent)'
              : trial.status === 'expiring_soon'
                ? 'color-mix(in srgb, #f59e0b 8%, transparent)'
                : 'color-mix(in srgb, var(--brand-color, #0055FF) 5%, transparent)',
          }}
          data-testid="account-billing-trial-card"
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-[10px] uppercase tracking-wider font-bold mb-1"
                   style={{ color: trial.status === 'expired' || trial.status === 'suspended' ? '#dc2626' : trial.status === 'expiring_soon' ? '#b45309' : 'var(--brand-color, var(--color-brand-blue))' }}>
                {trial.status === 'suspended' ? 'Trial suspended' :
                 trial.status === 'expired' ? 'Trial expired' :
                 trial.status === 'expiring_soon' ? 'Trial ending soon' :
                 'Free trial active'}
              </div>
              <div className="text-xl font-extrabold" style={{ color: 'var(--theme-text)' }} data-testid="account-billing-trial-countdown">
                {trial.status === 'suspended' ? 'Access has been suspended' :
                 trial.days_left > 0 ? `${trial.days_left} day${trial.days_left === 1 ? '' : 's'} remaining` :
                 trial.hours_left > 0 ? `${trial.hours_left} hour${trial.hours_left === 1 ? '' : 's'} remaining` :
                 'Trial has ended'}
              </div>
              <div className="text-sm mt-1" style={{ color: 'var(--theme-text-muted)' }}>
                Trial ends {trial.trial_ends_at ? new Date(trial.trial_ends_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' }) : '—'}.
                {trial.status === 'expired' && ' Upgrade to keep your data — it will be permanently deleted after the grace period.'}
                {trial.status === 'expiring_soon' && ' Upgrade now to avoid losing access.'}
                {trial.status === 'active' && ' Add a payment method whenever you’re ready.'}
              </div>
            </div>
            <button
              type="button"
              onClick={() => startCheckout('bundle', { site_count: 1 })}
              disabled={moduleBusy === 'bundle'}
              className="account-btn-primary flex-shrink-0"
              data-testid="account-billing-upgrade-now-btn"
            >
              {moduleBusy === 'bundle' ? <Loader2 size={14} className="animate-spin" /> : null}
              Upgrade Plan <ArrowUpRight size={14} />
            </button>
          </div>
        </div>
      )}

      <div className="account-card rounded-xl p-5">
        <div className="text-[10px] uppercase tracking-wider font-semibold mb-2" style={{ color: 'var(--theme-text-muted)' }}>Current plan</div>
        <div className="flex items-center justify-between">
          <div>
            <div className="text-xl font-extrabold" style={{ color: 'var(--theme-text)' }}>{billing.plan_name}</div>
            <div className="text-sm mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>
              {isTrial ? 'On free trial — payment due before trial ends' :
               billing.plan_price > 0 ? `£${billing.plan_price}/month` : 'No active subscription'}
            </div>
          </div>
          <button
            type="button"
            onClick={() => startCheckout('bundle', { site_count: 1 })}
            disabled={moduleBusy === 'bundle'}
            className="account-btn-primary"
            data-testid="account-billing-upgrade-btn"
          >
            {moduleBusy === 'bundle' ? <Loader2 size={14} className="animate-spin" /> : null}
            {billing.current_plan === 'none' || isTrial ? 'Upgrade Plan' : 'Change plan'}
            <ArrowUpRight size={14} />
          </button>
        </div>
      </div>

      {/* Modules — buy individual ones if you don't want the full bundle */}
      {pricing?.modules?.length > 0 && (
        <div data-testid="account-billing-modules">
          <h3 className="account-section-title">Add a module</h3>
          <p className="account-section-sub">
            Pay only for what you need — or upgrade to the {pricing.bundle?.name || 'GymAxis Pro'} bundle for everything at £{pricing.bundle?.monthly}/mo.
          </p>
          <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3">
            {pricing.modules.map((m) => {
              const active = enabledModules.has(m.id);
              return (
                <div
                  key={m.id}
                  className="account-card rounded-xl p-4 flex items-center justify-between gap-3"
                  data-testid={`account-billing-module-${m.id}`}
                >
                  <div className="min-w-0">
                    <div className="text-sm font-semibold capitalize" style={{ color: 'var(--theme-text)' }}>{m.name}</div>
                    <div className="text-[11px]" style={{ color: 'var(--theme-text-muted)' }}>£{m.monthly}/mo · £{m.annual}/yr</div>
                  </div>
                  {active ? (
                    <span className="text-[10px] uppercase tracking-wider px-2 py-1 rounded font-bold" style={{
                      color: 'var(--brand-color, var(--color-brand-blue))',
                      background: 'color-mix(in srgb, var(--brand-color, #0055FF) 12%, transparent)',
                    }}>
                      <Check size={10} className="inline mr-0.5" /> Active
                    </span>
                  ) : (
                    <button
                      type="button"
                      onClick={() => startCheckout('module', { module_id: m.id })}
                      disabled={moduleBusy === m.id}
                      className="account-btn-secondary flex-shrink-0"
                      data-testid={`account-billing-add-module-${m.id}`}
                    >
                      {moduleBusy === m.id ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
                      Add this module
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div>
        <h3 className="account-section-title">Payment history</h3>
        <p className="account-section-sub">Last 50 transactions on this account.</p>
        <div className="mt-3 account-card rounded-xl divide-y max-h-72 overflow-y-auto" style={{ borderColor: 'var(--theme-border)' }}>
          {(billing.payment_history || []).length === 0 && (
            <div className="px-4 py-6 text-sm text-center" style={{ color: 'var(--theme-text-muted)' }}>No payments yet.</div>
          )}
          {(billing.payment_history || []).map((p, idx) => {
            const invoiceId = p.id || p.session_id;
            const downloadPdf = async () => {
              if (!invoiceId) return;
              const token = localStorage.getItem('token');
              try {
                const resp = await fetch(
                  `${API}/account/billing/${encodeURIComponent(invoiceId)}/invoice.pdf`,
                  { headers: { Authorization: `Bearer ${token}` } },
                );
                if (resp.redirected) {
                  window.open(resp.url, '_blank', 'noopener');
                  return;
                }
                if (!resp.ok) throw new Error('Download failed');
                const blob = await resp.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `invoice-${String(invoiceId).slice(0, 12)}.pdf`;
                document.body.appendChild(a);
                a.click();
                a.remove();
                URL.revokeObjectURL(url);
              } catch (err) {
                toast.error('Could not download invoice');
              }
            };
            return (
              <div key={idx} className="px-4 py-3 flex items-center justify-between gap-3 text-sm" data-testid={`account-payment-${idx}`}>
                <div className="min-w-0">
                  <div className="font-medium truncate" style={{ color: 'var(--theme-text)' }}>{p.package_id ? p.package_id.charAt(0).toUpperCase() + p.package_id.slice(1) : (p.package_name || 'Charge')}</div>
                  <div className="text-[11px]" style={{ color: 'var(--theme-text-muted)' }}>{p.created_at ? new Date(p.created_at).toLocaleDateString() : ''}</div>
                </div>
                <div className="flex items-center gap-3 flex-shrink-0">
                  <div className="text-right">
                    <div className="font-semibold" style={{ color: 'var(--theme-text)' }}>£{Number(p.amount || 0).toFixed(2)}</div>
                    <div className={`text-[11px] uppercase tracking-wider font-bold ${p.payment_status === 'paid' ? 'text-emerald-500' : 'text-amber-500'}`}>
                      {p.payment_status || 'pending'}
                    </div>
                  </div>
                  {invoiceId && (
                    <button
                      type="button"
                      onClick={downloadPdf}
                      className="inline-flex items-center gap-1 text-xs px-2 py-1.5 rounded border transition"
                      style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}
                      title="Download invoice PDF"
                      data-testid={`account-payment-pdf-${idx}`}
                    >
                      <FileText size={12} /> PDF
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ─── Organisation ────────────────────────────────────────────────
