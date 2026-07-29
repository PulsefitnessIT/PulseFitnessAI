/**
 * Marketing → Contacts tab — Iter 215bf (May 1, 2026).
 *
 * Purpose:
 *  Lite contact directory inside the Marketing Suite so customers on
 *  the Marketing-only license (£49/mo) can manage the contacts they've
 *  captured via lead-capture forms, edit details, import CSVs, and
 *  feed them into audiences and campaigns. Customers on the CRM
 *  license see the full pipeline + deals UI in the dedicated CRM app
 *  (`/crm`) — this tab is the marketing-only on-ramp.
 *
 *  Backend: `/api/marketing/contacts` (list/get/create/update/delete +
 *  bulk CSV import) gated by `require_module(("crm","marketing"))`.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import { Search, Plus, Upload, Trash2, X, Loader2, AtSign, Phone as PhoneIcon, Tag, Sparkles } from 'lucide-react';
import CRMProTrialNudge from './CRMProTrialNudge';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { useAuth } from '@/App';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

const PAGE_SIZE = 25;

export default function ContactsTab() {
  const { t } = useTranslation();
  const { token } = useAuth();
  const API = process.env.REACT_APP_BACKEND_URL;
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);

  const [search, setSearch] = useState('');
  const [contacts, setContacts] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState(null); // contact | "new"

  const fileInputRef = useRef(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/api/marketing/contacts`, {
        headers,
        params: { search, skip: page * PAGE_SIZE, limit: PAGE_SIZE },
      });
      setContacts(data.contacts || []);
      setTotal(data.total || 0);
    } catch (e) {
      notifyApiError(notify, e, t('mkt.ct_load_err', 'Could not load contacts'));
    }
    setLoading(false);
  }, [API, headers, search, page]);

  useEffect(() => { load(); }, [load]);

  // Reset to page 0 when search changes (so users always see page 1 of new results).
  useEffect(() => { setPage(0); }, [search]);

  const handleDelete = async (c) => {
    if (!window.confirm(t('mkt.ct_delete_confirm', 'Delete {{email}}? This cannot be undone.', { email: c.email }))) return;
    try {
      await axios.delete(`${API}/api/marketing/contacts/${c.id}`, { headers });
      notify.success(t('mkt.ct_deleted', 'Contact deleted'));
      load();
    } catch (e) { notifyApiError(notify, e, t('mkt.ct_delete_err', 'Could not delete contact')); }
  };

  const handleImportClick = () => fileInputRef.current?.click();

  const handleImportFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = ''; // allow re-uploading same file
    const fd = new FormData();
    fd.append('file', file);
    try {
      const { data } = await axios.post(`${API}/api/marketing/contacts/import`, fd, {
        headers: { ...headers, 'Content-Type': 'multipart/form-data' },
      });
      notify.success(t('mkt.ct_import_done', 'Imported {{created}} new · {{updated}} updated · {{skipped}} skipped', { created: data.created, updated: data.updated, skipped: data.skipped }));
      load();
    } catch (e) { notifyApiError(notify, e, t('mkt.ct_import_err', 'CSV import failed')); }
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="space-y-5" data-testid="marketing-contacts-tab">
      {/* Iter 215dl — CRM Lite is bundled with Marketing. Surfacing this
          framing turns "another tab in the email tool" into a perceived
          mini-CRM without spinning up a second app. Customers upgrade
          to CRM Pro when they need pipeline / deals / forecasting. */}
      <div
        className="rounded-xl border px-4 py-3 flex items-start gap-3"
        style={{ borderColor: 'var(--theme-border)', background: 'linear-gradient(135deg, rgb(217 70 239 / 0.06) 0%, rgb(99 102 241 / 0.06) 100%)' }}
        data-testid="crm-lite-badge"
      >
        <div className="h-8 w-8 rounded-lg flex items-center justify-center shrink-0" style={{ background: 'linear-gradient(135deg, #d946ef 0%, #6366f1 100%)', color: 'white' }}>
          <Sparkles size={14} />
        </div>
        <div className="min-w-0 text-sm">
          <p className="font-bold" style={{ color: 'var(--theme-text)' }}>
            <span className="inline-block px-1.5 py-0.5 rounded text-[10px] font-extrabold uppercase tracking-wider mr-1.5" style={{ background: '#6366f122', color: '#6366f1' }}>{t('mkt.ct_crm_lite', 'CRM Lite')}</span>
            {t('mkt.ct_included', 'included with Marketing')}
          </p>
          <p className="text-xs opacity-70 mt-0.5">
            {t('mkt.ct_lite_desc', 'Manage contacts, segments and lead-capture forms here. Need pipeline, deals or forecasting?')}{' '}
            <span className="font-semibold" style={{ color: 'var(--theme-text)' }}>{t('mkt.ct_upgrade', 'Upgrade to CRM Pro.')}</span>
          </p>
        </div>
      </div>

      {/* Iter 215dm — in-product upsell when the contact base scales
          past 250. Self-renders empty (returns null) if the tenant
          already has CRM Pro, dismissed, or below threshold. */}
      <CRMProTrialNudge totalContacts={total} threshold={250} />

      <div className="flex flex-wrap items-center gap-3">
        {/* search + actions row */}
        <div className="flex-1 min-w-[220px] relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search name, email, phone…"
            className="pl-9 h-10 rounded-xl bg-white border-slate-200 dark:bg-zinc-900 dark:border-zinc-800"
            data-testid="contacts-search"
          />
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv"
          onChange={handleImportFile}
          className="hidden"
          data-testid="contacts-import-input"
        />
        <Button
          variant="outline"
          onClick={handleImportClick}
          className="h-10 rounded-full border-slate-200 dark:border-zinc-800"
          data-testid="contacts-import-btn"
        >
          <Upload size={14} className="mr-1.5" /> {t('mkt.ct_import_csv', 'Import CSV')}
        </Button>
        <Button
          onClick={() => setEditing('new')}
          className="h-10 rounded-full bg-gradient-to-r from-[var(--gx-brand-from)] to-[var(--gx-brand-to)] text-white border-0 shadow-[0_6px_16px_-6px_rgba(25, 205, 255,0.35)]"
          data-testid="contacts-create-btn"
        >
          <Plus size={14} className="mr-1.5" /> {t('mkt.ct_new_contact', 'New contact')}
        </Button>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden shadow-[0_1px_2px_rgba(15,23,42,0.04)] dark:bg-zinc-900 dark:border-zinc-800">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-200 text-[11px] uppercase tracking-[0.16em] font-bold text-slate-500 dark:bg-zinc-900 dark:border-zinc-800">
              <th className="text-left px-5 py-3">{t('mkt.ct_th_name', 'Name')}</th>
              <th className="text-left px-5 py-3 hidden sm:table-cell">{t('mkt.ct_th_email', 'Email')}</th>
              <th className="text-left px-5 py-3 hidden md:table-cell">{t('mkt.ct_th_phone', 'Phone')}</th>
              <th className="text-left px-5 py-3 hidden lg:table-cell">{t('mkt.ct_th_tags', 'Tags')}</th>
              <th className="text-right px-5 py-3 w-1">{t('mkt.ct_th_actions', 'Actions')}</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={5} className="px-5 py-8 text-center text-slate-400"><Loader2 size={16} className="animate-spin inline mr-2" /> {t('mkt.ct_loading', 'Loading contacts…')}</td></tr>
            )}
            {!loading && contacts.length === 0 && (
              <tr><td colSpan={5} className="px-5 py-12 text-center">
                <div className="text-slate-700 font-semibold mb-1">{t('mkt.ct_empty_title', 'No contacts yet')}</div>
                <p className="text-sm text-slate-500 max-w-sm mx-auto">
                  {t('mkt.ct_empty_body', 'Capture leads with a Form on your site, import a CSV, or create one manually. Contacts feed Audiences, Campaigns and Journeys.')}
                </p>
              </td></tr>
            )}
            {!loading && contacts.map((c) => (
              <tr key={c.id} className="border-b border-slate-100 hover:bg-slate-50/50 dark:border-zinc-800" data-testid={`contact-row-${c.id}`}>
                <td className="px-5 py-3">
                  <button
                    type="button"
                    onClick={() => setEditing(c)}
                    className="font-semibold text-slate-900 hover:text-[var(--gx-brand-from)] text-left dark:text-zinc-100"
                  >
                    {(c.first_name || c.last_name) ? `${c.first_name || ''} ${c.last_name || ''}`.trim() : <span className="text-slate-400 italic">{t('mkt.ct_no_name', 'No name')}</span>}
                  </button>
                  <div className="text-xs text-slate-500 sm:hidden mt-0.5">{c.email}</div>
                </td>
                <td className="px-5 py-3 hidden sm:table-cell text-slate-700">{c.email}</td>
                <td className="px-5 py-3 hidden md:table-cell text-slate-500">{c.phone || '—'}</td>
                <td className="px-5 py-3 hidden lg:table-cell">
                  <div className="flex flex-wrap gap-1">
                    {(c.tags || []).slice(0, 3).map((tag) => (
                      <span key={tag} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-100 text-[11px] font-semibold text-slate-700 dark:bg-zinc-800"><Tag size={9} /> {tag}</span>
                    ))}
                  </div>
                </td>
                <td className="px-5 py-3 text-right">
                  <button
                    type="button"
                    onClick={() => handleDelete(c)}
                    className="text-slate-400 hover:text-red-600 p-1.5 rounded-lg hover:bg-red-50"
                    aria-label={t('mkt.ct_delete_aria', 'Delete contact')}
                    data-testid={`contact-delete-${c.id}`}
                  >
                    <Trash2 size={14} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-5 py-3 border-t border-slate-100 text-sm text-slate-600 dark:border-zinc-800">
            <span>{t('mkt.ct_pagination', 'Page {{page}} of {{total}} · {{count}} contacts', { page: page + 1, total: totalPages, count: total.toLocaleString() })}</span>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={page <= 0} onClick={() => setPage((p) => p - 1)} data-testid="contacts-prev">{t('mkt.ct_prev', 'Prev')}</Button>
              <Button variant="outline" size="sm" disabled={page + 1 >= totalPages} onClick={() => setPage((p) => p + 1)} data-testid="contacts-next">{t('mkt.ct_next', 'Next')}</Button>
            </div>
          </div>
        )}
      </div>

      {editing && (
        <ContactDialog
          contact={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); load(); }}
          API={API}
          headers={headers}
        />
      )}
    </div>
  );
}

function ContactDialog({ contact, onClose, onSaved, API, headers }) {
  const { t } = useTranslation();
  const isNew = !contact;
  const [form, setForm] = useState({
    first_name: contact?.first_name || '',
    last_name: contact?.last_name || '',
    email: contact?.email || '',
    phone: contact?.phone || '',
    tags: (contact?.tags || []).join(', '),
    email_consent: contact?.marketing_consent?.email !== false,
    sms_consent: contact?.marketing_consent?.sms === true,
  });
  const [saving, setSaving] = useState(false);

  const save = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const body = {
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
        email: form.email.trim().toLowerCase(),
        phone: form.phone.trim() || null,
        tags: form.tags.split(',').map((tag) => tag.trim()).filter(Boolean),
        email_consent: form.email_consent,
        sms_consent: form.sms_consent,
      };
      if (isNew) {
        await axios.post(`${API}/api/marketing/contacts`, body, { headers });
        notify.success(t('mkt.ct_created', 'Contact created'));
      } else {
        await axios.put(`${API}/api/marketing/contacts/${contact.id}`, {
          ...body,
          marketing_consent: { email: body.email_consent, sms: body.sms_consent },
        }, { headers });
        notify.success(t('mkt.ct_updated', 'Contact updated'));
      }
      onSaved();
    } catch (e2) { notifyApiError(notify, e2, t('mkt.ct_save_err', 'Could not save contact')); }
    setSaving(false);
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-md bg-white dark:bg-zinc-900">
        <DialogHeader>
          <DialogTitle>{isNew ? t('mkt.ct_new_contact', 'New contact') : t('mkt.ct_edit_contact', 'Edit contact')}</DialogTitle>
        </DialogHeader>
        <form onSubmit={save} className="space-y-3" data-testid="contact-dialog-form">
          <div className="grid grid-cols-2 gap-3">
            <Input value={form.first_name} onChange={(e) => setForm((f) => ({ ...f, first_name: e.target.value }))} placeholder={t('mkt.ct_first_name', 'First name')} data-testid="contact-first-name" />
            <Input value={form.last_name} onChange={(e) => setForm((f) => ({ ...f, last_name: e.target.value }))} placeholder={t('mkt.ct_last_name', 'Last name')} data-testid="contact-last-name" />
          </div>
          <div className="relative">
            <AtSign size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <Input value={form.email} onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))} placeholder="email@example.com" required type="email" className="pl-9" data-testid="contact-email" />
          </div>
          <div className="relative">
            <PhoneIcon size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <Input value={form.phone} onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))} placeholder="Phone (optional)" className="pl-9" data-testid="contact-phone" />
          </div>
          <Input value={form.tags} onChange={(e) => setForm((f) => ({ ...f, tags: e.target.value }))} placeholder="Tags, comma separated" data-testid="contact-tags" />
          <div className="flex items-center gap-4 text-sm">
            <label className="inline-flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={form.email_consent} onChange={(e) => setForm((f) => ({ ...f, email_consent: e.target.checked }))} data-testid="contact-email-consent" />
              <span className="text-slate-700">Email consent</span>
            </label>
            <label className="inline-flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={form.sms_consent} onChange={(e) => setForm((f) => ({ ...f, sms_consent: e.target.checked }))} data-testid="contact-sms-consent" />
              <span className="text-slate-700">{t('mkt.ct_sms_consent', 'SMS consent')}</span>
            </label>
          </div>
          <DialogFooter className="pt-2">
            <Button type="button" variant="outline" onClick={onClose}><X size={14} className="mr-1.5" /> {t('mkt.ct_cancel', 'Cancel')}</Button>
            <Button type="submit" disabled={saving} className="bg-gradient-to-r from-[var(--gx-brand-from)] to-[var(--gx-brand-to)] text-white border-0" data-testid="contact-save-btn">
              {saving ? <><Loader2 size={14} className="animate-spin mr-1.5" /> {t('mkt.ct_saving', 'Saving…')}</> : t('mkt.ct_save_contact', 'Save contact')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
