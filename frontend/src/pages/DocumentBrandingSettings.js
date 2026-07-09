import { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import { Upload, Save, FileText, Image as ImageIcon, Loader2 } from 'lucide-react';

const TEXT_FIELDS = [
  'company_name', 'tagline', 'phone', 'email', 'web',
  'registered_office', 'company_reg', 'vat_reg',
  'bank_name', 'bank_account_name', 'bank_account_number', 'bank_sort_code',
  'payment_terms', 'footer_note', 'accent_color',
];

const GROUPS = [
  {
    title: 'Header',
    hint: 'Logo and contact block shown at the top of every document.',
    fields: [
      ['company_name', 'Company name'],
      ['tagline', 'Tagline'],
      ['phone', 'Phone'],
      ['email', 'Email'],
      ['web', 'Website'],
    ],
  },
  {
    title: 'Bank / payment details',
    hint: 'Printed on member statements and invoices so customers can pay you.',
    fields: [
      ['bank_name', 'Bank name'],
      ['bank_account_name', 'Account name'],
      ['bank_account_number', 'Account number'],
      ['bank_sort_code', 'Sort code'],
      ['payment_terms', 'Payment terms'],
    ],
  },
  {
    title: 'Legal footer',
    hint: 'Registered office / company & VAT numbers shown on every page.',
    fields: [
      ['registered_office', 'Registered office'],
      ['company_reg', 'Company registration no.'],
      ['vat_reg', 'VAT registration no.'],
      ['footer_note', 'Footer note'],
    ],
  },
];

const DocumentBrandingSettings = ({ API }) => {
  const [profile, setProfile] = useState(null);
  const [placeholders, setPlaceholders] = useState({});
  const [canEdit, setCanEdit] = useState(false);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [loading, setLoading] = useState(true);
  const fileRef = useRef(null);

  const token = () => localStorage.getItem('token');

  useEffect(() => {
    (async () => {
      try {
        const res = await axios.get(`${API}/document-branding`, { headers: { Authorization: `Bearer ${token()}` } });
        setProfile(res.data.profile || {});
        setPlaceholders(res.data.placeholders || {});
        setCanEdit(!!res.data.can_edit);
      } catch (e) {
        notifyApiError(notify, e, 'Failed to load document branding');
      } finally {
        setLoading(false);
      }
    })();
  }, [API]);

  const setField = (k, v) => setProfile(p => ({ ...p, [k]: v }));

  const handleLogo = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const res = await axios.post(`${API}/files/upload?category=branding`, fd, {
        headers: { Authorization: `Bearer ${token()}`, 'Content-Type': 'multipart/form-data' },
      });
      setProfile(p => ({
        ...p,
        logo_file_id: res.data.id || '',
        logo_storage_path: res.data.storage_path || '',
        logo_url: res.data.download_url || '',
      }));
      notify.success('Logo uploaded — save to apply');
    } catch (err) {
      notifyApiError(notify, err, 'Logo upload failed');
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload = {};
      TEXT_FIELDS.forEach(f => { payload[f] = profile[f] || ''; });
      ['logo_file_id', 'logo_storage_path', 'logo_url'].forEach(f => { payload[f] = profile[f] || ''; });
      const res = await axios.put(`${API}/document-branding`, payload, { headers: { Authorization: `Bearer ${token()}` } });
      setProfile(res.data.profile || profile);
      notify.success('Document branding saved');
    } catch (e) {
      notifyApiError(notify, e, 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  const handleSample = async () => {
    try {
      const res = await axios.get(`${API}/document-branding/sample.pdf`, {
        headers: { Authorization: `Bearer ${token()}` }, responseType: 'blob',
      });
      const url = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      window.open(url, '_blank');
    } catch (e) {
      notifyApiError(notify, e, 'Failed to generate sample');
    }
  };

  if (loading || !profile) {
    return <div className="py-12 text-center text-[var(--color-text-muted)]" data-testid="docbranding-loading">
      <Loader2 className="w-5 h-5 animate-spin inline mr-2" />Loading…</div>;
  }

  return (
    <div className="space-y-6" data-testid="document-branding-section">
      <Card className="p-6 bg-[var(--theme-card)] border-white/10">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h3 className="text-lg font-semibold text-[var(--theme-text)] flex items-center gap-2">
              <FileText className="w-5 h-5" /> Document branding
            </h3>
            <p className="text-sm text-[var(--color-text-muted)] mt-1 max-w-2xl">
              Set your own logo, company details, bank details and footer. These appear on your
              generated documents (member statements first). Leave a field blank to omit it.
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={handleSample} data-testid="docbranding-sample-btn">
              <ImageIcon className="w-4 h-4 mr-1" /> Download sample PDF
            </Button>
            {canEdit && (
              <Button size="sm" onClick={handleSave} disabled={saving}
                className="text-[var(--theme-text)]" style={{ backgroundColor: 'var(--brand-color)' }}
                data-testid="docbranding-save-btn">
                {saving ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Save className="w-4 h-4 mr-1" />}
                Save
              </Button>
            )}
          </div>
        </div>

        {!canEdit && (
          <p className="mt-3 text-xs text-amber-500" data-testid="docbranding-readonly">
            You can preview but only owners and managers can edit document branding.
          </p>
        )}

        {/* Logo */}
        <div className="mt-6 flex items-center gap-4" data-testid="docbranding-logo-row">
          <div className="w-24 h-24 rounded-lg border border-white/10 bg-white flex items-center justify-center overflow-hidden">
            {profile.logo_url
              ? <img src={profile.logo_url} alt="Logo" className="max-w-full max-h-full object-contain" data-testid="docbranding-logo-preview" />
              : <ImageIcon className="w-8 h-8 text-slate-300" />}
          </div>
          <div>
            <Label className="text-[var(--theme-text)]">Logo</Label>
            <p className="text-xs text-[var(--color-text-muted)] mb-2">PNG, JPG or SVG. Shown top-left on documents.</p>
            <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={handleLogo}
              data-testid="docbranding-logo-input" disabled={!canEdit} />
            <Button variant="outline" size="sm" onClick={() => fileRef.current?.click()} disabled={!canEdit || uploading}
              data-testid="docbranding-logo-upload-btn">
              {uploading ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Upload className="w-4 h-4 mr-1" />}
              Upload logo
            </Button>
          </div>
        </div>
      </Card>

      {GROUPS.map(group => (
        <Card key={group.title} className="p-6 bg-[var(--theme-card)] border-white/10">
          <h4 className="font-semibold text-[var(--theme-text)]">{group.title}</h4>
          <p className="text-xs text-[var(--color-text-muted)] mb-4">{group.hint}</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {group.fields.map(([key, label]) => (
              <div key={key}>
                <Label className="text-[var(--theme-text)] text-sm">{label}</Label>
                <Input
                  value={profile[key] || ''}
                  onChange={e => setField(key, e.target.value)}
                  placeholder={placeholders[key] || ''}
                  disabled={!canEdit}
                  data-testid={`docbranding-field-${key}`}
                  className="mt-1"
                />
              </div>
            ))}
          </div>
        </Card>
      ))}
    </div>
  );
};

export default DocumentBrandingSettings;
