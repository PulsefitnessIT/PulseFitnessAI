import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Loader2, RotateCcw, ShieldCheck } from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const authHeaders = () => ({ Authorization: `Bearer ${localStorage.getItem('token')}` });

const MODULES = [
  { key: 'operations',  label: 'Operations Portal', tip: 'Equipment, faults, PPM' },
  { key: 'memberships', label: 'Memberships',       tip: 'Members, plans, classes' },
  { key: 'marketing',   label: 'Marketing Suite',   tip: 'Campaigns, automation' },
];

/**
 * Per-site module override widget.
 * Reads/writes GET|PUT /api/sites/{site_id}/modules.
 * Shows "Inherited" vs "Override" state per module and a reset action.
 */
const SiteModulesOverride = ({ siteId, siteName, theme = 'dark' }) => {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(null);
  const [data, setData] = useState({ site_overrides: {}, effective: {} });

  const dark = theme === 'dark';
  const cardBg = dark ? 'bg-[var(--color-ink-alt)] border-white/10' : 'bg-white dark:bg-zinc-900 border-zinc-200 dark:border-zinc-700';
  const textMuted = dark ? 'text-[var(--color-text-muted)]' : 'text-zinc-500 dark:text-zinc-400';
  const textBody = dark ? 'text-white' : 'text-zinc-800 dark:text-zinc-100';

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/sites/${siteId}/modules`, { headers: authHeaders() });
      setData(r.data || { site_overrides: {}, effective: {} });
    } catch (e) {
      notifyApiError(notify, e, 'Failed to load site modules');
    }
    setLoading(false);
  };

  useEffect(() => { if (siteId) load(); /* eslint-disable-next-line */ }, [siteId]);

  const setOverride = async (key, enabled) => {
    setSaving(key);
    try {
      await axios.put(`${API}/sites/${siteId}/modules`,
        { modules: { [key]: { enabled } } },
        { headers: authHeaders() }
      );
      notify.success(`${key} ${enabled ? 'enabled' : 'disabled'} for ${siteName}`);
      await load();
    } catch (e) {
      notifyApiError(notify, e, 'Failed to update');
    }
    setSaving(null);
  };

  const clearOverride = async (key) => {
    setSaving(key);
    try {
      await axios.put(`${API}/sites/${siteId}/modules`,
        { modules: { [key]: { clear: true } } },
        { headers: authHeaders() }
      );
      notify.success(`${key} reverted to organisation default`);
      await load();
    } catch (e) {
      notifyApiError(notify, e, 'Failed to clear');
    }
    setSaving(null);
  };

  if (loading) {
    return (
      <div className={`mt-2 p-3 rounded-md ${cardBg} flex items-center gap-2 text-xs ${textMuted}`}
        data-testid={`site-modules-loading-${siteId}`}>
        <Loader2 size={12} className="animate-spin" /> Loading module overrides…
      </div>
    );
  }

  return (
    <div className={`mt-2 p-3 rounded-md ${cardBg}`} data-testid={`site-modules-${siteId}`}>
      <div className="flex items-center gap-1.5 mb-2">
        <ShieldCheck size={12} className={dark ? 'text-[var(--color-brand-cyan-hover)]' : 'text-[var(--color-brand-blue)]'} />
        <p className={`text-[11px] uppercase tracking-wider font-bold ${textMuted}`}>
          Module overrides for this site
        </p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
        {MODULES.map((m) => {
          const isOverride = Object.prototype.hasOwnProperty.call(data.site_overrides || {}, m.key);
          const effective = !!(data.effective || {})[m.key];
          const isSaving = saving === m.key;
          return (
            <div key={m.key}
              className={`p-2 rounded-md ${dark ? 'bg-[var(--theme-surface)] border border-white/5' : 'bg-zinc-50 dark:bg-zinc-800/50 border border-zinc-100 dark:border-zinc-700/40'}`}
              data-testid={`site-${siteId}-module-${m.key}`}>
              <div className="flex items-start justify-between gap-2 mb-1">
                <div className="min-w-0">
                  <p className={`text-xs font-semibold ${textBody} truncate`}>{m.label}</p>
                  <p className={`text-[10px] ${textMuted} truncate`}>{m.tip}</p>
                </div>
                <Switch
                  checked={effective}
                  disabled={isSaving}
                  onCheckedChange={(val) => setOverride(m.key, val)}
                  data-testid={`site-${siteId}-module-${m.key}-toggle`}
                />
              </div>
              <div className="flex items-center justify-between">
                {isOverride ? (
                  <Badge className={`h-4 text-[9px] ${effective
                    ? 'bg-emerald-500/15 text-emerald-400 border-0'
                    : 'bg-red-500/15 text-red-400 border-0'}`}>
                    Override · {effective ? 'on' : 'off'}
                  </Badge>
                ) : (
                  <Badge className="h-4 text-[9px] bg-zinc-500/15 text-zinc-300 border-0">
                    Inherited · {effective ? 'on' : 'off'}
                  </Badge>
                )}
                {isOverride && (
                  <Button size="sm" variant="ghost" disabled={isSaving}
                    className={`h-5 px-1 text-[10px] ${textMuted} hover:${textBody}`}
                    onClick={() => clearOverride(m.key)}
                    data-testid={`site-${siteId}-module-${m.key}-reset`}>
                    {isSaving ? <Loader2 size={10} className="animate-spin" /> : (
                      <><RotateCcw size={10} className="mr-0.5" /> Reset</>
                    )}
                  </Button>
                )}
              </div>
            </div>
          );
        })}
      </div>
      <p className={`text-[10px] ${textMuted} mt-1.5`}>
        Toggle to override the organisation default for this site only. Reset returns the
        module to whatever the organisation matrix says.
      </p>
    </div>
  );
};

export default SiteModulesOverride;
