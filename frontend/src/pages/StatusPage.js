/**
 * StatusPage — Iter 215by
 *
 * Public status page at /status. Calls `/api/health/deep` (added in
 * iter 215bt) on mount + every 30s, and renders a friendly status
 * dashboard. No auth required so anyone can verify uptime — useful
 * for support tickets ("the platform must be down!") and for
 * customers who want to monitor independently.
 */
import React from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import { CheckCircle2, AlertTriangle, XCircle, Loader2, ArrowLeft } from 'lucide-react';

const REFRESH_MS = 30_000;
const API = process.env.REACT_APP_BACKEND_URL;

// Customer-friendly labels for the noisier `/api/health/deep` keys.
const SERVICE_LABELS = {
  mongo: 'Database',
  file_validation: 'File Uploads',
  sentry: 'Error Tracking',
  stripe: 'Payments',
  resend: 'Email Delivery',
  llm: 'AI Services',
};

function pillFor(status) {
  if (status === 'ok' || status === 'configured') return { Icon: CheckCircle2, color: 'var(--color-success)', label: 'Operational' };
  if (status === 'down')  return { Icon: XCircle,        color: 'var(--color-danger)',  label: 'Down' };
  if (status === 'missing') return { Icon: AlertTriangle, color: 'var(--color-warning-soft)', label: 'Not configured' };
  return { Icon: AlertTriangle, color: 'var(--color-warning)', label: status };
}

const StatusPage = () => {
  const isPulse = typeof window !== 'undefined' && window.location.pathname.toLowerCase().startsWith('/pulse');
  const accent = isPulse ? 'var(--pulse-primary)' : 'var(--color-brand-blue)';
  const homeHref = isPulse ? '/pulse' : '/';
  const brandName = isPulse ? 'Pulse Fitness' : 'GymAxis';
  const [data, setData] = React.useState(null);
  const [error, setError] = React.useState(null);
  const [lastChecked, setLastChecked] = React.useState(null);

  React.useEffect(() => {
    let mounted = true;
    const load = async () => {
      try {
        const res = await axios.get(`${API}/api/health/deep`, { timeout: 5000 });
        if (mounted) {
          setData(res.data);
          setError(null);
          setLastChecked(new Date());
        }
      } catch (e) {
        if (mounted) {
          setError(e?.message || 'Failed to reach status endpoint');
          setLastChecked(new Date());
        }
      }
    };
    load();
    const t = setInterval(load, REFRESH_MS);
    return () => { mounted = false; clearInterval(t); };
  }, []);

  const overall = data?.overall || (error ? 'down' : 'loading');
  const overallPill = overall === 'loading'
    ? { Icon: Loader2, color: 'var(--color-info)', label: 'Checking…' }
    : pillFor(overall);

  return (
    <div className="min-h-screen bg-white dark:bg-zinc-900 px-6 py-12" data-testid="status-page" data-brand={isPulse ? 'pulse' : 'gymaxis'}>
      <div className="max-w-2xl mx-auto">
        <Link to={homeHref} className="inline-flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-700 mb-6">
          <ArrowLeft size={12} /> Back to {brandName}
        </Link>

        <p className="text-[10px] font-bold uppercase tracking-[0.24em] mb-3" style={{ color: accent }}>
          {brandName} · System Status
        </p>
        <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight text-zinc-900 dark:text-zinc-100 mb-8" style={{ letterSpacing: '-0.02em' }}>
          {overall === 'ok' ? 'All systems operational' : overall === 'loading' ? 'Checking systems…' : 'Some systems are degraded'}
        </h1>

        <div
          className="rounded-2xl border p-5 mb-6 flex items-start gap-3"
          style={{ borderColor: overallPill.color, background: `${overallPill.color}11` }}
          data-testid="status-overall-card"
        >
          <overallPill.Icon size={22} style={{ color: overallPill.color }} className={overall === 'loading' ? 'animate-spin' : ''} />
          <div className="flex-1">
            <p className="text-sm font-bold text-zinc-900 dark:text-zinc-100">{overallPill.label}</p>
            {data?.latency_ms != null && <p className="text-[11px] text-zinc-500 mt-0.5">Health check completed in {data.latency_ms}ms</p>}
            {error && <p className="text-[11px] text-zinc-500 mt-0.5">{error}</p>}
          </div>
          {lastChecked && <p className="text-[10px] text-zinc-400 self-center">Last checked {lastChecked.toLocaleTimeString()}</p>}
        </div>

        <div className="space-y-2">
          {data?.checks && Object.entries(data.checks).map(([key, info]) => {
            const pill = pillFor(info?.status);
            return (
              <div
                key={key}
                className="flex items-center justify-between p-3 rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white/50"
                data-testid={`status-row-${key}`}
              >
                <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">{SERVICE_LABELS[key] || key}</p>
                <span className="inline-flex items-center gap-1.5 text-xs font-bold" style={{ color: pill.color }}>
                  <pill.Icon size={12} /> {pill.label}
                </span>
              </div>
            );
          })}
        </div>

        <p className="mt-10 text-xs text-zinc-500 text-center">
          Auto-refreshes every 30 seconds. For incidents and post-mortems, see the <Link to="/whats-new" className="underline" style={{ color: accent }}>release notes</Link>.
        </p>
      </div>
    </div>
  );
};

export default StatusPage;
