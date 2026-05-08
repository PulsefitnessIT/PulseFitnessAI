import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useCRM } from './CRMApp';
import {
  Plus, Search, FileText, Upload, Trash2, ChevronRight, ArrowLeft,
  Target, AlertTriangle, CheckCircle, Clock, Award, Shield,
  Sparkles, BarChart3, Edit3, Eye, Send, Copy, BookOpen, Tag,
  Building2, User, Calendar, Loader2, X, Zap, TrendingUp
} from 'lucide-react';
import axios from 'axios';

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
function TenderList({ onSelect, c, isDark, API, headers }) {
  const [tenders, setTenders] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [companies, setCompanies] = useState([]);
  const [form, setForm] = useState({ title: '', type: 'ITT', issuer: '', company_id: '', deadline: '', ai_mode: 'assist', tone: 'professional' });
  const [saving, setSaving] = useState(false);

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

  const handleCreate = async () => {
    if (!form.title.trim()) return;
    setSaving(true);
    try {
      const res = await axios.post(`${API}/crm/v2/tenders`, form, { headers: headers() });
      onSelect(res.data.id);
    } catch (e) { console.error(e); }
    setSaving(false);
  };

  const openCreate = () => { loadCompanies(); setShowCreate(true); };
  const inputStyle = { background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${isDark ? 'var(--color-surface-dark-3)' : 'var(--color-border-alt)'}`, color: c.text };

  if (loading) return <div className="flex items-center justify-center h-64"><div className="w-5 h-5 border-2 border-[var(--color-info-ios)] border-t-transparent rounded-full animate-spin" /></div>;

  return (
    <div data-testid="crm-tender-list">
      <div className="flex items-center justify-end gap-3 mb-3 flex-wrap">
        <p className="text-xs mr-auto" style={{ color: c.textDim }}>{total} tender{total !== 1 ? 's' : ''}</p>
        <button type="button" onClick={openCreate} className="btn-primary" data-testid="create-tender-btn">
          <Plus size={14} /> New Tender
        </button>
      </div>

      {tenders.length === 0 ? (
        <div className="text-center py-16 rounded-lg border" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
          <Award size={40} className="mx-auto mb-3" style={{ color: c.textDim }} />
          <p className="text-sm font-medium" style={{ color: c.textMuted }}>No tenders yet</p>
          <p className="text-xs mt-1" style={{ color: c.textDim }}>Upload a tender pack to start winning contracts</p>
          <button onClick={openCreate} className="text-sm text-[var(--color-info-ios)] mt-3 hover:underline">Create your first tender</button>
        </div>
      ) : (
        <div className="space-y-2">
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
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-semibold truncate" style={{ color: c.text }}>{t.title}</p>
                    <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded" style={{ background: `${statusColor}20`, color: statusColor }}>{t.status}</span>
                    <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded" style={{ background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-100)', color: c.textDim }}>{t.type}</span>
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
        </div>
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
                  <select value={form.company_id || ''} onChange={e => setForm({ ...form, company_id: e.target.value })} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={inputStyle}>
                    <option value="">None</option>
                    {companies.map(co => <option key={co.id} value={co.id}>{co.name}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Deadline</label>
                  <input type="date" value={form.deadline || ''} onChange={e => setForm({ ...form, deadline: e.target.value })} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={inputStyle} />
                </div>
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
    </div>
  );
}

/* ═══ TENDER DETAIL ═══ */
function TenderDetail({ tenderId, onBack, c, isDark, API, headers }) {
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
      const res = await axios.post(`${API}/crm/v2/tenders/${tenderId}/ai/parse`, { text: parseText }, { headers: headers() });
      setShowParse(false); setParseText('');
      load();
    } catch (e) { console.error(e); }
    setAiLoading('');
  };

  const aiGenerateResponse = async (qId, action = 'generate') => {
    setAiLoading(`gen-${qId}`);
    try {
      const res = await axios.post(`${API}/crm/v2/tenders/${tenderId}/questions/${qId}/ai/generate`, { action, tone: tender?.tone }, { headers: headers() });
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

  if (!tender) return <div className="flex items-center justify-center h-64"><div className="w-5 h-5 border-2 border-[var(--color-info-ios)] border-t-transparent rounded-full animate-spin" /></div>;

  const statusColor = STATUS_COLORS[tender.status] || 'var(--color-text-faint-alt)';
  const progress = tender.total_questions > 0 ? Math.round((tender.answered_questions / tender.total_questions) * 100) : 0;
  const questions = tender.questions || [];
  const docs = tender.tender_documents || [];
  const inputStyle = { background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${isDark ? 'var(--color-surface-dark-3)' : 'var(--color-border-alt)'}`, color: c.text };
  const tabs = [
    { id: 'overview', label: 'Overview' },
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
                {questions.map((q, i) => {
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
                          <textarea defaultValue={q.response || q.ai_draft || ''} rows={5} placeholder="Write your response..."
                            className="w-full px-3 py-2 text-sm rounded-md resize-none mb-2" style={inputStyle}
                            onBlur={e => updateQuestion(q.id, { response: e.target.value, status: e.target.value.trim() ? 'draft' : 'not_started' })} />
                          <div className="flex items-center justify-between flex-wrap gap-2">
                            <div className="flex gap-1">
                              {['not_started', 'draft', 'reviewed', 'final'].map(s => (
                                <button key={s} onClick={() => updateQuestion(q.id, { status: s })}
                                  className={`px-2 py-1 text-[10px] rounded-md ${q.status === s ? 'bg-[var(--color-info-ios)] text-white' : ''}`}
                                  style={q.status !== s ? { background: isDark ? 'var(--color-ink-alt)' : 'var(--color-neutral-100)', color: c.textDim } : {}}>
                                  {s.replace('_', ' ')}
                                </button>
                              ))}
                            </div>
                            <div className="flex gap-1">
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
                          {q.response && <span className="text-[10px] block mt-1 text-right" style={{ color: c.textDim }}>{q.response.split(/\s+/).length} words</span>}
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
                  <div key={d.id} className="flex items-center gap-3 p-3 rounded-md border" style={{ borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
                    <FileText size={16} style={{ color: 'var(--color-info-ios)' }} />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate" style={{ color: c.text }}>{d.original_filename}</p>
                      <p className="text-[11px]" style={{ color: c.textDim }}>{d.uploaded_by} &middot; {new Date(d.created_at).toLocaleDateString('en-GB')}</p>
                    </div>
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
    </div>
  );
}

/* ═══ MAIN COMPONENT ═══ */
export default function CRMTenders() {
  const crm = useCRM();
  const [selectedId, setSelectedId] = useState(null);

  if (selectedId) {
    return <TenderDetail tenderId={selectedId} onBack={() => setSelectedId(null)} {...crm} />;
  }
  return <TenderList onSelect={setSelectedId} {...crm} />;
}
