/**
 * Sprint C — Saved Views dropdown.
 *
 * Lets the operator jump between built-in presets ("Trialists ending in
 * 7 days", "No-shows last 14 days", "Not yet on the portal", "New this
 * week") and their own saved views. The caller supplies `value` (the
 * currently selected view id — string or null = "All members") and an
 * `onChange(view)` callback. `view.filter` gets round-tripped back to
 * `GET /memberships/members-filtered?<params>`.
 *
 * Saving a custom view pops a tiny inline form; the parent provides the
 * current filter state (q, tag, status) to persist.
 */
import React, { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { ChevronDown, Bookmark, Clock, AlertCircle, Mail, Sparkles, X, Plus, Trash2 } from 'lucide-react';
import { notify } from '@/components/notifications';

const PRESET_ICONS = {
  clock: Clock,
  alert: AlertCircle,
  mail: Mail,
  sparkles: Sparkles,
};

export default function SavedViewsDropdown({ API, headers, value, onChange, currentFilter }) {
  const [open, setOpen] = useState(false);
  const [presets, setPresets] = useState([]);
  const [custom, setCustom] = useState([]);
  const [saving, setSaving] = useState(false);
  const [showSaveForm, setShowSaveForm] = useState(false);
  const [newName, setNewName] = useState('');
  const ref = useRef(null);

  const load = React.useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/memberships/saved-views`, { headers });
      setPresets(data.presets || []);
      setCustom(data.custom || []);
    } catch {
      /* silent — dropdown just shows defaults */
    }
  }, [API, headers]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!open) return undefined;
    const onDoc = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  const activeView = React.useMemo(() => {
    if (!value) return null;
    return [...presets, ...custom].find((v) => v.id === value) || null;
  }, [value, presets, custom]);

  const pick = (view) => {
    setOpen(false);
    onChange(view);
  };

  const saveCustom = async () => {
    const trimmed = newName.trim();
    if (!trimmed) { notify.error('Name required', 'Give your view a short label.'); return; }
    if (!currentFilter || Object.keys(currentFilter).length === 0) {
      notify.error('Nothing to save', 'Apply a filter first, then save it.');
      return;
    }
    setSaving(true);
    try {
      const { data } = await axios.post(`${API}/memberships/saved-views`,
        { name: trimmed, filter: currentFilter }, { headers });
      setCustom((prev) => [data.view, ...prev]);
      setNewName('');
      setShowSaveForm(false);
      notify.success('View saved', `"${trimmed}" is now in your dropdown.`);
      onChange(data.view);
      setOpen(false);
    } catch (e) {
      notify.error('Save failed', e.response?.data?.detail || 'Try again.');
    } finally {
      setSaving(false);
    }
  };

  const deleteCustom = async (view, e) => {
    e.stopPropagation();
    if (!window.confirm(`Delete saved view "${view.name}"?`)) return;
    try {
      await axios.delete(`${API}/memberships/saved-views/${view.id}`, { headers });
      setCustom((prev) => prev.filter((v) => v.id !== view.id));
      if (value === view.id) onChange(null);
      notify.success('View deleted');
    } catch (e) {
      notify.error('Delete failed', e.response?.data?.detail || 'Try again.');
    }
  };

  return (
    <div ref={ref} className="relative" data-testid="mbr-saved-views">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={`h-9 inline-flex items-center gap-1.5 rounded-full border px-3 text-xs font-bold transition-colors ${
          activeView
            ? 'bg-[color:var(--color-brand-cyan)]/10 border-[color:var(--color-brand-cyan)]/40 text-[color:var(--color-brand-cyan)]'
            : 'border-[color:var(--theme-border)] text-[color:var(--theme-text-muted)] hover:text-[color:var(--theme-text)]'
        }`}
        data-testid="mbr-saved-views-trigger"
      >
        <Bookmark size={13} />
        <span className="truncate max-w-[140px]">{activeView ? activeView.name : 'All members'}</span>
        <ChevronDown size={12} />
      </button>

      {open && (
        <div
          className="absolute left-0 top-10 z-30 w-72 rounded-xl border border-[color:var(--theme-border)] bg-[color:var(--theme-surface)] shadow-xl overflow-hidden"
          data-testid="mbr-saved-views-menu"
        >
          <div className="px-3 py-2 border-b border-[color:var(--theme-border)]">
            <p className="text-[10px] font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)]">Smart views</p>
          </div>
          <button
            type="button"
            onClick={() => pick(null)}
            className={`w-full text-left px-3 py-2 text-xs transition-colors ${
              !value ? 'bg-[color:var(--color-brand-cyan)]/10 text-[color:var(--color-brand-cyan)]' : 'hover:bg-[color:var(--theme-surface-hover)]'
            }`}
            data-testid="mbr-saved-views-all"
          >
            <span className="font-bold">All members</span>
          </button>
          {presets.map((p) => {
            const Icon = PRESET_ICONS[p.icon] || Bookmark;
            const active = value === p.id;
            return (
              <button
                key={p.id}
                type="button"
                onClick={() => pick(p)}
                className={`w-full text-left px-3 py-2 text-xs transition-colors flex items-start gap-2 ${
                  active ? 'bg-[color:var(--color-brand-cyan)]/10 text-[color:var(--color-brand-cyan)]' : 'hover:bg-[color:var(--theme-surface-hover)]'
                }`}
                data-testid={`mbr-saved-view-${p.id.replace(':','_')}`}
              >
                <Icon size={13} className="mt-0.5 shrink-0" />
                <span className="flex-1">
                  <span className="font-bold block">{p.name}</span>
                  <span className="opacity-70 text-[10px]">{p.description}</span>
                </span>
              </button>
            );
          })}
          {custom.length > 0 && (
            <>
              <div className="px-3 py-2 border-t border-[color:var(--theme-border)]">
                <p className="text-[10px] font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)]">Your saved views</p>
              </div>
              {custom.map((v) => {
                const active = value === v.id;
                return (
                  <div
                    key={v.id}
                    className={`flex items-center justify-between group transition-colors ${
                      active ? 'bg-[color:var(--color-brand-cyan)]/10 text-[color:var(--color-brand-cyan)]' : 'hover:bg-[color:var(--theme-surface-hover)]'
                    }`}
                  >
                    <button
                      type="button"
                      onClick={() => pick(v)}
                      className="flex-1 text-left px-3 py-2 text-xs font-bold truncate"
                      data-testid={`mbr-saved-view-custom-${v.id.slice(0,8)}`}
                    >
                      {v.name}
                    </button>
                    <button
                      type="button"
                      onClick={(e) => deleteCustom(v, e)}
                      className="px-2 py-1 opacity-0 group-hover:opacity-100 transition-opacity text-[color:var(--theme-text-muted)] hover:text-red-400"
                      aria-label={`Delete ${v.name}`}
                      data-testid={`mbr-saved-view-delete-${v.id.slice(0,8)}`}
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                );
              })}
            </>
          )}
          <div className="border-t border-[color:var(--theme-border)]">
            {showSaveForm ? (
              <div className="p-3 space-y-2">
                <input
                  autoFocus
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="e.g. VIPs with overdue invoice"
                  className="w-full h-8 rounded-md bg-transparent border border-[color:var(--theme-border)] px-2 text-xs text-[color:var(--theme-text)] focus:outline-none focus:border-[color:var(--color-brand-cyan)]"
                  data-testid="mbr-saved-views-name-input"
                />
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={saveCustom}
                    disabled={saving}
                    className="flex-1 h-7 rounded-md bg-[color:var(--color-brand-cyan)] text-[10px] font-bold text-white disabled:opacity-50"
                    data-testid="mbr-saved-views-save-confirm"
                  >
                    {saving ? 'Saving…' : 'Save current filter'}
                  </button>
                  <button
                    type="button"
                    onClick={() => { setShowSaveForm(false); setNewName(''); }}
                    className="h-7 w-7 rounded-md border border-[color:var(--theme-border)] text-[color:var(--theme-text-muted)]"
                    aria-label="Cancel"
                  >
                    <X size={12} />
                  </button>
                </div>
                <p className="text-[10px] text-[color:var(--theme-text-muted)]">
                  Saves: {Object.entries(currentFilter || {}).map(([k, v]) => `${k}=${v}`).join(' · ') || 'nothing (apply a filter first)'}
                </p>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setShowSaveForm(true)}
                className="w-full px-3 py-2 text-xs font-bold text-[color:var(--color-brand-cyan)] hover:bg-[color:var(--color-brand-cyan)]/10 transition-colors inline-flex items-center gap-1.5"
                data-testid="mbr-saved-views-new"
              >
                <Plus size={12} /> Save current filter as view
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
