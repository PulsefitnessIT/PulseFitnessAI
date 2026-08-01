/**
 * AccountSettingsModal — Emergent-style fixed-size settings popover for
 * Owner / Manager / Staff. Master Admins use the dedicated /master-admin
 * console and skip this modal entirely.
 *
 * Seven sections in a left rail:
 *   Profile · Onboarding · Security · Preferences · Plan & Billing · Organisation · Team & Roles
 *
 * Forced LIGHT theme — the modal always renders in the clean light
 * style (matching the Pulse/GymAxis Account Settings reference) via a
 * `data-theme="light"` scope on the shell, so it never inherits the
 * in-app light/dark toggle (a dark modal here looked off-brand).
 *
 * Iter 216h72 — sections extracted to `./AccountSettings/*.js` so each
 * concern lives in its own file. This file now just owns:
 *   • Modal open/close + Escape key + body-scroll-lock plumbing
 *   • One-time `/account/billing` fetch (drives both billing + profile)
 *   • Side-rail navigation + section routing
 *   • The shared style block (`account-input`, `account-btn-*`, etc.)
 */
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { X } from 'lucide-react';
import { useAuth } from '@/App';

import { API, SECTIONS, useAuthHeaders } from './AccountSettings/shared';
import ProfileSection from './AccountSettings/profile';
import OnboardingSection from './AccountSettings/onboarding';
import SecuritySection from './AccountSettings/security';
import PreferencesSection from './AccountSettings/preferences';
import BillingSection from './AccountSettings/billing';
import OrganisationSection from './AccountSettings/organisation';
import SuppliersSection from './AccountSettings/suppliers';
import TeamSection from './AccountSettings/team';
import DataExportSection from './AccountSettings/data_export';
import DocumentBrandingSettings from '@/pages/DocumentBrandingSettings';

export default function AccountSettingsModal({ open, onClose, initialSection }) {
  const { t } = useTranslation();
  // Static t() calls so the i18n extractor picks up the nav labels
  // (SECTIONS uses a dynamic labelKey the scanner can't see statically).
  const NAV_LABELS = {
    profile: t('settings.nav_profile', 'Profile'),
    onboarding: t('settings.nav_onboarding', 'Onboarding'),
    security: t('settings.nav_security', 'Security'),
    preferences: t('settings.nav_preferences', 'Preferences'),
    billing: t('settings.nav_billing', 'Plan & Billing'),
    organisation: t('settings.nav_organisation', 'Organisation'),
    documents: t('settings.nav_documents', 'Document Branding'),
    suppliers: t('settings.nav_suppliers', 'Suppliers'),
    team: t('settings.nav_team', 'Team & Roles'),
    'data-export': t('settings.nav_data_export', 'Data export'),
  };
  const { user, API: ctxAPI } = useAuth();
  const headers = useAuthHeaders();
  const [section, setSection] = useState('profile');
  const [profile, setProfile] = useState(null);
  const [billing, setBilling] = useState(null);

  // Iter 220w — honour a requested initial section (e.g. returning from
  // Stripe Connect onboarding opens straight on Plan & Billing).
  useEffect(() => {
    if (open && initialSection) setSection(initialSection);
  }, [open, initialSection]);

  const sections = useMemo(() => {
    // Iter 216h113h — MOD tenants don't have Plan & Billing
    // (centralised MOD procurement handles commercials), so the
    // section is filtered out for users on MOD account types.
    const isMOD = ['mod_site', 'mod_branch', 'mod_org'].includes(user?.account_type);
    return SECTIONS.filter((s) => !(isMOD && s.id === 'billing'));
  }, [user]);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  useEffect(() => {
    if (!open) return;
    const url = ctxAPI || API;
    axios.get(`${url}/account/billing`, { headers: headers() })
      .then((r) => {
        setBilling(r.data);
        setProfile((p) => p || ({
          id: user?.id, email: r.data.email, full_name: r.data.full_name,
          role: r.data.role, avatar_url: user?.avatar_url, phone: user?.phone,
        }));
      })
      .catch(() => setBilling(null));
  }, [open, ctxAPI, headers, user]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[120] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      onClick={onClose}
      data-testid="account-settings-overlay"
    >
      <style>{`
        .account-input {
          width: 100%; height: 40px; padding: 0 12px;
          background: var(--theme-input-bg);
          border: 1px solid var(--theme-input-border, var(--theme-border));
          color: var(--theme-text); border-radius: 8px; font-size: 14px;
          transition: border-color 0.15s;
        }
        .account-input.account-input-sm { height: 30px; font-size: 12px; padding: 0 8px; }
        .account-input:focus { outline: none; border-color: var(--brand-color, var(--color-brand-blue)); }
        .account-input::placeholder { color: var(--theme-text-muted); opacity: 0.7; }
        .account-section-title {
          font-size: 14px; font-weight: 700; color: var(--theme-text); letter-spacing: -0.01em;
        }
        .account-section-sub {
          font-size: 12px; color: var(--theme-text-muted); margin-top: 2px;
        }
        .account-btn-primary {
          display: inline-flex; align-items: center; gap: 6px;
          height: 36px; padding: 0 16px; font-size: 13px; font-weight: 600;
          background: var(--brand-color, var(--color-brand-blue)); color: #FFFFFF; border-radius: 8px;
          transition: opacity 0.15s; border: none;
        }
        .account-btn-primary:hover { opacity: 0.9; }
        .account-btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
        .account-btn-secondary {
          display: inline-flex; align-items: center; gap: 6px;
          height: 36px; padding: 0 14px; font-size: 13px; font-weight: 500;
          background: transparent; color: var(--theme-text);
          border: 1px solid var(--theme-border); border-radius: 8px;
          transition: background 0.15s;
        }
        .account-btn-secondary:hover { background: var(--theme-border-soft); }
        .account-modal-shell {
          background: var(--theme-bg);
          border: 1px solid var(--theme-border);
          color: var(--theme-text);
        }
        .account-modal-divider { border-color: var(--theme-border); }
        .account-sidebar { background: var(--theme-border-soft); }
        .account-nav-active {
          background: color-mix(in srgb, var(--brand-color, #0055FF) 15%, transparent);
          color: var(--brand-color, var(--color-brand-blue));
        }
        .account-nav-idle {
          color: var(--theme-text-muted);
        }
        .account-nav-idle:hover {
          background: var(--theme-border-soft);
          color: var(--theme-text);
        }
        .account-card {
          border: 1px solid var(--theme-border);
          background: var(--theme-border-soft);
        }
        .account-avatar-placeholder {
          background: color-mix(in srgb, var(--brand-color, #0055FF) 15%, transparent);
          border: 1px solid color-mix(in srgb, var(--brand-color, #0055FF) 30%, transparent);
          color: var(--brand-color, var(--color-brand-blue));
        }
      `}</style>
      <div
        onClick={(e) => e.stopPropagation()}
        data-theme="light"
        className="account-modal-shell relative w-[920px] max-w-full h-[640px] max-h-[92vh] rounded-2xl shadow-2xl overflow-hidden flex flex-col sm:rounded-2xl max-sm:rounded-none max-sm:h-full max-sm:max-h-full"
        data-testid="account-settings-modal"
      >
        <div className="flex items-center justify-between px-4 sm:px-6 py-3 sm:py-4 border-b account-modal-divider">
          <div className="min-w-0">
            <h2 className="text-base font-bold truncate" style={{ color: 'var(--theme-text)' }}>{t('settings.modal_title', 'Account Settings')}</h2>
            <p className="text-[11px] mt-0.5 truncate" style={{ color: 'var(--theme-text-muted)' }}>{t('settings.modal_subtitle', 'Manage your profile, security, plan and team.')}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-md transition flex-shrink-0"
            style={{ color: 'var(--theme-text-muted)' }}
            data-testid="account-settings-close"
          >
            <X size={18} />
          </button>
        </div>

        {/* Iter 216h227 — mobile-first layout. Below sm: horizontal
            pill rail across the top so the right pane gets the full
            screen width (otherwise the 200px rail squeezed cards to
            ~140px and step CTAs overlapped descriptions). Above sm:
            the original 200px / 1fr two-column grid. */}
        <div className="flex-1 flex flex-col sm:grid sm:grid-cols-[200px_1fr] min-h-0">
          <nav
            className="account-sidebar flex-shrink-0 border-b sm:border-b-0 sm:border-r account-modal-divider p-2 sm:p-3 flex flex-row sm:flex-col gap-1 overflow-x-auto sm:overflow-y-auto sm:overflow-x-hidden"
            aria-label={t('settings.modal_sections_aria', 'Account sections')}
          >
            {sections.map(({ id, labelKey, label, icon: Icon }) => (
              <button
                key={id}
                type="button"
                onClick={() => setSection(id)}
                className={`flex items-center gap-2 sm:gap-2.5 px-3 py-2 rounded-md text-xs sm:text-sm text-left font-medium transition flex-shrink-0 sm:flex-shrink whitespace-nowrap ${
                  section === id ? 'account-nav-active' : 'account-nav-idle'
                }`}
                data-testid={`account-nav-${id}`}
              >
                <Icon size={15} />
                {NAV_LABELS[id] || t(labelKey, label)}
              </button>
            ))}
          </nav>

          {/* Iter 260 — `flex-1 min-h-0` is required for the mobile flex-col
              layout: without it the pane grows to its full content height and
              overflows the `overflow-hidden` shell, so touch users could never
              scroll down to the password form in Security. */}
          <div className="flex-1 min-h-0 overflow-y-auto p-4 sm:p-6">
            {section === 'profile' && (
              <ProfileSection profile={profile} onProfileUpdate={(p) => setProfile((prev) => ({ ...(prev || {}), ...p }))} />
            )}
            {section === 'onboarding' && (
              <OnboardingSection
                onJumpSection={(id) => setSection(id)}
                onClose={onClose}
                profile={profile}
              />
            )}
            {section === 'security' && <SecuritySection />}
            {section === 'preferences' && <PreferencesSection />}
            {section === 'billing' && <BillingSection billing={billing} onClose={onClose} />}
            {section === 'organisation' && <OrganisationSection billing={billing} profile={profile} />}
            {section === 'suppliers' && <SuppliersSection />}
            {section === 'documents' && <DocumentBrandingSettings API={API} />}
            {section === 'team' && <TeamSection profile={profile} inviteCode={billing?.organization_code} />}
            {section === 'data-export' && <DataExportSection />}
          </div>
        </div>
      </div>
    </div>
  );
}
