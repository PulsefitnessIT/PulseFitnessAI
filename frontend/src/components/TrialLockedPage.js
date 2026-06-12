/* TrialLockedPage — full-screen lock shown when trial has expired.
 * Owner sees upgrade CTA; others see "contact your admin".
 *
 * Iter 216o-8 — Upgrade now sends the user to /pricing so they can pick
 * the bundle vs individual modules instead of being force-bought into
 * the bundle.
 */
import { useNavigate } from 'react-router-dom';
import { notify } from '@/components/notifications';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Lock, Zap, LogOut, Mail } from 'lucide-react';
import { useAuth } from '@/App';

export default function TrialLockedPage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const trial = user?.trial || {};
  const isSuspended = trial.status === 'suspended';
  const isOwner = user?.role === 'owner';
  const isPulse = user?.account_type === 'pulse_pro' || user?.account_type === 'lite';
  const isProvider = user?.account_type === 'service_provider';
  const brand = isPulse ? 'Pulse Fitness' : 'GymAxis';

  const upgrade = () => {
    if (!isOwner) {
      notify.info('Ask your organisation owner to upgrade.');
      return;
    }
    // Iter 258 — service providers convert on their dedicated Stripe page.
    navigate(isProvider ? '/service-desk/upgrade' : '/pricing?from=trial');
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-zinc-100 via-white to-red-50 p-4" data-testid="trial-locked-page">
      <Card className="max-w-lg w-full p-8 lg:p-10 border-red-200 shadow-xl">
        <div className="w-14 h-14 rounded-full bg-red-100 text-red-600 flex items-center justify-center mb-5">
          <Lock size={24} />
        </div>
        <h1 className="text-2xl font-semibold text-zinc-900 mb-2">
          {isSuspended ? 'Account suspended' : 'Your free trial has ended'}
        </h1>
        <p className="text-sm text-zinc-600 leading-relaxed">
          {isSuspended
            ? 'Your data is being held safely. Upgrade anytime within the next 30 days to restore full access.'
            : `Your 2-week ${brand} trial has finished. Upgrade now to keep all your equipment data, PPM schedules and site history — we preserve everything for 30 days after expiry.`}
        </p>

        <div className="mt-5 bg-zinc-50 border border-zinc-200 rounded-lg p-4">
          <p className="text-xs font-semibold uppercase tracking-wider text-zinc-500 mb-2">What you keep after upgrading</p>
          <ul className="text-sm text-zinc-700 space-y-1 list-disc list-inside">
            <li>All equipment and serial number records</li>
            <li>PPM schedules and engineer history</li>
            <li>Site details, users and permissions</li>
            <li>KPI history and uptime data</li>
          </ul>
        </div>

        <div className="mt-6 space-y-2">
          {isOwner ? (
            <Button onClick={upgrade}
              className="w-full bg-blue-600 hover:bg-blue-700 text-white h-11"
              data-testid="locked-upgrade-btn">
              <Zap size={14} className="mr-1" />
              Upgrade Plan — keep everything
            </Button>
          ) : (
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-sm text-blue-800 flex items-start gap-2" data-testid="locked-contact-admin">
              <Mail size={14} className="flex-shrink-0 mt-0.5" />
              <span>Ask your organisation owner to upgrade. They'll find the option on this screen after signing in.</span>
            </div>
          )}
          <Button variant="outline" onClick={logout} className="w-full h-10" data-testid="locked-logout">
            <LogOut size={12} className="mr-1" /> Sign out
          </Button>
        </div>
      </Card>
    </div>
  );
}
