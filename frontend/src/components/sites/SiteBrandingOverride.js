import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Loader2, RotateCcw, Palette, CheckCircle2 } from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const authHeaders = () => ({ Authorization: `Bearer ${localStorage.getItem('token')}` });

const FIELDS = [
  { key: 'name',            label: 'Site name override', placeholder: 'e.g. iGym Leeds', type: 'text' },
  { key: 'primary_color',   label: 'Primary colour',      placeholder: '#FF6B35', type: 'color' },
  { key: 'secondary_color', label: 'Secondary colour',    placeholder: '#1A1A2E', type: 'color' },
  { key: 'logo_url',        label: 'Logo URL',            placeholder: 'https://… or data:image/…', type: 'text' },
];

/**
 * Per-site brand override widget (iGym vs Pulse parent/child inheritance).
 * Reads/writes GET|PATCH /api/sites/{site_id}/branding.
 * Each field shows "Inherited" by default; typing overrides. Clearing
 * the input resets the field back to inherit from the parent org.
 */
const SiteBrandingOverride = ({ siteId, theme = 'dark' }) => {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [data, setData] = useState(null);
  const [draft, setDraft] = useState({});

  const dark = theme === 'dark';
  const textMuted = dark ? 'text-[var(--color-text-muted)]' : 'text-zinc-500 dark:text-zinc-400';
  const textBody = dark ? 'text-white' : 'text-zinc-800 dark:text-zinc-100';
  const inputBg = dark
    ? 'bg-[var(--color-ink)] border-white/10 text-white placeholder:text-white/30'
    : 'bg-white border-zinc-300 text-zinc-900 placeholder:text-zinc-400';

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/sites/${siteId}/branding`, { headers: authHeaders() });
      setData(r.data);
      setDraft(r.data.override || {});
    } catch (e) {
      notifyApiError(notify, e, 'Failed to load site branding');
    }
    setLoading(false);
  };

  useEffect(() => { if (siteId) load(); /* eslint-disable-next-line */ }, [siteId]);

  const save = async () => {
    setSaving(true);
    try {
      // Send a full field set so that cleared inputs become empty strings
      // which the backend interprets as "reset to inherit".
      const payload = {};
      FIELDS.forEach((f) => { payload[f.key] = draft[f.key] ?? ''; });
      const r = await axios.patch(`${API}/sites/${siteId}/branding`, payload, { headers: authHeaders() });
      setData(r.data);
      setDraft(r.data.override || {});
      notify.success('Branding saved');
    } catch (e) {
      notifyApiError(notify, e, 'Save failed');
    }
    setSaving(false);
  };

  const resetAll = async () => {
    if (!window.confirm('Reset this site to inherit from the parent organisation?')) return;
    setSaving(true);
    try {
      const payload = Object.fromEntries(FIELDS.map((f) => [f.key, '']));
      const r = await axios.patch(`${API}/sites/${siteId}/branding`, payload, { headers: authHeaders() });
      setData(r.data);
      setDraft({});
      notify.success('Reverted to parent branding');
    } catch (e) {
      notifyApiError(notify, e, 'Reset failed');
    }
    setSaving(false);
  };

  if (loading || !data) {
    return (
      <div className={`flex items-center gap-2 text-xs ${textMuted} py-4`}>
        <Loader2 size={12} className="animate-spin" /> Loading branding…
      </div>
    );
  }

  const parent = data.parent || {};
  const inherits = data.effective?._inherits || {};

  return (
    <div className="space-y-3" data-testid={`site-branding-override-${siteId}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1">
          <p className={`text-xs font-semibold ${textBody} inline-flex items-center gap-1.5`}>
            <Palette size={12} /> Brand override
          </p>
          <p className={`text-[10px] ${textMuted} mt-0.5`}>
            Any field left blank inherits from <strong className={textBody}>{parent.name || 'the parent organisation'}</strong>.
          </p>
        </div>
        <Button size="sm" variant="ghost" onClick={resetAll} disabled={saving}
          className={`${dark ? 'text-white/60 hover:text-white' : ''} h-7 px-2 text-[10px]`}
          data-testid={`site-branding-reset-${siteId}`}>
          <RotateCcw size={11} className="mr-1" /> Reset
        </Button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
        {FIELDS.map((f) => {
          const inherited = inherits[f.key];
          const val = draft[f.key] ?? '';
          const parentVal = parent[f.key] || '';
          const isColor = f.type === 'color';
          return (
            <div key={f.key}>
              <label className={`text-[10px] uppercase tracking-wider font-bold ${textMuted} flex items-center gap-1 mb-1`}>
                {f.label}
                {inherited
                  ? <Badge className="bg-emerald-500/15 text-emerald-400 border-0 text-[8px] px-1 py-0">Inherited</Badge>
                  : <Badge className="bg-amber-500/15 text-amber-400 border-0 text-[8px] px-1 py-0 inline-flex items-center gap-0.5"><CheckCircle2 size={8} /> Overridden</Badge>}
              </label>
              <div className="flex items-center gap-2">
                {isColor && (
                  <input type="color" value={val || parentVal || '#19CDFF'}
                    onChange={(e) => setDraft((d) => ({ ...d, [f.key]: e.target.value }))}
                    className="h-8 w-10 rounded border border-white/10 cursor-pointer bg-transparent flex-shrink-0"
                    data-testid={`site-branding-${f.key}-${siteId}-swatch`} />
                )}
                <input
                  type="text"
                  value={val}
                  placeholder={parentVal ? `Inherits: ${parentVal}` : f.placeholder}
                  onChange={(e) => setDraft((d) => ({ ...d, [f.key]: e.target.value }))}
                  className={`flex-1 h-8 px-2 rounded border text-xs ${inputBg}`}
                  data-testid={`site-branding-${f.key}-${siteId}`}
                />
              </div>
            </div>
          );
        })}
      </div>

      <div className="flex items-center justify-end gap-2 pt-1">
        <Button size="sm" variant="ghost" onClick={load} disabled={saving}
          className={`${dark ? 'text-white/50 hover:text-white' : ''} h-7 px-2 text-[10px]`}>
          Cancel
        </Button>
        <Button size="sm" onClick={save} disabled={saving}
          className="h-7 px-3 text-[11px] font-semibold"
          style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
          data-testid={`site-branding-save-${siteId}`}>
          {saving ? <Loader2 size={11} className="animate-spin mr-1" /> : null}
          Save branding
        </Button>
      </div>
    </div>
  );
};

export default SiteBrandingOverride;
