/**
 * EngineerAccountSettings — Iter 217a.
 *
 * Slide-out account settings drawer for the Engineer App. Triggered from the
 * hamburger menu in `EngineerHomeV2`. Houses one-off onboarding tasks and
 * housekeeping items that previously cluttered the main dashboard / customers
 * page:
 *   • Connect Stripe (payouts) — moved from the home dashboard amber banner.
 *   • Import customers from CSV (+ download template) — moved from
 *     `EngineerCustomers.js` header.
 *   • Support link.
 *   • Sign out.
 *
 * Receives the latest payouts/Stripe-connect status from the parent so the
 * banner copy stays consistent, and exposes an `onChanged` callback that the
 * parent can fire to refresh dashboard data after an import.
 */
import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/App';
import {
  X, CreditCard, Upload, Download, LifeBuoy, LogOut,
  Loader2, ChevronRight, CheckCircle2, AlertTriangle, FileSpreadsheet,
  Sliders, Palette, Sparkles, Star, Percent, PoundSterling, Bell, ShieldCheck,
  Boxes, Warehouse, Wand2, Tags, KeyRound, Mail, Globe, Check,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { useLocalization } from '@/utils/localization';
import { useTranslation } from 'react-i18next';
import { setLanguagePreference } from '@/utils/languagePref';
// Iter 220e7 — Web Push subscribe + per-kind notification prefs.
import NotificationSettings from './NotificationSettings';
import useEngineerOrgBrand from './hooks/useEngineerOrgBrand';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
});

const Row = ({ icon: Icon, title, subtitle, onClick, accent = '#0891b2', testid, right, disabled, danger }) => (
  <button
    type="button"
    onClick={onClick}
    disabled={disabled}
    className={`w-full text-left flex items-center gap-3 px-4 py-3 rounded-xl border transition-colors disabled:opacity-50 ${
      danger
        ? 'border-rose-200 bg-rose-50 hover:bg-rose-100'
        : 'border-slate-200 bg-white hover:bg-slate-50'
    }`}
    data-testid={testid}
  >
    <div
      className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0"
      style={{ background: danger ? '#fee2e2' : `${accent}15` }}
    >
      <Icon size={18} style={{ color: danger ? '#b91c1c' : accent }} />
    </div>
    <div className="flex-1 min-w-0">
      <p className={`text-sm font-bold truncate ${danger ? 'text-rose-900' : 'text-slate-900'}`}>{title}</p>
      {subtitle ? (
        <p className={`text-xs truncate ${danger ? 'text-rose-700' : 'text-slate-500'}`}>{subtitle}</p>
      ) : null}
    </div>
    {right || <ChevronRight size={16} className="text-slate-400 flex-shrink-0" />}
  </button>
);

export default function EngineerAccountSettings({ open, onClose, payouts, attention, onChanged }) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [importing, setImporting] = useState(false);
  const importRef = useRef(null);
  // Iter 220i — lightweight live partner status so the drawer can
  // surface "Active · £30/mo" or "Pending review" without forcing
  // the engineer to open the Partner Dashboard.
  const [partner, setPartner] = useState(null);
  const [subscription, setSubscription] = useState(null);
  const [partnerLoading, setPartnerLoading] = useState(false);
  // Iter 220e7 — Web Push & notification preferences drawer.
  const [notificationOpen, setNotificationOpen] = useState(false);
  // Iter 261 — org name in the drawer header + internal/partner split.
  const orgBrand = useEngineerOrgBrand();
  const attentionItems = (attention?.items) || [];
  // Iter 288 — Pulse-associated (internal) engineers have everything managed by
  // imports + the office, so hide the self-service settings and show only
  // Security · Support · Sign out.
  const internal = orgBrand.internal;

  useEffect(() => {
    if (!open) return undefined;
    let alive = true;
    setPartnerLoading(true);
    axios
      .get(`${API}/partners/me`, auth())
      .then((r) => {
        if (!alive) return;
        const p = r.data?.partner || null;
        setPartner(p);
        // Subscription lives nested on the partner doc (see PartnerDashboard).
        setSubscription((p && p.subscription) || null);
      })
      .catch(() => {
        if (alive) { setPartner(null); setSubscription(null); }
      })
      .finally(() => { if (alive) setPartnerLoading(false); });
    return () => { alive = false; };
  }, [open]);

  if (!open) return null;

  const handleDownloadTemplate = async () => {
    try {
      const r = await axios.get(`${API}/svc/engineer/customers/template.csv`, {
        ...auth(),
        responseType: 'blob',
      });
      const blob = new Blob([r.data], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'engineer-customers-template.csv';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      notify.error(t('service.eng_set_template_failed', 'Could not download template'), err?.response?.data?.detail || err?.message);
    }
  };

  const handleImportClick = () => importRef.current?.click();

  const handleImportFile = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setImporting(true);
    try {
      const fd = new FormData();
      fd.append('file', f);
      const r = await axios.post(`${API}/svc/engineer/customers/import-csv`, fd, {
        ...auth(),
        headers: { ...auth().headers, 'Content-Type': 'multipart/form-data' },
      });
      const d = r.data || {};
      const summary = t('service.eng_set_import_summary', '{{imported}} new · {{merged}} merged · {{skipped}} skipped', { imported: d.imported || 0, merged: d.merged || 0, skipped: (d.skipped || []).length });
      notify.success(t('service.eng_set_import_complete', 'Import complete'), summary);
      if ((d.errors || []).length) {
        notify.error(
          t('service.eng_set_import_rows_failed', '{{count}} row(s) failed', { count: d.errors.length }),
          d.errors.slice(0, 3).map((er) => `Row ${er.row}: ${er.error}`).join('\n')
        );
      }
      if (onChanged) onChanged();
    } catch (err) {
      notify.error(t('service.eng_set_import_failed', 'Import failed'), err?.response?.data?.detail || err?.message);
    } finally {
      setImporting(false);
      if (importRef.current) importRef.current.value = '';
    }
  };

  const handleSignOut = () => {
    // Iter 274 — use the shared auth-context logout: it revokes the HttpOnly
    // session cookie server-side, clears all cached tokens, resets in-memory
    // auth state and hard-navigates. The previous version only removed the
    // localStorage token, so the cookie session survived and the engineer was
    // bounced straight back in.
    onClose?.();
    logout();
  };

  const stripeReady = !!payouts?.ready;
  const stripeConnected = !!payouts?.connected;

  return (
    <div
      className="fixed inset-0 z-40 bg-black/50 flex justify-end"
      onClick={onClose}
      data-testid="engineer-settings-backdrop"
    >
      <aside
        className="bg-white w-full sm:max-w-md h-full shadow-2xl overflow-y-auto flex flex-col"
        onClick={(e) => e.stopPropagation()}
        data-testid="engineer-settings-drawer"
      >
        <header className="sticky top-0 z-10 bg-white border-b border-slate-200 px-4 py-3 flex items-center justify-between">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-cyan-700" data-testid="engineer-settings-brand">
              {orgBrand.label}
            </p>
            <h2 className="text-base font-extrabold text-slate-900">{t('service.eng_set_title', 'Account settings')}</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded-full border border-slate-200 bg-white hover:bg-slate-50"
            aria-label={t('service.eng_set_close', 'Close settings')}
            data-testid="engineer-settings-close"
          >
            <X size={16} />
          </button>
        </header>

        <div className="p-4 space-y-5 flex-1">
          {/* Iter 220j — Attention digest (only renders when something needs
              the engineer's eye). Mirrors the pulsing dot on the hamburger. */}
          {attentionItems.length > 0 && (
            <section data-testid="engineer-settings-section-attention">
              <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500 mb-2">
                {t('service.eng_set_needs_attention', 'Needs your attention')}
              </p>
              <div className="space-y-2">
                {attentionItems.map((it) => {
                  const isRed = it.severity === 'red';
                  return (
                    <button
                      key={it.key}
                      type="button"
                      onClick={() => {
                        if (it.cta_to) { onClose(); navigate(it.cta_to); }
                      }}
                      className={`w-full text-left flex items-start gap-3 px-3 py-2.5 rounded-xl border transition-colors ${
                        isRed
                          ? 'border-rose-200 bg-rose-50 hover:bg-rose-100'
                          : 'border-amber-200 bg-amber-50 hover:bg-amber-100'
                      }`}
                      data-testid={`engineer-attention-item-${it.key}`}
                    >
                      <AlertTriangle
                        size={14}
                        className={`mt-0.5 flex-shrink-0 ${isRed ? 'text-rose-600' : 'text-amber-600'}`}
                      />
                      <div className="flex-1 min-w-0">
                        <p className={`text-xs font-bold ${isRed ? 'text-rose-900' : 'text-amber-900'}`}>
                          {it.label}
                        </p>
                        {it.hint ? (
                          <p className={`text-[11px] mt-0.5 ${isRed ? 'text-rose-700' : 'text-amber-700'}`}>
                            {it.hint}
                          </p>
                        ) : null}
                      </div>
                      <ChevronRight size={14} className={isRed ? 'text-rose-400' : 'text-amber-400'} />
                    </button>
                  );
                })}
              </div>
            </section>
          )}

          {/* Iter 288 — everything below is hidden for internal Pulse engineers
              (managed by imports + the office). Partner/independent engineers
              keep the full self-service set. */}
          {!internal && (
          <>
          {/* Iter 220i — Partner Engineer hub link. Closes the loop so
              engineers can see compliance, referral code + plan from
              inside the Engineer App. */}
          <section data-testid="engineer-settings-section-partner">
            <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500 mb-2">{t('service.eng_set_partner', 'Partner Engineer')}</p>
            <Row
              icon={Sparkles}
              accent="#0e7490"
              title={
                partnerLoading
                  ? t('service.eng_set_partner_loading', 'Loading your plan…')
                  : partner
                    ? t('service.eng_set_partner_plan', 'Plan, referrals & compliance')
                    : t('service.eng_set_partner_network', 'Partner Engineer Network')
              }
              subtitle={(() => {
                if (partnerLoading) return t('service.eng_set_partner_pulling', 'Pulling latest status…');
                if (!partner) return t('service.eng_set_partner_apply', 'Apply to take paid jobs through the Engineer App.');
                const subStatus = subscription?.status;
                const partnerStatus = partner.status;
                const tierLabel = partner.app_fee_tier?.label || '£30/mo';
                if (partnerStatus === 'pending') return t('service.eng_set_partner_pending', 'Application under review · view referral link + upload compliance docs.');
                if (partnerStatus === 'rejected') return t('service.eng_set_partner_rejected', 'Application not approved · tap to update & resubmit.');
                if (partnerStatus === 'suspended') return t('service.eng_set_partner_suspended', 'Access suspended · contact Pulse Fitness support.');
                if (subStatus === 'active' || subStatus === 'trialing') {
                  return t('service.eng_set_partner_active', 'Plan: Active · {{tier}} · view referrals & compliance.', { tier: tierLabel });
                }
                if (subStatus === 'past_due') return t('service.eng_set_partner_past_due', 'Plan: Payment failed · tap to resolve.');
                if (subStatus === 'canceled') return t('service.eng_set_partner_canceled', 'Plan: Cancelled · tap to reactivate.');
                return t('service.eng_set_partner_activate', 'Activate the {{tier}} Partner Plan to unlock the Engineer App.', { tier: tierLabel });
              })()}
              onClick={() => { onClose(); navigate('/partner-engineer'); }}
              testid="engineer-settings-partner-row"
              right={
                partnerLoading
                  ? <Loader2 size={16} className="animate-spin text-teal-500 flex-shrink-0" />
                  : subscription?.status === 'active'
                    ? <CheckCircle2 size={18} className="text-emerald-500 flex-shrink-0" />
                    : partner && partner.status !== 'approved'
                      ? <AlertTriangle size={18} className="text-amber-500 flex-shrink-0" />
                      : <ChevronRight size={16} className="text-slate-400 flex-shrink-0" />
              }
            />
          </section>

          {/* Payouts / Stripe */}
          <section data-testid="engineer-settings-section-payouts">
            <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500 mb-2">{t('service.eng_set_payouts', 'Payouts')}</p>
            <Row
              icon={CreditCard}
              accent="#0e7490"
              title={
                stripeReady
                  ? t('service.eng_set_stripe_connected', 'Stripe connected')
                  : stripeConnected
                    ? t('service.eng_set_stripe_finish', 'Finish Stripe onboarding')
                    : t('service.eng_set_stripe_connect', 'Connect Stripe to take card payments')
              }
              subtitle={
                stripeReady
                  ? t('service.eng_set_stripe_enabled', 'Payouts are enabled on your invoices.')
                  : stripeConnected
                    ? t('service.eng_set_stripe_needed', 'A few details still needed — usually ID or bank account.')
                    : t('service.eng_set_stripe_blurb', 'Connect your Stripe (≈3 min) so customers can pay invoices by card.')
              }
              onClick={() => { onClose(); navigate('/svc/engineer/payouts'); }}
              testid="engineer-settings-stripe-row"
              right={
                stripeReady
                  ? <CheckCircle2 size={18} className="text-emerald-500 flex-shrink-0" />
                  : <AlertTriangle size={18} className="text-amber-500 flex-shrink-0" />
              }
            />
          </section>

          {/* Customers — import */}
          <section data-testid="engineer-settings-section-customers">
            <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500 mb-2">{t('service.eng_set_customers', 'Customers')}</p>
            <div className="space-y-2">
              <Row
                icon={Upload}
                accent="#0891b2"
                title={importing ? t('service.eng_set_importing', 'Importing customers…') : t('service.eng_set_import_customers', 'Import customers from CSV')}
                subtitle={t('service.eng_set_import_customers_sub', 'Bulk-add or merge customer records from a CSV file.')}
                onClick={handleImportClick}
                disabled={importing}
                testid="engineer-settings-import-row"
                right={
                  importing
                    ? <Loader2 size={16} className="animate-spin text-cyan-600 flex-shrink-0" />
                    : <ChevronRight size={16} className="text-slate-400 flex-shrink-0" />
                }
              />
              <Row
                icon={Download}
                accent="#0891b2"
                title="Download CSV template"
                subtitle="Get the import template with example rows."
                onClick={handleDownloadTemplate}
                testid="engineer-settings-template-row"
              />
              <input
                type="file"
                ref={importRef}
                accept=".csv,text/csv"
                onChange={handleImportFile}
                className="hidden"
                data-testid="engineer-settings-import-input"
              />
              <Row
                icon={FileSpreadsheet}
                accent="#0f766e"
                title={t('service.eng_set_open_customers', 'Open my customers')}
                subtitle={t('service.eng_set_open_customers_sub', 'View and edit saved customer records.')}
                onClick={() => { onClose(); navigate('/svc/engineer/customers'); }}
                testid="engineer-settings-customers-row"
              />
            </div>
          </section>

          {/* Iter 220cr — Pricing defaults. Set callout + hourly rate
              ONCE and every new quote/invoice line auto-fills. */}
          {partner && (
            <section data-testid="engineer-settings-section-pricing">
              <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500 mb-2">
                {t('service.eng_set_pricing_defaults', 'Pricing defaults')}
              </p>
              <RatesEditor
                partner={partner}
                onSaved={(updatedPartner) => {
                  setPartner(updatedPartner);
                  onChanged?.();
                }}
              />
            </section>
          )}

          {/* Iter 220ea·21 — Stock & parts. Import is tucked away here
              (off the main catalogue screen) so bulk-import options live
              only in settings. */}
          <section data-testid="engineer-settings-section-stock">
            <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500 mb-2">{t('service.eng_set_stock', 'Stock')}</p>
            <div className="space-y-2">
              <Row
                icon={Boxes}
                accent="#0f766e"
                title={t('service.eng_set_parts_catalogue', 'Parts catalogue')}
                subtitle={t('service.eng_set_parts_catalogue_sub', 'Browse, search and edit your parts catalogue.')}
                onClick={() => { onClose(); navigate('/svc/engineer/catalogue'); }}
                testid="engineer-settings-catalogue-row"
              />
              <Row
                icon={Warehouse}
                accent="#4f46e5"
                title={t('service.eng_set_stock_mgmt', 'Stock management')}
                subtitle={t('service.eng_set_stock_mgmt_sub', 'Office overview — all van stock, transfers, stock-take.')}
                onClick={() => { onClose(); navigate('/svc/engineer/stock-admin'); }}
                testid="engineer-settings-stock-admin-row"
              />
              <Row
                icon={Upload}
                accent="#0891b2"
                title={t('service.eng_set_import_parts', 'Import parts')}
                subtitle={t('service.eng_set_import_parts_sub', 'Bulk-add or update parts from a CSV / Excel spreadsheet.')}
                onClick={() => { onClose(); navigate('/svc/engineer/catalogue?import=1'); }}
                testid="engineer-settings-parts-import-row"
              />
            </div>
          </section>

          {/* Iter 220ea·33 — Legacy report import. One-off migration tool:
              turn historic PDFs/spreadsheets into branded Pulse Fitness PDFs.
              Iter 261 — hidden for internal engineers: their Service Desk
              imports historical reports via Settings instead. */}
          {!orgBrand.internal && (
          <section data-testid="engineer-settings-section-tools">
            <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500 mb-2">{t('service.eng_set_tools', 'Tools')}</p>
            <Row
              icon={Wand2}
              accent="#0e7490"
              title={t('service.eng_set_legacy_import', 'Import legacy reports')}
              subtitle={t('service.eng_set_legacy_import_sub', 'Turn old PDFs/spreadsheets into branded service reports with AI.')}
              onClick={() => { onClose(); navigate('/svc/engineer/legacy-import'); }}
              testid="engineer-settings-legacy-import-row"
            />
          </section>
          )}

          {/* Iter 220 — Work-report custom fields */}
          <section data-testid="engineer-settings-section-work-reports">
            <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500 mb-2">{t('service.eng_set_work_reports', 'Work reports')}</p>
            <Row
              icon={Tags}
              accent="#0891b2"
              title={t('service.eng_set_case_types', 'Case types')}
              subtitle={t('service.eng_set_case_types_sub', 'Repair, PPM & your own job types — each with its own report questions.')}
              onClick={() => { onClose(); navigate('/svc/engineer/case-types'); }}
              testid="engineer-settings-case-types-row"
            />
            <Row
              icon={Sliders}
              accent="#0e7490"
              title={t('service.eng_set_custom_fields', 'Custom report fields')}
              subtitle={t('service.eng_set_custom_fields_sub', 'Add machine-specific questions (e.g. Drag Factor, Current Software).')}
              onClick={() => { onClose(); navigate('/svc/engineer/work-report-fields'); }}
              testid="engineer-settings-work-report-fields-row"
            />
          </section>

          {/* Iter 220i — Branding (logo + colours for PDFs + portal) */}
          <section data-testid="engineer-settings-section-branding">
            <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500 mb-2">{t('service.eng_set_brand', 'Brand')}</p>
            <Row
              icon={Palette}
              accent="#db2777"
              title={t('service.eng_set_logo_colours', 'Logo & colours')}
              subtitle={t('service.eng_set_logo_colours_sub', 'Used on every PDF you email and across your engineer portal.')}
              onClick={() => { onClose(); navigate('/svc/engineer/branding'); }}
              testid="engineer-settings-branding-row"
            />
          </section>

          {/* Iter 220ea·10 — Health & Safety template editor. Lets
              owners / managers edit the pre-job checklist items
              (label + required flag) from the same drawer they
              configure rates + branding in. */}
          <section data-testid="engineer-settings-section-safety">
            <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500 mb-2">
              {t('service.eng_set_health_safety', 'Health & Safety')}
            </p>
            <Row
              icon={ShieldCheck}
              accent="#f59e0b"
              title={t('service.eng_set_hs_checklist', 'Pre-job H&S checklist')}
              subtitle={t('service.eng_set_hs_checklist_sub', 'Edit the tickable items engineers see on Summary before starting work.')}
              onClick={() => { onClose(); navigate('/svc/engineer/h-s-checklist'); }}
              testid="engineer-settings-safety-row"
            />
          </section>

          {/* Iter 220l — Reputation: customer ratings */}
          <section data-testid="engineer-settings-section-ratings">
            <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500 mb-2">{t('service.eng_set_reputation', 'Reputation')}</p>
            <Row
              icon={Star}
              accent="#f59e0b"
              title={t('service.eng_set_my_ratings', 'My ratings')}
              subtitle={t('service.eng_set_my_ratings_sub', 'See every star + comment customers have left.')}
              onClick={() => { onClose(); navigate('/svc/engineer/ratings'); }}
              testid="engineer-settings-ratings-row"
            />
          </section>

          {/* Iter 220l — Tax / VAT toggle */}
          {partner && (
            <section data-testid="engineer-settings-section-tax">
              <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500 mb-2">{t('service.eng_set_tax', 'Tax')}</p>
              <VatToggle
                partner={partner}
                onSaved={(updatedPartner) => {
                  setPartner(updatedPartner);
                  onChanged?.();
                }}
              />
            </section>
          )}

          {/* Iter 220e7 — Notifications */}
          <section data-testid="engineer-settings-section-notifications">
            <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500 mb-2">{t('service.eng_set_alerts', 'Alerts')}</p>
            <Row
              icon={Bell}
              accent="#059669"
              title={t('service.eng_set_notifications', 'Notifications')}
              subtitle={t('service.eng_set_notifications_sub', 'Enable push for new jobs and customer responses, snooze, and per-type toggles.')}
              onClick={() => setNotificationOpen(true)}
              testid="engineer-settings-notifications-row"
              right={<ChevronRight size={16} className="text-slate-300 flex-shrink-0" />}
            />
          </section>
          </>
          )}

          {/* Language — offline-safe quick-switch (EN/FR/DE). Shown to every
              engineer, including internal Pulse engineers. Uses
              setLanguagePreference so the choice sticks even with no signal
              and syncs to the account when back online. */}
          <section data-testid="engineer-settings-section-language">
            <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500 mb-2">{t('service.eng_set_language', 'Language')}</p>
            <div className="rounded-2xl border border-slate-200 bg-white p-3">
              <div className="flex items-center gap-3 mb-3">
                <div className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0" style={{ background: '#0891b215' }}>
                  <Globe size={18} style={{ color: '#0891b2' }} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-bold text-slate-900">{t('service.eng_set_language_title', 'App language')}</p>
                  <p className="text-xs text-slate-500">{t('service.eng_set_language_sub', 'Changes apply instantly and stay set even offline.')}</p>
                </div>
              </div>
              <div className="grid grid-cols-3 gap-2" data-testid="engineer-language-switch">
                {[{ code: 'en', label: 'English' }, { code: 'fr', label: 'Français' }, { code: 'de', label: 'Deutsch' }].map((l) => {
                  const active = (i18n.language || 'en').split('-')[0] === l.code;
                  return (
                    <button
                      key={l.code}
                      type="button"
                      onClick={() => setLanguagePreference(l.code)}
                      aria-pressed={active}
                      className={`inline-flex items-center justify-center gap-1.5 px-2 py-2 rounded-lg border text-xs font-bold transition-colors ${
                        active
                          ? 'bg-cyan-600 text-white border-cyan-600'
                          : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50'
                      }`}
                      data-testid={`engineer-language-${l.code}`}
                    >
                      {active ? <Check size={13} /> : null}
                      {l.label}
                    </button>
                  );
                })}
              </div>
            </div>
          </section>

          {/* Iter 288 — Security (login details). Shown to every engineer;
              for internal Pulse engineers this is the primary section. */}
          <section data-testid="engineer-settings-section-security">
            <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500 mb-2">{t('service.eng_set_security', 'Security')}</p>
            <SecurityEditor email={user?.email} />
          </section>

          {/* Support */}
          <section data-testid="engineer-settings-section-support">
            <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500 mb-2">{t('service.eng_set_help', 'Help')}</p>
            <Row
              icon={LifeBuoy}
              accent="#0284c7"
              title={t('service.eng_set_support', 'Support')}
              subtitle={t('service.eng_set_support_sub', 'Chat with the Pulse Fitness team or browse the help centre.')}
              onClick={() => { onClose(); navigate('/support'); }}
              testid="engineer-settings-support-row"
            />
          </section>

          {/* Account */}
          <section data-testid="engineer-settings-section-account">
            <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500 mb-2">{t('service.eng_set_account', 'Account')}</p>
            <Row
              icon={LogOut}
              danger
              title={t('service.eng_set_sign_out', 'Sign out')}
              subtitle={t('service.eng_set_sign_out_sub', 'End your session on this device.')}
              onClick={handleSignOut}
              testid="engineer-settings-signout-row"
              right={<ChevronRight size={16} className="text-rose-400 flex-shrink-0" />}
            />
          </section>
        </div>

        <footer className="px-4 py-3 border-t border-slate-200 text-[11px] text-slate-400 text-center">
          {t('service.eng_set_footer', 'Pulse Fitness Engineer · v2')}
        </footer>
      </aside>

      {/* Iter 220e7 — Notification drawer */}
      {notificationOpen && (
        <NotificationSettings onClose={() => setNotificationOpen(false)} />
      )}
    </div>
  );
}


// ─── SecurityEditor ──────────────────────────────────────────────
// Iter 288. Shows the engineer's login email (read-only) and an in-app
// change-password form (reuses the existing /account/change-password
// endpoint — no auth logic changed here).
function SecurityEditor({ email }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [saving, setSaving] = useState(false);

  const save = async () => {
    if (!current || !next) { notify.error(t('service.eng_sec_enter_pw', 'Enter your current and new password')); return; }
    if (next !== confirm) { notify.error(t('service.eng_sec_pw_mismatch', 'New passwords do not match')); return; }
    setSaving(true);
    try {
      await axios.post(`${API}/account/change-password`,
        { current_password: current, new_password: next }, auth());
      notify.success(t('service.eng_sec_pw_updated', 'Password updated'), t('service.eng_sec_pw_updated_sub', 'Use your new password next time you sign in.'));
      setCurrent(''); setNext(''); setConfirm(''); setOpen(false);
    } catch (e) {
      notify.error(t('service.eng_sec_pw_failed', 'Could not update password'), e?.response?.data?.detail || e?.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-3 space-y-3" data-testid="engineer-security-editor">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0" style={{ background: '#0891b215' }}>
          <Mail size={18} style={{ color: '#0891b2' }} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-wide text-slate-500">{t('service.eng_sec_login_email', 'Login email')}</p>
          <p className="text-sm font-bold text-slate-900 truncate" data-testid="engineer-security-email">{email || '—'}</p>
        </div>
      </div>

      {!open ? (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="w-full inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-sm font-bold text-slate-900"
          data-testid="engineer-security-change-toggle"
        >
          <KeyRound size={15} className="text-cyan-700" /> {t('service.eng_sec_change_pw', 'Change password')}
        </button>
      ) : (
        <div className="space-y-2" data-testid="engineer-security-form">
          <PwField label={t('service.eng_sec_current_pw', 'Current password')} value={current} onChange={setCurrent} testid="engineer-security-current" />
          <PwField label={t('service.eng_sec_new_pw', 'New password')} value={next} onChange={setNext} testid="engineer-security-new" />
          <PwField label={t('service.eng_sec_confirm_pw', 'Confirm new password')} value={confirm} onChange={setConfirm} testid="engineer-security-confirm" />
          <div className="flex gap-2 pt-1">
            <button
              type="button"
              onClick={() => { setOpen(false); setCurrent(''); setNext(''); setConfirm(''); }}
              className="flex-1 px-3 py-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-xs font-bold text-slate-700"
              data-testid="engineer-security-cancel"
            >
              {t('service.eng_sec_cancel', 'Cancel')}
            </button>
            <button
              type="button"
              onClick={save}
              disabled={saving}
              className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-700 text-white text-xs font-bold disabled:opacity-50"
              data-testid="engineer-security-save"
            >
              {saving ? <Loader2 size={12} className="animate-spin" /> : null}
              {saving ? t('service.eng_sec_saving', 'Saving…') : t('service.eng_sec_update_pw', 'Update password')}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function PwField({ label, value, onChange, testid }) {
  return (
    <label className="block">
      <span className="text-[10px] font-bold uppercase tracking-wide text-slate-500">{label}</span>
      <input
        type="password"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full text-sm border border-slate-200 rounded px-2 py-1.5 bg-white"
        autoComplete="off"
        data-testid={testid}
      />
    </label>
  );
}


// ─── RatesEditor ─────────────────────────────────────────────────
// Iter 220cr. Lets the engineer set their callout fee + hourly
// labour rate + mileage rate + parts markup ONCE, so every new
// quote/invoice line auto-fills with the right number.
function RatesEditor({ partner, onSaved }) {
  const { t } = useTranslation();
  const sym = useLocalization().currency_symbol || '£';
  const initial = partner?.rates || {};
  const [callout, setCallout] = useState(initial.callout_fee ?? '');
  const [hourly, setHourly] = useState(initial.labour_rate_per_hour ?? '');
  const [mileage, setMileage] = useState(initial.mileage_rate ?? '');
  const [markup, setMarkup] = useState(initial.parts_markup_pct ?? '');
  const [saving, setSaving] = useState(false);

  const num = (v) => (v === '' || v === null || v === undefined ? null : Number(v));
  const dirty = (
    num(callout) !== (initial.callout_fee ?? null)
    || num(hourly) !== (initial.labour_rate_per_hour ?? null)
    || num(mileage) !== (initial.mileage_rate ?? null)
    || num(markup) !== (initial.parts_markup_pct ?? null)
  );

  const save = async () => {
    setSaving(true);
    try {
      const payload = {};
      if (callout !== '') payload.callout_fee = Number(callout);
      if (hourly !== '')  payload.labour_rate_per_hour = Number(hourly);
      if (mileage !== '') payload.mileage_rate = Number(mileage);
      if (markup !== '')  payload.parts_markup_pct = Number(markup);
      const r = await axios.put(`${API}/partners/me/rates`, payload, auth());
      notify.success(t('service.eng_rates_saved', 'Pricing saved'), t('service.eng_rates_saved_sub', 'New quotes will use these defaults.'));
      onSaved?.(r.data?.partner || null);
    } catch (e) {
      notify.error(t('service.eng_rates_save_failed', 'Save failed'), e?.response?.data?.detail || e?.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="rounded-2xl border border-slate-200 bg-white p-3 space-y-3"
      data-testid="engineer-rates-editor"
    >
      <p className="text-[11px] text-slate-500 leading-snug">
        {t('service.eng_rates_blurb', 'Auto-populate every new quote/invoice with your standard rates. Leave a field blank to skip — you can still override per line.')}
      </p>
      <div className="grid grid-cols-2 gap-2">
        <RateField
          icon={PoundSterling}
          label={t('service.eng_rates_callout', 'Callout fee')}
          unit={sym}
          value={callout}
          onChange={setCallout}
          testid="engineer-rate-callout"
        />
        <RateField
          icon={PoundSterling}
          label={t('service.eng_rates_hourly', 'Hourly labour')}
          unit={`${sym}/hr`}
          value={hourly}
          onChange={setHourly}
          testid="engineer-rate-hourly"
        />
        <RateField
          icon={PoundSterling}
          label={t('service.eng_rates_mileage', 'Mileage')}
          unit={`${sym}/mi`}
          value={mileage}
          onChange={setMileage}
          testid="engineer-rate-mileage"
        />
        <RateField
          icon={Percent}
          label={t('service.eng_rates_markup', 'Parts markup')}
          unit="%"
          value={markup}
          onChange={setMarkup}
          testid="engineer-rate-parts-markup"
        />
      </div>
      {dirty && (
        <button
          type="button"
          onClick={save}
          disabled={saving}
          className="w-full inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-700 text-white text-xs font-bold disabled:opacity-50"
          data-testid="engineer-rates-save"
        >
          {saving ? <Loader2 size={12} className="animate-spin" /> : null}
          {saving ? t('service.eng_sec_saving', 'Saving…') : t('service.eng_rates_save', 'Save pricing defaults')}
        </button>
      )}
    </div>
  );
}

function RateField({ icon: Icon, label, unit, value, onChange, testid }) {
  return (
    <label className="block">
      <span className="text-[10px] font-bold uppercase tracking-wide text-slate-500 inline-flex items-center gap-1">
        <Icon size={10} /> {label}
      </span>
      <div className="mt-1 relative">
        <input
          type="number"
          inputMode="decimal"
          min="0"
          step="0.01"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full text-sm tabular-nums border border-slate-200 rounded px-2 py-1.5 bg-white pr-12"
          placeholder="0.00"
          data-testid={testid}
        />
        <span className="absolute right-2 top-1/2 -translate-y-1/2 text-[10px] font-semibold text-slate-400">
          {unit}
        </span>
      </div>
    </label>
  );
}


// ─── VatToggle ───────────────────────────────────────────────────
// Iter 220l. Lets sole-trader engineers below the £85k VAT threshold
// flag themselves as not-VAT-registered so every invoice + quote PDF
// from them hides the VAT line. One-time tick → everything Just Works.
function VatToggle({ partner, onSaved }) {
  const { t } = useTranslation();
  const initialReg = partner?.vat_registered !== false; // default True
  const [registered, setRegistered] = useState(initialReg);
  const [vatNumber, setVatNumber] = useState(partner?.vat_number || '');
  const [saving, setSaving] = useState(false);
  const dirty = (
    registered !== initialReg
    || (registered && (vatNumber || '').trim() !== (partner?.vat_number || ''))
  );

  const save = async () => {
    setSaving(true);
    try {
      const r = await axios.put(`${API}/partners/me/tax-settings`, {
        vat_registered: registered,
        vat_number: registered ? vatNumber : null,
      }, auth());
      notify.success(t('service.eng_vat_saved', 'Tax settings saved'), t('service.eng_vat_saved_sub', 'Your future invoices will use this.'));
      onSaved?.(r.data?.partner || null);
    } catch (e) {
      notify.error(t('service.eng_rates_save_failed', 'Save failed'), e?.response?.data?.detail || e?.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-3 space-y-3" data-testid="engineer-vat-toggle">
      <label className="flex items-start gap-3 cursor-pointer">
        <input
          type="checkbox"
          checked={registered}
          onChange={(e) => setRegistered(e.target.checked)}
          className="mt-0.5 h-4 w-4 rounded border-slate-300 text-cyan-600 focus:ring-cyan-500"
          data-testid="engineer-vat-registered-checkbox"
        />
        <div className="flex-1 min-w-0">
          <p className="text-xs font-bold text-slate-900">{t('service.eng_vat_registered', 'I am VAT-registered')}</p>
          <p className="text-[11px] text-slate-500 leading-snug mt-0.5">
            {t('service.eng_vat_blurb', 'Uncheck if you trade below the £85k VAT threshold — your invoice PDFs will hide VAT and read "Not chargeable".')}
          </p>
        </div>
        <Percent size={14} className="text-slate-400 mt-1" />
      </label>
      {registered && (
        <div data-testid="engineer-vat-number-block">
          <label htmlFor="vat-num" className="text-[10px] font-bold uppercase tracking-wide text-slate-500">
            {t('service.eng_vat_number', 'VAT registration number')}
          </label>
          <input
            id="vat-num"
            type="text"
            value={vatNumber}
            onChange={(e) => setVatNumber(e.target.value.toUpperCase())}
            placeholder="GB123456789"
            className="mt-1 w-full text-xs font-mono border border-slate-200 rounded px-2 py-1.5"
            data-testid="engineer-vat-number-input"
          />
        </div>
      )}
      {dirty && (
        <button
          type="button"
          onClick={save}
          disabled={saving}
          className="w-full inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-700 text-white text-xs font-bold disabled:opacity-50"
          data-testid="engineer-vat-save"
        >
          {saving ? <Loader2 size={12} className="animate-spin" /> : null}
          {saving ? t('service.eng_sec_saving', 'Saving…') : t('service.eng_vat_save', 'Save tax settings')}
        </button>
      )}
    </div>
  );
}
