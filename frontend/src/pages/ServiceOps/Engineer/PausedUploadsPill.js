/**
 * Iter 220ea·4 — Paused-Uploads pill for the Engineer App home.
 *
 * Tiny header badge that surfaces any in-flight uploads that
 * didn't finish (tab closed, signal lost, browser killed).
 * Tapping it opens a bottom sheet listing each paused upload with
 * Resume / Discard buttons, so the engineer never has to wonder
 * "did that 25 MB video actually go through?".
 *
 * Wiring:
 *   <PausedUploadsPill />
 * Mount once at the top of EngineerHome.js. The component manages
 * its own polling (window focus + a periodic refresh) so callers
 * don't have to thread state.
 */
import { useCallback, useEffect, useState } from 'react';
import { UploadCloud, X, Loader2, RotateCcw, Trash2 } from 'lucide-react';
import axios from 'axios';
import { notify } from '@/components/notifications';
import { chunkedUpload } from '@/utils/chunkedUpload';
import {
  listPausedUploads,
  dropPausedUpload,
  subscribePausedUploads,
} from '@/utils/engineerUploadStash';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
});

function fmtBytes(n) {
  if (!n || n < 1024) return `${n || 0} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}
function fmtAgo(ts) {
  const s = Math.max(0, Math.round((Date.now() - (ts || 0)) / 1000));
  if (s < 60)   return `${s}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

export default function PausedUploadsPill() {
  const [rows, setRows] = useState([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState({}); // upload_id → 'resuming' | 'discarding'

  const refresh = useCallback(async () => {
    setRows(await listPausedUploads());
  }, []);

  useEffect(() => {
    refresh();
    const unsubscribe = subscribePausedUploads(refresh);
    const onFocus = () => refresh();
    window.addEventListener('focus', onFocus);
    const t = setInterval(refresh, 30_000);
    return () => {
      unsubscribe();
      window.removeEventListener('focus', onFocus);
      clearInterval(t);
    };
  }, [refresh]);

  const resume = async (row) => {
    setBusy((m) => ({ ...m, [row.upload_id]: 'resuming' }));
    try {
      const uploaded = await chunkedUpload({
        baseURL: API,
        file: row.blob,
        category: 'service-media',
        authHeaders: auth().headers,
        resumeUploadId: row.upload_id,
      });
      const fileUrl = uploaded?.download_url || uploaded?.storage_path;
      // Iter 220ea·4 — Finalise on the engineer-photos endpoint so
      // the upload actually appears in the case's media. We use the
      // stashed case_id + machine_row_id + caption so the resumed
      // upload lands on the same row the original attempt targeted.
      await axios.post(`${API}/svc/engineer/photos`, {
        case_id: row.case_id,
        machine_row_id: row.machine_row_id || undefined,
        file_url: fileUrl,
        mime_type: uploaded?.content_type || row.content_type || 'image/jpeg',
        caption: row.caption || '',
      }, auth());
      await dropPausedUpload(row.upload_id);
      notify.success('Upload resumed', `${row.filename} attached`);
    } catch (err) {
      if (err?.code === 'session_expired') {
        // Server-side session was collected by the TTL. The bytes
        // are still in the stash, but the upload_id is dead. Drop
        // the row so the engineer can re-pick the file fresh.
        await dropPausedUpload(row.upload_id);
        notify.error(
          'Upload session expired',
          'The server forgot this upload. Re-attach the file from the job.',
        );
      } else {
        notify.error('Could not resume', err?.message || 'Try again.');
      }
    } finally {
      setBusy((m) => { const n = { ...m }; delete n[row.upload_id]; return n; });
      refresh();
    }
  };

  const discard = async (row) => {
    setBusy((m) => ({ ...m, [row.upload_id]: 'discarding' }));
    try {
      // Best-effort server cancel — TTL will collect it anyway if
      // the network is still down.
      try {
        await axios.delete(`${API}/files/upload/chunks/${row.upload_id}`, auth());
      } catch { /* swallow */ }
      await dropPausedUpload(row.upload_id);
    } finally {
      setBusy((m) => { const n = { ...m }; delete n[row.upload_id]; return n; });
      refresh();
    }
  };

  if (rows.length === 0) return null;

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        data-testid="paused-uploads-pill"
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold border border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-500/40 dark:bg-amber-500/15 dark:text-amber-200"
        title="Tap to resume or discard paused uploads"
      >
        <UploadCloud size={12} />
        {rows.length} upload{rows.length === 1 ? '' : 's'} paused
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-end sm:items-center sm:justify-center bg-black/40"
          onClick={() => setOpen(false)}
          data-testid="paused-uploads-sheet"
        >
          <div
            className="w-full sm:max-w-md bg-white dark:bg-[var(--theme-surface)] rounded-t-2xl sm:rounded-2xl shadow-xl p-4 max-h-[80vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-base font-extrabold text-slate-900 dark:text-slate-100">
                Paused uploads
              </h2>
              <button
                type="button"
                onClick={() => setOpen(false)}
                data-testid="paused-uploads-close"
                className="p-1.5 rounded-md text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
                aria-label="Close"
              >
                <X size={16} />
              </button>
            </div>
            <p className="text-[11px] text-slate-500 mb-3">
              These uploads didn&apos;t finish. Resume them when you&apos;re back on a
              good connection, or discard the ones you no longer need.
            </p>
            <ul className="space-y-2">
              {rows.map((r) => {
                const state = busy[r.upload_id];
                return (
                  <li
                    key={r.upload_id}
                    className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-[var(--theme-canvas)] p-3"
                    data-testid={`paused-upload-row-${r.upload_id}`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-bold text-slate-900 dark:text-slate-100 truncate">
                          {r.filename || 'Unnamed upload'}
                        </p>
                        <p className="text-[10px] text-slate-500">
                          {fmtBytes(r.size)} · {fmtAgo(r.saved_at)}
                          {r.case_id ? ` · case ${String(r.case_id).slice(0, 8)}` : ''}
                        </p>
                        {r.caption ? (
                          <p className="text-[10px] text-slate-400 truncate mt-0.5">
                            “{r.caption}”
                          </p>
                        ) : null}
                      </div>
                      <div className="flex flex-col gap-1.5 shrink-0">
                        <button
                          type="button"
                          onClick={() => resume(r)}
                          disabled={!!state || !r.blob}
                          data-testid={`paused-upload-resume-${r.upload_id}`}
                          className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-bold bg-[var(--color-info-ios)] text-white disabled:opacity-50"
                        >
                          {state === 'resuming'
                            ? <Loader2 size={11} className="animate-spin" />
                            : <RotateCcw size={11} />}
                          Resume
                        </button>
                        <button
                          type="button"
                          onClick={() => discard(r)}
                          disabled={!!state}
                          data-testid={`paused-upload-discard-${r.upload_id}`}
                          className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-bold border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 disabled:opacity-50"
                        >
                          {state === 'discarding'
                            ? <Loader2 size={11} className="animate-spin" />
                            : <Trash2 size={11} />}
                          Discard
                        </button>
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>
      )}
    </>
  );
}
