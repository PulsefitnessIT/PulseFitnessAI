import { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Camera, Loader2, Trash2 } from 'lucide-react';
import { API, useAuthHeaders, FieldRow } from './shared';
import LocalizationPanel from './LocalizationPanel';


export default function OrganisationSection({ billing, profile }) {
  const headers = useAuthHeaders();
  const [org, setOrg] = useState(null);
  const [form, setForm] = useState({
    address_line1: '', address_line2: '', address_line3: '', city: '',
    postcode: '', country: '', phone: '', primary_contact_email: '',
    primary_contact_phone: '', website: '',
  });
  const [saving, setSaving] = useState(false);
  // Iter 216h57 — inline logo upload so the "Upload logo" onboarding
  // step works without navigating away (previously it tried to push
  // to /dashboard?settings=brand which doesn't exist and closed the
  // settings modal).
  const [logoUploading, setLogoUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [applyingColor, setApplyingColor] = useState('');
  const logoFileRef = useRef(null);
  const isOwner = (profile?.role || '').toLowerCase() === 'owner';
  const isManager = (profile?.role || '').toLowerCase() === 'manager';
  const canEditLogo = isOwner || isManager;

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { data } = await axios.get(`${API}/account/organisation`, { headers: headers() });
        if (cancelled) return;
        setOrg(data);
        setForm({
          address_line1: data.address_line1 || '',
          address_line2: data.address_line2 || '',
          address_line3: data.address_line3 || '',
          city: data.city || '',
          postcode: data.postcode || '',
          country: data.country || '',
          phone: data.phone || '',
          primary_contact_email: data.primary_contact_email || '',
          primary_contact_phone: data.primary_contact_phone || '',
          website: data.website || '',
        });
      } catch {
        if (!cancelled) setOrg(null);
      }
    })();
    return () => { cancelled = true; };
  }, [headers]);

  const save = async () => {
    setSaving(true);
    try {
      const { data } = await axios.patch(`${API}/account/organisation`, form, { headers: headers() });
      setOrg(data);
      toast.success('Organisation details updated');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Update failed');
    }
    setSaving(false);
  };

  if (!org && !billing?.organization) {
    return <div className="text-sm" style={{ color: 'var(--theme-text-muted)' }}>No organisation linked to this account.</div>;
  }

  const update = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const onLogoFile = async (e) => {
    const f = e.target?.files?.[0] || e;
    if (!f) return;
    await uploadLogo(f);
    if (logoFileRef.current) logoFileRef.current.value = '';
  };

  const uploadLogo = async (f) => {
    setLogoUploading(true);
    try {
      const fd = new FormData();
      fd.append('file', f);
      const { data } = await axios.post(`${API}/account/logo`, fd, {
        headers: { ...headers(), 'Content-Type': 'multipart/form-data' },
      });
      setOrg((o) => ({ ...(o || {}), logo_url: data.logo_url, brand_palette: data.brand_palette || [] }));
      toast.success(
        data.brand_palette?.length
          ? `Logo uploaded — ${data.brand_palette.length} brand colour${data.brand_palette.length === 1 ? '' : 's'} detected`
          : 'Logo uploaded',
      );
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Logo upload failed');
    }
    setLogoUploading(false);
  };

  // Iter 216h58 — drag-and-drop + extracted brand-colour palette.
  const onLogoDrop = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
    if (!canEditLogo) {
      toast.error('Only the Owner or a Manager can change the logo.');
      return;
    }
    const f = e.dataTransfer?.files?.[0];
    if (!f) return;
    if (!/^image\//.test(f.type)) {
      toast.error('Please drop an image file (PNG, JPG, or WebP).');
      return;
    }
    await uploadLogo(f);
  };

  const applyBrandColor = async (hex) => {
    setApplyingColor(hex);
    try {
      await axios.post(`${API}/account/branding/apply`, { primary_color: hex }, { headers: headers() });
      setOrg((o) => ({ ...(o || {}), primary_color: hex }));
      toast.success(`Brand colour set to ${hex}`);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not apply brand colour');
    }
    setApplyingColor('');
  };

  const removeLogo = async () => {
    setLogoUploading(true);
    try {
      await axios.delete(`${API}/account/logo`, { headers: headers() });
      setOrg((o) => ({ ...(o || {}), logo_url: null }));
      toast.success('Logo removed');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Remove failed');
    }
    setLogoUploading(false);
  };

  return (
    <div className="space-y-5" data-testid="account-section-organisation">
      <div className="account-card rounded-xl p-5">
        <div className="text-[10px] uppercase tracking-wider font-semibold mb-2" style={{ color: 'var(--theme-text-muted)' }}>Organisation</div>
        <div className="text-xl font-extrabold" style={{ color: 'var(--theme-text)' }} data-testid="account-org-name">
          {org?.name || billing?.organization}
        </div>
        <div className="text-sm mt-1" style={{ color: 'var(--theme-text-muted)' }}>
          Joined {billing?.member_since ? new Date(billing.member_since).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' }) : '—'}
        </div>
      </div>

      <LocalizationPanel />

      {/* Iter 216h58 — drag-and-drop logo zone with auto-extracted
          brand-colour palette. Replaces the static button-only layout
          shipped in iter 216h57 — operators now drop a PNG/JPG and
          instantly see the dominant colours pulled from the image,
          one-click apply to set the org-wide primary brand colour. */}
      <div data-testid="account-section-logo">
        <h3 className="account-section-title">Organisation logo & brand colour</h3>
        <p className="account-section-sub">Drop a PNG / JPG. Brand colours are auto-extracted — one click applies them across invoices, member emails, and supplier case pages.</p>

        <div
          onDragOver={(e) => { if (canEditLogo) { e.preventDefault(); setDragOver(true); } }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onLogoDrop}
          className={`mt-3 relative rounded-xl border-2 border-dashed transition p-4 flex flex-col sm:flex-row gap-5 items-center ${dragOver ? 'border-[var(--theme-accent)] bg-[var(--theme-accent)]/5' : ''}`}
          style={{ borderColor: dragOver ? undefined : 'var(--theme-border)' }}
          data-testid="account-org-logo-dropzone"
        >
          <div className="relative w-24 h-24 shrink-0 rounded-xl flex items-center justify-center overflow-hidden" style={{ background: 'var(--theme-surface-sunken)', border: '1px solid var(--theme-border)' }}>
            {org?.logo_url ? (
              <img src={org.logo_url} alt={`${org?.name || 'Organisation'} logo`} className="max-w-full max-h-full object-contain" data-testid="account-org-logo-img" />
            ) : (
              <span className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>No logo</span>
            )}
            {logoUploading && (
              <div className="absolute inset-0 bg-black/60 flex items-center justify-center">
                <Loader2 size={20} className="animate-spin text-white" />
              </div>
            )}
          </div>

          <div className="flex-1 flex flex-col gap-2 min-w-0">
            <p className="text-xs font-semibold" style={{ color: 'var(--theme-text)' }}>
              {dragOver ? 'Drop to upload' : 'Drag & drop a logo here, or click the button.'}
            </p>
            <p className="text-[10px]" style={{ color: 'var(--theme-text-muted)' }}>
              PNG (transparent preferred), JPG or WebP — up to 8 MB. Auto-resized to 512px.
            </p>

            <input
              ref={logoFileRef} type="file" accept="image/png,image/jpeg,image/jpg,image/webp"
              onChange={onLogoFile} className="hidden" data-testid="account-org-logo-input"
            />
            <div className="flex flex-wrap gap-2 mt-1">
              <button
                type="button"
                onClick={() => logoFileRef.current?.click()}
                disabled={!canEditLogo || logoUploading}
                className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-wider px-3 py-1.5 border rounded-md transition disabled:opacity-50"
                style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
                data-testid="account-org-logo-upload-btn"
              >
                <Camera size={13} /> {org?.logo_url ? 'Replace logo' : 'Upload logo'}
              </button>
              {org?.logo_url && canEditLogo && (
                <button
                  type="button"
                  onClick={removeLogo}
                  disabled={logoUploading}
                  className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-wider px-3 py-1.5 hover:text-red-400 transition disabled:opacity-50"
                  style={{ color: 'var(--theme-text-muted)' }}
                  data-testid="account-org-logo-remove-btn"
                >
                  <Trash2 size={13} /> Remove
                </button>
              )}
              {!canEditLogo && (
                <p className="text-[10px]" style={{ color: 'var(--theme-text-muted)' }}>Only the Owner or a Manager can change the logo.</p>
              )}
            </div>
          </div>
        </div>

        {/* Extracted palette ─ tap to apply */}
        {(org?.brand_palette?.length || org?.primary_color) ? (
          <div className="mt-4" data-testid="account-org-palette">
            <p className="text-[11px] uppercase tracking-wider font-semibold mb-2" style={{ color: 'var(--theme-text-muted)' }}>
              Extracted brand palette {org?.primary_color ? <span className="ml-2 normal-case text-[10px]" style={{ color: 'var(--theme-text)' }}>· active: <span className="font-mono">{org.primary_color}</span></span> : null}
            </p>
            <div className="flex flex-wrap gap-2">
              {(org.brand_palette || []).map((hex) => {
                const active = (org?.primary_color || '').toUpperCase() === hex.toUpperCase();
                return (
                  <button
                    key={hex}
                    type="button"
                    onClick={() => canEditLogo && applyBrandColor(hex)}
                    disabled={!canEditLogo || applyingColor === hex}
                    className={`group relative w-16 h-16 rounded-lg border-2 transition flex flex-col items-center justify-end overflow-hidden disabled:opacity-50 ${active ? 'ring-2 ring-offset-2 ring-[var(--theme-accent)]' : 'hover:scale-[1.04]'}`}
                    style={{ background: hex, borderColor: active ? 'var(--theme-accent)' : 'var(--theme-border)' }}
                    data-testid={`account-org-palette-swatch-${hex.replace('#','').toLowerCase()}`}
                    title={active ? `${hex} — current brand colour` : `Apply ${hex} as brand colour`}
                  >
                    <span className="w-full bg-black/40 text-white text-[9px] font-mono py-0.5 backdrop-blur-sm">
                      {applyingColor === hex ? '…' : hex}
                    </span>
                  </button>
                );
              })}
              {!org?.brand_palette?.length && org?.primary_color && (
                <div
                  className="w-16 h-16 rounded-lg border flex items-end justify-center overflow-hidden"
                  style={{ background: org.primary_color, borderColor: 'var(--theme-border)' }}
                >
                  <span className="w-full bg-black/40 text-white text-[9px] font-mono py-0.5 text-center">
                    {org.primary_color}
                  </span>
                </div>
              )}
            </div>
            {canEditLogo && org?.brand_palette?.length > 0 && (
              <p className="mt-2 text-[10px]" style={{ color: 'var(--theme-text-muted)' }}>
                Click a swatch to set it as the organisation’s primary brand colour.
              </p>
            )}
          </div>
        ) : null}
      </div>

      <div>
        <h3 className="account-section-title">Registered address</h3>
        <p className="account-section-sub">Used on invoices, official emails, and admin records.</p>
        <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3">
          <FieldRow label="Address line 1">
            <input
              type="text" value={form.address_line1}
              onChange={(e) => update('address_line1', e.target.value)}
              disabled={!isOwner}
              className="account-input" data-testid="account-org-address1"
            />
          </FieldRow>
          <FieldRow label="Address line 2">
            <input
              type="text" value={form.address_line2}
              onChange={(e) => update('address_line2', e.target.value)}
              disabled={!isOwner}
              className="account-input" data-testid="account-org-address2"
            />
          </FieldRow>
          <FieldRow label="City">
            <input
              type="text" value={form.city}
              onChange={(e) => update('city', e.target.value)}
              disabled={!isOwner}
              className="account-input" data-testid="account-org-city"
            />
          </FieldRow>
          <FieldRow label="Postcode">
            <input
              type="text" value={form.postcode}
              onChange={(e) => update('postcode', e.target.value)}
              disabled={!isOwner}
              className="account-input" data-testid="account-org-postcode"
            />
          </FieldRow>
          <FieldRow label="Country">
            <input
              type="text" value={form.country}
              onChange={(e) => update('country', e.target.value)}
              disabled={!isOwner}
              className="account-input" data-testid="account-org-country"
            />
          </FieldRow>
          <FieldRow label="Website">
            <input
              type="url" placeholder="https://" value={form.website}
              onChange={(e) => update('website', e.target.value)}
              disabled={!isOwner}
              className="account-input" data-testid="account-org-website"
            />
          </FieldRow>
        </div>
      </div>

      <div>
        <h3 className="account-section-title">Primary contact</h3>
        <p className="account-section-sub">The point person we email about billing, downtime, and account issues.</p>
        <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3">
          <FieldRow label="Contact email">
            <input
              type="email" value={form.primary_contact_email}
              onChange={(e) => update('primary_contact_email', e.target.value)}
              disabled={!isOwner}
              className="account-input" data-testid="account-org-contact-email"
            />
          </FieldRow>
          <FieldRow label="Contact phone">
            <input
              type="tel" value={form.primary_contact_phone}
              onChange={(e) => update('primary_contact_phone', e.target.value)}
              disabled={!isOwner}
              className="account-input" data-testid="account-org-contact-phone"
            />
          </FieldRow>
          <FieldRow label="Main switchboard">
            <input
              type="tel" value={form.phone}
              onChange={(e) => update('phone', e.target.value)}
              disabled={!isOwner}
              className="account-input" data-testid="account-org-phone"
            />
          </FieldRow>
        </div>
      </div>

      {isOwner && (
        <div className="flex justify-end">
          <button
            type="button"
            onClick={save}
            disabled={saving}
            className="account-btn-primary"
            data-testid="account-org-save-btn"
          >
            {saving ? <Loader2 size={14} className="animate-spin" /> : null}
            Save organisation
          </button>
        </div>
      )}
      {!isOwner && (
        <p className="text-[11px]" style={{ color: 'var(--theme-text-muted)' }}>
          Only the organisation Owner can edit these details.
        </p>
      )}
    </div>
  );
}

