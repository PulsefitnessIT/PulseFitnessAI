/**
 * Canned Replies — Master Admin → Growth (Iter 216h100).
 *
 * Global library of reusable reply templates surfaced inside the
 * Communications Inbox reply composer. Master Admin can CRUD these
 * here; every admin sees the same set. Designed for the most common
 * sales-enquiry response patterns (pricing intro, demo invite,
 * security questionnaire ack, "out of office" holding reply, etc.).
 */
import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import {
  FileText, Plus, Trash2, Pencil, X, Save, RefreshCw,
} from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

function authHeader() {
  const token = localStorage.getItem('token') || localStorage.getItem('gymaxis_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

const EMPTY = { id: null, label: '', subject: '', body: '' };

export default function AdminCannedReplies() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState(null);  // either null or { id?, label, subject, body }

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/master-admin/canned-replies`, { headers: authHeader() });
      setItems(r.data?.items || []);
    } catch (e) {
      toast.error('Failed to load canned replies');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const remove = async (id) => {
    if (!window.confirm('Delete this template? This cannot be undone.')) return;
    try {
      await axios.delete(`${API}/master-admin/canned-replies/${id}`, { headers: authHeader() });
      toast.success('Template deleted.');
      await load();
    } catch (e) {
      toast.error('Delete failed');
    }
  };

  return (
    <div className="space-y-5" data-testid="admin-canned-replies">
      <div className="bg-white border border-zinc-200 rounded-2xl p-5 shadow-sm">
        <div className="flex items-center justify-between gap-4 mb-1">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-violet-50">
              <FileText size={18} className="text-violet-700" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-zinc-900">Canned reply templates</h2>
              <p className="text-xs text-zinc-500">Reusable replies surfaced inside the Communications inbox &quot;Send a reply&quot; composer.</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={load}
              disabled={loading}
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-zinc-700 hover:text-zinc-900 disabled:opacity-50"
              data-testid="canned-refresh"
            >
              <RefreshCw size={13} className={loading ? 'animate-spin' : ''} /> Refresh
            </button>
            <button
              type="button"
              onClick={() => setEditing({ ...EMPTY })}
              className="inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-xs font-semibold"
              style={{ background: '#0F172A', color: '#FFFFFF' }}
              data-testid="canned-new"
            >
              <Plus size={12} /> New template
            </button>
          </div>
        </div>
      </div>

      {items.length === 0 && !loading ? (
        <div className="bg-white border border-zinc-200 rounded-2xl py-14 text-center" data-testid="canned-empty">
          <FileText size={32} className="mx-auto text-zinc-300" />
          <p className="mt-2 text-sm text-zinc-500">No templates yet. Click <strong>New template</strong> to add one.</p>
        </div>
      ) : (
        <div className="bg-white border border-zinc-200 rounded-2xl overflow-hidden">
          <div className="divide-y divide-zinc-100">
            {items.map((it) => (
              <div key={it.id} className="px-5 py-4 flex items-start gap-4" data-testid={`canned-row-${it.id}`}>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold text-zinc-900">{it.label}</div>
                  <div className="text-xs text-zinc-500 mt-0.5 truncate">{it.subject}</div>
                  <div className="text-xs text-zinc-500 mt-1 line-clamp-2 whitespace-pre-wrap">{it.body}</div>
                </div>
                <div className="flex items-center gap-1 flex-shrink-0">
                  <button
                    type="button"
                    onClick={() => setEditing({ ...it })}
                    className="rounded-md p-1.5 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900"
                    aria-label="Edit"
                    data-testid={`canned-edit-${it.id}`}
                  >
                    <Pencil size={14} />
                  </button>
                  <button
                    type="button"
                    onClick={() => remove(it.id)}
                    className="rounded-md p-1.5 text-rose-500 hover:bg-rose-50 hover:text-rose-700"
                    aria-label="Delete"
                    data-testid={`canned-delete-${it.id}`}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {editing && (
        <EditorModal
          template={editing}
          onClose={() => setEditing(null)}
          onSaved={async () => { setEditing(null); await load(); }}
        />
      )}
    </div>
  );
}

function EditorModal({ template, onClose, onSaved }) {
  const [draft, setDraft] = useState(template);
  const [saving, setSaving] = useState(false);
  const isNew = !template.id;

  const save = async () => {
    if (!draft.label.trim() || !draft.subject.trim() || !draft.body.trim()) {
      toast.error('Label, subject and body are required.');
      return;
    }
    setSaving(true);
    try {
      const payload = { label: draft.label, subject: draft.subject, body: draft.body };
      if (isNew) {
        await axios.post(`${API}/master-admin/canned-replies`, payload, { headers: authHeader() });
        toast.success('Template created.');
      } else {
        await axios.put(`${API}/master-admin/canned-replies/${draft.id}`, payload, { headers: authHeader() });
        toast.success('Template updated.');
      }
      onSaved();
    } catch (e) {
      const msg = e.response?.data?.detail || 'Save failed';
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" data-testid="canned-editor">
      <button type="button" aria-label="Close" onClick={onClose} className="absolute inset-0 bg-zinc-900/40 backdrop-blur-sm" />
      <div className="relative w-full max-w-xl bg-white border border-zinc-200 rounded-2xl shadow-2xl overflow-hidden">
        <div className="px-6 py-4 border-b border-zinc-100 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-zinc-900">{isNew ? 'New canned reply' : 'Edit canned reply'}</h3>
          <button type="button" onClick={onClose} className="text-zinc-500 hover:text-zinc-900"><X size={16} /></button>
        </div>
        <div className="p-6 space-y-3">
          <Field label="Label (only visible to admins)" value={draft.label} onChange={(v) => setDraft((d) => ({ ...d, label: v }))} testid="canned-edit-label" placeholder="e.g. Pricing intro" />
          <Field label="Email subject" value={draft.subject} onChange={(v) => setDraft((d) => ({ ...d, subject: v }))} testid="canned-edit-subject" placeholder="Re: your enquiry…" />
          <div>
            <label className="text-xs font-semibold text-zinc-700">Body</label>
            <textarea
              value={draft.body}
              onChange={(e) => setDraft((d) => ({ ...d, body: e.target.value }))}
              rows={8}
              className="mt-1 w-full rounded-lg border border-zinc-200 px-3 py-2 text-sm focus:outline-none focus:border-zinc-400"
              placeholder="Hi {{first_name}}, …"
              data-testid="canned-edit-body"
            />
            <p className="text-[11px] text-zinc-400 mt-1">The reply composer pre-fills with this body. Operators can edit before sending.</p>
          </div>
        </div>
        <div className="px-6 py-4 border-t border-zinc-100 bg-zinc-50/60 flex items-center justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-full border border-zinc-200 bg-white px-4 py-2 text-xs font-semibold text-zinc-700 hover:bg-zinc-50">Cancel</button>
          <button
            type="button"
            onClick={save}
            disabled={saving}
            className="inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-xs font-semibold disabled:opacity-50"
            style={{ background: '#0F172A', color: '#FFFFFF' }}
            data-testid="canned-save"
          >
            <Save size={12} /> {saving ? 'Saving…' : isNew ? 'Create template' : 'Save changes'}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, value, onChange, testid, placeholder }) {
  return (
    <label className="block">
      <span className="text-xs font-semibold text-zinc-700">{label}</span>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="mt-1 w-full rounded-lg border border-zinc-200 px-3 py-2 text-sm focus:outline-none focus:border-zinc-400"
        data-testid={testid}
      />
    </label>
  );
}
