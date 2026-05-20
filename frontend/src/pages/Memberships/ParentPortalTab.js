/**
 * ParentPortalTab — Phase C (Iter 216ab)
 *
 * Operator-side controls for parent-portal features:
 *   1. Vocabulary preview (industry-driven nouns)
 *   2. Consent / waiver forms CRUD
 *   3. Push notification subscription stat
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  ShieldCheck, Bell, Loader2, Plus, Trash2, Save, Sparkles, Smartphone, FileText, ExternalLink, Eye,
} from 'lucide-react';
import { notify } from '@/components/notifications';

export default function ParentPortalTab({ API, headers }) {
  const auth = useMemo(() => ({ headers }), [headers]);
  const [vocab, setVocab] = useState(null);
  const [forms, setForms] = useState([]);
  const [pushCount, setPushCount] = useState(0);
  // Iter 216h250 — surface the studio slug so the operator can "Preview"
  // the customer-facing parent portal in a new tab.
  const [slug, setSlug] = useState('');
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState(null);
  const [draft, setDraft] = useState({ title: '', body_html: '', required: true });
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [v, f, p, o] = await Promise.all([
        axios.get(`${API}/memberships/studio/vocabulary`, auth),
        axios.get(`${API}/memberships/consent-forms`, auth),
        axios.get(`${API}/operator/push-subscriptions/count`, auth),
        axios.get(`${API}/account/organisation`, auth).catch(() => null),
      ]);
      setVocab(v.data || null);
      setForms(f.data?.forms || []);
      setPushCount(p.data?.count ?? 0);
      setSlug(o?.data?.slug || '');
    } catch (e) {
      notify.error('Failed to load parent portal', e?.response?.data?.detail || e.message);
    } finally { setLoading(false); }
  }, [API, auth]);
  useEffect(() => { load(); }, [load]);

  const previewParentPortal = () => {
    if (!slug) {
      notify.error('Set your studio slug first', 'Open the Memberships setup wizard to assign your app URL.');
      return;
    }
    window.open(`/m/${slug}`, '_blank', 'noopener,noreferrer');
  };

  const startNew = () => {
    setEditingId('new');
    setDraft({ title: '', body_html: '', required: true });
  };
  const startEdit = (form) => {
    setEditingId(form.id);
    setDraft({ title: form.title, body_html: form.body_html, required: !!form.required });
  };
  const cancelEdit = () => { setEditingId(null); setDraft({ title: '', body_html: '', required: true }); };

  const save = async () => {
    if (!draft.title.trim() || !draft.body_html.trim() || draft.body_html.length < 10) {
      notify.error('Missing fields', 'Title and at least 10 chars of body required');
      return;
    }
    setSaving(true);
    try {
      if (editingId === 'new') {
        await axios.post(`${API}/memberships/consent-forms`, draft, auth);
        notify.success('Form created');
      } else {
        await axios.put(`${API}/memberships/consent-forms/${editingId}`, draft, auth);
        notify.success('Form updated');
      }
      cancelEdit();
      await load();
    } catch (e) {
      notify.error('Save failed', e?.response?.data?.detail || e.message);
    } finally { setSaving(false); }
  };

  const remove = async (form) => {
    if (!window.confirm(`Archive "${form.title}"? Members already signed will keep their signatures on file.`)) return;
    try {
      await axios.delete(`${API}/memberships/consent-forms/${form.id}`, auth);
      await load();
    } catch (e) {
      notify.error('Delete failed', e?.response?.data?.detail || e.message);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground p-6" data-testid="parent-portal-loading">
        <Loader2 size={14} className="animate-spin" /> Loading parent portal…
      </div>
    );
  }

  return (
    <div className="space-y-5" data-testid="parent-portal-tab">
      {/* Iter 216h250 — Preview banner. Lets operators / managers see
          the customer-facing parent portal in a new tab. */}
      <section
        className="rounded-2xl border p-4 flex items-center gap-3 flex-wrap"
        style={{ borderColor: 'var(--theme-border, #e2e8f0)', background: 'var(--theme-surface, #fff)' }}
        data-testid="parent-portal-preview"
      >
        <div className="rounded-full p-2" style={{ background: 'rgba(34,211,238,0.12)' }}>
          <Eye size={16} style={{ color: 'var(--color-brand-cyan)' }} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-[11px] uppercase tracking-wider font-bold opacity-60">Preview</p>
          <h3 className="text-base font-bold">See it from a parent&apos;s phone</h3>
          <p className="text-[11px] opacity-70 mt-0.5">
            {slug
              ? <>Opens <code className="text-[10px] px-1 rounded bg-black/5 dark:bg-white/5">/m/{slug}</code> in a new tab — the same view your customers see.</>
              : <>Set your studio slug in the Memberships setup wizard to enable this preview.</>}
          </p>
        </div>
        <button
          type="button"
          onClick={previewParentPortal}
          disabled={!slug}
          className="px-3 py-2 rounded-lg text-xs font-extrabold inline-flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed"
          style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
          data-testid="parent-portal-preview-btn"
        >
          <ExternalLink size={12} /> Preview portal
        </button>
      </section>

      {/* Vocabulary preview */}
      <section
        className="rounded-2xl border p-4"
        style={{ borderColor: 'var(--theme-border, #e2e8f0)', background: 'var(--theme-surface, #fff)' }}
        data-testid="parent-portal-vocab"
      >
        <header className="flex items-start gap-2 flex-wrap mb-2">
          <div>
            <p className="text-[11px] uppercase tracking-wider font-bold opacity-60 inline-flex items-center gap-1">
              <Sparkles size={11} /> Studio vocabulary
            </p>
            <h3 className="text-base font-bold">Industry-aware copy across the parent portal</h3>
          </div>
        </header>
        <p className="text-[11.5px] opacity-70 mb-3">
          Your studio is set to <strong>{vocab?.label || 'Studio'}</strong>. The parent portal will refer to people as <strong>{vocab?.member_singular || 'member'}</strong> / <strong>{vocab?.member_plural || 'members'}</strong>, and parents/guardians as <strong>{vocab?.guardian_noun || 'guardian'}</strong>. Change your industry on the Studio Builder tab to update the vocabulary everywhere.
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2" data-testid="parent-portal-vocab-grid">
          <Stat label="Member (singular)" value={vocab?.member_singular || '—'} />
          <Stat label="Members (plural)" value={vocab?.member_plural || '—'} />
          <Stat label="Guardian" value={vocab?.guardian_noun || '—'} />
          <Stat label="Studio label" value={vocab?.label || '—'} />
        </div>
      </section>

      {/* Push subscriptions */}
      <section
        className="rounded-2xl border p-4 flex items-center gap-3 flex-wrap"
        style={{ borderColor: 'var(--theme-border, #e2e8f0)', background: 'var(--theme-surface, #fff)' }}
        data-testid="parent-portal-push"
      >
        <div className="rounded-full p-2" style={{ background: 'rgba(59,130,246,0.12)' }}>
          <Bell size={16} className="text-blue-600" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-[11px] uppercase tracking-wider font-bold opacity-60 inline-flex items-center gap-1">
            <Smartphone size={11} /> Push notifications
          </p>
          <h3 className="text-base font-bold">
            {pushCount.toLocaleString()} {vocab?.member_plural || 'members'} subscribed
          </h3>
          <p className="text-[11px] opacity-70 mt-0.5">
            Members opt-in from the Parent Portal. Reach them with class reminders, schedule changes, and trial-class reminders without paying for SMS.
          </p>
        </div>
      </section>

      {/* Consent forms */}
      <section
        className="rounded-2xl border p-4"
        style={{ borderColor: 'var(--theme-border, #e2e8f0)', background: 'var(--theme-surface, #fff)' }}
        data-testid="parent-portal-forms"
      >
        <header className="flex items-start justify-between flex-wrap gap-2 mb-3">
          <div>
            <p className="text-[11px] uppercase tracking-wider font-bold opacity-60 inline-flex items-center gap-1">
              <ShieldCheck size={11} /> Consent & waivers
            </p>
            <h3 className="text-base font-bold">Forms parents must sign before booking</h3>
            <p className="text-[11.5px] opacity-70 mt-1">Editing a form's body increments its version — every member must re-sign. Archived forms keep their old signatures on file.</p>
          </div>
          <button type="button" onClick={startNew} className="px-3 py-1.5 rounded-lg text-xs font-bold inline-flex items-center gap-1.5" style={{ background: 'var(--color-brand-blue, #1d4ed8)', color: '#fff' }} data-testid="parent-portal-form-new">
            <Plus size={11} /> New form
          </button>
        </header>

        {editingId ? (
          <div className="rounded-xl border p-3 space-y-2" style={{ borderColor: 'var(--theme-border)' }} data-testid="parent-portal-form-editor">
            <label className="block">
              <span className="text-[11px] font-bold opacity-70">Title</span>
              <input value={draft.title} onChange={(e) => setDraft((d) => ({ ...d, title: e.target.value }))} className="w-full px-2 py-1 text-sm rounded border" style={{ borderColor: 'var(--theme-border)' }} data-testid="parent-portal-form-title" />
            </label>
            <label className="block">
              <span className="text-[11px] font-bold opacity-70">Body (HTML supported)</span>
              <textarea rows={6} value={draft.body_html} onChange={(e) => setDraft((d) => ({ ...d, body_html: e.target.value }))} className="w-full px-2 py-1 text-sm rounded border font-mono" style={{ borderColor: 'var(--theme-border)' }} data-testid="parent-portal-form-body" />
            </label>
            <label className="inline-flex items-center gap-2 text-xs">
              <input type="checkbox" checked={draft.required} onChange={(e) => setDraft((d) => ({ ...d, required: e.target.checked }))} data-testid="parent-portal-form-required" />
              Required before first booking
            </label>
            <div className="flex items-center gap-2 justify-end">
              <button type="button" onClick={cancelEdit} className="px-2 py-1 rounded text-xs border" style={{ borderColor: 'var(--theme-border)' }} data-testid="parent-portal-form-cancel">Cancel</button>
              <button type="button" onClick={save} disabled={saving} className="px-3 py-1.5 rounded text-xs font-bold inline-flex items-center gap-1" style={{ background: 'var(--color-brand-blue, #1d4ed8)', color: '#fff', opacity: saving ? 0.6 : 1 }} data-testid="parent-portal-form-save">
                {saving ? <Loader2 size={11} className="animate-spin" /> : <Save size={11} />} Save
              </button>
            </div>
          </div>
        ) : null}

        <ul className="space-y-2 mt-3" data-testid="parent-portal-form-list">
          {forms.length === 0 ? (
            <li className="text-center py-6 px-3 rounded-xl border-2 border-dashed" style={{ borderColor: 'var(--theme-border, #e2e8f0)' }}>
              <FileText size={22} className="mx-auto mb-1 opacity-50" />
              <p className="text-sm font-bold">No forms yet</p>
              <p className="text-xs opacity-70 mt-1">Add your photography consent, medical waiver, or studio rules so parents can sign once and book everywhere.</p>
            </li>
          ) : forms.map((f) => (
            <li key={f.id} className="flex items-start gap-3 p-3 rounded-lg border" style={{ borderColor: 'var(--theme-border, #e2e8f0)' }} data-testid={`parent-portal-form-${f.id}`}>
              <div className="rounded-full p-1.5 mt-0.5" style={{ background: 'rgba(16,185,129,0.12)' }}>
                <ShieldCheck size={14} className="text-emerald-600" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-bold truncate inline-flex items-center gap-2">
                  {f.title}
                  <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 dark:bg-zinc-800">v{f.version}</span>
                  {f.required ? <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-amber-100 text-amber-800">required</span> : null}
                </p>
                <div className="text-[11px] opacity-70 line-clamp-2 mt-0.5" dangerouslySetInnerHTML={{ __html: f.body_html }} />
              </div>
              <button type="button" onClick={() => startEdit(f)} className="px-2 py-1 rounded text-[11px] border" style={{ borderColor: 'var(--theme-border)' }} data-testid={`parent-portal-form-edit-${f.id}`}>
                Edit
              </button>
              <button type="button" onClick={() => remove(f)} className="px-2 py-1 rounded text-[11px] border" style={{ borderColor: 'var(--theme-border)' }} data-testid={`parent-portal-form-delete-${f.id}`}>
                <Trash2 size={11} />
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div className="rounded-lg border p-2" style={{ borderColor: 'var(--theme-border, #e2e8f0)' }}>
      <p className="text-[10px] uppercase tracking-wider opacity-60 font-bold">{label}</p>
      <p className="text-sm font-bold mt-0.5 capitalize">{value}</p>
    </div>
  );
}
