import React, { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import {
  Plus, ArrowLeft, FileText, Upload, Download, Trash2, ShieldAlert,
  CheckCircle2, Circle, ClipboardList, History, AlertTriangle, Loader2, X,
  Sparkles, ClipboardCopy, GitCompare, Layers, WifiOff, CloudOff, RefreshCw, Cloud,
} from 'lucide-react';

const draftKey = (id) => `pis_survey_draft_${id}`;

const REPEATABLE = { site_contacts: 'Contact', rooms: 'Room / Area', equipment: 'Equipment', existing_equipment: 'Existing item', risks: 'Risk' };
const UNITS = ['m', 'cm', 'mm', 'ft/in'];

const fmtDiffVal = (v) => {
  if (v === true) return 'Yes';
  if (v === false) return 'No';
  if (v === null || v === undefined || v === '') return '—';
  if (Array.isArray(v)) return `${v.length} item${v.length === 1 ? '' : 's'}`;
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
};

const statusColor = (s) => {
  if (['approved_for_installation', 'completed'].includes(s)) return 'var(--color-success-alt)';
  if (['installation_risk_identified'].includes(s)) return 'var(--color-error-ios, #ef4444)';
  if (['approved_for_quote', 'awaiting_installation_review', 'awaiting_design_review'].includes(s)) return 'var(--color-accent-amber)';
  if (['archived', 'superseded'].includes(s)) return 'var(--color-text-faint-alt)';
  return 'var(--color-info-ios)';
};
const readinessColor = (s) => {
  if (['ready_for_installation', 'installation_approved'].includes(s)) return 'var(--color-success-alt)';
  if (['risks_need_review', 'information_missing', 'not_ready'].includes(s)) return 'var(--color-accent-amber)';
  return 'var(--color-info-ios)';
};

// ── Schema-driven field ──────────────────────────────────────────────
function Field({ f, value, onChange, c, isDark }) {
  const base = {
    background: isDark ? 'var(--color-surface-dark-2)' : '#fff',
    borderColor: c.border, color: c.text,
  };
  const cls = 'w-full px-3 py-2 text-sm rounded-md border outline-none focus:border-[var(--color-info-ios)]';
  const label = (
    <label className="block text-[11px] font-semibold mb-1" style={{ color: c.textMuted }}>
      {f.label}{f.required && <span style={{ color: 'var(--color-accent-amber)' }}> *</span>}
    </label>
  );
  if (f.type === 'boolean') {
    return (
      <div>
        {label}
        <div className="flex gap-2">
          {[['Yes', true], ['No', false]].map(([lbl, val]) => (
            <button key={lbl} type="button" onClick={() => onChange(val)} data-testid={`field-${f.key}-${lbl.toLowerCase()}`}
              className="px-3 py-1.5 text-xs font-medium rounded-md border transition-all"
              style={value === val ? { background: 'var(--color-info-ios)', color: '#fff', borderColor: 'var(--color-info-ios)' } : { ...base }}>
              {lbl}
            </button>
          ))}
        </div>
      </div>
    );
  }
  if (f.type === 'select') {
    return (
      <div>{label}
        <select value={value || ''} onChange={(e) => onChange(e.target.value)} className={cls} style={base} data-testid={`field-${f.key}`}>
          <option value="">—</option>
          {(f.options || []).map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      </div>
    );
  }
  if (f.type === 'textarea') {
    return (<div>{label}<textarea rows={2} value={value || ''} onChange={(e) => onChange(e.target.value)} className={cls} style={base} data-testid={`field-${f.key}`} /></div>);
  }
  const inputType = f.type === 'number' ? 'number' : (f.type === 'date' ? 'date' : 'text');
  return (
    <div>{label}
      <div className="flex gap-2">
        <input type={inputType} value={value ?? ''} onChange={(e) => onChange(f.type === 'number' ? (e.target.value === '' ? '' : Number(e.target.value)) : e.target.value)}
          className={cls} style={base} data-testid={`field-${f.key}`} />
        {f.unit && (
          <span className="px-2 py-2 text-xs rounded-md border shrink-0" style={{ ...base, color: c.textDim }}>{UNITS[0]}</span>
        )}
      </div>
    </div>
  );
}

// ── Editor ───────────────────────────────────────────────────────────
function SurveyEditor({ surveyId, schema, statuses, readinessStatuses, attachmentCategories, API, headers, c, isDark, onBack }) {
  const [survey, setSurvey] = useState(null);
  const [data, setData] = useState({});
  const [activeSection, setActiveSection] = useState('overview');
  const [saving, setSaving] = useState(false);
  const [attachments, setAttachments] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [uploadCat, setUploadCat] = useState('room_photos');
  const [showStatus, setShowStatus] = useState(false);
  const [statusForm, setStatusForm] = useState({ status: '', reason: '', override: false });
  const [showAudit, setShowAudit] = useState(false);
  const [audit, setAudit] = useState([]);
  const [showAI, setShowAI] = useState(false);
  const [aiMode, setAiMode] = useState('analyse');
  const [aiLoading, setAiLoading] = useState(false);
  const [aiResult, setAiResult] = useState(null);
  const [showVersions, setShowVersions] = useState(false);
  const [versions, setVersions] = useState([]);
  const [diffFrom, setDiffFrom] = useState('');
  const [diffTo, setDiffTo] = useState('');
  const [diffResult, setDiffResult] = useState(null);
  const [diffLoading, setDiffLoading] = useState(false);
  const [online, setOnline] = useState(typeof navigator === 'undefined' ? true : navigator.onLine !== false);
  const [pendingSync, setPendingSync] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [restore, setRestore] = useState(null);
  const skipPersist = useRef(true);
  const pendingRef = useRef(false);
  const dataRef = useRef(data);
  useEffect(() => { dataRef.current = data; }, [data]);
  useEffect(() => { pendingRef.current = pendingSync; }, [pendingSync]);

  const persistLocal = useCallback((d, isDirty) => {
    try { localStorage.setItem(draftKey(surveyId), JSON.stringify({ data: d, savedAt: Date.now(), dirty: isDirty })); } catch { /* quota */ }
  }, [surveyId]);
  const clearLocal = useCallback(() => { try { localStorage.removeItem(draftKey(surveyId)); } catch { /* noop */ } }, [surveyId]);

  const load = useCallback(async () => {
    const res = await axios.get(`${API}/crm/site-surveys/${surveyId}`, { headers: headers() });
    setSurvey(res.data);
    // Offline draft recovery: if a dirty local draft exists, offer to restore.
    let localDraft = null;
    try { localDraft = JSON.parse(localStorage.getItem(draftKey(surveyId)) || 'null'); } catch { localDraft = null; }
    skipPersist.current = true;
    setData(res.data.data || {});
    setTimeout(() => { skipPersist.current = false; }, 0);
    if (localDraft && localDraft.dirty && JSON.stringify(localDraft.data) !== JSON.stringify(res.data.data || {})) {
      setRestore(localDraft);
    } else if (localDraft && !localDraft.dirty) {
      clearLocal();
    }
    const a = await axios.get(`${API}/crm/site-surveys/${surveyId}/attachments`, { headers: headers() });
    setAttachments(a.data.attachments || []);
  }, [surveyId, API, headers, clearLocal]);

  useEffect(() => { load(); }, [load]);

  // Persist every edit to device (survives reload / poor signal).
  useEffect(() => {
    if (skipPersist.current) return;
    persistLocal(data, true);
    setDirty(true);
  }, [data, persistLocal]);

  const save = useCallback(async (silent = false) => {
    setSaving(true);
    try {
      const res = await axios.put(`${API}/crm/site-surveys/${surveyId}`, { data: dataRef.current }, { headers: headers() });
      setSurvey((s) => ({ ...s, ...res.data, data: dataRef.current }));
      setDirty(false); setPendingSync(false); clearLocal();
      if (!silent) toast.success('Survey saved');
      return true;
    } catch (e) {
      const isNetwork = (typeof navigator !== 'undefined' && !navigator.onLine) || e?.code === 'ERR_NETWORK' || !e?.response;
      if (isNetwork) {
        persistLocal(dataRef.current, true); setPendingSync(true); setOnline(false);
        if (!silent) toast('Saved on device — will sync when back online', { icon: '📴' });
      } else if (!silent) { toast.error('Save failed'); }
      return false;
    } finally { setSaving(false); }
  }, [API, surveyId, headers, persistLocal, clearLocal]);

  // Online/offline detection + auto-sync of pending drafts on reconnect.
  useEffect(() => {
    const goOnline = async () => {
      setOnline(true);
      if (pendingRef.current) {
        const ok = await save(true);
        if (ok) toast.success('Reconnected — your draft has been synced');
      }
    };
    const goOffline = () => setOnline(false);
    window.addEventListener('online', goOnline);
    window.addEventListener('offline', goOffline);
    return () => { window.removeEventListener('online', goOnline); window.removeEventListener('offline', goOffline); };
  }, [save]);

  const setSectionField = (secId, key, val) => {
    setData((d) => ({ ...d, [secId]: { ...(d[secId] || {}), [key]: val } }));
  };
  const setRepeatItem = (secId, idx, key, val) => {
    setData((d) => {
      const arr = [...(d[secId] || [])];
      arr[idx] = { ...(arr[idx] || {}), [key]: val };
      return { ...d, [secId]: arr };
    });
  };
  const addRepeatItem = (secId) => setData((d) => ({ ...d, [secId]: [...(d[secId] || []), {}] }));
  const removeRepeatItem = (secId, idx) => setData((d) => ({ ...d, [secId]: (d[secId] || []).filter((_, i) => i !== idx) }));

  const upload = async (file) => {
    if (!file) return;
    if (typeof navigator !== 'undefined' && !navigator.onLine) {
      toast("You're offline — photos & floor plans upload once you're back online", { icon: '📴' });
      return;
    }
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      await axios.post(`${API}/crm/site-surveys/${surveyId}/attachments?category=${uploadCat}`, fd, { headers: { ...headers() } });
      toast.success('File uploaded');
      await load();
    } catch (e) { toast.error(e?.response?.status === 413 ? 'File too large (max 25MB)' : 'Upload failed'); } finally { setUploading(false); }
  };
  const deleteAttachment = async (id) => {
    await axios.delete(`${API}/crm/site-surveys/${surveyId}/attachments/${id}`, { headers: headers() });
    await load();
  };
  const downloadPdf = async () => {
    try {
      const res = await axios.get(`${API}/crm/site-surveys/${surveyId}/handover.pdf`, { headers: headers(), responseType: 'blob' });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a'); a.href = url; a.download = `Installation_Handover_${survey?.reference}.pdf`; a.click();
      URL.revokeObjectURL(url);
    } catch (e) { toast.error('PDF export failed'); }
  };
  const openStatus = () => { setStatusForm({ status: survey.status, reason: '', override: false }); setShowStatus(true); };
  const changeStatus = async () => {
    try {
      await axios.post(`${API}/crm/site-surveys/${surveyId}/status`, statusForm, { headers: headers() });
      toast.success('Status updated');
      setShowStatus(false);
      await load();
    } catch (e) {
      const d = e?.response?.data?.detail;
      toast.error(typeof d === 'object' ? (d.message || 'Update blocked') : (d || 'Update failed'));
    }
  };
  const loadAudit = async () => {
    const res = await axios.get(`${API}/crm/site-surveys/${surveyId}/audit`, { headers: headers() });
    setAudit(res.data.events || []); setShowAudit(true);
  };
  const runAI = async (mode) => {
    setAiMode(mode); setShowAI(true); setAiLoading(true); setAiResult(null);
    const ep = mode === 'analyse' ? 'ai/analyse' : (mode === 'email' ? 'ai/follow-up-email' : 'ai/briefing');
    try {
      const res = await axios.post(`${API}/crm/site-surveys/${surveyId}/${ep}`, {}, { headers: headers() });
      setAiResult(res.data);
    } catch (e) {
      setAiResult({ available: false, error: e?.response?.data?.detail || 'AI request failed' });
    } finally { setAiLoading(false); }
  };
  const insertBriefingToNotes = async (text) => {
    const merged = { ...data, installation_notes: { ...(data.installation_notes || {}), notes: text } };
    setData(merged);
    try {
      await axios.put(`${API}/crm/site-surveys/${surveyId}`, { data: merged }, { headers: headers() });
      toast.success('Inserted into Installation Notes');
      setShowAI(false); await load();
    } catch (e) { toast.error('Insert failed'); }
  };
  const copyText = (t) => { navigator.clipboard?.writeText(t); toast.success('Copied'); };
  const openVersions = async () => {
    setShowVersions(true); setDiffResult(null);
    try {
      const res = await axios.get(`${API}/crm/site-surveys/${surveyId}/versions`, { headers: headers() });
      const vs = res.data.versions || [];
      setVersions(vs);
      if (vs.length >= 2) { setDiffFrom(vs[vs.length - 2].id); setDiffTo(vs[vs.length - 1].id); }
      else if (vs.length === 1) { setDiffFrom(vs[0].id); setDiffTo(vs[0].id); }
    } catch (e) { toast.error('Could not load versions'); }
  };
  const runDiff = async () => {
    if (!diffFrom || !diffTo || diffFrom === diffTo) { toast.error('Pick two different versions'); return; }
    setDiffLoading(true); setDiffResult(null);
    try {
      const res = await axios.get(`${API}/crm/site-surveys/${diffFrom}/diff?compare_to=${diffTo}`, { headers: headers() });
      setDiffResult(res.data);
    } catch (e) { toast.error(e?.response?.data?.detail || 'Diff failed'); } finally { setDiffLoading(false); }
  };

  if (!survey) return <div className="py-10 text-center"><Loader2 className="animate-spin inline" size={20} /></div>;
  const readiness = survey.readiness || { checks: [], critical_missing: [] };
  const section = schema.find((s) => s.id === activeSection);
  const isReadonly = ['archived', 'superseded'].includes(survey.status);

  const panel = { background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: c.border };

  return (
    <div data-testid="survey-editor">
      {restore && (
        <div className="mb-3 p-3 rounded-lg border flex items-center gap-3 flex-wrap" style={{ background: 'var(--color-accent-amber)12', borderColor: 'var(--color-accent-amber)' }} data-testid="survey-restore-banner">
          <CloudOff size={16} style={{ color: 'var(--color-accent-amber)' }} />
          <span className="text-xs flex-1" style={{ color: c.text }}>Unsynced changes were saved on this device (possibly from an offline session). Restore them?</span>
          <button onClick={() => { skipPersist.current = true; setData(restore.data); setTimeout(() => { skipPersist.current = false; setDirty(true); }, 0); setRestore(null); toast.success('Local draft restored'); }} className="px-3 py-1.5 text-xs font-semibold rounded-md bg-[var(--color-info-ios)] text-white" data-testid="survey-restore-confirm">Restore draft</button>
          <button onClick={() => { clearLocal(); setRestore(null); }} className="px-3 py-1.5 text-xs font-medium rounded-md border" style={{ borderColor: c.border, color: c.textMuted }} data-testid="survey-restore-discard">Discard</button>
        </div>
      )}
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <button onClick={onBack} className="p-1.5 rounded-md border" style={{ borderColor: c.border, color: c.textMuted }} data-testid="survey-editor-back"><ArrowLeft size={16} /></button>
        <div className="flex-1 min-w-0">
          <h2 className="text-base font-bold" style={{ color: c.text }}>{survey.reference} · {survey.company_name}</h2>
          <p className="text-xs" style={{ color: c.textDim }}>{survey.site_name || 'No site'} · {survey.survey_type?.replace(/_/g, ' ')}</p>
        </div>
        {/* Offline / sync status */}
        {!online ? (
          <span className="text-[10px] font-bold uppercase px-2 py-1 rounded inline-flex items-center gap-1" style={{ background: 'var(--color-accent-amber)20', color: 'var(--color-accent-amber)' }} data-testid="survey-sync-offline"><WifiOff size={11} /> Offline · saved on device</span>
        ) : pendingSync ? (
          <span className="text-[10px] font-bold uppercase px-2 py-1 rounded inline-flex items-center gap-1" style={{ background: 'var(--color-accent-amber)20', color: 'var(--color-accent-amber)' }} data-testid="survey-sync-pending"><RefreshCw size={11} /> Syncing…</span>
        ) : dirty ? (
          <span className="text-[10px] font-bold uppercase px-2 py-1 rounded inline-flex items-center gap-1" style={{ background: 'var(--color-info-ios)15', color: 'var(--color-info-ios)' }} data-testid="survey-sync-dirty"><CloudOff size={11} /> Unsaved</span>
        ) : (
          <span className="text-[10px] font-bold uppercase px-2 py-1 rounded inline-flex items-center gap-1" style={{ background: 'var(--color-success-alt)15', color: 'var(--color-success-alt)' }} data-testid="survey-sync-synced"><Cloud size={11} /> Synced</span>
        )}
        <span className="text-[10px] font-bold uppercase px-2 py-1 rounded" style={{ background: `${statusColor(survey.status)}20`, color: statusColor(survey.status) }} data-testid="survey-status-badge">
          {statuses.find((s) => s.key === survey.status)?.label || survey.status}
        </span>
        <button onClick={openStatus} disabled={isReadonly} className="px-3 py-1.5 text-xs font-medium rounded-md border" style={{ borderColor: c.border, color: c.textMuted }} data-testid="survey-change-status">Change status</button>
        <button onClick={loadAudit} className="px-3 py-1.5 text-xs font-medium rounded-md border inline-flex items-center gap-1" style={{ borderColor: c.border, color: c.textMuted }} data-testid="survey-audit-btn"><History size={12} /> Audit</button>
        <button onClick={openVersions} className="px-3 py-1.5 text-xs font-medium rounded-md border inline-flex items-center gap-1" style={{ borderColor: c.border, color: c.textMuted }} data-testid="survey-versions-btn"><Layers size={12} /> Versions</button>
        <button onClick={() => runAI('analyse')} className="px-3 py-1.5 text-xs font-semibold rounded-md border inline-flex items-center gap-1" style={{ borderColor: 'var(--color-info-ios)', color: 'var(--color-info-ios)' }} data-testid="survey-ai-btn"><Sparkles size={12} /> AI Assist</button>
        <button onClick={downloadPdf} className="px-3 py-1.5 text-xs font-medium rounded-md border inline-flex items-center gap-1" style={{ borderColor: c.border, color: c.textMuted }} data-testid="survey-handover-pdf"><Download size={12} /> Handover PDF</button>
        <button onClick={() => save(false)} disabled={saving || isReadonly} className="px-4 py-1.5 text-xs font-semibold rounded-md bg-[var(--color-info-ios)] text-white inline-flex items-center gap-1" data-testid="survey-save">
          {saving ? <Loader2 className="animate-spin" size={12} /> : <CheckCircle2 size={12} />} Save
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[200px_1fr_260px] gap-4">
        {/* Section nav */}
        <div className="rounded-lg border p-2 h-fit max-h-[70vh] overflow-y-auto" style={panel} data-testid="survey-section-nav">
          {schema.map((s) => (
            <button key={s.id} onClick={() => { save(true); setActiveSection(s.id); }} data-testid={`survey-nav-${s.id}`}
              className="w-full text-left px-2.5 py-1.5 text-xs rounded-md mb-0.5 transition-all"
              style={activeSection === s.id ? { background: 'var(--color-info-ios)', color: '#fff' } : { color: c.textMuted }}>
              {s.title}
            </button>
          ))}
        </div>

        {/* Section form */}
        <div className="rounded-lg border p-4" style={panel}>
          {section && (
            <>
              <h3 className="text-sm font-bold mb-1" style={{ color: c.text }}>{section.title}</h3>
              {section.help && (
                <div className="flex items-start gap-1.5 mb-3 text-[11px] p-2 rounded-md" style={{ background: section.warn ? 'var(--color-accent-amber)15' : (isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-100)'), color: section.warn ? 'var(--color-accent-amber)' : c.textDim }}>
                  {section.warn && <AlertTriangle size={13} className="shrink-0 mt-0.5" />}<span>{section.help}</span>
                </div>
              )}
              {section.repeatable ? (
                <div className="space-y-4">
                  {(data[section.id] || []).map((item, idx) => (
                    <div key={idx} className="rounded-lg border p-3 relative" style={{ borderColor: c.border }} data-testid={`survey-repeat-${section.id}-${idx}`}>
                      <button onClick={() => removeRepeatItem(section.id, idx)} className="absolute top-2 right-2 p-1 rounded" style={{ color: 'var(--color-error-ios, #ef4444)' }} data-testid={`survey-repeat-remove-${section.id}-${idx}`}><Trash2 size={13} /></button>
                      <p className="text-[11px] font-bold mb-2" style={{ color: c.textDim }}>{REPEATABLE[section.id] || 'Item'} {idx + 1}</p>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        {section.fields.map((f) => (
                          <Field key={f.key} f={f} value={item[f.key]} onChange={(v) => setRepeatItem(section.id, idx, f.key, v)} c={c} isDark={isDark} />
                        ))}
                      </div>
                    </div>
                  ))}
                  <button onClick={() => addRepeatItem(section.id)} className="px-3 py-1.5 text-xs font-medium rounded-md border inline-flex items-center gap-1" style={{ borderColor: c.border, color: 'var(--color-info-ios)' }} data-testid={`survey-repeat-add-${section.id}`}>
                    <Plus size={13} /> Add {REPEATABLE[section.id] || 'item'}
                  </button>
                </div>
              ) : section.id === 'attachments' ? null : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {section.fields.map((f) => (
                    <Field key={f.key} f={f} value={(data[section.id] || {})[f.key]} onChange={(v) => setSectionField(section.id, f.key, v)} c={c} isDark={isDark} />
                  ))}
                </div>
              )}
            </>
          )}

          {/* Attachments block (always available under nav item) */}
          <div className="mt-6 pt-4 border-t" style={{ borderColor: c.border }} data-testid="survey-attachments">
            <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
              <h4 className="text-xs font-bold" style={{ color: c.text }}>Photos / Videos / Floor plans</h4>
              <div className="flex items-center gap-2">
                <select value={uploadCat} onChange={(e) => setUploadCat(e.target.value)} className="px-2 py-1 text-xs rounded-md border" style={{ background: isDark ? 'var(--color-surface-dark-2)' : '#fff', borderColor: c.border, color: c.text }} data-testid="survey-upload-category">
                  {attachmentCategories.map((cat) => <option key={cat.key} value={cat.key}>{cat.label}</option>)}
                </select>
                <label className="px-3 py-1.5 text-xs font-medium rounded-md border inline-flex items-center gap-1 cursor-pointer" style={{ borderColor: c.border, color: 'var(--color-info-ios)' }} data-testid="survey-upload-btn">
                  {uploading ? <Loader2 className="animate-spin" size={12} /> : <Upload size={12} />} Upload
                  <input type="file" className="hidden" onChange={(e) => upload(e.target.files?.[0])} accept="image/*,video/*,.pdf,.dwg,.dxf" />
                </label>
              </div>
            </div>
            {attachments.length === 0 ? <p className="text-xs" style={{ color: c.textDim }}>No files yet.</p> : (
              <div className="space-y-1">
                {attachments.map((a) => (
                  <div key={a.id} className="flex items-center gap-2 text-xs p-1.5 rounded" style={{ background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-100)' }}>
                    <FileText size={13} style={{ color: c.textDim }} />
                    <span className="flex-1 truncate" style={{ color: c.text }}>{a.original_filename}</span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: 'var(--color-info-ios)20', color: 'var(--color-info-ios)' }}>{a.category?.replace(/_/g, ' ')}</span>
                    <a href={`${API}/crm/site-surveys/${surveyId}/attachments/${a.id}/download`} target="_blank" rel="noreferrer" style={{ color: c.textMuted }}><Download size={13} /></a>
                    <button onClick={() => deleteAttachment(a.id)} style={{ color: 'var(--color-error-ios, #ef4444)' }}><Trash2 size={13} /></button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Readiness panel */}
        <div className="rounded-lg border p-4 h-fit" style={panel} data-testid="survey-readiness-panel">
          <div className="flex items-center gap-1.5 mb-2"><ClipboardList size={14} style={{ color: 'var(--color-info-ios)' }} /><h4 className="text-xs font-bold" style={{ color: c.text }}>Installation Readiness</h4></div>
          <div className="text-[11px] font-bold uppercase px-2 py-1 rounded mb-3 inline-block" style={{ background: `${readinessColor(readiness.status)}20`, color: readinessColor(readiness.status) }} data-testid="survey-readiness-status">
            {readinessStatuses.find((s) => s.key === readiness.status)?.label || readiness.status}
          </div>
          {readiness.high_risk && (
            <div className="flex items-center gap-1 text-[11px] mb-2" style={{ color: 'var(--color-accent-amber)' }}><ShieldAlert size={13} /> High/critical risk flagged</div>
          )}
          <div className="space-y-1">
            {(readiness.checks || []).map((ck) => (
              <div key={ck.key} className="flex items-start gap-1.5 text-[11px]" style={{ color: ck.done ? c.text : c.textDim }} data-testid={`readiness-${ck.key}`}>
                {ck.done ? <CheckCircle2 size={13} style={{ color: 'var(--color-success-alt)' }} className="shrink-0 mt-0.5" /> : <Circle size={13} className="shrink-0 mt-0.5" style={{ color: ck.critical ? 'var(--color-accent-amber)' : c.textDim }} />}
                <span>{ck.label}{ck.critical && !ck.done && <span style={{ color: 'var(--color-accent-amber)' }}> (required)</span>}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Status modal */}
      {showStatus && (
        <div className="fixed inset-0 z-[1000] flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.5)' }} onClick={() => setShowStatus(false)}>
          <div className="w-full max-w-md rounded-xl border p-5" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: c.border }} onClick={(e) => e.stopPropagation()} data-testid="survey-status-modal">
            <div className="flex items-center justify-between mb-3"><h3 className="text-sm font-bold" style={{ color: c.text }}>Change status</h3><button onClick={() => setShowStatus(false)}><X size={16} style={{ color: c.textMuted }} /></button></div>
            <select value={statusForm.status} onChange={(e) => setStatusForm((f) => ({ ...f, status: e.target.value }))} className="w-full px-3 py-2 text-sm rounded-md border mb-3" style={{ background: isDark ? 'var(--color-surface-dark-2)' : '#fff', borderColor: c.border, color: c.text }} data-testid="survey-status-select">
              {statuses.filter((s) => !['superseded'].includes(s.key)).map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
            </select>
            {statusForm.status === 'approved_for_installation' && (readiness.critical_missing || []).length > 0 && (
              <div className="mb-3 p-2 rounded-md text-[11px]" style={{ background: 'var(--color-accent-amber)15', color: 'var(--color-accent-amber)' }}>
                <div className="font-bold mb-1 flex items-center gap-1"><AlertTriangle size={12} /> Critical info missing</div>
                {readiness.critical_missing.join(', ')}
                <label className="flex items-center gap-2 mt-2" style={{ color: c.text }}>
                  <input type="checkbox" checked={statusForm.override} onChange={(e) => setStatusForm((f) => ({ ...f, override: e.target.checked }))} data-testid="survey-override-check" />
                  Manager override
                </label>
              </div>
            )}
            <textarea rows={2} placeholder="Reason / note (required for override)" value={statusForm.reason} onChange={(e) => setStatusForm((f) => ({ ...f, reason: e.target.value }))} className="w-full px-3 py-2 text-sm rounded-md border mb-3" style={{ background: isDark ? 'var(--color-surface-dark-2)' : '#fff', borderColor: c.border, color: c.text }} data-testid="survey-status-reason" />
            <button onClick={changeStatus} className="w-full py-2 text-sm font-semibold rounded-md bg-[var(--color-info-ios)] text-white" data-testid="survey-status-confirm">Update status</button>
          </div>
        </div>
      )}

      {/* Audit modal */}
      {showAudit && (
        <div className="fixed inset-0 z-[1000] flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.5)' }} onClick={() => setShowAudit(false)}>
          <div className="w-full max-w-lg rounded-xl border p-5 max-h-[80vh] overflow-y-auto" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: c.border }} onClick={(e) => e.stopPropagation()} data-testid="survey-audit-modal">
            <div className="flex items-center justify-between mb-3"><h3 className="text-sm font-bold" style={{ color: c.text }}>Audit trail</h3><button onClick={() => setShowAudit(false)}><X size={16} style={{ color: c.textMuted }} /></button></div>
            {audit.map((e) => (
              <div key={e.id} className="text-xs py-1.5 border-b" style={{ borderColor: c.border, color: c.text }}>
                <span className="font-semibold">{e.action.replace(/_/g, ' ')}</span> · <span style={{ color: c.textDim }}>{e.user_name} · {new Date(e.created_at).toLocaleString('en-GB')}</span>
                {e.reason && <div style={{ color: c.textDim }}>“{e.reason}”</div>}
              </div>
            ))}
          </div>
        </div>
      )}
      {/* AI Assist modal */}
      {showAI && (
        <div className="fixed inset-0 z-[1000] flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.5)' }} onClick={() => setShowAI(false)}>
          <div className="w-full max-w-2xl rounded-xl border p-5 max-h-[85vh] overflow-y-auto" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: c.border }} onClick={(e) => e.stopPropagation()} data-testid="survey-ai-modal">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-bold inline-flex items-center gap-1.5" style={{ color: c.text }}><Sparkles size={15} style={{ color: 'var(--color-info-ios)' }} /> AI Assist <span className="text-[10px] font-normal px-1.5 py-0.5 rounded" style={{ background: 'var(--color-info-ios)20', color: 'var(--color-info-ios)' }}>advisory only</span></h3>
              <button onClick={() => setShowAI(false)}><X size={16} style={{ color: c.textMuted }} /></button>
            </div>
            <div className="flex gap-1 mb-4">
              {[['analyse', 'Analyse & risks'], ['email', 'Follow-up email'], ['briefing', 'Team briefing']].map(([m, lbl]) => (
                <button key={m} onClick={() => runAI(m)} data-testid={`survey-ai-tab-${m}`}
                  className="px-3 py-1.5 text-xs font-medium rounded-md border transition-all"
                  style={aiMode === m ? { background: 'var(--color-info-ios)', color: '#fff', borderColor: 'var(--color-info-ios)' } : { borderColor: c.border, color: c.textMuted }}>{lbl}</button>
              ))}
            </div>

            {aiLoading ? (
              <div className="py-10 text-center"><Loader2 className="animate-spin inline" size={22} style={{ color: 'var(--color-info-ios)' }} /><p className="text-xs mt-2" style={{ color: c.textDim }}>Reviewing the survey…</p></div>
            ) : !aiResult ? null : aiResult.available === false ? (
              <p className="text-sm py-6 text-center" style={{ color: c.textDim }}>{typeof aiResult.error === 'string' ? aiResult.error : 'AI is unavailable.'}</p>
            ) : aiMode === 'analyse' ? (
              <div className="space-y-4 text-sm" style={{ color: c.text }} data-testid="survey-ai-analyse-result">
                {aiResult.summary && <div><p className="text-[11px] font-bold uppercase mb-1" style={{ color: c.textDim }}>Summary</p><p>{aiResult.summary}</p></div>}
                {aiResult.readiness_recommendation && (
                  <div className="p-2 rounded-md" style={{ background: 'var(--color-info-ios)12' }}>
                    <span className="text-[11px] font-bold uppercase" style={{ color: 'var(--color-info-ios)' }}>Recommendation: {aiResult.readiness_recommendation.recommendation?.replace(/_/g, ' ')}</span>
                    <p className="text-xs mt-0.5" style={{ color: c.textDim }}>{aiResult.readiness_recommendation.reasoning}</p>
                  </div>
                )}
                {(aiResult.risks || []).length > 0 && (
                  <div><p className="text-[11px] font-bold uppercase mb-1" style={{ color: c.textDim }}>Flagged risks</p>
                    <div className="space-y-1">{aiResult.risks.map((r, i) => (
                      <div key={i} className="flex items-start gap-2 text-xs">
                        <span className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded shrink-0" style={{ background: ['high', 'critical'].includes((r.severity || '').toLowerCase()) ? 'var(--color-accent-amber)20' : 'var(--color-info-ios)15', color: ['high', 'critical'].includes((r.severity || '').toLowerCase()) ? 'var(--color-accent-amber)' : 'var(--color-info-ios)' }}>{r.severity} · {r.area}</span>
                        <span>{r.description}</span>
                      </div>))}</div>
                  </div>
                )}
                {(aiResult.missing_information || []).length > 0 && (
                  <div><p className="text-[11px] font-bold uppercase mb-1" style={{ color: c.textDim }}>Missing information</p>
                    <ul className="list-disc pl-4 space-y-0.5 text-xs" style={{ color: c.textDim }}>{aiResult.missing_information.map((m, i) => <li key={i}>{m}</li>)}</ul></div>
                )}
                {(aiResult.suggested_questions || []).length > 0 && (
                  <div><p className="text-[11px] font-bold uppercase mb-1" style={{ color: c.textDim }}>Questions to ask</p>
                    <ul className="list-disc pl-4 space-y-0.5 text-xs" style={{ color: c.textDim }}>{aiResult.suggested_questions.map((q, i) => <li key={i}>{q}</li>)}</ul></div>
                )}
                <p className="text-[10px] pt-2 border-t" style={{ color: c.textDim, borderColor: c.border }}>AI is advisory and cannot approve a site for installation. Review before acting.</p>
              </div>
            ) : aiMode === 'email' ? (
              <div className="text-sm" data-testid="survey-ai-email-result">
                <p className="text-[11px] font-bold uppercase mb-1" style={{ color: c.textDim }}>Subject</p>
                <p className="mb-2" style={{ color: c.text }}>{aiResult.subject}</p>
                <p className="text-[11px] font-bold uppercase mb-1" style={{ color: c.textDim }}>Body</p>
                <pre className="whitespace-pre-wrap text-xs p-2 rounded-md" style={{ background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-100)', color: c.text }}>{aiResult.body}</pre>
                <button onClick={() => copyText(`${aiResult.subject}\n\n${aiResult.body}`)} className="mt-3 px-3 py-1.5 text-xs font-medium rounded-md border inline-flex items-center gap-1" style={{ borderColor: c.border, color: c.textMuted }} data-testid="survey-ai-copy-email"><ClipboardCopy size={12} /> Copy email</button>
              </div>
            ) : (
              <div className="text-sm" data-testid="survey-ai-briefing-result">
                <pre className="whitespace-pre-wrap text-xs p-2 rounded-md" style={{ background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-100)', color: c.text }}>{aiResult.briefing}</pre>
                <div className="flex gap-2 mt-3">
                  <button onClick={() => copyText(aiResult.briefing)} className="px-3 py-1.5 text-xs font-medium rounded-md border inline-flex items-center gap-1" style={{ borderColor: c.border, color: c.textMuted }} data-testid="survey-ai-copy-briefing"><ClipboardCopy size={12} /> Copy</button>
                  <button onClick={() => insertBriefingToNotes(aiResult.briefing)} disabled={isReadonly} className="px-3 py-1.5 text-xs font-semibold rounded-md bg-[var(--color-info-ios)] text-white inline-flex items-center gap-1" data-testid="survey-ai-insert-briefing"><CheckCircle2 size={12} /> Insert into Installation Notes</button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Versions / diff modal */}
      {showVersions && (
        <div className="fixed inset-0 z-[1000] flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.5)' }} onClick={() => setShowVersions(false)}>
          <div className="w-full max-w-3xl rounded-xl border p-5 max-h-[85vh] overflow-y-auto" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: c.border }} onClick={(e) => e.stopPropagation()} data-testid="survey-versions-modal">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-bold inline-flex items-center gap-1.5" style={{ color: c.text }}><Layers size={15} style={{ color: 'var(--color-info-ios)' }} /> Version history &amp; compare</h3>
              <button onClick={() => setShowVersions(false)}><X size={16} style={{ color: c.textMuted }} /></button>
            </div>

            {versions.length <= 1 ? (
              <p className="text-sm py-4" style={{ color: c.textDim }}>This survey has a single version. Use “Change status” to create a new version (supersede) when the survey needs revising after approval.</p>
            ) : (
              <>
                <div className="space-y-1 mb-4">
                  {versions.map((v) => (
                    <div key={v.id} className="flex items-center gap-2 text-xs p-2 rounded" style={{ background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-100)' }} data-testid={`survey-version-${v.version}`}>
                      <span className="font-bold" style={{ color: c.text }}>v{v.version}</span>
                      <span style={{ color: c.textDim }}>{v.reference}</span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: `${statusColor(v.status)}20`, color: statusColor(v.status) }}>{v.status}</span>
                      {v.is_current && <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: 'var(--color-success-alt)20', color: 'var(--color-success-alt)' }}>current</span>}
                      <span className="ml-auto" style={{ color: c.textDim }}>{v.updated_at ? new Date(v.updated_at).toLocaleDateString('en-GB') : ''}</span>
                    </div>
                  ))}
                </div>

                <div className="flex items-end gap-2 mb-4 flex-wrap">
                  <div>
                    <label className="block text-[11px] font-semibold mb-1" style={{ color: c.textMuted }}>Compare</label>
                    <select value={diffFrom} onChange={(e) => setDiffFrom(e.target.value)} className="px-2 py-1.5 text-xs rounded-md border" style={{ background: isDark ? 'var(--color-surface-dark-2)' : '#fff', borderColor: c.border, color: c.text }} data-testid="survey-diff-from">
                      {versions.map((v) => <option key={v.id} value={v.id}>v{v.version} · {v.reference}</option>)}
                    </select>
                  </div>
                  <GitCompare size={16} style={{ color: c.textDim, marginBottom: 8 }} />
                  <div>
                    <label className="block text-[11px] font-semibold mb-1" style={{ color: c.textMuted }}>With</label>
                    <select value={diffTo} onChange={(e) => setDiffTo(e.target.value)} className="px-2 py-1.5 text-xs rounded-md border" style={{ background: isDark ? 'var(--color-surface-dark-2)' : '#fff', borderColor: c.border, color: c.text }} data-testid="survey-diff-to">
                      {versions.map((v) => <option key={v.id} value={v.id}>v{v.version} · {v.reference}</option>)}
                    </select>
                  </div>
                  <button onClick={runDiff} className="px-4 py-1.5 text-xs font-semibold rounded-md bg-[var(--color-info-ios)] text-white inline-flex items-center gap-1" data-testid="survey-diff-run">
                    {diffLoading ? <Loader2 className="animate-spin" size={12} /> : <GitCompare size={12} />} Compare
                  </button>
                </div>

                {diffResult && (
                  <div data-testid="survey-diff-result">
                    <p className="text-xs font-semibold mb-2" style={{ color: c.text }}>
                      {diffResult.changed_count} change{diffResult.changed_count === 1 ? '' : 's'} · v{diffResult.from.version} → v{diffResult.to.version}
                    </p>
                    {diffResult.changed_count === 0 ? (
                      <p className="text-sm py-3" style={{ color: c.textDim }}>No differences between these versions.</p>
                    ) : (
                      <div className="border rounded-lg overflow-hidden" style={{ borderColor: c.border }}>
                        <div className="grid grid-cols-[1.4fr_1fr_1fr] text-[10px] font-bold uppercase" style={{ background: 'var(--color-soft-black, #1B1C1D)', color: '#fff' }}>
                          <div className="p-2">Field</div><div className="p-2">v{diffResult.from.version}</div><div className="p-2">v{diffResult.to.version}</div>
                        </div>
                        {diffResult.changes.map((ch, i) => (
                          <div key={i} className="grid grid-cols-[1.4fr_1fr_1fr] text-xs border-t" style={{ borderColor: c.border }}>
                            <div className="p-2" style={{ color: c.text }}><span style={{ color: c.textDim }}>{ch.section_title} · </span>{ch.label}</div>
                            <div className="p-2" style={{ color: c.textDim, textDecoration: 'line-through' }}>{fmtDiffVal(ch.old)}</div>
                            <div className="p-2 font-medium" style={{ color: 'var(--color-success-alt)' }}>{fmtDiffVal(ch.new)}</div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}

    </div>
  );
}
export default function PreInstallSurveys({ companyId, companyName, siteId, API, headers, c, isDark }) {
  const [meta, setMeta] = useState(null);
  const [surveys, setSurveys] = useState([]);
  const [loading, setLoading] = useState(true);
  const [openId, setOpenId] = useState(null);
  const [sites, setSites] = useState([]);
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState({ site_id: siteId || '', survey_type: 'new_gym_installation', priority: 'normal', target_install_date: '' });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [m, list] = await Promise.all([
        axios.get(`${API}/crm/site-surveys/schema`, { headers: headers() }),
        axios.get(`${API}/crm/site-surveys?company_id=${companyId}${siteId ? `&site_id=${siteId}` : ''}`, { headers: headers() }),
      ]);
      setMeta(m.data);
      setSurveys(list.data.surveys || []);
    } catch (e) { toast.error('Failed to load surveys'); } finally { setLoading(false); }
  }, [API, headers, companyId, siteId]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!showCreate || siteId) return;
    axios.get(`${API}/sites`, { headers: headers() }).then((r) => setSites(r.data.sites || r.data || [])).catch(() => {});
  }, [showCreate, siteId, API, headers]);

  const create = async () => {
    try {
      const res = await axios.post(`${API}/crm/site-surveys`, { company_id: companyId, ...createForm }, { headers: headers() });
      toast.success('Survey created');
      setShowCreate(false);
      await load();
      setOpenId(res.data.id);
    } catch (e) { toast.error(e?.response?.data?.detail || 'Create failed'); }
  };

  if (openId) {
    return <SurveyEditor surveyId={openId} schema={meta.sections} statuses={meta.statuses} readinessStatuses={meta.readiness_statuses}
      attachmentCategories={meta.attachment_categories} API={API} headers={headers} c={c} isDark={isDark}
      onBack={() => { setOpenId(null); load(); }} />;
  }

  return (
    <div data-testid="pre-install-surveys">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div>
          <h3 className="text-sm font-bold" style={{ color: c.text }}>Pre-Install Site Surveys</h3>
          <p className="text-xs" style={{ color: c.textDim }}>Structured pre-installation surveys stored permanently against {companyName}.</p>
        </div>
        <button onClick={() => setShowCreate(true)} className="px-4 py-2 text-xs font-semibold rounded-md bg-[var(--color-info-ios)] text-white inline-flex items-center gap-1" data-testid="create-survey-btn">
          <Plus size={14} /> Create Pre-Install Site Survey
        </button>
      </div>

      {loading ? <div className="py-10 text-center"><Loader2 className="animate-spin inline" size={20} /></div>
        : surveys.length === 0 ? (
          <div className="py-10 text-center" data-testid="surveys-empty">
            <ClipboardList size={28} className="mx-auto mb-2" style={{ color: c.textDim }} />
            <p className="text-sm" style={{ color: c.textDim }}>No surveys yet. Create a Pre-Install Site Survey before installation.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {surveys.map((s) => (
              <button key={s.id} onClick={() => setOpenId(s.id)} className="w-full text-left p-3 rounded-lg border flex items-center gap-3 transition-all hover:border-[var(--color-info-ios)]"
                style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: c.border }} data-testid={`survey-row-${s.id}`}>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold truncate" style={{ color: c.text }}>{s.reference} · {(meta.survey_types.find((t) => t.key === s.survey_type) || {}).label || s.survey_type}</p>
                  <p className="text-xs" style={{ color: c.textDim }}>{s.site_name || 'No site'} · {s.completed_by_name || '—'} · v{s.version}</p>
                </div>
                <span className="text-[10px] font-bold uppercase px-2 py-1 rounded shrink-0" style={{ background: `${readinessColor(s.readiness_status)}20`, color: readinessColor(s.readiness_status) }}>
                  {(meta.readiness_statuses.find((r) => r.key === s.readiness_status) || {}).label || s.readiness_status}
                </span>
                <span className="text-[10px] font-bold uppercase px-2 py-1 rounded shrink-0" style={{ background: `${statusColor(s.status)}20`, color: statusColor(s.status) }}>
                  {(meta.statuses.find((t) => t.key === s.status) || {}).label || s.status}
                </span>
              </button>
            ))}
          </div>
        )}

      {showCreate && (
        <div className="fixed inset-0 z-[1000] flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.5)' }} onClick={() => setShowCreate(false)}>
          <div className="w-full max-w-md rounded-xl border p-5" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: c.border }} onClick={(e) => e.stopPropagation()} data-testid="create-survey-modal">
            <div className="flex items-center justify-between mb-4"><h3 className="text-sm font-bold" style={{ color: c.text }}>Create Pre-Install Site Survey</h3><button onClick={() => setShowCreate(false)}><X size={16} style={{ color: c.textMuted }} /></button></div>
            {!siteId && (
              <div className="mb-3">
                <label className="block text-[11px] font-semibold mb-1" style={{ color: c.textMuted }}>Site</label>
                <select value={createForm.site_id} onChange={(e) => setCreateForm((f) => ({ ...f, site_id: e.target.value }))} className="w-full px-3 py-2 text-sm rounded-md border" style={{ background: isDark ? 'var(--color-surface-dark-2)' : '#fff', borderColor: c.border, color: c.text }} data-testid="create-survey-site">
                  <option value="">— Select site —</option>
                  {sites.map((st) => <option key={st.id} value={st.id}>{st.name}</option>)}
                </select>
              </div>
            )}
            <div className="mb-3">
              <label className="block text-[11px] font-semibold mb-1" style={{ color: c.textMuted }}>Survey type</label>
              <select value={createForm.survey_type} onChange={(e) => setCreateForm((f) => ({ ...f, survey_type: e.target.value }))} className="w-full px-3 py-2 text-sm rounded-md border" style={{ background: isDark ? 'var(--color-surface-dark-2)' : '#fff', borderColor: c.border, color: c.text }} data-testid="create-survey-type">
                {(meta?.survey_types || []).map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
              </select>
            </div>
            <div className="grid grid-cols-2 gap-3 mb-4">
              <div>
                <label className="block text-[11px] font-semibold mb-1" style={{ color: c.textMuted }}>Priority</label>
                <select value={createForm.priority} onChange={(e) => setCreateForm((f) => ({ ...f, priority: e.target.value }))} className="w-full px-3 py-2 text-sm rounded-md border" style={{ background: isDark ? 'var(--color-surface-dark-2)' : '#fff', borderColor: c.border, color: c.text }}>
                  {['low', 'normal', 'high', 'urgent'].map((p) => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-[11px] font-semibold mb-1" style={{ color: c.textMuted }}>Target install date</label>
                <input type="date" value={createForm.target_install_date} onChange={(e) => setCreateForm((f) => ({ ...f, target_install_date: e.target.value }))} className="w-full px-3 py-2 text-sm rounded-md border" style={{ background: isDark ? 'var(--color-surface-dark-2)' : '#fff', borderColor: c.border, color: c.text }} />
              </div>
            </div>
            <button onClick={create} className="w-full py-2 text-sm font-semibold rounded-md bg-[var(--color-info-ios)] text-white" data-testid="create-survey-confirm">Create survey</button>
          </div>
        </div>
      )}
    </div>
  );
}
