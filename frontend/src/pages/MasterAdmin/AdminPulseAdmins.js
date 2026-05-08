/**
 * Pulse Master Admins management — list, provision, and revoke delegated
 * Pulse-side master admins. Visible only to the platform-level GymAxis
 * Master Admin (not to the Pulse Master Admins themselves).
 */
import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Plus, Trash2, RefreshCw, Mail, ShieldCheck, AlertCircle, Copy, KeyRound } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card } from '@/components/ui/card';
import { useInlineBanner, useConfirm } from '@/components/notifications';
import { SkeletonLine, SkeletonCircle } from '@/components/shared/Skeleton';

const AdminPulseAdmins = ({ API }) => {
 const token = localStorage.getItem('token');
 const headers = { Authorization: `Bearer ${token}` };
 const [admins, setAdmins] = useState([]);
 const [loading, setLoading] = useState(true);
 const [form, setForm] = useState({ email: '', full_name: '' });
 const [busy, setBusy] = useState(false);
 const [pendingTempPwd, setPendingTempPwd] = useState(null);
 const { banner, show, clear } = useInlineBanner();
 const confirm = useConfirm();

 const load = useCallback(async () => {
 setLoading(true);
 try {
 const { data } = await axios.get(`${API}/master-admin/pulse-admins`, { headers });
 setAdmins(data.admins || []);
 } catch (err) {
 show({ tone: 'error', title: 'Couldn\'t load admins', detail: err.response?.data?.detail });
 }
 setLoading(false);
 }, [API]);
 useEffect(() => { load(); }, [load]);

 const provision = async (e) => {
 e.preventDefault();
 clear();
 setPendingTempPwd(null);
 if (!form.email.trim() || !form.full_name.trim()) {
 show({ tone: 'error', title: 'Email and full name are required' });
 return;
 }
 setBusy(true);
 try {
 const { data } = await axios.post(`${API}/master-admin/pulse-admins`, {
 email: form.email.trim().toLowerCase(),
 full_name: form.full_name.trim(),
 }, { headers });
 if (data.email_sent) {
 show({
 tone: 'success',
 title: 'Pulse Master Admin provisioned',
 detail: `Temporary password emailed to ${data.email}. They'll be asked to set a permanent one on first login.`,
 });
 } else {
 // Email failed — surface the temp password so the platform admin can pass it on manually.
 setPendingTempPwd(data.temp_password);
 show({
 tone: 'warning',
 title: 'User created — but email failed',
 detail: 'Copy the temporary password below and share it via a secure channel.',
 });
 }
 setForm({ email: '', full_name: '' });
 load();
 } catch (err) {
 show({ tone: 'error', title: 'Couldn\'t provision', detail: err.response?.data?.detail });
 }
 setBusy(false);
 };

 const revoke = async (admin) => {
 const ok = await confirm({
 title: `Revoke access for ${admin.full_name}?`,
 body: `${admin.email} will no longer be able to sign in. Their audit-log history is preserved.`,
 tone: 'danger',
 confirmLabel: 'Revoke access',
 });
 if (!ok) return;
 try {
 await axios.delete(`${API}/master-admin/pulse-admins/${admin.id}`, { headers });
 show({ tone: 'success', title: 'Access revoked' });
 load();
 } catch (err) {
 show({ tone: 'error', title: 'Couldn\'t revoke', detail: err.response?.data?.detail });
 }
 };

 const reissueTempPwd = async (admin) => {
 const ok = await confirm({
 title: `Re-issue temp password for ${admin.full_name}?`,
 body: `A fresh 7-day temp password will be emailed to ${admin.email}. Their existing session will be invalidated and they'll be asked to set a new permanent password on next login.`,
 tone: 'warning',
 confirmLabel: 'Re-issue & email',
 });
 if (!ok) return;
 setPendingTempPwd(null);
 clear();
 try {
 const { data } = await axios.post(
 `${API}/master-admin/pulse-admins/${admin.id}/reissue-temp-password`, {}, { headers },
 );
 if (data.email_sent) {
 show({
 tone: 'success',
 title: 'Temp password re-issued',
 detail: `New password emailed to ${admin.email} — valid for 7 days.`,
 });
 } else {
 setPendingTempPwd(data.temp_password);
 show({
 tone: 'warning',
 title: 'Password rotated — but email failed',
 detail: 'Copy the temp password below and share it via a secure channel.',
 });
 }
 load();
 } catch (err) {
 show({ tone: 'error', title: 'Couldn\'t re-issue', detail: err.response?.data?.detail });
 }
 };

 return (
 <div className="space-y-6" data-testid="admin-pulse-admins">
 {banner}

 {/* Provision new */}
 <Card className="p-5 rounded-xl border-zinc-200">
 <div className="flex items-center gap-2 mb-4">
 <ShieldCheck size={18} className="text-[var(--color-brand-blue)]" />
 <h2 className="text-base font-semibold">Provision Pulse Master Admin</h2>
 </div>
 <p className="text-xs text-zinc-500 mb-4 leading-relaxed">
 Pulse Master Admins see the same Master Admin console you use, but with all data
 scoped to Pulse Fitness only. They can manage Pulse customers, payments, MOD sites,
 analytics, integrations, and Stripe — but cannot see other GymAxis-internal data.
 </p>
 <form onSubmit={provision} className="grid grid-cols-1 md:grid-cols-2 gap-3" data-testid="provision-pulse-admin-form">
 <div>
 <Label className="text-xs">Full name</Label>
 <Input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} placeholder="Craig Henshall" className="mt-1" data-testid="pulse-admin-name" />
 </div>
 <div>
 <Label className="text-xs">Email</Label>
 <Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="craig@pulsefitness.com" className="mt-1" data-testid="pulse-admin-email" />
 </div>
 <div className="md:col-span-2">
 <Button type="submit" disabled={busy} className="bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white rounded-full" data-testid="pulse-admin-submit">
 {busy ? 'Provisioning…' : <><Plus size={14} className="mr-1" /> Send invite</>}
 </Button>
 </div>
 </form>

 {pendingTempPwd && (
 <div className="mt-4 p-3 rounded-lg bg-amber-50 border border-amber-200 flex items-start gap-3" data-testid="pending-temp-pwd">
 <AlertCircle size={16} className="text-amber-700 mt-0.5 shrink-0" />
 <div className="flex-1 min-w-0">
 <p className="text-xs font-semibold text-amber-900 uppercase tracking-wider mb-1">Temporary password (one-time)</p>
 <div className="flex items-center gap-2">
 <code className="flex-1 text-sm font-mono bg-white px-2 py-1 rounded border border-amber-200 truncate">{pendingTempPwd}</code>
 <Button
 size="sm"
 variant="outline"
 onClick={() => {
 navigator.clipboard.writeText(pendingTempPwd);
 show({ tone: 'success', title: 'Copied to clipboard' });
 }}
 data-testid="copy-temp-pwd"
 >
 <Copy size={12} />
 </Button>
 </div>
 <p className="text-[11px] text-amber-800 mt-1.5">
 Share this via a secure channel. It expires in 7 days.
 </p>
 </div>
 </div>
 )}
 </Card>

 {/* Existing list */}
 <Card className="p-5 rounded-xl border-zinc-200">
 <div className="flex items-center justify-between mb-4">
 <h2 className="text-base font-semibold">Provisioned admins ({admins.length})</h2>
 <Button size="sm" variant="outline" onClick={load} disabled={loading} className="text-zinc-600">
 <RefreshCw size={12} className={`mr-1 ${loading ? 'animate-spin' : ''}`} /> Refresh
 </Button>
 </div>
 {loading ? (
 <div className="py-2 space-y-3" data-testid="pulse-admin-loading">
 {[0,1,2].map(i => (
 <div key={i} className="flex items-center gap-3 py-2.5">
 <SkeletonCircle size={32} />
 <div className="flex-1 space-y-2">
 <SkeletonLine width="40%" />
 <SkeletonLine width="65%" />
 </div>
 <SkeletonLine width={60} />
 </div>
 ))}
 </div>
 ) : admins.length === 0 ? (
 <div className="py-8 text-center text-zinc-400 text-sm" data-testid="pulse-admin-empty">
 No Pulse Master Admins yet — provision one above to delegate Pulse-side platform management.
 </div>
 ) : (
 <ul className="divide-y divide-zinc-100">
 {admins.map((a) => (
 <li key={a.id} className="py-3 flex items-center gap-3" data-testid={`pulse-admin-row-${a.id}`}>
 <div className="w-9 h-9 rounded-full bg-zinc-100 grid place-items-center text-zinc-500">
 <Mail size={14} />
 </div>
 <div className="flex-1 min-w-0">
 <p className="text-sm font-medium text-zinc-900 truncate">
 {a.full_name}
 {a.must_change_password && <span className="ml-2 text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200 align-middle">awaiting first login</span>}
 {a.active === false && <span className="ml-2 text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-zinc-100 text-zinc-500 border border-zinc-200 align-middle">revoked</span>}
 </p>
 <p className="text-xs text-zinc-500 truncate">{a.email}</p>
 <p className="text-[11px] text-zinc-400 mt-0.5">
 Created {a.created_at ? new Date(a.created_at).toLocaleDateString() : '—'}
 {a.last_login ? ` · Last login ${new Date(a.last_login).toLocaleString()}` : ' · never logged in'}
 </p>
 </div>
 {a.active !== false && (
 <div className="flex items-center gap-1">
 <Button
 size="sm"
 variant="ghost"
 onClick={() => reissueTempPwd(a)}
 className="text-amber-600 hover:text-amber-700 hover:bg-amber-50"
 title="Re-issue temporary password & email"
 data-testid={`pulse-admin-reissue-${a.id}`}
 >
 <KeyRound size={14} />
 </Button>
 <Button size="sm" variant="ghost" onClick={() => revoke(a)} className="text-red-500 hover:text-red-700 hover:bg-red-50" data-testid={`pulse-admin-revoke-${a.id}`}>
 <Trash2 size={14} />
 </Button>
 </div>
 )}
 </li>
 ))}
 </ul>
 )}
 </Card>
 </div>
 );
};

export default AdminPulseAdmins;
