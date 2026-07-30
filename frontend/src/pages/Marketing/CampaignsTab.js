/* Campaigns tab — list + minimal builder + send */
import { useEffect, useState } from 'react';
import axios from 'axios';
import { Mail, Plus, Send, Loader2, CheckCircle2, Sparkles, UserPlus, TrendingDown, Calendar, UserCheck, CreditCard, Share2, BarChart3, X, Pencil, Trash2, RotateCcw, FlaskConical, Trophy, Megaphone } from 'lucide-react';
import { notify, useConfirm } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import HelpHint from '@/components/HelpHint';
import EmptyState from '@/components/shared/EmptyState';
import { useTranslation } from 'react-i18next';

const TEMPLATE_ICONS = {
  'user-plus': UserPlus, 'trending-down': TrendingDown, calendar: Calendar,
  'user-check': UserCheck, 'credit-card': CreditCard, 'share-2': Share2,
};

const CampaignsTab = ({ API, headers }) => {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const [campaigns, setCampaigns] = useState([]);
  const [audiences, setAudiences] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [creating, setCreating] = useState(false);
  const [showTemplates, setShowTemplates] = useState(true);
  const [draft, setDraft] = useState({ name: '', subject: '', body_html: '', audience_id: '', ab_enabled: false, subject_b: '', body_html_b: '', sample_pct: 30, winner_metric: 'opens' });
  const [busy, setBusy] = useState(false);
  const [postMortemId, setPostMortemId] = useState(null);
  const [postMortemData, setPostMortemData] = useState(null);
  const [postMortemBusy, setPostMortemBusy] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState(null);  // null | "new" | template object

  const openPostMortem = async (campaignId) => {
    setPostMortemId(campaignId);
    setPostMortemBusy(true);
    setPostMortemData(null);
    try {
      const r = await axios.get(`${API}/api/marketing/campaigns/${campaignId}/post-mortem`, { headers, timeout: 60000 });
      setPostMortemData(r.data);
    } catch (e) {
      notifyApiError(notify, e, t('mkt.cmp_pm_failed', 'Post-mortem failed'));
      setPostMortemId(null);
    }
    setPostMortemBusy(false);
  };

  const load = async () => {
    const [c, a, tplRes] = await Promise.all([
      axios.get(`${API}/api/marketing/campaigns`, { headers }),
      axios.get(`${API}/api/marketing/audiences`, { headers }),
      axios.get(`${API}/api/marketing/templates`, { headers }),
    ]);
    setCampaigns(c.data.campaigns); setAudiences(a.data.audiences); setTemplates(tplRes.data.templates);
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: the loader closure(s) re-read live state on every call; the effect re-fires on the listed trigger deps, so adding the function identity would just thrash without changing behaviour.
  useEffect(() => { load();   }, []);

  const applyTemplate = async (templateId) => {
    setBusy(true);
    try {
      const { data } = await axios.post(`${API}/api/marketing/templates/${templateId}/instantiate`, {}, { headers, timeout: 30000 });
      notify.success(t('mkt.cmp_tmpl_ready', 'Template ready'), t('mkt.cmp_tmpl_ready_body', 'Audience size: {{n}} · saved as a draft below.', { n: data.audience_size }));
      load();
    } catch (err) {
      notify.error(err.code === 'ECONNABORTED'
        ? t('mkt.cmp_too_long', 'That took too long — please try again.')
        : (err.response?.data?.detail || t('mkt.cmp_tmpl_inst_err', 'Could not instantiate template')));
    } finally { setBusy(false); }
  };

  const removeTemplate = async (tpl) => {
    const ok = await confirm({
      title: tpl.source === 'custom' ? t('mkt.cmp_del_custom_title', 'Delete this custom template?')
        : t('mkt.cmp_hide_stock_title', 'Hide this stock template for your studio?'),
      body: tpl.source === 'custom'
        ? t('mkt.cmp_del_custom_body', 'This is permanent — the template is removed for everyone in your studio.')
        : t('mkt.cmp_hide_stock_body', 'Other studios still see it. Reset any time to bring it back.'),
      tone: tpl.source === 'custom' ? 'danger' : 'warning',
      confirmLabel: tpl.source === 'custom' ? t('mkt.cmp_delete', 'Delete') : t('mkt.cmp_hide', 'Hide'),
    });
    if (!ok) return;
    try {
      await axios.delete(`${API}/api/marketing/templates/${tpl.id}`, { headers });
      notify.success(tpl.source === 'custom' ? t('mkt.cmp_tmpl_deleted', 'Template deleted') : t('mkt.cmp_tmpl_hidden', 'Template hidden'));
      load();
    } catch (e) {
      notifyApiError(notify, e, t('mkt.cmp_failed', 'Failed'));
    }
  };

  const resetStockTemplate = async (tpl) => {
    try {
      await axios.post(`${API}/api/marketing/templates/${tpl.id}/reset`, {}, { headers });
      notify.success(t('mkt.cmp_reset_default', 'Reset to platform default'));
      load();
    } catch (e) {
      notifyApiError(notify, e, t('mkt.cmp_failed', 'Failed'));
    }
  };

  const create = async () => {    if (!draft.name.trim() || !draft.subject.trim() || !draft.audience_id) return;
    setBusy(true);
    try {
      const payload = {
        name: draft.name, channel: 'email', audience_id: draft.audience_id,
        content: { subject: draft.subject, body_html: draft.body_html },
      };
      if (draft.ab_enabled && draft.subject_b.trim()) {
        payload.variants = [
          { id: 'a', name: 'Variant A', subject: draft.subject, body_html: draft.body_html, weight: 1 },
          { id: 'b', name: 'Variant B', subject: draft.subject_b, body_html: draft.body_html_b || draft.body_html, weight: 1 },
        ];
        payload.ab_test = {
          enabled: true,
          winner_metric: draft.winner_metric,
          sample_pct: draft.sample_pct,
          decide_after_minutes: 240,
        };
      }
      await axios.post(`${API}/api/marketing/campaigns`, payload, { headers, timeout: 30000 });
      setDraft({ name: '', subject: '', body_html: '', audience_id: '', ab_enabled: false, subject_b: '', body_html_b: '', sample_pct: 30, winner_metric: 'opens' });
      setCreating(false); load();
      notify.success(draft.ab_enabled ? t('mkt.cmp_ab_saved', 'A/B campaign saved as draft') : t('mkt.cmp_saved', 'Campaign saved as draft'));
    } catch (e) {
      notify.error(e.response?.data?.detail || t('mkt.cmp_save_err', 'Could not save the campaign — your details are still here, please try again.'));
    } finally { setBusy(false); }
  };

  const decideWinner = async (id, winnerVariantId = null) => {
    setBusy(true);
    try {
      const body = winnerVariantId ? { winner_variant_id: winnerVariantId } : {};
      const { data } = await axios.post(`${API}/api/marketing/campaigns/${id}/decide-winner`, body, { headers });
      notify.success(t('mkt.cmp_winner_decided', 'Winner decided'), t('mkt.cmp_winner_body', 'Variant {{v}} chosen · {{n}} remainder sent.', { v: data.winner_variant_id?.toUpperCase?.(), n: data.remainder_sent }));
      load();
    } catch (err) {
      notifyApiError(notify, err, t('mkt.cmp_decide_err', 'Decide winner failed'));
    } finally { setBusy(false); }
  };

  const send = async (id) => {
    const ok = await confirm({
      title: t('mkt.cmp_send_title', 'Send this campaign now?'),
      detail: t('mkt.cmp_send_detail', 'This will email everyone in the audience. You cannot un-send.'),
      confirmLabel: t('mkt.cmp_send_now', 'Send now'),
      tone: 'warning',
    });
    if (!ok) return;
    setBusy(true);
    try {
      const { data } = await axios.post(`${API}/api/marketing/campaigns/${id}/send`, {}, { headers });
      notify.success(t('mkt.cmp_sent', 'Campaign sent'), t('mkt.cmp_sent_body', '{{n}} delivered · {{f}} failed.', { n: data.sent, f: data.failed || 0 }));
      load();
    } catch (err) {
      notifyApiError(notify, err, t('mkt.cmp_send_err', 'Send failed'));
    } finally { setBusy(false); }
  };

  return (
    <div className="space-y-4" data-testid="marketing-campaigns-tab">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-zinc-700 dark:text-zinc-300 flex items-center gap-1.5">
          {t('mkt.cmp_heading', 'Campaigns')}
          <HelpHint guideId="mkt-first-campaign" testId="help-hint-campaigns" />
        </h3>
        <button
          type="button"
          onClick={() => setCreating(!creating)}
          className="btn-secondary"
          data-testid="campaign-new-btn"
        >
          <Plus size={12} /> {t('mkt.cmp_build_scratch', 'Build from scratch')}
        </button>
      </div>

      {/* Quick-start templates */}
      {showTemplates && templates.length > 0 && (
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-gradient-to-br from-blue-50 via-white to-violet-50 dark:from-blue-950/30 dark:via-zinc-900 dark:to-violet-950/30 p-5" data-testid="campaign-templates-gallery">
          <div className="flex items-center justify-between mb-3">
            <p className="text-xs font-semibold text-zinc-700 dark:text-zinc-300 uppercase tracking-wider flex items-center gap-1.5">
              <Sparkles size={12} className="text-amber-500" /> {t('mkt.cmp_quickstart', 'Quick-start templates')}
            </p>
            <div className="flex items-center gap-2">
              <button onClick={() => setEditingTemplate('new')}
                className="text-[10px] font-bold text-[var(--color-brand-blue)] hover:underline inline-flex items-center gap-1"
                data-testid="template-new-btn">
                <Plus size={10}/> {t('mkt.cmp_new_custom', 'New custom')}
              </button>
              <button onClick={() => setShowTemplates(false)} className="text-[10px] text-zinc-400 dark:text-zinc-500 hover:text-zinc-600 dark:hover:text-zinc-300">{t('mkt.cmp_hide', 'Hide')}</button>
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {templates.map((tpl) => {
              const Icon = TEMPLATE_ICONS[tpl.icon] || Mail;
              const isStock = tpl.source !== 'custom';
              const isOverridden = tpl.source === 'stock_overridden';
              return (
                <div key={tpl.id}
                  className="text-left rounded-lg border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-3 hover:shadow-md hover:border-[var(--color-brand-blue)] transition group relative"
                  data-testid={`template-${tpl.id}`}>
                  <button onClick={() => applyTemplate(tpl.id)} disabled={busy}
                    className="text-left w-full disabled:opacity-50">
                    <div className="flex items-start gap-2">
                      <div className="w-7 h-7 rounded-md bg-[rgb(var(--rgb-brand-blue)/0.1)] flex items-center justify-center shrink-0 group-hover:bg-[var(--color-brand-blue)] group-hover:text-white transition">
                        <Icon size={14} className="text-[var(--color-brand-blue)] group-hover:text-white" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1 flex-wrap">
                          <p className="font-semibold text-zinc-900 dark:text-zinc-100 text-sm truncate">{tpl.name}</p>
                          {isOverridden && <span className="text-[8px] uppercase tracking-wider px-1 rounded bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300 font-bold">{t('mkt.cmp_edited', 'Edited')}</span>}
                          {!isStock && <span className="text-[8px] uppercase tracking-wider px-1 rounded bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300 font-bold">{t('mkt.cmp_custom', 'Custom')}</span>}
                        </div>
                        <p className="text-[11px] text-zinc-500 dark:text-zinc-400 mt-0.5 line-clamp-2">{tpl.description || tpl.subject || ''}</p>
                        {tpl.tone && <span className="inline-block mt-2 text-[10px] uppercase tracking-wider text-zinc-400 dark:text-zinc-500 font-semibold">{t('mkt.cmp_tone', '{{tone}} tone', { tone: tpl.tone })}</span>}
                      </div>
                    </div>
                  </button>
                  <div className="mt-2 pt-2 border-t border-zinc-200 dark:border-zinc-800 flex items-center justify-end gap-1">
                    <button onClick={() => setEditingTemplate(tpl)}
                      className="p-1 rounded hover:bg-zinc-100 dark:bg-zinc-800 dark:hover:bg-zinc-800 text-zinc-500 dark:text-zinc-400" title={t('mkt.cmp_edit', 'Edit')}
                      data-testid={`template-edit-${tpl.id}`}>
                      <Pencil size={11}/>
                    </button>
                    {isOverridden && (
                      <button onClick={() => resetStockTemplate(tpl)}
                        className="p-1 rounded hover:bg-zinc-100 dark:bg-zinc-800 dark:hover:bg-zinc-800 text-zinc-500 dark:text-zinc-400" title={t('mkt.cmp_reset_default_title', 'Reset to default')}
                        data-testid={`template-reset-${tpl.id}`}>
                        <RotateCcw size={11}/>
                      </button>
                    )}
                    <button onClick={() => removeTemplate(tpl)}
                      className="p-1 rounded hover:bg-rose-50 dark:hover:bg-rose-950/40 text-rose-500" title={isStock ? t('mkt.cmp_hide', 'Hide') : t('mkt.cmp_delete', 'Delete')}
                      data-testid={`template-delete-${tpl.id}`}>
                      <Trash2 size={11}/>
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
          <p className="text-[10px] text-zinc-400 dark:text-zinc-500 mt-3">{t('mkt.cmp_tmpl_hint', 'Each template auto-creates a matching audience and a campaign draft — you can edit before sending.')}</p>
        </div>
      )}

      {creating && (
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-5 space-y-3" data-testid="campaign-builder">
          <input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} placeholder={t('mkt.cmp_name_ph', 'Campaign name')} className="w-full px-3 py-2 border border-zinc-200 dark:border-zinc-800 rounded-md text-sm" data-testid="campaign-name-input" />
          <select value={draft.audience_id} onChange={(e) => setDraft({ ...draft, audience_id: e.target.value })} className="w-full px-3 py-2 border border-zinc-200 dark:border-zinc-800 rounded-md text-sm" data-testid="campaign-audience-select">
            <option value="">{t('mkt.cmp_pick_audience', 'Pick an audience…')}</option>
            {audiences.map((a) => <option key={a.id} value={a.id}>{t('mkt.cmp_audience_opt', '{{name}} ({{n}} contacts)', { name: a.name, n: a.estimated_size })}</option>)}
          </select>
          <input value={draft.subject} onChange={(e) => setDraft({ ...draft, subject: e.target.value })} placeholder={t('mkt.cmp_subject_ph', 'Subject line')} className="w-full px-3 py-2 border border-zinc-200 dark:border-zinc-800 rounded-md text-sm" data-testid="campaign-subject-input" />
          <textarea value={draft.body_html} onChange={(e) => setDraft({ ...draft, body_html: e.target.value })} placeholder="<h1>Hi {{first_name}}</h1><p>...</p>" rows={6} className="w-full px-3 py-2 border border-zinc-200 dark:border-zinc-800 rounded-md text-sm font-mono text-xs" data-testid="campaign-body-input" />
          <p className="text-[10px] text-zinc-400 dark:text-zinc-500">{t('mkt.cmp_personalise_pre', 'Use')} <code className="font-mono">{'{{first_name}}'}</code> {t('mkt.cmp_personalise_post', 'for personalisation. Plain HTML supported.')}</p>

          {/* A/B test section (Iter 230) */}
          <div className="mt-2 rounded-lg border border-zinc-200 dark:border-zinc-800 p-3 bg-zinc-50/50 dark:bg-zinc-900/40" data-testid="campaign-ab-section">
            <label className="flex items-center gap-2 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={draft.ab_enabled}
                onChange={(e) => setDraft({ ...draft, ab_enabled: e.target.checked })}
                className="rounded"
                data-testid="campaign-ab-toggle"
              />
              <FlaskConical size={14} className="text-fuchsia-500" />
              <span className="text-xs font-semibold text-zinc-800 dark:text-zinc-200">{t('mkt.cmp_ab_toggle', 'A/B test subject + body')}</span>
              <span className="text-[10px] text-zinc-500 dark:text-zinc-400">{t('mkt.cmp_ab_hint', '— send a sample, pick the winner.')}</span>
            </label>
            {draft.ab_enabled && (
              <div className="mt-3 space-y-2" data-testid="campaign-ab-fields">
                <input
                  value={draft.subject_b}
                  onChange={(e) => setDraft({ ...draft, subject_b: e.target.value })}
                  placeholder={t('mkt.cmp_variant_b_subject', 'Variant B — alternate subject line')}
                  className="w-full px-3 py-2 border border-zinc-200 dark:border-zinc-800 rounded-md text-sm bg-white dark:bg-zinc-900"
                  data-testid="campaign-subject-b-input"
                />
                <textarea
                  value={draft.body_html_b}
                  onChange={(e) => setDraft({ ...draft, body_html_b: e.target.value })}
                  placeholder={t('mkt.cmp_variant_b_body', "Variant B body (leave empty to reuse Variant A's body)")}
                  rows={4}
                  className="w-full px-3 py-2 border border-zinc-200 dark:border-zinc-800 rounded-md text-sm font-mono text-xs bg-white dark:bg-zinc-900"
                  data-testid="campaign-body-b-input"
                />
                <div className="flex items-center gap-3 flex-wrap">
                  <label className="text-[11px] text-zinc-700 dark:text-zinc-300 inline-flex items-center gap-1.5">
                    {t('mkt.cmp_sample_pct', 'Sample %:')}
                    <input
                      type="number"
                      min={5}
                      max={90}
                      value={draft.sample_pct}
                      onChange={(e) => setDraft({ ...draft, sample_pct: parseInt(e.target.value, 10) || 30 })}
                      className="w-16 px-2 py-1 border border-zinc-200 dark:border-zinc-800 rounded text-xs bg-white dark:bg-zinc-900"
                      data-testid="campaign-sample-pct"
                    />
                  </label>
                  <label className="text-[11px] text-zinc-700 dark:text-zinc-300 inline-flex items-center gap-1.5">
                    {t('mkt.cmp_winner_by', 'Winner by:')}
                    <select
                      value={draft.winner_metric}
                      onChange={(e) => setDraft({ ...draft, winner_metric: e.target.value })}
                      className="px-2 py-1 border border-zinc-200 dark:border-zinc-800 rounded text-xs bg-white dark:bg-zinc-900"
                      data-testid="campaign-winner-metric"
                    >
                      <option value="opens">{t('mkt.cmp_opens', 'Opens')}</option>
                      <option value="clicks">{t('mkt.cmp_clicks', 'Clicks')}</option>
                    </select>
                  </label>
                </div>
              </div>
            )}
          </div>

          <button onClick={create} disabled={busy} className="px-4 py-2 rounded-md bg-[var(--color-brand-blue)] text-white text-sm font-semibold disabled:opacity-50 inline-flex items-center gap-1.5" data-testid="campaign-create-btn">
            {busy ? <Loader2 size={13} className="animate-spin" /> : <CheckCircle2 size={13} />} {t('mkt.cmp_save_draft', 'Save draft')}
          </button>
        </div>
      )}

      <div data-testid="campaign-list">
        {campaigns.length === 0 ? (
          <EmptyState
            icon={Megaphone}
            title={t('mkt.cmp_empty_title', 'No campaigns yet')}
            hint={t('mkt.cmp_empty_hint', 'Create your first email or SMS campaign to reach your members. Pick an audience, drop in your copy, and launch in minutes.')}
            primaryAction={{ label: t('mkt.cmp_empty_cta', 'New campaign'), onClick: () => setCreating(true), testId: 'campaigns-empty-create' }}
            testId="campaigns-empty-state"
          />
        ) : (
          <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 overflow-x-auto">
          <table className="w-full text-sm min-w-[620px]">
            <thead className="border-b border-zinc-100 dark:border-zinc-800 text-[10px] uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
              <tr>
                <th className="text-left py-2 px-4 font-semibold">{t('mkt.cmp_th_name', 'Name')}</th>
                <th className="text-left font-semibold">{t('mkt.cmp_th_status', 'Status')}</th>
                <th className="text-right font-semibold">{t('mkt.cmp_th_sent', 'Sent')}</th>
                <th className="text-right font-semibold">{t('mkt.cmp_th_opened', 'Opened')}</th>
                <th className="text-right font-semibold">{t('mkt.cmp_th_revenue', 'Revenue')}</th>
                <th className="text-right font-semibold pr-4">&nbsp;</th>
              </tr>
            </thead>
            <tbody>
              {campaigns.map((c) => (
                <tr key={c.id} className="border-b border-zinc-50 last:border-b-0" data-testid={`campaign-row-${c.id}`}>
                  <td className="py-3 px-4">
                    <p className="font-medium text-zinc-900 dark:text-zinc-100">{c.name}</p>
                    <p className="text-[11px] text-zinc-400 dark:text-zinc-500">{c.content?.subject}</p>
                  </td>
                  <td>
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                      c.status === 'sent' ? 'bg-emerald-50 text-emerald-700' :
                      c.status === 'sending' ? 'bg-amber-50 text-amber-700' :
                      c.status === 'ab_testing' ? 'bg-fuchsia-50 text-fuchsia-700 dark:bg-fuchsia-950/40 dark:text-fuchsia-300' :
                      'bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 dark:text-zinc-500'
                    }`}>{c.status === 'ab_testing' ? t('mkt.cmp_status_ab', 'A/B testing') : c.status}</span>
                    {(c.ab_test?.enabled && c.metrics_by_variant) && (
                      <div className="mt-1 text-[9px] text-zinc-500 dark:text-zinc-400 inline-flex items-center gap-1.5">
                        <FlaskConical size={9}/>
                        {Object.entries(c.metrics_by_variant).map(([vid, mv]) => (
                          <span key={vid} data-testid={`campaign-variant-${c.id}-${vid}`}>
                            {vid.toUpperCase()}: {mv.opened || 0}/{mv.sent || 0}
                            {c.winner_variant_id === vid ? ' ★' : ''}
                          </span>
                        ))}
                      </div>
                    )}
                  </td>
                  <td className="text-right tabular-nums">{c.metrics?.sent || 0}</td>
                  <td className="text-right tabular-nums">{c.metrics?.opened || 0}</td>
                  <td className="text-right tabular-nums text-emerald-700 font-medium">£{(c.metrics?.revenue_gbp || 0).toLocaleString()}</td>
                  <td className="text-right pr-4">
                    {c.status === 'draft' && (
                      <button onClick={() => send(c.id)} disabled={busy} className="inline-flex items-center gap-1 px-2 py-1 text-[11px] font-semibold text-[var(--color-brand-blue)] hover:bg-[rgb(var(--rgb-brand-blue)/0.05)] rounded" data-testid={`campaign-send-${c.id}`}>
                        <Send size={11} /> {t('mkt.cmp_send_now', 'Send now')}
                      </button>
                    )}
                    {c.status === 'ab_testing' && (
                      <button onClick={() => decideWinner(c.id)} disabled={busy} className="inline-flex items-center gap-1 px-2 py-1 text-[11px] font-semibold text-fuchsia-600 dark:text-fuchsia-300 hover:bg-fuchsia-50 dark:hover:bg-fuchsia-950/30 rounded" data-testid={`campaign-decide-winner-${c.id}`}>
                        <Trophy size={11} /> {t('mkt.cmp_pick_winner', 'Pick winner')}
                      </button>
                    )}
                    {c.status === 'sent' && (c.metrics?.sent || 0) > 0 && (
                      <button onClick={() => openPostMortem(c.id)} disabled={postMortemBusy && postMortemId === c.id} className="inline-flex items-center gap-1 px-2 py-1 text-[11px] font-semibold text-purple-600 hover:bg-purple-50 dark:hover:bg-purple-900/20 rounded" data-testid={`campaign-postmortem-${c.id}`}>
                        {postMortemBusy && postMortemId === c.id ? <Loader2 size={11} className="animate-spin"/> : <BarChart3 size={11}/>} {t('mkt.cmp_postmortem', 'AI Post-mortem')}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </div>

      {/* Phase 5 — AI Post-mortem modal */}
      {postMortemId && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" onClick={() => { setPostMortemId(null); setPostMortemData(null); }} data-testid="postmortem-modal">
          <div onClick={(e) => e.stopPropagation()}
            className="bg-white dark:bg-zinc-900 rounded-xl shadow-2xl border border-zinc-200 dark:border-zinc-800 max-w-2xl w-full max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between p-4 border-b border-zinc-200 dark:border-zinc-800 sticky top-0 bg-white dark:bg-zinc-900">
              <div className="flex items-center gap-2">
                <BarChart3 size={16} className="text-purple-500"/>
                <h3 className="font-bold text-zinc-900 dark:text-zinc-100">{t('mkt.cmp_postmortem', 'AI Post-mortem')}</h3>
              </div>
              <button onClick={() => { setPostMortemId(null); setPostMortemData(null); }}
                className="text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200" data-testid="postmortem-close"><X size={16}/></button>
            </div>

            {postMortemBusy && !postMortemData && (
              <div className="p-12 text-center">
                <Loader2 size={32} className="animate-spin text-purple-500 mx-auto mb-3"/>
                <p className="text-sm text-zinc-500 dark:text-zinc-400">{t('mkt.cmp_pm_loading', 'Reading your metrics + 90-day baseline + recent winners…')}</p>
              </div>
            )}

            {postMortemData && (() => {
              const r = postMortemData.report || {};
              const m = postMortemData.metrics || {};
              const b = postMortemData.baseline || {};
              const scoreColor = {
                A: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300',
                B: 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300',
                C: 'bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300',
                D: 'bg-orange-100 text-orange-700 dark:bg-orange-900 dark:text-orange-300',
                F: 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300',
              }[r.headline_score] || 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800';
              return (
                <div className="p-5 space-y-4">
                  <div className="flex items-start gap-3">
                    <div className={`w-14 h-14 rounded-lg flex items-center justify-center text-2xl font-extrabold ${scoreColor}`}>
                      {r.headline_score || '—'}
                    </div>
                    <div className="flex-1">
                      <p className="text-xs uppercase tracking-wider font-semibold text-zinc-500 dark:text-zinc-400">{t('mkt.cmp_pm_subject', 'Subject')}</p>
                      <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">{postMortemData.subject || t('mkt.cmp_pm_no_subject', '(no subject)')}</p>
                      <p className="text-xs text-zinc-600 dark:text-zinc-300 mt-1.5">{r.summary}</p>
                    </div>
                  </div>

                  <div className="grid grid-cols-3 gap-2">
                    <div className="rounded-md border border-zinc-200 dark:border-zinc-700 p-2 bg-zinc-50/50 dark:bg-zinc-900/40">
                      <p className="text-[10px] uppercase tracking-wider text-zinc-500 dark:text-zinc-400 font-semibold">{t('mkt.cmp_pm_open_rate', 'Open rate')}</p>
                      <p className="text-lg font-bold text-zinc-900 dark:text-zinc-100">{((m.open_rate || 0) * 100).toFixed(1)}%</p>
                      <p className="text-[10px] text-zinc-400">{t('mkt.cmp_pm_vs_baseline', 'vs {{v}}% baseline', { v: ((b.avg_open || 0) * 100).toFixed(1) })}</p>
                    </div>
                    <div className="rounded-md border border-zinc-200 dark:border-zinc-700 p-2 bg-zinc-50/50 dark:bg-zinc-900/40">
                      <p className="text-[10px] uppercase tracking-wider text-zinc-500 dark:text-zinc-400 font-semibold">{t('mkt.cmp_pm_click_rate', 'Click rate')}</p>
                      <p className="text-lg font-bold text-zinc-900 dark:text-zinc-100">{((m.click_rate || 0) * 100).toFixed(1)}%</p>
                      <p className="text-[10px] text-zinc-400">{t('mkt.cmp_pm_vs_baseline', 'vs {{v}}% baseline', { v: ((b.avg_click || 0) * 100).toFixed(1) })}</p>
                    </div>
                    <div className="rounded-md border border-zinc-200 dark:border-zinc-700 p-2 bg-zinc-50/50 dark:bg-zinc-900/40">
                      <p className="text-[10px] uppercase tracking-wider text-zinc-500 dark:text-zinc-400 font-semibold">{t('mkt.cmp_pm_recipients', 'Recipients')}</p>
                      <p className="text-lg font-bold text-zinc-900 dark:text-zinc-100">{m.sent || 0}</p>
                      <p className="text-[10px] text-zinc-400">{t('mkt.cmp_pm_delivered', '{{n}} delivered', { n: m.delivered || 0 })}</p>
                    </div>
                  </div>

                  {r.subject_line_critique && (
                    <div className="rounded-md border border-amber-200 dark:border-amber-800 bg-amber-50/50 dark:bg-amber-950/30 p-3">
                      <p className="text-[10px] uppercase tracking-wider font-semibold text-amber-700 dark:text-amber-300 mb-1">{t('mkt.cmp_pm_subject_crit', 'Subject-line critique')}</p>
                      <p className="text-xs text-zinc-700 dark:text-zinc-200">{r.subject_line_critique}</p>
                    </div>
                  )}
                  {r.open_rate_critique && (
                    <div className="rounded-md border border-zinc-200 dark:border-zinc-700 bg-zinc-50/50 dark:bg-zinc-900/40 p-3">
                      <p className="text-[10px] uppercase tracking-wider font-semibold text-zinc-500 dark:text-zinc-400 mb-1">{t('mkt.cmp_pm_open_analysis', 'Open-rate analysis')}</p>
                      <p className="text-xs text-zinc-700 dark:text-zinc-200">{r.open_rate_critique}</p>
                    </div>
                  )}
                  {r.timing_critique && (
                    <div className="rounded-md border border-zinc-200 dark:border-zinc-700 bg-zinc-50/50 dark:bg-zinc-900/40 p-3">
                      <p className="text-[10px] uppercase tracking-wider font-semibold text-zinc-500 dark:text-zinc-400 mb-1">{t('mkt.cmp_pm_timing', 'Timing')}</p>
                      <p className="text-xs text-zinc-700 dark:text-zinc-200">{r.timing_critique}</p>
                    </div>
                  )}

                  {Array.isArray(r.next_time_actions) && r.next_time_actions.length > 0 && (
                    <div className="rounded-md border border-emerald-200 dark:border-emerald-800 bg-emerald-50/50 dark:bg-emerald-950/30 p-3">
                      <p className="text-[10px] uppercase tracking-wider font-semibold text-emerald-700 dark:text-emerald-300 mb-2">{t('mkt.cmp_pm_next_time', 'Next time, try:')}</p>
                      <ul className="space-y-1.5">
                        {r.next_time_actions.map((a, i) => (
                          <li key={i} className="text-xs text-zinc-700 dark:text-zinc-200 flex items-start gap-1.5">
                            <Sparkles size={10} className="text-emerald-500 mt-0.5 shrink-0"/>
                            <span>{a}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {r.winning_pattern_match && (
                    <div className="text-[11px] italic text-zinc-500 dark:text-zinc-400 border-l-2 border-zinc-300 dark:border-zinc-700 pl-2">
                      {r.winning_pattern_match}
                    </div>
                  )}
                </div>
              );
            })()}
          </div>
        </div>
      )}

      {editingTemplate && (
        <TemplateEditorModal
          API={API}
          headers={headers}
          template={editingTemplate === 'new' ? null : editingTemplate}
          onClose={(refresh) => { setEditingTemplate(null); if (refresh) load(); }}
        />
      )}
    </div>
  );
};

export default CampaignsTab;


// ───────────────────────── Template editor modal ─────────────────────────


function TemplateEditorModal({ API, headers, template, onClose }) {
  const { t } = useTranslation();
  const isNew = !template;
  const isStock = !isNew && template.source !== 'custom';
  const [form, setForm] = useState({
    name: template?.name || '',
    subject: template?.subject || '',
    body_html: template?.body_html || '',
    creative_brief: template?.creative_brief || '',
  });
  const [busy, setBusy] = useState(false);

  const save = async () => {
    if (!form.name.trim() || !form.subject.trim()) {
      notify.error(t('mkt.cmp_te_required', 'Name and subject are required'));
      return;
    }
    setBusy(true);
    try {
      if (isNew) {
        await axios.post(`${API}/api/marketing/templates`, {
          name: form.name, subject: form.subject,
          body_html: form.body_html || '<p></p>',
          creative_brief: form.creative_brief, audience_rules: {},
        }, { headers });
        notify.success(t('mkt.cmp_te_created', 'Template created'));
      } else {
        await axios.put(`${API}/api/marketing/templates/${template.id}`, form, { headers });
        notify.success(isStock ? t('mkt.cmp_te_overridden', 'Stock template overridden for your studio') : t('mkt.cmp_te_updated', 'Template updated'));
      }
      onClose(true);
    } catch (e) {
      notifyApiError(notify, e, t('mkt.cmp_failed', 'Failed'));
    }
    setBusy(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4 overflow-y-auto" onClick={() => onClose(false)}>
      <div className="absolute inset-0 bg-black/60" />
      <div className="relative w-full max-w-xl bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-2xl p-4 max-h-[calc(100vh-2rem)] overflow-y-auto shadow-2xl" onClick={(e) => e.stopPropagation()} data-testid="template-editor">
        <div className="flex items-start justify-between mb-3 gap-2">
          <div>
            <p className="text-[10px] uppercase tracking-wider font-bold text-[var(--color-brand-blue)]">
              {isNew ? t('mkt.cmp_te_new_eyebrow', 'New custom template') : isStock ? t('mkt.cmp_te_edit_stock', 'Edit stock template (override)') : t('mkt.cmp_te_edit_custom', 'Edit custom template')}
            </p>
            <h3 className="text-base font-extrabold text-zinc-900 dark:text-zinc-100">
              {isNew ? t('mkt.cmp_te_new_title', 'Build your own quick-start') : template.name}
            </h3>
            {isStock && (
              <p className="text-[11px] text-zinc-500 dark:text-zinc-400 mt-1">
                {t('mkt.cmp_te_override_note', 'Edits are stored as a per-studio override. Other studios still see the platform default.')}
              </p>
            )}
          </div>
          <button onClick={() => onClose(false)} className="p-1 rounded hover:bg-zinc-100 dark:bg-zinc-800 dark:hover:bg-zinc-800" data-testid="template-editor-close">
            <X size={16}/>
          </button>
        </div>

        <div className="space-y-3">
          <div>
            <label className="text-[10px] uppercase tracking-wider font-bold text-zinc-500 dark:text-zinc-400 mb-1 block">{t('mkt.cmp_te_name', 'Name')}</label>
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="w-full px-3 py-2 border border-zinc-200 dark:border-zinc-800 bg-transparent rounded-md text-sm"
              data-testid="template-edit-name"/>
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-wider font-bold text-zinc-500 dark:text-zinc-400 mb-1 block">{t('mkt.cmp_te_subject', 'Subject')}</label>
            <input value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })}
              className="w-full px-3 py-2 border border-zinc-200 dark:border-zinc-800 bg-transparent rounded-md text-sm"
              data-testid="template-edit-subject"/>
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-wider font-bold text-zinc-500 dark:text-zinc-400 mb-1 block">{t('mkt.cmp_te_body', 'Body HTML')}</label>
            <textarea value={form.body_html} onChange={(e) => setForm({ ...form, body_html: e.target.value })}
              rows={8}
              className="w-full px-3 py-2 border border-zinc-200 dark:border-zinc-800 bg-transparent rounded-md text-xs font-mono"
              data-testid="template-edit-body"/>
            <p className="text-[10px] text-zinc-400 dark:text-zinc-500 mt-1">{t('mkt.cmp_te_body_hint_pre', 'Use')} <code className="font-mono">{'{{first_name}}'}</code> {t('mkt.cmp_te_body_hint_and', 'and')} <code className="font-mono">{'{{gym_name}}'}</code> {t('mkt.cmp_te_body_hint_post', 'for personalisation.')}</p>
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-wider font-bold text-zinc-500 dark:text-zinc-400 mb-1 block">{t('mkt.cmp_te_brief', 'Creative brief (optional)')}</label>
            <input value={form.creative_brief} onChange={(e) => setForm({ ...form, creative_brief: e.target.value })}
              placeholder={t('mkt.cmp_te_brief_ph', 'One-line image prompt for AI Director')}
              className="w-full px-3 py-2 border border-zinc-200 dark:border-zinc-800 bg-transparent rounded-md text-sm"
              data-testid="template-edit-brief"/>
          </div>
        </div>

        <div className="mt-4 pt-3 border-t border-zinc-200 dark:border-zinc-800 flex justify-end gap-2">
          <button onClick={() => onClose(false)} className="px-3 py-2 rounded-md border border-zinc-200 dark:border-zinc-700 text-xs font-bold">{t('mkt.cmp_te_cancel', 'Cancel')}</button>
          <button onClick={save} disabled={busy} className="px-4 py-2 rounded-md bg-[var(--color-brand-blue)] text-white text-xs font-extrabold disabled:opacity-50 inline-flex items-center gap-1.5"
            data-testid="template-edit-save">
            {busy ? <Loader2 size={11} className="animate-spin"/> : <CheckCircle2 size={11}/>}
            {isNew ? t('mkt.cmp_te_create', 'Create') : t('mkt.cmp_te_save', 'Save')}
          </button>
        </div>
      </div>
    </div>
  );
}
