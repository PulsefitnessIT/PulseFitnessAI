/**
 * SiteStaffManager — commercial "Site Staff & Shared Site Login".
 *
 * Managers/owners use this to:
 *   • enable a shared site login (one username + password for the site)
 *   • maintain the authorised site-staff list (name, job title, email, phone)
 *   • deactivate / reactivate / transfer staff between sites
 *   • configure whether staff selection is mandatory before logging a fault
 *
 * Site staff then sign in on the normal landing page with the shared login
 * and must pick their name from the mandatory dropdown when logging a fault.
 */
import React, { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import {
  KeyRound, Loader2, Copy, Check, Plus, Pencil, UserX, UserCheck,
  ArrowRightLeft, RefreshCw, Power, Users, Phone, Mail, ShieldCheck,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { useAuth } from '@/App';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const EMPTY_STAFF = {
  first_name: '', last_name: '', job_title: '', email: '', phone: '',
  department: '', notes: '', receive_job_updates: true,
};

export default function SiteStaffManager({ headers }) {
  const { sites } = useAuth();
  const siteList = useMemo(() => sites || [], [sites]);
  const [siteId, setSiteId] = useState('');
  const [staff, setStaff] = useState([]);
  const [shared, setShared] = useState(null);
  const [loading, setLoading] = useState(false);

  const [showAdd, setShowAdd] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY_STAFF);
  const [transferring, setTransferring] = useState(null);
  const [transferTo, setTransferTo] = useState('');
  const [credential, setCredential] = useState(null); // {username,password}
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!siteId && siteList.length) setSiteId(siteList[0].id);
  }, [siteList, siteId]);

  const load = useCallback(async () => {
    if (!siteId) return;
    setLoading(true);
    try {
      const [s, sl] = await Promise.all([
        axios.get(`${API}/site-staff?site_id=${siteId}`, { headers }),
        axios.get(`${API}/sites/${siteId}/shared-login`, { headers }),
      ]);
      setStaff(s.data.staff || []);
      setShared(sl.data);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Could not load site staff');
    }
    setLoading(false);
  }, [siteId, headers]);

  useEffect(() => { load(); }, [load]);

  const saveStaff = async () => {
    if (!form.first_name || !form.last_name || !form.job_title || !form.email || !form.phone) {
      toast.error('First name, last name, job title, email and phone are required');
      return;
    }
    try {
      if (editing) {
        await axios.patch(`${API}/site-staff/${editing.id}`, form, { headers });
        toast.success('Staff updated');
      } else {
        await axios.post(`${API}/site-staff`, { ...form, site_id: siteId }, { headers });
        toast.success('Staff added');
      }
      setShowAdd(false); setEditing(null); setForm(EMPTY_STAFF);
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Save failed');
    }
  };

  const toggleActive = async (s) => {
    const action = s.is_active === false ? 'reactivate' : 'deactivate';
    try {
      await axios.post(`${API}/site-staff/${s.id}/${action}`, {}, { headers });
      load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const doTransfer = async () => {
    if (!transferTo) { toast.error('Pick a destination site'); return; }
    try {
      await axios.post(`${API}/site-staff/${transferring.id}/transfer`, { to_site_id: transferTo }, { headers });
      toast.success('Staff transferred');
      setTransferring(null); setTransferTo('');
      load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Transfer failed'); }
  };

  const provision = async (rotate) => {
    try {
      const r = await axios.post(`${API}/sites/${siteId}/shared-login/provision`, { rotate }, { headers });
      setCredential(r.data);
      toast.success(rotate ? 'Password rotated' : 'Shared login created');
      load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Provision failed'); }
  };

  const disableLogin = async () => {
    try {
      await axios.post(`${API}/sites/${siteId}/shared-login/disable`, {}, { headers });
      toast.success('Shared login disabled');
      load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const updateSetting = async (key, value) => {
    try {
      const r = await axios.patch(`${API}/sites/${siteId}/shared-login/settings`, { [key]: value }, { headers });
      setShared((p) => ({ ...p, settings: r.data.settings }));
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const settings = shared?.settings || {};

  return (
    <div className="space-y-6" data-testid="site-staff-manager">
      {/* Site selector */}
      <div className="flex items-center gap-3">
        <Label className="text-sm" style={{ color: 'var(--theme-text-muted)' }}>Site</Label>
        <Select value={siteId} onValueChange={setSiteId}>
          <SelectTrigger className="w-72" data-testid="site-staff-site-select"><SelectValue placeholder="Choose a site" /></SelectTrigger>
          <SelectContent>
            {siteList.map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}
          </SelectContent>
        </Select>
        {loading && <Loader2 className="animate-spin" size={16} />}
      </div>

      {/* Shared login panel */}
      <div className="rounded-xl border p-5" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }} data-testid="shared-login-panel">
        <div className="flex items-center gap-2 mb-1">
          <KeyRound size={18} className="text-indigo-500" />
          <h3 className="font-semibold" style={{ color: 'var(--theme-text)' }}>Shared Site Login</h3>
          {shared?.enabled && <span className="text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-700" data-testid="shared-login-status">Enabled</span>}
        </div>
        <p className="text-xs mb-4" style={{ color: 'var(--theme-text-muted)' }}>
          One username &amp; password for general site staff. Staff still pick their name when logging a fault, so your service team knows who to contact.
        </p>

        {shared?.enabled ? (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm" style={{ color: 'var(--theme-text)' }}>
              <span><b>Username:</b> <code data-testid="shared-login-username">{shared.username}</code></span>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" onClick={() => provision(true)} data-testid="shared-login-rotate"><RefreshCw size={14} className="mr-1.5" />Reset password</Button>
              <Button size="sm" variant="outline" className="text-red-600 border-red-200" onClick={disableLogin} data-testid="shared-login-disable"><Power size={14} className="mr-1.5" />Disable</Button>
            </div>
            <div className="border-t pt-4 space-y-3" style={{ borderColor: 'var(--theme-border)' }}>
              <SettingRow label="Require staff selection before logging a fault" testid="setting-require-staff"
                checked={settings.require_staff_selection !== false} onChange={(v) => updateSetting('require_staff_selection', v)} />
              <SettingRow label='Allow an "Other staff member" option (manual name + contact)' testid="setting-allow-other"
                checked={!!settings.allow_other_staff} onChange={(v) => updateSetting('allow_other_staff', v)} />
              <SettingRow label="Notify site manager when a fault is logged" testid="setting-notify-manager"
                checked={!!settings.notify_manager} onChange={(v) => updateSetting('notify_manager', v)} />
              <SettingRow label="Notify the selected staff member" testid="setting-notify-staff"
                checked={!!settings.notify_staff} onChange={(v) => updateSetting('notify_staff', v)} />
            </div>
          </div>
        ) : (
          <Button size="sm" onClick={() => provision(false)} disabled={!siteId} data-testid="shared-login-enable">
            <KeyRound size={14} className="mr-1.5" />Enable shared login
          </Button>
        )}
      </div>

      {/* Staff list */}
      <div className="rounded-xl border p-5" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }}>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Users size={18} className="text-[var(--color-brand-blue)]" />
            <h3 className="font-semibold" style={{ color: 'var(--theme-text)' }}>Site Staff</h3>
            <span className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>({staff.filter((s) => s.is_active !== false).length} active)</span>
          </div>
          <Button size="sm" onClick={() => { setEditing(null); setForm(EMPTY_STAFF); setShowAdd(true); }} disabled={!siteId} data-testid="site-staff-add">
            <Plus size={14} className="mr-1.5" />Add staff
          </Button>
        </div>

        {staff.length === 0 ? (
          <p className="text-sm py-6 text-center" style={{ color: 'var(--theme-text-muted)' }} data-testid="site-staff-empty">
            No site staff yet. Add the people who work at this site so they can log faults.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="site-staff-table">
              <thead>
                <tr className="text-left" style={{ color: 'var(--theme-text-muted)' }}>
                  <th className="py-2 pr-3 font-medium">Name</th>
                  <th className="py-2 pr-3 font-medium">Job title</th>
                  <th className="py-2 pr-3 font-medium">Contact</th>
                  <th className="py-2 pr-3 font-medium">Faults</th>
                  <th className="py-2 pr-3 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {staff.map((s) => (
                  <tr key={s.id} className="border-t" style={{ borderColor: 'var(--theme-border)', opacity: s.is_active === false ? 0.5 : 1 }} data-testid={`site-staff-row-${s.id}`}>
                    <td className="py-2 pr-3" style={{ color: 'var(--theme-text)' }}>{s.full_name}{s.is_active === false && <span className="ml-2 text-xs text-red-500">inactive</span>}</td>
                    <td className="py-2 pr-3" style={{ color: 'var(--theme-text-muted)' }}>{s.job_title}</td>
                    <td className="py-2 pr-3" style={{ color: 'var(--theme-text-muted)' }}>
                      <div className="flex items-center gap-1"><Mail size={11} />{s.email}</div>
                      <div className="flex items-center gap-1"><Phone size={11} />{s.phone}</div>
                    </td>
                    <td className="py-2 pr-3" style={{ color: 'var(--theme-text-muted)' }}>{s.fault_count || 0}</td>
                    <td className="py-2 pr-3">
                      <div className="flex items-center justify-end gap-1">
                        <Button size="icon" variant="ghost" title="Edit" onClick={() => { setEditing(s); setForm({ ...EMPTY_STAFF, ...s }); setShowAdd(true); }} data-testid={`site-staff-edit-${s.id}`}><Pencil size={14} /></Button>
                        <Button size="icon" variant="ghost" title="Transfer" onClick={() => { setTransferring(s); setTransferTo(''); }} data-testid={`site-staff-transfer-${s.id}`}><ArrowRightLeft size={14} /></Button>
                        <Button size="icon" variant="ghost" title={s.is_active === false ? 'Reactivate' : 'Deactivate'} onClick={() => toggleActive(s)} data-testid={`site-staff-toggle-${s.id}`}>
                          {s.is_active === false ? <UserCheck size={14} className="text-green-600" /> : <UserX size={14} className="text-red-500" />}
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Add/Edit dialog */}
      <Dialog open={showAdd} onOpenChange={setShowAdd}>
        <DialogContent data-testid="site-staff-dialog">
          <DialogHeader><DialogTitle>{editing ? 'Edit staff member' : 'Add staff member'}</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div><Label>First name</Label><Input value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} data-testid="staff-first-name" /></div>
            <div><Label>Last name</Label><Input value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} data-testid="staff-last-name" /></div>
            <div className="col-span-2"><Label>Job title</Label><Input value={form.job_title} onChange={(e) => setForm({ ...form, job_title: e.target.value })} data-testid="staff-job-title" /></div>
            <div><Label>Email</Label><Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} data-testid="staff-email" /></div>
            <div><Label>Phone</Label><Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} data-testid="staff-phone" /></div>
            <div className="col-span-2"><Label>Department (optional)</Label><Input value={form.department || ''} onChange={(e) => setForm({ ...form, department: e.target.value })} data-testid="staff-department" /></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAdd(false)}>Cancel</Button>
            <Button onClick={saveStaff} data-testid="staff-save">{editing ? 'Save changes' : 'Add staff'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Transfer dialog */}
      <Dialog open={!!transferring} onOpenChange={(o) => !o && setTransferring(null)}>
        <DialogContent data-testid="site-staff-transfer-dialog">
          <DialogHeader><DialogTitle>Transfer {transferring?.full_name}</DialogTitle></DialogHeader>
          <Label>Move to site</Label>
          <Select value={transferTo} onValueChange={setTransferTo}>
            <SelectTrigger data-testid="transfer-site-select"><SelectValue placeholder="Choose destination site" /></SelectTrigger>
            <SelectContent>
              {siteList.filter((s) => s.id !== transferring?.site_id).map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}
            </SelectContent>
          </Select>
          <DialogFooter>
            <Button variant="outline" onClick={() => setTransferring(null)}>Cancel</Button>
            <Button onClick={doTransfer} data-testid="transfer-confirm">Transfer</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Credential reveal dialog (shown once) */}
      <Dialog open={!!credential} onOpenChange={(o) => !o && setCredential(null)}>
        <DialogContent data-testid="shared-login-credential-dialog">
          <DialogHeader><DialogTitle className="flex items-center gap-2"><ShieldCheck size={18} className="text-green-600" />Shared login credentials</DialogTitle></DialogHeader>
          <p className="text-sm" style={{ color: 'var(--theme-text-muted)' }}>Share these with your site staff. The password is shown only once.</p>
          <div className="rounded-lg border p-4 space-y-2 font-mono text-sm" style={{ borderColor: 'var(--theme-border)' }}>
            <div>Username: <b data-testid="credential-username">{credential?.username}</b></div>
            <div>Password: <b data-testid="credential-password">{credential?.password}</b></div>
          </div>
          <DialogFooter>
            <Button onClick={() => {
              navigator.clipboard?.writeText(`Username: ${credential.username}\nPassword: ${credential.password}`);
              setCopied(true); setTimeout(() => setCopied(false), 1500);
            }} data-testid="credential-copy">
              {copied ? <Check size={14} className="mr-1.5" /> : <Copy size={14} className="mr-1.5" />}Copy
            </Button>
            <Button variant="outline" onClick={() => setCredential(null)}>Done</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function SettingRow({ label, checked, onChange, testid }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-sm" style={{ color: 'var(--theme-text)' }}>{label}</span>
      <Switch checked={checked} onCheckedChange={onChange} data-testid={testid} />
    </div>
  );
}
