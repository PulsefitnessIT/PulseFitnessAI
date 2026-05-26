/**
 * NotePresetChips — Iter 220d
 *
 * Quick-add chip palette for engineer notes. Shows pinned + most-used
 * presets first, with a search box for the long-tail. Tapping a chip
 * inserts the text into the bound textarea via `onInsert(text)` and
 * increments the preset's use_count server-side (so frequently-used
 * presets float to the top over time).
 *
 * Provides "+ Save current text as preset" so engineers can self-
 * curate their personal library and bookmark org-wide best practices
 * (e.g. "Million-Meter calibration check needed").
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Plus, Pin, PinOff, Trash2, Search, X, Loader2, Save } from 'lucide-react';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
});

export default function NotePresetChips({ onInsert, currentText }) {
  const [presets, setPresets] = useState([]);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState('');
  const [saving, setSaving] = useState(false);
  const [showAll, setShowAll] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/svc/engineer/note-presets`, auth());
      setPresets(r.data?.presets || []);
    } catch (e) {
      console.warn('[note-presets] load failed', e);
      setPresets([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    let list = presets;
    if (needle) {
      list = list.filter(p => (p.text || '').toLowerCase().includes(needle));
    }
    return showAll || needle ? list : list.slice(0, 8);
  }, [presets, query, showAll]);

  const insertAndCount = async (p) => {
    onInsert?.(p.text);
    try {
      await axios.post(`${API}/svc/engineer/note-presets/${p.id}/used`, {}, auth());
      // Optimistic local bump so the chip re-sorts in this session.
      setPresets((rows) => rows.map(r => r.id === p.id ? { ...r, use_count: (r.use_count || 0) + 1 } : r));
    } catch (e) { /* non-blocking */ }
  };

  const togglePin = async (p) => {
    try {
      const r = await axios.patch(`${API}/svc/engineer/note-presets/${p.id}`, { pinned: !p.pinned }, auth());
      setPresets((rows) => rows.map(x => x.id === p.id ? r.data : x).sort((a, b) => {
        if ((b.pinned ? 1 : 0) !== (a.pinned ? 1 : 0)) return (b.pinned ? 1 : 0) - (a.pinned ? 1 : 0);
        return (b.use_count || 0) - (a.use_count || 0);
      }));
    } catch (e) {
      notify.error('Could not update pin', e?.response?.data?.detail || e?.message);
    }
  };

  const archive = async (p) => {
    if (!window.confirm(`Remove "${p.text.slice(0, 60)}…" from your quick-adds?`)) return;
    try {
      await axios.delete(`${API}/svc/engineer/note-presets/${p.id}`, auth());
      setPresets((rows) => rows.filter(x => x.id !== p.id));
    } catch (e) {
      notify.error('Could not archive', e?.response?.data?.detail || e?.message);
    }
  };

  const saveCurrentAsPreset = async (scope) => {
    const text = (currentText || '').trim();
    if (!text) { notify.error('Type something first to save it'); return; }
    if (text.length < 8) { notify.error('Preset must be at least 8 characters'); return; }
    setSaving(true);
    try {
      const r = await axios.post(`${API}/svc/engineer/note-presets`, { text, scope }, auth());
      // Move new (or de-duped) preset to the top of the visible list.
      setPresets((rows) => [r.data, ...rows.filter(x => x.id !== r.data.id)]);
      notify.success(scope === 'shared' ? 'Saved as shared preset' : 'Saved to your quick-adds');
    } catch (e) {
      notify.error('Could not save', e?.response?.data?.detail || e?.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mt-2 rounded-xl border border-slate-200 bg-slate-50 p-2.5" data-testid="note-preset-chips">
      <div className="flex items-center gap-2 mb-2">
        <p className="text-[10px] font-bold uppercase tracking-wide text-slate-500 flex-1">
          Quick-add notes
        </p>
        <div className="relative">
          <Search size={11} className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search…"
            className="pl-6 pr-2 py-1 text-xs rounded border border-slate-200 bg-white w-32"
            data-testid="preset-search"
          />
        </div>
      </div>

      {loading ? (
        <div className="flex items-center text-xs text-slate-400 py-2">
          <Loader2 size={12} className="animate-spin mr-1" /> Loading…
        </div>
      ) : visible.length === 0 ? (
        <p className="text-xs text-slate-400 italic py-1" data-testid="preset-empty">
          {query ? 'No presets match.' : 'No quick-adds yet — type a recurring note below and tap "Save as preset".'}
        </p>
      ) : (
        <div className="flex flex-wrap gap-1.5" data-testid="preset-chip-list">
          {visible.map((p) => (
            <span
              key={p.id}
              className={`group inline-flex items-center gap-1 max-w-full text-xs rounded-full border px-2.5 py-1 cursor-pointer
                ${p.scope === 'shared' ? 'bg-blue-50 border-blue-200 text-blue-900' : 'bg-white border-slate-200 text-slate-800'}
                hover:shadow-sm`}
              data-testid={`preset-chip-${p.id}`}
              onClick={() => insertAndCount(p)}
              title={p.scope === 'shared' ? 'Org-wide preset' : 'Your personal preset'}
            >
              {p.pinned && <Pin size={9} className="text-amber-600 flex-shrink-0" />}
              <span className="truncate max-w-[260px]">{p.text}</span>
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); togglePin(p); }}
                className="opacity-0 group-hover:opacity-100 transition-opacity p-0.5"
                aria-label={p.pinned ? 'Unpin' : 'Pin'}
                data-testid={`preset-pin-${p.id}`}
              >
                {p.pinned ? <PinOff size={10} /> : <Pin size={10} />}
              </button>
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); archive(p); }}
                className="opacity-0 group-hover:opacity-100 transition-opacity p-0.5"
                aria-label="Remove"
                data-testid={`preset-archive-${p.id}`}
              >
                <X size={10} />
              </button>
            </span>
          ))}
        </div>
      )}

      {presets.length > 8 && !query && (
        <button
          type="button"
          onClick={() => setShowAll(s => !s)}
          className="text-[10px] text-blue-600 font-bold mt-1.5"
          data-testid="preset-show-toggle"
        >
          {showAll ? 'Show fewer' : `Show all ${presets.length}`}
        </button>
      )}

      <div className="mt-2 flex items-center gap-1.5 flex-wrap pt-2 border-t border-slate-200">
        <p className="text-[10px] text-slate-500 mr-1">Save current note as:</p>
        <button
          type="button"
          onClick={() => saveCurrentAsPreset('personal')}
          disabled={saving}
          className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-1 rounded-full border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          data-testid="preset-save-personal"
        >
          {saving ? <Loader2 size={9} className="animate-spin" /> : <Save size={9} />} Personal
        </button>
        <button
          type="button"
          onClick={() => saveCurrentAsPreset('shared')}
          disabled={saving}
          className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-1 rounded-full border border-blue-200 bg-blue-50 text-blue-800 hover:bg-blue-100 disabled:opacity-50"
          data-testid="preset-save-shared"
        >
          {saving ? <Loader2 size={9} className="animate-spin" /> : <Plus size={9} />} Shared (org)
        </button>
      </div>
    </div>
  );
}
