/**
 * Pulse Fitness AI — audience segment builder (Phase 2).
 * Saved + dynamic segments across contacts and members, using the shared
 * rule engine. Live preview count as you build.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Plus, Trash2, X, Users, Filter, RefreshCw, Pencil, Wand2, Loader2 } from 'lucide-react';

const apiRoot = (API) => (API || process.env.REACT_APP_BACKEND_URL || '').replace(/\/api\/?$/, '');
const card = { background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' };
const muted = { color: 'var(--theme-text-muted)' };
const txt = { color: 'var(--theme-text)' };
const inputCls = 'px-2.5 py-2 rounded-lg border text-sm focus:outline-none';
const inputStyle = { background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' };

export function SegmentsView({ API, headers }) {
  const root = apiRoot(API);
  const [meta, setMeta] = useState(null);
  const [segments, setSegments] = useState(null);
  const [editing, setEditing] = useState(null);
  const [showAI, setShowAI] = useState(false);
  const [aiDesc, setAiDesc] = useState('');
  const [aiBusy, setAiBusy] = useState(false);

  const aiSuggest = async () => {
    if (!aiDesc.trim()) { toast.error('Describe the audience'); return; }
    setAiBusy(true);
    try {
      const r = await axios.post(`${root}/api/comms/segments/ai-suggest`, { description: aiDesc }, { headers });
      setShowAI(false); setAiDesc('');
      setEditing({ name: r.data.name, source: r.data.source, type: 'dynamic', rules: r.data.rules });
      toast.success(`Suggested segment (~${r.data.count} matches) — review & save`);
    } catch (e) { toast.error(e?.response?.data?.detail || 'AI is unavailable right now'); }
    finally { setAiBusy(false); }
  };

  const load = useCallback(async () => {
    try { const r = await axios.get(`${root}/api/comms/segments`, { headers }); setSegments(r.data.segments); }
    catch { toast.error('Failed to load segments'); }
  }, [root, headers]);

  useEffect(() => { axios.get(`${root}/api/comms/segments/fields`, { headers }).then((r) => setMeta(r.data)).catch(() => {}); }, [root, headers]);
  useEffect(() => { load(); }, [load]);

  const del = async (s) => {
    try { await axios.delete(`${root}/api/comms/segments/${s.id}`, { headers }); toast.success('Segment deleted'); load(); }
    catch { toast.error('Delete failed'); }
  };

  return (
    <div data-testid="segments-view">
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm" style={muted}>Saved &amp; dynamic audiences — reusable across every campaign.</p>
        <div className="flex gap-2">
          <button onClick={() => setShowAI(true)} className="flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-bold text-white" style={{ backgroundImage: 'linear-gradient(135deg,#7C3AED,#19CDFF)' }} data-testid="segment-ai-btn"><Wand2 size={15} />AI suggest</button>
          <button onClick={() => setEditing({})} className="flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-bold" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid="segment-create-btn"><Plus size={15} />New segment</button>
        </div>
      </div>

      {showAI && (
        <div className="fixed inset-0 z-[160] bg-black/50 flex items-center justify-center p-4" onClick={() => setShowAI(false)}>
          <div className="rounded-2xl p-6 w-full max-w-md border" style={card} onClick={(e) => e.stopPropagation()} data-testid="segment-ai-modal">
            <h3 className="flex items-center gap-2 font-bold text-lg pulse-font-heading mb-1" style={txt}><Wand2 size={18} className="text-violet-500" />AI segment builder</h3>
            <p className="text-sm mb-4" style={muted}>Describe the audience in plain English — we'll build the rules for you to review.</p>
            <textarea value={aiDesc} onChange={(e) => setAiDesc(e.target.value)} rows={3} placeholder="e.g. lapsed members who haven't visited in 90 days" className={`w-full ${inputCls} mb-4`} style={inputStyle} data-testid="segment-ai-desc" />
            <div className="flex justify-end gap-2">
              <button onClick={() => setShowAI(false)} className="px-4 py-2 rounded-full text-sm font-semibold hover:bg-black/5" style={muted}>Cancel</button>
              <button onClick={aiSuggest} disabled={aiBusy} className="flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-bold text-white disabled:opacity-50" style={{ backgroundImage: 'linear-gradient(135deg,#7C3AED,#19CDFF)' }} data-testid="segment-ai-go">{aiBusy ? <Loader2 size={14} className="animate-spin" /> : <Wand2 size={14} />}Build it</button>
            </div>
          </div>
        </div>
      )}

      {!segments ? <p className="text-sm" style={muted}>Loading…</p>
        : segments.length === 0 ? (
          <div className="rounded-2xl border p-12 text-center" style={card}>
            <Filter size={28} className="mx-auto mb-2" style={muted} />
            <p className="font-semibold" style={txt}>No segments yet</p>
            <p className="text-sm mb-4" style={muted}>Build a targeted audience once and reuse it everywhere.</p>
            <button onClick={() => setEditing({})} className="px-4 py-2 rounded-full text-sm font-bold" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid="segment-empty-create">Create segment</button>
          </div>
        ) : (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3" data-testid="segment-list">
            {segments.map((s) => (
              <div key={s.id} className="rounded-2xl border p-4" style={card} data-testid={`segment-card-${s.id}`}>
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="font-bold truncate" style={txt}>{s.name}</p>
                    <p className="text-xs" style={muted}>{s.source === 'members' ? 'Members' : 'Contacts'} · {s.type}</p>
                  </div>
                  <div className="flex gap-1 shrink-0">
                    <button onClick={() => setEditing(s)} className="p-1 rounded hover:bg-black/5" style={muted} data-testid={`segment-edit-${s.id}`}><Pencil size={14} /></button>
                    <button onClick={() => del(s)} className="p-1 rounded hover:bg-black/5 text-rose-500" data-testid={`segment-del-${s.id}`}><Trash2 size={14} /></button>
                  </div>
                </div>
                <div className="flex items-center gap-1.5 mt-3"><Users size={16} style={{ color: 'var(--color-brand-cyan)' }} /><span className="text-2xl font-extrabold pulse-font-heading" style={txt}>{s.member_count}</span><span className="text-xs" style={muted}>members</span></div>
              </div>
            ))}
          </div>
        )}

      {editing && meta && (
        <SegmentEditor root={root} headers={headers} meta={meta} segment={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />
      )}
    </div>
  );
}

function SegmentEditor({ root, headers, meta, segment, onClose, onSaved }) {
  const isEdit = !!segment.id;
  const [name, setName] = useState(segment.name || '');
  const [source, setSource] = useState(segment.source || 'contacts');
  const [type, setType] = useState(segment.type || 'dynamic');
  const [matchOp, setMatchOp] = useState(segment.rules?.op || 'and');
  const [conditions, setConditions] = useState(segment.rules?.conditions?.length ? segment.rules.conditions : [{ field: meta.fields[segment.source || 'contacts'][0].field, op: '==', value: '' }]);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);

  const fields = meta.fields[source] || [];
  const fieldDef = (f) => fields.find((x) => x.field === f) || fields[0];

  const rules = useMemo(() => ({
    op: matchOp,
    conditions: conditions
      .filter((c) => c.field && c.value !== '')
      .map((c) => ({ field: c.field, op: c.op, value: c.op === 'in' ? String(c.value).split(',').map((x) => x.trim()).filter(Boolean) : c.value })),
  }), [matchOp, conditions]);

  useEffect(() => {
    const t = setTimeout(async () => {
      try { const r = await axios.post(`${root}/api/comms/segments/preview`, { source, rules }, { headers }); setPreview(r.data); }
      catch { setPreview(null); }
    }, 400);
    return () => clearTimeout(t);
  }, [root, headers, source, rules]);

  const setCond = (i, patch) => setConditions((prev) => prev.map((c, idx) => (idx === i ? { ...c, ...patch } : c)));
  const addCond = () => setConditions((prev) => [...prev, { field: fields[0].field, op: '==', value: '' }]);
  const rmCond = (i) => setConditions((prev) => prev.filter((_, idx) => idx !== i));

  const save = async () => {
    if (!name.trim()) { toast.error('Name your segment'); return; }
    setBusy(true);
    try {
      const payload = { name, source, type, rules };
      if (isEdit) await axios.put(`${root}/api/comms/segments/${segment.id}`, payload, { headers });
      else await axios.post(`${root}/api/comms/segments`, payload, { headers });
      toast.success('Segment saved');
      onSaved();
    } catch (e) { toast.error(e?.response?.data?.detail || 'Save failed'); }
    finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-[160] bg-black/50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto border" style={card} onClick={(e) => e.stopPropagation()} data-testid="segment-editor">
        <div className="flex items-center justify-between px-6 py-4 border-b sticky top-0" style={{ ...card, borderColor: 'var(--theme-border)' }}>
          <h3 className="font-bold text-lg pulse-font-heading" style={txt}>{isEdit ? 'Edit segment' : 'New segment'}</h3>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-black/5" style={muted}><X size={18} /></button>
        </div>
        <div className="p-6">
          <div className="grid sm:grid-cols-2 gap-3 mb-4">
            <div>
              <label className="block text-[11px] uppercase tracking-wider font-bold mb-1" style={muted}>Name</label>
              <input value={name} onChange={(e) => setName(e.target.value)} className={`w-full ${inputCls}`} style={inputStyle} placeholder="e.g. Lapsed premium members" data-testid="segment-name" />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-[11px] uppercase tracking-wider font-bold mb-1" style={muted}>Audience</label>
                <select value={source} onChange={(e) => { const s = e.target.value; setSource(s); setConditions([{ field: meta.fields[s][0].field, op: '==', value: '' }]); }} className={`w-full ${inputCls}`} style={inputStyle} data-testid="segment-source">
                  {meta.sources.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-[11px] uppercase tracking-wider font-bold mb-1" style={muted}>Type</label>
                <select value={type} onChange={(e) => setType(e.target.value)} className={`w-full ${inputCls}`} style={inputStyle} data-testid="segment-type">
                  <option value="dynamic">Dynamic</option>
                  <option value="saved">Saved (snapshot)</option>
                </select>
              </div>
            </div>
          </div>

          <div className="rounded-xl border p-4 mb-4" style={{ ...card, background: 'var(--theme-bg)' }}>
            <div className="flex items-center gap-2 mb-3 text-sm" style={txt}>
              Match
              <select value={matchOp} onChange={(e) => setMatchOp(e.target.value)} className={inputCls} style={inputStyle} data-testid="segment-match">
                <option value="and">all</option>
                <option value="or">any</option>
              </select>
              of these conditions
            </div>
            <div className="space-y-2">
              {conditions.map((c, i) => {
                const def = fieldDef(c.field);
                return (
                  <div key={i} className="flex flex-wrap items-center gap-2" data-testid={`segment-condition-${i}`}>
                    <select value={c.field} onChange={(e) => setCond(i, { field: e.target.value, value: '' })} className={inputCls} style={inputStyle} data-testid={`condition-field-${i}`}>
                      {fields.map((f) => <option key={f.field} value={f.field}>{f.label}</option>)}
                    </select>
                    <select value={c.op} onChange={(e) => setCond(i, { op: e.target.value })} className={inputCls} style={inputStyle} data-testid={`condition-op-${i}`}>
                      {meta.operators.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
                    </select>
                    {def?.kind === 'select' ? (
                      <select value={c.value} onChange={(e) => setCond(i, { value: e.target.value })} className={`flex-1 min-w-[120px] ${inputCls}`} style={inputStyle} data-testid={`condition-value-${i}`}>
                        <option value="">Choose…</option>
                        {def.options.map((o) => <option key={o} value={o}>{o}</option>)}
                      </select>
                    ) : def?.kind === 'date' ? (
                      <select value={c.value} onChange={(e) => setCond(i, { value: e.target.value })} className={`flex-1 min-w-[120px] ${inputCls}`} style={inputStyle} data-testid={`condition-value-${i}`}>
                        <option value="">Choose…</option>
                        {meta.date_sentinels.map((d) => <option key={d} value={d}>{d.replace('d_ago', ' days ago')}</option>)}
                      </select>
                    ) : (
                      <input value={c.value} onChange={(e) => setCond(i, { value: e.target.value })} type={def?.kind === 'number' ? 'number' : 'text'} placeholder={def?.kind === 'tag' ? 'tag value' : 'value'} className={`flex-1 min-w-[120px] ${inputCls}`} style={inputStyle} data-testid={`condition-value-${i}`} />
                    )}
                    <button onClick={() => rmCond(i)} className="p-1.5 rounded hover:bg-black/5 text-rose-500" data-testid={`condition-remove-${i}`}><Trash2 size={14} /></button>
                  </div>
                );
              })}
            </div>
            <button onClick={addCond} className="mt-3 text-xs font-bold" style={{ color: 'var(--color-brand-cyan)' }} data-testid="segment-add-condition">+ Add condition</button>
          </div>

          <div className="flex items-center justify-between rounded-xl border p-4" style={card}>
            <div className="flex items-center gap-2">
              <Users size={18} style={{ color: 'var(--color-brand-cyan)' }} />
              <span className="text-2xl font-extrabold pulse-font-heading" style={txt} data-testid="segment-preview-count">{preview ? preview.count : '…'}</span>
              <span className="text-sm" style={muted}>matching {source === 'members' ? 'members' : 'contacts'}</span>
            </div>
            <RefreshCw size={14} style={muted} />
          </div>

          <div className="flex justify-end gap-2 mt-5">
            <button onClick={onClose} className="px-4 py-2 rounded-full text-sm font-semibold hover:bg-black/5" style={muted}>Cancel</button>
            <button onClick={save} disabled={busy} className="px-5 py-2 rounded-full text-sm font-bold disabled:opacity-50" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid="segment-save">{busy ? 'Saving…' : 'Save segment'}</button>
          </div>
        </div>
      </div>
    </div>
  );
}
