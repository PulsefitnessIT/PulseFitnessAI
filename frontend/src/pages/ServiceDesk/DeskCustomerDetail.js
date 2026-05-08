import React, { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { ArrowLeft, Save, Eye, Users, Building2, Wrench, Truck } from 'lucide-react';
import { authConfig } from './authConfig';

function Section({ title, icon: Icon, children }) {
  return (
    <Card className="p-5">
      <div className="flex items-center gap-2 mb-4">
        <Icon className="w-4 h-4 text-zinc-500" />
        <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">{title}</h2>
      </div>
      {children}
    </Card>
  );
}

export default function DeskCustomerDetail({ API, orgId, onBack }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/service-desk/customers/${orgId}`, authConfig());
      setData(r.data);
      setForm({
        name: r.data.organization.name || '',
        primary_contact_name: r.data.organization.primary_contact_name || '',
        primary_contact_email: r.data.organization.primary_contact_email || '',
        primary_contact_phone: r.data.organization.primary_contact_phone || '',
        head_office_ref: r.data.organization.head_office_ref || '',
        notes: r.data.organization.notes || '',
      });
    } catch (e) {
      notify.error('Failed to load customer');
    } finally {
      setLoading(false);
    }
  }, [API, orgId]);

  useEffect(() => { load(); }, [load]);

  const save = async () => {
    setSaving(true);
    try {
      await axios.patch(`${API}/service-desk/customers/${orgId}`, form, authConfig());
      notify.success('Customer updated');
      await load();
    } catch (e) {
      notifyApiError(notify, e, 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const impersonate = async () => {
    try {
      const r = await axios.post(`${API}/service-desk/customers/${orgId}/impersonate`, {}, authConfig());
      const url = new URL(window.location.origin + '/dashboard');
      url.searchParams.set('impersonation_token', r.data.token);
      window.open(url.toString(), '_blank');
      notify.success('Impersonation session opened in new tab (1h)');
    } catch (e) {
      notifyApiError(notify, e, 'Impersonation failed');
    }
  };

  if (loading) return <div className="text-zinc-500">Loading…</div>;
  if (!data) return <div className="text-red-500">Customer not found</div>;

  const { organization: org, sites, staff, suppliers, equipment_count } = data;

  return (
    <div className="space-y-4" data-testid="desk-customer-detail">
      <div className="flex items-center justify-between">
        <Button variant="ghost" size="sm" onClick={onBack} data-testid="desk-back-to-list">
          <ArrowLeft className="w-4 h-4 mr-1" /> Back to customers
        </Button>
        <Button
          variant="outline" size="sm"
          onClick={impersonate}
          data-testid="desk-impersonate-btn"
          className="border-red-200 text-red-700 hover:bg-red-50"
        >
          <Eye className="w-4 h-4 mr-1" /> View as customer
        </Button>
      </div>

      <div>
        <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">{org.name}</h1>
        <div className="text-sm text-zinc-500 mt-1 flex items-center gap-3 flex-wrap">
          <Badge variant="outline">{org.account_type || '—'}</Badge>
          {org.sicon_customer_ref && <span>Sicon Ref: {org.sicon_customer_ref}</span>}
          {org.status && <span>Status: {org.status}</span>}
        </div>
      </div>

      <div className="grid grid-cols-4 gap-3">
        <div className="p-3 bg-white border border-zinc-200 rounded dark:bg-zinc-900 dark:border-zinc-800">
          <div className="text-xs text-zinc-500">Sites</div>
          <div className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">{sites.length}</div>
        </div>
        <div className="p-3 bg-white border border-zinc-200 rounded dark:bg-zinc-900 dark:border-zinc-800">
          <div className="text-xs text-zinc-500">Staff</div>
          <div className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">{staff.length}</div>
        </div>
        <div className="p-3 bg-white border border-zinc-200 rounded dark:bg-zinc-900 dark:border-zinc-800">
          <div className="text-xs text-zinc-500">Suppliers</div>
          <div className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">{suppliers.length}</div>
        </div>
        <div className="p-3 bg-white border border-zinc-200 rounded dark:bg-zinc-900 dark:border-zinc-800">
          <div className="text-xs text-zinc-500">Equipment</div>
          <div className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">{equipment_count}</div>
        </div>
      </div>

      <Section title="Customer Details" icon={Building2}>
        <div className="grid grid-cols-2 gap-4">
          {[
            { k: 'name', label: 'Company name' },
            { k: 'head_office_ref', label: 'Head Office Ref' },
            { k: 'primary_contact_name', label: 'Primary contact name' },
            { k: 'primary_contact_email', label: 'Primary contact email', type: 'email' },
            { k: 'primary_contact_phone', label: 'Primary contact phone' },
          ].map(({ k, label, type }) => (
            <div key={k}>
              <Label htmlFor={`f-${k}`} className="text-xs text-zinc-600">{label}</Label>
              <Input
                id={`f-${k}`} type={type || 'text'}
                value={form[k] || ''}
                onChange={(e) => setForm({ ...form, [k]: e.target.value })}
                data-testid={`desk-field-${k}`}
              />
            </div>
          ))}
          <div className="col-span-2">
            <Label htmlFor="f-notes" className="text-xs text-zinc-600">Internal notes (Service Desk only)</Label>
            <textarea
              id="f-notes" rows={3}
              value={form.notes || ''}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
              data-testid="desk-field-notes"
              className="w-full mt-1 px-3 py-2 border border-zinc-200 rounded-md text-sm dark:border-zinc-800"
            />
          </div>
        </div>
        <div className="mt-4 flex justify-end">
          <Button
            onClick={save} disabled={saving}
            className="bg-orange-600 hover:bg-orange-700"
            data-testid="desk-save-customer"
          >
            <Save className="w-4 h-4 mr-1" /> {saving ? 'Saving…' : 'Save changes'}
          </Button>
        </div>
      </Section>

      <Section title={`Sites (${sites.length})`} icon={Building2}>
        {sites.length === 0 ? (
          <div className="text-xs text-zinc-500">No sites recorded yet.</div>
        ) : (
          <div className="space-y-2">
            {sites.map((s) => (
              <div key={s.id} className="p-3 border border-zinc-200 rounded text-sm dark:border-zinc-800" data-testid={`desk-site-${s.id}`}>
                <div className="font-medium text-zinc-900 dark:text-zinc-100">{s.name}</div>
                <div className="text-xs text-zinc-500 mt-1">
                  {[s.address_line1, s.city, s.postcode].filter(Boolean).join(', ') || <em>No address</em>}
                  {s.phone && <span className="ml-3">📞 {s.phone}</span>}
                </div>
              </div>
            ))}
          </div>
        )}
      </Section>

      <Section title={`Staff (${staff.length})`} icon={Users}>
        {staff.length === 0 ? (
          <div className="text-xs text-zinc-500">No staff users yet.</div>
        ) : (
          <div className="space-y-1">
            {staff.map((u) => (
              <div key={u.id} className="flex items-center justify-between text-sm py-2 border-b border-zinc-100 last:border-0 dark:border-zinc-800" data-testid={`desk-staff-${u.id}`}>
                <div>
                  <span className="text-zinc-900 dark:text-zinc-100">{u.full_name || u.email}</span>
                  <span className="ml-2 text-xs text-zinc-500">{u.email}</span>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className="text-[10px]">{u.role}</Badge>
                  {u.disabled && <Badge variant="outline" className="text-[10px] bg-red-50 text-red-700 border-red-200">Disabled</Badge>}
                </div>
              </div>
            ))}
          </div>
        )}
      </Section>

      <Section title={`Suppliers (${suppliers.length})`} icon={Truck}>
        {suppliers.length === 0 ? (
          <div className="text-xs text-zinc-500">No suppliers — Pulse Fitness default will be seeded on first import.</div>
        ) : (
          <div className="space-y-1">
            {suppliers.map((s) => (
              <div key={s.id || s.name} className="flex items-center justify-between text-sm py-2 border-b border-zinc-100 last:border-0 dark:border-zinc-800">
                <div>
                  <span className="text-zinc-900 dark:text-zinc-100">{s.name}</span>
                  <span className="ml-2 text-xs text-zinc-500">{s.email}</span>
                </div>
                {s.is_default_supplier && (
                  <Badge variant="outline" className="text-[10px] bg-orange-50 text-orange-700 border-orange-200">Default</Badge>
                )}
              </div>
            ))}
          </div>
        )}
      </Section>
    </div>
  );
}
