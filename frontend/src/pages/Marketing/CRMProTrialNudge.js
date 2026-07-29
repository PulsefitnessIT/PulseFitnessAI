/**
 * CRMProTrialNudge — iter 215dm.
 *
 * In-product upsell nudge shown on Marketing → Contacts when the tenant
 * hits a soft scaling signal (≥250 contacts) and doesn't already have
 * full CRM access. Clicks start a 3-day trial via the existing
 * `/api/me/module-trials/start` endpoint.
 *
 * Behaviour rules:
 *   - Hidden while resolving module status.
 *   - Hidden if user already has full `crm` access.
 *   - Hidden if total contact count below threshold (default 250).
 *   - Hidden if dismissed (localStorage flag `crm_pro_nudge_dismissed`).
 *   - Hidden if the org already has / had a CRM trial
 *     (`trials.crm.ever_started` or an active trial).
 *   - Owner / master admin can start the trial; others see copy that
 *     nudges them to ask their owner.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import { Sparkles, Rocket, X, ShieldCheck } from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

const API = process.env.REACT_APP_BACKEND_URL;
const DISMISS_KEY = 'crm_pro_nudge_dismissed';

export default function CRMProTrialNudge({ totalContacts = 0, threshold = 250 }) {
  const { t } = useTranslation();
  const token = useMemo(() => localStorage.getItem('token'), []);
  const [trialData, setTrialData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [dismissed, setDismissed] = useState(
    typeof window !== 'undefined' && window.localStorage.getItem(DISMISS_KEY) === '1',
  );

  const fetchTrialState = useCallback(async () => {
    if (!token) { setLoading(false); return; }
    try {
      const { data } = await axios.get(`${API}/api/me/module-trials`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setTrialData(data);
    } catch {
      // Silent — endpoint may 401 for some user types; nudge just won't render.
      setTrialData(null);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { fetchTrialState(); }, [fetchTrialState]);

  const hasFullCrm = !!(trialData?.module_access?.crm);
  const crmTrial = trialData?.trials?.crm || {};
  // Hide the nudge once the CRM trial has been started or used — only
  // `available` means the operator still has an unused trial sitting idle.
  const trialEverStarted = (crmTrial.status || 'available') !== 'available';
  const isOwner = !!trialData?.is_owner;
  const trialDays = trialData?.trial_duration_days || 3;

  const handleStart = async () => {
    setStarting(true);
    try {
      await axios.post(
        `${API}/api/me/module-trials/start`,
        { module: 'crm' },
        { headers: { Authorization: `Bearer ${token}` } },
      );
      notify.success(
        t('mkt.cpn_started_title', 'CRM Pro trial started'),
        t('mkt.cpn_started_body', 'You have {{n}} days to explore pipelines, deals and forecasting. Happy selling!', { n: trialDays }),
      );
      // Reload state so the nudge hides + any app-level gates unlock.
      fetchTrialState();
    } catch (e) {
      notifyApiError(notify, e, t('mkt.cpn_start_err', 'Could not start CRM trial'));
    } finally { setStarting(false); }
  };

  const handleDismiss = () => {
    if (typeof window !== 'undefined') window.localStorage.setItem(DISMISS_KEY, '1');
    setDismissed(true);
  };

  if (loading) return null;
  if (dismissed) return null;
  if (hasFullCrm) return null;
  if (trialEverStarted) return null;
  if (totalContacts < threshold) return null;
  if (!trialData) return null;

  return (
    <div
      className="rounded-xl border px-4 py-4 relative flex flex-col sm:flex-row sm:items-center gap-3"
      style={{
        borderColor: 'var(--theme-border)',
        background: 'linear-gradient(135deg, rgb(99 102 241 / 0.10) 0%, rgb(217 70 239 / 0.08) 50%, rgb(56 189 248 / 0.08) 100%)',
      }}
      data-testid="crm-pro-trial-nudge"
    >
      <button
        type="button"
        onClick={handleDismiss}
        aria-label={t('mkt.cpn_dismiss', 'Dismiss')}
        className="absolute top-2 right-2 p-1 rounded hover:bg-black/10"
        data-testid="crm-pro-trial-nudge-dismiss"
      >
        <X size={12} />
      </button>
      <div
        className="h-10 w-10 rounded-xl flex items-center justify-center shrink-0"
        style={{ background: 'linear-gradient(135deg, #6366f1 0%, #d946ef 100%)', color: 'white' }}
      >
        <Rocket size={16} />
      </div>
      <div className="flex-1 min-w-0 pr-6">
        <p className="text-sm font-bold flex flex-wrap items-center gap-1.5" style={{ color: 'var(--theme-text)' }}>
          <Sparkles size={12} style={{ color: '#6366f1' }} />
          {t('mkt.cpn_headline', "You've built a {{n}}-strong contact base.", { n: totalContacts.toLocaleString('en-GB') })}
        </p>
        <p className="text-xs opacity-75 mt-1 max-w-2xl">
          {t('mkt.cpn_body', "That's the size where a pipeline starts paying for itself. Take CRM Pro for a {{n}}-day spin — deals, forecasting, commit-calls and automations, all on the contacts you've already built.", { n: trialDays })}
          <span className="inline-flex items-center gap-1 ml-1.5 opacity-70">
            <ShieldCheck size={11} /> {t('mkt.cpn_no_card', 'No card required.')}
          </span>
        </p>
      </div>
      {isOwner ? (
        <button
          type="button"
          onClick={handleStart}
          disabled={starting}
          className="px-4 py-2 rounded-lg text-sm font-bold text-white shrink-0 disabled:opacity-70"
          style={{ background: 'linear-gradient(135deg, #6366f1 0%, #d946ef 100%)' }}
          data-testid="crm-pro-trial-nudge-start"
        >
          {starting ? t('mkt.cpn_starting', 'Starting…') : t('mkt.cpn_start_cta', 'Start free {{n}}-day trial', { n: trialDays })}
        </button>
      ) : (
        <div className="text-xs opacity-80 shrink-0 sm:text-right" data-testid="crm-pro-trial-nudge-owner-only">
          <span className="font-semibold" style={{ color: 'var(--theme-text)' }}>{t('mkt.cpn_ask_owner', 'Ask your owner to start the trial.')}</span>
        </div>
      )}
    </div>
  );
}
