import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Check, Loader2 } from 'lucide-react';
import { useAuth } from '@/App';
import { API, useAuthHeaders } from './shared';
import { useNavigate } from 'react-router-dom';

export default function OnboardingSection({ onJumpSection, onClose, profile }) {
  const headers = useAuthHeaders();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

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
  // Pulse/Lite operators bounced to the GymAxis 404 page (Lee's
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

  const handleStep = (step) => {
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
  const pct = data?.percent ?? 0;
  return (
    <div className="space-y-5" data-testid="account-section-onboarding">
      <div>
        <h3 className="account-section-title">Setup checklist</h3>
        <p className="account-section-sub">
          {data?.completed_count ?? 0} of {data?.total ?? 0} steps complete — finish them in any order.
        </p>
      </div>
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
            className="account-card rounded-xl p-4 flex items-start gap-3"
            data-testid={`account-onboarding-step-${s.id}`}
            data-completed={s.completed ? 'true' : 'false'}
          >
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
            <button
              type="button"
              onClick={() => handleStep(s)}
              className="account-btn-secondary flex-shrink-0"
              data-testid={`account-onboarding-cta-${s.id}`}
            >
              {s.completed ? 'Review' : (s.cta_label || 'Open')}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

