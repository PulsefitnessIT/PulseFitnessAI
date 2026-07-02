/**
 * Master Admin → Catalogue & Library → Exploded Drawings.
 *
 * Curated exploded-diagram library keyed by manufacturer + model. Global
 * drawings (uploaded here by a master admin) are offered to every
 * organisation when an operator raises a Parts Request for a matching
 * machine — they open the drawing to locate the part they need.
 *
 * Backed by:
 *   GET    /api/exploded-drawings?manufacturer=&model=&q=
 *   POST   /api/exploded-drawings   (multipart: manufacturer, model, equipment_type, title, is_global, file)
 *   GET    /api/exploded-drawings/{id}/file
 *   DELETE /api/exploded-drawings/{id}
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { notify } from '@/components/notifications';
import { Image as ImageIcon, Trash2, Search, Loader2, Layers, Globe, UploadCloud, ListChecks, Plus, X, Save } from 'lucide-react';

function PartsEditorModal({ drawing, onClose, onSaved }) {
  const [rows, setRows] = useState((drawing.parts || []).map((p) => ({ ...p })));
  const [saving, setSaving] = useState(false);
  const addRow = () => setRows((r) => [...r, { part_number: '', description: '', notes: '' }]);
  const update = (i, k, v) => setRows((r) => r.map((row, j) => j === i ? { ...row, [k]: v } : row));
  const del = (i) => setRows((r) => r.filter((_, j) => j !== i));
  const save = async () => {
    setSaving(true);
    try {
      const r = await api.put(`/exploded-drawings/${drawing.id}/parts`, { parts: rows });
      notify.success('Parts list saved');
      onSaved(r.data?.parts || []);
    } catch (e) { notify.error(e?.response?.data?.detail || 'Failed to save'); }
    finally { setSaving(false); }
  };
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4" onClick={onClose} data-testid="drawing-parts-modal">
      <div className="bg-[var(--theme-surface)] rounded-xl max-w-2xl w-full max-h-[85vh] overflow-auto p-5 border border-[var(--theme-border)]" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-1">
          <h3 className="text-base font-bold text-[var(--theme-text)]">Parts list — {drawing.title}</h3>
          <button onClick={onClose} className="text-[var(--color-text-muted)] hover:text-[var(--theme-text)]" data-testid="drawing-parts-close"><X size={18} /></button>
        </div>
        <p className="text-xs text-[var(--color-text-muted)] mb-3">Operators can add these straight to a Parts Request from the drawing.</p>
        <div className="space-y-2">
          {rows.map((p, i) => (
            <div key={i} className="grid grid-cols-12 gap-2 items-center" data-testid={`drawing-part-edit-${i}`}>
              <input value={p.part_number} onChange={(e) => update(i, 'part_number', e.target.value)} placeholder="Part no." className="col-span-3 px-2 py-1.5 rounded border text-sm bg-[var(--theme-surface-2)] border-[var(--theme-border)] text-[var(--theme-text)]" data-testid={`drawing-part-number-${i}`} />
              <input value={p.description} onChange={(e) => update(i, 'description', e.target.value)} placeholder="Description" className="col-span-5 px-2 py-1.5 rounded border text-sm bg-[var(--theme-surface-2)] border-[var(--theme-border)] text-[var(--theme-text)]" data-testid={`drawing-part-desc-${i}`} />
              <input value={p.notes} onChange={(e) => update(i, 'notes', e.target.value)} placeholder="Notes" className="col-span-3 px-2 py-1.5 rounded border text-sm bg-[var(--theme-surface-2)] border-[var(--theme-border)] text-[var(--theme-text)]" />
              <button onClick={() => del(i)} className="col-span-1 text-[var(--color-text-muted)] hover:text-red-500 flex justify-center"><X size={15} /></button>
            </div>
          ))}
          {rows.length === 0 && <p className="text-sm text-[var(--color-text-muted)] py-2">No parts yet. Add the key spares shown on this diagram.</p>}
        </div>
        <div className="flex items-center justify-between mt-3">
          <button onClick={addRow} className="text-sm font-medium text-[var(--color-brand-blue)] inline-flex items-center gap-1" data-testid="drawing-part-add-row"><Plus size={14} /> Add part</button>
          <button onClick={save} disabled={saving} className="px-4 py-1.5 rounded-md text-sm font-semibold bg-[var(--color-brand-blue)] text-white inline-flex items-center gap-1.5 disabled:opacity-60" data-testid="drawing-parts-save">
            {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />} Save parts list
          </button>
        </div>
      </div>
    </div>
  );
}

export default function ExplodedDrawingsPanel() {
  const [drawings, setDrawings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState('');
  const [busyId, setBusyId] = useState(null);
  const [partsFor, setPartsFor] = useState(null);
  const [form, setForm] = useState({ manufacturer: '', model: '', equipment_type: '', title: '' });
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get('/exploded-drawings');
      setDrawings(r.data?.drawings || []);
    } catch { notify.error('Failed to load exploded drawings'); } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const filtered = useMemo(() => {
    const t = q.trim().toLowerCase();
    if (!t) return drawings;
    return drawings.filter((d) =>
      [d.title, d.manufacturer, d.model, d.equipment_type].some((v) => (v || '').toLowerCase().includes(t)));
  }, [drawings, q]);

  const view = async (d) => {
    try {
      const r = await api.get(`/exploded-drawings/${d.id}/file`, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([r.data], { type: d.content_type || 'image/png' }));
      window.open(url, '_blank');
      setTimeout(() => window.URL.revokeObjectURL(url), 30000);
    } catch { notify.error('Failed to open drawing'); }
  };

  const remove = async (d) => {
    if (!window.confirm(`Delete "${d.title}"?`)) return;
    setBusyId(d.id);
    try {
      await api.delete(`/exploded-drawings/${d.id}`);
      setDrawings((prev) => prev.filter((x) => x.id !== d.id));
      notify.success('Drawing deleted');
    } catch { notify.error('Failed to delete'); } finally { setBusyId(null); }
  };

  const upload = async (file) => {
    if (!file) return;
    if (!form.manufacturer.trim() || !form.model.trim()) { notify.error('Enter a manufacturer and model first'); return; }
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('manufacturer', form.manufacturer.trim());
      fd.append('model', form.model.trim());
      fd.append('equipment_type', form.equipment_type.trim());
      fd.append('title', form.title.trim() || file.name);
      fd.append('is_global', 'true');
      await api.post('/exploded-drawings', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      notify.success('Exploded drawing added');
      setForm({ manufacturer: '', model: '', equipment_type: '', title: '' });
      await load();
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Failed to upload drawing');
    } finally { setUploading(false); }
  };

  return (
    <div className="space-y-4" data-testid="exploded-drawings-panel">
      {/* Upload */}
      <div className="rounded-lg border border-[var(--theme-border)] p-3 bg-[var(--theme-surface)]" data-testid="exploded-drawing-upload">
        <div className="flex items-center gap-1.5 mb-2 text-sm font-semibold text-[var(--theme-text)]">
          <Globe size={14} className="text-[var(--color-brand-blue)]" /> Add an exploded drawing
        </div>
        <p className="text-xs text-[var(--color-text-muted)] mb-2">Drawings are matched to machines by make &amp; model and shown to operators raising a Parts Request. Uploaded here as platform-global (available to every organisation).</p>
        <div className="flex flex-wrap items-center gap-2">
          <input value={form.manufacturer} onChange={(e) => setForm((f) => ({ ...f, manufacturer: e.target.value }))} placeholder="Manufacturer" className="px-2.5 py-1.5 rounded-md border text-sm bg-[var(--theme-surface-2)] border-[var(--theme-border)] text-[var(--theme-text)] w-40" data-testid="drawing-manufacturer" />
          <input value={form.model} onChange={(e) => setForm((f) => ({ ...f, model: e.target.value }))} placeholder="Model" className="px-2.5 py-1.5 rounded-md border text-sm bg-[var(--theme-surface-2)] border-[var(--theme-border)] text-[var(--theme-text)] w-40" data-testid="drawing-model" />
          <input value={form.equipment_type} onChange={(e) => setForm((f) => ({ ...f, equipment_type: e.target.value }))} placeholder="Type (optional)" className="px-2.5 py-1.5 rounded-md border text-sm bg-[var(--theme-surface-2)] border-[var(--theme-border)] text-[var(--theme-text)] w-40" data-testid="drawing-type" />
          <input value={form.title} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} placeholder="Title (optional)" className="px-2.5 py-1.5 rounded-md border text-sm bg-[var(--theme-surface-2)] border-[var(--theme-border)] text-[var(--theme-text)] flex-1 min-w-[160px]" data-testid="drawing-title" />
          <input ref={fileRef} type="file" accept="image/*,.pdf" className="hidden" onChange={(e) => { upload(e.target.files?.[0]); e.target.value = ''; }} data-testid="drawing-file-input" />
          <button onClick={() => fileRef.current?.click()} disabled={uploading} className="px-3 py-1.5 rounded-md text-sm font-medium bg-[var(--color-brand-blue)] text-white inline-flex items-center gap-1.5 disabled:opacity-60" data-testid="drawing-upload-btn">
            {uploading ? <Loader2 size={13} className="animate-spin" /> : <UploadCloud size={13} />} Upload
          </button>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <div className="relative flex-1 max-w-sm">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-400" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search manufacturer, model, type…"
            className="w-full pl-8 pr-3 py-2 rounded-md border text-sm bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)]" data-testid="drawing-search" />
        </div>
        <span className="text-xs text-[var(--color-text-muted)]">{filtered.length} drawing{filtered.length === 1 ? '' : 's'}</span>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12 text-[var(--color-text-muted)]"><Loader2 className="animate-spin" /></div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-12 text-sm text-[var(--color-text-muted)]">
          <Layers className="mx-auto mb-2 opacity-40" size={28} />
          No exploded drawings uploaded yet.
        </div>
      ) : (
        <div className="rounded-lg border border-[var(--theme-border)] overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-[var(--theme-surface-2)] text-left text-xs text-[var(--color-text-muted)]">
                <th className="px-3 py-2 font-semibold">Drawing</th>
                <th className="px-3 py-2 font-semibold">Make / Model</th>
                <th className="px-3 py-2 font-semibold">Type</th>
                <th className="px-3 py-2 font-semibold text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((d) => (
                <tr key={d.id} className="border-t border-[var(--theme-border)]" data-testid={`drawing-row-${d.id}`}>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <ImageIcon size={13} className="text-[var(--color-brand-blue)] shrink-0" />
                      <span className="text-[var(--theme-text)] truncate">{d.title}</span>
                      {d.is_global && (
                        <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full text-[9px] font-semibold bg-[var(--color-brand-blue)]/10 text-[var(--color-brand-blue)] shrink-0" data-testid={`drawing-global-badge-${d.id}`}>
                          <Globe size={9} /> Global
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-2 text-[var(--color-text-muted)]">{d.manufacturer} · {d.model}</td>
                  <td className="px-3 py-2 text-[var(--color-text-muted)]">{d.equipment_type || '—'}</td>
                  <td className="px-3 py-2 text-right whitespace-nowrap">
                    <button onClick={() => setPartsFor(d)} className="h-7 px-2 rounded text-[var(--theme-text)] hover:bg-[var(--theme-surface-2)] inline-flex items-center gap-1 text-[11px] font-medium" title="Parts list" data-testid={`drawing-parts-${d.id}`}><ListChecks size={12} /> Parts{(d.parts || []).length ? ` (${d.parts.length})` : ''}</button>
                    <button onClick={() => view(d)} className="h-7 px-2 rounded text-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue)]/10 inline-flex items-center gap-1 text-[11px] font-medium" title="View" data-testid={`drawing-view-${d.id}`}><ImageIcon size={12} /> View</button>
                    <button onClick={() => remove(d)} disabled={busyId === d.id} className="h-7 w-7 rounded text-[var(--color-text-muted)] hover:text-red-500 inline-flex items-center justify-center disabled:opacity-50" title="Delete" data-testid={`drawing-delete-${d.id}`}>
                      {busyId === d.id ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={13} />}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {partsFor && (
        <PartsEditorModal
          drawing={partsFor}
          onClose={() => setPartsFor(null)}
          onSaved={(parts) => {
            setDrawings((prev) => prev.map((x) => x.id === partsFor.id ? { ...x, parts } : x));
            setPartsFor(null);
          }}
        />
      )}
    </div>
  );
}
