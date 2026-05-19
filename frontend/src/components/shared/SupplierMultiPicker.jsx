/**
 * SupplierMultiPicker — multi-select wrapper around the supplier
 * catalogue used by:
 *
 *   • Public Engineer Apply wizard (`/partners/engineers/apply`)
 *     → "Which brands do you service?" — was a free text input.
 *   • Partner Engineer settings drawer.
 *
 * Iter 216h217 — Craig's audit: drop-down boxes where possible, plus a
 * "+ Add new" button so engineers can self-declare a niche supplier.
 *
 * Renders as a list of chip-pills (selected brands) + a typeahead
 * input. Typing filters the curated list; clicking a list item adds
 * it. "Add new" commits a free-text custom value so an engineer who
 * services a one-off niche brand isn't blocked.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { ChevronDown, Search, Plus, X } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';

export default function SupplierMultiPicker({
  value = [],
  onChange,
  publicCatalogue = false,
  placeholder = 'Type a brand…',
  testid = 'supplier-multi-picker',
  disabled = false,
  // Iter 216h218 — `single` mode: emits the picked name as a STRING
  // (not an array) so it can drop straight into one-supplier fields
  // like equipment.supplier or part.supplier. The chip layout
  // collapses to a single chip + the picker hides the input once a
  // value is set (clearable via the chip ✕).
  single = false,
}) {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const wrapRef = useRef(null);

  const selected = useMemo(() => {
    if (!value) return [];
    if (Array.isArray(value)) return value.map((v) => String(v).trim()).filter(Boolean);
    if (single) {
      const v = String(value).trim();
      return v ? [v] : [];
    }
    return String(value).split(',').map((v) => v.trim()).filter(Boolean);
  }, [value, single]);

  const commit = (next) => {
    if (single) {
      onChange?.(next[0] || '');
    } else {
      onChange?.(next);
    }
  };

  // Lazy load
  const load = async () => {
    if (items.length || loading) return;
    setLoading(true);
    try {
      const path = publicCatalogue
        ? `${API}/suppliers/catalogue/public`
        : `${API}/suppliers/catalogue`;
      const headers = publicCatalogue
        ? {}
        : { Authorization: `Bearer ${localStorage.getItem('token')}` };
      const r = await axios.get(path, { headers });
      setItems(r.data?.all || []);
    } catch (_) {
      setItems([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const handler = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const filtered = useMemo(() => {
    const q = (query || '').trim().toLowerCase();
    const taken = new Set(selected.map((s) => s.toLowerCase()));
    return items.filter((s) => {
      const n = (s.name || '').toLowerCase();
      if (taken.has(n)) return false;
      return q ? n.includes(q) : true;
    });
  }, [items, query, selected]);

  const add = (name) => {
    const n = String(name || '').trim();
    if (!n) return;
    if (selected.some((s) => s.toLowerCase() === n.toLowerCase())) return;
    // Single-select replaces; multi-select appends.
    const next = single ? [n] : [...selected, n];
    commit(next);
    setQuery('');
    setOpen(!single); // close immediately in single mode
  };

  const remove = (name) => {
    commit(selected.filter((s) => s.toLowerCase() !== String(name).toLowerCase()));
  };

  const showAddNew = !!query.trim()
    && !filtered.some((s) => s.name.toLowerCase() === query.trim().toLowerCase())
    && !selected.some((s) => s.toLowerCase() === query.trim().toLowerCase());

  return (
    <div ref={wrapRef} className="relative" data-testid={testid}>
      <div
        className={`min-h-[2.5rem] w-full px-2.5 py-1.5 border rounded-lg flex flex-wrap items-center gap-1.5 bg-white ${
          open ? 'border-slate-900' : 'border-slate-200'
        }`}
        onClick={() => { if (!disabled) { load(); setOpen(true); } }}
      >
        {selected.map((name) => (
          <span
            key={name}
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-900 text-white text-xs font-semibold"
            data-testid={`${testid}-chip-${name.toLowerCase().replace(/\s+/g, '-')}`}
          >
            {name}
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); remove(name); }}
              className="hover:text-slate-300"
              aria-label={`Remove ${name}`}
              data-testid={`${testid}-remove-${name.toLowerCase().replace(/\s+/g, '-')}`}
            >
              <X size={11} />
            </button>
          </span>
        ))}
        <input
          type="text"
          value={query}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              const hit = filtered[0];
              if (hit) add(hit.name);
              else if (query.trim()) add(query.trim());
            } else if (e.key === 'Backspace' && !query && selected.length) {
              remove(selected[selected.length - 1]);
            }
          }}
          onFocus={() => { load(); setOpen(true); }}
          placeholder={selected.length === 0 ? placeholder : ''}
          className={`flex-1 min-w-[100px] outline-none bg-transparent text-sm py-1 ${
            single && selected.length ? 'hidden' : ''
          }`}
          disabled={disabled || (single && selected.length > 0)}
          data-testid={`${testid}-input`}
        />
        <ChevronDown size={13} className="text-slate-400" />
      </div>

      {open && (
        <div
          className="absolute z-50 left-0 right-0 mt-1 max-h-72 overflow-y-auto rounded-md border bg-white border-slate-200 shadow-lg"
          data-testid={`${testid}-dropdown`}
        >
          {loading && (
            <div className="px-3 py-2 text-xs text-slate-500">Loading suppliers…</div>
          )}
          {!loading && filtered.length === 0 && !showAddNew && (
            <div className="px-3 py-2 text-xs text-slate-500 flex items-center gap-1.5">
              <Search size={11} /> {selected.length === items.length
                ? 'All suppliers selected.'
                : `No match — keep typing to add "${query}" as a custom brand`}
            </div>
          )}
          {filtered.length > 0 && (
            <div>
              <div className="px-3 pt-2 pb-1 text-[10px] uppercase tracking-wider text-slate-500">
                Curated
              </div>
              {filtered.map((s) => (
                <button
                  key={s.slug}
                  type="button"
                  onClick={(e) => { e.stopPropagation(); add(s.name); }}
                  className="w-full text-left px-3 py-1.5 text-sm hover:bg-slate-50 flex items-center justify-between gap-2"
                  data-testid={`${testid}-option-${s.slug}`}
                >
                  <span className="flex flex-col">
                    <span className="text-slate-900">{s.name}</span>
                    {!!(s.categories?.length) && (
                      <span className="text-[10px] text-slate-500">
                        {(s.categories || []).slice(0, 3).join(' · ')}
                      </span>
                    )}
                  </span>
                </button>
              ))}
            </div>
          )}
          {showAddNew && (
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); add(query.trim()); }}
              className="w-full text-left px-3 py-2 text-xs border-t border-slate-200 hover:bg-slate-50 text-slate-900 flex items-center gap-1.5"
              data-testid={`${testid}-add-new`}
            >
              <Plus size={11} /> Add &quot;{query.trim()}&quot; as a new supplier
            </button>
          )}
        </div>
      )}
    </div>
  );
}
