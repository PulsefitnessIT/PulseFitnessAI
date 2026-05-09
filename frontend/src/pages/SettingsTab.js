import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { Alert, AlertDescription } from '@/components/ui/alert';
import axios from 'axios';
import { toast } from 'sonner';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import { Users, UserPlus, Copy, Crown, Shield, User, Trash2, Building, Plus, Mail, Phone, Palette, Upload, Link2, CheckCircle, PoundSterling, Save, Edit3, Send, Wrench } from 'lucide-react';
import SupplierEquipmentWizard from './SupplierEquipmentWizard';
import SiconIntegrationTab from './SiconIntegrationTab';
import FaultTemplatesManager from './Dashboard/FaultTemplatesManager';
import LaunchReadinessPanel from '@/components/shared/LaunchReadinessPanel';

const SettingsTab = () => {
 const { user, API, applyBranding } = useAuth();
 const { t } = useTranslation();
 const [organization, setOrganization] = useState(null);
 const [staff, setStaff] = useState([]);
 const [invites, setInvites] = useState([]);
 const [showInviteDialog, setShowInviteDialog] = useState(false);
 const [inviteForm, setInviteForm] = useState({ email: '', role: 'staff', full_name: '' });
 const [suppliers, setSuppliers] = useState([]);
 const [showSupplierDialog, setShowSupplierDialog] = useState(false);
 const [editingSupplier, setEditingSupplier] = useState(null);
 const [supplierForm, setSupplierForm] = useState({ name: '', email: '', phone: '', contact_person: '', address: '', notes: '', callout_fee: '', labour_rate_per_hour: '', mileage_rate: '', parts_markup_pct: '', custom_items: [] });
 const [settingsSection, setSettingsSection] = useState('team');
 const [branding, setBranding] = useState({ primary_color: 'var(--color-brand-blue)', company_name: '', logo_url: '' });
 const [brandingSaving, setBrandingSaving] = useState(false);
 const [orgAddress, setOrgAddress] = useState('');
 const [orgPhone, setOrgPhone] = useState('');
 const [orgEmail, setOrgEmail] = useState('');
 const [orgContactPerson, setOrgContactPerson] = useState('');

 useEffect(() => {
 loadData();
 // eslint-disable-next-line react-hooks/exhaustive-deps
 }, [API, user?.role]);

 const loadData = async () => {
 const token = localStorage.getItem('token');
 try {
 const [orgRes, staffRes, invitesRes, supplierRes, orgDetailsRes] = await Promise.all([
 axios.get(`${API}/organization`, { headers: { Authorization: `Bearer ${token}` } }),
 user.role !== 'staff' ? axios.get(`${API}/organization/staff`, { headers: { Authorization: `Bearer ${token}` } }) : Promise.resolve({ data: { staff: [] } }),
 user.role !== 'staff' ? axios.get(`${API}/organization/invites`, { headers: { Authorization: `Bearer ${token}` } }) : Promise.resolve({ data: { invites: [] } }),
 axios.get(`${API}/suppliers`, { headers: { Authorization: `Bearer ${token}` } }),
 axios.get(`${API}/settings/org-details`, { headers: { Authorization: `Bearer ${token}` } }).catch(() => ({ data: {} }))
 ]);
 
 setOrganization(orgRes.data);
 setStaff(staffRes.data.staff || []);
 setInvites(invitesRes.data.invites || []);
 setSuppliers(supplierRes.data.suppliers || []);
 
 const od = orgDetailsRes.data || {};
 setOrgAddress(od.address || '');
 setOrgPhone(od.phone || '');
 setOrgEmail(od.email || '');
 setOrgContactPerson(od.contact_person || '');

 if (orgRes.data?.branding) {
 setBranding({
 primary_color: orgRes.data.branding.primary_color || 'var(--color-brand-blue)',
 company_name: orgRes.data.branding.company_name || orgRes.data.name || '',
 logo_url: orgRes.data.branding.logo_url || orgRes.data.logo_url || '',
 });
 } else {
 setBranding(b => ({ ...b, company_name: orgRes.data?.name || '', logo_url: orgRes.data?.logo_url || '' }));
 }
 } catch (error) {
 console.error('Failed to load data:', error);
 }
 };

 const handleInviteStaff = async (e) => {
 e.preventDefault();
 const token = localStorage.getItem('token');
 
 try {
 const response = await axios.post(
 `${API}/organization/invite`,
 inviteForm,
 { headers: { Authorization: `Bearer ${token}` } }
 );
 
 notify.success(response.data.message);
 setShowInviteDialog(false);
 setInviteForm({ email: '', role: 'staff', full_name: '' });
 loadData();
 } catch (error) {
 notifyApiError(notify, error, 'Failed to send invite');
 }
 };

 const handleCopyCompanyCode = () => {
 navigator.clipboard.writeText(organization.company_code);
 notify.success('Company code copied to clipboard!');
 };

 const handleRemoveStaff = async (staffId) => {
 if (!confirm('Are you sure you want to remove this staff member?')) return;
 
 const token = localStorage.getItem('token');
 try {
 await axios.delete(`${API}/organization/staff/${staffId}`, {
 headers: { Authorization: `Bearer ${token}` }
 });
 notify.success('Staff member removed');
 loadData();
 } catch (error) {
 notify.error('Failed to remove staff member');
 }
 };

 const handleChangeRole = async (staffId, newRole) => {
 const token = localStorage.getItem('token');
 try {
 await axios.patch(`${API}/organization/staff/${staffId}/role?role=${newRole}`, {}, {
 headers: { Authorization: `Bearer ${token}` }
 });
 notify.success('Role updated');
 loadData();
 } catch (error) {
 notify.error('Failed to update role');
 }
 };

 const handleUpdatePermissions = async (staffId, patch) => {
 const token = localStorage.getItem('token');
 try {
 await axios.patch(`${API}/organization/staff/${staffId}/permissions`, patch, {
 headers: { Authorization: `Bearer ${token}` }
 });
 notify.success('Permissions updated');
 loadData();
 } catch (error) {
 notifyApiError(notify, error, 'Failed to update permissions');
 }
 };

 const getRoleIcon = (role) => {
 if (role === 'owner') return <Crown className="text-yellow-400" size={18} />;
 if (role === 'manager') return <Shield className="text-blue-400" size={18} />;
 return <User className="text-[var(--color-text-muted)]" size={18} />;
 };

 const getRoleBadgeColor = (role) => {
 if (role === 'owner') return 'bg-yellow-500/20 text-yellow-400';
 if (role === 'manager') return 'bg-blue-500/20 text-blue-400';
 return 'bg-gray-500/20 text-gray-400';
 };

 const [wizardSupplier, setWizardSupplier] = useState(null);

 const handleAddSupplier = async (e) => {
 e.preventDefault();
 const token = localStorage.getItem('token');
 try {
 if (editingSupplier) {
 await axios.put(`${API}/suppliers/${editingSupplier.id}`, supplierForm, { headers: { Authorization: `Bearer ${token}` } });
 notify.success(t('settings.supplier_added'));
 setShowSupplierDialog(false);
 setEditingSupplier(null);
 setSupplierForm({ name: '', email: '', phone: '', contact_person: '', address: '', notes: '', callout_fee: '', labour_rate_per_hour: '', mileage_rate: '', parts_markup_pct: '', custom_items: [] });
 loadData();
 } else {
 // Create with welcome deferred — the wizard dispatches it at the end,
 // with the equipment CSV attached.
 const r = await axios.post(
 `${API}/suppliers`,
 { ...supplierForm, send_welcome: false },
 { headers: { Authorization: `Bearer ${token}` } },
 );
 notify.success(t('settings.supplier_added'));
 setShowSupplierDialog(false);
 setSupplierForm({ name: '', email: '', phone: '', contact_person: '', address: '', notes: '', callout_fee: '', labour_rate_per_hour: '', mileage_rate: '', parts_markup_pct: '', custom_items: [] });
 loadData();
 // Auto-open the equipment wizard (tier-gated on the feature itself
 // via the welcome-email backend logic — harmless for orgs where
 // welcome emails don't apply).
 setWizardSupplier(r.data);
 }
 } catch (error) {
 notify.error(t('settings.supplier_failed'));
 }
 };

 const handleEditSupplier = (supplier) => {
 setEditingSupplier(supplier);
 setSupplierForm({
 name: supplier.name || '',
 email: supplier.email || '',
 phone: supplier.phone || '',
 contact_person: supplier.contact_person || '',
 address: supplier.address || '',
 notes: supplier.notes || '',
 callout_fee: supplier.callout_fee || '',
 labour_rate_per_hour: supplier.labour_rate_per_hour || '',
 mileage_rate: supplier.mileage_rate || '',
 parts_markup_pct: supplier.parts_markup_pct || '',
 custom_items: supplier.custom_items || []
 });
 setShowSupplierDialog(true);
 };

 const handleDeleteSupplier = async (id) => {
 const token = localStorage.getItem('token');
 try {
 await axios.delete(`${API}/suppliers/${id}`, { headers: { Authorization: `Bearer ${token}` } });
 notify.success(t('settings.supplier_added'));
 loadData();
 } catch (error) {
 notify.error(t('settings.supplier_failed'));
 }
 };

 const handleSendWelcomeEmail = async (supplier) => {
 if (!supplier.email) {
 notify.error('This supplier has no email on file — add one first.');
 return;
 }
 const token = localStorage.getItem('token');
 try {
 await axios.post(`${API}/suppliers/${supplier.id}/send-welcome`, {}, { headers: { Authorization: `Bearer ${token}` } });
 notify.success(`Welcome email sent to ${supplier.name}`, { duration: 6000 });
 loadData();
 } catch (err) {
 notifyApiError(notify, err, 'Failed to send welcome email');
 }
 };

 return (
 <div className="space-y-6" data-testid="settings-tab">
 <div>
 <h2 className="text-2xl font-semibold text-[var(--theme-text)]">{t('settings.title')}</h2>
 <p className="text-[var(--color-text-muted)]">Manage your gym, team, suppliers, and onboarding</p>
 </div>

 {/* Section Navigation */}
 <div className="flex items-center gap-2 border-b border-white/10 pb-4 overflow-x-auto">
 {['team', 'suppliers', 'branding', 'templates', 'sicon', 'onboarding', 'launch'].map(s => {
 const active = settingsSection === s;
 return (
 <Button key={s} size="sm" variant="outline"
 className={`flex-shrink-0 ${active ? 'bg-[var(--color-brand-blue)] text-white border-transparent' : 'border-white/10 text-[var(--color-text-muted)]'}`}
 style={active ? { color: 'var(--color-white)' } : undefined}
 onClick={() => setSettingsSection(s)} data-testid={`settings-section-${s}`}>
 {s === 'team' ? t('settings.team_org')
 : s === 'suppliers' ? t('settings.suppliers')
 : s === 'branding' ? t('settings.white_label')
 : s === 'templates' ? 'Fault Templates'
 : s === 'sicon' ? 'Sicon'
 : s === 'launch' ? 'Launch readiness'
 : t('settings.onboarding')}
 </Button>
 );
 })}
 </div>

 {/* Fault Templates Section */}
 {settingsSection === 'templates' && (
 <FaultTemplatesManager API={API} user={user} />
 )}

 {settingsSection === 'launch' && (
 <div data-testid="settings-launch">
 <LaunchReadinessPanel />
 </div>
 )}

 {/* Team & Org Section */}
 {settingsSection === 'team' && <>
 {/* Organization Info */}
 {organization && (
 <Card className="bg-[var(--theme-surface)] border-[var(--theme-border)] p-6" data-testid="org-info-card">
 <h3 className="text-xl font-semibold text-[var(--theme-text)] mb-4">{t('settings.team_org')}</h3>
 <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
 <div>
 <Label className="text-[var(--color-text-muted)]">{t('settings.org_name')}</Label>
 <p className="text-[var(--theme-text)] text-lg">{organization.name}</p>
 </div>
 {user.role !== 'staff' && (
 <div>
 <Label className="text-[var(--color-text-muted)]">Company Code</Label>
 <div className="flex items-center space-x-2">
 <code className="text-[var(--theme-text)] text-lg font-mono bg-[var(--color-ink-alt)] px-3 py-1 rounded border border-white/10">
 {organization.company_code}
 </code>
 <Button
 size="sm"
 variant="outline"
 onClick={handleCopyCompanyCode}
 className="border-white/10 text-[var(--theme-text)]"
 data-testid="copy-company-code-btn"
 >
 <Copy size={16} />
 </Button>
 </div>
 <p className="text-xs text-[var(--color-text-muted)] mt-1">Share this code with staff to join your organization</p>
 </div>
 )}
 </div>
 </Card>
 )}

 {/* Staff Management (Only for Owner & Manager) */}
 {user.role !== 'staff' && (
 <>
 <div className="flex items-center justify-between">
 <h3 className="text-xl font-semibold text-[var(--theme-text)]">{t('settings.team_members')}</h3>
 <Button
 onClick={() => setShowInviteDialog(true)}
 className=""
 data-testid="invite-staff-btn"
 >
 <UserPlus size={18} className="mr-2" /> {t('settings.invite_member')}
 </Button>
 </div>

 {/* Staff List */}
 <div className="space-y-3">
 {staff.map(member => {
 const isOwner = member.role === 'owner';
 const overrides = member.module_overrides || {};
 const isCurrentManagerOrOwner = ['owner', 'manager'].includes(user.role);
 const canEditPerms = isCurrentManagerOrOwner && !isOwner && member.id !== user.id;
 return (
 <Card key={member.id} className="bg-[var(--theme-surface)] border-[var(--theme-border)] p-5" data-testid={`staff-card-${member.id}`}>
 <div className="flex items-center justify-between flex-wrap gap-3">
 <div className="flex items-center space-x-4">
 {getRoleIcon(member.role)}
 <div>
 <p className="text-[var(--theme-text)] font-semibold">{member.full_name}</p>
 <p className="text-[var(--color-text-muted)] text-sm">{member.email}</p>
 </div>
 </div>
 <div className="flex items-center space-x-3">
 <Badge className={getRoleBadgeColor(member.role)}>
 {member.role}
 </Badge>
 {user.role === 'owner' && member.role !== 'owner' && (
 <>
 <Select
 value={member.role}
 onValueChange={(newRole) => handleChangeRole(member.id, newRole)}
 >
 <SelectTrigger className="w-32 bg-[var(--theme-surface-hover)] border-[var(--theme-border)] text-[var(--theme-text)]" data-testid={`role-selector-${member.id}`}>
 <SelectValue />
 </SelectTrigger>
 <SelectContent className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)]">
 <SelectItem value="manager">Manager</SelectItem>
 <SelectItem value="staff">Staff</SelectItem>
 </SelectContent>
 </Select>
 <Button
 size="sm"
 variant="outline"
 onClick={() => handleRemoveStaff(member.id)}
 className="border-red-500/50 text-red-400 hover:bg-red-500/10"
 data-testid={`remove-staff-btn-${member.id}`}
 >
 <Trash2 size={16} />
 </Button>
 </>
 )}
 </div>
 </div>

 {canEditPerms && (
 <div className="mt-4 pt-4 border-t border-white/5" data-testid={`staff-perms-${member.id}`}>
 <p className="text-[10px] uppercase tracking-wider font-bold text-[var(--color-text-muted)] mb-2">
 Module access · per-staff overrides
 </p>
 <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
 {[
 { key: 'memberships', label: 'Memberships' },
 { key: 'marketing', label: 'Marketing' },
 { key: 'crm', label: 'CRM' },
 ].map(mod => {
 const enabled = mod.key in overrides ? !!overrides[mod.key] : true;
 return (
 <div key={mod.key} className="flex items-center justify-between p-2 bg-[var(--color-ink-alt)] rounded-md border border-white/5">
 <span className="text-xs text-[var(--theme-text)]">{mod.label}</span>
 <Switch
 checked={enabled}
 onCheckedChange={(val) => handleUpdatePermissions(member.id, {
 module_overrides: { ...overrides, [mod.key]: val },
 })}
 data-testid={`staff-${member.id}-mod-${mod.key}`}
 />
 </div>
 );
 })}
 </div>
 <div className="flex items-center justify-between mt-3 p-2 bg-[var(--color-ink-alt)] rounded-md border border-white/5">
 <div>
 <p className="text-xs text-[var(--theme-text)] font-medium">Group Fitness timetable — view only</p>
 <p className="text-[10px] text-[var(--color-text-muted)]">Blocks creating, editing or cancelling classes & sessions.</p>
 </div>
 <Switch
 checked={!!member.timetable_view_only}
 onCheckedChange={(val) => handleUpdatePermissions(member.id, { timetable_view_only: val })}
 data-testid={`staff-${member.id}-view-only`}
 />
 </div>
 <p className="text-[10px] text-[var(--color-text-faint)] mt-2">
 Per-staff toggles can only restrict — they cannot grant access the organisation doesn't already have.
 </p>
 </div>
 )}
 </Card>
 );
 })}
 </div>

 {/* Pending Invites */}
 {invites.length > 0 && (
 <>
 <h3 className="text-xl font-semibold text-[var(--theme-text)] mt-8">Pending Invites</h3>
 <div className="space-y-3">
 {invites.filter(inv => inv.status === 'pending').map(invite => (
 <Card key={invite.id} className="bg-[var(--theme-surface)] border-yellow-500/30 p-5" data-testid={`invite-card-${invite.id}`}>
 <div className="flex items-center justify-between">
 <div>
 <p className="text-[var(--theme-text)] font-semibold">{invite.email}</p>
 <p className="text-[var(--color-text-muted)] text-sm">Invited as {invite.role}</p>
 </div>
 <Badge className="bg-yellow-500/20 text-yellow-400">Pending</Badge>
 </div>
 </Card>
 ))}
 </div>
 </>
 )}
 </>
 )}

 {/* Role Info Alert */}
 <Alert className="bg-[rgb(var(--rgb-brand-blue)/0.1)] border-[rgb(var(--rgb-brand-blue)/0.3)]">
 <AlertDescription className="text-[var(--theme-text)]">
 <strong>Your Role: {user.role}</strong><br />
 {user.role === 'owner' && 'You have full access and can manage all staff members.'}
 {user.role === 'manager' && 'You can manage equipment, invite staff, and view all data.'}
 {user.role === 'staff' && 'You can log issues and view equipment. Contact your manager for additional access.'}
 </AlertDescription>
 </Alert>

 {/* Invite Staff Dialog */}
 <Dialog open={showInviteDialog} onOpenChange={setShowInviteDialog}>
 <DialogContent className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)]" data-testid="invite-dialog">
 <DialogHeader>
 <DialogTitle className="text-[var(--theme-text)]">{t('settings.invite_member')}</DialogTitle>
 </DialogHeader>
 <form onSubmit={handleInviteStaff} className="space-y-4">
 <div>
 <Label htmlFor="invite_email" className="text-[var(--theme-text)]">Email Address</Label>
 <Input
 id="invite_email"
 type="email"
 value={inviteForm.email}
 onChange={(e) => setInviteForm({...inviteForm, email: e.target.value})}
 required
 placeholder="staff@example.com"
 className="bg-[var(--theme-surface-hover)] border-[var(--theme-border)] text-[var(--theme-text)] mt-2"
 data-testid="invite-email-input"
 />
 </div>

 <div>
 <Label htmlFor="invite_name" className="text-[var(--theme-text)]">Full Name (Optional)</Label>
 <Input
 id="invite_name"
 value={inviteForm.full_name}
 onChange={(e) => setInviteForm({...inviteForm, full_name: e.target.value})}
 placeholder="John Smith"
 className="bg-[var(--theme-surface-hover)] border-[var(--theme-border)] text-[var(--theme-text)] mt-2"
 data-testid="invite-name-input"
 />
 </div>

 <div>
 <Label htmlFor="invite_role" className="text-[var(--theme-text)]">Role</Label>
 <Select
 value={inviteForm.role}
 onValueChange={(val) => setInviteForm({...inviteForm, role: val})}
 >
 <SelectTrigger className="bg-[var(--theme-surface-hover)] border-[var(--theme-border)] text-[var(--theme-text)] mt-2" data-testid="invite-role-select">
 <SelectValue />
 </SelectTrigger>
 <SelectContent className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)]">
 <SelectItem value="manager">Manager - Can manage equipment and invite staff</SelectItem>
 <SelectItem value="staff">Staff - Can log issues and view equipment</SelectItem>
 </SelectContent>
 </Select>
 </div>

 <Alert className="bg-[var(--theme-surface-hover)] border-[var(--theme-border)]">
 <AlertDescription className="text-[var(--color-text-muted)] text-sm">
 Staff member will need to register using your company code: <strong className="text-[var(--theme-text)]">{organization?.company_code}</strong>
 </AlertDescription>
 </Alert>

 <Button type="submit" className="w-full" data-testid="send-invite-btn">
 Send Invite
 </Button>
 </form>
 </DialogContent>
 </Dialog>
 </>}

 {/* Suppliers Section */}
 {settingsSection === 'suppliers' && (
 <div className="space-y-4">
 <div className="flex items-center justify-between">
 <h3 className="text-xl font-semibold text-[var(--theme-text)]">Supplier Directory</h3>
 <Button onClick={() => { setEditingSupplier(null); setSupplierForm({ name: '', email: '', phone: '', contact_person: '', address: '', notes: '', callout_fee: '', labour_rate_per_hour: '', mileage_rate: '', parts_markup_pct: '', custom_items: [] }); setShowSupplierDialog(true); }} className="" data-testid="add-supplier-btn">
 <Plus size={18} className="mr-1" /> {t('settings.add_supplier')}
 </Button>
 </div>
 <p className="text-[var(--color-text-muted)] text-sm">{t('settings.suppliers')} — manage your equipment suppliers with their specific callout pricing.</p>
 
 <div className="grid grid-cols-1 gap-3">
 {suppliers.map(s => (
 <Card key={s.id} className="bg-[var(--theme-surface)] border-[var(--theme-border)] p-5" data-testid={`supplier-${s.id}`}>
 <div className="flex items-start justify-between">
 <div className="flex items-start gap-3">
 <div className="w-10 h-10 rounded-lg bg-[rgb(var(--rgb-brand-blue)/0.2)] flex items-center justify-center flex-shrink-0">
 <Building size={20} className="text-[var(--color-brand-blue)]" />
 </div>
 <div className="flex-1">
 <p className="text-[var(--theme-text)] font-semibold">{s.name}</p>
 {s.contact_person && <p className="text-[var(--color-text-muted)] text-sm">{s.contact_person}</p>}
 <div className="flex items-center gap-4 mt-1">
 {s.email && <span className="text-[var(--color-text-muted)] text-sm flex items-center gap-1"><Mail size={12} />{s.email}</span>}
 {s.phone && <span className="text-[var(--color-text-muted)] text-sm flex items-center gap-1"><Phone size={12} />{s.phone}</span>}
 </div>
 {(s.callout_fee || s.labour_rate_per_hour) ? (
 <div className="flex items-center gap-3 mt-2 flex-wrap">
 {!!s.callout_fee && <Badge className="bg-green-500/10 text-green-400 text-xs">{t('settings.callout_fee')}: £{s.callout_fee}</Badge>}
 {!!s.labour_rate_per_hour && <Badge className="bg-blue-500/10 text-blue-400 text-xs">{t('settings.labour_rate')}: £{s.labour_rate_per_hour}/hr</Badge>}
 {!!s.mileage_rate && <Badge className="bg-purple-500/10 text-purple-400 text-xs">{t('settings.mileage_rate')}: £{s.mileage_rate}/mi</Badge>}
 {!!s.parts_markup_pct && <Badge className="bg-amber-500/10 text-amber-400 text-xs">{t('settings.parts_markup')}: {s.parts_markup_pct}%</Badge>}
 </div>
 ) : (
 <p className="text-amber-400/70 text-xs mt-2 italic">No pricing set — click Edit to add callout rates</p>
 )}
 </div>
 </div>
 <div className="flex items-center gap-1">
 <Button
 size="sm" variant="ghost"
 className="text-[var(--color-text-muted)] hover:text-indigo-400 hover:bg-indigo-500/10"
 onClick={() => setWizardSupplier(s)}
 title="Link machines to this supplier"
 data-testid={`link-machines-supplier-${s.id}`}
 >
 <Wrench size={16} />
 </Button>
 {s.email && (
 <Button
 size="sm" variant="ghost"
 className={`text-[var(--color-text-muted)] hover:text-emerald-400 hover:bg-emerald-500/10 ${s.welcome_email_sent_at ? 'text-emerald-400' : ''}`}
 onClick={() => handleSendWelcomeEmail(s)}
 title={s.welcome_email_sent_at ? `Welcome email sent — send again?` : 'Send welcome email to this supplier'}
 data-testid={`send-welcome-supplier-${s.id}`}
 >
 <Send size={16} />
 </Button>
 )}
 <Button size="sm" variant="ghost" className="text-[var(--color-text-muted)] hover:text-[var(--theme-text)] hover:bg-white/10" onClick={() => handleEditSupplier(s)} data-testid={`edit-supplier-${s.id}`}>
 <Edit3 size={16} />
 </Button>
 <Button size="sm" variant="ghost" className="text-red-400 hover:bg-red-500/10" onClick={() => handleDeleteSupplier(s.id)} data-testid={`delete-supplier-${s.id}`}>
 <Trash2 size={16} />
 </Button>
 </div>
 </div>
 {s.welcome_email_sent_at && (
 <p className="text-emerald-400/70 text-[10px] mt-2 flex items-center gap-1">
 <CheckCircle size={10} /> Welcome email sent {new Date(s.welcome_email_sent_at).toLocaleDateString()}
 </p>
 )}
 </Card>
 ))}
 {suppliers.length === 0 && (
 <Card className="bg-[var(--theme-surface)] border-[var(--theme-border)] p-8 text-center">
 <Building size={40} className="mx-auto mb-3 text-[var(--color-text-muted)]" />
 <p className="text-[var(--color-text-muted)]">{t('settings.no_suppliers')}</p>
 </Card>
 )}
 </div>

 <Dialog open={showSupplierDialog} onOpenChange={(open) => { setShowSupplierDialog(open); if (!open) { setEditingSupplier(null); setSupplierForm({ name: '', email: '', phone: '', contact_person: '', address: '', notes: '', callout_fee: '', labour_rate_per_hour: '', mileage_rate: '', parts_markup_pct: '', custom_items: [] }); } }}>
 <DialogContent className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] max-h-[85vh] overflow-y-auto" data-testid="supplier-dialog">
 <DialogHeader><DialogTitle className="text-[var(--theme-text)]">{editingSupplier ? `${t('common.edit')} — ${editingSupplier.name}` : t('settings.add_supplier')}</DialogTitle></DialogHeader>
 <form onSubmit={handleAddSupplier} className="space-y-3">
 <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
 <div>
 <Label className="text-[var(--theme-text)]">{t('settings.supplier_name')}</Label>
 <Input value={supplierForm.name} onChange={e => setSupplierForm({...supplierForm, name: e.target.value})} required className="bg-[var(--theme-surface-hover)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1" data-testid="supplier-name-input" />
 </div>
 <div>
 <Label className="text-[var(--theme-text)]">{t('settings.email')}</Label>
 <Input type="email" value={supplierForm.email} onChange={e => setSupplierForm({...supplierForm, email: e.target.value})} className="bg-[var(--theme-surface-hover)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1" data-testid="supplier-email-input" />
 </div>
 <div>
 <Label className="text-[var(--theme-text)]">{t('settings.phone')}</Label>
 <Input value={supplierForm.phone} onChange={e => setSupplierForm({...supplierForm, phone: e.target.value})} className="bg-[var(--theme-surface-hover)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1" data-testid="supplier-phone-input" />
 </div>
 <div>
 <Label className="text-[var(--theme-text)]">{t('settings.supplier_contact')}</Label>
 <Input value={supplierForm.contact_person} onChange={e => setSupplierForm({...supplierForm, contact_person: e.target.value})} className="bg-[var(--theme-surface-hover)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1" data-testid="supplier-contact-input" />
 </div>
 </div>
 <div>
 <Label className="text-[var(--theme-text)]">{t('settings.supplier_address')}</Label>
 <Input value={supplierForm.address} onChange={e => setSupplierForm({...supplierForm, address: e.target.value})} className="bg-[var(--theme-surface-hover)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1" />
 </div>

 {/* Pricing Section */}
 <div className="border-t border-white/10 pt-3 mt-3">
 <h4 className="text-[var(--theme-text)] font-medium mb-3 flex items-center gap-2">
 <PoundSterling size={16} /> {t('settings.standard_prices')}
 </h4>
 <p className="text-[var(--color-text-muted)] text-xs mb-3">{t('settings.standard_prices_desc')}</p>
 <div className="grid grid-cols-2 gap-3">
 <div>
 <Label className="text-[var(--color-text-muted)] text-sm">{t('settings.callout_fee')}</Label>
 <Input type="number" step="0.01" value={supplierForm.callout_fee} onChange={e => setSupplierForm({...supplierForm, callout_fee: e.target.value})} placeholder="0.00" className="bg-[var(--theme-surface-hover)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1" data-testid="supplier-callout-fee" />
 </div>
 <div>
 <Label className="text-[var(--color-text-muted)] text-sm">{t('settings.labour_rate')}</Label>
 <Input type="number" step="0.01" value={supplierForm.labour_rate_per_hour} onChange={e => setSupplierForm({...supplierForm, labour_rate_per_hour: e.target.value})} placeholder="0.00" className="bg-[var(--theme-surface-hover)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1" data-testid="supplier-labour-rate" />
 </div>
 <div>
 <Label className="text-[var(--color-text-muted)] text-sm">{t('settings.mileage_rate')}</Label>
 <Input type="number" step="0.01" value={supplierForm.mileage_rate} onChange={e => setSupplierForm({...supplierForm, mileage_rate: e.target.value})} placeholder="0.00" className="bg-[var(--theme-surface-hover)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1" data-testid="supplier-mileage-rate" />
 </div>
 <div>
 <Label className="text-[var(--color-text-muted)] text-sm">{t('settings.parts_markup')}</Label>
 <Input type="number" step="0.01" value={supplierForm.parts_markup_pct} onChange={e => setSupplierForm({...supplierForm, parts_markup_pct: e.target.value})} placeholder="0" className="bg-[var(--theme-surface-hover)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1" data-testid="supplier-parts-markup" />
 </div>
 </div>
 </div>

 {/* Custom Line Items */}
 <div className="border-t border-white/10 pt-3 mt-3">
 <div className="flex items-center justify-between mb-2">
 <Label className="text-[var(--theme-text)] font-medium">{t('settings.custom_items')}</Label>
 <Button type="button" size="sm" variant="outline" className="border-white/10 text-[var(--color-text-muted)] text-xs"
 onClick={() => setSupplierForm({...supplierForm, custom_items: [...(supplierForm.custom_items || []), { description: '', quantity: 1, unit_price: 0 }]})}
 data-testid="add-custom-item-btn">
 <Plus size={12} className="mr-1" /> {t('settings.add_custom_item')}
 </Button>
 </div>
 <p className="text-[var(--color-text-muted)] text-xs mb-2">{t('settings.custom_items_desc')}</p>
 {(supplierForm.custom_items || []).map((item, idx) => (
 <div key={item.description || `custom-item-${idx}`} className="flex gap-2 mb-2 items-center">
 <Input value={item.description} onChange={e => {
 const updated = [...supplierForm.custom_items];
 updated[idx] = {...updated[idx], description: e.target.value};
 setSupplierForm({...supplierForm, custom_items: updated});
 }} placeholder="Item description" className="bg-[var(--theme-surface-hover)] border-[var(--theme-border)] text-[var(--theme-text)] flex-1" />
 <Input type="number" step="0.01" value={item.unit_price} onChange={e => {
 const updated = [...supplierForm.custom_items];
 updated[idx] = {...updated[idx], unit_price: parseFloat(e.target.value) || 0};
 setSupplierForm({...supplierForm, custom_items: updated});
 }} placeholder="£" className="bg-[var(--theme-surface-hover)] border-[var(--theme-border)] text-[var(--theme-text)] w-24" />
 <Button type="button" size="sm" variant="ghost" className="text-red-400" onClick={() => {
 setSupplierForm({...supplierForm, custom_items: supplierForm.custom_items.filter((_, i) => i !== idx)});
 }}><Trash2 size={14} /></Button>
 </div>
 ))}
 </div>

 <Button type="submit" className="w-full" data-testid="save-supplier-btn">{t('common.save')}</Button>
 </form>
 </DialogContent>
 </Dialog>
 </div>
 )}

 {/* PO Defaults Section */}
 {/* Gym Details Section - moved from PO Defaults */}
 {settingsSection === 'team' && organization && (
 <Card className="bg-[var(--theme-surface)] border-[var(--theme-border)] p-6" data-testid="gym-details-card">
 <h4 className="text-lg font-semibold text-[var(--theme-text)] mb-4 flex items-center gap-2">
 <Building size={18} /> {t('settings.gym_details')} <span className="text-[var(--color-text-muted)] text-sm font-normal">({t('settings.gym_details_desc')})</span>
 </h4>
 <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
 <div>
 <Label className="text-[var(--color-text-muted)]">{t('settings.address')}</Label>
 <Input value={orgAddress} onChange={e => setOrgAddress(e.target.value)} className="bg-[var(--theme-surface-hover)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1" data-testid="org-address-input" />
 </div>
 <div>
 <Label className="text-[var(--color-text-muted)]">{t('settings.contact_person')}</Label>
 <Input value={orgContactPerson} onChange={e => setOrgContactPerson(e.target.value)} className="bg-[var(--theme-surface-hover)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1" data-testid="org-contact-input" />
 </div>
 <div>
 <Label className="text-[var(--color-text-muted)]">{t('settings.phone')}</Label>
 <Input value={orgPhone} onChange={e => setOrgPhone(e.target.value)} className="bg-[var(--theme-surface-hover)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1" data-testid="org-phone-input" />
 </div>
 <div>
 <Label className="text-[var(--color-text-muted)]">{t('settings.email')}</Label>
 <Input type="email" value={orgEmail} onChange={e => setOrgEmail(e.target.value)} className="bg-[var(--theme-surface-hover)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1" data-testid="org-email-input" />
 </div>
 </div>
 <Button className="mt-4 bg-[var(--color-brand-blue)] text-white" onClick={async () => {
 const token = localStorage.getItem('token');
 try {
 await axios.put(`${API}/settings/org-details`, {
 address: orgAddress, phone: orgPhone, email: orgEmail, contact_person: orgContactPerson
 }, { headers: { Authorization: `Bearer ${token}` } });
 notify.success(t('settings.gym_saved'));
 } catch { notify.error(t('settings.gym_failed')); }
 }} data-testid="save-org-details-btn">
 <Save size={14} className="mr-1" /> {t('settings.save_gym_details')}
 </Button>
 </Card>
 )}

 {/* White Label / Branding Section */}
 {settingsSection === 'branding' && (
 <div className="space-y-6" data-testid="branding-section">
 <div>
 <h3 className="text-xl font-semibold text-[var(--theme-text)]">White Label Branding</h3>
 <p className="text-[var(--color-text-muted)] text-sm">Customise the platform with your own branding. Your logo and colours will appear on reports, purchase orders, and shared pages.</p>
 </div>

 <Card className="bg-[var(--theme-surface)] border-[var(--theme-border)] p-6 space-y-5">
 <div>
 <Label className="text-[var(--theme-text)]">Company Display Name</Label>
 <Input
 value={branding.company_name}
 onChange={e => setBranding({ ...branding, company_name: e.target.value })}
 placeholder="Your Gym Name"
 className="bg-[var(--theme-surface-hover)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1"
 data-testid="branding-company-name"
 />
 <p className="text-[var(--color-text-muted)] text-xs mt-1">Shown on PDFs, reports, and public pages</p>
 </div>

 <div>
 <Label className="text-[var(--theme-text)]">Brand Colour</Label>
 <div className="flex items-center gap-3 mt-1">
 <input
 type="color"
 value={branding.primary_color}
 onChange={e => setBranding({ ...branding, primary_color: e.target.value })}
 className="w-12 h-10 rounded border border-white/10 cursor-pointer bg-transparent"
 data-testid="branding-color-picker"
 />
 <Input
 value={branding.primary_color}
 onChange={e => setBranding({ ...branding, primary_color: e.target.value })}
 className="bg-[var(--theme-surface-hover)] border-[var(--theme-border)] text-[var(--theme-text)] w-32 font-mono"
 data-testid="branding-color-input"
 />
 <div className="h-10 flex-1 rounded-lg" style={{ backgroundColor: branding.primary_color }} />
 </div>
 </div>

 <div>
 <Label className="text-[var(--theme-text)]">Logo</Label>
 {branding.logo_url && (
 <div className="mt-2 mb-3 p-4 bg-[var(--color-ink-alt)] rounded-lg inline-block">
 <img 
 src={branding.logo_url.startsWith('http') || branding.logo_url.startsWith('/') ? branding.logo_url : `${API}/public/files/${branding.logo_url}`} 
 alt="Logo" 
 className="h-16 object-contain" 
 data-testid="branding-logo-preview"
 onError={(e) => e.target.style.display = 'none'}
 />
 </div>
 )}
 <label className="cursor-pointer block">
 <input
 type="file"
 className="hidden"
 accept="image/*"
 onChange={async (e) => {
 const file = e.target.files?.[0];
 if (!file) return;
 const token = localStorage.getItem('token');
 try {
 const formData = new FormData();
 formData.append('file', file);
 const res = await axios.post(`${API}/files/upload?category=branding`, formData, {
 headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'multipart/form-data' }
 });
 const fileUrl = `${API}/public/files/${res.data.id}`;
 setBranding({ ...branding, logo_url: fileUrl });
 notify.success('Logo uploaded');
 } catch { notify.error('Upload failed'); }
 e.target.value = '';
 }}
 data-testid="branding-logo-upload"
 />
 <div className="border-2 border-dashed border-white/10 rounded-lg p-4 text-center hover:border-[rgb(var(--rgb-brand-blue)/0.3)] transition-colors mt-1">
 <Upload size={20} className="mx-auto mb-1 text-[var(--color-text-muted)]" />
 <span className="text-[var(--color-text-muted)] text-sm">{branding.logo_url ? 'Change logo' : 'Upload your logo (PNG, JPG, SVG)'}</span>
 </div>
 </label>
 </div>

 {/* Preview */}
 <div className="border-t border-white/10 pt-5">
 <Label className="text-[var(--theme-text)] mb-3 block">Preview</Label>
 <div className="p-4 bg-white rounded-lg">
 <div className="flex items-center gap-3 border-b pb-3 mb-3" style={{ borderColor: branding.primary_color }}>
 {branding.logo_url && (
 <img 
 src={branding.logo_url.startsWith('http') || branding.logo_url.startsWith('/') ? branding.logo_url : `${API}/public/files/${branding.logo_url}`} 
 alt="Logo" 
 className="h-8 object-contain"
 onError={(e) => e.target.style.display = 'none'}
 />
 )}
 <span className="font-bold text-lg" style={{ color: branding.primary_color }}>{branding.company_name || 'Your Company'}</span>
 </div>
 <div className="text-sm text-gray-600">
 <p>Purchase Order: PO-2026-001</p>
 <p className="mt-1 text-gray-400">This is how your branding appears on PDFs, reports, and shared pages.</p>
 </div>
 </div>
 </div>

 <Button
 onClick={async () => {
 setBrandingSaving(true);
 const token = localStorage.getItem('token');
 try {
 await axios.patch(`${API}/organization/branding`, branding, {
 headers: { Authorization: `Bearer ${token}` }
 });
 applyBranding(branding);
 notify.success('Branding saved! Changes applied to the app.');
 loadData();
 } catch { notify.error('Failed to save branding'); }
 finally { setBrandingSaving(false); }
 }}
 disabled={brandingSaving}
 className="w-full"
 data-testid="save-branding-btn"
 >
 {brandingSaving ? 'Saving...' : 'Save Branding'}
 </Button>
 </Card>
 </div>
 )}

 {/* Sicon Integration Section */}
 {settingsSection === 'sicon' && (
 <SiconIntegrationTab />
 )}

 {/* Onboarding Section - Step-by-Step Wizard */}
 {settingsSection === 'onboarding' && (
 <OnboardingStepWizard 
 API={API} 
 onGoToSection={setSettingsSection} 
 />
 )}

 <SupplierEquipmentWizard
 supplier={wizardSupplier}
 open={!!wizardSupplier}
 onClose={() => setWizardSupplier(null)}
 onComplete={loadData}
 />
 </div>
 );
};

const OnboardingStepWizard = ({ API, onGoToSection }) => {
 const [currentStep, setCurrentStep] = useState(0);
 const [supplierForm, setSupplierForm] = useState({ name: '', email: '', phone: '', contact_person: '' });
 const [addedSuppliers, setAddedSuppliers] = useState([]);
 const [equipmentFile, setEquipmentFile] = useState(null);
 const [importing, setImporting] = useState(false);
 const [importResult, setImportResult] = useState(null);
 const [inviteEmail, setInviteEmail] = useState('');
 const [inviteRole, setInviteRole] = useState('staff');
 const [invitedMembers, setInvitedMembers] = useState([]);
 const [orgInfo, setOrgInfo] = useState(null);

 useEffect(() => {
 const token = localStorage.getItem('token');
 axios.get(`${API}/organization`, { headers: { Authorization: `Bearer ${token}` } })
 .then(res => setOrgInfo(res.data))
 .catch(() => {});
 }, [API]);

 const steps = [
 { title: 'Organisation', desc: 'Verify your organisation details' },
 { title: 'Suppliers', desc: 'Add equipment suppliers' },
 { title: 'Equipment', desc: 'Import your gym equipment' },
 { title: 'Team', desc: 'Invite your team members' },
 { title: 'Complete', desc: 'You\'re all set!' }
 ];

 const handleAddSupplier = async (e) => {
 e.preventDefault();
 const token = localStorage.getItem('token');
 try {
 await axios.post(`${API}/suppliers`, supplierForm, { headers: { Authorization: `Bearer ${token}` } });
 setAddedSuppliers([...addedSuppliers, supplierForm.name]);
 setSupplierForm({ name: '', email: '', phone: '', contact_person: '' });
 notify.success('Supplier added');
 } catch { notify.error('Failed to add supplier'); }
 };

 const handleImportCSV = async () => {
 if (!equipmentFile) return;
 setImporting(true);
 const token = localStorage.getItem('token');
 try {
 const formData = new FormData();
 formData.append('file', equipmentFile);
 const res = await axios.post(`${API}/equipment/import`, formData, {
 headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'multipart/form-data' }
 });
 setImportResult(res.data);
 notify.success(`Imported ${res.data.imported || 0} equipment items`);
 } catch { notify.error('Import failed'); }
 finally { setImporting(false); }
 };

 const handleInvite = async (e) => {
 e.preventDefault();
 const token = localStorage.getItem('token');
 try {
 await axios.post(`${API}/organization/invite`, { email: inviteEmail, role: inviteRole, full_name: '' }, {
 headers: { Authorization: `Bearer ${token}` }
 });
 setInvitedMembers([...invitedMembers, inviteEmail]);
 setInviteEmail('');
 notify.success('Invite sent');
 } catch (err) { notifyApiError(notify, err, 'Failed to invite'); }
 };

 return (
 <div className="space-y-6" data-testid="onboarding-wizard">
 <div>
 <h3 className="text-xl font-semibold text-[var(--theme-text)]">Onboarding Setup</h3>
 <p className="text-[var(--color-text-muted)] text-sm">Follow these steps to get your gym set up on GymAxis AI</p>
 </div>

 {/* Step Progress */}
 <div className="flex items-center justify-between" data-testid="onboarding-progress">
 {steps.map((step, idx) => (
 <div key={idx} className="flex items-center flex-1">
 <div className="flex flex-col items-center">
 <div
 className={`w-9 h-9 rounded-full flex items-center justify-center text-sm font-bold border-2 transition-colors ${
 idx < currentStep ? 'bg-green-500 border-green-500 text-[var(--theme-text)]' :
 idx === currentStep ? 'border-[var(--brand-color)] text-[var(--theme-text)] bg-[var(--brand-color)]' :
 'border-white/20 text-[var(--color-text-muted)] bg-transparent'
 }`}
 data-testid={`onboarding-step-${idx}`}
 >
 {idx < currentStep ? '✓' : idx + 1}
 </div>
 <span className={`text-xs mt-1 hidden sm:block ${idx <= currentStep ? 'text-[var(--theme-text)]' : 'text-[var(--color-text-muted)]'}`}>{step.title}</span>
 </div>
 {idx < steps.length - 1 && (
 <div className={`flex-1 h-0.5 mx-2 ${idx < currentStep ? 'bg-green-500' : 'bg-white/10'}`} />
 )}
 </div>
 ))}
 </div>

 {/* Step Content */}
 <Card className="bg-[var(--theme-surface)] border-[var(--theme-border)] p-6">
 <h4 className="text-lg font-semibold text-[var(--theme-text)] mb-1">{steps[currentStep].title}</h4>
 <p className="text-[var(--color-text-muted)] text-sm mb-5">{steps[currentStep].desc}</p>

 {/* Step 0: Organisation */}
 {currentStep === 0 && (
 <div className="space-y-4" data-testid="onboarding-step-org">
 {orgInfo ? (
 <div className="space-y-3">
 <div className="p-4 bg-[var(--color-ink-alt)] rounded-lg border border-white/10">
 <p className="text-[var(--color-text-muted)] text-sm">Organisation Name</p>
 <p className="text-[var(--theme-text)] text-lg font-semibold">{orgInfo.name}</p>
 </div>
 <div className="p-4 bg-[var(--color-ink-alt)] rounded-lg border border-white/10">
 <p className="text-[var(--color-text-muted)] text-sm">Company Code</p>
 <p className="text-[var(--theme-text)] text-lg font-mono">{orgInfo.company_code}</p>
 <p className="text-[var(--color-text-muted)] text-xs mt-1">Share this with staff to join your organisation</p>
 </div>
 <div className="p-4 bg-[var(--color-ink-alt)] rounded-lg border border-white/10">
 <p className="text-[var(--color-text-muted)] text-sm">Subscription</p>
 <p className="text-[var(--theme-text)] text-lg">{orgInfo.plan || 'Free'}</p>
 </div>
 </div>
 ) : (
 <p className="text-[var(--color-text-muted)]">Loading organisation details...</p>
 )}
 </div>
 )}

 {/* Step 1: Suppliers */}
 {currentStep === 1 && (
 <div className="space-y-4" data-testid="onboarding-step-suppliers">
 <form onSubmit={handleAddSupplier} className="grid grid-cols-1 sm:grid-cols-2 gap-3">
 <div>
 <Label className="text-[var(--color-text-muted)] text-sm">Company Name *</Label>
 <Input value={supplierForm.name} onChange={e => setSupplierForm({...supplierForm, name: e.target.value})} required placeholder="e.g. Pulse Fitness" className="bg-[var(--theme-surface-hover)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1" data-testid="onboard-supplier-name" />
 </div>
 <div>
 <Label className="text-[var(--color-text-muted)] text-sm">Email</Label>
 <Input type="email" value={supplierForm.email} onChange={e => setSupplierForm({...supplierForm, email: e.target.value})} placeholder="service@supplier.com" className="bg-[var(--theme-surface-hover)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1" data-testid="onboard-supplier-email" />
 </div>
 <div>
 <Label className="text-[var(--color-text-muted)] text-sm">Phone</Label>
 <Input value={supplierForm.phone} onChange={e => setSupplierForm({...supplierForm, phone: e.target.value})} placeholder="+44 1234 567890" className="bg-[var(--theme-surface-hover)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1" />
 </div>
 <div>
 <Label className="text-[var(--color-text-muted)] text-sm">Contact Person</Label>
 <Input value={supplierForm.contact_person} onChange={e => setSupplierForm({...supplierForm, contact_person: e.target.value})} placeholder="John Smith" className="bg-[var(--theme-surface-hover)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1" />
 </div>
 <div className="sm:col-span-2">
 <Button type="submit" size="sm" className="text-[var(--theme-text)]" style={{ backgroundColor: 'var(--brand-color)' }} data-testid="onboard-add-supplier-btn">
 <Plus size={14} className="mr-1" /> Add Supplier
 </Button>
 </div>
 </form>
 {addedSuppliers.length > 0 && (
 <div className="mt-3">
 <p className="text-[var(--color-text-muted)] text-sm mb-2">Added during this session:</p>
 <div className="flex flex-wrap gap-2">
 {addedSuppliers.map((s) => (
 <Badge key={s} className="bg-green-500/20 text-green-400">{s}</Badge>
 ))}
 </div>
 </div>
 )}
 <p className="text-[var(--color-text-muted)] text-xs">You can skip this step and add suppliers later from Settings.</p>
 </div>
 )}

 {/* Step 2: Equipment Import */}
 {currentStep === 2 && (
 <div className="space-y-4" data-testid="onboarding-step-equipment">
 <div className="p-4 bg-[var(--color-ink-alt)] rounded-lg border border-white/10">
 <p className="text-[var(--theme-text)] font-semibold mb-2">Import Equipment via CSV</p>
 <p className="text-[var(--color-text-muted)] text-sm mb-3">Upload a CSV file with columns: name, equipment_type, manufacturer, model, serial_number, location, purchase_date, warranty_expiry</p>
 <Input 
 type="file" 
 accept=".csv" 
 onChange={e => setEquipmentFile(e.target.files[0])} 
 className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)]" 
 data-testid="onboard-csv-input" 
 />
 {equipmentFile && (
 <Button onClick={handleImportCSV} disabled={importing} size="sm" className="mt-3 text-[var(--theme-text)]" style={{ backgroundColor: 'var(--brand-color)' }} data-testid="onboard-import-btn">
 {importing ? 'Importing...' : 'Import Equipment'}
 </Button>
 )}
 {importResult && (
 <p className="text-green-400 text-sm mt-2">Successfully imported {importResult.imported || 0} items</p>
 )}
 </div>
 <p className="text-[var(--color-text-muted)] text-xs">You can also add equipment manually from the Equipment tab. Skip this step if preferred.</p>
 </div>
 )}

 {/* Step 3: Invite Team */}
 {currentStep === 3 && (
 <div className="space-y-4" data-testid="onboarding-step-team">
 <form onSubmit={handleInvite} className="flex items-end gap-3">
 <div className="flex-1">
 <Label className="text-[var(--color-text-muted)] text-sm">Email Address</Label>
 <Input type="email" value={inviteEmail} onChange={e => setInviteEmail(e.target.value)} required placeholder="staff@yourgym.com" className="bg-[var(--theme-surface-hover)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1" data-testid="onboard-invite-email" />
 </div>
 <div className="w-36">
 <Label className="text-[var(--color-text-muted)] text-sm">Role</Label>
 <Select value={inviteRole} onValueChange={setInviteRole}>
 <SelectTrigger className="bg-[var(--theme-surface-hover)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1" data-testid="onboard-invite-role">
 <SelectValue />
 </SelectTrigger>
 <SelectContent className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)]">
 <SelectItem value="manager">Manager</SelectItem>
 <SelectItem value="staff">Staff</SelectItem>
 </SelectContent>
 </Select>
 </div>
 <Button type="submit" size="sm" className="text-[var(--theme-text)]" style={{ backgroundColor: 'var(--brand-color)' }} data-testid="onboard-send-invite-btn">
 Send Invite
 </Button>
 </form>
 {invitedMembers.length > 0 && (
 <div className="mt-3">
 <p className="text-[var(--color-text-muted)] text-sm mb-2">Invites sent:</p>
 <div className="flex flex-wrap gap-2">
 {invitedMembers.map((email, i) => (
 <Badge key={i} className="bg-green-500/20 text-green-400">{email}</Badge>
 ))}
 </div>
 </div>
 )}
 {orgInfo?.company_code && (
 <div className="p-4 bg-[var(--color-ink-alt)] rounded-lg border border-white/10">
 <p className="text-[var(--color-text-muted)] text-sm">Or share your company code for self-registration:</p>
 <p className="text-[var(--theme-text)] font-mono text-lg mt-1">{orgInfo.company_code}</p>
 </div>
 )}
 </div>
 )}

 {/* Step 4: Complete */}
 {currentStep === 4 && (
 <div className="text-center py-6" data-testid="onboarding-step-complete">
 <div className="w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-4" style={{ backgroundColor: 'var(--brand-color)', opacity: 0.2 }}>
 <CheckCircle size={32} style={{ color: 'var(--brand-color)' }} />
 </div>
 <h4 className="text-xl font-semibold text-[var(--theme-text)] mb-2">You're all set!</h4>
 <p className="text-[var(--color-text-muted)] text-sm mb-4">Your gym is configured and ready to use. You can always adjust settings later.</p>
 <div className="grid grid-cols-2 gap-3 max-w-md mx-auto">
 <div className="p-3 bg-[var(--color-ink-alt)] rounded-lg border border-white/10 text-center">
 <p className="text-[var(--theme-text)] font-semibold">{addedSuppliers.length}</p>
 <p className="text-[var(--color-text-muted)] text-xs">Suppliers Added</p>
 </div>
 <div className="p-3 bg-[var(--color-ink-alt)] rounded-lg border border-white/10 text-center">
 <p className="text-[var(--theme-text)] font-semibold">{invitedMembers.length}</p>
 <p className="text-[var(--color-text-muted)] text-xs">Team Invited</p>
 </div>
 </div>
 </div>
 )}
 </Card>

 {/* Navigation Buttons */}
 <div className="flex items-center justify-between">
 <Button
 variant="outline"
 className="border-white/10 text-[var(--color-text-muted)]"
 onClick={() => setCurrentStep(Math.max(0, currentStep - 1))}
 disabled={currentStep === 0}
 data-testid="onboarding-back-btn"
 >
 Back
 </Button>
 <div className="flex items-center gap-2">
 {currentStep < steps.length - 1 && currentStep > 0 && (
 <Button
 variant="outline"
 className="border-white/10 text-[var(--color-text-muted)]"
 onClick={() => setCurrentStep(currentStep + 1)}
 data-testid="onboarding-skip-btn"
 >
 Skip
 </Button>
 )}
 {currentStep < steps.length - 1 ? (
 <Button
 className="text-[var(--theme-text)]"
 style={{ backgroundColor: 'var(--brand-color)' }}
 onClick={() => setCurrentStep(currentStep + 1)}
 data-testid="onboarding-next-btn"
 >
 Next
 </Button>
 ) : (
 <Button
 className="text-[var(--theme-text)]"
 style={{ backgroundColor: 'var(--brand-color)' }}
 onClick={() => onGoToSection('team')}
 data-testid="onboarding-finish-btn"
 >
 Done
 </Button>
 )}
 </div>
 </div>
 </div>
 );
};

export default SettingsTab;
