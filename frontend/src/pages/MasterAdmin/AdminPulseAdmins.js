/**
 * Pulse Master Admins management — list, provision, and revoke delegated
 * Pulse-side master admins. Visible only to the platform-level Pulse Fitness
 * Master Admin (not to the Pulse Master Admins themselves).
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Plus, Trash2, RefreshCw, Mail, ShieldCheck, AlertCircle, Copy, KeyRound, Building2, X as XIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
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
 const [orgs, setOrgs] = useState([]);
 const [editingMembership, setEditingMembership] = useState(null);   // admin id
 const [draftMemberships, setDraftMemberships] = useState([]);
 const { banner, show, clear } = useInlineBanner();
 const confirm = useConfirm();

 const load = useCallback(async () => {
 setLoading(true);
 try {
 const [a, o] = await Promise.all([
 axios.get(`${API}/master-admin/pulse-admins`, { headers }),
 axios.get(`${API}/master-admin/organizations`, { headers }),
 ]);
 setAdmins(a.data.admins || []);
 setOrgs(o.data.organizations || []);
 } catch (err) {
 show({ tone: 'error', title: 'Couldn\'t load admins', detail: err.response?.data?.detail });
 }
 setLoading(false);
 // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: context helpers re-create each render but read the latest token / handler at call time; adding them would invalidate the memo every render and break the optimisation.
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

 const openMembershipEditor = (admin) => {
 setEditingMembership(admin.id);
 setDraftMemberships(admin.organization_memberships || []);
 };

 const closeMembershipEditor = () => {
 setEditingMembership(null);
 setDraftMemberships([]);
 };

 const toggleMembershipOrg = (orgId) => {
 setDraftMemberships((prev) => (
 prev.includes(orgId) ? prev.filter((o) => o !== orgId) : [...prev, orgId]
 ));
 };

 const saveMemberships = async (admin) => {
 try {
 await axios.put(
 `${API}/master-admin/pulse-admins/${admin.id}/org-memberships`,
 { organization_ids: draftMemberships },
 { headers },
 );
 show({
 tone: 'success',
 title: 'Gym attachments updated',
 detail: `${admin.full_name} now appears in ${draftMemberships.length} attached gym${draftMemberships.length === 1 ? '' : 's'}.`,
 });
 closeMembershipEditor();
 load();
 } catch (err) {
 show({ tone: 'error', title: 'Couldn\'t save attachments', detail: err.response?.data?.detail });
 }
 };

 const detachOrg = async (admin, orgId) => {
 const remaining = (admin.organization_memberships || []).filter((o) => o !== orgId);
 try {
 await axios.put(
 `${API}/master-admin/pulse-admins/${admin.id}/org-memberships`,
 { organization_ids: remaining },
 { headers },
 );
 show({ tone: 'success', title: 'Gym detached' });
 load();
 } catch (err) {
 show({ tone: 'error', title: 'Couldn\'t detach', detail: err.response?.data?.detail });
 }
 };

 const hardPurge = async (admin) => {
 const sure = window.confirm(
 `PERMANENTLY DELETE ${admin.full_name} (${admin.email})?\n\n`
 + 'This wipes the user row, invites, signup drafts, journey jobs, and tour bookings for that email. Cannot be undone.\n\n'
 + 'Use this when you want to re-onboard the same email cleanly.'
 );
 if (!sure) return;
 try {
 const r = await axios.delete(
 `${API}/master-admin/pulse-admins/${admin.id}/purge`,
 { headers },
 );
 const d = r.data?.deleted || {};
 show({
 tone: 'success',
 title: 'Permanently deleted',
 detail: `Wiped ${d.users || 0} user, ${d.invites || 0} invite(s), ${d.signup_drafts || 0} draft(s). The email is now free for re-onboarding.`,
 });
 load();
 } catch (err) {
 show({ tone: 'error', title: 'Purge failed', detail: err.response?.data?.detail });
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
 <div className="flex items-center gap-2 mb-2">
 <ShieldCheck size={18} className="text-[var(--color-brand-blue)]" />
 <h2 className="text-base font-semibold">Provision Pulse Platform Admin</h2>
 </div>
 <div className="mb-4 p-3 rounded-lg bg-amber-50 border border-amber-200 flex items-start gap-2 text-xs text-amber-800" data-testid="pulse-admin-warning">
 <AlertCircle size={14} className="mt-0.5 shrink-0" />
 <div>
 <strong>This is NOT for adding a member of staff to a single gym.</strong> Pulse
 Platform Admins are cross-org — they see ALL Pulse-customer gyms. To add a
 regular employee to one gym, go to <em>Master Admin → Organizations →
 [the gym] → expand → Users → Add user</em> instead.
 </div>
 </div>
 <p className="text-xs text-zinc-500 mb-4 leading-relaxed">
 Pulse Platform Admins see the same Master Admin console you use, but scoped to
 Pulse-customer data only. They can manage Pulse customers, payments, MOD sites,
 analytics, integrations, and Stripe — but cannot see other Pulse Fitness-internal data.
 </p>
 <form onSubmit={provision} className="grid grid-cols-1 md:grid-cols-2 gap-3" data-testid="provision-pulse-admin-form">
 <div>
 <Label className="text-xs">Full name</Label>
 <Input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} placeholder="e.g. Platform Operations Lead" className="mt-1" data-testid="pulse-admin-name" />
 </div>
 <div>
 <Label className="text-xs">Email</Label>
 <Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="e.g. ops@pulsefitness.com" className="mt-1" data-testid="pulse-admin-email" />
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
 <li key={a.id} className="py-3" data-testid={`pulse-admin-row-${a.id}`}>
 <div className="flex items-center gap-3">
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
 onClick={() => openMembershipEditor(a)}
 className="text-zinc-600 hover:text-[var(--color-brand-blue)] hover:bg-blue-50"
 title="Attach this admin to specific gyms (dual-role)"
 data-testid={`pulse-admin-attach-${a.id}`}
 >
 <Building2 size={14} />
 </Button>
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
 {a.active === false && (
 <Button
 size="sm"
 variant="outline"
 onClick={() => hardPurge(a)}
 className="border-red-300 text-red-700 hover:bg-red-600 hover:text-white hover:border-red-600 text-[11px] font-semibold"
 title="Permanently delete — wipes user row, invites, drafts, journey jobs. Cannot be undone. Use when you want to re-onboard with the same email."
 data-testid={`pulse-admin-purge-${a.id}`}
 >
 <Trash2 size={12} className="mr-1" /> Permanent delete
 </Button>
 )}
 </div>

 {/* Attached gyms pills */}
 {(a.membership_org_names || []).length > 0 && (
 <div className="mt-2 ml-12 flex flex-wrap items-center gap-1.5" data-testid={`pulse-admin-attached-${a.id}`}>
 <span className="text-[10px] uppercase tracking-wider text-zinc-400">Also a member of:</span>
 {a.membership_org_names.map((org) => (
 <Badge
 key={org.id}
 variant="outline"
 className="text-[11px] gap-1 pl-2 pr-1 py-0.5 bg-blue-50 border-blue-200 text-blue-800"
 data-testid={`pulse-admin-attached-pill-${a.id}-${org.id}`}
 >
 <Building2 size={10} />
 {org.name}
 {a.active !== false && (
 <button
 type="button"
 onClick={() => detachOrg(a, org.id)}
 className="ml-0.5 rounded-full p-0.5 hover:bg-blue-200"
 title={`Detach ${org.name}`}
 data-testid={`pulse-admin-detach-${a.id}-${org.id}`}
 >
 <XIcon size={10} />
 </button>
 )}
 </Badge>
 ))}
 </div>
 )}

 {/* Inline membership editor */}
 {editingMembership === a.id && (
 <div
 className="mt-3 ml-12 p-3 rounded-lg border border-blue-200 bg-blue-50/40"
 data-testid={`pulse-admin-membership-editor-${a.id}`}
 >
 <div className="flex items-center justify-between mb-2">
 <p className="text-xs font-semibold text-zinc-800">
 Attach <span className="text-[var(--color-brand-blue)]">{a.full_name}</span> to gyms
 </p>
 <Button
 size="sm"
 variant="ghost"
 onClick={closeMembershipEditor}
 className="h-6 px-2 text-zinc-500"
 data-testid={`pulse-admin-membership-close-${a.id}`}
 >
 <XIcon size={12} />
 </Button>
 </div>
 <p className="text-[11px] text-zinc-500 leading-relaxed mb-2">
 Tick a gym to make this admin also appear in that gym's Users list (as a Pulse
 Platform Admin). They keep their cross-org platform role — this is purely an
 additive dual-role assignment.
 </p>
 <div className="max-h-56 overflow-y-auto rounded border border-blue-100 bg-white divide-y divide-zinc-100">
 {orgs.length === 0 ? (
 <p className="p-3 text-xs text-zinc-400">No organizations available.</p>
 ) : orgs.map((o) => {
 const checked = draftMemberships.includes(o.id);
 return (
 <label
 key={o.id}
 className="flex items-center gap-2 px-3 py-2 text-xs cursor-pointer hover:bg-zinc-50"
 data-testid={`pulse-admin-membership-option-${a.id}-${o.id}`}
 >
 <input
 type="checkbox"
 checked={checked}
 onChange={() => toggleMembershipOrg(o.id)}
 className="rounded border-zinc-300"
 />
 <Building2 size={11} className="text-zinc-400" />
 <span className="flex-1 truncate">{o.name}</span>
 <span className="text-[10px] text-zinc-400 uppercase tracking-wider">{o.account_type || o.subscription_tier || ''}</span>
 </label>
 );
 })}
 </div>
 <div className="mt-3 flex items-center justify-end gap-2">
 <Button
 size="sm"
 variant="outline"
 onClick={closeMembershipEditor}
 className="text-xs"
 data-testid={`pulse-admin-membership-cancel-${a.id}`}
 >
 Cancel
 </Button>
 <Button
 size="sm"
 onClick={() => saveMemberships(a)}
 className="bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white text-xs"
 data-testid={`pulse-admin-membership-save-${a.id}`}
 >
 Save attachments
 </Button>
 </div>
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
