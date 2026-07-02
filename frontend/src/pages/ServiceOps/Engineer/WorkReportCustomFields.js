/**
 * WorkReportCustomFields — Iter 220
 *
 * Inline widget that renders the engineer-configurable custom fields
 * applicable to a particular case. Used inside the Complete tab of
 * `EngineerJobDetailV2`. Provides:
 *   • Dynamic input rendering per field type (text/number/dropdown/
 *     checkbox/date/file)
 *   • Required-field UI hint
 *   • "+ New field" inline editor so engineers can self-serve creation
 *     from the job itself without leaving the screen.
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Plus, Loader2, Sliders } from 'lucide-react';
import { notify } from '@/components/notifications';
import { FieldEditor } from './EngineerWorkReportFields';
import AssetReadingSparkline from './AssetReadingSparkline';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
});

export default function WorkReportCustomFields({ caseId, values, onChange }) {
  const [fields, setFields] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  // Iter 220a — last reading per field, surfaced as a subtle hint AND
  // used to seed the parent state for any field the engineer hasn't
  // touched yet.
  const [lastValues, setLastValues] = useState({});
  const [lastValuesMeta, setLastValuesMeta] = useState({});
  // Iter 220b — per-field history series for sparkline rendering.
  const [history, setHistory] = useState({});

  const load = useCallback(async () => {
    if (!caseId) { setLoading(false); return; }
    setLoading(true);
    try {
      const r = await axios.get(`${API}/svc/work-report-fields/for-case/${caseId}`, auth());
      const defs = r.data?.fields || [];
      setFields(defs);
      const stored = r.data?.values || {};
      const lastV = r.data?.last_values || {};
      const lastMeta = r.data?.last_values_meta || {};
      setLastValues(lastV);
      setLastValuesMeta(lastMeta);
      const seed = { ...lastV, ...stored };
      if (Object.keys(seed).length) {
        onChange?.((prev) => ({ ...seed, ...(prev || {}) }));
      }
      // Fetch trend history in parallel — non-blocking, fallback to {}.
      try {
        const h = await axios.get(`${API}/svc/work-report-fields/history/${caseId}`, auth());
        setHistory(h.data?.series || {});
      } catch (he) {
        console.warn('[work-report-fields] history failed', he);
        setHistory({});
      }
    } catch (e) {
      console.warn('[work-report-fields] load failed', e);
      setFields([]);
    } finally {
      setLoading(false);
    }
  }, [caseId, onChange]);

  useEffect(() => { load(); }, [load]);

  const setValue = (key, v) => {
    onChange?.((prev) => ({ ...(prev || {}), [key]: v }));
  };

  const uploadFile = async (key, file) => {
    if (!file) return;
    try {
      const form = new FormData();
      form.append('file', file);
      const r = await axios.post(`${API}/files/upload?category=work-report-fields`, form, {
        ...auth(),
        headers: { ...auth().headers, 'Content-Type': 'multipart/form-data' },
      });
      setValue(key, {
        storage_path: r.data?.storage_path || r.data?.url || '',
        original_filename: file.name,
        content_type: file.type || '',
      });
      notify.success('File attached');
    } catch (e) {
      notify.error('Upload failed', e?.response?.data?.detail || e?.message);
    }
  };

  if (loading) {
    return (
      <div className="bg-white rounded-2xl border border-slate-200 p-4 flex items-center justify-center text-slate-400" data-testid="wrf-loading">
        <Loader2 size={14} className="animate-spin mr-2" /> Loading custom fields…
      </div>
    );
  }

  return (
    <div className="bg-white rounded-2xl border border-slate-200 p-4 space-y-3" data-testid="wrf-widget">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Sliders size={14} className="text-cyan-600" />
          <p className="text-[11px] uppercase font-bold tracking-wide text-slate-500">
            Machine readings &amp; details
          </p>
        </div>
        <button
          type="button"
          onClick={() => setCreating(true)}
          className="inline-flex items-center gap-1 text-xs font-bold text-cyan-700 hover:underline"
          data-testid="wrf-widget-new-btn"
        >
          <Plus size={12} /> New field
        </button>
      </div>

      {creating && (
        <FieldEditor
          mode="create"
          onCancel={() => setCreating(false)}
          onSaved={() => { setCreating(false); load(); }}
        />
      )}

      {fields.length === 0 ? (
        <p className="text-xs text-slate-400 italic" data-testid="wrf-widget-empty">
          No custom fields for this machine yet — tap "New field" to add one
          (e.g. "Current Software" or "Drag Factor").
        </p>
      ) : (
        <div className="space-y-3">
          {fields.map((f) => (
            <div key={f.id} data-testid={`wrf-field-${f.key}`}>
              <label className="flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-slate-600">
                {f.name}
                {f.required && <span className="text-rose-500">*</span>}
              </label>
              {f.field_type === 'text' && (
                <input
                  value={(values || {})[f.key] || ''}
                  onChange={(e) => setValue(f.key, e.target.value)}
                  className="w-full mt-1 text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white"
                  placeholder={f.help_text || ''}
                  data-testid={`wrf-input-${f.key}`}
                />
              )}
              {f.field_type === 'number' && (
                <input
                  type="number"
                  value={(values || {})[f.key] ?? ''}
                  onChange={(e) => setValue(f.key, e.target.value)}
                  className="w-full mt-1 text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white"
                  placeholder={f.help_text || ''}
                  data-testid={`wrf-input-${f.key}`}
                />
              )}
              {f.field_type === 'date' && (
                <input
                  type="date"
                  value={(values || {})[f.key] || ''}
                  onChange={(e) => setValue(f.key, e.target.value)}
                  className="w-full mt-1 text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white"
                  data-testid={`wrf-input-${f.key}`}
                />
              )}
              {f.field_type === 'dropdown' && (
                <select
                  value={(values || {})[f.key] || ''}
                  onChange={(e) => setValue(f.key, e.target.value)}
                  className="w-full mt-1 text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white"
                  data-testid={`wrf-input-${f.key}`}
                >
                  <option value="">— select —</option>
                  {(f.options || []).map(o => <option key={o} value={o}>{o}</option>)}
                </select>
              )}
              {f.field_type === 'checkbox' && (
                <label className="flex items-center gap-2 mt-1 text-sm text-slate-700 select-none">
                  <input
                    type="checkbox"
                    checked={!!(values || {})[f.key]}
                    onChange={(e) => setValue(f.key, e.target.checked)}
                    data-testid={`wrf-input-${f.key}`}
                  />
                  {f.help_text || 'Yes'}
                </label>
              )}
              {f.field_type === 'file' && (
                <div className="mt-1 flex items-center gap-2">
                  <input
                    type="file"
                    onChange={(e) => uploadFile(f.key, e.target.files?.[0])}
                    className="text-xs"
                    data-testid={`wrf-input-${f.key}`}
                  />
                  {((values || {})[f.key]?.original_filename) && (
                    <span className="text-xs text-emerald-700 truncate" data-testid={`wrf-file-name-${f.key}`}>
                      {(values || {})[f.key].original_filename}
                    </span>
                  )}
                </div>
              )}
              {f.help_text && f.field_type !== 'checkbox' && (
                <p className="text-[10px] text-slate-400 mt-1">{f.help_text}</p>
              )}
              {(() => {
                // Iter 220b — sparkline below numeric / checkbox fields
                // when the asset has ≥2 prior readings. Suppressed for
                // text / date / dropdown / file since they don't trend.
                if (!['number', 'checkbox'].includes(f.field_type)) return null;
                const series = history[f.key];
                if (!series || series.length < 2) return null;
                return (
                  <AssetReadingSparkline
                    points={series}
                    currentValue={(values || {})[f.key]}
                    testid={`wrf-sparkline-${f.key}`}
                  />
                );
              })()}
              {(() => {
                // Iter 220a — last-reading hint surfaces the value the
                // engineer captured on the previous visit. Suppressed
                // for file fields (the path isn't useful as a hint).
                const lv = lastValues[f.key];
                if (lv === undefined || lv === null || lv === '') return null;
                if (f.field_type === 'file') return null;
                const meta = lastValuesMeta[f.key] || {};
                const display = f.field_type === 'checkbox'
                  ? (lv ? 'Yes' : 'No')
                  : String(lv);
                let when = '';
                if (meta.captured_at) {
                  try {
                    const d = new Date(meta.captured_at);
                    if (!Number.isNaN(d.getTime())) {
                      when = ` · ${d.toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' })}`;
                    }
                  } catch { /* ignore */ }
                }
                const refStr = meta.case_reference ? ` (${meta.case_reference})` : '';
                const current = (values || {})[f.key];
                const matches = current !== undefined
                  && current !== null
                  && current !== ''
                  && String(current) === String(lv);
                return (
                  <p
                    className={`text-[10px] mt-1 ${matches ? 'text-emerald-600' : 'text-cyan-600'}`}
                    data-testid={`wrf-lastreading-${f.key}`}
                  >
                    {matches ? '✓ ' : '↺ '}
                    Last reading: <span className="font-bold">{display}</span>{when}{refStr}
                  </p>
                );
              })()}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
