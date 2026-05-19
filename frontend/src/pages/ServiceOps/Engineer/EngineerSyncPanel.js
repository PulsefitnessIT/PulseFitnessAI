/**
 * EngineerSyncPanel — iter 216h143 (Phase 4 / Slice 3).
 *
 * Lists every queued offline write with its label, age, attempts and
 * last error. Provides "Sync now" + per-op delete.
 *
 * Route: /svc/engineer/sync (engineer-only)
 */
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ChevronLeft, RefreshCw, Trash2, WifiOff, Wifi, Loader2, CheckCircle2,
  AlertTriangle, CloudOff,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import {
  engineerListOps, engineerRemoveOp, engineerClearQueue, engineerFlushQueue,
  useEngineerOfflineQueue,
} from '@/utils/engineerOfflineQueue';

const fmtRelative = (ms) => {
  if (!ms) return '—';
  const diff = Date.now() - ms;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
};

export default function EngineerSyncPanel() {
  const navigate = useNavigate();
  const { online } = useEngineerOfflineQueue();
  const [ops, setOps] = useState([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setOps(await engineerListOps());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const onSync = useCallback(async () => {
    if (!online) {
      notify.error('Still offline', 'Reconnect to a network first.');
      return;
    }
    setSyncing(true);
    try {
      const r = await engineerFlushQueue();
      if (r.flushed > 0) notify.success(`Synced ${r.flushed} change${r.flushed === 1 ? '' : 's'}`);
      if (r.last_error) notify.error('Sync stalled', r.last_error);
      refresh();
    } finally {
      setSyncing(false);
    }
  }, [online, refresh]);

  const onDelete = useCallback(async (id) => {
    await engineerRemoveOp(id);
    refresh();
  }, [refresh]);

  const onClear = useCallback(async () => {
    if (!window.confirm('Discard every queued change? This cannot be undone.')) return;
    await engineerClearQueue();
    refresh();
  }, [refresh]);

  return (
    <div className="min-h-screen bg-slate-50" data-testid="engineer-sync-panel">
      <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
        <div className="max-w-3xl mx-auto px-4 py-4 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <button
              type="button"
              onClick={() => navigate('/svc/engineer')}
              className="text-slate-500 hover:text-slate-900"
              data-testid="sync-back"
              aria-label="Back"
            >
              <ChevronLeft size={22} />
            </button>
            <div className="min-w-0">
              <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-blue-700">
                GymAxis · Engineer
              </p>
              <h1 className="text-xl font-extrabold text-slate-900 flex items-center gap-2">
                {online ? <Wifi size={20} className="text-emerald-600" /> : <WifiOff size={20} className="text-red-600" />}
                Sync queue
              </h1>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={refresh}
              className="p-2 rounded-lg hover:bg-slate-100 text-slate-500"
              data-testid="sync-refresh"
              aria-label="Refresh"
            >
              {loading ? <Loader2 size={18} className="animate-spin" /> : <RefreshCw size={18} />}
            </button>
            <button
              type="button"
              onClick={onSync}
              disabled={!online || syncing || ops.length === 0}
              className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-300 disabled:cursor-not-allowed text-white text-xs font-semibold px-3 py-2 rounded-lg"
              data-testid="sync-now-btn"
            >
              {syncing ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
              Sync now
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-4 space-y-3">
        <div className={`rounded-2xl border p-4 flex items-center gap-3 ${
          online ? 'bg-emerald-50 border-emerald-200' : 'bg-red-50 border-red-200'
        }`}>
          {online ? <Wifi size={20} className="text-emerald-600" /> : <CloudOff size={20} className="text-red-600" />}
          <div className="flex-1 min-w-0">
            <p className={`text-sm font-bold ${online ? 'text-emerald-900' : 'text-red-900'}`}>
              {online ? 'You are online' : 'You are offline'}
            </p>
            <p className={`text-xs ${online ? 'text-emerald-700' : 'text-red-700'}`}>
              {online
                ? ops.length === 0
                  ? 'No pending changes — everything is in sync.'
                  : `${ops.length} change${ops.length === 1 ? '' : 's'} waiting to upload.`
                : 'Captured updates will sync automatically when you reconnect.'}
            </p>
          </div>
        </div>

        {ops.length === 0 ? (
          <div
            className="bg-white border border-dashed border-slate-300 rounded-2xl p-10 text-center"
            data-testid="sync-empty"
          >
            <CheckCircle2 size={28} className="mx-auto text-emerald-500 mb-2" />
            <p className="text-sm font-semibold text-slate-700">Queue is empty</p>
            <p className="text-xs text-slate-500 mt-1">
              You can keep working offline — time entries, mileage, photos and signatures will queue here automatically.
            </p>
          </div>
        ) : (
          <>
            <ul className="bg-white border border-slate-200 rounded-2xl divide-y divide-slate-100 overflow-hidden">
              {ops.map((op) => (
                <li
                  key={op.id}
                  className="px-3 py-3 flex items-start gap-3"
                  data-testid={`sync-op-${op.id}`}
                >
                  <span className={`w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 ${
                    op.last_error ? 'bg-red-100 text-red-700' : 'bg-blue-100 text-blue-700'
                  }`}>
                    {op.last_error ? <AlertTriangle size={16} /> : <RefreshCw size={16} />}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-slate-900 truncate">{op.label}</p>
                    <p className="text-xs text-slate-500 truncate">
                      {op.method} · queued {fmtRelative(op.created_at)}
                      {op.attempts > 0 ? ` · ${op.attempts} attempt${op.attempts === 1 ? '' : 's'}` : ''}
                    </p>
                    {op.last_error ? (
                      <p className="text-[11px] text-red-600 mt-0.5 truncate" title={op.last_error}>
                        {op.last_error}
                      </p>
                    ) : null}
                  </div>
                  <button
                    type="button"
                    onClick={() => onDelete(op.id)}
                    className="text-slate-400 hover:text-red-600 p-1"
                    data-testid={`sync-discard-${op.id}`}
                    title="Discard"
                  >
                    <Trash2 size={14} />
                  </button>
                </li>
              ))}
            </ul>
            <div className="flex justify-end">
              <button
                type="button"
                onClick={onClear}
                className="text-xs font-semibold text-red-700 hover:underline"
                data-testid="sync-clear-all"
              >
                Discard all queued changes
              </button>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
