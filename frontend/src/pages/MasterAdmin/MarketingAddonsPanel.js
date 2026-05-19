/**
 * MarketingAddonsPanel — Master Admin · Marketing module add-on packs.
 *
 * Catalog CRUD: name / code / price / included emails / SMS. Used by the
 * customer-facing EmailVolumePanel.
 */
import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Plus, Trash2, Save, RefreshCw, Mail, MessageSquare, Loader2 } from 'lucide-react';
import { notify } from '@/components/notifications';

const blank = () => ({
  code: '', name: '', kind: 'email',
  monthly_price_pence: 1900, included_emails: 25000, included_sms: 0,
  active: true, sort_order: 0,
});

const fmtMoney = (pence) => `£${(Number(pence || 0) / 100).toFixed(2)}`;

const MarketingAddonsPanel = () => {
  const { API } = useAuth();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [draft, setDraft] = useState(blank());
  const [saving, setSaving] = useState(false);
  const [editId, setEditId] = useState(null);
  const [editDraft, setEditDraft] = useState({});

  const headers = () => ({ Authorization: `Bearer ${localStorage.getItem('token')}` });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/master-admin/marketing/addons`, { headers: headers() });
      setRows(r.data?.rows || []);
      if (r.data?.seeded > 0) notify.success('Add-ons seeded', `${r.data.seeded} default packs added.`);
    } catch (e) {
      notify.error('Could not load add-ons', e.response?.data?.detail);
    }
    setLoading(false);
  }, [API]);
  useEffect(() => { load(); }, [load]);

  const create = async () => {
    if (!draft.code || !draft.name) {
      notify.error('Missing fields', 'Code and name required.');
      return;
    }
    setSaving(true);
    try {
      await axios.post(`${API}/master-admin/marketing/addons`, draft, { headers: headers() });
      notify.success('Pack added', draft.name);
      setDraft(blank());
      await load();
    } catch (e) {
      notify.error('Add failed', e.response?.data?.detail);
    }
    setSaving(false);
  };

  const startEdit = (row) => { setEditId(row.id); setEditDraft({ ...row }); };
  const saveEdit = async () => {
    setSaving(true);
    try {
      await axios.put(`${API}/master-admin/marketing/addons/${editId}`, editDraft, { headers: headers() });
      notify.success('Pack updated', editDraft.name);
      setEditId(null);
      setEditDraft({});
      await load();
    } catch (e) {
      notify.error('Update failed', e.response?.data?.detail);
    }
    setSaving(false);
  };
  const remove = async (row) => {
    if (!window.confirm(`Delete the "${row.name}" pack? Existing org attachments using its code will keep working until detached.`)) return;
    try {
      await axios.delete(`${API}/master-admin/marketing/addons/${row.id}`, { headers: headers() });
      notify.success('Pack removed', row.name);
      await load();
    } catch (e) {
      notify.error('Delete failed', e.response?.data?.detail);
    }
  };

  return (
    <div className="space-y-4" data-testid="marketing-addons-panel">
      <Card className="p-4 border-zinc-200">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <div>
            <h4 className="text-sm font-semibold text-zinc-900 flex items-center gap-2"><Mail size={15} className="text-fuchsia-600" /> Marketing add-on packs</h4>
            <p className="text-[11px] text-zinc-500 mt-0.5">Email-volume + SMS bolt-ons that customers can attach on top of the £39/mo Marketing module base. Base = 5,000 emails / month included.</p>
          </div>
          <Button size="sm" variant="outline" onClick={load} data-testid="addons-refresh">
            <RefreshCw size={12} className="mr-1" /> Refresh
          </Button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-12 gap-2 p-3 bg-zinc-50 rounded-lg border border-dashed border-zinc-200" data-testid="addon-add-row">
          <Input placeholder="code (snake_case)" value={draft.code} onChange={(e) => setDraft({ ...draft, code: e.target.value })} className="md:col-span-2 h-9" data-testid="addon-add-code" />
          <Input placeholder="Display name" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} className="md:col-span-3 h-9" data-testid="addon-add-name" />
          <select value={draft.kind} onChange={(e) => setDraft({ ...draft, kind: e.target.value })} className="md:col-span-1 h-9 rounded-md border border-zinc-200 bg-white px-2 text-sm" data-testid="addon-add-kind">
            <option value="email">Email</option>
            <option value="sms">SMS</option>
          </select>
          <Input type="number" placeholder="£ pence" value={draft.monthly_price_pence} onChange={(e) => setDraft({ ...draft, monthly_price_pence: parseInt(e.target.value || 0, 10) })} className="md:col-span-2 h-9" data-testid="addon-add-price" />
          <Input type="number" placeholder="+ emails" value={draft.included_emails} onChange={(e) => setDraft({ ...draft, included_emails: parseInt(e.target.value || 0, 10) })} className="md:col-span-2 h-9" data-testid="addon-add-emails" />
          <Input type="number" placeholder="+ SMS" value={draft.included_sms} onChange={(e) => setDraft({ ...draft, included_sms: parseInt(e.target.value || 0, 10) })} className="md:col-span-1 h-9" data-testid="addon-add-sms" />
          <Button onClick={create} disabled={saving} className="md:col-span-1 h-9 bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white" data-testid="addon-add-btn">
            {saving ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
          </Button>
        </div>
      </Card>

      <div className="bg-white border border-zinc-200 rounded-lg overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[11px] uppercase tracking-wider text-zinc-400 border-b border-zinc-100">
              <th className="text-left px-3 py-2.5 font-semibold">Pack</th>
              <th className="text-left px-3 py-2.5 font-semibold">Code</th>
              <th className="text-left px-3 py-2.5 font-semibold">Kind</th>
              <th className="text-right px-3 py-2.5 font-semibold">+ Emails</th>
              <th className="text-right px-3 py-2.5 font-semibold">+ SMS</th>
              <th className="text-right px-3 py-2.5 font-semibold">Monthly</th>
              <th className="text-center px-3 py-2.5 font-semibold">Active</th>
              <th className="text-right px-3 py-2.5 font-semibold">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={8} className="px-3 py-8 text-center text-zinc-400 text-sm">Loading…</td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={8} className="px-3 py-8 text-center text-zinc-400 text-sm">No add-ons yet.</td></tr>
            ) : rows.map((row) => {
              const editing = editId === row.id;
              return (
                <tr key={row.id} className="border-b border-zinc-50" data-testid={`addon-row-${row.code}`}>
                  <td className="px-3 py-2">{editing ? <Input value={editDraft.name} onChange={(e) => setEditDraft({ ...editDraft, name: e.target.value })} className="h-7 text-xs" /> : <span className="font-medium">{row.name}</span>}</td>
                  <td className="px-3 py-2 text-xs font-mono text-zinc-500">{row.code}</td>
                  <td className="px-3 py-2 text-xs">
                    {row.kind === 'sms' ? <MessageSquare size={12} className="inline text-violet-500" /> : <Mail size={12} className="inline text-blue-500" />} {row.kind}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{editing ? <Input type="number" value={editDraft.included_emails} onChange={(e) => setEditDraft({ ...editDraft, included_emails: parseInt(e.target.value || 0, 10) })} className="h-7 text-xs text-right" /> : (row.included_emails || 0).toLocaleString()}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{editing ? <Input type="number" value={editDraft.included_sms} onChange={(e) => setEditDraft({ ...editDraft, included_sms: parseInt(e.target.value || 0, 10) })} className="h-7 text-xs text-right" /> : (row.included_sms || 0).toLocaleString()}</td>
                  <td className="px-3 py-2 text-right tabular-nums font-semibold">{editing ? <Input type="number" value={editDraft.monthly_price_pence} onChange={(e) => setEditDraft({ ...editDraft, monthly_price_pence: parseInt(e.target.value || 0, 10) })} className="h-7 text-xs text-right" /> : fmtMoney(row.monthly_price_pence)}</td>
                  <td className="px-3 py-2 text-center">
                    <input type="checkbox" checked={editing ? !!editDraft.active : !!row.active} onChange={(e) => editing && setEditDraft({ ...editDraft, active: e.target.checked })} disabled={!editing} />
                  </td>
                  <td className="px-3 py-2 text-right whitespace-nowrap">
                    {editing ? (
                      <>
                        <Button size="sm" onClick={saveEdit} disabled={saving} className="h-7 text-[11px] bg-emerald-600 hover:bg-emerald-700 text-white mr-1" data-testid={`addon-save-${row.id}`}>
                          <Save size={11} className="mr-1" /> Save
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => { setEditId(null); setEditDraft({}); }} className="h-7 text-[11px]">Cancel</Button>
                      </>
                    ) : (
                      <>
                        <Button size="sm" variant="outline" onClick={() => startEdit(row)} className="h-7 text-[11px] mr-1" data-testid={`addon-edit-${row.id}`}>Edit</Button>
                        <Button size="sm" variant="ghost" onClick={() => remove(row)} className="h-7 text-[11px] text-rose-600 hover:bg-rose-50" data-testid={`addon-delete-${row.id}`}>
                          <Trash2 size={11} />
                        </Button>
                      </>
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

export default MarketingAddonsPanel;
