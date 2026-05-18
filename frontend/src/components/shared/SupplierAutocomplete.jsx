/**
 * SupplierAutocomplete — picker for equipment forms.
 *
 * Iter 216h193 — Lee's standardisation pass. Free-text supplier names
 * caused dirty reports ("TechnoGym" / "Technogym" / "techno gym"). We
 * now ship a curated UK fitness supplier list (Pulse, Technogym, Life
 * Fitness, Precor, …) plus the org's own custom suppliers, surfaced via
 * `GET /api/suppliers/catalogue`.
 *
 * Behaviour
 *   • Typing filters both groups (curated + custom) by name match.
 *   • Clicking an option commits the name back to the parent via
 *     `onChange(name, supplier)` where `supplier` includes slug,
 *     categories, etc. The frontend can then fire a photo-lookup.
 *   • "Add new…" at the bottom of the list lets the operator type a
 *     bespoke supplier without leaving the form. This commits the
 *     name only — they can edit address / phone in Settings later.
 *
 * Designed to drop into the existing equipment forms (OnboardingWizard,
 * AddEquipmentDialog, EquipmentInfoTab edit panels) without a layout
 * regression — width / height match a standard <Input>.
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { ChevronDown, Search, Plus, Check } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { useAuth } from '@/App';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';

export default function SupplierAutocomplete({
  value = '',
  onChange,
  onSelectSupplier,
  placeholder = 'Supplier',
  className = '',
  inputClassName = '',
  disabled = false,
  testid,
}) {
  const { } = useAuth();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState(value);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const wrapRef = useRef(null);

  useEffect(() => { setQuery(value || ''); }, [value]);

  // Lazy-load the catalogue once on first focus so we don't fan out a
  // request for every equipment row when the wizard renders 20 rows.
  const load = async () => {
    if (items.length || loading) return;
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const r = await axios.get(`${API}/suppliers/catalogue`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setItems(r.data?.all || []);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  };

  // Close on outside click
  useEffect(() => {
    const handler = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const filtered = useMemo(() => {
    const q = (query || '').trim().toLowerCase();
    if (!q) return items;
    return items.filter((s) => (s.name || '').toLowerCase().includes(q));
  }, [items, query]);

  const grouped = useMemo(() => ({
    curated: filtered.filter((s) => s.source === 'curated'),
    custom: filtered.filter((s) => s.source === 'custom'),
  }), [filtered]);

  const commit = (name, supplier = null) => {
    onChange?.(name);
    onSelectSupplier?.(supplier);
    setQuery(name);
    setOpen(false);
  };

  return (
    <div ref={wrapRef} className={`relative ${className}`}>
      <div className="relative">
        <Input
          value={query}
          disabled={disabled}
          onFocus={() => { load(); setOpen(true); }}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
            onChange?.(e.target.value);
          }}
          placeholder={placeholder}
          className={`pr-7 ${inputClassName}`}
          data-testid={testid || 'supplier-autocomplete'}
        />
        <ChevronDown
          size={14}
          className="absolute right-2 top-1/2 -translate-y-1/2 opacity-50 pointer-events-none"
        />
      </div>
      {open && (
        <div
          className="absolute z-50 left-0 right-0 mt-1 max-h-72 overflow-y-auto rounded-md border bg-[var(--theme-surface)] border-[var(--theme-border)] shadow-lg"
          data-testid={testid ? `${testid}-dropdown` : 'supplier-autocomplete-dropdown'}
        >
          {loading && (
            <div className="px-3 py-2 text-xs text-[var(--theme-text-muted)]">Loading suppliers…</div>
          )}
          {!loading && filtered.length === 0 && (
            <div className="px-3 py-2 text-xs text-[var(--theme-text-muted)] flex items-center gap-1.5">
              <Search size={11} /> No match — keep typing to add "{query}" as a new supplier
            </div>
          )}
          {grouped.curated.length > 0 && (
            <div>
              <div className="px-3 pt-2 pb-1 text-[10px] uppercase tracking-wider text-[var(--theme-text-muted)]">
                Curated
              </div>
              {grouped.curated.map((s) => (
                <button
                  key={`curated-${s.slug}`}
                  type="button"
                  onClick={() => commit(s.name, s)}
                  className="w-full text-left px-3 py-1.5 text-sm hover:bg-[var(--theme-surface-hover,var(--theme-border))] flex items-center justify-between gap-2"
                  data-testid={`supplier-option-${s.slug}`}
                >
                  <span className="flex flex-col">
                    <span className="text-[var(--theme-text)]">{s.name}</span>
                    {!!(s.categories?.length) && (
                      <span className="text-[10px] text-[var(--theme-text-muted)]">
                        {(s.categories || []).slice(0, 3).join(' · ')}
                      </span>
                    )}
                  </span>
                  {s.name.toLowerCase() === (value || '').toLowerCase() && (
                    <Check size={13} className="text-emerald-500 flex-shrink-0" />
                  )}
                </button>
              ))}
            </div>
          )}
          {grouped.custom.length > 0 && (
            <div>
              <div className="px-3 pt-2 pb-1 text-[10px] uppercase tracking-wider text-[var(--theme-text-muted)]">
                Yours
              </div>
              {grouped.custom.map((s) => (
                <button
                  key={`custom-${s.id || s.slug}`}
                  type="button"
                  onClick={() => commit(s.name, s)}
                  className="w-full text-left px-3 py-1.5 text-sm hover:bg-[var(--theme-surface-hover,var(--theme-border))] text-[var(--theme-text)]"
                  data-testid={`supplier-option-custom-${s.slug}`}
                >
                  {s.name}
                </button>
              ))}
            </div>
          )}
          {!loading && query && !filtered.some((s) => s.name.toLowerCase() === query.toLowerCase()) && (
            <button
              type="button"
              onClick={() => commit(query.trim(), null)}
              className="w-full text-left px-3 py-2 text-xs border-t border-[var(--theme-border)] hover:bg-[var(--theme-surface-hover,var(--theme-border))] text-[var(--theme-text)] flex items-center gap-1.5"
              data-testid="supplier-add-new"
            >
              <Plus size={11} /> Add "{query.trim()}" as a new supplier
            </button>
          )}
        </div>
      )}
    </div>
  );
}
