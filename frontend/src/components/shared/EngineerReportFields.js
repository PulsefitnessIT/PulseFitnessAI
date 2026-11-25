import { useEffect, useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';

const pad = (n) => String(n).padStart(2, '0');
export const toLocalInput = (iso) => {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
};
const fromLocalInput = (v) => (v ? new Date(v).toISOString() : '');

// Fills the auto times (from the job's timers) when the engineer hasn't edited them.
export function withReportDefaults(report, defaultStart, defaultEnd) {
  const r = report || {};
  return {
    ...r,
    start_time: r.start_time !== undefined ? r.start_time : (defaultStart || ''),
    end_time: r.end_time !== undefined ? r.end_time : (defaultEnd || new Date().toISOString()),
    further_parts_required: (r.further_parts_required || []).filter((p) => (p.name || '').trim()),
  };
}

export function reportTimeError(r) {
  if (r.start_time && r.end_time && new Date(r.end_time) <= new Date(r.start_time)) return 'End time must be after the start time';
  return '';
}

const inputCls = 'w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white dark:bg-zinc-900 dark:border-zinc-800';
const labelCls = 'text-[11px] uppercase font-bold tracking-wide text-slate-500 mb-1 block';

function PartRow({ part, idx, onChange, onRemove, onSearch }) {
  const [hits, setHits] = useState([]);
  useEffect(() => {
    if (!onSearch || (part.name || '').length < 2 || part.sku) { setHits([]); return undefined; }
    const tm = setTimeout(() => onSearch(part.name).then(setHits).catch(() => setHits([])), 250);
    return () => clearTimeout(tm);
  }, [part.name, part.sku, onSearch]);
  return (
    <div className="relative flex gap-2 items-start" data-testid={`report-part-row-${idx}`}>
      <input className={`${inputCls} flex-1 min-w-0`} placeholder="Part name or number" value={part.name || ''}
        onChange={(e) => onChange({ name: e.target.value, sku: '', part_id: null })} data-testid={`report-part-name-${idx}`} />
      <input type="number" min="1" className="w-20 shrink-0 text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white dark:bg-zinc-900 dark:border-zinc-800" value={part.qty || 1}
        onChange={(e) => onChange({ qty: Math.max(1, parseInt(e.target.value, 10) || 1) })} data-testid={`report-part-qty-${idx}`} aria-label="Quantity" />
      <button type="button" onClick={onRemove} className="p-2 text-slate-400 hover:text-red-600" data-testid={`report-part-remove-${idx}`} aria-label="Remove part"><Trash2 size={16} /></button>
      {hits.length > 0 && (
        <div className="absolute z-20 top-full left-0 right-24 mt-1 bg-white border border-slate-200 rounded-lg shadow-lg max-h-48 overflow-auto dark:bg-zinc-900 dark:border-zinc-800" data-testid={`report-part-suggestions-${idx}`}>
          {hits.map((h) => (
            <button key={h.id || h.sku} type="button" className="w-full text-left px-3 py-2 text-sm hover:bg-slate-50 dark:bg-zinc-900"
              onClick={() => { onChange({ name: h.name || h.description || h.sku, sku: h.sku || '', part_id: h.id || null }); setHits([]); }}>
              <span className="font-semibold">{h.name || h.description}</span>{h.sku ? <span className="text-slate-400"> · {h.sku}</span> : null}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function EngineerReportFields({ value, onChange, defaultStart, defaultEnd, showWork = false, onPartSearch }) {
  const r = withReportDefaults(value, defaultStart, defaultEnd);
  const parts = (value?.further_parts_required) || [];
  const setParts = (next) => onChange({ further_parts_required: next });
  return (
    <div className="bg-white rounded-2xl border border-slate-200 p-4 space-y-3 dark:bg-zinc-900 dark:border-zinc-800" data-testid="engineer-report-fields">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <label className="block"><span className={labelCls}>Start time *</span>
          <input type="datetime-local" className={inputCls} value={toLocalInput(r.start_time)} onChange={(e) => onChange({ start_time: fromLocalInput(e.target.value) })} data-testid="report-start-time" />
        </label>
        <label className="block"><span className={labelCls}>End time *</span>
          <input type="datetime-local" className={inputCls} value={toLocalInput(r.end_time)} onChange={(e) => onChange({ end_time: fromLocalInput(e.target.value) })} data-testid="report-end-time" />
        </label>
      </div>
      {reportTimeError(r) && <p className="text-xs text-red-600" data-testid="report-time-error">{reportTimeError(r)}</p>}
      {showWork && (
        <label className="block"><span className={labelCls}>Description of Work Completed *</span>
          <textarea rows={4} className={inputCls} value={value?.work_completed || ''} onChange={(e) => onChange({ work_completed: e.target.value })} data-testid="report-work-completed" />
        </label>
      )}
      <label className="block"><span className={labelCls}>Further Work Required</span>
        <textarea rows={3} className={inputCls} placeholder="Leave blank if none" value={value?.further_work_required || ''} onChange={(e) => onChange({ further_work_required: e.target.value })} data-testid="report-further-work" />
      </label>
      <div>
        <span className={labelCls}>Further Parts Required</span>
        <div className="space-y-2">
          {parts.map((p, i) => (
            <PartRow key={i} idx={i} part={p} onSearch={onPartSearch}
              onChange={(patch) => setParts(parts.map((x, j) => (j === i ? { ...x, ...patch } : x)))}
              onRemove={() => setParts(parts.filter((_, j) => j !== i))} />
          ))}
        </div>
        <button type="button" onClick={() => setParts([...parts, { name: '', qty: 1 }])}
          className="mt-2 inline-flex items-center gap-1 text-sm font-semibold text-[#0091CA]" data-testid="report-add-part">
          <Plus size={14} /> Add part
        </button>
      </div>
    </div>
  );
}

export default EngineerReportFields;
