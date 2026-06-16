import { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Check, Loader2 } from 'lucide-react';
import { API, useAuthHeaders } from './shared';
import { useNavigate } from 'react-router-dom';
import EquipmentImportInline from './EquipmentImportInline';
import QrPrintInline from './QrPrintInline';
import StripeConnectErrorBanner from '@/components/shared/StripeConnectErrorBanner';

export default function OnboardingSection({ onJumpSection, onClose, profile }) {
  const headers = useAuthHeaders();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [stripeBusy, setStripeBusy] = useState(false);
  const [stripeError, setStripeError] = useState(null);
  // Iter 216h108 — inline panel mode for steps that should open IN the
  // settings modal rather than navigating away.
  const [inlinePanel, setInlinePanel] = useState(null);  // 'equipment_import' | 'qr_print' | null

  const reload = async () => {
    try {
      const { data } = await axios.get(`${API}/account/onboarding`, { headers: headers() });
      setData(data);
    } catch { /* ignore */ }
  };

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const { data } = await axios.get(`${API}/account/onboarding`, { headers: headers() });
        if (!cancelled) setData(data);
      } catch {
        if (!cancelled) setData({ steps: [], percent: 0 });
      }
      if (!cancelled) setLoading(false);
    };
    load();
    return () => { cancelled = true; };
  }, [headers]);

  // Iter 216h60 — resolve symbolic onboarding routes to ACTUAL react-
  // router routes for the current user. Previously the backend handed
  // out `/sites` and `/dashboard?tab=equipment` indiscriminately and
  // Pulse/Lite operators bounced to the Pulse Fitness 404 page (Lee's
  // screenshot). Now we map them to the right destination.
  const resolveRoute = (route) => {
    if (!route) return route;
    const isMaster = !!profile?.is_master_admin;
    const at = (profile?.account_type || '').toLowerCase();
    const isPulse = at === 'pulse_pro' || at === 'lite';
    // /sites isn't a real route — direct to the right Sites surface.
    if (route === '/sites' || route.startsWith('/sites?')) {
      if (isMaster) return '/master-admin?section=organizations';
      // Pulse operators manage sites via the Settings dialog (which
      // hosts PulseSettingsTab → "Add Site"). Opening with the
      // ?settings=sites deep-link triggers the dialog on mount.
      if (isPulse) return '/pulse?settings=sites';
      return '/dashboard';
    }
    // Equipment tab: Pulse operators land on /pulse with the equipment tab.
    if (route.startsWith('/dashboard?tab=equipment')) {
      if (isPulse) return '/pulse?tab=equipment';
    }
    if (route === '/dashboard' || route.startsWith('/dashboard?')) {
      if (isMaster) return route.replace('/dashboard', '/master-admin');
      if (isPulse) return route.replace('/dashboard', '/pulse');
    }
    if (route === '/pricing' && isMaster) return '/master-admin?section=integrations-hub';
    return route;
  };

  // Iter 220w — "Connect Stripe" self-serve. Previously routed owners to
  // the marketing /pricing page (never reached Stripe). Now it requests a
  // fresh Stripe Connect Express onboarding link for the owner's own org
  // and redirects straight to Stripe; on return they land back on Account
  // Settings → billing.
  const startStripeConnect = async () => {
    setStripeBusy(true);
    try {
      const { data: res } = await axios.post(
        `${API}/stripe-connect/me/onboarding-link`,
        { return_path: window.location.pathname },
        { headers: headers() },
      );
      if (res?.url) {
        window.location.href = res.url;
        return;
      }
      toast.error('Could not start Stripe onboarding');
    } catch (e) {
      const detail = e.response?.data?.detail;
      const code = (typeof detail === 'object' && detail) ? detail.code : null;
      if (code === 'stripe_connect_profile_incomplete' || code === 'stripe_connect_not_enabled') {
        // Persistent banner with the fix link (survives the failed redirect).
        setStripeError(detail);
      }
      toast.error((typeof detail === 'object' ? detail?.message : detail) || 'Could not start Stripe onboarding');
    }
    setStripeBusy(false);
  };

  const handleStep = (step) => {
    // Iter 220w — Stripe Connect self-serve action (no route push).
    if (step.cta_action === 'connect_stripe') {
      startStripeConnect();
      return;
    }
    // Iter 216h108 — inline panels open within the settings modal
    if (step.cta_inline) {
      setInlinePanel(step.cta_inline);
      return;
    }
    if (step.cta_section) {
      onJumpSection(step.cta_section);
    } else if (step.cta_route) {
      navigate(resolveRoute(step.cta_route));
      onClose();
    }
  };

  if (loading) {
    return <div className="text-sm" style={{ color: 'var(--theme-text-muted)' }}>Loading checklist…</div>;
  }
  // Iter 216h108 — inline mode renders the panel in place of the
  // checklist so the user never bounces out of Account Settings.
  if (inlinePanel === 'equipment_import') {
    return (
      <EquipmentImportInline
        onClose={() => { setInlinePanel(null); reload(); }}
        onImported={reload}
      />
    );
  }
  if (inlinePanel === 'qr_print') {
    return <QrPrintInline onClose={() => setInlinePanel(null)} />;
  }
  const pct = data?.percent ?? 0;
  return (
    <div className="space-y-5" data-testid="account-section-onboarding">
      <div>
        <h3 className="account-section-title">Setup checklist</h3>
        <p className="account-section-sub">
          {data?.completed_count ?? 0} of {data?.total ?? 0} steps complete — finish them in any order.
        </p>
      </div>
      <StripeConnectErrorBanner error={stripeError} />
      <div className="rounded-full overflow-hidden h-2 w-full" style={{ background: 'var(--theme-border-soft)' }}>
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${pct}%`, background: 'var(--brand-color, var(--color-brand-blue))' }}
          data-testid="account-onboarding-progress"
        />
      </div>
      <div className="space-y-2">
        {(data?.steps || []).map((s) => (
          <div
            key={s.id}
            className="account-card rounded-xl p-4 flex flex-col sm:flex-row items-start gap-3"
            data-testid={`account-onboarding-step-${s.id}`}
            data-completed={s.completed ? 'true' : 'false'}
          >
            <div className="flex items-start gap-3 flex-1 min-w-0 w-full sm:w-auto">
              <div
                className="mt-0.5 w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0"
                style={{
                  background: s.completed
                    ? 'var(--brand-color, var(--color-brand-blue))'
                    : 'transparent',
                  border: s.completed
                    ? 'none'
                    : '1.5px solid var(--theme-border)',
                }}
              >
                {s.completed && <Check size={12} color="#FFFFFF" strokeWidth={3} />}
              </div>
              <div className="flex-1 min-w-0">
                <div
                  className={`text-sm font-semibold ${s.completed ? 'line-through opacity-60' : ''}`}
                  style={{ color: 'var(--theme-text)' }}
                >
                  {s.label}
                </div>
                <div className="text-xs mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>
                  {s.description}
                </div>
              </div>
            </div>
            <button
              type="button"
              onClick={() => handleStep(s)}
              disabled={s.cta_action === 'connect_stripe' && stripeBusy}
              className="account-btn-secondary flex-shrink-0 w-full sm:w-auto justify-center"
              data-testid={`account-onboarding-cta-${s.id}`}
            >
              {s.cta_action === 'connect_stripe' && stripeBusy && (
                <Loader2 size={13} className="animate-spin mr-1" />
              )}
              {s.completed ? 'Review' : (s.cta_label || 'Open')}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

