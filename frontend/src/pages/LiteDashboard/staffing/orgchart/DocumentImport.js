/** Org Chart — import an EXISTING chart (PDF / image) and convert to editable rows.
 *
 * Uploads to the async backend job, polls until extraction is done, then shows
 * the people in an EDITABLE table so the user can fix any OCR slips before the
 * rows become real (editable) cards on the chart. */
import { useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import {
  FileScan, UploadCloud, Loader2, CheckCircle2, Sparkles, Trash2, Plus, X,
} from 'lucide-react';
import { ocApi } from './api';

const inputCls = 'w-full px-2 py-1.5 rounded-md text-xs border outline-none';
const inputStyle = { background: 'var(--theme-bg,#fff)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' };

export default function DocumentImport({ chartId, onImported }) {
  const [phase, setPhase] = useState('idle'); // idle | working | review | done | error
  const [rows, setRows] = useState([]);
  const [source, setSource] = useState(null);
  const [errMsg, setErrMsg] = useState('');
  const [applyBusy, setApplyBusy] = useState(false);
  const pollRef = useRef(null);

  useEffect(() => () => clearInterval(pollRef.current), []);

  const fail = (msg) => { clearInterval(pollRef.current); setErrMsg(msg); setPhase('error'); toast.error(msg); };

  const upload = async (file) => {
    setPhase('working'); setRows([]); setErrMsg('');
    try {
      const { job_id } = await ocApi.importDocument(chartId, file);
      pollRef.current = setInterval(async () => {
        try {
          const s = await ocApi.importJobStatus(chartId, job_id);
          if (s.status === 'done') {
            clearInterval(pollRef.current);
            setRows(s.rows || []); setSource(s.source);
            setPhase('review');
            if (!s.rows?.length) toast('No people could be read — try a clearer file');
          } else if (s.status === 'error') {
            fail(s.error || 'Could not read that chart');
          }
        } catch { /* transient — keep polling */ }
      }, 3000);
    } catch (e) {
      fail(e?.response?.data?.detail || 'Upload failed — please try again');
    }
  };

  const setCell = (i, k, v) => setRows((rs) => rs.map((r, idx) => (idx === i ? { ...r, [k]: v } : r)));
  const removeRow = (i) => setRows((rs) => rs.filter((_, idx) => idx !== i));

  const apply = async () => {
    setApplyBusy(true);
    try {
      const clean = rows.filter((r) => (r.full_name || '').trim());
      const res = await ocApi.importApplyRows(chartId, clean, { link_existing: true });
      toast.success(`Added ${res.imported} cards — they're now fully editable on the chart`);
      setPhase('done'); onImported?.();
    } catch { toast.error('Could not add cards'); } finally { setApplyBusy(false); }
  };

  const reset = () => { setPhase('idle'); setRows([]); setSource(null); setErrMsg(''); };

  return (
    <div className="rounded-2xl border p-4" style={{ borderColor: 'var(--theme-border)' }} data-testid="orgchart-doc-import">
      <h4 className="text-sm font-bold mb-1 inline-flex items-center gap-2" style={{ color: 'var(--theme-text)' }}><FileScan size={15} /> Import an existing org chart</h4>
      <p className="text-[11px] mb-3" style={{ color: 'var(--theme-text-muted)' }}>Upload a PDF, PNG or JPG of an existing chart. We extract the people, titles and reporting lines so you can review, fix and turn them into editable cards.</p>

      {phase === 'idle' && (
        <label className="block rounded-xl border-2 border-dashed p-8 text-center cursor-pointer" style={{ borderColor: 'var(--theme-border)' }} data-testid="orgchart-doc-drop">
          <UploadCloud size={26} className="mx-auto mb-2" style={{ color: 'var(--theme-text-muted)' }} />
          <p className="text-sm font-semibold" style={{ color: 'var(--theme-text)' }}>Choose a chart file</p>
          <p className="text-[11px] mt-1" style={{ color: 'var(--theme-text-muted)' }}>PDF, PNG or JPG · up to 25MB</p>
          <input type="file" accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/*" className="hidden" onChange={(e) => e.target.files[0] && upload(e.target.files[0])} data-testid="orgchart-doc-file" />
        </label>
      )}

      {phase === 'working' && (
        <div className="rounded-xl border p-8 text-center" style={{ borderColor: 'var(--theme-border)' }} data-testid="orgchart-doc-working">
          <Loader2 size={24} className="mx-auto mb-2 animate-spin" style={{ color: 'var(--color-brand-cyan)' }} />
          <p className="text-sm font-semibold" style={{ color: 'var(--theme-text)' }}>Reading your chart…</p>
          <p className="text-[11px] mt-1" style={{ color: 'var(--theme-text-muted)' }}>Large or image-based charts can take up to a minute.</p>
        </div>
      )}

      {phase === 'review' && (
        <div data-testid="orgchart-doc-review">
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>
              <Sparkles size={12} className="inline mr-1" style={{ color: 'var(--color-brand-cyan)' }} />
              Found <b style={{ color: 'var(--theme-text)' }}>{rows.length}</b> people {source === 'text' ? '(from the file’s text)' : '(read from the image)'}. Edit anything below, then add to the chart.
            </p>
            <button onClick={reset} className="text-xs" style={{ color: 'var(--theme-text-muted)' }} data-testid="orgchart-doc-cancel"><X size={14} /></button>
          </div>
          <div className="rounded-xl border overflow-auto max-h-[50vh]" style={{ borderColor: 'var(--theme-border)' }}>
            <table className="w-full text-xs">
              <thead className="sticky top-0" style={{ background: 'var(--theme-surface,#fff)' }}>
                <tr style={{ color: 'var(--theme-text-muted)' }}>{['Name', 'Job title', 'Department', 'Reports to', ''].map((h) => <th key={h} className="px-2 py-1.5 text-left font-bold">{h}</th>)}</tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i} className="border-t" style={{ borderColor: 'var(--theme-border)' }} data-testid={`orgchart-doc-row-${i}`}>
                    <td className="px-1.5 py-1"><input className={inputCls} style={inputStyle} value={r.full_name || ''} onChange={(e) => setCell(i, 'full_name', e.target.value)} /></td>
                    <td className="px-1.5 py-1"><input className={inputCls} style={inputStyle} value={r.job_title || ''} onChange={(e) => setCell(i, 'job_title', e.target.value)} /></td>
                    <td className="px-1.5 py-1"><input className={inputCls} style={inputStyle} value={r.department || ''} onChange={(e) => setCell(i, 'department', e.target.value)} /></td>
                    <td className="px-1.5 py-1"><input className={inputCls} style={inputStyle} value={r.manager_name || ''} onChange={(e) => setCell(i, 'manager_name', e.target.value)} /></td>
                    <td className="px-1.5 py-1 text-center"><button onClick={() => removeRow(i)}><Trash2 size={12} style={{ color: '#dc2626' }} /></button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex gap-2 mt-3">
            <button onClick={apply} disabled={applyBusy || !rows.length} className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-bold disabled:opacity-50" style={{ background: '#16a34a', color: '#fff' }} data-testid="orgchart-doc-apply">
              {applyBusy ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />} Add {rows.length} cards
            </button>
            <button onClick={reset} className="px-4 py-2 rounded-lg text-xs font-semibold" style={{ color: 'var(--theme-text-muted)' }}>Cancel</button>
          </div>
        </div>
      )}

      {phase === 'done' && (
        <div className="text-center py-6" data-testid="orgchart-doc-done">
          <CheckCircle2 size={26} className="mx-auto mb-2" style={{ color: '#16a34a' }} />
          <p className="text-sm font-semibold" style={{ color: 'var(--theme-text)' }}>Imported — open the Org Chart tab and run Auto-layout to tidy it.</p>
          <button onClick={reset} className="mt-3 px-4 py-2 rounded-lg text-xs font-bold" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}>Import another</button>
        </div>
      )}

      {phase === 'error' && (
        <div className="rounded-xl border p-6 text-center" style={{ borderColor: '#fca5a5', background: '#fef2f2' }} data-testid="orgchart-doc-error">
          <X size={24} className="mx-auto mb-2" style={{ color: '#dc2626' }} />
          <p className="text-sm font-semibold" style={{ color: '#991b1b' }}>{errMsg || 'Could not import that file'}</p>
          <p className="text-[11px] mt-1" style={{ color: '#b91c1c' }}>Try a PDF/image where the boxes and text are clearly legible.</p>
          <button onClick={reset} className="mt-3 px-4 py-2 rounded-lg text-xs font-bold" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid="orgchart-doc-retry">Try again</button>
        </div>
      )}
    </div>
  );
}
