/**
 * H&S / RAMS Checklist admin (Iter 216h92).
 *
 * Operator-side editor for the org's pre-job safety checklist.
 *  - Add / edit / remove / reorder items
 *  - CSV export (template for bulk editing in Excel)
 *  - CSV import (append OR replace)
 *
 * Only owners and managers can persist changes (server-side enforced).
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import {
  ShieldCheck, Plus, Trash2, Save, Upload, Download, Loader2,
} from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } });


export default function SafetyTemplateAdmin() {
  const [tpl, setTpl] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const fileRef = useRef(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/svc/safety/template`, auth());
      setTpl(r.data);
    } catch (e) {
      toast.error('Could not load checklist', { description: e?.response?.data?.detail || e.message });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const updateItem = (idx, patch) => {
    if (!tpl) return;
    setTpl({ ...tpl, items: tpl.items.map((it, i) => (i === idx ? { ...it, ...patch } : it)) });
  };
  const addItem = () => {
    if (!tpl) return;
    setTpl({
      ...tpl,
      items: [...tpl.items, { id: `item_${Date.now()}`, label: '', required: false }],
    });
  };
  const removeItem = (idx) => {
    if (!tpl) return;
    setTpl({ ...tpl, items: tpl.items.filter((_, i) => i !== idx) });
  };
  const moveItem = (idx, dir) => {
    if (!tpl) return;
    const next = [...tpl.items];
    const target = idx + dir;
    if (target < 0 || target >= next.length) return;
    [next[idx], next[target]] = [next[target], next[idx]];
    setTpl({ ...tpl, items: next });
  };

  const save = async () => {
    if (!tpl) return;
    const valid = tpl.items.filter((i) => (i.label || '').trim());
    if (!valid.length) {
      toast.error('At least one item with a label is required');
      return;
    }
    setSaving(true);
    try {
      const r = await axios.put(`${API}/svc/safety/template`, { items: valid, name: tpl.name }, auth());
      setTpl(r.data);
      toast.success('Checklist saved');
    } catch (e) {
      toast.error('Save failed', { description: e?.response?.data?.detail || e.message });
    } finally {
      setSaving(false);
    }
  };

  const exportCsv = async () => {
    try {
      const r = await axios.get(`${API}/svc/safety/template/export.csv`, {
        ...auth(),
        responseType: 'blob',
      });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement('a');
      a.href = url; a.download = 'hs-checklist.csv';
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error('Export failed', { description: e?.message });
    }
  };

  const importCsv = async (replace) => {
    const file = fileRef.current?.files?.[0];
    if (!file) {
      toast.error('Choose a CSV file first');
      return;
    }
    if (replace && !window.confirm('Replace the entire checklist? Existing items will be lost.')) return;
    const fd = new FormData();
    fd.append('file', file);
    try {
      const r = await axios.post(
        `${API}/svc/safety/template/import-csv?replace=${replace}`,
        fd,
        { ...auth(), headers: { ...auth().headers, 'Content-Type': 'multipart/form-data' } },
      );
      toast.success(`Imported ${r.data.imported_count} row(s)`, {
        description: `Checklist now has ${r.data.total_count} items.`,
      });
      if (fileRef.current) fileRef.current.value = '';
      await load();
    } catch (e) {
      toast.error('Import failed', { description: e?.response?.data?.detail || e.message });
    }
  };

  if (loading) {
    return (
      <div className="p-8 flex items-center gap-2 text-slate-500" data-testid="safety-loading">
        <Loader2 className="animate-spin" size={16} /> Loading checklist…
      </div>
    );
  }
  if (!tpl) return null;

  return (
    <div className="p-4 sm:p-6 max-w-4xl" data-testid="safety-admin">
      <header className="flex items-center justify-between mb-4 flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <ShieldCheck size={20} className="text-emerald-600" />
          <h2 className="text-xl font-bold tracking-tight">Pre-job H&amp;S Checklist</h2>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={exportCsv}
            className="svc-btn svc-btn-secondary svc-btn-sm"
            data-testid="safety-export-csv"
          >
            <Download size={12} /> Export CSV
          </button>
          <button
            type="button"
            onClick={save}
            disabled={saving}
            className="svc-btn svc-btn-primary svc-btn-sm"
            data-testid="safety-save"
          >
            <Save size={12} /> {saving ? 'Saving…' : 'Save changes'}
          </button>
        </div>
      </header>

      <p className="text-sm svc-muted mb-4">
        These items appear on every engineer's mobile screen before they can start the on-site timer.
        Required items must be ticked. Drag-free reorder via the ↑/↓ arrows.
      </p>

      <div className="rounded-2xl border bg-white overflow-x-auto mb-4" style={{ borderColor: 'var(--theme-border)' }}>
        <table className="w-full text-sm" data-testid="safety-table" style={{ minWidth: '36rem' }}>
          <thead className="bg-slate-50/60">
            <tr className="text-left text-xs uppercase tracking-wider text-slate-500">
              <th className="px-3 py-2 w-14">Order</th>
              <th className="px-3 py-2">Label</th>
              <th className="px-3 py-2 w-28 text-center">Required</th>
              <th className="px-3 py-2 w-16"></th>
            </tr>
          </thead>
          <tbody>
            {tpl.items.map((it, idx) => (
              <tr key={it.id || idx} className="border-t" style={{ borderColor: 'var(--theme-border)' }} data-testid={`safety-row-${idx}`}>
                <td className="px-3 py-2 text-xs">
                  <div className="flex flex-col gap-0.5">
                    <button type="button" onClick={() => moveItem(idx, -1)} className="text-slate-400 hover:text-slate-700 disabled:opacity-30" disabled={idx === 0} aria-label="Move up">↑</button>
                    <button type="button" onClick={() => moveItem(idx, +1)} className="text-slate-400 hover:text-slate-700 disabled:opacity-30" disabled={idx === tpl.items.length - 1} aria-label="Move down">↓</button>
                  </div>
                </td>
                <td className="px-3 py-2">
                  <input
                    type="text"
                    value={it.label}
                    onChange={(e) => updateItem(idx, { label: e.target.value })}
                    placeholder="Checklist item label…"
                    className="w-full bg-transparent border-0 focus:outline-none text-sm"
                    data-testid={`safety-label-${idx}`}
                  />
                </td>
                <td className="px-3 py-2 text-center">
                  <input
                    type="checkbox"
                    checked={!!it.required}
                    onChange={(e) => updateItem(idx, { required: e.target.checked })}
                    data-testid={`safety-required-${idx}`}
                  />
                </td>
                <td className="px-3 py-2 text-right">
                  <button
                    type="button"
                    onClick={() => removeItem(idx)}
                    className="text-slate-400 hover:text-rose-500"
                    aria-label="Remove"
                    data-testid={`safety-remove-${idx}`}
                  >
                    <Trash2 size={14} />
                  </button>
                </td>
              </tr>
            ))}
            <tr>
              <td colSpan={4} className="px-3 py-2">
                <button
                  type="button"
                  onClick={addItem}
                  className="inline-flex items-center gap-1.5 text-sm text-blue-600 hover:underline"
                  data-testid="safety-add"
                >
                  <Plus size={13} /> Add item
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <section className="rounded-2xl border bg-slate-50/40 p-4 space-y-2" style={{ borderColor: 'var(--theme-border)' }} data-testid="safety-csv-import">
        <p className="text-xs font-bold uppercase tracking-wider text-slate-500">Bulk import (CSV)</p>
        <p className="text-xs svc-muted">
          CSV format: <code>label,required</code> (header required). Optional third column: <code>id</code>.
          Append-by-default preserves existing items. Replace mode wipes everything first.
        </p>
        <div className="flex items-center gap-2 flex-wrap">
          <input type="file" ref={fileRef} accept=".csv,text/csv" className="text-xs" data-testid="safety-csv-file" />
          <button
            type="button"
            onClick={() => importCsv(false)}
            className="svc-btn svc-btn-secondary svc-btn-sm"
            data-testid="safety-csv-import-append"
          >
            <Upload size={12} /> Append
          </button>
          <button
            type="button"
            onClick={() => importCsv(true)}
            className="svc-btn svc-btn-secondary svc-btn-sm"
            data-testid="safety-csv-import-replace"
          >
            <Upload size={12} /> Replace
          </button>
        </div>
      </section>
    </div>
  );
}
