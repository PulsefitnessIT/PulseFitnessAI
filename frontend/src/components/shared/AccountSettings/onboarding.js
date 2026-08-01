import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { toast } from 'sonner';
import { Check, Loader2, Rocket, ChevronDown, ClipboardList, Upload, ArrowLeft } from 'lucide-react';
import { API, useAuthHeaders } from './shared';
import { useNavigate } from 'react-router-dom';
import EquipmentImportInline from './EquipmentImportInline';
import QrPrintInline from './QrPrintInline';
import StripeConnectErrorBanner from '@/components/shared/StripeConnectErrorBanner';

const PORTAL_STATUS_IDS = ['in_progress', 'ready_for_review', 'complete'];

function CustomerPortalPanel() {
  const { t } = useTranslation();
  const headers = useAuthHeaders();
  const PORTAL_STATUSES = [
    { id: 'in_progress', label: t('settings.ob_status_in_progress', 'In progress') },
    { id: 'ready_for_review', label: t('settings.ob_status_ready', 'Ready for review') },
    { id: 'complete', label: t('settings.ob_status_complete', 'Complete') },
  ];
  const [portal, setPortal] = useState(null);
  const [loading, setLoading] = useState(true);
  const [savingStep, setSavingStep] = useState(null);

  const load = async () => {
    try {
      const { data } = await axios.get(`${API}/onboarding/portal/me`, { headers: headers() });
      setPortal(data);
    } catch {
      setPortal(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const setStep = async (stepId, status) => {
    setSavingStep(stepId);
    try {
      await axios.patch(`${API}/onboarding/portal/me/steps/${stepId}`, { status }, { headers: headers() });
      await load();
      toast.success(t('settings.ob_step_updated', 'Step updated'));
    } catch (e) {
      toast.error(e.response?.data?.detail || t('settings.ob_step_failed', 'Could not update step'));
    } finally {
      setSavingStep(null);
    }
  };

  if (loading || !portal) return null;

  const pct = portal.progress?.percent ?? 0;
  const groups = (portal.steps || []).reduce((acc, s) => { (acc[s.group] = acc[s.group] || []).push(s); return acc; }, {});

  return (
    <div className="space-y-4 pb-5 mb-5 border-b" style={{ borderColor: 'var(--theme-border)' }} data-testid="customer-onboarding-portal">
      <div className="flex items-center gap-2">
        <Rocket size={16} style={{ color: 'var(--brand-color, var(--color-brand-blue))' }} />
        <div>
          <h3 className="account-section-title">{t('settings.ob_your_onboarding', 'Your onboarding')}</h3>
          <p className="account-section-sub">
            {t('settings.ob_required_complete', '{{done}} of {{total}} required steps complete', { done: portal.progress?.required_complete ?? 0, total: portal.progress?.required_total ?? 0 })}
            {portal.go_live_target ? ` · ${t('settings.ob_go_live', 'go-live target')} ${String(portal.go_live_target).slice(0, 10)}` : ''}
          </p>
        </div>
      </div>
      <div className="rounded-full overflow-hidden h-2 w-full" style={{ background: 'var(--theme-border-soft)' }}>
        <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, background: 'var(--brand-color, var(--color-brand-blue))' }} data-testid="portal-progress" />
      </div>
      <div className="space-y-4">
        {Object.entries(groups).map(([grp, steps]) => (
          <div key={grp}>
            <p className="text-[10px] uppercase tracking-wider font-semibold mb-1.5" style={{ color: 'var(--theme-text-muted)' }}>{grp}</p>
            <div className="space-y-1.5">
              {steps.map((s) => (
                <div key={s.id} className="account-card rounded-lg p-2.5 flex items-center gap-2" data-testid={`portal-step-${s.id}`}>
                  <div className="w-4 h-4 rounded-full flex items-center justify-center flex-shrink-0"
                       style={{ background: s.status === 'complete' ? 'var(--brand-color, var(--color-brand-blue))' : 'transparent', border: s.status === 'complete' ? 'none' : '1.5px solid var(--theme-border)' }}>
                    {s.status === 'complete' && <Check size={10} color="#FFFFFF" strokeWidth={3} />}
                  </div>
                  <span className="flex-1 text-sm" style={{ color: 'var(--theme-text)' }}>
                    {s.label}{s.optional && <span className="text-[10px] ml-1" style={{ color: 'var(--theme-text-muted)' }}>{t('settings.ob_optional', '(optional)')}</span>}
                  </span>
                  <div className="relative flex items-center">
                    {savingStep === s.id && <Loader2 size={13} className="animate-spin mr-1.5" style={{ color: 'var(--theme-text-muted)' }} />}
                    <select
                      value={PORTAL_STATUSES.some((o) => o.id === s.status) ? s.status : ''}
                      onChange={(e) => setStep(s.id, e.target.value)}
                      disabled={savingStep === s.id}
                      className="account-input account-input-sm pr-6 appearance-none"
                      style={{ width: 140 }}
                      data-testid={`portal-step-status-${s.id}`}
                    >
                      {!PORTAL_STATUSES.some((o) => o.id === s.status) && <option value="" disabled>{t('settings.ob_update', 'Update…')}</option>}
                      {PORTAL_STATUSES.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
                    </select>
                    <ChevronDown size={12} className="absolute right-2 pointer-events-none" style={{ color: 'var(--theme-text-muted)' }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Pre-Install Site Survey customer portal ─────────────────────────
function PortalField({ f, value, onChange }) {
  const { t } = useTranslation();
  const label = (
    <div className="text-[11px] font-semibold uppercase tracking-wide mb-1" style={{ color: 'var(--theme-text-muted)' }}>{f.label}</div>
  );
  if (f.type === 'boolean') {
    return (
      <label className="block">{label}
        <div className="flex gap-2">
          {[[t('settings.ob_yes', 'Yes'), true], [t('settings.ob_no', 'No'), false]].map(([lbl, val]) => (
            <button key={String(val)} type="button" onClick={() => onChange(val)}
              className="px-3 py-1.5 text-xs font-medium rounded-md border"
              style={value === val
                ? { background: 'var(--brand-color, var(--color-brand-blue))', color: '#fff', borderColor: 'transparent' }
                : { borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
              data-testid={`survey-portal-field-${f.key}-${val ? 'yes' : 'no'}`}>{lbl}</button>
          ))}
        </div>
      </label>
    );
  }
  if (f.type === 'select') {
    return (
      <label className="block">{label}
        <select className="account-input" value={value || ''} onChange={(e) => onChange(e.target.value)} data-testid={`survey-portal-field-${f.key}`}>
          <option value="">—</option>
          {(f.options || []).map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      </label>
    );
  }
  if (f.type === 'textarea') {
    return (<label className="block">{label}<textarea className="account-input" style={{ height: 64, padding: 8 }} value={value || ''} onChange={(e) => onChange(e.target.value)} data-testid={`survey-portal-field-${f.key}`} /></label>);
  }
  const inputType = f.type === 'number' ? 'number' : (f.type === 'date' ? 'date' : 'text');
  return (<label className="block">{label}<input className="account-input" type={inputType} value={value ?? ''} onChange={(e) => onChange(e.target.value)} data-testid={`survey-portal-field-${f.key}`} /></label>);
}

function SurveyPortalDetail({ survey, onBack, headers }) {
  const { t } = useTranslation();
  const [data, setData] = useState(survey.data || {});
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [attachments, setAttachments] = useState([]);
  const [cat, setCat] = useState('floor_plans');
  const schema = survey.schema || [];
  const uploadCats = survey.upload_categories || [];

  const loadAtt = async () => {
    try {
      const { data: r } = await axios.get(`${API}/survey-portal/surveys/${survey.id}/attachments`, { headers: headers() });
      setAttachments(r.attachments || []);
    } catch { /* ignore */ }
  };
  useEffect(() => { loadAtt(); /* eslint-disable-next-line */ }, []);

  const setField = (sec, key, val) => setData((d) => ({ ...d, [sec]: { ...(d[sec] || {}), [key]: val } }));
  const setContact = (idx, key, val) => setData((d) => { const a = [...(d.site_contacts || [])]; a[idx] = { ...(a[idx] || {}), [key]: val }; return { ...d, site_contacts: a }; });
  const addContact = () => setData((d) => ({ ...d, site_contacts: [...(d.site_contacts || []), {}] }));
  const removeContact = (idx) => setData((d) => ({ ...d, site_contacts: (d.site_contacts || []).filter((_, i) => i !== idx) }));

  const save = async () => {
    setSaving(true);
    try {
      await axios.put(`${API}/survey-portal/surveys/${survey.id}`, { data }, { headers: headers() });
      toast.success(t('settings.ob_survey_sent', 'Thank you — your information has been sent to the installation team'));
      onBack(true);
    } catch (e) { toast.error(e.response?.data?.detail || t('settings.ob_survey_save_failed', 'Could not save')); } finally { setSaving(false); }
  };
  const upload = async (file) => {
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData(); fd.append('file', file);
      await axios.post(`${API}/survey-portal/surveys/${survey.id}/attachments?category=${cat}`, fd, { headers: { ...headers() } });
      toast.success(t('settings.ob_file_uploaded', 'File uploaded')); await loadAtt();
    } catch (e) { toast.error(e?.response?.status === 413 ? t('settings.ob_file_too_large', 'File too large (max 25MB)') : t('settings.ob_upload_failed', 'Upload failed')); } finally { setUploading(false); }
  };

  return (
    <div className="space-y-4" data-testid="survey-portal-detail">
      <button onClick={() => onBack(false)} className="account-btn-secondary" data-testid="survey-portal-back"><ArrowLeft size={13} /> {t('settings.ob_back_surveys', 'Back to surveys')}</button>
      <div>
        <h3 className="account-section-title">{survey.reference} — {survey.site_name || t('settings.ob_your_site', 'Your site')}</h3>
        <p className="account-section-sub">{t('settings.ob_survey_detail_sub', 'Please confirm the details below and upload a floor plan or site photos to help our installation team prepare.')}</p>
      </div>

      {schema.map((sec) => (
        <div key={sec.id} className="account-card rounded-lg p-3" data-testid={`survey-portal-section-${sec.id}`}>
          <p className="text-xs font-bold mb-2" style={{ color: 'var(--theme-text)' }}>{sec.title}</p>
          {sec.repeatable ? (
            <div className="space-y-3">
              {(data[sec.id] || []).map((item, idx) => (
                <div key={idx} className="rounded-md border p-2.5" style={{ borderColor: 'var(--theme-border)' }}>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                    {sec.fields.map((f) => <PortalField key={f.key} f={f} value={item[f.key]} onChange={(v) => setContact(idx, f.key, v)} />)}
                  </div>
                  <button onClick={() => removeContact(idx)} className="mt-2 text-[11px]" style={{ color: 'var(--color-error-ios, #ef4444)' }}>{t('settings.ob_remove', 'Remove')}</button>
                </div>
              ))}
              <button onClick={addContact} className="account-btn-secondary" data-testid="survey-portal-add-contact">{t('settings.ob_add_contact', '+ Add contact')}</button>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              {sec.fields.map((f) => <PortalField key={f.key} f={f} value={(data[sec.id] || {})[f.key]} onChange={(v) => setField(sec.id, f.key, v)} />)}
            </div>
          )}
        </div>
      ))}

      <div className="account-card rounded-lg p-3" data-testid="survey-portal-uploads">
        <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
          <p className="text-xs font-bold" style={{ color: 'var(--theme-text)' }}>{t('settings.ob_floor_plan', 'Floor plan / photos')}</p>
          <div className="flex items-center gap-2">
            <select className="account-input account-input-sm" style={{ width: 160 }} value={cat} onChange={(e) => setCat(e.target.value)} data-testid="survey-portal-upload-cat">
              {uploadCats.map((u) => <option key={u.key} value={u.key}>{u.label}</option>)}
            </select>
            <label className="account-btn-secondary cursor-pointer" data-testid="survey-portal-upload-btn">
              {uploading ? <Loader2 size={13} className="animate-spin" /> : <Upload size={13} />} {t('settings.ob_upload', 'Upload')}
              <input type="file" className="hidden" accept="image/*,.pdf,.dwg,.dxf" onChange={(e) => upload(e.target.files?.[0])} />
            </label>
          </div>
        </div>
        {attachments.length === 0 ? <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{t('settings.ob_no_files', 'No files uploaded yet.')}</p> : (
          <div className="space-y-1">
            {attachments.map((a) => (
              <div key={a.id} className="text-xs flex items-center gap-2" style={{ color: 'var(--theme-text)' }}>
                <Check size={12} style={{ color: 'var(--brand-color, var(--color-brand-blue))' }} /> {a.original_filename}
                <span className="text-[10px]" style={{ color: 'var(--theme-text-muted)' }}>({a.category?.replace(/_/g, ' ')})</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="flex justify-end">
        <button onClick={save} disabled={saving} className="account-btn-primary" data-testid="survey-portal-save">
          {saving ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />} {t('settings.ob_send_install', 'Send to installation team')}
        </button>
      </div>
    </div>
  );
}

function SurveyPortalPanel() {
  const { t } = useTranslation();
  const headers = useAuthHeaders();
  const [surveys, setSurveys] = useState([]);
  const [loading, setLoading] = useState(true);
  const [openSurvey, setOpenSurvey] = useState(null);

  const load = async () => {
    try {
      const { data } = await axios.get(`${API}/survey-portal/surveys`, { headers: headers() });
      setSurveys(data.enabled ? (data.surveys || []) : []);
    } catch { setSurveys([]); } finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const openOne = async (id) => {
    try {
      const { data } = await axios.get(`${API}/survey-portal/surveys/${id}`, { headers: headers() });
      setOpenSurvey(data);
    } catch (e) { toast.error(t('settings.ob_open_survey_failed', 'Could not open survey')); }
  };

  if (loading || surveys.length === 0) return null;

  if (openSurvey) {
    return (
      <div className="pb-5 mb-5 border-b" style={{ borderColor: 'var(--theme-border)' }}>
        <SurveyPortalDetail survey={openSurvey} headers={headers}
          onBack={(refresh) => { setOpenSurvey(null); if (refresh) load(); }} />
      </div>
    );
  }

  return (
    <div className="space-y-3 pb-5 mb-5 border-b" style={{ borderColor: 'var(--theme-border)' }} data-testid="survey-portal-panel">
      <div className="flex items-center gap-2">
        <ClipboardList size={16} style={{ color: 'var(--brand-color, var(--color-brand-blue))' }} />
        <div>
          <h3 className="account-section-title">{t('settings.ob_preinstall_title', 'Pre-Install Site Surveys')}</h3>
          <p className="account-section-sub">{t('settings.ob_preinstall_sub', 'Your installer needs a few site details. Please review and add any missing information.')}</p>
        </div>
      </div>
      <div className="space-y-1.5">
        {surveys.map((s) => (
          <button key={s.id} onClick={() => openOne(s.id)} className="account-card rounded-lg p-3 w-full text-left flex items-center gap-2" data-testid={`survey-portal-row-${s.id}`}>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold truncate" style={{ color: 'var(--theme-text)' }}>{s.reference} — {s.site_name || t('settings.ob_your_site', 'Your site')}</p>
              <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{t('settings.ob_info_requested', 'Information requested')}{s.target_install_date ? ` · ${t('settings.ob_target_install', 'target install')} ${String(s.target_install_date).slice(0, 10)}` : ''}</p>
            </div>
            <span className="text-[10px] font-bold uppercase px-2 py-1 rounded" style={{ background: 'color-mix(in srgb, var(--brand-color, #0055FF) 15%, transparent)', color: 'var(--brand-color, var(--color-brand-blue))' }}>{t('settings.ob_action_needed', 'Action needed')}</span>
          </button>
        ))}
      </div>
    </div>
  );
}


export default function OnboardingSection({ onJumpSection, onClose, profile }) {
  const { t } = useTranslation();
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
    const isMOD = at.startsWith('mod_') || !!profile?.is_mod_user;
    const isPulse = at === 'pulse_pro' || at === 'lite' || isMOD;
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
      toast.error(t('settings.ob_stripe_failed', 'Could not start Stripe onboarding'));
    } catch (e) {
      const detail = e.response?.data?.detail;
      const code = (typeof detail === 'object' && detail) ? detail.code : null;
      if (code === 'stripe_connect_profile_incomplete' || code === 'stripe_connect_not_enabled') {
        // Persistent banner with the fix link (survives the failed redirect).
        setStripeError(detail);
      }
      toast.error((typeof detail === 'object' ? detail?.message : detail) || t('settings.ob_stripe_failed', 'Could not start Stripe onboarding'));
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
    return <div className="text-sm" style={{ color: 'var(--theme-text-muted)' }}>{t('settings.ob_loading_checklist', 'Loading checklist…')}</div>;
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
      <SurveyPortalPanel />
      <CustomerPortalPanel />
      <div>
        <h3 className="account-section-title">{t('settings.ob_setup_checklist', 'Setup checklist')}</h3>
        <p className="account-section-sub">
          {t('settings.ob_steps_complete', '{{done}} of {{total}} steps complete — finish them in any order.', { done: data?.completed_count ?? 0, total: data?.total ?? 0 })}
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
                  className={`text-sm font-semibold`}
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
              {s.completed ? t('settings.ob_review', 'Review') : (s.cta_label || t('settings.ob_open', 'Open'))}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

