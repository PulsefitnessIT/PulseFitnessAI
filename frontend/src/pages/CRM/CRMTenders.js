import { useState, useEffect, useCallback, useRef } from 'react';
import { formatMoneySync } from '@/utils/localization';
import { useCRM } from './CRMApp';
import {
  Plus, FileText, Upload, Trash2, ChevronRight, ChevronLeft, ArrowLeft, Award,
  Sparkles, Edit3, Eye, Copy, BookOpen, Loader2, X, TrendingUp,
  Download, Presentation, Lightbulb, Building2, Target, Link as LinkIcon,
  Image as ImageIcon, Star, FileCheck2
} from 'lucide-react';
import axios from 'axios';
import ListPanel from '@/components/shared/ListPanel';
import CoverageBadge from '@/components/CRM/CoverageBadge';
import TenderCoveragePanel from '@/components/CRM/TenderCoveragePanel';
import TimelinePanel from '@/components/CRM/TimelinePanel';
import { notify } from '@/components/notifications';
import { notifyPicklistError } from '@/lib/picklistErrorHandler';

const STATUS_COLORS = { draft: 'var(--color-text-faint-alt)', parsing: 'var(--color-info-ios)', in_progress: 'var(--color-warning)', review: 'var(--color-accent-magenta)', submitted: 'var(--color-success-alt)', won: 'var(--color-success-alt-2)', lost: 'var(--color-danger)' };
const Q_STATUS_COLORS = { not_started: 'var(--color-text-faint-alt)', draft: 'var(--color-warning)', reviewed: 'var(--color-accent-magenta)', final: 'var(--color-success-alt)' };
const TENDER_TYPES = ['ITT', 'PQQ', 'SQ', 'RFP', 'RFQ', 'DPS', 'Framework'];
const AI_MODES = [
  { id: 'auto', label: 'Auto Mode', desc: 'AI completes full tender', color: 'var(--color-success-alt)' },
  { id: 'assist', label: 'Assist Mode', desc: 'AI writes drafts, you edit', color: 'var(--color-info-ios)' },
  { id: 'strategy', label: 'Strategy Mode', desc: 'AI advises only', color: 'var(--color-accent-magenta)' },
];
const TONES = ['professional', 'persuasive', 'formal', 'technical'];
const Q_CATEGORIES = ['technical', 'commercial', 'social_value', 'health_safety', 'service_delivery', 'mobilisation', 'general'];

/* ═══ TENDER LIST ═══ */
function TenderList({ onSelect, c, isDark, API, headers, navigateTo }) {
  const [tenders, setTenders] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [companies, setCompanies] = useState([]);
  const [form, setForm] = useState({ title: '', type: 'ITT', issuer: '', company_id: '', opportunity_id: '', deadline: '', ai_mode: 'assist', tone: 'professional' });
  const [saving, setSaving] = useState(false);
  const [showAnalytics, setShowAnalytics] = useState(false);
  // Iter 220an — deep-linking: load deals so the create dialog can offer
  // an "Opportunity" dropdown filtered by the selected company.
  const [opportunities, setOpportunities] = useState([]);

  const load = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/crm/v2/tenders`, { headers: headers() });
      setTenders(res.data.tenders); setTotal(res.data.total);
    } catch (e) { console.error(e); }
    setLoading(false);
  }, [API, headers]);

  useEffect(() => { load(); }, [load]);

  const loadCompanies = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/crm/v2/companies?limit=200`, { headers: headers() });
      setCompanies(res.data.companies);
    } catch (e) { console.error(e); }
  }, [API, headers]);

  const loadOpportunities = useCallback(async (companyId) => {
    try {
      const url = companyId
        ? `${API}/crm/v2/opportunities?company_id=${companyId}&limit=100`
        : `${API}/crm/v2/opportunities?limit=100`;
      const res = await axios.get(url, { headers: headers() });
      setOpportunities(res.data.opportunities || []);
    } catch (e) { console.error(e); setOpportunities([]); }
  }, [API, headers]);

  const handleCreate = async () => {
    if (!form.title.trim()) return;
    setSaving(true);
    try {
      const res = await axios.post(`${API}/crm/v2/tenders`, form, { headers: headers() });
      onSelect(res.data.id);
    } catch (e) {
      // Iter 220bt — surface picklist errors with "Did you mean" hint
      // before falling back to the generic toast.
      if (!notifyPicklistError(e, notify)) {
        notify.error('Could not create tender', e?.response?.data?.detail || e.message);
      }
    }
    setSaving(false);
  };

  const openCreate = () => { loadCompanies(); loadOpportunities(''); setShowCreate(true); };
  const inputStyle = { background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${isDark ? 'var(--color-surface-dark-3)' : 'var(--color-border-alt)'}`, color: c.text };

  return (
    <>
      {/* Iter 216h102 — Analytics toggle */}
      <div className="flex items-center justify-between mb-3" data-testid="tender-analytics-toggle-row">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setShowAnalytics(false)}
            className={`px-3 py-1.5 text-xs font-semibold rounded-md border transition ${
              !showAnalytics
                ? 'bg-[var(--color-info-ios)] text-white border-[var(--color-info-ios)]'
                : 'bg-transparent'
            }`}
            style={showAnalytics ? { color: c.textMuted, borderColor: c.border } : undefined}
            data-testid="tender-list-tab"
          >
            <FileText size={12} className="inline -mt-0.5 mr-1" /> All tenders
          </button>
          <button
            type="button"
            onClick={() => setShowAnalytics(true)}
            className={`px-3 py-1.5 text-xs font-semibold rounded-md border transition ${
              showAnalytics
                ? 'bg-[var(--color-info-ios)] text-white border-[var(--color-info-ios)]'
                : 'bg-transparent'
            }`}
            style={!showAnalytics ? { color: c.textMuted, borderColor: c.border } : undefined}
            data-testid="tender-analytics-tab"
          >
            <TrendingUp size={12} className="inline -mt-0.5 mr-1" /> Win/Loss analytics
          </button>
        </div>
      </div>

      {showAnalytics && (
        <TenderAnalyticsTab API={API} headers={headers} c={c} isDark={isDark} />
      )}

      {!showAnalytics && (
      <>
      <TenderCoveragePanel />
      <ListPanel
        data-testid="crm-tender-list"
        count={{ value: total, label: 'tender' }}
        primaryAction={{ label: 'New Tender', icon: Plus, onClick: openCreate, testId: 'create-tender-btn' }}
        loading={loading}
        empty={{
          when: tenders.length === 0,
          icon: Award,
          title: 'No tenders yet',
          hint: 'Upload a tender pack to start winning contracts.',
          primaryAction: { label: 'Create your first tender', onClick: openCreate },
          testId: 'crm-tender-empty',
        }}
      >
        {tenders.map(t => {
          const statusColor = STATUS_COLORS[t.status] || 'var(--color-text-faint-alt)';
          const progress = t.total_questions > 0 ? Math.round((t.answered_questions / t.total_questions) * 100) : 0;
          return (
            <div key={t.id} onClick={() => onSelect(t.id)}
              className="flex items-center gap-4 p-4 rounded-lg border cursor-pointer transition-all hover:scale-[1.003]"
              style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}
              data-testid={`tender-row-${t.id}`}>
              <div className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0" style={{ background: `${statusColor}15` }}>
                <Award size={18} style={{ color: statusColor }} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <p className="text-sm font-semibold truncate" style={{ color: c.text }}>{t.title}</p>
                  <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded" style={{ background: `${statusColor}20`, color: statusColor }}>{t.status}</span>
                  <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded" style={{ background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-100)', color: c.textDim }}>{t.type}</span>
                  {t.company_id && <CoverageBadge companyId={t.company_id} compact testId={`tender-coverage-${t.id}`} />}
                  {/* Iter 220an — deep-linking: clickable company + opp badges */}
                  {t.company_name && (
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); navigateTo && navigateTo('company', t.company_id); }}
                      className="text-[10px] font-medium px-1.5 py-0.5 rounded inline-flex items-center gap-1 hover:underline"
                      style={{ background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-info-ios-15)', color: 'var(--color-info-ios)' }}
                      data-testid={`tender-row-${t.id}-company-link`}
                      title="Open linked company"
                    >
                      <Building2 size={10} />{t.company_name}
                    </button>
                  )}
                  {t.opportunity_title && (
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); navigateTo && navigateTo('opportunity', t.opportunity_id); }}
                      className="text-[10px] font-medium px-1.5 py-0.5 rounded inline-flex items-center gap-1 hover:underline"
                      style={{ background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-accent-magenta-15)', color: 'var(--color-accent-magenta)' }}
                      data-testid={`tender-row-${t.id}-opportunity-link`}
                      title={`Open linked deal · ${t.opportunity_stage || ''}`}
                    >
                      <Target size={10} />{t.opportunity_title}
                    </button>
                  )}
                </div>
                <p className="text-[11px] mt-0.5" style={{ color: c.textDim }}>
                  {t.issuer && <>{t.issuer} &middot; </>}
                  {t.total_questions} questions &middot; {t.answered_questions} answered &middot; {t.documents_uploaded} docs
                  {t.deadline && <> &middot; Due: {new Date(t.deadline).toLocaleDateString('en-GB')}</>}
                </p>
              </div>
              <div className="w-20 shrink-0">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[10px]" style={{ color: c.textDim }}>{progress}%</span>
                </div>
                <div className="h-1.5 rounded-full overflow-hidden" style={{ background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-border-alt)' }}>
                  <div className="h-full rounded-full transition-all" style={{ width: `${progress}%`, background: progress >= 80 ? 'var(--color-success-alt)' : progress >= 40 ? 'var(--color-warning)' : 'var(--color-text-faint-alt)' }} />
                </div>
              </div>
              <ChevronRight size={16} style={{ color: c.textDim }} />
            </div>
          );
        })}
      </ListPanel>
      </>
      )}

      {/* Create Tender Dialog */}
      {showCreate && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setShowCreate(false)}>
          <div className="w-full max-w-lg mx-4 rounded-xl p-6 shadow-2xl max-h-[90vh] overflow-y-auto" style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', border: `1px solid ${c.border}` }} onClick={e => e.stopPropagation()} data-testid="create-tender-dialog">
            <div className="sticky top-0 z-10 -mx-6 -mt-6 px-6 pt-6 pb-3 mb-4 flex items-center justify-between border-b" style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', borderColor: c.border }}>
              <h2 className="text-lg font-semibold" style={{ color: c.text }}>New Tender</h2>
              <button onClick={() => setShowCreate(false)} className="p-1 hover:opacity-70" style={{ color: c.textDim }} data-testid="create-tender-close"><X size={16} /></button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Tender Title *</label>
                <input value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} placeholder="e.g. Leisure Centre Equipment Supply & Install" className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={inputStyle} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Type</label>
                  <select value={form.type} onChange={e => setForm({ ...form, type: e.target.value })} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={inputStyle}>
                    {TENDER_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Issuer</label>
                  <input value={form.issuer} onChange={e => setForm({ ...form, issuer: e.target.value })} placeholder="e.g. Birmingham City Council" className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={inputStyle} />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Link to Company</label>
                  <select
                    value={form.company_id || ''}
                    onChange={(e) => {
                      const cid = e.target.value;
                      // Iter 220an — reset opportunity when switching company
                      // so we never persist an inconsistent link.
                      setForm({ ...form, company_id: cid, opportunity_id: '' });
                      loadOpportunities(cid);
                    }}
                    className="w-full mt-1 px-3 py-2 text-sm rounded-md"
                    style={inputStyle}
                    data-testid="create-tender-company-select"
                  >
                    <option value="">None</option>
                    {companies.map(co => <option key={co.id} value={co.id}>{co.name}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Link to Deal (Opportunity)</label>
                  <select
                    value={form.opportunity_id || ''}
                    onChange={e => setForm({ ...form, opportunity_id: e.target.value })}
                    className="w-full mt-1 px-3 py-2 text-sm rounded-md"
                    style={inputStyle}
                    data-testid="create-tender-opportunity-select"
                  >
                    <option value="">None</option>
                    {opportunities.map(op => (
                      <option key={op.id} value={op.id}>{op.title} {op.stage ? `· ${op.stage}` : ''}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Deadline</label>
                <input type="date" value={form.deadline || ''} onChange={e => setForm({ ...form, deadline: e.target.value })} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={inputStyle} />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>AI Mode</label>
                <div className="grid grid-cols-3 gap-2 mt-1">
                  {AI_MODES.map(m => (
                    <button key={m.id} type="button" onClick={() => setForm({ ...form, ai_mode: m.id })}
                      className={`p-2.5 rounded-md text-left border transition-all ${form.ai_mode === m.id ? 'ring-2 ring-[var(--color-info-ios)]' : ''}`}
                      style={{ background: isDark ? 'var(--color-ink-alt)' : 'var(--color-neutral-50)', borderColor: form.ai_mode === m.id ? 'var(--color-info-ios)' : (isDark ? 'var(--color-surface-dark-3)' : 'var(--color-border-alt)') }}>
                      <p className="text-xs font-medium" style={{ color: m.color }}>{m.label}</p>
                      <p className="text-[10px] mt-0.5" style={{ color: c.textDim }}>{m.desc}</p>
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Tone</label>
                <div className="flex gap-1 mt-1">
                  {TONES.map(t => (
                    <button key={t} type="button" onClick={() => setForm({ ...form, tone: t })}
                      className={`px-3 py-1.5 text-xs rounded-md ${form.tone === t ? 'bg-[var(--color-info-ios)] text-white' : ''}`}
                      style={form.tone !== t ? { background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-100)', color: c.textMuted } : {}}>
                      {t.charAt(0).toUpperCase() + t.slice(1)}
                    </button>
                  ))}
                </div>
              </div>
            </div>
            <div className="flex gap-2 mt-5 justify-end">
              <button onClick={() => setShowCreate(false)} className="px-4 py-2 text-sm" style={{ color: c.textMuted }}>Cancel</button>
              <button onClick={handleCreate} disabled={saving || !form.title.trim()} className="px-4 py-2 bg-[var(--color-info-ios)] text-white text-sm font-medium rounded-md disabled:opacity-50">
                {saving ? 'Creating...' : 'Create Tender'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

/* ═══ TENDER LINKED RECORDS PANEL (Iter 220an) ═══ */
function TenderLinkedRecordsPanel({ tender, tenderId, API, headers, c, isDark, navigateTo, onSaved }) {
  const [editing, setEditing] = useState(false);
  const [companies, setCompanies] = useState([]);
  const [opportunities, setOpportunities] = useState([]);
  const [companyId, setCompanyId] = useState(tender?.company_id || '');
  const [opportunityId, setOpportunityId] = useState(tender?.opportunity_id || '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const loadCompanies = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/crm/v2/companies?limit=200`, { headers: headers() });
      setCompanies(r.data.companies || []);
    } catch (e) { console.error(e); }
  }, [API, headers]);

  const loadOpportunities = useCallback(async (cid) => {
    try {
      const url = cid
        ? `${API}/crm/v2/opportunities?company_id=${cid}&limit=100`
        : `${API}/crm/v2/opportunities?limit=100`;
      const r = await axios.get(url, { headers: headers() });
      setOpportunities(r.data.opportunities || []);
    } catch (e) { console.error(e); setOpportunities([]); }
  }, [API, headers]);

  const openEdit = () => {
    setCompanyId(tender?.company_id || '');
    setOpportunityId(tender?.opportunity_id || '');
    setError('');
    loadCompanies();
    loadOpportunities(tender?.company_id || '');
    setEditing(true);
  };

  const save = async () => {
    setSaving(true);
    setError('');
    try {
      await axios.put(`${API}/crm/v2/tenders/${tenderId}`, {
        company_id: companyId || null,
        opportunity_id: opportunityId || null,
      }, { headers: headers() });
      setEditing(false);
      onSaved && onSaved();
    } catch (e) {
      // Iter 220bt — picklist errors get the rich "Did you mean" toast;
      // any other failure falls back to the inline banner the form
      // already renders via `error`.
      if (notifyPicklistError(e, notify)) {
        setError('');
      } else {
        const detail = e?.response?.data?.detail;
        setError(typeof detail === 'string' ? detail : 'Failed to update links');
      }
    }
    setSaving(false);
  };

  const inputStyle = { background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${isDark ? 'var(--color-surface-dark-3)' : 'var(--color-border-alt)'}`, color: c.text };
  const linkedCo = tender?.company;
  const linkedOpp = tender?.opportunity;

  return (
    <div
      className="rounded-lg border p-4"
      style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}
      data-testid="tender-linked-records-panel"
    >
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold flex items-center gap-2" style={{ color: c.text }}>
          <LinkIcon size={14} /> Linked Records
        </h3>
        {!editing && (
          <button
            type="button"
            onClick={openEdit}
            className="text-[11px] font-medium px-2.5 py-1 rounded-md border hover:opacity-80"
            style={{ borderColor: c.border, color: c.textMuted }}
            data-testid="tender-links-edit-btn"
          >
            <Edit3 size={11} className="inline -mt-0.5 mr-1" /> Edit links
          </button>
        )}
      </div>

      {!editing && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="p-3 rounded-md border" style={{ borderColor: c.border }} data-testid="tender-linked-company">
            <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider mb-1" style={{ color: c.textDim }}>
              <Building2 size={11} /> Company
            </div>
            {linkedCo ? (
              <button
                type="button"
                onClick={() => navigateTo && navigateTo('company', linkedCo.id)}
                className="text-sm font-semibold hover:underline text-left"
                style={{ color: 'var(--color-info-ios)' }}
                data-testid="tender-linked-company-link"
              >
                {linkedCo.name}
                {linkedCo.sector && <span className="text-[11px] font-normal ml-2" style={{ color: c.textDim }}>· {linkedCo.sector}</span>}
              </button>
            ) : (
              <p className="text-sm" style={{ color: c.textDim }}>Not linked</p>
            )}
          </div>
          <div className="p-3 rounded-md border" style={{ borderColor: c.border }} data-testid="tender-linked-opportunity">
            <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider mb-1" style={{ color: c.textDim }}>
              <Target size={11} /> Deal (Opportunity)
            </div>
            {linkedOpp ? (
              <button
                type="button"
                onClick={() => navigateTo && navigateTo('opportunity', linkedOpp.id)}
                className="text-sm font-semibold hover:underline text-left"
                style={{ color: 'var(--color-accent-magenta)' }}
                data-testid="tender-linked-opportunity-link"
              >
                {linkedOpp.title}
                <span className="text-[11px] font-normal ml-2 capitalize" style={{ color: c.textDim }}>
                  · {linkedOpp.stage?.replace('_', ' ') || ''}{linkedOpp.value ? ` · £${linkedOpp.value.toLocaleString()}` : ''}
                </span>
              </button>
            ) : (
              <p className="text-sm" style={{ color: c.textDim }}>Not linked</p>
            )}
          </div>
        </div>
      )}

      {editing && (
        <div className="space-y-3" data-testid="tender-links-edit-form">
          <div>
            <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Company</label>
            <select
              value={companyId}
              onChange={(e) => {
                const cid = e.target.value;
                setCompanyId(cid);
                setOpportunityId('');
                loadOpportunities(cid);
              }}
              className="w-full mt-1 px-3 py-2 text-sm rounded-md"
              style={inputStyle}
              data-testid="tender-links-company-select"
            >
              <option value="">None</option>
              {companies.map(co => <option key={co.id} value={co.id}>{co.name}</option>)}
            </select>
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Deal (Opportunity)</label>
            <select
              value={opportunityId}
              onChange={e => setOpportunityId(e.target.value)}
              className="w-full mt-1 px-3 py-2 text-sm rounded-md"
              style={inputStyle}
              data-testid="tender-links-opportunity-select"
            >
              <option value="">None</option>
              {opportunities.map(op => (
                <option key={op.id} value={op.id}>{op.title} {op.stage ? `· ${op.stage}` : ''}</option>
              ))}
            </select>
          </div>
          {error && (
            <p className="text-xs" style={{ color: 'var(--color-danger-alt)' }} data-testid="tender-links-error">{error}</p>
          )}
          <div className="flex gap-2 justify-end">
            <button
              type="button"
              onClick={() => { setEditing(false); setError(''); }}
              className="px-3 py-1.5 text-xs"
              style={{ color: c.textMuted }}
              data-testid="tender-links-cancel"
            >Cancel</button>
            <button
              type="button"
              onClick={save}
              disabled={saving}
              className="px-3 py-1.5 bg-[var(--color-info-ios)] text-white text-xs font-medium rounded-md disabled:opacity-50"
              data-testid="tender-links-save"
            >{saving ? 'Saving…' : 'Save links'}</button>
          </div>
        </div>
      )}
    </div>
  );
}


/* ═══ TENDER DETAIL ═══ */
function TenderDetail({ tenderId, onBack, c, isDark, API, headers, navigateTo }) {
  const [tender, setTender] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [showAddQ, setShowAddQ] = useState(false);
  const [editingQ, setEditingQ] = useState(null);
  const [qForm, setQForm] = useState({ text: '', category: 'general', word_limit: '', weighting: '', mandatory: true, complexity: 'medium' });
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [aiLoading, setAiLoading] = useState('');
  const [parseText, setParseText] = useState('');
  const [showParse, setShowParse] = useState(false);
  const fileRef = useRef(null);

  const load = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/crm/v2/tenders/${tenderId}`, { headers: headers() });
      setTender(res.data);
    } catch (e) { console.error(e); }
  }, [API, headers, tenderId]);

  useEffect(() => { load(); }, [load]);

  const addQuestion = async () => {
    if (!qForm.text.trim()) return;
    setSaving(true);
    try {
      const payload = { ...qForm, word_limit: parseInt(qForm.word_limit) || null, weighting: parseInt(qForm.weighting) || null };
      await axios.post(`${API}/crm/v2/tenders/${tenderId}/questions`, payload, { headers: headers() });
      setShowAddQ(false);
      setQForm({ text: '', category: 'general', word_limit: '', weighting: '', mandatory: true, complexity: 'medium' });
      load();
    } catch (e) { console.error(e); }
    setSaving(false);
  };

  const updateQuestion = async (qId, data) => {
    try {
      await axios.put(`${API}/crm/v2/tenders/${tenderId}/questions/${qId}`, data, { headers: headers() });
      load();
    } catch (e) { console.error(e); }
  };

  const uploadDoc = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      await axios.post(`${API}/crm/v2/tenders/${tenderId}/documents?category=tender_pack`, formData,
        { headers: { ...headers(), 'Content-Type': 'multipart/form-data' } });
      load();
    } catch (e) { console.error(e); }
    setUploading(false);
    if (fileRef.current) fileRef.current.value = '';
  };

  const deleteTender = async () => {
    try { await axios.delete(`${API}/crm/v2/tenders/${tenderId}`, { headers: headers() }); onBack(); } catch (e) { console.error(e); }
  };

  const aiParse = async () => {
    if (!parseText || parseText.length < 20) return;
    setAiLoading('parse');
    try {
      const _res = await axios.post(`${API}/crm/v2/tenders/${tenderId}/ai/parse`, { text: parseText }, { headers: headers() });
      setShowParse(false); setParseText('');
      load();
    } catch (e) { console.error(e); }
    setAiLoading('');
  };

  const aiGenerateResponse = async (qId, action = 'generate') => {
    setAiLoading(`gen-${qId}`);
    try {
      const _res = await axios.post(`${API}/crm/v2/tenders/${tenderId}/questions/${qId}/ai/generate`, { action, tone: tender?.tone }, { headers: headers() });
      load();
    } catch (e) { console.error(e); }
    setAiLoading('');
  };

  const aiStrategy = async () => {
    setAiLoading('strategy');
    try {
      await axios.post(`${API}/crm/v2/tenders/${tenderId}/ai/strategy`, {}, { headers: headers() });
      load();
    } catch (e) { console.error(e); }
    setAiLoading('');
  };

  // Iter 216h101 — Tender Engine v2 additions
  const aiParseFromDoc = async (docId) => {
    setAiLoading(`parse-doc-${docId}`);
    try {
      await axios.post(`${API}/crm/v2/tenders/${tenderId}/ai/parse-from-doc`, { doc_id: docId }, { headers: headers() });
      load();
    } catch (e) {
      const msg = e.response?.data?.detail || 'Parse from document failed';
      alert(msg);
    }
    setAiLoading('');
  };
  const [snippetCache, setSnippetCache] = useState({}); // qId -> { loading, suggestions }
  const fetchSnippets = async (qId) => {
    setSnippetCache((c) => ({ ...c, [qId]: { ...(c[qId] || {}), loading: true } }));
    try {
      const r = await axios.post(`${API}/crm/v2/tenders/${tenderId}/questions/${qId}/ai/suggest-snippets`, {}, { headers: headers() });
      setSnippetCache((c) => ({ ...c, [qId]: { loading: false, suggestions: r.data?.suggestions || [] } }));
    } catch (e) {
      setSnippetCache((c) => ({ ...c, [qId]: { loading: false, suggestions: [] } }));
    }
  };
  const exportPdf = (kind) => {
    const token = localStorage.getItem('crm_token');
    // pitch → pitch-v2 (honours operator-edited slides)
    const path = kind === 'pitch' ? 'pitch-v2' : kind;
    const url = `${API}/crm/v2/tenders/${tenderId}/export/${path}?_t=${Date.now()}`;
    // Resend through fetch so we can set the Bearer header — browsers
    // can't attach Authorization to a plain anchor click.
    fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => { if (!r.ok) throw new Error('Export failed'); return r.blob(); })
      .then((blob) => {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `${(tender?.title || 'tender').replace(/[^a-z0-9]+/gi, '_')}-${kind}.pdf`;
        document.body.appendChild(a); a.click(); a.remove();
      })
      .catch(() => alert('Failed to export PDF'));
  };
  const seedBidLibrary = async () => {
    try {
      const r = await axios.post(`${API}/crm/v2/knowledge-base/seed-pulse-defaults`, {}, { headers: headers() });
      alert(`Seeded ${r.data.seeded} bid-library snippets (${r.data.skipped} already existed).`);
      load();
    } catch (e) { alert('Seed failed: ' + (e.response?.data?.detail || e.message)); }
  };

  // Iter 216h102 — Tender Engine v3 frontend hooks
  const [templates, setTemplates] = useState([]);
  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/crm/v2/tender-templates`, { headers: headers() });
        setTemplates(r.data?.items || []);
      } catch (_) { /* templates optional */ }
    })();
  }, [tenderId]); // eslint-disable-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — runs on the listed trigger deps; omitted refs are stable identities or read live state at call time.
  const applyTemplate = (qId, tplId) => {
    if (!tplId) return;
    const tpl = templates.find((t) => t.id === tplId);
    if (!tpl) return;
    updateQuestion(qId, { response: tpl.body, status: 'draft' });
  };
  const seedTenderTemplates = async () => {
    try {
      const r = await axios.post(`${API}/crm/v2/tender-templates/seed-pulse-defaults`, {}, { headers: headers() });
      const list = await axios.get(`${API}/crm/v2/tender-templates`, { headers: headers() });
      setTemplates(list.data?.items || []);
      alert(`Seeded ${r.data.seeded} tender response templates (${r.data.skipped} already existed).`);
    } catch (e) { alert('Seed failed: ' + (e.response?.data?.detail || e.message)); }
  };
  const ocrDoc = async (docId) => {
    setAiLoading(`ocr-${docId}`);
    try {
      await axios.post(`${API}/crm/v2/tenders/${tenderId}/documents/${docId}/ocr`, {}, { headers: headers() });
      load();
      alert('OCR extraction complete — try "Parse questions" now.');
    } catch (e) {
      alert('OCR failed: ' + (e.response?.data?.detail || e.message));
    }
    setAiLoading('');
  };
  const [showSlides, setShowSlides] = useState(false);
  const [showPackWizard, setShowPackWizard] = useState(false);
  const [kbItems, setKbItems] = useState([]);
  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/crm/v2/knowledge-base?limit=100`, { headers: headers() });
        setKbItems(r.data?.items || []);
      } catch (_) { /* KB optional */ }
    })();
  }, [tenderId]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!tender) return <div className="flex items-center justify-center h-64"><div className="w-5 h-5 border-2 border-[var(--color-info-ios)] border-t-transparent rounded-full animate-spin" /></div>;

  const statusColor = STATUS_COLORS[tender.status] || 'var(--color-text-faint-alt)';
  const progress = tender.total_questions > 0 ? Math.round((tender.answered_questions / tender.total_questions) * 100) : 0;
  const questions = tender.questions || [];
  const docs = tender.tender_documents || [];
  const inputStyle = { background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${isDark ? 'var(--color-surface-dark-3)' : 'var(--color-border-alt)'}`, color: c.text };
  const tabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'timeline', label: 'Timeline' },
    { id: 'questions', label: `Questions (${questions.length})` },
    { id: 'documents', label: `Documents (${docs.length})` },
    { id: 'strategy', label: 'Strategy' },
  ];

  return (
    <div data-testid="crm-tender-detail">
      <button onClick={onBack} className="flex items-center gap-1.5 text-sm mb-4 hover:underline" style={{ color: c.textMuted }}>
        <ArrowLeft size={14} /> Back to Tenders
      </button>

      {/* Header */}
      <div className="flex items-center gap-3 mb-5">
        <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ background: `${statusColor}15` }}>
          <Award size={20} style={{ color: statusColor }} />
        </div>
        <div className="flex-1 min-w-0">
          <h1 className="text-lg font-bold truncate" style={{ color: c.text }}>{tender.title}</h1>
          <div className="flex items-center gap-2 mt-0.5 flex-wrap">
            <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded" style={{ background: `${statusColor}20`, color: statusColor }}>{tender.status}</span>
            <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded" style={{ background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-100)', color: c.textDim }}>{tender.type}</span>
            {tender.issuer && <span className="text-xs" style={{ color: c.textDim }}>{tender.issuer}</span>}
            {tender.deadline && <span className="text-xs" style={{ color: 'var(--color-accent-amber)' }}>Due: {new Date(tender.deadline).toLocaleDateString('en-GB')}</span>}
          </div>
        </div>
        <button onClick={deleteTender} className="p-2 rounded-md" style={{ color: 'var(--color-danger-alt)' }} data-testid="delete-tender-btn"><Trash2 size={16} /></button>
      </div>

      {/* Iter 216h101 — Export bar */}
      <div className="flex items-center gap-2 mb-4 flex-wrap" data-testid="tender-export-bar">
        <button
          onClick={() => exportPdf('submission')}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md"
          style={{ background: 'var(--color-info-ios)', color: '#fff' }}
          data-testid="export-submission-btn"
        >
          <Download size={12} /> Export submission PDF
        </button>
        <button
          onClick={() => setShowPackWizard(true)}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md"
          style={{ background: 'var(--color-success-alt, #16a34a)', color: '#fff' }}
          data-testid="export-pack-btn"
        >
          <FileText size={12} /> Submission pack (.docx)
        </button>
        <button
          onClick={() => exportPdf('pitch')}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md border"
          style={{ borderColor: 'var(--color-info-ios)', color: 'var(--color-info-ios)' }}
          data-testid="export-pitch-btn"
        >
          <Presentation size={12} /> Generate pitch deck
        </button>
        <button
          onClick={() => setShowSlides(true)}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md border"
          style={{ borderColor: c.border, color: c.textMuted }}
          data-testid="manage-slides-btn"
        >
          <Edit3 size={12} /> Manage slides
        </button>
        <span className="flex-1" />
        <button
          onClick={seedTenderTemplates}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md border"
          style={{ borderColor: c.border, color: c.textMuted }}
          data-testid="seed-tender-templates-btn"
          title="Seed pre-approved Pulse Fitness tender response templates"
        >
          <Copy size={12} /> Seed response templates
        </button>
        <button
          onClick={seedBidLibrary}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md border"
          style={{ borderColor: c.border, color: c.textMuted }}
          data-testid="seed-bid-library-btn"
          title="Seed pre-approved Pulse Fitness bid-library snippets"
        >
          <BookOpen size={12} /> Seed bid library
        </button>
      </div>

      {/* KPI Strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
        {[
          { l: 'Progress', v: `${progress}%`, col: progress >= 80 ? 'var(--color-success-alt)' : 'var(--color-warning)' },
          { l: 'Questions', v: `${tender.answered_questions}/${tender.total_questions}`, col: 'var(--color-info-ios)' },
          { l: 'Documents', v: tender.documents_uploaded, col: 'var(--color-accent-magenta)' },
          { l: 'AI Mode', v: tender.ai_mode?.charAt(0).toUpperCase() + tender.ai_mode?.slice(1), col: AI_MODES.find(m => m.id === tender.ai_mode)?.color || 'var(--color-info-ios)' },
        ].map(kpi => (
          <div key={kpi.l} className="p-3 rounded-lg border" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
            <p className="text-[10px] uppercase tracking-wider" style={{ color: c.textDim }}>{kpi.l}</p>
            <p className="text-lg font-bold" style={{ color: kpi.col }}>{kpi.v}</p>
          </div>
        ))}
      </div>

      {/* Progress bar */}
      <div className="h-2 rounded-full overflow-hidden mb-5" style={{ background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-border-alt)' }}>
        <div className="h-full rounded-full transition-all duration-500" style={{ width: `${progress}%`, background: progress >= 80 ? 'var(--color-success-alt)' : progress >= 40 ? 'var(--color-warning)' : 'var(--color-info-ios)' }} />
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-4 overflow-x-auto pb-1">
        {tabs.map(tab => (
          <button key={tab.id} onClick={() => setActiveTab(tab.id)}
            className={`px-3 py-1.5 text-xs font-medium rounded-md whitespace-nowrap ${activeTab === tab.id ? 'bg-[var(--color-info-ios)] text-white' : ''}`}
            style={activeTab !== tab.id ? { background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-100)', color: c.textMuted } : {}}>
            {tab.label}
          </button>
        ))}
      </div>

      <div className="rounded-lg border p-5" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
        {/* Overview */}
        {activeTab === 'overview' && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-3">
              <h3 className="text-sm font-semibold" style={{ color: c.text }}>Tender Details</h3>
              {[
                { l: 'Type', v: tender.type },
                { l: 'Issuer', v: tender.issuer },
                { l: 'Bid Owner', v: tender.bid_owner },
                { l: 'AI Mode', v: tender.ai_mode },
                { l: 'Tone', v: tender.tone },
                { l: 'Deadline', v: tender.deadline ? new Date(tender.deadline).toLocaleDateString('en-GB') : 'Not set' },
                { l: 'Created', v: new Date(tender.created_at).toLocaleDateString('en-GB') },
              ].map(r => r.v ? (
                <div key={r.l} className="flex items-center gap-3">
                  <span className="text-xs w-20" style={{ color: c.textDim }}>{r.l}</span>
                  <span className="text-sm capitalize" style={{ color: c.text }}>{r.v}</span>
                </div>
              ) : null)}
            </div>
            <div>
              <h3 className="text-sm font-semibold mb-2" style={{ color: c.text }}>Status</h3>
              <select value={tender.status} onChange={e => updateQuestion(null, { status: e.target.value }).catch(() => {})}
                className="w-full px-3 py-2 text-sm rounded-md mb-3" style={inputStyle}>
                {['draft', 'parsing', 'in_progress', 'review', 'submitted', 'won', 'lost'].map(s => <option key={s} value={s}>{s.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())}</option>)}
              </select>
              {tender.executive_summary && (
                <div className="p-3 rounded-lg" style={{ background: isDark ? 'var(--color-neutral-950)' : 'var(--color-neutral-50)' }}>
                  <p className="text-[10px] uppercase tracking-wider mb-1" style={{ color: c.textDim }}>Executive Summary</p>
                  <p className="text-sm" style={{ color: c.textMuted }}>{tender.executive_summary}</p>
                </div>
              )}
            </div>
            </div>

            {/* Iter 220an — Deep linking: Linked Records panel */}
            <TenderLinkedRecordsPanel
              tender={tender}
              API={API}
              headers={headers}
              c={c}
              isDark={isDark}
              navigateTo={navigateTo}
              onSaved={load}
              tenderId={tenderId}
            />
          </div>
        )}

        {/* Iter 220bv — unified timeline */}
        {activeTab === 'timeline' && (
          <TimelinePanel
            scope={{ type: 'tender', id: tenderId }}
            API={API}
            headers={headers}
            isDark={isDark}
            c={c}
          />
        )}

        {/* Questions */}
        {activeTab === 'questions' && (
          <div>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold" style={{ color: c.text }}>Questions</h3>
              <div className="flex gap-2">
                <button onClick={() => setShowParse(true)} className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md border"
                  style={{ borderColor: 'var(--color-success-alt)30', color: 'var(--color-success-alt)' }} disabled={aiLoading === 'parse'} data-testid="ai-parse-btn">
                  {aiLoading === 'parse' ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />} AI Parse
                </button>
                <button onClick={() => setShowAddQ(true)} className="flex items-center gap-1.5 px-3 py-1.5 bg-[var(--color-info-ios)] text-white text-xs font-medium rounded-md" data-testid="add-question-btn">
                  <Plus size={12} /> Add Question
                </button>
              </div>
            </div>
            {questions.length > 0 ? (
              <div className="space-y-2">
                {questions.map((q, _i) => {
                  const qColor = Q_STATUS_COLORS[q.status] || 'var(--color-text-faint-alt)';
                  const isEditing = editingQ === q.id;
                  return (
                    <div key={q.id} className="p-4 rounded-lg border" style={{ borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }} data-testid={`question-${q.id}`}>
                      <div className="flex items-start gap-3">
                        <span className="text-xs font-mono w-6 text-right shrink-0 mt-0.5" style={{ color: c.textDim }}>Q{q.order}</span>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm" style={{ color: c.text }}>{q.text}</p>
                          <div className="flex items-center gap-2 mt-1 flex-wrap">
                            <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded" style={{ background: `${qColor}20`, color: qColor }}>{q.status?.replace('_', ' ')}</span>
                            <span className="text-[10px] capitalize" style={{ color: c.textDim }}>{q.category?.replace('_', ' ')}</span>
                            {q.word_limit && <span className="text-[10px]" style={{ color: c.textDim }}>{q.word_limit} words</span>}
                            {q.weighting && <span className="text-[10px]" style={{ color: 'var(--color-warning)' }}>{q.weighting}%</span>}
                            {q.mandatory && <span className="text-[9px] font-bold px-1 py-0.5 rounded bg-[rgb(var(--rgb-danger-alt)/0.1)] text-[var(--color-danger-alt)]">Required</span>}
                          </div>
                        </div>
                        <button onClick={() => setEditingQ(isEditing ? null : q.id)} className="p-1 rounded-md" style={{ color: 'var(--color-info-ios)' }}>
                          <Edit3 size={14} />
                        </button>
                      </div>
                      {isEditing && (
                        <div className="mt-3 pt-3" style={{ borderTop: `1px solid ${isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)'}` }}>
                          {q.ai_draft && !q.response && (
                            <div className="mb-2 p-3 rounded-md" style={{ background: isDark ? 'var(--color-info-ios)08' : 'var(--color-info-bg)', border: '1px solid rgba(0,122,255,0.15)' }}>
                              <p className="text-[10px] uppercase tracking-wider mb-1" style={{ color: 'var(--color-info-ios)' }}>AI Draft</p>
                              <p className="text-xs whitespace-pre-wrap" style={{ color: c.textMuted }}>{q.ai_draft.substring(0, 300)}{q.ai_draft.length > 300 ? '...' : ''}</p>
                              <button onClick={() => updateQuestion(q.id, { response: q.ai_draft, status: 'draft' })} className="text-[10px] text-[var(--color-info-ios)] mt-1 hover:underline">Use this draft</button>
                            </div>
                          )}
                          {/* Iter 216h101 — KB suggestions panel (top 3 RAG hits) */}
                          {snippetCache[q.id]?.suggestions?.length > 0 && (
                            <div className="mb-2 p-3 rounded-md" style={{ background: 'rgba(25, 205, 255,0.06)', border: '1px solid rgba(25, 205, 255,0.15)' }} data-testid={`kb-suggest-${q.id}`}>
                              <p className="text-[10px] uppercase tracking-wider mb-2 flex items-center gap-1" style={{ color: 'var(--color-accent-magenta)' }}>
                                <Lightbulb size={10} /> Top {snippetCache[q.id].suggestions.length} from bid library
                              </p>
                              <div className="space-y-1.5">
                                {snippetCache[q.id].suggestions.map((s, idx) => (
                                  <div key={idx} className="p-2 rounded-md" style={{ background: isDark ? 'var(--color-surface-dark-2)' : 'rgba(255,255,255,0.6)' }}>
                                    <div className="flex items-center justify-between gap-2 mb-0.5">
                                      <span className="text-[10px] font-bold" style={{ color: c.text }}>{s.title}</span>
                                      <span className="text-[9px] font-mono" style={{ color: c.textDim }}>match {s.score}</span>
                                    </div>
                                    <p className="text-[10px] line-clamp-2" style={{ color: c.textMuted }}>{s.text.substring(0, 220)}…</p>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                          <LiveResponseEditor
                            initial={q.response || q.ai_draft || ''}
                            wordLimit={q.word_limit}
                            onSave={(value) => updateQuestion(q.id, { response: value, status: value.trim() ? 'draft' : 'not_started' })}
                            inputStyle={inputStyle}
                            color={c}
                            testid={`response-${q.id}`}
                          />
                          {Array.isArray(q.ai_citations) && q.ai_citations.length > 0 && (
                            <div className="mb-2 mt-1 text-[10px]" style={{ color: c.textMuted }} data-testid={`citations-${q.id}`}>
                              <strong style={{ color: c.textMuted }}>Citations:</strong>{' '}
                              {q.ai_citations.map((cit) => (
                                <span key={cit.index} className="inline-block mr-2">[{cit.index}] {cit.title}</span>
                              ))}
                            </div>
                          )}
                          <QuestionFigures API={API} headers={headers} tenderId={tenderId} qId={q.id} figures={q.figures} onChange={load} c={c} isDark={isDark} inputStyle={inputStyle} />
                          <QuestionEvidence API={API} headers={headers} tenderId={tenderId} qId={q.id} evidence={q.evidence_sources} kbItems={kbItems} onChange={load} c={c} isDark={isDark} inputStyle={inputStyle} />
                          <div className="flex items-center justify-between flex-wrap gap-2">
                            <div className="flex items-center gap-1 flex-wrap">
                              {['not_started', 'draft', 'reviewed', 'final'].map(s => (
                                <button key={s} onClick={() => updateQuestion(q.id, { status: s })}
                                  className={`px-2 py-1 text-[10px] rounded-md ${q.status === s ? 'bg-[var(--color-info-ios)] text-white' : ''}`}
                                  style={q.status !== s ? { background: isDark ? 'var(--color-ink-alt)' : 'var(--color-neutral-100)', color: c.textDim } : {}}>
                                  {s.replace('_', ' ')}
                                </button>
                              ))}
                              {templates.length > 0 && (
                                <select
                                  onChange={(e) => { applyTemplate(q.id, e.target.value); e.target.value = ''; }}
                                  defaultValue=""
                                  className="ml-1 px-2 py-1 text-[10px] rounded-md border"
                                  style={{ background: isDark ? 'var(--color-ink-alt)' : 'var(--color-neutral-50)', color: c.textMuted, borderColor: c.border }}
                                  data-testid={`template-picker-${q.id}`}
                                  title="Insert a canned tender response"
                                >
                                  <option value="">Insert template…</option>
                                  {templates.map((t) => (
                                    <option key={t.id} value={t.id}>{t.label}</option>
                                  ))}
                                </select>
                              )}
                            </div>
                            <div className="flex gap-1 flex-wrap">
                              <button onClick={() => fetchSnippets(q.id)} disabled={!!aiLoading || snippetCache[q.id]?.loading}
                                className="flex items-center gap-1 px-2 py-1 text-[10px] rounded-md" style={{ background: 'rgba(25, 205, 255,0.12)', color: 'var(--color-accent-magenta)' }}
                                data-testid={`suggest-kb-${q.id}`}>
                                {snippetCache[q.id]?.loading ? <Loader2 size={10} className="animate-spin" /> : <Lightbulb size={10} />} Suggest from KB
                              </button>
                              <button onClick={() => aiGenerateResponse(q.id, 'generate')} disabled={!!aiLoading}
                                className="flex items-center gap-1 px-2 py-1 text-[10px] rounded-md" style={{ background: 'var(--color-success-alt)15', color: 'var(--color-success-alt)' }}>
                                {aiLoading === `gen-${q.id}` ? <Loader2 size={10} className="animate-spin" /> : <Sparkles size={10} />} Generate
                              </button>
                              {q.response && <>
                                <button onClick={() => aiGenerateResponse(q.id, 'rewrite_higher_score')} disabled={!!aiLoading}
                                  className="px-2 py-1 text-[10px] rounded-md" style={{ background: 'var(--color-warning)15', color: 'var(--color-warning)' }}>
                                  Higher Score
                                </button>
                                <button onClick={() => aiGenerateResponse(q.id, 'reduce_word_count')} disabled={!!aiLoading}
                                  className="px-2 py-1 text-[10px] rounded-md" style={{ background: 'var(--color-info-ios)15', color: 'var(--color-info-ios)' }}>
                                  Reduce Words
                                </button>
                              </>}
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="text-center py-8">
                <FileText size={32} className="mx-auto mb-2" style={{ color: c.textDim }} />
                <p className="text-sm" style={{ color: c.textDim }}>No questions yet</p>
                <button onClick={() => setShowAddQ(true)} className="text-xs text-[var(--color-info-ios)] mt-1 hover:underline">Add your first question</button>
              </div>
            )}
          </div>
        )}

        {/* Documents */}
        {activeTab === 'documents' && (
          <div>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold" style={{ color: c.text }}>Tender Documents</h3>
              <div>
                <input type="file" onChange={uploadDoc} ref={fileRef} className="hidden" id="tender-doc-upload" />
                <label htmlFor="tender-doc-upload" className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-[var(--color-info-ios)] text-white text-xs font-medium rounded-md cursor-pointer" data-testid="upload-tender-doc-btn">
                  <Upload size={12} /> {uploading ? 'Uploading...' : 'Upload Document'}
                </label>
              </div>
            </div>
            {docs.length > 0 ? (
              <div className="space-y-2">
                {docs.map(d => (
                  <div key={d.id} className="flex items-center gap-3 p-3 rounded-md border" style={{ borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }} data-testid={`tender-doc-${d.id}`}>
                    <FileText size={16} style={{ color: 'var(--color-info-ios)' }} />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate" style={{ color: c.text }}>{d.original_filename}</p>
                      <p className="text-[11px]" style={{ color: c.textDim }}>
                        {d.uploaded_by} &middot; {new Date(d.created_at).toLocaleDateString('en-GB')}
                        {typeof d.extracted_chars === 'number' && (
                          <> &middot; <span style={{ color: d.extracted_chars >= 40 ? 'var(--color-success-alt)' : 'var(--color-warning)' }}>
                            {d.extracted_chars >= 40 ? `${d.extracted_chars.toLocaleString()} chars extracted` : 'no text — likely scanned'}
                          </span></>
                        )}
                      </p>
                    </div>
                    {typeof d.extracted_chars === 'number' && d.extracted_chars >= 40 && (
                      <button
                        onClick={() => aiParseFromDoc(d.id)}
                        disabled={!!aiLoading}
                        className="flex items-center gap-1 px-2 py-1 text-[10px] font-semibold rounded-md disabled:opacity-50"
                        style={{ background: 'var(--color-success-alt)15', color: 'var(--color-success-alt)' }}
                        data-testid={`parse-from-doc-${d.id}`}
                      >
                        {aiLoading === `parse-doc-${d.id}` ? <Loader2 size={10} className="animate-spin" /> : <Sparkles size={10} />} Parse questions from this doc
                      </button>
                    )}
                    {typeof d.extracted_chars === 'number' && d.extracted_chars < 40 && (
                      <button
                        onClick={() => ocrDoc(d.id)}
                        disabled={!!aiLoading}
                        className="flex items-center gap-1 px-2 py-1 text-[10px] font-semibold rounded-md disabled:opacity-50"
                        style={{ background: 'var(--color-warning)15', color: 'var(--color-warning)' }}
                        data-testid={`ocr-doc-${d.id}`}
                        title="Re-extract using Vision OCR (works for scanned PDFs)"
                      >
                        {aiLoading === `ocr-${d.id}` ? <Loader2 size={10} className="animate-spin" /> : <Eye size={10} />} Run Vision OCR
                      </button>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-8 border border-dashed rounded-md" style={{ borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
                <Upload size={28} className="mx-auto mb-2" style={{ color: c.textDim }} />
                <p className="text-sm" style={{ color: c.textDim }}>Upload tender pack documents (PDF, Word, Excel)</p>
              </div>
            )}
          </div>
        )}

        {/* Strategy */}
        {activeTab === 'strategy' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Sparkles size={14} style={{ color: 'var(--color-info-ios)' }} />
                <span className="text-sm font-medium" style={{ color: c.text }}>Win Strategy Engine</span>
              </div>
              <button onClick={aiStrategy} disabled={!!aiLoading}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-[var(--color-info-ios)] text-white text-xs font-medium rounded-md disabled:opacity-50" data-testid="ai-strategy-btn">
                {aiLoading === 'strategy' ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
                {aiLoading === 'strategy' ? 'Analyzing...' : 'Generate Strategy'}
              </button>
            </div>

            {tender.win_probability !== null && tender.win_probability !== undefined && (
              <div className="flex items-center gap-4 p-4 rounded-lg" style={{ background: isDark ? 'var(--color-neutral-950)' : 'var(--color-neutral-50)', border: `1px solid ${isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)'}` }}>
                <div className="text-center">
                  <p className="text-4xl font-bold" style={{ color: tender.win_probability >= 70 ? 'var(--color-success-alt)' : tender.win_probability >= 40 ? 'var(--color-warning)' : 'var(--color-danger-alt)' }}>
                    {tender.win_probability}%
                  </p>
                  <p className="text-[10px] uppercase tracking-wider" style={{ color: c.textDim }}>Win Probability</p>
                </div>
                {tender.executive_summary && (
                  <div className="flex-1 min-w-0 pl-4" style={{ borderLeft: `1px solid ${isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)'}` }}>
                    <p className="text-[10px] uppercase tracking-wider mb-1" style={{ color: c.textDim }}>Executive Summary</p>
                    <p className="text-sm" style={{ color: c.textMuted }}>{tender.executive_summary}</p>
                  </div>
                )}
              </div>
            )}

            {(tender.strengths?.length > 0 || tender.weaknesses?.length > 0 || tender.recommendations?.length > 0) ? (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {tender.strengths?.length > 0 && (
                  <div className="p-3 rounded-lg border" style={{ background: 'var(--color-success-alt)08', borderColor: 'var(--color-success-alt)30' }}>
                    <h4 className="text-xs font-bold mb-2" style={{ color: 'var(--color-success-alt)' }}>Strengths</h4>
                    {tender.strengths.map((s, i) => <p key={i} className="text-xs py-1" style={{ color: c.textMuted }}>+ {s}</p>)}
                  </div>
                )}
                {tender.weaknesses?.length > 0 && (
                  <div className="p-3 rounded-lg border" style={{ background: 'var(--color-danger-alt)08', borderColor: 'var(--color-danger-alt)30' }}>
                    <h4 className="text-xs font-bold mb-2" style={{ color: 'var(--color-danger-alt)' }}>Weaknesses / Gaps</h4>
                    {tender.weaknesses.map((w, i) => <p key={i} className="text-xs py-1" style={{ color: c.textMuted }}>- {w}</p>)}
                  </div>
                )}
                {tender.recommendations?.length > 0 && (
                  <div className="p-3 rounded-lg border" style={{ background: 'var(--color-info-ios)08', borderColor: 'var(--color-info-ios)30' }}>
                    <h4 className="text-xs font-bold mb-2" style={{ color: 'var(--color-info-ios)' }}>Recommendations</h4>
                    {tender.recommendations.map((r, i) => <p key={i} className="text-xs py-1" style={{ color: c.textMuted }}>{r}</p>)}
                  </div>
                )}
              </div>
            ) : (
              <div className="p-4 rounded-lg text-center" style={{ background: isDark ? 'var(--color-info-ios)08' : 'var(--color-info-bg)', border: '1px solid rgba(0,122,255,0.15)' }}>
                <Sparkles size={24} className="mx-auto mb-2" style={{ color: 'var(--color-info-ios)' }} />
                <p className="text-sm" style={{ color: c.textMuted }}>Click "Generate Strategy" to get AI-powered win analysis</p>
                <p className="text-xs mt-1" style={{ color: c.textDim }}>Add questions first for the best results</p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* AI Parse Dialog */}
      {showParse && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setShowParse(false)}>
          <div className="w-full max-w-2xl mx-4 rounded-xl p-6 shadow-2xl max-h-[90vh] overflow-y-auto" style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', border: `1px solid ${c.border}` }} onClick={e => e.stopPropagation()} data-testid="ai-parse-dialog">
            <div className="sticky top-0 z-10 -mx-6 -mt-6 px-6 pt-6 pb-3 mb-3 flex items-center justify-between border-b" style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', borderColor: c.border }}>
              <div className="flex items-center gap-2">
                <Sparkles size={18} style={{ color: 'var(--color-success-alt)' }} />
                <h2 className="text-lg font-semibold" style={{ color: c.text }}>AI Tender Parser</h2>
              </div>
              <button onClick={() => setShowParse(false)} className="p-1 hover:opacity-70" style={{ color: c.textDim }} data-testid="ai-parse-close"><X size={16} /></button>
            </div>
            <p className="text-xs mb-3" style={{ color: c.textDim }}>Paste tender document text below. AI will extract questions, scoring criteria, and weightings automatically.</p>
            <textarea value={parseText} onChange={e => setParseText(e.target.value)} rows={12} placeholder="Paste the full tender document text here..."
              className="w-full px-3 py-2 text-sm rounded-md resize-none mb-3" style={inputStyle} data-testid="parse-text-input" />
            <div className="flex gap-2 justify-end">
              <button onClick={() => setShowParse(false)} className="px-4 py-2 text-sm" style={{ color: c.textMuted }}>Cancel</button>
              <button onClick={aiParse} disabled={aiLoading === 'parse' || parseText.length < 20}
                className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-md text-white disabled:opacity-50" style={{ background: 'var(--color-success-alt)' }} data-testid="parse-submit-btn">
                {aiLoading === 'parse' ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
                {aiLoading === 'parse' ? 'Parsing...' : 'Extract Questions'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Add Question Dialog */}
      {showAddQ && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setShowAddQ(false)}>
          <div className="w-full max-w-lg mx-4 rounded-xl p-6 shadow-2xl" style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', border: `1px solid ${c.border}` }} onClick={e => e.stopPropagation()} data-testid="add-question-dialog">
            <h2 className="text-lg font-semibold mb-4" style={{ color: c.text }}>Add Question</h2>
            <div className="space-y-3">
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Question Text *</label>
                <textarea value={qForm.text} onChange={e => setQForm({ ...qForm, text: e.target.value })} rows={3} className="w-full mt-1 px-3 py-2 text-sm rounded-md resize-none" style={inputStyle} />
              </div>
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Category</label>
                  <select value={qForm.category} onChange={e => setQForm({ ...qForm, category: e.target.value })} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={inputStyle}>
                    {Q_CATEGORIES.map(c => <option key={c} value={c}>{c.replace('_', ' ')}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Word Limit</label>
                  <input type="number" value={qForm.word_limit} onChange={e => setQForm({ ...qForm, word_limit: e.target.value })} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={inputStyle} />
                </div>
                <div>
                  <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Weighting %</label>
                  <input type="number" value={qForm.weighting} onChange={e => setQForm({ ...qForm, weighting: e.target.value })} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={inputStyle} />
                </div>
              </div>
            </div>
            <div className="flex gap-2 mt-4 justify-end">
              <button onClick={() => setShowAddQ(false)} className="px-4 py-2 text-sm" style={{ color: c.textMuted }}>Cancel</button>
              <button onClick={addQuestion} disabled={saving || !qForm.text.trim()} className="px-4 py-2 bg-[var(--color-info-ios)] text-white text-sm font-medium rounded-md disabled:opacity-50">
                {saving ? 'Adding...' : 'Add Question'}
              </button>
            </div>
          </div>
        </div>
      )}
      {/* Slide manager modal (Iter 216h102) */}
      {showPackWizard && (
        <SubmissionPackWizard
          API={API}
          headers={headers}
          tenderId={tenderId}
          tender={tender}
          c={c}
          isDark={isDark}
          onClose={() => setShowPackWizard(false)}
        />
      )}

      {showSlides && (
        <SlideManager
          tenderId={tenderId}
          API={API}
          headers={headers}
          onClose={() => setShowSlides(false)}
          c={c}
          inputStyle={inputStyle}
        />
      )}
    </div>
  );
}

/* ═══ Submission Pack Wizard — DOCX export + org template library (Iter 216h230) ═══ */
const BID_FOCUS_OPTIONS = [
  { id: '', label: 'General / not specified' },
  { id: 'New Equipment Install', label: 'New Equipment Install' },
  { id: 'Service & Maintenance', label: 'Service & Maintenance' },
  { id: 'Design & Build', label: 'Design & Build' },
];

function SubmissionPackWizard({ API, headers, tenderId, tender, c, isDark, onClose }) {
  const [mode, setMode] = useState('templated'); // templated | itt | traceability
  const [templates, setTemplates] = useState([]);
  const [loadingTpls, setLoadingTpls] = useState(true);
  const [selectedTpl, setSelectedTpl] = useState('');
  const [uploading, setUploading] = useState(false);
  const [uploadLabel, setUploadLabel] = useState('');
  const [bidFocus, setBidFocus] = useState('');
  const [tokens, setTokens] = useState([{ find: '', replace: '' }]);
  const [logoB64, setLogoB64] = useState('');
  const [logoName, setLogoName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [previewImg, setPreviewImg] = useState('');
  const [previewImgs, setPreviewImgs] = useState([]);
  const [previewPage, setPreviewPage] = useState(0);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewErr, setPreviewErr] = useState('');
  const fileRef = useRef(null);
  const logoRef = useRef(null);

  const overlayStyle = { background: 'rgba(0,0,0,0.55)' };
  const panelStyle = { background: isDark ? 'var(--color-surface-dark-1, #12151c)' : '#fff', border: `1px solid ${c.border}` };
  const inputStyle = { background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${isDark ? 'var(--color-surface-dark-3)' : 'var(--color-border-alt)'}`, color: c.text };

  // Smart prefill — fill EMPTY token replacements from this tender's linked
  // company + reference so a bidder rarely types common fields. Never
  // overwrites a value already saved on the template.
  function smartPrefill(rows) {
    const client = tender?.company?.name || tender?.issuer || '';
    const reference = tender?.reference || tender?.ref || '';
    const map = {
      CLIENT: client, CUSTOMER: client,
      REFERENCE: reference, REF: reference, TENDER_REF: reference,
      ISSUER: tender?.issuer || '', AUTHORITY: tender?.issuer || '',
      TITLE: tender?.title || '', TENDER_TITLE: tender?.title || '',
      DATE: new Date().toLocaleDateString('en-GB'),
    };
    return (rows || []).map((t) => {
      if ((t.replace || '').trim()) return t;
      const norm = (t.find || '').replace(/[{}]/g, '').trim().replace(/\s+/g, '_').toUpperCase();
      const val = map[norm] || map[norm.replace(/_/g, '')];
      return val ? { ...t, replace: val } : t;
    });
  }

  const loadTemplates = useCallback(async () => {
    setLoadingTpls(true);
    try {
      const r = await axios.get(`${API}/crm/v2/tender-docx-templates`, { headers: headers() });
      const list = r.data?.templates || [];
      setTemplates(list);
      if (list.length && !selectedTpl) {
        setSelectedTpl(list[0].id);
        const saved = (list[0].tokens || []).map((t) => ({ find: t.find || '', replace: t.replace || '' }));
        setTokens(smartPrefill(saved.length ? saved : [{ find: '', replace: '' }]));
      }
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to load templates');
    }
    setLoadingTpls(false);
  }, [API, headers]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { loadTemplates(); }, [loadTemplates]);

  const [savingTokens, setSavingTokens] = useState(false);
  const [tokensSaved, setTokensSaved] = useState(false);

  const selectTemplate = (id) => {
    setSelectedTpl(id);
    const tpl = templates.find((t) => t.id === id);
    const saved = (tpl?.tokens || []).map((t) => ({ find: t.find || '', replace: t.replace || '' }));
    setTokens(smartPrefill(saved.length ? saved : [{ find: '', replace: '' }]));
    setTokensSaved(false);
  };

  const saveTokensToTemplate = async () => {
    if (!selectedTpl) return;
    setSavingTokens(true); setError('');
    try {
      const effTokens = tokens.filter((t) => (t.find || '').trim());
      const r = await axios.put(`${API}/crm/v2/tender-docx-templates/${selectedTpl}`, { tokens: effTokens }, { headers: headers() });
      setTemplates((list) => list.map((t) => t.id === selectedTpl ? { ...t, tokens: r.data?.tokens || effTokens } : t));
      setTokensSaved(true);
      setTimeout(() => setTokensSaved(false), 2500);
    } catch (e) {
      setError(e.response?.data?.detail || 'Could not save tokens to template');
    }
    setSavingTokens(false);
  };

  const uploadTemplate = async (file) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.docx')) { setError('Please choose a .docx file.'); return; }
    setUploading(true); setError('');
    try {
      const fd = new FormData();
      fd.append('file', file);
      const label = encodeURIComponent(uploadLabel || file.name);
      const r = await axios.post(`${API}/crm/v2/tender-docx-templates?label=${label}`, fd, { headers: { ...headers() } });
      setUploadLabel('');
      if (fileRef.current) fileRef.current.value = '';
      await loadTemplates();
      if (r.data?.id) {
        setSelectedTpl(r.data.id);
        const saved = (r.data.tokens || []).map((t) => ({ find: t.find || '', replace: t.replace || '' }));
        setTokens(smartPrefill(saved.length ? saved : [{ find: '', replace: '' }]));
      }
    } catch (e) {
      setError(e.response?.data?.detail || 'Template upload failed');
    }
    setUploading(false);
  };

  const deleteTemplate = async (id) => {
    if (!window.confirm('Delete this template from the library?')) return;
    try {
      await axios.delete(`${API}/crm/v2/tender-docx-templates/${id}`, { headers: headers() });
      if (selectedTpl === id) setSelectedTpl('');
      loadTemplates();
    } catch (e) { setError(e.response?.data?.detail || 'Delete failed'); }
  };

  const setDefaultTemplate = async (id) => {
    try {
      await axios.put(`${API}/crm/v2/tender-docx-templates/${id}`, { is_default: true }, { headers: headers() });
      setTemplates((list) => list.map((t) => ({ ...t, is_default: t.id === id })));
    } catch (e) { setError(e.response?.data?.detail || 'Could not set default'); }
  };

  const renameTemplate = async (id, current) => {
    const label = window.prompt('Rename template', current || '');
    if (label == null || !label.trim() || label.trim() === current) return;
    try {
      const r = await axios.put(`${API}/crm/v2/tender-docx-templates/${id}`, { label: label.trim() }, { headers: headers() });
      setTemplates((list) => list.map((t) => t.id === id ? { ...t, label: r.data?.label || label.trim() } : t));
    } catch (e) { setError(e.response?.data?.detail || 'Rename failed'); }
  };

  const pickLogo = (file) => {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => { setLogoB64(String(reader.result)); setLogoName(file.name); };
    reader.readAsDataURL(file);
  };

  const setToken = (i, key, val) => setTokens((ts) => ts.map((t, idx) => idx === i ? { ...t, [key]: val } : t));
  const addTokenRow = () => setTokens((ts) => [...ts, { find: '', replace: '' }]);
  const removeTokenRow = (i) => setTokens((ts) => ts.filter((_, idx) => idx !== i));

  const download = (blob, suffix) => {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${(tender?.title || 'tender').replace(/[^a-z0-9]+/gi, '_')}-${suffix}.docx`;
    document.body.appendChild(a); a.click(); a.remove();
  };

  const fetchPreview = useCallback(async () => {
    if (mode === 'templated' && !selectedTpl) { setPreviewErr('Pick a template to preview.'); return; }
    setPreviewLoading(true); setPreviewErr('');
    try {
      const effTokens = tokens.filter((t) => (t.find || '').trim());
      if (mode === 'templated' && bidFocus) effTokens.push({ find: '{{SCOPE}}', replace: bidFocus });
      const body = mode === 'templated'
        ? { mode, template_id: selectedTpl, logo_b64: logoB64 || null, tokens: effTokens }
        : { mode };
      const r = await axios.post(`${API}/crm/v2/tenders/${tenderId}/export/preview`, body, { headers: headers() });
      const imgs = r.data?.images || (r.data?.image_b64 ? [r.data.image_b64] : []);
      setPreviewImgs(imgs);
      setPreviewImg(imgs[0] || '');
      setPreviewPage((p) => Math.min(p, Math.max(0, imgs.length - 1)));
    } catch (e) {
      setPreviewErr(e.response?.data?.detail || 'Preview failed');
    }
    setPreviewLoading(false);
  }, [API, headers, tenderId, mode, selectedTpl, tokens, bidFocus, logoB64]);

  // Debounced live refresh once a preview is on screen (edits to tokens / logo / bid focus / mode).
  useEffect(() => {
    if (!previewImg && !previewErr) return; // only after the user opts into preview
    const id = setTimeout(() => { fetchPreview(); }, 1300);
    return () => clearTimeout(id);
  }, [mode, selectedTpl, tokens, bidFocus, logoB64]); // eslint-disable-line react-hooks/exhaustive-deps

  const runExport = async () => {
    setBusy(true); setError('');
    const token = localStorage.getItem('crm_token');
    try {
      if (mode === 'templated') {
        if (!selectedTpl) { setError('Pick a template from the library (or upload one).'); setBusy(false); return; }
        const effTokens = tokens.filter((t) => (t.find || '').trim());
        if (bidFocus) effTokens.push({ find: '{{SCOPE}}', replace: bidFocus });
        const r = await fetch(`${API}/crm/v2/tenders/${tenderId}/export/submission-docx`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
          body: JSON.stringify({ template_id: selectedTpl, logo_b64: logoB64 || null, tokens: effTokens }),
        });
        if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || 'Export failed');
        download(await r.blob(), 'submission');
      } else {
        const path = mode === 'itt' ? 'itt-docx' : 'traceability-docx';
        const r = await fetch(`${API}/crm/v2/tenders/${tenderId}/export/${path}?_t=${Date.now()}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!r.ok) throw new Error('Export failed');
        download(await r.blob(), mode === 'itt' ? 'answers' : 'traceability');
      }
      onClose();
    } catch (e) {
      setError(e.message || 'Export failed');
    }
    setBusy(false);
  };

  const MODES = [
    { id: 'templated', label: 'Templated pack', desc: 'Your .docx template + tokens + logo' },
    { id: 'itt', label: 'ITT-direct', desc: 'Clean, template-free answers doc' },
    { id: 'traceability', label: 'Traceability matrix', desc: 'Answer → supporting evidence sources' },
  ];

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center p-4" style={overlayStyle} data-testid="submission-pack-wizard">
      <div className="w-full max-w-2xl max-h-[88vh] overflow-y-auto rounded-xl shadow-2xl" style={panelStyle}>
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b" style={{ borderColor: c.border }}>
          <div className="flex items-center gap-2">
            <FileText size={18} style={{ color: 'var(--color-success-alt, #16a34a)' }} />
            <h2 className="text-sm font-bold" style={{ color: c.text }}>Submission pack (.docx)</h2>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-md" style={{ color: c.textMuted }} data-testid="pack-wizard-close"><X size={16} /></button>
        </div>

        <div className="p-5 space-y-5">
          {error && <div className="px-3 py-2 rounded-md text-xs" style={{ background: 'var(--color-danger-alt)15', color: 'var(--color-danger-alt)' }} data-testid="pack-wizard-error">{error}</div>}

          {/* Mode selector */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2" data-testid="pack-mode-selector">
            {MODES.map((m) => (
              <button
                key={m.id}
                onClick={() => setMode(m.id)}
                className="text-left p-3 rounded-lg border transition-colors"
                style={{ borderColor: mode === m.id ? 'var(--color-info-ios)' : c.border, background: mode === m.id ? 'var(--color-info-ios)12' : 'transparent' }}
                data-testid={`pack-mode-${m.id}`}
              >
                <p className="text-xs font-bold mb-0.5" style={{ color: mode === m.id ? 'var(--color-info-ios)' : c.text }}>{m.label}</p>
                <p className="text-[10px] leading-tight" style={{ color: c.textDim }}>{m.desc}</p>
              </button>
            ))}
          </div>

          {mode === 'templated' && (
            <>
              {/* Template library */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <p className="text-xs font-semibold" style={{ color: c.text }}>Template library</p>
                  <span className="text-[10px]" style={{ color: c.textDim }}>{templates.length} saved</span>
                </div>
                {loadingTpls ? (
                  <div className="flex items-center gap-2 text-xs py-2" style={{ color: c.textDim }}><Loader2 size={14} className="animate-spin" /> Loading…</div>
                ) : templates.length === 0 ? (
                  <p className="text-xs py-2" style={{ color: c.textDim }} data-testid="pack-no-templates">No templates yet — upload a .docx layout below.</p>
                ) : (
                  <div className="space-y-1.5 mb-3" data-testid="pack-template-list">
                    {templates.map((t) => (
                      <label
                        key={t.id}
                        className="flex items-center gap-2 p-2 rounded-md border cursor-pointer"
                        style={{ borderColor: selectedTpl === t.id ? 'var(--color-info-ios)' : c.border, background: selectedTpl === t.id ? 'var(--color-info-ios)10' : 'transparent' }}
                        data-testid={`pack-template-${t.id}`}
                      >
                        <input type="radio" name="pack-tpl" checked={selectedTpl === t.id} onChange={() => selectTemplate(t.id)} data-testid={`pack-template-radio-${t.id}`} />
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-medium truncate flex items-center gap-1.5" style={{ color: c.text }}>
                            {t.label}
                            {t.is_default && <span className="text-[8px] font-bold uppercase px-1 py-0.5 rounded" style={{ background: 'var(--color-warning)20', color: 'var(--color-warning)' }} data-testid={`pack-template-default-badge-${t.id}`}>Default</span>}
                          </p>
                          <p className="text-[10px]" style={{ color: c.textDim }}>{t.original_filename} · {(t.size / 1024).toFixed(0)}KB{t.tokens?.length ? ` · ${t.tokens.length} saved token${t.tokens.length > 1 ? 's' : ''}` : ''}{t.created_by ? ` · ${t.created_by}` : ''}</p>
                        </div>
                        <button type="button" onClick={(e) => { e.preventDefault(); setDefaultTemplate(t.id); }} className="p-1 rounded" style={{ color: t.is_default ? 'var(--color-warning)' : c.textDim }} title={t.is_default ? 'Default template' : 'Set as default'} data-testid={`pack-template-default-${t.id}`}><Star size={13} fill={t.is_default ? 'var(--color-warning)' : 'none'} /></button>
                        <button type="button" onClick={(e) => { e.preventDefault(); renameTemplate(t.id, t.label); }} className="p-1 rounded" style={{ color: c.textMuted }} title="Rename" data-testid={`pack-template-rename-${t.id}`}><Edit3 size={13} /></button>
                        <button type="button" onClick={(e) => { e.preventDefault(); deleteTemplate(t.id); }} className="p-1 rounded" style={{ color: 'var(--color-danger-alt)' }} data-testid={`pack-template-delete-${t.id}`}><Trash2 size={13} /></button>
                      </label>
                    ))}
                  </div>
                )}
                {/* Upload */}
                <div className="flex items-center gap-2 flex-wrap p-2.5 rounded-md border border-dashed" style={{ borderColor: c.border }}>
                  <input value={uploadLabel} onChange={(e) => setUploadLabel(e.target.value)} placeholder="Label (optional)" className="flex-1 min-w-[120px] px-2 py-1.5 text-xs rounded-md" style={inputStyle} data-testid="pack-upload-label" />
                  <input ref={fileRef} type="file" accept=".docx" onChange={(e) => uploadTemplate(e.target.files?.[0])} className="hidden" data-testid="pack-upload-input" />
                  <button onClick={() => fileRef.current?.click()} disabled={uploading} className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md disabled:opacity-50" style={{ background: 'var(--color-info-ios)', color: '#fff' }} data-testid="pack-upload-btn">
                    {uploading ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />} Upload .docx template
                  </button>
                </div>
              </div>

              {/* Bid focus */}
              <div>
                <label className="text-xs font-semibold block mb-1.5" style={{ color: c.text }}>Bid focus <span className="font-normal" style={{ color: c.textDim }}>(fills <code>{'{{SCOPE}}'}</code> in your template)</span></label>
                <select value={bidFocus} onChange={(e) => setBidFocus(e.target.value)} className="w-full px-3 py-2 text-sm rounded-md" style={inputStyle} data-testid="pack-bid-focus">
                  {BID_FOCUS_OPTIONS.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
                </select>
              </div>

              {/* Find & replace tokens */}
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-xs font-semibold" style={{ color: c.text }}>Find &amp; replace tokens</label>
                  <div className="flex items-center gap-3">
                    {selectedTpl && (
                      <button onClick={saveTokensToTemplate} disabled={savingTokens} className="text-[11px] font-semibold inline-flex items-center gap-1 disabled:opacity-50" style={{ color: tokensSaved ? 'var(--color-success-alt, #16a34a)' : c.textMuted }} data-testid="pack-token-save-to-template" title="Save these tokens as defaults for this template">
                        {savingTokens ? <Loader2 size={12} className="animate-spin" /> : <BookOpen size={12} />} {tokensSaved ? 'Saved to template' : 'Save to template'}
                      </button>
                    )}
                    <button onClick={addTokenRow} className="text-[11px] font-semibold inline-flex items-center gap-1" style={{ color: 'var(--color-info-ios)' }} data-testid="pack-token-add"><Plus size={12} /> Add token</button>
                  </div>
                </div>
                <p className="text-[10px] mb-1.5" style={{ color: c.textDim }}>{'{{CLIENT}}'} and {'{{REFERENCE}}'} auto-fill from this tender's linked company &amp; reference. Save tokens to a template to reuse them on every export.</p>
                <div className="space-y-1.5" data-testid="pack-token-list">
                  {tokens.map((t, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <input value={t.find} onChange={(e) => setToken(i, 'find', e.target.value)} placeholder="Find e.g. {{CLIENT}}" className="flex-1 px-2 py-1.5 text-xs rounded-md" style={inputStyle} data-testid={`pack-token-find-${i}`} />
                      <ChevronRight size={12} style={{ color: c.textDim }} />
                      <input value={t.replace} onChange={(e) => setToken(i, 'replace', e.target.value)} placeholder="Replace with…" className="flex-1 px-2 py-1.5 text-xs rounded-md" style={inputStyle} data-testid={`pack-token-replace-${i}`} />
                      <button onClick={() => removeTokenRow(i)} className="p-1 rounded" style={{ color: 'var(--color-danger-alt)' }} data-testid={`pack-token-remove-${i}`}><X size={13} /></button>
                    </div>
                  ))}
                </div>
              </div>

              {/* Logo */}
              <div>
                <label className="text-xs font-semibold block mb-1.5" style={{ color: c.text }}>Customer logo <span className="font-normal" style={{ color: c.textDim }}>(optional, on the cover)</span></label>
                <div className="flex items-center gap-2">
                  <input ref={logoRef} type="file" accept="image/*" onChange={(e) => pickLogo(e.target.files?.[0])} className="hidden" data-testid="pack-logo-input" />
                  <button onClick={() => logoRef.current?.click()} className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md border" style={{ borderColor: c.border, color: c.textMuted }} data-testid="pack-logo-btn"><Upload size={12} /> Choose logo</button>
                  {logoName && <span className="text-[11px] inline-flex items-center gap-1.5" style={{ color: c.textDim }}>{logoName}<button onClick={() => { setLogoB64(''); setLogoName(''); }} style={{ color: 'var(--color-danger-alt)' }}><X size={12} /></button></span>}
                </div>
              </div>
            </>
          )}

          {mode !== 'templated' && (
            <p className="text-xs px-3 py-3 rounded-md" style={{ background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-100)', color: c.textDim }}>
              {mode === 'itt'
                ? 'Generates a clean, template-free Word document of every answered question — ideal for pasting straight into an ITT portal.'
                : 'Generates an evidence traceability matrix mapping each answer to its supporting knowledge-base sources.'}
            </p>
          )}

          {/* Live document preview (first few pages) */}
          <div data-testid="pack-preview-section">
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-xs font-semibold" style={{ color: c.text }}>Document preview</label>
              <button onClick={fetchPreview} disabled={previewLoading} className="text-[11px] font-semibold inline-flex items-center gap-1 disabled:opacity-50" style={{ color: 'var(--color-info-ios)' }} data-testid="pack-preview-btn">
                {previewLoading ? <Loader2 size={12} className="animate-spin" /> : <Eye size={12} />} {previewImgs.length ? 'Refresh preview' : 'Preview pages'}
              </button>
            </div>
            {previewErr && <p className="text-[11px] mb-1.5" style={{ color: 'var(--color-danger-alt)' }} data-testid="pack-preview-error">{previewErr}</p>}
            <div className="rounded-md border flex items-center justify-center overflow-hidden" style={{ borderColor: c.border, minHeight: 180, background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-100)' }}>
              {previewLoading ? (
                <div className="flex flex-col items-center gap-2 py-8" style={{ color: c.textDim }}>
                  <Loader2 size={20} className="animate-spin" />
                  <span className="text-[11px]">Rendering pages…</span>
                </div>
              ) : previewImgs.length ? (
                <img src={previewImgs[Math.min(previewPage, previewImgs.length - 1)]} alt={`Preview page ${previewPage + 1}`} className="w-full h-auto max-h-[360px] object-contain" data-testid="pack-preview-image" />
              ) : (
                <p className="text-[11px] py-10 text-center px-4" style={{ color: c.textDim }}>Click <strong>Preview pages</strong> to render the first pages with the real template formatting — updates live as you edit.</p>
              )}
            </div>
            {previewImgs.length > 1 && !previewLoading && (
              <div className="flex items-center justify-center gap-3 mt-2" data-testid="pack-preview-pager">
                <button onClick={() => setPreviewPage((p) => Math.max(0, p - 1))} disabled={previewPage === 0} className="p-1.5 rounded-md border disabled:opacity-40" style={{ borderColor: c.border, color: c.textMuted }} data-testid="pack-preview-prev"><ChevronLeft size={14} /></button>
                <span className="text-[11px] font-medium tabular-nums" style={{ color: c.textDim }} data-testid="pack-preview-page-label">Page {Math.min(previewPage, previewImgs.length - 1) + 1} of {previewImgs.length}</span>
                <button onClick={() => setPreviewPage((p) => Math.min(previewImgs.length - 1, p + 1))} disabled={previewPage >= previewImgs.length - 1} className="p-1.5 rounded-md border disabled:opacity-40" style={{ borderColor: c.border, color: c.textMuted }} data-testid="pack-preview-next"><ChevronRight size={14} /></button>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-5 py-4 border-t" style={{ borderColor: c.border }}>
          <button onClick={onClose} className="px-3 py-1.5 text-xs font-medium rounded-md border" style={{ borderColor: c.border, color: c.textMuted }} data-testid="pack-cancel">Cancel</button>
          <button onClick={runExport} disabled={busy} className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold rounded-md disabled:opacity-50" style={{ background: 'var(--color-success-alt, #16a34a)', color: '#fff' }} data-testid="pack-export-btn">
            {busy ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />} Generate .docx
          </button>
        </div>
      </div>
    </div>
  );
}

/* ═══ Slide manager with drag-and-drop reorder (Iter 216h102) ═══ */
function SlideManager({ tenderId, API, headers, onClose, c, inputStyle }) {
  const [slides, setSlides] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editingIdx, setEditingIdx] = useState(null);
  const [dragIdx, setDragIdx] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/crm/v2/tenders/${tenderId}/pitch-slides`, { headers: headers() });
        setSlides(r.data?.slides || []);
      } catch (_) { /* fall back to empty */ }
      setLoading(false);
    })();
  }, [tenderId]); // eslint-disable-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — runs on the listed trigger deps; omitted refs are stable identities or read live state at call time.

  const save = async () => {
    setSaving(true);
    try {
      await axios.put(`${API}/crm/v2/tenders/${tenderId}/pitch-slides`, slides, { headers: headers() });
      onClose();
    } catch (e) {
      alert('Save failed: ' + (e.response?.data?.detail || e.message));
    }
    setSaving(false);
  };

  const onDragStart = (idx) => setDragIdx(idx);
  const onDragOver = (e) => e.preventDefault();
  const onDrop = (idx) => {
    if (dragIdx === null || dragIdx === idx) return;
    const next = [...slides];
    const [moved] = next.splice(dragIdx, 1);
    next.splice(idx, 0, moved);
    setSlides(next);
    setDragIdx(null);
  };
  const update = (idx, key, val) => {
    const next = [...slides];
    next[idx] = { ...next[idx], [key]: val };
    setSlides(next);
  };
  const remove = (idx) => setSlides(slides.filter((_, i) => i !== idx));
  const add = () => setSlides([...slides, { title: 'New slide', kicker: '', subtitle: '', bullets: [], body: '' }]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" data-testid="slide-manager">
      <button type="button" aria-label="Close" onClick={onClose} className="absolute inset-0 bg-zinc-900/40 backdrop-blur-sm" />
      <div className="relative w-full max-w-3xl max-h-[88vh] rounded-2xl shadow-2xl overflow-hidden flex flex-col" style={{ background: c.bg, border: `1px solid ${c.border}` }}>
        <div className="px-6 py-4 border-b flex items-center justify-between" style={{ borderColor: c.border }}>
          <h3 className="text-sm font-semibold" style={{ color: c.text }}>Pitch deck slides ({slides.length})</h3>
          <button type="button" onClick={onClose} style={{ color: c.textMuted }}><X size={16} /></button>
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          {loading && <p className="text-xs text-center py-6" style={{ color: c.textDim }}>Loading slides…</p>}
          {!loading && slides.map((s, i) => {
            const isEditing = editingIdx === i;
            return (
              <div
                key={i}
                draggable
                onDragStart={() => onDragStart(i)}
                onDragOver={onDragOver}
                onDrop={() => onDrop(i)}
                className="p-3 rounded-lg border"
                style={{ borderColor: c.border, background: dragIdx === i ? 'rgba(25, 205, 255,0.06)' : 'transparent' }}
                data-testid={`slide-row-${i}`}
              >
                <div className="flex items-center gap-3 cursor-move">
                  <span className="text-xs font-mono w-7 text-center" style={{ color: c.textDim }}>≡{i + 1}</span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold truncate" style={{ color: c.text }}>{s.title}</p>
                    {s.subtitle && <p className="text-[11px] truncate" style={{ color: c.textMuted }}>{s.subtitle}</p>}
                  </div>
                  <button onClick={() => setEditingIdx(isEditing ? null : i)} className="p-1 rounded" style={{ color: 'var(--color-info-ios)' }}><Edit3 size={12} /></button>
                  <button onClick={() => remove(i)} className="p-1 rounded" style={{ color: 'var(--color-danger-alt)' }}><X size={12} /></button>
                </div>
                {isEditing && (
                  <div className="mt-3 grid grid-cols-1 gap-2">
                    <input value={s.kicker || ''} onChange={(e) => update(i, 'kicker', e.target.value)} placeholder="Kicker (small uppercase label)" className="px-2 py-1.5 text-xs rounded" style={inputStyle} />
                    <input value={s.title || ''} onChange={(e) => update(i, 'title', e.target.value)} placeholder="Slide title" className="px-2 py-1.5 text-sm font-semibold rounded" style={inputStyle} />
                    <input value={s.subtitle || ''} onChange={(e) => update(i, 'subtitle', e.target.value)} placeholder="Subtitle" className="px-2 py-1.5 text-xs rounded" style={inputStyle} />
                    <textarea value={(s.bullets || []).join('\n')} onChange={(e) => update(i, 'bullets', e.target.value.split('\n').filter(Boolean))} placeholder="Bullets — one per line" rows={4} className="px-2 py-1.5 text-xs rounded" style={inputStyle} />
                  </div>
                )}
              </div>
            );
          })}
          {!loading && (
            <button type="button" onClick={add} className="w-full px-3 py-2 text-xs font-semibold rounded-md border border-dashed" style={{ borderColor: c.border, color: c.textMuted }} data-testid="slide-add">
              + Add slide
            </button>
          )}
        </div>
        <div className="px-6 py-3 border-t flex items-center justify-end gap-2" style={{ borderColor: c.border, background: c.bgPanel }}>
          <button type="button" onClick={onClose} className="px-3 py-1.5 text-xs rounded-md border" style={{ borderColor: c.border, color: c.textMuted }}>Cancel</button>
          <button
            type="button"
            onClick={save}
            disabled={saving || slides.length === 0}
            className="px-3 py-1.5 text-xs font-semibold rounded-md disabled:opacity-50"
            style={{ background: 'var(--color-info-ios)', color: '#fff' }}
            data-testid="slide-save"
          >
            {saving ? 'Saving…' : 'Save slide order'}
          </button>
        </div>
      </div>
    </div>
  );
}
function LiveResponseEditor({ initial, wordLimit, onSave, inputStyle, color, testid }) {
  const [value, setValue] = useState(initial || '');
  useEffect(() => { setValue(initial || ''); }, [initial]);
  const words = value.trim() ? value.trim().split(/\s+/).length : 0;
  const overLimit = wordLimit && words > wordLimit;
  const nearLimit = wordLimit && words > wordLimit * 0.9 && !overLimit;
  return (
    <div>
      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={() => onSave(value)}
        rows={7}
        placeholder="Write your response — direct answer first, then evidence, differentiation, benefit, risk mitigation."
        className="w-full px-3 py-2 text-sm rounded-md resize-y mb-1"
        style={inputStyle}
        data-testid={testid}
      />
      <div className="flex items-center justify-between text-[10px] mb-2" style={{ color: color.textDim }}>
        <span>{wordLimit ? `Suggested ${wordLimit} words · evidence first` : 'No word limit set'}</span>
        <span style={{ color: overLimit ? 'var(--color-danger-alt)' : nearLimit ? 'var(--color-warning)' : color.textDim }}>
          <strong>{words}</strong>{wordLimit ? ` / ${wordLimit}` : ''} words
          {overLimit && ` · ${words - wordLimit} over`}
        </span>
      </div>
    </div>
  );
}


/* ═══ Phase 2 — Figure management per tender answer ═══ */
function QuestionFigures({ API, headers, tenderId, qId, figures, onChange, c, isDark, inputStyle }) {
  const [thumbs, setThumbs] = useState({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const inputRef = useRef(null);
  const figs = figures || [];
  const figKey = figs.map((f) => f.id).join(',');

  useEffect(() => {
    figs.forEach((f) => {
      setThumbs((prev) => {
        if (prev[f.id]) return prev;
        axios.get(`${API}/crm/v2/tenders/${tenderId}/questions/${qId}/figures/${f.id}/data`, { headers: headers() })
          .then((r) => setThumbs((t) => ({ ...t, [f.id]: r.data?.data_url })))
          .catch(() => {});
        return prev;
      });
    });
  }, [figKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const upload = async (file) => {
    if (!file) return;
    if (!file.type.startsWith('image/')) { setErr('Please choose an image (PNG or JPG).'); return; }
    setBusy(true); setErr('');
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('caption', '');
      await axios.post(`${API}/crm/v2/tenders/${tenderId}/questions/${qId}/figures`, fd, { headers: headers() });
      onChange();
    } catch (e) { setErr(e.response?.data?.detail || 'Upload failed'); }
    setBusy(false);
    if (inputRef.current) inputRef.current.value = '';
  };

  const saveCaption = async (figId, caption) => {
    try { await axios.put(`${API}/crm/v2/tenders/${tenderId}/questions/${qId}/figures/${figId}`, { caption }, { headers: headers() }); onChange(); } catch (_) { /* noop */ }
  };
  const remove = async (figId) => {
    if (!window.confirm('Remove this figure?')) return;
    try { await axios.delete(`${API}/crm/v2/tenders/${tenderId}/questions/${qId}/figures/${figId}`, { headers: headers() }); onChange(); } catch (_) { /* noop */ }
  };
  const move = async (idx, dir) => {
    const next = [...figs];
    const j = idx + dir;
    if (j < 0 || j >= next.length) return;
    [next[idx], next[j]] = [next[j], next[idx]];
    try { await axios.put(`${API}/crm/v2/tenders/${tenderId}/questions/${qId}/figures/reorder`, { order: next.map((f) => f.id) }, { headers: headers() }); onChange(); } catch (_) { /* noop */ }
  };

  return (
    <div className="mb-3 mt-2 p-2.5 rounded-md border" style={{ borderColor: c.border }} data-testid={`figures-${qId}`}>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[11px] font-semibold inline-flex items-center gap-1" style={{ color: c.text }}><ImageIcon size={12} /> Figures {figs.length ? `(${figs.length})` : ''}</span>
        <input ref={inputRef} type="file" accept="image/*" onChange={(e) => upload(e.target.files?.[0])} className="hidden" data-testid={`figure-upload-input-${qId}`} />
        <button onClick={() => inputRef.current?.click()} disabled={busy} className="text-[11px] font-semibold inline-flex items-center gap-1 disabled:opacity-50" style={{ color: 'var(--color-info-ios)' }} data-testid={`figure-upload-btn-${qId}`}>
          {busy ? <Loader2 size={11} className="animate-spin" /> : <Upload size={11} />} Add figure
        </button>
      </div>
      {err && <p className="text-[10px] mb-1" style={{ color: 'var(--color-danger-alt)' }} data-testid={`figure-error-${qId}`}>{err}</p>}
      {figs.length === 0 ? (
        <p className="text-[10px]" style={{ color: c.textDim }}>Attach floor plans, charts, or accreditation images — they embed under this answer in the .docx pack.</p>
      ) : (
        <div className="space-y-1.5" data-testid={`figure-list-${qId}`}>
          {figs.map((f, idx) => (
            <div key={f.id} className="flex items-center gap-2 p-1.5 rounded-md" style={{ background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-100)' }} data-testid={`figure-row-${f.id}`}>
              <div className="w-12 h-12 rounded overflow-hidden shrink-0 flex items-center justify-center" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}` }}>
                {thumbs[f.id] ? <img src={thumbs[f.id]} alt="figure" className="w-full h-full object-cover" /> : <ImageIcon size={16} style={{ color: c.textDim }} />}
              </div>
              <div className="flex-1 min-w-0">
                <input defaultValue={f.caption || ''} onBlur={(e) => { if (e.target.value !== (f.caption || '')) saveCaption(f.id, e.target.value); }} placeholder={`Caption for Figure ${idx + 1}`} className="w-full px-2 py-1 text-[11px] rounded" style={inputStyle} data-testid={`figure-caption-${f.id}`} />
                <p className="text-[9px] mt-0.5 truncate" style={{ color: c.textDim }}>{f.original_filename} · {(f.size / 1024).toFixed(0)}KB</p>
              </div>
              <div className="flex flex-col">
                <button onClick={() => move(idx, -1)} disabled={idx === 0} className="p-0.5 disabled:opacity-30" style={{ color: c.textMuted }} title="Move up" data-testid={`figure-up-${f.id}`}><ChevronRight size={12} className="-rotate-90" /></button>
                <button onClick={() => move(idx, 1)} disabled={idx === figs.length - 1} className="p-0.5 disabled:opacity-30" style={{ color: c.textMuted }} title="Move down" data-testid={`figure-down-${f.id}`}><ChevronRight size={12} className="rotate-90" /></button>
              </div>
              <button onClick={() => remove(f.id)} className="p-1 rounded" style={{ color: 'var(--color-danger-alt)' }} data-testid={`figure-remove-${f.id}`}><Trash2 size={12} /></button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ═══ Phase 2 — Deep evidence traceability mapping per answer ═══ */
function QuestionEvidence({ API, headers, tenderId, qId, evidence, kbItems, onChange, c, isDark, inputStyle }) {
  const [rows, setRows] = useState(evidence || []);
  const [saved, setSaved] = useState(false);
  useEffect(() => { setRows(evidence || []); }, [qId]); // eslint-disable-line react-hooks/exhaustive-deps

  const persist = async (next) => {
    try {
      await axios.put(`${API}/crm/v2/tenders/${tenderId}/questions/${qId}/evidence`, { evidence_sources: next }, { headers: headers() });
      setSaved(true); setTimeout(() => setSaved(false), 2000);
      onChange();
    } catch (_) { /* noop */ }
  };
  const addFromKb = (kbId) => {
    if (!kbId) return;
    const item = (kbItems || []).find((k) => k.id === kbId);
    if (!item) return;
    const next = [...rows, { title: item.title, reference: '', kb_id: item.id }];
    setRows(next); persist(next);
  };
  const addManual = () => setRows([...rows, { title: '', reference: '', kb_id: null }]);
  const setField = (i, key, val) => setRows(rows.map((r, idx) => idx === i ? { ...r, [key]: val } : r));
  const removeRow = (i) => { const next = rows.filter((_, idx) => idx !== i); setRows(next); persist(next); };

  return (
    <div className="mb-3 p-2.5 rounded-md border" style={{ borderColor: c.border }} data-testid={`evidence-${qId}`}>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[11px] font-semibold inline-flex items-center gap-1" style={{ color: c.text }}><FileCheck2 size={12} /> Supporting evidence {rows.length ? `(${rows.length})` : ''}</span>
        <div className="flex items-center gap-2">
          {saved && <span className="text-[10px]" style={{ color: 'var(--color-success-alt, #16a34a)' }} data-testid={`evidence-saved-${qId}`}>Saved</span>}
          {(kbItems || []).length > 0 && (
            <select onChange={(e) => { addFromKb(e.target.value); e.target.value = ''; }} defaultValue="" className="px-2 py-1 text-[10px] rounded-md border" style={{ background: isDark ? 'var(--color-ink-alt)' : 'var(--color-neutral-50)', color: c.textMuted, borderColor: c.border }} data-testid={`evidence-kb-picker-${qId}`} title="Add from knowledge base">
              <option value="">From KB…</option>
              {(kbItems || []).map((k) => <option key={k.id} value={k.id}>{k.title}</option>)}
            </select>
          )}
          <button onClick={addManual} className="text-[11px] font-semibold inline-flex items-center gap-1" style={{ color: 'var(--color-info-ios)' }} data-testid={`evidence-add-${qId}`}><Plus size={11} /> Source</button>
        </div>
      </div>
      {rows.length === 0 ? (
        <p className="text-[10px]" style={{ color: c.textDim }}>Map this answer to its proof (e.g. "ISO 9001 certificate — p.2"). Feeds the Evidence Traceability Matrix export.</p>
      ) : (
        <div className="space-y-1.5" data-testid={`evidence-list-${qId}`}>
          {rows.map((r, i) => (
            <div key={i} className="flex items-center gap-2" data-testid={`evidence-row-${qId}-${i}`}>
              {r.kb_id ? <BookOpen size={12} style={{ color: 'var(--color-accent-magenta)' }} title="From knowledge base" /> : <FileText size={12} style={{ color: c.textDim }} />}
              <input value={r.title} onChange={(e) => setField(i, 'title', e.target.value)} onBlur={() => persist(rows)} placeholder="Source / document title" className="flex-1 px-2 py-1 text-[11px] rounded" style={inputStyle} data-testid={`evidence-title-${qId}-${i}`} />
              <input value={r.reference || ''} onChange={(e) => setField(i, 'reference', e.target.value)} onBlur={() => persist(rows)} placeholder="Ref / page" className="w-24 px-2 py-1 text-[11px] rounded" style={inputStyle} data-testid={`evidence-ref-${qId}-${i}`} />
              <button onClick={() => removeRow(i)} className="p-1 rounded" style={{ color: 'var(--color-danger-alt)' }} data-testid={`evidence-remove-${qId}-${i}`}><X size={12} /></button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}


/* ═══ Win/Loss analytics rollup (Iter 216h102) ═══ */
function TenderAnalyticsTab({ API, headers, c, isDark }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const r = await axios.get(`${API}/crm/v2/tenders/analytics/win-loss`, { headers: headers() });
        if (alive) { setData(r.data); setLoading(false); }
      } catch (e) {
        if (alive) { setError(e.response?.data?.detail || 'Failed to load analytics'); setLoading(false); }
      }
    })();
    return () => { alive = false; };
  }, [API, headers]);

  if (loading) {
    return <div className="flex items-center justify-center h-32" data-testid="tender-analytics-loading"><Loader2 size={20} className="animate-spin" style={{ color: 'var(--color-info-ios)' }} /></div>;
  }
  if (error) {
    return <div className="p-4 rounded-lg text-center" style={{ background: 'var(--color-danger-alt)08', color: 'var(--color-danger-alt)' }}>{error}</div>;
  }
  if (!data) return null;

  const fmt = (n) => formatMoneySync(n, { minimumFractionDigits: 0, maximumFractionDigits: 0 });
  const decided = data.decided || 0;

  if (decided === 0) {
    return (
      <div className="text-center py-12 rounded-lg border border-dashed" style={{ borderColor: c.border }} data-testid="tender-analytics-empty">
        <TrendingUp size={36} className="mx-auto mb-2" style={{ color: c.textDim }} />
        <p className="text-sm font-semibold mb-1" style={{ color: c.text }}>No closed tenders yet</p>
        <p className="text-xs" style={{ color: c.textDim }}>Mark tenders as <strong>Won</strong> or <strong>Lost</strong> to populate this dashboard.</p>
      </div>
    );
  }

  const kpis = [
    { l: 'Win rate', v: `${data.win_rate_pct}%`, col: data.win_rate_pct >= 50 ? 'var(--color-success-alt)' : 'var(--color-warning)' },
    { l: 'Tenders decided', v: decided, col: 'var(--color-info-ios)' },
    { l: 'Value won', v: fmt(data.won_value), col: 'var(--color-success-alt)' },
    { l: 'Value lost', v: fmt(data.lost_value), col: 'var(--color-danger-alt)' },
  ];

  return (
    <div className="space-y-4" data-testid="tender-analytics-panel">
      {/* KPIs */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {kpis.map((k) => (
          <div key={k.l} className="p-3 rounded-lg border" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: c.border }}>
            <p className="text-[10px] uppercase tracking-wider" style={{ color: c.textDim }}>{k.l}</p>
            <p className="text-lg font-bold" style={{ color: k.col }}>{k.v}</p>
          </div>
        ))}
      </div>

      {/* By issuer */}
      <div className="rounded-lg border p-4" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: c.border }} data-testid="tender-analytics-by-issuer">
        <h3 className="text-sm font-semibold mb-3" style={{ color: c.text }}>Top issuers</h3>
        {data.by_issuer?.length > 0 ? (
          <div className="space-y-2">
            {data.by_issuer.map((r, i) => (
              <div key={i} className="flex items-center gap-3" data-testid={`issuer-row-${i}`}>
                <span className="text-xs flex-1 truncate" style={{ color: c.text }}>{r.issuer}</span>
                <span className="text-[10px] font-mono" style={{ color: c.textDim }}>{r.won}W / {r.lost}L</span>
                <div className="w-32 h-1.5 rounded-full overflow-hidden" style={{ background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-border-alt)' }}>
                  <div className="h-full" style={{ width: `${r.win_rate}%`, background: r.win_rate >= 50 ? 'var(--color-success-alt)' : 'var(--color-warning)' }} />
                </div>
                <span className="text-[11px] font-bold w-12 text-right" style={{ color: r.win_rate >= 50 ? 'var(--color-success-alt)' : 'var(--color-warning)' }}>{r.win_rate}%</span>
                <span className="text-[10px] w-20 text-right" style={{ color: c.textDim }}>{fmt(r.won_value)}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs" style={{ color: c.textDim }}>No issuer data yet.</p>
        )}
      </div>

      {/* By type */}
      <div className="rounded-lg border p-4" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: c.border }} data-testid="tender-analytics-by-type">
        <h3 className="text-sm font-semibold mb-3" style={{ color: c.text }}>By tender type</h3>
        {data.by_type?.length > 0 ? (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {data.by_type.map((r, i) => (
              <div key={i} className="p-3 rounded-md border" style={{ borderColor: c.border }} data-testid={`type-cell-${r.type}`}>
                <p className="text-[10px] uppercase tracking-wider" style={{ color: c.textDim }}>{r.type}</p>
                <p className="text-base font-bold" style={{ color: r.win_rate >= 50 ? 'var(--color-success-alt)' : 'var(--color-warning)' }}>{r.win_rate}%</p>
                <p className="text-[10px]" style={{ color: c.textDim }}>{r.won}W / {r.lost}L · {fmt(r.won_value)}</p>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs" style={{ color: c.textDim }}>No type data yet.</p>
        )}
      </div>
    </div>
  );
}


/* ═══ MAIN COMPONENT ═══ */
export default function CRMTenders() {
  const crm = useCRM();
  const [selectedId, setSelectedId] = useState(null);

  // Iter 220an — react to navigateTo('tender', id) deep links from other
  // CRM modules (Company → Tenders, Opportunity → Tenders, global search).
  useEffect(() => {
    if (crm.navTarget && crm.navTarget.type === 'tender' && crm.navTarget.id) {
      setSelectedId(crm.navTarget.id);
      crm.setNavTarget && crm.setNavTarget(null);
    }
  }, [crm]);

  if (selectedId) {
    return <TenderDetail tenderId={selectedId} onBack={() => setSelectedId(null)} {...crm} />;
  }
  return <TenderList onSelect={setSelectedId} {...crm} />;
}
