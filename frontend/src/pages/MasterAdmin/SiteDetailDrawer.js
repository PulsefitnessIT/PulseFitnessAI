/**
 * SiteDetailDrawer (Iter 216h53)
 *
 * Click into a site from OrgSitesPanel → modal drawer with two tabs:
 *   • Site Details  — editable form (name, Sicon ref, address, contacts)
 *   • Equipment     — inline-editable table of every machine at this site
 *
 * Lee asked for this so master admin can dig into a site without
 * bouncing through three modal layers; the equipment tab uses an inline
 * row pattern instead of "open detail card per click".
 */
import React, { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import {
  X, Loader2, MapPin, Wrench, Save, Building2, Crown, Archive, Trash2, RotateCcw,
} from 'lucide-react';
import { notify } from '@/components/notifications';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const auth = () => ({ Authorization: `Bearer ${localStorage.getItem('token')}` });

const TABS = [
  { id: 'details',   label: 'Site Details', icon: MapPin },
  { id: 'equipment', label: 'Equipment',    icon: Wrench },
];

const FIELD_INPUT_CLS = 'w-full px-2.5 py-1.5 text-sm rounded-md border border-zinc-200 focus:border-blue-400 focus:ring-1 focus:ring-blue-200 outline-none bg-white';

const SiteDetailDrawer = ({ orgId, site, onClose, onSaved }) => {
  const [tab, setTab] = useState('details');
  const [form, setForm] = useState({
    name: site.name || '',
    invoice_customer_ref: site.invoice_customer_ref || '',
    address: site.address || '',
    address_line1: site.address_line1 || site.address || '',
    address_line2: site.address_line2 || '',
    city: site.city || '',
    county: site.county || '',
    postcode: site.postcode || '',
    country: site.country || 'United Kingdom',
    phone: site.phone || '',
    email: site.email || '',
    site_manager_name: site.site_manager_name || '',
    site_manager_email: site.site_manager_email || '',
    default_location: site.default_location || 'Main Floor',
    // Iter 216h113j — MOD force tagging. Only persists when the
    // org is a MOD tenant; ignored on the backend otherwise.
    mod_force: site.mod_force || '',
  });
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  // Iter 216h61 — track archive state locally so the header buttons can
  // flip between Archive/Restore without a full reload.
  const [archived, setArchived] = useState(!!site.archived);
  const [busy, setBusy] = useState(false); // archive / delete in flight
  const set = (k, v) => { setForm((f) => ({ ...f, [k]: v })); setDirty(true); };

  const saveDetails = async () => {
    setSaving(true);
    try {
      await axios.patch(`${API}/master-admin/organizations/${orgId}/sites/${site.id}`, form, { headers: auth() });
      notify.success('Site updated');
      setDirty(false);
      onSaved && onSaved();
    } catch (e) {
      notify.error('Save failed', e?.response?.data?.detail || 'Try again.');
    } finally {
      setSaving(false);
    }
  };

  // Iter 216h61 (f) — Archive / Restore / Hard delete.
  const archiveSite = async () => {
    if (!window.confirm(`Archive "${site.name}"? It will be hidden from operator-facing screens. Equipment, faults, and history are preserved.`)) return;
    setBusy(true);
    try {
      await axios.post(`${API}/master-admin/organizations/${orgId}/sites/${site.id}/archive`, {}, { headers: auth() });
      notify.success('Site archived');
      setArchived(true);
      onSaved && onSaved();
    } catch (e) {
      notify.error('Archive failed', e?.response?.data?.detail || 'Try again.');
    }
    setBusy(false);
  };

  const restoreSite = async () => {
    setBusy(true);
    try {
      await axios.post(`${API}/master-admin/organizations/${orgId}/sites/${site.id}/restore`, {}, { headers: auth() });
      notify.success('Site restored');
      setArchived(false);
      onSaved && onSaved();
    } catch (e) {
      notify.error('Restore failed', e?.response?.data?.detail || 'Try again.');
    }
    setBusy(false);
  };

  const deleteSite = async () => {
    if (!window.confirm(`PERMANENTLY DELETE "${site.name}"? This cannot be undone. Only allowed when the site has no equipment and no open issues.`)) return;
    setBusy(true);
    try {
      await axios.delete(`${API}/master-admin/organizations/${orgId}/sites/${site.id}`, { headers: auth() });
      notify.success('Site deleted');
      onSaved && onSaved();
      onClose && onClose();
    } catch (e) {
      notify.error('Delete blocked', e?.response?.data?.detail || 'Try again.');
    }
    setBusy(false);
  };

  return (
    <div className="fixed inset-0 z-[60] bg-black/40 flex items-end md:items-center justify-end" data-testid="site-detail-drawer">
      <div className="bg-white w-full md:max-w-3xl h-[92vh] md:h-[88vh] md:rounded-l-xl shadow-2xl flex flex-col">
        {/* Header */}
        <header className="px-5 py-3 border-b border-zinc-200 flex items-center gap-3 shrink-0">
          <div className="w-9 h-9 rounded-lg bg-blue-50 flex items-center justify-center shrink-0">
            {site.is_head_office ? <Crown size={16} className="text-amber-600" /> : <MapPin size={16} className="text-blue-600" />}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-zinc-900 truncate flex items-center gap-2">
              {site.name}
              {archived && <span className="px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider bg-amber-100 text-amber-800 rounded">Archived</span>}
            </p>
            <p className="text-xs text-zinc-500 truncate">
              {site.is_head_office ? 'Head Office · ' : ''}
              {[site.city, site.postcode].filter(Boolean).join(' · ') || 'No location set'}
            </p>
          </div>
          {/* Iter 216h61 (f) — Archive / Restore / Delete actions */}
          <div className="flex items-center gap-1 shrink-0">
            {archived ? (
              <button
                onClick={restoreSite}
                disabled={busy}
                className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs rounded-md border border-amber-200 text-amber-700 hover:bg-amber-50 disabled:opacity-50"
                data-testid="site-detail-restore"
                title="Restore site"
              >
                <RotateCcw size={12} /> Restore
              </button>
            ) : (
              <button
                onClick={archiveSite}
                disabled={busy}
                className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs rounded-md border border-zinc-200 text-zinc-700 hover:bg-zinc-50 disabled:opacity-50"
                data-testid="site-detail-archive"
                title="Soft-archive (preserves data)"
              >
                <Archive size={12} /> Archive
              </button>
            )}
            <button
              onClick={deleteSite}
              disabled={busy}
              className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs rounded-md border border-red-200 text-red-600 hover:bg-red-50 disabled:opacity-50"
              data-testid="site-detail-delete"
              title="Hard delete (only when empty)"
            >
              <Trash2 size={12} /> Delete
            </button>
          </div>
          <button onClick={onClose} className="p-1.5 hover:bg-zinc-100 rounded-md text-zinc-500" data-testid="site-detail-close">
            <X size={16} />
          </button>
        </header>

        {/* Tab bar */}
        <div className="flex border-b border-zinc-200 px-4 shrink-0">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={`px-3 py-2 text-sm flex items-center gap-1.5 border-b-2 -mb-px ${tab === id ? 'border-blue-600 text-blue-700 font-semibold' : 'border-transparent text-zinc-500 hover:text-zinc-700'}`}
              data-testid={`site-detail-tab-${id}`}
            >
              <Icon size={13} />
              {label}
            </button>
          ))}
        </div>

        {/* Body */}
        <div className="flex-1 overflow-auto px-5 py-4">
          {tab === 'details' && (
            <SiteDetailsForm form={form} set={set} dirty={dirty} saving={saving} onSave={saveDetails} />
          )}
          {tab === 'equipment' && (
            <EquipmentInlineList orgId={orgId} siteId={site.id} siteName={site.name} />
          )}
        </div>
      </div>
    </div>
  );
};

/* ───────────────────── Site Details ───────────────────── */

const Field = ({ label, value, onChange, type = 'text', placeholder, testId }) => (
  <div>
    <label className="block text-[11px] uppercase tracking-wider text-zinc-500 font-semibold mb-1">{label}</label>
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className={FIELD_INPUT_CLS}
      data-testid={testId}
    />
  </div>
);

const SiteDetailsForm = ({ form, set, dirty, saving, onSave }) => (
  <div className="space-y-4" data-testid="site-detail-details">
    <Field label="Site name" value={form.name} onChange={(v) => set('name', v)} testId="site-detail-name" />
    <div className="grid grid-cols-2 gap-3">
      <Field label="Invoice Customer Ref (Sicon)" value={form.invoice_customer_ref} onChange={(v) => set('invoice_customer_ref', v)} placeholder="e.g. INV-CAR-001" testId="site-detail-invoice-ref" />
      <Field label="Default equipment location" value={form.default_location} onChange={(v) => set('default_location', v)} placeholder="Main Floor" testId="site-detail-default-location" />
    </div>

    {/* Iter 216h113j — Force tag for MOD tenants. Visible to all
        Master Admin users; only persists when the org is a MOD
        tenant. Shows three radio-style pills for a clean choice. */}
    <div data-testid="site-detail-mod-force">
      <label className="block text-[11px] uppercase tracking-wider text-zinc-500 font-semibold mb-1.5">
        MOD Force (Army / RAF / Navy — leave blank for non-MOD sites)
      </label>
      <div className="flex flex-wrap gap-2">
        {[
          { id: '',     label: 'Not MOD' },
          { id: 'army', label: 'British Army' },
          { id: 'raf',  label: 'Royal Air Force' },
          { id: 'navy', label: 'Royal Navy' },
        ].map((opt) => (
          <button
            key={opt.id || 'none'}
            type="button"
            onClick={() => set('mod_force', opt.id)}
            className={`px-3 py-1.5 rounded-full text-xs font-semibold border transition ${
              form.mod_force === opt.id
                ? 'border-blue-500 bg-blue-50 text-blue-700'
                : 'border-zinc-200 bg-white text-zinc-600 hover:border-zinc-300'
            }`}
            data-testid={`site-detail-mod-force-${opt.id || 'none'}`}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>

    <p className="text-[11px] uppercase tracking-wider text-zinc-400 font-semibold pt-2 border-t border-zinc-100">Address</p>
    <div className="space-y-3">
      <Field label="Address line 1" value={form.address_line1} onChange={(v) => { set('address_line1', v); set('address', v); }} testId="site-detail-address1" />
      <Field label="Address line 2" value={form.address_line2} onChange={(v) => set('address_line2', v)} testId="site-detail-address2" />
      <div className="grid grid-cols-3 gap-3">
        <Field label="City" value={form.city} onChange={(v) => set('city', v)} testId="site-detail-city" />
        <Field label="County" value={form.county} onChange={(v) => set('county', v)} testId="site-detail-county" />
        <Field label="Postcode" value={form.postcode} onChange={(v) => set('postcode', v)} testId="site-detail-postcode" />
      </div>
      <Field label="Country" value={form.country} onChange={(v) => set('country', v)} testId="site-detail-country" />
    </div>

    <p className="text-[11px] uppercase tracking-wider text-zinc-400 font-semibold pt-2 border-t border-zinc-100">Contacts</p>
    <div className="grid grid-cols-2 gap-3">
      <Field label="Site phone" value={form.phone} onChange={(v) => set('phone', v)} testId="site-detail-phone" />
      <Field label="Site email" value={form.email} onChange={(v) => set('email', v)} type="email" testId="site-detail-email" />
      <Field label="Site manager name" value={form.site_manager_name} onChange={(v) => set('site_manager_name', v)} testId="site-detail-manager-name" />
      <Field label="Site manager email" value={form.site_manager_email} onChange={(v) => set('site_manager_email', v)} type="email" testId="site-detail-manager-email" />
    </div>

    <div className="sticky bottom-0 bg-white pt-3 pb-1 flex justify-end gap-2 border-t border-zinc-100">
      <button
        onClick={onSave}
        disabled={!dirty || saving}
        className="text-sm px-4 py-2 rounded-md bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 inline-flex items-center gap-1.5"
        data-testid="site-detail-save"
      >
        {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
        Save changes
      </button>
    </div>
  </div>
);

/* ──────────────────── Equipment list ──────────────────── */

const EquipmentInlineList = ({ orgId, siteId, siteName }) => {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState({}); // id → {field: value}

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // Iter 216h61 — use the master-admin-scoped equipment endpoint
      // (org_id in the path) rather than `/api/equipment?site_id=`,
      // which falls back to filtering by the master-admin's own user_id
      // when their token has no organization_id — returning 0 cross-org
      // results. Lee saw only stale TEST_QR equipment because that's
      // what the master-admin created themselves via curl.
      const r = await axios.get(
        `${API}/master-admin/organizations/${orgId}/sites/${siteId}/equipment`,
        { headers: auth() },
      );
      setItems(r.data?.equipment || []);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [orgId, siteId]);

  useEffect(() => { load(); }, [load]);

  const saveRow = async (eq) => {
    const changes = editing[eq.id];
    if (!changes) return;
    try {
      await axios.patch(`${API}/equipment/${eq.id}`, changes, { headers: auth() });
      notify.success('Equipment updated');
      setEditing((e) => { const n = { ...e }; delete n[eq.id]; return n; });
      load();
    } catch (e) {
      notify.error('Save failed', e?.response?.data?.detail || 'Try again.');
    }
  };

  const setField = (id, field, val) => {
    setEditing((e) => ({ ...e, [id]: { ...(e[id] || {}), [field]: val } }));
  };

  const display = (eq, field) => editing[eq.id]?.[field] ?? eq[field] ?? '';

  if (loading) {
    return <div className="flex items-center gap-2 text-xs text-zinc-500 py-6"><Loader2 size={12} className="animate-spin" /> Loading equipment…</div>;
  }

  if (items.length === 0) {
    return (
      <div className="text-center py-12 border border-dashed border-zinc-200 rounded-lg" data-testid="site-detail-equipment-empty">
        <Wrench size={32} className="mx-auto mb-3 text-zinc-300" />
        <p className="text-sm font-medium text-zinc-600">No equipment at {siteName}</p>
        <p className="text-xs text-zinc-400 mt-1">Bulk-import equipment with `site_name = {siteName}` to populate this list.</p>
      </div>
    );
  }

  return (
    <div className="space-y-2" data-testid="site-detail-equipment">
      <div className="flex items-center justify-between mb-2">
        <p className="text-[11px] uppercase tracking-wider text-zinc-500 font-semibold">{items.length} item{items.length === 1 ? '' : 's'}</p>
        <p className="text-[11px] text-zinc-400 italic">Click any cell to edit · Save commits the row</p>
      </div>
      <div className="rounded-lg border border-zinc-200 overflow-hidden">
        <table className="w-full text-sm" data-testid="site-detail-equipment-table">
          <thead className="bg-zinc-50 text-[10px] uppercase tracking-wider text-zinc-500">
            <tr>
              <th className="text-left py-2 px-2 font-semibold">Name</th>
              <th className="text-left py-2 px-2 font-semibold">Type</th>
              <th className="text-left py-2 px-2 font-semibold">Model</th>
              <th className="text-left py-2 px-2 font-semibold">Serial</th>
              <th className="text-left py-2 px-2 font-semibold">Supplier</th>
              <th className="text-left py-2 px-2 font-semibold">Location</th>
              <th className="w-10"></th>
            </tr>
          </thead>
          <tbody>
            {items.map((eq) => {
              const isDirty = !!editing[eq.id];
              return (
                <tr
                  key={eq.id}
                  className={`border-t border-zinc-100 ${isDirty ? 'bg-blue-50/40' : ''}`}
                  data-testid={`site-equipment-row-${eq.id}`}
                >
                  <td className="px-1 py-1">
                    <input className={FIELD_INPUT_CLS} value={display(eq, 'name')} onChange={(e) => setField(eq.id, 'name', e.target.value)} data-testid={`equipment-name-${eq.id}`} />
                  </td>
                  <td className="px-1 py-1">
                    <input className={FIELD_INPUT_CLS} value={display(eq, 'equipment_type')} onChange={(e) => setField(eq.id, 'equipment_type', e.target.value)} />
                  </td>
                  <td className="px-1 py-1">
                    <input className={FIELD_INPUT_CLS} value={display(eq, 'model')} onChange={(e) => setField(eq.id, 'model', e.target.value)} />
                  </td>
                  <td className="px-1 py-1">
                    <input className={FIELD_INPUT_CLS} value={display(eq, 'serial_number')} onChange={(e) => setField(eq.id, 'serial_number', e.target.value)} />
                  </td>
                  <td className="px-1 py-1">
                    <input className={FIELD_INPUT_CLS} value={display(eq, 'supplier')} onChange={(e) => setField(eq.id, 'supplier', e.target.value)} />
                  </td>
                  <td className="px-1 py-1">
                    <input className={FIELD_INPUT_CLS} value={display(eq, 'location')} onChange={(e) => setField(eq.id, 'location', e.target.value)} />
                  </td>
                  <td className="px-1 py-1">
                    {isDirty && (
                      <button
                        onClick={() => saveRow(eq)}
                        className="p-1.5 rounded-md bg-blue-600 hover:bg-blue-700 text-white"
                        title="Save row"
                        data-testid={`equipment-save-${eq.id}`}
                      >
                        <Save size={11} />
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default SiteDetailDrawer;
