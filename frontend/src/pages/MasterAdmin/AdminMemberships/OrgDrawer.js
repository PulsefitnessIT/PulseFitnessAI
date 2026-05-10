import React from 'react';
import axios from 'axios';
import { useAuth } from '@/App';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { notify } from '@/components/notifications';
import { SectionCard, Pill, fmtMoney } from './shared';
import { Lock, ShieldCheck, SlidersHorizontal, Pencil, Save, XIcon, Link2, CreditCard } from 'lucide-react';
import OrgLinkedSitesTab from './OrgLinkedSitesTab';
import PaymentSetupCard from '../PaymentSetupCard';

const OrgDrawer = ({ orgId, onClose, onChanged }) => {
  const { API } = useAuth();
  const [data, setData] = React.useState(null);
  const [editing, setEditing] = React.useState(false);
  const [form, setForm] = React.useState({ name: '', slug: '', contact_email: '', notes: '' });
  const [saving, setSaving] = React.useState(false);
  const [tab, setTab] = React.useState('overview');

  const load = React.useCallback(() => {
    if (!orgId) return;
    const token = localStorage.getItem('token');
    axios.get(`${API}/master-admin/memberships/organizations/${orgId}`, {
      headers: { Authorization: `Bearer ${token}` },
    }).then((r) => setData(r.data)).catch(() => setData(null));
  }, [API, orgId]);

  React.useEffect(load, [load]);

  const startEdit = () => {
    setForm({
      name: data?.organization?.name || '',
      slug: data?.organization?.slug || '',
      contact_email: data?.organization?.contact_email || '',
      notes: data?.organization?.notes || '',
    });
    setEditing(true);
  };

  const save = async () => {
    setSaving(true);
    try {
      const token = localStorage.getItem('token');
      await axios.put(`${API}/master-admin/memberships/organizations/${orgId}`, form, {
        headers: { Authorization: `Bearer ${token}` },
      });
      notify.success('Organisation updated');
      setEditing(false);
      load();
      onChanged?.();
    } catch (e) {
      notify.error('Update failed', e.response?.data?.detail || 'Try again.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={!!orgId} onOpenChange={(o) => !o && onClose?.()}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto" data-testid="org-drawer">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-zinc-900 dark:text-zinc-100">
            {data?.organization?.name || 'Loading…'}
            {data?.organization?.locked && <Pill tone="red"><Lock size={10} className="mr-1" /> Locked</Pill>}
            {data && !editing && (
              <Button size="sm" variant="outline" onClick={startEdit} className="ml-auto h-7 text-xs" data-testid="org-drawer-edit">
                <Pencil size={12} className="mr-1" /> Edit
              </Button>
            )}
          </DialogTitle>
        </DialogHeader>
        {editing && (
          <div className="border border-zinc-200 dark:border-zinc-700 rounded-lg p-4 bg-zinc-50 dark:bg-zinc-800/40 space-y-3" data-testid="org-edit-form">
            <h4 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Edit organisation</h4>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Name</Label>
                <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="org-edit-name" />
              </div>
              <div>
                <Label className="text-xs">Slug</Label>
                <Input value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value })} placeholder="your-site-slug" data-testid="org-edit-slug" />
              </div>
              <div className="col-span-2">
                <Label className="text-xs">Contact email</Label>
                <Input type="email" value={form.contact_email} onChange={(e) => setForm({ ...form, contact_email: e.target.value })} placeholder="manager@gym.com" data-testid="org-edit-email" />
              </div>
              <div className="col-span-2">
                <Label className="text-xs">Notes (master admin only)</Label>
                <Input value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} placeholder="Internal notes…" />
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <Button size="sm" variant="outline" onClick={() => setEditing(false)} disabled={saving}>
                <XIcon size={12} className="mr-1" /> Cancel
              </Button>
              <Button size="sm" onClick={save} disabled={saving || !form.name?.trim()} className="bg-blue-600 hover:bg-blue-700 text-white" data-testid="org-edit-save">
                <Save size={12} className="mr-1" /> {saving ? 'Saving…' : 'Save'}
              </Button>
            </div>
          </div>
        )}
        {!data ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400 py-6 text-center">Loading organisation details…</p>
        ) : (
          <>
            {/* Iter 215br — tab strip so multi-site groups can manage linked sites without leaving the drawer. */}
            <div className="flex items-center gap-1 border-b border-zinc-200 dark:border-zinc-700 -mb-px" data-testid="org-drawer-tabs">
              {[
                { id: 'overview', label: 'Overview' },
                { id: 'payments', label: 'Payments', icon: CreditCard },
                { id: 'linked-sites', label: 'Linked sites', icon: Link2 },
              ].map((t) => {
                const Icon = t.icon;
                const active = tab === t.id;
                return (
                  <button
                    key={t.id}
                    onClick={() => setTab(t.id)}
                    className={`flex items-center gap-1.5 px-3 py-2 text-xs font-semibold border-b-2 transition-colors ${active
                      ? 'border-blue-600 text-blue-700 dark:text-blue-400'
                      : 'border-transparent text-zinc-500 dark:text-zinc-400 hover:text-zinc-800 dark:hover:text-zinc-200'}`}
                    data-testid={`org-drawer-tab-${t.id}`}
                  >
                    {Icon && <Icon size={12} />} {t.label}
                  </button>
                );
              })}
            </div>

            {tab === 'linked-sites' ? (
              <OrgLinkedSitesTab orgId={orgId} orgName={data.organization?.name || ''} />
            ) : tab === 'payments' ? (
              <div className="pt-3" data-testid="org-drawer-payments">
                <PaymentSetupCard organizationId={orgId} />
              </div>
            ) : (
              <div className="space-y-4 text-sm pt-2">
                <div className="grid grid-cols-3 gap-3">
                  <div className="bg-zinc-50 dark:bg-zinc-800/60 rounded-md p-3">
                    <p className="text-[10px] uppercase tracking-wider text-zinc-500 dark:text-zinc-400 font-semibold">Members</p>
                    <p className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">{data.stats.members}</p>
                  </div>
                  <div className="bg-zinc-50 dark:bg-zinc-800/60 rounded-md p-3">
                    <p className="text-[10px] uppercase tracking-wider text-zinc-500 dark:text-zinc-400 font-semibold">Bookings 30d</p>
                    <p className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">{data.stats.bookings_30d}</p>
                  </div>
                  <div className="bg-zinc-50 dark:bg-zinc-800/60 rounded-md p-3">
                    <p className="text-[10px] uppercase tracking-wider text-zinc-500 dark:text-zinc-400 font-semibold">Standardisation</p>
                    <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100 mt-1">
                      {data.organization.overrides_enabled ? (
                        <Pill tone="amber"><SlidersHorizontal size={10} className="mr-1" /> Customised</Pill>
                      ) : (
                        <Pill tone="green"><ShieldCheck size={10} className="mr-1" /> Standard</Pill>
                      )}
                    </p>
                  </div>
                </div>

                <SectionCard title={`Plans (${data.plans.length})`}>
                  {data.plans.length === 0 ? (
                    <p className="text-xs text-zinc-500 dark:text-zinc-400">No plans.</p>
                  ) : (
                    <div className="space-y-1.5">
                      {data.plans.map((p) => (
                        <div key={p.id} className="flex items-center justify-between py-1.5 border-b border-zinc-100 dark:border-zinc-800 last:border-b-0">
                          <div>
                            <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">{p.name}</p>
                            <p className="text-[11px] text-zinc-600 dark:text-zinc-400">{p.billing_cycle} · {p.kind} · {p.included_classes}</p>
                          </div>
                          <div className="text-right">
                            <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">{fmtMoney(p.price_pence)}</p>
                            {p.from_template_id && <Pill tone="blue">From template</Pill>}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </SectionCard>

                <SectionCard title={`Class templates (${data.classes.length})`}>
                  {data.classes.length === 0 ? (
                    <p className="text-xs text-zinc-500 dark:text-zinc-400">No classes.</p>
                  ) : (
                    <div className="grid grid-cols-2 gap-1.5">
                      {data.classes.map((c) => (
                        <div key={c.id} className="flex items-center gap-2 py-1.5">
                          <span className="w-2.5 h-2.5 rounded-full" style={{ background: c.colour || 'var(--color-brand-cyan)' }} />
                          <span className="text-sm text-zinc-800 dark:text-zinc-200 truncate">{c.name}</span>
                          <span className="text-[11px] text-zinc-500 dark:text-zinc-400">cap {c.capacity}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </SectionCard>

                <SectionCard title="Recent audit">
                  {data.audit.length === 0 ? (
                    <p className="text-xs text-zinc-500 dark:text-zinc-400">No actions recorded.</p>
                  ) : (
                    <ul className="space-y-1.5 text-xs">
                      {data.audit.map((a) => (
                        <li key={a.id} className="flex items-center justify-between">
                          <span className="text-zinc-600 dark:text-zinc-400"><span className="font-medium text-zinc-800 dark:text-zinc-200">{a.action}</span> · {a.by}</span>
                          <span className="text-zinc-500 dark:text-zinc-400">{new Date(a.at).toLocaleString()}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </SectionCard>
              </div>
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
};

export default OrgDrawer;
