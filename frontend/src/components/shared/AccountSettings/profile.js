import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Camera, Loader2, Trash2 } from 'lucide-react';
import { useAuth } from '@/App';
import { API, useAuthHeaders, FieldRow } from './shared';


export default function ProfileSection({ profile, onProfileUpdate }) {
  const headers = useAuthHeaders();
  const [fullName, setFullName] = useState(profile?.full_name || '');
  const [phone, setPhone] = useState(profile?.phone || '');
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef(null);

  useEffect(() => {
    setFullName(profile?.full_name || '');
    setPhone(profile?.phone || '');
  }, [profile?.full_name, profile?.phone]);

  const initials = (fullName || profile?.email || '?').slice(0, 1).toUpperCase();

  const save = async () => {
    setSaving(true);
    try {
      const { data } = await axios.patch(`${API}/account/profile`,
        { full_name: fullName, phone }, { headers: headers() });
      onProfileUpdate(data);
      toast.success('Profile updated');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Could not update profile');
    }
    setSaving(false);
  };

  const onFile = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append('file', f);
      const { data } = await axios.post(`${API}/account/avatar`, fd, {
        headers: { ...headers(), 'Content-Type': 'multipart/form-data' },
      });
      onProfileUpdate({ ...profile, avatar_url: data.avatar_url });
      toast.success('Avatar updated');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Upload failed');
    }
    setUploading(false);
    if (fileRef.current) fileRef.current.value = '';
  };

  const removeAvatar = async () => {
    setUploading(true);
    try {
      await axios.delete(`${API}/account/avatar`, { headers: headers() });
      onProfileUpdate({ ...profile, avatar_url: null });
      toast.success('Avatar removed');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Remove failed');
    }
    setUploading(false);
  };

  return (
    <div className="space-y-6" data-testid="account-section-profile">
      <div className="flex items-center gap-5">
        <div className="relative">
          {profile?.avatar_url ? (
            <img
              src={profile.avatar_url}
              alt="avatar"
              className="w-20 h-20 rounded-full object-cover"
              style={{ border: '1px solid var(--theme-border)' }}
              data-testid="account-avatar-img"
            />
          ) : (
            <div className="account-avatar-placeholder w-20 h-20 rounded-full flex items-center justify-center text-2xl font-bold">
              {initials}
            </div>
          )}
          {uploading && (
            <div className="absolute inset-0 rounded-full bg-black/60 flex items-center justify-center">
              <Loader2 size={20} className="animate-spin text-white" />
            </div>
          )}
        </div>
        <div className="flex flex-col gap-2">
          <input ref={fileRef} type="file" accept="image/*"
            onChange={onFile} className="hidden" data-testid="account-avatar-input" />
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-wider px-3 py-1.5 border rounded-md transition disabled:opacity-50"
            style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
            data-testid="account-avatar-upload-btn"
          >
            <Camera size={13} /> Upload photo
          </button>
          {profile?.avatar_url && (
            <button
              type="button"
              onClick={removeAvatar}
              disabled={uploading}
              className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-wider px-3 py-1.5 hover:text-red-400 transition disabled:opacity-50"
              style={{ color: 'var(--theme-text-muted)' }}
              data-testid="account-avatar-remove-btn"
            >
              <Trash2 size={13} /> Remove
            </button>
          )}
          <p className="text-[10px]" style={{ color: 'var(--theme-text-muted)' }}>
            JPG / PNG. Auto-cropped to a 256×256 thumbnail.
          </p>
        </div>
      </div>

      <FieldRow label="Full name">
        <input
          type="text"
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          className="account-input"
          data-testid="account-full-name-input"
        />
      </FieldRow>
      <FieldRow label="Email">
        <input
          type="email"
          value={profile?.email || ''}
          readOnly
          disabled
          className="account-input opacity-60 cursor-not-allowed"
          data-testid="account-email-input"
        />
        <p className="text-[10px] mt-1" style={{ color: 'var(--theme-text-muted)' }}>
          Contact your team admin or support to change this.
        </p>
      </FieldRow>
      <FieldRow label="Phone">
        <input
          type="tel"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          placeholder="+44 7700 900123"
          className="account-input"
          data-testid="account-phone-input"
        />
      </FieldRow>

      <div className="flex justify-end">
        <button
          type="button"
          onClick={save}
          disabled={saving}
          className="account-btn-primary"
          data-testid="account-profile-save-btn"
        >
          {saving ? <Loader2 size={14} className="animate-spin" /> : null}
          Save changes
        </button>
      </div>
    </div>
  );
}

