import { useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { useAuth } from '@/App';
import { Input } from '@/components/ui/input';
import { ChevronDown, Check, X } from 'lucide-react';

const OTHER_VALUE = '__other__';

/**
 * Searchable manufacturer dropdown backed by GET /api/equipment/manufacturers.
 *
 * Behaviour:
 *  - Type to filter the curated list
 *  - Pick a curated brand → emits its display name
 *  - Pick "Other" → reveals a free-text input below; emits the user-typed value
 *  - If `value` is already populated with a non-curated string, the field
 *    auto-bootstraps in "Other" mode pre-filled with that string (so editing
 *    legacy records doesn't blow them away).
 *
 * Loaded in iter 224 — replaces free-text manufacturer inputs in the
 * Add/Edit Equipment forms to reduce typo-driven supplier-routing errors.
 */
const ManufacturerCombobox = ({ value, onChange, testId = 'manufacturer-combobox', className = '' }) => {
  const { API } = useAuth();
  const [list, setList] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [otherMode, setOtherMode] = useState(false);
  const wrapperRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await axios.get(`${API}/equipment/manufacturers`);
        if (cancelled) return;
        setList(r.data?.manufacturers || []);
      } catch {
        // Fail open with empty list — caller can still pick "Other"
      }
      setLoaded(true);
    })();
    return () => { cancelled = true; };
  }, [API]);

  // Auto-detect "Other" mode for legacy records once the curated list loads.
  useEffect(() => {
    if (!loaded || !value) return;
    const inList = list.some((m) => m.name.toLowerCase() === value.toLowerCase());
    if (!inList) setOtherMode(true);
  }, [loaded, list, value]);

  // Close dropdown on outside click.
  useEffect(() => {
    const onDocClick = (e) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return list;
    return list.filter((m) => m.name.toLowerCase().includes(q));
  }, [list, query]);

  const selectedLabel = otherMode
    ? 'Other (enter manually)'
    : (value || '');

  const pick = (name) => {
    if (name === OTHER_VALUE) {
      setOtherMode(true);
      onChange('');
    } else {
      setOtherMode(false);
      onChange(name);
    }
    setOpen(false);
    setQuery('');
  };

  return (
    <div className={`relative ${className}`} ref={wrapperRef}>
      {!otherMode && (
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="w-full flex items-center justify-between bg-[var(--color-ink-alt)] border border-white/10 text-white rounded-md px-3 py-2 text-sm hover:border-white/20 focus:outline-none focus:border-[var(--color-brand-blue)] mt-1"
          data-testid={`${testId}-trigger`}
        >
          <span className={selectedLabel ? 'text-white' : 'text-[var(--color-text-muted)]'}>
            {selectedLabel || 'Select manufacturer…'}
          </span>
          <ChevronDown size={14} className="text-[var(--color-text-muted)] shrink-0" />
        </button>
      )}

      {otherMode && (
        <div className="flex gap-2 mt-1">
          <Input
            value={value || ''}
            onChange={(e) => onChange(e.target.value)}
            placeholder="Type the manufacturer name"
            className="bg-[var(--color-ink-alt)] border-white/10 text-white"
            data-testid={`${testId}-other-input`}
            autoFocus
          />
          <button
            type="button"
            onClick={() => { setOtherMode(false); onChange(''); }}
            className="px-2 text-[var(--color-text-muted)] hover:text-white text-xs flex items-center gap-1 border border-white/10 rounded-md"
            data-testid={`${testId}-other-cancel`}
            title="Pick from list instead"
          >
            <X size={12} /> List
          </button>
        </div>
      )}

      {open && !otherMode && (
        <div className="absolute z-50 mt-1 w-full bg-[var(--theme-surface)] border border-white/10 rounded-md shadow-xl max-h-72 overflow-hidden flex flex-col" data-testid={`${testId}-popup`}>
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search…"
            className="bg-[var(--color-ink-alt)] border-0 border-b border-white/10 text-white rounded-none focus-visible:ring-0"
            data-testid={`${testId}-search`}
            autoFocus
          />
          <div className="overflow-y-auto flex-1">
            {filtered.map((m) => (
              <button
                key={m.domain}
                type="button"
                onClick={() => pick(m.name)}
                className="w-full text-left px-3 py-2 text-sm text-white hover:bg-white/5 flex items-center justify-between"
                data-testid={`${testId}-option-${m.domain}`}
              >
                <span>{m.name}</span>
                {value === m.name && <Check size={14} className="text-[var(--color-brand-blue)]" />}
              </button>
            ))}
            {filtered.length === 0 && (
              <p className="text-[var(--color-text-muted)] text-xs px-3 py-3 text-center" data-testid={`${testId}-no-results`}>
                No matches — pick "Other" to enter a custom name.
              </p>
            )}
            <button
              type="button"
              onClick={() => pick(OTHER_VALUE)}
              className="w-full text-left px-3 py-2 text-sm text-[var(--color-brand-blue)] hover:bg-[rgb(var(--rgb-brand-blue)/0.1)] border-t border-white/10 font-medium"
              data-testid={`${testId}-option-other`}
            >
              + Other (enter manually)
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default ManufacturerCombobox;
