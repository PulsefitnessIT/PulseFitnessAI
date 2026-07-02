/**
 * CRM Picklists admin panel — Iter 216h223.
 *
 * Drop-in section rendered inside CRMSettings.js. Lets admins manage
 * the centralised picklist vocabulary (job titles, industries, lead
 * sources, lost reasons, etc.) that drives every CRM dropdown.
 *
 * The panel reads `/api/crm/picklists` for the key catalogue and
 * `/api/crm/picklists/{key}` for the merged value list. Master admins
 * can edit global defaults; per-org admins can only add to / edit
 * their own org's values. Soft-deprecate (PATCH deprecated=true) is
 * preferred over hard-delete so existing records keep their labels.
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { List, Plus, Loader2, Trash2, EyeOff, Eye, Save } from 'lucide-react';

export default function CRMPicklistsSection({ API, headers, user, c, isDark }) {
  const [keys, setKeys] = useState([]);
  const [activeKey, setActiveKey] = useState(null);
  const [values, setValues] = useState([]);
  const [loadingKeys, setLoadingKeys] = useState(true);
  const [loadingValues, setLoadingValues] = useState(false);
  const [newLabel, setNewLabel] = useState('');
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState('');
  const [editingId, setEditingId] = useState(null);
  const [editLabel, setEditLabel] = useState('');
  const isMasterAdmin = Boolean(user?.is_master_admin);

  const fetchKeys = useCallback(async () => {
    setLoadingKeys(true);
    try {
      const r = await axios.get(`${API}/crm/picklists`, { headers: headers() });
      const arr = r.data.keys || [];
      setKeys(arr);
      if (!activeKey && arr.length) setActiveKey(arr[0].key);
    } catch (e) {
      setError('Failed to load picklists');
    }
    setLoadingKeys(false);
  }, [API, headers, activeKey]);

  const fetchValues = useCallback(async () => {
    if (!activeKey) return;
    setLoadingValues(true);
    setError('');
    try {
      const r = await axios.get(`${API}/crm/picklists/${activeKey}`, { headers: headers() });
      setValues(r.data.values || []);
    } catch (e) {
      setError('Failed to load values');
    }
    setLoadingValues(false);
  }, [API, activeKey, headers]);

  useEffect(() => { fetchKeys(); }, [fetchKeys]);
  useEffect(() => { fetchValues(); }, [fetchValues]);

  const addValue = async (e) => {
    e?.preventDefault?.();
    const lbl = newLabel.trim();
    if (!lbl || !activeKey) return;
    setAdding(true);
    setError('');
    try {
      await axios.post(`${API}/crm/picklists/${activeKey}`, { label: lbl }, { headers: headers() });
      setNewLabel('');
      fetchValues();
      fetchKeys();
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to add value');
    }
    setAdding(false);
  };

  const toggleDeprecated = async (v) => {
    try {
      await axios.patch(
        `${API}/crm/picklists/${activeKey}/${v.id}`,
        { deprecated: !v.deprecated },
        { headers: headers() },
      );
      fetchValues();
      fetchKeys();
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to update');
    }
  };

  const saveRename = async (v) => {
    const lbl = editLabel.trim();
    if (!lbl || lbl === v.label) { setEditingId(null); return; }
    try {
      await axios.patch(
        `${API}/crm/picklists/${activeKey}/${v.id}`,
        { label: lbl },
        { headers: headers() },
      );
      setEditingId(null);
      fetchValues();
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to rename');
    }
  };

  const hardDelete = async (v) => {
    if (!window.confirm(`Hard-delete "${v.label}"? This is refused if the value is still referenced anywhere.`)) return;
    try {
      await axios.delete(
        `${API}/crm/picklists/${activeKey}/${v.id}`,
        { headers: headers() },
      );
      fetchValues();
      fetchKeys();
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to delete');
    }
  };

  return (
    <div
      className="rounded-lg border p-5"
      style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}
      data-testid="settings-picklists"
    >
      <div className="flex items-start justify-between mb-4">
        <div>
          <h3 className="text-sm font-semibold flex items-center gap-2" style={{ color: c.text }}>
            <List size={14} /> Picklists
          </h3>
          <p className="text-xs mt-0.5" style={{ color: c.textDim }}>
            Centralised editable dropdowns. Global defaults are managed by the master admin;
            anything you add here is scoped to your organisation only.
          </p>
        </div>
        <span className="text-[10px] px-2 py-0.5 rounded-full uppercase tracking-wider font-bold" style={{ background: isMasterAdmin ? 'rgba(25, 205, 255,0.15)' : 'rgba(120,120,120,0.1)', color: isMasterAdmin ? '#7c3aed' : c.textDim }} data-testid="picklists-role-badge">
          {isMasterAdmin ? 'Master · Global edit' : 'Org · Local edit'}
        </span>
      </div>

      {loadingKeys ? (
        <div className="flex items-center gap-2 text-sm py-6" style={{ color: c.textMuted }}><Loader2 size={14} className="animate-spin" /> Loading picklists…</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {/* Key sidebar */}
          <div className="space-y-1" data-testid="picklists-keys">
            {keys.map(k => {
              const active = activeKey === k.key;
              return (
                <button
                  key={k.key}
                  type="button"
                  onClick={() => setActiveKey(k.key)}
                  className="w-full text-left flex items-center justify-between gap-2 px-3 py-2 rounded-md text-xs transition"
                  style={{
                    background: active ? 'rgba(0,122,255,0.1)' : 'transparent',
                    color: active ? 'var(--color-info-ios)' : c.textMuted,
                    fontWeight: active ? 600 : 500,
                  }}
                  data-testid={`picklists-key-${k.key}`}
                >
                  <span>{k.label}</span>
                  <span className="text-[10px] opacity-60">{k.value_count}</span>
                </button>
              );
            })}
          </div>

          {/* Values column */}
          <div className="md:col-span-3 space-y-3">
            {error && (
              <div className="text-xs px-3 py-2 rounded-md border" style={{ background: 'rgba(239,68,68,0.06)', borderColor: 'rgba(239,68,68,0.25)', color: 'var(--color-danger-alt)' }} data-testid="picklists-error">
                {error}
              </div>
            )}

            {/* Add new value */}
            <form onSubmit={addValue} className="flex items-center gap-2" data-testid="picklists-add-form">
              <input
                type="text"
                value={newLabel}
                onChange={e => setNewLabel(e.target.value)}
                placeholder={`Add a new ${activeKey?.replace('_', ' ') || 'value'}…`}
                className="flex-1 h-9 px-3 text-xs rounded-md border focus:outline-none focus:ring-2 focus:ring-[var(--color-info-ios)]/30"
                style={{ background: isDark ? 'var(--color-surface-dark-2)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)', color: c.text }}
                data-testid="picklists-add-input"
              />
              <button
                type="submit"
                disabled={adding || !newLabel.trim()}
                className="inline-flex items-center gap-1.5 h-9 px-3 text-xs font-semibold rounded-md text-white disabled:opacity-50"
                style={{ background: 'var(--color-info-ios)' }}
                data-testid="picklists-add-btn"
              >
                {adding ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />} Add
              </button>
            </form>

            {/* Values list */}
            {loadingValues ? (
              <div className="text-xs py-4 flex items-center gap-2" style={{ color: c.textMuted }}><Loader2 size={12} className="animate-spin" /> Loading…</div>
            ) : (
              <ul className="divide-y rounded-md border" style={{ borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }} data-testid="picklists-values">
                {values.map(v => {
                  const isGlobal = !v.organization_id;
                  const canEdit = isMasterAdmin || !isGlobal;
                  const editing = editingId === v.id;
                  return (
                    <li
                      key={v.id}
                      className="flex items-center gap-2 px-3 py-2 text-xs"
                      style={{ color: v.deprecated ? c.textDim : c.text, opacity: v.deprecated ? 0.6 : 1 }}
                      data-testid={`picklists-row-${v.id}`}
                    >
                      <span className="text-[10px] px-1.5 py-0.5 rounded-full font-bold tracking-wider uppercase" style={{ background: isGlobal ? 'rgba(25, 205, 255,0.12)' : 'rgba(0,122,255,0.10)', color: isGlobal ? '#7c3aed' : 'var(--color-info-ios)' }}>
                        {isGlobal ? 'Global' : 'Org'}
                      </span>
                      {editing ? (
                        <input
                          autoFocus
                          value={editLabel}
                          onChange={e => setEditLabel(e.target.value)}
                          onKeyDown={e => { if (e.key === 'Enter') saveRename(v); if (e.key === 'Escape') setEditingId(null); }}
                          onBlur={() => saveRename(v)}
                          className="flex-1 h-7 px-2 text-xs rounded border focus:outline-none focus:ring-1 focus:ring-[var(--color-info-ios)]"
                          style={{ background: isDark ? 'var(--color-surface-dark-2)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)', color: c.text }}
                          data-testid={`picklists-edit-input-${v.id}`}
                        />
                      ) : (
                        <button
                          type="button"
                          disabled={!canEdit}
                          onClick={() => { setEditingId(v.id); setEditLabel(v.label); }}
                          className="flex-1 text-left truncate hover:underline disabled:cursor-default disabled:no-underline"
                          style={{ textDecoration: v.deprecated ? 'line-through' : 'none' }}
                          data-testid={`picklists-label-${v.id}`}
                        >
                          {v.label}
                        </button>
                      )}
                      {canEdit && (
                        <>
                          {editing && (
                            <button
                              type="button"
                              onClick={() => saveRename(v)}
                              className="p-1.5 rounded text-xs"
                              style={{ color: 'var(--color-success-alt)' }}
                              title="Save"
                              data-testid={`picklists-save-${v.id}`}
                            ><Save size={12} /></button>
                          )}
                          <button
                            type="button"
                            onClick={() => toggleDeprecated(v)}
                            className="p-1.5 rounded text-xs"
                            style={{ color: v.deprecated ? 'var(--color-success-alt)' : c.textMuted }}
                            title={v.deprecated ? 'Restore' : 'Hide from new forms'}
                            data-testid={`picklists-deprecate-${v.id}`}
                          >
                            {v.deprecated ? <Eye size={12} /> : <EyeOff size={12} />}
                          </button>
                          <button
                            type="button"
                            onClick={() => hardDelete(v)}
                            className="p-1.5 rounded text-xs"
                            style={{ color: 'var(--color-danger-alt)' }}
                            title="Hard delete (only if not referenced)"
                            data-testid={`picklists-delete-${v.id}`}
                          ><Trash2 size={12} /></button>
                        </>
                      )}
                    </li>
                  );
                })}
                {values.length === 0 && !loadingValues && (
                  <li className="px-3 py-4 text-xs" style={{ color: c.textDim }}>No values yet — add one above.</li>
                )}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
