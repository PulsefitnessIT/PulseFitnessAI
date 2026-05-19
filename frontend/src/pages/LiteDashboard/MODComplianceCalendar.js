/**
 * MOD Compliance Calendar (HQ only).
 *
 * Iter 216h116 — opened from the All-Sites leaderboard via a top
 * "Compliance" button. Shows the entire estate's upcoming expiries
 * with severity colouring and lets HQ add / edit / delete events.
 */
import { useEffect, useState } from 'react';
import axios from 'axios';
import { X, Calendar, AlertTriangle, Loader2, Plus, Trash2, ExternalLink } from 'lucide-react';

const BUCKET_COLORS = {
  overdue:  '#dc2626', // red-600
  critical: '#f97316', // orange-500
  warning:  '#f59e0b', // amber-500
  soon:     '#3b82f6', // blue-500
  ok:       '#10b981', // emerald-500
  unknown:  '#6b7280', // slate-500
};

const BUCKET_LABEL = {
  overdue: 'Overdue',
  critical: '≤ 7 days',
  warning:  '≤ 14 days',
  soon:     '≤ 30 days',
  ok:       '> 30 days',
  unknown:  'No date',
};

export default function MODComplianceCalendar({ sites, API, onClose }) {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : '';
  const headers = { Authorization: `Bearer ${token}` };
  const [events, setEvents] = useState([]);
  const [kinds, setKinds] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ site_id: '', kind: 'insurance', title: '', due_date: '', notes: '', doc_url: '' });
  const [submitting, setSubmitting] = useState(false);

  const load = () => {
    setLoading(true);
    axios.get(`${API}/mod/pro/compliance`, { headers })
      .then((r) => { setEvents(r.data.events || []); setKinds(r.data.kinds || {}); })
      .catch((e) => setError(e?.response?.data?.detail || 'Could not load compliance calendar'))
      .finally(() => setLoading(false));
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps -- todo: review missing dep(s) 'load'; pre-existing as of iter 216h226-polish-5.
  useEffect(() => { load();   }, []);

  const submit = async () => {
    if (!form.site_id || !form.title || !form.due_date) {
      setError('Site, title and due date are required.');
      return;
    }
    setSubmitting(true);
    try {
      await axios.post(`${API}/mod/pro/compliance`, form, { headers });
      setShowForm(false);
      setForm({ site_id: '', kind: 'insurance', title: '', due_date: '', notes: '', doc_url: '' });
      load();
    } catch (e) {
      setError(e?.response?.data?.detail || 'Could not create event');
    } finally {
      setSubmitting(false);
    }
  };

  const remove = async (id) => {
    if (!window.confirm('Delete this compliance event?')) return;
    try {
      await axios.delete(`${API}/mod/pro/compliance/${id}`, { headers });
      load();
    } catch (e) {
      setError(e?.response?.data?.detail || 'Could not delete event');
    }
  };

  const buckets = ['overdue', 'critical', 'warning', 'soon', 'ok'];
  const grouped = buckets.map((b) => ({ bucket: b, items: events.filter((e) => e.status === b) }));

  return (
    <div className="fixed inset-0 z-50 grid place-items-end sm:place-items-center bg-black/70 p-0 sm:p-4" data-testid="mod-compliance-panel">
      <div className="w-full max-w-4xl h-full sm:h-auto sm:max-h-[90vh] rounded-none sm:rounded-2xl overflow-hidden flex flex-col" style={{ background: 'var(--theme-surface)', border: '1px solid var(--theme-border)' }}>
        <header className="px-5 py-4 border-b flex items-start justify-between gap-3" style={{ borderColor: 'var(--theme-border-soft)' }}>
          <div className="flex-1 min-w-0">
            <div className="text-[10px] font-extrabold uppercase tracking-[0.3em]" style={{ color: 'var(--color-brand-cyan-hover)' }}>
              Pulse Fitness · MOD Service · Compliance calendar
            </div>
            <h3 className="text-base font-extrabold tracking-tight mt-1 flex items-center gap-2" style={{ color: 'var(--theme-text)' }} data-testid="mod-compliance-title">
              <Calendar size={16} /> {events.length} event{events.length === 1 ? '' : 's'} across {sites?.filter((s) => s.is_mod_child).length || 0} sites
            </h3>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setShowForm((s) => !s)}
              className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-bold border hover:bg-[var(--theme-hover-bg)]"
              style={{ borderColor: 'var(--theme-border)', color: 'var(--color-brand-cyan-hover)' }}
              data-testid="mod-compliance-add-btn"
            >
              <Plus size={12} /> Add event
            </button>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="p-1.5 rounded-full hover:bg-[var(--theme-hover-bg)]"
              data-testid="mod-compliance-close"
            >
              <X size={16} style={{ color: 'var(--theme-text-muted)' }} />
            </button>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {showForm && (
            <div className="rounded-lg border p-4 space-y-3" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface-2)' }} data-testid="mod-compliance-form">
              <div className="grid grid-cols-2 gap-3">
                <FormField label="Site">
                  <select
                    value={form.site_id}
                    onChange={(e) => setForm({ ...form, site_id: e.target.value })}
                    className="w-full bg-transparent border rounded-md px-2 py-1.5 text-sm"
                    style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
                    data-testid="mod-compliance-form-site"
                  >
                    <option value="">— Choose a site —</option>
                    {(sites || []).filter((s) => s.is_mod_child).map((s) => (
                      <option key={s.id} value={s.id}>{s.name}</option>
                    ))}
                  </select>
                </FormField>
                <FormField label="Type">
                  <select
                    value={form.kind}
                    onChange={(e) => setForm({ ...form, kind: e.target.value })}
                    className="w-full bg-transparent border rounded-md px-2 py-1.5 text-sm"
                    style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
                    data-testid="mod-compliance-form-kind"
                  >
                    {Object.entries(kinds).map(([k, v]) => (
                      <option key={k} value={k}>{v}</option>
                    ))}
                  </select>
                </FormField>
                <FormField label="Title">
                  <input
                    type="text"
                    value={form.title}
                    onChange={(e) => setForm({ ...form, title: e.target.value })}
                    className="w-full bg-transparent border rounded-md px-2 py-1.5 text-sm"
                    style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
                    data-testid="mod-compliance-form-title"
                  />
                </FormField>
                <FormField label="Due date">
                  <input
                    type="date"
                    value={form.due_date}
                    onChange={(e) => setForm({ ...form, due_date: e.target.value })}
                    className="w-full bg-transparent border rounded-md px-2 py-1.5 text-sm"
                    style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
                    data-testid="mod-compliance-form-due"
                  />
                </FormField>
                <FormField label="Notes" full>
                  <input
                    type="text"
                    value={form.notes}
                    onChange={(e) => setForm({ ...form, notes: e.target.value })}
                    className="w-full bg-transparent border rounded-md px-2 py-1.5 text-sm"
                    style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
                  />
                </FormField>
                <FormField label="Evidence URL (optional)" full>
                  <input
                    type="url"
                    value={form.doc_url}
                    onChange={(e) => setForm({ ...form, doc_url: e.target.value })}
                    className="w-full bg-transparent border rounded-md px-2 py-1.5 text-sm"
                    style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
                  />
                </FormField>
              </div>
              <div className="flex justify-end gap-2">
                <button onClick={() => setShowForm(false)} className="px-3 py-1.5 text-xs font-bold rounded-md" style={{ color: 'var(--theme-text-muted)' }}>Cancel</button>
                <button
                  onClick={submit}
                  disabled={submitting}
                  className="px-3 py-1.5 text-xs font-extrabold uppercase tracking-wider rounded-md text-white disabled:opacity-50"
                  style={{ background: 'var(--color-brand-cyan-hover)' }}
                  data-testid="mod-compliance-form-submit"
                >
                  {submitting ? <Loader2 size={12} className="animate-spin" /> : 'Save event'}
                </button>
              </div>
            </div>
          )}

          {loading && (
            <div className="flex items-center gap-2 text-sm py-10 justify-center" style={{ color: 'var(--theme-text-muted)' }}>
              <Loader2 size={14} className="animate-spin" /> Loading…
            </div>
          )}
          {error && (
            <div className="flex items-start gap-2 p-3 rounded-md text-sm text-rose-500" data-testid="mod-compliance-error">
              <AlertTriangle size={16} className="mt-0.5 shrink-0" /> {error}
            </div>
          )}

          {!loading && events.length === 0 && (
            <p className="text-sm py-10 text-center" style={{ color: 'var(--theme-text-muted)' }} data-testid="mod-compliance-empty">
              No compliance events yet. Click "Add event" to record an insurance renewal,
              PAT-test date, fixed-wiring inspection or load-test cert.
            </p>
          )}

          {!loading && grouped.map(({ bucket, items }) => items.length > 0 && (
            <section key={bucket} data-testid={`mod-compliance-bucket-${bucket}`}>
              <div className="flex items-center gap-2 mb-2">
                <span
                  className="inline-block w-2 h-2 rounded-full"
                  style={{ background: BUCKET_COLORS[bucket] }}
                />
                <h4 className="text-[11px] font-extrabold uppercase tracking-wider" style={{ color: 'var(--theme-text)' }}>
                  {BUCKET_LABEL[bucket]} · {items.length}
                </h4>
              </div>
              <ul className="space-y-1.5">
                {items.map((e) => (
                  <li
                    key={e.id}
                    className="rounded-lg border px-3 py-2.5 flex items-center justify-between gap-3"
                    style={{ background: 'var(--theme-surface-2)', borderColor: 'var(--theme-border)' }}
                    data-testid={`mod-compliance-row-${e.id}`}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-bold truncate" style={{ color: 'var(--theme-text)' }}>
                        {e.title}
                      </div>
                      <div className="text-[11px] truncate" style={{ color: 'var(--theme-text-muted)' }}>
                        {e.site_name} · {e.kind_label} · due {e.due_date}
                        {e.days_until !== null && (
                          <span style={{ color: BUCKET_COLORS[e.status], marginLeft: 6, fontWeight: 700 }}>
                            ({e.days_until >= 0 ? `+${e.days_until}` : e.days_until}d)
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      {e.doc_url && (
                        <a
                          href={e.doc_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="p-1.5 rounded hover:bg-[var(--theme-hover-bg)]"
                          title="Open evidence"
                          data-testid={`mod-compliance-doc-${e.id}`}
                        >
                          <ExternalLink size={12} style={{ color: 'var(--theme-text-muted)' }} />
                        </a>
                      )}
                      <button
                        type="button"
                        onClick={() => remove(e.id)}
                        className="p-1.5 rounded hover:bg-rose-500/10"
                        title="Delete"
                        data-testid={`mod-compliance-delete-${e.id}`}
                      >
                        <Trash2 size={12} className="text-rose-500" />
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}

function FormField({ label, children, full = false }) {
  return (
    <div className={full ? 'col-span-2' : ''}>
      <label className="block text-[10px] font-extrabold uppercase tracking-wider mb-1" style={{ color: 'var(--theme-text-muted)' }}>
        {label}
      </label>
      {children}
    </div>
  );
}
