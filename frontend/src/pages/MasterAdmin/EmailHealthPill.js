/**
 * Tiny "Email" pill for the Master Admin top bar.
 *
 * Polls /api/master-admin/email-health every 60s. Click to open a
 * dialog with the last 5 send attempts + a deep-link to Resend
 * domains config when the failure mode is "domain not verified".
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Mail, X, ExternalLink, RefreshCw, RotateCw } from 'lucide-react';
import { useAuth } from '@/App';

const TONE = {
  green:        { dot: 'bg-emerald-500', ring: 'ring-emerald-500/30', text: 'text-emerald-700', bg: 'bg-emerald-50', border: 'border-emerald-200' },
  amber:        { dot: 'bg-amber-500',   ring: 'ring-amber-500/30',   text: 'text-amber-700',   bg: 'bg-amber-50',   border: 'border-amber-200' },
  red:          { dot: 'bg-rose-500',    ring: 'ring-rose-500/30',    text: 'text-rose-700',    bg: 'bg-rose-50',    border: 'border-rose-200' },
  unconfigured: { dot: 'bg-zinc-400',    ring: 'ring-zinc-400/30',    text: 'text-zinc-600',    bg: 'bg-zinc-50',    border: 'border-zinc-200' },
};

export default function EmailHealthPill() {
  const { API } = useAuth();
  const headers = useMemo(() => ({ Authorization: `Bearer ${localStorage.getItem('token')}` }), []);

  const [data, setData] = useState(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [retryingId, setRetryingId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/master-admin/email-health`, { headers });
      setData(r.data);
    } catch (e) {
      // Silent fail — the pill is non-critical.
    } finally {
      setLoading(false);
    }
  }, [API, headers]);

  /** Iter 216h222 — replay a failed outbound email from the dialog.
      Mirrors the AdminEmails page handler so the operator can retry
      from either surface. */
  const onRetry = useCallback(async (eventId) => {
    if (!eventId || retryingId) return;
    setRetryingId(eventId);
    try {
      const r = await axios.post(
        `${API}/master-admin/email-events/${eventId}/retry`,
        {},
        { headers },
      );
      toast.success('Email retried successfully', {
        description: r.data?.resend_id ? `Resend id: ${r.data.resend_id}` : undefined,
      });
      load();
    } catch (e) {
      const detail = e?.response?.data?.detail || 'Retry failed';
      toast.error('Retry failed', { description: detail });
    } finally {
      setRetryingId(null);
    }
  }, [API, headers, retryingId, load]);

  useEffect(() => {
    load();
    const interval = setInterval(load, 60000);
    return () => clearInterval(interval);
  }, [load]);

  if (!data) return null;
  const tone = TONE[data.status] || TONE.unconfigured;

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className={`inline-flex items-center gap-1.5 px-2 py-1 text-[11px] font-semibold rounded-full ring-1 ${tone.ring} ${tone.bg} ${tone.text} hover:brightness-95`}
        title={data.label}
        data-testid="email-health-pill"
      >
        <span className={`w-1.5 h-1.5 rounded-full ${tone.dot}`} />
        Email
      </button>
      {open && (
        <EmailHealthDialog
          data={data}
          onClose={() => setOpen(false)}
          onRefresh={load}
          loading={loading}
          onRetry={onRetry}
          retryingId={retryingId}
        />
      )}
    </>
  );
}


function EmailHealthDialog({ data, onClose, onRefresh, loading, onRetry, retryingId }) {
  const tone = TONE[data.status] || TONE.unconfigured;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" data-testid="email-health-dialog">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-4 border-b border-zinc-100">
          <div className="flex items-center gap-2">
            <Mail size={16} className="text-zinc-500" />
            <h3 className="text-base font-semibold text-zinc-900">Email pipeline</h3>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={onRefresh}
              disabled={loading}
              className="p-1.5 hover:bg-zinc-100 rounded text-zinc-500"
              title="Refresh"
              data-testid="email-health-refresh"
            >
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            </button>
            <button onClick={onClose} className="p-1 hover:bg-zinc-100 rounded" data-testid="email-health-close">
              <X size={16} />
            </button>
          </div>
        </div>
        <div className="p-5 space-y-4">
          <div className={`p-3 rounded-lg border ${tone.border} ${tone.bg}`}>
            <div className={`text-xs font-bold uppercase tracking-wider ${tone.text}`}>
              <span className={`inline-block w-1.5 h-1.5 rounded-full mr-1.5 align-middle ${tone.dot}`} />
              {data.status}
            </div>
            <div className={`text-sm mt-1 ${tone.text}`}>{data.label}</div>
          </div>

          <div className="grid grid-cols-2 gap-3 text-xs">
            <Stat label="Sent (24h)"    value={data.sent ?? 0}    accent="text-emerald-600" />
            <Stat label="Failed (24h)"  value={data.failed ?? 0}  accent="text-rose-600" />
            <Stat label="Last sent"     value={(data.last_sent_at || '—').slice(0, 16).replace('T', ' ')} />
            <Stat label="Last failed"   value={(data.last_failed_at || '—').slice(0, 16).replace('T', ' ')} />
          </div>

          <div className="text-xs">
            <div className="text-[10px] uppercase tracking-wider font-bold text-zinc-500">Sender</div>
            <div className="text-zinc-900 font-mono mt-0.5">{data.sender || '—'}</div>
            {data.domain_verified === false && (
              <a
                href="https://resend.com/domains"
                target="_blank" rel="noreferrer"
                className="mt-2 inline-flex items-center gap-1 px-2 py-1 text-[11px] font-semibold rounded bg-rose-100 text-rose-700 hover:bg-rose-200"
                data-testid="email-health-resend-link"
              >
                Verify domain on Resend <ExternalLink size={11} />
              </a>
            )}
          </div>

          {data.last_error && (
            <div>
              <div className="text-[10px] uppercase tracking-wider font-bold text-zinc-500 mb-1">Last error</div>
              <div className="text-xs font-mono p-2 rounded bg-zinc-100 text-rose-700 break-all max-h-24 overflow-y-auto">
                {data.last_error}
              </div>
            </div>
          )}

          <div>
            <div className="text-[10px] uppercase tracking-wider font-bold text-zinc-500 mb-2">Last 5 attempts</div>
            {(data.recent || []).length === 0 ? (
              <div className="text-xs text-zinc-400">No activity yet.</div>
            ) : (
              <div className="space-y-1">
                {data.recent.map((row, i) => (
                  <div key={row.id || i} className="flex items-start gap-2 p-2 rounded border border-zinc-100 text-xs" data-testid={`email-health-row-${i}`}>
                    <span className={`mt-1 w-1.5 h-1.5 rounded-full flex-shrink-0 ${row.status === 'sent' ? 'bg-emerald-500' : 'bg-rose-500'}`} />
                    <div className="flex-1 min-w-0">
                      <div className="font-semibold text-zinc-900 truncate">{row.subject || '—'}</div>
                      <div className="text-zinc-500 truncate">{row.to}</div>
                      {row.error && <div className="text-rose-600 truncate text-[11px] mt-0.5">{row.error}</div>}
                      {/* Iter 216h222 — Try again button on failed
                          rows whose payload was captured. Pre-h222
                          failures have retryable=false → no button. */}
                      {row.retryable && (
                        <button
                          type="button"
                          onClick={() => onRetry?.(row.id)}
                          disabled={retryingId === row.id}
                          className="mt-1.5 inline-flex items-center gap-1 rounded-md bg-zinc-900 text-white text-[10px] font-bold px-2 py-1 hover:bg-zinc-800 disabled:opacity-60 disabled:cursor-wait transition"
                          data-testid={`email-health-retry-${i}`}
                        >
                          <RotateCw size={10} className={retryingId === row.id ? 'animate-spin' : ''} />
                          {retryingId === row.id ? 'Retrying…' : 'Try again'}
                        </button>
                      )}
                    </div>
                    <div className="text-zinc-400 text-[10px] flex-shrink-0">
                      {(row.created_at || '').slice(11, 16)}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}


function Stat({ label, value, accent }) {
  return (
    <div className="rounded-md border border-zinc-200 p-2.5">
      <div className="text-[10px] uppercase tracking-wider font-bold text-zinc-500">{label}</div>
      <div className={`text-base font-bold mt-0.5 ${accent || 'text-zinc-900'}`}>{value}</div>
    </div>
  );
}
