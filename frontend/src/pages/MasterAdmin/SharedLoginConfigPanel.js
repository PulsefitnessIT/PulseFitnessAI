/**
 * Admin → Portal Settings → Shared Site Login (global policy).
 * Master-admin defaults + a platform kill switch for commercial
 * shared site logins. Per-site settings are seeded from these defaults
 * when a site first provisions its shared login.
 */
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { KeyRound, Loader2, ShieldAlert } from 'lucide-react';
import { Switch } from '@/components/ui/switch';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const ROWS = [
  { key: 'require_staff_selection', label: 'Require staff selection before logging a fault (default)' },
  { key: 'allow_other_staff', label: 'Allow "Other staff member" fallback (default)' },
  { key: 'require_staff_pin', label: 'Require staff PIN confirmation (default)' },
  { key: 'notify_manager', label: 'Notify site manager on fault (default)' },
  { key: 'notify_staff', label: 'Send confirmation email to the selected staff member (default)' },
  { key: 'notify_service_desk', label: 'Notify the service desk (default)' },
  { key: 'notify_supplier', label: 'Notify the supplier (default)' },
];

export default function SharedLoginConfigPanel() {
  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };
  const [cfg, setCfg] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    axios.get(`${API}/master-admin/shared-login-config`, { headers })
      .then((r) => setCfg(r.data.config))
      .catch(() => toast.error('Could not load shared-login config'));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const update = async (key, value) => {
    const next = { ...cfg, [key]: value };
    setCfg(next);
    setSaving(true);
    try {
      const r = await axios.put(`${API}/master-admin/shared-login-config`, { [key]: value }, { headers });
      setCfg(r.data.config);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Save failed');
    }
    setSaving(false);
  };

  if (!cfg) return <div className="flex items-center gap-2 text-zinc-400 p-8"><Loader2 className="animate-spin" size={16} />Loading…</div>;

  return (
    <div className="max-w-2xl space-y-6" data-testid="shared-login-config-panel">
      <div>
        <h2 className="text-xl font-bold text-zinc-900 flex items-center gap-2"><KeyRound size={20} className="text-indigo-500" />Shared Site Login</h2>
        <p className="text-sm text-zinc-500 mt-1">Platform policy for commercial customer shared logins. These defaults apply to new site logins; managers can fine-tune per site.</p>
      </div>

      {/* Kill switch */}
      <div className="rounded-xl border border-zinc-200 p-4 flex items-center justify-between bg-zinc-50">
        <div className="flex items-start gap-3">
          <ShieldAlert size={18} className="text-amber-500 mt-0.5" />
          <div>
            <p className="font-medium text-zinc-900">Allow shared site logins</p>
            <p className="text-xs text-zinc-500">Master switch. When off, no site can provision a shared login.</p>
          </div>
        </div>
        <Switch checked={!!cfg.allow_shared_site_logins} onCheckedChange={(v) => update('allow_shared_site_logins', v)} data-testid="config-allow-shared" />
      </div>

      <div className="rounded-xl border border-zinc-200 divide-y divide-zinc-100">
        {ROWS.map((r) => (
          <div key={r.key} className="flex items-center justify-between gap-4 px-4 py-3">
            <span className="text-sm text-zinc-700">{r.label}</span>
            <Switch checked={!!cfg[r.key]} onCheckedChange={(v) => update(r.key, v)} disabled={!cfg.allow_shared_site_logins} data-testid={`config-${r.key}`} />
          </div>
        ))}
      </div>
      {saving && <p className="text-xs text-zinc-400 flex items-center gap-1"><Loader2 className="animate-spin" size={12} />Saving…</p>}
    </div>
  );
}
