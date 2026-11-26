import { useRef, useState } from 'react';
import { Loader2, UploadCloud, X, RotateCcw, Play, CheckCircle2, AlertTriangle } from 'lucide-react';
import chunkedUpload from '@/utils/chunkedUpload';

// The API gateway refuses request bodies over 2 MiB, so anything above ~1 MB is sent in 1 MB pieces.
const CHUNK_FROM = 1024 * 1024;
const STAGES = [['upload', 'Uploading document'], ['verify', 'Verifying file'], ['process', 'Reading, extracting and matching'], ['done', 'Ready for review']];

const fmt = (b) => (b >= 1048576 ? `${(b / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`);

async function sha256Hex(file) {
  const buf = await crypto.subtle.digest('SHA-256', await file.arrayBuffer());
  return [...new Uint8Array(buf)].map((x) => x.toString(16).padStart(2, '0')).join('');
}

export function friendlyError(e, fallback) {
  const st = e?.response?.status;
  const d = e?.response?.data?.detail;
  if (e?.code === 'cancelled' || e?.name === 'CanceledError') return 'Upload cancelled.';
  if (st === 401) return 'Your session has expired — sign in again, then Retry.';
  if (st === 413) return typeof d === 'string' ? d : 'The file is larger than the maximum allowed.';
  if (st === 415) return 'This file type is not supported.';
  if (!e?.response) return 'Upload interrupted — check your connection, then Resume or Retry.';
  if (st >= 500) return 'The server could not finish this step — please try again shortly.';
  return typeof d === 'string' ? d : fallback;
}

/** Poll a background reading job until it finishes; resolves with the job, throws a readable error on failure. */
export async function waitForJob(axios, API, headers, jobId) {
  const started = Date.now();
  for (let i = 0; ; i += 1) {
    if (Date.now() - started > 45 * 60 * 1000) {
      throw Object.assign(new Error('timeout'), { response: { status: 422, data: { detail: 'Still processing after 45 minutes — press Retry; the upload is kept.' } } });
    }
    const r = await axios.get(`${API}/crm/v2/aftersales/build-quote/jobs/${jobId}`, { headers: headers() });
    if (r.data.status === 'done') return r.data;
    if (r.data.status === 'failed') throw Object.assign(new Error(r.data.error), { response: { status: 422, data: { detail: r.data.error } } });
    await new Promise((res) => setTimeout(res, i < 20 ? 3000 : 6000));
  }
}

/** Drag-and-drop upload for Aftersales documents. Upload progress and processing are shown separately;
 *  `onUploaded(fileDoc)` runs the server-side reading and resolves when the result is ready. */
export default function AfsDocumentUploader({ c, accept, typesLabel, maxMb = 50, disabled, onUploaded, testId = 'afs-upload' }) {
  const [file, setFile] = useState(null);
  const [stage, setStage] = useState('idle');
  const [pct, setPct] = useState(0);
  const [err, setErr] = useState('');
  const [over, setOver] = useState(false);
  const resumeId = useRef(null);
  const ctrl = useRef(null);
  const input = useRef(null);
  const busy = ['upload', 'verify', 'process'].includes(stage);

  const run = async (f, resume) => {
    setErr('');
    const ext = `.${(f.name.split('.').pop() || '').toLowerCase()}`;
    if (!accept.split(',').includes(ext)) { setStage('error'); setErr(`File type not supported — use ${typesLabel}.`); return; }
    if (f.size > maxMb * 1048576) { setStage('error'); setErr(`This file is ${fmt(f.size)} — the maximum is ${maxMb} MB.`); return; }
    ctrl.current = new AbortController();
    try {
      setStage('upload'); setPct(0);
      const tok = localStorage.getItem('token');
      if (!tok) throw Object.assign(new Error('no session'), { response: { status: 401 } });
      const doc = await chunkedUpload({
        baseURL: `${process.env.REACT_APP_BACKEND_URL}/api`, file: f, category: 'contracts',
        authHeaders: tok ? { Authorization: `Bearer ${tok}` } : {}, threshold: CHUNK_FROM,
        sha256: f.size > CHUNK_FROM ? await sha256Hex(f) : undefined, signal: ctrl.current.signal,
        keepSessionOnError: true, resumeUploadId: resume ? resumeId.current : undefined,
        onSession: ({ uploadId }) => { resumeId.current = uploadId; },
        onProgress: (p) => { setPct(p); if (p >= 100) setStage('verify'); },
      });
      resumeId.current = null;
      setStage('process');
      await onUploaded(doc, f);
      setStage('done');
    } catch (e) {
      if (e?.uploadId) resumeId.current = e.uploadId;
      if (e?.code === 'session_expired') resumeId.current = null;
      setStage('error'); setErr(friendlyError(e, 'The document could not be processed.'));
    }
  };
  const pick = (f) => { if (f) { setFile(f); run(f, false); } };
  const idx = STAGES.findIndex(([k]) => k === stage);

  return (
    <div data-testid={testId}>
      <div
        role="button" tabIndex={0} aria-label="Upload a document"
        onClick={() => !busy && !disabled && input.current?.click()}
        onKeyDown={(e) => { if ((e.key === 'Enter' || e.key === ' ') && !busy && !disabled) input.current?.click(); }}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); if (!busy && !disabled) pick(e.dataTransfer.files?.[0]); }}
        className="rounded-xl border-2 border-dashed px-4 py-5 text-center cursor-pointer transition-colors"
        style={{ borderColor: over ? 'var(--color-brand-cyan)' : c.border, color: c.textDim, opacity: disabled ? 0.5 : 1 }}
        data-testid={`${testId}-dropzone`}>
        <UploadCloud size={22} className="mx-auto mb-1" style={{ color: 'var(--color-brand-cyan)' }} />
        <p className="text-sm font-semibold" style={{ color: c.text }}>Drag a document here or <span className="underline">browse files</span></p>
        <p className="text-[11px] mt-0.5">{typesLabel} · up to {maxMb} MB</p>
        <input ref={input} type="file" accept={accept} className="hidden" data-testid={`${testId}-file`} disabled={busy || disabled}
          onChange={(e) => { pick(e.target.files?.[0]); e.target.value = ''; }} />
      </div>
      {file && stage !== 'idle' && (
        <div className="mt-2 rounded-lg border px-3 py-2 text-xs" style={{ borderColor: c.border, color: c.text }} data-testid={`${testId}-status`}>
          <div className="flex items-center gap-2">
            <span className="font-semibold truncate">{file.name}</span><span style={{ color: c.textDim }}>{fmt(file.size)}</span>
            <span className="ml-auto flex gap-2">
              {stage === 'upload' && <button type="button" onClick={() => ctrl.current?.abort()} className="inline-flex items-center gap-1 underline" data-testid={`${testId}-cancel`}><X size={12} />Cancel</button>}
              {stage === 'error' && resumeId.current && <button type="button" onClick={() => run(file, true)} className="inline-flex items-center gap-1 underline" data-testid={`${testId}-resume`}><Play size={12} />Resume</button>}
              {stage === 'error' && <button type="button" onClick={() => { resumeId.current = null; run(file, false); }} className="inline-flex items-center gap-1 underline" data-testid={`${testId}-retry`}><RotateCcw size={12} />Retry</button>}
            </span>
          </div>
          {stage === 'upload' && (
            <div className="mt-1.5 h-1.5 rounded-full overflow-hidden" style={{ background: c.border }}>
              <div className="h-full" style={{ width: `${pct}%`, background: 'var(--color-brand-cyan)', transition: 'width 200ms' }} data-testid={`${testId}-progress`} />
            </div>
          )}
          <ol className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1" aria-label="Progress">
            {STAGES.map(([k, label], i) => (
              <li key={k} className="inline-flex items-center gap-1" data-testid={`${testId}-stage-${k}`}
                style={{ color: stage === 'error' ? c.textDim : i < idx || stage === 'done' ? 'var(--color-success-alt)' : i === idx ? c.text : c.textDim, fontWeight: i === idx ? 700 : 400 }}>
                {i === idx && busy ? <Loader2 size={11} className="animate-spin" /> : i < idx || stage === 'done' ? <CheckCircle2 size={11} /> : null}
                {label}{k === 'upload' && stage === 'upload' ? ` ${pct}%` : ''}
              </li>
            ))}
          </ol>
          {stage === 'process' && <p className="mt-1" style={{ color: c.textDim }}>Large documents are read page by page — this can take a few minutes.</p>}
          {err && <p className="mt-1 inline-flex items-center gap-1" style={{ color: 'var(--color-danger)' }} data-testid={`${testId}-error`}><AlertTriangle size={12} />{err}</p>}
        </div>
      )}
    </div>
  );
}
