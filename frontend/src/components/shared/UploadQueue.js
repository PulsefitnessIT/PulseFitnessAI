/**
 * UploadQueue — Iter 216h34
 *
 * Shared upload queue + bottom-right pinned drawer that surfaces every
 * in-flight file upload across the platform. Lee dropped 10 spec sheet
 * PDFs at once and couldn't tell which were done, which were stuck, and
 * which had failed — the legacy in-card "Processing... (3 remaining)"
 * pattern hides the per-file state. This component fixes that.
 *
 * Architecture:
 *   • `UploadQueueProvider` — wraps the app (mounted once in App.js).
 *     Owns an array of `UploadTask` objects.
 *   • `useUploadQueue()` — hook that returns `{ enqueue, retry, remove,
 *     cancel, tasks }`. Panels that own a dropzone call `enqueue(files,
 *     handler, { label, source })`.
 *   • `<UploadQueueDrawer>` — visual drawer pinned bottom-right. Auto-
 *     opens when the queue is non-empty; collapsible. Shows per-file
 *     name + progress bar + status (queued / uploading / done / failed)
 *     + per-file retry/dismiss actions.
 *
 * The handler signature is intentionally tiny so panels can adopt
 * without refactoring their existing upload code:
 *   handler(file, onProgress) => Promise<any>
 * Inside the handler you do your axios.post(...) — for per-file
 * progress, accept onProgress and pass it to `axios.onUploadProgress`.
 *
 * Drawer survives navigation (it's mounted at App.js level), so an
 * operator can flip tabs while large PDFs upload in the background.
 */
import React, {
  createContext, useCallback, useContext, useEffect, useMemo, useReducer, useState,
} from 'react';
import {
  Upload, X, ChevronDown, ChevronUp, RotateCw, CheckCircle2, AlertTriangle, Loader2,
} from 'lucide-react';

const UploadQueueCtx = createContext(null);

let _id = 0;
const nextId = () => {
  _id += 1;
  return `upl-${Date.now().toString(36)}-${_id}`;
};

const STATUS = {
  QUEUED: 'queued',
  UPLOADING: 'uploading',
  DONE: 'done',
  FAILED: 'failed',
};

function reducer(state, action) {
  switch (action.type) {
    case 'enqueue':
      return [...state, ...action.tasks];
    case 'patch':
      return state.map(t => (t.id === action.id ? { ...t, ...action.patch } : t));
    case 'remove':
      return state.filter(t => t.id !== action.id);
    case 'clear_done':
      return state.filter(t => t.status !== STATUS.DONE);
    default:
      return state;
  }
}

export function UploadQueueProvider({ children }) {
  const [tasks, dispatch] = useReducer(reducer, []);
  // Keep handler refs out of state so React doesn't re-render on every
  // progress tick. Indexed by task id.
  const handlersRef = React.useRef(new Map());

  const runTask = useCallback(async (taskId) => {
    const handler = handlersRef.current.get(taskId);
    if (!handler) return;
    dispatch({ type: 'patch', id: taskId, patch: { status: STATUS.UPLOADING, progress: 0, error: null } });
    try {
      const file = handler.file;
      await handler.fn(file, (pct) => {
        dispatch({ type: 'patch', id: taskId, patch: { progress: Math.max(0, Math.min(100, pct)) } });
      });
      dispatch({ type: 'patch', id: taskId, patch: { status: STATUS.DONE, progress: 100 } });
      // Fire completion callback if the caller provided one.
      handler.onDone?.(file);
    } catch (e) {
      const msg = e?.response?.data?.detail || e?.message || 'Upload failed';
      dispatch({ type: 'patch', id: taskId, patch: { status: STATUS.FAILED, error: msg } });
    }
  }, []);

  const enqueue = useCallback((files, fn, opts = {}) => {
    const list = Array.from(files || []);
    if (list.length === 0) return [];
    const newTasks = list.map(file => ({
      id: nextId(),
      name: file.name,
      size: file.size,
      label: opts.label || file.name,
      source: opts.source || 'upload',
      status: STATUS.QUEUED,
      progress: 0,
      error: null,
      createdAt: Date.now(),
    }));
    newTasks.forEach((t, i) => {
      handlersRef.current.set(t.id, { file: list[i], fn, onDone: opts.onDone });
    });
    dispatch({ type: 'enqueue', tasks: newTasks });
    // Kick off each task — they run in parallel. If you want serial,
    // chain inside the handler.
    newTasks.forEach(t => runTask(t.id));
    return newTasks.map(t => t.id);
  }, [runTask]);

  const retry = useCallback((taskId) => runTask(taskId), [runTask]);

  const remove = useCallback((taskId) => {
    handlersRef.current.delete(taskId);
    dispatch({ type: 'remove', id: taskId });
  }, []);

  const clearDone = useCallback(() => {
    dispatch({ type: 'clear_done' });
  }, []);

  const value = useMemo(() => ({ tasks, enqueue, retry, remove, clearDone }), [tasks, enqueue, retry, remove, clearDone]);

  // Iter 216h49 — Page-leave guard. Lee reported losing an in-progress
  // manual upload because he clicked away from the page mid-transfer.
  // While any task is QUEUED or UPLOADING, attach a beforeunload handler
  // so the browser prompts before tab close / hard refresh / route
  // change. Auto-cleared the moment all tasks settle (done/failed) so
  // we don't pester operators once the work is finished.
  const inFlightCount = tasks.filter(
    t => t.status === STATUS.QUEUED || t.status === STATUS.UPLOADING,
  ).length;
  useEffect(() => {
    if (inFlightCount === 0) return undefined;
    const handler = (e) => {
      e.preventDefault();
      // Most modern browsers ignore custom messages and show a generic
      // "Leave site?" prompt — but setting returnValue is still required
      // to trigger the dialog at all.
      e.returnValue = `${inFlightCount} upload${inFlightCount === 1 ? '' : 's'} in progress — leaving will cancel them.`;
      return e.returnValue;
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [inFlightCount]);

  return (
    <UploadQueueCtx.Provider value={value}>
      {children}
      <UploadQueueDrawer />
    </UploadQueueCtx.Provider>
  );
}

export function useUploadQueue() {
  const v = useContext(UploadQueueCtx);
  if (!v) {
    // Graceful no-op — code that calls enqueue() before the provider
    // mounts shouldn't crash. Falls back to a synchronous handler call.
    return {
      tasks: [],
      enqueue: async (files, fn) => {
        for (const f of Array.from(files || [])) {
          try { await fn(f, () => {}); } catch (e) { /* swallow */ }
        }
        return [];
      },
      retry: () => {},
      remove: () => {},
      clearDone: () => {},
    };
  }
  return v;
}

// ─── Drawer UI ──────────────────────────────────────────────────────
//
// Iter 216h36 — mobile-aware. The fixed bottom-right 340 px card is
// great on a laptop but collides with the iOS home indicator and the
// software keyboard on a phone. Now responsive:
//   • md+ (≥ 768 px) — unchanged: bottom-right floating card, 340 px wide.
//   • <md             — slide-up sheet pinned to the bottom, full-width
//                       minus 8 px margin. Collapsed state becomes a
//                       slim handle bar with a single-line summary so
//                       it never blocks page content. Expanded state
//                       respects `env(safe-area-inset-bottom)` so the
//                       footer "Clear complete" button stays above the
//                       iOS home indicator.
//   The list also grows tall enough on mobile to be usefully readable
//   (60 vh max instead of 280 px).

function UploadQueueDrawer() {
  const { tasks, retry, remove, clearDone } = useContext(UploadQueueCtx) || { tasks: [] };
  // Start collapsed on small viewports so the drawer doesn't eat half
  // the screen the moment a file upload starts.
  const [collapsed, setCollapsed] = useState(() => {
    if (typeof window !== 'undefined' && window.matchMedia) {
      return window.matchMedia('(max-width: 767px)').matches;
    }
    return false;
  });

  if (!tasks || tasks.length === 0) return null;

  const inFlight = tasks.filter(t => t.status === STATUS.QUEUED || t.status === STATUS.UPLOADING).length;
  const failed = tasks.filter(t => t.status === STATUS.FAILED).length;
  const done = tasks.filter(t => t.status === STATUS.DONE).length;

  return (
    <div
      className="
        fixed z-[200] rounded-t-2xl md:rounded-xl shadow-2xl border overflow-hidden
        bottom-0 left-2 right-2 md:bottom-4 md:left-auto md:right-4 md:w-[340px]
      "
      style={{
        background: 'var(--theme-surface, #fff)',
        borderColor: 'var(--theme-border, #E4E4E7)',
        paddingBottom: 'env(safe-area-inset-bottom)',
      }}
      data-testid="upload-queue-drawer"
    >
      {/* Mobile grab handle — hidden on desktop. */}
      <div className="md:hidden flex justify-center pt-1.5 pb-0.5">
        <div className="w-9 h-1 rounded-full" style={{ background: 'var(--theme-border, #E4E4E7)' }} aria-hidden />
      </div>
      {/* Header */}
      <button
        type="button"
        onClick={() => setCollapsed(c => !c)}
        className="w-full flex items-center gap-2 px-3 py-2.5 border-b text-left"
        style={{ borderColor: 'var(--theme-border, #E4E4E7)' }}
        data-testid="upload-queue-toggle"
      >
        <div className="w-7 h-7 rounded-md flex items-center justify-center shrink-0" style={{ background: 'rgb(var(--rgb-brand-cyan, 0 214 224) / 0.12)' }}>
          {inFlight > 0 ? (
            <Loader2 size={14} className="animate-spin" style={{ color: 'var(--color-brand-cyan, #00D6E0)' }} />
          ) : failed > 0 ? (
            <AlertTriangle size={14} className="text-amber-500" />
          ) : (
            <CheckCircle2 size={14} className="text-emerald-500" />
          )}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-bold tracking-tight" style={{ color: 'var(--theme-text, #18181B)' }}>
            {inFlight > 0
              ? `Uploading ${inFlight} file${inFlight === 1 ? '' : 's'}`
              : failed > 0
                ? `${failed} upload${failed === 1 ? '' : 's'} failed`
                : `${done} upload${done === 1 ? '' : 's'} complete`}
          </p>
          <p className="text-[10px] uppercase tracking-wider font-semibold" style={{ color: 'var(--theme-text-muted, #71717A)' }}>
            {tasks.length} total · {done} done · {failed} failed
          </p>
        </div>
        {collapsed ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>

      {/* Tasks — taller list on mobile so it's actually readable.
          280 px on desktop, 60 vh on mobile (still leaves header room). */}
      {!collapsed && (
        <div
          className="overflow-y-auto"
          style={{ maxHeight: 'min(60vh, 280px)' }}
          data-testid="upload-queue-list"
        >
          {tasks.map(t => (
            <UploadTaskRow key={t.id} task={t} onRetry={() => retry(t.id)} onRemove={() => remove(t.id)} />
          ))}
        </div>
      )}

      {/* Footer */}
      {!collapsed && done > 0 && (
        <div className="px-3 py-2 border-t flex items-center justify-between" style={{ borderColor: 'var(--theme-border, #E4E4E7)' }}>
          <span className="text-[10px] uppercase tracking-wider font-semibold" style={{ color: 'var(--theme-text-muted, #71717A)' }}>
            {done} complete
          </span>
          <button
            type="button"
            onClick={clearDone}
            className="text-xs font-bold underline-offset-2 hover:underline"
            style={{ color: 'var(--theme-text-muted, #71717A)' }}
            data-testid="upload-queue-clear-done"
          >
            Clear complete
          </button>
        </div>
      )}
    </div>
  );
}

function UploadTaskRow({ task, onRetry, onRemove }) {
  const isFailed = task.status === STATUS.FAILED;
  const isDone = task.status === STATUS.DONE;
  const isUploading = task.status === STATUS.UPLOADING;

  return (
    <div
      className="px-3 py-2 border-b last:border-b-0 flex items-start gap-2"
      style={{ borderColor: 'var(--theme-border-soft, #F4F4F5)' }}
      data-testid={`upload-task-${task.id}`}
    >
      <div className="mt-0.5 shrink-0">
        {isUploading && <Loader2 size={12} className="animate-spin" style={{ color: 'var(--color-brand-cyan, #00D6E0)' }} />}
        {task.status === STATUS.QUEUED && <Upload size={12} style={{ color: 'var(--theme-text-muted, #71717A)' }} />}
        {isDone && <CheckCircle2 size={12} className="text-emerald-500" />}
        {isFailed && <AlertTriangle size={12} className="text-red-500" />}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-xs font-semibold truncate" style={{ color: 'var(--theme-text, #18181B)' }} title={task.name}>
          {task.name}
        </p>
        {isFailed ? (
          <p className="text-[10px] text-red-500 truncate" title={task.error}>{task.error}</p>
        ) : (
          <div className="h-1 rounded-full mt-1 overflow-hidden" style={{ background: 'var(--theme-border-soft, #F4F4F5)' }}>
            <div
              className="h-full transition-all"
              style={{
                width: `${task.progress || (isUploading ? 30 : 0)}%`,
                background: isDone ? '#10B981' : 'var(--color-brand-cyan, #00D6E0)',
              }}
            />
          </div>
        )}
      </div>
      <div className="flex items-center gap-1 shrink-0">
        {isFailed && (
          <button
            type="button"
            onClick={onRetry}
            className="p-1 rounded hover:bg-zinc-100"
            title="Retry"
            data-testid={`upload-task-retry-${task.id}`}
          >
            <RotateCw size={11} style={{ color: 'var(--theme-text-muted, #71717A)' }} />
          </button>
        )}
        <button
          type="button"
          onClick={onRemove}
          className="p-1 rounded hover:bg-zinc-100"
          title={isUploading ? 'Cancel' : 'Dismiss'}
          data-testid={`upload-task-remove-${task.id}`}
        >
          <X size={11} style={{ color: 'var(--theme-text-muted, #71717A)' }} />
        </button>
      </div>
    </div>
  );
}

export default UploadQueueProvider;
