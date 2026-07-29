/**
 * Memberships Start tab — progressive onboarding checklist (iter 216ah, G1).
 *
 * Data-driven: fetches /memberships/studio/onboarding which computes step
 * completeness from live DB counts, then renders a 5-step checklist.
 *
 * Auto-dismissal: when every step is done (or the operator clicks "Hide
 * this"), the parent (MembershipsConsole) hides the Start tab entirely
 * via the `onAllComplete` callback — see useOnboardingChecklist below.
 */
import { useEffect, useState, useCallback, useRef } from 'react';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import {
  CheckCircle2, Circle, ArrowRight, EyeOff, Sparkles, Loader2, Zap, Upload, X,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import LaunchReadinessPanel from '@/components/shared/LaunchReadinessPanel';
import UpcomingToursPanel from './UpcomingToursPanel';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const authHeaders = () => ({ Authorization: `Bearer ${localStorage.getItem('token')}` });

/** Shared hook — also used by MembershipsConsole to decide whether to
 * render the Start tab button at all. Single source of truth so the tab
 * vanishes the moment the checklist is complete. */
export function useOnboardingChecklist() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/memberships/studio/onboarding`, { headers: authHeaders() });
      setData(r.data);
    } catch {
      setData(null);
    }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  return { data, loading, reload: load };
}

/** Single checklist row. Pulled out so the parent stays focused on
 * orchestration (load + dismiss + render the panel). */
function ChecklistStep({ step, index, onAdvance }) {
  const { t } = useTranslation();
  return (
    <li
      className="rounded-xl p-4 border transition-colors flex items-start gap-3"
      style={{
        background: step.done ? 'var(--theme-surface-hover)' : 'var(--theme-surface)',
        borderColor: step.done ? 'rgba(16,185,129,0.3)' : 'var(--theme-border)',
        opacity: step.done ? 0.75 : 1,
      }}
      data-testid={`mbr-start-step-${step.id}`}
    >
      <div className="pt-0.5">
        {step.done
          ? <CheckCircle2 size={18} className="text-emerald-400" />
          : <Circle size={18} className="text-[color:var(--theme-text-muted)]" />}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[10px] font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)]">
            {t('memberships_console.start_step', 'Step')} {index + 1}
          </span>
          {step.done && (
            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-400">
              {t('memberships_console.start_done', 'Done')}{step.count ? ` · ${step.count}` : ''}
            </span>
          )}
        </div>
        <p className="text-sm font-extrabold mt-0.5" style={{ color: 'var(--theme-text)' }}>{step.title}</p>
        <p className="text-xs mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>{step.note}</p>
      </div>
      {!step.done && (
        <button
          onClick={() => onAdvance(step.cta_tab)}
          className="inline-flex items-center gap-1.5 text-xs font-extrabold px-3 py-2 rounded-lg flex-shrink-0"
          style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
          data-testid={`mbr-start-cta-${step.id}`}
        >
          {step.cta_label} <ArrowRight size={11} />
        </button>
      )}
    </li>
  );
}

export default function MembershipsStartTab({ setTab }) {
  const { t } = useTranslation();
  const { data, loading, reload } = useOnboardingChecklist();
  const [dismissing, setDismissing] = useState(false);
  // Iter 216h249 — inline logo upload modal so the "Add your studio logo"
  // step doesn't punt the operator to a different module's settings screen.
  const [logoModalOpen, setLogoModalOpen] = useState(false);

  const advance = useCallback((ctaTab) => {
    if (ctaTab === 'settings') { setLogoModalOpen(true); return; }
    setTab?.(ctaTab);
  }, [setTab]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 p-10 text-sm text-[color:var(--theme-text-muted)]" data-testid="mbr-start-loading">
        <Loader2 size={14} className="animate-spin" /> {t('memberships_console.start_checking', 'Checking your setup…')}
      </div>
    );
  }
  if (!data) {
    return (
      <div className="p-10 text-sm text-[color:var(--theme-text-muted)]" data-testid="mbr-start-empty">
        {t('memberships_console.start_load_error', "Couldn't load your onboarding checklist.")} <button onClick={reload} className="underline">{t('memberships_console.start_retry', 'Retry')}</button>
      </div>
    );
  }

  const dismiss = async () => {
    if (!window.confirm(t('memberships_console.start_dismiss_confirm', 'Hide this checklist? You can still complete the remaining steps from each tab.'))) return;
    setDismissing(true);
    try {
      await axios.post(`${API}/memberships/studio/onboarding/dismiss`, {}, { headers: authHeaders() });
      notify.success(t('memberships_console.start_dismissed_ok', 'Checklist hidden. Welcome aboard.'));
      await reload();
      window.dispatchEvent(new CustomEvent('memberships-start-dismissed'));
    } catch (e) {
      notifyApiError(notify, e, t('memberships_console.start_dismiss_fail', 'Failed to dismiss'));
    }
    setDismissing(false);
  };

  const { steps, completed, total, percent, all_complete: allComplete } = data;

  return (
    <div className="max-w-4xl" data-testid="mbr-start-tab">
      <div className="flex items-start justify-between gap-4 flex-wrap mb-6">
        <div>
          <p className="text-[10px] font-extrabold uppercase tracking-[0.2em] text-[var(--color-brand-cyan)] flex items-center gap-1">
            <Sparkles size={11} /> {t('memberships_console.start_eyebrow', 'Studio quickstart')}
          </p>
          <h2 className="text-2xl sm:text-3xl tracking-tight font-semibold pulse-font-heading mt-1" style={{ color: 'var(--theme-text)' }}>
            {allComplete ? t('memberships_console.start_title_done', "You're fully set up") : t('memberships_console.start_title', "Let's get your studio live")}
          </h2>
          <p className="text-sm mt-1" style={{ color: 'var(--theme-text-muted)' }}>
            {allComplete
              ? t('memberships_console.start_subtitle_done', 'Every setup step is complete. This panel will disappear on your next visit.')
              : t('memberships_console.start_subtitle', '{{completed}} of {{total}} complete — tackle them in any order, each takes under 2 minutes.', { completed, total })}
          </p>
        </div>
        <button onClick={dismiss} disabled={dismissing}
          className="inline-flex items-center gap-1.5 text-xs font-bold px-3 py-2 rounded-lg border border-[color:var(--theme-border)] hover:bg-white/5"
          data-testid="mbr-start-dismiss">
          {dismissing ? <Loader2 size={12} className="animate-spin" /> : <EyeOff size={12} />}
          {t('memberships_console.start_hide', 'Hide this')}
        </button>
      </div>

      <div className="h-2 rounded-full overflow-hidden mb-6" style={{ background: 'var(--theme-surface-hover)' }} data-testid="mbr-start-progress">
        <div className="h-full transition-all" style={{ width: `${percent}%`, background: 'var(--color-brand-cyan)' }} />
      </div>

      <ul className="space-y-2">
        {steps.map((s, idx) => (
          <ChecklistStep key={s.id} step={s} index={idx} onAdvance={advance} />
        ))}
      </ul>

      {allComplete && (
        <div className="mt-6 rounded-xl p-5 border text-center"
          style={{ background: 'var(--theme-surface)', borderColor: 'rgba(16,185,129,0.3)' }}
          data-testid="mbr-start-all-done">
          <Zap size={20} className="mx-auto text-emerald-400 mb-2" />
          <p className="font-extrabold">{t('memberships_console.start_all_done_title', 'All set. The Start tab auto-hides on next load.')}</p>
          <p className="text-xs text-[color:var(--theme-text-muted)] mt-1">
            {t('memberships_console.start_all_done_note', 'Head to the Dashboard for your KPI strip, or Studio Brain for AI retention insights.')}
          </p>
        </div>
      )}

      {/* Iter 216bc — pre-launch readiness (sender branding + sample data) */}
      <div className="mt-8">
        <LaunchReadinessPanel />
      </div>

      {/* Iter 216h4 — upcoming tour bookings from the public sign-up flow */}
      <div className="mt-6">
        <UpcomingToursPanel compact />
      </div>

      {/* Iter 216h250 — module discovery card. Surfaces the other Pulse Fitness
          modules so a Memberships-first operator knows they can bolt-on
          Operations / CRM / Marketing without leaving the platform. */}
      <ModuleDiscoveryCard />

      {/* Iter 216h249 — inline logo upload modal triggered by the
          "Add your studio logo" checklist step. */}
      {logoModalOpen && (
        <LogoUploadModal onClose={() => { setLogoModalOpen(false); reload(); }} />
      )}
    </div>
  );
}

/* ─────────────────── Module discovery card ─────────────────── */
function ModuleDiscoveryCard() {
  const { t } = useTranslation();
  const otherModules = [
    { id: 'operations', label: t('memberships_console.start_mod_operations', 'Operations'), note: t('memberships_console.start_mod_operations_note', 'Equipment + faults + suppliers') },
    { id: 'crm',        label: t('memberships_console.start_mod_crm', 'CRM'),        note: t('memberships_console.start_mod_crm_note', 'Sales pipeline + deals + quotes') },
    { id: 'marketing',  label: t('memberships_console.start_mod_marketing', 'Marketing'),  note: t('memberships_console.start_mod_marketing_note', 'Campaigns + audiences + ads') },
  ];
  return (
    <div className="mt-8 rounded-2xl border p-5" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }} data-testid="mbr-module-discovery">
      <div className="flex items-start justify-between gap-3 flex-wrap mb-3">
        <div>
          <p className="text-[10px] font-extrabold uppercase tracking-[0.2em] text-[var(--color-brand-cyan)]">{t('memberships_console.start_add_module', 'Add another module')}</p>
          <h3 className="text-base font-semibold mt-1" style={{ color: 'var(--theme-text)' }}>{t('memberships_console.start_unlock_more', 'Unlock more of Pulse Fitness')}</h3>
          <p className="text-xs mt-1" style={{ color: 'var(--theme-text-muted)' }}>{t('memberships_console.start_unlock_note', 'Trial includes everything. After trial, bolt on only what you need.')}</p>
        </div>
        <a
          href="/pricing?from=memberships"
          className="px-3 py-2 rounded-lg text-xs font-extrabold inline-flex items-center gap-1.5"
          style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
          data-testid="mbr-module-discovery-cta"
        >
          {t('memberships_console.start_see_pricing', 'See pricing')} <ArrowRight size={11} />
        </a>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
        {otherModules.map((m) => (
          <div
            key={m.id}
            className="rounded-xl border p-3"
            style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface-hover)' }}
            data-testid={`mbr-module-discovery-${m.id}`}
          >
            <p className="text-xs font-extrabold" style={{ color: 'var(--theme-text)' }}>{m.label}</p>
            <p className="text-[11px] mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>{m.note}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ─────────────────── Logo upload modal ─────────────────── */
function LogoUploadModal({ onClose }) {
  const { t } = useTranslation();
  const inputRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [preview, setPreview] = useState(null);

  const handleFile = async (file) => {
    if (!file) return;
    if (!/^image\/(png|jpeg|jpg)/.test(file.type)) {
      notify.error(t('memberships_console.start_logo_type_err', 'Please choose a PNG or JPEG image.'));
      return;
    }
    setPreview(URL.createObjectURL(file));
    setUploading(true);
    const fd = new FormData();
    fd.append('file', file);
    try {
      await axios.post(`${API}/account/logo`, fd, {
        headers: { ...authHeaders(), 'Content-Type': 'multipart/form-data' },
      });
      notify.success(t('memberships_console.start_logo_ok', 'Logo uploaded — looking sharp.'));
      setTimeout(onClose, 600);
    } catch (e) {
      notifyApiError(notify, e, t('memberships_console.start_logo_fail', 'Logo upload failed'));
      setUploading(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      onClick={onClose}
      data-testid="mbr-logo-modal"
    >
      <div
        className="rounded-2xl border border-[color:var(--theme-border)] bg-[color:var(--theme-surface)] w-full max-w-md p-6 relative"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute right-3 top-3 text-[color:var(--theme-text-muted)] hover:text-white"
          aria-label="Close"
          data-testid="mbr-logo-modal-close"
        >
          <X size={18} />
        </button>
        <p className="text-[10px] font-extrabold uppercase tracking-[0.2em] text-[var(--color-brand-cyan)] flex items-center gap-1">
          <Sparkles size={11} /> {t('memberships_console.start_logo_eyebrow', 'Studio brand')}
        </p>
        <h3 className="text-xl font-semibold mt-1" style={{ color: 'var(--theme-text)' }}>{t('memberships_console.start_logo_title', 'Upload your logo')}</h3>
        <p className="text-xs mt-1 mb-4" style={{ color: 'var(--theme-text-muted)' }}>
          {t('memberships_console.start_logo_desc', 'PNG or JPEG, up to 512×512 px. Appears on your member portal, emails and invoices.')}
        </p>
        {preview && (
          <div className="rounded-xl border border-[color:var(--theme-border)] p-4 mb-4 flex items-center justify-center bg-white/5">
            <img src={preview} alt="logo preview" className="max-h-32 max-w-full object-contain" />
          </div>
        )}
        <input
          ref={inputRef}
          type="file"
          accept="image/png,image/jpeg"
          className="hidden"
          onChange={(e) => handleFile(e.target.files?.[0])}
          data-testid="mbr-logo-input"
        />
        <button
          onClick={() => inputRef.current?.click()}
          disabled={uploading}
          className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-extrabold"
          style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
          data-testid="mbr-logo-pick"
        >
          {uploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
          {uploading ? t('memberships_console.start_logo_uploading', 'Uploading…') : t('memberships_console.start_logo_choose', 'Choose image')}
        </button>
      </div>
    </div>
  );
}
