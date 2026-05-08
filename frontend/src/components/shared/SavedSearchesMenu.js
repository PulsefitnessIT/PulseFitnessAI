import React, { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { useAuth } from '@/App';
import { Bookmark, Plus, Trash2, X } from 'lucide-react';

/**
 * SavedSearchesMenu (iter 215c0)
 * Dropdown to load/save filter presets for any list view.
 *
 * Props:
 *   module: one of `crm_contacts | crm_pipeline | crm_companies |
 *           memberships_members | memberships_bookings | marketing_audiences`
 *   currentFilters: the current filter object (will be saved as-is)
 *   onApply: (filters) => void  — caller applies returned filters
 */
const SavedSearchesMenu = ({ module, currentFilters, onApply }) => {
  const { API } = useAuth();
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState('');
  const ref = useRef(null);

  const load = async () => {
    const token = localStorage.getItem('token');
    try {
      const res = await axios.get(`${API}/saved-searches`, {
        headers: { Authorization: `Bearer ${token}` },
        params: { module },
      });
      setItems(res.data.items || []);
    } catch { setItems([]); }
  };

  useEffect(() => { load(); }, [API, module]); // eslint-disable-line

  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const save = async () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    const token = localStorage.getItem('token');
    try {
      await axios.post(`${API}/saved-searches`, {
        name: trimmed, module, filters: currentFilters || {},
      }, { headers: { Authorization: `Bearer ${token}` } });
      setName('');
      setCreating(false);
      load();
    } catch { /* ignore */ }
  };

  const remove = async (id) => {
    const token = localStorage.getItem('token');
    try {
      await axios.delete(`${API}/saved-searches/${id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      load();
    } catch { /* ignore */ }
  };

  return (
    <div ref={ref} className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        data-testid={`saved-searches-trigger-${module}`}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium border border-[var(--theme-border)] bg-[var(--theme-surface)] text-[var(--theme-text)] hover:bg-[var(--theme-surface-hover)]"
      >
        <Bookmark className="w-3.5 h-3.5" /> Saved searches
      </button>
      {open && (
        <div data-testid={`saved-searches-menu-${module}`} className="absolute right-0 mt-1 w-72 rounded-lg shadow-lg border border-[var(--theme-border)] bg-[var(--theme-surface)] z-30">
          <div className="px-3 py-2 border-b border-[var(--theme-border)] flex items-center justify-between">
            <p className="text-xs font-semibold text-[var(--theme-text)]">Your saved searches</p>
            <button
              type="button"
              onClick={() => setCreating(c => !c)}
              data-testid="saved-searches-new"
              className="text-[var(--color-brand-blue)] hover:underline text-xs flex items-center gap-1"
            >
              <Plus className="w-3 h-3" /> Save current
            </button>
          </div>
          {creating && (
            <div className="px-3 py-2 border-b border-[var(--theme-border)] flex gap-2">
              <input
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="Name this search…"
                data-testid="saved-searches-name-input"
                className="flex-1 text-sm rounded border border-[var(--theme-border)] bg-[var(--theme-surface)] px-2 py-1 text-[var(--theme-text)]"
                onKeyDown={e => { if (e.key === 'Enter') save(); }}
              />
              <button
                type="button"
                onClick={save}
                data-testid="saved-searches-save"
                className="text-xs px-2 py-1 rounded bg-[var(--color-brand-blue)] text-white"
              >Save</button>
              <button
                type="button"
                onClick={() => { setCreating(false); setName(''); }}
                aria-label="Cancel"
                className="text-[var(--color-text-muted)] hover:text-[var(--theme-text)]"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          )}
          <ul className="max-h-72 overflow-y-auto">
            {items.length === 0 ? (
              <li className="px-3 py-4 text-xs text-[var(--color-text-muted)] text-center">
                No saved searches yet.
              </li>
            ) : items.map(s => (
              <li key={s.id} data-testid={`saved-search-${s.id}`} className="flex items-center justify-between px-3 py-1.5 hover:bg-[var(--theme-surface-hover)]">
                <button
                  type="button"
                  onClick={() => { onApply?.(s.filters || {}); setOpen(false); }}
                  className="flex-1 text-left text-sm text-[var(--theme-text)] truncate"
                  data-testid={`saved-search-apply-${s.id}`}
                >
                  {s.name}
                </button>
                <button
                  type="button"
                  onClick={() => remove(s.id)}
                  aria-label={`Delete ${s.name}`}
                  data-testid={`saved-search-delete-${s.id}`}
                  className="ml-2 text-[var(--color-text-muted)] hover:text-red-500"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

export default SavedSearchesMenu;
