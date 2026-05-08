import React, { useState } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Users, Building2, Sparkles, Loader2, Check, ArrowRight } from 'lucide-react';
import { notify } from '@/components/notifications';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

/**
 * Iter 215c — "What's CRM for?" empty-state shown when the signed-in
 * org has neither leisure nor business CRM enabled.
 *
 * Two cards:
 *   • Members CRM — bundled free with the Memberships module. Soft CTA
 *     to enable Memberships (links to plan page).
 *   • Business CRM — paid add-on. Hard CTA to start Stripe checkout.
 *
 * If only one mode is missing, that card is the only one shown.
 */
const CRMUpgradeScreen = ({ modes, accountType, membershipsEnabled, onUpgraded }) => {
  const [loadingBiz, setLoadingBiz] = useState(false);

  const isLite = accountType === 'lite';

  const startBusinessCheckout = async () => {
    const token = localStorage.getItem('token');
    if (!token) return;
    setLoadingBiz(true);
    try {
      const res = await axios.post(
        `${API}/me/crm-business/checkout`,
        { origin_url: window.location.origin },
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (res.data?.url) {
        window.location.href = res.data.url;
        return;
      }
      notify.error('Could not start checkout', 'Please try again.');
    } catch (e) {
      notify.error('Could not start checkout', e?.response?.data?.detail || 'Please try again.');
    } finally {
      setLoadingBiz(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto py-10 px-4" data-testid="crm-upgrade-screen">
      <div className="text-center mb-10">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold mb-4"
             style={{ background: 'rgba(0,85,255,0.1)', color: 'var(--color-brand-blue)' }}>
          <Sparkles size={12} /> Pick the right CRM for your business
        </div>
        <h1 className="text-3xl sm:text-4xl font-bold pulse-font-heading mb-3" style={{ color: 'var(--theme-text)' }}>
          Two CRMs, one platform.
        </h1>
        <p className="text-base pulse-font-body max-w-2xl mx-auto" style={{ color: 'var(--theme-text-muted)' }}>
          GymAxis CRM understands both <strong>members</strong> and <strong>corporate
          deals</strong>. Choose the one that matches how you sell — or get both.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {/* Members CRM */}
        <Card className="p-6 border-zinc-200 dark:border-white/10 flex flex-col" data-testid="crm-upgrade-leisure-card">
          <div className="flex items-center gap-2.5 mb-3">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center"
                 style={{ background: 'rgba(88,86,214,0.12)', color: 'var(--color-accent-indigo)' }}>
              <Users size={20} />
            </div>
            <div>
              <h3 className="text-lg font-semibold" style={{ color: 'var(--theme-text)' }}>Members CRM</h3>
              <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>Bundled free with Memberships</p>
            </div>
          </div>
          <ul className="space-y-2 text-sm pulse-font-body mb-5" style={{ color: 'var(--theme-text)' }}>
            {[
              'Lead → trial → joined → renewed pipeline',
              'MRR, churn and class fill-rate dashboards',
              'Auto-syncs with Memberships, dunning and class bookings',
              'No extra cost — turns on with Memberships',
            ].map((line) => (
              <li key={line} className="flex items-start gap-2">
                <Check size={14} className="mt-0.5 text-emerald-500 shrink-0" />
                <span>{line}</span>
              </li>
            ))}
          </ul>
          <div className="mt-auto">
            {modes?.leisure ? (
              <div className="text-sm font-semibold inline-flex items-center gap-1.5"
                   style={{ color: 'var(--color-success)' }}>
                <Check size={14} /> Active for your account
              </div>
            ) : membershipsEnabled ? (
              <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>Refresh to activate.</p>
            ) : (
              <Button
                variant="outline"
                onClick={() => { window.location.href = '/dashboard?upgrade=memberships'; }}
                className="w-full"
                data-testid="crm-upgrade-leisure-btn"
              >
                {isLite ? 'Upgrade to Pulse Pro + Memberships' : 'Enable Memberships'}
                <ArrowRight size={14} className="ml-1" />
              </Button>
            )}
          </div>
        </Card>

        {/* Business CRM */}
        <Card className="p-6 border-zinc-200 dark:border-white/10 flex flex-col" data-testid="crm-upgrade-business-card">
          <div className="flex items-center gap-2.5 mb-3">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center"
                 style={{ background: 'rgba(0,85,255,0.12)', color: 'var(--color-brand-blue)' }}>
              <Building2 size={20} />
            </div>
            <div>
              <h3 className="text-lg font-semibold" style={{ color: 'var(--theme-text)' }}>Business CRM</h3>
              <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>£49/mo — paid add-on</p>
            </div>
          </div>
          <ul className="space-y-2 text-sm pulse-font-body mb-5" style={{ color: 'var(--theme-text)' }}>
            {[
              'Discovery → demo → proposal → won pipeline',
              'Pipeline £, win rate and named-account heat-maps',
              'Sicon + Sage 200 + supplier sync ready',
              'Tenders, contracts and corporate-wellness deals',
            ].map((line) => (
              <li key={line} className="flex items-start gap-2">
                <Check size={14} className="mt-0.5 text-emerald-500 shrink-0" />
                <span>{line}</span>
              </li>
            ))}
          </ul>
          <div className="mt-auto">
            {modes?.business ? (
              <div className="text-sm font-semibold inline-flex items-center gap-1.5"
                   style={{ color: 'var(--color-success)' }}>
                <Check size={14} /> Active for your account
              </div>
            ) : (
              <Button
                onClick={startBusinessCheckout}
                disabled={loadingBiz}
                className="w-full bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white"
                data-testid="crm-upgrade-business-btn"
              >
                {loadingBiz
                  ? <><Loader2 size={14} className="mr-2 animate-spin" /> Opening checkout…</>
                  : <>Add Business CRM <ArrowRight size={14} className="ml-1" /></>}
              </Button>
            )}
          </div>
        </Card>
      </div>

      <p className="text-center text-xs mt-8 pulse-font-body" style={{ color: 'var(--theme-text-muted)' }}>
        Already have a code from your account manager?{' '}
        <a href="/master-admin" className="underline">Contact support</a> to redeem.
      </p>
    </div>
  );
};

export default CRMUpgradeScreen;
