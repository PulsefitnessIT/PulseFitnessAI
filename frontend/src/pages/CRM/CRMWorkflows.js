import React, { useState, useEffect, useCallback } from 'react';
import { useCRM } from './CRMApp';
import {
  Zap, Plus, Play, Pause, Trash2, ArrowRight, CheckCircle, X, Clock,
  AlertTriangle, ChevronRight, Activity, BarChart3, Copy, Eye
} from 'lucide-react';
import axios from 'axios';

const CONDITION_OPS = [
  { id: 'equals', label: 'equals' },
  { id: 'not_equals', label: 'does not equal' },
  { id: 'contains', label: 'contains' },
  { id: 'greater_than', label: 'greater than' },
];

export default function CRMWorkflows() {
  const { API, headers, c, isDark } = useCRM();
  const [workflows, setWorkflows] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [meta, setMeta] = useState({ triggers: [], actions: [], templates: [] });
  // Iter 216h195 — load the org's real pipeline stages + existing tag
  // vocabulary so the workflow builder offers a dropdown instead of
  // free text. Falls back to the legacy free-text input if either
  // endpoint fails (worst case = unchanged behaviour).
  const [stages, setStages] = useState([]);
  const [tags, setTags] = useState([]);
  const [showBuilder, setShowBuilder] = useState(false);
  const [showDetail, setShowDetail] = useState(null);
  const [showTemplates, setShowTemplates] = useState(false);
  const [form, setForm] = useState({
    name: '', description: '',
    trigger: { type: 'deal_stage_changed' },
    conditions: [],
    actions: [{ type: 'create_task', config: { description: '', priority: 'normal', due_days: 1 } }],
  });
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const [wfRes, metaRes, stagesRes, tagsRes] = await Promise.all([
        axios.get(`${API}/crm/v2/workflows`, { headers: headers() }),
        axios.get(`${API}/crm/v2/workflows/meta`, { headers: headers() }),
        axios.get(`${API}/crm/v2/opportunities/stages`, { headers: headers() }).catch(() => ({ data: { stages: [] } })),
        axios.get(`${API}/crm/v2/tags`, { headers: headers() }).catch(() => ({ data: { tags: [] } })),
      ]);
      setWorkflows(wfRes.data.workflows);
      setTotal(wfRes.data.total);
      setMeta(metaRes.data);
      setStages(stagesRes.data?.stages || stagesRes.data || []);
      setTags(tagsRes.data?.tags || tagsRes.data || []);
    } catch (e) { console.error(e); }
    setLoading(false);
  }, [API, headers]);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    if (!form.name.trim()) return;
    setSaving(true);
    try {
      await axios.post(`${API}/crm/v2/workflows`, form, { headers: headers() });
      setShowBuilder(false);
      resetForm();
      load();
    } catch (e) { console.error(e); }
    setSaving(false);
  };

  const handleCreateFromTemplate = async (tplId) => {
    try {
      await axios.post(`${API}/crm/v2/workflows/from-template`, { template_id: tplId }, { headers: headers() });
      setShowTemplates(false);
      load();
    } catch (e) { console.error(e); }
  };

  const toggleWorkflow = async (id) => {
    try {
      await axios.post(`${API}/crm/v2/workflows/${id}/toggle`, {}, { headers: headers() });
      load();
    } catch (e) { console.error(e); }
  };

  const deleteWorkflow = async (id) => {
    try {
      await axios.delete(`${API}/crm/v2/workflows/${id}`, { headers: headers() });
      if (showDetail?.id === id) setShowDetail(null);
      load();
    } catch (e) { console.error(e); }
  };

  const loadDetail = async (id) => {
    try {
      const res = await axios.get(`${API}/crm/v2/workflows/${id}`, { headers: headers() });
      setShowDetail(res.data);
    } catch (e) { console.error(e); }
  };

  const resetForm = () => {
    setForm({
      name: '', description: '',
      trigger: { type: 'deal_stage_changed' },
      conditions: [],
      actions: [{ type: 'create_task', config: { description: '', priority: 'normal', due_days: 1 } }],
    });
  };

  const addAction = () => {
    setForm({ ...form, actions: [...form.actions, { type: 'create_task', config: { description: '', priority: 'normal', due_days: 1 } }] });
  };
  const removeAction = (i) => { setForm({ ...form, actions: form.actions.filter((_, idx) => idx !== i) }); };
  const updateAction = (i, field, value) => {
    const updated = [...form.actions];
    if (field === 'type') updated[i] = { type: value, config: {} };
    else updated[i] = { ...updated[i], config: { ...updated[i].config, [field]: value } };
    setForm({ ...form, actions: updated });
  };

  const addCondition = () => {
    setForm({ ...form, conditions: [...form.conditions, { field: 'stage', operator: 'equals', value: '' }] });
  };
  const removeCondition = (i) => { setForm({ ...form, conditions: form.conditions.filter((_, idx) => idx !== i) }); };
  const updateCondition = (i, field, value) => {
    const updated = [...form.conditions];
    updated[i] = { ...updated[i], [field]: value };
    setForm({ ...form, conditions: updated });
  };

  const triggerLabel = (type) => meta.triggers.find(t => t.id === type)?.label || type;
  const actionLabel = (type) => meta.actions.find(a => a.id === type)?.label || type;

  if (loading) return <div className="flex items-center justify-center h-64"><div className="w-5 h-5 border-2 border-[var(--color-info-ios)] border-t-transparent rounded-full animate-spin" /></div>;

  // Workflow detail view
  if (showDetail) {
    const wf = showDetail;
    return (
      <div data-testid="crm-workflow-detail">
        <button onClick={() => setShowDetail(null)} className="flex items-center gap-1.5 text-sm mb-4 hover:underline" style={{ color: c.textMuted }}>
          <ChevronRight size={14} className="rotate-180" /> Back to Workflows
        </button>
        <div className="flex items-center gap-3 mb-5">
          <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ background: wf.active ? 'var(--color-success-alt)15' : 'var(--color-text-faint-alt)15' }}>
            <Zap size={20} style={{ color: wf.active ? 'var(--color-success-alt)' : 'var(--color-text-faint-alt)' }} />
          </div>
          <div className="flex-1">
            <h1 className="text-xl font-bold" style={{ color: c.text }}>{wf.name}</h1>
            <p className="text-xs mt-0.5" style={{ color: c.textDim }}>{wf.description || 'No description'}</p>
          </div>
          <div className="flex gap-2">
            <button onClick={() => toggleWorkflow(wf.id)} className="px-3 py-1.5 text-xs font-medium rounded-md border"
              style={{ borderColor: wf.active ? 'var(--color-success-alt)30' : (isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)'), color: wf.active ? 'var(--color-success-alt)' : c.textDim }}>
              {wf.active ? <><Pause size={10} className="inline mr-1" /> Pause</> : <><Play size={10} className="inline mr-1" /> Activate</>}
            </button>
            <button onClick={() => deleteWorkflow(wf.id)} className="px-3 py-1.5 text-xs rounded-md" style={{ color: 'var(--color-danger-alt)' }}>
              <Trash2 size={12} className="inline mr-1" /> Delete
            </button>
          </div>
        </div>

        {/* Workflow config */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-5">
          <div className="rounded-lg border p-4" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: 'var(--color-info-ios)30' }}>
            <div className="flex items-center gap-2 mb-3">
              <Zap size={14} style={{ color: 'var(--color-info-ios)' }} />
              <span className="text-xs uppercase tracking-wider font-medium" style={{ color: 'var(--color-info-ios)' }}>Trigger</span>
            </div>
            <p className="text-sm font-medium" style={{ color: c.text }}>{triggerLabel(wf.trigger?.type)}</p>
            {wf.conditions?.length > 0 && (
              <div className="mt-2 space-y-1">
                {wf.conditions.map((cond, i) => (
                  <p key={i} className="text-xs" style={{ color: c.textDim }}>
                    If <span style={{ color: c.text }}>{cond.field}</span> {cond.operator} <span style={{ color: 'var(--color-info-ios)' }}>{cond.value}</span>
                  </p>
                ))}
              </div>
            )}
          </div>
          <div className="rounded-lg border p-4" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: 'var(--color-success-alt)30' }}>
            <div className="flex items-center gap-2 mb-3">
              <ArrowRight size={14} style={{ color: 'var(--color-success-alt)' }} />
              <span className="text-xs uppercase tracking-wider font-medium" style={{ color: 'var(--color-success-alt)' }}>Actions ({wf.actions?.length || 0})</span>
            </div>
            {(wf.actions || []).map((a, i) => (
              <div key={i} className="flex items-center gap-2 py-1">
                <span className="text-[10px] w-4" style={{ color: c.textDim }}>{i + 1}.</span>
                <span className="text-sm" style={{ color: c.text }}>{actionLabel(a.type)}</span>
                {a.config?.description && <span className="text-xs" style={{ color: c.textDim }}>— {a.config.description}</span>}
                {a.config?.message && <span className="text-xs" style={{ color: c.textDim }}>— {a.config.message.substring(0, 40)}</span>}
              </div>
            ))}
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-3 gap-3 mb-5">
          {[
            { l: 'Executions', v: wf.execution_count || 0, col: 'var(--color-info-ios)' },
            { l: 'Status', v: wf.active ? 'Active' : 'Paused', col: wf.active ? 'var(--color-success-alt)' : 'var(--color-text-faint-alt)' },
            { l: 'Last Run', v: wf.last_run_at ? new Date(wf.last_run_at).toLocaleDateString('en-GB') : 'Never', col: c.textMuted },
          ].map(s => (
            <div key={s.l} className="p-3 rounded-lg border" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
              <p className="text-[10px] uppercase tracking-wider" style={{ color: c.textDim }}>{s.l}</p>
              <p className="text-lg font-bold" style={{ color: s.col }}>{s.v}</p>
            </div>
          ))}
        </div>

        {/* Execution History */}
        <div className="rounded-lg border p-4" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
          <h3 className="text-sm font-semibold mb-3" style={{ color: c.text }}>Execution History</h3>
          {(wf.runs || []).length > 0 ? (
            <div className="space-y-2">
              {wf.runs.map(run => (
                <div key={run.id} className="flex items-center gap-3 p-3 rounded-md border" style={{ borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
                  <CheckCircle size={14} style={{ color: run.status === 'success' ? 'var(--color-success-alt)' : 'var(--color-danger-alt)' }} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm" style={{ color: c.text }}>
                      {run.trigger_type?.replace(/_/g, ' ')} — <span style={{ color: 'var(--color-info-ios)' }}>{run.entity_name}</span>
                    </p>
                    <p className="text-[10px] mt-0.5" style={{ color: c.textDim }}>
                      {run.actions_executed?.length || 0} actions executed &middot; {new Date(run.created_at).toLocaleString('en-GB')}
                    </p>
                  </div>
                  <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded" style={{ background: run.status === 'success' ? 'var(--color-success-alt)20' : 'var(--color-danger-alt)20', color: run.status === 'success' ? 'var(--color-success-alt)' : 'var(--color-danger-alt)' }}>
                    {run.status}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-center py-6" style={{ color: c.textDim }}>No executions yet. This workflow will run when its trigger fires.</p>
          )}
        </div>
      </div>
    );
  }

  return (
    <div data-testid="crm-workflows">
      {/* Toolbar — counts + actions */}
      <div className="flex items-center justify-end gap-3 mb-3 flex-wrap">
        <p className="text-xs mr-auto" style={{ color: c.textDim }}>
          {total} workflow{total !== 1 ? 's' : ''} &middot; {workflows.filter(w => w.active).length} active &middot; {workflows.reduce((s, w) => s + (w.execution_count || 0), 0)} total runs
        </p>
        <div className="flex gap-2">
          <button type="button" onClick={() => setShowTemplates(true)} className="btn-secondary" data-testid="workflow-templates-btn">
            <Copy size={14} /> Templates
          </button>
          <button type="button" onClick={() => { resetForm(); setShowBuilder(true); }} className="btn-primary" data-testid="create-workflow-btn">
            <Plus size={14} /> New Workflow
          </button>
        </div>
      </div>

      {/* Workflow list */}
      {workflows.length === 0 ? (
        <div className="text-center py-16 rounded-lg border" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
          <Zap size={40} className="mx-auto mb-3" style={{ color: c.textDim }} />
          <p className="text-sm font-medium" style={{ color: c.textMuted }}>No workflows yet</p>
          <p className="text-xs mt-1" style={{ color: c.textDim }}>Automate repetitive tasks with trigger-action workflows</p>
          <div className="flex gap-2 justify-center mt-4">
            <button onClick={() => setShowTemplates(true)} className="text-sm text-[var(--color-info-ios)] hover:underline">Start from a template</button>
            <span style={{ color: c.textDim }}>or</span>
            <button onClick={() => { resetForm(); setShowBuilder(true); }} className="text-sm text-[var(--color-info-ios)] hover:underline">Build from scratch</button>
          </div>
        </div>
      ) : (
        <div className="space-y-2">
          {workflows.map(wf => (
            <div key={wf.id} onClick={() => loadDetail(wf.id)}
              className="flex items-center gap-4 p-4 rounded-lg border cursor-pointer transition-all hover:scale-[1.003]"
              style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}
              data-testid={`workflow-card-${wf.id}`}>
              <div className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0"
                style={{ background: wf.active ? 'var(--color-success-alt)15' : 'var(--color-text-faint-alt)15' }}>
                <Zap size={18} style={{ color: wf.active ? 'var(--color-success-alt)' : 'var(--color-text-faint-alt)' }} />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold" style={{ color: c.text }}>{wf.name}</p>
                {wf.description && <p className="text-[11px] mt-0.5 truncate" style={{ color: c.textDim }}>{wf.description}</p>}
                <div className="flex items-center gap-3 mt-1 text-[10px]" style={{ color: c.textDim }}>
                  <span className="flex items-center gap-1"><Zap size={10} /> {triggerLabel(wf.trigger?.type)}</span>
                  <ArrowRight size={10} />
                  <span>{wf.actions?.length || 0} action{(wf.actions?.length || 0) !== 1 ? 's' : ''}</span>
                  {wf.execution_count > 0 && <span className="flex items-center gap-1"><BarChart3 size={10} /> {wf.execution_count} runs</span>}
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0" onClick={e => e.stopPropagation()}>
                <button onClick={() => toggleWorkflow(wf.id)} className="px-3 py-1.5 text-xs font-medium rounded-md border"
                  style={{ borderColor: wf.active ? 'var(--color-success-alt)30' : (isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)'), color: wf.active ? 'var(--color-success-alt)' : c.textDim, background: wf.active ? 'var(--color-success-alt)10' : 'transparent' }}
                  data-testid={`workflow-toggle-${wf.id}`}>
                  {wf.active ? <><Pause size={10} className="inline mr-1" /> Active</> : <><Play size={10} className="inline mr-1" /> Paused</>}
                </button>
                <button onClick={() => deleteWorkflow(wf.id)} className="p-1.5 rounded-md" style={{ color: c.textDim }} data-testid={`workflow-delete-${wf.id}`}>
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Templates Dialog */}
      {showTemplates && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setShowTemplates(false)}>
          <div className="w-full max-w-2xl mx-4 rounded-xl p-6 shadow-2xl max-h-[80vh] overflow-y-auto"
            style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', border: `1px solid ${c.border}` }} onClick={e => e.stopPropagation()} data-testid="workflow-templates-dialog">
            <h2 className="text-lg font-semibold mb-4" style={{ color: c.text }}>Workflow Templates</h2>
            <p className="text-xs mb-5" style={{ color: c.textDim }}>Pre-built automations ready to activate</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {meta.templates.map(tpl => (
                <div key={tpl.id} className="p-4 rounded-lg border" style={{ background: isDark ? 'var(--color-neutral-950)' : 'var(--color-neutral-50)', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
                  <div className="flex items-center gap-2 mb-2">
                    <Zap size={14} style={{ color: 'var(--color-info-ios)' }} />
                    <h3 className="text-sm font-semibold" style={{ color: c.text }}>{tpl.name}</h3>
                  </div>
                  <p className="text-xs mb-3" style={{ color: c.textDim }}>{tpl.description}</p>
                  <p className="text-[10px] mb-2" style={{ color: c.textDim }}>
                    {tpl.actions.length} action{tpl.actions.length !== 1 ? 's' : ''} &middot; {tpl.conditions.length} condition{tpl.conditions.length !== 1 ? 's' : ''}
                  </p>
                  <button onClick={() => handleCreateFromTemplate(tpl.id)}
                    className="w-full px-3 py-1.5 bg-[var(--color-info-ios)] text-white text-xs font-medium rounded-md hover:bg-[var(--color-brand-blue-deep)]">
                    Use Template
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Workflow Builder Dialog */}
      {showBuilder && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setShowBuilder(false)}>
          <div className="w-full max-w-2xl mx-4 rounded-xl p-6 shadow-2xl max-h-[90vh] overflow-y-auto"
            style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', border: `1px solid ${c.border}` }} onClick={e => e.stopPropagation()} data-testid="workflow-builder-dialog">
            <div className="sticky top-0 z-10 -mx-6 -mt-6 px-6 pt-6 pb-3 mb-4 flex items-center justify-between border-b" style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', borderColor: c.border }}>
              <h2 className="text-lg font-semibold" style={{ color: c.text }}>Build Workflow</h2>
              <button onClick={() => setShowBuilder(false)} className="p-1 hover:opacity-70" style={{ color: c.textDim }} data-testid="workflow-builder-close"><X size={16} /></button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Name *</label>
                <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="e.g. Lead Nurture Sequence"
                  className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Description</label>
                <input value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} placeholder="What does this workflow do?"
                  className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
              </div>

              {/* Trigger */}
              <div className="p-4 rounded-lg" style={{ background: isDark ? 'var(--color-info-ios)08' : 'var(--color-info-bg)', border: '1px solid rgba(0,122,255,0.15)' }}>
                <div className="flex items-center gap-2 mb-3">
                  <Zap size={14} style={{ color: 'var(--color-info-ios)' }} />
                  <span className="text-xs uppercase tracking-wider font-medium" style={{ color: 'var(--color-info-ios)' }}>When...</span>
                </div>
                <select value={form.trigger.type} onChange={e => setForm({ ...form, trigger: { type: e.target.value } })}
                  className="w-full px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }}>
                  {meta.triggers.map(t => <option key={t.id} value={t.id}>{t.label}</option>)}
                </select>
              </div>

              {/* Conditions */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs uppercase tracking-wider font-medium" style={{ color: 'var(--color-warning)' }}>Only if... (conditions)</span>
                  <button onClick={addCondition} className="text-xs text-[var(--color-info-ios)] hover:underline">+ Add condition</button>
                </div>
                {form.conditions.map((cond, i) => (
                  <div key={i} className="flex items-center gap-2 mb-2">
                    <input value={cond.field} onChange={e => updateCondition(i, 'field', e.target.value)} placeholder="Field (e.g. stage)"
                      list="wf-condition-fields"
                      className="flex-1 px-3 py-1.5 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
                    <select value={cond.operator} onChange={e => updateCondition(i, 'operator', e.target.value)}
                      className="px-2 py-1.5 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }}>
                      {CONDITION_OPS.map(op => <option key={op.id} value={op.id}>{op.label}</option>)}
                    </select>
                    <input value={cond.value} onChange={e => updateCondition(i, 'value', e.target.value)} placeholder="Value"
                      list={cond.field === 'stage' ? 'wf-condition-stage-values' : (cond.field === 'tag' ? 'wf-condition-tag-values' : undefined)}
                      className="flex-1 px-3 py-1.5 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
                    <button onClick={() => removeCondition(i)} style={{ color: 'var(--color-danger-alt)' }}><X size={14} /></button>
                  </div>
                ))}
                {/* Iter 216h195 — shared datalists fed by the org's
                    pipeline stages + tag vocabulary. Empty fields keep
                    the inputs working as free text for power users. */}
                <datalist id="wf-condition-fields">
                  {['stage','tag','value','owner','company','source','priority'].map((f) => <option key={f} value={f} />)}
                </datalist>
                <datalist id="wf-condition-stage-values">
                  {stages.map((s) => <option key={s.id || s.name} value={s.name || s.id} />)}
                </datalist>
                <datalist id="wf-condition-tag-values">
                  {tags.map((t) => <option key={t.id || t.name || t} value={t.name || t} />)}
                </datalist>
                {form.conditions.length === 0 && <p className="text-xs" style={{ color: c.textDim }}>No conditions — workflow fires on every trigger</p>}
              </div>

              {/* Actions */}
              <div>
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <ArrowRight size={14} style={{ color: 'var(--color-success-alt)' }} />
                    <span className="text-xs uppercase tracking-wider font-medium" style={{ color: 'var(--color-success-alt)' }}>Then...</span>
                  </div>
                  <button onClick={addAction} className="text-xs text-[var(--color-info-ios)] hover:underline">+ Add action</button>
                </div>
                <div className="space-y-2">
                  {form.actions.map((action, i) => (
                    <div key={i} className="p-3 rounded-lg border" style={{ background: isDark ? 'var(--color-neutral-950)' : 'var(--color-neutral-50)', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
                      <div className="flex items-center gap-2 mb-2">
                        <span className="text-xs w-5" style={{ color: c.textDim }}>{i + 1}.</span>
                        <select value={action.type} onChange={e => updateAction(i, 'type', e.target.value)}
                          className="flex-1 px-3 py-1.5 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }}>
                          {meta.actions.map(a => <option key={a.id} value={a.id}>{a.label}</option>)}
                        </select>
                        {form.actions.length > 1 && <button onClick={() => removeAction(i)} style={{ color: 'var(--color-danger-alt)' }}><X size={14} /></button>}
                      </div>
                      {action.type === 'create_task' && (
                        <div className="grid grid-cols-3 gap-2">
                          <input value={action.config?.description || ''} onChange={e => updateAction(i, 'description', e.target.value)} placeholder="Task description"
                            className="col-span-2 px-3 py-1.5 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
                          <div className="flex gap-1">
                            <select value={action.config?.priority || 'normal'} onChange={e => updateAction(i, 'priority', e.target.value)}
                              className="flex-1 px-2 py-1.5 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }}>
                              <option value="high">High</option>
                              <option value="normal">Normal</option>
                              <option value="low">Low</option>
                            </select>
                          </div>
                        </div>
                      )}
                      {action.type === 'send_notification' && (
                        <input value={action.config?.message || ''} onChange={e => updateAction(i, 'message', e.target.value)} placeholder="Notification message"
                          className="w-full px-3 py-1.5 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
                      )}
                      {action.type === 'create_activity' && (
                        <input value={action.config?.subject || ''} onChange={e => updateAction(i, 'subject', e.target.value)} placeholder="Activity subject"
                          className="w-full px-3 py-1.5 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
                      )}
                      {action.type === 'move_deal_stage' && (
                        <>
                          <input value={action.config?.target_stage || ''} onChange={e => updateAction(i, 'target_stage', e.target.value)} placeholder="Target stage"
                            list={`wf-stages-${i}`}
                            className="w-full px-3 py-1.5 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
                          <datalist id={`wf-stages-${i}`}>
                            {stages.map((s) => <option key={s.id || s.name} value={s.name || s.id} />)}
                          </datalist>
                        </>
                      )}
                      {action.type === 'add_tag' && (
                        <>
                          <input value={action.config?.tag || ''} onChange={e => updateAction(i, 'tag', e.target.value)} placeholder="Tag name"
                            list={`wf-tags-${i}`}
                            className="w-full px-3 py-1.5 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
                          <datalist id={`wf-tags-${i}`}>
                            {tags.map((t) => <option key={t.id || t.name || t} value={t.name || t} />)}
                          </datalist>
                        </>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="flex gap-2 mt-5 justify-end">
              <button onClick={() => setShowBuilder(false)} className="px-4 py-2 text-sm" style={{ color: c.textMuted }}>Cancel</button>
              <button onClick={handleCreate} disabled={saving || !form.name.trim()} className="px-4 py-2 bg-[var(--color-info-ios)] text-white text-sm font-medium rounded-md disabled:opacity-50">
                {saving ? 'Creating...' : 'Create Workflow'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
