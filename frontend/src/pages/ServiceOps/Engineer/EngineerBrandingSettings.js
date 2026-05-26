/**
 * EngineerBrandingSettings — Iter 220i.
 *
 * Lets a Partner Engineer (especially a solo operator running under
 * their own trading name) override the org-default branding for their
 * portal + every PDF they email. Uploads a logo to
 * /api/files/upload (category=branding), then PUTs the canonical URL +
 * primary/accent hexes to /api/svc/branding/me.
 *
 * Falls back to org defaults when the engineer hasn't set anything.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft, Image as ImageIcon, Loader2, Upload, RotateCcw, Save, Sparkles,
} from 'lucide-react';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
});

const DEFAULT_PRIMARY = '#0055FF';
const DEFAULT_ACCENT = '#7C3AED';

function _absLogo(url) {
  if (!url) return '';
  if (url.startsWith('http') || url.startsWith('data:')) return url;
  const base = (process.env.REACT_APP_BACKEND_URL || '').replace(/\/$/, '');
  return `${base}${url}`;
}

export default function EngineerBrandingSettings() {
  const navigate = useNavigate();
  const fileRef = useRef(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [effective, setEffective] = useState({});
  const [orgDefaults, setOrgDefaults] = useState({});
  const [draft, setDraft] = useState({
    logo_url: null, primary_color: DEFAULT_PRIMARY, accent_color: DEFAULT_ACCENT,
  });
  const [hasOverride, setHasOverride] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/svc/branding`, auth());
      const eff = r.data?.effective || {};
      const eng = r.data?.engineer || {};
      const org = r.data?.organization || {};
      setEffective(eff);
      setOrgDefaults(org);
      setHasOverride(!!r.data?.has_engineer_override);
      setDraft({
        logo_url: eng.logo_url ?? eff.logo_url ?? null,
        primary_color: eng.primary_color ?? eff.primary_color ?? DEFAULT_PRIMARY,
        accent_color: eng.accent_color ?? eff.accent_color ?? DEFAULT_ACCENT,
      });
    } catch (e) {
      notify.error('Could not load branding', e?.response?.data?.detail || e?.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const onUpload = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (f.size > 4 * 1024 * 1024) {
      notify.error('Logo too large', 'Please keep logos under 4 MB.');
      return;
    }
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append('file', f);
      const r = await axios.post(`${API}/files/upload?category=branding`, fd, {
        ...auth(),
        headers: { ...auth().headers, 'Content-Type': 'multipart/form-data' },
      });
      const uploadedId = r.data?.id;
      if (!uploadedId) throw new Error('Upload failed — no file id');
      const logoUrl = `/api/public/files/${uploadedId}`;
      setDraft((d) => ({ ...d, logo_url: logoUrl }));
      notify.success('Logo uploaded', 'Click Save changes to apply.');
    } catch (err) {
      notify.error('Upload failed', err?.response?.data?.detail || err?.message);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const save = async () => {
    setSaving(true);
    try {
      await axios.put(`${API}/svc/branding/me`, draft, auth());
      notify.success('Branding saved', 'Your reports + portal will use it from now on.');
      await load();
    } catch (e) {
      notify.error('Save failed', e?.response?.data?.detail || e?.message);
    } finally {
      setSaving(false);
    }
  };

  const reset = async () => {
    if (!hasOverride) return;
    if (!window.confirm('Revert to your organisation\'s default branding?')) return;
    setSaving(true);
    try {
      await axios.delete(`${API}/svc/branding/me`, auth());
      notify.success('Reverted to organisation defaults');
      await load();
    } catch (e) {
      notify.error('Reset failed', e?.response?.data?.detail || e?.message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50" data-testid="branding-loading">
        <Loader2 size={20} className="animate-spin text-blue-600" />
      </div>
    );
  }

  const logoPreview = draft.logo_url || effective.logo_url;

  return (
    <div className="min-h-screen bg-slate-50" data-testid="engineer-branding">
      <header className="sticky top-0 z-10 bg-white border-b border-slate-200">
        <div className="max-w-2xl mx-auto px-4 py-3 flex items-center gap-3">
          <button
            type="button"
            onClick={() => navigate('/svc/engineer')}
            className="p-2 -ml-2 rounded-lg hover:bg-slate-100"
            data-testid="branding-back"
          >
            <ArrowLeft size={18} className="text-slate-700" />
          </button>
          <div className="flex-1 min-w-0">
            <h1 className="text-base font-extrabold text-slate-900">Branding</h1>
            <p className="text-xs text-slate-500">Logo + colours used on your PDFs and portal.</p>
          </div>
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-4 py-4 pb-24 space-y-5">
        <section className="rounded-2xl border border-slate-200 bg-white p-4 space-y-3">
          <div className="flex items-center gap-2">
            <ImageIcon size={14} className="text-blue-600" />
            <p className="text-[11px] font-bold uppercase tracking-wide text-slate-700">Logo</p>
          </div>
          <div className="flex items-center gap-4">
            <div className="w-28 h-20 rounded-lg border border-dashed border-slate-300 bg-slate-50 flex items-center justify-center overflow-hidden" data-testid="branding-logo-preview">
              {logoPreview ? (
                <img src={_absLogo(logoPreview)} alt="logo" className="max-h-full max-w-full object-contain" />
              ) : (
                <span className="text-[10px] text-slate-400">No logo</span>
              )}
            </div>
            <div className="flex-1">
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                disabled={uploading}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold disabled:opacity-50"
                data-testid="branding-upload-btn"
              >
                {uploading ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />}
                {uploading ? 'Uploading…' : 'Upload logo'}
              </button>
              <input
                type="file"
                ref={fileRef}
                accept="image/*"
                onChange={onUpload}
                className="hidden"
                data-testid="branding-upload-input"
              />
              <p className="text-[10px] text-slate-500 mt-1.5">PNG / JPG / SVG · &lt; 4 MB</p>
            </div>
          </div>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-4 space-y-3">
          <div className="flex items-center gap-2">
            <Sparkles size={14} className="text-purple-600" />
            <p className="text-[11px] font-bold uppercase tracking-wide text-slate-700">Colours</p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <label className="block" data-testid="branding-primary-label">
              <span className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Primary</span>
              <div className="mt-1 flex items-center gap-2">
                <input
                  type="color"
                  value={draft.primary_color || DEFAULT_PRIMARY}
                  onChange={(e) => setDraft((d) => ({ ...d, primary_color: e.target.value.toUpperCase() }))}
                  className="h-9 w-12 rounded border border-slate-200"
                  data-testid="branding-primary-color"
                />
                <input
                  type="text"
                  value={draft.primary_color || ''}
                  onChange={(e) => setDraft((d) => ({ ...d, primary_color: e.target.value }))}
                  className="flex-1 text-xs font-mono border border-slate-200 rounded px-2 py-1.5"
                  placeholder="#0055FF"
                  data-testid="branding-primary-input"
                />
              </div>
            </label>
            <label className="block" data-testid="branding-accent-label">
              <span className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Accent</span>
              <div className="mt-1 flex items-center gap-2">
                <input
                  type="color"
                  value={draft.accent_color || DEFAULT_ACCENT}
                  onChange={(e) => setDraft((d) => ({ ...d, accent_color: e.target.value.toUpperCase() }))}
                  className="h-9 w-12 rounded border border-slate-200"
                  data-testid="branding-accent-color"
                />
                <input
                  type="text"
                  value={draft.accent_color || ''}
                  onChange={(e) => setDraft((d) => ({ ...d, accent_color: e.target.value }))}
                  className="flex-1 text-xs font-mono border border-slate-200 rounded px-2 py-1.5"
                  placeholder="#7C3AED"
                  data-testid="branding-accent-input"
                />
              </div>
            </label>
          </div>
        </section>

        {Object.keys(orgDefaults || {}).length > 0 && (
          <section className="rounded-2xl border border-slate-200 bg-slate-100/60 p-3" data-testid="branding-org-defaults">
            <p className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Org defaults (fallback)</p>
            <div className="flex items-center gap-3 mt-2">
              {orgDefaults.logo_url && (
                <img src={_absLogo(orgDefaults.logo_url)} alt="org logo" className="h-8 max-w-[80px] object-contain" />
              )}
              {orgDefaults.primary_color && (
                <span className="inline-flex items-center gap-1 text-[11px] text-slate-700">
                  <span className="w-3 h-3 rounded" style={{ background: orgDefaults.primary_color }} />
                  {orgDefaults.primary_color}
                </span>
              )}
            </div>
          </section>
        )}

        <div className="flex items-center gap-2 sticky bottom-3">
          <button
            type="button"
            onClick={save}
            disabled={saving}
            className="flex-1 inline-flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-sm font-bold disabled:opacity-50"
            data-testid="branding-save"
          >
            {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
            {saving ? 'Saving…' : 'Save changes'}
          </button>
          {hasOverride && (
            <button
              type="button"
              onClick={reset}
              disabled={saving}
              className="inline-flex items-center gap-1.5 px-3 py-2.5 rounded-xl border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 text-sm font-bold disabled:opacity-50"
              data-testid="branding-reset"
            >
              <RotateCcw size={13} /> Reset
            </button>
          )}
        </div>
      </main>
    </div>
  );
}
