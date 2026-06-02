/**
 * Account Settings → Suppliers section.
 * (Iter 216h113j).
 *
 * Lets owners/managers maintain the org's supplier directory:
 *   name · primary contact · email · phone · manufacturer-match
 *
 * Supplier records auto-link to equipment by manufacturer. When a
 * fault is logged on a machine whose manufacturer matches a supplier
 * `manufacturer_keywords` entry, the fault notification routes to
 * that supplier automatically. MOD managers in particular need this
 * — different installations have different DIO / DEFCON suppliers.
 *
 * Hits `/api/suppliers` (existing routes — POST, GET, PUT, DELETE).
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import {
  Plus, Trash2, Pencil, X, Loader2, Truck, Mail, Phone, User, Tag,
  AlertTriangle, CheckCircle2,
} from 'lucide-react';
import { API, useAuthHeaders } from './shared';

const BLANK = {
  name: '', contact_name: '', email: '', phone: '',
  manufacturer_keywords: '',
};

export default function SuppliersSection() {
  const headers = useAuthHeaders();
  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(BLANK);
  const [submitting, setSubmitting] = useState(false);
  // Iter 220ea·40 — dispatch readiness: which machines won't auto-email a
  // supplier on fault submit (supplier has no email / isn't in directory).
  const [readiness, setReadiness] = useState(null);

  const loadReadiness = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/suppliers/dispatch-readiness`, { headers: headers() });
      setReadiness(r.data || null);
    } catch { /* non-blocking */ }
  }, [headers]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/suppliers`, { headers: headers() });
      setList(r.data?.suppliers || r.data || []);
    } catch (e) {
      toast.error('Could not load suppliers');
    } finally {
      setLoading(false);
    }
  }, [headers]);

  useEffect(() => { load(); loadReadiness(); }, [load, loadReadiness]);

  const openNew = () => { setEditing({}); setForm(BLANK); };
  const openEdit = (s) => {
    setEditing(s);
    setForm({
      name: s.name || '',
      contact_name: s.contact_name || '',
      email: s.email || '',
      phone: s.phone || '',
      manufacturer_keywords: Array.isArray(s.manufacturer_keywords)
        ? s.manufacturer_keywords.join(', ')
        : (s.manufacturer_keywords || ''),
    });
  };
  const close = () => { setEditing(null); setForm(BLANK); };

  const submit = async (e) => {
    e?.preventDefault?.();
    if (!form.name?.trim()) { toast.error('Name is required'); return; }
    setSubmitting(true);
    try {
      const body = {
        name: form.name.trim(),
        contact_name: form.contact_name.trim() || undefined,
        email: form.email.trim() || undefined,
        phone: form.phone.trim() || undefined,
        manufacturer_keywords: form.manufacturer_keywords
          ? form.manufacturer_keywords.split(',').map((s) => s.trim()).filter(Boolean)
          : [],
      };
      if (editing && editing.id) {
        await axios.put(`${API}/suppliers/${editing.id}`, body, { headers: headers() });
        toast.success('Supplier updated');
      } else {
        await axios.post(`${API}/suppliers`, body, { headers: headers() });
        toast.success('Supplier added');
      }
      close(); load(); loadReadiness();
    } catch (e) {
      const msg = e?.response?.data?.detail || 'Save failed';
      toast.error(typeof msg === 'string' ? msg : 'Save failed');
    } finally { setSubmitting(false); }
  };

  // Quick-fix a blocked supplier: open its editor (add email) or, if the
  // machine references a supplier not in the directory, pre-fill Add.
  const fixBlocked = (b) => {
    if (b.supplier_id) {
      const s = list.find((x) => x.id === b.supplier_id);
      if (s) { openEdit(s); return; }
    }
    setEditing({}); setForm({ ...BLANK, name: b.name || '' });
  };

  const remove = async (s) => {
    if (!window.confirm(`Remove supplier "${s.name}"?\n\nEquipment currently linked to this supplier will be left unassigned.`)) return;
    try {
      await axios.delete(`${API}/suppliers/${s.id}`, { headers: headers() });
      toast.success('Supplier removed');
      load(); loadReadiness();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Could not remove');
    }
  };

  return (
    <section className="space-y-4" data-testid="account-suppliers-section">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-bold" style={{ color: 'var(--theme-text)' }}>Suppliers</h3>
          <p className="text-sm mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>
            Manage equipment suppliers — fault notifications route to the
            matching supplier automatically when a machine's manufacturer
            matches one of their keywords.
          </p>
        </div>
        <button type="button" onClick={openNew} className="account-btn-primary inline-flex items-center gap-1.5" data-testid="account-suppliers-add">
          <Plus size={14} /> Add supplier
        </button>
      </header>

      {/* Iter 220ea·40 — fault auto-dispatch readiness. */}
      {readiness && (readiness.machines_blocked > 0 || (readiness.blocked_suppliers || []).length > 0) ? (
        <div className="rounded-xl border p-4" style={{ background: 'rgba(245,158,11,0.08)', borderColor: 'rgba(245,158,11,0.3)' }} data-testid="supplier-dispatch-readiness-warning">
          <div className="flex items-start gap-2.5">
            <AlertTriangle size={18} className="shrink-0 mt-0.5" style={{ color: '#f59e0b' }} />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-bold" style={{ color: 'var(--theme-text)' }}>
                {readiness.machines_blocked} machine{readiness.machines_blocked === 1 ? '' : 's'} won&rsquo;t auto-dispatch faults
              </p>
              <p className="text-xs mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>
                When a fault is logged on these machines, no supplier is emailed because the linked supplier has no email address (or isn&rsquo;t in your directory). Add an email to fix it.
              </p>
              <ul className="mt-3 space-y-1.5">
                {(readiness.blocked_suppliers || []).map((b) => (
                  <li key={`${b.supplier_id || b.name}`} className="flex items-center justify-between gap-3 text-xs rounded-lg px-3 py-2" style={{ background: 'var(--theme-surface)' }} data-testid={`blocked-supplier-${b.supplier_id || b.name}`}>
                    <span className="min-w-0 truncate" style={{ color: 'var(--theme-text)' }}>
                      <strong>{b.name}</strong>
                      <span style={{ color: 'var(--theme-text-muted)' }}> · {b.machine_count} machine{b.machine_count === 1 ? '' : 's'} · {b.reason === 'not_in_directory' ? 'not in directory' : 'no email'}</span>
                    </span>
                    <button type="button" onClick={() => fixBlocked(b)} className="account-btn-secondary inline-flex items-center gap-1 shrink-0 text-xs" data-testid={`fix-blocked-supplier-${b.supplier_id || b.name}`}>
                      <Mail size={11} /> {b.reason === 'not_in_directory' ? 'Add supplier' : 'Add email'}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      ) : readiness && readiness.total_machines > 0 ? (
        <div className="rounded-xl border p-3 flex items-center gap-2.5" style={{ background: 'rgba(16,185,129,0.08)', borderColor: 'rgba(16,185,129,0.25)' }} data-testid="supplier-dispatch-readiness-ok">
          <CheckCircle2 size={16} className="shrink-0" style={{ color: '#10b981' }} />
          <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>
            <strong style={{ color: 'var(--theme-text)' }}>{readiness.machines_ready} machine{readiness.machines_ready === 1 ? '' : 's'}</strong> will auto-email their supplier on fault submit.
            {readiness.machines_no_supplier > 0 && ` ${readiness.machines_no_supplier} have no supplier set.`}
          </p>
        </div>
      ) : null}

      <div className="rounded-xl border overflow-hidden" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
        {loading ? (
          <div className="p-8 text-center text-sm" style={{ color: 'var(--theme-text-muted)' }}>
            <Loader2 size={16} className="animate-spin inline mr-2" /> Loading suppliers…
          </div>
        ) : list.length === 0 ? (
          <div className="p-8 text-center text-sm" style={{ color: 'var(--theme-text-muted)' }} data-testid="account-suppliers-empty">
            <Truck size={28} className="mx-auto mb-2 opacity-50" />
            No suppliers yet. Click <strong>Add supplier</strong> above.
          </div>
        ) : (
          <ul className="divide-y" style={{ borderColor: 'var(--theme-border)' }}>
            {list.map((s) => (
              <li key={s.id} className="p-4 flex items-start gap-3" data-testid={`account-supplier-row-${s.id}`}>
                <div className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0" style={{ background: 'var(--theme-bg)', color: 'var(--color-brand-blue)' }}>
                  <Truck size={16} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-semibold text-sm" style={{ color: 'var(--theme-text)' }}>{s.name}</div>
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs mt-1" style={{ color: 'var(--theme-text-muted)' }}>
                    {s.contact_name && <span className="inline-flex items-center gap-1"><User size={11} /> {s.contact_name}</span>}
                    {s.email && <span className="inline-flex items-center gap-1"><Mail size={11} /> {s.email}</span>}
                    {s.phone && <span className="inline-flex items-center gap-1"><Phone size={11} /> {s.phone}</span>}
                  </div>
                  {Array.isArray(s.manufacturer_keywords) && s.manufacturer_keywords.length > 0 && (
                    <div className="flex flex-wrap items-center gap-1.5 mt-2">
                      <Tag size={11} style={{ color: 'var(--theme-text-muted)' }} />
                      {s.manufacturer_keywords.map((kw) => (
                        <span key={kw} className="text-[10px] uppercase tracking-wider font-bold px-1.5 py-0.5 rounded" style={{ background: 'rgba(102,204,255,0.10)', color: 'var(--color-brand-blue)' }}>
                          {kw}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  <button type="button" onClick={() => openEdit(s)} className="p-1.5 rounded-md" style={{ color: 'var(--theme-text-muted)' }} data-testid={`account-supplier-edit-${s.id}`} aria-label="Edit">
                    <Pencil size={14} />
                  </button>
                  <button type="button" onClick={() => remove(s)} className="p-1.5 rounded-md" style={{ color: 'var(--color-status-error, #DC2626)' }} data-testid={`account-supplier-delete-${s.id}`} aria-label="Remove">
                    <Trash2 size={14} />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {editing !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.55)' }} data-testid="account-supplier-modal">
          <form onSubmit={submit} className="rounded-2xl w-full max-w-lg p-6 relative" style={{ background: 'var(--theme-surface)' }}>
            <button type="button" onClick={close} className="absolute right-4 top-4 p-1.5 rounded-full" aria-label="Close" data-testid="account-supplier-close">
              <X size={16} />
            </button>
            <h4 className="text-base font-bold mb-4" style={{ color: 'var(--theme-text)' }}>
              {editing.id ? `Edit ${editing.name}` : 'Add supplier'}
            </h4>
            <div className="space-y-3">
              <SupField label="Supplier name *" testid="supplier-field-name">
                <input className="account-input" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Technogym UK" />
              </SupField>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <SupField label="Primary contact" testid="supplier-field-contact-name">
                  <input className="account-input" value={form.contact_name} onChange={(e) => setForm({ ...form, contact_name: e.target.value })} placeholder="John Smith" />
                </SupField>
                <SupField label="Phone" testid="supplier-field-phone">
                  <input className="account-input" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} placeholder="+44 …" />
                </SupField>
              </div>
              <SupField label="Email" testid="supplier-field-email">
                <input className="account-input" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="service@…" />
              </SupField>
              <SupField label="Manufacturer keywords (auto-match equipment)" testid="supplier-field-keywords">
                <input className="account-input" value={form.manufacturer_keywords} onChange={(e) => setForm({ ...form, manufacturer_keywords: e.target.value })} placeholder="Technogym, Skill Line, Selection" />
                <p className="text-[11px] mt-1" style={{ color: 'var(--theme-text-muted)' }}>
                  Comma-separated. Any equipment whose manufacturer matches one of these keywords (case-insensitive) will route its fault notifications to this supplier.
                </p>
              </SupField>
            </div>
            <div className="mt-5 flex items-center justify-end gap-2">
              <button type="button" onClick={close} className="account-btn-secondary" data-testid="account-supplier-cancel">Cancel</button>
              <button type="submit" disabled={submitting} className="account-btn-primary inline-flex items-center gap-2 disabled:opacity-50" data-testid="account-supplier-save">
                {submitting ? <Loader2 size={14} className="animate-spin" /> : null}
                {editing.id ? 'Save changes' : 'Add supplier'}
              </button>
            </div>
          </form>
        </div>
      )}
    </section>
  );
}

function SupField({ label, testid, children }) {
  return (
    <label className="block" data-testid={testid}>
      <span className="text-[11px] font-semibold uppercase tracking-wide mb-1.5 block" style={{ color: 'var(--theme-text-muted)' }}>{label}</span>
      {children}
    </label>
  );
}
