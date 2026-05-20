/* Dynamic Lists tab — auto-refreshing audience segments (Iter 229).
 *
 * Differs from static Audiences in two ways:
 *   • each list re-evaluates on read if older than its refresh interval
 *   • list rows show a "last refreshed" timestamp + manual refresh button
 *
 * Reuses the same FIELDS/OPS vocabulary as AudiencesTab so users learn
 * one rule-builder, not two.
 */
import React, { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { ListChecks, Plus, Sparkles, Loader2, Trash2, Save, RefreshCw, ChevronDown, ChevronUp, Clock } from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

const BASE_FIELDS = [
  { id: 'lifetime_value_gbp', label: 'Lifetime value (£)', type: 'number' },
  { id: 'churn_risk_score', label: 'Churn risk score', type: 'number' },
  { id: 'attendance_30d', label: 'Visits in last 30 days', type: 'number' },
  { id: 'last_attended_at', label: 'Last attended', type: 'days_ago' },
  { id: 'signup_at', label: 'Signed up', type: 'days_ago' },
  { id: 'class_preference', label: 'Class preference', type: 'enum', options: ['spin', 'hiit', 'pt', 'yoga', 'strength'] },
  { id: 'subscription_tier', label: 'Subscription tier', type: 'enum', options: ['free', 'pro', 'premium'] },
  { id: 'payment_status', label: 'Payment status', type: 'enum', options: ['active', 'failed', 'cancelled'] },
];
const FIELD_TYPE_TO_RB = (ft) => {
  if (ft === 'number') return 'number';
  if (ft === 'date') return 'days_ago';
  if (ft === 'select' || ft === 'multi_select') return 'enum';
  return 'text';
};
const OPS = [
  { id: '>=', label: '≥' }, { id: '<=', label: '≤' }, { id: '==', label: '=' }, { id: '!=', label: '≠' },
];
const REFRESH_OPTIONS = [
  { value: 15, label: 'Every 15 minutes' },
  { value: 60, label: 'Hourly (default)' },
  { value: 240, label: 'Every 4 hours' },
  { value: 1440, label: 'Daily' },
];

const formatRelative = (iso) => {
  if (!iso) return 'never';
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 60_000) return 'just now';
  const m = Math.floor(ms / 60_000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
};

const DynamicListsTab = ({ API, headers }) => {
  const [lists, setLists] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [draftName, setDraftName] = useState('');
  const [draftDescription, setDraftDescription] = useState('');
  const [draftInterval, setDraftInterval] = useState(60);
  const [draftConditions, setDraftConditions] = useState([]);
  const [draftPreviewSize, setDraftPreviewSize] = useState(0);
  const [busy, setBusy] = useState(false);
  const [expandedId, setExpandedId] = useState(null);
  const [members, setMembers] = useState({});
  const [customFields, setCustomFields] = useState([]);

  const FIELDS = React.useMemo(() => [...BASE_FIELDS, ...customFields], [customFields]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/api/marketing/dynamic-lists`, { headers });
      setLists(data.lists || []);
    } catch {
      notify.error('Failed to load dynamic lists');
    }
    setLoading(false);
  }, [API, headers]);

  const loadCustomProps = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/api/custom-properties?entity_type=contact`, { headers });
      const cf = (data.properties || []).map((p) => ({
        id: `custom_fields.${p.key}`,
        label: `${p.label} (custom)`,
        type: FIELD_TYPE_TO_RB(p.field_type),
        options: (p.options || []).map((o) => o.value),
      }));
      setCustomFields(cf);
    } catch { /* noop */ }
  }, [API, headers]);

  useEffect(() => { load(); loadCustomProps(); }, [load, loadCustomProps]);

  const refreshDraftPreview = useCallback(async (conditions) => {
    try {
      const { data } = await axios.post(`${API}/api/marketing/audiences/preview`, {
        rules: { op: 'and', conditions },
      }, { headers });
      setDraftPreviewSize(data.estimated_size || 0);
    } catch { /* noop */ }
  }, [API, headers]);

  useEffect(() => {
    if (creating) refreshDraftPreview(draftConditions);
  }, [creating, draftConditions, refreshDraftPreview]);

  const addCondition = () => setDraftConditions((c) => [...c, { field: 'lifetime_value_gbp', op: '>=', value: 100 }]);
  const updateCondition = (i, patch) => setDraftConditions((c) => c.map((x, idx) => idx === i ? { ...x, ...patch } : x));
  const removeCondition = (i) => setDraftConditions((c) => c.filter((_, idx) => idx !== i));

  const save = async () => {
    if (!draftName.trim()) return;
    setBusy(true);
    try {
      await axios.post(`${API}/api/marketing/dynamic-lists`, {
        name: draftName,
        description: draftDescription,
        rules: { op: 'and', conditions: draftConditions },
        refresh_interval_minutes: draftInterval,
      }, { headers });
      notify.success('Dynamic list created');
      setDraftName(''); setDraftDescription(''); setDraftConditions([]); setDraftInterval(60);
      setCreating(false);
      load();
    } catch (e) {
      notifyApiError(notify, e, 'Save failed');
    } finally { setBusy(false); }
  };

  const refreshOne = async (id) => {
    setBusy(true);
    try {
      await axios.post(`${API}/api/marketing/dynamic-lists/${id}/refresh`, {}, { headers });
      load();
      if (expandedId === id) loadMembers(id);
      notify.success('List refreshed');
    } catch (e) {
      notifyApiError(notify, e, 'Refresh failed');
    } finally { setBusy(false); }
  };

  const remove = async (id) => {
    if (!window.confirm('Delete this dynamic list?')) return;
    try {
      await axios.delete(`${API}/api/marketing/dynamic-lists/${id}`, { headers });
      notify.success('Deleted');
      load();
    } catch (e) {
      notifyApiError(notify, e, 'Delete failed');
    }
  };

  const loadMembers = async (id) => {
    try {
      const { data } = await axios.get(`${API}/api/marketing/dynamic-lists/${id}/members?page=1&page_size=20`, { headers });
      setMembers((prev) => ({ ...prev, [id]: data.members || [] }));
    } catch { /* noop */ }
  };

  const toggleExpand = (id) => {
    if (expandedId === id) {
      setExpandedId(null);
    } else {
      setExpandedId(id);
      if (!members[id]) loadMembers(id);
    }
  };

  return (
    <div className="space-y-5" data-testid="marketing-dynamic-lists-tab">
      {/* Iter 216h245 — H2 "Dynamic Lists" removed (redundant with the
          tab pill). The "What is a Dynamic List?" explainer box stays —
          it's onboarding content, not a sub-header. */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="flex-1 min-w-0">
          <div className="max-w-3xl rounded-xl border border-fuchsia-200/60 bg-fuchsia-50/40 px-4 py-3 text-[13px] leading-relaxed" style={{ color: 'var(--theme-text)' }} data-testid="dynamic-lists-explainer">
            <strong className="text-fuchsia-700">What is a Dynamic List?</strong>
            <span className="text-[var(--theme-text-muted)]"> A saved audience that <em>updates itself</em>. You write a rule once
            (e.g. <em>“members joined in the last 30 days who skipped a class”</em>) and the list re-evaluates
            every time a contact&apos;s data changes — no manual refresh, no stale exports. Use them as campaign
            audiences or journey entry conditions. Compare with a <em>Static list</em> (fixed snapshot, never updates).</span>
          </div>
        </div>
        <button
          onClick={() => setCreating((c) => !c)}
          className="px-3 py-2 rounded-md bg-[var(--color-brand-blue)] text-white text-sm font-semibold inline-flex items-center gap-1.5"
          data-testid="dynamic-list-new-btn"
        >
          <Plus size={13} /> {creating ? 'Cancel' : 'New dynamic list'}
        </button>
      </div>

      {/* Create form */}
      {creating && (
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-5 space-y-3" data-testid="dynamic-list-builder">
          <input
            value={draftName}
            onChange={(e) => setDraftName(e.target.value)}
            placeholder="List name"
            className="w-full px-3 py-2 border border-zinc-200 dark:border-zinc-800 rounded-md text-sm bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100"
            data-testid="dynamic-list-name-input"
          />
          <input
            value={draftDescription}
            onChange={(e) => setDraftDescription(e.target.value)}
            placeholder="Optional description"
            className="w-full px-3 py-2 border border-zinc-200 dark:border-zinc-800 rounded-md text-sm bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100"
            data-testid="dynamic-list-desc-input"
          />
          <div className="space-y-2">
            {draftConditions.map((c, i) => {
              const f = FIELDS.find((x) => x.id === c.field) || FIELDS[0];
              return (
                <div key={i} className="flex items-center gap-2" data-testid={`dynamic-list-condition-${i}`}>
                  <select value={c.field} onChange={(e) => updateCondition(i, { field: e.target.value })} className="px-2 py-1.5 border border-zinc-200 dark:border-zinc-800 rounded-md text-xs flex-1 bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100">
                    {FIELDS.map((fld) => <option key={fld.id} value={fld.id}>{fld.label}</option>)}
                  </select>
                  <select value={c.op} onChange={(e) => updateCondition(i, { op: e.target.value })} className="px-2 py-1.5 border border-zinc-200 dark:border-zinc-800 rounded-md text-xs w-16 bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100">
                    {OPS.map((op) => <option key={op.id} value={op.id}>{op.label}</option>)}
                  </select>
                  {f.type === 'enum' ? (
                    <select value={c.value} onChange={(e) => updateCondition(i, { value: e.target.value })} className="px-2 py-1.5 border border-zinc-200 dark:border-zinc-800 rounded-md text-xs flex-1 bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100">
                      {f.options.map((o) => <option key={o} value={o}>{o}</option>)}
                    </select>
                  ) : f.type === 'days_ago' ? (
                    <input type="text" value={c.value} onChange={(e) => updateCondition(i, { value: e.target.value })} placeholder="30d_ago" className="px-2 py-1.5 border border-zinc-200 dark:border-zinc-800 rounded-md text-xs flex-1 bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100" />
                  ) : (
                    <input type="number" value={c.value} onChange={(e) => updateCondition(i, { value: parseFloat(e.target.value) || 0 })} className="px-2 py-1.5 border border-zinc-200 dark:border-zinc-800 rounded-md text-xs flex-1 bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100" />
                  )}
                  <button onClick={() => removeCondition(i)} className="p-1 text-zinc-400 dark:text-zinc-500 hover:text-red-500"><Trash2 size={13} /></button>
                </div>
              );
            })}
            <button onClick={addCondition} className="inline-flex items-center gap-1 text-xs text-[var(--color-brand-blue)] font-semibold mt-1" data-testid="dynamic-list-add-condition">
              <Plus size={12} /> Add condition
            </button>
          </div>
          <div className="flex items-center justify-between flex-wrap gap-2 mt-3 pt-3 border-t border-zinc-200 dark:border-zinc-800">
            <label className="text-xs inline-flex items-center gap-1.5" style={{ color: 'var(--theme-text-muted)' }}>
              <Clock size={12} /> Refresh:
              <select
                value={draftInterval}
                onChange={(e) => setDraftInterval(parseInt(e.target.value, 10))}
                className="px-2 py-1 border border-zinc-200 dark:border-zinc-800 rounded text-xs bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100"
                data-testid="dynamic-list-interval"
              >
                {REFRESH_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </label>
            <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>
              <Sparkles size={12} className="inline text-amber-500 mr-1" />
              <span className="font-bold" style={{ color: 'var(--theme-text)' }}>{draftPreviewSize.toLocaleString()}</span> contacts will match
            </p>
            <button
              onClick={save}
              disabled={busy || !draftName.trim()}
              className="px-3 py-1.5 rounded-md bg-[var(--color-brand-blue)] text-white text-xs font-semibold disabled:opacity-50 inline-flex items-center gap-1"
              data-testid="dynamic-list-save"
            >
              {busy ? <Loader2 size={11} className="animate-spin" /> : <Save size={11} />} Save
            </button>
          </div>
        </div>
      )}

      {/* Lists */}
      {loading ? (
        <div className="text-center py-12">
          <Loader2 size={32} className="animate-spin text-[var(--color-brand-blue)] mx-auto" />
        </div>
      ) : lists.length === 0 ? (
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-10 text-center" data-testid="dynamic-list-empty">
          <ListChecks size={36} className="mx-auto text-zinc-300 dark:text-zinc-600 mb-3" />
          <p className="text-sm font-medium" style={{ color: 'var(--theme-text)' }}>No dynamic lists yet</p>
          <p className="text-xs mt-1" style={{ color: 'var(--theme-text-muted)' }}>Create one to auto-refresh a segment as your contacts change.</p>
        </div>
      ) : (
        <div className="space-y-2" data-testid="dynamic-list-rows">
          {lists.map((l) => {
            const expanded = expandedId === l.id;
            return (
              <div key={l.id} className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900" data-testid={`dynamic-list-row-${l.id}`}>
                <div className="p-4 flex items-center gap-3 flex-wrap">
                  <button onClick={() => toggleExpand(l.id)} className="text-zinc-500 dark:text-zinc-400 hover:text-zinc-800 dark:hover:text-zinc-200" aria-label="Toggle">
                    {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                  </button>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 truncate">{l.name}</p>
                    {l.description && (
                      <p className="text-[11px] text-zinc-500 dark:text-zinc-400 truncate">{l.description}</p>
                    )}
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-bold tabular-nums text-zinc-900 dark:text-zinc-100" data-testid={`dynamic-list-count-${l.id}`}>{(l.member_count || 0).toLocaleString()}</p>
                    <p className="text-[10px] text-zinc-400 dark:text-zinc-500">contacts</p>
                  </div>
                  <div className="text-right text-[10px]" style={{ color: 'var(--theme-text-muted)' }}>
                    Refreshed {formatRelative(l.last_evaluated_at)}<br />
                    every {l.refresh_interval_minutes}m
                  </div>
                  <button
                    onClick={() => refreshOne(l.id)}
                    disabled={busy}
                    className="p-2 rounded hover:bg-zinc-100 dark:bg-zinc-800 dark:hover:bg-zinc-800 text-zinc-500 dark:text-zinc-400"
                    data-testid={`dynamic-list-refresh-${l.id}`}
                    title="Refresh now"
                  >
                    <RefreshCw size={13} />
                  </button>
                  <button
                    onClick={() => remove(l.id)}
                    className="p-2 rounded hover:bg-rose-50 dark:hover:bg-rose-950/40 text-rose-500"
                    data-testid={`dynamic-list-delete-${l.id}`}
                    title="Delete"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
                {expanded && (
                  <div className="border-t border-zinc-200 dark:border-zinc-800 p-4 bg-zinc-50/50 dark:bg-zinc-950/40" data-testid={`dynamic-list-members-${l.id}`}>
                    <p className="text-[10px] uppercase tracking-wider font-semibold mb-2" style={{ color: 'var(--theme-text-muted)' }}>
                      First {(members[l.id] || []).length} of {(l.member_count || 0).toLocaleString()} members
                    </p>
                    {(members[l.id] || []).length === 0 ? (
                      <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>No members match this list yet.</p>
                    ) : (
                      <div className="space-y-1">
                        {(members[l.id] || []).map((m) => (
                          <div key={m.id} className="flex items-center justify-between text-xs py-1">
                            <span className="text-zinc-800 dark:text-zinc-200">{m.first_name} {m.last_name}</span>
                            <span className="text-zinc-500 dark:text-zinc-400">{m.email}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default DynamicListsTab;
