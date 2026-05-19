/* Social Media — Meta OAuth wizard + status */
import { useEffect, useState } from 'react';
import axios from 'axios';
import { AlertTriangle, CheckCircle2, ExternalLink, Loader2 } from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

const SocialTab = ({ API, headers }) => {
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = () => axios.get(`${API}/api/marketing/social/status`, { headers }).then((r) => setStatus(r.data)).catch(() => setStatus({ platform_configured: false, accounts: [] }));
  useEffect(() => { load();   }, []);

  const connect = async () => {
    setBusy(true);
    try {
      const { data } = await axios.get(`${API}/api/marketing/social/connect-url?network=facebook`, { headers });
      window.location.href = data.authorise_url;
    } catch (err) {
      notifyApiError(notify, err, 'Could not start OAuth flow');
      setBusy(false);
    }
  };

  if (!status) return <div className="flex items-center gap-2 text-zinc-400 dark:text-zinc-500 py-8"><Loader2 className="animate-spin" size={14} /> Loading…</div>;

  return (
    <div className="space-y-4" data-testid="marketing-social-tab">
      {!status.platform_configured && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-5 flex items-start gap-3" data-testid="social-not-configured">
          <AlertTriangle className="text-amber-600 shrink-0 mt-0.5" size={18} />
          <div className="text-xs text-zinc-700 dark:text-zinc-300">
            <p className="font-semibold">Meta App not yet configured by GymAxis</p>
            <p className="mt-1">The platform admin needs to register the GymAxis Meta App and set <code className="font-mono">META_APP_ID</code> + <code className="font-mono">META_APP_SECRET</code> in the backend environment. Until then, you can still draft posts in the Creative Studio and copy/paste them.</p>
            <p className="mt-2 text-[10px] text-zinc-500 dark:text-zinc-400 dark:text-zinc-500">Missing env vars: {(status.missing_env_vars || []).join(', ') || 'none'}</p>
          </div>
        </div>
      )}

      {status.platform_configured && (
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-5">
          <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 mb-3">Connect your accounts</p>
          <p className="text-xs text-zinc-500 dark:text-zinc-400 dark:text-zinc-500 mb-4">We'll redirect you to Facebook to authorise GymAxis. You'll pick which Page (and linked Instagram Business account) to connect.</p>
          <button
            onClick={connect}
            disabled={busy}
            className="px-4 py-2 rounded-md bg-[#1877F2] text-white text-sm font-semibold inline-flex items-center gap-2 disabled:opacity-50"
            data-testid="social-connect-meta-btn"
          >
            {busy ? <Loader2 size={13} className="animate-spin" /> : <ExternalLink size={13} />} Connect with Meta
          </button>
        </div>
      )}

      {(status.accounts || []).length > 0 && (
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-5" data-testid="social-accounts-list">
          <p className="text-xs font-semibold text-zinc-700 dark:text-zinc-300 mb-3 uppercase tracking-wider">Connected accounts</p>
          <ul className="space-y-2">
            {status.accounts.map((a) => (
              <li key={a.id} className="flex items-center justify-between py-2 border-b border-zinc-100 dark:border-zinc-800 last:border-b-0">
                <div className="flex items-center gap-3">
                  <CheckCircle2 className="text-emerald-500" size={14} />
                  <div>
                    <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">{a.page_name}</p>
                    <p className="text-[10px] text-zinc-400 dark:text-zinc-500 uppercase tracking-wider">{a.network}</p>
                  </div>
                </div>
                <span className="text-[10px] uppercase tracking-wider text-emerald-700 font-semibold">Active</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900/50 p-4 text-[11px] text-zinc-500 dark:text-zinc-400 dark:text-zinc-500">
        <strong>How it works:</strong> GymAxis registers a single Meta Business app at the platform level (one OAuth app for the whole SaaS). Each gym connects their own Facebook Page + Instagram Business account through that app. Tokens are encrypted with the platform Fernet key — your account credentials never reach our servers.
      </div>
    </div>
  );
};

export default SocialTab;
