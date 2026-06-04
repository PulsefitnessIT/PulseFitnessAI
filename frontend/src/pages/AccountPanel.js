import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/App';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import axios from 'axios';
import { Link } from 'react-router-dom';
import MFASetupCard from '../components/shared/MFASetupCard';
import DigestPreferencesCard from '../components/shared/DigestPreferencesCard';
import UsageMeterCard from '../components/shared/UsageMeterCard';
import NotificationPreferencesPanel from '../components/shared/NotificationPreferencesPanel';
import SubscriptionManagementPanel from '../components/shared/SubscriptionManagementPanel';
import LocalizationPanel from '../components/shared/AccountSettings/LocalizationPanel';
import {
  CreditCard, Calendar, Building2, ArrowUpRight, Clock, Wrench
} from 'lucide-react';

const AccountPanel = ({ open, onClose }) => {
  const { _t } = useTranslation();
  const { API, _user } = useAuth();
  const [billing, setBilling] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (open) loadBilling();
  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: the loader closure(s) re-read live state on every call; the effect re-fires on the listed trigger deps, so adding the function identity would just thrash without changing behaviour.
  }, [open]);

  const loadBilling = async () => {
    setLoading(true);
    const token = localStorage.getItem('token');
    try {
      const res = await axios.get(`${API}/account/billing`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setBilling(res.data);
    } catch {
      setBilling(null);
    } finally {
      setLoading(false);
    }
  };

  const tierColors = {
    none: 'bg-gray-500/20 text-gray-400',
    basic: 'bg-blue-500/20 text-blue-400',
    pro: 'bg-[rgb(var(--rgb-brand-blue)/0.2)] text-[var(--color-brand-blue)]',
    premium: 'bg-amber-500/20 text-amber-400',
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="bg-[var(--theme-surface)] border-white/10 text-white max-w-lg max-h-[85vh] overflow-y-auto" data-testid="account-panel">
        <DialogHeader>
          <DialogTitle className="text-white text-xl">Account Details</DialogTitle>
        </DialogHeader>

        {loading ? (
          <div className="text-center py-8 text-[var(--color-text-muted)]">Loading account info...</div>
        ) : billing ? (
          <div className="space-y-5">
            {/* Profile */}
            <Card className="bg-[var(--color-ink-alt)] border-white/10 p-5">
              <div className="flex items-center gap-4">
                <div className="w-14 h-14 bg-[var(--color-brand-blue)] rounded-full flex items-center justify-center text-white text-xl font-bold flex-shrink-0">
                  {billing.full_name?.charAt(0)?.toUpperCase() || 'U'}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-white font-semibold text-lg truncate" data-testid="account-name">{billing.full_name}</p>
                  <p className="text-[var(--color-text-muted)] text-sm truncate" data-testid="account-email">{billing.email}</p>
                  <div className="flex items-center gap-2 mt-1">
                    <Badge className={tierColors[billing.current_plan] || tierColors.none} data-testid="account-plan-badge">
                      {billing.plan_name}
                    </Badge>
                    <Badge className="bg-white/5 text-[var(--color-text-muted)] capitalize" data-testid="account-role-badge">{billing.role}</Badge>
                  </div>
                </div>
              </div>
            </Card>

            {/* Current Plan */}
            <Card className="bg-[var(--color-ink-alt)] border-white/10 p-5">
              <h3 className="text-sm font-medium text-[var(--color-text-muted)] uppercase tracking-wider mb-3 flex items-center gap-2">
                <CreditCard size={14} /> Subscription
              </h3>
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-white font-semibold text-lg">{billing.plan_name}</p>
                  {billing.plan_price > 0 ? (
                    <p className="text-[var(--color-text-muted)] text-sm">{"\u00A3"}{billing.plan_price}/month</p>
                  ) : (
                    <p className="text-[var(--color-text-muted)] text-sm">No active subscription</p>
                  )}
                </div>
                {billing.current_plan === 'none' ? (
                  // Iter 216o-6 — only send first-time visitors to the
                  // marketing pricing page. Active subscribers should
                  // manage their plan via the SubscriptionManagementPanel
                  // below (which exposes proper "Change plan" + "Cancel
                  // subscription" workflows hitting the Stripe API).
                  <Link to="/pricing" onClick={onClose}>
                    <Button size="sm" className="bg-[var(--color-brand-blue)] text-white" data-testid="account-upgrade-btn">
                      Subscribe <ArrowUpRight size={14} className="ml-1" />
                    </Button>
                  </Link>
                ) : (
                  <Button
                    size="sm"
                    className="bg-[var(--color-brand-blue)] text-white"
                    data-testid="account-manage-subscription-btn"
                    onClick={() => {
                      // Smooth-scroll the dialog body down to the
                      // SubscriptionManagementPanel where Change/Cancel live.
                      const target = document.querySelector('[data-testid="sub-mgmt-panel"]');
                      if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    }}
                  >
                    Manage <ArrowUpRight size={14} className="ml-1" />
                  </Button>
                )}
              </div>
            </Card>

            {/* Organization */}
            {billing.organization && (
              <Card className="bg-[var(--color-ink-alt)] border-white/10 p-5">
                <h3 className="text-sm font-medium text-[var(--color-text-muted)] uppercase tracking-wider mb-3 flex items-center gap-2">
                  <Building2 size={14} /> Organisation
                </h3>
                <p className="text-white font-semibold" data-testid="account-org-name">{billing.organization}</p>
                {billing.organization_code && (
                  <p className="text-[var(--color-text-muted)] text-sm mt-1">
                    Invite code: <span className="font-mono text-[var(--color-brand-blue)]" data-testid="account-org-code">{billing.organization_code}</span>
                  </p>
                )}
                {/* Iter 220p1 — region & currency (USA readiness) */}
                <div className="mt-4 pt-4 border-t border-white/10">
                  <LocalizationPanel />
                </div>
              </Card>
            )}

            {/* Member Since */}
            <Card className="bg-[var(--color-ink-alt)] border-white/10 p-5">
              <h3 className="text-sm font-medium text-[var(--color-text-muted)] uppercase tracking-wider mb-3 flex items-center gap-2">
                <Calendar size={14} /> Membership
              </h3>
              <p className="text-white text-sm" data-testid="account-member-since">
                Member since {billing.member_since ? new Date(billing.member_since).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' }) : 'N/A'}
              </p>
            </Card>

            {/* Payment History */}
            <Card className="bg-[var(--color-ink-alt)] border-white/10 p-5">
              <h3 className="text-sm font-medium text-[var(--color-text-muted)] uppercase tracking-wider mb-3 flex items-center gap-2">
                <Clock size={14} /> Payment History
              </h3>
              {billing.payment_history && billing.payment_history.length > 0 ? (
                <div className="space-y-2 max-h-[200px] overflow-y-auto">
                  {billing.payment_history.map((p, idx) => (
                    <div key={idx} className="flex items-center justify-between p-2 bg-[var(--theme-surface)] rounded" data-testid={`payment-${idx}`}>
                      <div>
                        <p className="text-white text-sm">{p.package_id?.charAt(0).toUpperCase() + p.package_id?.slice(1)} Plan</p>
                        <p className="text-[var(--color-text-muted)] text-xs">{p.created_at ? new Date(p.created_at).toLocaleDateString() : ''}</p>
                      </div>
                      <div className="text-right">
                        <p className="text-white text-sm font-medium">{"\u00A3"}{p.amount?.toFixed(2)}</p>
                        <Badge className={p.payment_status === 'paid' ? 'bg-green-500/20 text-green-400 text-xs' : 'bg-yellow-500/20 text-yellow-400 text-xs'}>
                          {p.payment_status}
                        </Badge>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-[var(--color-text-muted)] text-sm text-center py-3">No payment history yet</p>
              )}
            </Card>
          </div>
        ) : (
          <div className="text-center py-8 text-[var(--color-text-muted)]">Failed to load account info</div>
        )}

        {/* Security / MFA */}
        <div className="mt-4">
          <MFASetupCard />
        </div>

        {/* Usage meter (iter 215c0) */}
        <div className="mt-4">
          <UsageMeterCard />
        </div>

        {/* Subscription management (iter 215c1) */}
        <div className="mt-4">
          <SubscriptionManagementPanel />
        </div>

        {/* Notification preferences (iter 215c0) */}
        <div className="mt-4">
          <NotificationPreferencesPanel />
        </div>

        {/* Digest email preferences */}
        <div className="mt-4">
          <DigestPreferencesCard />
        </div>

        {/* Iter 220du — Custom Fields admin link. Engineer admins
            create / edit / job-type-scope custom fields here so
            the engineer's job tabs auto-load the right per-machine
            data-capture rows. */}
        <div className="mt-4">
          <Card className="bg-[var(--color-ink-alt)] border-white/10 p-4">
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-xl bg-indigo-500/20 text-indigo-300 flex items-center justify-center shrink-0">
                <Wrench size={18} />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-white text-sm font-semibold">Engineer custom fields</p>
                <p className="text-[var(--color-text-muted)] text-xs leading-snug mt-0.5">
                  Define machine + job-type specific capture fields
                  (e.g. PPM checklist values, install commissioning
                  readings).
                </p>
                <Link
                  to="/svc/engineer/work-report-fields"
                  onClick={onClose}
                  className="inline-flex items-center gap-1 mt-2 text-xs font-bold text-[var(--color-brand-blue)] hover:underline"
                  data-testid="account-link-custom-fields"
                >
                  Manage custom fields <ArrowUpRight size={12} />
                </Link>
                <Link
                  to="/svc/engineer/case-types"
                  onClick={onClose}
                  className="inline-flex items-center gap-1 mt-2 ml-3 text-xs font-bold text-[var(--color-brand-blue)] hover:underline"
                  data-testid="account-link-case-types"
                >
                  Manage case types <ArrowUpRight size={12} />
                </Link>
              </div>
            </div>
          </Card>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default AccountPanel;
